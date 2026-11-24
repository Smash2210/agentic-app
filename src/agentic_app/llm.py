import os

from dotenv import load_dotenv
from functools import lru_cache
from google import genai
from google.genai import types

load_dotenv()

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
