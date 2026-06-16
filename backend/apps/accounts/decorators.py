from django.shortcuts import redirect
from django.contrib import messages


def mfa_required(view_func):
    def wrapper(request, *args, **kwargs):
        profile = getattr(request.user, "profile", None)

        if not profile:
            messages.error(request, "User profile is missing.")
            return redirect("login")

        if profile.role in ["platform_admin", "org_admin", "facility_manager", "auditor"]:
            if not profile.mfa_enabled:
                messages.error(request, "MFA is required for this action.")
                return redirect("accounts:mfa_setup")

        return view_func(request, *args, **kwargs)

    return wrapper