"""End to end through the HTTP API with fake models: upload -> index -> ask -> cite."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import get_services
from tests.conftest import ENGLISH_PARAGRAPH, make_pdf


@pytest.fixture
def client(services):
    app.dependency_overrides[get_services] = lambda: services
    # the lifespan hook uses get_services() directly
    import app.services as svc

    previous, svc._services = svc._services, services
    with TestClient(app) as c:
        yield c
    svc._services = previous
    app.dependency_overrides.clear()


def upload(client, data: bytes, name="policy.pdf"):
    return client.post("/documents", files={"file": (name, data, "application/pdf")})


def test_upload_index_ask_and_cite(client, services):
    other = "The canteen opens at 8 am and closes at 4 pm on working days. " * 3
    data = make_pdf([ENGLISH_PARAGRAPH, other, None])  # page 3 is a "scan"
    r = upload(client, data)
    assert r.status_code == 202, r.text
    doc_id = r.json()["document"]["id"]

    # TestClient runs background tasks before returning, so indexing is finished
    detail = client.get(f"/documents/{doc_id}").json()
    assert detail["status"] == "ready", detail["error"]
    assert detail["pages_done"] == 3
    methods = [p["method"] for p in detail["pages"]]
    assert methods == ["text", "text", "fake"]  # the OCR engine that read the page
    assert detail["pages"][2]["low_confidence"] is True
    assert services.ocr.calls == 1

    img = client.get(f"/documents/{doc_id}/pages/1/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"

    r = client.post("/ask", json={"question": "What is the monthly stipend for each student?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["found"] and body["language"] == "en"
    assert len(body["citations"]) == 1  # the unknown S99 citation was dropped
    cite = body["citations"][0]
    assert cite["filename"] == "policy.pdf" and cite["page_no"] == 1
    assert cite["quote_verified"] and body["grounded"]
    assert cite["image_url"] == f"/documents/{doc_id}/pages/1/image"

    # OCR'd Urdu page is searchable with an Urdu question
    r = client.post("/ask", json={"question": "وظیفہ کی ماہانہ رقم کتنی ہے؟"})
    body = r.json()
    assert body["language"] == "ur"
    assert body["citations"][0]["page_no"] == 3

    # repeated question is served from the cache
    again = client.post("/ask", json={"question": "What is the monthly stipend for each student?"}).json()
    assert again["cached"] is True


def test_not_found_and_document_filter(client, services):
    a = upload(client, make_pdf([ENGLISH_PARAGRAPH]), "a.pdf").json()["document"]["id"]
    b = upload(client, make_pdf(["Library hours are nine to five on weekdays. " * 4]), "b.pdf").json()[
        "document"
    ]["id"]

    r = client.post("/ask", json={"question": "library hours", "document_ids": [b]}).json()
    assert {c["document_id"] for c in r["citations"]} == {b}

    r = client.post("/ask", json={"question": "zzqx unrelated"}).json()
    assert r["found"] is False
    assert r["answer"] == "The answer was not found in the provided documents."
    assert a


def test_duplicate_invalid_and_delete(client, services):
    data = make_pdf([ENGLISH_PARAGRAPH])
    first = upload(client, data).json()
    dup = upload(client, data).json()
    assert dup["duplicate"] is True and dup["document"]["id"] == first["document"]["id"]

    assert upload(client, b"not a pdf", "x.pdf").status_code == 422
    assert upload(client, data, "x.docx").status_code == 415

    doc_id = first["document"]["id"]
    assert client.delete(f"/documents/{doc_id}").status_code == 204
    assert client.get(f"/documents/{doc_id}").status_code == 404
    assert client.get("/documents").json() == []
    assert services.vector_store.collection.count() == 0
    r = client.post("/ask", json={"question": "monthly stipend"}).json()
    assert r["found"] is False


def test_ask_with_no_documents_loads_no_models(client, services):
    r = client.post("/ask", json={"question": "آخری تاریخ کیا ہے؟"}).json()
    assert r["found"] is False and r["language"] == "ur" and r["note"]
    assert "_answers" not in services.__dict__  # retriever, embedder and LLM never built


def test_ask_stream_reports_steps_then_the_answer(client):
    upload(client, make_pdf([ENGLISH_PARAGRAPH]))
    r = client.post("/ask/stream", json={"question": "What is the monthly stipend for each student?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in r.text.splitlines()]
    steps = [e["step"] for e in events if e["type"] == "step"]
    assert steps == ["embed_query", "vector_search", "bm25", "fetch_chunks", "rerank", "llm"]
    sources = next(e for e in events if e["type"] == "sources")["sources"]
    assert sources[0] == {"filename": "policy.pdf", "page_no": 1}
    assert events[-1]["type"] == "result"
    assert events[-1]["result"]["found"] and events[-1]["result"]["citations"]


def test_reprocess_and_health(client):
    doc_id = upload(client, make_pdf([ENGLISH_PARAGRAPH])).json()["document"]["id"]
    r = client.post(f"/documents/{doc_id}/reprocess")
    assert r.status_code == 202
    assert client.get(f"/documents/{doc_id}").json()["status"] == "ready"
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["ready"] == 1
