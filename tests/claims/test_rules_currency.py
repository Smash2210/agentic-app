"""Currency conversion and unsupported currencies (spec FR-012, FR-013; POL-CURRENCY §2–4)."""

from decimal import Decimal as D

import pytest


@pytest.mark.parametrize(
    ("amount", "currency", "usd"),
    [
        ("30.00", "EUR", "32.40"),
        ("10.01", "EUR", "10.81"),  # 10.8108 rounded (POL-CURRENCY §3 example)
        ("18.00", "GBP", "22.86"),
        ("2083.75", "INR", "25.01"),  # 25.005 rounds half-up
        ("12.34", "USD", "12.34"),
    ],
)
def test_line_is_converted_and_rounded_half_up(make_claim, check, amount, currency, usd):
    result = check(make_claim({"category": "transport", "amount": amount, "currency": currency}))

    line = result.lines[0]
    assert line.claimed_usd == D(usd)
    assert line.reimbursable_usd == D(usd)
    assert line.rejected_usd == D("0.00")
    assert result.violations == []


def test_each_line_is_converted_separately(make_claim, check):
    result = check(make_claim(
        {"category": "transport", "amount": "10.01", "currency": "EUR"},
        {"category": "other", "amount": "10.01", "currency": "EUR"},
    ))

    assert [line.claimed_usd for line in result.lines] == [D("10.81"), D("10.81")]
    assert result.lines_reimbursable_usd == D("21.62")


def test_amounts_have_two_decimal_places(make_claim, check):
    result = check(make_claim({"category": "transport", "amount": "18.00", "currency": "GBP"}))

    line = result.lines[0]
    for value in (line.claimed_usd, line.reimbursable_usd, line.rejected_usd):
        assert value.as_tuple().exponent == -2


def test_unsupported_currency_is_rejected_and_rest_is_checked(make_claim, check):
    result = check(make_claim(
        {"category": "meal", "amount": "1500.00", "currency": "JPY"},
        {"category": "meal", "amount": "30.00", "currency": "EUR"},
    ))

    jpy, eur = result.lines
    assert jpy.claimed_usd is None
    assert jpy.rejected_usd is None
    assert jpy.reimbursable_usd == D("0.00")
    assert eur.claimed_usd == D("32.40")
    assert eur.reimbursable_usd == D("32.40")

    [violation] = result.violations
    assert violation.rule_id == "CURRENCY_UNSUPPORTED"
    assert violation.line_nos == [1]
    assert violation.date is None
    assert violation.excess_usd is None
    assert violation.citation.doc_id == "POL-CURRENCY"
    assert violation.citation.sections == ["2"]
    assert "JPY" in violation.message


def test_unsupported_currency_line_does_not_need_a_receipt_check(make_claim, check):
    # No USD amount exists, so the receipt rule cannot apply; only the currency rule fires.
    result = check(make_claim({"amount": "5000.00", "currency": "JPY", "receipt_attached": False}))

    assert [v.rule_id for v in result.violations] == ["CURRENCY_UNSUPPORTED"]


def test_unsupported_currency_adds_nothing_to_totals(make_claim, check):
    result = check(make_claim(
        {"category": "transport", "amount": "1500.00", "currency": "JPY"},
        {"category": "transport", "amount": "20.00", "currency": "USD"},
    ))

    assert result.lines_reimbursable_usd == D("20.00")
    assert result.total_reimbursable_usd == D("20.00") + result.per_diem.amount_usd
