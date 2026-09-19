"""Serve the shipped `/jobs` page plus a stub jobs API, for a real-browser look at the page.

Run from `apps/admin-console`, after `make_payload.py`:

    uv run python ../../.agents/runs/connect-collection-line/jobs-page-harness/stub_server.py 18325
    # -> http://127.0.0.1:18325/jobs

Loopback only, stdlib only, no app code and no dependency: the payload comes from
`JOBS_HARNESS_OUT/payload.json` (default `/tmp/jobs-harness`), the page and the nav script
from the repository. Not part of the application.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse

REPO = Path(os.environ.get("JOBS_HARNESS_REPO", Path(__file__).resolve().parents[4]))
OUT = Path(os.environ.get("JOBS_HARNESS_OUT", "/tmp/jobs-harness"))
FIXTURE = json.loads((OUT / "payload.json").read_text(encoding="utf-8"))
PAGE = REPO / "apps/admin-console/backend/static/jobs.html"
NAV = REPO / "apps/admin-console/backend/static/nav_auth.js"
API = "/api/canonical-v2/admin/jobs"


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: object) -> None:
        self._send(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:  # noqa: N802 - http.server's method name
        path = urlparse(self.path).path
        if path in ("/", "/jobs"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/static/nav_auth.js":
            self._send(200, NAV.read_bytes(), "text/javascript; charset=utf-8")
            return
        if path == "/api/auth/me":
            # The shipped nav bounces a signed-out browser back to /main; the stub is the
            # signed-in operator so the page under test stays on screen.
            self._json(200, {"username": "ops"})
            return
        if path == API:
            self._json(200, FIXTURE["payload"])
            return
        if path.startswith(API + "/"):
            rest = unquote(path[len(API) + 1 :])
            if rest.endswith("/runs"):
                task_id = rest[: -len("/runs")]
                self._json(200, {"task_id": task_id, "runs": FIXTURE["runs"].get(task_id, [])})
                return
            if rest.startswith("runs/"):
                self._json(
                    200,
                    {
                        "run_id": rest[len("runs/") :],
                        "status": "succeeded",
                        "trigger_source": "manual",
                        "operator": "ops",
                        "duration_ms": 1000,
                        "exit_code": 0,
                        "items_processed": 1,
                        "command": ["uv"],
                        "stderr_excerpt": "",
                        "stdout_excerpt": "",
                    },
                )
                return
        self._json(404, {"detail": "not found"})

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - http.server's name
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18325
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"stub /jobs on http://127.0.0.1:{port}/jobs (payload from {OUT})", flush=True)
    server.serve_forever()
