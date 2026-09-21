#!/usr/bin/env python3
"""读 /admin 配置视图里的 **chat LLM 运行期凭据来源**（用来证明"页面保存的 key 真的生效"）。

登录 → GET /api/canonical-v2/admin/config → 只打印连接/运行期相关的字段（不含密钥）。

用法： llm_origin.py <port> <state_dir>
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
BASE = f"http://127.0.0.1:{PORT}"
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def call(method: str, path: str, payload: object = None, timeout: int = 60):
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
login = call("POST", "/api/auth/login", {"username": "admin", "password": password})[0]
code, text = call("GET", "/api/canonical-v2/admin/config")
try:
    payload = json.loads(text)
except json.JSONDecodeError:
    print(json.dumps({"login": login, "config_status": code, "raw": text[:400]}, ensure_ascii=False, indent=2))
    raise SystemExit(0)

# 只挑运行期/凭据来源相关字段，避免把整页配置倒出来
interesting: dict[str, object] = {}
stack = [("", payload)]
while stack:
    prefix, node = stack.pop()
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, (dict, list)):
                stack.append((path, value))
            elif any(token in path.lower() for token in ("origin", "source", "profile", "key", "connected", "readonly", "available")):
                interesting[path] = value
    elif isinstance(node, list):
        for index, value in enumerate(node):
            stack.append((f"{prefix}[{index}]", value))

print(json.dumps({"login": login, "config_status": code, "fields": interesting}, ensure_ascii=False, indent=2))
