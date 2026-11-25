"""Pydantic models for claims, shared by later tiers (data-model.md).

Money is Decimal everywhere and is serialised to JSON as a string. Request money must be sent
as a JSON string (research R-05).
"""

import re
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError


class Category(StrEnum):
    MEAL = "meal"
    LODGING = "lodging"
    TRANSPORT = "transport"
    OTHER = "other"


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be empty")
    return value


# Input bounds (spec FR-002, Clarifications "M06 security").
MAX_AMOUNT = Decimal("1000000.00")
MAX_TRIP_DAYS = 366
MAX_LINES = 50
MAX_TEXT = 200

# ASCII digits only: Python's \d and Decimal also accept other scripts' digits.
_PLAIN_DECIMAL = re.compile(r"[0-9]+(\.[0-9]{0,2})?")


def _money_must_be_plain_decimal_string(value: Any) -> Any:
    if not isinstance(value, str):
        raise ValueError('money must be sent as a string such as "12.50", not a number')
    value = value.strip()
    if not _PLAIN_DECIMAL.fullmatch(value):
        raise ValueError(
            'money must be plain decimal text such as "12.50": digits, optionally "." and at '
            "most 2 decimals, no sign or exponent"
        )
    return value


def _trimmed(value: str) -> str:
    return _not_blank(value).strip()


def _normalise_currency(value: str) -> str:
    return _trimmed(value).upper()


NonBlankStr = Annotated[str, AfterValidator(_not_blank)]
BoundedText = Annotated[NonBlankStr, Field(max_length=MAX_TEXT)]
MoneyIn = Annotated[
    Decimal,
    BeforeValidator(_money_must_be_plain_decimal_string),
    Field(gt=0, le=MAX_AMOUNT, decimal_places=2),
]
CurrencyCode = Annotated[str, AfterValidator(_normalise_currency)]
EmployeeId = Annotated[str, Field(max_length=MAX_TEXT), AfterValidator(_trimmed)]

_MONEY_OUT = "JSON string with 2 decimals."

