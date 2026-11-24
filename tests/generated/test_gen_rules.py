"""Generated edge-case and adversarial tests for agentic_app.claims.rules.check_claim.

Every expected value is worked out by hand from specs/001-claims-api/spec.md and
data/policies/*.md (rates: USD 1.00, EUR 1.08, GBP 1.27, INR 0.012; meals 75/day;
lodging caps Berlin 180, London 220, other 140; per diem Berlin 60, London 70, other 45,
travel days 75%; receipts over 25 USD). Nothing here was derived by running the code.
"""

from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agentic_app.claims.policy import load_policy
from agentic_app.claims.rules import check_claim
from agentic_app.schemas import Claim, ExpenseLine, PriorLine, Trip

POLICY = load_policy(Path(__file__).resolve().parents[2] / "data" / "policies")

OUTRIGHT = {"CURRENCY_UNSUPPORTED", "RECEIPT_MISSING", "DUPLICATE"}
LIMITS = {"MEALS_DAILY_LIMIT", "LODGING_NIGHTLY_CAP"}
CAPS = {"berlin": D("180"), "london": D("220")}
OTHER_CAP = D("140")


def line(line_no, day, category="transport", amount="10.00", currency="USD",
         merchant=None, receipt=True, nights=None):
    if category == "lodging" and nights is None:
        nights = 1
    return ExpenseLine(
        line_no=line_no, date=day, category=category,
        merchant=merchant if merchant is not None else f"Merchant {line_no}",
        amount=D(amount) if isinstance(amount, str) else amount,
        currency=currency, receipt_attached=receipt, nights=nights,
    )


def claim(lines, city="Paris", start=date(2026, 3, 10), end=date(2026, 3, 12),
          claim_id=1, employee="E-001"):
    return Claim(id=claim_id, employee_id=employee,
                 trip=Trip(destination_city=city, start_date=start, end_date=end),
                 lines=list(lines))


def run(c, prior=()):
    return check_claim(c, list(prior), POLICY)


def rules_of(result):
    return sorted(v.rule_id.value for v in result.violations)


def of_rule(result, rule):
    return [v for v in result.violations if v.rule_id == rule]


D1, D2, D3, D4 = (date(2026, 3, 10) + timedelta(days=k) for k in range(4))


# --------------------------------------------------------------------------------------------
# Currency conversion and rounding (FR-012, POL-CURRENCY §2-3)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("amount", "currency", "usd"), [
    # 1.50 GBP x 1.27 = 1.905 -> half-up 1.91 (half-even would give 1.90)
    ("1.50", "GBP", "1.91"),
    # 3.75 INR x 0.012 = 0.045 -> half-up 0.05 (half-even would give 0.04)
    ("3.75", "INR", "0.05"),
    # 0.50 GBP x 1.27 = 0.635 -> 0.64
    ("0.50", "GBP", "0.64"),
])
def test_exact_half_cent_rounds_up(amount, currency, usd):
    """FR-012 / POL-CURRENCY §3 / edge case 'Rounding boundary': exactly half a cent rounds up,
    including where banker's rounding would round down."""
    result = run(claim([line(1, D1, amount=amount, currency=currency)]))
    assert result.lines[0].claimed_usd == D(usd)
    assert result.lines[0].reimbursable_usd == D(usd)


def test_tiny_inr_line_converts_to_zero_usd_without_error():
    """FR-012 / POL-CURRENCY §2-3: 0.01 INR x 0.012 = 0.00012 -> 0.00 USD. Valid input
    (amount > 0, 2 dp); the line is claimed and paid 0.00 with no violation."""
    result = run(claim([line(1, D1, amount="0.01", currency="INR", receipt=False)]))
    lr = result.lines[0]
    assert (lr.claimed_usd, lr.reimbursable_usd, lr.rejected_usd) == (D("0.00"),) * 3
    assert result.violations == []


