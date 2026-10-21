"""Translation runner.

The pdf2zh-next asynchronous stream runs in a worker thread owned by the API
server. The public job and SSE interfaces remain independent of the engine.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import threading
import time
from contextlib import aclosing, nullcontext
from pathlib import Path
from typing import Any, Callable

from .. import config
from . import credentials
from .credentials import BY_ID

Emit = Callable[..., None]


class CancelledError(Exception):
    """Raised when the user cancels a running job."""


class CancelToken:
    """Thread-safe cancellation signal shared with the async stream watcher."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()


def parse_page_range(text: str | None) -> list[int] | None:
    """'1-5, 8' -> [0,1,2,3,4,7]; empty / 'all' -> None."""
    if not text or not text.strip() or text.strip().lower() == "all":
        return None
    pages: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            first, last = int(start.strip()), int(end.strip())
            if first < 1 or last < first:
                raise ValueError("页码范围必须是递增的正整数")
            pages.extend(range(first - 1, last))
        else:
            page = int(part)
            if page < 1:
                raise ValueError("页码必须是正整数")
            pages.append(page - 1)
    if not pages:
        raise ValueError("页码范围不能为空")
    return sorted(set(pages))


def parse_formats(value: str | list[str] | None) -> list[str]:
    if not value:
        return ["mono", "dual", "side_by_side"]
    items = value.split(",") if isinstance(value, str) else value
    allowed = {"mono", "dual", "side_by_side"}
    formats = [item.strip() for item in items if item.strip() in allowed]
    return formats or ["mono"]


