"""Spec 004 agent: fault recovery, iteration guard, routing, reflection, model fallback.
The model is a scripted fake BaseLlm; tools run for real on a seeded temp DB (FR-401..FR-411)."""

import asyncio

import pytest
from google.adk.models import LlmRequest
from google.genai import errors

from agent_helpers import FakeLlm, call, say, tool_results
from agentic_app import guardrails
from agentic_app.agents import claims_agent as ca
from agentic_app.tools import claims_tools
from agentic_app.tools.resilience import resilient
TASK = "Check claim 3 for employee E-002: which rules were broken and what will be reimbursed?"


pytestmark = pytest.mark.usefixtures("agent_env")


def run(script, text=TASK):
    fake = FakeLlm(script=script, requests=[])
    events = []
    final = ca.run(ca.build_agent(fake), text, events.append)
    return final, fake, events


GOOD_ANSWER = ("Claim 3: meals on 2026-02-03 were over the daily limit, so 6.00 USD is rejected "
               "[POL-MEALS#1]. Total reimbursable: 642.90 USD.")


def test_root_agent_is_an_adk_agent_with_the_tools():
    names = [getattr(t, "__name__", None) for t in ca.root_agent.tools]
    assert ca.root_agent.name == "claims_agent"
    assert names == ["search_policy", "get_claim", "check_claim", "review_answer"]


def test_multi_step_claim_task_completes():
    final, fake, _ = run([call("get_claim", claim_id=3), call("check_claim", claim_id=3),
                          call("search_policy", query="meal limit"), say(GOOD_ANSWER)])
    assert final == GOOD_ANSWER
    results = tool_results(fake.requests[-1])
    assert [r["status"] for r in results] == ["ok", "ok", "ok"]


def test_timed_out_tool_is_reported_to_the_model_and_the_run_completes(monkeypatch):
    """SC-401: search_policy always times out; the agent gets a ToolTimeout result, follows the
    fallback (cite check_claim's references) and still finishes."""
    monkeypatch.setenv("TOOL_FAULT", "search_policy:timeout")
    fast_search = resilient("search_policy", timeout_s=0.05, fallback=claims_tools.SEARCH_FALLBACK)(
        claims_tools.search_policy.__wrapped__)  # same tool, 0.05 s timeout so the test is quick
    monkeypatch.setattr(ca, "search_policy", fast_search)
    seen = {}

    def answer(request):
        seen["results"] = tool_results(request)
        return say("Policy search was unavailable. " + GOOD_ANSWER.replace("[POL-MEALS#1]", "(POL-MEALS §1)"))

    fake = FakeLlm(script=[call("search_policy", query="meal limit"), call("check_claim", claim_id=3),
                           answer], requests=[])
    final = ca.run(ca.build_agent(fake), TASK)
    timeout = seen["results"][0]
    assert timeout["status"] == "error" and timeout["error"]["type"] == "ToolTimeout"
    assert timeout["error"]["attempts"] == 2 and "check_claim" in timeout["fallback"]
    assert seen["results"][1]["status"] == "ok"
    assert final.startswith("Policy search was unavailable") and "642.90" in final


def test_failed_tool_never_raises_out_of_the_run(monkeypatch):
    monkeypatch.setenv("TOOL_FAULT", "get_claim:error,check_claim:error")
    final, fake, _ = run([call("get_claim", claim_id=3), call("check_claim", claim_id=3),
                          say("Claim 3 could not be loaded or checked; no amounts are available.")])
    assert [r["error"]["type"] for r in tool_results(fake.requests[-1])] == ["ToolUnavailable"] * 2
    assert "could not be" in final


