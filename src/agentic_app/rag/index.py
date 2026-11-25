"""Hybrid retrieval (spec 003 FR-302): BM25 + embedding similarity, fused with Reciprocal Rank Fusion.

RRF only uses ranks, so it needs no score calibration between the two methods; but for the same
reason a fused score says nothing about absolute relevance. The refusal gate therefore uses the
embedding similarity of the best passage (best_similarity), not the fused score.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from agentic_app.rag.chunks import Chunk

TOP_K = 5
CANDIDATES = 20  # how deep each ranking goes into the fusion
RRF_K = 60  # the usual RRF constant: damps the difference between rank 1 and rank 2

_WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _unit(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float  # fused RRF score (or the single method's score in "bm25"/"vector" mode)
    bm25_rank: int | None  # 1-based; None if not in the BM25 candidates
    vector_rank: int | None
    similarity: float  # cosine similarity between the query and this passage


class PolicyIndex:
    def __init__(self, chunks: Sequence[Chunk], vectors: dict[str, Sequence[float]]):
        self.chunks = list(chunks)
        self._bm25 = BM25Okapi([tokens(c.text) for c in self.chunks])
        self._vectors = [_unit(vectors[c.id]) for c in self.chunks]

    def _similarities(self, query_vector: Sequence[float]) -> list[float]:
        q = _unit(query_vector)
        return [sum(a * b for a, b in zip(q, v)) for v in self._vectors]

    def best_similarity(self, query_vector: Sequence[float]) -> float:
        return max(self._similarities(query_vector))

    def search(self, query: str, query_vector: Sequence[float], *, k: int = TOP_K,
               mode: str = "hybrid") -> list[Hit]:
        """Top k passages. mode: "hybrid" (RRF of both), "bm25" or "vector" (for the evaluation)."""
        sims = self._similarities(query_vector)
        bm25_scores = self._bm25.get_scores(tokens(query))
        by_bm25 = [i for i in sorted(range(len(self.chunks)), key=lambda i: -bm25_scores[i])
                   if bm25_scores[i] > 0][:CANDIDATES]
        by_vector = sorted(range(len(self.chunks)), key=lambda i: -sims[i])[:CANDIDATES]
        bm25_rank = {i: r for r, i in enumerate(by_bm25, 1)}
        vector_rank = {i: r for r, i in enumerate(by_vector, 1)}

        if mode == "bm25":
            scores = {i: float(bm25_scores[i]) for i in by_bm25}
        elif mode == "vector":
            scores = {i: sims[i] for i in by_vector}
        elif mode == "hybrid":
            scores = {}
            for ranks in (bm25_rank, vector_rank):
                for i, rank in ranks.items():
                    scores[i] = scores.get(i, 0.0) + 1.0 / (RRF_K + rank)
        else:
            raise ValueError(f"unknown mode {mode!r}")

        top = sorted(scores, key=lambda i: (-scores[i], self.chunks[i].id))[:k]
        return [Hit(self.chunks[i], scores[i], bm25_rank.get(i), vector_rank.get(i), sims[i])
                for i in top]
