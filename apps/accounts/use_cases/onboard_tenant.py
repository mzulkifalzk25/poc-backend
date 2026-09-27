from dataclasses import dataclass

from apps.accounts.domain.role_rules import OWNER
from apps.accounts.models import User
from apps.accounts.repositories.onboarding import OnboardingRepository, onboarding_repository
from apps.tenants.models import Tenant


class TenantSlugTakenError(Exception):
    pass


@dataclass(frozen=True)
class NewTenant:
    tenant_name: str
    tenant_slug: str
    owner_name: str
    owner_email: str | None
    owner_username: str | None
    password: str


def onboard_tenant(
    new: NewTenant, repo: OnboardingRepository = onboarding_repository
) -> tuple[Tenant, User]:
    """A brand new mart: its tenant row, default settings, and its first
    owner account. One tenant, one call; run again for the next customer."""
    if repo.slug_taken(new.tenant_slug):
        raise TenantSlugTakenError
    owner = User(
        full_name=new.owner_name, role=OWNER, email=new.owner_email, username=new.owner_username
    )
    owner.set_password(new.password)
    tenant = repo.create(new.tenant_name, new.tenant_slug, owner)
    return tenant, owner
