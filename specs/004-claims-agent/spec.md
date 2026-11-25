# Feature Specification: Claims agent

**Feature Branch**: `004-claims-agent` | **Created**: 2026-11-25 | **Status**: Implemented (M09)

**Input**: An employee asks the copilot, in their own words, either a policy question or a task about
their stored claims ("check claims 3 and 4 and tell me what I'll be reimbursed and why"). An agent
plans the steps, calls tools, and answers with policy citations. When a tool fails or times out, the
run does not crash: the agent is told what failed and finishes as well as it honestly can.

## User story (P1): a multi-step claim task that survives a failed tool

**Independent test**: with the model faked, a claim task whose `search_policy` tool always times
out still ends with a final answer built from the other tools; a model that never stops calling
tools is stopped by the iteration guard. Live: the same two cases with `TOOL_FAULT` set.

### Acceptance scenarios

1. "Check claims 3 and 4 for employee E-002: which rules did they break, what will be reimbursed,
   and what does the policy say?" → a short plan, then `get_claim` / `check_claim` for each claim
   and `search_policy`; the answer gives the totals from `check_claim` and cites policy sections.
2. Same request with `TOOL_FAULT=search_policy:timeout` → `search_policy` times out, is retried once,
   returns a `ToolTimeout` result; the agent continues and answers using the policy references
   `check_claim` returned, and says policy search was unavailable.
3. "What is the daily limit for meals?" → routed as a policy question: only `search_policy` is
   offered; the answer cites `POL-MEALS`.
4. A run that would need more steps than the limit stops with a fixed message, not an exception.

## Requirements

- **FR-401** Agent: an ADK `Agent` named `root_agent` in `src/agentic_app/agents/claims_agent.py`,
  Gemini model, tools `search_policy(query)`, `get_claim(claim_id)`, `check_claim(claim_id)`.
- **FR-402** Tools reuse existing code: hybrid policy search (spec 003), the claims store and the
  rules engine (spec 001). Every tool returns a dict with `status: "ok"` and its data, or
  `status: "error"` and a typed error.
- **FR-403** Resilience: each tool call has a timeout and at most one retry (after a short backoff)
  on timeout or unavailability; bad input is not retried. After that the tool returns a typed error
  result (`ToolTimeout`, `ToolUnavailable`, `ToolBadInput`, from `tools/errors.py`) with a message and
  the fallback the agent should follow. No tool failure raises out of the agent run.
- **FR-404** Fallback per tool, given to the model in the error result:
  `search_policy` → use the policy references in `check_claim` results, otherwise say policy search
  is unavailable (never cite from memory); `get_claim` / `check_claim` → say which claim could not
  be loaded or checked, and give no amounts for it.
- **FR-405** Fault injection: `TOOL_FAULT=<tool>:<timeout|error>[,…]` makes that tool time out or
  fail on every attempt.
- **FR-406** Iteration guard: at most `AGENT_MAX_STEPS` (default 8) model calls per user request;
  the next one is replaced by a fixed message saying the run was stopped at the limit.
- **FR-407** Routing (code): a request that names a claim number is a claim task (all tools); anything
  else is a policy question and is offered only `search_policy`.
- **FR-408** Planning: for a claim task the agent first writes a numbered plan, then executes it.
- **FR-409** Reflection (code check): a final answer must cite at least one policy reference returned
  by a tool (when any tool returned one), and every money amount in it must appear in a tool result.
  On failure the agent is sent the problems and revises once; a second failure is returned with a
  note listing the problems.
- **FR-410** Money (Principle III): the model never computes an amount; totals come only from
  `check_claim`. FR-409 enforces it.
- **FR-411** Model availability: transient model errors are retried (ADK HTTP retry options) and
  then the next model in `GEMINI_FALLBACK_MODELS` is tried.

## Out of scope

Creating or changing claims (`draft_claim`), FX and per-diem tools, sessions that outlive a run,
memory, human approval, `adk web` deployment, evals (M10).

## Success criteria

- **SC-401** Offline: the fault, recovery and guard scenarios pass with a faked model and no key.
- **SC-402** Live: scenario 2 completes with the timeout visible in the run log; scenario 4 stops at
  the limit.
