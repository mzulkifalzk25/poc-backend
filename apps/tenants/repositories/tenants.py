from typing import Protocol

from apps.tenants.models import Tenant


class TenantRepository(Protocol):
    def get(self, tenant_id: int) -> Tenant: ...


class DjangoTenantRepository:
    def get(self, tenant_id: int) -> Tenant:
        return Tenant.objects.get(id=tenant_id)


tenant_repository = DjangoTenantRepository()
