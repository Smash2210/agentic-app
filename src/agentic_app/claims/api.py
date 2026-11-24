"""HTTP routes for claims (contracts/claims-api.md). Routes are added per user story."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from agentic_app.claims import store
from agentic_app.claims.policy import Policy
from agentic_app.claims.rules import check_claim
from agentic_app.schemas import CheckResult, Claim, ClaimIn

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


def _claim_or_404(conn: sqlite3.Connection, claim_id: int) -> Claim:
    claim = store.get_claim(conn, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    return claim


@router.get("/claims/{claim_id}/check", response_model=CheckResult)
def check(claim_id: int, conn: Conn, policy: CurrentPolicy) -> CheckResult:
    """Policy check of a stored claim; recomputed on every call (User Story 1)."""
    claim = _claim_or_404(conn, claim_id)
    prior = store.prior_lines(conn, claim.employee_id, claim.id)
    return check_claim(claim, prior, policy)


@router.post("/claims", status_code=201, response_model=Claim)
def submit(claim_in: ClaimIn, conn: Conn) -> Claim:
    """Store a valid claim and return it with its new ID (User Story 2). Invalid input never
    reaches here: FastAPI answers 422 listing each error (research R-06)."""
    return store.add_claim(conn, claim_in)

