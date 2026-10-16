# Urdu Document Q&A (RAG) — Project Plan

Oct 16, 2026 · @Muhammad Usman

## About

The system lets a user upload Urdu or English PDFs, including scanned ones, and ask questions about them in either language. Every answer comes with the file and page it was taken from.

**Problem.** Offices in Pakistan hold large volumes of Urdu documents: applications, notices, policies, contracts and reports. Many are scanned, and much of the rest is exported from InPage with a broken text layer. Finding one fact means reading the documents by hand, and ordinary search tools fail on Nastaliq script.

**Target users**

- Administrative and welfare staff who review applications and case files
- Teams that work with policies, notices and contracts in Urdu
- Anyone who needs answers from a document archive without reading every file

**Goals**

- Read typed, scanned and InPage-exported Urdu PDFs reliably
- Answer Urdu and English questions from Urdu or English documents
- Show the exact source page and passage for every answer
- Say "not found" instead of guessing when the documents don't hold the answer
- Measure accuracy with a fixed test set, not by feel

**Non-goals for v1**

- Handwriting recognition
- Editing or generating documents
- Multi-organization accounts and billing
- A mobile app

## Features and v1 scope

Version 1 covers the full path from upload to cited answer for one user with a few hundred documents.

| Feature | What it does | In v1 |
| --- | --- | --- |
| PDF upload | Validates the file, removes duplicates by hash, stores the original | Yes |
| Page classifier | Decides per page: direct text extraction or OCR | Yes |
| Urdu OCR | Reads scanned and InPage-exported pages | Yes |
| Text cleanup | Normalizes Urdu characters, fixes spacing, strips headers and footers | Yes |
| Bilingual search | Finds Urdu passages for English questions and the reverse | Yes |
| Cited answers | Answer plus file, page number and source passage | Yes |
| Page preview | Shows the source page image next to the answer | Yes |
| Processing status | Uploaded, extracting, indexing, ready or failed | Yes |
| Document filters | Limit a question to chosen files | Yes |
| Chat history | Follow-up questions that use earlier turns | Later |
| User accounts and roles | Login, per-team document access | Later |
| Feedback buttons | Users mark answers right or wrong | Later |

## Architecture and data flow

The system runs as two pipelines that share one store: indexing runs once per document in the background, answering runs on every question.

&#91;embedded content: system architecture · indexing and answering pipelines\]

The page number is attached at chunking and carried through retrieval, so the cited answer can link back to the exact page image. Questions pass through the same Urdu normalizer as documents, otherwise letter variants make search miss.

## Tech stack

The stack is Python end to end, with free and open-source parts wherever accuracy allows. The two choices to test, not assume, are OCR and embeddings.

| Layer | First choice | Alternatives | Why |
| --- | --- | --- | --- |
| Language | Python 3.11+ | — | Best library support for PDF, OCR and ML |
| Backend API | FastAPI | Django REST | Async, fast, automatic API docs |
| Background jobs | FastAPI BackgroundTasks | Celery or RQ with Redis | Simple for v1; move to a queue when uploads grow |
| PDF text and rendering | PyMuPDF | pdfplumber | Text layer, page images and metadata in one library |
| Urdu OCR | Tesseract (urd model) as baseline | Google Document AI, a vision LLM | Compare all three on your own scans before choosing |
| Text normalization | Custom rules + `urduhack`-style normalizer | — | Unify letter variants (ی ي, ک ك, ہ ه) and spacing |
| Embeddings | BGE-M3 | multilingual-e5-large, OpenAI or Cohere multilingual | Strong multilingual retrieval, runs locally |
| Vector database | ChromaDB | Qdrant, PostgreSQL + pgvector | Zero setup for v1; pgvector once you need SQL alongside |
| Keyword search | BM25 (rank-bm25) | PostgreSQL full-text | Catches names, numbers and dates that vectors miss |
| Reranker | bge-reranker-v2-m3 | Cohere Rerank | Reorders retrieved chunks; often the biggest accuracy gain |
| LLM | Claude Sonnet 5.5 | GPT, an open model via Ollama | Good Urdu, follows "answer only from sources" rules well |
| Metadata database | SQLite | PostgreSQL | Documents, pages, jobs and status |
| File storage | Local disk | S3 or MinIO | Originals and page images |
| Frontend | Streamlit | React + Tailwind with RTL support | Streamlit for the prototype; React for the polished version |
| Evaluation | Custom test set + RAGAS | — | Retrieval and answer accuracy on fixed questions |
| Deployment | Docker + Docker Compose | — | One command to run on any server |

## Phases and milestones

The project takes about ten weeks part-time, in five phases. Each phase ends with a gate measured on the test set, so you only move on once the current layer works.

&#91;embedded content: project roadmap · 5 phases, 4 gates\]

