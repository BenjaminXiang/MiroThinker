#!/usr/bin/env python3
"""Stand-in rerank endpoint that answers with a malformed payload.

Used for the live fault-injection instance: the serving process points its
rerank base URL at this stub, so the adapter must reject the payload and the
answer must fall back to the deterministic order. Stopping this stub mid-batch
turns the next turn into a connection-refused case on the same instance.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 18099


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        body = json.dumps({"results": [{"index": 0, "relevance_score": "not-a-number"}]})
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
