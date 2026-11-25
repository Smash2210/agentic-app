# Implementation Plan: Claims agent

**Spec**: [spec.md](spec.md) | **Branch**: `004-claims-agent`

## Modules

| Module | Does |
|---|---|
| `tools/errors.py` | `ToolError` base and `ToolTimeout`, `ToolUnavailable`, `ToolBadInput`; `.result(hint)` turns one into the dict the model sees |
| `tools/resilience.py` | `resilient(name, timeout_s, hint)` decorator: runs the tool in a worker thread with a timeout, one retry after `BACKOFF_S` for timeout/unavailable, `TOOL_FAULT` injection, any other exception → `ToolUnavailable`; returns a typed error result instead of raising |
| `tools/claims_tools.py` | `search_policy` (spec 003 `PolicyIndex`, question embedded live), `get_claim`, `check_claim` (store + `rules.check_claim`); DB from `CLAIMS_DB_PATH` (default `data/claims.db`) |
| `agents/claims_agent.py` | `build_agent(model)` and `root_agent`; callbacks: `before_model` = router + iteration guard, `after_model` = reflection check, `after_tool` = records tool output for the check; `FallbackGemini` model; `run(agent, text)` helper used by tests and the live script |
| `scripts/run_agent.py` | Live run that prints every event (tool calls, results, text) as a run log |

## Decisions

- **One agent, routing in code.** A regex for a claim number decides the route and trims the tool list
  for policy questions. A router sub-agent would cost one more model call per request on a
  rate-limited free tier, and a regex is deterministic and testable; M10's router eval measures it.
- **Recovery is the agent's, retries are the tool's.** The wrapper retries once (transient faults
  often clear) and then hands the model a typed error with the fallback to follow (FR-404). The
  model decides how to finish; it is never given an exception that ends the run.
- **Timeout by worker thread.** Tools are sync (SQLite, the embedding HTTP call); a
  `ThreadPoolExecutor` future with a timeout works for any of them. A timed-out worker is abandoned,
  not killed; acceptable for read-only tools.
- **Reflection is a code check, revision by the model.** The check (citation present, amounts found in
  tool output) reuses M07's "no invented amounts" idea. To get one revision inside ADK's loop, the
  `after_model` callback swaps a failing final answer for a call to a `review_answer` tool whose
  result lists the problems; the model then answers again.
- **Iteration guard as `before_model_callback`.** Returning an `LlmResponse` skips the model call and
  ends the run with that text, so the stop is clean. Counted per invocation.
- **Model fallback.** ADK's `Gemini(retry_options=HttpRetryOptions(...))` retries 429/5xx on one
  model; `FallbackGemini` then tries `GEMINI_FALLBACK_MODELS` in order, the same policy as `llm.py`.
- **Dependency: `google-adk`** (ADR 0001). Its current release (2.15.1) needs `google-genai<3`, so
  `google-genai` moves from `>=3.6.1` to `>=2.34,<3`; the whole suite passes on 2.34 unchanged.

## Constitution check

| Principle | How |
|---|---|
| I Spec-first | This spec and plan before code |
| II Policy source of truth | Answers must cite references returned by tools (FR-409); never from memory (FR-404) |
| III Deterministic core | Amounts come only from `check_claim`; the reflection check rejects any amount not in a tool result |
| IV Money | Unchanged; rules engine and `Decimal` |
| V Test-first, offline | Model faked with a scripted `BaseLlm`; embeddings faked; temp SQLite DB |
| VI Simplicity | One agent, three tools, no new runtime dependency besides ADK |
