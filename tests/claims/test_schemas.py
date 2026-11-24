import copy
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from agentic_app.schemas import ClaimIn


def valid_claim() -> dict:
    """The contracts/claims-api.md POST /claims example, as parsed JSON."""
    return {
        "employee_id": "E-001",
        "trip": {"destination_city": "Berlin", "start_date": "2026-03-10", "end_date": "2026-03-12"},
        "lines": [
            {"date": "2026-03-10", "category": "meal", "merchant": "Cafe Roma",
             "amount": "50.00", "currency": "EUR", "receipt_attached": True},
            {"date": "2026-03-10", "category": "meal", "merchant": "Imbiss 24",
             "amount": "30.00", "currency": "USD", "receipt_attached": False},
            {"date": "2026-03-10", "category": "lodging", "merchant": "Hotel Mitte",
             "amount": "400.00", "currency": "EUR", "receipt_attached": True, "nights": 2},
        ],
    }


def with_change(change) -> dict:
    body = copy.deepcopy(valid_claim())
    change(body)
    return body


def error_locs(body: dict) -> list[tuple]:
    with pytest.raises(ValidationError) as exc:
        ClaimIn.model_validate(body)
    return [e["loc"] for e in exc.value.errors()]


# --- valid input --------------------------------------------------------------------------------


def test_valid_claim_parses():
    claim = ClaimIn.model_validate(valid_claim())
    assert claim.employee_id == "E-001"
    assert claim.trip.start_date == date(2026, 3, 10)
    assert [line.category for line in claim.lines] == ["meal", "meal", "lodging"]


def test_amount_round_trips_as_submitted_string():
    claim = ClaimIn.model_validate(valid_claim())
    assert claim.lines[0].amount == Decimal("50.00")
    assert str(claim.lines[0].amount) == "50.00"
    assert claim.model_dump(mode="json")["lines"][0]["amount"] == "50.00"


def test_currency_is_trimmed_and_upper_cased():
    claim = ClaimIn.model_validate(with_change(lambda b: b["lines"][0].update(currency=" eur")))
    assert claim.lines[0].currency == "EUR"


def test_unsupported_currency_is_accepted():  # spec FR-013: found at check time, not here
    claim = ClaimIn.model_validate(with_change(lambda b: b["lines"][0].update(currency="JPY")))
    assert claim.lines[0].currency == "JPY"


def test_lodging_nights_default_to_one():
    claim = ClaimIn.model_validate(with_change(lambda b: b["lines"][2].pop("nights")))
    assert claim.lines[2].nights == 1


def test_non_lodging_nights_stay_null():
    claim = ClaimIn.model_validate(valid_claim())
    assert claim.lines[0].nights is None


def test_merchant_and_city_are_stored_as_submitted():
    def change(b):
        b["trip"]["destination_city"] = " berlin "
        b["lines"][0]["merchant"] = " Cafe Roma "

    claim = ClaimIn.model_validate(with_change(change))
    assert claim.trip.destination_city == " berlin "
    assert claim.lines[0].merchant == " Cafe Roma "


def test_same_day_trip_is_valid():
    def change(b):
        b["trip"]["end_date"] = "2026-03-10"
        b["lines"][2]["nights"] = 1

    ClaimIn.model_validate(with_change(change))


def test_last_night_on_end_date_is_valid():
    ClaimIn.model_validate(with_change(lambda b: b["lines"][2].update(nights=3)))


