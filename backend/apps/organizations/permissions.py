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
