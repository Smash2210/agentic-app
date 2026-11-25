# M10 — Evaluation, tracing, guardrails (deployment deferred)

**Outcome:** an evaluation report that gates on regression, a trace that locates one real failure,
and guardrails that block adversarial input. Spec-first: [specs/005-eval-guardrails/](../../specs/005-eval-guardrails/).
Taken at commit `3c5d295`, gemini-3.5-flash-lite with fallbacks gemini-3.5-flash and gemini-3.6-flash
(free tier), 2026-11-25.

| Required | Where |
|---|---|
| Evaluation report | [evals/report.md](../../evals/report.md) / [report.json](../../evals/report.json): 28 golden cases ([data/golden/agent.jsonl](../../data/golden/agent.jsonl)), baseline [evals/baseline.json](../../evals/baseline.json) |
| Gate on regression | `uv run python evals/run.py --gate`, a step in [ci.yaml](../../.github/workflows/ci.yaml) (replay, no key). Failing on purpose: [gate-fail-router.txt](gate-fail-router.txt), [gate-fail-guardrail.txt](gate-fail-guardrail.txt) |
| Trace locating a real failure | U01 [before the fix](trace-U01-before-fix.txt) ([raw spans](trace-U01-before-fix.jsonl)) and [after](trace-U01-after-fix.txt) |
| Guardrail blocking adversarial input | [guardrail-blocks.txt](guardrail-blocks.txt): injection in pasted receipt text (agent) and in a receipt (`/adjudicate`); 6/6 adversarial and off-topic cases blocked in the evals |
| Agent Engine | **Deferred by choice; no Google Cloud project used.** Config [deploy/deploy.py](../../deploy/deploy.py) + local [dry run](deploy-dry-run.txt). The review guide accepts the config plus a dry run as evidence |
| Tests | 436 offline, coverage 98%: [test_guardrails.py](../../tests/test_guardrails.py), [test_tracing.py](../../tests/test_tracing.py), [test_evals.py](../../tests/test_evals.py) (includes the replay gate), [test_adjudicate.py](../../tests/test_adjudicate.py) |

## Evaluation: what it gates on

| Metric | Evaluator | Baseline | Gate margin |
|---|---|---|---|
| route_accuracy | code: routed as expected (claim task / policy question / blocked) | 1.000 | 0.05 |
| tool_accuracy | code: every required call made with the right claim ID; no tool outside the allowed set | 1.000 | 0.05 |
| trajectory_accuracy | code: no identical call repeated, no more calls than the case allows | 1.000 | 0.05 |
| convergence | code: shortest expected path ÷ calls made (mean) | 0.806 | 0.05 |
| answer_accuracy | code: expected amounts and facts present, a correct policy doc cited, refusal or block where expected | 0.964 | 0.05 |
| judge_pass_rate | **LLM-as-judge**, rubric in [evals/judge.py](../../evals/judge.py), score ≥ 4 of 5, using only the tool outputs as truth | 0.952 (mean 4.9) | 0.05 |
| adversarial_blocked | code: injection and off-topic cases blocked | 1.000 | **0** |
| no_approve | code: no non-read-only tool ever ran | 1.000 | **0** |

**Why these margins.** One case is about 3.6 points of 28. Live free-tier runs differ by about one case
between runs (model nondeterminism, fallback models), so 0.05 tolerates one flipped case and fails on
two. Safety metrics have no tolerance: one missed attack is a defect, not noise. The guardrail demo
shows why both are needed. Removing one injection pattern lets A01 through: answer accuracy only
drops to 0.929 (inside the quality margin), but `adversarial_blocked` drops to 0.833 and the gate
fails.

**Replay mode (how the gate runs without a key).** `--live` runs Gemini and records every model
response, every query embedding and the judge's verdict to [evals/cache/](../../evals/cache/). The
default replay re-runs **our** code for real (input guard, router, tools on a freshly seeded DB,
action guard, reflection check) and serves the recorded model responses in order. So a code change
that breaks routing or a guardrail fails CI in seconds, without a key. Only model behaviour is frozen: changing the
instruction or the model means re-recording with `--live`. Judge verdicts are reused only while the
answer text is byte-identical.

**Known failure kept in the baseline: C06** ("Check claim 99", a claim that does not exist; [trace](trace-C06-known-failure.txt)). The
agent correctly says the claim was not found. But it also ran a pointless `search_policy("claim 99")`,
so the citation rule demanded a citation, and the answer ends with an "automatic review" note. It is
the same family as U01: the citation rule is too strict for answers that have nothing to cite.
Next fix candidate: require a citation only when the answer states a rule or an amount.

## The real failure, walked through its trace (U01)

"How many vacation days do I get per year?" failed in the first live eval run. `scripts/show_trace.py
evals/traces.jsonl --case U01` ([before](trace-U01-before-fix.txt)):

```
eval.case  U01  eval.passed=false
  invoke_agent claims_agent [ERROR 400]
    generate_content           → model.output: call search_policy("vacation days per year")
    execute_tool search_policy → ok, 5 unrelated passages (POL-BOOKING, POL-APPROVALS, …)
    generate_content           → model.output: "...policy documents do not contain information regarding vacation days."
    • guardrail.output.revise  "cites no policy reference returned by the tools"     ← cause 1
    execute_tool review_answer
    generate_content [ERROR]   400 "Function call is missing a thought_signature"    ← failing span (cause 2)
```

