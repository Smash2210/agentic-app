"""Per diem allowance by city and travel days (spec FR-018; POL-PERDIEM §1–4)."""

from decimal import Decimal as D

import pytest


@pytest.mark.parametrize(
    ("city", "rate", "amount"),
    [("Berlin", "60", "45.00"), ("London", "70", "52.50"), ("Paris", "45", "33.75")],
)
def test_same_day_trip_is_one_day_at_75_percent(make_claim, check, city, rate, amount):
    result = check(make_claim({}, city=city, start="2026-03-10", end="2026-03-10"))

    per_diem = result.per_diem
    assert per_diem.city == city
    assert per_diem.daily_rate_usd == D(rate)
    assert per_diem.days == 1
    assert per_diem.amount_usd == D(amount)
    assert per_diem.citation.doc_id == "POL-PERDIEM"
    assert per_diem.citation.sections == ["1", "3"]


@pytest.mark.parametrize(
    ("city", "start", "end", "days", "amount"),
    [
        ("Berlin", "2026-03-10", "2026-03-11", 2, "90.00"),  # 45 + 45
        ("London", "2026-03-10", "2026-03-12", 3, "175.00"),  # 52.50 + 70 + 52.50
        ("Paris", "2026-03-10", "2026-03-13", 4, "157.50"),  # spec US1 scenario 4
    ],
)
def test_multi_day_trip_pays_travel_days_at_75_percent(make_claim, check, city, start, end,
                                                      days, amount):
    result = check(make_claim({}, city=city, start=start, end=end))

    assert result.per_diem.days == days
    assert result.per_diem.amount_usd == D(amount)
    assert result.per_diem.citation.sections == ["1", "2"]


def test_amount_has_two_decimal_places(make_claim, check):
    result = check(make_claim({}, city="Berlin", start="2026-03-10", end="2026-03-11"))

    assert result.per_diem.amount_usd.as_tuple().exponent == -2


def test_city_lookup_ignores_case_and_keeps_submitted_name(make_claim, check):
    result = check(make_claim({}, city=" LONDON ", start="2026-03-10", end="2026-03-10"))

    assert result.per_diem.amount_usd == D("52.50")
    assert result.per_diem.city == " LONDON "


def test_per_diem_is_not_affected_by_line_violations(make_claim, check):
    clean = check(make_claim({"amount": "20.00"}))
    messy = check(make_claim(
        {"amount": "500.00", "receipt_attached": False},
        {"amount": "200.00", "currency": "JPY"},
    ))

    assert messy.violations
    assert messy.per_diem == clean.per_diem


def test_total_is_lines_plus_per_diem(make_claim, check):
    result = check(make_claim({"amount": "20.00"}, {"category": "transport", "amount": "30.00"}))

    assert result.lines_reimbursable_usd == D("50.00")
    assert result.per_diem.amount_usd == D("150.00")  # Berlin, 3 days
    assert result.total_reimbursable_usd == D("200.00")
