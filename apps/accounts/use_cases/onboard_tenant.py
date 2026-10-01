from dataclasses import dataclass

from apps.accounts.domain.passwords import generate_password
from apps.accounts.domain.role_rules import OWNER
from apps.accounts.models import User
from apps.accounts.repositories.onboarding import (
    NewOwner,
    OnboardingRepository,
    onboarding_repository,
)
from apps.tenants.models import Tenant


class TenantSlugTakenError(Exception):
    pass


@dataclass(frozen=True)
class NewTenant:
    tenant_name: str
    tenant_slug: str
    owner_first_name: str
    owner_last_name: str
    owner_email: str | None
    owner_username: str | None = None
    tenant_phone: str = ""
    tenant_address: str = ""
    owner_phone: str = ""
    password: str | None = None


@dataclass(frozen=True)
class OnboardedTenant:
    tenant: Tenant
    owner: User
    password: str


def onboard_tenant(
    new: NewTenant, repo: OnboardingRepository = onboarding_repository
) -> OnboardedTenant:
    """A brand new mart: its tenant row, default settings, and its first
    owner account. One tenant, one call; run again for the next customer.
    A password typed by the caller is used as is; otherwise one is made up
    and returned once, the same way a staff password reset works."""
    if repo.slug_taken(new.tenant_slug):
        raise TenantSlugTakenError
    password = new.password or generate_password()
    full_name = f"{new.owner_first_name.strip()} {new.owner_last_name.strip()}".strip()
    owner = User(
        full_name=full_name,
        role=OWNER,
        email=new.owner_email,
        username=new.owner_username,
        phone=new.owner_phone,
    )
    owner.set_password(password)
    tenant = repo.create(
        new.tenant_name,
        new.tenant_slug,
        NewOwner(owner, phone=new.tenant_phone, address=new.tenant_address),
    )
    return OnboardedTenant(tenant, owner, password)
