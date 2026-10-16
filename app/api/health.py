"""Service check."""

from fastapi import APIRouter, Depends

from app.services import Services, get_services

router = APIRouter(tags=["health"])


@router.get("/health")
def health(services: Services = Depends(get_services)):
    docs = services.db.list_documents()
    return {
        "status": "ok",
        "documents": len(docs),
        "ready": sum(1 for d in docs if d["status"] == "ready"),
        "embedding_model": services.settings.embedding_model,
        "llm_model": services.settings.llm_model,
        "ocr_engine": services.settings.ocr_engine,
    }
