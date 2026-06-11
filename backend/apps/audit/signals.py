from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .utils import write_audit_log


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    write_audit_log(
        request=request,
        actor=user,
        action="login",
        object_type="User",
        object_id=user.id,
        metadata={"username": user.username}
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    if user:
        write_audit_log(
            request=request,
            actor=user,
            action="logout",
            object_type="User",
            object_id=user.id,
            metadata={"username": user.username}
        )


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    username = credentials.get("username", "")

    write_audit_log(
        request=request,
        actor=None,
        action="failed_login",
        object_type="User",
        object_id="",
        metadata={"username": username}
    )
