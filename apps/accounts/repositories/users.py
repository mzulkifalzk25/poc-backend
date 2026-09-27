from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from apps.accounts.domain.role_rules import CASHIER
from apps.accounts.domain.staff_errors import StaffConflictError
from apps.accounts.models import User

_UNIQUE_CONSTRAINTS = {
    "uniq_user_tenant_cashier_name_lower": ("name_exists", "full_name"),
    "uniq_user_tenant_email_lower": ("email_exists", "email"),
    "uniq_user_tenant_username_lower": ("username_exists", "username"),
}


class UserRepository(Protocol):
    def login_candidates(self, login: str, roles: Iterable[str]) -> list[User]: ...

    def django_admin(self, email: str) -> User | None: ...

    def django_admin_by_id(self, user_id: int) -> User | None: ...

    def in_tenant(self, tenant_id: int, user_id: int) -> User | None: ...

    def tenant_id_of(self, user_id: str | None) -> int | None: ...

    def staff_list(self, tenant_id: int, now: datetime, filters: dict) -> QuerySet[User]: ...

    def active_cashier(self, tenant_id: int, user_id: int) -> User | None: ...

    def ids_in_tenant(self, tenant_id: int, ids: Iterable[int]) -> set[int]: ...

    def touch_cashier(self, tenant_id: int, cashier_id: int, now: datetime) -> bool: ...

    def save(self, user: User, fields: list[str] | None = None) -> None: ...

    def save_unique(self, user: User) -> None: ...


class DjangoUserRepository:
    def login_candidates(self, login: str, roles: Iterable[str]) -> list[User]:
        """At most two active accounts of `roles` whose email or username
        matches, case-insensitively, across all tenants."""
        return list(
            User.objects.filter(
                Q(email__iexact=login.strip()) | Q(username__iexact=login.strip()),
                role__in=tuple(roles),
                is_active=True,
                is_django_admin=False,
            )[:2]
        )

    def django_admin(self, email: str) -> User | None:
        return User.objects.filter(is_django_admin=True, email__iexact=email.strip()).first()

    def django_admin_by_id(self, user_id: int) -> User | None:
        return User.objects.filter(is_django_admin=True, id=user_id).first()

    def in_tenant(self, tenant_id: int, user_id: int) -> User | None:
        return User.objects.for_tenant(tenant_id).filter(id=user_id).first()

    def tenant_id_of(self, user_id: str | None) -> int | None:
        return User.objects.filter(id=user_id).values_list("tenant_id", flat=True).first()

    def staff_list(self, tenant_id: int, now: datetime, filters: dict) -> QuerySet[User]:
        users = User.objects.for_tenant(tenant_id)
        return _filtered(users, filters).order_by("full_name", "id")

    def active_cashier(self, tenant_id: int, user_id: int) -> User | None:
        return (
            User.objects.for_tenant(tenant_id)
            .filter(id=user_id, role=CASHIER, is_active=True)
            .first()
        )

    def ids_in_tenant(self, tenant_id: int, ids: Iterable[int]) -> set[int]:
        """Deactivated staff included: their past sales still upload."""
        found = User.objects.for_tenant(tenant_id).filter(id__in=list(set(ids)))
        return set(found.values_list("id", flat=True))

    def touch_cashier(self, tenant_id: int, cashier_id: int, now: datetime) -> bool:
        """A plain update, so `updated_at` does not move."""
        updated = (
            User.objects.for_tenant(tenant_id)
            .filter(id=cashier_id, role=CASHIER)
            .update(last_active_at=now)
        )
        return bool(updated)

    def save(self, user: User, fields: list[str] | None = None) -> None:
        user.save(update_fields=fields)

    def save_unique(self, user: User) -> None:
        try:
            with transaction.atomic():
                user.save()
        except IntegrityError as error:
            for constraint, (code, field_name) in _UNIQUE_CONSTRAINTS.items():
                if constraint in str(error):
                    raise StaffConflictError(code, field_name) from None
            raise


def _filtered(users: QuerySet[User], filters: dict) -> QuerySet[User]:
    if "role" in filters:
        users = users.filter(role=filters["role"])
    if "status" in filters:
        users = users.filter(is_active=filters["status"] == "active")
    if "counter" in filters:
        users = users.filter(default_counter_id=filters["counter"])
    return users


user_repository = DjangoUserRepository()
