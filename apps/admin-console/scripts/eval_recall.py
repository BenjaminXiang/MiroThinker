"""Lean recall diagnostic over the test set (single-domain gradable cases).

First-principles baseline: for each case, run the production retrieve() with the
EXPECTED domain, then check whether each required entity (from 关键点) appears in the
top-K candidate snippets. Reports per-case hit/miss so failure modes surface:
not-in-DB / not-ready / not-embedded / reranked-out / mis-domain.

Run (from apps/admin-console):
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  MILVUS_USE_REAL_CLIENT=1 UV_OFFLINE=1 \
  uv run python scripts/eval_recall.py [--top-k 10] [--relax]
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

# Defaults required before importing backend.deps (env-driven wiring).
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real",
)
os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")


@dataclass
class Case:
    qid: int
    query: str
    domain: str
    required: list[str]  # substrings that MUST appear in some candidate snippet
    note: str = ""


# Single-domain, objectively gradable cases (关键点 lists required entities).
# Multi-turn (D) / cross-domain (C) / web-E / refusal-F need richer harness — deferred.
CASES: list[Case] = [
    Case(1, "介绍清华的丁文伯", "professor", ["丁文伯"]),
    Case(4, "中国有哪些成熟的酒店送餐机器人供应商", "company",
         ["普渡", "开普勒", "云迹", "九号", "擎朗"], "关键点: 5 nationwide leaders must appear"),
    Case(10, "请介绍无界智航的相关信息", "company", ["无界智航"]),
    Case(13, "我想找PCB打板， 有哪些推荐", "company", ["嘉立创", "一博", "深南电路"]),
    Case(16, "pFedGPA: Diffusion-based Generative Parameter Aggregation for Personalized Federated Learning",
         "paper", ["pFedGPA"]),
    Case(19, "毕业于早稻田，且在深圳专注在机器人行业的企业家有谁", "professor",
         ["许晋诚", "陈功"]),
    Case(21, "华力创科学这家公司相关信息，这家公司的产量特点是什么，市场竞争力怎么样",
         "company", ["华力创"]),
    Case(24, "清华的王学谦的评价如何，他是否是属于大牛", "professor", ["王学谦"]),
    Case(26, "爱博合创企业情况以及创始人信息还有市场对这家企业的评价如何",
         "company", ["爱博合创"]),
    Case(34, "目前深圳有哪些具身智能、灵巧手厂商，他们在数据层面分别是什么路线",
         "company", ["自变量"]),
    Case(40, "优必选有哪些专利", "patent", ["优必选"]),
    Case(41, "专利 CN117873146A 的详细信息是什么", "patent", ["CN117873146A"]),
]


def run(top_k: int, relax: bool) -> None:
    from backend.deps import get_retrieval_service

    svc = get_retrieval_service()
    fqs = False if relax else None  # None = env default (ready-gate ON); False = relax
    total_req = 0
    total_hit = 0
    print(f"{'qid':>3} {'dom':<9} {'hit/req':>8}  query / misses")
    print("-" * 90)
    for c in CASES:
        try:
            evs = svc.retrieve(
                query=c.query, domains=(c.domain,), final_top_k=top_k,
                filter_by_quality_status=fqs,
            )
        except Exception as e:  # noqa: BLE001
            print(f"{c.qid:>3} {c.domain:<9} {'ERR':>8}  {c.query[:40]} -> {type(e).__name__}: {e}")
            total_req += len(c.required)
            continue
        snippets = [(e.snippet or "") for e in evs]
        hits, misses = [], []
        for r in c.required:
            (hits if any(r in s for s in snippets) else misses).append(r)
        total_req += len(c.required)
        total_hit += len(hits)
        flag = "OK " if not misses else "MISS"
        print(f"{c.qid:>3} {c.domain:<9} {len(hits)}/{len(c.required):>3} {flag}  "
              f"{c.query[:34]}  miss={misses}")
        # show recalled names for diagnosis
        if misses:
            names = [(s.split('是一家')[0][:18] if '是一家' in s else s[:18]) for s in snippets[:4]]
            print(f"        recalled-top4: {names}")
    print("-" * 90)
    pct = 100.0 * total_hit / total_req if total_req else 0.0
    print(f"ENTITY RECALL: {total_hit}/{total_req} entities hit ({pct:.0f}%)  "
          f"[top_k={top_k} relax={relax}]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--relax", action="store_true", help="filter_by_quality_status=False")
    args = ap.parse_args()
    run(args.top_k, args.relax)
    return 0


if __name__ == "__main__":
    sys.exit(main())
