# Feature Specification: Claims API

**Feature Branch**: `main` (no feature branch created; spec id `001-claims-api`)

**Created**: 2026-11-24

**Status**: Draft

**Input**: User description: "Claims API: employees submit travel expense claims and get them checked
against company policy, with a clear reimbursement result. Users: an employee (submits and views
claims); auth out of scope, callers state the employee id. P1 check a claim, P2 submit a claim,
P3 view claims. Rules: meals daily limit, lodging nightly cap, per diem, currency, receipts,
duplicates — every number from data/policies/*.md with doc_id + section citations. Synthetic seed
data of 10–15 claims. Out of scope: auth and roles, approval workflow and status changes, receipt
files or text, any LLM use, editing or deleting claims."

## Clarifications

### Session 2026-11-24

- Q: How is a line in an unsupported currency handled? → A: The claim is stored; at check time the
  line raises an unsupported-currency violation (POL-CURRENCY §2) and is reimbursed 0 USD.
- Q: How is excess over a daily meal limit or nightly lodging cap split across several lines? →
  A: Lines are paid in line order; the line crossing the limit is partly paid, later lines are fully
  rejected.
- Q: What about a line dated outside the trip's start–end dates? → A: The claim is refused at
  submission as invalid input.
- Q: How is a single lodging line covering several nights capped? → A: Lodging lines carry a number
  of nights (default 1, dated the first night); each night is capped on its own.
- Q: How is a multi-night lodging amount assigned to each night? → A: Split evenly per night, rounded
  half-up to cents, with the last night taking any leftover cent; then each night is capped, filling
  lines in line order.
- Q: Do merchant names differing only in case or surrounding spaces count as the same merchant for
  duplicates? → A: Yes; trim surrounding spaces and compare case-insensitively.
- Q: Does a line already rejected for another reason use up the daily meal limit or nightly lodging
  cap? → A: No; it counts as 0 USD toward the limit.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Check a claim against policy (Priority: P1)

An employee asks for the policy check of a claim that is already stored. They get back every policy
violation on the claim and a reimbursement summary, so they know exactly what will be paid, what
will not, and which written rule decided it.

**Why this priority**: This is the core value of the product: correct, explainable expense
decisions grounded in written policy. Submission and viewing exist to feed it.

**Independent Test**: Load the seed claims, check each one, and compare the violations and amounts
with the expected results worked out by hand from the policy documents.

**Acceptance Scenarios**:

1. **Given** a stored claim with no policy problems, **When** it is checked, **Then** the result
   lists no violations, every line's reimbursable USD amount equals its claimed USD amount, and the
   total reimbursable equals the sum of the lines plus the trip's per diem allowance.
2. **Given** a 3-day trip to Berlin with two meal lines on one day of 50.00 USD and 40.00 USD (both
   with receipts), **When** it is checked, **Then** there is one meals-limit violation citing
   POL-MEALS §1 for that day, 75.00 USD of meals is reimbursable for that day, and 15.00 USD is
   rejected as excess.
3. **Given** a London trip with a lodging line of 250.00 USD for one night (with receipt), **When**
   it is checked, **Then** 220.00 USD is reimbursable, 30.00 USD is rejected, and the violation cites
   POL-LODGING §1 and §3.
4. **Given** a trip to Paris from 10 March to 13 March, **When** it is checked, **Then** the per diem
   allowance is 45 × 0.75 + 45 + 45 + 45 × 0.75 = 157.50 USD, citing POL-PERDIEM §1–2.
5. **Given** a same-day trip to London, **When** it is checked, **Then** the per diem allowance is
   70 × 0.75 = 52.50 USD, citing POL-PERDIEM §3.
6. **Given** a meal line of 30.00 EUR with a receipt, **When** it is checked, **Then** its claimed
   USD amount is 32.40 (30.00 × 1.08, rounded half-up to 2 decimals per POL-CURRENCY §2–3).
7. **Given** a transport line of 25.01 USD with no receipt, **When** it is checked, **Then** the line
   is not reimbursed and a missing-receipt violation cites POL-RECEIPTS §1–2; **and given** a line of
   exactly 25.00 USD with no receipt, **Then** no receipt violation is raised.
8. **Given** an employee whose earlier claim has a line (same date, amount, currency and merchant)
   that matches a line in a later claim, **When** the later claim is checked, **Then** the later line
   is rejected and flagged as a duplicate citing POL-RECEIPTS §3–4, and the earlier claim's check
   result is unchanged.
9. **Given** a claim with a line in an unsupported currency (for example JPY), **When** it is
   submitted, **Then** the claim is stored; **and when** it is checked, **Then** that line raises an
   unsupported-currency violation citing POL-CURRENCY §2, is reimbursed 0 USD, has no USD amount, and
   the rest of the claim is checked normally.
10. **Given** a claim ID that does not exist, **When** a check is requested, **Then** a clear
    "claim not found" error is returned.
11. **Given** a Berlin trip with one lodging line of 540.00 EUR for 3 nights (with receipt), **When**
    it is checked, **Then** the line's claimed amount is 583.20 USD, each night's share is 194.40 USD
    against a 180 USD cap, 540.00 USD is reimbursable, 43.20 USD is rejected, and one lodging-cap
    violation is raised for each of the 3 nights citing POL-LODGING §1–3.
12. **Given** a day with a 60.00 USD meal line with no receipt and a 50.00 USD meal line with a
    receipt, **When** it is checked, **Then** the first line is rejected for the missing receipt and
    the second is reimbursed in full (50.00 USD), with no meals-limit violation.

---

### User Story 2 - Submit a claim (Priority: P2)

An employee submits a claim: their employee ID, the trip (destination city, start date, end date)
and a list of expense lines (date, category, merchant, amount, currency, whether a receipt is
attached). Valid claims are stored and given an ID; invalid input is refused with an error that
says what is wrong.

**Why this priority**: Claims must get into the system before they can be checked, but checking
can be demonstrated first using seed data.

**Independent Test**: Submit valid and invalid claims; valid ones return a new ID and can be read
back unchanged, invalid ones return an error naming each bad field and store nothing.

**Acceptance Scenarios**:

1. **Given** a well-formed claim, **When** it is submitted, **Then** it is stored, a new unique claim
   ID is returned, and the claim can be retrieved with exactly the submitted data.
2. **Given** a claim whose end date is before its start date, **When** it is submitted, **Then** it
   is refused with an error naming the trip dates and nothing is stored.
3. **Given** a line with a category other than meal, lodging, transport or other, a zero or
   negative amount, a missing merchant, or a missing field, **When** it is submitted, **Then** it is
   refused with an error identifying the line and field, and nothing is stored.
4. **Given** a line dated outside the trip's start–end range, **When** it is submitted, **Then**
   it is refused with an error naming the line and its date, and nothing is stored.

---

### User Story 3 - View claims (Priority: P3)

An employee retrieves one claim by its ID, or lists all claims for an employee ID.

**Why this priority**: Useful for confirming what was submitted, but not needed to get a policy
decision.

**Independent Test**: With seed data loaded, fetch a known claim by ID and list claims for a seed
employee; compare with the seed data.

**Acceptance Scenarios**:

1. **Given** a stored claim, **When** it is fetched by ID, **Then** the employee ID, trip and every
   line are returned as submitted, with its claim ID.
2. **Given** an employee with three stored claims, **When** their claims are listed, **Then** exactly
   those three claims are returned, in submission order.
3. **Given** an employee ID with no claims, **When** their claims are listed, **Then** an empty list
   is returned (not an error).
4. **Given** an unknown claim ID, **When** it is fetched, **Then** a clear "claim not found" error is
   returned.

---

### Edge Cases

- A meal or lodging line that is also rejected for another reason (missing receipt, duplicate,
  unsupported currency) counts as 0 USD toward the day's meal limit or the night's lodging cap;
  limits are applied only to lines not already rejected.
- Several meal lines on the same calendar day, or several lodging lines covering the same night,
  whose total exceeds the limit: lines are paid in line order until the limit is reached; the line
  that crosses the limit is partly reimbursed and every later line on that day or night is fully
  rejected for that day or night.
- A multi-night lodging line whose amount does not split evenly into cents (e.g. 100.00 USD over
  3 nights): shares are 33.33, 33.33 and 33.34 USD (half-up rounding, leftover cent on the last
  night).
- Duplicate merchant matching ignores case and surrounding spaces ("Cafe Roma" and " cafe roma"
  match) but not differences inside the name ("Cafe Roma" and "Café Roma" do not).
- A line that breaks several rules (e.g. duplicate and missing receipt) reports one violation per
  rule broken; it is still reimbursed 0 USD, not less than 0.
- Duplicate lines within one claim: the earlier line (in line order) is processed normally; each
  later one is rejected.
- Destination city matching for Berlin and London is case-insensitive and ignores surrounding
  spaces; any other city uses the "any other city" rate.
- Meal of exactly 75.00 USD on a day, or lodging exactly at the cap: no violation.
- Rounding boundary: a converted amount ending in exactly half a cent rounds up (POL-CURRENCY §3).
- Checking the same stored claim twice gives identical results, and submitting later claims never
  changes the check result of an earlier claim.

## Requirements *(mandatory)*

### Functional Requirements

**Submitting and viewing**

- **FR-001**: The system MUST accept a claim containing an employee ID, a trip (destination city,
  start date, end date) and one or more expense lines, each with a date, category (meal, lodging,
  transport or other), merchant, amount, currency code and a receipt-attached yes/no flag. Lodging
  lines also carry a number of nights (whole number, default 1); the line's date is the first
  night.
- **FR-002**: The system MUST refuse invalid input with an error that names every invalid field (and
  the line it belongs to) and MUST NOT store any part of a refused claim. Invalid input includes:
  missing required fields, end date before start date, unknown category, amount that is zero,
  negative or has more than 2 decimal places, empty merchant, empty currency code, empty employee ID
  or city, no expense lines, a line dated before the trip's start date or after its end date, a
  number of nights that is not a whole number of at least 1, a number of nights on a non-lodging
  line, and a lodging line whose last night (date + nights − 1) is after the trip's end date.
  An unsupported currency code is not invalid input (see FR-013).
- **FR-003**: The system MUST store each valid claim, assign it a unique ID, and record its
  submission order relative to all other claims.
- **FR-004**: Users MUST be able to retrieve a stored claim by ID, and to list all claims for an
  employee ID in submission order.
- **FR-005**: The system MUST return a "not found" error for an unknown claim ID.
- **FR-006**: Claims MUST NOT be editable or deletable through this feature.

**Checking a claim — results**

- **FR-007**: Users MUST be able to request the policy check of any stored claim by ID. The check is
  computed from stored data and MUST give the same result every time for the same stored data.
- **FR-008**: The check result MUST list every violation found. Each violation MUST include a rule
  ID, the affected line (or lines, or calendar day for daily limits), a plain-language message, and a
  policy citation of doc_id and section (e.g. `POL-MEALS §1`).
- **FR-009**: The check result MUST include, for each line: its claimed amount in USD, its
  reimbursable amount in USD, and its rejected amount in USD (claimed minus reimbursable). For a line
  in an unsupported currency the claimed and rejected USD amounts are absent and the reimbursable
  amount is 0 USD.
- **FR-010**: The check result MUST include the trip's per diem allowance in USD and the total
  reimbursable USD, equal to the sum of all lines' reimbursable amounts plus the per diem allowance.
- **FR-011**: Every limit, rate, threshold and percentage used by the check MUST come from the
  policy documents in `data/policies/`; none may be defined anywhere else.

**Checking a claim — rules**

- **FR-012 (Currency, POL-CURRENCY §2–4)**: Each line MUST be converted to USD on its own using the
  fixed rate for its currency (USD 1.00, EUR 1.08, GBP 1.27, INR 0.012), rounded half-up to
  2 decimals. Totals MUST be sums of rounded line amounts. All limits and thresholds are compared
  against converted USD amounts. The receipt threshold (FR-014) applies to a line's whole USD amount,
  including multi-night lodging lines.
- **FR-013 (Unsupported currency, POL-CURRENCY §2)**: A claim with a line in any currency not listed
  in POL-CURRENCY §2 MUST still be accepted and stored. At check time that line MUST raise an
  unsupported-currency violation and be reimbursed 0 USD; it is not converted and is excluded from
  the receipt, meals and lodging rules, but still takes part in duplicate detection.
- **FR-014 (Receipts, POL-RECEIPTS §1–2)**: A line whose USD amount is over 25.00 and has no receipt
  attached MUST raise a missing-receipt violation and be reimbursed 0 USD. A line of exactly
  25.00 USD or less needs no receipt.
- **FR-015 (Duplicates, POL-RECEIPTS §3–4)**: Two lines are duplicates when they have the same
  employee, same date, same amount and currency as submitted, and same merchant (compared
  case-insensitively, ignoring surrounding spaces). Comparison covers lines earlier in the same
  claim and lines in that employee's earlier-submitted claims. The earliest submitted line is
  processed normally; each later duplicate MUST raise a duplicate violation, be reimbursed 0 USD and
  be flagged for review.
- **FR-016 (Meals, POL-MEALS §1, §3)**: For each calendar day, reimbursable meal-line amounts MUST
  NOT exceed 75.00 USD in total. Lines already rejected by FR-013, FR-014 or FR-015 count as 0 USD. Lines are paid in line order until the limit is reached; the line
  that crosses it is partly reimbursed and later meal lines that day are fully rejected. Any excess
  MUST raise a meals-limit violation for that day; the rest of the claim is processed normally.
- **FR-017 (Lodging, POL-LODGING §1–3)**: A lodging line covers the nights from its date for its
  number of nights. Its USD amount is split evenly across those nights, each share rounded half-up
  to 2 decimals, with the last night taking any leftover cent so the shares sum to the line amount.
  For each night, reimbursable lodging shares MUST NOT exceed the cap for the trip's destination
  city (Berlin 180, London 220, any other city 140 USD). Nights are capped independently; an unused
  cap on one night never carries to another. Shares for the same night are paid in line order until
  the cap is reached, as in FR-016; lines already rejected by FR-013, FR-014 or FR-015 count as
  0 USD. Any excess MUST raise a lodging-cap violation for that night and be rejected. A line's
  reimbursable amount is the sum of its paid shares.
- **FR-018 (Per diem, POL-PERDIEM §1–4)**: The per diem allowance MUST be computed from the trip's
  destination city rate (Berlin 60, London 70, any other city 45 USD per day) over the calendar days
  from start to end date inclusive: first and last day at 75%, every day in between at 100%; a
  same-day trip is one day at 75%. The result is rounded half-up to 2 decimals. The per diem needs no
  receipts and is not affected by any line's violations.
- **FR-019**: Transport and other lines are subject only to the currency, receipt and duplicate
  rules.

**Seed data**

- **FR-020**: The feature MUST include a synthetic seed set of 10–15 claims, loadable into an empty
  store, that together trigger every rule in FR-013 to FR-018 at least once — including a duplicate
  within one claim, a duplicate across claims, a same-day trip, a multi-day trip, a multi-night
  lodging line, and lines in each of EUR, GBP and INR — plus at least two clean claims with no violations. Each seed claim MUST record
  which rules it is meant to trigger and its expected total reimbursable USD.

### Key Entities

- **Claim**: One employee's request for reimbursement for one trip. Has a unique ID, employee ID,
  trip, ordered expense lines, and a submission order.
- **Trip**: Destination city, start date and end date (inclusive). Drives the lodging cap and the
  per diem rate.
- **Expense line**: One expense on a claim: date, category, merchant, amount, currency code,
  receipt-attached flag, number of nights (lodging only, default 1), and its position within the
  claim.
- **Violation**: A rule broken by a claim: rule ID, affected line(s) or day, message, and citation
  (doc_id + section).
- **Check result**: The outcome of checking a claim: violations, per-line USD amounts (claimed,
  reimbursable, rejected), per diem allowance, and total reimbursable USD. Computed on request; not
  stored.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100% of seed claims, the check result's violations and total reimbursable amount
  exactly match the expected values worked out by hand from the policy documents, to the cent.
- **SC-002**: Every rule listed in FR-013 to FR-018 is triggered by at least one seed claim, and at
  least two seed claims produce no violations.
- **SC-003**: 100% of violations carry a doc_id and section that exist in `data/policies/`.
- **SC-004**: For every rule threshold (25.00 USD receipts, 75.00 USD meals, each lodging cap, the
  per diem 75%/100% day split), behaviour is verified at the threshold and one cent (or one day)
  either side.
- **SC-005**: Checking the same stored claim repeatedly returns identical results, including after
  further claims are submitted.
- **SC-006**: Every refused submission names each invalid field, and none leaves partial data
  stored.

## Assumptions

- Authentication and roles are out of scope: callers state the employee ID and any caller may
  submit, view or check any claim.
- Lodging lines have no city of their own; the trip's destination city sets the nightly cap. A
  multi-night bill gives no per-night breakdown, so its even split per night is the closest
  available reading of POL-LODGING §2.
- Meal days are calendar days by the line's date; no time zones are involved.
- POL-MEALS §2 (alcohol, meals already included elsewhere) and POL-LODGING §4 (minibar, room service
  etc.) cannot be checked because lines carry no itemised detail; they are out of scope for this
  feature.
- Claims carry no status; approval workflow, receipt files and any LLM use are out of scope.
- Amounts are entered with at most 2 decimal places in the original currency.
- A claim must contain at least one expense line.
- Policy documents are fixed for this feature; changing a rate or limit means changing the policy
  file and this spec.
