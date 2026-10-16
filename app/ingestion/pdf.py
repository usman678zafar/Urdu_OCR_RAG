"""PDF validation, text extraction and page rendering with PyMuPDF."""

import hashlib
import io

import pymupdf
from PIL import Image


class InvalidPDF(ValueError):
    pass


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def open_pdf(data: bytes, max_pages: int) -> pymupdf.Document:
    """Open and validate PDF bytes; raise InvalidPDF with a user-facing message."""
    if not data.startswith(b"%PDF-"):
        raise InvalidPDF("File is not a PDF.")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # PyMuPDF raises several error types for corrupt files
        raise InvalidPDF(f"PDF could not be read: {e}") from e
    if doc.needs_pass and not doc.authenticate(""):
        raise InvalidPDF("PDF is password-protected.")
    if doc.page_count == 0:
        raise InvalidPDF("PDF has no pages.")
    if doc.page_count > max_pages:
        raise InvalidPDF(f"PDF has {doc.page_count} pages; the limit is {max_pages}.")
    return doc


def page_text(page: pymupdf.Page) -> str:
    return page.get_text("text", sort=True)


def image_coverage(page: pymupdf.Page) -> float:
    """Share of the page area covered by embedded images (capped at 1)."""
    area = abs(page.rect)
    if not area:
        return 0.0
    covered = 0.0
    for info in page.get_image_info():
        bbox = pymupdf.Rect(info["bbox"]) & page.rect
        covered += abs(bbox)
    return min(covered / area, 1.0)


def render_page(page: pymupdf.Page, dpi: int) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
