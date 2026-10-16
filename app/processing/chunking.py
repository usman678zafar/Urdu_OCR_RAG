"""Split page text into overlapping chunks that never cross a page boundary.

Keeping each chunk on one page is what lets every answer cite an exact page.
"""

import re
from dataclasses import dataclass

from app.processing.language import Language, detect_language

# Split after Urdu/English sentence enders, keeping the punctuation with the sentence
_SENTENCE_END = re.compile(r"(?<=[۔؟!?.])\s+|\n+")


@dataclass
class Chunk:
    page_no: int
    chunk_index: int
    text: str
    language: Language


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s and s.strip()]


def _split_long(sentence: str, size: int) -> list[str]:
    """Break a sentence longer than `size` at word boundaries."""
    words, parts, current = sentence.split(), [], ""
    for w in words:
        if current and len(current) + 1 + len(w) > size:
            parts.append(current)
            current = w
        else:
            current = f"{current} {w}" if current else w
    if current:
        parts.append(current)
    return parts


def chunk_page(text: str, page_no: int, size: int, overlap: int, start_index: int = 0) -> list[Chunk]:
    pieces: list[str] = []
    for s in _sentences(text):
        pieces.extend(_split_long(s, size) if len(s) > size else [s])

    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for piece in pieces:
        if current and length + 1 + len(piece) > size:
            chunks.append(" ".join(current))
            # carry trailing sentences forward as overlap
            carry, carry_len = [], 0
            for prev in reversed(current):
                if carry_len + len(prev) > overlap:
                    break
                carry.insert(0, prev)
                carry_len += len(prev) + 1
            current, length = carry, carry_len
        current.append(piece)
        length += len(piece) + 1
    if current:
        chunks.append(" ".join(current))

    return [
        Chunk(page_no=page_no, chunk_index=start_index + i, text=c, language=detect_language(c))
        for i, c in enumerate(chunks)
    ]


def chunk_pages(pages: list[tuple[int, str]], size: int, overlap: int) -> list[Chunk]:
    """Chunk (page_no, text) pairs; chunk_index runs across the whole document."""
    out: list[Chunk] = []
    for page_no, text in pages:
        out.extend(chunk_page(text, page_no, size, overlap, start_index=len(out)))
    return out
