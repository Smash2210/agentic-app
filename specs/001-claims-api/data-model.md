# Data Model: Claims API

Models live in `src/agentic_app/schemas.py` (Pydantic v2) unless noted. All money is `Decimal`;
in JSON it is a string (research R-05).

## Input models

### Trip

| Field | Type | Rules |
|---|---|---|
| `destination_city` | str | required; non-empty after trim; at most 200 characters as submitted |
| `start_date` | date (`YYYY-MM-DD`) | required |
| `end_date` | date | required; `end_date >= start_date`; trip at most 366 days, start to end inclusive (`end_date − start_date + 1 <= 366`) (cross-field, ClaimIn validator) |

### ExpenseLineIn

| Field | Type | Rules |
|---|---|---|
| `date` | date | required; `trip.start_date <= date <= trip.end_date` (cross-field) |
| `category` | enum `meal` \| `lodging` \| `transport` \| `other` | required |
| `merchant` | str | required; non-empty after trim; at most 200 characters as submitted |
| `amount` | Decimal (JSON string) | required; plain decimal text `[0-9]+(\.[0-9]{0,2})?` after trimming surrounding spaces (no sign, exponent, inner spaces or non-ASCII digits); `> 0`; `<= 1000000.00` |
| `currency` | str | required; non-empty; trimmed and upper-cased (R-07); not checked against rates here |
| `receipt_attached` | bool | required |
| `nights` | int \| null | lodging: integer ≥ 1, default 1; other categories: must be absent/null; lodging: `date + nights − 1 <= trip.end_date` (cross-field) |

### ClaimIn

| Field | Type | Rules |
|---|---|---|
| `employee_id` | str | required; non-empty after trim; at most 200 characters as submitted; trimmed |
| `trip` | Trip | required |
| `lines` | list[ExpenseLineIn] | at least 1, at most 50 |

Bounds (amount, trip length, lines, text lengths) and employee ID trimming come from the M06
security amendment (spec FR-002, Clarifications "M06 security").

Cross-field errors are collected together in one claim-level validator (research R-06), with
locations such as `trip.end_date`, `lines.2.date`, `lines.0.nights`.

## Stored / output models

### Claim (response of POST /claims, GET /claims/{id}, items of GET /claims)

`ClaimIn` fields plus `id: int`; each line additionally has `line_no: int` (1-based, submission
order within the claim). Lodging lines always show `nights` (1 if it was omitted); other lines show
`nights: null`.

### PriorLine (internal, not exposed)

`claim_id`, `line_no`, `date`, `amount`, `currency`, `merchant` — lines from the same employee's
earlier claims, passed to `check_claim` for duplicate detection (R-11).

### Citation

| Field | Type |
|---|---|
| `doc_id` | str, e.g. `POL-MEALS` |
| `sections` | list[str], e.g. `["1", "3"]` |

### Violation

| Field | Type | Notes |
|---|---|---|
| `rule_id` | enum `RuleId` | `CURRENCY_UNSUPPORTED`, `RECEIPT_MISSING`, `DUPLICATE`, `MEALS_DAILY_LIMIT`, `LODGING_NIGHTLY_CAP` — defined once in `schemas.py`, re-exported from `claims/rules.py` |
| `line_nos` | list[int] | affected lines, ascending |
| `date` | date \| null | the day (meals) or night (lodging); null for per-line rules |
| `excess_usd` | Decimal \| null | amount rejected by this violation for `MEALS_DAILY_LIMIT` and `LODGING_NIGHTLY_CAP`; null for the other rules |
| `message` | str | plain language, includes amounts and the limit |
| `citation` | Citation | per research R-09 table |

### LineResult

| Field | Type | Notes |
|---|---|---|
| `line_no` | int | |
| `claimed_usd` | Decimal \| null | null only for unsupported currency |
| `reimbursable_usd` | Decimal | ≥ 0 |
| `rejected_usd` | Decimal \| null | `claimed_usd − reimbursable_usd`; null when `claimed_usd` is null |
| `flagged_for_review` | bool | true for duplicates (FR-015) |

### PerDiem

`city` (as submitted), `daily_rate_usd`, `days` (calendar days inclusive), `amount_usd`, `citation`.

