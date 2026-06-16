from .models import BusinessAssociateAgreement


def organization_has_active_baa(organization):
    return BusinessAssociateAgreement.objects.filter(
        organization=organization,
        status="signed",
    ).exists()