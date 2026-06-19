from django.contrib import admin
from .models import BackupRestoreTest


@admin.register(BackupRestoreTest)
class BackupRestoreTestAdmin(admin.ModelAdmin):
    list_display = ("backup_file", "performed_by", "result", "restore_started_at", "restore_completed_at")
    list_filter = ("result", "created_at")
    search_fields = ("backup_file", "performed_by__username", "notes")