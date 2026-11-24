# M03 — AI-assisted testing and code quality

**Outcome:** a test suite with a before-and-after coverage figure, at least one real defect the
AI-assisted tests caught, and an AI code review report with the engineer's accept or reject decision
on each finding.

| Required | Where |
|---|---|
| Test suite | 224 tests from M02 + 44 AI-generated in [tests/generated/test_gen_rules.py](../../tests/generated/test_gen_rules.py) (generator: [.claude/agents/test-generator.md](../../.claude/agents/test-generator.md)); triage in [triage.md](triage.md) |
| Before-and-after coverage | [coverage-before.txt](coverage-before.txt), [coverage-after.txt](coverage-after.txt); mutation testing: [mutation-before.txt](mutation-before.txt), [mutation-after.txt](mutation-after.txt) |
| Real defect caught by AI tests | [defect.md](defect.md): lodging paid over the nightly cap. Failing tests `c4e8cbd`, fix `83b8e5b` |
| AI code review with decisions | [ai-review.md](ai-review.md): 13 findings from two specialised reviewers ([prompts](../../review/prompts/)), 7 accepted, 6 rejected, each with a reason |

## The figures

| | Before (end of M02) | After (M03) |
|---|---|---|
| Tests | 224 | 268 |
| Line + branch coverage | 93% | 93% |
| `rules.py` coverage | 100% | 100% |
| Mutants killed / survived / no tests | 676 / 53 / 89 (818) | 683 / 53 / 89 (825) |
| Mutation score (killed ÷ tested) | 92.7% | 92.8% |
| Real test gaps among `rules.py` survivors | 2 | **0** |

**Reading the figures honestly:**
- **Coverage did not move, and that is the finding.** `rules.py` was already at 100% line and branch
  coverage, yet it had a defect that pays money over the policy cap. Coverage says code *ran*, not
  that a test *checked the right thing*.
- The mutation score moved where it matters. Before, two `rules.py` survivors were real test gaps:
  - `excess += …` → `excess = …` (wrong excess when two lines go over the same night's cap)
  - `max(remaining, 0)` → `max(remaining, 1)` (a line arriving after the cap is used up gets paid
    1.00)

  Both are killed now. The 14 `rules.py` survivors left are message wording (not part of the API
  contract) or equivalent changes that cannot change a result. The total survivor count stays at 53
  because the new `money.to_cents_down` adds two mutants that only change an error message's text.
- 89 "no tests" mutants are `seed.py` and `app.py`. Their tests start a fresh Python process or are
  excluded from mutation runs (see `[tool.mutmut]` in `pyproject.toml`). Accepted as review finding P4.

## How it was done

1. Baselines: `pytest-cov` with branch coverage, and `mutmut` (whole package except `llm.py` and the
   CLI).
2. AI test generation: a Claude Code subagent with a "context engine" (constitution, spec, policy,
   module and its imports, existing tests), run **blind** to our own defect notes. It used Hypothesis
   for invariants. Its raw output was committed before any human decision.
3. Triage of every generated test; the failing ones traced to a **spec** defect, so the spec was
   amended before the code (Principle I).
4. AI code review by two specialised reviewers (security, codebase patterns) that read the spec and
   related files, not just a diff. Every high or medium finding was reproduced against a running app
   before it went in the report.

Scope kept to the submission: the generator ran on `rules.py`, the highest-risk module. The other
modules were covered by the AI review instead of a second round of generated tests.

**Probe:** "Which defect did the generated tests find that you had missed? Why did your original
suite miss it?" → [defect.md](defect.md), section "Why the original suite missed it".