### CheckResult

`claim_id`, `lines: list[LineResult]` (in `line_no` order), `violations: list[Violation]` (sorted per
R-09), `per_diem: PerDiem`, `lines_reimbursable_usd`, `total_reimbursable_usd`
(= `lines_reimbursable_usd + per_diem.amount_usd`). Computed on request; never stored.

## Policy (frozen dataclass, `claims/policy.py`)

| Field | Source |
|---|---|
| `currency_rates: Mapping[str, Decimal]` | POL-CURRENCY §2 table |
| `meals_daily_limit_usd: Decimal` | POL-MEALS §1 |
| `lodging_caps_usd: Mapping[str, Decimal]`, `lodging_default_cap_usd` | POL-LODGING §1 table |
| `per_diem_rates_usd: Mapping[str, Decimal]`, `per_diem_default_rate_usd` | POL-PERDIEM §1 table |
| `travel_day_fraction: Decimal` | POL-PERDIEM §2 (`75%` → `0.75`) |
| `same_day_fraction: Decimal` | POL-PERDIEM §3 |
| `receipt_threshold_usd: Decimal` | POL-RECEIPTS §1 |
| `sections: Mapping[str, frozenset[str]]` | `doc_id` → section numbers present, for citation checks |

City keys are stored case-folded; lookups case-fold and trim the trip city.

## Storage (SQLite, `claims/store.py`)

```text
claims
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  employee_id   TEXT NOT NULL
  city          TEXT NOT NULL
  start_date    TEXT NOT NULL   -- ISO date
  end_date      TEXT NOT NULL

expense_lines
  claim_id          INTEGER NOT NULL REFERENCES claims(id)
  line_no           INTEGER NOT NULL
  date              TEXT NOT NULL      -- ISO date
  category          TEXT NOT NULL
  merchant          TEXT NOT NULL
  amount            TEXT NOT NULL      -- Decimal string, never REAL
  currency          TEXT NOT NULL
  receipt_attached  INTEGER NOT NULL   -- 0/1
  nights            INTEGER            -- NULL for non-lodging
  PRIMARY KEY (claim_id, line_no)

INDEX claims(employee_id, id)
```

No updates or deletes are implemented (FR-006). There is no state machine: claims have no status.

## Seed coverage

`data/seed/claims.json`, inserted in this order. Expected totals are computed by hand in the task
that writes the file.

| # | Employee | Trip | Purpose | expected_rules |
|---|---|---|---|---|
| 1 | E-001 | Berlin, 3 days | clean: USD meals under limit, lodging under cap, receipts | — |
| 2 | E-001 | London, same day | clean: same-day per diem, 18.00 GBP transport without receipt (22.86 USD) | — |
| 3 | E-002 | Paris, 4 days | EUR meals over 75 USD on one day (two lines, line-order split) | MEALS_DAILY_LIMIT |
| 4 | E-002 | London, 2 days | GBP lodging night over 220 cap | LODGING_NIGHTLY_CAP |
| 5 | E-002 | Berlin, 4 days | one EUR lodging line for 3 nights over 180 cap | LODGING_NIGHTLY_CAP |
| 6 | E-003 | Mumbai, 2 days | INR 2083.75 (→ 25.01 USD) without receipt; a 25.00 USD line without receipt is fine | RECEIPT_MISSING |
| 7 | E-003 | Tokyo, 2 days | one JPY line | CURRENCY_UNSUPPORTED |
| 8 | E-003 | Berlin, 2 days | same taxi twice in one claim | DUPLICATE |
| 9 | E-004 | Paris, 2 days | original line for claim 10 | — |
| 10 | E-004 | Paris, 2 days | repeats a line of claim 9 with merchant in different case | DUPLICATE |
| 11 | E-004 | London, 2 days | meal without receipt plus valid meal same day: rejected line counts 0, no meals violation | RECEIPT_MISSING |
| 12 | E-001 | Madrid, 3 days | clean boundary: meals exactly 75.00 USD, lodging exactly 140.00 USD | — |

Covered: every rule ID; duplicate within and across claims; same-day and multi-day trips;
multi-night lodging; EUR, GBP and INR; four clean claims (1, 2, 9, 12).
