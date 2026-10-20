"""Show what is stored: documents, pages, chunks and their embedding vectors.

    python scripts/inspect_store.py                  # summary + every chunk (short)
    python scripts/inspect_store.py --chunk c20      # one chunk in full, with its vector
    python scripts/inspect_store.py --search "سوال"  # nearest chunks to a question
    python scripts/inspect_store.py --export chunks.csv
"""

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import chromadb  # noqa: E402

from app.config import get_settings  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--chunk", help="vector id, e.g. c20")
    p.add_argument("--search", help="question to embed and search")
    p.add_argument("-k", type=int, default=5)
    p.add_argument("--export", help="write chunks + vectors to a CSV file")
    args = p.parse_args()

    s = get_settings()
    db = sqlite3.connect(s.storage_dir / "app.db")
    db.row_factory = sqlite3.Row
    client = chromadb.PersistentClient(path=str(s.chroma_dir))
    cols = client.list_collections()
    col = client.get_collection(cols[0].name) if cols else None

    def chunk_row(vid):
        return db.execute(
            "SELECT c.*, d.filename FROM chunks c JOIN documents d ON d.id = c.document_id WHERE vector_id = ?",
            (vid,),
        ).fetchone()

    if args.chunk:
        row = chunk_row(args.chunk)
        vec = col.get(ids=[args.chunk], include=["embeddings", "metadatas"])
        print(f"{args.chunk}  {row['filename']}  page {row['page_no']}  lang {row['language']}")
        print(f"metadata: {vec['metadatas'][0]}\n\n{row['text']}\n")
        e = vec["embeddings"][0]
        print(f"vector ({len(e)} dims): {[round(float(x), 4) for x in e[:16]]} ...")
        return

    if args.search:
        from sentence_transformers import SentenceTransformer

        q = SentenceTransformer(s.embedding_model).encode([args.search], normalize_embeddings=True)
        r = col.query(query_embeddings=q.tolist(), n_results=args.k)
        for vid, dist in zip(r["ids"][0], r["distances"][0]):
            row = chunk_row(vid)
            print(f"[{vid}] distance {dist:.3f}  {row['filename']} p{row['page_no']}")
            print("   ", row["text"][:200].replace("\n", " "), "\n")
        return

    if args.export:
        rows = db.execute(
            "SELECT c.*, d.filename FROM chunks c JOIN documents d ON d.id = c.document_id ORDER BY c.id"
        ).fetchall()
        vecs = col.get(ids=[r["vector_id"] for r in rows], include=["embeddings"])
        by_id = dict(zip(vecs["ids"], vecs["embeddings"]))
        with open(args.export, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["vector_id", "file", "page", "language", "text", "vector"])
            for r in rows:
                v = by_id.get(r["vector_id"])
                vs = " ".join(f"{x:.5f}" for x in v) if v is not None else ""
                w.writerow([r["vector_id"], r["filename"], r["page_no"], r["language"], r["text"], vs])
        print(f"wrote {len(rows)} chunks to {args.export}")
        return

    print("DOCUMENTS")
    for d in db.execute("SELECT * FROM documents"):
        print(f"  #{d['id']} {d['filename']}  pages {d['pages_done']}/{d['page_count']}  {d['status']}")
    print("\nPAGES (extraction method)")
    for m in db.execute("SELECT method, COUNT(*) n FROM pages GROUP BY method"):
        print(f"  {m['method']}: {m['n']}")
    if col:
        print(f"\nVECTOR DB  collection {col.name}: {col.count()} vectors")
    print("\nCHUNKS")
    for r in db.execute(
        "SELECT c.*, d.filename FROM chunks c JOIN documents d ON d.id = c.document_id ORDER BY c.id"
    ):
        print(f"  [{r['vector_id']}] p{r['page_no']} {r['language']}  {r['text'][:90].replace(chr(10), ' ')}")


if __name__ == "__main__":
    main()
