"""HTTP routes for claims (contracts/claims-api.md). Routes are added per user story."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from agentic_app.claims import store
from agentic_app.claims.policy import Policy
from agentic_app.claims.rules import check_claim
from agentic_app.schemas import (
    AdjudicateRequest,
    Adjudication,
    CheckResult,
    Claim,
    ClaimIn,
    NotFound,
)

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


# Higher than any claim ID: an adjudication is checked against all of the employee's stored claims.
_AFTER_EVERY_CLAIM = 2**63 - 1


@router.post(
    "/adjudicate",
    response_model=Adjudication,
    tags=["adjudicate"],
    summary="Adjudicate receipts",
    description=(
        "Read receipts given as plain text, turn them into expense lines and check them against "
        "the policy, with a decision and a short explanation. A model reads the receipts and "
        "writes the explanation; every amount, violation and the decision come from the policy "
        "check and code, never from the model. Items the policy excludes but the check cannot "
        "see (alcohol, minibar, ...) and unreadable receipts are reported and make the decision "
        "needs_human_review. Nothing is stored: submit the lines with POST /claims."
    ),
    responses={503: {"description": "The model is not configured or still unavailable after retries."}},
)
def adjudicate_receipts(body: AdjudicateRequest, conn: Conn, policy: CurrentPolicy) -> Adjudication:
    """Preview adjudication of raw receipts (spec 002)."""
    # Imported here so the Claims API can start without loading .env or the Gemini SDK (M02 U1).
    from agentic_app.adjudicate import adjudicate
    from agentic_app.llm import ModelUnavailable

    prior = store.prior_lines(conn, body.employee_id, _AFTER_EVERY_CLAIM)
    try:
        return adjudicate(body, prior, policy)
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
