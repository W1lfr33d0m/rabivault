import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.organizations.models import Organization, Facility


def document_upload_path(instance, filename):
    org_id = instance.organization_id or "unknown-org"
    facility_id = instance.facility_id or "org-level"
    document_id = instance.public_id or uuid.uuid4()

    return f"organizations/{org_id}/facilities/{facility_id}/documents/{document_id}/{filename}"


class VaultFolder(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="vault_folders"
    )
    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="vault_folders"
    )
    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "facility", "parent", "name")

    def __str__(self):
        return self.name


class Document(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("archived", "Archived"),
        ("deleted", "Deleted"),
    ]

    DOCUMENT_TYPE_CHOICES = [
        ("license", "License"),
        ("policy", "Policy"),
        ("inspection", "Inspection"),
        ("equipment", "Equipment"),
        ("contract", "Contract"),
        ("invoice", "Invoice"),
        ("training", "Training"),
        ("report", "Report"),
        ("other", "Other"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="documents"
    )

    facility = models.ForeignKey(
        Facility,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents"
    )

    folder = models.ForeignKey(
        VaultFolder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents"
    )

    title = models.CharField(max_length=255)

    document_type = models.CharField(
        max_length=100,
        choices=DOCUMENT_TYPE_CHOICES,
        default="other"
    )

    file = models.FileField(upload_to=document_upload_path)
    original_filename = models.CharField(max_length=255, blank=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_documents"
    )

    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="active")
    version = models.PositiveIntegerField(default=1)

    checksum_sha256 = models.CharField(max_length=64, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=120, blank=True)

    expires_at = models.DateField(null=True, blank=True)
    retention_until = models.DateField(null=True, blank=True)

    tags = models.JSONField(default=list, blank=True)

    deleted_at = models.DateTimeField(null=True, blank=True)

    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deleted_documents"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["facility", "status"]),
            models.Index(fields=["document_type"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return self.title

    def soft_delete(self, user=None):
        self.status = "deleted"
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=["status", "deleted_at", "deleted_by", "updated_at"])

    def restore(self):
        self.status = "active"
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["status", "deleted_at", "deleted_by", "updated_at"])

    @property
    def is_expired(self):
        if not self.expires_at:
            return False
        return self.expires_at < timezone.now().date()


class DocumentVersion(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="versions"
    )

    version = models.PositiveIntegerField()

    file = models.FileField(upload_to=document_upload_path)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    checksum_sha256 = models.CharField(max_length=64, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    original_filename = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("document", "version")
        ordering = ["-version"]

    def __str__(self):
        return f"{self.document.title} v{self.version}"
