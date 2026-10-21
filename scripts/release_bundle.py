"""Build-time helpers for a relocatable, self-contained macOS resource tree."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import sqlite3
import subprocess
import zipfile
from pathlib import Path

from scripts.font_profile import FONT_NAMES, restrict_metadata_file


def assert_clean_bundle(root: Path) -> None:
    """Reject build caches and private runtime data before signing a release."""
    forbidden = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache",
                 ".next", "node_modules", ".git"}
    for path in root.rglob("*"):
        if (set(path.relative_to(root).parts) & forbidden
                or path.suffix in {".pyc", ".pyo", ".log", ".db", ".sqlite", ".sqlite3"}
                or path.name in {".env", "user.json", ".DS_Store"}):
            raise ValueError(f"Cache/private file must not enter the App: {path.relative_to(root)}")


def prune_runtime(destination: Path, minor: str) -> dict:
    """Remove build tools and unused C APIs, then keep only the host CPU slice."""
    def size():
        return sum(p.stat().st_size for p in destination.rglob("*")
                   if p.is_file() and not p.is_symlink())

    before = size()
    site = destination / f"lib/python{minor}/site-packages"
    removed = []
    paths = [site / "pip", *site.glob("pip-*.dist-info")]
    paths += [destination / f"lib/python{minor}" / name for name in ("ensurepip", "idlelib", "turtledemo", "tkinter")]
    # The native UI is WebKit; no backend feature uses Python's Tcl/Tk GUI.
    paths += [p for pattern in ("tcl*", "tk*", "itcl*", "thread*", "libtcl*", "libtk*")
              for p in destination.joinpath("lib").glob(pattern)]
    paths += list(destination.joinpath(f"lib/python{minor}/lib-dynload").glob("_tkinter*"))
    paths += [destination / "bin" / name for name in ("pip", "pip3", f"pip{minor}", "idle3", f"idle{minor}", f"python{minor}-config")]
    paths += [p for p in (site / "onnx").rglob("*") if p.suffix in {".cc", ".cpp", ".h", ".hpp", ".c"}]
    for path in paths:
        if path.exists() or path.is_symlink():
            removed.append(str(path.relative_to(destination)))
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()

    natives = []
    thinned = 0
    for path in destination.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as handle:
            magic = handle.read(4)
        if magic not in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf"}:
            continue
        if magic in {b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf"}:
            temporary = path.with_name(path.name + ".translator-thin")
            subprocess.run(["xcrun", "lipo", str(path), "-thin", platform.machine(), "-output", str(temporary)], check=True)
            temporary.replace(path)
            thinned += 1
        natives.append(path)

    # Both current Python/ORT entrypoints have their runtime statically linked.
    # Keep a candidate if any other native library actually links to it.
    candidates = [*destination.joinpath("lib").glob("libpython*.dylib"),
                  *site.joinpath("onnxruntime/capi").glob("libonnxruntime.*.dylib")]
    consumers = [str(p) for p in natives if p not in candidates]
    links = subprocess.check_output(["otool", "-L", *consumers], text=True)
    for path in candidates:
        if not any(path.name in line for line in links.splitlines() if line.startswith("\t")):
            removed.append(str(path.relative_to(destination)))
            path.unlink()
    # Remove aliases of pruned developer tools/C APIs as well. Dangling
    # symlinks would fail macOS's deep bundle signature verification.
    for path in destination.rglob("*"):
        if path.is_symlink() and not path.exists():
            removed.append(str(path.relative_to(destination)))
            path.unlink()
    return {"saved_bytes": before - size(), "thinned_binaries": thinned, "removed_files": removed}


def interpreter_info(python: Path) -> dict:
    code = r"""
