# M09 — Agent fundamentals: `root_agent` (Google ADK)

**Outcome:** an agent that completes a multi-step task and recovers cleanly from a failed or
timed-out tool call. Taken at commit `ea0100d`, gemini-3.5-flash-lite (free tier), 2026-11-25.

| Required | Where |
|---|---|
| The agent | ADK `Agent` `root_agent` in [src/agentic_app/agents/claims_agent.py](../../src/agentic_app/agents/claims_agent.py), spec-first: [specs/004-claims-agent/](../../specs/004-claims-agent/) |
| Tools with failure handling | `search_policy` (M08 hybrid index), `get_claim` (claims store), `check_claim` (M02 rules engine) in [tools/claims_tools.py](../../src/agentic_app/tools/claims_tools.py); timeout, 1 retry and typed error results in [tools/resilience.py](../../src/agentic_app/tools/resilience.py) and [tools/errors.py](../../src/agentic_app/tools/errors.py) |
| Failed tool call → recovery → completed answer | [run-fault-search-timeout.log](run-fault-search-timeout.log) (`TOOL_FAULT=search_policy:timeout`) |
| Iteration guard | [run-iteration-guard.log](run-iteration-guard.log) (`AGENT_MAX_STEPS=2`) |
| Tests | [tests/test_tools.py](../../tests/test_tools.py) (17), [tests/test_claims_agent.py](../../tests/test_claims_agent.py) (19): model faked, tools real on a seeded temp DB; suite **390 passed** offline, coverage 97% |

## How it works

```
request ─► before_model  ROUTER (code): names a claim number? claim_task : policy_question
           │             (policy_question is offered only search_policy)
           │             ITERATION GUARD: call > AGENT_MAX_STEPS (8)? fixed stop message, no model call
           ├─ model      claim_task: numbered PLAN first, then tool calls
           ├─ tools      timeout ─► 1 retry ─► {"status":"error","error":{"type":"ToolTimeout",…},"fallback":…}
           └─ after_model REFLECTION (code): cites a POL- doc a tool returned? every amount in a tool result?
                         no ─► swapped for a review_answer call with the problems; model revises once
```

## Live run 1: a tool killed mid-run ([log](run-fault-search-timeout.log))

"Check claims 3 and 4 for employee E-002 …" with `TOOL_FAULT=search_policy:timeout`:

1. The model writes a 3-step plan, then calls `get_claim` + `check_claim` for both claims (all ok).
2. It calls `search_policy` twice. Each call times out at 10 s, is retried, times out again, and
   returns `ToolTimeout after 2 attempts` with the fallback "use the policy references in
   check_claim results … never cite policy from memory".
3. The agent follows it: it says policy search was unavailable, cites `POL-MEALS §1, §3`,
   `POL-LODGING §1–3`, `POL-PERDIEM §1–2` from the rules engine's violations, and reports
   **642.90** and **344.05 USD**, the rules engine's totals (the M02 seed's expected values).
   The answer passed the reflection check on the first draft. 46 s in all, 40 s of it the timeouts.

## Live run 2: the iteration guard ([log](run-iteration-guard.log))

Three claims with `AGENT_MAX_STEPS=2`: two model calls (6 claim tools, then 2 searches), then the
guard replaces the 3rd model call with "I stopped after 2 steps without finishing … Nothing was
changed." The run ends normally, no exception. Offline, a fake model that never stops calling tools
is stopped the same way (`test_iteration_guard_stops_a_runaway_loop`).

## The three patterns (and why each is built this way)

| Pattern | How | Why |
|---|---|---|
| Routing | Code: a regex for a claim number picks the route; policy questions get only `search_policy` | Deterministic and free. A router sub-agent costs one more model call per request on a rate-limited free tier. M10's router eval measures it |
| Planning | Instruction: a claim task starts with a numbered plan | Light by design. Run 1 planned; run 2 went straight to tools. Not enforced in code; a plan check is a candidate for M10 trajectory evals |
| Reflection | Code check + one model revision (FR-409) | The check is M07's "no invented amounts" plus "cite a policy doc a tool returned". The model only rewrites; it never judges itself. Tested offline (`test_reflection_sends_problems_back_and_the_model_revises_once`); not triggered live |

## Decisions to defend

- **Retries belong to the tool, recovery to the agent.** One retry handles a blip; after that the
  model gets a typed error with a per-tool fallback and decides how to finish. Bad input
  (`claim 999 not found`) is not retried. Any unexpected exception becomes `ToolUnavailable`, so no
  tool failure can end the run.
- **Money (Principle III):** amounts come only from `check_claim`. The instruction forbids
  computing them, and the reflection check rejects any amount not found in a tool result.
- **Model availability:** ADK `HttpRetryOptions` (3 attempts on 429/500/503/504), then
  `FallbackGemini` tries `GEMINI_FALLBACK_MODELS` in order, the same policy as `llm.py`. Not needed in
  these runs: flash-lite answered every call.
- **Dependency change:** google-adk 2.15.1 requires `google-genai<3`, so genai went from 3.6.1 to
  2.34. All 354 earlier tests pass unchanged.
- **Timeout by worker thread:** a timed-out worker is abandoned, not killed. That is acceptable for
  read-only tools; a tool that writes (M11 `draft_claim`) will need an idempotency key.

## Reviewer probe: "Kill a tool mid-run. Show the recovery and the maximum-iteration guard."

`TOOL_FAULT=search_policy:timeout` kills policy search for the whole run. Run 1 shows each timeout,
the retry, the typed error the model received, and a completed answer with correct totals and
citations taken from the rules engine. `AGENT_MAX_STEPS=2` shows the guard stopping a run that
needed more steps, with a clear message and no crash.

## Reproduce

```bash
uv run pytest -q tests/test_tools.py tests/test_claims_agent.py   # offline, no key
TOOL_FAULT=search_policy:timeout uv run python scripts/run_agent.py "Check claims 3 and 4 for employee E-002: which policy rules did each break, what will be reimbursed, and what does the policy say about it?"
AGENT_MAX_STEPS=2 uv run python scripts/run_agent.py "Check claims 3, 4 and 5 for employee E-002: which policy rules did each break, what will be reimbursed, and what does the policy say about each rule?"
```

Live runs need `GOOGLE_API_KEY`, `GEMINI_MODEL` and a seeded `data/claims.db`
(`uv run python -m agentic_app.claims.seed --db data/claims.db`).
