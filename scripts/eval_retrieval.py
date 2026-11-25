"""Retrieval evaluation (spec 003 FR-308): recall@5 and MRR for BM25, vector and hybrid retrieval
over data/golden/retrieval.jsonl, plus the best-passage similarity used for the refusal threshold.

    uv run python scripts/eval_retrieval.py

Needs GOOGLE_API_KEY for the question embeddings (passages come from data/index/embeddings.json).
"""

import json
from pathlib import Path

from agentic_app.rag.chunks import load_chunks
from agentic_app.rag.embeddings import gemini_embed, passage_vectors
from agentic_app.rag.index import TOP_K, PolicyIndex

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "evidence" / "M08-rag" / "retrieval-eval.md"
MODES = ("bm25", "vector", "hybrid")


def main() -> None:
    chunks = load_chunks(REPO / "data" / "policies")
    index = PolicyIndex(chunks, passage_vectors(chunks, REPO / "data" / "index" / "embeddings.json"))
    golden = [json.loads(line) for line in (REPO / "data" / "golden" / "retrieval.jsonl").open()]
    vectors = gemini_embed([g["question"] for g in golden], "RETRIEVAL_QUERY")

    totals = {m: {"recall": 0.0, "rr": 0.0} for m in MODES}
    rows = []
    answerable = [g for g in golden if g["answerable"]]
    for g, vector in zip(golden, vectors):
        best = index.best_similarity(vector)
        row = {"id": g["id"], "answerable": g["answerable"], "best_similarity": best}
        for mode in MODES:
            ids = [h.chunk.id for h in index.search(g["question"], vector, mode=mode)]
            if g["answerable"]:
                found = [i for i in ids if i in g["relevant"]]
                totals[mode]["recall"] += len(found) / len(g["relevant"])
                first = next((r for r, i in enumerate(ids, 1) if i in g["relevant"]), None)
                totals[mode]["rr"] += 1 / first if first else 0.0
                row[mode] = first
        rows.append(row)

    lines = [f"# Retrieval evaluation ({len(answerable)} answerable + "
             f"{len(golden) - len(answerable)} unanswerable questions, {len(chunks)} passages)", "",
             f"| Method | Recall@{TOP_K} | MRR |", "|---|---|---|"]
    for mode in MODES:
        n = len(answerable)
        lines.append(f"| {mode} | {totals[mode]['recall'] / n:.3f} | {totals[mode]['rr'] / n:.3f} |")
    lines += ["", "Rank of the first relevant passage per question (— = not in the top 5), and the "
              "best embedding similarity of any passage (the refusal signal):", "",
              "| Question | Answerable | BM25 | Vector | Hybrid | Best similarity |", "|---|---|---|---|---|---|"]
    for r in rows:
        ranks = [str(r.get(m) or "—") if r["answerable"] else "n/a" for m in MODES]
        lines.append(f"| {r['id']} | {'yes' if r['answerable'] else 'no'} | {' | '.join(ranks)} "
                     f"| {r['best_similarity']:.3f} |")
    low = min(r["best_similarity"] for r in rows if r["answerable"])
    high = max(r["best_similarity"] for r in rows if not r["answerable"])
    lines += ["", f"Lowest best-similarity among answerable questions: **{low:.3f}**. "
              f"Highest among unanswerable: **{high:.3f}**."]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
