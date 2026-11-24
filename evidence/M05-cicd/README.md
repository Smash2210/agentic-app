# M05 — AI in CI/CD

**Outcome:** working pipeline configuration files with at least one AI-assisted gate, plus a
pipeline run showing the gate correctly blocking a bad change.

| Required | Where |
|---|---|
| Pipeline configuration | [.github/workflows/ci.yaml](../../.github/workflows/ci.yaml) (rule-based stage), [.github/workflows/ai-review.yml](../../.github/workflows/ai-review.yml) (AI stage); gate settings in `pyproject.toml` (`[tool.ruff]`, `[tool.coverage.report]`) |
| AI-assisted gate | [review/run_review.py](../../review/run_review.py) with the M03 reviewer prompts [review/prompts/](../../review/prompts/); gate logic tested offline in [tests/test_review_gate.py](../../tests/test_review_gate.py) |
| Run showing the gate blocking a bad change | PR [#2 "Update meal limit to 100 USD"](https://github.com/Smash2210/agentic-app/pull/2): [blocked-pr-verdict.png](blocked-pr-verdict.png), [blocked-pr-reviewers.png](blocked-pr-reviewers.png) |
| The gate added through its own PR | PR [#1](https://github.com/Smash2210/agentic-app/pull/1), merged: the gate reviewed its own code and passed |

## The two stages

| Stage | Runs on | Checks | Fails when |
|---|---|---|---|
| `ci` (rule-based, fast, no secrets) | every push to `master` and every PR | `ruff check` (correctness rules E, F); `pytest` with coverage; `exports_openapi.py --check` | lint error, failing test, coverage under 90%, stale `openapi.json` |
| `ai-review` (model-graded) | every PR | Two reviewers (security, patterns) on Gemini free tier, given the diff, the full changed files, the constitution, `CLAUDE.md` and every `spec.md`. Output forced into a `Verdict` schema and validated with Pydantic | any reviewer reports a **spec violation**, or any finding is **high** risk; or the review itself fails (invalid output twice, API error after retries): **fails closed** |

Cheap deterministic checks run everywhere; the model-graded check runs where a human decision is
about to be made (the PR). The secret `GOOGLE_API_KEY` is given only to the AI review step.

## The blocked change

PR #2 raised the meal limit from 75 to 100 USD in `data/policies/meals.md` and updated 14 tests and
the seed expectations so everything rule-based still passed. Re-run locally on the PR's commit
`1245c9d`:

```
ruff check .                          All checks passed!
pytest --cov                          272 passed, total coverage 92.66% (required 90%)
exports_openapi.py --check            docs/api/openapi.json is up to date
```

So `ci` was green. `ai-review` was red: the patterns reviewer reported a **spec violation** ("the
daily meal limit was increased from 75 USD to 100 USD … but specs/001-claims-api/spec.md still
specifies 75 USD per calendar day, violating Principle I") and a **high-risk** finding P1 on
`data/policies/meals.md:4`. The security reviewer had no findings, which is right: this is a
spec-consistency problem, not a security one. The PR was closed without merging.

**This is why the AI gate exists:** the tests were changed along with the number, so every
rule-based check agreed with the bad change. Only a check that reads the spec could see that the
policy moved without the spec moving first.

**One inaccuracy in the verdict:** it says "the policy doc itself still specifies 75 USD". The PR
did change the policy doc to 100. The blocking reason (spec not updated) is correct; that detail
is not. LLM verdicts are evidence for a human, not facts. The gate blocks, and a person reads why.

## Thresholds and why

- **Coverage floor 90%** (`pyproject.toml`, reasoning in a comment there): current total is 93%.
  The margin lets a refactor move a few lines, but a module losing its tests (e.g. `rules.py`,
  ~120 statements at 100%) drops the total below 90 and fails. Raise it as coverage grows; never
  lower it to get a PR through.
- **AI gate: block on spec violation or any `high` finding; `med` and `low` are reported, not
  blocking.** Spec violations are what tests cannot catch (they move with the code). `high` is
  defined in the prompts as money or other users' data at risk, or easy denial of service. `med`
  findings blocking every PR would train people to ignore the gate.
- **`temperature=0`, one retry with the validation error fed back, transient API errors retried
  with backoff (max ~35 s), everything else fails closed.** A gate that silently passes when the
  model misbehaves is worse than no gate.

## Known limits

- **The gate marks the PR as failed but cannot lock the Merge button.** Branch protection and
  rulesets are not available for private repositories on a free GitHub account. Enforcing it needs
  GitHub Pro/Team or a public repo, then requiring both checks on `master`.
- **Prompt injection.** The diff is given to the model as data, with an instruction to ignore any
  text that tries to steer the verdict. That is a first defence only; M15 attacks it.
- **Model-graded means not fully deterministic.** The same diff can produce different findings on a
  re-run. The blocking rule depends only on the two coarse fields (`spec_violation`, `high` risk).
- **Data sent to Gemini:** the diff, changed files and specs, all synthetic. Free-tier prompts may
  be used by Google to improve its products; acceptable for synthetic data, not for client code
  (to be covered in the M06 data statement).
- The good PR for contrast was skipped; PR #1 (adding the gate) shows a clean pass.

**Probe:** "What is the threshold, and why that number?" → "Thresholds and why" above.
