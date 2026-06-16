from django.contrib import admin
from .models import VaultFolder, Document, DocumentVersion, DocumentShare


@admin.register(VaultFolder)
class VaultFolderAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "facility", "parent", "created_at")
    search_fields = ("name", "organization__name", "facility__name")
    list_filter = ("organization",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "organization",
        "facility",
        "document_type",
        "status",
        "version",
        "uploaded_by",
        "created_at",
    )
    search_fields = (
        "title",
        "organization__name",
        "facility__name",
        "original_filename",
        "checksum_sha256",
    )
    list_filter = ("status", "document_type", "organization")
    readonly_fields = (
        "public_id",
        "checksum_sha256",
        "file_size",
        "content_type",
        "created_at",
        "updated_at",
    )


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ("document", "version", "uploaded_by", "created_at")
    search_fields = ("document__title", "checksum_sha256", "original_filename")

@admin.register(DocumentShare)
class DocumentShareAdmin(admin.ModelAdmin):
    list_display = ("document", "user", "permission", "granted_by", "created_at")
    list_filter = ("permission", "created_at")
    search_fields = ("document__title", "user__username", "user__email")