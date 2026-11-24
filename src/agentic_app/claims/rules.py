"""The policy rules engine: check_claim (research R-08).

Pure: no I/O, no clock, no randomness, no LLM. Every limit, rate and percentage comes from the
Policy object; this module contains no policy numbers (spec FR-011).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from types import MappingProxyType

from agentic_app.claims.money import to_cents
from agentic_app.claims.policy import Policy
from agentic_app.schemas import (
    Category,
    CheckResult,
    Citation,
    Claim,
    ExpenseLine,
    LineResult,
    PerDiem,
    PriorLine,
    RuleId,  # re-exported: defined with the Violation model it types
    Violation,
)


@dataclass(frozen=True)
class PolicyRef:
    """An immutable doc_id + sections pair; a fresh Citation is built from it for each result."""

    doc_id: str
    sections: tuple[str, ...]

    def citation(self) -> Citation:
        return Citation(doc_id=self.doc_id, sections=list(self.sections))


RULE_CITATIONS = MappingProxyType({
    RuleId.CURRENCY_UNSUPPORTED: PolicyRef("POL-CURRENCY", ("2",)),
    RuleId.RECEIPT_MISSING: PolicyRef("POL-RECEIPTS", ("1", "2")),
    RuleId.DUPLICATE: PolicyRef("POL-RECEIPTS", ("3", "4")),
    RuleId.MEALS_DAILY_LIMIT: PolicyRef("POL-MEALS", ("1", "3")),
    RuleId.LODGING_NIGHTLY_CAP: PolicyRef("POL-LODGING", ("1", "2", "3")),
})

PER_DIEM_CITATIONS = MappingProxyType({
    "multi_day": PolicyRef("POL-PERDIEM", ("1", "2")),
    "same_day": PolicyRef("POL-PERDIEM", ("1", "3")),
})

_RULE_ORDER = tuple(RuleId)


@dataclass
class _LineState:
    line: ExpenseLine
    claimed_usd: Decimal | None
    rejected: bool = False  # rejected outright by the currency, receipt or duplicate rule
    flagged_for_review: bool = False
    paid_usd: Decimal = field(default_factory=lambda: to_cents(Decimal(0)))


def _violation(
    rule: RuleId, line_nos: list[int], message: str,
    day: date | None = None, excess_usd: Decimal | None = None,
) -> Violation:
    return Violation(
        rule_id=rule, line_nos=sorted(line_nos), date=day, excess_usd=excess_usd,
        message=message, citation=RULE_CITATIONS[rule].citation(),
    )


def _duplicate_key(line_date: date, amount: Decimal, currency: str, merchant: str) -> tuple:
    return (line_date, amount, currency, merchant.strip().casefold())


def _check_lines(
    claim: Claim, prior_lines: Sequence[PriorLine], policy: Policy, violations: list[Violation]
) -> list[_LineState]:
    """Steps 1–3: currency, receipt and duplicate rules, line by line."""
    seen: dict[tuple, str] = {}
    for prior in prior_lines:
        key = _duplicate_key(prior.date, prior.amount, prior.currency, prior.merchant)
        seen.setdefault(key, f"claim {prior.claim_id} line {prior.line_no}")

    states = []
    for line in claim.lines:
        rate = policy.rate_for(line.currency)
        state = _LineState(line, None if rate is None else to_cents(line.amount * rate))

        if state.claimed_usd is None:
            state.rejected = True
            violations.append(_violation(
                RuleId.CURRENCY_UNSUPPORTED, [line.line_no],
                f"Line {line.line_no}: currency {line.currency} is not supported; not reimbursed. "
                "Resubmit it in a supported currency.",
            ))
        elif state.claimed_usd > policy.receipt_threshold_usd and not line.receipt_attached:
            state.rejected = True
            violations.append(_violation(
                RuleId.RECEIPT_MISSING, [line.line_no],
                f"Line {line.line_no}: {state.claimed_usd} USD is over "
                f"{to_cents(policy.receipt_threshold_usd)} USD and has no receipt; not reimbursed.",
            ))

        key = _duplicate_key(line.date, line.amount, line.currency, line.merchant)
        if key in seen:
            state.rejected = True
            state.flagged_for_review = True
            violations.append(_violation(
                RuleId.DUPLICATE, [line.line_no],
                f"Line {line.line_no}: duplicate of {seen[key]}; not reimbursed and flagged for "
                "review.",
            ))
        else:
            seen[key] = f"line {line.line_no} in this claim"

        if not state.rejected and line.category not in (Category.MEAL, Category.LODGING):
            state.paid_usd = state.claimed_usd  # FR-019: no further limits apply
        states.append(state)
    return states


def _apply_meals_limit(
    states: list[_LineState], policy: Policy, violations: list[Violation]
) -> None:
    """Step 4: per calendar day, pay meal lines in line order up to the daily limit."""
    by_day: dict[date, list[_LineState]] = defaultdict(list)
    for state in states:
        if state.line.category is Category.MEAL and not state.rejected:
            by_day[state.line.date].append(state)

    limit = policy.meals_daily_limit_usd
    for day in sorted(by_day):
        remaining = limit
        over_lines, excess = [], to_cents(Decimal(0))
        for state in by_day[day]:
            state.paid_usd = to_cents(min(state.claimed_usd, max(remaining, Decimal(0))))
            remaining -= state.paid_usd
            if state.paid_usd < state.claimed_usd:
                over_lines.append(state.line.line_no)
                excess += state.claimed_usd - state.paid_usd
        if over_lines:
            total = sum((s.claimed_usd for s in by_day[day]), to_cents(Decimal(0)))
            violations.append(_violation(
                RuleId.MEALS_DAILY_LIMIT, over_lines,
                f"Meals on {day}: {total} USD is over the daily limit of {to_cents(limit)} USD; "
                f"{excess} USD rejected.",
                day=day, excess_usd=excess,
            ))


def _night_shares(state: _LineState) -> list[tuple[date, Decimal]]:
    """Split a lodging line evenly per night; the last night takes any leftover cent (R-10)."""
    nights = state.line.nights or 1
    share = to_cents(state.claimed_usd / nights)
    shares = [share] * (nights - 1) + [state.claimed_usd - share * (nights - 1)]
    return [(state.line.date + timedelta(days=k), amount) for k, amount in enumerate(shares)]


def _apply_lodging_cap(
    states: list[_LineState], city: str, policy: Policy, violations: list[Violation]
) -> None:
    """Step 5: per night, pay lodging shares in line order up to the city's nightly cap."""
    by_night: dict[date, list[tuple[_LineState, Decimal]]] = defaultdict(list)
    for state in states:
        if state.line.category is Category.LODGING and not state.rejected:
            for night, share in _night_shares(state):
                by_night[night].append((state, share))

    cap = policy.lodging_cap_for(city)
    for night in sorted(by_night):
        remaining = cap
        over_lines, excess = [], to_cents(Decimal(0))
        for state, share in by_night[night]:
            paid = to_cents(min(share, max(remaining, Decimal(0))))
            remaining -= paid
            state.paid_usd += paid
            if paid < share:
                over_lines.append(state.line.line_no)
                excess += share - paid
        if over_lines:
            total = sum((share for _, share in by_night[night]), to_cents(Decimal(0)))
            violations.append(_violation(
                RuleId.LODGING_NIGHTLY_CAP, over_lines,
                f"Night of {night}: lodging {total} USD is over the {city.strip()} cap of "
                f"{to_cents(cap)} USD; {excess} USD rejected.",
                day=night, excess_usd=excess,
            ))


