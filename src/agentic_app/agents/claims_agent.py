"""The claims agent (spec 004): ADK `root_agent` with resilient tools and three light patterns.

    user request
      └─ before_model  INPUT GUARD (spec 005): injection / off-topic -> fixed message, no model call
      │                ROUTER (code): names a claim number? claim task : policy question
      │                (a policy question is offered only search_policy)
      │                ITERATION GUARD: more than AGENT_MAX_STEPS model calls -> fixed stop message
      ├─ model         claim task: writes a numbered PLAN first, then calls tools
      ├─ before_tool   ACTION GUARD (spec 005): only read-only tools; nothing can approve a claim
      ├─ tools         search_policy / get_claim / check_claim: timeout, 1 retry, typed error result
      ├─ after_tool    records tool output for the reflection check
      └─ after_model   REFLECTION (code): final answer must cite a policy doc a tool returned and use
                       only amounts found in tool output; else one revision via review_answer

The model never computes an amount (Principle III): totals come from check_claim, and the
reflection check rejects any amount that no tool returned.
"""

import asyncio
import json
import logging
import os
import re
import uuid
from collections.abc import AsyncGenerator

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import Gemini, LlmRequest, LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import errors, types

from agentic_app import guardrails
from agentic_app.llm import TRANSIENT_CODES  # also loads .env, like the rest of the app
from agentic_app.tracing import event as trace_event
from agentic_app.tools.claims_tools import check_claim, get_claim, search_policy

log = logging.getLogger(__name__)

APP_NAME = "claims_agent"
DEFAULT_MAX_STEPS = 8
STATE = "temp:claims_agent"  # per-invocation bookkeeping (route, steps, tool output, revised)

NOT_IN_POLICY = "NOT_IN_POLICY"
# The same code-written refusal as POST /ask (spec 003 FR-304); never the model's own wording.
REFUSAL = ("I can't answer that from the travel and expense policy. "
           "Please ask your manager or the finance team.")
# Gemini 3 requires a thought signature on every function call in the history; a call the system
# injects itself (review_answer) has none, so it carries Gemini's documented placeholder.
INJECTED_CALL_SIGNATURE = b"skip_thought_signature_validator"

STOP_MESSAGE = ("I stopped after {n} steps without finishing (the step limit for one request). "
                "Nothing was changed. Please ask about fewer claims at a time, or try again.")

INSTRUCTION = """You are the expense and travel policy copilot for employees.

Route: {route}

For a policy question: call search_policy, then answer in 1-4 sentences using only the passages,
citing passage IDs in brackets, e.g. [POL-MEALS#1]. If the passages do not answer the question,
reply with exactly NOT_IN_POLICY and nothing else.

For a claim task:
1. First write a short numbered plan (one line per step: which tool, for which claim).
2. Then carry it out: get_claim and check_claim for every claim named, and search_policy for the
   rules involved.
3. Answer per claim: the violations, the total reimbursable in USD, and the policy behind it, cited
   as [POL-XXX#n] or POL-XXX §n.

Rules:
- Never compute, add up or estimate an amount. Repeat amounts exactly as check_claim returned them.
- Never cite policy from memory; cite only references returned by a tool.
- A tool result with "status": "error" is not fatal: follow its "fallback" and finish the rest of
  the task. Tell the user briefly which step failed.
- If review_answer returns problems, rewrite your answer once to fix them."""

_CLAIM_NUMBER = re.compile(r"\bclaims?\s*(?:#|no\.?|number)?\s*\d+", re.IGNORECASE)


def model_timeout_s() -> float:
    return float(os.getenv("MODEL_TIMEOUT_S", "60"))


def max_steps() -> int:
    return int(os.getenv("AGENT_MAX_STEPS", DEFAULT_MAX_STEPS))


def route_of(text: str) -> str:
    """FR-407: a request naming a claim number is a claim task; anything else a policy question."""
    return "claim_task" if _CLAIM_NUMBER.search(text) else "policy_question"


def review_answer(problems: list[str]) -> dict:
    """Internal review step added by the system after a draft answer fails its check. Do not call it
    yourself.

    Args:
        problems: What the draft answer got wrong.
    """
    return {"status": "revise", "problems": problems,
            "instruction": "Rewrite your answer once, fixing these problems."}


# --- callbacks -------------------------------------------------------------------------------------

def _run_state(ctx: CallbackContext) -> dict:
    """Bookkeeping for this invocation (reset when a new user request starts)."""
    state = ctx.state.get(STATE)
    if not state or state.get("invocation") != ctx.invocation_id:
        text = "".join(p.text or "" for p in (ctx.user_content.parts if ctx.user_content else []))
        state = {"invocation": ctx.invocation_id, "route": route_of(text), "steps": 0,
                 "tool_output": "", "revised": False, "fixed_reply": False}
    return state


def _text(response: LlmResponse) -> str:
    parts = response.content.parts if response.content and response.content.parts else []
    return "".join(p.text or "" for p in parts if not p.thought)


def _has_call(response: LlmResponse) -> bool:
    parts = response.content.parts if response.content and response.content.parts else []
    return any(p.function_call for p in parts)


