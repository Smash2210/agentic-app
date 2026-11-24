# Implementation Plan: Adjudicate receipts

**Spec**: [spec.md](spec.md) | **Branch**: `002-adjudicate`

## Approach

Two model phases plus code, in `src/agentic_app/adjudicate.py`:

1. **Read (tools, thinking on).** Gemini gets the receipts and one tool, `check_claim(lines)`.
   Thinking budget 1,024 tokens. It reads the receipts and calls the tool. The code validates the
   tool arguments with spec 001's `ClaimIn` (adding employee, trip and `receipt_attached=True`). If
   they are invalid, it returns the validation errors to the model as the tool result, so the model
   can correct them. If they are valid, it runs the real rules engine and returns the `CheckResult`.
   At most 3 tool turns.
2. **Answer (structured output, no tools).** Gemini returns `ReaderAnswer {flags, unreadable,
   explanation}` with `response_schema`. Pydantic validates it, plus one semantic check: every
   2-decimal amount in the explanation must appear in the lines or the check result (FR-204). If it
   is invalid, it gets one retry with the error appended; if it is still invalid, the request becomes
   needs_human_review (FR-208).
3. **Decide (code).** Build `Adjudication` from the last valid tool call's lines and engine result.
   The decision follows FR-207.

Splitting tools and structured output into separate calls was chosen after a probe: one call with
both was accepted by the API, but the turn after the tool result came back with no text.

## Caching (free tier)

Explicit context caching (`caches.create`) returns 404 on the free tier, even with a 7k-token prompt
(probed 2026-11-24). Implicit caching works: a repeated prefix reported `cached_content_token_count`.
So the system instruction is kept **byte-identical** across requests (instructions + full policy
text) and comes first; the trip and receipts come after it. Usage is reported per request (FR-211)
and measured over repeated runs for the evidence.

## Resilience

`llm.generate_content()` retries 429/500/503 with backoff (5, 10, 20 s), because the free-tier model
often answers 503 under load. After that it raises `ModelUnavailable`, and the API answers 503
(FR-210). Tool timeouts and fallbacks are M09.

## Interfaces

- `POST /adjudicate`: body `AdjudicateRequest`, response `Adjudication`, 422 on invalid input, 503 when
  the model is unavailable.
- `adjudicate(request, prior_lines, policy) -> Adjudication`. The caller supplies the prior lines
  (store), so the function has no database access.
- Schemas in `schemas.py`: `AdjudicateRequest`, `Flag`, `ModelUsage`, `Adjudication`.

## Constitution check

| Principle | How |
|---|---|
| I Spec-first | This spec and plan come before the code |
| II Policy source of truth | The full policy text is given to the model; all numbers in the result come from the engine, which reads the policy files |
| III Deterministic core | The model only reads and explains. Amounts, violations and the decision come from code; the explanation is checked for invented amounts |
| IV Money | Unchanged: the engine does all money arithmetic in Decimal |
| V Test-first, offline | The model is faked in tests; live runs are evidence, not tests |
| VI Simplicity | No new dependency; one module, one route |
