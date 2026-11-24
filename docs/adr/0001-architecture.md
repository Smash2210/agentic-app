# ADR 0001 — Agent framework and architecture

- **Status:** Accepted

## Context

We are building an **Expense & Travel Policy Copilot**. It answers questions about a company travel and expense
policy and cites the policy text. It reads receipts, checks expense claims against the policy, and files claims. The
same repository grows over 18 sprints, from a deterministic Claims API to a multi-agent system, and goes to peer review
as one system.

Constraints:

- **Free tier, runs locally.** Gemini through an AI Studio key; no paid services to run or review it. `RUN.md` must
  start it in under 15 minutes without real keys.
- **Must deploy to Vertex AI Agent Engine** (Sprints 2.4 and 3.6).
- Later sprints need **MCP tools and A2A agents** (3.2), **durable sessions and human approval** (3.1) and **live
  voice** (Elective A).
- Decisions about money stay in **deterministic code** (the rules engine) or with a **human**. The model reasons and
  explains; it never approves a claim.

## Options considered

| | Google ADK | LangGraph | Plain `google-genai` SDK |
|---|---|---|---|
| Agent Engine deploy | Native (`AdkApp`) | Supported via a template | Custom wrapper |
| MCP tools | Built in (`MCPToolset`) | Via adapters | Hand-written client |
| A2A | Built in | Via `a2a-sdk` | Hand-written |
| Durable state / human in the loop | Persistent sessions (`DatabaseSessionService`), tool confirmation | Strongest: checkpointers, `interrupt()`, time travel | Build it ourselves |
| Live voice | Built in (Gemini Live streaming) | Not built in | Hand-written |
| Taught in the track | Google Skills ADK path, Box MCP, A2A, live-voice courses | LangChain Academy, NAT, long-term memory courses | Vertex AI Studio |

## Decision

**Use Google ADK as the agent framework, with Gemini through `google-genai`.** Every model call goes through one
module, `src/agentic_app/llm.py`.

ADK covers the most sprints natively: Agent Engine deploy, MCP, A2A and voice. It is also the framework of the Google
Skills path, which keeps one framework across the system. The plain SDK stays underneath for simple calls (`llm.py`).
Writing our own agent loop would cost time without teaching anything the sprints test.
