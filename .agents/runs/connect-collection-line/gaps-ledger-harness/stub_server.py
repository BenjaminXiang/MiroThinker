"""Serve the shipped `/browse` gaps tab and `/chat` feedback control over a stub API.

Run from `apps/admin-console`:

    uv run python ../../.agents/runs/connect-collection-line/gaps-ledger-harness/stub_server.py 18327
    # -> http://127.0.0.1:18327/browse#gaps  ·  http://127.0.0.1:18327/chat

Loopback only, stdlib only, no app code and no dependency: the ledger rows are fixtures shaped
like the sibling batch's `GET /api/canonical-v2/admin/chat-gaps` contract, the chat stream is a
minimal SSE turn, and a feedback POST is only recorded — nothing reaches a real service. Not
part of the application.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import urlparse

REPO = Path(os.environ.get("GAPS_HARNESS_REPO", Path(__file__).resolve().parents[4]))
STATIC = REPO / "apps/admin-console/backend/static"
API = "/api/canonical-v2/admin"
SESSION_COOKIE = "miroflow_chat_session"

LEDGER = {
    "items": [
        {
            "signal_id": "gap-signal:chat-feedback:sha256:9c1f4e7a2b8d5f3019",
            "session_id": "4f1c9a2e-6d3b-4a71-9c58-2b0e7d1f8a63",
            "turn_id": "turn:log:8b7d1234c5e6f7a8",
            "release_id": "candidate-v2-20260916-r1",
            "feedback_type": "incorrect_answer",
            "note": "结果里有不相关企业",
            "query_trace_id": "query:trace:5a2b6c8d0e1f2a3b",
            "answer_trace_id": "answer:trace:3f9e1d5c7b2a4860",
            "observed_at": "2026-09-20T06:30:00+00:00",
            "recorded_at": "2026-09-20T06:30:00+00:00",
        },
        {
            "signal_id": "gap-signal:chat-feedback:sha256:1a2b3c4d5e6f7081",
            "session_id": "b7d3e5f1-0a92-4c68-bf31-7e5a9c2d4b80",
            "turn_id": "turn:log:1d2e3f4a5b6c7d8e",
            "release_id": "candidate-v2-20260916-r1",
            "feedback_type": "evidence_gap",
            "note": "",
            "query_trace_id": "query:trace:0d9c8b7a6f5e4d3c",
            "answer_trace_id": "answer:trace:7e6d5c4b3a291807",
            "observed_at": "2026-09-19T01:05:00+00:00",
            "recorded_at": "2026-09-19T01:05:00+00:00",
        },
        {
            "signal_id": "gap-signal:chat-feedback:sha256:deadbeefcafe0001",
            "session_id": "4f1c9a2e-6d3b-4a71-9c58-2b0e7d1f8a63",
            "turn_id": "turn:log:9988776655443322",
            "release_id": "candidate-v2-20260916-r1",
            "feedback_type": "unreadable_vendor_code",
            "note": "这台机器上还没见过的类型",
            "query_trace_id": "query:trace:1122334455667788",
            "answer_trace_id": "answer:trace:8877665544332211",
            "observed_at": "2026-09-18T15:59:00+00:00",
            "recorded_at": "2026-09-18T15:59:00+00:00",
        },
    ],
    "total": 3,
    "counts": {"incorrect_answer": 2, "evidence_gap": 1},
}

STATUS = {
    "as_of": "2026-09-20T04:00:00+00:00",
    "domains": [],
    "gap_summary": {"total": 91},
}

ANSWER_TEXT = "共找到 6 个企业：不止技术、华力创科学等。"
SSE_TURN = (
    'event: stage\ndata: {"name":"planning"}\n\n'
    'event: plan_done\ndata: {"views":[{"domain":"company"}]}\n\n'
    'event: stage\ndata: {"name":"retrieval"}\n\n'
    'event: retrieval_done\ndata: {"lanes":[{"lane":"vector","status":"succeeded","candidates":6}]}\n\n'
    'event: stage\ndata: {"name":"synthesis"}\n\n'
    f'event: answer\ndata: {json.dumps({"query_type": "B_company_topic_search", "answer_text": ANSWER_TEXT, "citations": [], "answer_style": "template"}, ensure_ascii=False)}\n\n'
    "event: done\ndata: {}\n\n"
)

FEEDBACK_POSTS: list[dict[str, object]] = []


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str, cookies: tuple[str, ...] = ()) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for cookie in cookies:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: object) -> None:
        self._send(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _page(self, name: str) -> None:
        self._send(200, (STATIC / name).read_bytes(), "text/html; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802 - http.server's method name
        path = urlparse(self.path).path
        if path in ("/", "/browse"):
            self._page("browse.html")
            return
        if path == "/chat":
            self._page("chat.html")
            return
        if path.startswith("/static/"):
            asset = STATIC / path[len("/static/") :]
            if asset.is_file():
                self._send(200, asset.read_bytes(), "text/javascript; charset=utf-8")
                return
        if path == "/api/auth/me":
            # The shipped nav bounces a signed-out browser back to /main; the stub is the
            # signed-in operator so the page under test stays on screen.
            self._json(200, {"username": "ops"})
            return
        if path == API + "/status":
            self._json(200, STATUS)
            return
        if path == API + "/chat-gaps":
            self._json(200, LEDGER)
            return
        self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - http.server's method name
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if path == "/api/chat/stream":
            self._send(
                200,
                SSE_TURN.encode("utf-8"),
                "text/event-stream; charset=utf-8",
                cookies=(f"{SESSION_COOKIE}=stub-session; Path=/; SameSite=Lax",),
            )
            return
        if path == "/api/canonical-v2/chat/feedback":
            if SESSION_COOKIE not in (self.headers.get("Cookie") or ""):
                self._json(409, {"detail": "canonical_v2_feedback_checkpoint_required"})
                return
            FEEDBACK_POSTS.append(json.loads(raw or b"{}"))
            print(f"feedback #{len(FEEDBACK_POSTS)}: {json.dumps(FEEDBACK_POSTS[-1], ensure_ascii=False)}", flush=True)
            self._json(200, {"issue_id": "gap:stub", "status": "filed", "reported_at": None})
            return
        self._json(404, {"detail": "not found"})

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - http.server's name
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18327
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"stub on http://127.0.0.1:{port}/browse#gaps and http://127.0.0.1:{port}/chat", flush=True)
    server.serve_forever()
