# M07 — Reasoning and structured outputs: `POST /adjudicate`

**Outcome:** a service that solves a multi-step reasoning task and returns validated, structured
results.

| Required | Where |
|---|---|
| The service | `POST /adjudicate` ([src/agentic_app/adjudicate.py](../../src/agentic_app/adjudicate.py), route in `claims/api.py`), spec-first: [specs/002-adjudicate/](../../specs/002-adjudicate/) |
| Multi-step reasoning task | Messy receipt text → expense lines (several items per receipt, several receipts, three currencies, multi-night lodging) → policy check via a tool → flags and explanation |
| Validated, structured results | `Adjudication` (Pydantic): decision, lines, the rules engine's check, flags, unreadable, explanation, usage |
| Live runs | [example-A.json](example-A.json) … [example-D.json](example-D.json), [summary.json](summary.json), [usage.md](usage.md) |
| Tests | [tests/test_adjudicate.py](../../tests/test_adjudicate.py): 26 offline tests with a faked model; full suite 333 passed, coverage 94% (`adjudicate.py` 99%) |

## How it works

```
receipts (text) ──► 1. READ   Gemini, thinking on, one tool: check_claim(lines)
                              tool args validated as a spec 001 claim; errors go back to the model
                    2. CHECK  the M02 rules engine computes every amount, violation and citation
                    3. ANSWER Gemini, response_schema only: flags, unreadable, explanation
                              Pydantic + "no invented amounts" check; 1 retry, then needs_human_review
                    4. DECIDE code: approve | partial | reject | needs_human_review
```

**The model never sets a number or the decision** (constitution Principle III). It reads and
explains; the rules engine and `decide()` do the rest. Items the policy excludes but the engine
cannot see (alcohol, minibar) are left out and **flagged**, and any flag forces human review. That
is the safety net when the model's judgement is wrong. In an early probe it put a beer in a meal
line when only loosely instructed.

## Live results (gemini-3.5-flash-lite, free tier, 2026-11-25)

| Example | Receipts | Lines read | Flags / unreadable | Check total | Decision | Expected |
|---|---|---|---|---|---|---|
| A | Berlin hotel + dinner | lodging 472.50 EUR × 3 nights (rooms + city tax); meal 48.50 EUR | minibar 14.00 EUR (POL-LODGING §4); Riesling 29.00 EUR (POL-MEALS §2) | 772.68 USD | needs_human_review | ✅ |
| B | London taxis + dinner | 2 × transport, 1 × meal 70.00 GBP | — | 306.37 USD (meal over the limit by 13.90) | partial | ✅ |
| C | London taxis | 2 × transport | — | 231.37 USD | approve | ✅ |
| D | smudged taxi receipt | none (no tool call) | "date is unreadable and amount is incomplete" | — | needs_human_review | ✅ |

All four match spec 002 exactly, including every line and flag. The totals are the rules engine's
own, the same figures computed when the spec was written.

**One weakness seen live:** example A's explanation opens with "Your claim has been successfully
processed", while the decision is `needs_human_review`. The explanation is the model's wording. It
cannot change the decision or any amount, but it can sound more final than the result. A tighter
instruction (or checking the explanation's tone against the decision) is a candidate fix for M10's
output guardrails.

## Prompt caching: measured, and why it shows 0

| Probe (same request twice) | Prompt tokens | Cached on 2nd call |
|---|---|---|
| Our stable prefix (instructions + full policy) | 1,705 | **0** |
| Same prefix + spec 001 appended | 7,707 | **4,076** |

- **Explicit caching** (`caches.create`) returns 404 on the AI Studio free tier, even for 7k tokens.
- **Implicit caching** works, but only for a prefix of roughly 4,000 tokens or more, in blocks of
  about that size. Our stable prefix is 1,705 tokens, so every live run shows 0 cached tokens
  ([usage.md](usage.md)).
- **Decision: no padding.** Making the prompt bigger only to trigger the cache would cost more than
  it saves. The design (the instructions and policy are a byte-identical system prefix, with the
  receipts after it) means caching starts by itself once the policy corpus grows past ~4k tokens
  (M08 adds about 15 policy documents). Every response reports `cached_tokens`, so it will show
  when that happens.

## Resilience (free tier)

Free-tier models were often overloaded during the build. Observed: 503 "high demand", 504
"deadline expired", 429 quota, and client read timeouts. So:

- `llm.generate_content()` treats 429/500/503/504 and timeouts as temporary: 3 tries per model
  (5 s, 10 s backoff), then the next model in `GEMINI_FALLBACK_MODELS`.
- One adjudication stays on the model that already answered; `usage.model` says which.
- If every model fails: HTTP **503**, never a guessed decision (FR-210).

## What happens when the model's output is rejected (the reviewer's question)

1. **Tool arguments** that fail spec 001 validation (bad category, date outside the trip, amount as
   a number) are not run. The errors go back to the model as the tool result, so it can correct
   them (`test_invalid_tool_arguments_go_back_to_the_model_as_errors`).
2. **The final answer** must match `ReaderAnswer` (`response_schema` + Pydantic), and its
   explanation may only mention amounts found on the receipts or in the check result. If not, it
   gets one retry with the reason (`test_invalid_answer_is_retried_once_with_the_reason`,
   `test_explanation_may_not_invent_amounts`).
3. **Still invalid:** the request still succeeds, with `needs_human_review` and the reason in
   `review_reasons`, never a 500 (`test_invalid_answer_twice_needs_human_review_not_an_error`).

## Structured-output approaches (course comparison)

| Approach | How | Used? |
|---|---|---|
| Vendor structured output | Gemini `response_schema` from the Pydantic model | **Yes**, plus Pydantic validation, because the schema alone cannot check meaning (invented amounts) |
| Retry-based (`instructor`) | Validate, re-ask with the error | **Yes, the same idea, written by hand** in `_Run.answer()`, so no extra dependency (Principle VI) |
| Constrained decoding (`outlines`) | Restrict tokens to the grammar while generating | No: needs a local model; not possible through a hosted API |

## Reproduce

```bash
uv run pytest -q tests/test_adjudicate.py          # offline, no key
uv run python scripts/run_adjudicate_examples.py   # live, needs GOOGLE_API_KEY + GEMINI_MODEL
```
