# Specification Analysis Report: 001-claims-api

**Date**: 2026-11-24 (run 2, after remediation)
**Command**: `/speckit-analyze` (read-only)
**Artifacts analysed**: spec.md, plan.md, tasks.md, research.md, data-model.md, contracts/claims-api.md,
`.specify/memory/constitution.md` (v1.0.0)
**Extension hooks**: none (`.specify/extensions.yml` does not exist)

## Summary

No CRITICAL, HIGH or MEDIUM issues. 2 LOW. All 12 findings from run 1 are resolved. Every FR and SC
is fully covered. Ready for `/speckit-implement`.

## Run 1 findings: resolution

Task IDs below are the new numbers (T013 onward shifted by 2 when the U1 task pair was inserted).

| ID | Severity | Resolution |
|----|----------|------------|
| U1 | HIGH | New test-first pair in Phase 2: T013 (tests/test_package_import.py: `import agentic_app` and `import agentic_app.app` leave `agentic_app.llm` and `google.genai` out of `sys.modules`; CLI still works) and T014 (move the `llm` import inside `main()`). T015 (app.py) now depends on T014. Noted in research.md R-12 and plan.md file tree. |
| C1 | HIGH | T010 cites all 10 `data-model.md Policy.*` fields by name. |
| C2 | HIGH | T011 cites all 13 input fields and every `PriorLine`, `Citation`, `Violation`, `LineResult`, `PerDiem` and `CheckResult` field as `data-model.md Entity.field`. |
| I1 | MEDIUM | T022 compares every field except `message`; messages must be non-empty and contain the amounts. |
| C3 | MEDIUM | T022 adds the FR-019 case: 200.00 USD transport with receipt paid in full. |
| C4 | MEDIUM | T017 adds 24.99 USD; T020 adds cap − 0.01 for each city. |
| D1 | MEDIUM | research.md R-04 note: 2-decimal precision is fixed by Constitution IV and POL-CURRENCY §3, the one permitted constant. |
| D2 | MEDIUM | T023 float scan covers src/agentic_app/schemas.py too. |
| C5 | MEDIUM | T023 fails on numeric literals in rules.py other than 0 and 1 (ints, floats and numeric strings in `Decimal(...)`; 0 and 1 allowed in any form, e.g. `Decimal("0.00")`). |
| I2 | LOW | plan.md file tree lists test_app.py, test_rules_purity.py, test_api_check.py, test_api_submit.py, test_api_view.py and tests/test_package_import.py. |
| I3 | LOW | spec.md US1 scenario 3 cites POL-LODGING §1–3. |
| I4 | LOW | spec.md Key Entities: Violation includes the rejected amount for daily and nightly limits. |

Also applied: T041 evidence path is `evidence/M02-agentic-coding/README.md`.

## Findings (run 2)

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| A1 | Duplication | LOW | tasks.md:63 T008; tasks.md:71 T013 | Both tasks spawn a fresh interpreter to import `agentic_app.app`: T008 checks no DB file and no policy read, T013 checks no `llm`/`google.genai`. Overlapping but different assertions. | Optional: have T013 own all import-side-effect checks and T008 keep only factory behaviour. Fine to leave. |
| C6 | Coverage (field citations) | LOW | tasks.md:70 T012; data-model.md:105 | Storage columns are cited as the data-model.md Storage section rather than column by column. | Acceptable: the schema is one unit implemented by one task. No change needed. |

## Requirement Coverage

| Requirement | Has task? | Task IDs | Notes |
|---|---|---|---|
| FR-001 | ✓ | T006, T011, T034, T035 | |
| FR-002 | ✓ | T006, T011, T034 | |
| FR-003 | ✓ | T007, T012, T035 | |
| FR-004 | ✓ | T036–T039 | |
| FR-005 | ✓ | T024, T030, T037, T039 | |
| FR-006 | ✓ (by omission) | — | Nothing builds edit or delete |
| FR-007 | ✓ | T022, T024, T030 | |
| FR-008 | ✓ | T011, T022, T029 | |
| FR-009 | ✓ | T011, T016, T025 | |
| FR-010 | ✓ | T022, T025 | |
| FR-011 | ✓ | T005, T010, T023 | Literal scan added (C5) |
| FR-012 | ✓ | T016, T025 | |
| FR-013 | ✓ | T016, T025, T034 | |
| FR-014 | ✓ | T017, T026 | |
| FR-015 | ✓ | T018, T026 | |
| FR-016 | ✓ | T019, T027 | |
| FR-017 | ✓ | T020, T028 | |
| FR-018 | ✓ | T021, T025 | |
| FR-019 | ✓ | T022, T025–T028 | Added (C3) |
| FR-020 | ✓ | T031–T033 | |
| SC-001 / SC-002 | ✓ | T032 | |
| SC-003 | ✓ | T022 | |
| SC-004 | ✓ | T017, T019, T020, T021 | Below-threshold cases added (C4) |
| SC-005 | ✓ | T022, T024 | |
| SC-006 | ✓ | T006, T034 | |

## Constrained-Field Coverage

| Field (`Entity.field`) | Canonical location | Implementing tasks | Notes |
|---|---|---|---|
| `Trip.*` (3), `ExpenseLineIn.*` (7), `ClaimIn.*` (3) | data-model.md Input models | T011 | Each cited |
| `Claim.id`, `Claim.lines.line_no` | data-model.md Stored / output models | T011, T012 | Each cited |
| `PriorLine.*` (6) | data-model.md PriorLine | T011, T012 | Each cited |
| `Citation.*`, `Violation.*`, `LineResult.*`, `PerDiem.*`, `CheckResult.*` | data-model.md:52–88 | T011 (also T025, T029) | Each cited |
| `Policy.*` (10) | data-model.md:90 | T010 | Each cited |
| Storage columns | data-model.md:105 | T012 | Section-level (C6, LOW) |

No task-stated constraint contradicts data-model.md.

## Constitution Alignment

No issues. Principle II/IV: literal and float scans (T023) plus the R-04 precision note. Principle III:
purity scan (T023) and no import side effects (T008, T013). `.env` is no longer read by importing the
Claims API (T014).

## Unmapped Tasks

None.

## Metrics

| Metric | Value |
|---|---|
| Total requirements | 26 (20 FR, 6 SC) |
| Total tasks | 42 |
| Coverage (≥ 1 task) | 100%, none partial |
| Ambiguity count | 0 |
| Duplication count | 1 (LOW) |
| Critical issues | 0 |
| High / Medium / Low | 0 / 0 / 2 |

## Next Actions

Only LOW findings remain; proceed to `/speckit-implement`. Commit the remediated artifacts first.
