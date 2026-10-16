"""Strip running headers, footers and page-number lines from a document's pages."""

import re
from collections import Counter

from app.processing.normalize import normalize

_DIGITS = re.compile(r"[0-9۰-۹٠-٩]+")
_PAGE_NUMBER_LINE = re.compile(
    r"^\W*(page|p\.|صفحہ|صفحه|ص)?\s*[0-9۰-۹٠-٩]+\s*((of|/|از|کا|من)\s*[0-9۰-۹٠-٩]+)?\W*$",
    re.IGNORECASE,
)
_EDGE_LINES = 2  # lines checked at the top and bottom of each page
_MIN_PAGES = 3  # repeated-line detection needs at least this many pages
_REPEAT_SHARE = 0.5  # a line on this share of pages counts as a header/footer


def _key(line: str) -> str:
    return _DIGITS.sub("#", normalize(line)).strip()


def _edge_keys(lines: list[str]) -> set[str]:
    non_empty = [line for line in lines if line.strip()]
    edges = non_empty[:_EDGE_LINES] + non_empty[-_EDGE_LINES:]
    return {_key(line) for line in edges if _key(line)}


def strip_headers_footers(pages: list[str]) -> list[str]:
    """Return page texts with repeated edge lines and bare page numbers removed."""
    split = [p.splitlines() for p in pages]

    repeated: set[str] = set()
    if len(pages) >= _MIN_PAGES:
        counts = Counter(k for lines in split for k in _edge_keys(lines))
        threshold = max(_MIN_PAGES, _REPEAT_SHARE * len(pages))
        repeated = {k for k, n in counts.items() if n >= threshold}

    cleaned = []
    for lines in split:
        non_empty_idx = [i for i, line in enumerate(lines) if line.strip()]
        edge_idx = set(non_empty_idx[:_EDGE_LINES] + non_empty_idx[-_EDGE_LINES:])
        kept = []
        for i, line in enumerate(lines):
            if i in edge_idx and (_key(line) in repeated or _PAGE_NUMBER_LINE.match(line.strip())):
                continue
            kept.append(line)
        cleaned.append("\n".join(kept))
    return cleaned
