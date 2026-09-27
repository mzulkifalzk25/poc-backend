"""Events a counter uploads for the activity log. Only these are accepted."""

PIN_FAILURE = "pin_failure"
HELD_BILL_DELETED = "held_bill_deleted"
CLIENT_ACTIONS = frozenset({PIN_FAILURE, HELD_BILL_DELETED})


def is_client_action(action: str) -> bool:
    return action in CLIENT_ACTIONS
