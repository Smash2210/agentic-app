# Contract: Claims API

JSON over HTTP. Money is always a JSON **string** (research R-05). Dates are `YYYY-MM-DD`.
Field definitions are in [data-model.md](../data-model.md).

## POST /claims — submit a claim (User Story 2)

Request:

```json
{
  "employee_id": "E-001",
  "trip": {"destination_city": "Berlin", "start_date": "2026-03-10", "end_date": "2026-03-12"},
  "lines": [
    {"date": "2026-03-10", "category": "meal", "merchant": "Cafe Roma",
     "amount": "50.00", "currency": "EUR", "receipt_attached": true},
    {"date": "2026-03-10", "category": "meal", "merchant": "Imbiss 24",
     "amount": "30.00", "currency": "USD", "receipt_attached": false},
    {"date": "2026-03-10", "category": "lodging", "merchant": "Hotel Mitte",
     "amount": "400.00", "currency": "EUR", "receipt_attached": true, "nights": 2}
  ]
}
```

Responses:

- **201** — the stored claim: request body plus `"id": 1`, each line with `line_no` (1, 2, 3) and
  `nights` (`null` for non-lodging, the given or default `1` for lodging). Currency is returned
  upper-cased.
- **422** — invalid input; nothing stored. FastAPI's standard body, one entry per error:

  ```json
  {"detail": [
    {"loc": ["body", "lines", 1, "amount"], "msg": "Value error, amount must be greater than 0", "type": "value_error"},
    {"loc": ["body", "trip", "destination_city"], "msg": "...", "type": "..."}
  ]}
  ```

  Cross-field errors (`trip.end_date`, `lines.N.date`, `lines.N.nights`) appear once the fields they
  compare are valid (R-06). An unsupported currency is **not** a 422 (FR-013).

## GET /claims/{id} — one claim (User Story 3)

- **200** — the stored claim, same shape as the POST 201 body.
- **404** — `{"detail": "Claim 99 not found"}`.

## GET /claims?employee_id=E-001 — list an employee's claims (User Story 3)

- **200** — JSON array of claims in submission order (ascending `id`); `[]` if none.
- **422** — `employee_id` query parameter missing.

## GET /claims/{id}/check — policy check (User Story 1)

Read-only; recomputed on every call. For the example claim above:

```json
{
  "claim_id": 1,
  "lines": [
    {"line_no": 1, "claimed_usd": "54.00", "reimbursable_usd": "54.00", "rejected_usd": "0.00", "flagged_for_review": false},
    {"line_no": 2, "claimed_usd": "30.00", "reimbursable_usd": "0.00", "rejected_usd": "30.00", "flagged_for_review": false},
    {"line_no": 3, "claimed_usd": "432.00", "reimbursable_usd": "360.00", "rejected_usd": "72.00", "flagged_for_review": false}
  ],
  "violations": [
    {"rule_id": "RECEIPT_MISSING", "line_nos": [2], "date": null, "excess_usd": null,
     "message": "Line 2: 30.00 USD is over 25.00 USD and has no receipt; not reimbursed.",
     "citation": {"doc_id": "POL-RECEIPTS", "sections": ["1", "2"]}},
    {"rule_id": "LODGING_NIGHTLY_CAP", "line_nos": [3], "date": "2026-03-10", "excess_usd": "36.00",
     "message": "Night of 2026-03-10: lodging 216.00 USD is over the Berlin cap of 180.00 USD; 36.00 USD rejected.",
     "citation": {"doc_id": "POL-LODGING", "sections": ["1", "2", "3"]}},
    {"rule_id": "LODGING_NIGHTLY_CAP", "line_nos": [3], "date": "2026-03-11", "excess_usd": "36.00",
     "message": "Night of 2026-03-11: lodging 216.00 USD is over the Berlin cap of 180.00 USD; 36.00 USD rejected.",
     "citation": {"doc_id": "POL-LODGING", "sections": ["1", "2", "3"]}}
  ],
  "per_diem": {"city": "Berlin", "daily_rate_usd": "60.00", "days": 3, "amount_usd": "150.00",
               "citation": {"doc_id": "POL-PERDIEM", "sections": ["1", "2"]}},
  "lines_reimbursable_usd": "414.00",
  "total_reimbursable_usd": "564.00"
}
```

Worked numbers: 50.00 EUR × 1.08 = 54.00; the 30.00 USD meal has no receipt, so it counts 0 toward
the meal limit and day 10 has no meals violation; 400.00 EUR × 1.08 = 432.00 split 216.00 + 216.00,
each capped at 180.00; per diem 60 × 0.75 + 60 + 60 × 0.75 = 150.00; total 54.00 + 0.00 + 360.00 +
150.00 = 564.00.

- **404** — `{"detail": "Claim 99 not found"}`.

Message wording is not part of the contract; `rule_id`, `line_nos`, `date`, `excess_usd`,
`citation` and all amounts are.

## Python contract: `check_claim` (`agentic_app.claims.rules`)

```text
check_claim(claim: Claim, prior_lines: Sequence[PriorLine], policy: Policy) -> CheckResult
```

- Pure: no I/O, no clock, no randomness, no module-level mutable state, no LLM.
- `prior_lines`: lines of the same employee's claims with a lower claim ID (caller's job).
- Same arguments → equal result. Raises nothing for policy violations; they are data in the result.

## Python contract: `load_policy` (`agentic_app.claims.policy`)

```text
load_policy(policy_dir: Path) -> Policy      # raises PolicyError naming file + section on any parse failure
```

## CLI contract: seed loader

```text
uv run python -m agentic_app.claims.seed --db PATH   # exit 0, prints "Loaded 12 claims"; exit 1 if DB not empty
```