def test_iteration_guard_stops_a_runaway_loop(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_STEPS", "3")
    final, fake, _ = run([call("get_claim", claim_id=3)])  # the fake never stops calling tools
    assert len(fake.requests) == 3  # the 4th model call was replaced by the stop message
    assert final == ca.STOP_MESSAGE.format(n=3)


def test_default_step_limit():
    assert ca.max_steps() == 8


@pytest.mark.parametrize("text,route", [
    (TASK, "claim_task"), ("please check claims 3 and 4", "claim_task"), ("claim #12?", "claim_task"),
    ("What is the daily limit for meals?", "policy_question"),
    ("Can I claim the minibar?", "policy_question")])
def test_router(text, route):
    assert ca.route_of(text) == route


def test_policy_question_is_offered_only_search_policy():
    _, fake, _ = run([call("search_policy", query="meals"),
                      say("Meals are limited to 75.00 USD a day [POL-MEALS#1].")],
                     text="What is the daily limit for meals?")
    offered = [d.name for t in fake.requests[0].config.tools for d in t.function_declarations]
    assert offered == ["search_policy"]
    assert "Route: policy_question" in fake.requests[0].config.system_instruction


def test_claim_task_is_offered_every_tool_and_asked_for_a_plan():
    _, fake, _ = run([say(GOOD_ANSWER)])
    offered = {d.name for t in fake.requests[0].config.tools for d in t.function_declarations}
    assert {"search_policy", "get_claim", "check_claim"} <= offered
    instruction = fake.requests[0].config.system_instruction
    assert "Route: claim_task" in instruction and "numbered plan" in instruction


def test_review_flags_missing_citation_and_invented_amounts():
    tools = '{"total_reimbursable_usd": "642.90", "citation": {"doc_id": "POL-MEALS"}, "id": "POL-MEALS#1"}'
    assert guardrails.grounding_problems(GOOD_ANSWER, tools + ' "6.00"') == []
    problems = guardrails.grounding_problems("You get 700.00 USD.", tools)
    assert len(problems) == 2 and "POL-MEALS" in problems[0] and "700.00" in problems[1]
    assert guardrails.grounding_problems("No policy was available.", "") == []  # nothing to cite, no amounts


def test_reflection_sends_problems_back_and_the_model_revises_once():
    revised = say(GOOD_ANSWER.replace("[POL-MEALS#1]", "(POL-MEALS §1)"))  # no search_policy run
    final, fake, _ = run([call("check_claim", claim_id=3),
                          say("You will get 700.00 USD."),  # invented amount, no citation
                          revised])
    review = tool_results(fake.requests[-1])[-1]
    assert review["status"] == "revise" and any("700.00" in p for p in review["problems"])
    assert final == revised.content.parts[0].text


def test_second_failed_draft_is_returned_with_a_note():
    final, _, _ = run([call("check_claim", claim_id=3), say("You will get 700.00 USD."),
                       say("You will get 700.00 USD.")])
    assert final.startswith("You will get 700.00 USD.") and "automatic review still found" in final


def test_fallback_model_is_tried_after_a_transient_error(monkeypatch):
    calls = []

    async def parent(self, llm_request, stream=False):
        calls.append(llm_request.model)
        if llm_request.model == "primary":
            raise errors.ServerError(503, {"error": {"message": "high demand"}})
        yield say("ok")

    monkeypatch.setattr(ca.Gemini, "generate_content_async", parent)
    model = ca.FallbackGemini(model="primary", fallbacks=["backup"])

    async def collect():
        return [r async for r in model.generate_content_async(LlmRequest(model="primary"))]

    assert _text(asyncio.run(collect())) == "ok" and calls == ["primary", "backup"]


def test_non_transient_model_error_is_raised(monkeypatch):
    async def parent(self, llm_request, stream=False):
        raise errors.ClientError(400, {"error": {"message": "bad request"}})
        yield  # pragma: no cover

    monkeypatch.setattr(ca.Gemini, "generate_content_async", parent)
    model = ca.FallbackGemini(model="primary", fallbacks=["backup"])

    async def collect():
        return [r async for r in model.generate_content_async(LlmRequest(model="primary"))]

    with pytest.raises(errors.ClientError):
        asyncio.run(collect())


def test_default_model_reads_env(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "m1")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "m2, m1 ,m3")
    model = ca.default_model()
    assert model.model == "m1" and model.fallbacks == ["m2", "m1", "m3"]
    assert 503 in model.retry_options.http_status_codes


def _text(responses):
    return "".join(p.text or "" for r in responses for p in r.content.parts)


def test_hung_model_call_times_out_and_falls_back(monkeypatch):
    calls = []

    async def parent(self, llm_request, stream=False):
        calls.append(llm_request.model)
        if llm_request.model == "primary":
            await asyncio.sleep(5)  # hangs past the limit
        yield say("ok")

    monkeypatch.setattr(ca.Gemini, "generate_content_async", parent)
    monkeypatch.setenv("MODEL_TIMEOUT_S", "0.05")
    model = ca.FallbackGemini(model="primary", fallbacks=["backup"])

    async def collect():
        return [r async for r in model.generate_content_async(LlmRequest(model="primary"))]

    assert _text(asyncio.run(collect())) == "ok" and calls == ["primary", "backup"]
