# M02 — Agentic coding: Claims API, built spec-first with Claude Code

**Outcome:** a working feature built through a spec-anchored agentic coding workflow, with the spec,
the agent plan, the session log, and passing tests.

| Required | Where |
|---|---|
| The spec | [specs/001-claims-api/spec.md](../../specs/001-claims-api/spec.md) (with clarifications), under the [constitution](../../.specify/memory/constitution.md) v1.0.0 |
| The agent plan | [plan.md](../../specs/001-claims-api/plan.md), [research.md](../../specs/001-claims-api/research.md), [data-model.md](../../specs/001-claims-api/data-model.md), [contract](../../specs/001-claims-api/contracts/claims-api.md), [tasks.md](../../specs/001-claims-api/tasks.md) (46 tasks), [analysis.md](../../specs/001-claims-api/analysis.md) |
| The session log | [session-log/01-claims-api-session.md](session-log/01-claims-api-session.md) (constitution → converge), [02-playwright-mcp-session.md](session-log/02-playwright-mcp-session.md); raw `.jsonl.gz` beside them. Scanned for API keys: none. |
| Passing tests | [pytest-output.txt](pytest-output.txt): 224 passed offline, no API key |
| Working feature | [quickstart-run.md](quickstart-run.md): real server, 15 scenarios, all as expected |

## Workflow followed

`/speckit-constitution` → `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` (human review,
3 fixes, approved in the session) → `/speckit-tasks` → `/speckit-analyze` (12 findings, all
resolved; re-run clean) → `/speckit-implement` phase by phase, tests shown failing first, human
review at each checkpoint → `/speckit-converge` × 3 until converged ([converge-final.md](converge-final.md)).
Feature branch `001-claims-api`, merged to `main` with `--no-ff`.

## Agent extended with tools

- **Hook** (`.claude/settings.json`): after every Edit/Write, Claude Code runs `uv run pytest -q`; on
  failure it exits 2 so the last 20 lines go back to the agent. Command tested directly: exit 0 when
  green, exit 2 with the failure output when not.
- **MCP server** (`.mcp.json`): Playwright. The agent drove the Swagger UI at `/docs`, ran
  `GET /claims/5/check` and reported 777.00 with 3 `LODGING_NIGHTLY_CAP` violations
  ([session log](session-log/02-playwright-mcp-session.md)).
- **Permission rule**: the agent may not read `.env` (`permissions.deny`).

## Off-spec and how it was caught

See [off-spec.md](off-spec.md). The headline: the agent wrote `days - 1 - 1` to get past a
no-literals guard test; human review caught it, and the only test change was one I approved.

## Not done, on purpose

The second feature with a mid-way replan (from the SDD course) was skipped: it is not part of the
M02 submission, and the replan skill was exercised anyway when the plan and spec were amended after
review (off-spec items 3–4).

**Probe:** "Show me a place the agent went off-spec. How did you catch it?" → off-spec item 1.
