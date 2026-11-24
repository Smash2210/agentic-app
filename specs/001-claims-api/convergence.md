# Convergence Report: 001-claims-api

**Date**: 2026-11-24
**Command**: `/speckit-converge`
**Outcome**: `tasks_appended`: 3 tasks added to tasks.md as Phase 7: Convergence (T043–T045)
**Extension hooks**: none (`.specify/extensions.yml` does not exist)

The check compared the code against spec.md, plan.md, tasks.md and the constitution (v1.0.0). Its
only write was appending Phase 7 to tasks.md; no code was changed.

## Findings

| ID | Gap Type | Severity | Source | Evidence | Remaining Work |
|----|----------|----------|--------|----------|----------------|
| F1 | contradicts | CRITICAL | Constitution III; contracts/claims-api.md "no module-level mutable state" | In `src/agentic_app/claims/rules.py`, `_RULE_ORDER = list(RuleId)` is a mutable list, and `RULE_CITATIONS` / `PER_DIEM_CITATIONS` hold mutable Pydantic `Citation` objects. An in-memory probe appended to `RULE_CITATIONS[DUPLICATE].sections` and the shared value became `['3', '4', '99']`. | **T043**: make the order a tuple; store citations as immutable values (e.g. a frozen dataclass with a `sections` tuple) and build a fresh `Citation` on each check; add a test that a shared citation cannot be changed, without changing existing tests. |
| F2 | partial | LOW | data-model.md `Violation.rule_id` | `src/agentic_app/schemas.py` types `rule_id` as `str` rather than the five rule IDs, so the OpenAPI schema does not list the allowed values. | **T044**: move `RuleId` into `schemas.py` (re-exported from `rules.py`) and use it for `Violation.rule_id`. |
| F3 | unrequested | LOW | contracts/claims-api.md CLI contract | `src/agentic_app/claims/seed.py` has a `--seed` option the CLI contract does not mention. | **T045**: document it in the contract and quickstart.md, or remove it. |

### Note on F1

Nothing in the code changes these values today, and every check deep-copies a citation before
returning it, so this is a latent risk rather than a live bug; that is also why the tests pass. It is
rated CRITICAL only because it breaks a MUST in the constitution ("no globals") and in the contract
("no module-level mutable state"). The fix is small and needs no existing test changed.

## Already Tracked (not appended)

Phase 6 (T040–T042) has not run yet: the README section, the quickstart run recorded in
`evidence/M02-agentic-coding/`, and the final offline check. Still unverified: the server has not been
started for real with `uv run uvicorn agentic_app.app:app_from_env --factory`; tests call the factory
directly, and T041 will cover a real start.

## What Was Checked

| Item | Count |
|---|---|
| Functional requirements | 20 (FR-001–FR-020) |
| Success criteria | 6 (SC-001–SC-006) |
| User-story acceptance scenarios | 20 (US1: 12, US2: 4, US3: 4), plus the spec's edge cases |
| Plan decisions | 14 (research.md R-01–R-14) |
| Constitution principles | 6 (I–VI) |

| Findings by gap type | Count |
|---|---|
| missing | 0 |
| partial | 1 |
| contradicts | 1 |
| unrequested | 1 |

| Findings by severity | Count |
|---|---|
| CRITICAL | 1 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 2 |

## Next Actions

Run `/speckit-implement` for Phase 7 (T043–T045), then Phase 6 (T040–T042). A follow-up
`/speckit-converge` should then report the feature converged.
