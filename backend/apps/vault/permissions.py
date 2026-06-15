from .models import DocumentShare

def user_has_document_share(user, document, permission):
    return DocumentShare.objects.filter(
        user=user,
        document=document,
        permission=permission,
    ).exists()

def get_user_profile(user):
    return getattr(user, "profile", None)


def user_can_access_organization(user, organization):
    if not user.is_authenticated:
        return False

    profile = get_user_profile(user)

    if not profile or not profile.active:
        return False

    if profile.role == "platform_admin":
        return True

    return profile.organization_id == organization.id


def user_can_access_facility(user, facility):
    if not user.is_authenticated:
        return False

    profile = get_user_profile(user)

    if not profile or not profile.active:
        return False

    if profile.role == "platform_admin":
        return True

    if profile.organization_id != facility.organization_id:
        return False

    if profile.role == "org_admin":
        return True

    return profile.facilities.filter(id=facility.id).exists()


def user_can_view_document(user, document):
    if not user.is_authenticated:
        return False

    profile = get_user_profile(user)

    if not profile or not profile.active:
        return False

    if profile.role == "platform_admin":
        return True

    if profile.organization_id != document.organization_id:
        return False

    if profile.role in ["org_admin", "auditor"]:
        return True

    if user_has_document_share(user, document, "view"):
        return True

    if user_has_document_share(user, document, "download"):
        return True

    if user_has_document_share(user, document, "manage"):
        return True

    if document.facility_id:
        return profile.facilities.filter(id=document.facility_id).exists()

    return profile.role in ["facility_manager", "staff", "external_reviewer"]

def user_can_upload_document(user, organization, facility=None):
    if not user.is_authenticated:
        return False

    profile = get_user_profile(user)

    if not profile or not profile.active:
        return False

    if profile.role == "platform_admin":
        return True

    if profile.organization_id != organization.id:
        return False

    if profile.role in ["org_admin", "facility_manager", "staff"]:
        if facility:
            return user_can_access_facility(user, facility)
        return True

    return False

def user_can_download_document(user, document):
    if not user_can_view_document(user, document):
        return False

    profile = get_user_profile(user)

    if profile.role in ["platform_admin", "org_admin", "facility_manager", "auditor"]:
        return True

    return (
        user_has_document_share(user, document, "download") or
        user_has_document_share(user, document, "manage")
    )

def documents_for_user(user):
    from .models import Document

    if not user.is_authenticated:
        return Document.objects.none()

    profile = get_user_profile(user)

    if not profile or not profile.active:
        return Document.objects.none()

    if profile.role == "platform_admin":
        return Document.objects.all()

    qs = Document.objects.filter(organization=profile.organization)

    if profile.role in ["org_admin", "auditor"]:
        return qs

    facility_ids = profile.facilities.values_list("id", flat=True)

    return qs.filter(facility_id__in=facility_ids)
