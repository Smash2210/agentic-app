# Style rules for API docs

- Write for an API user who has never seen the code. No internal names (task IDs, spec FR numbers,
  "user story") unless the API itself exposes them.
- Copy field names, enum values and status codes exactly from the spec.
- Money, dates and IDs: show the exact JSON form the API uses (e.g. "12.50" as a string).
- Prefer citing a source document over repeating a number that lives there.
- Present tense, short sentences, tables over prose for fields.
- Never invent an example value that contradicts a schema rule (type, enum, min/max, pattern).
