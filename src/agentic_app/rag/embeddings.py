"""Embeddings for retrieval (spec 003): gemini-embedding-001, 256 dimensions, passages cached on disk.

The cache (data/index/embeddings.json) is keyed by passage ID and a hash of its text, so a passage is
embedded again only when it changes, and the index loads offline. Only questions need a live call.
"""

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from agentic_app.rag.chunks import Chunk

MODEL = "gemini-embedding-001"
DIMENSIONS = 256
BATCH = 50

Embedder = Callable[[list[str], str], list[list[float]]]  # (texts, task_type) -> vectors


def gemini_embed(texts: list[str], task_type: str) -> list[list[float]]:
    from agentic_app import llm  # loaded only when embeddings are needed

    vectors = []
    for start in range(0, len(texts), BATCH):
        vectors += llm.embed(texts[start:start + BATCH], model=MODEL, task_type=task_type,
                             dimensions=DIMENSIONS)
    return vectors


def _hash(chunk: Chunk) -> str:
    return hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()[:16]


def passage_vectors(
    chunks: Sequence[Chunk], cache_path: Path, embed: Embedder = gemini_embed
) -> dict[str, list[float]]:
    """A vector per passage: from the cache where the text is unchanged, otherwise embedded now and
    written back to the cache."""
    cache_path = Path(cache_path)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    if cache.get("model") != MODEL or cache.get("dimensions") != DIMENSIONS:
        cache = {"model": MODEL, "dimensions": DIMENSIONS, "passages": {}}
    stored = cache["passages"]
    stale = [c for c in chunks if stored.get(c.id, {}).get("hash") != _hash(c)]
    if stale:
        for chunk, vector in zip(stale, embed([c.text for c in stale], "RETRIEVAL_DOCUMENT")):
            stored[chunk.id] = {"hash": _hash(chunk), "vector": [round(x, 6) for x in vector]}
    known = {c.id for c in chunks}
    if stale or set(stored) - known:
        cache["passages"] = {k: v for k, v in sorted(stored.items()) if k in known}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, separators=(",", ":")) + "\n", encoding="utf-8")
    return {c.id: cache["passages"][c.id]["vector"] for c in chunks}