def test_each_line_converted_separately_three_tiny_gbp_lines():
    """Constitution IV / POL-CURRENCY §3: convert per line, then sum.
    0.01 GBP x 1.27 = 0.0127 -> 0.01 each; three lines total 0.03.
    (One-step 0.03 GBP x 1.27 = 0.0381 -> 0.04, which would be wrong.)"""
    lines = [line(n, D1, amount="0.01", currency="GBP") for n in (1, 2, 3)]
    result = run(claim(lines))
    assert [lr.claimed_usd for lr in result.lines] == [D("0.01")] * 3
    assert result.lines_reimbursable_usd == D("0.03")


def test_exponent_notation_amount_is_treated_as_its_value():
    """'Odd but valid input' 1e2: Decimal('1E+2') is 100 -> claimed 100.00 USD. As a meal it is
    over the 75.00 daily limit (POL-MEALS §1, §3): 75.00 paid, 25.00 excess."""
    result = run(claim([line(1, D1, "meal", amount=D("1E+2"))]))
    lr = result.lines[0]
    assert lr.claimed_usd == D("100.00")
    assert lr.reimbursable_usd == D("75.00")
    assert lr.rejected_usd == D("25.00")
    [v] = result.violations
    assert v.rule_id == "MEALS_DAILY_LIMIT" and v.excess_usd == D("25.00")


def test_very_large_eur_amount_keeps_cents():
    """FR-012: 9999999999.99 EUR x 1.08 = 10799999999.9892 -> 10799999999.99 USD.
    Transport has no limit (FR-019), so all of it is reimbursable."""
    result = run(claim([line(1, D1, amount="9999999999.99", currency="EUR")]))
    assert result.lines[0].claimed_usd == D("10799999999.99")
    assert result.lines[0].reimbursable_usd == D("10799999999.99")
    # per diem Paris 3 days: 33.75 + 45 + 33.75 = 112.50
    assert result.total_reimbursable_usd == D("10799999999.99") + D("112.50")


# --------------------------------------------------------------------------------------------
# Receipts (FR-014, POL-RECEIPTS §1-2) at converted boundaries
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("amount", "currency", "usd", "needs_receipt"), [
    # 2083.74 INR x 0.012 = 25.00488 -> 25.00 : exactly the threshold, no receipt needed
    ("2083.74", "INR", "25.00", False),
    # 2083.75 INR x 0.012 = 25.005 -> 25.01 (half-up) : over 25, receipt needed
    ("2083.75", "INR", "25.01", True),
    # 19.68 GBP x 1.27 = 24.9936 -> 24.99
    ("19.68", "GBP", "24.99", False),
    # 19.69 GBP x 1.27 = 25.0063 -> 25.01
    ("19.69", "GBP", "25.01", True),
])
def test_receipt_threshold_after_conversion(amount, currency, usd, needs_receipt):
    """FR-014 / POL-RECEIPTS §1 / POL-CURRENCY §4: threshold compares the rounded USD amount."""
    result = run(claim([line(1, D1, amount=amount, currency=currency, receipt=False)]))
    lr = result.lines[0]
    assert lr.claimed_usd == D(usd)
    if needs_receipt:
        assert rules_of(result) == ["RECEIPT_MISSING"]
        assert lr.reimbursable_usd == D("0.00")
        assert lr.rejected_usd == D(usd)
    else:
        assert result.violations == []
        assert lr.reimbursable_usd == D(usd)


def test_missing_receipt_is_not_flagged_for_review():
    """FR-015 vs FR-014: only duplicates are 'flagged for review' (POL-RECEIPTS §4);
    a missing receipt is simply not reimbursed (POL-RECEIPTS §2)."""
    result = run(claim([line(1, D1, amount="30.00", receipt=False)]))
    assert result.lines[0].flagged_for_review is False


