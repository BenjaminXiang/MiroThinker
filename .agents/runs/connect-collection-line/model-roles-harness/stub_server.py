"""Scratch static+API stub for a real-browser pass over /admin (I page slice).

Serves the **real** static assets from the worktree and the fixtures the DOM
harness uses (`.agents/runs/connect-collection-line/model-roles-harness`), so the
browser sees the shipped page with contract-shaped payloads. Not a service: binds
127.0.0.1 on a free port, serves until killed, and is never pointed at 18188.

    uv run python .agents/runs/connect-collection-line/model-roles-harness/stub_server.py
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import sys
import time

FIXTURES = Path(__file__).with_name("fixtures.json")
REPO = Path(__file__).resolve().parents[4]
STATIC = REPO / "apps" / "admin-console" / "backend" / "static"
DATA = json.loads(FIXTURES.read_text(encoding="utf-8"))

# Which answer the models probe gives per key; override on the command line
# (`stub_server.py PORT llm=ok rerank=unauthorized`). The payloads are the real
# ones dumped by dump_fixtures.py, not hand-written shapes.
MODELS_MODE = {"llm": "ok", "rerank": "many"}
MODES = {
    "ok": "modelsOk",
    "many": "modelsMany",
    "unauthorized": "modelsUnauthorized",
    "timeout": "modelsTimeout",
    "unreachable": "modelsUnreachable",
}
# How `POST /connections/test` answers per connection, so one 「全部测试」 run shows
# mixed outcomes (`stub_server.py PORT test:rerank=fail test:serper=rate_limited`).
# Default = a plain 200; `fail` = a reachable endpoint with a rejected credential.
TEST_MODE: dict[str, str] = {}


def _request_url(base: str, fallback: str) -> str:
    """Mirror the server-side join: a base already ending in /v1 is not doubled."""

    if not base:
        return fallback
    root = base.rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/models"
    return f"{root}/v1/models"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:  # keep the harness output readable
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: object, status: int = 200) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json")

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return {}

    def do_GET(self) -> None:  # noqa: N802 - http.server's spelling
        route = self.path.split("?")[0]
        if route in {"/admin", "/admin/"}:
            return self._send(200, (STATIC / "admin.html").read_bytes(), "text/html; charset=utf-8")
        if route.startswith("/static/"):
            name = route[len("/static/") :]
            target = STATIC / name
            types = {
                ".js": "application/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".html": "text/html; charset=utf-8",
                ".png": "image/png",
                ".svg": "image/svg+xml",
            }
            if target.is_file():
                return self._send(
                    200, target.read_bytes(), types.get(target.suffix, "application/octet-stream")
                )
            return self._json({"detail": "not found"}, status=404)
        if route.endswith("/admin/config"):
            return self._json(DATA["config"])
        if route.endswith("/admin/secrets"):
            return self._json(DATA["secrets"])
        if route.endswith("/admin/connections/presets"):
            return self._json(DATA["presets"])
        if route.endswith("/admin/system-status"):
            return self._json({"state": "ok", "freshness": {}, "storage": {}, "disk": {}})
        # What the shared nav script needs: an identity, and the gate signal.
        if route == "/api/auth/me":
            return self._json({"username": "operator"})
        if route.endswith("/admin/jobs"):
            return self._json({"postgres": {"available": True}, "tasks": []})
        return self._json({"detail": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        route = self.path.split("?")[0]
        match = re.search(r"/admin/connections/([^/]+)/models$", route)
        if match:
            key = match.group(1)
            mode = MODELS_MODE.get(key, "ok")
            shape = MODES.get(mode, "modelsOk")
            body = self._read_body()
            base = str(body.get("base_url") or "").rstrip("/")
            payload = dict(DATA[shape])
            if payload.get("request_url"):
                payload["request_url"] = _request_url(base, payload["request_url"])
            if mode == "timeout":
                time.sleep(3.5)  # the page's own 3 s guard must fire first
            return self._json(payload)
        if route.endswith("/admin/connections/test"):
            body = self._read_body()
            key = str(body.get("connection") or "")
            mode = TEST_MODE.get(key, "ok")
            if mode == "rate_limited":
                return self._json(
                    {
                        "detail": {
                            "error": "rate_limited",
                            "connection": key,
                            "retry_after_seconds": 43,
                        }
                    },
                    status=429,
                )
            ok = mode != "fail"
            return self._json(
                {
                    "connection": key,
                    "label": key,
                    "ok": ok,
                    "latency_ms": 63,
                    "http_status": 200 if ok else 401,
                    "detail": "HTTP 200" if ok else "HTTP 401：端点可达，凭据被拒绝",
                    "called": True,
                    "runtime": {"enabled": True},
                    "used": {
                        "api_key_source": "request" if body.get("api_key") else "managed-file",
                        "effective_api_key_source": "managed-file",
                        "endpoint_source": "request" if body.get("base_url") else "runtime",
                        "base_url": body.get("base_url"),
                        "model": body.get("model"),
                    },
                    "rate": {"per_minute_limit": 6, "min_interval_seconds": 1.0, "remaining": 4},
                    "restart_required": None,
                }
            )
        return self._json({"detail": "not found"}, status=404)

    def do_PATCH(self) -> None:  # noqa: N802
        route = self.path.split("?")[0]
        body = self._read_body()
        if route.endswith("/admin/config"):
            return self._json({**DATA["config"], "changed": _changed_paths(body)})
        if route.endswith("/admin/secrets"):
            values = body.get("values") or {}
            return self._json(
                {**DATA["secrets"], "changed": sorted(values), "audit_written": True}
            )
        return self._json({"detail": "not found"}, status=404)


def _changed_paths(body: dict, prefix: str = "") -> list[str]:
    paths: list[str] = []
    for key, value in body.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            paths.extend(_changed_paths(value, f"{path}."))
        else:
            paths.append(path)
    return sorted(paths)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18321
    for argument in sys.argv[2:]:
        key, _, mode = argument.partition("=")
        if key.startswith("test:"):
            TEST_MODE[key[len("test:") :]] = mode or "ok"
        else:
            MODELS_MODE[key] = mode or "ok"
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(
        f"stub serving /admin on http://127.0.0.1:{port} "
        f"models={MODELS_MODE} test={TEST_MODE} (ctrl-c to stop)",
        flush=True,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
