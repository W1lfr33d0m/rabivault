import json
import uuid

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.decorators import mfa_required
from apps.audit.utils import write_audit_log

from .models import Document, VaultFolder
from .permissions import (
    documents_for_user,
    user_can_manage_document,
    user_can_manage_folder,
    user_can_upload_document,
)
from .views import _search_documents, _workspace_lists_for_user


def _json_error(message, code, status=400):
    return JsonResponse({"ok": False, "error": message, "code": code}, status=status)


def _parse_json_body(request):
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    return payload


def _serialize_folder(folder):
    return {
        "id": folder.id,
        "name": folder.name,
        "facility_id": folder.facility_id,
        "facility_name": folder.facility.name if folder.facility else None,
        "subfolder_count": folder.subfolder_count,
        "document_count": folder.document_count,
    }


def _serialize_document(document):
    return {
        "public_id": str(document.public_id),
        "title": document.title,
        "original_filename": document.original_filename,
        "document_type": document.document_type,
        "document_type_display": document.get_document_type_display(),
        "document_category_display": document.get_document_category_display(),
        "scan_status": document.scan_status,
        "scan_status_display": document.get_scan_status_display(),
        "status": document.status,
        "facility_id": document.facility_id,
        "facility_name": document.facility.name if document.facility else None,
        "folder_id": document.folder_id,
        "created_at": document.created_at.isoformat(),
        "file_size": document.file_size,
        "detail_url": reverse("vault:document_detail", args=[document.public_id]),
        "download_url": reverse("vault:document_download", args=[document.public_id]),
        "delete_url": reverse("vault:document_delete", args=[document.public_id]),
    }


@login_required
@require_GET
def folder_tree(request):
    _, folders_qs = _workspace_lists_for_user(request.user)

    parent_param = request.GET.get("parent", "").strip()
    parent_id = None

    if parent_param:
        try:
            parent_id = int(parent_param)
        except ValueError:
            return _json_error("Invalid parent id.", "invalid_parent", status=400)

        if not folders_qs.filter(id=parent_id).exists():
            return _json_error("Folder not found.", "not_found", status=404)

    children = (
        folders_qs.filter(parent_id=parent_id)
        .select_related("facility")
        .annotate(child_count=Count("children", distinct=True))
        .order_by("name")
    )

    return JsonResponse({
        "folders": [
            {
                "id": folder.id,
                "name": folder.name,
                "facility_id": folder.facility_id,
                "facility_name": folder.facility.name if folder.facility else None,
                "has_children": folder.child_count > 0,
            }
            for folder in children
        ]
    })


@login_required
@require_GET
def folder_contents(request):
    query = request.GET.get("q", "").strip()

    if query:
        documents = (
            _search_documents(documents_for_user(request.user).filter(status="active"), query)
            .select_related("facility", "folder")
            .order_by("-created_at")[:100]
        )

        return JsonResponse({
            "folder": None,
            "breadcrumbs": [{"id": None, "name": "Home"}],
            "folders": [],
            "documents": [_serialize_document(document) for document in documents],
            "can_upload": False,
            "can_create_folder": False,
            "can_delete_folder": False,
        })

    _, folders_qs = _workspace_lists_for_user(request.user)

    folder_param = request.GET.get("folder", "").strip()
    folder = None

    if folder_param:
        try:
            folder_id = int(folder_param)
        except ValueError:
            return _json_error("Invalid folder id.", "invalid_folder", status=400)

        folder = folders_qs.filter(id=folder_id).select_related("facility", "parent", "organization").first()

        if not folder:
            return _json_error("Folder not found.", "not_found", status=404)

    child_folders = list(
        folders_qs.filter(parent_id=folder.id if folder else None)
        .select_related("facility")
        .annotate(
            subfolder_count=Count("children", distinct=True),
            document_count=Count("documents", filter=Q(documents__status="active"), distinct=True),
        )
        .order_by("name")
    )

    documents = list(
        documents_for_user(request.user)
        .filter(status="active", folder_id=folder.id if folder else None)
        .select_related("facility", "folder")
        .order_by("-created_at")
    )

    breadcrumbs = [{"id": None, "name": "Home"}]

    if folder:
        chain = []
        node = folder

        while node:
            chain.append({"id": node.id, "name": node.name})
            node = node.parent

        breadcrumbs.extend(reversed(chain))

    profile = getattr(request.user, "profile", None)
    organization = folder.organization if folder else (profile.organization if profile else None)
    facility = folder.facility if folder else None

    can_upload = bool(organization) and user_can_upload_document(request.user, organization, facility)
    can_create_folder = bool(organization)
    can_delete_folder = bool(
        folder
        and not child_folders
        and not documents
        and user_can_manage_folder(request.user, folder)
    )

    return JsonResponse({
        "folder": {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "facility_id": folder.facility_id,
            "facility_name": folder.facility.name if folder.facility else None,
        } if folder else None,
        "breadcrumbs": breadcrumbs,
        "folders": [_serialize_folder(child) for child in child_folders],
        "documents": [_serialize_document(document) for document in documents],
        "can_upload": can_upload,
        "can_create_folder": can_create_folder,
        "can_delete_folder": can_delete_folder,
    })