import importlib.metadata as md, json, re, sys, sysconfig
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
all_packages = {canonicalize_name(d.metadata['Name']): d for d in md.distributions()}
# Our App uses the Python API and WKWebView, never the upstream Gradio GUI.
# Preserve upstream metadata/licenses; only omit GUI-only dependency edges.
gui = {'gradio', 'gradio-i18n', 'gradio-pdf'}
selected, extras = set(), {}
pending = [('pdf2zh-next', set()), ('fastapi', set()), ('uvicorn', {'standard'}),
           ('python-multipart', set()), ('bitstring', set()), ('tomlkit', set())]
while pending:
    name, requested = pending.pop()
    name = canonicalize_name(name)
    combined = extras.get(name, set()) | requested
    if name in selected and combined == extras[name]:
        continue
    selected.add(name)
    extras[name] = combined
    for raw in all_packages[name].requires or []:
        requirement = Requirement(raw)
        if name == 'pdf2zh-next' and canonicalize_name(requirement.name) in gui:
            continue
        if requirement.marker and not any(requirement.marker.evaluate({'extra': e}) for e in {''} | combined):
            continue
        pending.append((requirement.name, set(requirement.extras)))
minimum = (13, 0)
packages = []
for name in sorted(selected):
    d = all_packages[name]
    tags = re.findall(r'macosx_(\d+)_(\d+)_(?:arm64|universal2)', d.read_text('WHEEL') or '')
    if tags:
        minimum = max(minimum, min(tuple(map(int, version)) for version in tags))
    packages.append({'name': d.metadata['Name'], 'version': d.version,
        'license': d.metadata.get('License-Expression') or d.metadata.get('License', ''),
        'files': [str(f) for f in d.files or []],
        'entrypoints': {e.name:e.value for e in d.entry_points if e.group == 'console_scripts'}})
print(json.dumps({'base':sys.base_prefix, 'site':sysconfig.get_paths()['purelib'],
    'version':sys.version.split()[0], 'minor':f'{sys.version_info.major}.{sys.version_info.minor}',
    'minimum_macos':'.'.join(map(str,minimum)), 'packages':packages,
    'excluded_gui_packages':sorted(set(all_packages) - selected)}))
"""
    return json.loads(subprocess.check_output([str(python), "-B", "-c", code], text=True))


def copy_runtime(python: Path, destination: Path) -> dict:
    info = interpreter_info(python)
    base = Path(info["base"])
    if base == Path(info["site"]).parents[2]:
        raise ValueError("Use a clean virtual environment built from standalone CPython")
    ignored = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "_virtualenv.py", "_virtualenv.pth")
    shutil.copytree(base, destination, symlinks=True, ignore=ignored)
    site = destination / f"lib/python{info['minor']}/site-packages"
    # Copy wheel-owned runtime files, not every package installed in the build env.
    for package in info["packages"]:
        for filename in package.pop("files"):
            relative = Path(filename)
            # Console scripts are regenerated below; never follow RECORD outside site.
            if relative.is_absolute() or ".." in relative.parts:
                continue
            if set(relative.parts) & {"__pycache__", "tests", "test"} or relative.suffix in {".pyc", ".pyo"}:
                continue
            original = Path(info["site"]) / relative
            target = site / relative
            if original.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, target, follow_symlinks=False)
    # Build headers/manual pages are not used by the embedded API runtime.
    for directory in (destination / "include", destination / "share/man"):
        if directory.exists():
            shutil.rmtree(directory)
    if next(p["version"] for p in info["packages"] if p["name"].lower() == "babeldoc") != "0.6.2":
        raise ValueError("Review the simplified font profile before changing BabelDOC version")
    info["font_profile"] = restrict_metadata_file(site / "babeldoc/assets/embedding_assets_metadata.py")
    for package in info["packages"]:
        for name in package["entrypoints"]:
            if Path(name).name != name:
                raise ValueError("Unexpected console entrypoint name")
            script = destination / "bin" / name
            script.write_text(
                "#!/usr/bin/env python" + info["minor"] + "\n"
                "import sys\nfrom importlib.metadata import entry_points\n"
                f"sys.exit(next(e for e in entry_points(group='console_scripts') if e.name == {name!r}).load()())\n"
            )
            script.chmod(0o755)
    info["runtime_pruning"] = prune_runtime(destination, info["minor"])
    # Do not preserve any absolute symlink back to the build host.
    for path in destination.rglob("*"):
        if path.is_symlink():
            resolved = path.resolve()
            if not resolved.exists() or not resolved.is_relative_to(destination.resolve()):
                raise ValueError(f"Non-relocatable runtime symlink: {path.relative_to(destination)}")
    return info


def copy_engine_assets(python: Path, destination: Path) -> int:
    code = """
