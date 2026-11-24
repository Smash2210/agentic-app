# Feature Specification: Adjudicate receipts

**Feature Branch**: `002-adjudicate` | **Created**: 2026-11-25 | **Status**: Implemented (M07)

**Input**: An employee sends their trip and the raw text of their receipts, and gets back a
structured, explained adjudication they can trust, without having to type the expense lines in.

## User story (P1): adjudicate receipts

An employee sends their employee ID, the trip (city, start and end date) and one or more receipts as
plain text. They get back: the expense lines read from the receipts, the policy check of those lines
(exactly as spec 001's check computes it), anything the reader could not or should not decide, a
decision, and a short explanation that cites policy sections.

**Independent test**: send the acceptance examples below and compare lines, flags, check result and
decision. With the model replaced by a fake, every branch of the decision can be tested offline.

### Acceptance examples (data/receipts/)

| # | Trip | Receipts | Expected lines | Expected flags | Check (spec 001) | Decision |
|---|---|---|---|---|---|---|
| A | Berlin, 2026-03-10 → 03-13 | r1 hotel, r2 dinner | lodging 472.50 EUR from 03-10, 3 nights (rooms + city tax: taxes count towards the cap, POL-LODGING §2); meal 48.50 EUR on 03-11 (food, water, service) | minibar 14.00 EUR (POL-LODGING §4); wine 29.00 EUR (POL-MEALS §2) | no violations; total 772.68 USD (lines 562.68 + per diem 210.00) | needs_human_review |
| B | London, 2026-04-20 → 04-21 | r3 taxis, r4 dinner | transport 48.00 GBP on 04-20; transport 51.50 GBP on 04-21; meal 70.00 GBP on 04-20 | none | MEALS_DAILY_LIMIT on 04-20, excess 13.90 USD; total 306.37 USD | partial |
| C | London, 2026-04-20 → 04-21 | r3 taxis | the two transport lines | none | no violations; total 231.37 USD | approve |
| D | Paris, 2026-05-04 → 05-05 | r5 unreadable taxi | none (date and amount unreadable) | the receipt is reported as unreadable | none | needs_human_review |

## Requirements

- **FR-201** Input: employee ID, trip (as in spec 001) and 1–10 receipts, each non-empty text of at
  most 5,000 characters. Invalid input is refused with a validation error.
- **FR-202** The reader turns receipts into expense lines with the fields of spec 001 (FR-001). One
  receipt may give several lines (e.g. two journeys), and several items may form one line (e.g. a
  meal). Every line read from a receipt has a receipt attached.
- **FR-203** Lines are checked by the spec 001 policy check, against the employee's stored claims for
  duplicates. Lines that fail spec 001 input validation are not checked; the reader is told why and
  may correct them.
- **FR-204** (constitution Principle III) **Amounts, violations and citations in the result come only
  from the policy check.** The reader never sets an amount or the decision. Any amount mentioned in
  the explanation must be one that appears in the receipts' lines or the check result.
- **FR-205** **Flags**: items the policy excludes but the policy check cannot see are left out of the
  lines and reported as flags with a citation: alcohol and meals already included elsewhere
  (POL-MEALS §2); minibar, room service, laundry, in-room entertainment (POL-LODGING §4).
- **FR-206** **Unreadable**: a receipt whose date, amount or currency cannot be read with confidence
  is reported as unreadable. Missing data is never guessed.
- **FR-207** **Decision**, set by code: `needs_human_review` if there is any flag, any unreadable
  receipt, no checked lines, or the reader's answer is invalid after one retry; otherwise `reject`
  if nothing is reimbursable, `partial` if any amount is rejected or any violation found, `approve`
  if not. Each `needs_human_review` lists its reasons.
- **FR-208** The reader's answer must match a fixed structure; an answer that does not is retried
  once with the reason, then treated as invalid (FR-207). The request never fails because of it.
- **FR-209** Nothing is stored. This is a preview; storing stays `POST /claims` (spec 001).
- **FR-210** If the model service is unavailable after retries, the request fails with a clear
  "service unavailable" error, not a decision.
- **FR-211** The result reports model usage: calls made, tokens, tokens served from cache, reasoning
  tokens, time taken.

## Out of scope

Storing claims, authentication, receipt images or PDFs, changing any policy rule, timeouts and
fallbacks for tools (M09).

## Success criteria

- **SC-201** With the reader faked, every decision branch and both retry paths are tested offline.
- **SC-202** Live, examples A–D give the expected decisions, and the amounts in each result are
  exactly the policy check's.
