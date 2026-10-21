"""Critical standalone packaging boundaries and user-history migration."""

import hashlib
import importlib.util
import json
import runpy
import sqlite3
import zipfile
from pathlib import Path

import pytest

from scripts.release_bundle import assert_clean_bundle, copy_backend, migrate_local_data, prune_runtime
from scripts.font_profile import FONT_NAMES, restrict_metadata_file
from server.desktop_assets import seed_assets


@pytest.mark.parametrize("relative", ["runtime/__pycache__/module.pyc", "web/.next/cache/data", "backend/jobs.db", "backend/.env"])
def test_release_rejects_caches_and_private_data(tmp_path, relative):
    file = tmp_path / relative
    file.parent.mkdir(parents=True)
    file.write_bytes(b"must not ship")
    with pytest.raises(ValueError, match="Cache/private"):
        assert_clean_bundle(tmp_path)


def test_slim_fonts_keep_styles_and_do_not_redownload_regional_families(tmp_path):
    spec = importlib.util.find_spec("babeldoc")
    if spec is None:
        pytest.skip("Requires the optional real translation engine")
    original = Path(spec.origin).parent / "assets/embedding_assets_metadata.py"
    metadata = tmp_path / "metadata.py"
    metadata.write_bytes(original.read_bytes())
    full = runpy.run_path(str(metadata))
    restrict_metadata_file(metadata)
    slim = runpy.run_path(str(metadata))
    # This is the map used by both warmup and individual font downloads.
    assert set(slim["EMBEDDING_FONT_METADATA"]) == FONT_NAMES
    for lang in full["ALL_FONT_FAMILY"]:
        for kind, fonts in slim["get_font_family"](lang).items():
            assert fonts, (lang, kind)
            assert fonts == [f for f in full["get_font_family"](lang)[kind] if f in FONT_NAMES]
    assert slim["get_font_family"]("CN")["normal"][0] == "SourceHanSerifCN-Bold.ttf"
    assert "NotoSans-BoldItalic.ttf" in slim["get_font_family"]("EN")["script"]


def test_runtime_pruning_keeps_linked_libraries_and_application_files(tmp_path, monkeypatch):
    site = tmp_path / "lib/python3.12/site-packages"
    linked = tmp_path / "lib/libpython3.12.dylib"
    unused = site / "onnxruntime/capi/libonnxruntime.1.31.0.dylib"
    consumer = site / "application.so"
    for path in (linked, unused, consumer):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xcf\xfa\xed\xfefixture")
    alias = unused.with_name("libonnxruntime.dylib")
    alias.symlink_to(unused.name)
    (site / "pip").mkdir()
    (site / "pip/__init__.py").write_text("build tool")
    (site / "application.py").write_text("runtime code")
    monkeypatch.setattr("scripts.release_bundle.subprocess.check_output",
                        lambda *args, **kwargs: "application.so:\n\t@rpath/libpython3.12.dylib (compatibility version 3.12)\n")
    report = prune_runtime(tmp_path, "3.12")
    assert linked.is_file() and consumer.is_file()
    assert not unused.exists() and not alias.is_symlink() and not (site / "pip").exists()
    assert (site / "application.py").read_text() == "runtime code"
    assert report["saved_bytes"] > 0


def test_seed_assets_validates_and_skips_existing(tmp_path):
    source, cache = tmp_path / "bundle", tmp_path / "cache"
    (source / "models").mkdir(parents=True)
    data = b"public-model-fixture"
    (source / "models/model.onnx").write_bytes(data)
    (source / "private-cache.db").write_bytes(b"must not be copied")
    (source / "manifest.json").write_text(json.dumps({"models/model.onnx": hashlib.sha3_256(data).hexdigest()}))
    assert seed_assets(source, cache) == 1
    assert seed_assets(source, cache) == 0
    assert not (cache / "private-cache.db").exists()
    (cache / "models/model.onnx").write_bytes(b"damaged")
    assert seed_assets(source, cache) == 1
    (source / "models/model.onnx").write_bytes(b"tampered")
    (cache / "models/model.onnx").unlink()
    with pytest.raises(ValueError, match="Invalid bundled"):
        seed_assets(source, cache)


@pytest.mark.parametrize("path", ["../private", "/etc/private", "cache/private.db"])
def test_seed_assets_rejects_unexpected_paths(tmp_path, path):
    (tmp_path / "manifest.json").write_text(json.dumps({path: "0" * 64}))
    with pytest.raises(ValueError):
        seed_assets(tmp_path, tmp_path / "destination")


def test_compressed_assets_verify_before_publishing(tmp_path):
    archive, cache = tmp_path / "assets.zip", tmp_path / "cache"
    data = b"verified font"
    manifest = {"fonts/body.ttf": hashlib.sha3_256(data).hexdigest()}
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest))
        bundle.writestr("fonts/body.ttf", b"corrupt")
    with pytest.raises(ValueError, match="Invalid bundled"):
        seed_assets(archive, cache)
    assert not (cache / "fonts/body.ttf").exists()
    assert not list(cache.rglob("*.translator-tmp"))
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest))
        bundle.writestr("fonts/body.ttf", data)
    assert seed_assets(archive, cache) == 1
    assert seed_assets(archive, cache) == 0


def test_migration_preserves_history_and_rebases_output_paths(tmp_path):
    source, destination = tmp_path / "old", tmp_path / "new"
    original = source / "outputs/job/source/paper.pdf"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"original-user-document")
    output = source / "outputs/job/mono.pdf"
    output.write_bytes(b"user-output")
    with sqlite3.connect(source / "jobs.db") as db:
        db.execute("CREATE TABLE jobs (id TEXT, status TEXT, output_dir TEXT, output_files TEXT)")
        db.execute("INSERT INTO jobs VALUES ('job','done',?,?)",
                   (str(output.parent), json.dumps({"mono": str(output)})))
    assert migrate_local_data(source, destination)
    with sqlite3.connect(destination / "jobs.db") as db:
        directory, files = db.execute("SELECT output_dir,output_files FROM jobs").fetchone()
    assert directory == str(destination / "outputs/job")
    assert json.loads(files)["mono"] == str(destination / "outputs/job/mono.pdf")
    assert (Path(directory) / "source/paper.pdf").read_bytes() == b"original-user-document"
    assert original.exists() and output.exists()
    assert not migrate_local_data(source, destination)


def test_backend_copy_excludes_private_and_test_files(tmp_path):
    source, destination = tmp_path / "repo", tmp_path / "app"
    for relative in ("server/main.py", "server/tests/test_api.py", "server/private.env",
                     "ui/__init__.py", "ui/config_manager.py", "ui/glossary_manager.py", "web/out/index.html"):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    copy_backend(source, destination)
    assert (destination / "server/main.py").exists()
    assert not (destination / "server/tests").exists()
    assert not (destination / "server/private.env").exists()
