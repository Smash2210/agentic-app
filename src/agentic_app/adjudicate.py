"""Adjudicate receipts (spec 002): the model reads and explains; the rules engine decides money.

    1. Read   - Gemini, thinking on, with one tool: check_claim(lines). The tool's arguments are
                validated as a spec 001 claim; invalid ones go back to the model as errors.
    2. Answer - Gemini again, structured output only: flags, unreadable receipts, explanation.
                Invalid answer -> one retry with the reason -> otherwise needs_human_review.
    3. Decide - code: amounts and violations are the engine's, the decision follows FR-207.

The system instruction (rules + full policy text) is identical on every call, so the model's
implicit cache can serve it (explicit caching is not available on the free tier; plan.md).
"""

import json
import re
import time
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

from google.genai import types
from pydantic import BaseModel, ValidationError

from agentic_app import llm
from agentic_app.claims.policy import Policy
from agentic_app.claims.rules import check_claim
from agentic_app.schemas import (
    AdjudicateRequest,
    Adjudication,
    Category,
    CheckResult,
    Claim,
    ClaimIn,
    Decision,
    ExpenseLine,
    Flag,
    ModelUsage,
    PriorLine,
)

MAX_TOOL_TURNS = 3
THINKING_BUDGET = 1024
TOOL_NAME = "check_claim"

INSTRUCTIONS = """You read expense receipts for the company travel and expense policy below and
prepare them for an automatic policy check. You never decide amounts or approval: a rules engine
does that.

Step 1. Read every receipt, then call check_claim once with all the expense lines:
- A meal is one line: all food, soft drinks and service/tip on one bill together.
- A hotel stay is one lodging line dated on the first night, with nights = number of nights. It
  includes the room charges and taxes or city fees (POL-LODGING §2).
- Each journey is one transport line, even when one receipt lists several journeys.
- Amounts and currency exactly as printed on the receipt, as plain decimal text ("472.50"): no
  currency symbols, no thousands separators. Dates as YYYY-MM-DD, inside the trip dates.
- Leave OUT items the policy excludes but the rules engine cannot check, and remember them as flags:
  alcohol, or meals already included in a conference fee or hotel rate (POL-MEALS §2); minibar, room
  service, laundry, in-room entertainment (POL-LODGING §4).
- If a receipt's date, amount or currency cannot be read with confidence, leave it out and remember
  it as unreadable. Never guess a missing value.
- If check_claim returns errors, correct the lines and call it again.
- If no receipt can be read, do not call check_claim.

Step 2. When asked for the final answer, return:
- flags: every item you left out under the rule above (receipt number from 1, item, reason, policy
  section such as "POL-MEALS §2");
- unreadable: one entry per receipt, or part of one, you could not read, saying what was missing;
- explanation: 3 to 6 plain sentences for the employee about the check result, citing policy
  sections such as "POL-MEALS §1". Mention only amounts that appear on the receipts or in the check
  result; never calculate new ones.

# POLICY

"""

FINAL_ASK = "Give the final answer now: flags, unreadable and explanation."

_LINE_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "YYYY-MM-DD. For lodging, the first night."},
        "category": {"type": "string", "enum": [c.value for c in Category]},
        "merchant": {"type": "string", "description": "Who was paid, as on the receipt."},
        "amount": {"type": "string", "description": 'Plain decimal text, e.g. "472.50".'},
        "currency": {"type": "string", "description": "3-letter code, e.g. EUR."},
        "nights": {"type": "integer", "description": "Lodging only: number of nights."},
    },
    "required": ["date", "category", "merchant", "amount", "currency"],
}
CHECK_TOOL = types.Tool(function_declarations=[types.FunctionDeclaration(
    name=TOOL_NAME,
    description="Check expense lines against the policy. Returns the rules engine's result, or "
                "errors to correct.",
    parameters_json_schema={
        "type": "object",
        "properties": {"lines": {"type": "array", "items": _LINE_SCHEMA}},
        "required": ["lines"],
    },
)])

_AMOUNT = re.compile(r"\d[\d,]*\.\d{2}")


class ReaderAnswer(BaseModel):
    """The model's final answer (phase 2). Contains no amounts it could get wrong except in text."""

    flags: list[Flag]
    unreadable: list[str]
    explanation: str


class _Usage:
    def __init__(self) -> None:
        self.calls = self.prompt = self.cached = self.thoughts = self.output = 0
        self.ms = 0

    def add(self, response: types.GenerateContentResponse, ms: int) -> None:
        u = response.usage_metadata
        self.calls += 1
        self.ms += ms
        if u is not None:
            self.prompt += u.prompt_token_count or 0
            self.cached += u.cached_content_token_count or 0
            self.thoughts += u.thoughts_token_count or 0
            self.output += u.candidates_token_count or 0

    def model(self) -> ModelUsage:
        return ModelUsage(
            model=llm.model_name(), model_calls=self.calls, prompt_tokens=self.prompt,
            cached_tokens=self.cached, thoughts_tokens=self.thoughts, output_tokens=self.output,
            latency_ms=self.ms,
        )


def _call(contents: list, config: types.GenerateContentConfig, usage: _Usage):
    start = time.monotonic()
    response = llm.generate_content(contents, config)
    usage.add(response, int((time.monotonic() - start) * 1000))
    return response


def _amounts(text: str) -> set[Decimal]:
    found = set()
    for raw in _AMOUNT.findall(text):
        try:
            found.add(Decimal(raw.replace(",", "")))
        except InvalidOperation:
            pass
    return found


