"""Question answering endpoints: /ask returns the answer, /ask/stream also reports progress."""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.api.documents import page_image_url
from app.api.schemas import AskIn, AskOut, CitationOut
from app.generation.llm import LLMError
from app.generation.prompts import NOT_FOUND
from app.processing.language import question_language
from app.retrieval.hybrid import Progress
from app.services import Services, get_services

router = APIRouter(tags=["ask"])
log = logging.getLogger(__name__)


async def answer(body: AskIn, services: Services, progress: Progress | None = None) -> AskOut:
    if services.db.count_ready(body.document_ids) == 0:
        # answer before loading any model, so an empty system starts instantly
        language = question_language(body.question)
        return AskOut(
            answer=NOT_FOUND[language],
            language=language,
            found=False,
            grounded=True,
            citations=[],
            latency_ms=0,
            cached=False,
            note="No ready documents to search. Upload a PDF or wait for processing to finish.",
        )
    try:
        # retrieval and the LLM call block, so keep them off the event loop
        result = await run_in_threadpool(
            services.answers.ask, body.question, body.document_ids, progress=progress
        )
    except LLMError as e:
        raise HTTPException(502, str(e)) from e
    return AskOut(
        answer=result.answer,
        language=result.language,
        found=result.found,
        grounded=result.grounded,
        citations=[
            CitationOut(
                document_id=c.document_id,
                filename=c.filename,
                page_no=c.page_no,
                quote=c.quote,
                passage=c.passage,
                quote_verified=c.quote_verified,
                image_url=page_image_url(c.document_id, c.page_no),
            )
            for c in result.citations
        ],
        latency_ms=result.latency_ms,
        cached=result.cached,
        note=result.note,
        timings=result.timings if services.settings.debug_timings else None,
    )


@router.post("/ask", response_model=AskOut)
async def ask(body: AskIn, services: Services = Depends(get_services)):
    return await answer(body, services)


@router.post("/ask/stream")
async def ask_stream(body: AskIn, services: Services = Depends(get_services)):
    """Newline-delimited JSON events: {"type": "step"|"candidates"|"sources", ...} while
    working, then one {"type": "result", "result": AskOut} or {"type": "error", "detail": str}."""
    loop = asyncio.get_running_loop()
    events: asyncio.Queue[dict | None] = asyncio.Queue()

    def emit(event: dict | None) -> None:  # called from the worker thread
        loop.call_soon_threadsafe(events.put_nowait, event)

    async def run() -> None:
        try:
            out = await answer(body, services, emit)
            emit({"type": "result", "result": out.model_dump()})
        except HTTPException as e:
            emit({"type": "error", "detail": f"{e.status_code}: {e.detail}"})
        except Exception as e:
            log.exception("Answering failed")
            emit({"type": "error", "detail": f"{type(e).__name__}: {e}"})
        finally:
            emit(None)

    task = asyncio.create_task(run())

    async def stream():
        while (event := await events.get()) is not None:
            yield json.dumps(event, ensure_ascii=False) + "\n"
        await task

    # no-transform / X-Accel-Buffering stop proxies from holding events back
    headers = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}
    return StreamingResponse(stream(), media_type="application/x-ndjson", headers=headers)
