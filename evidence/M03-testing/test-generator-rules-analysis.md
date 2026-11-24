# Test-generator analysis: `src/agentic_app/claims/rules.py`

- **Date:** 2026-11-24 (branch `m03-ai-testing`)
- **Generator:** `test-generator` subagent (`.claude/agents/`). It worked from `specs/001-claims-api/` and `data/policies/*.md`, not from the code, and did not change `src/`.
- **Reviewer check:** the main session re-ran the suite and read the spec, research and policy lines cited below.

## Result

| Run | Result |
|---|---|
| `uv run pytest tests/generated -q` | 44 collected: **42 passed, 2 failed** |
| `uv run pytest -q` | **266 passed, 2 failed**, 1 deselected (`live`). All 224 existing tests pass. |

New file: `tests/generated/test_gen_rules.py` (plus an empty `__init__.py`). It needs `hypothesis`, which is in the uncommitted `pyproject.toml` / `uv.lock` changes.

Raw pytest summary:

```
FAILED tests/generated/test_gen_rules.py::test_tiny_multi_night_line_cannot_let_another_line_exceed_the_nightly_cap
FAILED tests/generated/test_gen_rules.py::test_property_multi_night_share_never_frees_cap_on_its_last_night
2 failed, 266 passed, 1 deselected in 3.21s
```

## Finding: a negative last-night share lets another line go over the nightly cap

Both failures have the same cause.

### Reproduction

Paris trip, 2026-03-10 to 03-13. Paris falls under "other city", with a cap of 140 USD per night.

| Line | Category | Amount | Nights | Date |
|---|---|---|---|---|
| 1 | lodging | 0.02 USD | 4 | 03-10 |
| 2 | lodging | 140.01 USD | 1 | 03-13 |

- **Expected:** line 2 is paid at most 140.00. There is a `LODGING_NIGHTLY_CAP` violation for 03-13.
- **Actual:** line 2 is paid **140.01**, with nothing rejected and no violation.

The Hypothesis test found the smallest failing case, 0.02 USD over 4 nights in Berlin: line 2 is paid 180.01 against a cap of 180.

### Mechanism (verified in code)

`_night_shares` (`src/agentic_app/claims/rules.py:156`):

```python
share = to_cents(state.claimed_usd / nights)          # 0.02 / 4 = 0.005 -> 0.01 (half-up)
shares = [share] * (nights - 1) + [state.claimed_usd - share * (nights - 1)]   # last = 0.02 - 0.03 = -0.01
```

In `_apply_lodging_cap`, `paid = to_cents(min(share, max(remaining, 0)))` comes out as −0.01 for the negative share. The next step, `remaining -= paid`, then raises the night's remaining cap by one cent. Line 2 uses that extra cent.

The overpayment grows with the number of nights. For 1.00 USD over 60 nights, 59 shares of 0.02 leave −0.18 for the last night, so another line on that night can be paid 0.18 over the cap. Line 1's own total still comes to its claimed amount.

### Spec trace

- `spec.md:30` (clarification) and `spec.md:239` (FR-017) say each share is "rounded half-up to 2 decimals, with the last night taking any leftover cent so the shares sum to the line amount."
- `research.md:155` (R-10) turns that into the exact formula above, and the code follows R-10 as written.
- `spec.md:240` (FR-017) says per-night lodging "MUST NOT exceed the cap". `data/policies/lodging.md` §1–2 says there is a cap per night and that "A cheaper night does not make room for a more expensive one".
- `spec.md:160` (edge cases) says reimbursement is "not less than 0".

### Classification

**This is a spec defect that the code faithfully implements.** It is not a coding slip. The split rule in the clarification, FR-017 and R-10 assumes the leftover is zero or a positive cent. Rounding half-up can overshoot, and nobody covered that case. When it happens, the split rule conflicts with the cap requirement in the same FR-017.

The main session agrees with the subagent's classification.

### Decision needed (not made)

Under `CLAUDE.md` ("if the spec is unclear, ask instead of guessing"), the spec has to be amended before any code changes. Two candidate fixes:

1. **Floor-and-distribute:** each share is the amount divided by nights, rounded *down* to cents. The leftover cents (always 0 to nights−1 of them) go to the last night. Shares are never negative. This changes the "half-up" wording in FR-017.
2. **Clamp:** keep the half-up rounding, but cap each share at what is left of the line amount, so later shares become 0 instead of negative. The current wording mostly stands, but the result is uneven: 0.01, 0.01, 0.00, 0.00.

Both keep the existing examples: 100.00 / 3 → 33.33 / 33.33 / 33.34, and 540 EUR over 3 nights in Berlin. Either way, `research.md` R-10 and the two failing tests' expectations need to match the chosen wording.

## Areas covered that passed (42 tests)

- **Currency rounding:** half-cent amounts round up, not banker's style (1.50 GBP → 1.91, 3.75 INR → 0.05). Also 0.01 INR → 0.00, three 0.01 GBP lines totalling 0.03, `Decimal("1E+2")`, and 9,999,999,999.99 EUR.
- **Receipt threshold after conversion:** 2083.74 / 2083.75 INR and 19.68 / 19.69 GBP on either side of 25.00 USD.
- **Meals:** the 75.00 limit at 69.44 / 69.45 EUR, a line that exactly fills what is left, lines out of date order, a month boundary, and lines in an unsupported currency or duplicates counting as 0.
- **Lodging:** where the leftover cent lands (420.02 / 3 and 420.01 / 3 in Paris), a leap-day night, overlapping multi-night and one-night lines, and line order rather than date order.
- **Duplicates:** category is ignored, an inner double space does not match, `1E+2` matches `100.00`, and a prior-claim line plus two copies in the same claim.
- **Per diem:** leap and non-leap February, a year boundary, 365- and 366-day trips, and "Bérlin" getting the other-city rate.
- **Hypothesis properties** (300 examples each):
  - each line is paid at least 0 and at most its claimed amount
  - claimed equals paid plus rejected
  - every amount has exactly 2 decimals, and the same input always gives the same output
  - only duplicates are flagged for review
  - meals are paid exactly up to the daily limit
  - single-night lodging is paid exactly up to the cap
  - each violation's excess equals the amount rejected

Note: the general lodging property test did **not** find this defect in 300 examples, because it needs a rare combination of inputs. Only the targeted property test caught it. Random properties on their own would have missed it.

## Spec ambiguities found (no tests written)

| Topic | Current code behaviour | Spec says |
|---|---|---|
| Unicode case folding of merchant names | `casefold()`: "Straße" matches "STRASSE" | only "case-insensitively" |
| What counts as "surrounding spaces" | `strip()` also removes tabs, newlines and NBSP (merchant and city) | "spaces" |
| NFC vs NFD forms of "Café" | treated as different merchants | only rules on Cafe vs Café |
| Lowercase currency reaching `rules.py` | "eur" is treated as unsupported | normalisation promised only at API input |
| Very large amounts (> 28 significant digits) | rounded by the Decimal context, or an error is raised | no upper bound |
| Lines named in a meals violation | only lines that lost money | "affected line(s)" (FR-008) |
| Per diem half-up rounding | can't be tested with current rates (whole number × 0.75 never needs rounding) | half-up rule exists |

## Suggested next steps

1. Pick a split rule (option 1 or 2 above) and amend the clarification Q5, FR-017 and R-10 in `specs/001-claims-api/`.
2. Fix `_night_shares`. The two failing tests then become regression tests. Until then, mark them `xfail(strict=True)` with a link to this file, so `uv run pytest` is green again as `CLAUDE.md` requires.
3. Optionally clarify the ambiguities in the table above, or record them as accepted behaviour.
