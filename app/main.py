"""FastAPI application. Run with: uvicorn app.main:app --reload"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import ask, documents, health
from app.services import get_services

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    interrupted = get_services().db.fail_interrupted()
    if interrupted:
        log.warning("Marked %d interrupted document(s) as failed: %s", len(interrupted), interrupted)
    yield


app = FastAPI(
    title="Urdu Document Q&A",
    description="Upload Urdu or English PDFs and ask questions; every answer cites its file and page.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(documents.router)
app.include_router(ask.router)
app.include_router(health.router)
