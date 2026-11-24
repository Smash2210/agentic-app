---

description: "Task list for 001-claims-api"
---

# Tasks: Claims API

**Input**: Design documents from `specs/001-claims-api/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/claims-api.md, quickstart.md

**Tests**: Required. Constitution Principle V (test-first, offline) makes tests mandatory: write
each test task first, run it, and see it fail before the matching implementation task.

**Organization**: Tasks are grouped by user story. Field constraints are cited as
`data-model.md Entity.field` rather than restated; decisions are cited as `research.md R-NN`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story (US1, US2, US3)

## Path Conventions

Single project: `src/agentic_app/`, `tests/` at repository root (plan.md Project Structure).

## Ground rules for every task

- No policy number in Python source: rates, caps, limits, thresholds and percentages come from the
  `Policy` object (spec FR-011). Tests may state expected numbers.
- Money is `Decimal`; never `float`. Round only with `money.to_cents` (research R-04).
- `claims/rules.py` stays pure: no I/O, clock, randomness, globals or LLM (constitution III).
- Never read `.env`. `uv run pytest` must stay green with no API key and no network.
- Commit after each completed phase (constitution Development Workflow).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies and package skeleton

- [X] T001 Add runtime dependencies with `uv add fastapi uvicorn` and the dev dependency with `uv add --dev httpx` (research.md R-01; nothing else) in pyproject.toml and uv.lock; confirm `uv run pytest` is still green
- [X] T002 [P] Add `data/claims.db` to .gitignore (plan.md "Required tasks from plan review")
- [X] T003 [P] Create empty packages src/agentic_app/claims/__init__.py and tests/claims/__init__.py, and tests/claims/conftest.py with a session fixture `policy_dir` returning the repository's `data/policies` path computed from `__file__` and a fixture `db_path` returning `tmp_path / "claims.db"`

**Checkpoint**: `uv run pytest` green; commit "chore(001): dependencies and claims package skeleton".

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Money helper, policy loader, shared models with validation, storage core, app factory.
Every user story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests (write first, see them fail)

- [X] T004 [P] Write tests for `to_cents` in tests/claims/test_money.py: half-up at the half cent (`Decimal("0.005")` → `0.01`, `Decimal("25.005")` → `25.01`, `Decimal("10.8108")` → `10.81`), exact values unchanged, result always has 2 decimal places, and a `float` argument raises `TypeError` (research.md R-04)
- [X] T005 [P] Write tests for `load_policy` in tests/claims/test_policy.py against the real `policy_dir`: every field of data-model.md `Policy` (`currency_rates`, `meals_daily_limit_usd`, `lodging_caps_usd`, `lodging_default_cap_usd`, `per_diem_rates_usd`, `per_diem_default_rate_usd`, `travel_day_fraction`, `same_day_fraction`, `receipt_threshold_usd`, `sections`) equals the value in data/policies/*.md and is a `Decimal`; city lookups are case-insensitive and trim spaces, unknown cities get the default; the object and its mappings cannot be mutated. Failure cases using small Markdown copies in `tmp_path`: missing `doc_id`, missing "Any other city" row, a bold value missing or present twice in its section, a missing file — each raises `PolicyError` whose message names the file and section (research.md R-02)
- [X] T006 [P] Write validation tests in tests/claims/test_schemas.py for data-model.md `Trip.destination_city`, `Trip.start_date`, `Trip.end_date`, `ExpenseLineIn.date`, `ExpenseLineIn.category`, `ExpenseLineIn.merchant`, `ExpenseLineIn.amount`, `ExpenseLineIn.currency`, `ExpenseLineIn.receipt_attached`, `ExpenseLineIn.nights`, `ClaimIn.employee_id`, `ClaimIn.trip`, `ClaimIn.lines`: one valid case and one invalid case per rule; amount given as a JSON number is refused (research.md R-05); `" eur"` becomes `"EUR"` and `"JPY"` is accepted (research.md R-07, spec FR-013); lodging `nights` defaults to 1, non-lodging `nights` must be null; several cross-field errors (end before start, line date outside trip, last night after end date) are all reported together with locations like `lines.2.date` (research.md R-06); amounts round-trip as the exact submitted string
- [X] T007 [P] Write tests for the storage core in tests/claims/test_store.py: `init_db` is idempotent; `add_claim` returns increasing integer IDs and `line_no` 1..n (data-model.md `Claim.id`, `Claim.lines.line_no`); `get_claim` round-trips every field exactly (amount `"50.00"` stays `"50.00"`, `nights` null for non-lodging) and returns `None` for an unknown ID; `PRAGMA table_info` shows money columns are `TEXT`; `prior_lines(employee_id, before_claim_id)` returns only that employee's lines from lower claim IDs as data-model.md `PriorLine`; a failure while inserting lines (monkeypatched) leaves no claim row behind
- [X] T008 [P] Write tests for app wiring in tests/claims/test_app.py: importing `agentic_app.app` in a fresh interpreter (`subprocess` with `cwd=tmp_path`) creates no `data/claims.db` and does not read the policy; `create_app(db_path, policy_dir)` creates the schema in `db_path`; `app_from_env()` uses `CLAIMS_DB_PATH` and `POLICY_DIR` (set with `monkeypatch.setenv`); `create_app` with a broken policy directory raises `PolicyError` (research.md R-12)

### Implementation

- [X] T009 [P] Implement `to_cents` in src/agentic_app/claims/money.py (research.md R-04)
- [X] T010 [P] Implement `Policy` (frozen dataclass, mappings in `MappingProxyType`), `PolicyError`, `load_policy(policy_dir)` and city/currency lookup helpers in src/agentic_app/claims/policy.py, filling `data-model.md Policy.currency_rates`, `Policy.meals_daily_limit_usd`, `Policy.lodging_caps_usd`, `Policy.lodging_default_cap_usd`, `Policy.per_diem_rates_usd`, `Policy.per_diem_default_rate_usd`, `Policy.travel_day_fraction`, `Policy.same_day_fraction`, `Policy.receipt_threshold_usd` and `Policy.sections` from the sources listed there (research.md R-02); then add a session-scoped `policy` fixture to tests/claims/conftest.py
- [X] T011 [P] Implement the Pydantic models in src/agentic_app/schemas.py: input models with validation for `data-model.md Trip.destination_city`, `Trip.start_date`, `Trip.end_date`, `ExpenseLineIn.date`, `ExpenseLineIn.category`, `ExpenseLineIn.merchant`, `ExpenseLineIn.amount`, `ExpenseLineIn.currency`, `ExpenseLineIn.receipt_attached`, `ExpenseLineIn.nights`, `ClaimIn.employee_id`, `ClaimIn.trip` and `ClaimIn.lines` (field-level validators plus one claim-level `model_validator(mode="after")` that collects all cross-field errors, research.md R-06; `ExpenseLineIn.amount` uses a string-only money input type, research.md R-05); stored models `ExpenseLine` (adds `data-model.md Claim.lines.line_no`) and `Claim` (adds `data-model.md Claim.id`) that accept `Decimal`; `PriorLine` (`data-model.md PriorLine.claim_id`, `PriorLine.line_no`, `PriorLine.date`, `PriorLine.amount`, `PriorLine.currency`, `PriorLine.merchant`); and the output models with `data-model.md Citation.doc_id`, `Citation.sections`, `Violation.rule_id`, `Violation.line_nos`, `Violation.date`, `Violation.excess_usd`, `Violation.message`, `Violation.citation`, `LineResult.line_no`, `LineResult.claimed_usd`, `LineResult.reimbursable_usd`, `LineResult.rejected_usd`, `LineResult.flagged_for_review`, `PerDiem.city`, `PerDiem.daily_rate_usd`, `PerDiem.days`, `PerDiem.amount_usd`, `PerDiem.citation`, `CheckResult.claim_id`, `CheckResult.lines`, `CheckResult.violations`, `CheckResult.per_diem`, `CheckResult.lines_reimbursable_usd` and `CheckResult.total_reimbursable_usd`, with money serialised as strings
- [X] T012 Implement src/agentic_app/claims/store.py: `connect(db_path)`, `init_db(conn)` creating the tables and index in data-model.md Storage, `add_claim(conn, claim_in) -> Claim` in one transaction, `get_claim(conn, claim_id) -> Claim | None`, `prior_lines(conn, employee_id, before_claim_id) -> list[PriorLine]` (research.md R-03, R-11); money stored as `str(Decimal)` (depends on T011)
- [X] T013 [P] Write tests in tests/test_package_import.py, each importing in a fresh interpreter (`subprocess` running `sys.executable -c ...`): `import agentic_app` and `import agentic_app.app` both leave `agentic_app.llm` and `google.genai` out of `sys.modules` (the `agentic_app.app` case passes once T015 lands); and `agentic_app.main()` with a patched `agentic_app.llm.generate` still prints its answer, so the CLI is unchanged (research.md R-12)
- [X] T014 [P] Move `from agentic_app.llm import generate` from module level into `main()` in src/agentic_app/__init__.py so importing the package no longer runs `load_dotenv()` or imports `google.genai` (research.md R-12) so the `import agentic_app` cases of T013 pass
- [X] T015 Implement src/agentic_app/app.py with `create_app(db_path, policy_dir)` (loads policy once, runs `init_db`, stores both on `app.state`, mounts the router) and the no-argument factory `app_from_env()`; no app built at import time; and src/agentic_app/claims/api.py with an empty `APIRouter` plus dependencies that open one `sqlite3` connection per request and return `app.state.policy` (research.md R-12) (depends on T010, T012, T014)

**Checkpoint**: Foundation ready, `uv run pytest` green; commit "feat(001): money, policy loader, schemas, store, app factory".

---

## Phase 3: User Story 1 - Check a claim against policy (Priority: P1) 🎯 MVP

**Goal**: `GET /claims/{id}/check` returns every violation with citations and the per-line USD
reimbursement summary, per diem and total, computed by the pure `check_claim`.

**Independent Test**: Load the seed data, check each claim, and compare rules and totals with the
hand-computed expected values (spec SC-001, SC-002).

### Tests for User Story 1 (write first, see them fail)

All rule tests call `check_claim` directly with models built in the test and the real `policy`
fixture, and assert data-model.md `LineResult`, `Violation` and `PerDiem` fields.

- [X] T016 [P] [US1] Currency tests in tests/claims/test_rules_currency.py: 30.00 EUR → 32.40, 10.01 EUR → 10.81 (two such lines total 21.62), 18.00 GBP → 22.86, 2083.75 INR → 25.01; a `JPY` line gives `CURRENCY_UNSUPPORTED` citing POL-CURRENCY §2 with `claimed_usd` and `rejected_usd` null, `reimbursable_usd` 0.00 and `excess_usd` null, while other lines are checked normally (spec FR-012, FR-013)
- [X] T017 [P] [US1] Receipt tests in tests/claims/test_rules_receipts.py: 24.99 and 25.00 USD without receipt → no violation; 25.01 USD without receipt → `RECEIPT_MISSING` citing POL-RECEIPTS §1, §2, reimbursable 0.00, rejected 25.01; same amounts with a receipt → no violation; 2083.75 INR without receipt → violation; a multi-night lodging line uses its whole USD amount for the threshold (spec FR-014)
- [X] T018 [P] [US1] Duplicate tests in tests/claims/test_rules_duplicates.py: second identical line in a claim → `DUPLICATE` citing POL-RECEIPTS §3, §4 with `flagged_for_review` true and reimbursable 0.00, first line untouched; match against `prior_lines`; merchants differing only in case or surrounding spaces match, `"Café Roma"` vs `"Cafe Roma"` do not; same amount in a different currency does not match; `"10.0"` equals `"10.00"`; a `JPY` line still takes part; the message names the original line or claim (spec FR-015, research.md R-09)
- [X] T019 [P] [US1] Meals tests in tests/claims/test_rules_meals.py: one day at 74.99, 75.00 (no violation) and 75.01 (`MEALS_DAILY_LIMIT`, `excess_usd` 0.01); 50.00 + 40.00 on one day → line 1 pays 50.00, line 2 pays 25.00, one violation with that `date`, `line_nos` [2] and `excess_usd` 15.00, citing POL-MEALS §1, §3; different days are independent; a meal line rejected for a missing receipt counts 0 so the other line is paid in full (spec scenario 12, FR-016)
- [X] T020 [P] [US1] Lodging tests in tests/claims/test_rules_lodging.py: one night at 0.01 under each city cap, at the cap and 0.01 over it for Berlin, London and an other city (city matched case-insensitively); 540.00 EUR for 3 nights in Berlin → claimed 583.20, reimbursable 540.00, rejected 43.20, three violations (one per night date) each with `excess_usd` 14.40 citing POL-LODGING §1, §2, §3; 100.00 USD over 3 nights splits 33.33/33.33/33.34; two lodging lines on the same night are paid in line order; a cheap night does not raise another night's cap; a rejected lodging line counts 0 (spec FR-017, research.md R-10)
- [X] T021 [P] [US1] Per diem tests in tests/claims/test_rules_per_diem.py: same-day trips in Berlin, London and Paris → 45.00, 52.50 and 33.75 citing POL-PERDIEM §1, §3; 2-day Berlin → 90.00; 4-day Paris 10–13 March → 157.50 citing POL-PERDIEM §1, §2; per diem is unchanged when lines have violations (spec FR-018)
- [X] T022 [P] [US1] Whole-check tests in tests/claims/test_rules_check.py: the contracts/claims-api.md example claim gives the documented `CheckResult` (total 564.00) in every field except `message`, and each message is non-empty and contains the amounts it reports; a 200.00 USD transport line with a receipt is paid in full with no meals or lodging violation (spec FR-019); violations are sorted per research.md R-09; `total_reimbursable_usd` = `lines_reimbursable_usd` + per diem; calling twice gives equal results; every citation the engine can emit (all `RuleId` values and both per diem variants) names a doc_id and sections present in `policy.sections` (spec SC-003)
- [X] T023 [P] [US1] Purity test in tests/claims/test_rules_purity.py: parse src/agentic_app/claims/rules.py with `ast` and fail on imports of `sqlite3`, `os`, `pathlib`, `random`, `time`, `agentic_app.llm` or `google`, on any call to `.now(`/`.today(`, on `float(` anywhere in src/agentic_app/claims/ or src/agentic_app/schemas.py, and on any numeric literal in rules.py other than 0 and 1 — ints, floats and numeric strings passed to `Decimal(...)` all count, while 0 and 1 are allowed in any form such as `Decimal("0.00")` (spec FR-011, constitution II, III, IV)
- [X] T024 [P] [US1] Check endpoint tests in tests/claims/test_api_check.py using `TestClient(create_app(db_path, policy_dir))` with claims inserted via `store.add_claim`: 200 with the contract shape and money as strings; 404 `{"detail": "Claim 99 not found"}`; an earlier claim's check is unchanged after a later claim duplicating one of its lines is added, and the later claim gets `DUPLICATE` (spec SC-005)

### Implementation for User Story 1

- [X] T025 [US1] In src/agentic_app/claims/rules.py define `RuleId` (the five IDs in data-model.md `Violation.rule_id`) and the citation table from research.md R-09, and implement `check_claim(claim, prior_lines, policy) -> CheckResult` covering currency conversion and unsupported currency, per-line results, per diem and totals (research.md R-08 steps 1 and 6) so T016 and T021 pass
- [X] T026 [US1] Add receipt and duplicate rules to `check_claim` in src/agentic_app/claims/rules.py (research.md R-08 steps 2–3, merchant normalisation per R-07) so T017 and T018 pass
- [X] T027 [US1] Add the meals daily limit to `check_claim` in src/agentic_app/claims/rules.py (research.md R-08 step 4) so T019 passes
- [X] T028 [US1] Add lodging night splitting and the nightly cap to `check_claim` in src/agentic_app/claims/rules.py (research.md R-08 step 5, R-10) so T020 passes
- [X] T029 [US1] Finish src/agentic_app/claims/rules.py: violation sort order, plain-language messages with amounts and limits, `excess_usd` per data-model.md `Violation.excess_usd`, so T022 and T023 pass
- [X] T030 [US1] Add `GET /claims/{claim_id}/check` to src/agentic_app/claims/api.py: load the claim, fetch `prior_lines`, call `check_claim`, 404 if unknown (contracts/claims-api.md) so T024 passes
- [X] T031 [US1] Write data/seed/claims.json: the 12 claims in data-model.md Seed coverage, in that order, each with `expected_rules`, `expected_total_usd` and an `expected_working` string showing the hand calculation from the policy documents (not from running the code) (research.md R-13)
- [X] T032 [US1] Write tests in tests/claims/test_seed.py: running the loader into an empty temp DB prints `Loaded 12 claims` and exits 0; a second run exits 1; every claim's set of violation `rule_id`s equals `expected_rules` and its total equals `expected_total_usd` (spec SC-001); across the seed every `RuleId` appears and at least two claims have no rules (spec SC-002) (depends on T031)
- [X] T033 [US1] Implement src/agentic_app/claims/seed.py runnable as `python -m agentic_app.claims.seed --db PATH`: refuse a non-empty DB, strip `expected_*` keys, validate each claim with `ClaimIn`, insert in file order with `store.add_claim` (contracts/claims-api.md CLI contract) so T032 passes

**Checkpoint**: US1 works on its own with seed data; `uv run pytest` green; commit "feat(001): US1 policy check with seed data".

---

## Phase 4: User Story 2 - Submit a claim (Priority: P2)

**Goal**: `POST /claims` stores valid claims and returns them with an ID; invalid input gets a 422
naming each field it can evaluate and stores nothing.

**Independent Test**: Submit valid and invalid claims through the API; valid ones come back with an
ID and read back unchanged, invalid ones leave the database unchanged.

### Tests for User Story 2 (write first, see them fail)

- [X] T034 [P] [US2] Submit endpoint tests in tests/claims/test_api_submit.py: the contracts/claims-api.md request returns 201 with `id`, `line_no` 1..3, lodging `nights` 2 and other `nights` null, currency upper-cased; a `JPY` line is accepted with 201; 422 with the right `loc` for end before start, unknown category, zero amount, amount as a JSON number, empty merchant, line date outside the trip, `nights` on a meal line, and no lines; after each 422 the claim count in the DB is unchanged; the stored claim read via `store.get_claim` matches the request (spec FR-001–FR-003, SC-006)

### Implementation for User Story 2

- [X] T035 [US2] Add `POST /claims` (status 201, body `ClaimIn`, response `Claim`) to src/agentic_app/claims/api.py using `store.add_claim` so T034 passes

**Checkpoint**: US1 and US2 both work; `uv run pytest` green; commit "feat(001): US2 submit claims".

---

## Phase 5: User Story 3 - View claims (Priority: P3)

**Goal**: Get one claim by ID and list an employee's claims in submission order.

**Independent Test**: With claims stored, fetch one by ID and list by employee; compare with what was
stored.

### Tests for User Story 3 (write first, see them fail)

- [X] T036 [P] [US3] Add `list_claims` tests to tests/claims/test_store.py: an employee's claims come back in ascending ID order; another employee's claims are excluded; an unknown employee gives `[]`
- [X] T037 [P] [US3] View endpoint tests in tests/claims/test_api_view.py: `GET /claims/{id}` 200 with the stored claim and 404 `{"detail": "Claim 99 not found"}`; `GET /claims?employee_id=E-001` lists three claims in submission order; unknown employee → 200 `[]`; missing `employee_id` → 422 (spec FR-004, FR-005)

### Implementation for User Story 3

- [X] T038 [US3] Implement `list_claims(conn, employee_id) -> list[Claim]` in src/agentic_app/claims/store.py so T036 passes
- [X] T039 [US3] Add `GET /claims/{claim_id}` and `GET /claims?employee_id=` to src/agentic_app/claims/api.py so T037 passes

**Checkpoint**: All three stories work; `uv run pytest` green; commit "feat(001): US3 view claims".

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T040 [P] Add a "Claims API" section to README.md with the quickstart.md commands (install, seed, run with `--factory`, docs URL)
- [ ] T041 Run every quickstart.md step and validation scenario against a fresh `data/claims.db`; record the commands and responses in evidence/M02-agentic-coding/README.md
- [ ] T042 Run `env -u GOOGLE_API_KEY uv run pytest` and confirm it is green with no network access; confirm `git status` shows no `data/claims.db`

**Checkpoint**: commit "docs(001): quickstart evidence and README".

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup; blocks all user stories
- **US1 (Phase 3)**, **US2 (Phase 4)**, **US3 (Phase 5)**: each depends only on Foundational; done in
  priority order P1 → P2 → P3 by default
- **Polish (Phase 6)**: after all stories

### User Story Dependencies

- **US1**: needs T011 models, T012 store and T015 app; seed loading uses `store.add_claim` directly,
  not the POST endpoint, so US1 does not depend on US2
- **US2**: needs Foundational only; the 422 behaviour comes from T011 validation
- **US3**: needs Foundational only

### Within Each Phase

- Test tasks before their implementation tasks; run them and see them fail first
- T025 → T026 → T027 → T028 → T029 share src/agentic_app/claims/rules.py, so run in order
- T030, T035 and T039 share src/agentic_app/claims/api.py, so run in order across stories
- T031 → T032 → T033 (seed data, then its test, then the loader)

### Parallel Opportunities

- Phase 1: T002, T003
- Phase 2: tests T004–T008 and T013 together; then T009, T010, T011, T014 together; T012 then T015
- Phase 3: tests T016–T024 together (separate files)
- Phase 5: T036 and T037 together
- After Phase 2, US2 and US3 test writing can proceed alongside US1 work

---

## Parallel Example: User Story 1

```bash
# Write all US1 tests together (separate files):
Task: "Currency tests in tests/claims/test_rules_currency.py"
Task: "Receipt tests in tests/claims/test_rules_receipts.py"
Task: "Duplicate tests in tests/claims/test_rules_duplicates.py"
Task: "Meals tests in tests/claims/test_rules_meals.py"
Task: "Lodging tests in tests/claims/test_rules_lodging.py"
Task: "Per diem tests in tests/claims/test_rules_per_diem.py"
Task: "Whole-check tests in tests/claims/test_rules_check.py"
Task: "Purity test in tests/claims/test_rules_purity.py"
Task: "Check endpoint tests in tests/claims/test_api_check.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup → Phase 2 Foundational
2. Phase 3 US1: rule tests, `check_claim`, check endpoint, seed data
3. **STOP and VALIDATE**: `uv run pytest`; load the seed and call `GET /claims/{id}/check`

### Incremental Delivery

1. Setup + Foundational → commit
2. US1 → validate with seed → commit (MVP)
3. US2 → validate submissions → commit
4. US3 → validate viewing → commit
5. Polish → quickstart evidence → commit

---

## Notes

- [P] tasks touch different files and depend on no incomplete task
- Every test task must be seen failing before its implementation task
- If a task reveals a spec gap, stop and ask (constitution I); do not guess

---

## Phase 7: Convergence

- [X] T043 CRITICAL: Remove module-level mutable state from src/agentic_app/claims/rules.py: make `_RULE_ORDER` a tuple, and hold `RULE_CITATIONS` / `PER_DIEM_CITATIONS` as immutable values (e.g. a frozen dataclass with `doc_id` and a `sections` tuple) that are turned into fresh `Citation` models on each check; add a test in tests/claims/test_rules_purity.py that a shared citation cannot be mutated, without changing existing tests per Constitution III (contradicts)
- [X] T044 Type data-model.md `Violation.rule_id` as the five rule IDs instead of a free `str` in src/agentic_app/schemas.py (e.g. move `RuleId` into schemas.py and re-export it from rules.py) so the OpenAPI schema lists the allowed values per data-model.md Violation.rule_id (partial)
- [X] T045 Review the `--seed` option in src/agentic_app/claims/seed.py, which contracts/claims-api.md's CLI contract does not mention: either document it in the contract and quickstart.md or remove it per contracts/claims-api.md CLI contract (unrequested)

