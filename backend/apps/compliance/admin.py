from django.contrib import admin
from .models import (
    BusinessAssociateAgreement,
    RetentionPolicy,
    AccessReview,
    Incident,
)


@admin.register(BusinessAssociateAgreement)
class BusinessAssociateAgreementAdmin(admin.ModelAdmin):
    list_display = ("organization", "status", "effective_date", "expiration_date", "created_at")
    list_filter = ("status",)
    search_fields = ("organization__name", "signed_by_name", "signed_by_email")


@admin.register(RetentionPolicy)
class RetentionPolicyAdmin(admin.ModelAdmin):
    list_display = ("organization", "name", "document_type", "retention_days", "auto_delete")
    list_filter = ("document_type", "auto_delete")


@admin.register(AccessReview)
class AccessReviewAdmin(admin.ModelAdmin):
    list_display = ("organization", "reviewed_by", "period_start", "period_end", "completed_at")


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "severity", "status", "detected_at")
    list_filter = ("severity", "status")
    search_fields = ("title", "description", "organization__name")