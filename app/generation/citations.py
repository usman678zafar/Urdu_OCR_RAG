"""Check the model's citations against the chunks it was actually given."""

from dataclasses import dataclass

from rapidfuzz import fuzz

from app.generation.prompts import source_id
from app.processing.normalize import normalize
from app.retrieval.hybrid import RetrievedChunk

QUOTE_MATCH_THRESHOLD = 85


@dataclass
class Citation:
    chunk_id: int
    document_id: int
    filename: str
    page_no: int
    quote: str
    passage: str
    quote_verified: bool


def quote_in_passage(quote: str, passage: str) -> bool:
    q, p = normalize(quote).lower(), normalize(passage).lower()
    if not q:
        return False
    return q in p or fuzz.partial_ratio(q, p) >= QUOTE_MATCH_THRESHOLD


def build_citations(raw: list[dict], chunks: list[RetrievedChunk]) -> list[Citation]:
    """Map source ids to chunks, drop unknown ids and duplicates, verify each quote."""
    by_id = {source_id(i): c for i, c in enumerate(chunks)}
    out: list[Citation] = []
    seen: set[int] = set()
    for item in raw:
        chunk = by_id.get(str(item.get("source_id", "")).strip())
        if chunk is None or chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        quote = str(item.get("quote", "")).strip()
        out.append(
            Citation(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                filename=chunk.filename,
                page_no=chunk.page_no,
                quote=quote,
                passage=chunk.text,
                quote_verified=quote_in_passage(quote, chunk.text),
            )
        )
    return out
