# Quickstart Run: 001-claims-api (T041)

**Date**: 2026-11-24
**Branch**: `001-claims-api`
**Environment**: macOS, Python 3.12.16, fastapi 0.165.0, uvicorn 0.54.0, pydantic 2.14.4
**Guide**: `specs/001-claims-api/quickstart.md`

Every step of the quickstart was run against a fresh `data/claims.db`, with the real server started
by uvicorn. Requests were sent with `curl`; responses are copied unedited (only `/docs` is truncated).
All data is synthetic.

## Result

All 15 scenarios gave the expected result.

| Scenario | Expected | Got |
|---|---|---|
| List E-001's claims | 200, claims 1, 2, 12 in order | 200, ids [1, 2, 12] |
| Unknown employee | 200, `[]` | 200, `[]` |
| Clean claim 1 | no violations, total 580.00 | no violations, 580.00 |
| Meals limit, claim 3 | one `MEALS_DAILY_LIMIT`, POL-MEALS §1, §3 | one, 2026-02-03, excess 6.00, total 642.90 |
| Multi-night lodging, claim 5 | one `LODGING_NIGHTLY_CAP` per night | three (03-02, 03-03, 03-04), 14.40 each, total 777.00 |
| Duplicate across claims, claim 10 | `DUPLICATE`, flagged for review | `DUPLICATE` on line 1, `flagged_for_review: true`, total 89.10 |
| Original, claim 9 | unchanged, no violations | no violations, 123.66 |
| Unsupported currency, claim 7 | `CURRENCY_UNSUPPORTED`, `claimed_usd: null` | as expected, total 87.50 |
| Submit valid claim | 201 with new id | 201, id 13 |
| Check claim 13 | matches contract example (564.00) | `RECEIPT_MISSING` + two `LODGING_NIGHTLY_CAP` at 36.00, total 564.00 |
| Submit end before start | 422 naming `trip.end_date`, nothing stored | 422 on `trip.end_date` (and on each line's `date`, since no date fits an inverted trip) |
| Amount as JSON number | 422 on that line's amount | 422 on `lines.0.amount`: "money must be sent as a string such as \"12.50\"" |
| Refused submits stored nothing | only claim 13 for E-005 | `[13]` |
| Unknown claim | 404 | 404 `{"detail": "Claim 999 not found"}` |
| Interactive docs | 200 | 200 |

Finding during the run: the seed file's explanation for claim 3 said "excess 6.20"; the correct
excess is 6.00 (43.20 + 37.80 = 81.00, minus the 75.00 limit). The expected total (642.90) and the
code were already right; only the `expected_working` text in `data/seed/claims.json` was corrected.

## 1. Offline test suite

```bash
env -u GOOGLE_API_KEY -u GEMINI_API_KEY uv run pytest -q
```

```text
224 passed, 1 deselected in 0.96s
```

## 2. Load the seed data

```bash
uv run python -m agentic_app.claims.seed --db data/claims.db
```

```text
Loaded 12 claims
exit=0
```

Second run on the same database:

```text
Database data/claims.db is not empty; refusing to load seed data.
exit=1
```

## 3. Run the server

```bash
uv run uvicorn agentic_app.app:app_from_env --factory
```

`CLAIMS_DB_PATH` and `POLICY_DIR` were left unset, so the defaults `data/claims.db` and
`data/policies` were used.

```text
INFO:     Started server process [12104]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

The server was stopped with SIGTERM after the scenarios:

```text
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [12104]
```

## 4. Validation scenarios

### List an employee's claims (US3)

Expected: 200, claims 1, 2, 12 in that order

```bash
curl -s -X GET 'http://127.0.0.1:8000/claims?employee_id=E-001'
```

HTTP 200

```json
[
  {
    "id": 1,
    "employee_id": "E-001",
    "trip": {
      "destination_city": "Berlin",
      "start_date": "2026-01-12",
      "end_date": "2026-01-14"
    },
    "lines": [
      {
        "line_no": 1,
        "date": "2026-01-12",
        "category": "meal",
        "merchant": "Cafe Mitte",
        "amount": "40.00",
        "currency": "USD",
        "receipt_attached": true,
        "nights": null
      },
      {
        "line_no": 2,
        "date": "2026-01-13",
        "category": "meal",
        "merchant": "Brauhaus Nord",
        "amount": "30.00",
        "currency": "USD",
        "receipt_attached": true,
        "nights": null
      },
      {
        "line_no": 3,
        "date": "2026-01-12",
        "category": "lodging",
        "merchant": "Hotel Spree",
        "amount": "340.00",
        "currency": "USD",
        "receipt_attached": true,
        "nights": 2
      },
      {
        "line_no": 4,
        "date": "2026-01-14",
        "category": "transport",
        "merchant": "BVG U-Bahn",
        "amount": "20.00",
        "currency": "USD",
        "receipt_attached": false,
        "nights": null
      }
    ]
  },
  {
    "id": 2,
    "employee_id": "E-001",
    "trip": {
      "destination_city": "London",
      "start_date": "2026-01-20",
      "end_date": "2026-01-20"
    },
    "lines": [
      {
        "line_no": 1,
        "date": "2026-01-20",
        "category": "transport",
        "merchant": "Heathrow Express",
        "amount": "18.00",
        "currency": "GBP",
        "receipt_attached": false,
        "nights": null
      },
      {
        "line_no": 2,
        "date": "2026-01-20",
        "category": "meal",
        "merchant": "Pret Holborn",
        "amount": "20.00",
        "currency": "GBP",
        "receipt_attached": true,
        "nights": null
      }
    ]
  },
  {
    "id": 12,
    "employee_id": "E-001",
    "trip": {
      "destination_city": "Madrid",
      "start_date": "2026-05-04",
      "end_date": "2026-05-06"
    },
    "lines": [
      {
        "line_no": 1,
        "date": "2026-05-04",
        "category": "meal",
        "merchant": "Casa Lucio",
        "amount": "50.00",
        "currency": "USD",
        "receipt_attached": true,
        "nights": null
      },
      {
        "line_no": 2,
        "date": "2026-05-04",
        "category": "meal",
        "merchant": "Mercado San Miguel",
        "amount": "25.00",
        "currency": "USD",
        "receipt_attached": false,
        "nights": null
      },
      {
        "line_no": 3,
        "date": "2026-05-04",
        "category": "lodging",
        "merchant": "Hotel Gran Via",
        "amount": "140.00",
        "currency": "USD",
        "receipt_attached": true,
        "nights": 1
      }
    ]
  }
]
```

### Unknown employee (US3)

Expected: 200, []

```bash
curl -s -X GET 'http://127.0.0.1:8000/claims?employee_id=E-999'
```

HTTP 200

```json
[]
```

### Clean claim (US1)

Expected: no violations; total = lines + per diem (580.00)

```bash
curl -s -X GET 'http://127.0.0.1:8000/claims/1/check'
```

HTTP 200

```json
{
  "claim_id": 1,
  "lines": [
    {
      "line_no": 1,
      "claimed_usd": "40.00",
      "reimbursable_usd": "40.00",
      "rejected_usd": "0.00",
      "flagged_for_review": false
    },
    {
      "line_no": 2,
      "claimed_usd": "30.00",
      "reimbursable_usd": "30.00",
      "rejected_usd": "0.00",
      "flagged_for_review": false
    },
    {
      "line_no": 3,
      "claimed_usd": "340.00",
      "reimbursable_usd": "340.00",
      "rejected_usd": "0.00",
      "flagged_for_review": false
    },
    {
      "line_no": 4,
      "claimed_usd": "20.00",
      "reimbursable_usd": "20.00",
      "rejected_usd": "0.00",
      "flagged_for_review": false
    }
  ],
  "violations": [],
  "per_diem": {
    "city": "Berlin",
    "daily_rate_usd": "60.00",
    "days": 3,
    "amount_usd": "150.00",
    "citation": {
      "doc_id": "POL-PERDIEM",
      "sections": [
        "1",
        "2"
      ]
    }
  },
  "lines_reimbursable_usd": "430.00",
  "total_reimbursable_usd": "580.00"
}
```

### Meals limit (US1)

Expected: one MEALS_DAILY_LIMIT, citation POL-MEALS §1, §3

```bash
curl -s -X GET 'http://127.0.0.1:8000/claims/3/check'
```

HTTP 200

```json
{
  "claim_id": 3,
  "lines": [
    {
      "line_no": 1,
      "claimed_usd": "388.80",
      "reimbursable_usd": "388.80",
      "rejected_usd": "0.00",
      "flagged_for_review": false
    },
    {
      "line_no": 2,
      "claimed_usd": "43.20",
      "reimbursable_usd": "43.20",
      "rejected_usd": "0.00",
      "flagged_for_review": false
    },
    {
      "line_no": 3,
      "claimed_usd": "37.80",
      "reimbursable_usd": "31.80",
      "rejected_usd": "6.00",
      "flagged_for_review": false
    },
    {
      "line_no": 4,
      "claimed_usd": "21.60",
      "reimbursable_usd": "21.60",
      "rejected_usd": "0.00",
      "flagged_for_review": false
    }
  ],
  "violations": [
    {
      "rule_id": "MEALS_DAILY_LIMIT",
      "line_nos": [
        3
      ],
      "date": "2026-02-03",
      "excess_usd": "6.00",
      "message": "Meals on 2026-02-03: 81.00 USD is over the daily limit of 75.00 USD; 6.00 USD rejected.",
      "citation": {
        "doc_id": "POL-MEALS",
        "sections": [
          "1",
          "3"
        ]
      }
    }
  ],
  "per_diem": {
    "city": "Paris",
    "daily_rate_usd": "45.00",
    "days": 4,
    "amount_usd": "157.50",
    "citation": {
      "doc_id": "POL-PERDIEM",
      "sections": [
        "1",
        "2"
      ]
    }
  },
  "lines_reimbursable_usd": "485.40",
  "total_reimbursable_usd": "642.90"
}
```

### Multi-night lodging (US1)

Expected: one LODGING_NIGHTLY_CAP per night

```bash
curl -s -X GET 'http://127.0.0.1:8000/claims/5/check'
```

HTTP 200

```json
{
  "claim_id": 5,
  "lines": [
    {
      "line_no": 1,
      "claimed_usd": "583.20",
      "reimbursable_usd": "540.00",
      "rejected_usd": "43.20",
      "flagged_for_review": false
    },
    {
      "line_no": 2,
      "claimed_usd": "27.00",
      "reimbursable_usd": "27.00",
      "rejected_usd": "0.00",
      "flagged_for_review": false
    }
  ],
  "violations": [
    {
      "rule_id": "LODGING_NIGHTLY_CAP",
      "line_nos": [
        1
      ],
      "date": "2026-03-02",
      "excess_usd": "14.40",
      "message": "Night of 2026-03-02: lodging 194.40 USD is over the Berlin cap of 180.00 USD; 14.40 USD rejected.",
      "citation": {
        "doc_id": "POL-LODGING",
        "sections": [
          "1",
          "2",
          "3"
        ]
      }
    },
    {
      "rule_id": "LODGING_NIGHTLY_CAP",
      "line_nos": [
        1
      ],
      "date": "2026-03-03",
      "excess_usd": "14.40",
      "message": "Night of 2026-03-03: lodging 194.40 USD is over the Berlin cap of 180.00 USD; 14.40 USD rejected.",
      "citation": {
        "doc_id": "POL-LODGING",
        "sections": [
          "1",
          "2",
          "3"
        ]
      }
    },
    {
      "rule_id": "LODGING_NIGHTLY_CAP",
      "line_nos": [
        1
      ],
      "date": "2026-03-04",
      "excess_usd": "14.40",
      "message": "Night of 2026-03-04: lodging 194.40 USD is over the Berlin cap of 180.00 USD; 14.40 USD rejected.",
      "citation": {
        "doc_id": "POL-LODGING",
        "sections": [
          "1",
          "2",
          "3"
        ]
      }
    }
  ],
  "per_diem": {
    "city": "Berlin",
    "daily_rate_usd": "60.00",
    "days": 4,
    "amount_usd": "210.00",
    "citation": {
      "doc_id": "POL-PERDIEM",
      "sections": [
        "1",
        "2"
      ]
    }
  },
  "lines_reimbursable_usd": "567.00",
  "total_reimbursable_usd": "777.00"
}
```

### Duplicate across claims (US1)

Expected: DUPLICATE, flagged_for_review: true

```bash
curl -s -X GET 'http://127.0.0.1:8000/claims/10/check'
```

HTTP 200

```json
{
  "claim_id": 10,
  "lines": [
    {
      "line_no": 1,
      "claimed_usd": "23.76",
      "reimbursable_usd": "0.00",
      "rejected_usd": "23.76",
      "flagged_for_review": true
    },
    {
      "line_no": 2,
      "claimed_usd": "21.60",
      "reimbursable_usd": "21.60",
      "rejected_usd": "0.00",
      "flagged_for_review": false
    }
  ],
  "violations": [
    {
      "rule_id": "DUPLICATE",
      "line_nos": [
        1
      ],
      "date": null,
      "excess_usd": null,
      "message": "Line 1: duplicate of claim 9 line 1; not reimbursed and flagged for review.",
      "citation": {
        "doc_id": "POL-RECEIPTS",
        "sections": [
          "3",
          "4"
        ]
      }
    }
  ],
  "per_diem": {
    "city": "Paris",
    "daily_rate_usd": "45.00",
    "days": 2,
    "amount_usd": "67.50",
    "citation": {
      "doc_id": "POL-PERDIEM",
      "sections": [
        "1",
        "2"
      ]
    }
  },
  "lines_reimbursable_usd": "21.60",
  "total_reimbursable_usd": "89.10"
}
```

### Original of that duplicate is unchanged (US1)

Expected: no violations

```bash
curl -s -X GET 'http://127.0.0.1:8000/claims/9/check'
```

HTTP 200

```json
{
  "claim_id": 9,
  "lines": [
    {
      "line_no": 1,
      "claimed_usd": "23.76",
      "reimbursable_usd": "23.76",
      "rejected_usd": "0.00",
      "flagged_for_review": false
    },
    {
      "line_no": 2,
      "claimed_usd": "32.40",
      "reimbursable_usd": "32.40",
      "rejected_usd": "0.00",
      "flagged_for_review": false
    }
  ],
  "violations": [],
  "per_diem": {
    "city": "Paris",
    "daily_rate_usd": "45.00",
    "days": 2,
    "amount_usd": "67.50",
    "citation": {
      "doc_id": "POL-PERDIEM",
      "sections": [
        "1",
        "2"
      ]
    }
  },
  "lines_reimbursable_usd": "56.16",
  "total_reimbursable_usd": "123.66"
}
```

### Unsupported currency (US1)

Expected: CURRENCY_UNSUPPORTED, claimed_usd: null

```bash
curl -s -X GET 'http://127.0.0.1:8000/claims/7/check'
```

HTTP 200

```json
{
  "claim_id": 7,
  "lines": [
    {
      "line_no": 1,
      "claimed_usd": null,
      "reimbursable_usd": "0.00",
      "rejected_usd": null,
      "flagged_for_review": false
    },
    {
      "line_no": 2,
      "claimed_usd": "20.00",
      "reimbursable_usd": "20.00",
      "rejected_usd": "0.00",
      "flagged_for_review": false
    }
  ],
  "violations": [
    {
      "rule_id": "CURRENCY_UNSUPPORTED",
      "line_nos": [
        1
      ],
      "date": null,
      "excess_usd": null,
      "message": "Line 1: currency JPY is not supported; not reimbursed. Resubmit it in a supported currency.",
      "citation": {
        "doc_id": "POL-CURRENCY",
        "sections": [
          "2"
        ]
      }
    }
  ],
  "per_diem": {
    "city": "Tokyo",
    "daily_rate_usd": "45.00",
    "days": 2,
    "amount_usd": "67.50",
    "citation": {
      "doc_id": "POL-PERDIEM",
      "sections": [
        "1",
        "2"
      ]
    }
  },
  "lines_reimbursable_usd": "20.00",
  "total_reimbursable_usd": "87.50"
}
```

### Submit valid claim (US2)

Expected: 201 with new id

```bash
curl -s -X POST 'http://127.0.0.1:8000/claims' \
  -H 'Content-Type: application/json' \
  -d '{"employee_id": "E-005", "trip": {"destination_city": "Berlin", "start_date": "2026-03-10", "end_date": "2026-03-12"}, "lines": [{"date": "2026-03-10", "category": "meal", "merchant": "Cafe Roma", "amount": "50.00", "currency": "EUR", "receipt_attached": true}, {"date": "2026-03-10", "category": "meal", "merchant": "Imbiss 24", "amount": "30.00", "currency": "USD", "receipt_attached": false}, {"date": "2026-03-10", "category": "lodging", "merchant": "Hotel Mitte", "amount": "400.00", "currency": "EUR", "receipt_attached": true, "nights": 2}]}'
```

HTTP 201

```json
{
  "id": 13,
  "employee_id": "E-005",
  "trip": {
    "destination_city": "Berlin",
    "start_date": "2026-03-10",
    "end_date": "2026-03-12"
  },
  "lines": [
    {
      "line_no": 1,
      "date": "2026-03-10",
      "category": "meal",
      "merchant": "Cafe Roma",
      "amount": "50.00",
      "currency": "EUR",
      "receipt_attached": true,
      "nights": null
    },
    {
      "line_no": 2,
      "date": "2026-03-10",
      "category": "meal",
      "merchant": "Imbiss 24",
      "amount": "30.00",
      "currency": "USD",
      "receipt_attached": false,
      "nights": null
    },
    {
      "line_no": 3,
      "date": "2026-03-10",
      "category": "lodging",
      "merchant": "Hotel Mitte",
      "amount": "400.00",
      "currency": "EUR",
      "receipt_attached": true,
      "nights": 2
    }
  ]
}
```

### Check the new claim (US1)

Expected: matches the contract example (total 564.00)

```bash
curl -s -X GET 'http://127.0.0.1:8000/claims/13/check'
```

HTTP 200

```json
{
  "claim_id": 13,
  "lines": [
    {
      "line_no": 1,
      "claimed_usd": "54.00",
      "reimbursable_usd": "54.00",
      "rejected_usd": "0.00",
      "flagged_for_review": false
    },
    {
      "line_no": 2,
      "claimed_usd": "30.00",
      "reimbursable_usd": "0.00",
      "rejected_usd": "30.00",
      "flagged_for_review": false
    },
    {
      "line_no": 3,
      "claimed_usd": "432.00",
      "reimbursable_usd": "360.00",
      "rejected_usd": "72.00",
      "flagged_for_review": false
    }
  ],
  "violations": [
    {
      "rule_id": "RECEIPT_MISSING",
      "line_nos": [
        2
      ],
      "date": null,
      "excess_usd": null,
      "message": "Line 2: 30.00 USD is over 25.00 USD and has no receipt; not reimbursed.",
      "citation": {
        "doc_id": "POL-RECEIPTS",
        "sections": [
          "1",
          "2"
        ]
      }
    },
    {
      "rule_id": "LODGING_NIGHTLY_CAP",
      "line_nos": [
        3
      ],
      "date": "2026-03-10",
      "excess_usd": "36.00",
      "message": "Night of 2026-03-10: lodging 216.00 USD is over the Berlin cap of 180.00 USD; 36.00 USD rejected.",
      "citation": {
        "doc_id": "POL-LODGING",
        "sections": [
          "1",
          "2",
          "3"
        ]
      }
    },
    {
      "rule_id": "LODGING_NIGHTLY_CAP",
      "line_nos": [
        3
      ],
      "date": "2026-03-11",
      "excess_usd": "36.00",
      "message": "Night of 2026-03-11: lodging 216.00 USD is over the Berlin cap of 180.00 USD; 36.00 USD rejected.",
      "citation": {
        "doc_id": "POL-LODGING",
        "sections": [
          "1",
          "2",
          "3"
        ]
      }
    }
  ],
  "per_diem": {
    "city": "Berlin",
    "daily_rate_usd": "60.00",
    "days": 3,
    "amount_usd": "150.00",
    "citation": {
      "doc_id": "POL-PERDIEM",
      "sections": [
        "1",
        "2"
      ]
    }
  },
  "lines_reimbursable_usd": "414.00",
  "total_reimbursable_usd": "564.00"
}
```

### Submit invalid claim (US2)

Expected: 422 naming trip.end_date; nothing stored

```bash
curl -s -X POST 'http://127.0.0.1:8000/claims' \
  -H 'Content-Type: application/json' \
  -d '{"employee_id": "E-005", "trip": {"destination_city": "Berlin", "start_date": "2026-03-10", "end_date": "2026-03-09"}, "lines": [{"date": "2026-03-10", "category": "meal", "merchant": "Cafe Roma", "amount": "50.00", "currency": "EUR", "receipt_attached": true}, {"date": "2026-03-10", "category": "meal", "merchant": "Imbiss 24", "amount": "30.00", "currency": "USD", "receipt_attached": false}, {"date": "2026-03-10", "category": "lodging", "merchant": "Hotel Mitte", "amount": "400.00", "currency": "EUR", "receipt_attached": true, "nights": 2}]}'
```

HTTP 422

```json
{
  "detail": [
    {
      "type": "cross_field",
      "loc": [
        "body",
        "trip",
        "end_date"
      ],
      "msg": "end_date must not be before start_date",
      "input": "2026-03-09"
    },
    {
      "type": "cross_field",
      "loc": [
        "body",
        "lines",
        0,
        "date"
      ],
      "msg": "date must be within the trip's start and end dates",
      "input": "2026-03-10"
    },
    {
      "type": "cross_field",
      "loc": [
        "body",
        "lines",
        1,
        "date"
      ],
      "msg": "date must be within the trip's start and end dates",
      "input": "2026-03-10"
    },
    {
      "type": "cross_field",
      "loc": [
        "body",
        "lines",
        2,
        "date"
      ],
      "msg": "date must be within the trip's start and end dates",
      "input": "2026-03-10"
    }
  ]
}
```

### Money as number (US2)

Expected: 422 on that line's amount

```bash
curl -s -X POST 'http://127.0.0.1:8000/claims' \
  -H 'Content-Type: application/json' \
  -d '{"employee_id": "E-005", "trip": {"destination_city": "Berlin", "start_date": "2026-03-10", "end_date": "2026-03-12"}, "lines": [{"date": "2026-03-10", "category": "meal", "merchant": "Cafe Roma", "amount": 12.5, "currency": "EUR", "receipt_attached": true}, {"date": "2026-03-10", "category": "meal", "merchant": "Imbiss 24", "amount": "30.00", "currency": "USD", "receipt_attached": false}, {"date": "2026-03-10", "category": "lodging", "merchant": "Hotel Mitte", "amount": "400.00", "currency": "EUR", "receipt_attached": true, "nights": 2}]}'
```

HTTP 422

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": [
        "body",
        "lines",
        0,
        "amount"
      ],
      "msg": "Value error, money must be sent as a string such as \"12.50\", not a number",
      "input": 12.5,
      "ctx": {
        "error": {}
      }
    }
  ]
}
```

### Nothing stored by the refused submits (US3)

Expected: only the one valid claim (id 13)

```bash
curl -s -X GET 'http://127.0.0.1:8000/claims?employee_id=E-005'
```

HTTP 200

```json
[
  {
    "id": 13,
    "employee_id": "E-005",
    "trip": {
      "destination_city": "Berlin",
      "start_date": "2026-03-10",
      "end_date": "2026-03-12"
    },
    "lines": [
      {
        "line_no": 1,
        "date": "2026-03-10",
        "category": "meal",
        "merchant": "Cafe Roma",
        "amount": "50.00",
        "currency": "EUR",
        "receipt_attached": true,
        "nights": null
      },
      {
        "line_no": 2,
        "date": "2026-03-10",
        "category": "meal",
        "merchant": "Imbiss 24",
        "amount": "30.00",
        "currency": "USD",
        "receipt_attached": false,
        "nights": null
      },
      {
        "line_no": 3,
        "date": "2026-03-10",
        "category": "lodging",
        "merchant": "Hotel Mitte",
        "amount": "400.00",
        "currency": "EUR",
        "receipt_attached": true,
        "nights": 2
      }
    ]
  }
]
```

### Unknown claim

Expected: 404

```bash
curl -s -X GET 'http://127.0.0.1:8000/claims/999/check'
```

HTTP 404

```json
{
  "detail": "Claim 999 not found"
}
```

### Interactive docs

Expected: 200

```bash
curl -s -X GET 'http://127.0.0.1:8000/docs'
```

HTTP 200

```json

    <!DOCTYPE html>
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swag …(truncated)
```