# The claim in contracts/claims-api.md, shown as the request example in the OpenAPI docs.
_CLAIM_EXAMPLE = {
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


# --- input --------------------------------------------------------------------------------------


class Trip(BaseModel):
    destination_city: Annotated[BoundedText, Field(description=(
        "City the trip is to; must not be blank, at most 200 characters. Sets the lodging cap and "
        "per diem rate, matched case-insensitively; a city without its own rate gets the 'any "
        "other city' rate."
    ))]
    start_date: Annotated[date, Field(description="First day of the trip.")]
    end_date: Annotated[date, Field(description=(
        "Last day of the trip, included. Must not be before start_date; the trip is at most 366 "
        "days, start to end inclusive."
    ))]


class ExpenseLineIn(BaseModel):
    date: Annotated[date, Field(description=(
        "Day of the expense; must be within the trip's dates. For lodging, the first night."
    ))]
    category: Annotated[Category, Field(description="Kind of expense.")]
    merchant: Annotated[BoundedText, Field(description=(
        "Who was paid; must not be blank, at most 200 characters. Used to detect duplicate lines."
    ))]
    amount: Annotated[MoneyIn, Field(description=(
        'Amount in `currency`, as a JSON string such as "12.50" (a JSON number is rejected). '
        'Plain decimal text: digits, optionally "." and at most 2 decimals (no sign or exponent '
        'such as "1e2"). Greater than 0, at most 1000000.00.'
    ))]
    currency: Annotated[CurrencyCode, Field(description=(
        "3-letter currency code, upper-cased on submit. Supported: USD, EUR, GBP, INR. Any other "
        "code is accepted here and flagged as CURRENCY_UNSUPPORTED when the claim is checked."
    ))]
    receipt_attached: Annotated[bool, Field(description=(
        "Whether a receipt is attached. A line over 25 USD (after conversion) without a receipt "
        "is not reimbursed."
    ))]
    nights: Annotated[int, Field(strict=True, ge=1)] | None = Field(
        default=None, validate_default=True, description=(
            "Lodging lines only: number of nights, integer of at least 1, default 1. `date` is "
            "the first night; the last night must not be after the trip's end date. Omit (or "
            "send null) for other categories."
        ),
    )

    @field_validator("nights")
    @classmethod
    def _nights_only_on_lodging(cls, nights: int | None, info: ValidationInfo) -> int | None:
        category = info.data.get("category")
        if category is None:
            return nights  # category itself is invalid; that error is reported instead
        if category is Category.LODGING:
            return 1 if nights is None else nights
        if nights is not None:
            raise ValueError("nights is only allowed on lodging lines")
        return None


def _cross_field_error(loc: tuple, message: str, value: Any) -> InitErrorDetails:
    return InitErrorDetails(
        type=PydanticCustomError("cross_field", message), loc=loc, input=value
    )


class ClaimIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [_CLAIM_EXAMPLE]})

    employee_id: Annotated[EmployeeId, Field(description=(
        "Employee making the claim, e.g. E-001; must not be blank, at most 200 characters. "
        "Trimmed on submit."
    ))]
    trip: Annotated[Trip, Field(description="The trip the expenses belong to.")]
    lines: Annotated[list[ExpenseLineIn], Field(min_length=1, max_length=MAX_LINES, description=(
        "Expense lines, at least one and at most 50. They are numbered 1, 2, ... in this order."
    ))]

    @model_validator(mode="after")
    def _check_dates_against_trip(self) -> "ClaimIn":
        """Report every cross-field error at once, each at its own location (research R-06)."""
        trip = self.trip
        errors = []
        if trip.end_date < trip.start_date:
            errors.append(_cross_field_error(
                ("trip", "end_date"), "end_date must not be before start_date", trip.end_date
            ))
        elif (trip.end_date - trip.start_date).days + 1 > MAX_TRIP_DAYS:
            errors.append(_cross_field_error(
                ("trip", "end_date"), f"the trip must be at most {MAX_TRIP_DAYS} days long",
                trip.end_date,
            ))
        for i, line in enumerate(self.lines):
            if not trip.start_date <= line.date <= trip.end_date:
                errors.append(_cross_field_error(
                    ("lines", i, "date"), "date must be within the trip's start and end dates",
                    line.date,
                ))
            elif line.nights is not None:
                last_night = line.date + timedelta(days=line.nights - 1)
                if last_night > trip.end_date:
                    errors.append(_cross_field_error(
                        ("lines", i, "nights"),
                        "the last night must not be after the trip's end date",
                        line.nights,
                    ))
        if errors:
            raise ValidationError.from_exception_data(type(self).__name__, errors)
        return self


# --- stored -------------------------------------------------------------------------------------


class ExpenseLine(BaseModel):
    line_no: Annotated[int, Field(description="Position of the line in the claim, from 1.")]
    date: Annotated[date, Field(description="Day of the expense. For lodging, the first night.")]
    category: Annotated[Category, Field(description="Kind of expense.")]
    merchant: Annotated[str, Field(description="Who was paid.")]
    amount: Annotated[Decimal, Field(
        description="Amount in `currency`, as submitted. JSON string."
    )]
    currency: Annotated[str, Field(description="Currency code, upper-cased.")]
    receipt_attached: Annotated[bool, Field(description="Whether a receipt is attached.")]
    nights: Annotated[int | None, Field(description=(
        "Lodging: number of nights (1 if it was omitted). Null for other categories."
    ))]


class Claim(BaseModel):
    id: Annotated[int, Field(description="Claim ID, assigned on submit.")]
    employee_id: Annotated[str, Field(description="Employee who made the claim.")]
    trip: Annotated[Trip, Field(description="The trip the expenses belong to.")]
    lines: Annotated[list[ExpenseLine], Field(description="Expense lines, in line_no order.")]


