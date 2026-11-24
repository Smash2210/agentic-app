"""Receipt required over 25 USD after conversion (spec FR-014; POL-RECEIPTS §1–2)."""

from decimal import Decimal as D

import pytest


@pytest.mark.parametrize("amount", ["24.99", "25.00"])
def test_at_or_below_threshold_needs_no_receipt(make_claim, check, amount):
    result = check(make_claim({"category": "transport", "amount": amount, "receipt_attached": False}))

    assert result.violations == []
    assert result.lines[0].reimbursable_usd == D(amount)


def test_over_threshold_without_receipt_is_not_reimbursed(make_claim, check):
    result = check(make_claim({"category": "transport", "amount": "25.01", "receipt_attached": False}))

    line = result.lines[0]
    assert line.claimed_usd == D("25.01")
    assert line.reimbursable_usd == D("0.00")
    assert line.rejected_usd == D("25.01")
    assert line.flagged_for_review is False

    [violation] = result.violations
    assert violation.rule_id == "RECEIPT_MISSING"
    assert violation.line_nos == [1]
    assert violation.date is None
    assert violation.excess_usd is None
    assert violation.citation.doc_id == "POL-RECEIPTS"
    assert violation.citation.sections == ["1", "2"]
    assert "25.01" in violation.message


@pytest.mark.parametrize("amount", ["24.99", "25.00", "25.01", "500.00"])
def test_with_receipt_no_violation(make_claim, check, amount):
    result = check(make_claim({"category": "transport", "amount": amount, "receipt_attached": True}))

    assert result.violations == []


def test_threshold_uses_converted_amount(make_claim, check):
    # 2083.75 INR x 0.012 = 25.005 -> 25.01 USD, over the threshold.
    result = check(make_claim(
        {"category": "transport", "amount": "2083.75", "currency": "INR", "receipt_attached": False}
    ))

    assert [v.rule_id for v in result.violations] == ["RECEIPT_MISSING"]
    assert result.lines[0].claimed_usd == D("25.01")


def test_converted_amount_rounding_to_exactly_threshold_is_fine(make_claim, check):
    # 2083.33 INR x 0.012 = 24.99996 -> 25.00 USD, not over the threshold.
    result = check(make_claim(
        {"category": "transport", "amount": "2083.33", "currency": "INR", "receipt_attached": False}
    ))

    assert result.violations == []
    assert result.lines[0].reimbursable_usd == D("25.00")


def test_multi_night_lodging_uses_whole_line_amount(make_claim, check):
    # 60.00 USD over 3 nights is 20.00 a night, but the line itself is over 25.00 USD.
    result = check(make_claim(
        {"category": "lodging", "amount": "60.00", "nights": 3, "receipt_attached": False},
        end="2026-03-13",
    ))

    assert [v.rule_id for v in result.violations] == ["RECEIPT_MISSING"]
    assert result.lines[0].reimbursable_usd == D("0.00")


def test_rest_of_claim_is_still_processed(make_claim, check):
    result = check(make_claim(
        {"category": "transport", "amount": "40.00", "receipt_attached": False},
        {"category": "transport", "amount": "40.00", "merchant": "Bus", "receipt_attached": True},
    ))

    assert [line.reimbursable_usd for line in result.lines] == [D("0.00"), D("40.00")]
