"""SQLite schema and queries for documents, pages, chunks and logged questions."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT NOT NULL,
    sha256      TEXT NOT NULL UNIQUE,
    page_count  INTEGER NOT NULL DEFAULT 0,
    pages_done  INTEGER NOT NULL DEFAULT 0,
    pages_failed INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL,
    error       TEXT,
    uploaded_at TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id    INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no        INTEGER NOT NULL,
    method         TEXT NOT NULL,
    reason         TEXT,
    text           TEXT NOT NULL DEFAULT '',
    raw_text       TEXT NOT NULL DEFAULT '',
    image_path     TEXT,
    ocr_confidence REAL,
    ocr_status     TEXT NOT NULL DEFAULT 'ok',
    quality        REAL,
    error          TEXT,
    UNIQUE (document_id, page_no)
);
CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no     INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    text        TEXT NOT NULL,
    language    TEXT NOT NULL,
    vector_id   TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE TABLE IF NOT EXISTS queries (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    question       TEXT NOT NULL,
    document_ids   TEXT,
    answer         TEXT,
    found          INTEGER,
    chunk_ids_used TEXT,
    latency_ms     INTEGER,
    created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

STATUSES = ("uploaded", "extracting", "indexing", "ready", "failed")

# Columns added after the first release; created on startup if an older database lacks them
_MIGRATIONS = {
    "documents": {"pages_failed": "INTEGER NOT NULL DEFAULT 0"},
    "pages": {"ocr_status": "TEXT NOT NULL DEFAULT 'ok'", "quality": "REAL", "error": "TEXT"},
}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            for table, columns in _MIGRATIONS.items():
                have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                for name, decl in columns.items():
                    if name not in have:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ---- documents -------------------------------------------------------

    def create_document(self, filename: str, sha256: str, page_count: int) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO documents (filename, sha256, page_count, status, uploaded_at, updated_at)"
                " VALUES (?, ?, ?, 'uploaded', ?, ?)",
                (filename, sha256, page_count, _now(), _now()),
            )
            return cur.lastrowid

    def get_document(self, doc_id: int) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            return dict(row) if row else None

    def get_document_by_sha(self, sha256: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE sha256 = ?", (sha256,)).fetchone()
            return dict(row) if row else None

    def list_documents(self) -> list[dict]:
        with self.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM documents ORDER BY id DESC")]

    def count_ready(self, document_ids: list[int] | None = None) -> int:
        with self.connect() as conn:
            if document_ids:
                marks = ",".join("?" * len(document_ids))
                row = conn.execute(
                    f"SELECT COUNT(*) FROM documents WHERE status = 'ready' AND id IN ({marks})", document_ids
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM documents WHERE status = 'ready'").fetchone()
            return row[0]

    def set_status(self, doc_id: int, status: str, error: str | None = None) -> None:
        assert status in STATUSES
        with self.connect() as conn:
            conn.execute(
                "UPDATE documents SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                (status, error, _now(), doc_id),
            )

    def set_progress(self, doc_id: int, pages_done: int, pages_failed: int = 0) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE documents SET pages_done = ?, pages_failed = ?, updated_at = ? WHERE id = ?",
                (pages_done, pages_failed, _now(), doc_id),
            )

    def fail_interrupted(self) -> list[int]:
        """Mark documents left mid-processing by a restart as failed."""
        with self.connect() as conn:
            ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM documents WHERE status IN ('uploaded', 'extracting', 'indexing')"
                )
            ]
            conn.execute(
                "UPDATE documents SET status = 'failed',"
                " error = 'Interrupted by a server restart; reprocess the document.', updated_at = ?"
                " WHERE status IN ('uploaded', 'extracting', 'indexing')",
                (_now(),),
            )
            return ids

    def delete_document(self, doc_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            self._bump_index_version(conn)

    # ---- pages -----------------------------------------------------------

    def save_page(
        self,
        doc_id: int,
        page_no: int,
        method: str,
        reason: str,
        text: str,
        raw_text: str,
        image_path: str | None,
        ocr_confidence: float | None,
        ocr_status: str = "ok",
        quality: float | None = None,
        error: str | None = None,
    ) -> None:
        """Insert or replace one page. ocr_status: ok | low_quality | failed."""
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pages (document_id, page_no, method, reason, text, raw_text,"
                " image_path, ocr_confidence, ocr_status, quality, error)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    doc_id,
                    page_no,
                    method,
                    reason,
                    text,
                    raw_text,
                    image_path,
                    ocr_confidence,
                    ocr_status,
                    quality,
                    error,
                ),
            )

    def update_page_texts(self, doc_id: int, texts: dict[int, str]) -> None:
        with self.connect() as conn:
            conn.executemany(
                "UPDATE pages SET text = ? WHERE document_id = ? AND page_no = ?",
                [(t, doc_id, n) for n, t in texts.items()],
            )

    def get_pages(self, doc_id: int) -> list[dict]:
        with self.connect() as conn:
            return [
                dict(r)
                for r in conn.execute("SELECT * FROM pages WHERE document_id = ? ORDER BY page_no", (doc_id,))
            ]

    def get_page(self, doc_id: int, page_no: int) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM pages WHERE document_id = ? AND page_no = ?", (doc_id, page_no)
            ).fetchone()
            return dict(row) if row else None

    def clear_document_content(self, doc_id: int, keep_pages: bool = False) -> None:
        """Remove chunks (and pages, unless keep_pages) so a document can be processed again."""
        with self.connect() as conn:
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            if not keep_pages:
                conn.execute("DELETE FROM pages WHERE document_id = ?", (doc_id,))
            conn.execute("UPDATE documents SET pages_done = 0, pages_failed = 0 WHERE id = ?", (doc_id,))
            self._bump_index_version(conn)

    # ---- chunks ----------------------------------------------------------

    def insert_chunks(self, doc_id: int, chunks: list[dict]) -> list[int]:
        """Insert chunks and return their ids; vector_id is set to 'c<id>'."""
        ids = []
        with self.connect() as conn:
            for c in chunks:
                cur = conn.execute(
                    "INSERT INTO chunks (document_id, page_no, chunk_index, text, language)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (doc_id, c["page_no"], c["chunk_index"], c["text"], c["language"]),
                )
                ids.append(cur.lastrowid)
            conn.executemany("UPDATE chunks SET vector_id = ? WHERE id = ?", [(f"c{i}", i) for i in ids])
            self._bump_index_version(conn)
        return ids

    def get_chunks(self, chunk_ids: list[int]) -> dict[int, dict]:
        if not chunk_ids:
            return {}
        marks = ",".join("?" * len(chunk_ids))
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT c.*, d.filename, d.status AS doc_status FROM chunks c"
                f" JOIN documents d ON d.id = c.document_id WHERE c.id IN ({marks})",
                chunk_ids,
            )
            return {r["id"]: dict(r) for r in rows}

    def all_ready_chunks(self) -> list[dict]:
        with self.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT c.id, c.document_id, c.page_no, c.text FROM chunks c"
                    " JOIN documents d ON d.id = c.document_id WHERE d.status = 'ready' ORDER BY c.id"
                )
            ]

    def chunk_ids_for_document(self, doc_id: int) -> list[int]:
        with self.connect() as conn:
            return [r["id"] for r in conn.execute("SELECT id FROM chunks WHERE document_id = ?", (doc_id,))]

    # ---- index version (invalidates BM25 and the answer cache) -----------

    def _bump_index_version(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('index_version', '1')"
            " ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + 1"
        )

    def bump_index_version(self) -> None:
        with self.connect() as conn:
            self._bump_index_version(conn)

    def index_version(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = 'index_version'").fetchone()
            return int(row["value"]) if row else 0

    # ---- queries ---------------------------------------------------------

    def log_query(
        self,
        question: str,
        document_ids: list[int] | None,
        answer: str,
        found: bool,
        chunk_ids: list[int],
        latency_ms: int,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO queries (question, document_ids, answer, found, chunk_ids_used,"
                " latency_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    question,
                    json.dumps(document_ids) if document_ids else None,
                    answer,
                    int(found),
                    json.dumps(chunk_ids),
                    latency_ms,
                    _now(),
                ),
            )
            return cur.lastrowid
