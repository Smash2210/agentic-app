# Real defect caught by AI-assisted tests: lodging paid over the nightly cap

| | |
|---|---|
| Found by | `test-generator` subagent ([.claude/agents/test-generator.md](../../.claude/agents/test-generator.md)), run blind: it could not read `evidence/` |
| Failing tests | `test_tiny_multi_night_line_cannot_let_another_line_exceed_the_nightly_cap` and the Hypothesis property `test_property_multi_night_share_never_frees_cap_on_its_last_night` in [tests/generated/test_gen_rules.py](../../tests/generated/test_gen_rules.py) |
| Failing-test commit | `c4e8cbd`: raw generated tests, committed before any fix |
| Fix commit | `83b8e5b`: spec amended first (clarification Q5, FR-017, research R-10), then the code |
| Generator's own analysis | [test-generator-rules-analysis.md](test-generator-rules-analysis.md) |

## What was wrong

A multi-night lodging line is split evenly across its nights, and each night is capped
(POL-LODGING §1–2: "A cheaper night does not make room for a more expensive one"). Each share was
rounded **half-up**, and the last night took whatever was left:

```
0.02 USD over 4 nights: share = 0.005 → 0.01, so 0.01, 0.01, 0.01 and the last night 0.02 − 0.03 = −0.01
```

The negative share went into that night's cap calculation as a payment of −0.01. That **raised the
night's remaining cap by a cent**, and another lodging line on the same night was paid **180.01
against Berlin's 180 cap**, with no violation. The overpayment grows with the number of nights:
1.00 USD over 60 nights frees 0.18.

## Why the original suite missed it

- `rules.py` had **100% line and branch coverage**. Every line of the split ran, but no test used
  an amount so small that rounding up a share overshoots the total.
- The spec itself carried the bug. Clarification Q5 and FR-017 said "rounded half-up, last night
  takes any leftover cent". They assumed the leftover is never negative. The code followed the spec
  exactly, so example tests written from the spec agreed with it.
- It took a **property** ("a single-night line is never paid over the cap") checked against
  generated inputs to find it. The generator's broad property test did not hit it in 300 random
  examples; its targeted property test (tiny amounts, many nights) did, and Hypothesis shrank it to
  0.02 USD over 4 nights.

## Fix

- **Spec first** (Principle I): shares are rounded **down**, and the last night takes the leftover
  cents, which can no longer be negative. Every earlier worked example is unchanged (100.00 / 3 →
  33.33 / 33.33 / 33.34; 540 EUR over 3 nights in Berlin).
- **Code:** `money.to_cents_down()` (`ROUND_DOWN`, so all rounding stays in `money.py`), used by
  `rules._night_shares()`.
- One generated test asserted the old split for 420.02 / 3 (nights 1 and 2 over by 0.01). Its
  expectation was updated to the amended spec (night 3 over by 0.02; the line still pays 420.00 and
  rejects 0.02). This is a deliberate spec change, not a test bent to fit the code.
- Both failing tests now pass; the full suite is 268 passed.
