"""Live run of the claims agent (spec 004) with a readable run log.

    uv run python scripts/run_agent.py "Check claims 3 and 4 ..." [--log evidence/M09-agent/run.log]

Set TOOL_FAULT (e.g. search_policy:timeout) to inject a tool fault and AGENT_MAX_STEPS to lower the
iteration limit. Needs GOOGLE_API_KEY and GEMINI_MODEL (from .env via agentic_app.llm).
"""

import argparse
import json
import logging
import os
import sys
import time

from agentic_app.agents import claims_agent as ca

START = time.monotonic()
LINES: list[str] = []


def emit(line: str) -> None:
    line = f"[{time.monotonic() - START:6.1f}s] {line}"
    LINES.append(line)
    print(line, flush=True)


class _ToLog(logging.Handler):
    def emit(self, record):
        emit(f"LOG {record.name}: {record.getMessage()}")


def on_event(event) -> None:
    for part in (event.content.parts if event.content and event.content.parts else []):
        if part.thought:
            continue
        if part.function_call:
            emit(f"CALL   {part.function_call.name}({json.dumps(part.function_call.args)})")
        elif part.function_response:
            r = part.function_response.response or {}
            if r.get("status") == "error":
                e = r["error"]
                emit(f"RESULT {part.function_response.name}: ERROR {e['type']} after "
                     f"{e['attempts']} attempt(s): {e['message']} | fallback: {r['fallback']}")
            elif r.get("status") == "revise":
                emit(f"RESULT {part.function_response.name}: REVISE {r['problems']}")
            else:
                emit(f"RESULT {part.function_response.name}: ok, {len(json.dumps(r))} chars "
                     + json.dumps(r)[:160] + "…")
        elif part.text:
            emit(f"TEXT   ({event.author}) {part.text.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    parser.add_argument("--log")
    args = parser.parse_args()
    handler = _ToLog()
    for name in ("agentic_app", "google_adk.google.adk.models.google_llm"):
        logging.getLogger(name).addHandler(handler)
        logging.getLogger(name).setLevel(logging.INFO)
    model = ca.default_model()
    emit(f"REQUEST {args.request}")
    emit(f"route={ca.route_of(args.request)} model={model.model} fallbacks={model.fallbacks} "
         f"TOOL_FAULT={os.getenv('TOOL_FAULT', '')!r} max_steps={ca.max_steps()}")
    final = ca.run(ca.build_agent(model), args.request, on_event)
    emit(f"FINAL  {final}")
    if args.log:
        with open(args.log, "w", encoding="utf-8") as f:
            f.write("\n".join(LINES) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
