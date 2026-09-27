"""Resets and rebuilds the demo tenant only. Other tenants are never touched.

The activity log is append-only, so entries from earlier runs stay. The seed
itself writes none: it is set-up data, not a user action.
"""

import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction

from apps.accounts.domain.pin import generate_pin
from apps.accounts.domain.role_rules import CASHIER, OWNER
from apps.accounts.models import PinDelay, User
from apps.accounts.use_cases.staff import set_pin
from apps.catalog.domain.product_rules import name_key, normalize_product_name
from apps.catalog.models import Category, PriceHistory, Product
from apps.inventory.models import StockLevel
from apps.tenants.domain.device_token import generate_device_token, hash_device_token
from apps.tenants.models import Counter, Device, DeviceCode, Tenant, TenantSettings
from apps.tenants.use_cases.activation_codes import IssuedCode, issue_activation_code
from scripts.seed.sample_data import (
    CASHIERS,
    CATEGORIES,
    OWNER_NAME,
    OWNER_USERNAME,
    STORE_NAME,
    TENANT_SLUG,
    TIMEZONE,
    SampleCounter,
    SampleProduct,
)

# Children before parents, so no PROTECT foreign key blocks a delete.
RESET_ORDER = (
    PinDelay,
    StockLevel,
    PriceHistory,
    Product,
    Category,
    Device,
    DeviceCode,
    User,
    Counter,
)
_BATCH_SIZE = 2000


@dataclass(frozen=True)
class SeedResult:
    tenant: Tenant
    owner_password: str
    pins: dict[str, str]
    device_tokens: dict[str, str]
    activation_codes: dict[str, IssuedCode]
    product_count: int


def seed_demo_tenant(
    now: datetime, counters: Sequence[SampleCounter], products: Sequence[SampleProduct]
) -> SeedResult:
    with transaction.atomic():
        tenant = _reset_tenant()
        counter_rows = _create_counters(tenant, counters)
        owner, password = _create_owner(tenant)
        pins = _create_cashiers(tenant, counter_rows)
        tokens = _activate_counters(counters, counter_rows, now)
        _create_catalogue(tenant, products)
        codes = {
            sample.code: issue_activation_code(
                tenant.id, counter_rows[sample.code].id, owner.id, now
            )
            for sample in counters
            if not sample.activated
        }
    return SeedResult(tenant, password, pins, tokens, codes, len(products))


def _reset_tenant() -> Tenant:
    tenant, _ = Tenant.objects.update_or_create(
        slug=TENANT_SLUG,
        defaults={"name": STORE_NAME, "timezone": TIMEZONE, "status": "active"},
    )
    for model in RESET_ORDER:
        model.objects.for_tenant(tenant.id).delete()
    TenantSettings.objects.filter(tenant=tenant).delete()
    TenantSettings.objects.create(tenant=tenant, store_name=STORE_NAME)
    return tenant


def _create_counters(tenant: Tenant, counters: Sequence[SampleCounter]) -> dict[str, Counter]:
    rows = Counter.objects.bulk_create(
        [Counter(tenant_id=tenant.id, code=sample.code, name=sample.name) for sample in counters]
    )
    return {row.code: row for row in rows}


def _create_owner(tenant: Tenant) -> tuple[User, str]:
    password = secrets.token_urlsafe(12)
    owner = User(tenant_id=tenant.id, full_name=OWNER_NAME, role=OWNER, username=OWNER_USERNAME)
    owner.set_password(password)
    owner.save()
    return owner, password


def _create_cashiers(tenant: Tenant, counters: dict[str, Counter]) -> dict[str, str]:
    pins = {}
    for sample in CASHIERS:
        counter = counters.get(sample.counter_code or "")
        cashier = User(
            tenant_id=tenant.id,
            full_name=sample.full_name,
            role=CASHIER,
            is_active=sample.is_active,
            default_counter_id=counter.id if counter else None,
        )
        pins[sample.full_name] = generate_pin()
        set_pin(cashier, pins[sample.full_name])
        cashier.save()
    return pins


def _activate_counters(
    counters: Sequence[SampleCounter], rows: dict[str, Counter], now: datetime
) -> dict[str, str]:
    tokens = {sample.code: generate_device_token() for sample in counters if sample.activated}
    Device.objects.bulk_create(
        [
            Device(
                tenant_id=rows[code].tenant_id,
                counter=rows[code],
                token_hash=hash_device_token(token),
                last_seen_at=now,
            )
            for code, token in tokens.items()
        ]
    )
    return tokens


def _create_catalogue(tenant: Tenant, products: Sequence[SampleProduct]) -> None:
    categories = {
        sample.name: Category(
            tenant_id=tenant.id, name=sample.name, tint=sample.tint, sort_order=order
        )
        for order, sample in enumerate(CATEGORIES, start=1)
    }
    Category.objects.bulk_create(categories.values())
    rows = Product.objects.bulk_create(
        [_product_row(tenant, categories[sample.category], sample) for sample in products],
        batch_size=_BATCH_SIZE,
    )
    StockLevel.objects.bulk_create(
        [
            StockLevel(tenant_id=tenant.id, product=row, qty=sample.stock)
            for row, sample in zip(rows, products, strict=True)
        ],
        batch_size=_BATCH_SIZE,
    )


def _product_row(tenant: Tenant, category: Category, sample: SampleProduct) -> Product:
    return Product(
        tenant_id=tenant.id,
        barcode=sample.barcode,
        name=normalize_product_name(sample.name),
        name_lc=name_key(sample.name),
        category=category,
        unit=sample.unit,
        price=sample.price,
        cost=sample.cost,
        low_stock_alert=sample.low_stock_alert,
    )