class PriorLine(BaseModel):
    """A line from one of the employee's earlier claims, for duplicate detection (R-11)."""

    claim_id: int
    line_no: int
    date: date
    amount: Decimal
    currency: str
    merchant: str


# --- check result -------------------------------------------------------------------------------


class RuleId(StrEnum):
    """Violation rule IDs, in the order violations are reported."""

    # Order and IDs: research R-09.

    CURRENCY_UNSUPPORTED = "CURRENCY_UNSUPPORTED"
    RECEIPT_MISSING = "RECEIPT_MISSING"
    DUPLICATE = "DUPLICATE"
    MEALS_DAILY_LIMIT = "MEALS_DAILY_LIMIT"
    LODGING_NIGHTLY_CAP = "LODGING_NIGHTLY_CAP"


class Citation(BaseModel):
    doc_id: Annotated[str, Field(description="Policy document ID, e.g. POL-MEALS.")]
    sections: Annotated[list[str], Field(
        description='Section numbers in that document, e.g. ["1", "2"].'
    )]


class Violation(BaseModel):
    rule_id: Annotated[RuleId, Field(description="The rule that was broken.")]
    line_nos: Annotated[list[int], Field(description="The lines affected, ascending.")]
    date: Annotated[date | None, Field(description=(
        "The day (MEALS_DAILY_LIMIT) or night (LODGING_NIGHTLY_CAP) concerned; null for the "
        "other rules."
    ))]
    excess_usd: Annotated[Decimal | None, Field(description=(
        "USD rejected by this violation, as a " + _MONEY_OUT + " Set only for "
        "MEALS_DAILY_LIMIT and LODGING_NIGHTLY_CAP; null for the other rules."
    ))]
    message: Annotated[str, Field(description=(
        "Plain-language explanation with the amounts and the limit. The wording may change; "
        "do not parse it."
    ))]
    citation: Annotated[Citation, Field(description="Where the rule is in the policy.")]


class LineResult(BaseModel):
    line_no: Annotated[int, Field(description="The line this result is for.")]
    claimed_usd: Annotated[Decimal | None, Field(description=(
        "The line's amount converted to USD, rounded half-up, as a " + _MONEY_OUT + " Null when "
        "the currency is not supported."
    ))]
    reimbursable_usd: Annotated[Decimal, Field(description=(
        "USD reimbursed for this line (0.00 or more), as a " + _MONEY_OUT
    ))]
    rejected_usd: Annotated[Decimal | None, Field(description=(
        "claimed_usd minus reimbursable_usd, as a " + _MONEY_OUT + " Null when claimed_usd is "
        "null."
    ))]
    flagged_for_review: Annotated[bool, Field(description=(
        "True when the line duplicates an earlier line and was rejected."
    ))]


class PerDiem(BaseModel):
    city: Annotated[str, Field(description="Destination city, as submitted.")]
    daily_rate_usd: Annotated[Decimal, Field(description=(
        "Per diem rate for the city, as a " + _MONEY_OUT
    ))]
    days: Annotated[int, Field(description="Calendar days of the trip, both ends included.")]
    amount_usd: Annotated[Decimal, Field(description=(
        "Per diem paid, as a " + _MONEY_OUT + " The first and last day are paid at 75% of the "
        "daily rate, the days in between at 100%; a same-day trip is one day at 75%."
    ))]
    citation: Annotated[Citation, Field(description="Where the per diem rules are in the policy.")]


class CheckResult(BaseModel):
    claim_id: Annotated[int, Field(description="The claim that was checked.")]
    lines: Annotated[list[LineResult], Field(description="One result per line, in line_no order.")]
    violations: Annotated[list[Violation], Field(description=(
        "Every policy violation found; empty if there are none. Sorted by rule (in the order "
        "the rule_id values are listed), then date, then first line number."
    ))]
    per_diem: Annotated[PerDiem, Field(description="Per diem for the trip.")]
    lines_reimbursable_usd: Annotated[Decimal, Field(description=(
        "Sum of reimbursable_usd over all lines, as a " + _MONEY_OUT
    ))]
    total_reimbursable_usd: Annotated[Decimal, Field(description=(
        "lines_reimbursable_usd plus per_diem.amount_usd, as a " + _MONEY_OUT
    ))]


