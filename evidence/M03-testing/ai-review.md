# AI code review: Tier 1 Claims API (after the M03 fix)

- **Scope:** `src/agentic_app/` at commit `83b8e5b` (branch `m03-ai-testing`): `schemas.py`, `app.py`,
  `claims/{api,store,rules,policy,money,seed}.py`. `llm.py` and the CLI are out of scope.
- **Reviewers:** two specialised AI reviewers, run by Claude with the prompts in
  [review/prompts/security.md](../../review/prompts/security.md) and
  [review/prompts/patterns.md](../../review/prompts/patterns.md). These are the same prompt files the
  M05 CI gate will use.
- **Context engine:** each reviewer read the constitution, `CLAUDE.md`, `specs/001-claims-api/`
  (spec, research R-01–R-14) and the modules each file calls, not only a diff.
- **Verification:** every high or medium finding was reproduced against a running app (FastAPI
  `TestClient` with a temp database) before it went in this report. The inputs are in the Evidence
  column.

## Findings and decisions

Decisions are the engineer's. "Accept → M06" means the finding is real and will be fixed in the M06
security sprint, where it belongs. "Reject" means not a defect, with the reason.

| ID | Reviewer | Finding | File | Risk | Evidence | Decision | Reason |
|---|---|---|---|---|---|---|---|
| S1 | security | No access control: any caller can read any claim by its guessable integer ID, and list any employee's claims | `claims/api.py:57`, `:63` | high | `GET /claims/1` and `GET /claims?employee_id=E-9` return 200 for anyone | **Accept → M06** | Auth is explicitly out of scope in spec 001; M06 adds identity and "employees see only their own claims" |
| S2 | security | A huge amount passes validation, is stored, then crashes the check with a 500 (Decimal quantize exceeds precision) | `schemas.py:49`, `claims/money.py:10` | med | amount `"1" + 30 zeros + ".00"` → `POST` 201, `GET /check` 500 | **Accept → M06** | Real crash on stored data; fix is an upper bound on `amount` (OWASP ASVS V5 input validation) |
| S3 | security | Trip length and lodging nights have no upper bound, so one claim can make every check slow | `schemas.py:71`, `claims/rules.py:156` | med | trip to 9999-12-31 with 2,900,000 nights → `POST` 201, each `GET /check` takes 4.5 s | **Accept → M06** | Easy denial of service; fix is maximum trip length / nights (spec amendment first) |
| S4 | security | `employee_id` is not normalised, so `" E-7"` and `"E-7"` are different employees and cross-claim duplicate detection is dodged | `schemas.py:95` | med | same line under `E-7` then `" E-7"` → no `DUPLICATE` | **Accept → M06** | Lets a duplicate be paid twice. A spec gap (FR-001 says "non-empty after trim", not "trimmed"); amend spec, then trim at input |
| S5 | security | SQLite connection opened with `check_same_thread=False` | `claims/store.py:43` | low | n/a | **Reject** | One connection per request, never shared; FastAPI may use it on another worker thread. Documented in a comment |
| S6 | security | Seed loader writes to any `--db` path | `claims/seed.py:26` | low | n/a | **Reject** | Local developer CLI, not reachable over HTTP |
| P1 | patterns | Lodging split could give a night a negative share, freeing cap for another line (Principle IV, FR-017) | `claims/rules.py:156` | high | 0.02 USD over 4 nights + 180.01 one-night line → paid 180.01 vs cap 180 | **Accept, fixed** | The M03 defect: spec amended, fixed in `83b8e5b` ([defect.md](defect.md)) |
| P2 | patterns | `"1e2"` is accepted and stored/echoed as `"1E+2"`, unlike every other amount (contract: money as plain decimal strings) | `schemas.py:49` | low | `amount: "1e2"` → stored `1E+2` | **Accept → M06** | Belongs with S2's input-validation fix: reject exponent notation |
| P3 | patterns | `list_claims` runs one query per claim (N+1) | `claims/store.py:145` | low | n/a | **Reject** | Principle VI (simplicity): tens of claims per employee; revisit only if it shows up in a trace |
| P4 | patterns | `seed.py` shows 0% coverage: its tests run it with `subprocess`, which coverage does not see | `claims/seed.py` | low | coverage report | **Accept, not fixed** | Real gap in the measurement, not in behaviour (the CLI contract is tested). Low value for this sprint |
| P5 | patterns | Per diem is rounded once at the end, not per day (R-04); the two differ for a rate like 45.50 | `claims/rules.py:212` | low | not reachable with current rates | **Reject** | Matches R-04 as approved; POL-PERDIEM §4 is ambiguous. Revisit if a rate with an odd number of cents is added |
| P6 | patterns | Lowercase currency reaching `rules.py` is treated as unsupported | `claims/rules.py:91` | low | only with a hand-built `Claim` | **Reject** | By design: currency is normalised at the API boundary (R-07); stored data is always upper case |
| P7 | patterns | A field named `date` shadows the `datetime.date` type in models | `schemas.py:180` | low | n/a | **Reject** | Works in Pydantic v2 and is part of the published contract; renaming would break clients |

## Summary

| | Count |
|---|---|
| Findings | 13 (6 security, 7 patterns) |
| Accepted | 7: 1 fixed in M03 (P1), 5 for M06 (S1–S4, P2), 1 accepted, not fixed (P4) |
| Rejected | 6, each with a reason |

The four "Accept → M06" security findings are real, reproduced defects. M06 starts from them.
