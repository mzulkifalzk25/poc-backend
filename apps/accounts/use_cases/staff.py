from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction

from apps.accounts.domain.names import normalize_full_name
from apps.accounts.domain.pin import make_pin_verifier, new_salt
from apps.accounts.domain.role_rules import CASHIER, RoleFields, RoleRuleError, validate_role_fields
from apps.accounts.models import User
from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.tenants.models import Counter

_UNIQUE_CONSTRAINTS = {
    "uniq_user_tenant_cashier_name_lower": ("name_exists", "full_name"),
    "uniq_user_tenant_email_lower": ("email_exists", "email"),
    "uniq_user_tenant_username_lower": ("username_exists", "username"),
}
UPDATABLE_FIELDS = ("full_name", "default_counter_id", "is_active", "email", "username")


class StaffConflictError(Exception):
    def __init__(self, code: str, field_name: str):
        super().__init__(code)
        self.code = code
        self.field_name = field_name


class StaffInvalidError(Exception):
    def __init__(self, field_name: str, message: str):
        super().__init__(message)
        self.field_name = field_name
        self.message = message


@dataclass(frozen=True)
class NewStaff:
    full_name: str
    role: str
    pin: str | None = None
    password: str | None = None
    email: str | None = None
    username: str | None = None
    default_counter_id: int | None = None


@dataclass(frozen=True)
class Actor:
    tenant_id: int
    user_id: int


def set_pin(user: User, pin: str) -> None:
    """Argon2 for the server; a PBKDF2 verifier for offline checks on counters."""
    user.pin_hash = make_password(pin, hasher="argon2")
    user.pin_verifier = make_pin_verifier(pin, new_salt(), settings.PIN_VERIFIER_ITERATIONS)


def create_staff(actor: Actor, new: NewStaff) -> User:
    _check_role_fields(
        new.role,
        RoleFields(
            has_email=bool(new.email),
            has_username=bool(new.username),
            has_password=bool(new.password),
            has_pin=bool(new.pin),
        ),
    )
    _check_counter(actor.tenant_id, new.default_counter_id)
    user = User(
        tenant_id=actor.tenant_id,
        full_name=normalize_full_name(new.full_name),
        role=new.role,
        email=new.email,
        username=new.username,
        default_counter_id=new.default_counter_id,
    )
    if new.role == CASHIER:
        set_pin(user, new.pin or "")
    else:
        user.set_password(new.password)
    with transaction.atomic():
        _save(user)
        _log(actor, "staff_created", user, before=None)
    return user


def update_staff(actor: Actor, user: User, changes: dict) -> User:
    before = present_staff_snapshot(user)
    for name in UPDATABLE_FIELDS:
        if name in changes:
            setattr(user, name, changes[name])
    user.full_name = normalize_full_name(user.full_name)
    if user.id == actor.user_id and not user.is_active:
        raise StaffConflictError("cannot_deactivate_self", "is_active")
    _check_role_fields(
        user.role,
        RoleFields(
            has_email=bool(user.email),
            has_username=bool(user.username),
            has_password=bool(user.password),
            has_pin=bool(user.pin_hash),
        ),
    )
    _check_counter(actor.tenant_id, user.default_counter_id)
    with transaction.atomic():
        _save(user)
        _log(actor, "staff_updated", user, before=before)
    return user


def present_staff_snapshot(user: User) -> dict:
    return {
        "full_name": user.full_name,
        "role": user.role,
        "email": user.email,
        "username": user.username,
        "default_counter_id": user.default_counter_id,
        "is_active": user.is_active,
    }


def _check_role_fields(role: str, fields: RoleFields) -> None:
    try:
        validate_role_fields(role, fields)
    except RoleRuleError as error:
        raise StaffInvalidError("role", str(error)) from None


def _check_counter(tenant_id: int, counter_id: int | None) -> None:
    if counter_id is None:
        return
    if not Counter.objects.for_tenant(tenant_id).filter(id=counter_id).exists():
        raise StaffInvalidError("default_counter_id", "Counter not found.")


def _save(user: User) -> None:
    try:
        with transaction.atomic():
            user.save()
    except IntegrityError as error:
        for constraint, (code, field_name) in _UNIQUE_CONSTRAINTS.items():
            if constraint in str(error):
                raise StaffConflictError(code, field_name) from None
        raise


def _log(actor: Actor, action: str, user: User, before: dict | None) -> None:
    record_activity(
        ActivityEntry(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            action=action,
            entity_type="user",
            entity_id=str(user.id),
            before=before,
            after=present_staff_snapshot(user),
        )
    )
