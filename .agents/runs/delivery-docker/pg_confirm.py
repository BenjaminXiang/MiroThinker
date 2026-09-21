#!/usr/bin/env python3
"""Task A 最终镜像上的"快速确认"：登录 + 采集面 + 既有 run 行（**不新建 seed、不触发采集**）。

用法： pg_confirm.py <port> <state_dir> <out_json>
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

PORT = sys.argv[1]
STATE = Path(sys.argv[2])
OUT = Path(sys.argv[3])
BASE = f"http://127.0.0.1:{PORT}"
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

# 上一轮真跑出来的 preview run（job 侧 run_id；见 verification.md Task A 表）
KNOWN_RUN_IDS = ["e9fbc5ce-bb4d-460b-8fee-bbb4c5c3fc0c"]


def call(method: str, path: str, payload: object = None, timeout: int = 60):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json", "Origin": BASE, "Referer": BASE + "/main"},
    )
    try:
        with OPENER.open(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def body(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


report: dict[str, object] = {}
password = (STATE / "admin-initial-password.txt").read_text(encoding="utf-8").strip()
status, _ = call("POST", "/api/auth/login", {"username": "admin", "password": password})
report["login"] = status
report["whoami"] = body(call("GET", "/api/auth/me")[1])

pages = {}
for path in ("/seeds", "/upload", "/jobs", "/admin"):
    pages[path] = call("GET", path)[0]
report["pages"] = pages

apis = {}
for path in (
    "/api/canonical-v2/admin/seeds",
    "/api/canonical-v2/admin/uploads",
    "/api/canonical-v2/admin/jobs",
    "/api/canonical-v2/admin/system-status",
):
    code, text = call("GET", path)
    payload = body(text)
    summary: object = payload
    if isinstance(payload, list):
        summary = f"list[{len(payload)}]"
    elif isinstance(payload, dict):
        summary = {k: payload[k] for k in list(payload)[:8]}
    apis[path] = {"status": code, "summary": summary}
report["apis"] = apis

# 既有 run 行（证明 /jobs 能看到那一跑，且不产生新的采集）
runs = {}
for run_id in KNOWN_RUN_IDS:
    code, text = call("GET", f"/api/canonical-v2/admin/jobs/runs/{run_id}")
    payload = body(text)
    runs[run_id] = {
        "status": code,
        "run_status": (payload or {}).get("status") if isinstance(payload, dict) else None,
        "duration_ms": (payload or {}).get("duration_ms") if isinstance(payload, dict) else None,
        "summary": (payload or {}).get("summary") if isinstance(payload, dict) else None,
    }
report["known_runs"] = runs

status_code, text = call("GET", "/api/canonical-v2/admin/system-status")
payload = body(text) or {}
report["admin_panel"] = {
    "status": status_code,
    "freshness_state": (payload.get("freshness") or {}).get("state"),
    "collection": payload.get("collection"),
    "state": payload.get("state"),
}

OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({
    "login": report["login"],
    "pages": pages,
    "api_status": {k: v["status"] for k, v in apis.items()},
    "known_run": runs[KNOWN_RUN_IDS[0]]["run_status"],
    "freshness": report["admin_panel"]["freshness_state"],
}, ensure_ascii=False))
