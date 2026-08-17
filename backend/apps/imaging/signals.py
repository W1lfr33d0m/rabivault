from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ImagingStudy
from .tasks import sync_imaging_study_labels


@receiver(post_save, sender=ImagingStudy)
def push_imaging_study_labels(sender, instance, **kwargs):
    sync_imaging_study_labels.delay(instance.id)
