from dataclasses import dataclass

OWNER = "owner"
MANAGER = "manager"
CASHIER = "cashier"
ROLES = (OWNER, MANAGER, CASHIER)


class RoleRuleError(ValueError):
    pass


@dataclass(frozen=True)
class RoleFields:
    has_email: bool
    has_username: bool
    has_password: bool


def validate_role_fields(role: str, fields: RoleFields) -> None:
    """Every role signs in with email or username, and a password."""
    if role not in ROLES:
        raise RoleRuleError(f"Unknown role: {role}")
    if not (fields.has_email or fields.has_username):
        raise RoleRuleError("Staff need an email or a username.")
    if not fields.has_password:
        raise RoleRuleError("Staff need a password.")
