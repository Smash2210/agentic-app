# How AI tooling was used on this codebase, and what it could see

## AI tools used (M01–M06)

| Tool | Used for | What it received |
|---|---|---|
| **Claude Code** (desktop app, coding agent) | Writing code, specs and tests through spec-kit (M02), the test-generator subagent (M03), docs generation via the `api-docs` skill (M04) | Files in this repository, read on demand, plus command output in the session |
| **Claude** (assistant, separate session) | Guiding each sprint, reviewing work, running the M03 AI code review, triaging scanner output | Files in this repository and the session logs |
| **Gemini via AI Studio, free tier** | The app's `llm.py` smoke test (M01); the CI AI review gate (M05) | Smoke test: one short prompt. CI gate: the PR diff, the full changed files, the constitution, `CLAUDE.md` and every `spec.md` |

The application itself never calls Claude, and in Tier 1 it makes no model calls at all.

## What the AI tools were allowed to see

**Only this repository, and everything in it is synthetic.** The travel policy, seed claims and
receipts were written for this project. There is no client code, no real personal data and no
production system.

## What they were not allowed to see, and what enforces it

| Protected | Enforcement | Verified |
|---|---|---|
| `.env` (holds the Gemini API key) | Claude Code permission deny rules in `.claude/settings.json`: `Read(./.env)`, `Read(./.env.*)`, `Bash(cat .env*)`. These are enforced by the Claude Code harness, not by asking the model. | Yes, after a fix: in M02 the file was first saved at `.claude/skills/settings.json`, where it is **not loaded**. Caught in review and moved (commit `cf23a0f`). A control that looks present is not the same as one that works. |
| `.env` in git | `.gitignore`; gitleaks scans the whole history on every push and PR (`security.yml`) | `.env` has never been committed; key-pattern scan of all history: 0 hits; gitleaks in CI: 0 |
| The API key in CI | GitHub Actions secret, given as an environment variable **only** to the AI review step; masked in logs. The other jobs and the security scanners get no secret. | `ai-review.yml`, `ci.yaml`, `security.yml` |
| Keys in AI session logs | The Claude Code session logs were scanned for the Google API key pattern before being committed as M02 evidence | 0 hits |
| Production credentials | None exist, and none were given to any agent. The GitHub access token was typed by the engineer into git, never into an AI chat. | — |

## Known limits of these controls

- **Deny rules are path-based.** A secret saved under another file name would be readable by the
  coding agent. Mitigation: secrets only in `.env`, gitleaks in CI. A local pre-commit hook is not
  set up yet, so a secret could be committed locally and only caught when pushed.
- **The coding agent can read the whole repository**, including evidence and session logs. That is
  acceptable only because all of it is synthetic.
- **Gemini free tier:** Google may use free-tier prompts to improve its products. Acceptable for
  synthetic data. **Not acceptable for client code.**
- **The CI AI gate sends code to an external API** on every PR. Prompt injection inside a diff is
  mitigated only by an instruction to treat the diff as data (tested properly in M15).

## For a client codebase, this would change

1. Only code the client has approved for AI processing, under an enterprise agreement with
   no-training and data-retention terms (e.g. Vertex AI with the client's own project, or the
   client's approved provider). No free tiers.
2. The same harness-enforced deny rules, extended to every secret and data path; secrets in a
   secret manager, never in the repo.
3. Secret scanning both before commit (pre-commit hook) and in CI.
4. Synthetic or masked test data only; no production data or credentials ever reach an agent.
5. The AI review gate pointed at the client-approved model endpoint, with its prompts and verdicts
   kept as an audit trail.

**Probe:** "What may an AI tool be shown when pointed at client code, and what enforces that?" →
"For a client codebase" above. Enforcement is in the tools (deny rules, secret scanning, secrets kept
out of the repo), not in instructions to the model.
