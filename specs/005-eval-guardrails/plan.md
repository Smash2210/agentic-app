# Implementation Plan: Evaluation gate, tracing and guardrails

**Spec**: [spec.md](spec.md) | **Branch**: `005-eval-guardrails`

## Modules

| Module | Does |
|---|---|
| `src/agentic_app/guardrails.py` | `screen_input` (injection patterns, on-topic vocabulary), `grounding_problems` (moved from spec 004's `review`, plus passage IDs), `before_tool` action guard, `explanation_for_decision` (FR-509) |
| `src/agentic_app/tracing.py` | `setup_tracing(path)`: SDK `TracerProvider` + a JSON-lines file exporter; `tracer` used by the tool wrapper and guardrails |
| `agents/claims_agent.py` | wires the guardrails into the existing callbacks |
| `tools/resilience.py` | one span per attempt (`tool.attempt`), with error type |
| `adjudicate.py` | receipt screening and the explanation fix |
| `evals/` | `run.py` (live / replay, report, gate), `evaluators.py`, `judge.py`, `cache/`, `baseline.json` |
| `scripts/show_trace.py` | prints one trace from the JSON-lines file as an indented span tree |
| `deploy/deploy.py` | Agent Engine config; `--dry-run` runs `AdkApp` locally |

## Decisions

- **Replay, not a cached report.** Replay re-runs the agent with the recorded model responses served in
  order, so a change to routing, guardrails, tools or the reflection check shows up offline. Only model
  behaviour is frozen; a change to the instruction needs a new `--live` recording.
- **Margin 0.05 for quality, 0 for safety.** With ~25 cases one case is 4 points. Live runs on the free
  tier vary by about one case (model nondeterminism, fallback models), so 0.05 tolerates one flipped
  case and fails on two. Safety metrics (blocked adversarial inputs, no approve call) have no
  tolerance: one miss is a real defect. Replay is deterministic, so any drop there is a code change.
- **Guardrails in code, not a classifier.** Regex patterns and a topic vocabulary are deterministic,
  free and testable; they will miss paraphrased attacks (M15 red-teams them). The action guard is the
  hard line: even a fooled model cannot run an approving tool.
- **Groundedness = citation and amount check, not NLI.** Every cited passage must be one the tools
  returned, and every amount must appear in tool output. Semantic faithfulness is scored by the LLM
  judge in the evals, not at runtime (one more model call per answer on the free tier).
- **Tracing to a file.** ADK already emits OpenTelemetry spans (`invoke_agent`, `generate_content`,
  `execute_tool`); we add a provider and a file exporter, no hosted service. Phoenix or Langfuse
  could read the same spans over OTLP later.
- **Dependencies.** `opentelemetry-sdk` already comes with `google-adk`. `google-cloud-aiplatform`
  was transitive at 1.91, whose `AdkApp` template calls ADK 2's now-async `create_session` and
  fails; it becomes a direct dependency `google-cloud-aiplatform[agent_engines]>=2.10` (the deploy
  config needs it). Its `AdkApp.set_up()` always switches to the Vertex AI backend, so the local dry
  run builds and serializes the `AdkApp` but queries `root_agent` through ADK's own runner.

## Constitution check

| Principle | How |
|---|---|
| I Spec-first | This spec and plan before code |
| II Policy source of truth | Output guard requires cited passages to be ones the tools returned |
| III Deterministic core | Action guard blocks approval tools; decisions stay in `decide()` |
| IV Money | Unchanged |
| V Test-first, offline | Guardrail tests offline; eval gate runs in replay without a key |
| VI Simplicity | No new dependency; regex guards; file exporter |
