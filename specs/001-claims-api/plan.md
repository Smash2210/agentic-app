# Implementation Plan: Claims API

**Branch**: `001-claims-api` | **Date**: 2026-11-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-claims-api/spec.md`

## Summary

A FastAPI service where employees submit travel expense claims, view them, and request a policy
check. The check is a pure function, `check_claim(claim, prior_lines, policy)`, that applies the
currency, receipt, duplicate, meals and lodging rules and the per diem allowance, and returns every
violation (with doc_id + section citations) and a per-line USD reimbursement summary. All limits and
rates are parsed from `data/policies/*.md` at startup into a frozen `Policy`; no policy number is
written in Python. Claims are stored in stdlib `sqlite3` with money as Decimal strings. A synthetic
seed set of 12 claims with hand-computed expected results drives end-to-end tests. Design decisions
are in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastAPI (HTTP API, request validation via Pydantic v2), uvicorn (runs the
server). Dev: httpx (required by FastAPI's TestClient). Pydantic v2 comes with FastAPI.

**Storage**: SQLite via stdlib `sqlite3`; file path configurable (default `data/claims.db`,
git-ignored); tests use a temporary file per test

**Testing**: pytest, offline; API tests via FastAPI TestClient

**Target Platform**: Local developer machine (macOS/Linux), single process

**Project Type**: Web service (JSON HTTP API) inside the existing single `src/agentic_app` package

**Performance Goals**: A check of a 50-line claim completes well under 100 ms locally; not a design
driver

**Constraints**: No network, no API key, no LLM in this feature; Decimal-only money; rules engine
pure (no I/O, clock, randomness, globals)

**Scale/Scope**: Learning project: tens of employees, hundreds of claims; 4 endpoints, 5 violation
rules plus per diem

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan passes | Status |
|---|---|---|
| I. Spec-first | Every endpoint, rule and field traces to FR-001–FR-020 and the 7 clarifications in spec.md. Nothing outside the spec is built (no auth, statuses, edits, deletes, LLM). Design choices the spec leaves open are listed in research.md for review at this plan review, not silently decided. | PASS |
| II. Policy is the source of truth | `claims/policy.py` parses every rate, cap, limit, threshold and percentage from `data/policies/*.md`; parsing fails loudly if a value is missing or ambiguous. Each rule cites doc_id + section; a test checks every cited section exists in the loaded policy (SC-003). | PASS |
| III. Deterministic core | `claims/rules.py` is pure: inputs are the claim, the employee's earlier lines and the `Policy`; no I/O, clock, randomness, globals or LLM. Storage and HTTP stay in `store.py` and `api.py`. Prior lines are limited to earlier-submitted claims, so later claims never change a result (SC-005). | PASS |
| IV. Money correctness | `Decimal` everywhere; requests take money as JSON strings (numbers refused, so no float ever parses); SQLite stores TEXT; per-line conversion then `ROUND_HALF_UP` to 0.01; totals are sums of rounded values; one shared `to_cents()` helper. | PASS |
| V. Test-first, offline | Tests written before each rule's code: at, below and above every threshold (SC-004), API tests with a temp DB, seed tests asserting expected rules and totals (SC-001/002). No network or key needed; `live` tests untouched. | PASS |
| VI. Simplicity | One package, 6 modules, stdlib `sqlite3`, no ORM, no migrations tool. Three dependencies, each justified in research.md (R-01). | PASS |

## Project Structure

### Documentation (this feature)

```text
specs/001-claims-api/
├── plan.md              # This file
├── research.md          # Phase 0: design decisions R-01..R-14
├── data-model.md        # Phase 1: entities, validation, storage tables, seed coverage
├── quickstart.md        # Phase 1: run and validate end to end
├── contracts/
│   └── claims-api.md    # Phase 1: HTTP endpoints + check_claim() contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 (/speckit-tasks; not created here)
```

### Source Code (repository root)

```text
src/agentic_app/
├── __init__.py          # existing CLI; llm import moved inside main() (R-12)
├── llm.py               # existing Gemini wrapper (unchanged, not imported by this feature)
├── schemas.py           # Pydantic models: Trip, ExpenseLine, ClaimIn, Claim, RuleId, Citation,
│                        #   Violation, LineResult, PerDiem, CheckResult
├── app.py               # create_app(db_path, policy_dir); app_from_env() factory for
│                        #   `uvicorn --factory`; no app built at import time (R-12)
└── claims/
    ├── __init__.py
    ├── money.py         # to_cents(): Decimal quantize to 0.01, ROUND_HALF_UP
    ├── policy.py        # load_policy(dir) -> Policy (frozen); PolicyError
    ├── rules.py         # check_claim() (pure); re-exports RuleId from schemas.py
    ├── store.py         # sqlite3: init_db, add_claim, get_claim, list_claims, prior_lines
    ├── api.py           # APIRouter: POST /claims, GET /claims, GET /claims/{id}, GET /claims/{id}/check
    └── seed.py          # python -m agentic_app.claims.seed --db PATH  (empty DB only)

data/
├── policies/*.md        # existing source of truth (read-only)
└── seed/claims.json     # 12 synthetic claims with expected_rules + expected_total_usd

tests/
├── test_llm.py          # existing
├── test_package_import.py   # importing agentic_app does not load llm / google.genai
├── claims/
│   ├── conftest.py      # policy fixture (real data/policies), tmp DB, TestClient
│   ├── test_money.py
│   ├── test_policy.py   # parsing, citations exist, parse failures
│   ├── test_rules_currency.py
│   ├── test_rules_receipts.py
│   ├── test_rules_duplicates.py
│   ├── test_rules_meals.py
│   ├── test_rules_lodging.py
│   ├── test_rules_per_diem.py
│   ├── test_rules_check.py   # combined behaviour, ordering, determinism
│   ├── test_schemas.py       # validation (FR-002)
│   ├── test_store.py
│   ├── test_app.py           # app factory, no import side effects
│   ├── test_rules_purity.py  # AST scan: no I/O, clock, float or policy literals
│   ├── test_api_check.py
│   ├── test_api_submit.py
│   ├── test_api_view.py
│   └── test_seed.py          # SC-001, SC-002
```

**Structure Decision**: Keep the existing single-package src layout. Feature code lives in
`src/agentic_app/claims/`; `schemas.py` sits at package level because later tiers (the ADK agent)
will reuse these models. Tests mirror the modules under `tests/claims/`.

## Complexity Tracking

No constitution violations; nothing to justify.

## Post-Design Constitution Re-check

Re-evaluated after writing data-model.md and contracts/claims-api.md: all six principles still PASS.
Points for the human plan review (decisions not dictated by the spec, see research.md):

1. **R-05** Money in requests must be JSON strings (`"12.50"`); JSON numbers get 422. **Approved**.
2. **R-06** Cross-field checks (line date inside trip, nights fit, end ≥ start) are reported only once
   the fields they compare are themselves valid. **Resolved**: accepted; spec SC-006 amended to match
   (Principle I: spec changed first).
3. **R-07** Currency codes are trimmed and upper-cased on input (`" eur"` → `EUR`). **Resolved**:
   accepted; recorded in spec.md Clarifications.
4. **R-09** Violation output shape: `line_nos` (1-based), optional `date`, and `citation` with a list
   of sections; lines also carry `flagged_for_review`. **Approved** with one addition: `excess_usd`
   (amount rejected by `MEALS_DAILY_LIMIT` / `LODGING_NIGHTLY_CAP`, null otherwise); spec FR-008
   updated to match.
5. **R-03** Claim IDs are integers that also give submission order. **Approved**.
6. **R-12** Review fix: no app is built at import time; `app_from_env()` factory run with
   `uvicorn agentic_app.app:app_from_env --factory`. **Resolved**.

**Plan review (2026-11-24)**: reviewed against Principles I–VI with fixes to R-12, SC-006, R-07 and
R-09 applied. **Approved**; ready for `/speckit-tasks`.

## Required tasks from plan review

- Add `data/claims.db` to `.gitignore` (R-12).
