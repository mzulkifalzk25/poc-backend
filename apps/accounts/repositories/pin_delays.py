from datetime import datetime
from typing import Protocol

from apps.accounts.models import PinDelay, User


class PinDelayRepository(Protocol):
    def lock(self, tenant_id: int, counter_id: int, user_id: int) -> PinDelay: ...

    def save(self, row: PinDelay) -> None: ...

    def clear_everywhere(self, user: User, counter_ids: list[int], now: datetime) -> None: ...


class DjangoPinDelayRepository:
    def lock(self, tenant_id: int, counter_id: int, user_id: int) -> PinDelay:
        """The row for this cashier on this counter, created if missing and
        locked until the end of the caller's transaction."""
        row, _ = PinDelay.objects.select_for_update().get_or_create(
            tenant_id=tenant_id, counter_id=counter_id, user_id=user_id
        )
        return row

    def save(self, row: PinDelay) -> None:
        row.save()

    def clear_everywhere(self, user: User, counter_ids: list[int], now: datetime) -> None:
        """A cleared row with `unlocked_at` per counter, inserted or updated."""
        rows = [
            PinDelay(
                tenant_id=user.tenant_id,
                counter_id=counter_id,
                user_id=user.id,
                fail_count=0,
                next_allowed_at=None,
                unlocked_at=now,
            )
            for counter_id in counter_ids
        ]
        PinDelay.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=["tenant_id", "counter_id", "user_id"],
            update_fields=["fail_count", "next_allowed_at", "unlocked_at", "updated_at"],
        )


pin_delay_repository = DjangoPinDelayRepository()
