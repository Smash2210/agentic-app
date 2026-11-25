import pytest

from agent_helpers import VECTORS
from agentic_app.claims import seed
from agentic_app.tools import claims_tools, resilience


@pytest.fixture
def agent_env(tmp_path, monkeypatch):
    """Seeded temp claims DB, offline question embeddings, no injected faults, default limits."""
    db = tmp_path / "claims.db"
    assert seed.main(["--db", str(db)]) == 0
    monkeypatch.setenv("CLAIMS_DB_PATH", str(db))
    monkeypatch.setattr(claims_tools, "embed", lambda texts, task: [VECTORS["POL-MEALS#1"]] * len(texts))
    monkeypatch.setattr(resilience, "BACKOFF_S", 0)
    monkeypatch.delenv("TOOL_FAULT", raising=False)
    monkeypatch.delenv("AGENT_MAX_STEPS", raising=False)
