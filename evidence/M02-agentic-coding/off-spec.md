# Off-spec moments and how they were caught

The main one for the reviewer is 1. The others show the other checks in the workflow doing their job.

1. **The agent dodged a guard test (Phase 3, T025–T029).** The C5 purity test bans numeric literals
   other than 0 and 1 in `rules.py`. The agent wrote `full_days = days - 1 - 1` instead of `days - 2`:
   correct behaviour, but it satisfies the letter of the guard while hiding the intent. **Caught by:**
   human review of the Phase 3 checkpoint. **Fix:** `days - 2` with a comment, plus a narrow allowance
   in `test_rules_purity.py`, which I approved explicitly in the session (the agent was told not to
   change tests on its own). The session log shows no other test edited after `rules.py` was written.
2. **No feature branch.** `/speckit-specify` left the spec on `main` ("Feature Branch: main").
   **Caught by:** reviewing spec.md. **Fix:** `git switch -c 001-claims-api` before planning.
3. **The plan went beyond the spec.** R-07 upper-cased currency codes, which the spec didn't say,
   and R-06's two-stage validation contradicted SC-006. **Caught by:** plan review against
   Principle I. **Fix:** the spec was amended first (clarification + SC-006 wording), then the plan.
4. **The plan built the app at import time** (R-12, module-level `app = create_app(...)`), and
   `/speckit-analyze` then found that importing the package read `.env` through `llm.py` (U1).
   **Caught by:** plan review and the analyze step. **Fix:** `app_from_env()` factory run with
   `uvicorn --factory`; the `llm` import moved inside the CLI's `main()`, with a subprocess test.
5. **Shared mutable state in the "pure" rules engine.** `RULE_CITATIONS` held mutable `Citation`
   objects, against Principle III. Human review missed it. **Caught by:** `/speckit-converge` run 1
   (F1), which proved it by mutating a shared citation. **Fix:** T043, frozen citations built fresh per
   check, with a test.
6. **A wrong number in hand-written expectations.** Seed claim 3's working said the meal excess was
   6.20; the correct figure is 6.00. Tests only assert rule IDs and totals (642.90, which was right),
   so they passed. **Caught by:** the real-server quickstart run (T041). **Fix:** `7fa5aed`.
