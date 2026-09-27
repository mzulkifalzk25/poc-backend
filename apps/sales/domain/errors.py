class BatchBusyError(Exception):
    """Another batch for this counter is being written."""


class BillIdTakenError(Exception):
    """The bill or payment UUID is already stored."""


class BillNotFoundError(Exception):
    pass


class HeldBillIdTakenError(Exception):
    """The held-bill UUID belongs to another counter or tenant."""
