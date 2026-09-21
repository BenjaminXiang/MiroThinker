#!/usr/bin/env python3
"""嵌入连接测试（含**向量身份校验**）探针 —— 只为看清"跑了哪条臂"。

用法： identity_probe.py <port> <state_dir> <out_json> [--no-identity]

对 POST /api/canonical-v2/admin/connections/test 发两次：
  · {"connection":"embedding"}                     —— 不跑身份校验（基线）
  · {"connection":"embedding","identity_check":true} —— 跑身份校验（reference/index 两臂）
落 JSON 到 out_json，并在 stdout 打印一行摘要（arm / cosine / passed / detail 前 120 字）。
口令从状态目录读，从不打印。
"""

from __future__ import annotations

import json
import time
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path


def main() -> int:
    port = sys.argv[1]
    state = Path(sys.argv[2])
    out = Path(sys.argv[3])
    with_identity = "--no-identity" not in sys.argv[4:]
    base = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def call(method: str, path: str, payload: object = None, timeout: int = 300, retry_429: int = 4):
        """429 = 管理面连接测试有冷却（retry_after_seconds）；按提示退避重试。"""
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        for attempt in range(retry_429 + 1):
            request = urllib.request.Request(
                base + path, data=data, method=method,
                headers={"Content-Type": "application/json", "Origin": base, "Referer": base + "/main"},
            )
            try:
                with opener.open(request, timeout=timeout) as response:
                    return response.status, response.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as exc:
                text = exc.read().decode("utf-8", "replace")
                if exc.code != 429 or attempt == retry_429:
                    return exc.code, text
                wait = 2.0
                try:
                    wait = float(json.loads(text).get("retry_after_seconds") or 0) + 1.5
                except Exception:  # noqa: BLE001
                    pass
                print(f"[identity_probe] 429 rate_limited → 等 {wait:.1f}s 重试（{attempt + 1}/{retry_429}）", file=sys.stderr)
                time.sleep(wait)
        raise AssertionError("unreachable")

    def body(text: str):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    report: dict[str, object] = {}
    password = (state / "admin-initial-password.txt").read_text(encoding="utf-8").strip()
    report["login_status"] = call("POST", "/api/auth/login", {"username": "admin", "password": password})[0]

    code, text = call("POST", "/api/canonical-v2/admin/connections/test", {"connection": "embedding"})
    baseline = body(text)
    report["baseline"] = {"status": code, "body": baseline if baseline is not None else text[:600]}

    identity = None
    if with_identity:
        code, text = call(
            "POST", "/api/canonical-v2/admin/connections/test",
            {"connection": "embedding", "identity_check": True},
        )
        identity = body(text)
        report["identity"] = {"status": code, "body": identity if identity is not None else text[:600]}

    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def pick(node: object, keys: tuple[str, ...]):
        if not isinstance(node, dict):
            return None
        for key in keys:
            if key in node:
                return node[key]
        for value in node.values():
            if isinstance(value, dict):
                found = pick(value, keys)
                if found is not None:
                    return found
            if isinstance(value, list):
                for item in value:
                    found = pick(item, keys)
                    if found is not None:
                        return found
        return None

    def identity_of(node: object):
        """连接测试把身份校验结果放在 body.identity 里（可能为 null）。"""
        if isinstance(node, dict) and isinstance(node.get("identity"), dict):
            return node["identity"]
        return None

    ident = identity_of(identity)
    summary = {
        "login": report["login_status"],
        "baseline_status": report["baseline"]["status"],
        "baseline_identity": identity_of(baseline),
        "identity_status": report["identity"]["status"] if identity is not None else None,
        "arm": (ident or {}).get("arm"),
        "passed": (ident or {}).get("passed"),
        "cosine": (ident or {}).get("cosine", (ident or {}).get("cosine_similarity")),
        "threshold": (ident or {}).get("threshold"),
        "detail": str((ident or {}).get("detail") or "")[:220],
        "checks": (ident or {}).get("checks"),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
