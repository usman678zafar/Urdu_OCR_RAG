"""OCR quality check, retries, the Tesseract fallback, resumable reprocessing and the
relevance threshold."""

import pytest
from fastapi.testclient import TestClient

from app.generation.providers import LLMError
from app.ingestion.ocr import OCRResult
from app.ingestion.ocr_quality import ocr_quality
from app.ingestion.retry import AdaptiveLimiter, backoff_delay, call_with_retry, is_retryable
from app.main import app
from app.services import get_services
from tests.conftest import ENGLISH_PARAGRAPH, URDU_PARAGRAPH, make_pdf

# Real Tesseract output from a scanned Nastaliq book page
GARBLED = (
    "rar HA بی کے متا ہروں مل (i) SEL toy کی کے ew نے کرت رائے سے ارکان be Wty اضان ہ گر "
    "aad یس ساڑ سے مین سو Unie 1 ورڑاء ky منظو رک میا۔ وزرا ا اور Sede Ske زیشن"
)


# ---- quality score -----------------------------------------------------------


def test_clean_urdu_passes(services):
    q = ocr_quality(URDU_PARAGRAPH)
    assert q.urdu_share == 1.0 and not q.garbled(services.settings)


def test_garbled_urdu_is_caught(services):
    q = ocr_quality(GARBLED)
    assert 0.1 < q.urdu_share < 0.85
    assert q.garbled(services.settings)


def test_english_page_is_not_garbled_urdu(services):
    q = ocr_quality(ENGLISH_PARAGRAPH)
    assert q.urdu_share == 0.0 and not q.garbled(services.settings)


def test_urdu_with_a_few_english_terms_passes(services):
    text = URDU_PARAGRAPH + " Punjab Education Department"
    assert not ocr_quality(text).garbled(services.settings)


def test_empty_or_tiny_output_counts_as_garbled(services):
    assert ocr_quality("").garbled(services.settings)
    assert ocr_quality("۳۰۰ ab").garbled(services.settings)


# ---- retries -----------------------------------------------------------------


def flaky(errors: list[Exception], value="ok"):
    calls = []

    def fn():
        calls.append(1)
        if errors:
            raise errors.pop(0)
        return value

    return fn, calls


def test_retries_transient_errors_then_succeeds():
    fn, calls = flaky([LLMError("busy", status=503), LLMError("slow down", status=429)])
    slept = []
    assert call_with_retry(fn, attempts=4, base_delay=2, sleep=slept.append, rng=lambda: 0) == "ok"
    assert len(calls) == 3
    assert slept == [2, 4]  # exponential backoff


def test_gives_up_after_max_attempts():
    fn, calls = flaky([LLMError("busy", status=503) for _ in range(10)])
    with pytest.raises(LLMError):
        call_with_retry(fn, attempts=4, base_delay=1, sleep=lambda _: None)
    assert len(calls) == 4


def test_does_not_retry_permanent_errors():
    fn, calls = flaky([LLMError("bad key", status=400)])
    with pytest.raises(LLMError):
        call_with_retry(fn, attempts=4, base_delay=1, sleep=lambda _: None)
    assert len(calls) == 1


def test_retryable_classification():
    assert is_retryable(TimeoutError())
    assert is_retryable(LLMError("network", retryable=True))
    assert is_retryable(LLMError("x", status=503))
    assert not is_retryable(LLMError("x", status=403))
    assert not is_retryable(ValueError("bug"))


def test_backoff_jitter_stays_within_half():
    assert backoff_delay(3, 2, rng=lambda: 0) == 8
    assert backoff_delay(3, 2, rng=lambda: 1) == 12


def test_limiter_halves_on_rate_limit_and_recovers():
    lim = AdaptiveLimiter(4, recover_after=2)
    lim.rate_limited()
    assert lim.limit == 2
    lim.rate_limited()
    lim.rate_limited()
    assert lim.limit == 1
    for _ in range(4):
        lim.succeeded()
    assert lim.limit == 3


# ---- pipeline: fallback, failures and resuming -------------------------------


class ScriptedOCR:
    """Returns texts (or raises errors) from a script, one entry per call."""

    def __init__(self, name: str, script: list):
        self.name, self.script, self.calls = name, list(script), 0

    def ocr(self, image) -> OCRResult:
        self.calls += 1
        item = self.script.pop(0) if self.script else URDU_PARAGRAPH
        if isinstance(item, Exception):
            raise item
        return OCRResult(text=item, confidence=0.5)


