"""Pydantic models shared by the API layer and the job manager."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "done", "error", "cancelled"]
EventType = Literal["status", "progress", "done", "error", "cancelled"]


class Progress(BaseModel):
    current: int = 0
    total: int = 0


class JobOut(BaseModel):
    id: str
    status: JobStatus
    filename: str
    size: int
    pages: int
    progress: Progress = Field(default_factory=Progress)
    message: str = ""
    error: str | None = None
    files: dict[str, str] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    finished_at: str | None = None


class JobEvent(BaseModel):
    seq: int
    type: EventType
    job_id: str
    current: int | None = None
    total: int | None = None
    message: str | None = None
    data: dict[str, Any] | None = None


class ServiceOut(BaseModel):
    id: str
    name: str
    needs_key: bool
    has_key: bool
    base_url: str = ""
    model: str = ""
    default_base_url: str = ""
    default_model: str = ""
    note: str = ""


class Defaults(BaseModel):
    lang_in: str = "en"
    lang_out: str = "zh"
    service: str = "bing"
    thread: int = 4
    output_formats: list[str] = Field(
        default_factory=lambda: ["mono", "dual", "side_by_side"]
    )


class SettingsOut(BaseModel):
    services: list[ServiceOut]
    defaults: Defaults
    glossary_count: int


class ServicePatch(BaseModel):
    id: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class SettingsPatch(BaseModel):
    services: list[ServicePatch] = Field(default_factory=list)
    defaults: Defaults | None = None


class GlossaryOut(BaseModel):
    terms: dict[str, str]
    presets: list[str]


class GlossaryPatch(BaseModel):
    terms: dict[str, str]


class GlossaryTermIn(BaseModel):
    term: str
    zh: str


class PaperOut(BaseModel):
    id: str
    title: str
    zhTitle: str = ""
    authors: str = ""
    pages: int = 0
    size: str = ""
    service: str = ""
    date: str
    status: str = "completed"
    downloadable: bool = False


class ParagraphOut(BaseModel):
    id: str
    en: str
    zh: str
    bbox: list[float] | None = None
    latex: str | None = None


class SectionOut(BaseModel):
    id: str
    headingEn: str = ""
    headingZh: str = ""
    paragraphs: list[ParagraphOut] = Field(default_factory=list)


class PaperContentOut(BaseModel):
    id: str
    title: str
    titleZh: str = ""
    authors: str = ""
    conference: str = ""
    totalPages: int = 0
    abstract: dict[str, str] = Field(default_factory=lambda: {"en": "", "zh": ""})
    sections: list[SectionOut] = Field(default_factory=list)
    has_content: bool = False
