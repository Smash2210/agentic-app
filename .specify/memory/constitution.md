<!--
Sync Impact Report
- Version change: (unfilled template) → 1.0.0
- Modified principles (template placeholders → named principles):
  - [PRINCIPLE_1_NAME] → I. Spec-First
  - [PRINCIPLE_2_NAME] → II. Policy Is the Source of Truth
  - [PRINCIPLE_3_NAME] → III. Deterministic Core
  - [PRINCIPLE_4_NAME] → IV. Money Correctness (NON-NEGOTIABLE)
  - [PRINCIPLE_5_NAME] → V. Test-First, Offline
  - (new) VI. Simplicity
- Added sections: Mission, Technical Constraints, Development Workflow, Governance (filled)
- Removed sections: none
- Templates requiring updates: none modified by this command (dependent templates read the
  constitution at runtime); .specify/templates/plan-template.md Constitution Check gate should
  list Principles I–VI when a plan is generated
- Follow-up TODOs: none
-->
# agentic-app Constitution

**Mission**: Employees get correct, explainable expense decisions grounded in written policy.
Money decisions are made by code or humans, never by a model.

agentic-app is an Expense & Travel Policy Copilot built in tiers:

- **Tier 1 (current)**: a deterministic Claims API.
- **Tier 2**: an LLM agent on Google ADK + Gemini.
- **Tier 3**: a multi-agent system using MCP and A2A.

Every tier is bound by this constitution. Later tiers MAY add language understanding and
orchestration, but they MUST call the deterministic core for every money decision.

## Core Principles

### I. Spec-First

- No behaviour exists without a spec in `specs/NNN-*/` (spec.md, plan.md, tasks.md).
- The spec MUST be changed before the code that implements a change in behaviour.
- If a spec is ambiguous or silent, the implementer MUST ask; guessing is forbidden.

Rationale: the spec is the reviewable contract; code that outruns it cannot be verified.

### II. Policy Is the Source of Truth

- Every limit, rate, threshold and rule MUST come from a document in `data/policies/`.
- Every rule in code and every decision it produces MUST cite the policy `doc_id` and section
  (e.g. `POL-MEALS §1`).
- Code MUST NOT invent, hard-code from memory, or approximate a number that is not in policy.
  If policy lacks a needed number, the policy (and spec) is amended first.

Rationale: decisions must be explainable to employees by pointing at the written rule.

### III. Deterministic Core

- The rules engine is pure functions: no I/O, no clock or current-time calls, no randomness,
  no globals, no LLM calls. Dates and all other context are passed in as arguments.
- The same input MUST always produce the same output.
- No model (Tier 2/3 agents included) may compute, approve, or alter a reimbursable amount;
  models may only gather input and explain results the core produced.

Rationale: money decisions must be reproducible, auditable and testable in isolation.

### IV. Money Correctness (NON-NEGOTIABLE)

- Monetary values use `Decimal` only; `float` MUST NOT appear in any money path.
- Each expense line is converted to USD separately, then rounded half-up to 2 decimals.
- Totals are the sum of the rounded lines; a claim total is never converted in one step.
- Limits and thresholds are checked against converted USD amounts (POL-CURRENCY §3–§4).

Rationale: rounding order changes results; one rule, applied everywhere, keeps cents correct.

### V. Test-First, Offline

- Every rule has tests at, just below and just above each boundary in its policy
  (e.g. 25.00 vs 25.01 USD for receipts).
- Every new behaviour gets a test before or with its implementation.
- `uv run pytest` MUST be green with no API key and no network access. Live LLM tests are
  marked `live`, excluded by default, and run only when explicitly requested.

Rationale: boundaries are where policy bugs hide, and the suite must run anywhere.

### VI. Simplicity

- Build the smallest design that meets the spec; no speculative features or abstractions.
- Persistence uses stdlib `sqlite3`.
- No new dependency may be added without a reason written in the feature's plan.md.

Rationale: a learning project stays understandable only if each piece earns its place.

## Technical Constraints

- Stack: Python 3.12, uv, FastAPI, Pydantic v2, SQLite (stdlib `sqlite3`), pytest.
- Package layout: `src/agentic_app/` (src layout).
- Data: all data in the repository is synthetic. Real personal or financial data MUST NOT
  be committed.
- Secrets: `.env` MUST NOT be read, printed or committed by any tool or agent.

## Development Workflow

1. **Specify** → `/speckit-specify` creates `specs/NNN-*/spec.md`.
2. **Clarify** → `/speckit-clarify` resolves ambiguities into the spec.
3. **Plan** → `/speckit-plan`; a human MUST review and approve plan.md before tasks are made.
4. **Tasks** → `/speckit-tasks`.
5. **Analyze** → `/speckit-analyze` checks spec, plan and tasks for consistency.
6. **Implement** → `/speckit-implement`.
7. **Converge** → `/speckit-converge`, then implement again, repeated until no work remains.

A commit is made after each completed task phase, with `uv run pytest` green.

## Governance

- This constitution supersedes other practices and guidance files; CLAUDE.md MUST stay
  consistent with it.
- Amendments are made only by editing this file in a commit that bumps the version and sets
  the Last Amended date.
- Versioning follows semantic versioning: MAJOR for removing or redefining a principle or
  governance rule; MINOR for adding a principle or section or materially expanding guidance;
  PATCH for clarifications and wording.
- Every plan.md MUST include a Constitution Check stating how it satisfies each of
  Principles I–VI; any deviation MUST be justified there and approved at plan review.
- Reviews of specs, plans and code verify compliance with this constitution.

**Version**: 1.0.0 | **Ratified**: 2026-11-24 | **Last Amended**: 2026-11-24
