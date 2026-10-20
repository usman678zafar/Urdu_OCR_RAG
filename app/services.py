"""Lazily built shared services. Heavy models load on first use, and tests can
replace any of them with a fake by assigning the attribute."""

import threading
from functools import cached_property

from app.config import Settings, get_settings
from app.db.database import Database
from app.generation.answer import AnswerService
from app.generation.llm import AnswerLLM, ProviderLLM
from app.ingestion.ocr import OCREngine, make_ocr_engine
from app.ingestion.pipeline import IndexingPipeline
from app.retrieval.bm25 import BM25Index
from app.retrieval.embeddings import Embedder, SentenceTransformerEmbedder
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.reranker import CrossEncoderReranker, Reranker
from app.retrieval.vector_store import VectorStore


class Services:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.settings.ensure_dirs()
        self._lock = threading.RLock()

    def _locked(self, name: str, build):
        # cached_property is not thread-safe; background indexing and /ask can race
        with self._lock:
            if name not in self.__dict__:
                self.__dict__[name] = build()
            return self.__dict__[name]

    @cached_property
    def db(self) -> Database:
        return Database(self.settings.db_path)

    @property
    def embedder(self) -> Embedder:
        return self._locked("_embedder", lambda: SentenceTransformerEmbedder(self.settings))

    @embedder.setter
    def embedder(self, value: Embedder) -> None:
        self.__dict__["_embedder"] = value

    @property
    def reranker(self) -> Reranker | None:
        if not self.settings.reranker_enabled:
            return None
        return self._locked("_reranker", lambda: CrossEncoderReranker(self.settings))

    @reranker.setter
    def reranker(self, value: Reranker | None) -> None:
        self.__dict__["_reranker"] = value

    @property
    def vector_store(self) -> VectorStore:
        return self._locked(
            "_vector_store", lambda: VectorStore(self.settings.chroma_dir, self.settings.embedding_model)
        )

    @property
    def ocr(self) -> OCREngine:
        return self._locked("_ocr", lambda: make_ocr_engine(self.settings.ocr_engine, self.settings))

    @ocr.setter
    def ocr(self, value: OCREngine) -> None:
        self.__dict__["_ocr"] = value

    @property
    def llm(self) -> AnswerLLM:
        return self._locked("_llm", lambda: ProviderLLM(self.settings))

    @llm.setter
    def llm(self, value: AnswerLLM) -> None:
        self.__dict__["_llm"] = value

    @cached_property
    def bm25(self) -> BM25Index:
        return BM25Index(self.db)

    @cached_property
    def pipeline(self) -> IndexingPipeline:
        return IndexingPipeline(
            self.settings,
            self.db,
            embedder_factory=lambda: self.embedder,
            store_factory=lambda: self.vector_store,
            ocr_factory=lambda: self.ocr,
        )

    @property
    def answers(self) -> AnswerService:
        def build():
            retriever = HybridRetriever(
                self.settings, self.db, self.embedder, self.vector_store, self.bm25, self.reranker
            )
            # the LLM client is built on first question, so retrieval works without an API key
            return AnswerService(self.settings, self.db, retriever, _Lazy(self, "llm"))

        return self._locked("_answers", build)


class _Lazy:
    """Forwards calls to a Services attribute, resolved at call time (so overrides apply)."""

    def __init__(self, services: Services, name: str):
        self._services, self._name = services, name

    def __getattr__(self, item):
        return getattr(getattr(self._services, self._name), item)


_services: Services | None = None


def get_services() -> Services:
    global _services
    if _services is None:
        _services = Services()
    return _services


def set_services(services: Services) -> None:
    global _services
    _services = services
