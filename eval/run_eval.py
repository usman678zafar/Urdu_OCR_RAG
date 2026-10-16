"""Run the fixed test set and record scores for one experiment.

    python -m eval.run_eval --label baseline
    python -m eval.run_eval --label e5 --embedding-model intfloat/multilingual-e5-large --retrieval-only
    python -m eval.run_eval --label no-rerank --no-reranker

Documents in eval/documents are indexed into a separate store (eval/.storage by default),
so experiments never touch the app's own data. Each run writes a JSON file with every
question's outcome and appends one summary row to eval/results/log.csv.
"""

import argparse
import csv
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from app.config import Settings
from app.ingestion import pdf
from app.processing.normalize import normalize
from app.services import Services

EVAL_DIR = Path(__file__).parent
TARGETS = {
    "retrieval_hit_rate_at_5": 0.85,
    "answer_accuracy": 0.80,
    "citation_accuracy": 0.90,
    "not_found_accuracy": 0.90,
}
TARGET_LATENCY_MS = 8000

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"correct": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["correct", "reason"],
    "additionalProperties": False,
}
JUDGE_PROMPT = """\
Grade a question-answering system. Decide whether the system's answer gives the same \
information as the reference answer. The two may be in different languages (Urdu or English) \
and worded differently; that is fine. Mark it correct when the key facts (names, numbers, \
dates, amounts, yes/no) match the reference and nothing it adds contradicts it. Mark it \
incorrect when a key fact is missing or wrong.

Question: {question}
Reference answer: {reference}
System answer: {answer}"""


def load_questions(path: Path) -> list[dict]:
    questions = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip() and not line.lstrip().startswith("//"):
            try:
                questions.append(json.loads(line))
            except json.JSONDecodeError as e:
                sys.exit(f"{path}:{n}: invalid JSON: {e}")
    return questions


def ingest(services: Services, docs_dir: Path) -> dict[str, int]:
    """Index every PDF in docs_dir (skipping ones already ready); return filename -> doc id."""
    db, pipeline = services.db, services.pipeline
    ids = {}
    for path in sorted(docs_dir.glob("*.pdf")):
        data = path.read_bytes()
        sha = pdf.sha256_of(data)
        doc = db.get_document_by_sha(sha)
        if doc is None:
            with pdf.open_pdf(data, services.settings.max_pages) as d:
                page_count = d.page_count
            pipeline.original_path(sha).write_bytes(data)
            doc = {"id": db.create_document(path.name, sha, page_count), "status": "uploaded"}
        if doc["status"] != "ready":
            print(f"  indexing {path.name} ...", flush=True)
            pipeline.process(doc["id"])
            doc = db.get_document(doc["id"])
            if doc["status"] != "ready":
                print(f"  ! {path.name} failed: {doc['error']}")
        elif not services.vector_store.has_document(doc["id"]):
            print(f"  embedding {path.name} with {services.settings.embedding_model} ...", flush=True)
            pipeline.reembed(doc["id"])
        ids[path.name] = doc["id"]
    return ids


def judge(client, model: str, question: str, reference: str, answer: str) -> tuple[bool, str]:
    response = client.messages.create(
        model=model,
        max_tokens=4000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": JUDGE_PROMPT.format(question=question, reference=reference, answer=answer),
            }
        ],
    )
    if response.stop_reason == "refusal":
        return False, "judge declined"
    data = json.loads(next(b.text for b in response.content if b.type == "text"))
    return bool(data["correct"]), data["reason"]


def on_expected_page(filename: str, page_no: int, q: dict) -> bool:
    return filename == q.get("document") and page_no in q.get("pages", [])


