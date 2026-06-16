import profile

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.utils import timezone

from apps.audit.utils import write_audit_log
from apps.accounts.decorators import mfa_required
from apps.organizations.models import Organization, Facility
from .forms import DocumentUploadForm
from .models import Document, VaultFolder
from .permissions import (
    documents_for_user,
    user_can_download_document,
    user_can_view_document,
    user_can_upload_document,
)
from django.shortcuts import redirect
from .utils import calculate_sha256, generate_presigned_download_url
from .permissions import user_can_download_document
from .tasks import scan_document_for_virus
from django_ratelimit.decorators import ratelimit
from apps.compliance.utils import organization_has_active_baa


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

    query = request.GET.get("q")
    document_type = request.GET.get("type")
    facility_id = request.GET.get("facility")

    if query:
        docs = docs.filter(title__icontains=query)

    if document_type:
        docs = docs.filter(document_type=document_type)

    if facility_id:
        docs = docs.filter(facility_id=facility_id)

    context = {
        "documents": docs,
        "query": query or "",
        "document_type": document_type or "",
        "facility_id": facility_id or "",
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
        metadata={"title": document.title}
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

        if form.is_valid():
            document = form.save(commit=False)
            document.organization = organization
            document.uploaded_by = request.user
            document.original_filename = document.file.name
            document.file_size = document.file.size
            document.content_type = getattr(document.file.file, "content_type", "")

            facility = document.facility

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
                }
            )

            messages.success(request, "Document uploaded successfully.")
            return redirect("vault:document_detail", public_id=document.public_id)
    else:
        form = DocumentUploadForm()

        if profile.role != "platform_admin":
            form.fields["facility"].queryset = Facility.objects.filter(
                organization=organization,
                active=True
            )

            form.fields["folder"].queryset = VaultFolder.objects.filter(
                organization=organization
            )

    return render(request, "vault/document_upload.html", {"form": form})


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
        }
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
            metadata={"title": document.title}
        )

        messages.success(request, "Document deleted.")
        return redirect("vault:document_list")

    return render(request, "vault/document_confirm_delete.html", {"document": document})
