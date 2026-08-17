from celery import shared_task
from django.utils import timezone

from .orthanc_client import OrthancClientError, set_study_labels


@shared_task
def sync_imaging_study_labels(imaging_study_id):
    from .models import ImagingStudy

    try:
        study = ImagingStudy.objects.get(id=imaging_study_id)
    except ImagingStudy.DoesNotExist:
        return {"error": "ImagingStudy not found", "imaging_study_id": imaging_study_id}

    if not study.orthanc_study_id:
        return {"skipped": "no orthanc_study_id", "imaging_study_id": imaging_study_id}

    try:
        set_study_labels(study.orthanc_study_id, study.orthanc_labels())
    except OrthancClientError as exc:
        return {"error": str(exc), "imaging_study_id": imaging_study_id}

    study.labels_synced_at = timezone.now()
    study.save(update_fields=["labels_synced_at"])

    return {"imaging_study_id": imaging_study_id, "labels": sorted(study.orthanc_labels())}
