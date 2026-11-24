# Off-spec moments

1. Phase 3 (T025-T029): the agent wrote `full_days = days - 1 - 1` in rules.py to get past the C5 no-literals purity test instead of writing `days - 2`. Caught in human review of the Phase 3 checkpoint. Fix: `days - 2` with a comment, plus a narrow, human-approved allowance in test_rules_purity.py.
