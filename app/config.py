"""Application settings, read from environment variables or a .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Storage
    storage_dir: Path = Path("storage")
    max_upload_mb: int = 50
    max_pages: int = 500

    # Page classifier
    min_text_chars: int = 30  # fewer letters than this -> treat page as scanned
    max_garbage_ratio: float = 0.05  # private-use / replacement glyphs -> broken text layer
    max_latin_ext_ratio: float = 0.3  # Latin-1 accented letters -> InPage mojibake
    max_mixed_script_ratio: float = 0.15  # Urdu words with Latin letters inside -> broken mapping
    max_single_letter_ratio: float = 0.4  # Urdu letters split apart by spaces
    min_common_word_ratio: float = 0.05  # Urdu/English function words -> real, ordered text
    image_coverage_threshold: float = 0.5
    image_page_max_chars: int = 300  # a big image with little text is a scan with a stamp/header

    # OCR
    ocr_engine: Literal["tesseract", "claude", "docai"] = "tesseract"
    tesseract_cmd: str | None = None  # e.g. C:\Program Files\Tesseract-OCR\tesseract.exe
    tesseract_lang: str = "urd+eng"
    tesseract_config: str = "--oem 1 --psm 3"
    ocr_dpi: int = 300
    preview_dpi: int = 150
    low_confidence_threshold: float = 0.6
    docai_project_id: str | None = None
    docai_location: str = "us"
    docai_processor_id: str | None = None

    # Chunking
    chunk_size: int = 800  # characters
    chunk_overlap: int = 150

    # Retrieval
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str | None = None  # None = auto (cuda if available)
    embedding_batch_size: int = 16
    embedding_max_seq_length: int = 512
    reranker_enabled: bool = True
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_min_score: float | None = None  # below this top score, answer "not found" without the LLM
    dense_top_k: int = 20
    bm25_top_k: int = 20
    candidate_k: int = 20
    final_top_k: int = 6

    # Generation
    anthropic_api_key: str | None = None  # falls back to the SDK's own credential lookup
    llm_model: str = "claude-sonnet-5-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    llm_max_tokens: int = 16000
    llm_fallbacks: bool = True  # server-side refusal fallback (Claude API only)
    vision_ocr_model: str = "claude-sonnet-5-5"
    answer_cache_size: int = 256

    @property
    def db_path(self) -> Path:
        return self.storage_dir / "app.db"

    @property
    def originals_dir(self) -> Path:
        return self.storage_dir / "originals"

    @property
    def pages_dir(self) -> Path:
        return self.storage_dir / "pages"

    @property
    def chroma_dir(self) -> Path:
        return self.storage_dir / "chroma"

    def ensure_dirs(self) -> None:
        for d in (self.storage_dir, self.originals_dir, self.pages_dir, self.chroma_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
