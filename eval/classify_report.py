"""Check the page classifier on the test documents (phase 1 gate: right on 95% of pages).

    python -m eval.classify_report

Writes every page's decision and stats to eval/results/classifier_report.csv. If
eval/page_labels.csv exists (columns: filename,page,expected with expected = text or ocr),
it also prints accuracy and every page where the classifier disagrees with your label.
"""

import csv
import sys
from pathlib import Path

import pymupdf

from app.config import Settings
from app.ingestion import pdf
from app.ingestion.classifier import classify_text

EVAL_DIR = Path(__file__).parent
GATE = 0.95


def main() -> None:
    # Windows consoles default to cp1252, which cannot print Urdu
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    settings = Settings()
    rows = []
    for path in sorted((EVAL_DIR / "documents").glob("*.pdf")):
        with pymupdf.open(path) as doc:
            for i, page in enumerate(doc):
                d = classify_text(pdf.page_text(page), pdf.image_coverage(page), settings)
                rows.append(
                    {
                        "filename": path.name,
                        "page": i + 1,
                        "method": d.method,
                        "reason": d.reason,
                        **d.to_dict()["stats"],
                    }
                )
    if not rows:
        print("No PDFs in eval/documents.")
        return

    out = EVAL_DIR / "results" / "classifier_report.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    by_method = {m: sum(1 for r in rows if r["method"] == m) for m in ("text", "ocr")}
    print(f"{len(rows)} pages: {by_method['text']} text, {by_method['ocr']} ocr -> {out}")

    labels_path = EVAL_DIR / "page_labels.csv"
    if not labels_path.exists():
        print("Add eval/page_labels.csv (filename,page,expected) to measure accuracy.")
        return
    with labels_path.open(encoding="utf-8") as f:
        labels = {(r["filename"], int(r["page"])): r["expected"].strip() for r in csv.DictReader(f)}
    checked = [r for r in rows if (r["filename"], r["page"]) in labels]
    wrong = [r for r in checked if labels[(r["filename"], r["page"])] != r["method"]]
    if not checked:
        print("No labelled pages matched the documents.")
        return
    accuracy = 1 - len(wrong) / len(checked)
    print(
        f"Accuracy on {len(checked)} labelled pages: {accuracy:.1%} "
        f"(gate {GATE:.0%}: {'PASS' if accuracy >= GATE else 'below'})"
    )
    for r in wrong:
        print(
            f"  {r['filename']} p.{r['page']}: got {r['method']} ({r['reason']}), "
            f"expected {labels[(r['filename'], r['page'])]}"
        )


if __name__ == "__main__":
    main()
