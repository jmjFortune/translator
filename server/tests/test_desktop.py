"""Desktop service lifecycle and reversible bundle installation."""

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(os.name != "posix", reason="macOS launcher process groups")
def test_desktop_server_binds_private_socket_and_exits(tmp_path):
    ready = tmp_path / "ready.json"
    environment = {**os.environ, "PDF2ZH_MOCK": "1", "PDF2ZH_DATA_DIR": str(tmp_path / "data")}
    process = subprocess.Popen([sys.executable, "-m", "server.desktop", "--ready-file", str(ready)],
                               cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        info = json.loads(ready.read_text())
        assert info["pid"] == process.pid
        assert os.getpgid(process.pid) == process.pid
        with httpx.Client(trust_env=False) as client:
            response = None
            while time.monotonic() < deadline:
                try:
                    response = client.get(info["url"] + "/api/health")
                    if response.status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.05)
            assert response is not None and response.json()["mock"] is True
        process.terminate()
        process.wait(timeout=5)
        with httpx.Client(trust_env=False) as client, pytest.raises(httpx.ConnectError):
            client.get(info["url"] + "/api/health")
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def test_install_keeps_original_bundle_backup(tmp_path):
    spec = importlib.util.spec_from_file_location("macos_builder", ROOT / "scripts/build_macos_app.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    old, new = tmp_path / "installed.app", tmp_path / "new.app"
    old.mkdir()
    new.mkdir()
    (old / "version").write_text("legacy")
    (new / "version").write_text("webkit")
    backup = builder.install_bundle(new, old, tmp_path / "backups")
    assert (old / "version").read_text() == "webkit"
    assert (backup / "version").read_text() == "legacy"
    assert (new / "version").read_text() == "webkit"


def test_install_restores_original_when_copy_fails(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("macos_builder", ROOT / "scripts/build_macos_app.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    old, new = tmp_path / "installed.app", tmp_path / "new.app"
    old.mkdir()
    new.mkdir()
    (old / "version").write_text("legacy")

    def failed_copy(source, destination, **kwargs):
        destination.mkdir()
        (destination / "partial").write_text("incomplete")
        raise OSError("simulated interrupted copy")

    monkeypatch.setattr(builder.shutil, "copytree", failed_copy)
    with pytest.raises(OSError, match="interrupted copy"):
        builder.install_bundle(new, old, tmp_path / "backups")
    assert (old / "version").read_text() == "legacy"
    assert not (old / "partial").exists()
