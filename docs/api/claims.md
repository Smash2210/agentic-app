# Expense & Travel Policy Copilot — Claims API

Submit expense claims and check them against the company's currency, receipts, meals, lodging and
per diem policies. Employees (or tools acting for them) store a claim once, then ask for a policy
check that says what is reimbursable in USD, what is rejected, and which policy section each
decision comes from.

- **Version:** 0.1.0
- **Base URL:** wherever the server runs; locally `http://127.0.0.1:8000` (see the README).
- **Auth:** none.
- **Format:** JSON. Money is always a JSON string such as `"12.50"`, never a number. Checked amounts
  are in USD. Dates are `YYYY-MM-DD`.

Source of truth: [`openapi.json`](openapi.json).

## Endpoints

| Method | Path | Summary |
|---|---|---|
| `POST` | `/claims` | Submit a claim |
| `GET` | `/claims` | List an employee's claims |
| `GET` | `/claims/{claim_id}` | Get a claim |
| `GET` | `/claims/{claim_id}/check` | Check a claim against policy |

## POST /claims — Submit a claim

Stores an expense claim and returns it with its new `id` and a `line_no` (1, 2, ...) on each line.
The claim and all its lines are stored in one transaction. Invalid input is answered with `422`,
listing every error, and nothing is stored. A currency the policy does not support is accepted here
and flagged as `CURRENCY_UNSUPPORTED` when the claim is checked.

Claims cannot be updated or deleted through this API.