@login_required
@mfa_required
@require_POST
def folder_move(request):
    payload = _parse_json_body(request)

    if payload is None:
        return _json_error("Invalid JSON body.", "invalid_body", status=400)

    try:
        folder_id = int(payload.get("folder_id"))
    except (TypeError, ValueError):
        return _json_error("folder_id is required.", "missing_folder_id", status=400)

    raw_new_parent_id = payload.get("new_parent_id")
    new_parent_id = None

    if raw_new_parent_id is not None:
        try:
            new_parent_id = int(raw_new_parent_id)
        except (TypeError, ValueError):
            return _json_error("new_parent_id must be an integer or null.", "invalid_new_parent_id", status=400)

    folder = get_object_or_404(VaultFolder, id=folder_id)

    if not user_can_manage_folder(request.user, folder):
        return _json_error("You do not have permission to move this folder.", "forbidden", status=403)

    new_parent = None

    if new_parent_id is not None:
        new_parent = get_object_or_404(VaultFolder, id=new_parent_id)

        if new_parent.organization_id != folder.organization_id:
            return _json_error(
                "The destination folder does not belong to your organization.", "org_mismatch", status=400
            )

        if new_parent.id == folder.id or new_parent.id in folder.get_descendant_ids():
            return _json_error(
                "Cannot move a folder into itself or one of its subfolders.", "cycle", status=400
            )

        if folder.facility_id and new_parent.facility_id and folder.facility_id != new_parent.facility_id:
            return _json_error(
                "The destination folder belongs to a different facility.", "facility_mismatch", status=400
            )

        if not user_can_manage_folder(request.user, new_parent):
            return _json_error(
                "You do not have permission to move folders into the destination.", "forbidden", status=403
            )

    duplicate_exists = VaultFolder.objects.filter(
        organization=folder.organization,
        facility=folder.facility,
        parent=new_parent,
        name=folder.name,
    ).exclude(pk=folder.pk).exists()

    if duplicate_exists:
        return _json_error(
            "A folder with this name already exists in the destination.", "duplicate_name", status=409
        )

    old_parent_id = folder.parent_id
    folder.parent = new_parent
    folder.save(update_fields=["parent"])

    write_audit_log(
        request=request,
        action="move_folder",
        object_type="VaultFolder",
        object_id=folder.id,
        metadata={
            "name": folder.name,
            "from_parent_id": old_parent_id,
            "to_parent_id": new_parent.id if new_parent else None,
        },
    )

    return JsonResponse({"ok": True, "folder_id": folder.id, "new_parent_id": new_parent.id if new_parent else None})


@login_required
@mfa_required
@require_POST
def folder_rename(request):
    payload = _parse_json_body(request)

    if payload is None:
        return _json_error("Invalid JSON body.", "invalid_body", status=400)

    try:
        folder_id = int(payload.get("folder_id"))
    except (TypeError, ValueError):
        return _json_error("folder_id is required.", "missing_folder_id", status=400)

    name = (payload.get("name") or "").strip()

    if not name:
        return _json_error("Folder name cannot be empty.", "invalid_name", status=400)

    if len(name) > 255:
        return _json_error("Folder name is too long.", "invalid_name", status=400)

    folder = get_object_or_404(VaultFolder, id=folder_id)

    if not user_can_manage_folder(request.user, folder):
        return _json_error("You do not have permission to rename this folder.", "forbidden", status=403)

    duplicate_exists = VaultFolder.objects.filter(
        organization=folder.organization,
        facility=folder.facility,
        parent=folder.parent,
        name=name,
    ).exclude(pk=folder.pk).exists()

    if duplicate_exists:
        return _json_error("A folder with this name already exists here.", "duplicate_name", status=409)

    old_name = folder.name
    folder.name = name
    folder.save(update_fields=["name"])

    write_audit_log(
        request=request,
        action="rename_folder",
        object_type="VaultFolder",
        object_id=folder.id,
        metadata={"old_name": old_name, "new_name": name},
    )

    return JsonResponse({"ok": True, "folder_id": folder.id, "name": folder.name})


