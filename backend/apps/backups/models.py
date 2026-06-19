# Create your models here.
from django.conf import settings
from django.db import models


class BackupRestoreTest(models.Model):
    RESULT_CHOICES = [
        ("passed", "Passed"),
        ("failed", "Failed"),
        ("partial", "Partial"),
    ]

    backup_file = models.CharField(max_length=255)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="backup_restore_tests",
    )
    result = models.CharField(max_length=20, choices=RESULT_CHOICES)
    notes = models.TextField(blank=True)
    restore_started_at = models.DateTimeField()
    restore_completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.backup_file} - {self.result}"