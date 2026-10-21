"""Per-job loopback bridge for OpenCode Go's required HTTP headers.

pdf2zh-next's OpenAI settings do not expose headers. Keeping the bridge local
to one job also works with the engine's spawned processes, without patching
global SDK state or putting credentials in command lines or config files.
"""

from __future__ import annotations

import secrets
import threading
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx


@contextmanager
def opencode_bridge(base_url: str, api_key: str):
    bridge_key = secrets.token_urlsafe(32)
    session_id = str(uuid.uuid4())
    upstream = base_url.rstrip("/").removesuffix("/chat/completions")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never log authorization headers or request content.

        def do_POST(self):
            if self.path != "/v1/chat/completions" or self.headers.get("Authorization") != f"Bearer {bridge_key}":
                self.send_error(403)
                return
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            try:
                # pdf2zh-next uses non-streaming chat completions.
                with httpx.Client(timeout=120) as client:
                    response = client.post(
                        f"{upstream}/chat/completions",
                        content=body,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                            "User-Agent": "translator/1.0",
                            "x-opencode-session": session_id,
                        },
                    )
                self.send_response(response.status_code)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(response.content)))
                if retry_after := response.headers.get("Retry-After"):
                    self.send_header("Retry-After", retry_after)
                self.end_headers()
                self.wfile.write(response.content)
            except httpx.HTTPError:
                self.send_error(502, "OpenCode Go request failed")
            except (BrokenPipeError, ConnectionResetError):
                pass  # The engine was cancelled while a request was in flight.

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", bridge_key
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
