import os
import time

from dotenv import load_dotenv
from functools import lru_cache
from google import genai
from google.genai import errors, types

load_dotenv()

# Temporary errors worth retrying: rate limit, server error, overloaded ("high demand").
TRANSIENT_CODES = (429, 500, 503)
BACKOFF_S = (5, 10, 20)
_sleep = time.sleep  # replaced in tests


class ModelUnavailable(RuntimeError):
    """The model could not be reached: not configured, or still failing after retries."""


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    timeout_ms = int(os.getenv("GEMINI_TIMEOUT_MS", "30000"))
    c = genai.Client(http_options=types.HttpOptions(timeout=timeout_ms))
    return c

def _model_name() -> str:
    model_name = os.getenv("GEMINI_MODEL")
    if not model_name:
        raise ValueError("GEMINI_MODEL environment variable is not set.")
    return model_name

def model_name() -> str:
    return _model_name()

def generate(prompt:str, *, system: str | None = None) -> str:
    model_name = _model_name()
    c = get_client()
    config = types.GenerateContentConfig(system_instruction=system) if system else None
    response = c.models.generate_content(
        model=model_name,
        contents=prompt,
        config=config
    )
    if response.text is None:
        # e.g. the answer was blocked by a safety filter
        raise RuntimeError(f"Gemini returned no text (model={model_name}).")
    return response.text

def generate_content(contents, config: types.GenerateContentConfig) -> types.GenerateContentResponse:
    """One model call, retrying temporary errors with backoff; anything else is raised at once."""
    try:
        model = _model_name()
        client = get_client()
    except ValueError as exc:  # no model name or no API key
        raise ModelUnavailable(f"model not configured: {exc}") from exc
    for attempt in range(len(BACKOFF_S) + 1):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as exc:
            if exc.code not in TRANSIENT_CODES:
                raise
            if attempt == len(BACKOFF_S):
                raise ModelUnavailable(
                    f"{model} still unavailable after {attempt + 1} tries (HTTP {exc.code})"
                ) from exc
            _sleep(BACKOFF_S[attempt])
