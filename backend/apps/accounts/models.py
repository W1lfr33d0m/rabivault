from django.conf import settings
from django.db import models
from apps.organizations.models import Organization, Facility


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("platform_admin", "Platform Admin"),
        ("org_admin", "Organization Admin"),
        ("facility_manager", "Facility Manager"),
        ("staff", "Staff"),
        ("external_reviewer", "External Reviewer"),
        ("auditor", "Auditor"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="user_profiles"
    )

    facilities = models.ManyToManyField(
        Facility,
        blank=True,
        related_name="user_profiles"
    )

    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default="staff")
    mfa_enabled = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"

    @property
    def is_platform_admin(self):
        return self.role == "platform_admin"

    @property
    def is_org_admin(self):
        return self.role == "org_admin"
