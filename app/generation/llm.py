"""Sources-only answering on top of the configured LLM provider (Gemini by default)."""

from dataclasses import dataclass, field
from typing import Protocol

from app.config import Settings
from app.generation.prompts import ANSWER_SCHEMA, SYSTEM_PROMPT
from app.generation.providers import LLMError, LLMRefused, make_llm_provider

__all__ = ["AnswerLLM", "LLMAnswer", "LLMError", "ProviderLLM"]


@dataclass
class LLMAnswer:
    found: bool
    answer: str
    citations: list[dict] = field(default_factory=list)  # [{"source_id", "quote"}]
    refused: bool = False


class AnswerLLM(Protocol):
    def answer(self, user_message: str) -> LLMAnswer: ...


class ProviderLLM:
    def __init__(self, settings: Settings):
        self.provider = make_llm_provider(settings)

    def answer(self, user_message: str) -> LLMAnswer:
        try:
            data = self.provider.complete_json(SYSTEM_PROMPT, user_message, ANSWER_SCHEMA)
        except LLMRefused:
            return LLMAnswer(found=False, answer="", refused=True)
        citations = data.get("citations") or []
        return LLMAnswer(
            found=bool(data.get("found")),
            answer=str(data.get("answer") or "").strip(),
            citations=[c for c in citations if isinstance(c, dict)],
        )
