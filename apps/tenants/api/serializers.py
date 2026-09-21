from rest_framework import serializers

from apps.tenants.domain.counter_rules import format_bill_no, is_valid_counter_code, next_bill_no
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


class CounterSerializer(serializers.ModelSerializer):
    next_bill_no = serializers.SerializerMethodField()

    class Meta:
        model = Counter
        fields = ["id", "name", "code", "is_active", "last_bill_seq", "next_bill_no"]
        read_only_fields = ["last_bill_seq"]

    def validate_code(self, value: str) -> str:
        if not is_valid_counter_code(value):
            raise serializers.ValidationError("Counter code must be exactly 3 digits.")
        return value

    def get_next_bill_no(self, obj: Counter) -> str:
        return format_bill_no(obj.code, next_bill_no(obj.last_bill_seq))
