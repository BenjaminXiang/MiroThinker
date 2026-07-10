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
from collections import defaultdict
from dataclasses import dataclass, field

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
    false_positives: list[str] = field(default_factory=list)


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
    Case(50, "有哪些做具身智能和灵巧手的教授", "professor",
         ["柯文德", "任尔夫", "王强", "刘桂良"],
         "FM4 ground-truth: profs with >=6 embodied/dexterous papers (first-draft; refine "
         "after labeling). Tests cross-domain paper->professor recall gap — professor vector "
         "recall on profile_summary is not expected to surface these by topic."),
    Case(51, "深圳法本信息科技有限公司的产品特点以及团队介绍", "company",
         ["法本信息技术"],
         "FM5: clear single-company query; classifier routes to `unknown` because the name "
         "variant (法本信息科技有限公司) doesn't exact-match the DB canonical (法本信息技术). "
         "Entity IS in the DB (COMP-d5c254c49820, ready)."),
    Case(40, "优必选有哪些专利", "patent", ["优必选"]),
    Case(41, "专利 CN117873146A 的详细信息是什么", "patent", ["CN117873146A"]),
    # --- paper-retrievability-baseline (2026-07-09). Structural gold verified vs miroflow_real.
    # See .agents/runs/paper-retrievability-baseline/slice-contract.md. Measures behavioral
    # retrievability of PAPERS (recall leg). Type1=title-self; Type2=professor->paper (FM4
    # territory — single-domain paper recall likely MISSes unless abstracts name the prof; the
    # full /api/chat path in eval_recall_chat.py is the real cross-domain test); Type4=topic.
    # Type3 (company->paper) has NO structural gold: professor_company_role is empty, so the
    # company->prof->paper chain is dead — recorded as a gap, not a case.
    Case(100, "ShuffleNet V2: Practical Guidelines for Efficient CNN Architecture Design",
         "paper", ["ShuffleNet V2"], "Type1 title-self"),
    Case(101, "ESRGAN: Enhanced Super-Resolution Generative Adversarial Networks",
         "paper", ["ESRGAN"], "Type1 title-self"),
    Case(102, "Valley polarization in MoS2 monolayers by optical pumping",
         "paper", ["Valley polarization"], "Type1 title-self"),
    Case(103, "Memristors with diffusive dynamics as synaptic emulators for neuromorphic computing",
         "paper", ["diffusive dynamics"], "Type1 title-self"),
    Case(104, "Structure of the TRPV1 ion channel determined by electron cryo-microscopy",
         "paper", ["TRPV1"], "Type1 title-self"),
    Case(105, "Polymer electrolytes for lithium-based batteries: advances and prospects",
         "paper", ["Polymer electrolytes"], "Type1 title-self"),
    Case(106, "常瑞华教授发表了哪些论文",
         "paper", ["VCSEL", "Fabry-Perot", "Grating"],
         "Type2 professor->paper (常瑞华, 12 verified ready papers). Cross-domain; single-domain "
         "paper recall expected to MISS unless abstracts mention the prof."),
    Case(107, "刘江教授发表了哪些论文",
         "paper", ["Glaucoma", "Retinal", "SkrGAN"],
         "Type2 professor->paper (刘江, 12 verified ready papers)."),
    Case(108, "陈勇勇教授发表了哪些论文",
         "paper", ["Mamba-Transformer", "Quaternion", "Snapshot Compressive"],
         "Type2 professor->paper (陈勇勇, 12 verified ready papers)."),
    Case(109, "关于perovskite钙钛矿材料的论文有哪些",
         "paper", ["Perovskite"],
         "Type4 topic (284 ready papers). required=topic-indicative title token (capital 'Perovskite' "
         "vs the lowercase query echo) -> measures 'did perovskite papers surface', not specific "
         "notable papers (substring topic-recall is weak per Q3)."),
    Case(110, "关于联邦学习federated learning的最新论文",
         "paper", ["Federated Learning"],
         "Type4 topic (145 ready papers). required=topic-indicative title token ('Federated Learning' "
         "capital vs lowercase query) -> did FL papers surface."),
]


def run(top_k: int, relax: bool) -> None:
    from backend.deps import get_retrieval_service

    svc = get_retrieval_service()
    fqs = False if relax else None  # None = env default (ready-gate ON); False = relax
    total_req = 0
    total_hit = 0
    dom_req: dict[str, int] = defaultdict(int)
    dom_hit: dict[str, int] = defaultdict(int)
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
            dom_req[c.domain] += len(c.required)
            continue
        snippets = [(e.snippet or "") for e in evs]
        hits, misses = [], []
        for r in c.required:
            (hits if any(r in s for s in snippets) else misses).append(r)
        total_req += len(c.required)
        total_hit += len(hits)
        dom_req[c.domain] += len(c.required)
        dom_hit[c.domain] += len(hits)
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
    print("-" * 90)
    print("PER-DOMAIN RECALL:")
    for d in sorted(dom_req):
        dpct = 100.0 * dom_hit[d] / dom_req[d] if dom_req[d] else 0.0
        print(f"  {d:<11} {dom_hit[d]}/{dom_req[d]} ({dpct:.0f}%)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--relax", action="store_true", help="filter_by_quality_status=False")
    args = ap.parse_args()
    run(args.top_k, args.relax)
    return 0


if __name__ == "__main__":
    sys.exit(main())