import json
from babeldoc.assets.assets import generate_all_assets_file_list
from babeldoc.const import CACHE_FOLDER
print(json.dumps({'cache':str(CACHE_FOLDER),'files':generate_all_assets_file_list()}))
"""
    info = json.loads(subprocess.check_output([str(python), "-B", "-c", code], text=True))
    manifest = {}
    # The same allowlist is applied to the bundled engine's runtime metadata.
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_LZMA) as archive:
        for category, items in info["files"].items():
            for item in items:
                if category == "fonts" and item["name"] not in FONT_NAMES:
                    continue
                relative = Path(category) / item["name"]
                original = Path(info["cache"]) / relative
                with original.open("rb") as handle:
                    digest = hashlib.file_digest(handle, "sha3_256").hexdigest()
                if digest != item["sha3_256"]:
                    raise ValueError(f"Engine asset missing or invalid: {relative}; run BabelDOC warmup")
                archive.write(original, relative.as_posix())
                manifest[relative.as_posix()] = digest
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
    return len(manifest)


def copy_backend(root: Path, destination: Path) -> None:
    for original in (root / "server").rglob("*.py"):
        relative = original.relative_to(root / "server")
        if "tests" in relative.parts or "__pycache__" in relative.parts:
            continue
        target = destination / "server" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
    ui = destination / "ui"
    ui.mkdir()
    for name in ("__init__.py", "config_manager.py", "glossary_manager.py"):
        shutil.copyfile(root / "ui" / name, ui / name)
    shutil.copytree(root / "web/out", destination / "web/out")


def sign_native_files(root: Path) -> int:
    magic = {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf"}
    count = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as handle:
            if handle.read(4) not in magic:
                continue
        subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(path)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        count += 1
    return count


def migrate_local_data(source: Path, destination: Path) -> bool:
    """Installation-only copy: never called while creating the distributed App."""
    database = source / "jobs.db"
    if not database.exists() or (destination / "jobs.db").exists():
        return False
    destination.mkdir(parents=True, exist_ok=True)
    temporary = destination / "jobs.migrating.db"
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as old:
            active = old.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            if active:
                raise RuntimeError("Wait for active translation jobs before installing")
            with sqlite3.connect(temporary) as new:
                old.backup(new)
        for name in ("uploads", "outputs"):
            if (source / name).is_dir():
                shutil.copytree(source / name, destination / name, dirs_exist_ok=True)
        def rebase(value: str) -> str:
            path = Path(value)
            for ancestor in path.parents:
                if ancestor.exists() and ancestor.samefile(source):
                    return str(destination / path.relative_to(ancestor))
            return value

        # Also handles the old Translator vs translator casing on macOS.
        with sqlite3.connect(temporary) as db:
            for job_id, directory, files in db.execute("SELECT id,output_dir,output_files FROM jobs").fetchall():
                output_files = {key: rebase(value) for key, value in json.loads(files).items()}
                db.execute("UPDATE jobs SET output_dir=?,output_files=? WHERE id=?",
                           (rebase(directory), json.dumps(output_files), job_id))
        temporary.replace(destination / "jobs.db")
    finally:
        temporary.unlink(missing_ok=True)
    return True
