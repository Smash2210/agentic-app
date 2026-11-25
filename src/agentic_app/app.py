"""FastAPI application factory (research R-12).

No app is built at import time. Run the server with:

    uv run uvicorn agentic_app.app:app_from_env --factory
"""

import os
from pathlib import Path

from fastapi import FastAPI

from agentic_app.claims import store
from agentic_app.claims.api import router
from agentic_app.claims.policy import load_policy

DEFAULT_DB_PATH = "data/claims.db"
DEFAULT_POLICY_DIR = "data/policies"


def create_app(db_path: Path, policy_dir: Path) -> FastAPI:
    policy = load_policy(Path(policy_dir))
    conn = store.connect(Path(db_path))
    try:
        store.init_db(conn)
    finally:
        conn.close()

    app = FastAPI(
        title="Expense & Travel Policy Copilot — Claims API",
        version="0.1.0",
        description=(
            "Submit expense claims and check them against the company's currency, receipts, "
            "meals, lodging and per diem policies. Money is always a JSON string (never a "
            "number); checked amounts are in USD. Dates are YYYY-MM-DD."
        ),
    )
    app.state.policy = policy
    app.state.db_path = Path(db_path)
    app.state.policy_dir = Path(policy_dir)
    app.include_router(router)
    return app


def app_from_env() -> FastAPI:
    """Factory for uvicorn --factory: reads CLAIMS_DB_PATH and POLICY_DIR (not .env)."""
    return create_app(
        Path(os.environ.get("CLAIMS_DB_PATH", DEFAULT_DB_PATH)),
        Path(os.environ.get("POLICY_DIR", DEFAULT_POLICY_DIR)),
    )