def _per_diem(claim: Claim, policy: Policy) -> PerDiem:
    """Step 6: first and last day at the travel-day fraction, days between at the full rate;
    a same-day trip is one day at the same-day fraction (POL-PERDIEM §2–3)."""
    trip = claim.trip
    rate = policy.per_diem_rate_for(trip.destination_city)
    days = (trip.end_date - trip.start_date).days + 1
    if days == 1:
        amount = rate * policy.same_day_fraction
        ref = PER_DIEM_CITATIONS["same_day"]
    else:
        travel_days_amount = rate * policy.travel_day_fraction
        full_days = days - 2  # first and last day are paid at the travel-day fraction
        amount = travel_days_amount + rate * full_days + travel_days_amount
        ref = PER_DIEM_CITATIONS["multi_day"]
    return PerDiem(
        city=trip.destination_city, daily_rate_usd=to_cents(rate), days=days,
        amount_usd=to_cents(amount), citation=ref.citation(),
    )


def _sort_key(violation: Violation) -> tuple:
    return (
        _RULE_ORDER.index(violation.rule_id),
        violation.date or date.min,
        violation.line_nos[0],
    )


def check_claim(claim: Claim, prior_lines: Sequence[PriorLine], policy: Policy) -> CheckResult:
    """Check a stored claim against policy.

    `prior_lines` are the lines of the same employee's earlier-submitted claims (the caller's job,
    research R-11). Same arguments always give an equal result.
    """
    violations: list[Violation] = []
    states = _check_lines(claim, prior_lines, policy, violations)
    _apply_meals_limit(states, policy, violations)
    _apply_lodging_cap(states, claim.trip.destination_city, policy, violations)
    per_diem = _per_diem(claim, policy)

    lines = [
        LineResult(
            line_no=state.line.line_no,
            claimed_usd=state.claimed_usd,
            reimbursable_usd=state.paid_usd,
            rejected_usd=None if state.claimed_usd is None else state.claimed_usd - state.paid_usd,
            flagged_for_review=state.flagged_for_review,
        )
        for state in states
    ]
    lines_total = sum((line.reimbursable_usd for line in lines), to_cents(Decimal(0)))
    return CheckResult(
        claim_id=claim.id,
        lines=lines,
        violations=sorted(violations, key=_sort_key),
        per_diem=per_diem,
        lines_reimbursable_usd=lines_total,
        total_reimbursable_usd=lines_total + per_diem.amount_usd,
    )
