# M01 — Orientation, decision and setup

- **ADR:** [docs/adr/0001-architecture.md](../../docs/adr/0001-architecture.md). ADK chosen over LangGraph and the
  plain SDK; the trade-offs and the M11 re-check are written down.
- **Working Gemini call:** [gemini-call.txt](gemini-call.txt). The live smoke test and a CLI call through
  `agentic_app.llm.generate`.
- **Reproduce:** `uv run pytest` (offline, no key) · `uv run pytest -m live` · `uv run agentic-app "your question"`
- **Commit:** see tag `m01-done`.

**Probe — "Why this architecture over the alternative?"** ADK supports Agent Engine deploy, MCP, A2A and live voice
natively, so one framework covers M09–M17. LangGraph has stronger explicit checkpointing and `interrupt()`. Sprint 3.1
needs those, so M11 begins by testing whether ADK sessions and tool confirmation are enough.
