from django.conf import settings
from django.db import models
from apps.organizations.models import Organization


class BusinessAssociateAgreement(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("signed", "Signed"),
        ("expired", "Expired"),
        ("terminated", "Terminated"),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="baas",
    )

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="draft")
    effective_date = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    signed_document = models.FileField(upload_to="baa/", null=True, blank=True)

    signed_by_name = models.CharField(max_length=255, blank=True)
    signed_by_email = models.EmailField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def is_active(self):
        return self.status == "signed"

    def __str__(self):
        return f"{self.organization} - {self.status}"
    
class RetentionPolicy(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="retention_policies",
    )

    name = models.CharField(max_length=255)
    document_type = models.CharField(max_length=100)
    retention_days = models.PositiveIntegerField()
    auto_delete = models.BooleanField(default=False)
    requires_approval_before_delete = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class AccessReview(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="access_reviews",
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="completed_access_reviews",
    )

    period_start = models.DateField()
    period_end = models.DateField()
    notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.organization} access review {self.period_start} - {self.period_end}"
    
class Incident(models.Model):
    STATUS_CHOICES = [
        ("open", "Open"),
        ("contained", "Contained"),
        ("resolved", "Resolved"),
    ]

    SEVERITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidents",
    )

    title = models.CharField(max_length=255)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="open")

    detected_at = models.DateTimeField()
    contained_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    description = models.TextField()
    impact_summary = models.TextField(blank=True)
    corrective_actions = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title