@login_required
@mfa_required
@require_POST
def folder_delete(request):
    payload = _parse_json_body(request)

    if payload is None:
        return _json_error("Invalid JSON body.", "invalid_body", status=400)

    try:
        folder_id = int(payload.get("folder_id"))
    except (TypeError, ValueError):
        return _json_error("folder_id is required.", "missing_folder_id", status=400)

    folder = get_object_or_404(VaultFolder, id=folder_id)

    if not user_can_manage_folder(request.user, folder):
        return _json_error("You do not have permission to delete this folder.", "forbidden", status=403)

    if folder.children.exists():
        return _json_error(
            "This folder still contains subfolders. Move or delete them first.", "not_empty", status=409
        )

    if folder.documents.filter(status="active").exists():
        return _json_error(
            "This folder still contains documents. Move or delete them first.", "not_empty", status=409
        )

    folder_id_for_log = folder.id
    folder_name = folder.name
    facility_id = folder.facility_id

    folder.delete()

    write_audit_log(
        request=request,
        action="delete_folder",
        object_type="VaultFolder",
        object_id=folder_id_for_log,
        metadata={"name": folder_name, "facility_id": facility_id},
    )

    return JsonResponse({"ok": True, "folder_id": folder_id_for_log})


@login_required
@mfa_required
@require_POST
def document_move(request):
    payload = _parse_json_body(request)

    if payload is None:
        return _json_error("Invalid JSON body.", "invalid_body", status=400)

    try:
        public_id = uuid.UUID(str(payload.get("public_id")))
    except (TypeError, ValueError):
        return _json_error("A valid public_id is required.", "invalid_public_id", status=400)

    raw_folder_id = payload.get("folder_id")
    folder_id = None

    if raw_folder_id is not None:
        try:
            folder_id = int(raw_folder_id)
        except (TypeError, ValueError):
            return _json_error("folder_id must be an integer or null.", "invalid_folder_id", status=400)

    document = get_object_or_404(Document, public_id=public_id, status="active")

    if not user_can_manage_document(request.user, document):
        return _json_error("You do not have permission to move this document.", "forbidden", status=403)

    target_folder = None

    if folder_id is not None:
        target_folder = get_object_or_404(VaultFolder, id=folder_id)

        if target_folder.organization_id != document.organization_id:
            return _json_error(
                "The destination folder does not belong to your organization.", "org_mismatch", status=400
            )

        if target_folder.facility_id not in (None, document.facility_id):
            return _json_error(
                "The destination folder belongs to a different facility.", "facility_mismatch", status=400
            )

        target_facility = target_folder.facility
    else:
        target_facility = document.facility

    if not user_can_upload_document(request.user, document.organization, target_facility):
        return _json_error(
            "You do not have permission to place documents in the destination.", "forbidden", status=403
        )

    old_folder_id = document.folder_id
    document.folder = target_folder
    document.save(update_fields=["folder", "updated_at"])

    write_audit_log(
        request=request,
        action="move_document",
        object_type="Document",
        object_id=document.public_id,
        metadata={
            "title": document.title,
            "from_folder_id": old_folder_id,
            "to_folder_id": target_folder.id if target_folder else None,
        },
    )

    return JsonResponse({
        "ok": True,
        "public_id": str(document.public_id),
        "folder_id": target_folder.id if target_folder else None,
    })


@login_required
@mfa_required
@require_POST
def document_rename(request):
    payload = _parse_json_body(request)

    if payload is None:
        return _json_error("Invalid JSON body.", "invalid_body", status=400)

    try:
        public_id = uuid.UUID(str(payload.get("public_id")))
    except (TypeError, ValueError):
        return _json_error("A valid public_id is required.", "invalid_public_id", status=400)

    title = (payload.get("title") or "").strip()

    if not title:
        return _json_error("Title cannot be empty.", "invalid_title", status=400)

    if len(title) > 255:
        return _json_error("Title is too long.", "invalid_title", status=400)

    document = get_object_or_404(Document, public_id=public_id, status="active")

    if not user_can_manage_document(request.user, document):
        return _json_error("You do not have permission to rename this document.", "forbidden", status=403)

    old_title = document.title
    document.title = title
    document.save(update_fields=["title", "updated_at"])

    write_audit_log(
        request=request,
        action="rename_document",
        object_type="Document",
        object_id=document.public_id,
        metadata={"old_title": old_title, "new_title": title},
    )

    return JsonResponse({"ok": True, "public_id": str(document.public_id), "title": document.title})
