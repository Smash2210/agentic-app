"""Lodging nightly cap by city, multi-night split (spec FR-017; POL-LODGING §1–3; research R-10)."""

from datetime import date
from decimal import Decimal as D

import pytest


def lodging(**overrides):
    return {"category": "lodging", "merchant": "Hotel", **overrides}


def caps(result):
    return [v for v in result.violations if v.rule_id == "LODGING_NIGHTLY_CAP"]


CITY_CAPS = [("Berlin", "180.00"), ("London", "220.00"), ("Paris", "140.00")]


@pytest.mark.parametrize(("city", "cap"), CITY_CAPS)
def test_one_cent_under_and_at_cap_is_fine(make_claim, check, city, cap):
    for amount in (D(cap) - D("0.01"), D(cap)):
        result = check(make_claim(lodging(amount=str(amount)), city=city))
        assert result.violations == []
        assert result.lines[0].reimbursable_usd == amount


@pytest.mark.parametrize(("city", "cap"), CITY_CAPS)
def test_one_cent_over_cap(make_claim, check, city, cap):
    result = check(make_claim(lodging(amount=str(D(cap) + D("0.01"))), city=city))

    line = result.lines[0]
    assert line.reimbursable_usd == D(cap)
    assert line.rejected_usd == D("0.01")

    [violation] = result.violations
    assert violation.rule_id == "LODGING_NIGHTLY_CAP"
    assert violation.line_nos == [1]
    assert violation.date == date(2026, 3, 10)
    assert violation.excess_usd == D("0.01")
    assert violation.citation.doc_id == "POL-LODGING"
    assert violation.citation.sections == ["1", "2", "3"]


def test_city_is_matched_ignoring_case_and_spaces(make_claim, check):
    result = check(make_claim(lodging(amount="220.00"), city="  london "))

    assert result.violations == []


def test_multi_night_line_is_capped_per_night(make_claim, check):
    # spec US1 scenario 11: 540.00 EUR -> 583.20 USD = 194.40 a night against a 180 cap.
    result = check(make_claim(
        lodging(amount="540.00", currency="EUR", nights=3), end="2026-03-13"
    ))

    line = result.lines[0]
    assert line.claimed_usd == D("583.20")
    assert line.reimbursable_usd == D("540.00")
    assert line.rejected_usd == D("43.20")
    assert [(v.date, v.line_nos, v.excess_usd) for v in caps(result)] == [
        (date(2026, 3, 10), [1], D("14.40")),
        (date(2026, 3, 11), [1], D("14.40")),
        (date(2026, 3, 12), [1], D("14.40")),
    ]


@pytest.mark.parametrize(
    ("extra_night", "extra_amount", "excess"),
    [
        # 100.00 over 3 nights splits 33.33 / 33.33 / 33.34 (leftover cent on the last night).
        ("2026-03-10", "106.67", None),  # 33.33 + 106.67 = 140.00: at the cap
        ("2026-03-10", "106.68", "0.01"),
        ("2026-03-12", "106.66", None),  # 33.34 + 106.66 = 140.00
        ("2026-03-12", "106.67", "0.01"),
    ],
)
def test_uneven_split_puts_leftover_cent_on_last_night(
    make_claim, check, extra_night, extra_amount, excess
):
    result = check(make_claim(
        lodging(amount="100.00", nights=3),
        lodging(date=extra_night, amount=extra_amount, merchant="City tax"),
        city="Paris", end="2026-03-13",
    ))

    assert [v.excess_usd for v in caps(result)] == ([] if excess is None else [D(excess)])


def test_lines_on_the_same_night_are_paid_in_line_order(make_claim, check):
    result = check(make_claim(
        lodging(amount="150.00"), lodging(amount="50.00", merchant="City tax")
    ))

    assert [line.reimbursable_usd for line in result.lines] == [D("150.00"), D("30.00")]
    [violation] = caps(result)
    assert violation.line_nos == [2]
    assert violation.excess_usd == D("20.00")


def test_cheap_night_does_not_raise_another_nights_cap(make_claim, check):
    result = check(make_claim(
        lodging(date="2026-03-10", amount="100.00"),
        lodging(date="2026-03-11", amount="200.00"),
    ))

    assert result.lines_reimbursable_usd == D("280.00")
    [violation] = caps(result)
    assert violation.date == date(2026, 3, 11)
    assert violation.excess_usd == D("20.00")


def test_rejected_lodging_line_counts_zero_toward_cap(make_claim, check):
    result = check(make_claim(
        lodging(amount="170.00", receipt_attached=False),
        lodging(amount="170.00", merchant="Other hotel"),
    ))

    assert [v.rule_id for v in result.violations] == ["RECEIPT_MISSING"]
    assert [line.reimbursable_usd for line in result.lines] == [D("0.00"), D("170.00")]


def test_multi_night_excess_adds_up(make_claim, check):
    result = check(make_claim(lodging(amount="600.00", nights=3), end="2026-03-13"))

    assert result.lines[0].reimbursable_usd == D("540.00")
    assert sum(v.excess_usd for v in caps(result)) == D("60.00")
