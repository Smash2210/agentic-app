# Research & Design Decisions: Claims API

No `NEEDS CLARIFICATION` items remained in Technical Context. Each entry below records a design
decision the spec leaves open, with rationale and rejected alternatives.

## R-01 Dependencies

- **Decision**: Add `fastapi` and `uvicorn` as runtime dependencies and `httpx` as a dev dependency
  (`uv add fastapi uvicorn`, `uv add --dev httpx`). Nothing else.
- **Rationale**:
  - `fastapi`: HTTP routing plus Pydantic v2 request validation that produces per-field 422 errors
    (FR-002) with no extra code. Brings Pydantic v2, which the stack already names.
  - `uvicorn`: ASGI server needed to run the service locally (quickstart).
  - `httpx`: required by `fastapi.testclient.TestClient`; tests only, so dev group.
- **Alternatives considered**: stdlib `http.server` (hand-written validation and JSON encoding, more
  code to test); Flask (no built-in Pydantic validation); SQLAlchemy/SQLModel (rejected by
  Principle VI: stdlib `sqlite3` is enough for two tables).

## R-02 Policy loading and parsing

- **Decision**: `load_policy(policy_dir) -> Policy` reads the five Markdown files once at app start
  and returns a frozen dataclass (mappings wrapped in `MappingProxyType`). It extracts:
  - `doc_id:` line and `## N. Title` section numbers for every file (used to verify citations);
  - Markdown tables: currency rates (POL-CURRENCY §2), lodging caps (POL-LODGING §1), per diem rates
    (POL-PERDIEM §1); the `Any other city` row becomes the default;
  - bold values from prose with one anchored pattern each, scoped to its section: meals limit
    `**75 USD per calendar day**` (POL-MEALS §1), receipt threshold `**over 25 USD**`
    (POL-RECEIPTS §1), travel-day percentage `**75%**` (POL-PERDIEM §2), same-day percentage
    `**one day at 75%**` (POL-PERDIEM §3).
  - Each pattern must match exactly once, otherwise `PolicyError` names the file and section; the app
    refuses to start and tests fail.
- **Rationale**: FR-011 and Principle II: no number in Python. Failing loudly means a policy edit
  that the parser cannot read is caught immediately rather than silently using a stale value.
- **Alternatives considered**: a separate YAML/JSON copy of the numbers (two sources of truth, can
  drift); hard-coded constants with a test comparing them to the Markdown (still numbers in code).

## R-03 Claim identity and submission order

- **Decision**: Claim IDs are SQLite `INTEGER PRIMARY KEY AUTOINCREMENT`. A higher ID means later
  submission. Lines have a 1-based `line_no` within their claim.
