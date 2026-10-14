#!/usr/bin/env python3
"""Dev-line watchdog (100.64.0.4:18188): one rotating demo question per run.

Purpose: the 2026-10-14 episodes of 22–32 s turns (and one 0-web-result turn)
were transient and did not reproduce; this probe turns the next episode into
data — it logs wall time, TTFT, streamed chunk count and the turn's per-lane
timings (read back from the turn-debug dump the serving process already writes).

Install: cron entry every 15 minutes (`7-59/15 * * * *`), see the run log line.

Log: <runs>/lane-watch.log  — one line per run, append-only.
"""

from __future__ import annotations

import json
import pathlib
import time
import urllib.request

BASE = "http://127.0.0.1:18188"
RUNS = pathlib.Path("/home/longxiang/MiroThinker/.agents/runs/close-workbook-gaps")
DEBUG_DIR = RUNS / "turn-debug"
LOG = RUNS / "lane-watch.log"
STATE = RUNS / ".lane-watch-idx"

QUESTIONS = [
    "优必选有哪些专利",
    "丁文伯教授的研究方向",
    "详细介绍国先中心（深圳）",
    "目前主流的JEPA（联合嵌入预测架构）变体有哪些",
    "深圳有哪些做具身智能的公司",
    "丁文伯创办的公司是哪家",
    "本地知识库收录了优必选多少专利",
    "深圳科创数据平台收录了哪些教授",
]


def newest_lane_timings() -> object:
    try:
        files = sorted(
            DEBUG_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True
        )
    except OSError:
        return None
    if not files:
        return None
    newest = files[0]
    if time.time() - newest.stat().st_mtime > 600:
        return None
    try:
        return json.loads(newest.read_text(encoding="utf-8")).get("lane_timings")
    except (OSError, ValueError):
        return None


def main() -> int:
    index = 0
    if STATE.exists():
        try:
            index = int(STATE.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            index = 0
    question = QUESTIONS[index % len(QUESTIONS)]
    STATE.write_text(str((index + 1) % len(QUESTIONS)), encoding="utf-8")

    request = urllib.request.Request(
        BASE + "/api/chat/stream",
        data=json.dumps({"query": question}).encode(),
        headers={
            "Content-Type": "application/json",
            "Cookie": "miroflow_chat_session=probe:lane-watch",
        },
        method="POST",
    )
    start = time.monotonic()
    ttft = None
    chunks = 0
    status = 0
    error = ""
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            status = response.status
            event = None
            for raw in response:
                line = raw.decode("utf-8", "replace").rstrip("\n")
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:") and event:
                    if event == "answer_chunk":
                        chunks += 1
                        if ttft is None:
                            ttft = time.monotonic() - start
                    if event in ("done", "error"):
                        break
    except Exception as exc:  # noqa: BLE001 - the watchdog records, never dies
        error = f"{type(exc).__name__}:{exc}"
    total = time.monotonic() - start

    lanes = newest_lane_timings()
    slow = " SLOW" if total > 30 or any(
        isinstance(lane, (list, tuple)) and len(lane) > 1 and isinstance(lane[1], (int, float)) and lane[1] > 15
        for lane in (lanes or [])
    ) else ""
    record = (
        f"{time.strftime('%F %T')} total={total:.1f}s ttft="
        f"{'-' if ttft is None else round(ttft, 1)}s chunks={chunks} http={status}"
        f"{' err=' + error if error else ''}{slow} lanes={lanes} q={question}"
    )
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(record + "\n")
    print(record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
