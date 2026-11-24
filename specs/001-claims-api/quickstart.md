# Quickstart: Claims API

Validates the feature end to end on a local machine. No API key or network needed.

## Prerequisites

- Python 3.12 and uv installed; repository cloned.
- `uv sync` (installs fastapi, uvicorn, and httpx for tests).

## 1. Offline test suite

```bash
uv run pytest
```

Expected: all tests pass, including `tests/claims/` (rules boundaries, API, seed). No test needs
`GOOGLE_API_KEY`.

## 2. Load the seed data

```bash
uv run python -m agentic_app.claims.seed --db data/claims.db
```

Expected: `Loaded 12 claims`. Running it again exits with an error because the DB is not empty
(delete `data/claims.db` to start over). Run it from the repository root: the default seed file is
`data/seed/claims.json`; pass `--seed FILE` to load a different one.

## 3. Run the server

```bash
CLAIMS_DB_PATH=data/claims.db uv run uvicorn agentic_app.app:app_from_env --factory --reload
```

Interactive docs: http://127.0.0.1:8000/docs

## 4. Validation scenarios

| Scenario | Request | Expected |
|---|---|---|
| List an employee's claims (US3) | `GET /claims?employee_id=E-001` | 200, claims 1, 2, 12 in that order |
| Unknown employee (US3) | `GET /claims?employee_id=E-999` | 200, `[]` |
| Clean claim (US1) | `GET /claims/1/check` | no violations; total = lines + per diem |
| Meals limit (US1) | `GET /claims/3/check` | one `MEALS_DAILY_LIMIT`, citation POL-MEALS §1, §3 |
| Multi-night lodging (US1) | `GET /claims/5/check` | one `LODGING_NIGHTLY_CAP` per night |
| Duplicate across claims (US1) | `GET /claims/10/check` | `DUPLICATE`, `flagged_for_review: true`; `GET /claims/9/check` unchanged |
| Unsupported currency (US1) | `GET /claims/7/check` | `CURRENCY_UNSUPPORTED`, `claimed_usd: null` |
| Submit valid claim (US2) | `POST /claims` with the body in [contracts/claims-api.md](contracts/claims-api.md) | 201 with new `id`; its check matches the contract example |
| Submit invalid claim (US2) | `POST /claims` with `end_date` before `start_date` | 422 naming `trip.end_date`; nothing stored |
| Money as number (US2) | `POST /claims` with `"amount": 12.5` | 422 on that line's `amount` |
| Unknown claim | `GET /claims/999/check` | 404 |

Every seed claim's expected rules and total are asserted automatically by `tests/claims/test_seed.py`
(SC-001, SC-002).
