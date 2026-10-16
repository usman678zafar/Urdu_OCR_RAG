"""Compare OCR engines by character error rate on hand-typed reference pages.

1. Render the scanned pages you want to test:
       python -m eval.ocr_compare render eval/documents/notice.pdf 3
   This writes eval/ocr_pages/notice_p3.png.
2. Type the page's exact text into eval/ocr_pages/notice_p3.txt (UTF-8).
3. Run the comparison:
       python -m eval.ocr_compare run --engines tesseract,claude,docai

CER = edit distance / reference length, after both sides pass through the same
Urdu normalizer and whitespace is collapsed. Results go to eval/results/.
"""

import argparse
import csv
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pymupdf
from PIL import Image
from rapidfuzz.distance import Levenshtein

from app.config import Settings
from app.ingestion import pdf
from app.ingestion.ocr import make_ocr_engine
from app.processing.normalize import normalize

EVAL_DIR = Path(__file__).parent
PAGES_DIR = EVAL_DIR / "ocr_pages"
CER_TARGET = 0.10


def canonical(text: str) -> str:
    return re.sub(r"\s+", " ", normalize(text)).strip()


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = canonical(reference), canonical(hypothesis)
    return Levenshtein.distance(ref, hyp) / max(len(ref), 1)


def render(args, settings: Settings) -> None:
    PAGES_DIR.mkdir(exist_ok=True)
    with pymupdf.open(args.pdf) as doc:
        for page_no in args.pages:
            out = PAGES_DIR / f"{Path(args.pdf).stem}_p{page_no}.png"
            pdf.render_page(doc[page_no - 1], settings.ocr_dpi).save(out)
            print(f"wrote {out}  (now type its text into {out.with_suffix('.txt').name})")


def run(args, settings: Settings) -> None:
    pairs = []
    for img in sorted(PAGES_DIR.glob("*")):
        if img.suffix.lower() in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
            ref = img.with_suffix(".txt")
            if ref.exists():
                pairs.append((img, ref.read_text(encoding="utf-8")))
            else:
                print(f"skipping {img.name}: no {ref.name}")
    if not pairs:
        sys.exit(f"No image + .txt reference pairs in {PAGES_DIR}")

    results = []
    for engine_name in args.engines.split(","):
        try:
            engine = make_ocr_engine(engine_name.strip(), settings)
        except Exception as e:
            print(f"{engine_name}: unavailable ({e})")
            continue
        for img_path, reference in pairs:
            start = time.perf_counter()
            try:
                out = engine.ocr(Image.open(img_path).convert("RGB"))
                error = cer(reference, out.text)
                conf = out.confidence
            except Exception as e:
                print(f"  {engine_name} {img_path.name}: failed ({e})")
                continue
            seconds = time.perf_counter() - start
            results.append(
                {
                    "engine": engine.name,
                    "page": img_path.name,
                    "cer": round(error, 4),
                    "confidence": conf,
                    "seconds": round(seconds, 1),
                }
            )
            print(f"  {engine.name:10} {img_path.name:30} CER {error:6.1%}  {seconds:5.1f}s")
            (EVAL_DIR / "results" / "ocr_output").mkdir(parents=True, exist_ok=True)
            (EVAL_DIR / "results" / "ocr_output" / f"{img_path.stem}.{engine.name}.txt").write_text(
                out.text, encoding="utf-8"
            )

    if not results:
        return
    print("\nMean CER by engine (target < 10%)")
    for name in dict.fromkeys(r["engine"] for r in results):
        rows = [r for r in results if r["engine"] == name]
        mean = sum(r["cer"] for r in rows) / len(rows)
        secs = sum(r["seconds"] for r in rows) / len(rows)
        print(
            f"  {name:10} {mean:6.1%}  over {len(rows)} pages, {secs:.1f}s/page  "
            f"{'PASS' if mean < CER_TARGET else 'below'}"
        )

    out = EVAL_DIR / "results" / f"{datetime.now():%Y%m%d-%H%M%S}-ocr.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(f"\nDetails: {out}")


def main() -> None:
    # Windows consoles default to cp1252, which cannot print Urdu
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="render PDF pages to images for reference typing")
    r.add_argument("pdf")
    r.add_argument("pages", type=int, nargs="+")
    c = sub.add_parser("run", help="run engines against the reference pages")
    c.add_argument("--engines", default="tesseract")
    args = ap.parse_args()
    settings = Settings()
    render(args, settings) if args.cmd == "render" else run(args, settings)


if __name__ == "__main__":
    main()
