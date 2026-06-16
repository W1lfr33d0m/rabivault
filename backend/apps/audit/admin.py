from django.contrib import admin
from .models import AuditLog, SecurityEvent

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "organization",
        "actor",
        "action",
        "object_type",
        "object_id",
        "ip_address",
    )
    list_filter = ("action", "created_at")
    search_fields = (
        "actor__username",
        "organization__name",
        "object_type",
        "object_id",
        "ip_address",
    )
    readonly_fields = (
        "organization",
        "actor",
        "action",
        "object_type",
        "object_id",
        "ip_address",
        "user_agent",
        "metadata",
        "created_at",
        "previous_hash",
        "current_hash",
    )

    def has_add_permission(self, request):
        return False

@admin.register(SecurityEvent)
class SecurityEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "organization", "actor", "severity", "event_type", "resolved")
    list_filter = ("severity", "event_type", "resolved", "created_at")
    search_fields = ("description", "actor__username", "organization__name")