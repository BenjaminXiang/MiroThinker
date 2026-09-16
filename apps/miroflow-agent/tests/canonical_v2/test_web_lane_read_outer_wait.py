"""Web-lane read-orchestrator outer wait (fix-web-lane-read-outer-wait).

Regression documented 2026-08-28 (live E2E): the read layer reused the
provider-search budget (web_policy.timeout_ms = 1 500 ms) as the outer wait
for the WHOLE web-lane future. The lane's real workload (view searches × 2
providers + enumeration refinement + fetch_depth=8 page fetches + LLM gap
judge) takes 2–40 s, so real-work lanes were killed at 1.5 s and recorded
`status="unavailable", candidates=0` — the serving-layer trace meanwhile
showed `web in=72 retained=72` with zero provider errors. This collapsed
web-fused enumerations to local-only lists (G7 missing 优必选) and fired the
outage rewrite on thin answers (waseda query).
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib import import_module
from typing import Any

TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_read"
NOW = datetime(2026, 7, 15, 2, 35, tzinfo=timezone.utc)


def _module() -> Any:
    return import_module(TARGET_MODULE)


def test_slow_web_items_kept_under_tight_provider_budget() -> None:
    """A web lane that legitimately needs >timeout_ms (but <floor) seconds
    must land its items in the evidence set with a succeeded trace."""
    import time

    module = _module()

    def local_search(request: Any) -> Any:
        return module.RetrievalLaneResult(items=())

    def web_search(request: Any) -> Any:
        time.sleep(2.0)  # > policy timeout_ms (1.5 s), < wait floor
        snapshot_bytes = b"slow-lane web snapshot"
        snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
        return module.RetrievalLaneResult(
            items=(
                module.EvidenceItem(
                    evidence_id="web:slow",
                    object_id="company:1",
                    domain="company",
                    lane="web",
                    source_nature="current_web",
                    source_locator="https://current.example/slow",
                    snippet="Slow but real web corroboration.",
                    score=0.9,
                    web_snapshot=module.WebEvidenceSnapshot(
                        snapshot_id=f"web-snapshot:sha256:{snapshot_sha256}",
                        content_sha256=snapshot_sha256,
                        retrieved_at=NOW,
                        byte_length=len(snapshot_bytes),
                    ),
                ),
            )
        )

    read = module.create_ephemeral_knowledge_read(
        local_search=local_search,
        web_search=web_search,
        universal_web_policy=module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_500,
            max_results=5,
        ),
    )
    plan = module.RetrievalPlan(
        plan_version="retrieval-plan-v1",
        original_query="synthetic A information request",
        behavior_class="A",
        interaction_mode="information_retrieval",
        release_id="candidate-r1",
        domains=("company",),
        protected_slots=(),
        lanes=("exact", "web"),
        max_candidates=10,
        web_required=True,
        web_policy=module.WebSearchPolicy(mode="disabled"),
    )
    result = read.execute(plan)
    web_traces = [t for t in result.traces if t.lane == "web"]
    assert len(web_traces) == 1
    assert web_traces[0].status == "succeeded", (
        f"web lane declared {web_traces[0].status!r} with "
        f"failure_kind={web_traces[0].failure_kind!r} — the read layer "
        "killed a working lane at the provider-search budget"
    )
    assert web_traces[0].candidate_count == 1
    assert [i.evidence_id for i in result.items if i.lane == "web"] == [
        "web:slow"
    ]


def test_outer_wait_floor_math() -> None:
    module = _module()
    helper = module._web_lane_outer_wait_seconds
    # floor applies below it
    assert helper(module.WebSearchPolicy(mode="universal", timeout_ms=1_500)) == 20.0
    assert helper(module.WebSearchPolicy(mode="universal", timeout_ms=0)) == 20.0
    # policy wins above the floor
    assert helper(module.WebSearchPolicy(mode="universal", timeout_ms=30_000)) == 30.0
    # disabled lane never waits
    assert helper(module.WebSearchPolicy(mode="disabled")) is None