# --------------------------------------------------------------------------------------------
# Meals daily limit (FR-016, POL-MEALS §1, §3)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("amount", "usd", "excess"), [
    ("69.44", "75.00", None),   # 69.44 x 1.08 = 74.9952 -> 75.00, exactly at limit
    ("69.45", "75.01", "0.01"),  # 69.45 x 1.08 = 75.006 -> 75.01, one cent over
])
def test_meal_limit_at_converted_eur_boundary(amount, usd, excess):
    """FR-016 / POL-CURRENCY §4 / SC-004: limit checked on converted, rounded USD."""
    result = run(claim([line(1, D1, "meal", amount=amount, currency="EUR")]))
    lr = result.lines[0]
    assert lr.claimed_usd == D(usd)
    if excess is None:
        assert result.violations == []
        assert lr.reimbursable_usd == D("75.00")
    else:
        [v] = result.violations
        assert v.rule_id == "MEALS_DAILY_LIMIT"
        assert v.excess_usd == D(excess)
        assert lr.reimbursable_usd == D("75.00")


def test_line_exactly_filling_remaining_is_not_named_but_later_line_is():
    """FR-016 + clarification Q2: 50 + 25 reaches 75 exactly; line 3 (10.00) is fully rejected.
    Only line 3 lost money, so the violation's excess is 10.00 for day D1."""
    lines = [line(1, D1, "meal", "50.00"), line(2, D1, "meal", "25.00"),
             line(3, D1, "meal", "10.00")]
    result = run(claim(lines))
    assert [lr.reimbursable_usd for lr in result.lines] == [D("50.00"), D("25.00"), D("0.00")]
    [v] = result.violations
    assert v.date == D1
    assert v.excess_usd == D("10.00")
    assert 3 in v.line_nos and 1 not in v.line_nos


def test_meal_lines_out_of_date_order_are_grouped_per_day_in_line_order():
    """FR-016: per calendar day, paid in line order. Day D2: line 1 60.00 + line 3 20.00 = 80
    -> line 3 paid 15.00, excess 5.00. Day D1: line 2 60.00 alone, fine."""
    lines = [line(1, D2, "meal", "60.00"), line(2, D1, "meal", "60.00"),
             line(3, D2, "meal", "20.00")]
    result = run(claim(lines))
    assert [lr.reimbursable_usd for lr in result.lines] == [D("60.00"), D("60.00"), D("15.00")]
    [v] = result.violations
    assert (v.date, v.excess_usd, v.line_nos) == (D2, D("5.00"), [3])


def test_meal_days_across_month_end_are_separate():
    """FR-016 + assumption 'Meal days are calendar days': 31 Jan and 1 Feb are different days.
    70.00 on each -> no violation; 140.00 reimbursable."""
    start, end = date(2026, 1, 30), date(2026, 2, 2)
    lines = [line(1, date(2026, 1, 31), "meal", "70.00"),
             line(2, date(2026, 2, 1), "meal", "70.00")]
    result = run(claim(lines, start=start, end=end))
    assert result.violations == []
    assert result.lines_reimbursable_usd == D("140.00")


def test_unsupported_currency_meal_does_not_use_daily_limit():
    """FR-013 + edge case: an unsupported-currency line is excluded from the meals rule and counts
    0 USD. A 75.00 USD meal on the same day is paid in full; only CURRENCY_UNSUPPORTED raised."""
    lines = [line(1, D1, "meal", "10000.00", currency="JPY"), line(2, D1, "meal", "75.00")]
    result = run(claim(lines))
    assert rules_of(result) == ["CURRENCY_UNSUPPORTED"]
    assert result.lines[1].reimbursable_usd == D("75.00")
    lr = result.lines[0]
    assert (lr.claimed_usd, lr.reimbursable_usd, lr.rejected_usd) == (None, D("0.00"), None)