class NotFound(BaseModel):
    """Error body when no claim has the requested ID."""

    detail: Annotated[str, Field(description="What was not found, e.g. Claim 99 not found.")]


# --- adjudication (spec 002) --------------------------------------------------------------------

MAX_RECEIPTS = 10
MAX_RECEIPT_TEXT = 5000

ReceiptText = Annotated[NonBlankStr, Field(max_length=MAX_RECEIPT_TEXT)]


class Decision(StrEnum):
    APPROVE = "approve"
    PARTIAL = "partial"
    REJECT = "reject"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class AdjudicateRequest(BaseModel):
    employee_id: Annotated[EmployeeId, Field(description=(
        "Employee the receipts belong to, e.g. E-001; trimmed. Their stored claims are used to "
        "spot duplicates."
    ))]
    trip: Annotated[Trip, Field(description="The trip the receipts belong to.")]
    receipts: Annotated[list[ReceiptText], Field(min_length=1, max_length=MAX_RECEIPTS, description=(
        "Receipts as plain text, one string per receipt (1 to 10, each at most 5,000 characters)."
    ))]


class Flag(BaseModel):
    receipt: Annotated[int, Field(ge=1, description="Receipt number, from 1, in request order.")]
    item: Annotated[str, Field(description="The item as it appears on the receipt.")]
    reason: Annotated[str, Field(description="Why it was left out of the lines.")]
    citation: Annotated[str, Field(description="Policy section, e.g. POL-LODGING §4.")]


class ModelUsage(BaseModel):
    model: Annotated[str, Field(description=(
        "Model(s) that answered, comma-separated if a fallback model was used."
    ))]
    model_calls: Annotated[int, Field(description="Model calls made for this request.")]
    prompt_tokens: Annotated[int, Field(description="Input tokens, summed over calls.")]
    cached_tokens: Annotated[int, Field(description="Input tokens served from the model's cache.")]
    thoughts_tokens: Annotated[int, Field(description="Reasoning tokens, summed over calls.")]
    output_tokens: Annotated[int, Field(description="Output tokens, summed over calls.")]
    latency_ms: Annotated[int, Field(description="Time spent in model calls, milliseconds.")]


class Adjudication(BaseModel):
    decision: Annotated[Decision, Field(description=(
        "Set by code, never by the model: needs_human_review if anything is flagged, unreadable "
        "or invalid; otherwise reject (nothing reimbursable), partial (anything rejected or any "
        "violation) or approve."
    ))]
    review_reasons: Annotated[list[str], Field(description=(
        "Why the decision is needs_human_review; empty otherwise."
    ))]
    lines: Annotated[list[ExpenseLine], Field(description=(
        "Expense lines read from the receipts, as checked. Empty if none could be checked."
    ))]
    check: Annotated[CheckResult | None, Field(description=(
        "The policy check of `lines`, exactly as GET /claims/{id}/check computes it. Every amount "
        "in this response comes from here. Null if no lines could be checked."
    ))]
    flags: Annotated[list[Flag], Field(description=(
        "Items left out because the policy excludes them but the check cannot see them."
    ))]
    unreadable: Annotated[list[str], Field(description=(
        "Receipts, or parts of them, that could not be read with confidence."
    ))]
    explanation: Annotated[str, Field(description=(
        "Short explanation for the employee, citing policy sections."
    ))]
    usage: Annotated[ModelUsage, Field(description="Model usage for this request.")]


# --- policy Q&A (spec 003) ----------------------------------------------------------------------

MAX_QUESTION = 500


class AskRequest(BaseModel):
    question: Annotated[NonBlankStr, Field(max_length=MAX_QUESTION, description=(
        "A question about the travel and expense policy, in your own words (at most 500 characters)."
    ))]
