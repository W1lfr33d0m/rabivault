import requests
from django.conf import settings


class OrthancClientError(Exception):
    pass


def _headers():
    # Orthanc runs with its core HTTP authentication disabled (see DEPLOY notes
    # in docker-compose.yml) and delegates every request to the Authorization
    # plugin instead. RabiVault's own backend authenticates to it the same way
    # a viewing user would: by presenting a token in the header configured as
    # Authorization.TokenHttpHeaders. ORTHANC_SERVICE_TOKEN is a long-lived
    # secret that apps/imaging/views.py's orthanc_auth_user_profile() webhook
    # recognizes and grants an all-labels/all-permissions profile to.
    return {"token": settings.ORTHANC_SERVICE_TOKEN}


def set_study_labels(orthanc_study_id, labels):
    """Replace the label set on an Orthanc study with `labels` (an iterable
    of strings). Orthanc's Authorization plugin uses these labels to decide
    which studies a given token/profile is allowed to see, so this is the
    step that actually puts a study "inside" an organization/facility from
    Orthanc's point of view.
    """
    base_url = f"{settings.ORTHANC_INTERNAL_URL}/studies/{orthanc_study_id}/labels"

    response = requests.get(base_url, headers=_headers(), timeout=10)

    if response.status_code == 404:
        raise OrthancClientError(f"Orthanc study {orthanc_study_id} not found")

    response.raise_for_status()
    existing_labels = set(response.json())
    target_labels = set(labels)

    for label in existing_labels - target_labels:
        delete_response = requests.delete(f"{base_url}/{label}", headers=_headers(), timeout=10)
        delete_response.raise_for_status()

    for label in target_labels - existing_labels:
        put_response = requests.put(f"{base_url}/{label}", headers=_headers(), timeout=10)
        put_response.raise_for_status()