def test_duplicate_meal_counts_zero_toward_limit():
    """FR-016 / clarification Q7: duplicate line 2 counts 0. 40 (line 1) + 35 (line 3) = 75 ->
    no meals violation, line 3 paid in full."""
    lines = [line(1, D1, "meal", "40.00", merchant="Cafe"),
             line(2, D1, "meal", "40.00", merchant="Cafe"),
             line(3, D1, "meal", "35.00")]
    result = run(claim(lines))
    assert rules_of(result) == ["DUPLICATE"]
    assert [lr.reimbursable_usd for lr in result.lines] == [D("40.00"), D("0.00"), D("35.00")]


# --------------------------------------------------------------------------------------------
# Lodging nightly cap (FR-017, POL-LODGING §1-3)
# --------------------------------------------------------------------------------------------


def test_leftover_cent_on_last_night_decides_which_nights_are_over():
    """FR-017 / clarification Q5 (amended in M03: shares rounded down): 420.02 / 3 = 140.0067 ->
    140.00, 140.00, last 420.02 - 280.00 = 140.02. Paris cap 140: only night 3 is over, by 0.02.
    (Under the original half-up rule this was nights 1 and 2 over by 0.01 each.)"""
    c = claim([line(1, D1, "lodging", "420.02", nights=3)], end=D3)
    result = run(c)
    caps = of_rule(result, "LODGING_NIGHTLY_CAP")
    assert [(v.date, v.excess_usd) for v in caps] == [(D3, D("0.02"))]
    assert result.lines[0].reimbursable_usd == D("420.00")
    assert result.lines[0].rejected_usd == D("0.02")


def test_leftover_cent_goes_to_last_night_only():
    """FR-017: 420.01 / 3 = 140.0033 -> 140.00, 140.00, last 140.01. Only night 3 is over."""
    c = claim([line(1, D1, "lodging", "420.01", nights=3)], end=D3)
    result = run(c)
    caps = of_rule(result, "LODGING_NIGHTLY_CAP")
    assert [(v.date, v.excess_usd) for v in caps] == [(D3, D("0.01"))]
    assert result.lines[0].reimbursable_usd == D("420.00")


def test_leap_day_night_is_capped_and_competes():
    """FR-017 with leap day: 540.00 USD over 3 nights from 2028-02-28 -> 180.00 on 28 Feb,
    29 Feb and 1 Mar (Berlin cap 180, all full). Lines 2 (29 Feb) and 3 (1 Mar), 10.00 each,
    come later in line order so they are fully rejected, one violation per night."""
    feb28, feb29, mar1 = date(2028, 2, 28), date(2028, 2, 29), date(2028, 3, 1)
    lines = [line(1, feb28, "lodging", "540.00", nights=3),
             line(2, feb29, "lodging", "10.00"),
             line(3, mar1, "lodging", "10.00")]
    result = run(claim(lines, city="Berlin", start=date(2028, 2, 27), end=date(2028, 3, 2)))
    assert [lr.reimbursable_usd for lr in result.lines] == [D("540.00"), D("0.00"), D("0.00")]
    caps = of_rule(result, "LODGING_NIGHTLY_CAP")
    assert [(v.date, v.line_nos, v.excess_usd) for v in caps] == [
        (feb29, [2], D("10.00")), (mar1, [3], D("10.00"))]


def test_overlapping_multi_night_and_single_night_lines_share_a_night():
    """FR-017 edge case 'several lodging lines covering the same night': Berlin, line 1 300.00
    over 3 nights = 100.00/night; line 2 100.00 on night D2. Night D2: 100 + 100 = 200 > 180
    -> line 2 paid 80.00, 20.00 excess."""
    lines = [line(1, D1, "lodging", "300.00", nights=3), line(2, D2, "lodging", "100.00")]
    result = run(claim(lines, city="Berlin", end=D3))
    assert result.lines[0].reimbursable_usd == D("300.00")
    assert result.lines[1].reimbursable_usd == D("80.00")
    [v] = result.violations
    assert (v.date, v.line_nos, v.excess_usd) == (D2, [2], D("20.00"))


