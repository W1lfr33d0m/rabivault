import io

import qrcode
import qrcode.image.svg
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.audit.utils import write_audit_log


def _safe_next_url(request, default="vault:dashboard"):
    next_url = request.POST.get("next") or request.GET.get("next")

    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url

    return reverse(default)


def _render_qr_svg(config_url):
    qr = qrcode.make(config_url, image_factory=qrcode.image.svg.SvgPathImage)
    stream = io.BytesIO()
    qr.save(stream)
    return stream.getvalue().decode("utf-8")


@login_required
def mfa_setup(request):
    profile = getattr(request.user, "profile", None)

    if not profile:
        messages.error(request, "Your user profile is missing. Ask a platform admin to create it first.")
        return redirect("vault:dashboard")

    confirmed_device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()

    if confirmed_device:
        if not profile.mfa_enabled:
            profile.mfa_enabled = True
            profile.save(update_fields=["mfa_enabled"])

        messages.info(request, "MFA is already enabled for your account.")
        return redirect("vault:dashboard")

    device, _created = TOTPDevice.objects.get_or_create(
        user=request.user,
        name="default",
        confirmed=False,
    )

    if request.method == "POST":
        token = request.POST.get("token", "").strip()

        if device.verify_token(token):
            device.confirmed = True
            device.save(update_fields=["confirmed"])

            profile.mfa_enabled = True
            profile.save(update_fields=["mfa_enabled"])
            request.session["mfa_verified_user_id"] = request.user.id

            write_audit_log(
                request=request,
                action="mfa_enabled",
                object_type="UserProfile",
                object_id=profile.id,
                metadata={"username": request.user.username},
            )

            messages.success(request, "MFA has been enabled for your account.")
            return redirect("vault:dashboard")

        messages.error(request, "Invalid MFA code. Try the current 6-digit code from your authenticator app.")

    return render(
        request,
        "accounts/mfa_setup.html",
        {
            "device": device,
            "qr_svg": _render_qr_svg(device.config_url),
            "manual_config_url": device.config_url,
        },
    )


@login_required
def mfa_verify(request):
    profile = getattr(request.user, "profile", None)

    if not profile:
        messages.error(request, "Your user profile is missing.")
        return redirect("login")

    device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()

    if not profile.mfa_enabled or not device:
        messages.error(request, "MFA setup is required before continuing.")
        return redirect("accounts:mfa_setup")

    next_url = _safe_next_url(request)

    if request.method == "POST":
        token = request.POST.get("token", "").strip()

        if device.verify_token(token):
            request.session["mfa_verified_user_id"] = request.user.id

            write_audit_log(
                request=request,
                action="mfa_verified",
                object_type="UserProfile",
                object_id=profile.id,
                metadata={"username": request.user.username},
            )

            messages.success(request, "MFA verified.")
            return redirect(next_url)

        messages.error(request, "Invalid MFA code. Try the current 6-digit code from your authenticator app.")

    return render(request, "accounts/mfa_verify.html", {"next": next_url})
