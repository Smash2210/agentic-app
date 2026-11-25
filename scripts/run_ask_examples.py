"""Ask every golden question through POST /ask against the live model (M08 evidence, SC-302/303).

    uv run python scripts/run_ask_examples.py

Writes evidence/M08-rag/ask-results.md (one row per question) and three raw SSE transcripts.
Needs GOOGLE_API_KEY and GEMINI_MODEL; about 3 model calls and 2 embedding calls per question.
"""

import json
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from agentic_app.app import create_app

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "evidence" / "M08-rag"
TRANSCRIPTS = {"q01": "sse-minibar.txt", "q06": "sse-wine-with-client.txt", "q20": "sse-refusal-dress-code.txt"}


def main() -> None:
    client = TestClient(create_app(Path(tempfile.mkdtemp()) / "claims.db", REPO / "data" / "policies"))
    golden = [json.loads(line) for line in (REPO / "data" / "golden" / "retrieval.jsonl").open()]
    rows = ["| Q | Answerable | Refused | Grounded | Citations | Unverified | Similarity | s | Answer |",
            "|---|---|---|---|---|---|---|---|---|"]
    ok = True
    for g in golden:
        start = time.monotonic()
        with client.stream("POST", "/ask", json={"question": g["question"]}) as response:
            raw = "".join(response.iter_text())
        events = [(b.split("\n", 1)[0].removeprefix("event: "), json.loads(b.split("\n", 1)[1].removeprefix("data: ")))
                  for b in raw.split("\n\n") if b.strip()]
        answer = "".join(d for e, d in events if e == "token")
        cites = next((d for e, d in events if e == "citations"), {})
        refused = cites.get("refused")
        right = refused == (not g["answerable"]) and not cites.get("unverified")
        ok &= right
        if g["id"] in TRANSCRIPTS:
            (OUT / TRANSCRIPTS[g["id"]]).write_text(f"POST /ask {json.dumps({'question': g['question']})}\n\n{raw}", encoding="utf-8")
        rows.append(f"| {g['id']} | {'yes' if g['answerable'] else 'no'} | {refused} | {cites.get('grounded')} "
                    f"| {', '.join(c['id'] for c in cites.get('citations', []))} | {', '.join(cites.get('unverified', []))} "
                    f"| {cites.get('question_similarity')} | {time.monotonic() - start:.1f} "
                    f"| {answer.replace('|', '/')[:160]}{' ✅' if right else ' ❌'} |")
        print(rows[-1], flush=True)
    (OUT / "ask-results.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("ALL AS EXPECTED" if ok else "SOME NOT AS EXPECTED")


if __name__ == "__main__":
    main()
