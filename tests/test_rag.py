"""Spec 003 offline: chunks, the embeddings cache, hybrid search, and /ask with the model and the
question embeddings faked. Passage vectors are the real cached ones, so similarities are realistic."""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.genai import errors, types

from agentic_app import llm
from agentic_app.app import create_app
from agentic_app.rag import ask as ask_module
from agentic_app.rag import embeddings
from agentic_app.rag.ask import NOT_IN_POLICY, REFUSAL, AskSession, cited_ids
from agentic_app.rag.chunks import load_chunks
from agentic_app.rag.index import PolicyIndex

REPO = Path(__file__).resolve().parents[1]
POLICIES = REPO / "data" / "policies"
CACHE = REPO / "data" / "index" / "embeddings.json"


def no_live_embedding(texts, task):
    raise AssertionError("the committed cache should cover every passage")


CHUNKS = load_chunks(POLICIES)
VECTORS = embeddings.passage_vectors(CHUNKS, CACHE, embed=no_live_embedding)
INDEX = PolicyIndex(CHUNKS, VECTORS)


# --- chunks and cache ---------------------------------------------------------------------------


def test_one_chunk_per_numbered_section_with_stable_ids():
    ids = [c.id for c in CHUNKS]
    assert len(ids) == len(set(ids)) == 44
    meals2 = next(c for c in CHUNKS if c.id == "POL-MEALS#2")
    assert meals2.title == "What is not covered" and "Alcohol" in meals2.body
    assert meals2.text.startswith("Meals Policy — What is not covered: ")


def test_cache_is_current_and_only_changed_passages_are_embedded(tmp_path):
    cache = tmp_path / "embeddings.json"
    shutil.copy(CACHE, cache)
    changed = [*CHUNKS[:-1], type(CHUNKS[-1])(**{**CHUNKS[-1].__dict__, "body": "Edited text."})]
    asked = []

    def fake_embed(texts, task):
        asked.append((texts, task))
        return [[0.5] * embeddings.DIMENSIONS for _ in texts]

    vectors = embeddings.passage_vectors(changed, cache, embed=fake_embed)
    assert asked == [([changed[-1].text], "RETRIEVAL_DOCUMENT")]
    assert vectors[changed[-1].id][0] == 0.5
    assert embeddings.passage_vectors(changed, cache, embed=no_live_embedding)  # now cached


# --- hybrid search ------------------------------------------------------------------------------


def test_vector_and_hybrid_rank_the_matching_passage_first():
    vector = VECTORS["POL-TRANSPORT#3"]
    for mode in ("vector", "hybrid"):
        assert INDEX.search("private car mileage rate", vector, mode=mode)[0].chunk.id == "POL-TRANSPORT#3"
    assert INDEX.best_similarity(vector) == pytest.approx(1.0)


def test_bm25_finds_exact_keywords():
    hits = INDEX.search("minibar room service laundry", VECTORS["POL-MEALS#1"], mode="bm25")
    assert hits[0].chunk.id == "POL-LODGING#4" and hits[0].bm25_rank == 1


def test_hybrid_fuses_both_rankings_with_rrf():
    hit = INDEX.search("minibar", VECTORS["POL-LODGING#4"], mode="hybrid")[0]
    assert hit.chunk.id == "POL-LODGING#4" and hit.bm25_rank == 1 and hit.vector_rank == 1
    assert hit.score == pytest.approx(2 / 61)


def test_unknown_search_mode_is_an_error():
    with pytest.raises(ValueError):
        INDEX.search("x", VECTORS["POL-MEALS#1"], mode="magic")


def test_citation_ids_are_parsed_from_brackets():
    text = "No [POL-LODGING#4]. Yes [POL-MEALS#2, POL-ENTERTAIN#3] and [POL-LODGING#4] [not-an-id]."
    assert cited_ids(text) == ["POL-LODGING#4", "POL-MEALS#2", "POL-ENTERTAIN#3"]


# --- /ask with fakes ----------------------------------------------------------------------------

QUESTION = "Can I claim the minibar from my hotel bill?"
OFF_TOPIC = "What is the dress code in the office?"


def fake_question_embed(texts, task):
    """On-topic text gets the minibar passage's own vector; anything else points away from it."""
    target = VECTORS["POL-LODGING#4"]
    return [target if "minibar" in t.lower() else [-x for x in target] for t in texts]


def search_call(query):
    part = types.Part(function_call=types.FunctionCall(name="search_policy", args={"query": query}))
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))])


def text(value):
    return types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(role="model", parts=[types.Part(text=value)]))])


DONE = text("Searched.")


