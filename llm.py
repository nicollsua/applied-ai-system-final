"""LLM access: a thin Gemini wrapper plus a FakeLLM for tests and offline runs."""

from __future__ import annotations

import os
from collections import deque

from dotenv import load_dotenv

GEMINI_MODEL = "gemini-2.5-flash"

load_dotenv()


class GeminiLLM:
    """Calls Google Gemini through the google-genai package."""

    def __init__(self, model: str = GEMINI_MODEL, api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set (add it to .env)")
        from google import genai  # imported lazily so tests never need it

        self._client = genai.Client(api_key=self.api_key)

    def ask(self, prompt: str, system: str = "") -> str:
        from google.genai import types

        config = types.GenerateContentConfig(system_instruction=system or None)
        response = self._client.models.generate_content(
            model=self.model, contents=prompt, config=config
        )
        return response.text or ""


class FakeLLM:
    """Returns queued canned responses and records every prompt it gets."""

    def __init__(self, responses: list[str] | None = None, default: str | None = None):
        self.responses = deque(responses or [])
        self.default = default
        self.prompts: list[str] = []
        self.systems: list[str] = []

    def queue(self, response: str) -> None:
        self.responses.append(response)

    def ask(self, prompt: str, system: str = "") -> str:
        self.prompts.append(prompt)
        self.systems.append(system)
        if self.responses:
            return self.responses.popleft()
        if self.default is not None:
            return self.default
        raise RuntimeError("FakeLLM has no queued responses left")


_default_llm: GeminiLLM | None = None


def ask(prompt: str, system: str = "") -> str:
    """Send one prompt to Gemini and return the text reply."""
    global _default_llm
    if _default_llm is None:
        _default_llm = GeminiLLM()
    return _default_llm.ask(prompt, system)
