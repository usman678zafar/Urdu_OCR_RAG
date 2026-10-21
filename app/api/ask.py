"""Question answering endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.api.documents import page_image_url
from app.api.schemas import AskIn, AskOut, CitationOut
from app.generation.llm import LLMError
from app.generation.prompts import NOT_FOUND
from app.processing.language import question_language
from app.services import Services, get_services

router = APIRouter(tags=["ask"])


@router.post("/ask", response_model=AskOut)
async def ask(body: AskIn, services: Services = Depends(get_services)):
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
        result = await run_in_threadpool(services.answers.ask, body.question, body.document_ids)
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
