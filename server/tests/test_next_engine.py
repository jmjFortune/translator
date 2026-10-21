"""Engine contract tests against the installed pdf2zh-next settings models.

The stream is stubbed: no model downloads, API credentials or translation
service are needed. Run these with Python 3.11-3.13 and server/requirements.txt.
"""

from __future__ import annotations

import asyncio
import csv
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("pdf2zh_next")
import fitz
import pdf2zh_next.high_level as high_level

from server.services import credentials
from server.services.next_engine import build_settings, engine_settings
from server.services.translate import CancelledError, CancelToken, _run_stream, parse_page_range, run_real


def _pdf(path: Path, texts: list[str]):
    with fitz.open() as doc:
        for text in texts:
            page = doc.new_page()
            page.insert_text((72, 72), text)
        doc.save(path)


@pytest.fixture
def job(tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    _pdf(source, ["original one", "original two", "original three"])
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(credentials, "build_envs", lambda service: {})
    return {
        "source_path": str(source), "filename": source.name,
        "output_dir": str(output),
        "options": {"service": "bing", "lang_in": "en", "lang_out": "zh"},
    }


@pytest.mark.parametrize("spec", credentials.SERVICES, ids=lambda spec: spec.id)
def test_every_advertised_service_has_valid_engine(spec):
    envs = {name: "test-key" for name in [spec.api_env, *[key for key, _ in spec.extras]] if name}
    if spec.id == "openailiked":
        envs.update(OPENAILIKED_BASE_URL="https://example.com/v1", OPENAILIKED_MODEL="test-model")
    engine = engine_settings(spec.id, envs)
    engine.validate_settings()


def test_saved_endpoint_and_model_take_precedence():
    engine = engine_settings("deepseek", {
        "DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_BASE_URL": "https://example.com/v1",
        "DEEPSEEK_MODEL": "saved-model",
    })
    assert engine.openai_base_url == "https://example.com/v1"
    assert engine.openai_model == "saved-model"


def test_settings_preserve_options_and_glossary(job):
    job["options"].update(service="openai", thread=7, ocr=True, translate_tables=True,
                          auto_glossary=True, glossary={"comma, term": "换行\n术语"})
    settings = build_settings(job, {"OPENAI_API_KEY": "test-key"}, [0, 2], ["mono", "dual"])
    assert settings.pdf.pages == "1,3"
    assert settings.pdf.only_include_translated_page is True
    assert settings.pdf.use_alternating_pages_dual is True
    assert settings.pdf.dual_translate_first is False
    assert settings.pdf.watermark_output_mode == "no_watermark"
    assert settings.pdf.ocr_workaround is True
    assert settings.pdf.translate_table_text is True
    assert settings.translation.qps == settings.translation.pool_max_workers == 7
    assert settings.translation.no_auto_extract_glossary is False
    assert settings.translation.save_auto_extracted_glossary is True
    with Path(settings.translation.glossaries).open(newline="", encoding="utf-8") as handle:
        assert list(csv.DictReader(handle)) == [{"source": "comma, term", "target": "换行\n术语"}]


def test_non_llm_glossary_does_not_break_bing(job):
    job["options"].update(auto_glossary=True, glossary={"term": "术语"})
    settings = build_settings(job, {}, None, ["side_by_side"])
    assert settings.translation.glossaries is None
    assert settings.translation.no_auto_extract_glossary is True
    assert settings.pdf.no_mono is True
    assert settings.pdf.no_dual is False


def test_selected_pages_and_all_download_formats(job, monkeypatch):
    job["options"]["page_range"] = "2,3"
    output = Path(job["output_dir"])

    async def stream(settings, source):
        assert source == Path(job["source_path"])
        assert settings.pdf.pages == "2,3"
        yield {"type": "progress_update", "stage": "Translate", "overall_progress": 37.5}
        mono, dual = output / "mono.pdf", output / "dual.pdf"
        _pdf(mono, ["translated two", "translated three"])
        _pdf(dual, ["original two", "translated two", "original three", "translated three"])
        yield {"type": "finish", "translate_result": SimpleNamespace(mono_pdf_path=mono, dual_pdf_path=dual)}

    monkeypatch.setattr(high_level, "do_translate_async_stream", stream)
    events = []
    result = run_real(job, lambda kind, **data: events.append((kind, data)), CancelToken())
    assert set(result["files"]) == {"mono", "dual", "side_by_side"}
    assert result["pages"] == 3
    assert ("progress", {"current": 37, "total": 100}) in events
    with fitz.open(result["files"]["mono"]) as doc:
        assert len(doc) == 2
    with fitz.open(result["files"]["side_by_side"]) as doc:
        assert len(doc) == 2
        assert doc[0].rect.width == 1190
        assert "original two" in doc[0].get_text() and "translated two" in doc[0].get_text()


def test_side_only_keeps_no_extra_downloads(job, monkeypatch):
    job["options"]["output_formats"] = ["side_by_side"]
    dual = Path(job["output_dir"]) / "dual.pdf"

    async def stream(settings, source):
        assert settings.pdf.no_mono is True
        _pdf(dual, ["original", "translated"])
        yield {"type": "finish", "translate_result": SimpleNamespace(dual_pdf_path=dual)}

    monkeypatch.setattr(high_level, "do_translate_async_stream", stream)
    result = run_real(job, lambda *args, **kwargs: None, CancelToken())
    assert set(result["files"]) == {"side_by_side"}
    assert not dual.exists()


def test_cancel_interrupts_quiet_stream_and_closes_it(monkeypatch, tmp_path):
    token = CancelToken()
    closed = threading.Event()

    async def stream(settings, source):
        try:
            token.cancel()
            await asyncio.sleep(30)
            yield {"type": "finish"}
        finally:
            closed.set()

    monkeypatch.setattr(high_level, "do_translate_async_stream", stream)
    with pytest.raises(CancelledError):
        asyncio.run(asyncio.wait_for(_run_stream(None, tmp_path, lambda *a, **k: None, token), timeout=2))
    assert closed.is_set()


@pytest.mark.parametrize("event", [None, {"type": "error", "error": "upstream failed"},
                                   {"type": "finish", "translate_result": SimpleNamespace()}])
def test_empty_error_and_missing_output_fail_job(job, monkeypatch, event):
    async def stream(settings, source):
        if event:
            yield event

    monkeypatch.setattr(high_level, "do_translate_async_stream", stream)
    with pytest.raises(RuntimeError):
        run_real(job, lambda *a, **k: None, CancelToken())


def test_pages_outside_document_fail_before_translation(job, monkeypatch):
    job["options"]["page_range"] = "99"
    with pytest.raises(ValueError, match="页码"):
        run_real(job, lambda *a, **k: None, CancelToken())


@pytest.mark.parametrize("value", ["0", "3-1", "-1", ",", "one"])
def test_invalid_page_ranges(value):
    with pytest.raises(ValueError):
        parse_page_range(value)