def before_model(callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
    state = _run_state(callback_context)
    state["steps"] += 1
    callback_context.state[STATE] = state
    if state["steps"] == 1:  # spec 005 FR-506: the request is screened before any model call
        text = "".join(p.text or "" for p in (callback_context.user_content.parts
                                               if callback_context.user_content else []))
        blocked = guardrails.screen_input(text)
        if blocked:
            reason, message = blocked
            log.warning("input guard: blocked (%s)", reason)
            trace_event("guardrail.input.blocked", reason=reason)
            state["fixed_reply"] = True
            callback_context.state[STATE] = state
            return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=message)]))
    if state["steps"] > max_steps():  # FR-406: stop the loop instead of calling the model again
        log.warning("iteration guard: stopping after %d model calls", max_steps())
        trace_event("guardrail.iteration.stopped", max_steps=max_steps())
        state["fixed_reply"] = True
        callback_context.state[STATE] = state
        return LlmResponse(content=types.Content(role="model", parts=[
            types.Part(text=STOP_MESSAGE.format(n=max_steps()))]))
    if state["route"] == "policy_question":  # FR-407: only the policy tool is offered
        for tool in llm_request.config.tools or []:
            if tool.function_declarations:
                tool.function_declarations = [d for d in tool.function_declarations
                                              if d.name == "search_policy"]
        llm_request.tools_dict = {k: v for k, v in llm_request.tools_dict.items()
                                  if k == "search_policy"}
    return None


def after_tool(tool, args: dict, tool_context, tool_response: dict) -> dict | None:
    state = _run_state(tool_context)
    state["tool_output"] += json.dumps(tool_response, ensure_ascii=False, default=str) + "\n"
    tool_context.state[STATE] = state
    return None


def after_model(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
    parts = llm_response.content.parts if llm_response.content and llm_response.content.parts else []
    trace_event("model.output", text=_text(llm_response)[:4000], calls=json.dumps(
        [{"name": p.function_call.name, "args": p.function_call.args} for p in parts if p.function_call]))
    if llm_response.partial or _has_call(llm_response):
        return None
    answer = _text(llm_response)
    state = _run_state(callback_context)
    if not answer or state["fixed_reply"]:
        return None
    if answer.strip().startswith(NOT_IN_POLICY):  # spec 005: a refusal needs no citation
        trace_event("guardrail.output.refusal")
        state["fixed_reply"] = True
        callback_context.state[STATE] = state
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=REFUSAL)]))
    problems = guardrails.grounding_problems(answer, state["tool_output"])
    if not problems:
        return None
    if not state["revised"]:  # FR-409: send the problems back; the model answers once more
        state["revised"] = True
        callback_context.state[STATE] = state
        log.info("reflection: draft failed review: %s", problems)
        trace_event("guardrail.output.revise", problems=" | ".join(problems))
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(
            function_call=types.FunctionCall(id=f"review-{uuid.uuid4().hex[:8]}",
                                             name="review_answer", args={"problems": problems}),
            thought_signature=INJECTED_CALL_SIGNATURE)]))
    trace_event("guardrail.output.unresolved", problems=" | ".join(problems))
    note = "\n\nNote: automatic review still found problems: " + " ".join(problems)
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=answer + note)]))


# --- model with fallbacks (FR-411) -------------------------------------------------------------------

class FallbackGemini(Gemini):
    """Gemini with ADK's HTTP retries on one model, then the next model in `fallbacks`."""

    fallbacks: list[str] = []

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        names = [self.model] + [m for m in self.fallbacks if m != self.model]
        for i, name in enumerate(names):
            llm_request.model = name
            try:
                # Hard limit per model (ADK's client has no request timeout; a hung call once
                # stalled a live eval run for 20 minutes). Responses are collected inside the limit.
                async with asyncio.timeout(model_timeout_s()):
                    responses = [r async for r in Gemini.generate_content_async(self, llm_request, stream)]
            except (errors.APIError, TimeoutError) as exc:
                transient = isinstance(exc, TimeoutError) or exc.code in TRANSIENT_CODES
                if not transient or i == len(names) - 1:
                    raise
                reason = "timeout" if isinstance(exc, TimeoutError) else f"HTTP {exc.code}"
                log.warning("model %s unavailable (%s); trying %s", name, reason, names[i + 1])
                continue
            for response in responses:
                yield response
            return


def default_model() -> FallbackGemini:
    return FallbackGemini(
        model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        fallbacks=[m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()],
        retry_options=types.HttpRetryOptions(attempts=3, initial_delay=2, max_delay=10,
                                             http_status_codes=list(TRANSIENT_CODES)),
    )


def _instruction(ctx) -> str:
    """Built by ADK before before_model runs, so the route is computed from the request here too."""
    text = "".join(p.text or "" for p in (ctx.user_content.parts if ctx.user_content else []))
    return INSTRUCTION.replace("{route}", route_of(text))


def build_agent(model=None) -> Agent:
    return Agent(
        name=APP_NAME,
        model=model or default_model(),
        description="Answers policy questions and checks stored expense claims, citing policy.",
        instruction=_instruction,
        tools=[search_policy, get_claim, check_claim, review_answer],
        before_model_callback=before_model,
        after_model_callback=after_model,
        before_tool_callback=guardrails.before_tool,
        after_tool_callback=after_tool,
    )


root_agent = build_agent()


# --- running (tests and scripts/run_agent.py) -----------------------------------------------------

async def run_async(agent: Agent, text: str, on_event=None) -> str:
    """Run one request in a fresh in-memory session; returns the final text."""
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id="employee")
    final = ""
    message = types.Content(role="user", parts=[types.Part(text=text)])
    async for event in runner.run_async(user_id="employee", session_id=session.id,
                                        new_message=message):
        if on_event:
            on_event(event)
        if event.is_final_response() and event.content and event.content.parts:
            final = "".join(p.text or "" for p in event.content.parts if not p.thought) or final
    return final


def run(agent: Agent, text: str, on_event=None) -> str:
    return asyncio.run(run_async(agent, text, on_event))
