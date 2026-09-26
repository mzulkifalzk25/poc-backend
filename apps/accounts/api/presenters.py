from datetime import datetime

from apps.accounts.domain.names import initials
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


def present_staff(user: User) -> dict:
    return {
        **present_user(user),
        "initials": initials(user.full_name),
        "default_counter_id": user.default_counter_id,
        "is_active": user.is_active,
        "last_active_at": _iso(user.last_active_at),
        "pin_delay_until": _iso(getattr(user, "pin_delay_until", None)),
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def present_roster_row(user: User) -> dict:
    return {"id": user.id, "full_name": user.full_name, "initials": initials(user.full_name)}


def present_person(user: User) -> dict:
    """A deactivated cashier is sent without a verifier, so the counter drops it."""
    return {
        **present_roster_row(user),
        "pin_verifier": user.pin_verifier if user.is_active else None,
        "active": user.is_active,
        "unlocked_at": _iso(getattr(user, "unlocked_at", None)),
    }
