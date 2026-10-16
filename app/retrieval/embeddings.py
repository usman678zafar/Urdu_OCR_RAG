"""Multilingual sentence embeddings (BGE-M3 by default; multilingual-e5 also supported)."""

from typing import Protocol

from app.config import Settings


class Embedder(Protocol):
    model_name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbedder:
    def __init__(self, settings: Settings):
        from sentence_transformers import SentenceTransformer

        self.model_name = settings.embedding_model
        self.model = SentenceTransformer(self.model_name, device=settings.embedding_device)
        self.model.max_seq_length = settings.embedding_max_seq_length
        self.batch_size = settings.embedding_batch_size
        # e5 models are trained with these prefixes; BGE-M3 needs none
        is_e5 = "e5" in self.model_name.lower()
        self.query_prefix = "query: " if is_e5 else ""
        self.doc_prefix = "passage: " if is_e5 else ""

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False
        )
        return vectors.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode([self.doc_prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self.query_prefix + text])[0]
