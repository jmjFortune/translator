"""Start a private loopback server for the macOS launcher.

The socket stays bound while Uvicorn starts, so choosing an ephemeral port
does not race another process. The native parent owns this process group.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
from pathlib import Path

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()
    if hasattr(os, "setsid") and os.getpgrp() != os.getpid():
        os.setsid()

    if source := os.environ.get("PDF2ZH_ASSET_SOURCE"):
        from .desktop_assets import seed_assets

        count = seed_assets(Path(source), Path.home() / ".cache/babeldoc")
        print(f"Engine assets ready ({count} copied)", flush=True)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(socket.SOMAXCONN)
        port = listener.getsockname()[1]
        args.ready_file.write_text(json.dumps({"url": f"http://127.0.0.1:{port}", "pid": os.getpid()}))
        try:
            server = uvicorn.Server(uvicorn.Config("server.main:app", log_level="info"))
            server.run(sockets=[listener])
        finally:
            args.ready_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
