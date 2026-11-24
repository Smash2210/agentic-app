"""The one rounding rule for money (research R-04)."""

from decimal import ROUND_HALF_UP, Decimal

# 2-decimal precision is fixed by Constitution IV and POL-CURRENCY §3; it is the one
# permitted numeric constant in the money path.
CENT = Decimal("0.01")


def to_cents(value: Decimal) -> Decimal:
    """Round half-up to 2 decimal places. Refuses anything that is not a Decimal."""
    if not isinstance(value, Decimal):
        raise TypeError(f"money must be a Decimal, got {type(value).__name__}")
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
