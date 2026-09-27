from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.db.models import QuerySet

from apps.accounts.domain.names import normalize_full_name
from apps.accounts.domain.passwords import generate_password
from apps.accounts.domain.role_rules import RoleFields, RoleRuleError, validate_role_fields
from apps.accounts.domain.staff_errors import StaffConflictError
from apps.accounts.models import User
from apps.accounts.repositories.users import UserRepository, user_repository
from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.tenants.repositories.counters import CounterRepository, counter_repository

UPDATABLE_FIELDS = ("full_name", "default_counter_id", "is_active", "email", "username")


class StaffInvalidError(Exception):
    def __init__(self, field_name: str, message: str):
        super().__init__(message)
        self.field_name = field_name
        self.message = message


@dataclass(frozen=True)
class NewStaff:
    full_name: str
    role: str
    password: str | None = None
    email: str | None = None
    username: str | None = None
    default_counter_id: int | None = None


@dataclass(frozen=True)
class Actor:
    tenant_id: int
    user_id: int


def create_staff(
    actor: Actor,
    new: NewStaff,
    users: UserRepository = user_repository,
    counters: CounterRepository = counter_repository,
) -> User:
    _check_role_fields(
        new.role,
        RoleFields(
            has_email=bool(new.email),
            has_username=bool(new.username),
            has_password=bool(new.password),
        ),
    )
    _check_counter(counters, actor.tenant_id, new.default_counter_id)
    user = User(
        tenant_id=actor.tenant_id,
        full_name=normalize_full_name(new.full_name),
        role=new.role,
        email=new.email,
        username=new.username,
        default_counter_id=new.default_counter_id,
    )
    user.set_password(new.password)
    with transaction.atomic():
        users.save_unique(user)
        _log(actor, "staff_created", user, before=None)
    return user


def update_staff(
    actor: Actor,
    user: User,
    changes: dict,
    users: UserRepository = user_repository,
    counters: CounterRepository = counter_repository,
) -> User:
    before = present_staff_snapshot(user)
    for name in UPDATABLE_FIELDS:
        if name in changes:
            setattr(user, name, changes[name])
    user.full_name = normalize_full_name(user.full_name)
    if user.id == actor.user_id and not user.is_active:
        raise StaffConflictError("cannot_deactivate_self", "is_active")
    _check_role_fields(
        user.role,
        RoleFields(has_email=bool(user.email), has_username=bool(user.username), has_password=True),
    )
    _check_counter(counters, actor.tenant_id, user.default_counter_id)
    with transaction.atomic():
        users.save_unique(user)
        _log(actor, "staff_updated", user, before=before)
    return user


def reset_password(
    actor: Actor, user: User, now: datetime, users: UserRepository = user_repository
) -> str:
    """Returns the new password once; the same pattern PIN reset used."""
    password = generate_password()
    user.set_password(password)
    with transaction.atomic():
        users.save(user, ["password", "updated_at"])
        _log(actor, "password_reset", user, before=None)
    return password


def find_staff(
    tenant_id: int, user_id: int, users: UserRepository = user_repository
) -> User | None:
    return users.in_tenant(tenant_id, user_id)


def staff_rows(
    tenant_id: int, now: datetime, filters: dict, users: UserRepository = user_repository
) -> QuerySet[User]:
    return users.staff_list(tenant_id, now, filters)


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


def _check_counter(counters: CounterRepository, tenant_id: int, counter_id: int | None) -> None:
    if counter_id is None:
        return
    if not counters.exists(tenant_id, counter_id):
        raise StaffInvalidError("default_counter_id", "Counter not found.")


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
