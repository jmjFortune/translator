"""History/library endpoints."""

from __future__ import annotations

from itertools import groupby
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..models import (
    PaperContentOut,
    PaperOut,
    ParagraphOut,
    SectionOut,
)
from ..services.credentials import BY_ID

router = APIRouter(prefix="/papers", tags=["papers"])


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def _paper(job: dict[str, Any]) -> PaperOut:
    options = job.get("options", {})
    stem = Path(job["filename"]).stem
    spec = BY_ID.get(options.get("service", ""))
    return PaperOut(
        id=job["id"],
        title=stem.replace("_", " ").strip(),
        zhTitle="",
        authors="",
        pages=job.get("pages", 0),
        size=_human_size(job.get("size", 0)),
        service=spec.name if spec else options.get("service", ""),
        date=job.get("created_at", ""),
        status="completed" if job["status"] == "done" else job["status"],
        downloadable=bool(job.get("files")),
    )


@router.get("", response_model=list[PaperOut])
async def list_papers(query: str = Query("", description="按标题过滤")) -> list[PaperOut]:
    jobs = db.list_done_jobs()
    papers = [_paper(job) for job in jobs]
    if query:
        needle = query.lower()
        papers = [
            paper
            for paper in papers
            if needle in paper.title.lower() or needle in paper.zhTitle.lower()
        ]
    return papers


@router.get("/{paper_id}", response_model=PaperOut)
async def get_paper(paper_id: str) -> PaperOut:
    job = db.get_job(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="论文不存在")
    return _paper(job)


@router.delete("/{paper_id}")
async def delete_paper(paper_id: str) -> dict[str, bool]:
    from ..jobs import manager

    if not manager.delete(paper_id):
        raise HTTPException(status_code=404, detail="论文不存在")
    return {"deleted": True}


@router.get("/{paper_id}/content", response_model=PaperContentOut)
async def get_content(paper_id: str) -> PaperContentOut:
    job = db.get_job(paper_id)
    if job is None:
        raise HTTPException(status_code=404, detail="论文不存在")

    rows = db.get_paragraphs(paper_id)
    sections: list[SectionOut] = []
    for page, items in groupby(rows, key=lambda row: row["page"]):
        paragraphs = [
            ParagraphOut(
                id=f"p-{page + 1}-{index + 1}",
                en=row["source"],
                zh=row["translated"],
                bbox=row.get("bbox"),
                latex=row.get("latex"),
            )
            for index, row in enumerate(items)
        ]
        sections.append(
            SectionOut(
                id=f"page-{page + 1}",
                headingEn=f"Page {page + 1}",
                headingZh=f"第 {page + 1} 页",
                paragraphs=paragraphs,
            )
        )

    stem = Path(job["filename"]).stem.replace("_", " ").strip()
    abstract = {"en": "", "zh": ""}
    if sections and sections[0].paragraphs:
        first = sections[0].paragraphs[:2]
        abstract["en"] = " ".join(p.en for p in first if p.en)
        abstract["zh"] = " ".join(p.zh for p in first if p.zh)

    return PaperContentOut(
        id=job["id"],
        title=stem,
        titleZh="",
        authors="",
        conference="",
        totalPages=job.get("pages", 0),
        abstract=abstract,
        sections=sections,
        has_content=bool(rows),
    )
