from apps.organizations.permissions import get_user_profile


def user_can_view_study(user, study):
    if not user.is_authenticated:
        return False

    profile = get_user_profile(user)

    if not profile or not profile.active:
        return False

    if not profile.can_view_orthanc_link:
        return False

    if profile.role == "platform_admin":
        return True

    if profile.organization_id != study.organization_id:
        return False

    if profile.role in ["org_admin", "auditor"]:
        return True

    if study.facility_id:
        return profile.facilities.filter(id=study.facility_id).exists()

    return False


def studies_for_user(user):
    from .models import ImagingStudy

    if not user.is_authenticated:
        return ImagingStudy.objects.none()

    profile = get_user_profile(user)

    if not profile or not profile.active or not profile.can_view_orthanc_link:
        return ImagingStudy.objects.none()

    if profile.role == "platform_admin":
        return ImagingStudy.objects.all()

    qs = ImagingStudy.objects.filter(organization=profile.organization)

    if profile.role in ["org_admin", "auditor"]:
        return qs

    facility_ids = profile.facilities.values_list("id", flat=True)

    return qs.filter(facility_id__in=facility_ids)


def labels_for_user(user):
    """Orthanc labels this user is allowed to see, in the shape the
    Authorization plugin's /user/get-profile webhook expects. Mirrors
    studies_for_user()/user_can_view_study() so a user can never see more
    through the Orthanc viewer than through the file manager's imaging tab.
    """
    profile = get_user_profile(user)

    if not profile or not profile.active or not profile.can_view_orthanc_link:
        return []

    if profile.role == "platform_admin":
        return ["*"]

    if not profile.organization_id:
        return []

    if profile.role in ["org_admin", "auditor"]:
        return [f"org-{profile.organization_id}"]

    return [f"facility-{fid}" for fid in profile.facilities.values_list("id", flat=True)]
