import base64
import binascii
import json
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.accounts.decorators import mfa_required
from apps.audit.utils import write_audit_log
from apps.organizations.models import Facility

from .models import ImagingStudy, OrthancAccessToken
from .permissions import labels_for_user, studies_for_user, user_can_view_study


# ---------------------------------------------------------------------------
# RabiVault-side views: browsing studies and opening the Orthanc viewer.
# ---------------------------------------------------------------------------

@login_required
def imaging_study_list(request):
    studies = studies_for_user(request.user).select_related("organization", "facility")

    facility_id = request.GET.get("facility", "")

    if facility_id:
        studies = studies.filter(facility_id=facility_id)

    profile = getattr(request.user, "profile", None)
    facilities = Facility.objects.none()

    if profile and profile.active:
        if profile.role == "platform_admin":
            facilities = Facility.objects.filter(active=True)
        elif profile.organization_id:
            facilities = Facility.objects.filter(organization=profile.organization, active=True)

    paginator = Paginator(studies, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "imaging/study_list.html",
        {
            "studies": page_obj.object_list,
            "page_obj": page_obj,
            "facility_id": facility_id,
            "facilities": facilities,
        },
    )


def _open_viewer(request, study=None):
    profile = getattr(request.user, "profile", None)

    if not profile or not profile.active or not profile.can_view_orthanc_link:
        messages.error(
            request,
            "You don't have permission to access the imaging viewer. Ask an organization admin to grant access.",
        )
        return redirect("vault:dashboard")

    token_obj, raw_token = OrthancAccessToken.issue(request.user, settings.IMAGING_TOKEN_LIFETIME_SECONDS)

    write_audit_log(
        request=request,
        action="access_imaging_viewer",
        object_type="ImagingStudy" if study else "Orthanc",
        object_id=study.orthanc_study_id if study else "",
        metadata={"orthanc_token_id": token_obj.id},
    )

    return redirect(f"{settings.ORTHANC_URL}/ui/app/token-landing.html?token={raw_token}")


@login_required
def orthanc_redirect(request):
    return _open_viewer(request)


@login_required
@mfa_required
def imaging_study_open(request, pk):
    study = get_object_or_404(ImagingStudy, pk=pk)

    if not user_can_view_study(request.user, study):
        raise PermissionDenied("You do not have access to this imaging study.")

    return _open_viewer(request, study=study)


# ---------------------------------------------------------------------------
# Orthanc Authorization plugin webhooks.
#
# Orthanc's core HTTP authentication is disabled (docker-compose.yml);
# instead every request Orthanc receives is checked against these endpoints,
# so *this* is the real access-control boundary for the imaging viewer - the
# equivalent of apps/vault/permissions.py for the file manager. Orthanc
# authenticates itself to us with HTTP Basic Auth (ORTHANC_WEBHOOK_USERNAME/
# PASSWORD), separate from the per-user "token" bearer credentials we mint.
# ---------------------------------------------------------------------------

def _webhook_authenticated(request):
    expected_user = settings.ORTHANC_WEBHOOK_USERNAME
    expected_password = settings.ORTHANC_WEBHOOK_PASSWORD

    if not expected_user or not expected_password:
        return False

    header = request.META.get("HTTP_AUTHORIZATION", "")

    if not header.startswith("Basic "):
        return False

    try:
        decoded = base64.b64decode(header[len("Basic "):]).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return False

    return secrets.compare_digest(username, expected_user) and secrets.compare_digest(password, expected_password)


def _deny_profile():
    return JsonResponse({"name": "anonymous", "authorized-labels": [], "permissions": [], "validity": 5})


def _resolve_token(token_value):
    """Returns (labels, permissions) for a token presented by Orthanc, or
    None if the token isn't recognized. Mirrors apps/vault/permissions.py's
    documents_for_user()/user_can_view_document() split: labels drive what a
    profile can list/see (list-level), the caller still separately checks
    individual resources against those same labels (object-level).
    """
    if not token_value:
        return None

    if settings.ORTHANC_SERVICE_TOKEN and secrets.compare_digest(token_value, settings.ORTHANC_SERVICE_TOKEN):
        return ["*"], ["all"]

    token = OrthancAccessToken.verify(token_value)

    if not token:
        return None

    labels = labels_for_user(token.user)

    if not labels:
        return None

    return labels, ["view"]


@csrf_exempt
@require_POST
def orthanc_auth_user_profile(request):
    if not _webhook_authenticated(request):
        return HttpResponse(status=401)

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        payload = {}

    resolved = _resolve_token(payload.get("token-value", ""))

    if not resolved:
        return _deny_profile()

    labels, permissions = resolved

    return JsonResponse({
        "name": "rabivault-user",
        "authorized-labels": labels,
        "permissions": permissions,
        "validity": 5,
    })


@csrf_exempt
@require_POST
def orthanc_auth_token_validate(request):
    if not _webhook_authenticated(request):
        return HttpResponse(status=401)

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        payload = {}

    resolved = _resolve_token(payload.get("token-value", ""))

    if not resolved:
        return JsonResponse({"granted": False})

    labels, _ = resolved

    if "*" in labels:
        return JsonResponse({"granted": True, "validity": 5})

    if payload.get("level") != "study":
        return JsonResponse({"granted": False})

    orthanc_id = payload.get("orthanc-id", "")
    study = ImagingStudy.objects.filter(orthanc_study_id=orthanc_id).first()

    if not study:
        return JsonResponse({"granted": False})

    granted = bool(study.orthanc_labels() & set(labels))

    return JsonResponse({"granted": granted, "validity": 5})


@csrf_exempt
@require_POST
def orthanc_auth_token_decode(request):
    # We only ever hand out general-purpose session tokens (see
    # OrthancAccessToken), never Orthanc's own resource-sharing tokens, so
    # there is nothing for this webhook to resolve. Returning no resources is
    # the documented "not a sharing token" response and lets Orthanc Explorer
    # 2's token-landing page fall through to a normal, label-filtered session.
    if not _webhook_authenticated(request):
        return HttpResponse(status=401)

    return JsonResponse({})