class FakeModels:
    def __init__(self, calls, streams):
        self.calls, self.streams, self.seen = list(calls), list(streams), []

    def generate_content(self, model, contents, config):
        self.seen.append(("call", list(contents)))
        return self.calls.pop(0)

    def generate_content_stream(self, model, contents, config):
        self.seen.append(("stream", list(contents)))
        item = self.streams.pop(0)
        if isinstance(item, Exception):
            raise item

        def gen():
            for piece in item:
                if isinstance(piece, Exception):
                    raise piece
                yield text(piece)
        return gen()


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "fake-model")
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    monkeypatch.setattr(embeddings, "gemini_embed", fake_question_embed)

    def install(calls=(), streams=()):
        models = FakeModels(calls, streams)
        monkeypatch.setattr(llm, "get_client", lambda: type("C", (), {"models": models})())
        return models

    return install


def run(question=QUESTION):
    session = AskSession(question, INDEX)
    session.prepare()
    return session, parse(session.events())


def parse(stream):
    events = []
    for block in "".join(stream).split("\n\n"):
        if block.strip():
            head, data = block.split("\n", 1)
            events.append((head.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def answer_of(events):
    return "".join(d for e, d in events if e == "token")


def citations_of(events):
    return next(d for e, d in events if e == "citations")


def test_grounded_answer_streams_tokens_then_citations_then_done(fake):
    fake([search_call("minibar"), DONE], [["Minibar charges are not ", "reimbursable [POL-LODGING#4]."]])
    session, events = run()

    assert [e for e, _ in events] == ["token", "token", "citations", "done"]
    assert answer_of(events) == "Minibar charges are not reimbursable [POL-LODGING#4]."
    cites = citations_of(events)
    assert [c["id"] for c in cites["citations"]] == ["POL-LODGING#4"]
    assert cites["grounded"] is True and cites["refused"] is False and cites["unverified"] == []


def test_empty_chunks_are_not_sent_as_tokens(fake):
    fake([search_call("minibar"), DONE], [["Not reimbursable ", "[POL-LODGING#4].", ""]])
    events = run()[1]
    assert all(d for e, d in events if e == "token")


def test_citation_of_a_passage_not_retrieved_is_unverified(fake):
    fake([search_call("minibar"), DONE], [["Not covered [POL-LODGING#4]; insure yourself [POL-SAFETY#2]."]])
    cites = citations_of(run()[1])
    assert cites["unverified"] == ["POL-SAFETY#2"] and cites["grounded"] is True


def test_answer_with_no_valid_citation_is_not_grounded(fake):
    fake([search_call("minibar"), DONE], [["Probably fine to claim it."]])
    cites = citations_of(run()[1])
    assert cites["grounded"] is False and cites["citations"] == []


def test_model_refusal_marker_is_replaced_by_the_fixed_refusal_even_when_split(fake):
    fake([search_call("minibar"), DONE], [["NOT_IN", "_POLICY"]])
    events = run()[1]
    assert answer_of(events) == REFUSAL and NOT_IN_POLICY not in answer_of(events)
    assert citations_of(events)["refused"] is True


def test_off_topic_question_is_refused_by_the_gate_without_any_model_call(fake):
    models = fake()  # no scripted model replies: any call would fail
    session, events = run(OFF_TOPIC)
    assert session.question_similarity < ask_module.REFUSAL_THRESHOLD
    assert answer_of(events) == REFUSAL and models.seen == []


def test_question_is_searched_when_the_model_does_not_search(fake):
    models = fake([DONE], [["Not reimbursable [POL-LODGING#4]."]])
    session, events = run()
    assert "POL-LODGING#4" in session.retrieved
    assert "Passages from search_policy" in models.seen[1][1][-2].parts[0].text
    assert citations_of(events)["grounded"] is True


def test_error_after_streaming_started_is_sent_as_an_error_event(fake):
    fake([search_call("minibar"), DONE], [["Minibar charges are ", RuntimeError("connection lost")]])
    events = run()[1]
    assert [e for e, _ in events] == ["token", "error"]


def test_temporary_error_before_the_first_chunk_is_retried(fake):
    busy = errors.APIError(503, {"error": {"code": 503, "message": "busy", "status": "UNAVAILABLE"}})
    fake([search_call("minibar"), DONE], [busy, ["Not reimbursable [POL-LODGING#4]."]])
    assert citations_of(run()[1])["grounded"] is True


# --- HTTP ---------------------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path / "claims.db", POLICIES))


def test_post_ask_streams_server_sent_events(fake, client):
    fake([search_call("minibar"), DONE], [["Not reimbursable [POL-LODGING#4]."]])
    with client.stream("POST", "/ask", json={"question": QUESTION}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = parse(response.iter_text())
    assert events[-1] == ("done", {}) and citations_of(events)["citations"][0]["id"] == "POL-LODGING#4"


def test_post_ask_503_when_the_model_is_unavailable(fake, client, monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL")
    response = client.post("/ask", json={"question": QUESTION})
    assert response.status_code == 503


@pytest.mark.parametrize("question", ["", "   ", "x" * 501])
def test_post_ask_validates_the_question(client, question):
    assert client.post("/ask", json={"question": question}).status_code == 422
