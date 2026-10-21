"""In-process job queue, progress fan-out and cancellation."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import config, db
from .services.translate import CancelledError, CancelToken, cleanup_dir, run_job

TERMINAL = {"done", "error", "cancelled"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class JobState:
    id: str
    filename: str
    size: int
    pages: int
    options: dict[str, Any]
    created_at: str
    output_dir: str
    source_path: str
    status: str = "queued"
    current: int = 0
    total: int = 0
    message: str = ""
    error: str | None = None
    files: dict[str, str] = field(default_factory=dict)
    finished_at: str | None = None
    cancel_token: CancelToken = field(default_factory=CancelToken)
    condition: threading.Condition = field(default_factory=threading.Condition)
    events: list[dict[str, Any]] = field(default_factory=list)
    seq: int = 0
    last_persist: float = 0.0

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "size": self.size,
            "pages": self.pages,
            "status": self.status,
            "progress": {"current": self.current, "total": self.total},
            "message": self.message,
            "error": self.error,
            "options": self.options,
            "files": dict(self.files),
            "output_dir": self.output_dir,
            "source_path": self.source_path,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


class JobManager:
    def __init__(self, workers: int | None = None) -> None:
        db.init_db()
        db.mark_interrupted()
        self._executor = ThreadPoolExecutor(
            max_workers=workers or config.MAX_WORKERS, thread_name_prefix="pdf2zh"
        )
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()

    # ── lifecycle ──────────────────────────────────────────────

    def create(
        self,
        job_id: str,
        filename: str,
        size: int,
        source_path: str,
        output_dir: str,
        options: dict[str, Any],
        pages: int = 0,
    ) -> dict[str, Any]:
        state = JobState(
            id=job_id,
            filename=filename,
            size=size,
            pages=pages,
            options=options,
            created_at=_now(),
            output_dir=output_dir,
            source_path=source_path,
        )
        with self._lock:
            self._jobs[job_id] = state
        db.save_job(state.snapshot())
        self._executor.submit(self._run, state)
        return state.snapshot()

    def _run(self, state: JobState) -> None:
        if state.cancel_token.is_set():
            self._finish(state, "cancelled", message="已取消")
            return

        state.status = "running"
        self._emit(state, "status", message="任务已开始")
        try:
            result = run_job(state.snapshot(), self._emitter(state), state.cancel_token)
            if state.cancel_token.is_set():
                self._finish(state, "cancelled", message="已取消")
                return
            state.files = result.get("files", {})
            state.pages = result.get("pages", state.pages)
            state.current = state.total or state.pages
            if state.total:
                state.total = state.total
            self._finish(state, "done", message="翻译完成", files=state.files)
        except CancelledError:
            self._finish(state, "cancelled", message="已取消")
        except Exception as exc:  # noqa: BLE001 - surface every failure to the user
            self._finish(state, "error", message="翻译失败", error=str(exc) or exc.__class__.__name__)
        finally:
            if state.total == 0 and state.pages:
                state.total = state.pages
            db.save_job(state.snapshot())

    def _finish(
        self,
        state: JobState,
        status: str,
        *,
        message: str,
        error: str | None = None,
        files: dict[str, str] | None = None,
    ) -> None:
        state.status = status
        state.finished_at = _now()
        if error:
            state.error = error
        if files is not None:
            state.files = files
        event_type = "done" if status == "done" else status
        if event_type not in {"done", "error", "cancelled"}:
            event_type = "status"
        urls = {
            kind: f"/api/jobs/{state.id}/download/{kind}" for kind in state.files
        }
        self._emit(
            state,
            event_type,
            message=message,
            data={"files": urls, "error": state.error} if status != "done" else {"files": urls},
        )
        db.save_job(state.snapshot())

    # ── events ────────────────────────────────────────────────

    def _emitter(self, state: JobState):
        def emit(event_type: str, **payload: Any) -> None:
            self._emit(state, event_type, **payload)

        return emit

    def _emit(self, state: JobState, event_type: str, **payload: Any) -> None:
        with state.condition:
            state.seq += 1
            event: dict[str, Any] = {
                "seq": state.seq,
                "type": event_type,
                "job_id": state.id,
            }
            if "current" in payload:
                state.current = int(payload["current"])
                event["current"] = state.current
            if "total" in payload:
                state.total = int(payload["total"])
                event["total"] = state.total
            if payload.get("message") is not None:
                state.message = str(payload["message"])
                event["message"] = state.message
            if payload.get("data") is not None:
                event["data"] = payload["data"]

            state.events.append(event)
            if len(state.events) > 2000:
                del state.events[:500]
            state.condition.notify_all()

        now = time.monotonic()
        if event_type != "progress" or now - state.last_persist >= 1.0:
            state.last_persist = now
            db.save_job(state.snapshot())

    def events_since(self, job_id: str, since: int) -> list[dict[str, Any]]:
        with self._lock:
            state = self._jobs.get(job_id)
        if state is None:
            return []
        with state.condition:
            return [event for event in state.events if event["seq"] > since]

    # ── queries ───────────────────────────────────────────────

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._jobs.get(job_id)
        if state is not None:
            return state.snapshot()
        return db.get_job(job_id)

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._jobs.get(job_id)
        if state is None:
            return None
        state.cancel_token.cancel()
        if state.status == "queued":
            self._finish(state, "cancelled", message="已取消")
        return state.snapshot()

    def delete(self, job_id: str) -> bool:
        with self._lock:
            state = self._jobs.pop(job_id, None)
        if state is not None:
            state.cancel_token.cancel()
        job = db.delete_job(job_id)
        if job is None and state is None:
            return False
        output_dir = (state.output_dir if state else job.get("output_dir")) or ""
        if output_dir:
            cleanup_dir(output_dir)
        return True

    def wait(self, job_id: str, timeout: float = 30.0) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.get(job_id)
            if job and job["status"] in TERMINAL:
                return job
            time.sleep(0.05)
        return self.get(job_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


manager = JobManager()
