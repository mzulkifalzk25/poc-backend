import pytest

from apps.accounts.domain.role_rules import RoleFields, RoleRuleError, validate_role_fields


def test_cashier_needs_a_pin_and_nothing_else():
    validate_role_fields(
        "cashier", RoleFields(has_email=False, has_username=False, has_password=False, has_pin=True)
    )


def test_cashier_cannot_have_email_username_or_password():
    with pytest.raises(RoleRuleError):
        validate_role_fields(
            "cashier",
            RoleFields(has_email=True, has_username=False, has_password=False, has_pin=True),
        )


def test_cashier_without_a_pin_is_rejected():
    with pytest.raises(RoleRuleError):
        validate_role_fields(
            "cashier",
            RoleFields(has_email=False, has_username=False, has_password=False, has_pin=False),
        )


def test_owner_and_manager_need_a_password_and_email_or_username():
    validate_role_fields(
        "owner", RoleFields(has_email=True, has_username=False, has_password=True, has_pin=False)
    )
    validate_role_fields(
        "manager", RoleFields(has_email=False, has_username=True, has_password=True, has_pin=False)
    )


def test_owner_without_a_password_is_rejected():
    with pytest.raises(RoleRuleError):
        validate_role_fields(
            "owner",
            RoleFields(has_email=True, has_username=False, has_password=False, has_pin=False),
        )


def test_owner_without_email_or_username_is_rejected():
    with pytest.raises(RoleRuleError):
        validate_role_fields(
            "owner",
            RoleFields(has_email=False, has_username=False, has_password=True, has_pin=False),
        )


def test_owner_cannot_have_a_pin():
    with pytest.raises(RoleRuleError):
        validate_role_fields(
            "owner", RoleFields(has_email=True, has_username=False, has_password=True, has_pin=True)
        )


def test_unknown_role_is_rejected():
    with pytest.raises(RoleRuleError):
        validate_role_fields(
            "superadmin",
            RoleFields(has_email=True, has_username=False, has_password=True, has_pin=False),
        )
