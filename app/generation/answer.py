"""The answering pipeline: normalize -> hybrid retrieve -> rerank -> LLM -> citation check."""

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from app.config import Settings
from app.db.database import Database
from app.generation.citations import Citation, build_citations
from app.generation.llm import AnswerLLM
from app.generation.prompts import NOT_FOUND, build_user_message
from app.processing.language import question_language
from app.processing.normalize import normalize
from app.retrieval.hybrid import HybridRetriever, Progress, RetrievedChunk, timed

logger = logging.getLogger(__name__)


@dataclass
class AnswerResult:
    question: str
    answer: str
    language: str
    found: bool
    grounded: bool  # every citation's quote was found in its source chunk
    citations: list[Citation]
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    latency_ms: int = 0
    cached: bool = False
    note: str | None = None
    timings: dict[str, int] = field(default_factory=dict)  # milliseconds per step


def relevance(chunks: list[RetrievedChunk], reranker_enabled: bool) -> float | None:
    """How well the best chunk matches: top reranker score, or top vector similarity."""
    if not chunks:
        return None
    if reranker_enabled:
        return chunks[0].score
    similarities = [c.similarity for c in chunks if c.similarity is not None]
    return max(similarities) if similarities else None


class AnswerService:
    def __init__(self, settings: Settings, db: Database, retriever: HybridRetriever, llm: AnswerLLM):
        self.settings = settings
        self.db = db
        self.retriever = retriever
        self.llm = llm
        self._cache: OrderedDict[tuple, AnswerResult] = OrderedDict()
        self._cache_lock = threading.Lock()

    def ask(
        self,
        question: str,
        document_ids: list[int] | None = None,
        log: bool = True,
        progress: Progress | None = None,
    ) -> AnswerResult:
        """Answer a question; `progress`, if given, hears about each step as it starts."""
        start = time.perf_counter()
        normalized = normalize(question)
        language = question_language(normalized)
        doc_key = tuple(sorted(set(document_ids))) if document_ids else ()
        cache_key = (normalized, doc_key, self.db.index_version())

        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached:
                self._cache.move_to_end(cache_key)
        if cached:
            result = AnswerResult(
                **{**cached.__dict__, "cached": True, "latency_ms": int((time.perf_counter() - start) * 1000)}
            )
            if log:
                self._log(result, document_ids)
            return result

        timings: dict[str, int] = {}
        chunks = self.retriever.retrieve(normalized, list(doc_key) or None, timings=timings, progress=progress)
        if progress is not None:
            pages = list(dict.fromkeys((c.filename, c.page_no) for c in chunks))
            progress({"type": "sources", "sources": [{"filename": f, "page_no": p} for f, p in pages]})
        result = self._generate(question, normalized, language, chunks, timings, progress)
        result.latency_ms = int((time.perf_counter() - start) * 1000)
        timings["total"] = result.latency_ms
        result.timings = timings
        top = relevance(chunks, self.settings.reranker_enabled)
        logger.info(
            "ask timings (ms): %s; top relevance %s; found=%s",
            ", ".join(f"{k}={v}" for k, v in timings.items()),
            f"{top:.3f}" if top is not None else "-",
            result.found,
        )

        if result.note is None:  # don't cache refusals
            with self._cache_lock:
                self._cache[cache_key] = result
                while len(self._cache) > self.settings.answer_cache_size:
                    self._cache.popitem(last=False)
        if log:
            self._log(result, document_ids)
        return result

    def _not_found(
        self, question: str, language: str, chunks: list[RetrievedChunk], note: str | None = None
    ) -> AnswerResult:
        return AnswerResult(
            question=question,
            answer=NOT_FOUND[language],
            language=language,
            found=False,
            grounded=True,
            citations=[],
            retrieved=chunks,
            note=note,
        )

    def _generate(
        self,
        question: str,
        normalized: str,
        language: str,
        chunks: list[RetrievedChunk],
        timings: dict[str, int] | None = None,
        progress: Progress | None = None,
    ) -> AnswerResult:
        if not chunks:
            return self._not_found(question, language, chunks)
        min_score = self.settings.min_relevance_score
        top = relevance(chunks, self.settings.reranker_enabled)
        if min_score is not None and top is not None and top < min_score:
            return self._not_found(question, language, chunks)

        with timed(timings, "llm", progress):
            llm_answer = self.llm.answer(build_user_message(normalized, language, chunks))
        if llm_answer.refused:
            return self._not_found(
                question, language, chunks, note="The model declined to answer this question."
            )
        if not llm_answer.found or not llm_answer.answer:
            return self._not_found(question, language, chunks)

        citations = build_citations(llm_answer.citations, chunks)
        grounded = bool(citations) and all(c.quote_verified for c in citations)
        return AnswerResult(
            question=question,
            answer=llm_answer.answer,
            language=language,
            found=True,
            grounded=grounded,
            citations=citations,
            retrieved=chunks,
        )

    def _log(self, result: AnswerResult, document_ids: list[int] | None) -> None:
        self.db.log_query(
            result.question,
            document_ids,
            result.answer,
            result.found,
            [c.chunk_id for c in result.citations],
            result.latency_ms,
        )
