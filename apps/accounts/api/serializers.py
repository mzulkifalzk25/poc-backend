from rest_framework import serializers

from apps.accounts.domain.names import normalize_full_name
from apps.accounts.domain.role_rules import CASHIER, ROLES


class LoginRequestSerializer(serializers.Serializer):
    login = serializers.CharField()
    password = serializers.CharField()


class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class _BlankAsNullCharField(serializers.CharField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        return value or None


class StaffCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    role = serializers.ChoiceField(choices=ROLES, default=CASHIER)
    password = serializers.CharField(write_only=True)
    email = _BlankAsNullCharField(required=False, allow_null=True, allow_blank=True, max_length=254)
    username = _BlankAsNullCharField(
        required=False, allow_null=True, allow_blank=True, max_length=150
    )
    default_counter_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_full_name(self, value: str) -> str:
        return _non_empty_name(value)


class StaffUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255, required=False)
    email = _BlankAsNullCharField(required=False, allow_null=True, allow_blank=True, max_length=254)
    username = _BlankAsNullCharField(
        required=False, allow_null=True, allow_blank=True, max_length=150
    )
    default_counter_id = serializers.IntegerField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)

    def validate_full_name(self, value: str) -> str:
        return _non_empty_name(value)


class StaffFilterSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=ROLES, required=False)
    status = serializers.ChoiceField(choices=["active", "deactivated"], required=False)
    counter = serializers.IntegerField(required=False)


def _non_empty_name(value: str) -> str:
    name = normalize_full_name(value)
    if not name:
        raise serializers.ValidationError("Full name is required.")
    return name
