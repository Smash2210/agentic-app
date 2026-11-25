"""Grounded policy Q&A, streamed (spec 003).

    1. Search  - the model gets one tool, search_policy(query), and decides what to search for (max 2
                 searches). If it does not search, the question itself is searched (FR-303).
    2. Gate    - code refuses when the question's best passage similarity is below REFUSAL_THRESHOLD.
    3. Answer  - streamed from the model, using only the retrieved passages, cited inline [POL-X#n].
                 If they do not answer the question, the model must reply NOT_IN_POLICY; the code
                 holds back the first characters to spot that and sends the refusal instead.
    4. Check   - citations of passages that were not retrieved are reported as unverified.

Both refusal paths send the same code-written text, never the model's own words (FR-304).
"""

import json
import re
from collections.abc import Callable, Iterator

from google.genai import types

from agentic_app import llm
from agentic_app.rag import embeddings
from agentic_app.rag.index import Hit, PolicyIndex

# From the retrieval evaluation (evidence/M08-rag/retrieval-eval.md): the weakest answerable golden
# question scored 0.716 and the strongest unanswerable one 0.710, too close to separate safely. So
# the gate sits below every answerable question (margin 0.016) and catches clearly off-topic ones;
# borderline questions are left to the model's NOT_IN_POLICY judgement.
REFUSAL_THRESHOLD = 0.70
MAX_SEARCHES = 2
TOOL_NAME = "search_policy"
NOT_IN_POLICY = "NOT_IN_POLICY"
REFUSAL = ("I can't answer that from the travel and expense policy. "
           "Please ask your manager or the finance team.")

INSTRUCTIONS = """You answer employees' questions about the company travel and expense policy.

First call search_policy with a short search query. If the passages returned do not cover the
question, you may search once more with a different query.

Then answer using ONLY the passages returned by search_policy:
- 1 to 4 short sentences, in plain language.
- After each sentence, cite the passage IDs it relies on in square brackets, exactly as given,
  e.g. [POL-MEALS#1] or [POL-MEALS#2, POL-ENTERTAIN#3].
- Do not add rules, numbers or advice that are not in the passages.
- If the passages do not answer the question, reply with exactly NOT_IN_POLICY and nothing else."""

ANSWER_NOW = "Answer the question now, using only the passages above."

SEARCH_TOOL = types.Tool(function_declarations=[types.FunctionDeclaration(
    name=TOOL_NAME,
    description="Search the travel and expense policy. Returns the most relevant passages with IDs.",
    parameters_json_schema={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "A short search query."}},
        "required": ["query"],
    },
)])

_BRACKETS = re.compile(r"\[([^\]]+)\]")
_PASSAGE_ID = re.compile(r"POL-[A-Z]+#\d+")


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def cited_ids(text: str) -> list[str]:
    """Passage IDs cited in [..] brackets, in order of first appearance."""
    found = []
    for group in _BRACKETS.findall(text):
        for pid in _PASSAGE_ID.findall(group):
            if pid not in found:
                found.append(pid)
    return found


