#!/usr/bin/env python3
"""Build a standalone macOS App, or an explicit lightweight development launcher."""

from __future__ import annotations

import argparse
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.release_bundle import assert_clean_bundle, copy_backend, copy_engine_assets, copy_runtime, migrate_local_data, sign_native_files


def install_bundle(source: Path, destination: Path, backups: Path) -> Path | None:
    backup = None
    if destination.exists():
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / f"{destination.stem}-{datetime.now():%Y%m%d-%H%M%S-%f}.app"
        shutil.move(str(destination), backup)
    try:
        shutil.copytree(source, destination, symlinks=True)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        if backup:
            shutil.move(str(backup), destination)
        raise
    return backup


def build(output: Path, python: Path, development: bool = False) -> None:
    if not (ROOT / "web/out/index.html").is_file():
        raise SystemExit("Build the frontend first: cd web && PDF2ZH_STATIC_EXPORT=1 npm run build")
    subprocess.run([str(python), "-B", "-c", "import sys; assert (3,11) <= sys.version_info[:2] < (3,14); import uvicorn, pdf2zh_next"], check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="macos-build-", dir=output.parent) as work:
        bundle = Path(work) / "translator.app"
        contents = bundle / "Contents"
        executable = contents / "MacOS/translator"
        resources = contents / "Resources"
        executable.parent.mkdir(parents=True)
        resources.mkdir()
        minimum_macos = "13.0"
        subprocess.run([
            "xcrun", "swiftc", "-swift-version", "5", "-parse-as-library", "-O", "-target", f"{platform.machine()}-apple-macos13.0",
            "-framework", "AppKit", "-framework", "WebKit", "-framework", "UniformTypeIdentifiers",
            str(ROOT / "scripts/macos_app.swift"), "-o", str(executable),
        ], check=True)
        shutil.copyfile(ROOT / "assets/AppIcon.icns", resources / "TranslatorIcon.icns")
        if development:
            launcher = {"mode": "development", "projectRoot": str(ROOT), "python": str(python.absolute())}
        else:
            info = copy_runtime(python, resources / "runtime")
            minimum_macos = info["minimum_macos"]
            copy_backend(ROOT, resources / "backend")
            asset_count = copy_engine_assets(python, resources / "engine-assets.zip")
            launcher = {"mode": "bundled", "projectRoot": "backend", "python": f"runtime/bin/python{info['minor']}"}
            # Test the copied runtime, not the fuller build environment. A lazy
            # health endpoint cannot detect a missing translation dependency.
            validation_home = Path(work) / "validation-home"
            validation_home.mkdir()
            subprocess.run([
                str(resources / launcher["python"]), "-I", "-B", "-c",
                "from pdf2zh_next.high_level import do_translate_async_stream; "
                "from babeldoc.assets.embedding_assets_metadata import EMBEDDING_FONT_METADATA; "
                "assert len(EMBEDDING_FONT_METADATA) == 15; print('Bundled engine API imports verified')",
            ], check=True, cwd=resources / "backend", env={
                "HOME": str(validation_home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "PYTHONDONTWRITEBYTECODE": "1", "LANG": "en_US.UTF-8",
                "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
            })
            native_count = sign_native_files(resources / "runtime")
            packages = [{k: v for k, v in item.items() if k != "entrypoints"} for item in info["packages"]]
            (resources / "THIRD_PARTY_PACKAGES.json").write_text(json.dumps(packages, indent=2) + "\n")
            (resources / "FONT_PROFILE.json").write_text(json.dumps(info["font_profile"], indent=2) + "\n")
            (resources / "RUNTIME_PRUNING.json").write_text(json.dumps(info["runtime_pruning"], indent=2) + "\n")
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            (resources / "build.json").write_text(json.dumps({
                "version": "3.0.0", "architecture": platform.machine(), "python": info["version"],
                "mode": "bundled", "source_commit": revision, "static_assets": asset_count,
                "minimum_macos": minimum_macos,
                "font_profile": info["font_profile"]["name"],
                "dependency_profile": "Python API only; upstream Gradio GUI excluded",
                "excluded_gui_packages": info["excluded_gui_packages"],
                "native_binaries": native_count, "signing": "ad-hoc; not notarized",
            }, indent=2) + "\n")
            print(f"Bundled Python {info['version']}, {len(packages)} packages, {asset_count} verified engine assets, {native_count} native binaries", flush=True)
        (resources / "launcher.json").write_text(json.dumps(launcher) + "\n")
        with (contents / "Info.plist").open("wb") as handle:
            plistlib.dump({
                "CFBundleExecutable": "translator", "CFBundleName": "translator",
                "CFBundleDisplayName": "translator", "CFBundleIdentifier": "com.aarongig.pdf2zh.fixed",
                "CFBundlePackageType": "APPL", "CFBundleInfoDictionaryVersion": "6.0",
                "CFBundleShortVersionString": "3.0.0", "CFBundleVersion": "3.0.1",
                "CFBundleIconFile": "TranslatorIcon.icns", "LSMinimumSystemVersion": minimum_macos,
                "NSHighResolutionCapable": True, "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
                "LSApplicationCategoryType": "public.app-category.productivity",
            }, handle)
        assert_clean_bundle(bundle)
        subprocess.run(["codesign", "--force", "--sign", "-", str(bundle)], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
        if output.exists():
            marker = output / "Contents/Resources/launcher.json"
            if not marker.is_file():
                raise SystemExit(f"Refusing to replace an unrelated output bundle: {output}")
            prior = json.loads(marker.read_text())
            if prior.get("mode") != "bundled" and prior.get("projectRoot") != str(ROOT):
                raise SystemExit(f"Refusing to replace an unrelated output bundle: {output}")
            shutil.rmtree(output)
        shutil.move(str(bundle), output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=ROOT / ".venv-release/bin/python")
    parser.add_argument("--output", type=Path, default=ROOT / "pdf2zh_files/release.noindex/translator.app")
    parser.add_argument("--development", action="store_true", help="Explicit absolute-path launcher; not distributable")
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("This launcher uses the macOS SDK and must be built on macOS.")
    build(args.output.absolute(), args.python, args.development)
    print(f"Built: {args.output}")
    if args.install:
        destination = Path("/Applications/translator.app")
        if not args.development:
            migrated = migrate_local_data(ROOT / "pdf2zh_files", Path.home() / "Library/Application Support/translator/pdf2zh_files")
            if migrated:
                print("Existing local translation history copied to Application Support; original retained")
        backup = install_bundle(args.output, destination, Path.home() / "Library/Application Support/pdf2zh/backups")
        if backup:
            print(f"Previous app saved: {backup}")
        register = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
        subprocess.run([register, "-f", str(destination)], check=True)
        print(f"Installed: {destination}")


if __name__ == "__main__":
    main()
