"""Spec 004 tools: timeout, one retry, typed error results, fault injection (FR-402..FR-405)."""

import json
import time
from pathlib import Path

import pytest

from agentic_app.claims import seed
from agentic_app.tools import claims_tools, resilience
from agentic_app.tools.errors import ToolBadInput, ToolUnavailable
from agentic_app.tools.resilience import resilient

REPO = Path(__file__).resolve().parents[1]
VECTORS = {k: v["vector"] for k, v in
           json.loads((REPO / "data/index/embeddings.json").read_text())["passages"].items()}


def meals_embed(texts, task):
    return [VECTORS["POL-MEALS#1"] for _ in texts]


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(resilience, "BACKOFF_S", 0)
    monkeypatch.delenv("TOOL_FAULT", raising=False)


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    db = tmp_path / "claims.db"
    assert seed.main(["--db", str(db)]) == 0
    monkeypatch.setenv("CLAIMS_DB_PATH", str(db))
    monkeypatch.setattr(claims_tools, "embed", meals_embed)
    return db


def counting(behaviours, timeout_s=0.2, fallback="do X"):
    """A resilient tool that follows behaviours[i] on call i: 'ok', 'slow', 'down', 'bad', 'bug'."""
    calls = []

    @resilient("t", timeout_s=timeout_s, fallback=fallback)
    def tool(x: int) -> dict:
        b = behaviours[len(calls)]
        calls.append(b)
        if b == "slow":
            time.sleep(timeout_s * 3)
        if b == "down":
            raise ToolUnavailable("t", "service down")
        if b == "bad":
            raise ToolBadInput("t", "bad x")
        if b == "bug":
            raise KeyError("oops")
        return {"status": "ok", "x": x}
    return tool, calls


def test_success_returns_the_result():
    tool, calls = counting(["ok"])
    assert tool(1) == {"status": "ok", "x": 1} and calls == ["ok"]


def test_timeout_is_retried_once_then_succeeds():
    tool, calls = counting(["slow", "ok"])
    assert tool(1)["status"] == "ok" and calls == ["slow", "ok"]


def test_timeout_twice_returns_a_typed_error_result_not_an_exception():
    tool, calls = counting(["slow", "slow"], fallback="use check_claim citations")
    result = tool(1)
    assert calls == ["slow", "slow"]
    assert result["status"] == "error"
    assert result["error"]["type"] == "ToolTimeout" and result["error"]["attempts"] == 2
    assert result["fallback"] == "use check_claim citations"


def test_unavailable_is_retried_once():
    tool, calls = counting(["down", "down"])
    assert tool(1)["error"]["type"] == "ToolUnavailable" and len(calls) == 2


def test_bad_input_is_not_retried():
    tool, calls = counting(["bad", "ok"])
    result = tool(1)
    assert result["error"] == {"type": "ToolBadInput", "tool": "t", "message": "bad x",
                               "attempts": 1, "retryable": False}
    assert calls == ["bad"]


def test_unexpected_exception_becomes_tool_unavailable():
    tool, _ = counting(["bug", "bug"])
    result = tool(1)
    assert result["error"]["type"] == "ToolUnavailable" and "KeyError" in result["error"]["message"]


def test_wrapper_keeps_the_signature_and_docstring_adk_reads():
    import inspect

    assert list(inspect.signature(claims_tools.check_claim).parameters) == ["claim_id"]
    assert "rules engine" in claims_tools.check_claim.__doc__


@pytest.mark.parametrize("value,expected", [
    ("search_policy:timeout", "timeout"), ("get_claim:error, search_policy:error", "error"),
    ("check_claim:timeout", None), ("search_policy:explode", None), ("", None)])
def test_fault_spec_parsing(monkeypatch, value, expected):
    monkeypatch.setenv("TOOL_FAULT", value)
    assert resilience.injected_fault("search_policy") == expected


def test_injected_error_hits_only_the_named_tool(monkeypatch, seeded):
    monkeypatch.setenv("TOOL_FAULT", "get_claim:error")
    assert claims_tools.get_claim(3)["error"]["type"] == "ToolUnavailable"
    assert claims_tools.check_claim(3)["status"] == "ok"  # other tools unaffected


def test_injected_timeout_on_a_real_tool(monkeypatch, seeded):
    monkeypatch.setenv("TOOL_FAULT", "search_policy:timeout")
    # the timeout is bound at decoration time, so rebuild the tool with the short timeout
    tool = resilient("search_policy", timeout_s=0.05, fallback="fb")(claims_tools.search_policy.__wrapped__)
    result = tool("meal limit")
    assert result["error"]["type"] == "ToolTimeout" and result["error"]["attempts"] == 2


def test_check_claim_returns_the_rules_engine_totals(seeded):
    result = claims_tools.check_claim(3)
    assert result["status"] == "ok"
    assert result["check"]["total_reimbursable_usd"] == "642.90"  # seed: expected_total_usd
    assert result["check"]["violations"][0]["citation"]["doc_id"] == "POL-MEALS"


def test_get_claim_and_missing_claim(seeded):
    assert claims_tools.get_claim(4)["claim"]["trip"]["destination_city"] == "London"
    missing = claims_tools.get_claim(999)
    assert missing["error"]["type"] == "ToolBadInput" and "999" in missing["error"]["message"]
    assert claims_tools.check_claim(0)["error"]["type"] == "ToolBadInput"


def test_search_policy_returns_cited_passages(seeded):
    result = claims_tools.search_policy("daily meal limit")
    assert result["status"] == "ok" and result["passages"][0]["id"] == "POL-MEALS#1"
    assert claims_tools.search_policy("  ")["error"]["type"] == "ToolBadInput"
