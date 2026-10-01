"""Pre-summed report tables. The rollup job fills them from uploaded bills
(and returns, as negative deltas); reports read only these tables."""

from django.db import models

from apps.core.models import TenantModel


def _money() -> models.DecimalField:
    return models.DecimalField(max_digits=14, decimal_places=2, default=0, db_default=0)


def _quantity() -> models.DecimalField:
    return models.DecimalField(max_digits=14, decimal_places=3, default=0, db_default=0)


class SalesTotals(TenantModel):
    bills = models.PositiveIntegerField(default=0, db_default=0)
    items = _quantity()
    gross = _money()
    tax = _money()
    cash = _money()
    card = _money()
    wallet = _money()
    cost = _money()
    refund_count = models.PositiveIntegerField(default=0, db_default=0)
    refund_amount = _money()
    refund_cost_recovered = _money()

    class Meta:
        abstract = True


class SalesHourly(SalesTotals):
    counter_id = models.BigIntegerField()
    hour_start = models.DateTimeField()

    class Meta:
        db_table = "sales_hourly"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "counter_id", "hour_start"], name="uniq_sales_hourly"
            ),
        ]


class SalesDaily(SalesTotals):
    local_date = models.DateField()

    class Meta:
        db_table = "sales_daily"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "local_date"], name="uniq_sales_daily"),
        ]


class SalesDailyProduct(TenantModel):
    local_date = models.DateField()
    product_id = models.BigIntegerField()
    qty = _quantity()
    revenue = _money()
    cost = _money()
    returns_qty = _quantity()
    refund_amount = _money()

    class Meta:
        db_table = "sales_daily_product"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "local_date", "product_id"], name="uniq_sales_daily_product"
            ),
        ]


class SalesDailyCashier(TenantModel):
    """Rows for deactivated cashiers stay: refunds by cashier include them."""

    local_date = models.DateField()
    cashier_id = models.BigIntegerField()
    bills = models.PositiveIntegerField(default=0, db_default=0)
    revenue = _money()
    refund_count = models.PositiveIntegerField(default=0, db_default=0)
    refund_amount = _money()

    class Meta:
        db_table = "sales_daily_cashier"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "local_date", "cashier_id"], name="uniq_sales_daily_cashier"
            ),
        ]


class PurchasesDaily(TenantModel):
    """Stock bought per delivery date; filled when a stock receipt is confirmed."""

    local_date = models.DateField()
    amount = _money()

    class Meta:
        db_table = "purchases_daily"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "local_date"], name="uniq_purchases_daily"
            ),
        ]
