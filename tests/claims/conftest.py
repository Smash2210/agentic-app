from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def policy_dir() -> Path:
    return REPO_ROOT / "data" / "policies"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "claims.db"


@pytest.fixture(scope="session")
def policy(policy_dir):
    from agentic_app.claims.policy import load_policy

    return load_policy(policy_dir)


def _make_claim(
    *lines: dict,
    city: str = "Berlin",
    start: str = "2026-03-10",
    end: str = "2026-03-12",
    employee_id: str = "E-001",
    claim_id: int = 1,
):
    """Build a stored Claim for rule tests. Each line dict overrides these defaults:
    date = trip start, category meal, merchant "Merchant <n>", amount "10.00" USD, receipt attached,
    nights 1 for lodging and None otherwise."""
    from agentic_app.schemas import Claim, ExpenseLine, Trip

    built = []
    for line_no, overrides in enumerate(lines, start=1):
        fields = {
            "date": start,
            "category": "meal",
            "merchant": f"Merchant {line_no}",
            "amount": "10.00",
            "currency": "USD",
            "receipt_attached": True,
        }
        fields.update(overrides)
        fields.setdefault("nights", 1 if fields["category"] == "lodging" else None)
        fields["amount"] = Decimal(fields["amount"])
        built.append(ExpenseLine(line_no=line_no, **fields))
    return Claim(
        id=claim_id,
        employee_id=employee_id,
        trip=Trip(destination_city=city, start_date=start, end_date=end),
        lines=built,
    )


def _prior_lines_of(*claims):
    """The PriorLine records a store would return for these earlier claims."""
    from agentic_app.schemas import PriorLine

    return [
        PriorLine(claim_id=claim.id, line_no=line.line_no, date=line.date, amount=line.amount,
                  currency=line.currency, merchant=line.merchant)
        for claim in claims
        for line in claim.lines
    ]


@pytest.fixture
def make_claim():
    return _make_claim


@pytest.fixture
def prior_lines_of():
    return _prior_lines_of


@pytest.fixture
def check(policy):
    """check_claim with the real policy; prior lines default to none."""

    def run(claim, prior_lines=()):
        from agentic_app.claims.rules import check_claim

        return check_claim(claim, list(prior_lines), policy)

    return run
