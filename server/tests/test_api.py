"""Smoke tests for the API. Run: .venv/bin/python -m pytest server/tests -q"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="pdf2zh-test-"))
(TMP / "home").mkdir(parents=True, exist_ok=True)
os.environ["PDF2ZH_MOCK"] = "1"
os.environ["PDF2ZH_DATA_DIR"] = str(TMP / "data")
os.environ["HOME"] = str(TMP / "home")

from contextlib import contextmanager  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from server.jobs import manager  # noqa: E402
from server.main import app  # noqa: E402

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"

_client_instance = TestClient(app)


@contextmanager
def _client():
    # Do not use TestClient as a context manager here: that runs the lifespan
    # shutdown after every test and permanently closes the job executor.
    yield _client_instance


def _create_job(client: TestClient, **data) -> dict:
    payload = {
        "lang_in": "en",
        "lang_out": "zh",
        "service": "google",
        "output_formats": "mono,dual,side_by_side",
        "mock_pages": "3",
        **data,
    }
    response = client.post(
        "/api/jobs",
        files={"file": ("sample.pdf", PDF_BYTES, "application/pdf")},
        data=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_health() -> None:
    with _client() as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["mock"] is True


def test_job_lifecycle_and_download() -> None:
    with _client() as client:
        job = _create_job(client)
        finished = manager.wait(job["id"], timeout=10)
        assert finished is not None
        assert finished["status"] == "done", finished
        assert set(finished["files"]) == {"mono", "dual", "side_by_side"}

        files = client.get(f"/api/jobs/{job['id']}/files").json()
        assert set(files) == {"mono", "dual", "side_by_side"}

        download = client.get(files["mono"])
        assert download.status_code == 200
        assert download.content.startswith(b"%PDF")


def test_cancel() -> None:
    with _client() as client:
        job = _create_job(client, mock_pages="50")
        response = client.post(f"/api/jobs/{job['id']}/cancel")
        assert response.status_code == 200
        final = manager.wait(job["id"], timeout=10)
        assert final is not None
        assert final["status"] in {"cancelled", "done"}


def test_papers_list_and_content() -> None:
    with _client() as client:
        job = _create_job(client, output_formats="mono")
        manager.wait(job["id"], timeout=10)

        papers = client.get("/api/papers").json()
        assert any(paper["id"] == job["id"] for paper in papers)

        content = client.get(f"/api/papers/{job['id']}/content").json()
        assert content["id"] == job["id"]
        assert content["has_content"] is False
        assert content["sections"] == []

        assert client.delete(f"/api/papers/{job['id']}").status_code == 200
        assert client.get(f"/api/papers/{job['id']}").status_code == 404


def test_settings_never_returns_secret() -> None:
    with _client() as client:
        initial = client.get("/api/settings")
        assert initial.status_code == 200
        assert "services" in initial.json()

        response = client.put(
            "/api/settings",
            json={"services": [{"id": "openai", "api_key": "sk-test-secret"}]},
        )
        assert response.status_code == 200
        assert "sk-test-secret" not in response.text

        services = {item["id"]: item for item in response.json()["services"]}
        assert services["openai"]["has_key"] is True

        client.put("/api/settings", json={"services": [{"id": "openai", "api_key": ""}]})
        services = {
            item["id"]: item
            for item in client.get("/api/settings").json()["services"]
        }
        assert services["openai"]["has_key"] is False


def test_glossary() -> None:
    with _client() as client:
        initial = client.get("/api/glossary")
        assert initial.status_code == 200
        assert "学术通用" in initial.json()["presets"]

        replaced = client.put("/api/glossary", json={"terms": {"Transformer": "Transformer"}})
        assert replaced.status_code == 200
        assert replaced.json()["terms"] == {"Transformer": "Transformer"}

        added = client.post("/api/glossary/terms", json={"term": "Attention", "zh": "注意力"})
        assert added.status_code == 200
        assert added.json()["terms"]["Attention"] == "注意力"

        removed = client.delete("/api/glossary/terms", params={"term": "Attention"})
        assert removed.status_code == 200
        assert "Attention" not in removed.json()["terms"]


def test_unavailable_legacy_services_are_not_advertised() -> None:
    from server.api import settings

    with _client() as client:
        services = {item["id"] for item in client.get("/api/settings").json()["services"]}
        assert not {"argos", "deeplx"} & services
        for service in ("argos", "deeplx"):
            response = client.post(
                "/api/jobs", files={"file": ("sample.pdf", PDF_BYTES, "application/pdf")},
                data={"service": service},
            )
            assert response.status_code == 400
            assert settings._defaults({"service": service}).service == "bing"


def test_original_inline_preview_and_sse_resume() -> None:
    import json

    with _client() as client:
        job = _create_job(client)
        final = manager.wait(job["id"], timeout=10)
        assert final["status"] == "done"
        original = client.get(f"/api/jobs/{job['id']}/download/original?inline=true")
        assert original.status_code == 200
        assert original.content == PDF_BYTES
        assert original.headers["content-disposition"].startswith("inline;")
        mono = client.get(f"/api/jobs/{job['id']}/download/mono?inline=true")
        assert mono.content.startswith(b"%PDF")
        assert mono.headers["content-disposition"].startswith("inline;")
        attachment = client.get(f"/api/jobs/{job['id']}/download/mono")
        assert attachment.headers["content-disposition"].startswith("attachment;")

        events = manager.events_since(job["id"], 0)
        cursor = events[-2]["seq"]
        resumed = client.get(f"/api/jobs/{job['id']}/events", headers={"Last-Event-ID": str(cursor)})
        received = [json.loads(line[6:]) for line in resumed.text.splitlines() if line.startswith("data: ")]
        assert received and all(event["seq"] > cursor for event in received)
        assert received[-1]["type"] == "done"


def test_original_preview_after_server_restart(monkeypatch) -> None:
    from server import db

    with _client() as client:
        job = _create_job(client, output_formats="mono")
        assert manager.wait(job["id"], timeout=10)["status"] == "done"
        # A restarted server reads only the persisted row, which has no
        # source_path column; the upload is still in output_dir/source.
        monkeypatch.setattr(manager, "get", db.get_job)
        preview = client.get(f"/api/jobs/{job['id']}/download/original?inline=true")
        assert preview.status_code == 200
        assert preview.content == PDF_BYTES


def test_settings_reports_environment_credentials_without_exposing_them(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "environment-test-secret")
    with _client() as client:
        response = client.get("/api/settings")
        services = {service["id"]: service for service in response.json()["services"]}
        assert services["openai"]["has_key"] is True
        assert "environment-test-secret" not in response.text
        assert services["ollama"]["needs_key"] is False
