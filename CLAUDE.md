# agentic-app — Expense & Travel Policy Copilot

## What this is
Learning project built in sprints. Current sprint: Tier 1 Claims API — a FastAPI service that stores
expense claims and checks them against deterministic policy rules. **No LLM calls in Tier 1 code.**

## Stack
Python 3.12, uv, FastAPI, Pydantic v2, SQLite (stdlib sqlite3), pytest.
Package: `src/agentic_app/` (src layout). Gemini wrapper: `src/agentic_app/llm.py` (not used by Tier 1).

## Commands
- Install deps: `uv sync`
- Tests (offline, default): `uv run pytest`
- Live LLM tests: `uv run pytest -m live`  (never run these unless asked)
- Add a dependency: `uv add <pkg>` / dev: `uv add --dev <pkg>`

## Rules
- Spec-driven: work comes from `specs/NNN-*/` (spec.md, plan.md, tasks.md). Do not add behaviour
  that is not in the spec; if the spec is unclear, ask instead of guessing.
- Policy numbers live in `data/policies/*.md`. Code must match them; never invent limits.
- Rules engine must be pure: no I/O, no globals, no current-time calls; pass dates in.
- Money: use `Decimal`, never float. Round half-up to 2 decimals.
- Every new behaviour gets a test. Keep `uv run pytest` green and runnable with no API key.
- Never read or print `.env`. All data in this repo is synthetic.