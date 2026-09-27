class ShiftAlreadyOpenError(Exception):
    """The counter already has an open shift."""


class ShiftIdTakenError(Exception):
    """The client UUID belongs to another counter's or tenant's shift."""


class ShiftNotFoundError(Exception):
    pass


class CashierNotFoundError(Exception):
    """`cashier_id` is not an active cashier of the tenant."""
