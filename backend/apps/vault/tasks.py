from celery import shared_task
from django.utils import timezone
from datetime import timedelta

import tempfile
from django.core.files.storage import default_storage

from django.conf import settings
from .ai_classifier import classify_document_with_ollama

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
def classify_document_with_ai(document_id):
    from .models import Document

    document = Document.objects.get(id=document_id)

    if not getattr(settings, "ENABLE_AI_CLASSIFICATION", False):
        document.ai_classification_status = "skipped"
        document.save(update_fields=["ai_classification_status"])
        return {"document_id": document_id, "status": "skipped"}

    if document.scan_status != "clean":
        document.ai_classification_status = "skipped"
        document.save(update_fields=["ai_classification_status"])
        return {
            "document_id": document_id,
            "status": "skipped",
            "reason": "Document is not clean.",
        }

    document.ai_classification_status = "processing"
    document.save(update_fields=["ai_classification_status"])

    try:
        # Simple MVP: use title + description first.
        # Later we can extract actual text from PDFs, DOCX, XLSX, PPTX.
        extracted_text = getattr(document, "description", "") or ""

        extracted_text = ""

        metadata_preview = f"""
        Title: {document.title}
        Detected document type: {document.document_type}
        Original filename: {document.file.name if document.file else ""}
        Scan status: {document.scan_status}
        """

        result = classify_document_with_ollama(
            title=document.title,
            document_type=document.document_type,
            extracted_text=metadata_preview,
        )

        document.ai_category = result.get("category", "other")
        document.ai_summary = result.get("summary", "")
        document.ai_suggested_tags = result.get("suggested_tags", [])
        document.ai_classification_result = result
        document.ai_classification_status = "completed"
        document.ai_classified_at = timezone.now()

        document.save(
            update_fields=[
                "ai_category",
                "ai_summary",
                "ai_suggested_tags",
                "ai_classification_result",
                "ai_classification_status",
                "ai_classified_at",
            ]
        )

        return {
            "document_id": document_id,
            "status": "completed",
            "category": document.ai_category,
        }

    except Exception as exc:
        document.ai_classification_status = "failed"
        document.ai_classification_result = {"error": str(exc)}
        document.save(
            update_fields=[
                "ai_classification_status",
                "ai_classification_result",
            ]
        )

        return {
            "document_id": document_id,
            "status": "failed",
            "error": str(exc),
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

        classify_document_with_ai.delay(document.id)

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
