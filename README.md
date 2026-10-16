# Urdu Document Q&A (RAG)

Upload Urdu or English PDFs, including scanned and InPage-exported ones, and ask questions in either language. Every answer comes with the file, page and passage it was taken from, and the system says "not found" instead of guessing.

The full plan is in [Project Plan/](Project%20Plan/).

## How it works

Two pipelines share one store. Indexing runs once per document in the background; answering runs on every question.

```
Indexing   Upload ─► Classify pages ─► Extract or OCR ─► Clean + normalize ─► Chunk + embed
           (hash,     (text layer or     (PyMuPDF /        (headers/footers,     (per page,
            dedupe)    OCR, per page)     Tesseract)        ی ي ک ك ہ ه, digits)  BGE-M3)
                                              │
Storage    SQLite (documents, pages, chunks, queries) · ChromaDB vectors · page images on disk
                                              │
Answering  Question ─► Normalize ─► Hybrid retrieve ─► Rerank ─► Claude, sources only ─► Citation check
                                    (vectors + BM25,   (bge-reranker,  (structured JSON)   (quote must be
                                     RRF, top 20)       top 6)                               in its chunk)
```

Every chunk stays on one page, so each citation points at an exact page image.

| Module | What it does |
| --- | --- |
| [app/ingestion/classifier.py](app/ingestion/classifier.py) | Per page: trust the text layer, or OCR. Catches empty pages, private-use glyphs, Latin-1 mojibake, broken ligature mappings, letters split apart, reversed or garbled words (no common Urdu/English words), and scans with a small typed header |
| [app/ingestion/ocr.py](app/ingestion/ocr.py) | Three engines behind one interface: Tesseract (`urd+eng`), Claude vision, Google Document AI |
| [app/processing/bidi.py](app/processing/bidi.py) | Repairs Urdu lines extracted in visual (reversed) word order, a common PDF text-layer fault, by checking frequent Urdu word pairs in both directions |
| [app/processing/normalize.py](app/processing/normalize.py) | NFKC (presentation forms → letters), letter variants, Urdu/Arabic digits → ASCII, diacritics, tatweel, spacing. Used for documents **and** questions |
| [app/processing/cleanup.py](app/processing/cleanup.py) | Removes running headers/footers and page-number lines |
| [app/processing/chunking.py](app/processing/chunking.py) | Sentence-aware chunks (`۔ ؟ ! . ?`) with overlap, never crossing a page |
| [app/retrieval/](app/retrieval/) | BGE-M3 embeddings, ChromaDB, BM25, reciprocal rank fusion, bge-reranker-v2-m3 |
| [app/generation/](app/generation/) | Sources-only prompt, Claude client with structured output, citation verification, answer cache |
| [app/api/](app/api/) | FastAPI routes |
| [ui/streamlit_app.py](ui/streamlit_app.py) | Prototype UI with right-to-left text, Noto Nastaliq Urdu and page previews |
| [eval/](eval/) | Test-set runner, OCR comparison, classifier report |

## Quick start with make

`make` lists every task. The common ones:

```bash
make setup      # .venv with Python 3.12, dependencies, .env from the example
make doctor     # checks Python env, API key, Tesseract + Urdu, Docker
make dev        # backend on :8000 and frontend on :8501 together (Ctrl+C stops both)
make backend    # or run them separately: FastAPI with auto-reload
make frontend   #                         Streamlit UI
make test
make lint       # ruff: format and fix (make lint-check only reports, for CI)
make eval LABEL=baseline
```