**Request body** — [`ClaimIn`](#claimin), required.

Example request (the `ClaimIn` example from the spec):

```bash
curl -X POST http://127.0.0.1:8000/claims \
  -H 'Content-Type: application/json' \
  -d '{
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
  }'
```

**Responses**

| Status | When | Body |
|---|---|---|
| `201` | The claim was stored. | [`Claim`](#claim) |
| `422` | Any field is missing or invalid; nothing is stored. | [`HTTPValidationError`](#httpvalidationerror) |

Example response (`201`, the example request sent to an empty database):

```json
{
  "id": 1,
  "employee_id": "E-001",
  "trip": {"destination_city": "Berlin", "start_date": "2026-03-10", "end_date": "2026-03-12"},
  "lines": [
    {"line_no": 1, "date": "2026-03-10", "category": "meal", "merchant": "Cafe Roma",
     "amount": "50.00", "currency": "EUR", "receipt_attached": true, "nights": null},
    {"line_no": 2, "date": "2026-03-10", "category": "meal", "merchant": "Imbiss 24",
     "amount": "30.00", "currency": "USD", "receipt_attached": false, "nights": null},
    {"line_no": 3, "date": "2026-03-10", "category": "lodging", "merchant": "Hotel Mitte",
     "amount": "400.00", "currency": "EUR", "receipt_attached": true, "nights": 2}
  ]
}
```

## GET /claims — List an employee's claims

Returns every claim the employee has submitted, oldest first (ascending `id`). Returns an empty
list if there are none. `employee_id` must match exactly as it was submitted. Read-only.

**Parameters**

| Name | In | Type | Required | Description |
|---|---|---|---|---|
| `employee_id` | query | string | yes | Employee whose claims to list, e.g. `E-001`. |

```bash
curl 'http://127.0.0.1:8000/claims?employee_id=E-001'
```

**Responses**

| Status | When | Body |
|---|---|---|
| `200` | Always when `employee_id` is given, including when the employee has no claims (`[]`). | array of [`Claim`](#claim) |
| `422` | `employee_id` is missing. | [`HTTPValidationError`](#httpvalidationerror) |

Example response (`200`): a JSON array of claims, each shaped like the `POST /claims` `201` body.

## GET /claims/{claim_id} — Get a claim

Returns one stored claim, in the same shape as the submit response. Read-only.

**Parameters**

| Name | In | Type | Required | Description |
|---|---|---|---|---|
| `claim_id` | path | integer | yes | ID returned when the claim was submitted. |

```bash
curl http://127.0.0.1:8000/claims/1
```

**Responses**

| Status | When | Body |
|---|---|---|
| `200` | The claim exists. | [`Claim`](#claim) |
| `404` | No claim has this ID. | [`NotFound`](#notfound), e.g. `{"detail": "Claim 99 not found"}` |
| `422` | `claim_id` is not an integer. | [`HTTPValidationError`](#httpvalidationerror) |

Example response (`200`): the same body as the `POST /claims` `201` example.

## GET /claims/{claim_id}/check — Check a claim against policy

Checks a stored claim against the expense policies and returns what is reimbursable. Each line is
converted to USD; the receipt, duplicate, meals and lodging rules are applied; the per diem for the
trip is added. Every violation is listed with the policy sections it comes from.

Read-only: the result is computed on every call and never stored. Duplicates are looked for within
the claim and in the same employee's earlier claims (claims with a lower `id`), so a claim's result
does not change when later claims are submitted.

**Parameters**

| Name | In | Type | Required | Description |
|---|---|---|---|---|
| `claim_id` | path | integer | yes | ID returned when the claim was submitted. |

```bash
curl http://127.0.0.1:8000/claims/1/check
```

**Responses**

| Status | When | Body |
|---|---|---|
| `200` | The claim exists. Policy violations are part of a `200` body, not errors. | [`CheckResult`](#checkresult) |
| `404` | No claim has this ID. | [`NotFound`](#notfound), e.g. `{"detail": "Claim 99 not found"}` |
| `422` | `claim_id` is not an integer. | [`HTTPValidationError`](#httpvalidationerror) |

Example response (`200`, for the claim in the `POST /claims` example):

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

## Models

### ClaimIn

Request body of `POST /claims`.

| Field | Type | Required | Description |
|---|---|---|---|
| `employee_id` | string | yes | Employee making the claim, e.g. E-001; must not be blank. |
| `trip` | [`Trip`](#trip) | yes | The trip the expenses belong to. |
| `lines` | array of [`ExpenseLineIn`](#expenselinein), at least 1 | yes | Expense lines, at least one. They are numbered 1, 2, ... in this order. |

### Trip

Used in requests and responses.

| Field | Type | Required | Description |
|---|---|---|---|
| `destination_city` | string | yes | City the trip is to; must not be blank. Sets the lodging cap and per diem rate, matched case-insensitively; a city without its own rate gets the 'any other city' rate. |
| `start_date` | string (date) | yes | First day of the trip. |
| `end_date` | string (date) | yes | Last day of the trip, included. Must not be before `start_date`. |

### ExpenseLineIn

| Field | Type | Required | Description |
|---|---|---|---|
| `date` | string (date) | yes | Day of the expense; must be within the trip's dates. For lodging, the first night. |
| `category` | [`Category`](#category) | yes | Kind of expense. |
| `merchant` | string | yes | Who was paid; must not be blank. Used to detect duplicate lines. |
| `amount` | string | yes | Amount in `currency`, as a JSON string such as `"12.50"` (a JSON number is rejected). Greater than 0, at most 2 decimals. |
| `currency` | string | yes | 3-letter currency code, upper-cased on submit. Supported: USD, EUR, GBP, INR. Any other code is accepted here and flagged as `CURRENCY_UNSUPPORTED` when the claim is checked. |
| `receipt_attached` | boolean | yes | Whether a receipt is attached. A line over 25 USD (after conversion) without a receipt is not reimbursed. |
| `nights` | integer ≥ 1 or null | no | Lodging lines only: number of nights, integer of at least 1, default 1. `date` is the first night; the last night must not be after the trip's end date. Omit (or send null) for other categories. |

### Category

Enum: `meal`, `lodging`, `transport`, `other`.

### Claim

Response of `POST /claims` and `GET /claims/{claim_id}`; items of `GET /claims`.

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | integer | yes | Claim ID, assigned on submit. |
| `employee_id` | string | yes | Employee who made the claim. |
| `trip` | [`Trip`](#trip) | yes | The trip the expenses belong to. |
| `lines` | array of [`ExpenseLine`](#expenseline) | yes | Expense lines, in `line_no` order. |

### ExpenseLine

| Field | Type | Required | Description |
|---|---|---|---|
| `line_no` | integer | yes | Position of the line in the claim, from 1. |
| `date` | string (date) | yes | Day of the expense. For lodging, the first night. |
| `category` | [`Category`](#category) | yes | Kind of expense. |
| `merchant` | string | yes | Who was paid. |
| `amount` | string | yes | Amount in `currency`, as submitted. JSON string. |
| `currency` | string | yes | Currency code, upper-cased. |
| `receipt_attached` | boolean | yes | Whether a receipt is attached. |
| `nights` | integer or null | yes | Lodging: number of nights (1 if it was omitted). Null for other categories. |

### CheckResult

Response of `GET /claims/{claim_id}/check`.

| Field | Type | Required | Description |
|---|---|---|---|
| `claim_id` | integer | yes | The claim that was checked. |
| `lines` | array of [`LineResult`](#lineresult) | yes | One result per line, in `line_no` order. |
| `violations` | array of [`Violation`](#violation) | yes | Every policy violation found; empty if there are none. Sorted by rule (in the order the `rule_id` values are listed), then date, then first line number. |
| `per_diem` | [`PerDiem`](#perdiem) | yes | Per diem for the trip. |
| `lines_reimbursable_usd` | string | yes | Sum of `reimbursable_usd` over all lines, as a JSON string with 2 decimals. |
| `total_reimbursable_usd` | string | yes | `lines_reimbursable_usd` plus `per_diem.amount_usd`, as a JSON string with 2 decimals. |

### LineResult

| Field | Type | Required | Description |
|---|---|---|---|
| `line_no` | integer | yes | The line this result is for. |
| `claimed_usd` | string or null | yes | The line's amount converted to USD, rounded half-up, as a JSON string with 2 decimals. Null when the currency is not supported. |
| `reimbursable_usd` | string | yes | USD reimbursed for this line (0.00 or more), as a JSON string with 2 decimals. |
| `rejected_usd` | string or null | yes | `claimed_usd` minus `reimbursable_usd`, as a JSON string with 2 decimals. Null when `claimed_usd` is null. |
| `flagged_for_review` | boolean | yes | True when the line duplicates an earlier line and was rejected. |

### Violation

| Field | Type | Required | Description |
|---|---|---|---|
| `rule_id` | [`RuleId`](#ruleid) | yes | The rule that was broken. |
| `line_nos` | array of integer | yes | The lines affected, ascending. |
| `date` | string (date) or null | yes | The day (`MEALS_DAILY_LIMIT`) or night (`LODGING_NIGHTLY_CAP`) concerned; null for the other rules. |
| `excess_usd` | string or null | yes | USD rejected by this violation, as a JSON string with 2 decimals. Set only for `MEALS_DAILY_LIMIT` and `LODGING_NIGHTLY_CAP`; null for the other rules. |
| `message` | string | yes | Plain-language explanation with the amounts and the limit. The wording may change; do not parse it. |
| `citation` | [`Citation`](#citation) | yes | Where the rule is in the policy. |

### RuleId

Violation rule IDs, in the order violations are reported. Enum: `CURRENCY_UNSUPPORTED`,
`RECEIPT_MISSING`, `DUPLICATE`, `MEALS_DAILY_LIMIT`, `LODGING_NIGHTLY_CAP`.

### Citation

| Field | Type | Required | Description |
|---|---|---|---|
| `doc_id` | string | yes | Policy document ID, e.g. POL-MEALS. |
| `sections` | array of string | yes | Section numbers in that document, e.g. `["1", "2"]`. |

### PerDiem

| Field | Type | Required | Description |
|---|---|---|---|
| `city` | string | yes | Destination city, as submitted. |
| `daily_rate_usd` | string | yes | Per diem rate for the city, as a JSON string with 2 decimals. |
| `days` | integer | yes | Calendar days of the trip, both ends included. |
| `amount_usd` | string | yes | Per diem paid, as a JSON string with 2 decimals. The first and last day are paid at 75% of the daily rate, the days in between at 100%; a same-day trip is one day at 75%. |
| `citation` | [`Citation`](#citation) | yes | Where the per diem rules are in the policy. |

### NotFound

Error body when no claim has the requested ID.

| Field | Type | Required | Description |
|---|---|---|---|
| `detail` | string | yes | What was not found, e.g. Claim 99 not found. |

### HTTPValidationError

FastAPI's standard validation error body.

| Field | Type | Required | Description |
|---|---|---|---|
| `detail` | array of [`ValidationError`](#validationerror) | no | One entry per error. |

### ValidationError

| Field | Type | Required | Description |
|---|---|---|---|
| `loc` | array of string or integer | yes | Where the error is, e.g. `["body", "lines", 0, "amount"]`. |
| `msg` | string | yes | Human-readable message. |
| `type` | string | yes | Error type, e.g. `missing`, `value_error`. |
| `input` | any | no | The value that was rejected. |
| `ctx` | object | no | Extra context for some error types. |

## Errors

Errors are JSON with a `detail` field. Policy violations are **not** errors: they are returned in a
`200` check result.

| Status | Body | Cause |
|---|---|---|
| `404` | [`NotFound`](#notfound): `{"detail": "Claim 99 not found"}` | `GET /claims/{claim_id}` or `GET /claims/{claim_id}/check` with an ID no claim has. |
| `422` | [`HTTPValidationError`](#httpvalidationerror) | `POST /claims` body invalid (one entry per error, nothing stored); `employee_id` missing on `GET /claims`; `claim_id` not an integer. |

Example `422` (an `amount` sent as a JSON number):

```json
{"detail": [
  {"type": "value_error", "loc": ["body", "lines", 0, "amount"],
   "msg": "Value error, money must be sent as a string such as \"12.50\", not a number",
   "input": 50, "ctx": {"error": {}}}
]}
```

Other status codes (for example `500`) are not specified.
