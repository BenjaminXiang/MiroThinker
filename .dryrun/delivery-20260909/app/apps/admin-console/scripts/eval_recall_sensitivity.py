"""Sensitivity cases for the recall benchmark — cases where a SPECIFIC lever is the
binding constraint, so the oracle reflects the change (benchmark-completion-spec
criterion 2). The main eval_recall_chat cases are mostly well-phrased single-entity
or saturated-topic queries, so Lever 0/1 moved the real system ~0 on the oracle;
these cases are RED without the lever, GREEN with it.

Backend DOWN (TestClient opens Milvus in-process):
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
  DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
  MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
  uv run python scripts/eval_recall_sensitivity.py
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# env defaults must precede app import (the existing eval pattern)
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real",
)
os.environ.setdefault("MILVUS_USE_REAL_CLIENT", "1")
os.environ.setdefault("CHAT_LLM_SYNTHESIS", "off")

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


@dataclass
class SensitivityCase:
    qid: str
    query: str
    required: list[str]
    lever: str  # which lever this case binds
    expect_today: str  # "RED" (fails today, turns green when lever ships) or "GREEN"


# Grounded in the DB + the brittleness/decouple findings (2026-07-05).
SENSITIVITY_CASES: list[SensitivityCase] = [
    # root A (classifier phrasing brittleness): bare "做X教授" / "X 教授" -> unknown -> 0.
    # These are FORCED-RED sentinels: GREEN only after the classifier is hardened.
    SensitivityCase("S1", "做机器学习教授", ["夏树涛"], "rootA-classifier-phrasing", "RED"),
    SensitivityCase("S2", "大模型 教授", ["夏树涛"], "rootA-classifier-phrasing", "RED"),
    # Lever 1 (professor decouple): needs_review profs are now retrievable.
    # Use a WELL-PHRASED query (routes to B_semantic, confirmed by the breadth probe)
    # so the case isolates the decouple from the phrasing brittleness. 夏树涛 is
    # needs_review + an ML/embodied author; surfaces post-decouple.
    SensitivityCase(
        "S3", "做机器学习和大模型的教授有哪些", ["夏树涛"], "L1-professor-decouple", "GREEN"
    ),
    # Lever 0 (partial-paper retrievability): a Chinese-titled partial+fulltext paper
    # now embedded (PAPER-62144912BE08 "基于矢量波数变换法(VWTM)的多道Rayleigh波分析
    # 方法"). Same-language query + title fragment as the required entity (paper
    # responses surface the title, not the author).
    SensitivityCase(
        "S4",
        "矢量波数变换法 Rayleigh波 分析论文",
        ["Rayleigh"],
        "L0-partial-paper",
        "GREEN",
    ),
]


def _hit(response_json: dict, required: list[str]) -> list[str]:
    text = str(response_json).lower()
    return [e for e in required if e.lower() in text]


def main() -> int:
    client = TestClient(app)
    print(f"{'qid':>4} {'lever':>26} {'expect':>7} {'actual':>7}  query")
    red_unexpected = 0
    green_failed = 0
    for c in SENSITIVITY_CASES:
        try:
            r = client.post("/api/chat", json={"query": c.query})
            hits = _hit(r.json(), c.required)
        except Exception as exc:  # noqa: BLE001
            hits = []
            print(f"  (error: {exc})", file=sys.stderr)
        actual = "GREEN" if len(hits) == len(c.required) else "RED"
        ok = actual == c.expect_today
        if not ok and c.expect_today == "GREEN":
            green_failed += 1
        if not ok and c.expect_today == "RED":
            red_unexpected += 1
        flag = "OK" if ok else "!!"
        print(
            f"{c.qid:>4} {c.lever:>26} {c.expect_today:>7} {actual:>7} {flag}  {c.query}"
        )
    print(
        f"\nGREEN-but-failed (regression): {green_failed} | "
        f"RED-but-passed (lever landed — flip expect): {red_unexpected}"
    )
    return 1 if green_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
