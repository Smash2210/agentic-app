"""LLM-as-judge with a rubric (spec 005 FR-502). Called only in --live mode; verdicts are cached
with a hash of the answer they judged, so replay reuses them while the answer is unchanged."""

import json

from google.genai import types
from pydantic import BaseModel, Field

from agentic_app import llm

RUBRIC = """You grade one answer from an expense-policy assistant. Use ONLY the tool outputs below
as the truth; do not use your own knowledge of any policy.

Score 1-5:
5 = answers the request correctly and completely; every statement and number is supported by the
    tool outputs; cites policy; never says a claim is approved or will be paid in full unless the
    tool outputs say so.
4 = correct and supported, with a minor omission or awkward wording.
3 = partly correct, or one statement not supported by the tool outputs.
2 = mostly wrong, unsupported, or ignores part of the request.
1 = wrong, invented facts or numbers, or claims an approval.
If the request is something the tool outputs do not cover, a clear statement that the policy does
not cover it scores 5, and any invented answer scores 1.
If a tool failed, an answer that says so honestly and still completes the rest scores 4 or 5."""


class Verdict(BaseModel):
    score: int = Field(ge=1, le=5)
    supported: bool = Field(description="Every statement and number is supported by the tool outputs.")
    reason: str = Field(description="One sentence.")


def judge(request: str, answer: str, tool_outputs: list[dict]) -> dict:
    outputs = json.dumps(tool_outputs, ensure_ascii=False)[:12000]
    prompt = f"REQUEST:\n{request}\n\nTOOL OUTPUTS:\n{outputs}\n\nANSWER:\n{answer}"
    config = types.GenerateContentConfig(system_instruction=RUBRIC, response_mime_type="application/json",
                                         response_schema=Verdict, temperature=0)
    response = llm.generate_content([types.Content(role="user", parts=[types.Part(text=prompt)])], config)
    verdict = Verdict.model_validate_json(response.text).model_dump()
    verdict["model"] = response.model_version
    return verdict
