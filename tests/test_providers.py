import pytest

from app.config import Settings
from app.generation.llm import ProviderLLM
from app.generation.providers import (
    FallbackProvider,
    LLMError,
    LLMRefused,
    _parse,
    make_llm_provider,
)


class Stub:
    def __init__(self, name, result=None, error=None):
        self.name, self.result, self.error, self.calls = name, result, error, 0

    def complete_json(self, system, user, schema):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_backup_used_when_primary_fails():
    primary = Stub("gemini", error=LLMError("quota"))
    backup = Stub("openai", result={"found": True})
    assert FallbackProvider(primary, backup).complete_json("s", "u", {}) == {"found": True}
    assert backup.calls == 1


def test_backup_not_used_when_primary_succeeds_or_refuses():
    backup = Stub("openai", result={})
    assert FallbackProvider(Stub("gemini", result={"a": 1}), backup).complete_json("s", "u", {}) == {"a": 1}
    with pytest.raises(LLMRefused):
        FallbackProvider(Stub("gemini", error=LLMRefused("safety")), backup).complete_json("s", "u", {})
    assert backup.calls == 0


def test_both_failing_reports_both():
    p = FallbackProvider(Stub("gemini", error=LLMError("quota")), Stub("openai", error=LLMError("bad key")))
    with pytest.raises(LLMError, match="quota.*bad key"):
        p.complete_json("s", "u", {})


def test_refusal_becomes_not_found_answer():
    llm = ProviderLLM.__new__(ProviderLLM)
    llm.provider = Stub("gemini", error=LLMRefused("safety"))
    answer = llm.answer("question")
    assert answer.refused and not answer.found


def test_parse_handles_code_fences_and_rejects_junk():
    assert _parse('```json\n{"found": false}\n```', "x") == {"found": False}
    with pytest.raises(LLMError):
        _parse("not json", "x")
    with pytest.raises(LLMError):
        _parse("", "x")


def test_missing_keys_give_clear_error_and_backup_is_used():
    s = Settings(_env_file=None, gemini_api_key=None, openai_api_key=None)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        make_llm_provider(s)
    s = Settings(_env_file=None, gemini_api_key=None, openai_api_key="sk-test", llm_backup_provider="openai")
    assert make_llm_provider(s).name == "openai"
