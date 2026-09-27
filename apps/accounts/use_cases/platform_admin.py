"""The platform admin is the only account that can open the Django admin.

It belongs to an internal tenant, so no store ever lists it as staff, and
`/auth/login` never matches it, so it cannot sign in to the store app."""

from apps.accounts.domain.role_rules import OWNER
from apps.accounts.models import User
from apps.accounts.repositories.users import UserRepository, user_repository
from apps.tenants.repositories.tenants import TenantRepository, tenant_repository

PLATFORM_TENANT_SLUG = "martdesk-platform"
PLATFORM_TENANT_NAME = "MartDesk platform"


def save_platform_admin(
    email: str,
    password: str,
    users: UserRepository = user_repository,
    tenants: TenantRepository = tenant_repository,
) -> bool:
    """Creates the admin, or reactivates it and resets its password. True when created."""
    email = email.strip().lower()
    user = users.platform_admin(email)
    created = user is None
    if user is None:
        tenant = tenants.get_or_create(PLATFORM_TENANT_SLUG, PLATFORM_TENANT_NAME)
        user = User(
            tenant_id=tenant.id,
            full_name="Platform admin",
            role=OWNER,
            email=email,
            is_platform_admin=True,
        )
    user.is_active = True
    user.set_password(password)
    users.save(user)
    return created


def authenticate_platform_admin(
    email: str, password: str, users: UserRepository = user_repository
) -> User | None:
    user = users.platform_admin(email)
    if user is None:
        User().set_password(password)  # same hashing time whether or not the email exists
        return None
    return user if user.is_active and user.check_password(password) else None


def platform_admin_by_id(user_id: int, users: UserRepository = user_repository) -> User | None:
    return users.platform_admin_by_id(user_id)