def test_line_order_not_date_order_decides_who_is_paid_first():
    """Clarification Q2/Q5: shares for the same night are paid in LINE order. London cap 220.
    Line 1: 200.00 on night D2. Line 2: 400.00 over D1-D2 = 200.00/night. Night D2: line 1 paid
    200, line 2 paid 20, excess 180. Line 2 total = 200 (D1) + 20 (D2) = 220."""
    lines = [line(1, D2, "lodging", "200.00"), line(2, D1, "lodging", "400.00", nights=2)]
    result = run(claim(lines, city="London", end=D3))
    assert [lr.reimbursable_usd for lr in result.lines] == [D("200.00"), D("220.00")]
    [v] = result.violations
    assert (v.date, v.line_nos, v.excess_usd) == (D2, [2], D("180.00"))


def test_tiny_multi_night_line_cannot_let_another_line_exceed_the_nightly_cap():
    """POL-LODGING §1 ('claimed up to a cap per night') / FR-017 ('split evenly', nothing
    negative): a single-night line is never paid more than the cap for its night.

    Paris cap 140. Line 1: 0.02 USD over 4 nights D1-D4. An even split cannot give any night a
    negative share (0.02 / 4 = 0.005 per night; any even cent split is 0.01/0.01/0.00/0.00 or
    similar, all >= 0). Line 2: 140.01 USD for night D4 alone -> at most 140.00 paid on D4,
    0.01 rejected by a LODGING_NIGHTLY_CAP violation on D4."""
    lines = [line(1, D1, "lodging", "0.02", nights=4), line(2, D4, "lodging", "140.01")]
    result = run(claim(lines, end=D4))
    assert result.lines[1].reimbursable_usd <= D("140.00")
    assert any(v.date == D4 for v in of_rule(result, "LODGING_NIGHTLY_CAP"))


def test_lodging_duplicate_ignores_number_of_nights():
    """FR-015 / POL-RECEIPTS §3: duplicates are same date, amount, currency, merchant - nights is
    not part of the key. Line 2 (same Hotel, 300.00, D1, 1 night) duplicates line 1 (3 nights).
    Line 1: 300/3 = 100/night under Berlin 180 -> paid 300.00."""
    lines = [line(1, D1, "lodging", "300.00", merchant="Hotel", nights=3),
             line(2, D1, "lodging", "300.00", merchant="Hotel", nights=1)]
    result = run(claim(lines, city="Berlin", end=D3))
    assert rules_of(result) == ["DUPLICATE"]
    assert result.lines[1].flagged_for_review is True
    assert [lr.reimbursable_usd for lr in result.lines] == [D("300.00"), D("0.00")]


# --------------------------------------------------------------------------------------------
# Duplicates (FR-015, POL-RECEIPTS §3-4)
# --------------------------------------------------------------------------------------------


def test_duplicate_ignores_category():
    """FR-015: category is not part of the duplicate definition. A meal and a transport line,
    same date/amount/currency/merchant -> the later one is a duplicate."""
    lines = [line(1, D1, "meal", "20.00", merchant="Cafe"),
             line(2, D1, "transport", "20.00", merchant="Cafe")]
    result = run(claim(lines))
    assert rules_of(result) == ["DUPLICATE"]
    assert result.lines[1].reimbursable_usd == D("0.00")
    assert result.lines[1].flagged_for_review is True


def test_internal_whitespace_difference_is_not_a_duplicate():
    """FR-015 + edge case: only SURROUNDING spaces and case are ignored; 'Cafe  Roma' (two
    spaces) differs inside the name from 'Cafe Roma'."""
    lines = [line(1, D1, merchant="Cafe Roma"), line(2, D1, merchant="Cafe  Roma")]
    assert run(claim(lines)).violations == []


