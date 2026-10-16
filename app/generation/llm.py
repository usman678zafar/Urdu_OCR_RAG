"""Claude client that returns a structured, sources-only answer."""

import json
from dataclasses import dataclass, field
from typing import Protocol

from app.config import Settings
from app.generation.prompts import ANSWER_SCHEMA, SYSTEM_PROMPT


@dataclass
class LLMAnswer:
    found: bool
    answer: str
    citations: list[dict] = field(default_factory=list)  # [{"source_id", "quote"}]
    refused: bool = False


class LLMError(RuntimeError):
    """The LLM could not be reached or returned an unusable response."""


class AnswerLLM(Protocol):
    def answer(self, user_message: str) -> LLMAnswer: ...


class ClaudeLLM:
    def __init__(self, settings: Settings):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        self.settings = settings

    def answer(self, user_message: str) -> LLMAnswer:
        a = self._anthropic
        s = self.settings
        # Server-side fallback re-runs a policy-declined request on another model instead of failing
        extra = (
            {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if s.llm_fallbacks else {}
        )
        try:
            response = self.client.beta.messages.create(
                model=s.llm_model,
                max_tokens=s.llm_max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
                output_config={
                    "effort": s.llm_effort,
                    "format": {"type": "json_schema", "schema": ANSWER_SCHEMA},
                },
                **extra,
            )
        except a.AuthenticationError as e:
            raise LLMError("Anthropic API key is missing or invalid; set ANTHROPIC_API_KEY.") from e
        except a.RateLimitError as e:
            raise LLMError("Anthropic API rate limit reached; try again shortly.") from e
        except a.APIStatusError as e:
            raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except a.APIConnectionError as e:
            raise LLMError("Could not reach the Anthropic API.") from e
        except TypeError as e:  # raised when no credentials can be resolved at all
            raise LLMError(f"Anthropic client is not configured: {e}") from e

        if response.stop_reason == "refusal":
            return LLMAnswer(found=False, answer="", refused=True)
        if response.stop_reason == "max_tokens":
            raise LLMError("The answer was cut off at the token limit.")

        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError("The model returned an answer that is not valid JSON.") from e
        return LLMAnswer(
            found=bool(data.get("found")),
            answer=data.get("answer", "").strip(),
            citations=data.get("citations", []),
        )
