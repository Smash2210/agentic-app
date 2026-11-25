"""Timeout, one bounded retry and typed error results for agent tools (spec 004 FR-403, FR-405).

    @resilient("check_claim", timeout_s=5, fallback="...")
    def check_claim(claim_id: int) -> dict: ...

The tool body runs in a worker thread. A timeout or ToolUnavailable is retried once after BACKOFF_S;
ToolBadInput is not. If it still fails, the tool returns error.result(...) instead of raising, so the
model sees what failed and the fallback to follow. Any other exception counts as ToolUnavailable.

Fault injection: TOOL_FAULT="search_policy:timeout,check_claim:error" makes those tools time out or
fail on every attempt (read on each call, so a test or a live run can set it at any time).
"""

import functools
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from agentic_app.tracing import tracer
from agentic_app.tools.errors import ToolError, ToolTimeout, ToolUnavailable

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # the first call and one retry
BACKOFF_S = 0.5
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tool")


def injected_fault(tool: str) -> str | None:
    for item in os.getenv("TOOL_FAULT", "").split(","):
        name, _, mode = item.strip().partition(":")
        if name == tool and mode in ("timeout", "error"):
            return mode
    return None


def _body_with_fault(tool: str, fn, timeout_s: float):
    def body(*args, **kwargs):
        fault = injected_fault(tool)
        if fault == "timeout":
            time.sleep(timeout_s * 3)  # outlives the timeout; the worker is abandoned
        elif fault == "error":
            raise ToolUnavailable(tool, "injected fault: service error (TOOL_FAULT)")
        return fn(*args, **kwargs)
    return body


def resilient(tool: str, *, timeout_s: float, fallback: str):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> dict:
            body = _body_with_fault(tool, fn, timeout_s)
            for attempt in range(1, MAX_ATTEMPTS + 1):
                with tracer.start_as_current_span("tool.attempt") as span:
                    span.set_attributes({"tool.name": tool, "tool.attempt": attempt,
                                         "tool.fault": injected_fault(tool) or "",
                                         "tool.args": json.dumps(kwargs or list(args), default=str)})
                    try:
                        future = _executor.submit(body, *args, **kwargs)
                        try:
                            result = future.result(timeout=timeout_s)
                            span.set_attributes({"tool.status": result.get("status", "ok"),
                                                 "tool.result": json.dumps(result, default=str)[:4000]})
                            return result
                        except FutureTimeout:
                            future.cancel()
                            raise ToolTimeout(tool, f"no answer within {timeout_s:g} s") from None
                    except ToolError as exc:
                        error = exc
                    except Exception as exc:  # a bug or an outage behind the tool: never kill the run
                        error = ToolUnavailable(tool, f"{type(exc).__name__}: {exc}")
                    span.set_attributes({"tool.status": "error", "error.type": type(error).__name__,
                                         "error.message": error.message})
                log.warning("tool %s attempt %d/%d failed: %s: %s", tool, attempt, MAX_ATTEMPTS,
                            type(error).__name__, error.message)
                if not error.retryable or attempt == MAX_ATTEMPTS:
                    return error.result(attempts=attempt, fallback=fallback)
                time.sleep(BACKOFF_S)
            raise AssertionError("unreachable")
        return wrapper
    return decorate