Phase 2 deliberately ignores scanned pages: a working end-to-end system on easy PDFs gives a baseline that every later phase is measured against. If OCR in phase 3 misses its gate, spend another week there before tuning retrieval, since retrieval cannot fix bad text.

## Data model and API

Four tables hold everything; the page number travels from `pages` into every chunk so citations always work.

**Tables**

| Table | Key fields |
| --- | --- |
| documents | id, filename, sha256, page\_count, status, error, uploaded\_at |
| pages | id, document\_id, page\_no, method (text or ocr), text, image\_path, ocr\_confidence |
| chunks | id, document\_id, page\_no, chunk\_index, text, language, vector\_id |
| queries | id, question, answer, chunk\_ids\_used, latency\_ms, created\_at |

**API endpoints**

| Method | Path | Purpose |
| --- | --- | --- |
| POST | /documents | Upload a PDF; returns the document id at once |
| GET | /documents | List documents with their status |
| GET | /documents/{id} | One document's status and per-page methods |
| GET | /documents/{id}/pages/{n}/image | Page image for citation previews |
| DELETE | /documents/{id} | Remove a document, its chunks and vectors |
| POST | /ask | Question + optional document ids; returns answer and citations |
| GET | /health | Service check |

A `/ask` response returns the answer, its language and a list of citations, each with document id, filename, page number and the quoted passage.

## Evaluation and success metrics

Every change is judged against one fixed test set, so you know whether a new OCR engine or embedding model actually helped.

**Test set.** Collect 15–20 real documents covering typed, scanned, InPage-exported and mixed PDFs. Write 50 questions with known answers and the page each answer sits on: half in Urdu, half in English, plus about 10 whose answer is not in any document.

| Metric | What it measures | v1 target |
| --- | --- | --- |
| OCR character error rate | Mistakes per 100 characters on 10 hand-typed reference pages | Under 10% |
| Page classifier accuracy | Pages sent to the right method, checked by eye | Over 95% |
| Retrieval hit rate @5 | The correct page is among the top 5 chunks | Over 85% |
| Answer accuracy | Answer judged correct against the known answer | Over 80% |
| Citation accuracy | Cited page really contains the answer | Over 90% |
| Not-found accuracy | Says "not found" for the unanswerable questions | Over 90% |
| Response time | Question to answer | Under 8 seconds |

The targets are starting points to adjust after the first baseline run. Keep a results log per experiment, for example "BGE-M3 vs multilingual-e5 on Urdu questions"; this comparison is the most valuable portfolio material in the project.

## Risks and mitigations

The biggest risk is poor OCR on Nastaliq scans, because every later step inherits its errors.

| Risk | Effect | Mitigation |
| --- | --- | --- |
| Weak Urdu OCR | Wrong or missing text, so wrong answers | Benchmark three engines early; store OCR confidence and flag low-confidence pages |
| Broken InPage text layers | Text looks fine but extracts as gibberish | Urdu-character ratio check in the page classifier; send failures to OCR |
| Letter-variant mismatches | Same word stored two ways, so search misses it | Normalize ی ي, ک ك, ہ ه and spacing before chunking and before embedding questions |
| Poor cross-language retrieval | English questions miss Urdu passages | Hybrid search + reranker; test two embedding models |
| LLM invents answers | Confident but false answers | Strict "sources only" prompt, a not-found path, citation check against retrieved chunks |
| Wrong right-to-left display | Mixed Urdu and English renders out of order | `dir="auto"` per paragraph, an Urdu web font such as Noto Nastaliq Urdu |
| Sensitive documents | Personal data in welfare files reaches outside services | Local OCR and embeddings where possible; review what is sent to the LLM; access control before any shared deployment |
| Slow processing of large scans | Users wait minutes for a document | Background jobs, per-page progress, cache page images |
| API costs | Bills grow with usage | Cache answers to repeated questions; run embeddings locally |

## Folder structure and next steps

The code splits into ingestion, retrieval and API modules so each can be tested and swapped on its own.

```
urdu-rag/
├── app/
│   ├── api/            # FastAPI routes: documents, ask, health
│   ├── ingestion/      # upload, page classifier, extraction, OCR, cleanup
│   ├── processing/     # Urdu normalization, chunking
│   ├── retrieval/      # embeddings, vector store, BM25, reranker
│   ├── generation/     # prompts, LLM client, citation builder
│   ├── db/             # SQLite models and queries
│   └── config.py
├── ui/                 # Streamlit app (later: React)
├── eval/
│   ├── documents/      # test PDFs
│   ├── questions.jsonl # questions, answers, pages
│   └── run_eval.py
├── storage/            # originals, page images, vector data
├── tests/
├── docker-compose.yml
└── README.md
```

**Next steps**

- [ ] Collect 15–20 real documents of each type from work
- [ ] Write the first 20 test questions with answers and page numbers
- [ ] Set up the repository and folder structure
- [ ] Build and check the page classifier on the collected documents
- [ ] Run the three-engine OCR comparison on 10 scanned pages
