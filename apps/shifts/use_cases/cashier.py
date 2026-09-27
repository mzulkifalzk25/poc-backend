from apps.accounts.repositories.users import UserRepository, user_repository
from apps.shifts.domain.errors import CashierNotFoundError


def shift_cashier(
    tenant_id: int,
    token_cashier_id: int | None,
    body_cashier_id: int | None,
    users: UserRepository = user_repository,
) -> int:
    """A cashier token names its own cashier. A PC token (a cashier signed in
    offline) must name an active cashier of the tenant in the body."""
    if token_cashier_id is not None:
        return token_cashier_id
    if body_cashier_id is None or users.active_cashier(tenant_id, body_cashier_id) is None:
        raise CashierNotFoundError
    return body_cashier_id
