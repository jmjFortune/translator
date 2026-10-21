"""Job endpoints: upload, status, SSE progress, cancellation, download."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from .. import config
from ..jobs import TERMINAL, manager
from ..models import JobOut
from ..services.credentials import BY_ID
from ..services.translate import parse_formats

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_or_404(job_id: str) -> dict[str, Any]:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


def _public(job: dict[str, Any]) -> JobOut:
    """Hide absolute disk paths; clients only get download URLs."""
    data = dict(job)
    data["files"] = {
        kind: f"/api/jobs/{job['id']}/download/{kind}"
        for kind in job.get("files", {})
    }
    return JobOut(**data)


@router.post("", response_model=JobOut, status_code=201)
async def create_job(
    file: UploadFile = File(...),
    lang_in: str = Form("en"),
    lang_out: str = Form("zh"),
    service: str = Form("bing"),
    page_range: str = Form(""),
    output_formats: str = Form("mono,dual,side_by_side"),
    thread: int = Form(4),
    ocr: bool = Form(False),
    translate_tables: bool = Form(False),
    auto_glossary: bool = Form(False),
    mock_pages: int = Form(5),
) -> JobOut:
    if service not in BY_ID:
        raise HTTPException(status_code=400, detail=f"未知翻译服务: {service}")

    filename = Path(file.filename or "document.pdf").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只支持 PDF 文件")

    job_id = uuid.uuid4().hex
    output_dir = config.OUTPUT_DIR / job_id
    source_dir = output_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / filename

    size = 0
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    try:
        with source_path.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过 {config.MAX_UPLOAD_MB} MB 限制",
                    )
                handle.write(chunk)
    except HTTPException:
        source_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if size == 0:
        source_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="空文件")

    try:
        from ui.glossary_manager import GlossaryManager

        glossary = GlossaryManager.load()
    except Exception:
        glossary = {}

    options: dict[str, Any] = {
        "lang_in": lang_in,
        "lang_out": lang_out,
        "service": service,
        "page_range": page_range,
        "output_formats": parse_formats(output_formats),
        "thread": max(1, min(thread, 32)),
        "ocr": ocr,
        "translate_tables": translate_tables,
        "auto_glossary": auto_glossary,
        "glossary": glossary,
        "mock_pages": mock_pages,
    }

    job = manager.create(
        job_id=job_id,
        filename=filename,
        size=size,
        source_path=str(source_path),
        output_dir=str(output_dir),
        options=options,
    )
    return _public(job)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str) -> JobOut:
    return _public(_job_or_404(job_id))


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: str) -> JobOut:
    job = manager.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _public(job)


@router.get("/{job_id}/events")
async def job_events(
    job_id: str, request: Request, since: int = 0,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> StreamingResponse:
    _job_or_404(job_id)
    if last_event_id and last_event_id.isdigit():
        since = max(since, int(last_event_id))

    async def stream():
        last = since
        while True:
            if await request.is_disconnected():
                break
            events = manager.events_since(job_id, last)
            for event in events:
                last = int(event["seq"])
                payload = json.dumps(event, ensure_ascii=False)
                yield f"id: {last}\ndata: {payload}\n\n"
            job = manager.get(job_id)
            if job is None:
                break
            if job["status"] in TERMINAL and not events:
                break
            if not events:
                yield ": ping\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}/files")
async def job_files(job_id: str) -> dict[str, str]:
    job = _job_or_404(job_id)
    return {
        kind: f"/api/jobs/{job_id}/download/{kind}"
        for kind in job.get("files", {})
    }


@router.get("/{job_id}/download/{kind}")
async def download(job_id: str, kind: str, inline: bool = False) -> FileResponse:
    """Read original upload (`original`) or a generated PDF; inline enables preview."""
    job = _job_or_404(job_id)
    files = job.get("files", {})
    if kind != "original" and kind not in files:
        raise HTTPException(status_code=404, detail="该格式尚未生成")

    base = Path(job["output_dir"]).resolve()
    source = base / "source" / Path(job["filename"]).name
    path = Path(source if kind == "original" else files[kind]).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise HTTPException(status_code=404, detail="产物文件已丢失")

    stem = Path(job["filename"]).stem
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{stem}-{kind}.pdf",
        content_disposition_type="inline" if inline else "attachment",
    )
