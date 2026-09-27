from typing import Protocol

from apps.tenants.models import Tenant


class TenantRepository(Protocol):
    def get(self, tenant_id: int) -> Tenant: ...

    def get_or_create(self, slug: str, name: str) -> Tenant: ...


class DjangoTenantRepository:
    def get(self, tenant_id: int) -> Tenant:
        return Tenant.objects.get(id=tenant_id)

    def get_or_create(self, slug: str, name: str) -> Tenant:
        return Tenant.objects.get_or_create(slug=slug, defaults={"name": name})[0]


tenant_repository = DjangoTenantRepository()