def test_exponent_amount_duplicates_two_decimal_amount():
    """FR-015 'same amount ... as submitted': Decimal('1E+2') and Decimal('100.00') are the same
    amount, so line 2 is a duplicate (and only 1 line pays: 100.00 transport)."""
    lines = [line(1, D1, amount=D("100.00"), merchant="Taxi"),
             line(2, D1, amount=D("1E+2"), merchant="Taxi")]
    result = run(claim(lines))
    assert rules_of(result) == ["DUPLICATE"]
    assert result.lines_reimbursable_usd == D("100.00")


def test_prior_and_in_claim_duplicates_are_all_rejected():
    """FR-015: the earliest submitted line (in a prior claim) is the original; both copies in the
    later claim are duplicates, flagged, 0 USD."""
    prior = [PriorLine(claim_id=1, line_no=1, date=D1, amount=D("30.00"), currency="USD",
                       merchant="Taxi Co")]
    lines = [line(1, D1, amount="30.00", merchant=" taxi co"),
             line(2, D1, amount="30.00", merchant="TAXI CO ")]
    result = run(claim(lines, claim_id=2), prior)
    assert rules_of(result) == ["DUPLICATE", "DUPLICATE"]
    assert all(lr.flagged_for_review and lr.reimbursable_usd == D("0.00")
               for lr in result.lines)


# --------------------------------------------------------------------------------------------
# Per diem (FR-018, POL-PERDIEM §1-4)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("city", "start", "end", "days", "amount"), [
    # leap year: 28 Feb, 29 Feb, 1 Mar = 3 days; Berlin 45 + 60 + 45 = 150.00
    ("Berlin", date(2028, 2, 28), date(2028, 3, 1), 3, "150.00"),
    # non-leap: 28 Feb, 1 Mar = 2 days; Berlin 45 + 45 = 90.00
    ("Berlin", date(2027, 2, 28), date(2027, 3, 1), 2, "90.00"),
    # year boundary: 31 Dec, 1 Jan = 2 days; London 52.50 + 52.50 = 105.00
    ("London", date(2026, 12, 31), date(2027, 1, 1), 2, "105.00"),
    # whole year 2026 = 365 days; other 33.75 x 2 + 45 x 363 = 67.50 + 16335 = 16402.50
    ("Paris", date(2026, 1, 1), date(2026, 12, 31), 365, "16402.50"),
    # leap year 2028 = 366 days; London 52.50 x 2 + 70 x 364 = 105 + 25480 = 25585.00
    ("London", date(2028, 1, 1), date(2028, 12, 31), 366, "25585.00"),
])
def test_per_diem_calendar_edges(city, start, end, days, amount):
    """FR-018 / POL-PERDIEM §1-2: inclusive calendar days, first and last at 75%."""
    result = run(claim([line(1, start)], city=city, start=start, end=end))
    assert result.per_diem.days == days
    assert result.per_diem.amount_usd == D(amount)


def test_per_diem_city_with_accent_uses_other_city_rate():
    """Edge case 'Destination city matching': only case and surrounding spaces are ignored, so
    'Bérlin' is 'any other city': same-day 45 x 0.75 = 33.75 (POL-PERDIEM §3)."""
    result = run(claim([line(1, D1)], city="Bérlin", end=D1))
    assert result.per_diem.amount_usd == D("33.75")


# --------------------------------------------------------------------------------------------
# Hypothesis invariants
# --------------------------------------------------------------------------------------------

MERCHANTS = ["Cafe", " cafe ", "Hotel", "Taxi"]
CURRENCIES = ["USD", "EUR", "GBP", "INR", "JPY"]
CITIES = ["Berlin", " london ", "Paris"]


