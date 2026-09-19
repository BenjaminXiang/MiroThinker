"""Serve the shipped `/seeds` page plus a stub seeds API, for a real-browser look at the page.

Run from `apps/admin-console`:

    uv run python ../../.agents/runs/connect-collection-line/seeds-page-harness/stub_server.py 18326
    # -> http://127.0.0.1:18326/seeds

Loopback only, stdlib only, no app code and no dependency: the rows are fixtures shaped like
the live registry (long school and department names), the page and the nav script come from the
repository, and a trigger POST is only recorded — no crawl is started. Not part of the
application.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import urlparse

REPO = Path(os.environ.get("SEEDS_HARNESS_REPO", Path(__file__).resolve().parents[4]))
PAGE = REPO / "apps/admin-console/backend/static/seeds.html"
NAV = REPO / "apps/admin-console/backend/static/nav_auth.js"
API = "/api/canonical-v2/admin"

SEEDS = [
    {
        "id": 12,
        "school": "哈尔滨工业大学（深圳）",
        "department": "计算机科学与技术学院",
        "seed_url": "https://www.hitsz.edu.cn/szdw/jsjkxyjsxy.htm",
        "last_run_status": "success",
        "last_run_at": "2026-09-18T02:31:00Z",
    },
    {
        "id": 18,
        "school": "清华大学深圳国际研究生院",
        "department": "信息科学与技术学部",
        "seed_url": "https://www.sigs.tsinghua.edu.cn/szdw/xxkxyjsxb.htm",
        "last_run_status": "failure",
        "last_run_at": "2026-09-17T22:05:00Z",
    },
    {
        "id": 30,
        "school": "南方科技大学",
        "department": "计算机科学与工程系",
        "seed_url": "https://www.sustech.edu.cn/szdw.htm",
        "last_run_status": "never_run",
        "last_run_at": None,
    },
    {
        "id": 31,
        "school": "深圳大学",
        "department": None,
        "seed_url": "https://www.szu.edu.cn/teachers.htm",
        "last_run_status": "in_progress",
        "last_run_at": "2026-09-19T03:10:00Z",
    },
]

RUNS = [
    {
        "run_id": "9f2c4d1a-0000-0000-0000-000000000000",
        "task_id": "admin-seed-refresh-sample",
        "status": "failed",
        "trigger_source": "manual",
        "operator": "ops",
        "started_at": "2026-09-18T02:31:00Z",
        "exit_code": 1,
        "stderr_excerpt": "TimeoutError: page read exceeded 20 s on https://www.hitsz.edu.cn/szdw/jsjkxyjsxy.htm",
        "summary": {"job_summary": {"trigger_mode": "sample"}},
    },
    {
        "run_id": "1a2b3c4d-0000-0000-0000-000000000000",
        "task_id": "admin-seed-refresh",
        "status": "succeeded",
        "trigger_source": "manual",
        "operator": "ops",
        "started_at": "2026-09-17T22:05:00Z",
        "exit_code": 0,
        "stderr_excerpt": "",
        "summary": {"job_summary": {"trigger_mode": "preview"}},
    },
]

TRIGGERS: list[dict[str, object]] = []


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
        if path in ("/", "/seeds"):
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
        if path == API + "/seeds":
            self._json(200, SEEDS)
            return
        if path.startswith(API + "/seeds/") and path.endswith("/runs"):
            self._json(200, {"seed_id": 12, "total": len(RUNS), "runs": RUNS})
            return
        self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - http.server's method name
        path = urlparse(self.path).path
        if path.startswith(API + "/seeds/") and path.endswith("/trigger"):
            length = int(self.headers.get("Content-Length") or 0)
            TRIGGERS.append(
                {"path": path, "body": json.loads(self.rfile.read(length) or b"{}")}
            )
            print(f"trigger #{len(TRIGGERS)}: {path} {TRIGGERS[-1]['body']}", flush=True)
            self._json(
                202,
                {
                    "run_id": "stub-run",
                    "seed_id": 12,
                    "status": "running",
                    "task_id": "admin-seed-refresh",
                    "mode": "preview",
                    "skip_reason": None,
                },
            )
            return
        self._json(404, {"detail": "not found"})

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - http.server's name
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18326
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"stub /seeds on http://127.0.0.1:{port}/seeds", flush=True)
    server.serve_forever()
