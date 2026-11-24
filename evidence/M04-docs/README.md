# M04 — Documentation and API design automation

**Outcome:** generated and human-reviewed documentation and an OpenAPI (or equivalent)
specification, plus the reusable workflow that produced them.

| Required | Where |
|---|---|
| OpenAPI specification | [docs/api/openapi.json](../../docs/api/openapi.json), generated from the code by [scripts/exports_openapi.py](../../scripts/exports_openapi.py) |
| Generated documentation | [docs/api/claims.md](../../docs/api/claims.md) and the README section between the `api-docs:claims` markers (commit `6682b2c`, committed as generated) |
| Human review | [review-notes.md](review-notes.md): checks made, decisions, a workflow defect found and fixed |
| Reusable workflow | Claude Code Agent Skill [.claude/skills/api-docs/](../../.claude/skills/api-docs/): `SKILL.md` + `references/doc-template.md` + `references/style.md` |

## How the pieces fit

1. **Spec from the source.** Route summaries and descriptions, field descriptions, a request example
   and the 404 responses are written in the code (`claims/api.py`, `schemas.py`, `app.py`, commit
   `ece4837`), so the spec cannot drift from the implementation. That commit was docs-only:
   comparing the OpenAPI before and after with every description and example removed showed only
   the added 404 responses and their `NotFound` model.
2. **Exported and guarded.** `exports_openapi.py` writes `openapi.json` with sorted keys and a
   throwaway database. `--check` fails if the committed file is stale, and
   `tests/test_openapi.py` runs that check in the normal test suite (M05 adds it to CI).
3. **Docs from the spec.** The `api-docs` skill reads the spec and the code behind each operation
   and writes the endpoint reference and README section. It checks its own output against the spec
   and reports anything it could not determine instead of guessing.
4. **Human review** of the output, recorded separately from the generated commit.

## Why it is reusable

- Nothing in the skill mentions this project: the service is an input, and it works from any
  OpenAPI 3 spec (exporting one for a FastAPI app if needed).
- Progressive disclosure: only the skill's short description is in context until it is used; the
  template and style rules are loaded at the step that needs them.
- It writes only between its own README markers, so re-running it updates its section without
  touching anything else.

## Not done

- **The reviewer's question "run your documentation workflow on a service it has not seen" has not
  been tried yet.** Expected weak points to check when it is: services with no OpenAPI spec (the
  skill stops; it does not reverse-engineer routes), auth schemes (the template only has a one-line
  auth note), and specs with no examples (examples must then be built from field types). The M13
  `portal/` and M12 `mcp_server/` are the natural first unseen services.

**Probe:** "Run your documentation workflow on a service it has not seen. What breaks?" → see "Not
done" above; try it on `portal/` in M13.
