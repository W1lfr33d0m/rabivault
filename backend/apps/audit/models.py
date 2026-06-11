from django.conf import settings
from django.db import models
from apps.organizations.models import Organization


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ("login", "Login"),
        ("logout", "Logout"),
        ("failed_login", "Failed Login"),
        ("view_document", "View Document"),
        ("download_document", "Download Document"),
        ("upload_document", "Upload Document"),
        ("delete_document", "Delete Document"),
        ("restore_document", "Restore Document"),
        ("update_document", "Update Document"),
        ("permission_change", "Permission Change"),
        ("create_share", "Create Share"),
        ("export_package", "Export Package"),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs"
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs"
    )

    action = models.CharField(max_length=100, choices=ACTION_CHOICES)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=100, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action} by {self.actor} at {self.created_at}"
