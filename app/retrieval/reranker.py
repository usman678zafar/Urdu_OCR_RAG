"""Cross-encoder reranker (bge-reranker-v2-m3): scores each (question, chunk) pair."""

from typing import Protocol

from app.config import Settings


class Reranker(Protocol):
    def score(self, query: str, passages: list[str]) -> list[float]: ...


class CrossEncoderReranker:
    def __init__(self, settings: Settings):
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(settings.reranker_model, device=settings.embedding_device, max_length=512)

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        scores = self.model.predict([(query, p) for p in passages], show_progress_bar=False)
        return [float(s) for s in scores]
