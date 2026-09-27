from datetime import datetime
from typing import Protocol

from django.db import IntegrityError, transaction

from apps.tenants.models import Counter, DeviceCode


class CodeHashTakenError(Exception):
    """Another stored code has the same hash; the caller draws a new code."""


class ActivationCodeRepository(Protocol):
    def revoke_unused(self, counter: Counter, now: datetime) -> None: ...

    def add(
        self, counter: Counter, code_hash: str, expires_at: datetime, created_by: int
    ) -> DeviceCode: ...

    def lock_by_hash(self, code_hash: str) -> DeviceCode | None: ...

    def mark_used(self, row: DeviceCode, now: datetime) -> None: ...


class DjangoActivationCodeRepository:
    def revoke_unused(self, counter: Counter, now: datetime) -> None:
        DeviceCode.objects.for_tenant(counter.tenant_id).filter(
            counter=counter, used_at__isnull=True, revoked_at__isnull=True
        ).update(revoked_at=now)

    def add(
        self, counter: Counter, code_hash: str, expires_at: datetime, created_by: int
    ) -> DeviceCode:
        try:
            with transaction.atomic():
                return DeviceCode.objects.create(
                    tenant_id=counter.tenant_id,
                    counter=counter,
                    code_hash=code_hash,
                    expires_at=expires_at,
                    created_by=created_by,
                )
        except IntegrityError:
            raise CodeHashTakenError from None

    def lock_by_hash(self, code_hash: str) -> DeviceCode | None:
        """Global on purpose: activation is public and the code finds the tenant."""
        return DeviceCode.objects.select_for_update().filter(code_hash=code_hash).first()

    def mark_used(self, row: DeviceCode, now: datetime) -> None:
        row.used_at = now
        row.save(update_fields=["used_at", "updated_at"])


code_repository = DjangoActivationCodeRepository()
