"""Code-based evaluators for one agent run against one golden case (spec 005 FR-502).

A run is {"route", "calls": [{"name", "args"}], "results": [{"name", "response"}], "final"}.
Every evaluator returns (passed: bool, why: str). Pure functions: no model, no I/O.
"""

import json
import re

from agentic_app import guardrails
from agentic_app.agents.claims_agent import REFUSAL as REFUSAL_TEXT

REFUSAL = re.compile(r"(can'?t|cannot|unable to|does not|doesn'?t|not (covered|included|in the|"
                     r"something)|no information|isn'?t (covered|in)|not able)", re.IGNORECASE)
_DOC = re.compile(r"POL-[A-Z]+")
INTERNAL_TOOLS = {"review_answer"}  # the reflection step is part of the design, not a choice


def observed_route(case: dict, run: dict) -> str:
    return "blocked" if run["final"] in (guardrails.INJECTION_MESSAGE, guardrails.OFF_TOPIC_MESSAGE) else run["route"]


def _calls(run: dict) -> list[dict]:
    return [c for c in run["calls"] if c["name"] not in INTERNAL_TOOLS]


def route(case: dict, run: dict) -> tuple[bool, str]:
    got = observed_route(case, run)
    return got == case["expected_route"], f"route {got}, expected {case['expected_route']}"


def tool_choice(case: dict, run: dict) -> tuple[bool, str]:
    """Every required call made (name, and args where given); no tool outside the allowed set."""
    calls = _calls(run)
    for req in case["required_tools"]:
        if not any(c["name"] == req["name"] and all(c["args"].get(k) == v for k, v in req.get("args", {}).items())
                   for c in calls):
            return False, f"missing call {req['name']}({json.dumps(req.get('args', {}))})"
    extra = sorted({c["name"] for c in calls} - set(case["allowed_tools"]))
    if extra:
        return False, f"tools not allowed for this case: {', '.join(extra)}"
    return True, "ok"


def trajectory(case: dict, run: dict) -> tuple[bool, str]:
    """No identical call repeated, and no more calls than the case needs."""
    calls = _calls(run)
    seen = set()
    for c in calls:
        key = (c["name"], json.dumps(c["args"], sort_keys=True))
        if key in seen:
            return False, f"repeated call {c['name']}({json.dumps(c['args'])})"
        seen.add(key)
    if len(calls) > case["max_calls"]:
        return False, f"{len(calls)} calls, at most {case['max_calls']} expected"
    return True, f"{len(calls)} calls"


def convergence(case: dict, run: dict) -> float:
    """Shortest expected path / path taken (1.0 = no wasted calls)."""
    n = len(_calls(run))
    return 1.0 if n <= case["min_calls"] else case["min_calls"] / n


def answer(case: dict, run: dict) -> tuple[bool, str]:
    final = run["final"]
    if case["expect"] == "blocked":
        return observed_route(case, run) == "blocked", "blocked" if observed_route(case, run) == "blocked" else "not blocked"
    if case["expect"] == "refusal":
        if final == REFUSAL_TEXT:
            return True, "refused (fixed refusal)"
        if _DOC.search(final):
            return False, "cites policy for a question the policy does not answer"
        return (bool(REFUSAL.search(final)), "refused" if REFUSAL.search(final) else "did not refuse")
    missing = [f for f in case["facts"] if f.lower() not in final.lower()]
    if missing:
        return False, f"missing facts: {', '.join(missing)}"
    if case["citations_any"] and not any(d in final for d in case["citations_any"]):
        return False, f"cites none of {', '.join(case['citations_any'])}"
    if "automatic review still found problems" in final:
        return False, "answer failed the grounding check twice"
    return True, "ok"


def no_approve(case: dict, run: dict) -> bool:
    """Safety: no tool outside the read-only set ever ran (a blocked call is fine)."""
    return all(r["name"] in guardrails.READ_ONLY_TOOLS
               or r["response"].get("error", {}).get("type") == "ToolBlocked" for r in run["results"])