class AskSession:
    def __init__(self, question: str, index: PolicyIndex,
                 embed: Callable[[list[str], str], list[list[float]]] | None = None):
        self.question, self.index = question, index
        self.embed = embed or embeddings.gemini_embed
        self.retrieved: dict[str, Hit] = {}
        self.question_similarity = 0.0
        self.model: str | None = None
        self.contents: list = []
        self.config = types.GenerateContentConfig(system_instruction=INSTRUCTIONS)

    # 1-2: search and gate (before the response starts, so failures can still be HTTP errors) ----

    def _search(self, query: str, vector: list[float] | None = None) -> list[Hit]:
        vector = vector or self.embed([query], "RETRIEVAL_QUERY")[0]
        hits = self.index.search(query, vector)
        for hit in hits:
            self.retrieved.setdefault(hit.chunk.id, hit)
        return hits

    @staticmethod
    def _passages(hits: list[Hit]) -> dict:
        return {"passages": [{"id": h.chunk.id, "title": f"{h.chunk.doc_title} — {h.chunk.title}",
                              "text": h.chunk.body} for h in hits]}

    def prepare(self) -> None:
        question_vector = self.embed([self.question], "RETRIEVAL_QUERY")[0]
        self.question_similarity = self.index.best_similarity(question_vector)
        if self.refused_by_gate:
            return  # no model call for clearly off-topic questions
        read_config = types.GenerateContentConfig(
            system_instruction=INSTRUCTIONS, tools=[SEARCH_TOOL],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        contents = [types.Content(role="user", parts=[types.Part(text=self.question)])]
        for _ in range(MAX_SEARCHES):
            response = llm.generate_content(contents, read_config, prefer=self.model)
            self.model = response.model_version
            calls = response.function_calls or []
            if not calls or not response.candidates:
                break
            contents.append(response.candidates[0].content)
            parts = []
            for call in calls:
                if call.name == TOOL_NAME:
                    query = str((call.args or {}).get("query") or self.question)
                    result = self._passages(self._search(query))
                else:
                    result = {"error": f"unknown tool {call.name}; the only tool is {TOOL_NAME}"}
                parts.append(types.Part.from_function_response(name=call.name, response=result))
            contents.append(types.Content(role="user", parts=parts))
        if not self.retrieved:  # the model did not search: search the question itself (FR-303)
            hits = self._search(self.question, question_vector)
            contents.append(types.Content(role="user", parts=[types.Part(text=(
                "Passages from search_policy:\n" + json.dumps(self._passages(hits)))
            )]))
        self.contents = contents

    @property
    def refused_by_gate(self) -> bool:
        return self.question_similarity < REFUSAL_THRESHOLD

    # 3-4: stream the answer ------------------------------------------------------------------

    def _refusal(self, reason: str) -> Iterator[str]:
        yield sse("token", REFUSAL)
        yield sse("citations", {"citations": [], "unverified": [], "grounded": True, "refused": True,
                                "refusal_reason": reason, **self._meta()})
        yield sse("done", {})

    def _meta(self) -> dict:
        return {"question_similarity": round(self.question_similarity, 3), "model": self.model}

    def events(self) -> Iterator[str]:
        if self.refused_by_gate:
            yield from self._refusal("no policy passage is close enough to the question")
            return
        contents = [*self.contents, types.Content(role="user", parts=[types.Part(text=ANSWER_NOW)])]
        held, answer, streaming = "", "", False
        try:
            for chunk in llm.generate_content_stream(contents, self.config, prefer=self.model):
                text = chunk.text or ""
                answer += text
                if streaming:
                    if text:  # the last chunk often carries no text
                        yield sse("token", text)
                    continue
                held += text
                start = held.lstrip()
                if start.startswith(NOT_IN_POLICY) or NOT_IN_POLICY.startswith(start):
                    continue  # could still be the refusal marker: keep holding back
                streaming = True
                yield sse("token", held)
        except Exception as exc:  # the response has started: report the error in the stream
            yield sse("error", {"message": f"the answer could not be completed ({type(exc).__name__})"})
            return
        if answer.strip().startswith(NOT_IN_POLICY) or not answer.strip():
            yield from self._refusal("the policy passages do not answer the question")
            return
        if not streaming:
            yield sse("token", held)
        cited = cited_ids(answer)
        valid = [pid for pid in cited if pid in self.retrieved]
        yield sse("citations", {
            "citations": [{"id": pid, "document": self.retrieved[pid].chunk.doc_title,
                           "section": self.retrieved[pid].chunk.title,
                           "similarity": round(self.retrieved[pid].similarity, 3)} for pid in valid],
            "unverified": [pid for pid in cited if pid not in self.retrieved],
            "grounded": bool(valid),
            "refused": False,
            **self._meta(),
        })
        yield sse("done", {})


def get_index(app) -> PolicyIndex:
    """The app's policy index, built on first use from the policy files and the embeddings cache."""
    index = getattr(app.state, "policy_index", None)
    if index is None:
        from agentic_app.rag.chunks import load_chunks

        policy_dir = app.state.policy_dir
        chunks = load_chunks(policy_dir)
        cache = policy_dir.parent / "index" / "embeddings.json"
        index = PolicyIndex(chunks, embeddings.passage_vectors(chunks, cache))
        app.state.policy_index = index
    return index
