"""The answering pipeline: normalize -> hybrid retrieve -> rerank -> LLM -> citation check."""

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
from app.retrieval.hybrid import HybridRetriever, RetrievedChunk


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


class AnswerService:
    def __init__(self, settings: Settings, db: Database, retriever: HybridRetriever, llm: AnswerLLM):
        self.settings = settings
        self.db = db
        self.retriever = retriever
        self.llm = llm
        self._cache: OrderedDict[tuple, AnswerResult] = OrderedDict()
        self._cache_lock = threading.Lock()

    def ask(self, question: str, document_ids: list[int] | None = None, log: bool = True) -> AnswerResult:
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

        chunks = self.retriever.retrieve(normalized, list(doc_key) or None)
        result = self._generate(question, normalized, language, chunks)
        result.latency_ms = int((time.perf_counter() - start) * 1000)

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
        self, question: str, normalized: str, language: str, chunks: list[RetrievedChunk]
    ) -> AnswerResult:
        if not chunks:
            return self._not_found(question, language, chunks)
        min_score = self.settings.rerank_min_score
        if min_score is not None and self.settings.reranker_enabled and chunks[0].score < min_score:
            return self._not_found(question, language, chunks)

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
