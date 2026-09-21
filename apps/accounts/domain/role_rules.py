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
    has_pin: bool


def validate_role_fields(role: str, fields: RoleFields) -> None:
    if role == CASHIER:
        _validate_cashier(fields)
    elif role in (OWNER, MANAGER):
        _validate_owner_or_manager(fields)
    else:
        raise RoleRuleError(f"Unknown role: {role}")


def _validate_cashier(fields: RoleFields) -> None:
    if fields.has_email or fields.has_username or fields.has_password:
        raise RoleRuleError("Cashiers have no email, username or password.")
    if not fields.has_pin:
        raise RoleRuleError("Cashiers must have a PIN.")


def _validate_owner_or_manager(fields: RoleFields) -> None:
    if fields.has_pin:
        raise RoleRuleError("Owners and managers do not sign in with a PIN.")
    if not (fields.has_email or fields.has_username):
        raise RoleRuleError("Owners and managers need an email or a username.")
    if not fields.has_password:
        raise RoleRuleError("Owners and managers need a password.")
