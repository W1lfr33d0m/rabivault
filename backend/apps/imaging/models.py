import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


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

    labels_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this study's organization/facility labels were pushed to Orthanc.",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.study_description or self.study_instance_uid or str(self.id)

    def orthanc_labels(self):
        """Labels this study should be tagged with in Orthanc, driving the
        Authorization plugin's per-resource access checks."""
        labels = {f"org-{self.organization_id}"}

        if self.facility_id:
            labels.add(f"facility-{self.facility_id}")

        return labels


class OrthancAccessToken(models.Model):
    """A short-lived bearer credential minted when a RabiVault user opens the
    Orthanc viewer. Orthanc's Authorization plugin calls back into our
    /imaging/orthanc-auth/ webhooks with this token to ask who the holder is
    and what they're allowed to see, so the raw token itself is never stored
    (only its hash) and it is single-purpose: viewing, not a login credential.
    """

    token_hash = models.CharField(max_length=64, unique=True, db_index=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orthanc_tokens",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["token_hash", "expires_at"]),
        ]

    def __str__(self):
        return f"Orthanc token for {self.user} (expires {self.expires_at})"

    @staticmethod
    def _hash(raw_token):
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @classmethod
    def issue(cls, user, lifetime_seconds):
        raw_token = secrets.token_urlsafe(32)

        instance = cls.objects.create(
            token_hash=cls._hash(raw_token),
            user=user,
            expires_at=timezone.now() + timezone.timedelta(seconds=lifetime_seconds),
        )

        return instance, raw_token

    @classmethod
    def verify(cls, raw_token):
        if not raw_token:
            return None

        try:
            token = cls.objects.select_related("user", "user__profile").get(
                token_hash=cls._hash(raw_token),
                expires_at__gt=timezone.now(),
            )
        except cls.DoesNotExist:
            return None

        token.last_used_at = timezone.now()
        token.save(update_fields=["last_used_at"])

        return token
