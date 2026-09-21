from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")
WHOLE_RUPEE = Decimal("1")


class Money:
    __slots__ = ("amount",)

    def __init__(self, amount: Decimal | int | str) -> None:
        self.amount = Decimal(amount).quantize(CENTS, rounding=ROUND_HALF_UP)

    @classmethod
    def zero(cls) -> Money:
        return cls(Decimal("0"))

    def __add__(self, other: Money) -> Money:
        return Money(self.amount + other.amount)

    def __sub__(self, other: Money) -> Money:
        return Money(self.amount - other.amount)

    def __mul__(self, multiplier: Decimal | int | str) -> Money:
        return Money(self.amount * Decimal(multiplier))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Money) and self.amount == other.amount

    def __lt__(self, other: Money) -> bool:
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        return self.amount <= other.amount

    def __hash__(self) -> int:
        return hash(self.amount)

    def __repr__(self) -> str:
        return f"Money({self.as_string()!r})"

    def as_string(self) -> str:
        return str(self.amount)

    def round_to_whole_rupee(self) -> Money:
        return Money(self.amount.quantize(WHOLE_RUPEE, rounding=ROUND_HALF_UP))

    def rounding_adjustment(self) -> Money:
        return self.round_to_whole_rupee() - self
