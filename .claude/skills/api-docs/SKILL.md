---
name: api-docs
description: Generate endpoint documentation and a README section for an HTTP service from its OpenAPI spec and source code. Use when asked to document an API, refresh API docs, or write docs for a service.
---

# API docs from OpenAPI

Input: the service to document (a folder, an app module, or an OpenAPI file). Ask if not given.
Works for any service with an OpenAPI 3 spec; nothing here is specific to one project.

## Steps

1. **Get the spec.** Use an existing `openapi.json`/`openapi.yaml` for the service if there is one.
   For a FastAPI app with no exported file, export it (`app.openapi()`) without starting a server
   or touching real data. If there is no spec and none can be generated, stop and say so.
2. **Read the code behind each operation** (route handler, request/response models) to learn what the
   spec does not say: side effects, ordering, when each error happens.
3. **Write `docs/api/<service>.md`** following `references/doc-template.md` and the rules in
   `references/style.md`.
4. **Update the README** section between `<!-- api-docs:<service>:start -->` and
   `<!-- api-docs:<service>:end -->` (add the markers at the end of the file if missing): a short
   overview, how to run it, and a link to the full doc. Never change text outside the markers.
5. **Check your output** before finishing:
   - every operation in the spec appears in the doc, and nothing appears that is not in the spec
   - every field name, status code and example matches the spec exactly
   - every claim about behaviour comes from the spec or the code you read; if unsure, write
     "Not specified" rather than guessing
6. **Report** what you wrote, anything you could not determine, and any mismatch you found between the
   spec and the code (do not fix code).