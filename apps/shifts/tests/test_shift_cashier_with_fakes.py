import pytest

from apps.shifts.domain.errors import CashierNotFoundError
from apps.shifts.use_cases.cashier import shift_cashier


class FakeUsers:
    def __init__(self, active_ids: set[int]) -> None:
        self.active_ids = active_ids

    def active_cashier(self, tenant_id: int, user_id: int):
        return object() if user_id in self.active_ids else None


def test_a_cashier_token_wins_over_the_body():
    assert shift_cashier(1, token_cashier_id=5, body_cashier_id=9, users=FakeUsers(set())) == 5


def test_a_pc_token_takes_an_active_cashier_from_the_body():
    assert shift_cashier(1, token_cashier_id=None, body_cashier_id=9, users=FakeUsers({9})) == 9


@pytest.mark.parametrize("body_cashier_id", [None, 4])
def test_a_pc_token_without_an_active_cashier_is_refused(body_cashier_id):
    with pytest.raises(CashierNotFoundError):
        shift_cashier(1, None, body_cashier_id, users=FakeUsers({9}))
