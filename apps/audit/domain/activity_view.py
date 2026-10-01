"""How activity-log rows read on the owner's screen: filter groups, a plain
label and details line for each action, and the Info or Review flag."""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

TYPE_ACTIONS = {
    "price": ["price_changed"],
    "refund": ["return_processed"],
    "held_bill": ["held_bill_deleted"],
    "stock": ["stock_adjusted", "stock_received"],
    "shift": ["shift_opened", "shift_closed"],
}
TYPES = ("all", *TYPE_ACTIONS)


def actions_for(kind: str) -> list[str] | None:
    return TYPE_ACTIONS.get(kind)


@dataclass(frozen=True)
class Names:
    users: dict[int, str] = field(default_factory=dict)
    products: dict[str, str] = field(default_factory=dict)
    counters: dict[int, str] = field(default_factory=dict)


def rupees(value: str | None) -> str:
    amount = Decimal(value or "0").quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"Rs {amount:,}"


def first_name(full_name: str | None) -> str:
    return full_name.split()[0] if full_name else "unknown"


def label(action: str) -> str:
    return {
        "price_changed": "Price change",
        "return_processed": "Refund",
        "held_bill_deleted": "Held bill deleted",
        "stock_adjusted": "Stock adjustment",
        "stock_received": "Stock received",
        "shift_opened": "Shift opened",
        "shift_closed": "Shift closed",
    }.get(action, action.replace("_", " ").capitalize())


def is_review(action: str, detail: dict) -> bool:
    """Every refund, every held bill deleted, and a cash difference at close."""
    if action in ("return_processed", "held_bill_deleted"):
        return True
    if action == "shift_closed":
        return Decimal(detail.get("difference") or "0") != 0
    return False


def describe(
    action: str, user_id: int | None, entity_id: str, before, after, detail, names: Names
) -> str:
    detail = detail or {}
    who = first_name(names.users.get(user_id) if user_id else None)
    product = names.products.get(entity_id, f"product {entity_id}")
    if action == "return_processed":
        items = len(detail.get("items") or [])
        noun = "item" if items == 1 else "items"
        return f"cashier {who} · {items} {noun} · {rupees(detail.get('amount'))}"
    if action == "price_changed":
        old, new = (before or {}).get("price"), (after or {}).get("price")
        return f"{product} · {rupees(old)} to {rupees(new)}"
    if action == "held_bill_deleted":
        title = detail.get("title") or "Held bill"
        return f"cashier {who} · {title} · {rupees(detail.get('total'))}"
    if action == "stock_adjusted":
        return _stock_adjusted(product, before, after, detail)
    if action == "stock_received":
        lines = detail.get("lines", 0)
        return f"{detail.get('supplier', '')} · {lines} lines · {rupees(detail.get('total_cost'))}"
    if action in ("shift_opened", "shift_closed"):
        return _shift(action, who, detail, names)
    return who if user_id else ""


def _stock_adjusted(product: str, before, after, detail: dict) -> str:
    change = Decimal((after or {}).get("qty", "0")) - Decimal((before or {}).get("qty", "0"))
    sign = "+" if change >= 0 else "-"
    reason = (detail.get("reason") or "").replace("_", " ")
    return f"{product} · {sign}{abs(change).normalize():f} · {reason}"


def _shift(action: str, who: str, detail: dict, names: Names) -> str:
    counter = names.counters.get(detail.get("counter_id"), "counter")
    if action == "shift_opened":
        return f"{who} · {counter} · opening cash {rupees(detail.get('opening_cash'))}"
    difference = Decimal(detail.get("difference") or "0")
    if difference == 0:
        return f"{who} · {counter} · cash matched"
    word = "over" if difference > 0 else "short"
    return f"{who} · {counter} · {rupees(str(abs(difference)))} {word}"
