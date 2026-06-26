from functools import wraps
from urllib.parse import quote

from django.contrib import messages
from django.shortcuts import redirect


MFA_REQUIRED_ROLES = ["platform_admin", "org_admin", "facility_manager", "auditor"]


def mfa_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        profile = getattr(request.user, "profile", None)

        if not profile:
            messages.error(request, "User profile is missing.")
            return redirect("login")

        if profile.role in MFA_REQUIRED_ROLES:
            if not profile.mfa_enabled:
                messages.error(request, "MFA is required for this action.")
                return redirect("accounts:mfa_setup")

            if request.session.get("mfa_verified_user_id") != request.user.id:
                messages.info(request, "Enter your MFA code to continue.")
                return redirect(f"/account/mfa/verify/?next={quote(request.get_full_path())}")

        return view_func(request, *args, **kwargs)

    return wrapper
