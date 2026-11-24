import sqlite3
import subprocess
import sys

import pytest

from agentic_app.app import app_from_env, create_app
from agentic_app.claims.policy import Policy, PolicyError


def test_import_has_no_side_effects(tmp_path):
    # Run in an empty directory: building an app at import time would fail to find
    # data/policies here, or would create data/claims.db.
    result = subprocess.run(
        [sys.executable, "-c", "import agentic_app.app"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "data").exists()


def test_create_app_loads_policy_and_creates_schema(db_path, policy_dir):
    app = create_app(db_path, policy_dir)

    assert isinstance(app.state.policy, Policy)
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"claims", "expense_lines"} <= tables


def test_app_from_env_uses_environment(monkeypatch, tmp_path, policy_dir):
    db_path = tmp_path / "from-env.db"
    monkeypatch.setenv("CLAIMS_DB_PATH", str(db_path))
    monkeypatch.setenv("POLICY_DIR", str(policy_dir))

    app = app_from_env()

    assert db_path.exists()
    assert isinstance(app.state.policy, Policy)


def test_broken_policy_dir_raises(db_path, tmp_path):
    with pytest.raises(PolicyError):
        create_app(db_path, tmp_path / "no-policies-here")