def ratio(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def main() -> None:
    # Windows consoles default to cp1252, which cannot print Urdu
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", required=True, help="experiment name for the results log")
    ap.add_argument("--questions", type=Path, default=EVAL_DIR / "questions.jsonl")
    ap.add_argument("--documents", type=Path, default=EVAL_DIR / "documents")
    ap.add_argument("--storage", type=Path, default=EVAL_DIR / ".storage")
    ap.add_argument("--embedding-model")
    ap.add_argument("--no-reranker", action="store_true")
    ap.add_argument("--ocr-engine", choices=["tesseract", "claude", "docai"])
    ap.add_argument("--retrieval-only", action="store_true", help="skip the LLM; score retrieval only")
    ap.add_argument("--judge-model", default="claude-sonnet-5-5")
    ap.add_argument("--limit", type=int, help="only the first N questions")
    args = ap.parse_args()

    if not args.questions.exists():
        sys.exit(f"{args.questions} not found. Copy eval/questions.example.jsonl and fill it in.")
    questions = load_questions(args.questions)[: args.limit]

    overrides = {"storage_dir": args.storage}
    if args.embedding_model:
        overrides["embedding_model"] = args.embedding_model
    if args.no_reranker:
        overrides["reranker_enabled"] = False
    if args.ocr_engine:
        overrides["ocr_engine"] = args.ocr_engine
    settings = Settings(**overrides)
    services = Services(settings)

    print(f"Indexing documents from {args.documents} ...")
    doc_ids = ingest(services, args.documents)
    missing = {q["document"] for q in questions if q.get("answerable", True)} - set(doc_ids)
    if missing:
        print(f"Warning: questions refer to documents not in {args.documents}: {sorted(missing)}")

    judge_client = None
    if not args.retrieval_only:
        import anthropic

        judge_client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    rows = []
    for i, q in enumerate(questions, 1):
        answerable = q.get("answerable", True)
        start = time.perf_counter()
        if args.retrieval_only:
            retrieved = services.answers.retriever.retrieve(normalize(q["question"]))
            result = None
        else:
            result = services.answers.ask(q["question"], log=False)
            retrieved = result.retrieved
        latency = int((time.perf_counter() - start) * 1000)

        row = {
            "id": q.get("id", str(i)),
            "question": q["question"],
            "answerable": answerable,
            "latency_ms": latency,
            "top5": [
                {"file": c.filename, "page": c.page_no, "score": round(c.score, 4)} for c in retrieved[:5]
            ],
        }
        if answerable:
            row["retrieval_hit"] = any(on_expected_page(c.filename, c.page_no, q) for c in retrieved[:5])
        if result is not None:
            row.update(
                answer=result.answer,
                found=result.found,
                grounded=result.grounded,
                citations=[{"file": c.filename, "page": c.page_no} for c in result.citations],
            )
            if answerable:
                row["citation_hit"] = any(
                    on_expected_page(c.filename, c.page_no, q) for c in result.citations
                )
                if result.found:
                    row["correct"], row["judge_reason"] = judge(
                        judge_client, args.judge_model, q["question"], q["answer"], result.answer
                    )
                else:
                    row["correct"], row["judge_reason"] = False, "system said not found"
            else:
                row["correct"] = not result.found
        rows.append(row)
        mark = {True: "✓", False: "✗", None: "·"}[row.get("correct", row.get("retrieval_hit"))]
        print(f"[{i}/{len(questions)}] {mark} {q['question'][:70]}", flush=True)

    answerable_rows = [r for r in rows if r["answerable"]]
    unanswerable_rows = [r for r in rows if not r["answerable"]]
    latencies = [r["latency_ms"] for r in rows]
    summary = {
        "label": args.label,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "embedding_model": settings.embedding_model,
        "reranker": settings.reranker_model if settings.reranker_enabled else "none",
        "llm_model": "none" if args.retrieval_only else settings.llm_model,
        "llm_effort": settings.llm_effort,
        "ocr_engine": settings.ocr_engine,
        "questions": len(rows),
        "retrieval_hit_rate_at_5": ratio([r["retrieval_hit"] for r in answerable_rows]),
        "answer_accuracy": None if args.retrieval_only else ratio([r["correct"] for r in answerable_rows]),
        "citation_accuracy": None
        if args.retrieval_only
        else ratio([r["citation_hit"] for r in answerable_rows if r.get("found")]),
        "not_found_accuracy": None
        if args.retrieval_only
        else ratio([r["correct"] for r in unanswerable_rows]),
        "latency_ms_mean": int(statistics.mean(latencies)) if latencies else None,
        "latency_ms_p95": int(sorted(latencies)[int(0.95 * (len(latencies) - 1))]) if latencies else None,
    }

    results_dir = EVAL_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = results_dir / f"{stamp}-{args.label}.json"
    out.write_text(
        json.dumps({"summary": summary, "questions": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log_path = results_dir / "log.csv"
    new_log = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary))
        if new_log:
            writer.writeheader()
        writer.writerow(summary)

    print("\nResults")
    for key, target in TARGETS.items():
        value = summary[key]
        if value is not None:
            print(f"  {key:26} {value:6.1%}   target > {target:.0%}  {'PASS' if value > target else 'below'}")
    if summary["latency_ms_p95"] is not None:
        p95 = summary["latency_ms_p95"]
        verdict = "PASS" if p95 < TARGET_LATENCY_MS else "below"
        print(f"  {'latency p95':26} {p95 / 1000:5.1f}s   target < 8s   {verdict}")
    print(f"\nDetails: {out}\nLog:     {log_path}")


if __name__ == "__main__":
    main()
