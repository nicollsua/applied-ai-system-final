"""Guardrails around every LLM call.

Three jobs:
  1. check_input()  -> reject empty or oversized text, strip prompt-injection
                       phrases before the text ever reaches the model
  2. safe_ask()     -> call the LLM, retry briefly on temporary errors
                       (503 overloaded, 429 rate limit, timeouts)
  3. friendly_error() -> turn any API exception into a message an owner can read
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

logger = logging.getLogger("guardrails")

MAX_INPUT_CHARS = 2000
API_RETRY_DELAYS = (2.0, 5.0)  # seconds to wait before retry 1 and retry 2

_sleep = time.sleep  # indirection so tests can skip the waiting

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|prompts?|rules)",
    r"disregard\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)?\s*(instructions|prompts?|rules)",
    r"forget\s+(all\s+|everything\s+)?(your|the|previous)?\s*(instructions|rules|everything)",
    r"you\s+are\s+now\s+[^.\n]*",
    r"(reveal|show|print|repeat)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions)",
    r"new\s+instructions?\s*:",
    r"system\s+prompt",
    r"</?\s*(system|assistant|user)\s*>",
]
_INJECTION = re.compile("|".join(f"(?:{p})" for p in INJECTION_PATTERNS), re.IGNORECASE)

_TRANSIENT_MARKERS = (
    "503", "unavailable", "high demand", "overloaded",
    "429", "resource_exhausted", "rate limit",
    "timeout", "timed out", "deadline", "connection",
)


class GuardrailError(ValueError):
    """Input was rejected before reaching the model."""


class LLMUnavailable(RuntimeError):
    """The model could not be reached; message is safe to show the user."""


@dataclass
class CheckedInput:
    text: str
    warnings: list[str] = field(default_factory=list)


def check_input(text: str | None, max_chars: int = MAX_INPUT_CHARS) -> CheckedInput:
    """Validate and clean user text. Raises GuardrailError if unusable."""
    if text is None or not text.strip():
        raise GuardrailError("Input is empty. Paste a schedule to import.")
    if len(text) > max_chars:
        raise GuardrailError(
            f"Input is too long ({len(text)} characters, max {max_chars}). "
            "Import a shorter piece at a time."
        )

    warnings: list[str] = []
    found = [m.group(0) for m in _INJECTION.finditer(text)]
    cleaned = text
    if found:
        cleaned = _INJECTION.sub(" ", text)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
        warnings.append(
            "Removed text that looked like instructions to the AI: "
            + ", ".join(repr(f.strip()) for f in found)
        )
        logger.warning("Stripped %d injection phrase(s)", len(found))

    if not cleaned.strip():
        raise GuardrailError("Nothing left to import after removing unsafe text.")
    return CheckedInput(cleaned, warnings)


def is_transient(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def friendly_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "api_key" in text or "api key" in text or "permission" in text or "401" in text or "403" in text:
        return "The AI service rejected the API key. Check GEMINI_API_KEY in your .env file."
    if "404" in text or "not_found" in text:
        return "The AI model was not found. The model name in llm.py may need updating."
    if "429" in text or "quota" in text or "resource_exhausted" in text:
        return "The AI service quota or rate limit was hit. Wait a minute and try again."
    if is_transient(exc):
        return "The AI service is busy or unreachable right now. Please try again in a minute."
    return f"The AI service failed unexpectedly ({type(exc).__name__}). Please try again."


def safe_ask(llm, prompt: str, system: str = "", delays: tuple[float, ...] = API_RETRY_DELAYS) -> str:
    """Call llm.ask, retrying temporary failures. Raises LLMUnavailable."""
    attempt = 0
    while True:
        try:
            return llm.ask(prompt, system)
        except Exception as exc:
            if is_transient(exc) and attempt < len(delays):
                logger.warning("Temporary LLM error (%s); retrying in %.0fs", exc, delays[attempt])
                _sleep(delays[attempt])
                attempt += 1
                continue
            logger.error("LLM call failed: %s", exc)
            raise LLMUnavailable(friendly_error(exc)) from exc
