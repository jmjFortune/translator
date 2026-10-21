"""SQLite persistence for jobs and paragraph pairs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id               TEXT PRIMARY KEY,
    filename         TEXT NOT NULL,
    size             INTEGER NOT NULL DEFAULT 0,
    pages            INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL,
    progress_current INTEGER NOT NULL DEFAULT 0,
    progress_total   INTEGER NOT NULL DEFAULT 0,
    message          TEXT NOT NULL DEFAULT '',
    error            TEXT,
    options          TEXT NOT NULL DEFAULT '{}',
    output_files     TEXT NOT NULL DEFAULT '{}',
    output_dir       TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    finished_at      TEXT
);

CREATE TABLE IF NOT EXISTS paragraphs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT NOT NULL,
    page       INTEGER NOT NULL,
    seq        INTEGER NOT NULL,
    bbox       TEXT,
    source     TEXT NOT NULL DEFAULT '',
    translated TEXT NOT NULL DEFAULT '',
    latex      TEXT
);

CREATE INDEX IF NOT EXISTS idx_paragraphs_job ON paragraphs(job_id, page, seq);
"""


def _connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


def _job_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "size": row["size"],
        "pages": row["pages"],
        "status": row["status"],
        "progress": {"current": row["progress_current"], "total": row["progress_total"]},
        "message": row["message"],
        "error": row["error"],
        "options": json.loads(row["options"] or "{}"),
        "files": json.loads(row["output_files"] or "{}"),
        "output_dir": row["output_dir"],
        "created_at": row["created_at"],
        "finished_at": row["finished_at"],
    }


def save_job(job: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, filename, size, pages, status, progress_current,
                              progress_total, message, error, options, output_files,
                              output_dir, created_at, finished_at)
            VALUES (:id, :filename, :size, :pages, :status, :pc, :pt, :message, :error,
                    :options, :files, :output_dir, :created_at, :finished_at)
            ON CONFLICT(id) DO UPDATE SET
                pages=excluded.pages,
                status=excluded.status,
                progress_current=excluded.progress_current,
                progress_total=excluded.progress_total,
                message=excluded.message,
                error=excluded.error,
                options=excluded.options,
                output_files=excluded.output_files,
                output_dir=excluded.output_dir,
                finished_at=excluded.finished_at
            """,
            {
                "id": job["id"],
                "filename": job["filename"],
                "size": job["size"],
                "pages": job["pages"],
                "status": job["status"],
                "pc": job["progress"]["current"],
                "pt": job["progress"]["total"],
                "message": job["message"],
                "error": job.get("error"),
                "options": json.dumps(job.get("options", {}), ensure_ascii=False),
                "files": json.dumps(job.get("files", {}), ensure_ascii=False),
                "output_dir": job.get("output_dir", ""),
                "created_at": job["created_at"],
                "finished_at": job.get("finished_at"),
            },
        )


def get_job(job_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _job_row(row) if row else None


def list_done_jobs(limit: int = 200) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = 'done' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_job_row(row) for row in rows]


def delete_job(job_id: str) -> dict[str, Any] | None:
    job = get_job(job_id)
    if not job:
        return None
    with _connect() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.execute("DELETE FROM paragraphs WHERE job_id = ?", (job_id,))
    return job


def mark_interrupted() -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status='error', error=?, finished_at=? "
            "WHERE status IN ('queued', 'running')",
            ("服务重启，任务已中断", datetime.now().isoformat(timespec="seconds")),
        )


def get_paragraphs(job_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT page, seq, bbox, source, translated, latex FROM paragraphs "
            "WHERE job_id = ? ORDER BY page, seq",
            (job_id,),
        ).fetchall()
    result = []
    for row in rows:
        result.append(
            {
                "page": row["page"],
                "seq": row["seq"],
                "bbox": json.loads(row["bbox"]) if row["bbox"] else None,
                "source": row["source"],
                "translated": row["translated"],
                "latex": row["latex"],
            }
        )
    return result
