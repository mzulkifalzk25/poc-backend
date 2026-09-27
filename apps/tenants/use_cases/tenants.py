from apps.tenants.models import Tenant
from apps.tenants.repositories.tenants import TenantRepository, tenant_repository


def tenant_of(tenant_id: int, repo: TenantRepository = tenant_repository) -> Tenant:
    return repo.get(tenant_id)
