from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from .models import Document


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
