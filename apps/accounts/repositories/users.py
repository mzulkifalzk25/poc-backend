from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from django.db import IntegrityError, transaction
from django.db.models import OuterRef, Q, QuerySet, Subquery

from apps.accounts.domain.role_rules import CASHIER, MANAGER, OWNER
from apps.accounts.domain.staff_errors import StaffConflictError
from apps.accounts.models import PinDelay, User

_UNIQUE_CONSTRAINTS = {
    "uniq_user_tenant_cashier_name_lower": ("name_exists", "full_name"),
    "uniq_user_tenant_email_lower": ("email_exists", "email"),
    "uniq_user_tenant_username_lower": ("username_exists", "username"),
}


class UserRepository(Protocol):
    def login_candidates(self, login: str) -> list[User]: ...

    def in_tenant(self, tenant_id: int, user_id: int) -> User | None: ...

    def tenant_id_of(self, user_id: str | None) -> int | None: ...

    def staff_list(self, tenant_id: int, now: datetime, filters: dict) -> QuerySet[User]: ...

    def active_cashier(self, tenant_id: int, user_id: int) -> User | None: ...

    def ids_in_tenant(self, tenant_id: int, ids: Iterable[int]) -> set[int]: ...

    def active_roster(self, tenant_id: int) -> list[User]: ...

    def cashiers_for_sync(
        self, tenant_id: int, counter_id: int, since: datetime | None
    ) -> list[User]: ...

    def touch_cashier(self, tenant_id: int, cashier_id: int, now: datetime) -> bool: ...

    def save(self, user: User, fields: list[str] | None = None) -> None: ...

    def save_unique(self, user: User) -> None: ...


class DjangoUserRepository:
    def login_candidates(self, login: str) -> list[User]:
        """At most two active owners or managers whose email or username
        matches, case-insensitively, across all tenants."""
        return list(
            User.objects.filter(
                Q(email__iexact=login.strip()) | Q(username__iexact=login.strip()),
                role__in=(OWNER, MANAGER),
                is_active=True,
            )[:2]
        )

    def in_tenant(self, tenant_id: int, user_id: int) -> User | None:
        return User.objects.for_tenant(tenant_id).filter(id=user_id).first()

    def tenant_id_of(self, user_id: str | None) -> int | None:
        return User.objects.filter(id=user_id).values_list("tenant_id", flat=True).first()

    def staff_list(self, tenant_id: int, now: datetime, filters: dict) -> QuerySet[User]:
        """Adds `pin_delay_until`: the latest running delay on any counter."""
        running = PinDelay.objects.filter(
            tenant_id=tenant_id, user_id=OuterRef("pk"), next_allowed_at__gt=now
        ).order_by("-next_allowed_at")
        users = User.objects.for_tenant(tenant_id).annotate(
            pin_delay_until=Subquery(running.values("next_allowed_at")[:1])
        )
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

    def active_roster(self, tenant_id: int) -> list[User]:
        return list(
            User.objects.for_tenant(tenant_id)
            .filter(role=CASHIER, is_active=True)
            .order_by("full_name", "id")
        )

    def cashiers_for_sync(
        self, tenant_id: int, counter_id: int, since: datetime | None
    ) -> list[User]:
        """No `since`: active cashiers only. With `since`: everyone changed
        after it, deactivated cashiers included. Adds this counter's `unlocked_at`."""
        cashiers = User.objects.for_tenant(tenant_id).filter(role=CASHIER)
        if since is None:
            cashiers = cashiers.filter(is_active=True)
        else:
            cashiers = cashiers.filter(updated_at__gt=since)
        unlocks = PinDelay.objects.filter(
            tenant_id=tenant_id, counter_id=counter_id, user_id=OuterRef("pk")
        )
        cashiers = cashiers.annotate(unlocked_at=Subquery(unlocks.values("unlocked_at")[:1]))
        return list(cashiers.order_by("updated_at", "id"))

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