@st.composite
def claims(draw, single_night_only=False, tiny=False):
    start = date(2026, 3, 10)
    length = draw(st.integers(0, 4))
    end = start + timedelta(days=length)
    city = draw(st.sampled_from(CITIES))
    n = draw(st.integers(1, 8))
    amounts = (st.decimals(D("0.01"), D("0.10"), places=2) | st.decimals(D("100"), D("260"),
               places=2)) if tiny else st.decimals(D("0.01"), D("300.00"), places=2)
    built = []
    for line_no in range(1, n + 1):
        offset = draw(st.integers(0, length))
        day = start + timedelta(days=offset)
        category = draw(st.sampled_from(["meal", "lodging", "transport", "other"]))
        nights = None
        if category == "lodging":
            max_nights = length - offset + 1
            nights = 1 if single_night_only else draw(st.integers(1, max_nights))
        built.append(line(
            line_no, day, category, draw(amounts),
            currency=draw(st.sampled_from(CURRENCIES)),
            merchant=draw(st.sampled_from(MERCHANTS)),
            receipt=draw(st.booleans()), nights=nights,
        ))
    return claim(built, city=city, start=start, end=end)


def cap_for(city):
    return CAPS.get(city.strip().casefold(), OTHER_CAP)


def outright_lines(result):
    return {n for v in result.violations if v.rule_id in OUTRIGHT for n in v.line_nos}


SETTINGS = settings(max_examples=300, deadline=None,
                    suppress_health_check=[HealthCheck.too_slow])


@SETTINGS
@given(claims())
def test_property_line_amounts_are_consistent(c):
    """FR-009, edge case 'not less than 0', Constitution IV: for every line,
    0 <= reimbursable <= claimed, rejected = claimed - reimbursable, every amount has exactly
    2 decimals; unsupported currency -> claimed/rejected None and reimbursable 0."""
    result = run(c)
    for src, lr in zip(c.lines, result.lines, strict=True):
        assert lr.reimbursable_usd >= 0
        assert lr.reimbursable_usd.as_tuple().exponent == -2
        if src.currency == "JPY":
            assert lr.claimed_usd is None and lr.rejected_usd is None
            assert lr.reimbursable_usd == 0
        else:
            assert lr.reimbursable_usd <= lr.claimed_usd
            assert lr.rejected_usd == lr.claimed_usd - lr.reimbursable_usd
            assert lr.claimed_usd.as_tuple().exponent == -2


@SETTINGS
@given(claims())
def test_property_totals_add_up_and_are_deterministic(c):
    """FR-010 (total = sum of lines + per diem), FR-007/SC-005 (same input, same output)."""
    first, second = run(c), run(c.model_copy(deep=True))
    assert first == second
    lines_sum = sum((lr.reimbursable_usd for lr in first.lines), D("0.00"))
    assert first.lines_reimbursable_usd == lines_sum
    assert first.total_reimbursable_usd == lines_sum + first.per_diem.amount_usd


@SETTINGS
@given(claims())
def test_property_outright_rejected_pay_zero_and_flag_only_duplicates(c):
    """FR-013/14/15: a line with a currency, receipt or duplicate violation pays 0 USD;
    flagged_for_review is set exactly for duplicate lines (POL-RECEIPTS §4)."""
    result = run(c)
    dup_lines = {n for v in of_rule(result, "DUPLICATE") for n in v.line_nos}
    for lr in result.lines:
        if lr.line_no in outright_lines(result):
            assert lr.reimbursable_usd == 0
        assert lr.flagged_for_review == (lr.line_no in dup_lines)


@SETTINGS
@given(claims())
def test_property_meals_per_day_never_exceed_limit_and_fill_it_exactly(c):
    """FR-016 / POL-MEALS §1, §3: per day, paid meals <= 75.00; if eligible (not outright
    rejected) claimed meals exceed 75.00, exactly 75.00 is paid, else everything is paid."""
    result = run(c)
    out = outright_lines(result)
    days = {ln.date for ln in c.lines if ln.category == "meal"}
    for day in days:
        eligible = [(ln, lr) for ln, lr in zip(c.lines, result.lines, strict=True)
                    if ln.category == "meal" and ln.date == day and ln.line_no not in out]
        claimed = sum((lr.claimed_usd for _, lr in eligible), D(0))
        paid = sum((lr.reimbursable_usd for _, lr in eligible), D(0))
        assert paid == min(claimed, D("75.00"))
        over = [v for v in of_rule(result, "MEALS_DAILY_LIMIT") if v.date == day]
        assert len(over) == (1 if claimed > D("75.00") else 0)
        if over:
            assert over[0].excess_usd == claimed - D("75.00")