class _Run:
    """One adjudication: the conversation with the model and the last valid check."""

    def __init__(self, request: AdjudicateRequest, prior_lines: Sequence[PriorLine], policy: Policy):
        self.request, self.prior_lines, self.policy = request, prior_lines, policy
        self.usage = _Usage()
        self.claim: Claim | None = None
        self.check: CheckResult | None = None
        system = INSTRUCTIONS + policy.text
        self.read_config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[CHECK_TOOL],
            thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        self.answer_config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=ReaderAnswer,
        )

    def user_message(self) -> str:
        trip = self.request.trip
        receipts = "\n\n".join(
            f"--- Receipt {i} ---\n{text}" for i, text in enumerate(self.request.receipts, 1)
        )
        return (
            f"Employee: {self.request.employee_id}\n"
            f"Trip: {trip.destination_city}, {trip.start_date} to {trip.end_date}\n\n{receipts}"
        )

    # phase 1 -----------------------------------------------------------------------------------

    def read(self) -> list:
        contents = [types.Content(role="user", parts=[types.Part(text=self.user_message())])]
        for _ in range(MAX_TOOL_TURNS):
            response = _call(contents, self.read_config, self.usage)
            calls = response.function_calls or []
            if not calls or not response.candidates:
                break
            contents.append(response.candidates[0].content)
            contents.append(types.Content(role="user", parts=[
                types.Part.from_function_response(name=call.name, response=self.run_tool(call))
                for call in calls
            ]))
        return contents

    def run_tool(self, call: types.FunctionCall) -> dict:
        if call.name != TOOL_NAME:
            return {"error": f"unknown tool {call.name}; the only tool is {TOOL_NAME}"}
        lines = (call.args or {}).get("lines") or []
        try:
            claim_in = ClaimIn.model_validate({
                "employee_id": self.request.employee_id,
                "trip": self.request.trip.model_dump(),
                "lines": [{**line, "receipt_attached": True} for line in lines],
            })
        except ValidationError as exc:
            return {"error": [
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            ]}
        claim = Claim(
            id=0, employee_id=claim_in.employee_id, trip=claim_in.trip,
            lines=[ExpenseLine(line_no=i, **line.model_dump())
                   for i, line in enumerate(claim_in.lines, 1)],
        )
        self.claim, self.check = claim, check_claim(claim, self.prior_lines, self.policy)
        return {"result": self.check.model_dump(mode="json")}

    # phase 2 -----------------------------------------------------------------------------------

    def answer(self, contents: list) -> tuple[ReaderAnswer | None, str | None]:
        contents = [*contents, types.Content(role="user", parts=[types.Part(text=FINAL_ASK)])]
        problem = None
        for _ in range(2):  # one retry, with the reason
            if problem is not None:
                contents = [*contents, types.Content(role="user", parts=[types.Part(text=(
                    f"That answer was invalid: {problem}. Answer again."
                ))])]
            response = _call(contents, self.answer_config, self.usage)
            problem = self.validate(response)
            if problem is None:
                return ReaderAnswer.model_validate_json(response.text), None
        return None, problem

    def validate(self, response: types.GenerateContentResponse) -> str | None:
        """Why the answer is unusable, or None. Includes the FR-204 check on amounts."""
        try:
            answer = ReaderAnswer.model_validate_json(response.text or "")
        except ValidationError as exc:
            return f"it did not match the required structure ({exc.error_count()} errors)"
        allowed = _amounts("\n".join(self.request.receipts)) | _amounts(self.policy.text)
        if self.check is not None:
            allowed |= _amounts(json.dumps(self.check.model_dump(mode="json")))
        invented = sorted(_amounts(answer.explanation) - allowed)
        if invented:
            return (f"the explanation mentions amounts that are not on the receipts or in the "
                    f"check result: {', '.join(str(a) for a in invented)}")
        if any(flag.receipt > len(self.request.receipts) for flag in answer.flags):
            return "a flag refers to a receipt number that does not exist"
        return None


def decide(check: CheckResult | None, answer: ReaderAnswer | None, problem: str | None) -> tuple[Decision, list[str]]:
    """FR-207. Pure: the only place a decision is made."""
    reasons = []
    if problem is not None:
        reasons.append(f"the reader's answer was invalid after one retry: {problem}")
    if check is None:
        reasons.append("no expense lines could be checked")
    if answer is not None:
        reasons += [f"flagged: {f.item} ({f.citation})" for f in answer.flags]
        reasons += [f"unreadable: {u}" for u in answer.unreadable]
    if reasons:
        return Decision.NEEDS_HUMAN_REVIEW, reasons
    if check.lines_reimbursable_usd == 0:
        return Decision.REJECT, []
    if check.violations or any((line.rejected_usd or 0) > 0 for line in check.lines):
        return Decision.PARTIAL, []
    return Decision.APPROVE, []


def adjudicate(
    request: AdjudicateRequest, prior_lines: Sequence[PriorLine], policy: Policy
) -> Adjudication:
    """Read the receipts, check them, decide. Raises llm.ModelUnavailable (FR-210)."""
    run = _Run(request, prior_lines, policy)
    contents = run.read()
    answer, problem = run.answer(contents)
    decision, reasons = decide(run.check, answer, problem)
    return Adjudication(
        decision=decision,
        review_reasons=reasons,
        lines=run.claim.lines if run.claim else [],
        check=run.check,
        flags=answer.flags if answer else [],
        unreadable=answer.unreadable if answer else [],
        explanation=answer.explanation if answer else "",
        usage=run.usage.model(),
    )
