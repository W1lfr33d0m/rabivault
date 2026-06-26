from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import render
from django_ratelimit.decorators import ratelimit

from apps.accounts.decorators import mfa_required

from .models import AuditLog


@login_required
@mfa_required
@ratelimit(key="user", rate="30/h", block=True)
def audit_log_list(request):
    profile = request.user.profile

    if profile.role == "platform_admin":
        logs = AuditLog.objects.all()
    elif profile.role in ["org_admin", "auditor"]:
        logs = AuditLog.objects.filter(organization=profile.organization)
    else:
        raise PermissionDenied("You do not have permission to view audit logs.")

    action = request.GET.get("action", "")
    query = request.GET.get("q", "").strip()

    if action:
        logs = logs.filter(action=action)

    if query:
        logs = logs.filter(object_id__icontains=query)

    paginator = Paginator(logs.select_related("organization", "actor"), 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "audit/audit_log_list.html",
        {
            "logs": page_obj.object_list,
            "page_obj": page_obj,
            "action": action,
            "query": query,
            "action_choices": AuditLog.ACTION_CHOICES,
        },
    )
