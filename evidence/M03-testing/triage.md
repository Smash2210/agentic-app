# Triage of AI-generated tests (`tests/generated/test_gen_rules.py`)

44 tests from the `test-generator` subagent, raw output in commit `c4e8cbd`. Each was checked to
make sure its expected value comes from the spec or policy (worked in its docstring), not from the
code's current output.

| Tests | Count | Verdict | Reason |
|---|---|---|---|
| `test_tiny_multi_night_line_cannot_let_another_line_exceed_the_nightly_cap`, `test_property_multi_night_share_never_frees_cap_on_its_last_night` | 2 | **keep: real defect** | Failed: another line paid over the nightly cap. Spec defect; fixed in `83b8e5b` ([defect.md](defect.md)) |
| `test_leftover_cent_on_last_night_decides_which_nights_are_over` | 1 | **keep, updated** | Asserted the old half-up split. Expectation changed to the amended FR-017 in the fix commit |
| Currency rounding and conversion (5), receipts at converted boundaries (2) | 7 | keep | Half-cent rounding, tiny INR, per-line conversion, `1E+2`, very large EUR; receipt threshold either side of 25.00 after conversion |
| Meals (6) | 6 | keep | Converted boundary, exact fill, out-of-date-order lines, month end, unsupported and duplicate lines counting 0 |
| Lodging (others) | 5 | keep | Leftover on the last night, leap day, overlapping lines, line order beats date order, duplicate ignores nights |
| Duplicates (4) | 4 | keep | Category ignored, inner spaces matter, `1E+2` = `100.00`, prior and in-claim duplicates together |
| Per diem (2 groups) | 2 | keep | Leap years, year boundary, 365/366-day trips, accented city falls back to the other-city rate |
| Hypothesis properties (7 others) | 7 | keep | Paid between 0 and claimed; claimed = paid + rejected; determinism; only duplicates flagged; limits filled exactly; excess = rejected |
| | **34 test functions (44 test cases once parametrised)** | **all kept, 0 rejected** | |

No test was rejected. None asserted current output instead of the spec, none duplicated an
existing test by name and intent, and all 42 that passed before the fix also pass after it.

## Spec ambiguities the generator raised (no tests written)

Recorded as accepted current behaviour for now; the ones with security impact are in
[ai-review.md](ai-review.md) for M06. They cover: Unicode case folding of merchants; `strip()` also
removing tabs and non-breaking spaces; NFC vs NFD "Café"; lowercase currency inside `rules.py`; very
large amounts; which lines a meals violation names; per diem half-up rounding, which current rates
can't reach.
