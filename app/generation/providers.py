"""LLM providers behind one call: system + user text in, a JSON object out.

- gemini:    Google Gemini (default: gemini-2.5-flash)
- openai:    any OpenAI-compatible chat API (OpenAI itself or a proxy via OPENAI_BASE_URL)
- anthropic: Claude

A primary provider can have a backup; the backup is used only when the primary
fails (network, quota, server error, unparseable output), not when it declines.
"""

import json
import logging
from typing import Protocol

from app.config import Settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The LLM could not be reached or returned an unusable response."""


class LLMRefused(RuntimeError):
    """The model declined to answer (safety filter or refusal)."""


class JSONProvider(Protocol):
    name: str

    def complete_json(self, system: str, user: str, schema: dict) -> dict: ...


def _parse(text: str | None, provider: str) -> dict:
    if not text:
        raise LLMError(f"{provider} returned an empty response.")
    text = text.strip()
    if text.startswith("```"):  # some OpenAI-compatible proxies wrap JSON in a code fence
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"{provider} returned text that is not valid JSON.") from e


class GeminiProvider:
    name = "gemini"

    def __init__(self, settings: Settings, model: str | None = None):
        from google import genai

        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not set.")
        self._genai = genai
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = model or settings.gemini_model
        self.thinking_budget = settings.gemini_thinking_budget

    def _config(self, system: str | None, schema: dict | None):
        types = self._genai.types
        return types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            response_mime_type="application/json" if schema else None,
            response_json_schema=schema,
            thinking_config=types.ThinkingConfig(thinking_budget=self.thinking_budget),
        )

    def _generate(self, contents, system: str | None, schema: dict | None):
        errors = self._genai.errors
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=contents, config=self._config(system, schema)
            )
        except errors.ClientError as e:
            raise LLMError(f"Gemini rejected the request ({e.code}): {e.message}") from e
        except errors.APIError as e:
            raise LLMError(f"Gemini API error ({e.code}): {e.message}") from e
        except Exception as e:  # network failures surface as httpx errors
            raise LLMError(f"Could not reach Gemini: {e}") from e

        feedback = response.prompt_feedback
        if feedback is not None and feedback.block_reason:
            raise LLMRefused(f"Gemini blocked the prompt ({feedback.block_reason}).")
        candidate = (response.candidates or [None])[0]
        reason = str(getattr(candidate, "finish_reason", "") or "")
        if any(r in reason for r in ("SAFETY", "PROHIBITED", "BLOCKLIST", "RECITATION")):
            raise LLMRefused(f"Gemini stopped the answer ({reason}).")
        if "MAX_TOKENS" in reason:
            raise LLMError("Gemini's answer was cut off at the token limit.")
        return response

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        return _parse(self._generate(user, system, schema).text, "Gemini")

    def transcribe(self, image_jpeg: bytes, prompt: str) -> str:
        """Vision call used by the Gemini OCR engine."""
        part = self._genai.types.Part.from_bytes(data=image_jpeg, mime_type="image/jpeg")
        return (self._generate([part, prompt], None, None).text or "").strip()


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: Settings):
        import openai

        if not settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY is not set.")
        self._openai = openai
        self.client = openai.OpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url or None
        )
        self.model = settings.openai_model

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        o = self._openai
        # json_object mode works on OpenAI and most compatible proxies; the schema goes in the prompt
        system = (
            f"{system}\n\nReply with a single JSON object matching this JSON schema:\n{json.dumps(schema)}"
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
        except o.AuthenticationError as e:
            raise LLMError("OpenAI-compatible API rejected the key; check OPENAI_API_KEY.") from e
        except o.RateLimitError as e:
            raise LLMError("OpenAI-compatible API rate limit or quota reached.") from e
        except o.APIStatusError as e:
            raise LLMError(f"OpenAI-compatible API error {e.status_code}: {e.message}") from e
        except o.APIConnectionError as e:
            raise LLMError("Could not reach the OpenAI-compatible API; check OPENAI_BASE_URL.") from e

        choice = response.choices[0]
        if choice.finish_reason == "content_filter" or getattr(choice.message, "refusal", None):
            raise LLMRefused("The backup model declined to answer.")
        if choice.finish_reason == "length":
            raise LLMError("The backup model's answer was cut off at the token limit.")
        return _parse(choice.message.content, "OpenAI-compatible API")


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: Settings):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)
        self.settings = settings

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        a, s = self._anthropic, self.settings
        extra = (
            {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if s.llm_fallbacks else {}
        )
        try:
            response = self.client.beta.messages.create(
                model=s.anthropic_model,
                max_tokens=s.llm_max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": s.llm_effort, "format": {"type": "json_schema", "schema": schema}},
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
            raise LLMRefused("Claude declined to answer.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The answer was cut off at the token limit.")
        return _parse(next((b.text for b in response.content if b.type == "text"), ""), "Anthropic")


class FallbackProvider:
    """Try the primary provider; on an LLMError, try the backup."""

    def __init__(self, primary: JSONProvider, backup: JSONProvider):
        self.primary, self.backup = primary, backup
        self.name = f"{primary.name}+{backup.name}"

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        try:
            return self.primary.complete_json(system, user, schema)
        except LLMError as e:
            log.warning("%s failed (%s); using backup %s", self.primary.name, e, self.backup.name)
            try:
                return self.backup.complete_json(system, user, schema)
            except LLMError as backup_error:
                raise LLMError(f"{e} Backup also failed: {backup_error}") from backup_error


_PROVIDERS = {"gemini": GeminiProvider, "openai": OpenAIProvider, "anthropic": AnthropicProvider}


def make_provider(name: str, settings: Settings) -> JSONProvider:
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown LLM provider {name!r}; choose from {sorted(_PROVIDERS)}")
    return _PROVIDERS[name](settings)


def make_llm_provider(settings: Settings) -> JSONProvider:
    """The configured provider, wrapped with the backup when one is set and usable."""
    primary_error = None
    try:
        primary = make_provider(settings.llm_provider, settings)
    except LLMError as e:
        primary, primary_error = None, e
    backup = None
    if settings.llm_backup_provider and settings.llm_backup_provider != settings.llm_provider:
        try:
            backup = make_provider(settings.llm_backup_provider, settings)
        except LLMError as e:
            log.warning("Backup provider %s unavailable: %s", settings.llm_backup_provider, e)
    if primary and backup:
        return FallbackProvider(primary, backup)
    if primary or backup:
        if primary_error:
            log.warning(
                "Primary provider %s unavailable (%s); using backup", settings.llm_provider, primary_error
            )
        return primary or backup
    raise primary_error or LLMError("No LLM provider is configured.")
