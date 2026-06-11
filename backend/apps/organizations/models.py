from django.db import models


class Organization(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("suspended", "Suspended"),
        ("archived", "Archived"),
    ]

    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Facility(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="facilities"
    )
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=50, blank=True)
    zip_code = models.CharField(max_length=20, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Facilities"

    def __str__(self):
        return f"{self.name} - {self.organization.name}"
