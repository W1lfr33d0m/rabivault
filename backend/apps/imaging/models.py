from django.conf import settings
from django.db import models


class ImagingStudy(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="imaging_studies",
    )

    facility = models.ForeignKey(
        "organizations.Facility",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="imaging_studies",
    )

    orthanc_study_id = models.CharField(max_length=255, unique=True, blank=True)
    study_instance_uid = models.CharField(max_length=255, blank=True)
    accession_number = models.CharField(max_length=255, blank=True)
    patient_identifier = models.CharField(max_length=255, blank=True)
    modality = models.CharField(max_length=50, blank=True)
    study_description = models.CharField(max_length=255, blank=True)
    study_date = models.DateField(null=True, blank=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.study_description or self.study_instance_uid or str(self.id)
    