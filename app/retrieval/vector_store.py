"""ChromaDB vector store. One collection per embedding model, so switching
models for a comparison never mixes vectors of different sizes."""

import re
from pathlib import Path

import chromadb


class VectorStore:
    def __init__(self, path: Path, embedding_model: str):
        self.client = chromadb.PersistentClient(path=str(path))
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", embedding_model).strip("-").lower()
        self.collection = self.client.get_or_create_collection(
            name=f"chunks-{slug}"[:63], metadata={"hnsw:space": "cosine"}
        )

    def add(
        self, chunk_ids: list[int], vectors: list[list[float]], document_id: int, page_nos: list[int]
    ) -> None:
        if not chunk_ids:
            return
        self.collection.add(
            ids=[f"c{i}" for i in chunk_ids],
            embeddings=vectors,
            metadatas=[{"document_id": document_id, "page_no": p} for p in page_nos],
        )

    def search(
        self, vector: list[float], k: int, document_ids: list[int] | None = None
    ) -> list[tuple[int, float]]:
        """Return (chunk_id, similarity) pairs, best first."""
        if self.collection.count() == 0:
            return []
        where = None
        if document_ids:
            where = {"document_id": {"$in": list(document_ids)}}
        result = self.collection.query(
            query_embeddings=[vector], n_results=min(k, self.collection.count()), where=where
        )
        ids = result["ids"][0]
        distances = result["distances"][0]
        return [(int(i[1:]), 1.0 - d) for i, d in zip(ids, distances)]

    def has_document(self, document_id: int) -> bool:
        return bool(self.collection.get(where={"document_id": document_id}, limit=1)["ids"])

    def delete_document(self, document_id: int) -> None:
        self.collection.delete(where={"document_id": document_id})
