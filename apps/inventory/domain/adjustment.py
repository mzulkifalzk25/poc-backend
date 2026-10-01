from decimal import Decimal

MODES = ("add", "remove", "set")
REASONS = ("received", "damaged", "expired", "stolen_lost", "count_correction")


def movement_type(mode: str) -> str:
    return {"add": "adjust_add", "remove": "adjust_remove", "set": "count_correction"}[mode]


def adjustment_delta(mode: str, qty: Decimal, before: Decimal) -> Decimal:
    """What the stock level changes by. `set` is an exact count, so the change
    is whatever reaches it; `remove` may take the level below zero (allowed)."""
    if mode == "add":
        return qty
    if mode == "remove":
        return -qty
    return qty - before