# --- field-level errors -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "loc"),
    [
        (lambda b: b.update(employee_id="  "), ("employee_id",)),
        (lambda b: b.pop("employee_id"), ("employee_id",)),
        (lambda b: b.pop("trip"), ("trip",)),
        (lambda b: b["trip"].update(destination_city=""), ("trip", "destination_city")),
        (lambda b: b["trip"].pop("start_date"), ("trip", "start_date")),
        (lambda b: b["trip"].update(end_date="12/03/2026"), ("trip", "end_date")),
        (lambda b: b.update(lines=[]), ("lines",)),
        (lambda b: b["lines"][1].update(date="not-a-date"), ("lines", 1, "date")),
        (lambda b: b["lines"][1].update(category="food"), ("lines", 1, "category")),
        (lambda b: b["lines"][1].update(merchant="   "), ("lines", 1, "merchant")),
        (lambda b: b["lines"][1].update(amount="0"), ("lines", 1, "amount")),
        (lambda b: b["lines"][1].update(amount="0.00"), ("lines", 1, "amount")),
        (lambda b: b["lines"][1].update(amount="-5.00"), ("lines", 1, "amount")),
        (lambda b: b["lines"][1].update(amount="1.234"), ("lines", 1, "amount")),
        (lambda b: b["lines"][1].update(amount="abc"), ("lines", 1, "amount")),
        (lambda b: b["lines"][1].update(amount=12.5), ("lines", 1, "amount")),  # JSON number (R-05)
        (lambda b: b["lines"][1].update(amount=12), ("lines", 1, "amount")),
        (lambda b: b["lines"][1].update(currency=" "), ("lines", 1, "currency")),
        (lambda b: b["lines"][1].pop("receipt_attached"), ("lines", 1, "receipt_attached")),
        (lambda b: b["lines"][2].update(nights=0), ("lines", 2, "nights")),
        (lambda b: b["lines"][2].update(nights=1.5), ("lines", 2, "nights")),
        (lambda b: b["lines"][1].update(nights=1), ("lines", 1, "nights")),  # nights on a meal line
    ],
)
def test_invalid_field_is_reported_at_its_location(change, loc):
    assert loc in error_locs(with_change(change))


def test_number_amount_error_says_to_use_a_string():
    with pytest.raises(ValidationError, match="string"):
        ClaimIn.model_validate(with_change(lambda b: b["lines"][0].update(amount=12.5)))


def test_several_field_errors_are_reported_together():
    def change(b):
        b["trip"]["destination_city"] = ""
        b["lines"][0]["amount"] = "-1"
        b["lines"][1]["category"] = "food"

    locs = error_locs(with_change(change))
    assert ("trip", "destination_city") in locs
    assert ("lines", 0, "amount") in locs
    assert ("lines", 1, "category") in locs


# --- cross-field errors (research R-06) ---------------------------------------------------------


def test_end_before_start():
    assert ("trip", "end_date") in error_locs(
        with_change(lambda b: b["trip"].update(end_date="2026-03-09"))
    )


@pytest.mark.parametrize("bad_date", ["2026-03-09", "2026-03-13"])
def test_line_date_outside_trip(bad_date):
    assert ("lines", 1, "date") in error_locs(
        with_change(lambda b: b["lines"][1].update(date=bad_date))
    )


def test_last_night_after_end_date():
    assert ("lines", 2, "nights") in error_locs(
        with_change(lambda b: b["lines"][2].update(nights=4))
    )


def test_all_cross_field_errors_are_reported_together():
    def change(b):
        b["lines"][0]["date"] = "2026-03-01"
        b["lines"][1]["date"] = "2026-03-20"
        b["lines"][2]["nights"] = 5

    locs = error_locs(with_change(change))
    assert ("lines", 0, "date") in locs
    assert ("lines", 1, "date") in locs
    assert ("lines", 2, "nights") in locs


def test_end_before_start_reported_with_line_errors():
    def change(b):
        b["trip"]["end_date"] = "2026-03-09"
        b["lines"].append(
            {"date": "2026-03-11", "category": "transport", "merchant": "Taxi",
             "amount": "12.00", "currency": "EUR", "receipt_attached": False}
        )

    locs = error_locs(with_change(change))
    assert ("trip", "end_date") in locs
    assert ("lines", 3, "date") in locs


# --- M06 security bounds (spec FR-002, Clarifications "M06 security") ---------------------------


