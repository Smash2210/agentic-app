# <Service title> API

<One paragraph: what the service does, for whom. Base URL and auth (say "none" if none).>

## Endpoints

| Method | Path | Summary |
|---|---|---|

## <METHOD> <path> — <summary>

<What it does and when to use it. Side effects.>

**Request** — parameters table (name, in, type, required, description) and/or body fields table.

Example request (from the spec's example, or built only from spec fields):

```bash
curl ...
```

**Responses** — one row per status code: when it happens, body shape.

Example response (`200`/`201`):

```json
...
```

(repeat per endpoint)

## Models

One table per schema: field, type, required, description. Enums list every value.

## Errors

How errors look (body shape) and every status code the API returns, with the cause.