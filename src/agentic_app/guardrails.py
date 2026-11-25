"""Guardrails (spec 005): input, output and action checks, all deterministic code.

    input   screen_input()        prompt injection (also in pasted receipt text) and off-topic
                                  requests are answered with a fixed message; no model call
    output  grounding_problems()  cited passages and amounts must come from tool output
            explanation_for_decision()  an adjudication explanation never sounds final unless the
                                  decision is approve (fixes the weakness seen live in M07)
    action  before_tool()         only read-only tools may run; nothing may approve a claim

Patterns will miss paraphrased attacks; the action guard is the hard line that holds even when the
model is fooled. M15 red-teams all of them.
"""

import re

from agentic_app.tracing import event

# --- input ------------------------------------------------------------------------------------------

INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|earlier|all|your|the)\b.{0,20}\b(instructions?|rules?|prompts?|guidelines?)",
    r"\byou are now\b|\bact as\b|\bpretend (to be|you are)\b|\bdeveloper mode\b|\bjailbreak\b",
    r"\b(reveal|show|print|repeat)\b.{0,30}\b(system prompt|instructions|hidden prompt)\b",
    # an order to approve (sentence start), not a question about who approves
    r"(^|[.!?:;\n]\s*)(please\s+)?(auto-?)?approve\b|\bmark\b.{0,30}\bas (approved|paid)\b",
    r"</?(system|instructions?)>|\[\s*system\s*\]",
]
_INJECTION = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in INJECTION_PATTERNS]

# A request must mention the expense/travel domain. Unanswerable but on-topic questions ("vacation
# days") still reach the agent, which refuses them from retrieval.
TOPIC_WORDS = re.compile(
    r"\b(expense|claim|receipt|reimburs\w*|policy|policies|travel|trip|hotel|lodging|room|meal|food|"
    r"dinner|lunch|breakfast|per ?diem|flight|airfare|train|taxi|uber|car|mileage|km|transport|"
    r"currency|fx|usd|eur|gbp|limit|cap|allowance|approval|manager|conference|client|entertain\w*|"
    r"alcohol|wine|minibar|tip|booking|business class|economy|vacation|leave|pay|paid|"
    r"cost|spend|budget)s?\b", re.IGNORECASE)

INJECTION_MESSAGE = ("I can't act on that request: it contains instructions aimed at changing how I "
                     "work. I can answer expense policy questions and check stored claims; I never "
                     "approve claims.")
OFF_TOPIC_MESSAGE = ("I can only help with the travel and expense policy and your expense claims. "
                     "Please ask about those.")


def screen_input(text: str) -> tuple[str, str] | None:
    """(reason, fixed message) if the request must be blocked, else None."""
    for pattern in _INJECTION:
        if pattern.search(text):
            return "prompt_injection", INJECTION_MESSAGE
    if not TOPIC_WORDS.search(text):
        return "off_topic", OFF_TOPIC_MESSAGE
    return None


def injected_receipts(receipts: list[str]) -> list[int]:
    """1-based numbers of receipts that contain a prompt-injection pattern (FR-509)."""
    return [i for i, r in enumerate(receipts, 1) if any(p.search(r) for p in _INJECTION)]


# --- output -----------------------------------------------------------------------------------------

_DOC_ID = re.compile(r"POL-[A-Z]+")
_PASSAGE_ID = re.compile(r"POL-[A-Z]+#\d+")
_AMOUNT = re.compile(r"\d[\d,]*\.\d{2}")


def _amounts(text: str) -> set[str]:
    return {a.replace(",", "") for a in _AMOUNT.findall(text)}


def grounding_problems(answer: str, tool_output: str) -> list[str]:
    """Why an answer is not grounded in this run's tool output (empty if it is)."""
    problems = []
    known_docs = set(_DOC_ID.findall(tool_output))
    if known_docs and not set(_DOC_ID.findall(answer)) & known_docs:
        problems.append("The answer cites no policy reference returned by the tools; cite one of: "
                        + ", ".join(sorted(known_docs)) + ".")
    unknown_passages = sorted(set(_PASSAGE_ID.findall(answer)) - set(_PASSAGE_ID.findall(tool_output)))
    if unknown_passages:
        problems.append("These passages were cited but not returned by search_policy: "
                        + ", ".join(unknown_passages) + ".")
    invented = sorted(_amounts(answer) - _amounts(tool_output))
    if invented:
        problems.append("These amounts do not appear in any tool result (do not compute amounts): "
                        + ", ".join(invented) + ".")
    return problems


_FINAL = re.compile(
    r"\b(successfully (processed|approved|submitted)|has been (processed|approved|paid)|"
    r"(is|was) approved|will be (paid|reimbursed in full)|all set|no further action)\b", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
STATUS = {
    "partial": "Part of this claim is reimbursable; the rest was rejected under the policy below.",
    "reject": "This claim is not reimbursable under the policy below.",
    "needs_human_review": ("This claim needs review by a person before anything is paid; "
                           "nothing has been approved yet."),
}


def explanation_for_decision(explanation: str, decision: str) -> str:
    """FR-509: for any decision but approve, drop sentences that sound final and lead with a
    code-written status sentence."""
    if decision == "approve" or not explanation:
        return explanation
    kept = [s for s in _SENTENCE.split(explanation.strip()) if not _FINAL.search(s)]
    if len(kept) != len(_SENTENCE.split(explanation.strip())):
        event("guardrail.output.tone", decision=decision)
    return " ".join([STATUS[decision], *kept])


# --- action -----------------------------------------------------------------------------------------

READ_ONLY_TOOLS = {"search_policy", "get_claim", "check_claim", "review_answer"}
def blocked_tool_result(name: str, reason: str) -> dict:
    return {"status": "error",
            "error": {"type": "ToolBlocked", "tool": name, "message": reason, "attempts": 0,
                      "retryable": False},
            "fallback": "This action is not allowed. Claims are approved only by people. Tell the "
                        "user what the check found and that a person makes the decision."}


def before_tool(tool, args: dict, tool_context) -> dict | None:
    """FR-508: refuse any tool that is not read-only, or any arguments that try to approve."""
    name = getattr(tool, "name", str(tool))
    if name in READ_ONLY_TOOLS:
        return None
    reason = f"tool {name} is not allowed: only read-only tools may run, and no tool may approve a claim"
    event("guardrail.action.blocked", tool=name, reason=reason)
    return blocked_tool_result(name, reason)
