from celery import shared_task
from django.utils import timezone
from datetime import timedelta

import tempfile
from django.core.files.storage import default_storage

from apps.audit.utils import write_audit_log
from .models import Document
from .utils import scan_file_stream_with_clamav


@shared_task
def find_expiring_documents():
    today = timezone.now().date()
    soon = today + timedelta(days=30)

    documents = Document.objects.filter(
        status="active",
        expires_at__gte=today,
        expires_at__lte=soon,
    )

    count = documents.count()

    return {
        "expiring_documents": count,
        "date_checked": str(today),
    }

@shared_task
def scan_document_for_virus(document_id):
    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return {"error": "Document not found", "document_id": document_id}

    document.scan_status = "pending"
    document.save(update_fields=["scan_status"])

    try:
        with tempfile.NamedTemporaryFile(delete=True) as temp_file:
            with default_storage.open(document.file.name, "rb") as stored_file:
                for chunk in iter(lambda: stored_file.read(1024 * 1024), b""):
                    temp_file.write(chunk)

            temp_file.flush()
            temp_file.seek(0)

            clean, result = scan_file_stream_with_clamav(temp_file)

        if clean:
            document.scan_status = "clean"
            document.scan_result = ""
        else:
            document.scan_status = "infected"
            document.scan_result = str(result)

        document.scanned_at = timezone.now()
        document.save(
            update_fields=[
                "scan_status",
                "scan_result",
                "scanned_at",
            ]
        )

        write_audit_log(
            actor=document.uploaded_by,
            organization=document.organization,
            action="update_document",
            object_type="Document",
            object_id=document.public_id,
            metadata={
                "event": "antivirus_scan",
                "scan_status": document.scan_status,
                "scan_result": document.scan_result,
            },
        )

        return {
            "document_id": document.id,
            "scan_status": document.scan_status,
            "scan_result": document.scan_result,
        }

    except Exception as exc:
        document.scan_status = "failed"
        document.scan_result = str(exc)
        document.scanned_at = timezone.now()
        document.save(
            update_fields=[
                "scan_status",
                "scan_result",
                "scanned_at",
            ]
        )

        write_audit_log(
            actor=document.uploaded_by,
            organization=document.organization,
            action="update_document",
            object_type="Document",
            object_id=document.public_id,
            metadata={
                "event": "antivirus_scan_failed",
                "error": str(exc),
            },
        )

        return {
            "document_id": document.id,
            "scan_status": "failed",
            "error": str(exc),
        }


"""@shared_task
def scan_document_for_virus(document_id):
    document = Document.objects.get(id=document_id)

    try:
        file_path = document.file.path
    except NotImplementedError:
        document.scan_status = "failed"
        document.scan_result = "Storage backend does not support local file path. Implement temporary S3 download scanning."
        document.scanned_at = timezone.now()
        document.save(update_fields=["scan_status", "scan_result", "scanned_at"])
        return document.scan_result

    clean, result = scan_file_with_clamav(file_path)

    if clean:
        document.scan_status = "clean"
        document.scan_result = ""
    else:
        document.scan_status = "infected"
        document.scan_result = str(result)

    document.scanned_at = timezone.now()
    document.save(update_fields=["scan_status", "scan_result", "scanned_at"])

    write_audit_log(
        actor=document.uploaded_by,
        organization=document.organization,
        action="update_document",
        object_type="Document",
        object_id=document.public_id,
        metadata={
            "event": "antivirus_scan",
            "scan_status": document.scan_status,
            "scan_result": document.scan_result,
        }
    )

    return document.scan_status"""
