from typing import Protocol
from uuid import UUID

from apps.shifts.domain.drawer import ShiftSales


class ShiftSalesRepository(Protocol):
    def sales_of(self, tenant_id: int, shift_id: UUID) -> ShiftSales: ...


class DjangoShiftSalesRepository:
    def sales_of(self, tenant_id: int, shift_id: UUID) -> ShiftSales:
        """No bill or return tables yet: bills come in the bills-batch branch,
        returns in Step B6."""
        return ShiftSales.none()


shift_sales_repository = DjangoShiftSalesRepository()