It works from PowerShell or Git Bash on Windows (it needs [GNU Make](https://community.chocolatey.org/packages/make) and Git for Windows) and on Linux and macOS. The manual steps are below.

## Setup (Windows, local)

1. **Python 3.12.** Some dependencies (torch, chromadb) lag behind the newest Python, so use 3.12:
   ```powershell
   py -3.12 -m venv .venv
   .venv\Scripts\activate
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   pip install -r requirements-dev.txt
   ```
2. **Tesseract with Urdu.** Install from the [UB Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki) and tick *Urdu* under additional languages, or drop `urd.traineddata` into `C:\Program Files\Tesseract-OCR\tessdata`. The [tessdata_best](https://github.com/tesseract-ocr/tessdata_best) model is slower but more accurate on Nastaliq. Check with `tesseract --list-langs`.
3. **Configuration.** Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` (and `TESSERACT_CMD` if Tesseract is not on PATH).
4. **Run:**
   ```powershell
   uvicorn app.main:app --reload          # API on http://localhost:8000, docs at /docs
   streamlit run ui/streamlit_app.py      # UI on http://localhost:8501
   ```

The first upload downloads BGE-M3 (~2.3 GB), and the first question downloads the reranker (~2.3 GB), into the Hugging Face cache. On a CPU, indexing takes a few seconds per text page; Tesseract OCR takes roughly 5–15 seconds per scanned page.

## Setup (Docker)

```bash
cp .env.example .env        # set ANTHROPIC_API_KEY
docker compose up --build   # API :8000, UI :8501
```

The image includes Tesseract with the Urdu model. Models are cached in a named volume, and data lives in `./storage`.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/documents` | Upload a PDF (multipart `file`); returns the document id at once, processing runs in the background |
| GET | `/documents` | List documents with status (`uploaded`, `extracting`, `indexing`, `ready`, `failed`) and page progress |
| GET | `/documents/{id}` | One document with per-page method, classifier reason, OCR confidence and a low-confidence flag |
| GET | `/documents/{id}/pages/{n}/image` | Page image for citation previews |
| POST | `/documents/{id}/reprocess` | Run indexing again (after changing OCR engine or classifier settings, or after a failure) |
| DELETE | `/documents/{id}` | Remove a document, its pages, chunks, vectors and files |
| POST | `/ask` | `{"question": "...", "document_ids": [1, 2]}` → answer, language, `found`, `grounded`, citations |
| GET | `/health` | Service check |

An `/ask` response looks like this:

```json
{
  "answer": "ہر مستحق طالب علم کو ماہانہ 12,000 روپے وظیفہ ملے گا۔",
  "language": "ur",
  "found": true,
  "grounded": true,
  "citations": [{
    "document_id": 3, "filename": "welfare_policy_2025.pdf", "page_no": 4,
    "quote": "each eligible student will receive a monthly stipend of Rs. 12,000",
    "passage": "…full chunk text…", "quote_verified": true,
    "image_url": "/documents/3/pages/4/image"
  }],
  "latency_ms": 4210, "cached": false, "note": null
}
```

`grounded` is false when a quote can't be matched to the chunk it cites. The UI shows a warning so the user checks the page.

## Evaluation

Each change is judged against one fixed test set. The scripts index `eval/documents` into a separate store (`eval/.storage`), so experiments never touch the app's data.

1. Put 15–20 real PDFs (typed, scanned, InPage-exported, mixed) in `eval/documents/`.
2. Copy `eval/questions.example.jsonl` to `eval/questions.jsonl` and write your questions. Aim for 50: half Urdu, half English, and about 10 with `"answerable": false`.
3. Run the gates:

| Phase gate | Command |
| --- | --- |
| Classifier right on 95% of pages | `python -m eval.classify_report` (label pages in `eval/page_labels.csv`, see the example) |
| Baseline scores recorded | `python -m eval.run_eval --label baseline` |
| OCR error rate under 10% | `python -m eval.ocr_compare render eval/documents/x.pdf 2 5`, type the reference `.txt` files, then `python -m eval.ocr_compare run --engines tesseract,claude,docai` |
| Answer accuracy over 80% | `python -m eval.run_eval --label <experiment>` |

Comparing models is cheap: retrieval-only runs skip the LLM, and switching embedding models re-embeds stored chunks without re-running OCR.

```bash
python -m eval.run_eval --label bge-m3 --retrieval-only
python -m eval.run_eval --label e5-large --retrieval-only --embedding-model intfloat/multilingual-e5-large
python -m eval.run_eval --label no-rerank --no-reranker
```

Every run appends a row to `eval/results/log.csv`, and writes per-question detail to a JSON file next to it. Answer accuracy is graded by Claude against your reference answer; retrieval hit@5, citation accuracy and not-found accuracy are computed directly.

## Configuration

All settings are in [app/config.py](app/config.py) and can be set in `.env`. The ones you will tune most:

| Setting | Default | Notes |
| --- | --- | --- |
| `OCR_ENGINE` | `tesseract` | `claude` and `docai` send page images to outside services |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | e5 models get their `query:`/`passage:` prefixes automatically |
| `RERANKER_ENABLED` | `true` | |
| `RERANK_MIN_SCORE` | unset | When set, low-scoring retrievals answer "not found" without calling the LLM |
| `FINAL_TOP_K` | `6` | Chunks sent to the LLM |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `150` | Characters |
| `LLM_MODEL` / `LLM_EFFORT` | `claude-sonnet-5-5` / `low` | Raise the effort if answer accuracy is short of the gate and latency allows |
| `LLM_FALLBACKS` | `true` | Server-side refusal fallback: if Claude declines a request, the API retries it on another model instead of failing |
| `LOW_CONFIDENCE_THRESHOLD` | `0.6` | OCR pages below this are flagged |

## Privacy

Tesseract and the embedding and reranking models run locally. Retrieved passages, never whole documents, are sent to the Anthropic API to write answers. Choosing `OCR_ENGINE=claude` or `docai` also sends page images out. Add access control before any shared deployment.

## Tests

```bash
pytest
```

The tests replace the embedder, reranker, OCR engine and LLM with fakes. They cover the full path, upload → classify → OCR → chunk → index → ask → cite → delete, without downloading models or calling an API.

## Roadmap

- **Phases 1–4 (built):** foundation, basic RAG, OCR and normalization, hybrid retrieval and reranking, not-found handling, citation check, and the evaluation tooling.
- **Phase 5:** React + Tailwind UI with RTL, then deployment polish and a README with measured results.
- **Later:** chat history, user accounts and roles, feedback buttons.
