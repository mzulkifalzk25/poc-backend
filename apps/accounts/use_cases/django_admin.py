"""The Django admin is for the product maintainer only: one account, whose email
is set on the server (`DJANGO_ADMIN_EMAIL`). Store owners and cashiers use the
store app and can never open it.

The account belongs to an internal tenant, so no store lists it as staff, and
`/auth/login` never matches it, so it cannot sign in to the store app."""

from apps.accounts.domain.django_admin import is_django_admin_email, normalize_email
from apps.accounts.domain.role_rules import OWNER
from apps.accounts.models import User
from apps.accounts.repositories.users import UserRepository, user_repository
from apps.tenants.repositories.tenants import TenantRepository, tenant_repository

MAINTENANCE_TENANT_SLUG = "martdesk-maintenance"
MAINTENANCE_TENANT_NAME = "MartDesk maintenance"


def save_django_admin(
    configured_email: str,
    password: str,
    users: UserRepository = user_repository,
    tenants: TenantRepository = tenant_repository,
) -> bool:
    """Creates the account for the configured email, or reactivates it and resets
    its password. True when created."""
    email = normalize_email(configured_email)
    user = users.django_admin(email)
    created = user is None
    if user is None:
        tenant = tenants.get_or_create(MAINTENANCE_TENANT_SLUG, MAINTENANCE_TENANT_NAME)
        user = User(
            tenant_id=tenant.id,
            full_name="Django admin",
            role=OWNER,
            email=email,
            is_django_admin=True,
        )
    user.is_active = True
    user.set_password(password)
    users.save(user)
    return created


def authenticate_django_admin(
    email: str, password: str, configured_email: str, users: UserRepository = user_repository
) -> User | None:
    user = users.django_admin(email) if is_django_admin_email(email, configured_email) else None
    if user is None:
        User().set_password(password)  # same hashing time whatever the email
        return None
    return user if user.is_active and user.check_password(password) else None


def django_admin_by_id(
    user_id: int, configured_email: str, users: UserRepository = user_repository
) -> User | None:
    user = users.django_admin_by_id(user_id)
    return user if user and is_django_admin_email(user.email, configured_email) else None
