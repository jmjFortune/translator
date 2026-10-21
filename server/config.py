"""Runtime paths and switches for the pdf2zh-next API server."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = Path(os.environ.get("PDF2ZH_DATA_DIR", ROOT / "pdf2zh_files")).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
DB_PATH = Path(os.environ.get("PDF2ZH_DB_PATH", DATA_DIR / "jobs.db")).resolve()

WEB_OUT = ROOT / "web" / "out"
APP_NAME = "translator API"
APP_VERSION = "1.0.0"

MAX_UPLOAD_MB = int(os.environ.get("PDF2ZH_MAX_UPLOAD_MB", "200"))
MAX_WORKERS = int(os.environ.get("PDF2ZH_WORKERS", "2"))
MOCK = os.environ.get("PDF2ZH_MOCK", "").lower() in {"1", "true", "yes", "on"}

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "PDF2ZH_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

for _dir in (DATA_DIR, UPLOAD_DIR, OUTPUT_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
