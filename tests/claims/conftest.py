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
