# Security and compliance report: Tier 1 Claims API

- **Scope:** `src/agentic_app/` (Claims API), plus the CI tooling in `review/` and `scripts/`, at
  branch `m06-security` (PR [#3](https://github.com/Smash2210/agentic-app/pull/3)).
- **Standards:** OWASP ASVS 4.0.3 **Level 1**, the requirements that apply to a JSON API with no
  sessions, passwords or file uploads; and the four pillars from *Governing AI Agents*.
- **Method:** automated scanners in CI, AI triage of their output, and a context-aware AI code review
  (from M03) for the logic and access-control issues scanners cannot see. Every finding below was
  reproduced against a running app.

## 1. Summary

| | Count |
|---|---|
| Real findings remediated in M06 | **4** (S2, S3, S4, P2), each with tests that reproduce the attack |
| Real findings accepted as known risk, with a plan | 1 high (S1 access control) + 3 low (rate limiting, security headers, employee ID in URL) |
| Scanner findings | 5 bandit (all false positives, triaged), 0 semgrep, 0 pip-audit, 0 gitleaks |

**The main result:** the pattern scanners found nothing real. Every real issue was a business-logic,
input-bounds or access-control problem. They were found by an AI reviewer that read the spec and the
code together, then confirmed by hand.

## 2. Real findings and remediation

From the M03 AI review ([../M03-testing/ai-review.md](../M03-testing/ai-review.md)), fixed spec-first
in commit `805472e`: the spec (`specs/001-claims-api/spec.md`, Clarifications "M06 security" and
FR-002) was amended, then tests, then `schemas.py`.

| ID | Finding (reproduced before the fix) | Risk | Remediation | Verified after the fix |
|---|---|---|---|---|
| **S2** | A 31-digit amount was accepted and stored, then every check of that claim crashed with a 500 (Decimal precision exceeded) | med | Amount must be plain decimal text, at most 1,000,000.00 | 31-digit amount → 422; 1,000,000.00 → 201; 1,000,000.01 → 422 |
| **S3** | No bound on trip length: a trip to 9999-12-31 with a 2,900,000-night lodging line made **every** check take 4.5 s (easy denial of service) | med | Trip at most 366 days; at most 50 lines; text fields at most 200 characters | the attack → 422; 366-day trip → 201, 367 → 422; 50 lines → 201, 51 → 422 |
| **S4** | `employee_id` was not trimmed, so the same expense under `" E-7"` was not detected as a duplicate of `"E-7"`, and could be paid twice | med | `employee_id` trimmed on input, like currency codes | `" E-7 "` stored as `"E-7"`; the second claim gets `DUPLICATE` |
| **P2** | `"1e2"` accepted as an amount and stored/echoed as `"1E+2"` | low | Same plain-decimal rule as S2 | `"1e2"` → 422; `"12.5"` and `" 12.50"` still accepted |

Tests added (none existing changed): `tests/claims/test_schemas.py` (each bound at the limit and
just over it), `tests/claims/test_api_submit.py` and `test_api_check.py` (each original attack
replayed through the API). Suite: 307 passed.

## 3. Scanners and AI triage

`.github/workflows/security.yml` runs on every push to `master` and every PR, with pinned tool
versions:

| Scanner | Scope | Result | AI triage | Decision |
|---|---|---|---|---|
| gitleaks v8.21.2 | whole git history | 0 secrets | n/a | — |
| pip-audit 2.10.1 | locked dependencies (`uv export`) | 0 known vulnerabilities | n/a | — |
| semgrep 1.186.0 (`p/python`, 151 rules) | `src`, `review`, `scripts` | 0 findings | n/a | — |
| bandit 1.9.4 B608 × 2 | `claims/store.py:54`, `:103` | "possible SQL injection" (medium) | **False positive.** The f-string inserts only the constant `_LINE_COLUMNS`; every value is a `?` parameter. Bandit flags the pattern without tracing the input. | Suppressed with `# nosec B608` and the reason on the line (`0a861ed`); the gate passed once it was |
| bandit B404, B603, B607 | `review/run_review.py:15`, `:65` | `subprocess` use (low) | **Not exploitable here.** It runs `git` with fixed arguments and no shell, in CI only. B607 (partial path) relies on the runner's `PATH`, which is GitHub-controlled. | Accepted; below the CI threshold (`-ll`, medium and above) |

The first CI run of PR #3 failed on the two B608 findings before the suppressions were added. That
shows the gate works, and that each suppression is a reviewed decision with a reason, not a bulk
ignore.

## 4. OWASP ASVS 4.0.3 Level 1 checklist (applicable items)

| Requirement | Status | Evidence / reason |
|---|---|---|
| V2 Authentication (whole chapter) | **Fail: accepted risk** | No authentication exists. Spec 001 puts auth out of scope; callers state the employee ID. Planned in M12 (caller identity on the MCP server). |
| 4.1.1 Access control enforced on a trusted service layer | **Fail: accepted risk (S1)** | None; see S1 below |
| 4.2.1 Protection against insecure direct object references | **Fail: accepted risk (S1)** | Any caller can `GET /claims/{id}` for any integer ID, and list any employee's claims. Reproduced. |
| 5.1.3 Input validated against an allow list | Pass | Pydantic models: category enum, plain-decimal amount pattern, date ranges, bounds (M06) |
| 5.1.4 Structured data strongly typed and validated against a schema | Pass | Every request body is a Pydantic model; JSON numbers refused for money |
| 5.3.4 Parameterised queries | Pass | Every SQL value is a `?` parameter (bandit B608 triaged above) |
| 7.4.1 Generic error message on unexpected errors | Pass | A forced internal error returns `500 Internal Server Error` with no detail or path |
| 8.3.1 No sensitive data in URL query strings | **Partial: accepted** | `GET /claims?employee_id=…` puts the employee ID in the URL (and so in server logs). Synthetic data now; M12 takes identity from the caller, not a query parameter. |
| 9.1.1 TLS for all client connections | n/a locally | Runs on localhost in development. The deployed service (M10, Agent Engine) is served over HTTPS. |
| 11.1.4 Anti-automation (rate limiting) | **Fail: accepted, low** | No rate limiting. Local service only; S3's bounds remove the cheapest slow request. Revisit at deployment. |
| 13.2.1 Only valid HTTP methods enabled | Pass | `DELETE` and `PUT` on a claim → 405 |
| Content type of requests checked | Pass | A form-encoded `POST /claims` → 422 |
| 14.2.1 Components up to date, no known vulnerabilities | Pass | pip-audit in CI, 0 findings |
| 14.3.2 Debug modes disabled | Pass | `app.debug` is false; no stack traces in responses |
| 14.4.4 `X-Content-Type-Options: nosniff` on responses | **Fail: accepted, low** | Header not set. JSON-only API, so little impact; a one-line middleware when deployed. |
| 14.5.3 CORS origin allow list | Pass | No CORS middleware: browsers on other origins cannot read responses |

### S1, the accepted high risk

**Finding:** no access control. Anyone who can reach the service can read every claim (integer IDs
are guessable) and list any employee's claims.
**Why accepted now:** authentication and roles are explicitly out of scope in spec 001; the
service runs only on localhost with synthetic data.
**Plan:** M12 adds caller identity and scopes on the MCP server (employees read their own claims and
draft; managers approve; nobody approves their own claim). The direct API must then be either bound
to localhost only or given the same identity check.
**Do not deploy the Claims API on a reachable network before then.**

## 5. Governing AI Agents: four pillars

| Pillar | Status | Evidence |
|---|---|---|
| **Lifecycle** | Pass | Constitution v1.0.0 governs every change; spec-first (specs amended before code in M03 and M06); one frozen tag per module; CI gates on every PR |
| **Risk** | Partial | Money decisions are made by deterministic code (Principle III); no model in Tier 1. Accepted risks listed with owners and plans (section 4). No formal risk register yet (M16 model card). |
| **Security** | Partial | Least privilege in CI (read-only token; the Gemini key given only to the AI review step); the coding agent is denied `.env`; secret, dependency and code scanning in CI; input bounds. **Gap:** no access control (S1). |
| **Observability** | Fail: planned | No application logging or tracing yet. The AI review gate's verdicts are kept as PR comments (an audit trail for AI decisions). Tracing (OpenTelemetry → Langfuse) is planned for M10. |

## 6. How AI was used, and what it could see

See [ai-data-statement.md](ai-data-statement.md).
