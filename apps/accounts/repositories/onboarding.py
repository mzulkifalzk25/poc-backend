from dataclasses import dataclass
from typing import Protocol

from django.db import transaction

from apps.accounts.models import User
from apps.tenants.models import Tenant, TenantSettings


@dataclass(frozen=True)
class NewOwner:
    user: User
    phone: str = ""
    address: str = ""


class OnboardingRepository(Protocol):
    def slug_taken(self, slug: str) -> bool: ...

    def create(self, tenant_name: str, slug: str, owner: NewOwner) -> Tenant: ...


class DjangoOnboardingRepository:
    def slug_taken(self, slug: str) -> bool:
        return Tenant.objects.filter(slug=slug).exists()

    def create(self, tenant_name: str, slug: str, owner: NewOwner) -> Tenant:
        with transaction.atomic():
            tenant = Tenant.objects.create(name=tenant_name, slug=slug)
            TenantSettings.objects.create(
                tenant=tenant, store_name=tenant_name, phone=owner.phone, address=owner.address
            )
            owner.user.tenant_id = tenant.id
            owner.user.save()
        return tenant


onboarding_repository = DjangoOnboardingRepository()
