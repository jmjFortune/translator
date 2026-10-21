"""Seed only verified public engine assets, never translation cache databases."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from contextlib import ExitStack
from pathlib import Path


def seed_assets(source: Path, destination: Path) -> int:
    with ExitStack() as stack:
        if source.is_file():
            archive = stack.enter_context(zipfile.ZipFile(source))
            manifest = json.loads(archive.read("manifest.json"))
            open_asset = archive.open
        else:
            manifest = json.loads((source / "manifest.json").read_text())
            open_asset = lambda name: (source / name).open("rb")
        return _seed_manifest(manifest, open_asset, destination)


def _seed_manifest(manifest, open_asset, destination: Path) -> int:
    copied = 0
    for relative, digest in manifest.items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 2:
            raise ValueError("Invalid engine asset path")
        if path.parts[0] not in {"fonts", "models", "tiktoken", "cmap"}:
            raise ValueError("Unexpected engine asset category")
        target = destination / path
        if target.is_file():
            with target.open("rb") as handle:
                if hashlib.file_digest(handle, "sha3_256").hexdigest() == digest:
                    continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + f".{os.getpid()}.translator-tmp")
        try:
            with open_asset(relative) as original, temporary.open("wb") as output:
                shutil.copyfileobj(original, output)
            with temporary.open("rb") as handle:
                if hashlib.file_digest(handle, "sha3_256").hexdigest() != digest:
                    raise ValueError(f"Invalid bundled engine asset: {relative}")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        copied += 1
    return copied
