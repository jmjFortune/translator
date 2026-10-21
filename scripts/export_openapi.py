#!/usr/bin/env python3
"""Export the FastAPI schema to docs/openapi.json (single source for the frontend)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.main import app  # noqa: E402

if __name__ == "__main__":
    target = ROOT / "docs" / "openapi.json"
    target.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {target}")
