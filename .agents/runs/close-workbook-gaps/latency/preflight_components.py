#!/usr/bin/env python3
"""Preflight for the latency harness: prove the production components work.

Checks (no serving pack needed, ~1 minute):
  1. embedding adapter  — qwen-embedding-bundle-v1 + the real Qwen endpoint
  2. page fetcher        — create_tiered_page_fetcher tier-0 vs tier-1 timing
  3. query rewriter      — real _ServingQueryRewriter under CHAT_LLM_PROFILE
  4. LLM judge           — real create_llm_judge, 1.8s timeout + fail-open outcome

Run with the worktree venv:
  .../.worktrees/canonical-v2-s11-consolidation/.venv/bin/python3 \
      .agents/runs/close-workbook-gaps/latency/preflight_components.py [--urls a,b]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HARNESS = Path(__file__).resolve()
WORKTREE = HARNESS.parents[4] / ".worktrees" / "canonical-v2-s11-consolidation"
APP_ROOT = WORKTREE / "apps" / "miroflow-agent"
RUN_ROOT = WORKTREE / ".agents" / "runs" / "rebuild-canonical-v2-knowledge-platform"
sys.dont_write_bytecode = True
sys.path.insert(0, str(APP_ROOT))

DEFAULT_URLS = (
    "https://www.dji.com/cn",
    "https://baike.baidu.com/item/%E5%A4%A7%E7%96%86%E5%88%9B%E6%96%B0",
)


def check_embedding() -> dict:
    from src.data_agents.canonical_v2 import knowledge_build_isolated as build_iso

    adapter = build_iso.load_content_addressed_embedding_adapter(
        RUN_ROOT / "s12c" / "qwen-embedding-bundle-v1.json"
    )
    started = time.perf_counter()
    vectors = adapter.embed_batch(("大疆创新主要做什么",))
    first = time.perf_counter() - started
    started = time.perf_counter()
    adapter.embed_batch(("大疆创新主要做什么",))
    cached = time.perf_counter() - started
    return {
        "model_id": adapter.model_id,
        "dimension": len(vectors[0]),
        "first_call_s": round(first, 4),
        "cached_call_s": round(cached, 4),
    }


def check_page_fetch(urls: tuple[str, ...]) -> dict:
    from src.data_agents.providers import page_fetch

    direct_times = {}
    original = page_fetch.fetch_page_text

    def direct(url: str) -> str | None:
        started = time.perf_counter()
        text = original(url)
        direct_times[url] = time.perf_counter() - started
        return text

    fetcher = page_fetch.create_tiered_page_fetcher(direct_fetcher=direct)
    started = time.perf_counter()
    fetcher.warm(10.0)
    warm_s = round(time.perf_counter() - started, 3)
    rows = []
    for url in urls:
        started = time.perf_counter()
        text = fetcher(url)
        total = time.perf_counter() - started
        rows.append(
            {
                "url": url,
                "total_s": round(total, 3),
                "direct_s": round(direct_times.get(url, 0.0), 3),
                "tier1_s": round(total - direct_times.get(url, 0.0), 3),
                "chars": len(text or ""),
            }
        )
    return {"browser_warm_s": warm_s, "pages": rows}


def check_rewriter(queries: tuple[str, ...]) -> dict:
    from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving

    rewriter = serving._ServingQueryRewriter()
    rows = []
    for query in queries:
        started = time.perf_counter()
        views = rewriter(query)
        rows.append(
            {
                "query": query,
                "wall_s": round(time.perf_counter() - started, 3),
                "views": list(views),
                "producer_version": rewriter.producer_version,
            }
        )
    return {"rows": rows}


def check_judge() -> dict:
    from src.data_agents.canonical_v2.llm_judgments import create_llm_judge

    judge = create_llm_judge()
    started = time.perf_counter()
    results = judge.judge_batch(
        "gap_check",
        "大疆创新主要做什么",
        {"gap": "- 大疆创新：全球无人机与影像设备厂商\n- 大疆：消费级无人机龙头"},
    )
    wall = time.perf_counter() - started
    return {
        "wall_s": round(wall, 3),
        "outcome": judge.last_outcome,
        "results": [json.loads(item.model_dump_json()) for item in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls", default="")
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()

    import os

    print("CHAT_LLM_PROFILE =", os.getenv("CHAT_LLM_PROFILE"), flush=True)
    report: dict = {"chat_llm_profile": os.getenv("CHAT_LLM_PROFILE")}

    for name, fn in (
        ("embedding", check_embedding),
        ("rewriter", lambda: check_rewriter(("大疆创新主要做什么", "深圳有哪些研究机器人的教授"))),
        ("judge", check_judge),
    ):
        try:
            report[name] = fn()
        except Exception as exc:  # noqa: BLE001
            report[name] = {"error": f"{type(exc).__name__}: {exc}"}
        print(f"[{name}] {json.dumps(report[name], ensure_ascii=False)[:400]}", flush=True)

    if not args.skip_fetch:
        urls = tuple(item for item in args.urls.split(",") if item) or DEFAULT_URLS
        try:
            report["page_fetch"] = check_page_fetch(urls)
        except Exception as exc:  # noqa: BLE001
            report["page_fetch"] = {"error": f"{type(exc).__name__}: {exc}"}
        print(f"[page_fetch] {json.dumps(report['page_fetch'], ensure_ascii=False)[:800]}", flush=True)

    out = HARNESS.with_name("preflight-components.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