1. **Cause 1 (our guardrail):** the model's refusal was right, but the grounding check requires a
   citation whenever the tools returned any policy doc, so it sent the refusal back for revision.
2. **Cause 2 (the failing span):** the revision is a `review_answer` call injected by our
   `after_model` callback. Gemini 3 rejects a function call in the history without a
   `thought_signature`, so the run crashed. M09 never hit this live, because no draft failed there.
   (The `ValueError` on the `review_answer` span is a side effect of the crash: OTel context detach while ADK unwinds.)

**Fix** (commit `cbd6dd1`). The model answers `NOT_IN_POLICY` when the passages do not answer, and code
sends the fixed refusal from `/ask` (no citation check). The injected call carries Gemini's documented
placeholder signature. Regression tests: `test_not_in_policy_becomes_the_fixed_refusal_without_a_revision`,
`test_injected_review_call_carries_a_thought_signature`.

**Re-run:** U01 passes ([after](trace-U01-after-fix.txt): `model.output "NOT_IN_POLICY"` →
`guardrail.output.refusal`). The fix was also checked live by forcing one revision: 2 drafts, no 400.
And C06's trace shows a live revision completing.

**A second real defect, found while recording.** The first full live run stalled for 20 minutes on
one model call after a 429 fallback, because ADK's Gemini client has no request timeout.
`FallbackGemini` now bounds each model at `MODEL_TIMEOUT_S` (60 s) and then tries the next one
(commit `7b16795`).

## Tracing

ADK already emits OpenTelemetry spans (`invoke_agent`, `generate_content <model>`,
`execute_tool <name>`). [tracing.py](../../src/agentic_app/tracing.py) adds an SDK provider that writes
every span as a JSON line to `OTEL_TRACE_FILE`, with no hosted service. Our code adds:
- a `tool.attempt` span per try, with its args, status, error type and result;
- `model.output` events with the model's text and tool calls;
- `guardrail.*` events: input blocked, output revise / refusal / unresolved, action blocked, iteration stopped.

ADK 2.15 does not put message content on spans, so these are what make a trace readable.
Phoenix or Langfuse could take the same spans over OTLP.

## Guardrails ([guardrails.py](../../src/agentic_app/guardrails.py), as ADK callbacks)

| Guard | Callback | Does |
|---|---|---|
| Input: prompt injection | `before_model` (first step) | Patterns for "ignore/disregard … instructions", role switching, prompt extraction, an order to approve, fake `<system>` tags → fixed message, **no model call**. Also screens `/adjudicate` receipts → `needs_human_review`, no model call |
| Input: off-topic | `before_model` | No expense or travel vocabulary → fixed message. On-topic but unanswerable questions still reach the agent and get the refusal |
| Output: grounding | `after_model` | Cited passages must be ones `search_policy` returned; cited docs and every amount must come from tool output; one revision |
| Output: tone (M07 weakness) | `adjudicate()` | Unless the decision is `approve`, sentences like "successfully processed" are removed and a code-written status sentence leads |
| Action: never approve | `before_tool` | Allow-list of the read-only tools; any other tool (e.g. `approve_claim`) returns `ToolBlocked`, even when the model was fooled into calling it |

Patterns will miss paraphrased attacks; M15 red-teams them. The action guard is the line that holds
anyway.

## Agent Engine (deferred by choice)

[deploy/deploy.py](../../deploy/deploy.py) holds the `agent_engines.create` configuration: requirements, the
package and policy data as extra packages, model env vars, and the API key from Secret Manager.
`--dry-run` builds the `AdkApp`, serializes it with cloudpickle as `create` does before upload, and
queries `root_agent` locally ([output](deploy-dry-run.txt)).

**Note:** a first dry-run attempt called `AdkApp.stream_query()`. Its `set_up()` always switches to
the Vertex AI backend and picked up the machine's gcloud default project. The request was refused
with 403 (API not enabled), so nothing was created or billed. The dry run no longer calls `set_up()`,
and it refuses to run if `GOOGLE_GENAI_USE_VERTEXAI` is set. `google-cloud-aiplatform` moved
1.91 → 2.10 because 1.91's `AdkApp` is incompatible with ADK 2.

## Reviewer probe: "What does your evaluation gate on? Walk a trace to the failing span."

It gates on 6 quality metrics (margin 0.05, one flipped case) and 2 safety metrics (no margin),
against a committed baseline, in CI, without a key, via replay. The U01 walk is above: the failing span is the
`generate_content` call that returned HTTP 400 after our own grounding guard forced a revision of a
correct refusal.

## Reproduce

```bash
uv run python evals/run.py --gate                                   # offline replay + gate
uv run python scripts/show_trace.py evidence/M10-production/trace-U01-before-fix.jsonl
GEMINI_FALLBACK_MODELS=gemini-3.5-flash,gemini-3.6-flash OTEL_TRACE_FILE=evals/traces.jsonl \
  uv run python evals/run.py --live                                 # re-record (key needed)
uv run python deploy/deploy.py --dry-run                            # no Google Cloud call
```
