from rest_framework import serializers

from apps.tenants.models import TenantSettings


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
