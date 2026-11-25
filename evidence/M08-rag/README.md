# M08 — RAG and an AI-native backend: `POST /ask`

**Outcome:** an application backend that answers grounded, cited questions and streams responses in
real time.

| Required | Where |
|---|---|
| Backend | `POST /ask` ([src/agentic_app/rag/](../../src/agentic_app/rag/), route in `claims/api.py`), spec-first: [specs/003-policy-qa/](../../specs/003-policy-qa/) |
| Grounded retrieval as a tool | The model gets `search_policy(query)` and decides what to search; hybrid BM25 + embeddings fused with Reciprocal Rank Fusion |
| Citations | Inline `[POL-XXX#n]`, checked against the passages actually retrieved; anything else is reported as `unverified` |
| Streaming | Server-Sent Events: `token` … `citations` → `done` ([sse-minibar.txt](sse-minibar.txt), [sse-wine-with-client.txt](sse-wine-with-client.txt), [sse-refusal-dress-code.txt](sse-refusal-dress-code.txt)) |
| Refusal | [sse-refusal-dress-code.txt](sse-refusal-dress-code.txt); all 4 unanswerable golden questions refused ([ask-results.md](ask-results.md)) |
| Retrieval evaluation | [retrieval-eval.md](retrieval-eval.md) |
| Tests | [tests/test_rag.py](../../tests/test_rag.py): 21 offline tests (model and question embeddings faked, real cached passage vectors); suite 354 passed, coverage 94% |

## How it works

```
question ─► embed question ─► GATE: best passage similarity < 0.70? ─► refusal (no model call)
                │
                └─► model + tool search_policy(query) ─► hybrid search (BM25 ⊕ vectors, RRF) ─► top 5 passages
                        │
                        └─► model streams the answer from those passages only, citing [POL-X#n]
                              ├─ starts with NOT_IN_POLICY ─► the same refusal, written by code
                              └─ otherwise: token events, then citations checked against retrieved IDs
```

- **Corpus:** 13 policy documents (the 5 the rules engine reads plus 8 new synthetic ones), split
  into **44 passages**, one per numbered section, with IDs like `POL-MEALS#2`: the same section
  numbers the M02 rules engine cites in its violations.
- **Embeddings:** `gemini-embedding-001`, 256 dimensions, documents and questions embedded with
  their own task types. Passage vectors are cached in `data/index/embeddings.json` (108 KB,
  committed; re-embedded only when a passage's text changes), so the index loads offline and only
  the question needs a live call.
- **No vector database.** 44 × 256 numbers are searched by brute force in microseconds; Chroma or
  similar would add a heavy dependency for nothing (Principle VI). At scale, the managed equivalent
  is Vertex AI Vector Search behind the same `PolicyIndex.search()`.

## Retrieval evaluation (16 answerable + 4 unanswerable questions)

| Method | Recall@5 | MRR |
|---|---|---|
| BM25 (keywords) | 0.875 | 0.802 |
| Vector (embeddings) | **1.000** | **0.969** |
| Hybrid (RRF) | **1.000** | **0.969** |

**Read honestly:** hybrid ties vector search here; it does not beat it. BM25 alone missed two
paraphrased questions (e.g. "submit my claim" vs "claims must be submitted within 30 days"). On a
small, clean corpus, embeddings already find everything. Hybrid is kept because it is never worse
here, and it protects the cases embeddings handle badly (exact codes, IDs, rare terms) once the
corpus grows. SC-301 ("at least as good as either method alone") holds.

## Refusal: does it refuse or fabricate? (the reviewer's question)

It refuses. The evaluation showed a single similarity threshold is not safe: the weakest
answerable question scored **0.716**, and "How many vacation days do I get per year?" scored
**0.710**. So refusal has two layers, and both send the same code-written text:

1. **Gate (code):** best similarity below **0.70**: refuse at once, with no model call. That
   threshold sits 0.016 under every answerable golden question.
2. **Model judgement:** above the gate, the model must answer exactly `NOT_IN_POLICY` when the
   passages do not cover the question. The code holds back the first streamed characters to spot
   it, and never shows the model's own wording.

Live, all 20 golden questions ([ask-results.md](ask-results.md)):

| | Result |
|---|---|
| 16 answerable | all answered, all grounded, **0 unverified citations**, facts correct (75 USD meals, 70 USD London per diem, business class only over 8 h with VP approval, 0.40 USD/km, …) |
| 4 unanswerable | **all refused**: dress code, parental leave and performance reviews by the gate (~0.6 s, no model call); vacation days (0.710, above the gate) by the model |

## Things a reviewer may probe

- **A cited passage that was not retrieved** is listed under `unverified`, not as a citation; an
  answer with no valid citation has `grounded: false`. Both are tested offline, and neither happened
  live.
- **Errors while streaming:** retries and fallback models apply until the first chunk arrives;
  after that, an `error` event ends the stream (HTTP status is already 200). Before streaming, a
  model outage is HTTP 503.
- **Caching:** the instructions are a fixed system prompt, but at ~1k tokens they are below the
  ~4k-token prefix implicit caching needs (measured in M07).
- **Fixed during the build:** an empty `token` event was sent for the stream's last, text-less
  chunk. Fixed, tested, and the transcript re-recorded.

## Reproduce

```bash
uv run pytest -q tests/test_rag.py              # offline, no key
uv run python scripts/eval_retrieval.py         # live: retrieval evaluation
uv run python scripts/run_ask_examples.py       # live: all 20 golden questions through /ask
```
