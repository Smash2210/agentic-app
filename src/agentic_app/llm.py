import os
import time

from dotenv import load_dotenv
from functools import lru_cache
from google import genai
from google.genai import errors, types

load_dotenv()

# Temporary errors worth retrying: rate limit, server error, overloaded ("high demand").
TRANSIENT_CODES = (429, 500, 503)


def _transport_errors() -> tuple[type[Exception], ...]:
    """Timeouts and connection failures from the HTTP client the SDK uses (httpx2, or httpx)."""
    found = []
    for name in ("httpx2", "httpx"):
        try:
            found.append(__import__(name).TransportError)
        except (ImportError, AttributeError):
            pass
    return tuple(found)


TRANSPORT_ERRORS = _transport_errors()
BACKOFF_S = (5, 10)  # per model: 3 tries over ~15 s, then the next model in the fallback list
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

def models() -> list[str]:
    """GEMINI_MODEL first, then GEMINI_FALLBACK_MODELS (comma-separated), in order, no repeats."""
    names = [_model_name()]
    for name in os.getenv("GEMINI_FALLBACK_MODELS", "").split(","):
        if name.strip() and name.strip() not in names:
            names.append(name.strip())
    return names

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

def generate_content(
    contents, config: types.GenerateContentConfig, *, prefer: str | None = None
) -> types.GenerateContentResponse:
    """One model call. Temporary errors are retried with backoff, then the next fallback model is
    tried; any other error is raised at once. `prefer` (a model that already answered in this
    conversation) is tried first. The response's model_version is set to the model that answered."""
    try:
        names = models()
        client = get_client()
    except ValueError as exc:  # no model name or no API key
        raise ModelUnavailable(f"model not configured: {exc}") from exc
    if prefer in names:
        names = [prefer] + [n for n in names if n != prefer]
    failures = []
    for model in names:
        for attempt in range(len(BACKOFF_S) + 1):
            try:
                response = client.models.generate_content(model=model, contents=contents, config=config)
                response.model_version = model  # the name we asked for, so callers can prefer it
                return response
            except (errors.APIError, *TRANSPORT_ERRORS) as exc:
                if isinstance(exc, errors.APIError) and exc.code not in TRANSIENT_CODES:
                    raise
                if attempt == len(BACKOFF_S):
                    reason = f"HTTP {exc.code}" if isinstance(exc, errors.APIError) else type(exc).__name__
                    failures.append(f"{model} ({reason})")
                    break
                _sleep(BACKOFF_S[attempt])
    raise ModelUnavailable(
        f"model unavailable after {len(BACKOFF_S) + 1} tries each: {', '.join(failures)}"
    )
