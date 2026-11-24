"""HTTP routes for claims (contracts/claims-api.md). Routes are added per user story."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from agentic_app.claims import store
from agentic_app.claims.policy import Policy
from agentic_app.claims.rules import check_claim
from agentic_app.schemas import CheckResult, Claim, ClaimIn, NotFound

router = APIRouter()


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    """One SQLite connection per request (research R-12)."""
    conn = store.connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_policy(request: Request) -> Policy:
    return request.app.state.policy


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
CurrentPolicy = Annotated[Policy, Depends(get_policy)]
ClaimId = Annotated[int, Path(description="ID returned when the claim was submitted.")]

NOT_FOUND = {
    404: {
        "model": NotFound,
        "description": "No claim with this ID.",
        "content": {"application/json": {"example": {"detail": "Claim 99 not found"}}},
    }
}


def _claim_or_404(conn: sqlite3.Connection, claim_id: int) -> Claim:
    claim = store.get_claim(conn, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    return claim


@router.get(
    "/claims/{claim_id}/check",
    response_model=CheckResult,
    tags=["claims"],
    summary="Check a claim against policy",
    description=(
        "Check a stored claim against the expense policies and return what is reimbursable. "
        "Each line is converted to USD; the receipt, duplicate, meals and lodging rules are "
        "applied; the per diem for the trip is added. Every violation is listed with the policy "
        "sections it comes from. Read-only: the result is computed on every call and never "
        "stored. Duplicates are looked for within the claim and in the same employee's earlier "
        "claims."
    ),
    responses=NOT_FOUND,
)
def check(claim_id: ClaimId, conn: Conn, policy: CurrentPolicy) -> CheckResult:
    """Policy check of a stored claim; recomputed on every call."""
    claim = _claim_or_404(conn, claim_id)
    prior = store.prior_lines(conn, claim.employee_id, claim.id)
    return check_claim(claim, prior, policy)


@router.post(
    "/claims",
    status_code=201,
    response_model=Claim,
    tags=["claims"],
    summary="Submit a claim",
    description=(
        "Store an expense claim and return it with its new ID and a `line_no` (1, 2, ...) on "
        "each line. Money must be sent as a JSON string such as \"12.50\". Invalid input is "
        "answered with 422, listing every error, and nothing is stored. A currency the policy "
        "does not support is accepted here and flagged when the claim is checked."
    ),
)
def submit(claim_in: ClaimIn, conn: Conn) -> Claim:
    """Store a valid claim and return it with its new ID. Invalid input never
    reaches here: FastAPI answers 422 listing each error (research R-06)."""
    return store.add_claim(conn, claim_in)


@router.get(
    "/claims/{claim_id}",
    response_model=Claim,
    tags=["claims"],
    summary="Get a claim",
    description="Return one stored claim, in the same shape as the submit response.",
    responses=NOT_FOUND,
)
def get_one(claim_id: ClaimId, conn: Conn) -> Claim:
    """One stored claim."""
    return _claim_or_404(conn, claim_id)


@router.get(
    "/claims",
    response_model=list[Claim],
    tags=["claims"],
    summary="List an employee's claims",
    description=(
        "Return every claim the employee has submitted, oldest first (ascending ID). "
        "Returns an empty list if there are none."
    ),
)
def list_for_employee(
    employee_id: Annotated[str, Query(description="Employee whose claims to list, e.g. E-001.")],
    conn: Conn,
) -> list[Claim]:
    """An employee's claims in submission order; [] if none."""
    return store.list_claims(conn, employee_id)