- **Rationale**: One value gives both identity (FR-003) and submission order (FR-015 "earliest
  submitted", list order in FR-004) without a clock (Principle III).
- **Alternatives considered**: UUIDs plus a `submitted_at` timestamp (needs a clock and a tiebreak).

## R-04 Money handling

- **Decision**: `Decimal` end to end. `money.to_cents(x)` = `x.quantize(Decimal("0.01"),
  ROUND_HALF_UP)` is the only rounding function. Conversion: `to_cents(amount * rate)` per line.
  Per diem: `to_cents(rate * travel_pct * travel_days + rate * full_days)`; with current rates every
  term is already exact, so rounding once at the end equals rounding per day. SQLite columns holding
  money are `TEXT` storing `str(Decimal)`; read back with `Decimal(text)`.
- **Rationale**: Principle IV; POL-CURRENCY §3; POL-PERDIEM §4.
- **Note**: the 2-decimal precision (`Decimal("0.01")` in `to_cents`) is fixed by Constitution IV and
  POL-CURRENCY §3. It is the one permitted numeric constant in the money path; every other number
  comes from the `Policy` object.
- **Alternatives considered**: integer cents (loses the original amount's exact form, e.g. INR rates
  of 0.012 produce sub-cent values before rounding); REAL columns (float, forbidden).

## R-05 Money in JSON

- **Decision**: Requests must send money as JSON strings (`"amount": "12.50"`). A JSON number is
  rejected with 422 ("amount must be a string such as \"12.50\""). Responses serialise all money as
  strings with exactly 2 decimals (original `amount` echoed as submitted).
- **Rationale**: A JSON number is parsed as a float before Pydantic sees it, which Principle IV
  forbids. Strings keep the exact value and make the rule easy to test.
- **Alternatives considered**: accept numbers and convert via `str(float)` (float still touched;
  rejected).
- **Review point**: this is a client-visible choice not dictated by the spec.

## R-06 Validation and error reporting (FR-002)

- **Decision**: Pydantic models in `schemas.py` validate field-level rules (required fields,
  non-empty strings, category enum, amount > 0 with ≤ 2 decimal places, nights integer ≥ 1 and only on
  lodging, ≥ 1 line). Cross-field rules (end ≥ start, each line date within the trip, last night ≤ end
  date) run in a claim-level `model_validator(mode="after")` that collects **all** cross-field errors
  and raises them together, each with its location (e.g. `lines.2.date`). FastAPI returns the
  standard 422 body listing every error with `loc` and `msg`.
- **Limitation**: the claim-level validator runs only when every field is individually valid, so a
  request with both a malformed amount and an out-of-trip date first reports the amount; the date is
  reported on resubmission. Each response still names every error it can evaluate.
- **Rationale**: Standard FastAPI behaviour, no custom error framework (Principle VI).
- **Alternatives considered**: a hand-written validator collecting everything in one pass
  (duplicates Pydantic's work; more code to test).
- **Review point (resolved 2026-11-24)**: two-stage reporting accepted; spec SC-006 amended to
  "names each invalid field it can evaluate; cross-field errors are reported once the fields they
  compare are valid".

## R-07 Text normalisation

- **Decision**:
  - Currency code: trimmed and upper-cased on input; stored normalised. Any non-empty code is
    accepted (FR-013); unsupported codes are found at check time.
  - Merchant: stored as submitted; duplicate comparison uses `merchant.strip().casefold()`
    (clarification Q6).
  - City: stored as submitted; policy lookup uses `city.strip().casefold()` against table keys.
- **Rationale**: Matches spec edge cases; currency normalisation avoids "eur" being treated as an
  unsupported currency.
- **Review point (resolved 2026-11-24)**: currency upper-casing accepted and added to spec.md
  Clarifications.

## R-08 Rule evaluation order inside `check_claim`

- **Decision**: For each line in `line_no` order:
  1. **Currency** (FR-013): no rate → `CURRENCY_UNSUPPORTED`; `claimed_usd`/`rejected_usd` = None,
     reimbursable 0. Otherwise `claimed_usd = to_cents(amount × rate)`.
  2. **Receipt** (FR-014): supported currency, `claimed_usd > threshold`, no receipt →
     `RECEIPT_MISSING`, reimbursable 0.
  3. **Duplicate** (FR-015): key `(date, amount, currency, merchant_norm)` seen in `prior_lines` or an
     earlier line of this claim → `DUPLICATE`, reimbursable 0, `flagged_for_review = True`. Runs for
     every line, including unsupported-currency lines.

  A line can collect several of these violations. Then:

  4. **Meals** (FR-016): per date, over meal lines not rejected above, in `line_no` order, pay
     `min(claimed_usd, remaining)`; one `MEALS_DAILY_LIMIT` violation per date with any excess.
  5. **Lodging** (FR-017): split each non-rejected lodging line into per-night shares (R-10); per
     night, in `line_no` order, pay `min(share, remaining)`; one `LODGING_NIGHTLY_CAP` violation per
     night with any excess; line reimbursable = sum of paid shares.
  6. **Per diem** (FR-018) from the trip only.

  `total = sum(line reimbursable) + per_diem`.
- **Rationale**: Matches the order requested for the plan and clarifications Q2/Q7 (rejected lines
  count 0 toward limits; fill in line order).

## R-09 Check result shape

- **Decision**:
  - `Violation`: `rule_id`, `line_nos` (1-based, ascending), `date` (the day/night for
    `MEALS_DAILY_LIMIT` / `LODGING_NIGHTLY_CAP`, else null), `excess_usd` (amount rejected by that
    violation for `MEALS_DAILY_LIMIT` / `LODGING_NIGHTLY_CAP`, else null), `message`, `citation`
    (`doc_id`, `sections: list[str]`). Duplicate messages name the original
    (`"duplicate of claim 3 line 2"` or `"duplicate of line 1 in this claim"`).
  - Violations sorted by rule order (as R-08), then date, then first line number.
  - `LineResult`: `line_no`, `claimed_usd`, `reimbursable_usd`, `rejected_usd`,
    `flagged_for_review`.
  - `PerDiem`: `city`, `daily_rate_usd`, `days`, `amount_usd`, `citation`.
  - `CheckResult`: `claim_id`, `lines`, `violations`, `per_diem`, `lines_reimbursable_usd`,
    `total_reimbursable_usd`.
- **Citations per rule** (each section verified to exist at load):

  | Rule ID | Citation |
  |---|---|
  | `CURRENCY_UNSUPPORTED` | POL-CURRENCY §2 |
  | `RECEIPT_MISSING` | POL-RECEIPTS §1, §2 |
  | `DUPLICATE` | POL-RECEIPTS §3, §4 |
  | `MEALS_DAILY_LIMIT` | POL-MEALS §1, §3 |
  | `LODGING_NIGHTLY_CAP` | POL-LODGING §1, §2, §3 |
  | per diem | POL-PERDIEM §1, §2 (multi-day) or §1, §3 (same-day) |

- **Rationale**: FR-008/FR-009/FR-010; `line_nos` is a list because a daily or nightly limit spans
  several lines.

## R-10 Multi-night lodging split

- **Decision**: `share = (claimed_usd / nights)` rounded **down** to cents (`ROUND_DOWN`) for every
  night except the last; the last night gets `claimed_usd − share × (nights − 1)`. Night dates are
  `date + k` for `k in 0..nights−1`.
- **Rationale**: Clarification Q5; shares always sum exactly to the line amount, and rounding down
  means the leftover is never negative.
- **Amended 2026-11-24 (M03)**: the original rule rounded each share half-up. For 0.02 USD over 4
  nights that gives 0.01 × 3 and −0.01 on the last night; the negative share freed one cent of that
  night's cap for another line (found by the test-generator subagent; see
  `evidence/M03-testing/defect.md`).

## R-11 Prior lines for duplicates

- **Decision**: `store.prior_lines(employee_id, before_claim_id)` returns every line of that
  employee's claims with a lower ID, as `PriorLine(claim_id, line_no, date, amount, currency,
  merchant)`. The API passes them to `check_claim`.
- **Rationale**: Keeps `rules.py` pure; earlier claims are unaffected by later ones (SC-005).

## R-12 App wiring and configuration

- **Decision**: `app.create_app(db_path, policy_dir)` loads the policy once, initialises the DB
  schema (`CREATE TABLE IF NOT EXISTS`), stores both on `app.state`, and mounts the router.
  `app.app_from_env()` is a no-argument factory that reads `CLAIMS_DB_PATH` (default
  `data/claims.db`) and `POLICY_DIR` (default `data/policies`) from the environment and calls
  `create_app`. The server runs with `uvicorn agentic_app.app:app_from_env --factory`. The module
  builds **no** app at import time. `agentic_app/__init__.py` imports `agentic_app.llm` only inside
  `main()`, so importing `agentic_app.app` does not run `load_dotenv()` or import `google.genai`
  (analysis U1; tasks T013–T014). A new `sqlite3` connection is opened per request; inserts run in
  one transaction so refused or failed submits store nothing. `data/claims.db` is git-ignored.
- **Rationale**: Importing `agentic_app.app` (including from tests) must have no side effects: no
  policy parsing and no database file created, the same import-side-effect problem fixed in
  `llm.py` in M01. Tests build their own app with a temp DB; no global state in the rules engine.
  `.env` is not read by this code.
- **Alternatives considered**: a module-level `app = create_app(...)` for plain
  `uvicorn agentic_app.app:app` (rejected: parses the policy and creates `data/claims.db` on import);
  a single shared connection (thread-safety issues under uvicorn's thread pool).

## R-13 Seed data

- **Decision**: `data/seed/claims.json` holds 12 claims for 4 synthetic employees (`E-001`…`E-004`),
  in submission order. Each entry is a normal claim body plus `expected_rules` (list of rule IDs) and
  `expected_total_usd` (string). `python -m agentic_app.claims.seed --db PATH` validates each claim
  through the same Pydantic model as the API and inserts them in order; it refuses a non-empty DB.
  Coverage plan is in [data-model.md](data-model.md#seed-coverage).
- **Rationale**: FR-020, SC-001/SC-002; expected values are hand-computed from the policy, so the
  test is independent of the code.

## R-14 Testing approach

- **Decision**: Unit tests per rule against the real `data/policies` (so tests also prove the
  parser), with boundary cases: receipt 25.00/25.01 USD and a converted value landing on 25.005;
  meals 74.99/75.00/75.01 per day; lodging cap ±0.01 for each city; per diem 1, 2 and 4-day trips per
  city; rounding at half a cent. Policy parser tests use small Markdown fixtures in `tmp_path` for
  failure cases. API tests use TestClient with a temp DB. Seed tests load the seed into a temp DB and
  compare every claim's rules and total. No test touches the network or `.env`.
