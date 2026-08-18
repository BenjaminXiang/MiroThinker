#!/usr/bin/env python3
"""Replay harness for systematic-fix round 1 (fix-round-1-serving-pipeline).

Replays the seven real user test sessions (P1–P8, 2026-08-17) against a live
canonical-v2 backend, saves each turn's SSE, and evaluates the per-group
acceptance lines frozen in Phase 0. Doubles as the pre-hot-update regression
suite: run against the release line before every customer hot update.

Usage:
  python replay_fix_round1.py --base-url http://127.0.0.1:18188 \
      --out-dir .agents/runs/fix-round-1-serving-pipeline/<label>

Exit code 0 iff every assertion passes. Assertions are deterministic
(substring / event checks) so the suite is reproducible without an LLM judge.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ORG = "国际先进技术应用推进中心"
ORG_SHORT = "国先中心"
UBTECH = "优必选"
PARK = "河套深港科技创新合作区深圳园区"
ARTICLE_TITLE = "河套深圳园区打造深港科技创新聚集地"
WEBANK = "微众银行"
DEFLECTION = ("国家知识产权局", "PatSnap", "Incopat")
REFUSAL = ("未找到", "暂无公开", "无法确定具体指代对象")

# --- sessions -------------------------------------------------------------

SESSIONS = {
    "G1_framing": [
        ("介绍一下 国际先进技术应用推进中心（深圳）", None),
        ("有没有更详细的信息", None),
        (
            "它有哪些布局和进展",
            {
                "subject_in_first_sentence": ORG,
                "forbidden_answer": (WEBANK, ARTICLE_TITLE),
            },
        ),
    ],
    "G2_bare_name": [
        (
            "国际先进技术应用推进中心（深圳）",
            {
                "forbidden_answer": ("未找到关于", "暂无公开的详细运营信息"),
                "required_answer_any": (ORG, ORG_SHORT),
            },
        ),
        (
            "这个中心的企业培育情况怎么样",
            {
                "not_clarification": True,
                "required_answer_any": (ORG_SHORT, ORG),
            },
        ),
    ],
    "G3_person_pronoun": [
        ("介绍一下 国际先进技术应用推进中心（深圳）", None),
        (
            "他有哪些论文",
            {
                "must_clarify_or_person_scoped": True,
                "forbidden_answer": (ARTICLE_TITLE, WEBANK, "这一机构名称"),
            },
        ),
    ],
    "G4_patents": [
        ("优必选科技怎么样", {"required_answer": (UBTECH,)}),
        (
            "该公司的专利有哪些",
            {
                "forbidden_answer": DEFLECTION + ("未找到",),
            },
        ),
    ],
    "G5_expansion": [
        ("优必选科技怎么样", None),
        (
            "还有哪些类似的公司",
            {
                "forbidden_answer": (WEBANK,),
                "required_answer_any": (UBTECH, "越疆", "乐聚", "众擎", "机器人"),
            },
        ),
    ],
    "G6_anaphoric_opener": [
        (
            "这个中心是做什么的",
            {"must_clarify": True},
        ),
    ],
    "G7_enumeration": [
        (
            "深圳有哪些做具身智能的公司",
            {
                # Web-luck variance defect (P8): the flagship must appear in EVERY
                # repetition, not on average — hence required (not _any) + repeats.
                "required_answer": (UBTECH,),
            },
        ),
    ],
}

# Web-lane variance is part of the defect: these sessions replay N times with
# fresh cookies and every repetition must pass.
SESSION_REPEATS = {"G2_bare_name": 3, "G7_enumeration": 3}


# --- SSE client -----------------------------------------------------------

def post_turn(base_url: str, jar: CookieJar, query: str, timeout: int = 120) -> dict:
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/chat/stream",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    raw = b""
    with opener.open(req, timeout=timeout) as resp:
        for chunk in resp:
            raw += chunk
    text = raw.decode("utf-8", errors="replace")
    events: dict[str, list] = {}
    answer = {}
    current_event = None
    for line in text.splitlines():
        if line.startswith("event: "):
            current_event = line[7:].strip()
            events.setdefault(current_event, 0)
            events[current_event] += 1
        elif line.startswith("data: {") and current_event == "answer":
            try:
                answer = json.loads(line[6:])
            except json.JSONDecodeError:
                pass
    return {
        "events": events,
        "answer": answer,
        "raw_len": len(text),
        "raw": text,
    }


# --- assertion evaluation -------------------------------------------------

def first_sentence(text: str) -> str:
    return re.split(r"[。！？\n]", text, maxsplit=1)[0] if text else ""


def check_assertions(turn_result: dict, spec: dict | None) -> list[str]:
    failures = []
    if spec is None:
        return failures
    answer = turn_result["answer"]
    text = answer.get("answer_text") or ""
    query_type = answer.get("query_type") or ""
    events = turn_result["events"]
    if "error" in events:
        failures.append("SSE error event present")
    if "answer" not in events or "done" not in events:
        failures.append(f"missing answer/done events: {events}")
    for needle in spec.get("forbidden_answer", ()):
        if needle in text:
            failures.append(f"forbidden substring in answer: {needle}")
    for needle in spec.get("required_answer", ()):
        if needle not in text:
            failures.append(f"required substring missing: {needle}")
    if spec.get("required_answer_any"):
        if not any(n in text for n in spec["required_answer_any"]):
            failures.append(
                f"none of required-any present: {spec['required_answer_any']}"
            )
    if spec.get("subject_in_first_sentence"):
        if spec["subject_in_first_sentence"] not in first_sentence(text):
            failures.append(
                f"subject not in first sentence: {spec['subject_in_first_sentence']}"
            )
    if spec.get("must_clarify"):
        if "clarification_only" not in query_type:
            failures.append(f"expected clarification, got query_type={query_type}")
    if spec.get("must_clarify_or_person_scoped"):
        clarified = "clarification_only" in query_type
        person_scoped = any(n in text for n in ("教授", "老师", "学者", "论文作者"))
        if not (clarified or person_scoped):
            failures.append(
                f"neither clarification nor person-scoped answer (type={query_type})"
            )
    if spec.get("not_clarification"):
        if "clarification_only" in query_type:
            failures.append("unexpected clarification")
    return failures


# --- main -----------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18188")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--only", help="comma-separated session keys")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, dict] = {}
    keys = (
        {k.strip() for k in args.only.split(",")} if args.only else set(SESSIONS)
    )
    total_failures = 0
    for session_name in SESSIONS:
        if session_name not in keys:
            continue
        session_report = {"turns": [], "pass": True}
        for repeat in range(1, SESSION_REPEATS.get(session_name, 1) + 1):
            jar = CookieJar()
            for idx, (query, spec) in enumerate(SESSIONS[session_name], start=1):
                print(f"[{session_name}#{repeat}] T{idx}: {query}", flush=True)
                started = time.time()
                result = post_turn(args.base_url, jar, query, args.timeout)
                elapsed = round(time.time() - started, 1)
                sse_name = f"{session_name}_r{repeat}_t{idx}.sse"
                (out_dir / sse_name).write_text(result["raw"], encoding="utf-8")
                failures = check_assertions(result, spec)
                total_failures += len(failures)
                session_report["pass"] = session_report["pass"] and not failures
                session_report["turns"].append(
                    {
                        "query": query,
                        "repeat": repeat,
                        "sse": sse_name,
                        "seconds": elapsed,
                        "query_type": result["answer"].get("query_type"),
                        "answer_head": (result["answer"].get("answer_text") or "")[:120],
                        "failures": failures,
                    }
                )
                status = "PASS" if not failures else f"FAIL {failures}"
                print(
                    f"    -> {result['answer'].get('query_type')} ({elapsed}s) {status}",
                    flush=True,
                )
        report[session_name] = session_report
    summary = {
        "base_url": args.base_url,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sessions": report,
        "all_pass": total_failures == 0,
        "total_failures": total_failures,
    }
    (out_dir / "report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"\n{'='*60}\nRESULT: {'ALL PASS' if total_failures == 0 else f'{total_failures} FAILURE(S)'}"
    )
    for name, sess in report.items():
        print(f"  {name}: {'PASS' if sess['pass'] else 'FAIL'}")
    return 0 if total_failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
