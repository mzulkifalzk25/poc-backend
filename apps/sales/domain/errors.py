class BatchBusyError(Exception):
    """Another batch for this counter is being written."""


class BillIdTakenError(Exception):
    """The bill or payment UUID is already stored."""
