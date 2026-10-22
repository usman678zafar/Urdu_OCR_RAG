"""The indexing pipeline, run once per document in the background:
classify pages -> extract or OCR -> clean and normalize -> chunk -> embed -> store.

OCR runs on several pages at once. Each page is saved as soon as it is read, so an
interrupted run loses nothing, and a later reprocess only redoes pages that failed
or came out garbled. One page failing never fails the whole document.
"""

import logging
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor

import pymupdf

from app.config import Settings
from app.db.database import Database
from app.ingestion import pdf
from app.ingestion.classifier import classify_text
from app.ingestion.ocr import OCREngine, OCRResult
from app.ingestion.ocr_quality import ocr_quality
from app.ingestion.retry import AdaptiveLimiter, call_with_retry, status_of
from app.processing.bidi import WordOrderVotes, document_is_reversed, reverse_urdu_lines, word_order_votes
from app.processing.chunking import chunk_pages
from app.processing.cleanup import strip_headers_footers
from app.processing.normalize import normalize
from app.retrieval.embeddings import Embedder
from app.retrieval.vector_store import VectorStore

log = logging.getLogger(__name__)

LEGACY_OCR_METHOD = "ocr"  # pages OCR'd before the engine name was stored (always Tesseract)


class _Progress:
    """Thread-safe page counters, written to the document row as pages finish."""

    def __init__(self, db: Database, doc_id: int):
        self.db, self.doc_id = db, doc_id
        self.done = self.failed = 0
        self._lock = threading.Lock()

    def page_finished(self, failed: bool = False) -> None:
        with self._lock:
            self.done += 1
            self.failed += int(failed)
            self.db.set_progress(self.doc_id, self.done, self.failed)


