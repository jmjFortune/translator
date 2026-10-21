#!/usr/bin/env python3
"""Run the API from the repository root: python server/run.py"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(
        "server.main:app",
        host=os.environ.get("PDF2ZH_HOST", "127.0.0.1"),
        port=int(os.environ.get("PDF2ZH_PORT", "8000")),
        reload=os.environ.get("PDF2ZH_RELOAD", "1") == "1",
    )
