#!/usr/bin/env python3
"""对话模型（llm）连接测试探针：登录 → POST /connections/test {"connection":"llm"} → 打印结论。

用途：证明"页面保存的凭据在下次启动后真的生效"（看运行期凭据来源是否由
legacy-file 变成受管/环境来源）。不打印任何密钥。

用法： llm_probe.py <port> <state_dir> [out_json]
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


import os as _os

_password_file = _os.environ.get("MIROTHINKER_ADMIN_PASSWORD_FILE", "")
if _password_file:
    password = Path(_password_file).read_text(encoding="utf-8").strip()
else:
    password = (STATE / "admin-initial-password.txt").read_text(encoding="utf-8").strip()
report: dict[str, object] = {"login": call("POST", "/api/auth/login", {"username": "admin", "password": password})[0]}

code, text = call("POST", "/api/canonical-v2/admin/connections/test", {"connection": "llm"})
try:
    body = json.loads(text)
except json.JSONDecodeError:
    body = text[:600]
report["llm_test"] = {"status": code, "body": body}

# 运行期凭据来源（config 视图里与 llm 有关的那几条）
code2, text2 = call("GET", "/api/canonical-v2/admin/config")
report["config_status"] = code2
try:
    cfg = json.loads(text2)
except json.JSONDecodeError:
    cfg = {}
def walk(node, prefix=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{prefix}[{i}]")
    else:
        yield prefix, node
report["llm_origin_fields"] = {
    k: v for k, v in walk(cfg) if "llm" in k.lower() and any(t in k.lower() for t in ("origin", "source", "profile", "key"))
}
print(json.dumps(report, ensure_ascii=False, indent=2))
if OUT:
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
