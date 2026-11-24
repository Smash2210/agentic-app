from decimal import Decimal

import pytest

from agentic_app.claims.money import to_cents


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.005", "0.01"),  # half a cent rounds up
        ("0.004", "0.00"),
        ("25.005", "25.01"),  # receipt threshold boundary (POL-RECEIPTS §1)
        ("10.8108", "10.81"),  # POL-CURRENCY §3 example
        ("2.675", "2.68"),  # would be 2.67 with binary floats
    ],
)
def test_rounds_half_up_to_cents(value, expected):
    assert to_cents(Decimal(value)) == Decimal(expected)


@pytest.mark.parametrize("value", ["54", "54.00", "0", "583.2"])
def test_exact_values_keep_their_value(value):
    assert to_cents(Decimal(value)) == Decimal(value)


@pytest.mark.parametrize("value", ["54", "0.1", "1.005", "123.4567"])
def test_result_always_has_two_decimal_places(value):
    assert to_cents(Decimal(value)).as_tuple().exponent == -2


def test_float_is_refused():
    with pytest.raises(TypeError):
        to_cents(10.81)  # type: ignore[arg-type]
