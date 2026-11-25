"""Run spec 002's acceptance examples A-D against the live model and save the results (M07 evidence).

    uv run python scripts/run_adjudicate_examples.py            # examples A-D
    uv run python scripts/run_adjudicate_examples.py --repeat 3 # also run example C 3 more times (cache)

Needs GOOGLE_API_KEY and GEMINI_MODEL. Uses the free tier: about 3-4 model calls per example.
No stored claims are used (no duplicates), so results depend only on the receipts.
"""

import argparse
import json
from pathlib import Path

from agentic_app.adjudicate import adjudicate
from agentic_app.claims.policy import load_policy
from agentic_app.schemas import AdjudicateRequest

REPO = Path(__file__).resolve().parents[1]
RECEIPTS = REPO / "data" / "receipts"
OUT = REPO / "evidence" / "M07-adjudicate"

EXAMPLES = {
    "A": ("E-001", ("Berlin", "2026-03-10", "2026-03-13"), ["r1-berlin-hotel.txt", "r2-berlin-dinner-wine.txt"], "needs_human_review"),
    "B": ("E-002", ("London", "2026-04-20", "2026-04-21"), ["r3-london-taxis.txt", "r4-london-dinner.txt"], "partial"),
    "C": ("E-002", ("London", "2026-04-20", "2026-04-21"), ["r3-london-taxis.txt"], "approve"),
    "D": ("E-003", ("Paris", "2026-05-04", "2026-05-05"), ["r5-unreadable-taxi.txt"], "needs_human_review"),
}


def request(name: str) -> AdjudicateRequest:
    employee, (city, start, end), files, _ = EXAMPLES[name]
    return AdjudicateRequest.model_validate({
        "employee_id": employee,
        "trip": {"destination_city": city, "start_date": start, "end_date": end},
        "receipts": [(RECEIPTS / f).read_text(encoding="utf-8") for f in files],
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=0, help="extra runs of example C for cache numbers")
    args = parser.parse_args()
    policy = load_policy(REPO / "data" / "policies")
    OUT.mkdir(parents=True, exist_ok=True)

    rows = []
    for name in EXAMPLES:
        result = adjudicate(request(name), [], policy)
        (OUT / f"example-{name}.json").write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        expected = EXAMPLES[name][3]
        total = result.check.total_reimbursable_usd if result.check else None
        rows.append((name, expected, result.decision.value, total, result.usage))
        print(f"{name}: expected {expected}, got {result.decision.value}, total {total}")

    usage_rows = [(f"{n} ({d})", u) for n, _, d, _, u in rows]
    for i in range(args.repeat):
        usage_rows.append((f"C repeat {i + 1}", adjudicate(request("C"), [], policy).usage))

    lines = ["| Run | Calls | Prompt tokens | Cached tokens | Cached % | Reasoning tokens | Model time (ms) |",
             "|---|---|---|---|---|---|---|"]
    for label, u in usage_rows:
        pct = 100 * u.cached_tokens / u.prompt_tokens if u.prompt_tokens else 0
        lines.append(f"| {label} | {u.model_calls} | {u.prompt_tokens} | {u.cached_tokens} | {pct:.0f}% "
                     f"| {u.thoughts_tokens} | {u.latency_ms} |")
    (OUT / "usage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    summary = [{"example": n, "expected": e, "decision": d, "total_usd": str(t) if t is not None else None}
               for n, e, d, t, _ in rows]
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
