from django import forms
from .models import Document, VaultFolder


ALLOWED_CONTENT_TYPES = [
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
]

MAX_FILE_SIZE_MB = 25


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = [
            "title",
            "document_type",
            "facility",
            "folder",
            "file",
            "expires_at",
            "retention_until",
            "tags",
        ]

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]

        if uploaded_file.size > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise forms.ValidationError(f"File must be under {MAX_FILE_SIZE_MB} MB.")

        content_type = getattr(uploaded_file, "content_type", "")

        if content_type not in ALLOWED_CONTENT_TYPES:
            raise forms.ValidationError("This file type is not allowed.")

        return uploaded_file


class VaultFolderForm(forms.ModelForm):
    class Meta:
        model = VaultFolder
        fields = ["name", "facility", "parent"]