@SETTINGS
@given(claims(single_night_only=True))
def test_property_single_night_lodging_fills_cap_exactly(c):
    """FR-017 / POL-LODGING §1-3 with one-night lines: per night, paid = min(eligible claimed,
    cap); one violation per over-cap night with excess = claimed - cap."""
    result = run(c)
    out = outright_lines(result)
    cap = cap_for(c.trip.destination_city)
    for night in {ln.date for ln in c.lines if ln.category == "lodging"}:
        eligible = [lr for ln, lr in zip(c.lines, result.lines, strict=True)
                    if ln.category == "lodging" and ln.date == night and ln.line_no not in out]
        claimed = sum((lr.claimed_usd for lr in eligible), D(0))
        paid = sum((lr.reimbursable_usd for lr in eligible), D(0))
        assert paid == min(claimed, cap)
        over = [v for v in of_rule(result, "LODGING_NIGHTLY_CAP") if v.date == night]
        assert len(over) == (1 if claimed > cap else 0)


@SETTINGS
@given(claims())
def test_property_limit_excess_equals_rejected_of_limit_only_lines(c):
    """FR-008/FR-009 invariant: the USD rejected by meals/lodging violations (excess_usd) adds
    up to the rejected_usd of lines that were not outright rejected."""
    result = run(c)
    out = outright_lines(result)
    excess = sum((v.excess_usd for v in result.violations if v.rule_id in LIMITS), D(0))
    rejected = sum((lr.rejected_usd for lr in result.lines
                    if lr.line_no not in out and lr.rejected_usd is not None), D(0))
    assert excess == rejected


@SETTINGS
@given(claims(tiny=True))
def test_property_no_single_night_line_is_paid_over_the_cap(c):
    """POL-LODGING §1 ('up to a cap per night') + FR-017 ('split evenly'; shares are never
    negative): a one-night lodging line can never be reimbursed more than the nightly cap,
    whatever multi-night lines share its night; and per night, paid one-night lines sum to
    at most the cap."""
    result = run(c)
    cap = cap_for(c.trip.destination_city)
    per_night: dict[date, D] = {}
    for ln, lr in zip(c.lines, result.lines, strict=True):
        if ln.category == "lodging" and ln.nights == 1:
            assert lr.reimbursable_usd <= cap
            per_night[ln.date] = per_night.get(ln.date, D(0)) + lr.reimbursable_usd
    assert all(total <= cap for total in per_night.values())


@SETTINGS
@given(amount=st.decimals(D("0.01"), D("0.50"), places=2), nights=st.integers(2, 10),
       city=st.sampled_from(CITIES))
def test_property_multi_night_share_never_frees_cap_on_its_last_night(amount, nights, city):
    """FR-017 ('split evenly'; nothing negative) + POL-LODGING §1-3: a tiny multi-night line plus
    a one-night line of cap + 0.01 on its LAST night. Whatever the even split of a <= 0.50 USD
    line, its last-night share is >= 0, so night total >= cap + 0.01: the one-night line is paid
    at most the cap and a LODGING_NIGHTLY_CAP violation is raised for that night."""
    start = date(2026, 3, 10)
    last = start + timedelta(days=nights - 1)
    cap = cap_for(city)
    c = claim([line(1, start, "lodging", amount, nights=nights),
               line(2, last, "lodging", cap + D("0.01"))],
              city=city, start=start, end=last)
    result = run(c)
    assert result.lines[1].reimbursable_usd <= cap
    assert any(v.date == last for v in of_rule(result, "LODGING_NIGHTLY_CAP"))
