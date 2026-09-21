from apps.accounts.models import User
from apps.tenants.models import Tenant


def present_user(user: User) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "role": user.role,
        "email": user.email,
        "username": user.username,
    }


def present_tenant(tenant: Tenant) -> dict:
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "timezone": tenant.timezone,
    }
