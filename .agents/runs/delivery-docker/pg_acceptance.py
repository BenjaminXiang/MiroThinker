#!/usr/bin/env python3
"""Task A 验收（宿主机侧，纯标准库）：登录 → 采集面 → 一个 preview 采集 → 管理面面板。

用法： pg_acceptance.py <base_url_host_port> <state_dir> <out_json_path>

只读约定：
* admin 口令从状态目录的 admin-initial-password.txt 读进内存，**从不打印**；
* 只触发一次 preview（不触发 full/sample），最多花一次采集配额；
* 所有输出落到 <out_json_path>，终端只打摘要。
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE = ""
OPENER = None
REPORT: dict[str, object] = {}
SEED_URL_CANDIDATES = [
    # 这些 URL 能命中内置的 school adapter（roster.py 的 _SCHOOL_ROSTER_ADAPTERS），
    # 否则 preview 会在 adapter_missing 上失败（第一次实测就是如此）。
    "https://www.sustech.edu.cn/zh/letter",       # sustech-roster
    "https://www.szu.edu.cn/szdw",                # szu-teacher-family
    "https://www.hitsz.edu.cn/",                  # hitsz-college-teacher-family
]


def _build(base: str) -> None:
    global BASE, OPENER
    BASE = base
    jar = CookieJar()
    OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(method: str, path: str, payload: object = None, timeout: int = 180) -> tuple[int, str]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/html;q=0.9",
            # 写方法会被同源检查拦下（admin_gate.py:136-139）⇒ 必须带 Origin
            "Origin": BASE,
            "Referer": BASE + "/main",
        },
    )
    try:
        with OPENER.open(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def json_body(body: str) -> object:
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def main() -> int:
    _build(f"http://127.0.0.1:{sys.argv[1]}")
    state_dir = Path(sys.argv[2])
    out_path = Path(sys.argv[3])
    password_path = state_dir / "admin-initial-password.txt"
    password = password_path.read_text(encoding="utf-8").strip()
    username = "admin"

    # --- 1. 登录 ---------------------------------------------------------------
    status, body = call("POST", "/api/auth/login", {"username": username, "password": password})
    REPORT["login"] = {"status": status, "user": username, "password_len": len(password)}
    me_status, me_body = call("GET", "/api/auth/me")
    REPORT["whoami"] = {"status": me_status, "body": json_body(me_body)}

    # --- 2. 采集面（页面 + API）------------------------------------------------
    surfaces: dict[str, object] = {}
    for path in ("/seeds", "/upload", "/jobs", "/browse", "/logs", "/admin"):
        code, _ = call("GET", path)
        surfaces[f"page{path}"] = code
    for path in (
        "/api/canonical-v2/admin/seeds",
        "/api/canonical-v2/admin/uploads",
        "/api/canonical-v2/admin/jobs",
        "/api/canonical-v2/admin/system-status",
        "/api/canonical-v2/admin/config",
    ):
        code, body = call("GET", path)
        payload = json_body(body)
        summary: object = payload
        if isinstance(payload, list):
            summary = f"list[{len(payload)}]"
        elif isinstance(payload, dict):
            summary = {k: payload[k] for k in list(payload)[:10]}
        surfaces[f"api{path}"] = {"status": code, "summary": summary}
    REPORT["surfaces"] = surfaces

    # --- 3. 建一条 seed（预览用），并挑一个容器内可达的 URL ---------------------
    seeds_before = json_body(call("GET", "/api/canonical-v2/admin/seeds")[1]) or []
    seed_id = None
    chosen_url = None
    created = None
    for candidate in SEED_URL_CANDIDATES:
        code, body = call(
            "POST",
            "/api/canonical-v2/admin/seeds",
            {"school": "容器交付验收（合成）", "department": "preview 冒烟",
             "seed_url": candidate},
        )
        if code in (200, 201):
            created = json_body(body)
            chosen_url = candidate
            if isinstance(created, dict):
                seed_id = created.get("id")
            break
        created = {"status": code, "body": body[:300]}
    REPORT["seed"] = {
        "count_before": len(seeds_before),
        "created": created,
        "seed_id": seed_id,
        "seed_url": chosen_url,
    }
    if seed_id is None:
        REPORT["preview"] = {"skipped": "seed could not be created"}
        out_path.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"phase": "seed-failed", "detail": created}, ensure_ascii=False))
        return 1

    # --- 4. 触发一次 preview（唯一一次采集）------------------------------------
    trigger_started = time.time()
    code, body = call("POST", f"/api/canonical-v2/admin/seeds/{seed_id}/trigger", {"mode": "preview"})
    trigger_payload = json_body(body)
    run_id = None
    if isinstance(trigger_payload, dict):
        run_id = trigger_payload.get("run_id")
    REPORT["preview"] = {
        "trigger_status": code,
        "trigger_body": trigger_payload if isinstance(trigger_payload, dict) else body[:300],
        "run_id": run_id,
    }

    # --- 5. 有界轮询 run 状态 --------------------------------------------------
    if run_id:
        deadline = time.time() + 600
        terminal = False
        last: dict[str, object] = {}
        while time.time() < deadline:
            for path in (f"/api/canonical-v2/admin/seeds/{seed_id}/runs", "/api/canonical-v2/admin/jobs"):
                code, body = call("GET", path)
                payload = json_body(body)
                if isinstance(payload, dict):
                    for item in payload.get("runs", []) or []:
                        if isinstance(item, dict) and str(item.get("run_id")) == str(run_id):
                            last = item
                            status = str(item.get("status", ""))
                            if status in {"success", "failed", "error", "interrupted", "cancelled"}:
                                terminal = True
                    for item in payload.get("items", []) or []:
                        if isinstance(item, dict) and str(item.get("run_id")) == str(run_id):
                            last = item
                            status = str(item.get("status", ""))
                            if status in {"success", "failed", "error", "interrupted", "cancelled"}:
                                terminal = True
                if terminal:
                    break
            if terminal:
                break
            time.sleep(5)
        REPORT["preview"]["seconds"] = round(time.time() - trigger_started, 1)
        REPORT["preview"]["terminal"] = terminal
        REPORT["preview"]["run_detail"] = last
        detail_code, detail_body = call("GET", f"/api/canonical-v2/admin/jobs/runs/{run_id}")
        REPORT["preview"]["run_detail_status"] = detail_code
        REPORT["preview"]["run_detail_body"] = json_body(detail_body) or detail_body[:1500]

    # --- 6. 管理面 system-status（采集/新鲜度面板）------------------------------
    code, body = call("GET", "/api/canonical-v2/admin/system-status")
    payload = json_body(body)
    REPORT["admin_system_status"] = {"status": code, "body": payload if payload else body[:1500]}

    # --- 7. seed 行与 run 行的最终状态（给 pg_dump 对账用）----------------------
    code, body = call("GET", f"/api/canonical-v2/admin/seeds/{seed_id}")
    REPORT["seed_after"] = {"status": code, "body": json_body(body)}
    code, body = call("GET", f"/api/canonical-v2/admin/seeds/{seed_id}/runs")
    REPORT["seed_runs"] = {"status": code, "body": json_body(body)}

    out_path.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(
        {
            "phase": "done",
            "login_status": REPORT["login"]["status"],
            "preview_trigger": REPORT["preview"].get("trigger_status"),
            "preview_run_id": run_id,
            "preview_terminal": REPORT["preview"].get("terminal"),
            "preview_seconds": REPORT["preview"].get("seconds"),
        },
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
