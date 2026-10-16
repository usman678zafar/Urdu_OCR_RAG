"""BM25 keyword search over all ready chunks. Catches names, numbers and dates
that dense vectors miss. Rebuilt in memory whenever the index version changes."""

import threading

from rank_bm25 import BM25Okapi

from app.db.database import Database
from app.processing.normalize import tokenize


class BM25Index:
    def __init__(self, db: Database):
        self.db = db
        self._lock = threading.Lock()
        self._version = -1
        self._bm25: BM25Okapi | None = None
        self._chunk_ids: list[int] = []
        self._doc_ids: list[int] = []

    def _refresh(self) -> None:
        version = self.db.index_version()
        if version == self._version:
            return
        chunks = self.db.all_ready_chunks()
        self._chunk_ids = [c["id"] for c in chunks]
        self._doc_ids = [c["document_id"] for c in chunks]
        corpus = [tokenize(c["text"]) for c in chunks]
        self._bm25 = BM25Okapi(corpus) if corpus else None
        self._version = version

    def search(self, query: str, k: int, document_ids: list[int] | None = None) -> list[tuple[int, float]]:
        with self._lock:
            self._refresh()
            if self._bm25 is None:
                return []
            tokens = tokenize(query)
            if not tokens:
                return []
            scores = self._bm25.get_scores(tokens)
            allowed = set(document_ids) if document_ids else None
            ranked = sorted(
                (
                    (cid, float(s))
                    for cid, did, s in zip(self._chunk_ids, self._doc_ids, scores)
                    if s > 0 and (allowed is None or did in allowed)
                ),
                key=lambda x: x[1],
                reverse=True,
            )
            return ranked[:k]
