"""Fakes for the heavy services, so the whole pipeline runs in tests without
downloading models, installing Tesseract or calling the Anthropic API."""

import hashlib
import math
import re

import pymupdf
import pytest
from PIL import Image

from app.config import Settings
from app.generation.llm import LLMAnswer
from app.ingestion.ocr import OCRResult
from app.processing.normalize import tokenize
from app.services import Services

URDU_PARAGRAPH = (
    "حکومت پنجاب نے طلبہ کے لیے نئی وظیفہ پالیسی کا اعلان کیا ہے۔ اس پالیسی کے تحت ہر مستحق "
    "طالب علم کو ماہانہ بارہ ہزار روپے دیے جائیں گے۔ درخواست جمع کروانے کی آخری تاریخ پندرہ مارچ "
    "ہے اور درخواستیں ضلعی دفتر میں جمع کی جائیں گی۔ مزید معلومات کے لیے دفتر سے رابطہ کریں۔"
)

ENGLISH_PARAGRAPH = (
    "The welfare committee met on 12 January 2026 to review the scholarship policy. "
    "Under the revised policy, each eligible student will receive a monthly stipend of "
    "Rs. 12,000 for the duration of the program. Applications must be submitted at the "
    "district office before the deadline, and incomplete forms will not be considered."
)


class FakeEmbedder:
    model_name = "fake-embedder"
    dims = 64

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dims
        for tok in tokenize(text):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dims] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class FakeReranker:
    def score(self, query, passages):
        q = set(tokenize(query))
        return [len(q & set(tokenize(p))) / (len(q) or 1) for p in passages]


class FakeOCR:
    name = "fake"

    def __init__(self, text: str = URDU_PARAGRAPH):
        self.text = text
        self.calls = 0

    def ocr(self, image: Image.Image) -> OCRResult:
        self.calls += 1
        return OCRResult(text=self.text, confidence=0.42)


class FakeLLM:
    """Answers from the first source and quotes its opening words."""

    def __init__(self):
        self.messages: list[str] = []

    def answer(self, user_message: str) -> LLMAnswer:
        self.messages.append(user_message)
        match = re.search(r'<source id="S1"[^>]*>\n(.*?)\n</source>', user_message, re.S)
        if not match or "unrelated" in user_message:
            return LLMAnswer(found=False, answer="")
        first = match.group(1)
        return LLMAnswer(
            found=True,
            answer="fake answer",
            citations=[
                {"source_id": "S1", "quote": " ".join(first.split()[:6])},
                {"source_id": "S99", "quote": "unknown source"},
            ],
        )


@pytest.fixture
def services(tmp_path) -> Services:
    settings = Settings(
        _env_file=None,
        storage_dir=tmp_path / "storage",
        embedding_model="fake-embedder",
        preload_models=False,
    )
    s = Services(settings)
    s.embedder = FakeEmbedder()
    s.reranker = FakeReranker()
    s.ocr = FakeOCR()
    s.fallback_ocr = None  # never call a real outside OCR service from tests
    s.llm = FakeLLM()
    return s


def make_pdf(pages: list[str | None]) -> bytes:
    """A PDF with one page per entry; None makes a page with no text layer (a 'scan')."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data