@pytest.fixture
def client(services):
    services.settings.ocr_retry_base_delay = 0
    services.settings.ocr_concurrency = 1  # keeps the scripted call order deterministic
    app.dependency_overrides[get_services] = lambda: services
    import app.services as svc

    previous, svc._services = svc._services, services
    with TestClient(app) as c:
        yield c
    svc._services = previous
    app.dependency_overrides.clear()


def upload_scan(client, pages: int) -> int:
    data = make_pdf([None] * pages)  # pages without a text layer go to OCR
    return client.post("/documents", files={"file": ("scan.pdf", data, "application/pdf")}).json()[
        "document"
    ]["id"]


def test_garbled_tesseract_page_is_reread_by_fallback(client, services):
    services.ocr = ScriptedOCR("tesseract", [URDU_PARAGRAPH, GARBLED])
    services.fallback_ocr = ScriptedOCR("gemini", [URDU_PARAGRAPH])
    doc_id = upload_scan(client, 2)

    pages = client.get(f"/documents/{doc_id}").json()["pages"]
    assert [p["method"] for p in pages] == ["tesseract", "gemini"]
    assert [p["ocr_status"] for p in pages] == ["ok", "ok"]
    assert "garbled" in pages[1]["reason"]
    assert services.fallback_ocr.calls == 1


def test_without_fallback_garbled_page_is_flagged_not_sent_out(client, services):
    services.settings.ocr_fallback_enabled = False
    services.ocr = ScriptedOCR("tesseract", [GARBLED])
    services.__dict__.pop("_fallback_ocr", None)
    assert services.fallback_ocr is None  # nothing would be sent to an outside service

    doc_id = upload_scan(client, 1)
    detail = client.get(f"/documents/{doc_id}").json()
    assert detail["pages"][0]["method"] == "tesseract"
    assert detail["pages"][0]["ocr_status"] == "low_quality"
    assert detail["status"] == "ready" and "low-quality" in detail["error"]


def test_failed_page_does_not_fail_document_and_reprocess_redoes_only_it(client, services):
    overloaded = [LLMError("Gemini API error (503)", status=503)] * 4  # every attempt fails
    services.ocr = ScriptedOCR("gemini", [URDU_PARAGRAPH, *overloaded, URDU_PARAGRAPH])
    doc_id = upload_scan(client, 3)

    detail = client.get(f"/documents/{doc_id}").json()
    assert detail["status"] == "ready"
    assert detail["pages_failed"] == 1
    assert [p["ocr_status"] for p in detail["pages"]] == ["ok", "failed", "ok"]
    assert "503" in detail["pages"][1]["error"]
    assert services.ocr.calls == 6  # 1 + 4 attempts + 1

    # incremental reprocess: only the failed page is OCR'd again
    services.ocr = ScriptedOCR("gemini", [URDU_PARAGRAPH])
    assert client.post(f"/documents/{doc_id}/reprocess").status_code == 202
    detail = client.get(f"/documents/{doc_id}").json()
    assert services.ocr.calls == 1
    assert detail["pages_failed"] == 0 and detail["error"] is None
    assert all(p["ocr_status"] == "ok" for p in detail["pages"])

    # full reprocess: every page again
    services.ocr = ScriptedOCR("gemini", [])
    client.post(f"/documents/{doc_id}/reprocess?full=true")
    assert services.ocr.calls == 3


# ---- relevance threshold -----------------------------------------------------


def test_low_relevance_answers_not_found_without_llm(client, services):
    services.ocr = ScriptedOCR("gemini", [URDU_PARAGRAPH])
    upload_scan(client, 1)
    question = {"question": "وظیفہ کی ماہانہ رقم کتنی ہے؟"}

    services.settings.min_relevance_score = 0.99
    r = client.post("/ask", json=question).json()
    assert r["found"] is False
    assert services.llm.messages == []  # LLM never called

    services.settings.min_relevance_score = 0.01
    services.settings.debug_timings = True
    r = client.post("/ask", json={"question": "ماہانہ وظیفہ کتنا ہے؟"}).json()
    assert r["found"] is True and len(services.llm.messages) == 1
    assert {"embed_query", "vector_search", "bm25", "rerank", "llm", "total"} <= set(r["timings"])
