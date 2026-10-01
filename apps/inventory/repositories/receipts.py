from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from django.db import IntegrityError, transaction
from django.db.models import F, QuerySet

from apps.catalog.models import Product
from apps.inventory.domain.errors import SupplierNameExistsError
from apps.inventory.models import StockReceipt, StockReceiptLine, Supplier
from apps.reports.models import PurchasesDaily


class ReceiptRepository(Protocol):
    def suppliers(self, tenant_id: int) -> QuerySet[Supplier]: ...

    def add_supplier(self, tenant_id: int, name: str, phone: str) -> Supplier: ...

    def supplier(self, tenant_id: int, supplier_id: int) -> Supplier | None: ...

    def product_costs(self, tenant_id: int, product_ids: list[int]) -> dict[int, Decimal]: ...

    def add_receipt(
        self,
        tenant_id: int,
        supplier: Supplier,
        invoice_no: str,
        delivery_date: date,
        total_cost: Decimal,
        lines: list[tuple[int, Decimal, Decimal, Decimal]],
    ) -> StockReceipt: ...

    def receipt(self, tenant_id: int, receipt_id: int) -> StockReceipt | None: ...

    def locked_receipt(self, tenant_id: int, receipt_id: int) -> StockReceipt | None: ...

    def lines(self, receipt: StockReceipt) -> list[StockReceiptLine]: ...

    def history(self, tenant_id: int) -> QuerySet[StockReceipt]: ...

    def confirm(
        self, receipt: StockReceipt, lines: list[StockReceiptLine], user_id: int, now: datetime
    ) -> None: ...


class DjangoReceiptRepository:
    def suppliers(self, tenant_id: int) -> QuerySet[Supplier]:
        return Supplier.objects.for_tenant(tenant_id).order_by("name")

    def add_supplier(self, tenant_id: int, name: str, phone: str) -> Supplier:
        try:
            with transaction.atomic():
                return Supplier.objects.create(tenant_id=tenant_id, name=name, phone=phone)
        except IntegrityError:
            raise SupplierNameExistsError from None

    def supplier(self, tenant_id: int, supplier_id: int) -> Supplier | None:
        return Supplier.objects.for_tenant(tenant_id).filter(id=supplier_id).first()

    def product_costs(self, tenant_id: int, product_ids: list[int]) -> dict[int, Decimal]:
        rows = Product.objects.for_tenant(tenant_id).filter(id__in=product_ids)
        return dict(rows.values_list("id", "cost"))

    def add_receipt(
        self,
        tenant_id: int,
        supplier: Supplier,
        invoice_no: str,
        delivery_date: date,
        total_cost: Decimal,
        lines: list[tuple[int, Decimal, Decimal, Decimal]],
    ) -> StockReceipt:
        """`lines` are `(product_id, qty, unit_cost, prev_cost)`."""
        with transaction.atomic():
            receipt = StockReceipt.objects.create(
                tenant_id=tenant_id,
                supplier=supplier,
                invoice_no=invoice_no,
                delivery_date=delivery_date,
                total_cost=total_cost,
            )
            StockReceiptLine.objects.bulk_create(
                StockReceiptLine(
                    tenant_id=tenant_id,
                    receipt=receipt,
                    product_id=product_id,
                    qty=qty,
                    unit_cost=unit_cost,
                    prev_cost=prev_cost,
                )
                for product_id, qty, unit_cost, prev_cost in lines
            )
        return receipt

    def receipt(self, tenant_id: int, receipt_id: int) -> StockReceipt | None:
        receipts = StockReceipt.objects.for_tenant(tenant_id).select_related("supplier")
        return receipts.filter(id=receipt_id).first()

    def locked_receipt(self, tenant_id: int, receipt_id: int) -> StockReceipt | None:
        receipts = StockReceipt.objects.for_tenant(tenant_id).select_related("supplier")
        return receipts.select_for_update(of=("self",)).filter(id=receipt_id).first()

    def lines(self, receipt: StockReceipt) -> list[StockReceiptLine]:
        rows = StockReceiptLine.objects.for_tenant(receipt.tenant_id).filter(receipt=receipt)
        return list(rows.select_related("product").order_by("id"))

    def history(self, tenant_id: int) -> QuerySet[StockReceipt]:
        receipts = StockReceipt.objects.for_tenant(tenant_id).select_related("supplier")
        return receipts.order_by("-delivery_date", "-id")

    def confirm(
        self, receipt: StockReceipt, lines: list[StockReceiptLine], user_id: int, now: datetime
    ) -> None:
        """Each product takes the delivery's cost (`updated_at` set so counters
        sync it), the total joins the delivery date's money out, and the
        receipt is marked confirmed."""
        tenant_id = receipt.tenant_id
        for line in lines:
            line.prev_cost = line.product.cost
            line.save(update_fields=["prev_cost", "updated_at"])
            Product.objects.for_tenant(tenant_id).filter(id=line.product_id).update(
                cost=line.unit_cost, updated_at=now
            )
        PurchasesDaily.objects.get_or_create(
            tenant_id=tenant_id, local_date=receipt.delivery_date, defaults={"amount": 0}
        )
        purchases = PurchasesDaily.objects.for_tenant(tenant_id)
        purchases.filter(local_date=receipt.delivery_date).update(
            amount=F("amount") + receipt.total_cost
        )
        receipt.status = StockReceipt.Status.CONFIRMED
        receipt.confirmed_by = user_id
        receipt.confirmed_at = now
        receipt.save(update_fields=["status", "confirmed_by", "confirmed_at", "updated_at"])


receipt_repository = DjangoReceiptRepository()
