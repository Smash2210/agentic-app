# Implementation Plan: Policy Q&A

**Spec**: [spec.md](spec.md) | **Branch**: `003-policy-qa`

## Modules (`src/agentic_app/rag/`)

| Module | Does |
|---|---|
| `chunks.py` | `load_chunks(policy_dir)`: one `Chunk` per `## N.` section of every policy file, ID `<doc_id>#<N>`; the text embedded and searched is "doc title — section title: body" |
| `index.py` | `PolicyIndex`: BM25 (`rank-bm25`) over lower-cased word tokens; cosine similarity over embeddings; **RRF** (`1 / (60 + rank)`, summed over both rankings of the top 20) → top 5 `Hit`s with fused score, both ranks and the embedding similarity |
| `embeddings.py` | `embed(texts, task)` via `gemini-embedding-001`, 256 dimensions; a cache file `data/index/embeddings.json` keyed by chunk ID + text hash, so passages are embedded once and the index loads offline. Only the question needs a live call. |
| `ask.py` | Phase 1: the model with the `search_policy` tool (max 2 turns). Gate: refusal if the best similarity is below `REFUSAL_THRESHOLD`. Phase 2: `generate_content_stream` with the retrieved passages; then citation check |

`POST /ask` (in `claims/api.py`, imported lazily like `/adjudicate`): phase 1 runs before the response
starts, so `ModelUnavailable` can still be a 503; phase 2 streams as `text/event-stream`.

## Decisions

- **In-memory index, no vector database.** The corpus is 13 documents and ~40 passages. Brute-force
  cosine over 40 × 256 numbers takes microseconds, and the vectors fit in a ~100 KB JSON file.
  Chroma or another vector DB would add a heavy dependency for nothing at this size (Principle VI).
  At scale, the managed equivalent is **Vertex AI Vector Search** (ANN index, also supports hybrid
  search), behind the same `PolicyIndex.search()` interface.
- **256 dimensions** (Matryoshka truncation of `gemini-embedding-001`): smaller cache, and enough for
  ~40 passages. Documents are embedded with `RETRIEVAL_DOCUMENT`, questions with `RETRIEVAL_QUERY`.
- **Refusal in two layers, one refusal text written by code.** RRF scores are rank-based and say
  nothing about absolute relevance, so the gate uses the embedding similarity of the question's best
  passage. The evaluation showed it cannot separate the classes on its own: weakest answerable 0.716,
  strongest unanswerable 0.710 ("vacation days"). So:
  (1) **gate**: below 0.70, refuse without any model call (catches clearly off-topic questions, with
  a 0.016 margin under every answerable one);
  (2) **model judgement**: for questions that pass the gate, the model must reply exactly
  `NOT_IN_POLICY` if the passages do not answer; the code holds back the first streamed characters to
  spot it, and sends the fixed refusal instead.
- **New dependency: `rank-bm25`** (BM25Okapi). The alternative, writing BM25 by hand, is about 30
  lines, but a reviewed library is less to get wrong. It brings **numpy** with it; our own code still
  uses plain lists for vectors (40 × 256 numbers need nothing faster).
- **Streaming retry**: `llm.generate_content_stream()` retries and falls back like
  `generate_content()`, but only until the first chunk arrives; after that, an error ends the stream
  with an `error` event.

## Constitution check

| Principle | How |
|---|---|
| I Spec-first | Spec and plan before code |
| II Policy source of truth | Answers may use only retrieved policy passages and must cite them; uncited answers are marked ungrounded |
| III Deterministic core | No money decisions here; the refusal gate is code, not the model |
| IV Money | Not touched |
| V Test-first, offline | Model and embeddings faked in tests; the passage embeddings load from the committed cache |
| VI Simplicity | One direct dependency (`rank-bm25`, which brings numpy); no vector DB |
