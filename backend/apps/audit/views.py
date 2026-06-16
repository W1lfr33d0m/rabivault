from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from apps.accounts.decorators import mfa_required
from django_ratelimit.decorators import ratelimit
from .models import AuditLog


@login_required
@mfa_required
@ratelimit(key="user", rate="30/h", block=True)
def audit_log_list(request):
    profile = request.user.profile

    if profile.role == "platform_admin":
        logs = AuditLog.objects.all()
    elif profile.role == "org_admin":
        logs = AuditLog.objects.filter(organization=profile.organization)
    else:
        raise PermissionDenied("You do not have permission to view audit logs.")

    return render(request, "audit/audit_log_list.html", {"logs": logs[:500]})
