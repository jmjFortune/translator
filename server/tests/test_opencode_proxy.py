"""Exercise the real loopback bridge against a local upstream server."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from server.services.opencode_proxy import opencode_bridge


def test_headers_authorization_isolation_and_shutdown():
    requests = []

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            requests.append({"path": self.path, "headers": dict(self.headers),
                             "body": self.rfile.read(int(self.headers["Content-Length"]))})
            body = json.dumps({"choices": [{"message": {"content": "translated"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    try:
        upstream_url = f"http://127.0.0.1:{upstream.server_port}/v1"
        with httpx.Client(trust_env=False) as client:
            with opencode_bridge(upstream_url, "upstream-test-secret") as (url, key):
                assert key != "upstream-test-secret"
                assert client.post(f"{url}/chat/completions", json={}).status_code == 403
                assert client.post(f"{url}/other", headers={"Authorization": f"Bearer {key}"}).status_code == 403
                for _ in range(2):
                    response = client.post(f"{url}/chat/completions", json={"model": "test"},
                                           headers={"Authorization": f"Bearer {key}"})
                    assert response.status_code == 200
                    assert response.json()["choices"][0]["message"]["content"] == "translated"
            with opencode_bridge(upstream_url, "second-test-secret") as (url, key):
                client.post(f"{url}/chat/completions", json={}, headers={"Authorization": f"Bearer {key}"})
        assert len(requests) == 3
        assert requests[0]["path"] == "/v1/chat/completions"
        assert requests[0]["headers"]["Authorization"] == "Bearer upstream-test-secret"
        assert requests[0]["headers"]["User-Agent"] == "translator/1.0"
        assert requests[0]["headers"]["x-opencode-session"] == requests[1]["headers"]["x-opencode-session"]
        assert requests[0]["headers"]["x-opencode-session"] != requests[2]["headers"]["x-opencode-session"]
        assert json.loads(requests[0]["body"]) == {"model": "test"}
    finally:
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=2)
