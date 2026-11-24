import os
from unittest.mock import MagicMock

import pytest

from agentic_app import llm


@pytest.fixture(autouse=True)
def fresh_client_cache():
    # get_client is lru_cached; clear it so one test's client never leaks into another
    llm.get_client.cache_clear()
    yield
    llm.get_client.cache_clear()


@pytest.fixture
def fake_client(monkeypatch):
    # Stand-in for genai.Client: records the call and returns a canned answer
    client = MagicMock()
    client.models.generate_content.return_value.text = "canned answer"
    monkeypatch.setattr(llm, "get_client", lambda: client)
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    return client


def test_generate_returns_model_text(fake_client):
    assert llm.generate("hello") == "canned answer"


def test_generate_sends_model_and_prompt(fake_client):
    llm.generate("hello")

    kwargs = fake_client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "test-model"
    assert kwargs["contents"] == "hello"


def test_generate_passes_system_instruction(fake_client):
    llm.generate("hello", system="You are terse.")

    config = fake_client.models.generate_content.call_args.kwargs["config"]
    assert config.system_instruction == "You are terse."


def test_generate_without_system_sends_no_config(fake_client):
    llm.generate("hello")

    assert fake_client.models.generate_content.call_args.kwargs["config"] is None


def test_missing_model_name_fails_before_calling_gemini(fake_client, monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL")

    with pytest.raises(ValueError, match="GEMINI_MODEL"):
        llm.generate("hello")
    fake_client.models.generate_content.assert_not_called()


def test_get_client_uses_timeout_from_env_and_is_cached(monkeypatch):
    built = MagicMock()
    monkeypatch.setattr(llm.genai, "Client", built)
    monkeypatch.setenv("GEMINI_TIMEOUT_MS", "5000")

    first = llm.get_client()
    second = llm.get_client()

    assert first is second
    built.assert_called_once()
    assert built.call_args.kwargs["http_options"].timeout == 5000


def test_get_client_defaults_timeout_when_env_unset(monkeypatch):
    built = MagicMock()
    monkeypatch.setattr(llm.genai, "Client", built)
    monkeypatch.delenv("GEMINI_TIMEOUT_MS", raising=False)

    llm.get_client()

    assert built.call_args.kwargs["http_options"].timeout == 30000


def test_empty_response_raises_instead_of_returning_none(fake_client):
    fake_client.models.generate_content.return_value.text = None

    with pytest.raises(RuntimeError, match="no text"):
        llm.generate("hello")


@pytest.mark.live
@pytest.mark.skipif(not os.getenv("GOOGLE_API_KEY"), reason="needs GOOGLE_API_KEY")
def test_live_gemini_call():
    answer = llm.generate("Reply with the single word: pong")

    assert "pong" in answer.lower()
