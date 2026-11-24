# agentic-app — Expense & Travel Policy Copilot

Employees get correct, explainable expense decisions grounded in written policy. Money decisions
are made by code or humans, never by a model. See `.specify/memory/constitution.md`.

## Claims API

A FastAPI service that stores expense claims and checks them against the deterministic policy rules
in `data/policies/*.md`. Spec, plan and contract: `specs/001-claims-api/`. All data is synthetic.

### Install and test

```bash
uv sync
uv run pytest
```

The test suite runs offline and needs no API key.

### Load the seed data

```bash
uv run python -m agentic_app.claims.seed --db data/claims.db
```

Prints `Loaded 12 claims`. It refuses a database that already has claims; delete `data/claims.db` to
start over. `--seed FILE` loads a different seed file.

### Run the server

```bash
CLAIMS_DB_PATH=data/claims.db uv run uvicorn agentic_app.app:app_from_env --factory --reload
```

`POLICY_DIR` (default `data/policies`) sets where the policy documents are read from. Interactive
docs: http://127.0.0.1:8000/docs

### Endpoints

| Method and path | Purpose |
|---|---|
| `POST /claims` | Submit a claim; 201 with its new ID, or 422 listing each invalid field |
| `GET /claims/{id}` | One claim; 404 if unknown |
| `GET /claims?employee_id=E-001` | An employee's claims in submission order |
| `GET /claims/{id}/check` | Policy violations with citations, per-line USD amounts, per diem and total |

Money is always a JSON string such as `"12.50"`, in requests and responses.
