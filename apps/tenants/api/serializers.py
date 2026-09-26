from datetime import datetime
from decimal import Decimal

from rest_framework import serializers

from apps.tenants.domain.counter_rules import (
    counter_status,
    format_bill_no,
    is_valid_counter_code,
    next_bill_no,
)
from apps.tenants.domain.settings_rules import is_valid_tax_rate
from apps.tenants.models import Counter, TenantSettings


class TenantSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantSettings
        fields = [
            "store_name",
            "phone",
            "address",
            "logo",
            "currency",
            "tax_rate",
            "prices_include_tax",
            "block_when_out_of_stock",
            "receipt_paper_mm",
            "receipt_header",
            "receipt_footer",
            "receipt_show_barcode",
        ]
        read_only_fields = ["currency"]

    def validate_tax_rate(self, value: Decimal) -> Decimal:
        if not is_valid_tax_rate(value):
            raise serializers.ValidationError("Tax rate is a percent from 0 to 100.")
        return value


class CounterSerializer(serializers.ModelSerializer):
    """Device fields come from `counters_with_device_state`; a counter read
    without those annotations (just created) has no PC and no code yet."""

    status = serializers.SerializerMethodField()
    code_expires_at = serializers.SerializerMethodField()
    last_seen_at = serializers.SerializerMethodField()
    app_version = serializers.SerializerMethodField()
    unsynced_count = serializers.SerializerMethodField()
    next_bill_no = serializers.SerializerMethodField()
    has_open_shift = serializers.SerializerMethodField()
    has_bills = serializers.SerializerMethodField()

    class Meta:
        model = Counter
        fields = [
            "id",
            "name",
            "code",
            "is_active",
            "status",
            "code_expires_at",
            "last_seen_at",
            "app_version",
            "last_bill_seq",
            "next_bill_no",
            "unsynced_count",
            "has_open_shift",
            "has_bills",
        ]
        read_only_fields = ["last_bill_seq"]

    def validate_code(self, value: str) -> str:
        if not is_valid_counter_code(value):
            raise serializers.ValidationError("Counter code must be exactly 3 digits.")
        return value

    def get_status(self, obj: Counter) -> str:
        return counter_status(
            has_live_device=getattr(obj, "has_live_device", False),
            has_ready_code=getattr(obj, "ready_code_expires_at", None) is not None,
            had_revoked_device=getattr(obj, "had_revoked_device", False),
        )

    def get_code_expires_at(self, obj: Counter) -> str | None:
        if self.get_status(obj) != "code_ready":
            return None
        return _iso(obj.ready_code_expires_at)

    def get_last_seen_at(self, obj: Counter) -> str | None:
        return _iso(getattr(obj, "live_last_seen_at", None))

    def get_app_version(self, obj: Counter) -> str | None:
        return getattr(obj, "live_app_version", None)

    def get_unsynced_count(self, obj: Counter) -> int | None:
        return getattr(obj, "live_unsynced_count", None)

    def get_next_bill_no(self, obj: Counter) -> str:
        return format_bill_no(obj.code, next_bill_no(obj.last_bill_seq))

    def get_has_open_shift(self, obj: Counter) -> bool:
        return False  # shifts arrive in Step B5

    def get_has_bills(self, obj: Counter) -> bool:
        return obj.last_bill_seq > 0


def _iso(value: datetime | None) -> str | None:
    return serializers.DateTimeField().to_representation(value) if value else None
