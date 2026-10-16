"""Document upload, status, page images and deletion."""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.schemas import DocumentDetailOut, DocumentOut, PageOut, UploadOut
from app.ingestion import pdf
from app.services import Services, get_services

router = APIRouter(prefix="/documents", tags=["documents"])

BUSY = ("uploaded", "extracting", "indexing")


def page_image_url(doc_id: int, page_no: int) -> str:
    return f"/documents/{doc_id}/pages/{page_no}/image"


def _get_or_404(services: Services, doc_id: int) -> dict:
    doc = services.db.get_document(doc_id)
    if doc is None:
        raise HTTPException(404, "Document not found.")
    return doc


@router.post("", response_model=UploadOut, status_code=202)
async def upload_document(
    file: UploadFile, background: BackgroundTasks, services: Services = Depends(get_services)
):
    s = services.settings
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(415, "Only PDF files are accepted.")
    data = await file.read(s.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {s.max_upload_mb} MB.")

    sha = pdf.sha256_of(data)
    existing = services.db.get_document_by_sha(sha)
    if existing:
        return UploadOut(document=DocumentOut(**existing), duplicate=True)

    try:
        with pdf.open_pdf(data, s.max_pages) as doc:
            page_count = doc.page_count
    except pdf.InvalidPDF as e:
        raise HTTPException(422, str(e)) from e

    services.pipeline.original_path(sha).write_bytes(data)
    doc_id = services.db.create_document(Path(file.filename).name, sha, page_count)
    background.add_task(services.pipeline.process, doc_id)
    return UploadOut(document=DocumentOut(**services.db.get_document(doc_id)), duplicate=False)


@router.get("", response_model=list[DocumentOut])
def list_documents(services: Services = Depends(get_services)):
    return [DocumentOut(**d) for d in services.db.list_documents()]


@router.get("/{doc_id}", response_model=DocumentDetailOut)
def get_document(doc_id: int, services: Services = Depends(get_services)):
    doc = _get_or_404(services, doc_id)
    threshold = services.settings.low_confidence_threshold
    pages = [
        PageOut(
            page_no=p["page_no"],
            method=p["method"],
            reason=p["reason"],
            ocr_confidence=p["ocr_confidence"],
            low_confidence=p["ocr_confidence"] is not None and p["ocr_confidence"] < threshold,
            text_chars=len(p["text"] or p["raw_text"]),
            image_url=page_image_url(doc_id, p["page_no"]),
        )
        for p in services.db.get_pages(doc_id)
    ]
    return DocumentDetailOut(**doc, pages=pages)


@router.get("/{doc_id}/pages/{page_no}/image")
def page_image(doc_id: int, page_no: int, services: Services = Depends(get_services)):
    page = services.db.get_page(doc_id, page_no)
    if page is None or not page["image_path"] or not Path(page["image_path"]).exists():
        raise HTTPException(404, "Page image not found.")
    return FileResponse(page["image_path"], media_type="image/png")


@router.post("/{doc_id}/reprocess", response_model=DocumentOut, status_code=202)
def reprocess_document(doc_id: int, background: BackgroundTasks, services: Services = Depends(get_services)):
    doc = _get_or_404(services, doc_id)
    if doc["status"] in BUSY[1:]:
        raise HTTPException(409, "Document is already being processed.")
    services.db.set_status(doc_id, "uploaded")
    background.add_task(services.pipeline.process, doc_id)
    return DocumentOut(**services.db.get_document(doc_id))


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: int, services: Services = Depends(get_services)):
    doc = _get_or_404(services, doc_id)
    if doc["status"] in BUSY[1:]:
        raise HTTPException(409, "Document is being processed; delete it once it is ready or failed.")
    services.pipeline.delete(doc_id)
