import json
import os

from django import forms

from .models import Document, VaultFolder


ALLOWED_CONTENT_TYPES = [
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
    "application/zip",
    "application/x-zip-compressed",
    "application/dicom",
]

ALLOWED_EXTENSIONS = [
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

MAX_FILE_SIZE_MB = 500


class DocumentUploadForm(forms.ModelForm):
    tags = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "inspection, 2026, MRI"}),
        help_text="Use comma-separated tags. JSON lists are also accepted.",
    )

    class Meta:
        model = Document
        fields = [
            "title",
            "document_type",
            "document_category",
            "facility",
            "folder",
            "file",
            "modality",
            "study_date",
            "patient_identifier",
            "accession_number",
            "study_instance_uid",
            "expires_at",
            "retention_until",
            "tags",
        ]
        widgets = {
            "study_date": forms.DateInput(attrs={"type": "date"}),
            "expires_at": forms.DateInput(attrs={"type": "date"}),
            "retention_until": forms.DateInput(attrs={"type": "date"}),
            "modality": forms.TextInput(attrs={"placeholder": "CT, MR, MG, US..."}),
            "patient_identifier": forms.TextInput(attrs={"placeholder": "Use a facility-safe identifier"}),
            "accession_number": forms.TextInput(attrs={"placeholder": "Optional"}),
            "study_instance_uid": forms.TextInput(attrs={"placeholder": "Optional DICOM StudyInstanceUID"}),
        }

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]

        if uploaded_file.size > MAX_FILE_SIZE_MB * 1024 * 1024:
            raise forms.ValidationError(f"File must be under {MAX_FILE_SIZE_MB} MB.")

        ext = os.path.splitext(uploaded_file.name)[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError(
                "This file type is not allowed. Allowed types: "
                + ", ".join(ALLOWED_EXTENSIONS)
            )

        return uploaded_file

    def clean_tags(self):
        value = self.cleaned_data.get("tags", "")

        if not value:
            return []

        if isinstance(value, list):
            return value

        value = value.strip()

        if value.startswith("["):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise forms.ValidationError("Tags JSON is invalid.") from exc

            if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
                raise forms.ValidationError("Tags must be a list of text values.")

            return [item.strip() for item in parsed if item.strip()]

        return [item.strip() for item in value.split(",") if item.strip()]

    def clean(self):
        cleaned = super().clean()
        folder = cleaned.get("folder")
        facility = cleaned.get("facility")

        if folder and facility and folder.facility_id and folder.facility_id != facility.id:
            raise forms.ValidationError("The selected folder belongs to a different facility.")

        return cleaned


class VaultFolderForm(forms.ModelForm):
    class Meta:
        model = VaultFolder
        fields = ["name", "facility", "parent"]
