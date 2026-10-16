"""Hybrid retrieval: dense + BM25 candidates fused with reciprocal rank fusion,
then reordered by the cross-encoder reranker."""

from dataclasses import dataclass

from app.config import Settings
from app.db.database import Database
from app.retrieval.bm25 import BM25Index
from app.retrieval.embeddings import Embedder
from app.retrieval.reranker import Reranker
from app.retrieval.vector_store import VectorStore

RRF_K = 60


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    filename: str
    page_no: int
    text: str
    score: float  # reranker score, or fused RRF score when reranking is off
    dense_rank: int | None
    bm25_rank: int | None


def rrf_fuse(*rankings: list[int]) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class HybridRetriever:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        embedder: Embedder,
        store: VectorStore,
        bm25: BM25Index,
        reranker: Reranker | None,
    ):
        self.settings = settings
        self.db = db
        self.embedder = embedder
        self.store = store
        self.bm25 = bm25
        self.reranker = reranker

    def retrieve(
        self, normalized_query: str, document_ids: list[int] | None = None, top_k: int | None = None
    ) -> list[RetrievedChunk]:
        s = self.settings
        top_k = top_k or s.final_top_k

        dense = [
            cid
            for cid, _ in self.store.search(
                self.embedder.embed_query(normalized_query), s.dense_top_k, document_ids
            )
        ]
        keyword = [cid for cid, _ in self.bm25.search(normalized_query, s.bm25_top_k, document_ids)]
        fused = rrf_fuse(dense, keyword)[: s.candidate_k]
        if not fused:
            return []

        rows = self.db.get_chunks([cid for cid, _ in fused])
        # skip chunks whose document was deleted or is mid-reprocessing
        candidates = [
            (cid, score) for cid, score in fused if cid in rows and rows[cid]["doc_status"] == "ready"
        ]
        if not candidates:
            return []
        dense_rank = {cid: i for i, cid in enumerate(dense)}
        bm25_rank = {cid: i for i, cid in enumerate(keyword)}

        if self.reranker is not None:
            scores = self.reranker.score(normalized_query, [rows[cid]["text"] for cid, _ in candidates])
            candidates = sorted(zip([c for c, _ in candidates], scores), key=lambda x: x[1], reverse=True)

        return [
            RetrievedChunk(
                chunk_id=cid,
                document_id=rows[cid]["document_id"],
                filename=rows[cid]["filename"],
                page_no=rows[cid]["page_no"],
                text=rows[cid]["text"],
                score=float(score),
                dense_rank=dense_rank.get(cid),
                bm25_rank=bm25_rank.get(cid),
            )
            for cid, score in candidates[:top_k]
        ]
