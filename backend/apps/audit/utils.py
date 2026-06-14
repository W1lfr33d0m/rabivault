from .models import AuditLog


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


def get_user_organization(user):
    if not user or not user.is_authenticated:
        return None

    profile = getattr(user, "profile", None)

    if not profile:
        return None

    return profile.organization


def write_audit_log(
    *,
    request=None,
    actor=None,
    organization=None,
    action,
    object_type="",
    object_id="",
    metadata=None
):
    metadata = metadata or {}

    ip_address = None
    user_agent = ""

    if request:
        if not actor and request.user.is_authenticated:
            actor = request.user

        if not organization and actor:
            organization = get_user_organization(actor)

        ip_address = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

    return AuditLog.objects.create(
        organization=organization,
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id else "",
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=metadata,
    )
