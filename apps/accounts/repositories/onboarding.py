from typing import Protocol

from django.db import transaction

from apps.accounts.models import User
from apps.tenants.models import Tenant, TenantSettings


class OnboardingRepository(Protocol):
    def slug_taken(self, slug: str) -> bool: ...

    def create(self, tenant_name: str, slug: str, owner: User) -> Tenant: ...


class DjangoOnboardingRepository:
    def slug_taken(self, slug: str) -> bool:
        return Tenant.objects.filter(slug=slug).exists()

    def create(self, tenant_name: str, slug: str, owner: User) -> Tenant:
        with transaction.atomic():
            tenant = Tenant.objects.create(name=tenant_name, slug=slug)
            TenantSettings.objects.create(tenant=tenant, store_name=tenant_name)
            owner.tenant_id = tenant.id
            owner.save()
        return tenant


onboarding_repository = DjangoOnboardingRepository()
