#!/usr/bin/env python3
"""「只填 key」验收探针（宿主机侧，纯标准库）。

做四件事，全部落 JSON 到 out：
  1) 登录（口令从状态目录读，从不打印）
  2) /admin 的配置视图：嵌入端点/模型是否**已预置**、是否只读、档位是什么
  3) 模拟管理员在页面上**点一次「测试」**：POST /connections/test {"connection":"embedding"}
  4) 过 /api/chat/stream 问一个真实问题：query_type / 引用数 / 本地引用数 / 答案开头（判断是否模板降级）

用法： keys_only_probe.py <port> <state_dir> <out_json>
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

PORT = sys.argv[1]
STATE = Path(sys.argv[2])
OUT = Path(sys.argv[3])
BASE = f"http://127.0.0.1:{PORT}"
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
QUESTION = "介绍一下 国际先进技术应用推进中心（深圳）"


def call(method: str, path: str, payload: object = None, timeout: int = 240):
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


def body(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


report: dict[str, object] = {}
password = (STATE / "admin-initial-password.txt").read_text(encoding="utf-8").strip()
report["login"] = call("POST", "/api/auth/login", {"username": "admin", "password": password})[0]

# ---- 2. 配置视图：嵌入端点是否已预置 ----------------------------------------
code, text = call("GET", "/api/canonical-v2/admin/config")
config = body(text)
report["config_status"] = code
if isinstance(config, dict):
    fields = config.get("fields") or config.get("settings") or config
    interesting = {}
    if isinstance(fields, dict):
        for key, value in fields.items():
            if any(t in str(key) for t in ("embedding", "chat_llm", "llm_", "readonly", "source")):
                interesting[str(key)] = value
    report["config_excerpt"] = interesting or {k: config[k] for k in list(config)[:12]}
else:
    report["config_excerpt"] = text[:600]

# ---- 3. 管理员点一次「测试」（嵌入端点）-------------------------------------
code, text = call("POST", "/api/canonical-v2/admin/connections/test", {"connection": "embedding"})
report["embedding_test"] = {"status": code, "body": body(text) or text[:800]}

# ---- 4. 真实问题（看有没有本地引用、是否模板降级）----------------------------
req = urllib.request.Request(
    f"{BASE}/api/chat/stream",
    data=json.dumps({"query": QUESTION}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
started = time.monotonic()
raw = b""
try:
    with OPENER.open(req, timeout=240) as response:
        for chunk in response:
            raw += chunk
except Exception as exc:  # noqa: BLE001
    report["chat"] = {"error": f"{type(exc).__name__}: {exc}"}
else:
    text = raw.decode("utf-8", "replace")
    events: dict[str, int] = {}
    answer: dict = {}
    current = None
    for line in text.splitlines():
        if line.startswith("event: "):
            current = line[7:].strip()
            events[current] = events.get(current, 0) + 1
        elif line.startswith("data: {") and current == "answer":
            try:
                answer = json.loads(line[6:])
            except json.JSONDecodeError:
                pass
    citations = answer.get("citations") or []
    origins = []
    for item in citations:
        if isinstance(item, dict):
            origins.append(str(item.get("url") or item.get("source_locator") or item.get("handle") or "local/?")[:70])
        else:
            origins.append(str(item)[:70])
    answer_text = answer.get("answer_text") or ""
    report["chat"] = {
        "seconds": round(time.monotonic() - started, 1),
        "events": events,
        "query_type": answer.get("query_type"),
        "answer_len": len(answer_text),
        "answer_head": answer_text[:220],
        "degraded_template": answer_text.startswith("（以下为基于本地数据的简要信息）"),
        "citations": len(citations),
        "local_citations": sum(1 for o in origins if not o.startswith("http")),
        "citation_origins": origins[:8],
        "has_error_event": "error" in events,
    }

OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({
    "login": report["login"],
    "config_status": report["config_status"],
    "embedding_test": report["embedding_test"]["status"],
    "chat": {k: v for k, v in report.get("chat", {}).items()
             if k in ("query_type", "answer_len", "citations", "local_citations", "degraded_template", "seconds")},
}, ensure_ascii=False))
