from django.contrib import admin
from .models import Organization, Facility


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "created_at")
    search_fields = ("name", "legal_name")


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "city", "state", "active")
    search_fields = ("name", "organization__name")
    list_filter = ("active", "state")
