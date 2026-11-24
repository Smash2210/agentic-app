"""Meals daily limit of 75 USD per calendar day (spec FR-016; POL-MEALS §1, §3)."""

from datetime import date
from decimal import Decimal as D

import pytest

DAY = "2026-03-10"


def meals(result):
    return [v for v in result.violations if v.rule_id == "MEALS_DAILY_LIMIT"]


@pytest.mark.parametrize("amount", ["74.99", "75.00"])
def test_at_or_below_limit(make_claim, check, amount):
    result = check(make_claim({"amount": amount}))

    assert result.violations == []
    assert result.lines[0].reimbursable_usd == D(amount)


def test_one_cent_over_limit(make_claim, check):
    result = check(make_claim({"amount": "75.01"}))

    line = result.lines[0]
    assert line.reimbursable_usd == D("75.00")
    assert line.rejected_usd == D("0.01")

    [violation] = result.violations
    assert violation.rule_id == "MEALS_DAILY_LIMIT"
    assert violation.line_nos == [1]
    assert violation.date == date(2026, 3, 10)
    assert violation.excess_usd == D("0.01")
    assert violation.citation.doc_id == "POL-MEALS"
    assert violation.citation.sections == ["1", "3"]


def test_lines_are_paid_in_line_order(make_claim, check):
    result = check(make_claim({"amount": "50.00"}, {"amount": "40.00"}))

    first, second = result.lines
    assert (first.reimbursable_usd, first.rejected_usd) == (D("50.00"), D("0.00"))
    assert (second.reimbursable_usd, second.rejected_usd) == (D("25.00"), D("15.00"))

    [violation] = meals(result)
    assert violation.line_nos == [2]
    assert violation.excess_usd == D("15.00")
    assert violation.date == date(2026, 3, 10)


def test_later_lines_after_the_limit_get_nothing(make_claim, check):
    result = check(make_claim({"amount": "60.00"}, {"amount": "20.00"}, {"amount": "10.00"}))

    assert [line.reimbursable_usd for line in result.lines] == [D("60.00"), D("15.00"), D("0.00")]
    [violation] = meals(result)
    assert violation.line_nos == [2, 3]
    assert violation.excess_usd == D("15.00")


def test_days_are_independent(make_claim, check):
    result = check(make_claim({"amount": "70.00"}, {"date": "2026-03-11", "amount": "70.00"}))

    assert result.violations == []


def test_one_violation_per_day_over_limit(make_claim, check):
    result = check(make_claim(
        {"amount": "80.00"}, {"date": "2026-03-11", "amount": "90.00"}
    ))

    assert [(v.date, v.excess_usd) for v in meals(result)] == [
        (date(2026, 3, 10), D("5.00")),
        (date(2026, 3, 11), D("15.00")),
    ]


def test_rejected_line_counts_zero_toward_limit(make_claim, check):
    # spec US1 scenario 12: the line without a receipt is rejected and does not use up the limit.
    result = check(make_claim(
        {"amount": "60.00", "receipt_attached": False}, {"amount": "50.00"}
    ))

    assert [v.rule_id for v in result.violations] == ["RECEIPT_MISSING"]
    assert [line.reimbursable_usd for line in result.lines] == [D("0.00"), D("50.00")]


def test_limit_applies_to_converted_amounts(make_claim, check):
    # 40.00 EUR -> 43.20 USD, 30.00 EUR -> 32.40 USD; day total 75.60 USD.
    result = check(make_claim(
        {"amount": "40.00", "currency": "EUR"}, {"amount": "30.00", "currency": "EUR"}
    ))

    assert [line.reimbursable_usd for line in result.lines] == [D("43.20"), D("31.80")]
    [violation] = meals(result)
    assert violation.excess_usd == D("0.60")


def test_only_meal_lines_count(make_claim, check):
    result = check(make_claim(
        {"amount": "70.00"}, {"category": "transport", "amount": "70.00", "merchant": "Taxi"}
    ))

    assert result.violations == []
