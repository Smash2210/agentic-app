"""Duplicate lines within a claim and across earlier claims (spec FR-015; POL-RECEIPTS §3–4)."""

from decimal import Decimal as D

TAXI = {"date": "2026-03-10", "category": "transport", "merchant": "Taxi Berlin",
        "amount": "12.00", "currency": "EUR"}


def rule_ids(result):
    return [v.rule_id for v in result.violations]


def test_second_identical_line_in_claim_is_a_duplicate(make_claim, check):
    result = check(make_claim(TAXI, TAXI))

    first, second = result.lines
    assert first.reimbursable_usd == D("12.96")
    assert first.flagged_for_review is False
    assert second.claimed_usd == D("12.96")
    assert second.reimbursable_usd == D("0.00")
    assert second.rejected_usd == D("12.96")
    assert second.flagged_for_review is True

    [violation] = result.violations
    assert violation.rule_id == "DUPLICATE"
    assert violation.line_nos == [2]
    assert violation.date is None
    assert violation.excess_usd is None
    assert violation.citation.doc_id == "POL-RECEIPTS"
    assert violation.citation.sections == ["3", "4"]
    assert "line 1" in violation.message


def test_every_later_copy_is_a_duplicate(make_claim, check):
    result = check(make_claim(TAXI, TAXI, TAXI))

    assert [v.line_nos for v in result.violations] == [[2], [3]]
    assert [line.flagged_for_review for line in result.lines] == [False, True, True]


def test_matches_line_from_earlier_claim(make_claim, check, prior_lines_of):
    earlier = make_claim({"category": "meal", "merchant": "Cafe Roma", "amount": "9.00"}, TAXI,
                         claim_id=3)
    current = make_claim(TAXI, claim_id=7)

    result = check(current, prior_lines_of(earlier))

    assert rule_ids(result) == ["DUPLICATE"]
    assert result.lines[0].flagged_for_review is True
    assert "claim 3" in result.violations[0].message
    assert "line 2" in result.violations[0].message


def test_merchant_case_and_surrounding_spaces_are_ignored(make_claim, check):
    result = check(make_claim(TAXI, {**TAXI, "merchant": "  taxi BERLIN "}))

    assert rule_ids(result) == ["DUPLICATE"]


def test_different_letters_in_merchant_are_not_ignored(make_claim, check):
    result = check(make_claim(
        {**TAXI, "merchant": "Cafe Roma"}, {**TAXI, "merchant": "Café Roma"}
    ))

    assert result.violations == []


def test_same_amount_in_other_currency_is_not_a_duplicate(make_claim, check):
    result = check(make_claim(TAXI, {**TAXI, "currency": "GBP"}))

    assert result.violations == []


def test_equal_decimal_amounts_match(make_claim, check):
    result = check(make_claim({**TAXI, "amount": "10.0"}, {**TAXI, "amount": "10.00"}))

    assert rule_ids(result) == ["DUPLICATE"]


def test_different_date_is_not_a_duplicate(make_claim, check):
    result = check(make_claim(TAXI, {**TAXI, "date": "2026-03-11"}))

    assert result.violations == []


def test_unsupported_currency_lines_take_part(make_claim, check):
    jpy = {**TAXI, "amount": "1500.00", "currency": "JPY"}
    result = check(make_claim(jpy, jpy))

    assert sorted(rule_ids(result)) == ["CURRENCY_UNSUPPORTED", "CURRENCY_UNSUPPORTED", "DUPLICATE"]
    duplicate = next(v for v in result.violations if v.rule_id == "DUPLICATE")
    assert duplicate.line_nos == [2]
    assert result.lines[1].flagged_for_review is True


def test_duplicate_missing_receipt_reports_both_rules(make_claim, check):
    expensive = {**TAXI, "amount": "40.00", "receipt_attached": False}
    result = check(make_claim(expensive, expensive))

    assert sorted(v.rule_id for v in result.violations if v.line_nos == [2]) == [
        "DUPLICATE", "RECEIPT_MISSING",
    ]
    assert result.lines[1].reimbursable_usd == D("0.00")
