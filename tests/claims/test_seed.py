"""Seed data and loader (spec FR-020, SC-001, SC-002; contracts/claims-api.md CLI contract)."""

import json
import subprocess
import sys
from decimal import Decimal

import pytest

from agentic_app.claims import store
from agentic_app.claims.rules import RuleId, check_claim

from .conftest import REPO_ROOT

SEED_FILE = REPO_ROOT / "data" / "seed" / "claims.json"


def run_loader(db_path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "agentic_app.claims.seed", "--db", str(db_path)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def seed() -> list[dict]:
    return json.loads(SEED_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("seed") / "claims.db"
    result = run_loader(db_path)
    assert result.returncode == 0, result.stderr
    return db_path, result


def test_seed_has_10_to_15_claims(seed):
    assert 10 <= len(seed) <= 15


def test_loader_reports_count(seeded_db, seed):
    _, result = seeded_db
    assert result.stdout.strip() == f"Loaded {len(seed)} claims"


def test_loader_refuses_non_empty_db(seeded_db):
    db_path, _ = seeded_db
    second = run_loader(db_path)

    assert second.returncode == 1
    assert "not empty" in second.stderr


def test_every_seed_claim_matches_its_expected_result(seeded_db, seed, policy):
    # spec SC-001: expected values were worked out by hand from the policy documents.
    db_path, _ = seeded_db
    conn = store.connect(db_path)
    try:
        for claim_id, expected in enumerate(seed, start=1):
            claim = store.get_claim(conn, claim_id)
            prior = store.prior_lines(conn, claim.employee_id, claim.id)
            result = check_claim(claim, prior, policy)

            assert claim.employee_id == expected["employee_id"]
            assert {v.rule_id for v in result.violations} == set(expected["expected_rules"]), (
                f"claim {claim_id}: {expected['expected_working']}"
            )
            assert result.total_reimbursable_usd == Decimal(expected["expected_total_usd"]), (
                f"claim {claim_id}: {expected['expected_working']}"
            )
    finally:
        conn.close()


def test_seed_covers_every_rule_and_has_clean_claims(seed):
    # spec SC-002
    triggered = {rule for claim in seed for rule in claim["expected_rules"]}
    assert triggered == {rule.value for rule in RuleId}
    assert sum(1 for claim in seed if not claim["expected_rules"]) >= 2


def test_seed_covers_required_situations(seed):
    # spec FR-020: same-day and multi-day trips, multi-night lodging, EUR, GBP and INR lines.
    trips = [(c["trip"]["start_date"] == c["trip"]["end_date"]) for c in seed]
    lines = [line for claim in seed for line in claim["lines"]]
    assert any(trips) and not all(trips)
    assert any(line.get("nights", 1) > 1 for line in lines)
    assert {"EUR", "GBP", "INR"} <= {line["currency"] for line in lines}
