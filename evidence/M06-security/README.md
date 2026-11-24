# M06 — AI-assisted security and compliance checks

**Outcome:** a security and compliance report with at least one real finding and its remediation,
and a written statement of how AI tooling was used on the codebase without exposing data it should
not have seen.

| Required | Where |
|---|---|
| Security and compliance report | [report.md](report.md): scanner results with AI triage, ASVS 4.0.3 L1 checklist, *Governing AI Agents* pillars, accepted risks |
| Real findings and remediation | [report.md §2](report.md#2-real-findings-and-remediation): **4 fixed** (S2, S3, S4, P2) spec-first in `805472e`, each attack replayed as a test |
| AI data-exposure statement | [ai-data-statement.md](ai-data-statement.md) |
| Security pipeline | [.github/workflows/security.yml](../../.github/workflows/security.yml): gitleaks, pip-audit, bandit, semgrep, all green on PR [#3](https://github.com/Smash2210/agentic-app/pull/3) |

## In one paragraph

The pattern scanners (semgrep, bandit, pip-audit, gitleaks) found nothing real: five bandit items,
all false positives, triaged and suppressed with reasons. The real problems came from an AI
reviewer that read the spec and the code together, and each was reproduced by hand:
- a huge amount crashed every check;
- an unbounded trip made every check take 4.5 s;
- an untrimmed employee ID let a duplicate be paid twice;
- exponent-notation amounts were accepted.

All four are fixed spec-first, with tests that replay each attack. The one high risk left, no
access control (S1), is accepted with a written plan for M12, because auth is out of scope in the
current spec.

**Probe:** "What may an AI tool be shown when pointed at client code, and what enforces that?" →
[ai-data-statement.md](ai-data-statement.md), last section.
