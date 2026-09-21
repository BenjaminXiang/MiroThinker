#!/usr/bin/env python3
"""嵌入凭据探针：登录 → POST /connections/test {"connection":"embedding"} → 打印结论。

口令从状态目录读（从不回显）。只打印连接测试的 HTTP 状态与响应体（响应体里是
ok/http_status/latency/来源标注，不含密钥原文）。

用法： key_probe.py <port> <state_dir> [out_json]
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
OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else None
BASE = f"http://127.0.0.1:{PORT}"
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def call(method: str, path: str, payload: object = None, timeout: int = 90):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json", "Origin": BASE, "Referer": BASE + "/main"},
    )
    try:
        with OPENER.open(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


password = (STATE / "admin-initial-password.txt").read_text(encoding="utf-8").strip()
report: dict[str, object] = {}
report["login"] = call("POST", "/api/auth/login", {"username": "admin", "password": password})[0]

code, text = call("POST", "/api/canonical-v2/admin/connections/test", {"connection": "embedding"})
try:
    body = json.loads(text)
except json.JSONDecodeError:
    body = text[:600]
report["embedding_test"] = {"status": code, "body": body}
if isinstance(body, dict):
    used = body.get("used") or {}
    report["summary"] = {
        "ok": body.get("ok"),
        "http_status": body.get("http_status") or body.get("status_code"),
        "dimension": body.get("dimension") or body.get("dimensions") or ((body.get("detail") or {}) if isinstance(body.get("detail"), dict) else {}).get("dimension"),
        "api_key_source": used.get("api_key_source"),
        "endpoint_source": used.get("endpoint_source"),
        "error": body.get("error") or body.get("message"),
    }
print(json.dumps(report, ensure_ascii=False, indent=2))
if OUT:
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
