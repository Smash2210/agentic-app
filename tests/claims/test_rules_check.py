"""Whole-claim behaviour of check_claim (spec FR-007–FR-011, FR-019, SC-003, SC-005)."""

from datetime import date
from decimal import Decimal as D

from agentic_app.claims.rules import PER_DIEM_CITATIONS, RULE_CITATIONS, RuleId

# The contracts/claims-api.md example claim.
CONTRACT_LINES = (
    {"date": "2026-03-10", "category": "meal", "merchant": "Cafe Roma",
     "amount": "50.00", "currency": "EUR", "receipt_attached": True},
    {"date": "2026-03-10", "category": "meal", "merchant": "Imbiss 24",
     "amount": "30.00", "currency": "USD", "receipt_attached": False},
    {"date": "2026-03-10", "category": "lodging", "merchant": "Hotel Mitte",
     "amount": "400.00", "currency": "EUR", "receipt_attached": True, "nights": 2},
)


def without_messages(result) -> dict:
    data = result.model_dump(mode="json")
    for violation in data["violations"]:
        violation.pop("message")
    return data


def test_contract_example(make_claim, check):
    result = check(make_claim(*CONTRACT_LINES, city="Berlin", start="2026-03-10",
                              end="2026-03-12"))

    lodging_citation = {"doc_id": "POL-LODGING", "sections": ["1", "2", "3"]}
    assert without_messages(result) == {
        "claim_id": 1,
        "lines": [
            {"line_no": 1, "claimed_usd": "54.00", "reimbursable_usd": "54.00",
             "rejected_usd": "0.00", "flagged_for_review": False},
            {"line_no": 2, "claimed_usd": "30.00", "reimbursable_usd": "0.00",
             "rejected_usd": "30.00", "flagged_for_review": False},
            {"line_no": 3, "claimed_usd": "432.00", "reimbursable_usd": "360.00",
             "rejected_usd": "72.00", "flagged_for_review": False},
        ],
        "violations": [
            {"rule_id": "RECEIPT_MISSING", "line_nos": [2], "date": None, "excess_usd": None,
             "citation": {"doc_id": "POL-RECEIPTS", "sections": ["1", "2"]}},
            {"rule_id": "LODGING_NIGHTLY_CAP", "line_nos": [3], "date": "2026-03-10",
             "excess_usd": "36.00", "citation": lodging_citation},
            {"rule_id": "LODGING_NIGHTLY_CAP", "line_nos": [3], "date": "2026-03-11",
             "excess_usd": "36.00", "citation": lodging_citation},
        ],
        "per_diem": {"city": "Berlin", "daily_rate_usd": "60.00", "days": 3,
                     "amount_usd": "150.00",
                     "citation": {"doc_id": "POL-PERDIEM", "sections": ["1", "2"]}},
        "lines_reimbursable_usd": "414.00",
        "total_reimbursable_usd": "564.00",
    }


def test_messages_are_plain_and_name_their_amounts(make_claim, check):
    result = check(make_claim(*CONTRACT_LINES))

    for violation in result.violations:
        assert violation.message.strip()
        if violation.excess_usd is not None:
            assert str(violation.excess_usd) in violation.message
    receipt = next(v for v in result.violations if v.rule_id == "RECEIPT_MISSING")
    assert "30.00" in receipt.message


def test_violations_are_sorted_by_rule_then_date_then_line(make_claim, check):
    result = check(make_claim(
        {"amount": "50.00", "merchant": "Cafe"},                                 # 1
        {"amount": "40.00", "merchant": "Bistro"},                               # 2: meals day 10
        {"category": "transport", "amount": "900.00", "currency": "JPY"},        # 3: currency
        {"amount": "50.00", "merchant": "Cafe"},                                 # 4: duplicate of 1
        {"category": "transport", "amount": "30.00", "receipt_attached": False},  # 5: receipt
        {"category": "lodging", "amount": "200.00", "merchant": "Hotel"},        # 6: lodging day 10
        {"date": "2026-03-11", "amount": "80.00", "merchant": "Grill"},          # 7: meals day 11
    ))

    assert [(v.rule_id, v.date, v.line_nos) for v in result.violations] == [
        ("CURRENCY_UNSUPPORTED", None, [3]),
        ("RECEIPT_MISSING", None, [5]),
        ("DUPLICATE", None, [4]),
        ("MEALS_DAILY_LIMIT", date(2026, 3, 10), [2]),
        ("MEALS_DAILY_LIMIT", date(2026, 3, 11), [7]),
        ("LODGING_NIGHTLY_CAP", date(2026, 3, 10), [6]),
    ]


def test_transport_and_other_lines_skip_meal_and_lodging_limits(make_claim, check):
    # spec FR-019: only the currency, receipt and duplicate rules apply.
    result = check(make_claim(
        {"category": "transport", "amount": "200.00", "merchant": "Airline"},
        {"category": "other", "amount": "150.00", "merchant": "Conference"},
    ))

    assert result.violations == []
    assert [line.reimbursable_usd for line in result.lines] == [D("200.00"), D("150.00")]


def test_total_is_sum_of_lines_plus_per_diem(make_claim, check):
    result = check(make_claim(*CONTRACT_LINES))

    assert result.lines_reimbursable_usd == sum(line.reimbursable_usd for line in result.lines)
    assert result.total_reimbursable_usd == (
        result.lines_reimbursable_usd + result.per_diem.amount_usd
    )


def test_rejected_is_claimed_minus_reimbursable(make_claim, check):
    result = check(make_claim(*CONTRACT_LINES))

    for line in result.lines:
        assert line.rejected_usd == line.claimed_usd - line.reimbursable_usd


def test_same_input_gives_same_result(make_claim, check, prior_lines_of):
    earlier = make_claim(CONTRACT_LINES[0], claim_id=1)
    claim = make_claim(*CONTRACT_LINES, claim_id=2)
    prior = prior_lines_of(earlier)

    assert check(claim, prior) == check(claim, prior)


def test_claim_id_is_echoed(make_claim, check):
    assert check(make_claim({}, claim_id=42)).claim_id == 42


def test_every_rule_has_a_citation():
    assert set(RULE_CITATIONS) == set(RuleId)
    assert {rule.value for rule in RuleId} == {
        "CURRENCY_UNSUPPORTED", "RECEIPT_MISSING", "DUPLICATE",
        "MEALS_DAILY_LIMIT", "LODGING_NIGHTLY_CAP",
    }


def test_every_citation_exists_in_the_policy(policy):
    # spec SC-003: each doc_id and section the engine can emit is present in data/policies.
    citations = [*RULE_CITATIONS.values(), *PER_DIEM_CITATIONS.values()]
    for citation in citations:
        assert citation.doc_id in policy.sections, citation
        assert set(citation.sections) <= policy.sections[citation.doc_id], citation