def _minimal_pdf(text: str) -> bytes:
    """A valid one-page PDF, used by mock mode so downloads stay testable."""
    safe = re.sub(r"[()\\]", lambda m: "\\" + m.group(0), text)
    stream = f"BT /F1 18 Tf 72 760 Td ({safe}) Tj ET".encode("latin-1", "replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for index, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


def _write_mock_outputs(job: dict[str, Any], formats: list[str]) -> dict[str, str]:
    output_dir = Path(job["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(job["filename"]).stem
    content = _minimal_pdf(f"[mock] {stem} - translated to {job['options'].get('lang_out', 'zh')}")
    files: dict[str, str] = {}
    for kind in formats:
        path = output_dir / f"{stem}-{kind}.pdf"
        path.write_bytes(content)
        files[kind] = str(path)
    return files


def run_mock(job: dict[str, Any], emit: Emit, token: CancelToken) -> dict[str, Any]:
    total = max(1, int(job["options"].get("mock_pages", 5)))
    steps = ["解析版面", "隔离公式", "翻译段落", "对齐排版", "生成文件"]
    for index, step in enumerate(steps):
        if token.is_set():
            raise CancelledError
        time.sleep(0.25)
        emit("status", message=f"[mock] {step}")
        emit("progress", current=round(total * (index + 1) / len(steps)), total=total)
    formats = parse_formats(job["options"].get("output_formats"))
    files = _write_mock_outputs(job, formats)
    return {"files": files, "pages": total}


def _apply_output_formats(
    files: dict[str, str], formats: list[str]
) -> dict[str, str]:
    for kind in list(files):
        if kind not in formats and files.get(kind):
            path = Path(files[kind])
            if path.exists():
                path.unlink(missing_ok=True)
            files.pop(kind, None)
    return files


async def _run_stream(settings: Any, source: Path, emit: Emit, token: CancelToken):
    from pdf2zh_next.high_level import do_translate_async_stream

    async def consume():
        result = None
        last_stage = None
        async with aclosing(do_translate_async_stream(settings, source)) as stream:
            async for event in stream:
                if token.is_set():
                    raise CancelledError
                event_type = event.get("type")
                if event_type in {"progress_start", "progress_update", "progress_end"}:
                    stage = event.get("stage")
                    if stage and stage != last_stage:
                        emit("status", message=str(stage))
                        last_stage = stage
                    if event.get("overall_progress") is not None:
                        current = max(0, min(100, int(float(event["overall_progress"]))))
                        emit("progress", current=current, total=100)
                elif event_type == "error":
                    raise RuntimeError(str(event.get("error") or "pdf2zh-next 翻译失败"))
                elif event_type == "finish":
                    result = event.get("translate_result")
        if result is None:
            raise RuntimeError("pdf2zh-next 未返回完成结果")
        return result

    async def watch_cancel(task):
        while not task.done():
            if token.is_set():
                task.cancel()
                return
            await asyncio.sleep(0.1)

    task = asyncio.create_task(consume())
    watcher = asyncio.create_task(watch_cancel(task))
    try:
        return await task
    except asyncio.CancelledError:
        if token.is_set():
            raise CancelledError from None
        raise
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


def run_real(job: dict[str, Any], emit: Emit, token: CancelToken) -> dict[str, Any]:
    if token.is_set():
        raise CancelledError
    try:
        import fitz
        from pdf2zh_next.high_level import do_translate_async_stream  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on installed runtime
        raise RuntimeError(
            "pdf2zh-next 依赖不可用，请使用 Python 3.11–3.13 安装 server/requirements.txt"
        ) from exc

    from .next_engine import build_settings

    options = job["options"]
    service = options.get("service", "bing")
    spec = BY_ID.get(service)
    if spec is None:
        raise ValueError(f"pdf2zh-next 不支持翻译服务: {service}")
    envs = credentials.build_envs(service)
    if spec.needs_key and spec.api_env and not envs.get(spec.api_env):
        raise ValueError(f"「{spec.name}」的 API Key 未配置，请先到设置页填写。")

    source = Path(job["source_path"])
    with fitz.open(source) as doc:
        total_pages = len(doc)
    pages = parse_page_range(options.get("page_range"))
    if pages is not None:
        pages = [page for page in pages if page < total_pages]
        if not pages:
            raise ValueError("所选页码不在文档范围内")
    formats = parse_formats(options.get("output_formats"))
    emit("progress", current=0, total=100)
    emit("status", message="正在启动 pdf2zh-next…")

    bridge = nullcontext(None)
    if service == "opencode-go":
        from .opencode_proxy import opencode_bridge

        bridge = opencode_bridge(
            envs.get(spec.url_env) or spec.default_base_url, envs[spec.api_env]
        )
    with bridge as local:
        if local:
            envs = {**envs, spec.url_env: local[0], spec.api_env: local[1]}
        settings = build_settings(job, envs, pages, formats)
        if options.get("glossary") and not settings.translation.glossaries:
            emit("status", message="当前服务不支持术语库，已跳过；可选择 OpenAI 兼容服务使用术语库")
        if options.get("auto_glossary") and settings.translation.no_auto_extract_glossary:
            emit("status", message="当前服务不支持自动术语提取，已跳过")
        result = asyncio.run(_run_stream(settings, source, emit, token))

    if token.is_set():
        raise CancelledError
    files: dict[str, str] = {}
    required = set(formats) - {"side_by_side"}
    if "side_by_side" in formats:
        required.add("dual")
    output_dir = Path(job["output_dir"]).resolve()
    for kind in required:
        path_value = getattr(result, f"no_watermark_{kind}_pdf_path", None) or getattr(result, f"{kind}_pdf_path", None)
        if not path_value:
            raise RuntimeError(f"pdf2zh-next 未生成 {kind} 文件")
        path = Path(path_value).resolve()
        if not path.is_relative_to(output_dir) or not path.is_file():
            raise RuntimeError(f"pdf2zh-next 的 {kind} 产出文件无效")
        files[kind] = str(path)

    if "side_by_side" in formats:
        emit("status", message="正在生成左右并排版…")
        side_path = output_dir / f"{source.stem}-side_by_side.pdf"
        create_side_by_side_pdf(files.get("mono", ""), files["dual"], str(side_path))
        files["side_by_side"] = str(side_path)

    if token.is_set():
        raise CancelledError
    files = _apply_output_formats(files, formats)
    return {"files": files, "pages": total_pages}


def create_side_by_side_pdf(mono_path: str, dual_path: str, output_path: str) -> str:
    """Left page = original, right page = translation (same as the desktop app)."""
    import fitz

    doc_dual = fitz.open(dual_path)
    doc_out = fitz.open()
    try:
        if not len(doc_dual) or len(doc_dual) % 2:
            raise ValueError("双语文件必须包含成对的原文页和译文页")
        for index in range(len(doc_dual) // 2):
            original = doc_dual[index * 2]
            translated = doc_dual[index * 2 + 1]
            width = original.rect.width + translated.rect.width
            height = max(original.rect.height, translated.rect.height)
            page = doc_out.new_page(width=width, height=height)
            page.show_pdf_page(fitz.Rect(0, 0, original.rect.width, height), doc_dual, index * 2)
            page.show_pdf_page(
                fitz.Rect(original.rect.width, 0, width, height), doc_dual, index * 2 + 1
            )
            page.draw_line(
                fitz.Point(original.rect.width, 0),
                fitz.Point(original.rect.width, height),
                color=(0.7, 0.7, 0.7),
                width=0.8,
            )
        doc_out.save(output_path, deflate=True, garbage=3)
    finally:
        doc_dual.close()
        doc_out.close()
    return output_path


def run_job(job: dict[str, Any], emit: Emit, token: CancelToken) -> dict[str, Any]:
    if config.MOCK:
        return run_mock(job, emit, token)
    return run_real(job, emit, token)


def cleanup_dir(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)
