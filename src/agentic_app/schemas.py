"""Pydantic models for claims, shared by later tiers (data-model.md).

Money is Decimal everywhere and is serialised to JSON as a string. Request money must be sent
as a JSON string (research R-05).
"""

from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
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


def _money_must_be_string(value: Any) -> Any:
    if not isinstance(value, str):
        raise ValueError('money must be sent as a string such as "12.50", not a number')
    return value


def _normalise_currency(value: str) -> str:
    return _not_blank(value).strip().upper()


NonBlankStr = Annotated[str, AfterValidator(_not_blank)]
MoneyIn = Annotated[
    Decimal, BeforeValidator(_money_must_be_string), Field(gt=0, decimal_places=2)
]
CurrencyCode = Annotated[str, AfterValidator(_normalise_currency)]


# --- input --------------------------------------------------------------------------------------


class Trip(BaseModel):
    destination_city: NonBlankStr
    start_date: date
    end_date: date


class ExpenseLineIn(BaseModel):
    date: date
    category: Category
    merchant: NonBlankStr
    amount: MoneyIn
    currency: CurrencyCode
    receipt_attached: bool
    nights: Annotated[int, Field(strict=True, ge=1)] | None = Field(
        default=None, validate_default=True
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
    employee_id: NonBlankStr
    trip: Trip
    lines: Annotated[list[ExpenseLineIn], Field(min_length=1)]

    @model_validator(mode="after")
    def _check_dates_against_trip(self) -> "ClaimIn":
        """Report every cross-field error at once, each at its own location (research R-06)."""
        trip = self.trip
        errors = []
        if trip.end_date < trip.start_date:
            errors.append(_cross_field_error(
                ("trip", "end_date"), "end_date must not be before start_date", trip.end_date
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
    line_no: int
    date: date
    category: Category
    merchant: str
    amount: Decimal
    currency: str
    receipt_attached: bool
    nights: int | None


class Claim(BaseModel):
    id: int
    employee_id: str
    trip: Trip
    lines: list[ExpenseLine]


class PriorLine(BaseModel):
    """A line from one of the employee's earlier claims, for duplicate detection (R-11)."""

    claim_id: int
    line_no: int
    date: date
    amount: Decimal
    currency: str
    merchant: str


# --- check result -------------------------------------------------------------------------------


class Citation(BaseModel):
    doc_id: str
    sections: list[str]


class Violation(BaseModel):
    rule_id: str
    line_nos: list[int]
    date: date | None
    excess_usd: Decimal | None
    message: str
    citation: Citation


class LineResult(BaseModel):
    line_no: int
    claimed_usd: Decimal | None
    reimbursable_usd: Decimal
    rejected_usd: Decimal | None
    flagged_for_review: bool


class PerDiem(BaseModel):
    city: str
    daily_rate_usd: Decimal
    days: int
    amount_usd: Decimal
    citation: Citation


class CheckResult(BaseModel):
    claim_id: int
    lines: list[LineResult]
    violations: list[Violation]
    per_diem: PerDiem
    lines_reimbursable_usd: Decimal
    total_reimbursable_usd: Decimal