def test_employee_id_is_trimmed():  # S4
    claim = ClaimIn.model_validate(with_change(lambda b: b.update(employee_id=" E-7 ")))
    assert claim.employee_id == "E-7"


@pytest.mark.parametrize("amount", ["12", "12.5", "12.50", " 12.50 ", "1000000.00"])
def test_plain_decimal_amount_is_accepted(amount):  # S2/P2; 1,000,000.00 is the maximum
    claim = ClaimIn.model_validate(with_change(lambda b: b["lines"][1].update(amount=amount)))
    assert claim.lines[1].amount == Decimal(amount.strip())


@pytest.mark.parametrize(
    "amount",
    [
        "1000000.01",  # S2: over the maximum
        "1" + "0" * 30 + ".00",  # S2: the original attack
        "1e2", "1E2", "1.5e1",  # P2: exponent notation
        "+5.00",  # sign
        "1 000.00", "12 .50",  # spaces inside
        ".50",  # no leading digit
        "١٢.00",  # non-ASCII digits (Decimal would accept them)
        "NaN", "Infinity",
    ],
)
def test_non_plain_or_too_large_amount_is_refused(amount):  # S2/P2
    assert ("lines", 1, "amount") in error_locs(
        with_change(lambda b: b["lines"][1].update(amount=amount))
    )


def test_trip_of_366_days_is_valid():  # S3: start to end inclusive
    ClaimIn.model_validate(with_change(lambda b: b["trip"].update(end_date="2027-03-10")))


def test_trip_of_367_days_is_refused():  # S3
    assert ("trip", "end_date") in error_locs(
        with_change(lambda b: b["trip"].update(end_date="2027-03-11"))
    )


def test_50_lines_are_valid():  # S3
    claim = ClaimIn.model_validate(with_change(lambda b: b.update(lines=[b["lines"][0]] * 50)))
    assert len(claim.lines) == 50


def test_51_lines_are_refused():  # S3
    assert ("lines",) in error_locs(with_change(lambda b: b.update(lines=[b["lines"][0]] * 51)))


def _set_text(field: str, text: str):
    def change(b):
        if field == "employee_id":
            b["employee_id"] = text
        elif field == "destination_city":
            b["trip"]["destination_city"] = text
        else:
            b["lines"][0]["merchant"] = text

    return change


_TEXT_LOCS = {
    "employee_id": ("employee_id",),
    "destination_city": ("trip", "destination_city"),
    "merchant": ("lines", 0, "merchant"),
}


@pytest.mark.parametrize("field", list(_TEXT_LOCS))
def test_text_of_200_characters_is_valid(field):  # S3
    ClaimIn.model_validate(with_change(_set_text(field, "x" * 200)))


@pytest.mark.parametrize("field", list(_TEXT_LOCS))
def test_text_of_201_characters_is_refused(field):  # S3
    assert _TEXT_LOCS[field] in error_locs(with_change(_set_text(field, "x" * 201)))


# --- Violation.rule_id is one of the five rule IDs (data-model.md Violation.rule_id) ------------


def test_violation_rule_id_must_be_a_known_rule():
    from agentic_app.schemas import Citation, Violation

    fields = {"line_nos": [1], "date": None, "excess_usd": None, "message": "m",
              "citation": Citation(doc_id="POL-RECEIPTS", sections=["3", "4"])}
    assert Violation(rule_id="DUPLICATE", **fields).rule_id == "DUPLICATE"
    with pytest.raises(ValidationError):
        Violation(rule_id="NOT_A_RULE", **fields)


def test_openapi_lists_the_rule_ids():
    from agentic_app.schemas import Violation

    schema = Violation.model_json_schema()
    rule_id = schema["$defs"]["RuleId"]
    assert rule_id["enum"] == [
        "CURRENCY_UNSUPPORTED", "RECEIPT_MISSING", "DUPLICATE",
        "MEALS_DAILY_LIMIT", "LODGING_NIGHTLY_CAP",
    ]
