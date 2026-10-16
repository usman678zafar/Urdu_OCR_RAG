"""The indexing pipeline, run once per document in the background:
classify pages -> extract or OCR -> clean and normalize -> chunk -> embed -> store."""

import logging
import shutil
import threading

import pymupdf

from app.config import Settings
from app.db.database import Database
from app.ingestion import pdf
from app.ingestion.classifier import classify_text
from app.ingestion.ocr import OCREngine
from app.processing.bidi import fix_word_order
from app.processing.chunking import chunk_pages
from app.processing.cleanup import strip_headers_footers
from app.processing.normalize import normalize
from app.retrieval.embeddings import Embedder
from app.retrieval.vector_store import VectorStore

log = logging.getLogger(__name__)


class IndexingPipeline:
    def __init__(self, settings: Settings, db: Database, embedder_factory, store_factory, ocr_factory):
        # Factories defer loading heavy models until the first document needs them
        self.settings = settings
        self.db = db
        self._embedder_factory = embedder_factory
        self._store_factory = store_factory
        self._ocr_factory = ocr_factory
        self._lock = threading.Lock()  # one document at a time keeps memory use flat

    def original_path(self, sha256: str):
        return self.settings.originals_dir / f"{sha256}.pdf"

    def page_dir(self, doc_id: int):
        return self.settings.pages_dir / str(doc_id)

    def process(self, doc_id: int) -> None:
        with self._lock:
            try:
                self._process(doc_id)
            except Exception as e:
                log.exception("Processing document %s failed", doc_id)
                self._cleanup_vectors(doc_id)
                self.db.set_status(doc_id, "failed", f"{type(e).__name__}: {e}")

    def _process(self, doc_id: int) -> None:
        s = self.settings
        doc_row = self.db.get_document(doc_id)
        if doc_row is None:
            return
        self._cleanup_vectors(doc_id)
        self.db.clear_document_content(doc_id)
        self.db.set_status(doc_id, "extracting")

        page_dir = self.page_dir(doc_id)
        page_dir.mkdir(parents=True, exist_ok=True)
        ocr: OCREngine | None = None

        raw_pages: list[tuple[int, str]] = []
        with pymupdf.open(self.original_path(doc_row["sha256"])) as doc:
            for index, page in enumerate(doc):
                page_no = index + 1
                image_path = page_dir / f"{page_no}.png"
                pdf.render_page(page, s.preview_dpi).save(image_path)

                text = pdf.page_text(page)
                decision = classify_text(text, pdf.image_coverage(page), s)
                confidence = None
                reason = decision.reason
                if decision.method == "text":
                    text, flipped = fix_word_order(text)
                    if flipped:
                        reason += "; word order repaired"
                else:
                    ocr = ocr or self._ocr_factory()
                    result = ocr.ocr(pdf.render_page(page, s.ocr_dpi))
                    text, confidence = result.text, result.confidence

                self.db.save_page(
                    doc_id,
                    page_no,
                    decision.method,
                    reason,
                    text="",
                    raw_text=text,
                    image_path=str(image_path),
                    ocr_confidence=confidence,
                )
                raw_pages.append((page_no, text))
                self.db.set_progress(doc_id, page_no)

        self.db.set_status(doc_id, "indexing")
        cleaned = strip_headers_footers([t for _, t in raw_pages])
        normalized = {n: normalize(t) for (n, _), t in zip(raw_pages, cleaned)}
        self.db.update_page_texts(doc_id, normalized)

        chunks = chunk_pages(sorted(normalized.items()), s.chunk_size, s.chunk_overlap)
        if chunks:
            chunk_ids = self.db.insert_chunks(doc_id, [c.__dict__ for c in chunks])
            embedder: Embedder = self._embedder_factory()
            vectors = embedder.embed_documents([c.text for c in chunks])
            store: VectorStore = self._store_factory()
            store.add(chunk_ids, vectors, doc_id, [c.page_no for c in chunks])

        self.db.set_status(doc_id, "ready")
        self.db.bump_index_version()

    def reembed(self, doc_id: int) -> None:
        """Embed a ready document's stored chunks into the current model's collection
        (used when comparing embedding models, so pages are not extracted or OCR'd again)."""
        with self._lock:
            ids = self.db.chunk_ids_for_document(doc_id)
            rows = self.db.get_chunks(ids)
            store: VectorStore = self._store_factory()
            store.delete_document(doc_id)
            if ids:
                vectors = self._embedder_factory().embed_documents([rows[i]["text"] for i in ids])
                store.add(ids, vectors, doc_id, [rows[i]["page_no"] for i in ids])

    def _cleanup_vectors(self, doc_id: int) -> None:
        try:
            self._store_factory().delete_document(doc_id)
        except Exception:
            log.exception("Could not remove vectors for document %s", doc_id)

    def delete(self, doc_id: int) -> None:
        doc_row = self.db.get_document(doc_id)
        if doc_row is None:
            return
        self._cleanup_vectors(doc_id)
        self.db.delete_document(doc_id)
        shutil.rmtree(self.page_dir(doc_id), ignore_errors=True)
        self.original_path(doc_row["sha256"]).unlink(missing_ok=True)
