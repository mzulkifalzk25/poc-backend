import pytest

from apps.accounts.domain.role_rules import RoleFields, RoleRuleError, validate_role_fields


@pytest.mark.parametrize("role", ["owner", "manager", "cashier"])
def test_every_role_needs_a_password_and_email_or_username(role):
    validate_role_fields(role, RoleFields(has_email=True, has_username=False, has_password=True))
    validate_role_fields(role, RoleFields(has_email=False, has_username=True, has_password=True))


@pytest.mark.parametrize("role", ["owner", "manager", "cashier"])
def test_a_role_without_a_password_is_rejected(role):
    with pytest.raises(RoleRuleError):
        validate_role_fields(
            role, RoleFields(has_email=True, has_username=False, has_password=False)
        )


@pytest.mark.parametrize("role", ["owner", "manager", "cashier"])
def test_a_role_without_email_or_username_is_rejected(role):
    with pytest.raises(RoleRuleError):
        validate_role_fields(
            role, RoleFields(has_email=False, has_username=False, has_password=True)
        )


def test_unknown_role_is_rejected():
    with pytest.raises(RoleRuleError):
        validate_role_fields(
            "superadmin",
            RoleFields(has_email=True, has_username=False, has_password=True),
        )
