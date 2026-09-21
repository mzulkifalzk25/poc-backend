from decimal import Decimal

from django.db import models

from apps.core.models import TenantModel


class Tenant(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    plan = models.CharField(max_length=50, default="poc")
    status = models.CharField(max_length=20, default="active")
    timezone = models.CharField(max_length=50, default="Asia/Karachi")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name


class TenantSettings(models.Model):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="settings")
    store_name = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    address = models.CharField(max_length=255, blank=True, default="")
    logo = models.CharField(max_length=255, blank=True, default="")
    currency = models.CharField(max_length=3, default="PKR")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    prices_include_tax = models.BooleanField(default=False)
    block_when_out_of_stock = models.BooleanField(default=False)
    receipt_paper_mm = models.PositiveSmallIntegerField(default=80)
    receipt_header = models.CharField(max_length=255, blank=True, default="")
    receipt_footer = models.CharField(max_length=255, blank=True, default="")
    receipt_show_barcode = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Settings for {self.tenant.name}"

    def save(self, *args, **kwargs) -> None:
        self.currency = "PKR"  # fixed, display only (contract section 2)
        super().save(*args, **kwargs)


class Counter(TenantModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=3)
    is_active = models.BooleanField(default=True)
    last_bill_seq = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "code"], name="uniq_counter_tenant_code"),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"
