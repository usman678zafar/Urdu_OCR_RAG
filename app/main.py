"""FastAPI application. Run with: uvicorn app.main:app --reload"""

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import ask, documents, health
from app.services import get_services

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def _preload(services) -> None:
    """Build the embedder and reranker now instead of on the first question. Runs in a
    thread so the server answers at once; a question that arrives early waits for it."""
    start = time.perf_counter()
    try:
        services.embedder.embed_query("warm up")
        if services.reranker is not None:
            services.reranker.score("warm up", ["warm up"])
        log.info("Models preloaded in %.1fs", time.perf_counter() - start)
    except Exception:
        log.exception("Preloading models failed; they will load on the first question")


@asynccontextmanager
async def lifespan(app: FastAPI):
    services = get_services()
    interrupted = services.db.fail_interrupted()
    if interrupted:
        log.warning("Marked %d interrupted document(s) as failed: %s", len(interrupted), interrupted)
    if services.settings.preload_models:
        threading.Thread(target=_preload, args=(services,), name="preload", daemon=True).start()
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
