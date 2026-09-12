"""Live smoke for RemoteReranker against the real relevance endpoint.

Run with the CANONICAL_V2_RERANK_* env set (base url, model, key file). Prints
only ordering, scores and wall time -- never the credential.

    cd <worktree>/apps/miroflow-agent
    uv run python /home/longxiang/MiroThinker/.agents/runs/retrieval-v2-derived-index-and-fusion/live_rerank_smoke.py
"""

from __future__ import annotations

import logging  # noqa: F401  (must load before `src` shadows it)
import os
import sys
import time

sys.path.insert(0, os.path.join(os.getcwd(), "src"))

from data_agents.canonical_v2.rerank_client import (  # noqa: E402
    RerankUnavailable,
    configured_reranker,
)

CASES: list[tuple[str, list[str]]] = [
    (
        "深圳有哪些做激光雷达的公司",
        [
            "深圳市速腾聚创科技有限公司: 激光雷达与感知硬件供应商, 面向自动驾驶量产",
            "深圳市优必选科技股份有限公司: 人形机器人整机与伺服驱动器",
            "深圳传音控股股份有限公司: 手机整机与移动终端",
            "深圳市大疆创新科技有限公司: 无人机整机与云台相机",
        ],
    ),
    (
        "该公司的专利有哪些",
        [
            "深圳市优必选科技股份有限公司 专利: 一种机器人关节伺服控制方法",
            "优必选科技: 企业简介, 成立于 2012 年, 总部深圳南山",
            "国家知识产权局专利检索平台使用说明",
        ],
    ),
]


def main() -> int:
    reranker = configured_reranker()
    if reranker is None:
        print("REFUSED: no CANONICAL_V2_RERANK_BASE_URL configured")
        return 2
    print(f"endpoint={reranker.endpoint} model={reranker.model_id} cap={reranker.max_documents}")

    failures = 0
    for query, documents in CASES:
        started = time.perf_counter()
        try:
            scores = reranker.score(query, documents)
        except RerankUnavailable as exc:
            failures += 1
            print(f"UNAVAILABLE query={query!r} reason={exc}")
            continue
        elapsed_ms = (time.perf_counter() - started) * 1000
        order = sorted(range(len(documents)), key=lambda i: (-scores[i], i))
        print(f"\nquery={query!r} documents={len(documents)} wall_ms={elapsed_ms:.0f}")
        for rank, index in enumerate(order, start=1):
            print(f"  {rank}. score={scores[index]:.4f} :: {documents[index][:44]}")

    # Oversized input must be refused locally, not sent to the server.
    try:
        reranker.score("cap probe", [f"doc-{i}" for i in range(reranker.max_documents + 1)])
    except RerankUnavailable as exc:
        print(f"\ncap probe refused locally: {exc}")
    else:
        failures += 1
        print("\ncap probe FAILED: oversized payload was accepted")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
