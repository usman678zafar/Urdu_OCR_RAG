"""Request and response models for the HTTP API."""

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: int
    filename: str
    sha256: str
    page_count: int
    pages_done: int
    pages_failed: int = 0
    status: str
    error: str | None
    uploaded_at: str
    updated_at: str


class UploadOut(BaseModel):
    document: DocumentOut
    duplicate: bool


class PageOut(BaseModel):
    page_no: int
    method: str  # text | tesseract | gemini | claude | docai
    reason: str | None
    ocr_confidence: float | None
    ocr_status: str  # ok | low_quality | failed
    quality: float | None  # share of Urdu (Arabic-script) letters among all letters
    error: str | None
    low_confidence: bool
    text_chars: int
    image_url: str


class DocumentDetailOut(DocumentOut):
    pages: list[PageOut]


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[int] | None = None


class CitationOut(BaseModel):
    document_id: int
    filename: str
    page_no: int
    quote: str
    passage: str
    quote_verified: bool
    image_url: str


class AskOut(BaseModel):
    answer: str
    language: str
    found: bool
    grounded: bool
    citations: list[CitationOut]
    latency_ms: int
    cached: bool
    note: str | None = None
    timings: dict[str, int] | None = None  # milliseconds per step, when DEBUG_TIMINGS is on