class IndexingPipeline:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        embedder_factory,
        store_factory,
        ocr_factory,
        fallback_ocr_factory=lambda: None,
    ):
        # Factories defer loading heavy models until the first document needs them
        self.settings = settings
        self.db = db
        self._embedder_factory = embedder_factory
        self._store_factory = store_factory
        self._ocr_factory = ocr_factory
        self._fallback_ocr_factory = fallback_ocr_factory  # returns None when there is no fallback
        self._lock = threading.Lock()  # one document at a time keeps memory use flat

    def original_path(self, sha256: str):
        return self.settings.originals_dir / f"{sha256}.pdf"

    def page_dir(self, doc_id: int):
        return self.settings.pages_dir / str(doc_id)

    def process(self, doc_id: int, full: bool = True) -> None:
        """Index a document. full=False keeps pages that were already read well and only
        redoes failed, garbled or missing ones (this also resumes an interrupted run)."""
        with self._lock:
            try:
                self._process(doc_id, full)
            except Exception as e:
                log.exception("Processing document %s failed", doc_id)
                self._cleanup_vectors(doc_id)
                self.db.set_status(doc_id, "failed", f"{type(e).__name__}: {e}")

    def _process(self, doc_id: int, full: bool) -> None:
        s = self.settings
        doc_row = self.db.get_document(doc_id)
        if doc_row is None:
            return
        self._cleanup_vectors(doc_id)
        existing = {} if full else {p["page_no"]: p for p in self.db.get_pages(doc_id)}
        self.db.clear_document_content(doc_id, keep_pages=not full)
        self.db.set_status(doc_id, "extracting")

        page_dir = self.page_dir(doc_id)
        page_dir.mkdir(parents=True, exist_ok=True)
        progress = _Progress(self.db, doc_id)
        limiter = AdaptiveLimiter(s.ocr_concurrency)
        # bounds how many rendered high-dpi page images wait in memory for a worker
        slots = threading.BoundedSemaphore(s.ocr_concurrency * 2)

        order_votes: list[WordOrderVotes] = []
        # text-layer pages too ambiguous to judge alone: page_no -> (text, reason, image_path)
        unsure_order: dict[int, tuple[str, str, str]] = {}

        with (
            pymupdf.open(self.original_path(doc_row["sha256"])) as doc,
            ThreadPoolExecutor(max_workers=s.ocr_concurrency, thread_name_prefix="ocr") as pool,
        ):
            futures = []
            for index, page in enumerate(doc):
                page_no = index + 1
                image_path = page_dir / f"{page_no}.png"
                if not image_path.exists():
                    pdf.render_page(page, s.preview_dpi).save(image_path)

                old = existing.get(page_no)
                if old is not None and self._page_is_good(old):
                    progress.page_finished()
                    continue

                text = pdf.page_text(page)
                decision = classify_text(text, pdf.image_coverage(page), s)
                if decision.method == "text":
                    votes = word_order_votes(text)
                    order_votes.append(votes)
                    reason = decision.reason
                    if votes.reversed:
                        text = reverse_urdu_lines(text)
                        reason += "; word order repaired"
                    elif not votes.in_order:
                        unsure_order[page_no] = (text, reason, str(image_path))
                    self.db.save_page(
                        doc_id,
                        page_no,
                        "text",
                        reason,
                        text="",
                        raw_text=text,
                        image_path=str(image_path),
                        ocr_confidence=None,
                    )
                    progress.page_finished()
                    continue

                # pymupdf is not thread-safe, so pages are rendered here and OCR'd in the pool
                slots.acquire()
                image = pdf.render_page(page, s.ocr_dpi)
                future = pool.submit(
                    self._ocr_page,
                    doc_id,
                    page_no,
                    image,
                    decision.reason,
                    str(image_path),
                    progress,
                    limiter,
                )
                future.add_done_callback(lambda _: slots.release())
                futures.append(future)
            for future in futures:
                future.result()

        if unsure_order and document_is_reversed(order_votes):
            for page_no, (text, reason, image_path) in unsure_order.items():
                fixed = reverse_urdu_lines(text)
                if fixed == text:  # no Urdu lines
                    continue
                self.db.save_page(
                    doc_id,
                    page_no,
                    "text",
                    reason + "; word order repaired (whole document is reversed)",
                    text="",
                    raw_text=fixed,
                    image_path=image_path,
                    ocr_confidence=None,
                )

        self.db.set_status(doc_id, "indexing")
        pages = self.db.get_pages(doc_id)
        cleaned = strip_headers_footers([p["raw_text"] for p in pages])
        normalized = {p["page_no"]: normalize(t) for p, t in zip(pages, cleaned)}
        self.db.update_page_texts(doc_id, normalized)

        chunks = chunk_pages(sorted(normalized.items()), s.chunk_size, s.chunk_overlap)
        if chunks:
            chunk_ids = self.db.insert_chunks(doc_id, [c.__dict__ for c in chunks])
            embedder: Embedder = self._embedder_factory()
            vectors = embedder.embed_documents([c.text for c in chunks])
            store: VectorStore = self._store_factory()
            store.add(chunk_ids, vectors, doc_id, [c.page_no for c in chunks])

        failed = sum(1 for p in pages if p["ocr_status"] == "failed")
        low = sum(1 for p in pages if p["ocr_status"] == "low_quality")
        problems = [f"{failed} page(s) failed OCR"] if failed else []
        problems += [f"{low} page(s) have low-quality OCR"] if low else []
        note = "; ".join(problems) + ". Reprocess to retry them." if problems else None
        self.db.set_status(doc_id, "ready", note)
        self.db.bump_index_version()

    def _page_is_good(self, page: dict) -> bool:
        if page["ocr_status"] != "ok":
            return False
        if page["method"] == LEGACY_OCR_METHOD:  # judge old Tesseract pages by today's check
            return not ocr_quality(page["raw_text"]).garbled(self.settings)
        return True

    def _run_ocr(self, engine: OCREngine, image, limiter: AdaptiveLimiter) -> OCRResult:
        def attempt() -> OCRResult:
            with limiter:
                return engine.ocr(image)

        def on_retry(error: BaseException, _attempt: int) -> None:
            if status_of(error) == 429:
                limiter.rate_limited()

        s = self.settings
        result = call_with_retry(attempt, s.ocr_max_attempts, s.ocr_retry_base_delay, on_retry)
        limiter.succeeded()
        return result

    def _ocr_page(
        self,
        doc_id: int,
        page_no: int,
        image,
        reason: str,
        image_path: str,
        progress: _Progress,
        limiter: AdaptiveLimiter,
    ) -> None:
        """OCR one page (with retries and the Tesseract fallback) and save it straight away."""
        s = self.settings
        method = s.ocr_engine
        try:
            engine = self._ocr_factory()
            method = engine.name
            result = self._run_ocr(engine, image, limiter)
            status, error = "ok", None

            if engine.name == "tesseract":
                quality = ocr_quality(result.text)
                if quality.garbled(s):
                    status = "low_quality"
                    reason = f"{reason}; Tesseract output garbled ({quality.describe()})"
                    try:
                        fallback = self._fallback_ocr_factory()
                        if fallback is not None:
                            result = self._run_ocr(fallback, image, limiter)
                            method, status = fallback.name, "ok"
                            reason += f", re-read with {fallback.name}"
                    except Exception as e:
                        log.warning("Fallback OCR failed on document %s page %s: %s", doc_id, page_no, e)
                        error = f"Fallback OCR failed: {type(e).__name__}: {e}"
        except Exception as e:
            log.warning("OCR failed on document %s page %s: %s", doc_id, page_no, e)
            self.db.save_page(
                doc_id,
                page_no,
                method,
                reason,
                text="",
                raw_text="",
                image_path=image_path,
                ocr_confidence=None,
                ocr_status="failed",
                error=f"{type(e).__name__}: {e}",
            )
            progress.page_finished(failed=True)
            return

        self.db.save_page(
            doc_id,
            page_no,
            method,
            reason,
            text="",
            raw_text=result.text,
            image_path=image_path,
            ocr_confidence=result.confidence,
            ocr_status=status,
            quality=ocr_quality(result.text).urdu_share,
            error=error,
        )
        progress.page_finished()

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
