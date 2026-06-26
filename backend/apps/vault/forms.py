import os
from django import forms
from .models import Document, VaultFolder


ALLOWED_CONTENT_TYPES = [
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
]

MAX_FILE_SIZE_MB = 500


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

        allowed_extensions = [
            ".pdf",
            ".jpg",
            ".jpeg",
            ".png",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".txt",
            ".csv",
            ".dcm",
            ".dicom",
            ".zip",
            ]

        ext = os.path.splitext(uploaded_file.name)[1].lower()

        if ext not in allowed_extensions:
            raise forms.ValidationError("This file type is not allowed.")

        return uploaded_file

class VaultFolderForm(forms.ModelForm):
    class Meta:
        model = VaultFolder
        fields = ["name", "facility", "parent"]
