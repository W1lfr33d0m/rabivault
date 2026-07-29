from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from apps.audit.utils import write_audit_log


@login_required
def orthanc_redirect(request):
    profile = getattr(request.user, "profile", None)

    if not profile or not profile.can_view_orthanc_link:
        messages.error(
            request,
            "You don't have permission to access the imaging viewer. Ask an organization admin to grant access.",
        )
        return redirect("vault:dashboard")

    write_audit_log(
        request=request,
        action="access_imaging_viewer",
        object_type="Orthanc",
    )

    return redirect(settings.ORTHANC_URL)
