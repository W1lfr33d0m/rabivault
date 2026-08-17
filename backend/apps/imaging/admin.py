from django.contrib import admin

from .models import ImagingStudy, OrthancAccessToken


@admin.register(ImagingStudy)
class ImagingStudyAdmin(admin.ModelAdmin):
    list_display = (
        "study_description",
        "organization",
        "facility",
        "modality",
        "study_date",
        "labels_synced_at",
    )
    list_filter = ("organization", "facility", "modality")
    search_fields = ("orthanc_study_id", "study_instance_uid", "accession_number", "patient_identifier")
    readonly_fields = ("labels_synced_at", "created_at")
    autocomplete_fields = ("organization", "facility")


@admin.register(OrthancAccessToken)
class OrthancAccessTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "expires_at", "last_used_at")
    list_filter = ("user",)
    readonly_fields = ("token_hash", "user", "created_at", "expires_at", "last_used_at")

    def has_add_permission(self, request):
        return False
