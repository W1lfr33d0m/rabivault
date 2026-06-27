from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django_ratelimit.decorators import ratelimit

from apps.accounts.decorators import mfa_required
from apps.audit.utils import write_audit_log
from apps.compliance.utils import organization_has_active_baa
from apps.organizations.models import Facility

from .forms import DocumentUploadForm, VaultFolderForm
from .models import Document, VaultFolder
from .permissions import (
    documents_for_user,
    user_can_access_facility,
    user_can_download_document,
    user_can_upload_document,
    user_can_view_document,
)
from .tasks import scan_document_for_virus
from .utils import calculate_sha256, generate_presigned_download_url
from .forms import detect_document_type

def _workspace_lists_for_user(user):
    profile = getattr(user, "profile", None)

    if not profile or not profile.active:
        return Facility.objects.none(), VaultFolder.objects.none()

    if profile.role == "platform_admin":
        return (
            Facility.objects.filter(active=True).select_related("organization"),
            VaultFolder.objects.all().select_related("organization", "facility", "parent"),
        )

    if not profile.organization_id:
        return Facility.objects.none(), VaultFolder.objects.none()

    facilities = Facility.objects.filter(organization=profile.organization, active=True)
    folders = VaultFolder.objects.filter(organization=profile.organization).select_related("facility", "parent")

    if profile.role not in ["org_admin", "auditor"]:
        facility_ids = profile.facilities.values_list("id", flat=True)
        facilities = facilities.filter(id__in=facility_ids)
        folders = folders.filter(facility_id__in=facility_ids)

    return facilities, folders


@login_required
def vault_dashboard(request):
    docs = documents_for_user(request.user).filter(status="active")

    context = {
        "total_documents": docs.count(),
        "expired_documents": docs.filter(expires_at__lt=timezone.now().date()).count(),
        "recent_documents": docs[:10],
    }

    return render(request, "vault/dashboard.html", context)


@login_required
def document_list(request):
    docs = documents_for_user(request.user).filter(status="active")

    query = request.GET.get("q", "").strip()
    document_type = request.GET.get("type", "")
    facility_id = request.GET.get("facility", "")
    folder_id = request.GET.get("folder", "")

    if query:
        docs = docs.filter(
            Q(title__icontains=query) |
            Q(original_filename__icontains=query) |
            Q(checksum_sha256__icontains=query)
        )

    if document_type:
        docs = docs.filter(document_type=document_type)

    if facility_id:
        docs = docs.filter(facility_id=facility_id)

    if folder_id:
        docs = docs.filter(folder_id=folder_id)

    facilities, folders = _workspace_lists_for_user(request.user)

    docs = docs.select_related("organization", "facility", "folder", "uploaded_by")
    paginator = Paginator(docs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "documents": page_obj.object_list,
        "page_obj": page_obj,
        "query": query,
        "document_type": document_type,
        "facility_id": facility_id,
        "folder_id": folder_id,
        "facilities": facilities,
        "folders": folders,
        "document_type_choices": Document.DOCUMENT_TYPE_CHOICES,
    }

    return render(request, "vault/document_list.html", context)


@login_required
def document_detail(request, public_id):
    document = get_object_or_404(Document, public_id=public_id)

    if not user_can_view_document(request.user, document):
        raise PermissionDenied("You do not have access to this document.")

    write_audit_log(
        request=request,
        action="view_document",
        object_type="Document",
        object_id=document.public_id,
        metadata={"title": document.title},
    )

    return render(request, "vault/document_detail.html", {"document": document})


