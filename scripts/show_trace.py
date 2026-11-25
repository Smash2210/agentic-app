"""Print one trace from an OTel JSON-lines file (spec 005 FR-505) as an indented span tree.

    uv run python scripts/show_trace.py evals/traces.jsonl --case C07     # the trace of eval case C07
    uv run python scripts/show_trace.py run.jsonl                         # the last trace in the file

Each line: span name, duration, the attributes that matter (tool name/args/status/error, model), then
the span's events (guardrail decisions, model output) indented under it, all in time order.
"""

import argparse
import json
import sys
from datetime import datetime

KEEP = ("tool.", "error.", "eval.", "gen_ai.request.model", "gen_ai.tool.name")


def _t(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def pick(spans: list[dict], case: str | None, trace_id: str | None) -> list[dict]:
    if case:
        roots = [s for s in spans if s["attributes"].get("eval.case_id") == case]
        if not roots:
            sys.exit(f"no trace for case {case}")
        trace_id = roots[-1]["context"]["trace_id"]
    trace_id = trace_id or spans[-1]["context"]["trace_id"]
    return [s for s in spans if s["context"]["trace_id"] == trace_id]


def render(spans: list[dict], width: int = 160) -> str:
    children: dict[str | None, list[dict]] = {}
    ids = {s["context"]["span_id"] for s in spans}
    for s in spans:
        parent = s["parent_id"] if s["parent_id"] in ids else None
        children.setdefault(parent, []).append(s)
    out = [f"trace {spans[0]['context']['trace_id']}"]

    def walk(span, depth):
        ms = (_t(span["end_time"]) - _t(span["start_time"])) * 1000
        attrs = {k: v for k, v in span["attributes"].items() if k.startswith(KEEP)}
        status = "" if span["status"]["status_code"] == "UNSET" else f" [{span['status']['status_code']}]"
        out.append(f"{'  ' * depth}{span['name']} ({ms:.0f} ms){status} "
                   f"{json.dumps(attrs, ensure_ascii=False) if attrs else ''}"[:width])
        items = [(_t(c["start_time"]), "span", c) for c in children.get(span["context"]["span_id"], [])]
        items += [(_t(e["timestamp"]), "event", e) for e in span["events"]]
        for _, kind, item in sorted(items, key=lambda i: i[0]):
            if kind == "span":
                walk(item, depth + 1)
            else:
                out.append(f"{'  ' * (depth + 1)}• {item['name']} "
                           f"{json.dumps(item['attributes'], ensure_ascii=False)}"[:width])

    for root in sorted(children.get(None, []), key=lambda s: _t(s["start_time"])):
        walk(root, 0)
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("file")
    p.add_argument("--case")
    p.add_argument("--trace")
    p.add_argument("--width", type=int, default=160)
    a = p.parse_args()
    print(render(pick(load(a.file), a.case, a.trace), a.width))
    return 0


if __name__ == "__main__":
    sys.exit(main())
