"""HTTP routes for claims (contracts/claims-api.md). Routes are added per user story."""

import sqlite3
from collections.abc import Iterator

from fastapi import APIRouter, Request

from agentic_app.claims import store
from agentic_app.claims.policy import Policy

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