@login_required
@mfa_required
@ratelimit(key="user", rate="30/h", block=True)
def document_upload(request):
    profile = request.user.profile

    if profile.role == "platform_admin":
        messages.error(request, "Platform admins must select an organization before uploading.")
        return redirect("vault:document_list")

    organization = profile.organization

    if not organization:
        messages.error(request, "Your user is not assigned to an organization.")
        return redirect("vault:document_list")

    if not organization_has_active_baa(organization):
        messages.error(request, "A signed Business Associate Agreement is required before uploading PHI.")
        return redirect("vault:document_list")

    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
    else:
        form = DocumentUploadForm()

    form.fields["facility"].queryset = Facility.objects.filter(
        organization=organization,
        active=True,
    )
    form.fields["folder"].queryset = VaultFolder.objects.filter(organization=organization)

    if profile.role not in ["org_admin"]:
        facility_ids = profile.facilities.values_list("id", flat=True)
        form.fields["facility"].queryset = form.fields["facility"].queryset.filter(id__in=facility_ids)
        form.fields["folder"].queryset = form.fields["folder"].queryset.filter(facility_id__in=facility_ids)

    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        document.organization = request.user.profile.organization
        document.uploaded_by = request.user
        document.document_type = detect_document_type(document.file)
        document.original_filename = document.file.name
        document.file_size = document.file.size
        document.content_type = getattr(document.file.file, "content_type", "")
        document.save()
        form.save_m2m()

        facility = document.facility

        if document.folder and document.folder.organization_id != organization.id:
            raise PermissionDenied("The selected folder does not belong to your organization.")

        if not user_can_upload_document(request.user, organization, facility):
            raise PermissionDenied("You do not have permission to upload here.")

        document.checksum_sha256 = calculate_sha256(document.file)
        document.save()

        scan_document_for_virus.delay(document.id)

        write_audit_log(
            request=request,
            action="upload_document",
            object_type="Document",
            object_id=document.public_id,
            metadata={
                "title": document.title,
                "filename": document.original_filename,
                "checksum_sha256": document.checksum_sha256,
            },
        )

        messages.success(request, "Document uploaded successfully. Antivirus scanning has been queued.")
        return redirect("vault:document_detail", public_id=document.public_id)

    return render(request, "vault/document_upload.html", {"form": form})


@login_required
@mfa_required
def folder_create(request):
    profile = request.user.profile

    if profile.role == "platform_admin":
        messages.error(request, "Platform admins must select an organization before creating folders.")
        return redirect("vault:document_list")

    organization = profile.organization

    if not organization:
        messages.error(request, "Your user is not assigned to an organization.")
        return redirect("vault:document_list")

    if request.method == "POST":
        form = VaultFolderForm(request.POST)
    else:
        form = VaultFolderForm()

    form.fields["facility"].queryset = Facility.objects.filter(organization=organization, active=True)
    form.fields["parent"].queryset = VaultFolder.objects.filter(organization=organization)

    if profile.role not in ["org_admin"]:
        facility_ids = profile.facilities.values_list("id", flat=True)
        form.fields["facility"].queryset = form.fields["facility"].queryset.filter(id__in=facility_ids)
        form.fields["parent"].queryset = form.fields["parent"].queryset.filter(facility_id__in=facility_ids)

    if request.method == "POST" and form.is_valid():
        folder = form.save(commit=False)
        folder.organization = organization

        if folder.facility and not user_can_access_facility(request.user, folder.facility):
            raise PermissionDenied("You do not have permission to create folders for this facility.")

        if folder.parent and folder.parent.organization_id != organization.id:
            raise PermissionDenied("The selected parent folder does not belong to your organization.")

        if folder.parent and folder.facility_id and folder.parent.facility_id and folder.parent.facility_id != folder.facility_id:
            raise PermissionDenied("The selected parent folder belongs to a different facility.")

        folder.save()

        write_audit_log(
            request=request,
            action="create_folder",
            object_type="VaultFolder",
            object_id=folder.id,
            metadata={"name": folder.name},
        )

        messages.success(request, "Folder created successfully.")
        return redirect("vault:document_list")

    return render(request, "vault/folder_form.html", {"form": form})


@login_required
@mfa_required
@ratelimit(key="user", rate="30/h", block=True)
def document_download(request, public_id):
    document = get_object_or_404(Document, public_id=public_id, status="active")

    if not user_can_download_document(request.user, document):
        raise PermissionDenied("You do not have permission to download this document.")

    if document.scan_status != "clean":
        raise PermissionDenied("This document is not available for download until antivirus scanning is complete.")

    signed_url = generate_presigned_download_url(document, expires_in=300)

    write_audit_log(
        request=request,
        action="download_document",
        object_type="Document",
        object_id=document.public_id,
        metadata={
            "title": document.title,
            "signed_url_expires_seconds": 300,
        },
    )

    return redirect(signed_url)


@login_required
@mfa_required
def document_delete(request, public_id):
    document = get_object_or_404(Document, public_id=public_id)

    if not user_can_view_document(request.user, document):
        raise PermissionDenied("You do not have access to this document.")

    profile = request.user.profile

    if profile.role not in ["platform_admin", "org_admin", "facility_manager"]:
        raise PermissionDenied("You do not have permission to delete documents.")

    if request.method == "POST":
        document.soft_delete(user=request.user)

        write_audit_log(
            request=request,
            action="delete_document",
            object_type="Document",
            object_id=document.public_id,
            metadata={"title": document.title},
        )

        messages.success(request, "Document deleted.")
        return redirect("vault:document_list")

    return render(request, "vault/document_confirm_delete.html", {"document": document})
