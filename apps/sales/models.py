from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.catalog.models import Product
from apps.core.models import TenantModel
from apps.sales.domain.flags import BILL_NO_CONFLICT
from apps.tenants.models import Counter


def _money(**kwargs) -> models.DecimalField:
    return models.DecimalField(max_digits=12, decimal_places=2, **kwargs)


def _quantity(**kwargs) -> models.DecimalField:
    return models.DecimalField(max_digits=12, decimal_places=3, **kwargs)


class Bill(TenantModel):
    """A completed sale, uploaded from a counter. The id is the client UUID.

    `shift_id` is a plain UUID: a shift opened offline may upload after its
    bills. Totals are stored as the counter sent them. A bill flagged
    `bill_no_conflict` is outside the unique bill number index.
    """

    class Status(models.TextChoices):
        PAID = "paid"
        PARTIALLY_REFUNDED = "partially_refunded"
        REFUNDED = "refunded"

    id = models.UUIDField(primary_key=True)
    counter = models.ForeignKey(
        Counter, on_delete=models.PROTECT, related_name="bills", db_index=False
    )
    shift_id = models.UUIDField()
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bills", db_index=False
    )
    bill_no = models.CharField(max_length=9)
    sold_at = models.DateTimeField()
    received_at = models.DateTimeField()
    item_count = _quantity()
    subtotal = _money()
    tax_amount = _money()
    rounding = _money()
    total = _money()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PAID)
    flags = ArrayField(models.CharField(max_length=30), default=list, blank=True)
    rolled_up_at = models.DateTimeField(null=True, blank=True)
    device_id = models.BigIntegerField(null=True, blank=True)
    app_version = models.CharField(max_length=32, blank=True, default="")
    # Phase 2 columns, created now so discounts and customers need no migration.
    discount_type = models.CharField(max_length=10, null=True, blank=True)
    discount_value = _money(null=True, blank=True)
    discount_amount = _money(null=True, blank=True)
    customer_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "bill_no"],
                condition=~models.Q(flags__contains=[BILL_NO_CONFLICT]),
                name="uniq_bill_tenant_bill_no",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "-sold_at", "id"], name="bill_sold_idx"),
            models.Index(fields=["tenant_id", "cashier", "sold_at"], name="bill_cashier_idx"),
            models.Index(fields=["tenant_id", "shift_id"], name="bill_shift_idx"),
            models.Index(
                fields=["tenant_id", "received_at"],
                condition=models.Q(rolled_up_at__isnull=True),
                name="bill_rollup_pending_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.bill_no


class BillItem(TenantModel):
    """One row per product per bill."""

    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="items", db_index=False)
    line_no = models.PositiveIntegerField()
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="bill_items", db_index=False
    )
    name_snapshot = models.CharField(max_length=255)
    barcode_snapshot = models.CharField(max_length=64)
    qty = _quantity()
    unit_price = _money()
    cost_snapshot = _money()
    line_total = _money()
    sold_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "bill", "product"], name="uniq_bill_item_product"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.qty} x {self.name_snapshot}"


class Payment(TenantModel):
    """POC rule: exactly one row per bill (the table allows split payment later)."""

    class Method(models.TextChoices):
        CASH = "cash"
        CARD = "card"
        WALLET = "wallet"

    id = models.UUIDField(primary_key=True)
    bill = models.ForeignKey(
        Bill, on_delete=models.PROTECT, related_name="payments", db_index=False
    )
    method = models.CharField(max_length=10, choices=Method.choices)
    amount = _money()
    tendered = _money(null=True, blank=True)
    change_given = _money(null=True, blank=True)
    reference = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        indexes = [models.Index(fields=["tenant_id", "bill"], name="payment_bill_idx")]

    def __str__(self) -> str:
        return f"{self.method} {self.amount}"


class HeldBill(TenantModel):
    """Best-effort server mirror of a counter's held bills. The id is the
    client UUID; `client_updated_at` is the counter's own change time, so the
    newest version wins whatever order uploads arrive in."""

    class Status(models.TextChoices):
        HELD = "held"
        RECALLED = "recalled"
        DELETED = "deleted"
        ABANDONED = "abandoned"

    id = models.UUIDField(primary_key=True)
    counter = models.ForeignKey(
        Counter, on_delete=models.PROTECT, related_name="held_bills", db_index=False
    )
    shift_id = models.UUIDField(null=True, blank=True)
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="held_bills",
        db_index=False,
    )
    title = models.CharField(max_length=100, blank=True, default="")
    payload = models.JSONField(default=dict)
    total = _money()
    status = models.CharField(max_length=10, choices=Status.choices)
    client_updated_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=["tenant_id", "counter"], name="held_bill_counter_idx")]

    def __str__(self) -> str:
        return self.title or str(self.id)


class Return(TenantModel):
    """A customer bringing items back, uploaded from a counter. The id is the
    client UUID. `refund_total` is the amount paid out as the counter sent it;
    `original_bill` is set when the typed bill number is found."""

    class Reason(models.TextChoices):
        EXPIRED_DAMAGED = "expired_damaged"
        WRONG_ITEM = "wrong_item"
        CHANGED_MIND = "changed_mind"
        PRICE_ERROR = "price_error"

    id = models.UUIDField(primary_key=True)
    counter = models.ForeignKey(
        Counter, on_delete=models.PROTECT, related_name="returns", db_index=False
    )
    shift_id = models.UUIDField()
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="returns", db_index=False
    )
    original_bill_no = models.CharField(max_length=20, null=True, blank=True)
    original_bill = models.ForeignKey(
        Bill,
        on_delete=models.PROTECT,
        related_name="returns",
        null=True,
        blank=True,
        db_index=False,
    )
    reason = models.CharField(max_length=20, choices=Reason.choices)
    restock = models.BooleanField()
    refund_method = models.CharField(max_length=10, choices=Payment.Method.choices)
    paid_from_drawer = models.BooleanField()
    refund_total = _money()
    returned_at = models.DateTimeField()
    received_at = models.DateTimeField()
    flags = ArrayField(models.CharField(max_length=30), default=list, blank=True)
    rolled_up_at = models.DateTimeField(null=True, blank=True)
    device_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant_id", "original_bill"], name="return_bill_idx"),
            models.Index(fields=["tenant_id", "shift_id"], name="return_shift_idx"),
            models.Index(fields=["tenant_id", "cashier", "returned_at"], name="return_cashier_idx"),
            models.Index(
                fields=["tenant_id", "received_at"],
                condition=models.Q(rolled_up_at__isnull=True),
                name="return_rollup_pending_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Return {self.id}"


class ReturnItem(TenantModel):
    """One row per product per return. `bill_item` is set when the product is
    on the found bill; `cost_snapshot` keeps profit right either way."""

    class PriceSource(models.TextChoices):
        PAID = "paid"
        CURRENT = "current"

    return_record = models.ForeignKey(
        Return, on_delete=models.PROTECT, related_name="items", db_index=False
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="return_items", db_index=False
    )
    bill_item = models.ForeignKey(
        BillItem,
        on_delete=models.PROTECT,
        related_name="return_items",
        null=True,
        blank=True,
        db_index=False,
    )
    qty = _quantity()
    price_source = models.CharField(max_length=10, choices=PriceSource.choices)
    unit_price = _money()
    refund_amount = _money()
    tax_refund = _money()
    cost_snapshot = _money()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "return_record", "product"], name="uniq_return_item_product"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_id", "bill_item"], name="return_item_bill_item_idx"),
            models.Index(fields=["tenant_id", "product"], name="return_item_product_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.qty} of {self.product_id}"
