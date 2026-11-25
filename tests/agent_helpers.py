"""Shared fakes for the agent tests (spec 004/005): a scripted ADK model and response builders."""

import json
from collections.abc import AsyncGenerator
from pathlib import Path

from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.genai import types

REPO = Path(__file__).resolve().parents[1]
VECTORS = {k: v["vector"] for k, v in
           json.loads((REPO / "data/index/embeddings.json").read_text())["passages"].items()}


def call(name, **args):
    return LlmResponse(content=types.Content(role="model", parts=[
        types.Part(function_call=types.FunctionCall(name=name, args=args))]))


def say(text):
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


class FakeLlm(BaseLlm):
    """Plays back a script; each step is an LlmResponse or a function of the request."""

    model: str = "fake"
    script: list = []
    requests: list = []

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False
                                     ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        step = self.script[min(len(self.requests), len(self.script)) - 1]
        yield step(llm_request) if callable(step) else step


def tool_results(request: LlmRequest) -> list[dict]:
    return [p.function_response.response for c in request.contents for p in c.parts or []
            if p.function_response]
