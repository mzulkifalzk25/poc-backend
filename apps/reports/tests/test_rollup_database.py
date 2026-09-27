import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.core.management import CommandError, call_command
from django.db import connection, transaction

from apps.reports.models import SalesDaily, SalesDailyCashier, SalesDailyProduct, SalesHourly
from apps.reports.use_cases.rollup import roll_up_pending
from apps.sales.models import Bill, BillItem, Payment
from apps.sales.tests.factories import make_product
from apps.shifts.tests.conftest import make_cashier
from apps.tenants.models import Counter
from apps.tenants.tests.helpers import make_tenant

D = Decimal
SEPT_19_NOON_KARACHI = datetime(2026, 9, 19, 7, 0, tzinfo=UTC)


def sell(counter, cashier, product, qty="2", method="cash", sold_at=SEPT_19_NOON_KARACHI):
    total = product.price * D(qty)
    bill = Bill.objects.create(
        id=uuid4(),
        tenant_id=counter.tenant_id,
        counter=counter,
        shift_id=uuid4(),
        cashier=cashier,
        bill_no=f"{counter.code}{uuid4().int % 10**6:06d}",
        sold_at=sold_at,
        received_at=datetime.now(UTC),
        item_count=D(qty),
        subtotal=total,
        tax_amount=D("0"),
        rounding=D("0"),
        total=total,
    )
    BillItem.objects.create(
        tenant_id=counter.tenant_id,
        bill=bill,
        line_no=1,
        product=product,
        name_snapshot=product.name,
        barcode_snapshot=product.barcode,
        qty=D(qty),
        unit_price=product.price,
        cost_snapshot=product.cost,
        line_total=total,
        sold_at=sold_at,
    )
    Payment.objects.create(
        id=uuid4(), tenant_id=counter.tenant_id, bill=bill, method=method, amount=total
    )
    return bill


def shop(slug="fresh-basket-mart"):
    tenant = make_tenant(slug=slug)
    counter = Counter.objects.create(tenant_id=tenant.id, name="Counter 2", code="002")
    return counter, make_cashier(tenant), make_product(tenant.id, price="620.00", cost="540.00")


@pytest.mark.django_db
def test_rolls_bills_up_into_every_report_table_once():
    counter, cashier, oil = shop()
    sell(counter, cashier, oil)
    sell(counter, cashier, oil, qty="1", method="card")

    assert roll_up_pending(datetime.now(UTC)) == 2
    assert roll_up_pending(datetime.now(UTC)) == 0

    day = SalesDaily.objects.get(tenant_id=counter.tenant_id)
    assert day.local_date == date(2026, 9, 19)
    assert (day.bills, day.items, day.gross) == (2, D("3"), D("1860"))
    assert (day.cash, day.card, day.cost) == (D("1240"), D("620"), D("1620"))
    hour = SalesHourly.objects.get(tenant_id=counter.tenant_id)
    assert (hour.counter_id, hour.bills) == (counter.id, 2)
    product = SalesDailyProduct.objects.get(tenant_id=counter.tenant_id)
    assert (product.product_id, product.qty, product.revenue) == (oil.id, D("3"), D("1860"))
    by_cashier = SalesDailyCashier.objects.get(tenant_id=counter.tenant_id)
    assert (by_cashier.cashier_id, by_cashier.bills) == (cashier.id, 2)
    assert not Bill.objects.filter(rolled_up_at__isnull=True).exists()


@pytest.mark.django_db
def test_a_later_upload_adds_to_its_own_sale_day():
    counter, cashier, oil = shop()
    sell(counter, cashier, oil)
    roll_up_pending(datetime.now(UTC))

    sell(counter, cashier, oil, sold_at=SEPT_19_NOON_KARACHI - timedelta(days=1))
    sell(counter, cashier, oil, qty="1")
    roll_up_pending(datetime.now(UTC))

    days = dict(
        SalesDaily.objects.filter(tenant_id=counter.tenant_id).values_list("local_date", "gross")
    )
    assert days == {date(2026, 9, 18): D("1240"), date(2026, 9, 19): D("1860")}


@pytest.mark.django_db
def test_tenants_never_share_rows():
    first = shop()
    second = shop(slug="other-mart")
    sell(*first)
    sell(*second, qty="1")

    roll_up_pending(datetime.now(UTC))

    grosses = dict(SalesDaily.objects.values_list("tenant_id", "gross"))
    assert grosses == {first[0].tenant_id: D("1240"), second[0].tenant_id: D("620")}


@pytest.mark.django_db
def test_the_command_reports_how_many_bills_it_added(capsys):
    sell(*shop())

    call_command("run_rollup")

    assert "Rolled up 1 bills." in capsys.readouterr().out


@pytest.mark.django_db(transaction=True)
def test_skips_a_bill_another_transaction_holds_and_takes_it_later():
    counter, cashier, oil = shop()
    held = sell(counter, cashier, oil)
    free = sell(counter, cashier, oil, qty="1")
    locked, release = threading.Event(), threading.Event()

    def hold_one_bill():
        with transaction.atomic():
            Bill.objects.select_for_update().get(id=held.id)
            locked.set()
            release.wait(timeout=10)
        connection.close()

    holder = threading.Thread(target=hold_one_bill)
    holder.start()
    locked.wait(timeout=10)
    try:
        assert roll_up_pending(datetime.now(UTC)) == 1
    finally:
        release.set()
        holder.join()

    assert Bill.objects.get(id=free.id).rolled_up_at is not None
    assert Bill.objects.get(id=held.id).rolled_up_at is None
    assert roll_up_pending(datetime.now(UTC)) == 1
    assert SalesDaily.objects.get(tenant_id=counter.tenant_id).bills == 2


@pytest.mark.django_db(transaction=True)
def test_the_command_refuses_to_run_while_another_runner_holds_the_lock():
    sell(*shop())
    locked, release = threading.Event(), threading.Event()

    def other_runner():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(7302, 0)")
            locked.set()
            release.wait(timeout=10)
            cursor.execute("SELECT pg_advisory_unlock(7302, 0)")
        connection.close()

    holder = threading.Thread(target=other_runner)
    holder.start()
    locked.wait(timeout=10)
    try:
        with pytest.raises(CommandError, match="Another rollup is running"):
            call_command("run_rollup")
    finally:
        release.set()
        holder.join()

    assert Bill.objects.filter(rolled_up_at__isnull=True).count() == 1
    call_command("run_rollup")
    assert not Bill.objects.filter(rolled_up_at__isnull=True).exists()
