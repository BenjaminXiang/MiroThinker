"""Vector-lane fail-open behaviour at the retrieval-trace level (F1.2/F1.3).

Clusters B (lane fail-open + outer wait) and C4 (outer-wait notification) of
`.agents/runs/embedding-endpoint-configurable-and-lane-fail-open/verification-contract.md`.

Fixture source: constructed scenarios driving the real `KnowledgeRead.execute`
lane machinery with a stub vector lane adapter, mirroring
`tests/canonical_v2/test_knowledge_read_universal_web_contract.py`.
"""

from __future__ import annotations

from importlib import import_module
import threading
import time
from typing import Any

import pytest

READ_MODULE = "src.data_agents.canonical_v2.knowledge_read"
ISOLATED_READ_MODULE = "src.data_agents.canonical_v2.knowledge_read_isolated"


def _module() -> Any:
    return import_module(READ_MODULE)


def _plan(module: Any, *, lanes: tuple[str, ...] = ("exact", "vector")) -> Any:
    return module.RetrievalPlan(
        plan_version="retrieval-plan-v1",
        original_query="深圳有哪些芯片企业",
        behavior_class="A",
        interaction_mode="information_retrieval",
        release_id="candidate-r1",
        domains=("company",),
        protected_slots=(),
        lanes=lanes,
        max_candidates=10,
        web_required=False,
        web_policy=module.WebSearchPolicy(mode="disabled"),
        freshness_material=False,
    )


def _lane_result(module: Any) -> Any:
    return module.RetrievalLaneResult(
        items=(
            module.EvidenceItem(
                evidence_id="local:exact",
                object_id="company:1",
                domain="company",
                lane="exact",
                source_nature="local",
                source_locator="artifact:company-release#item:1",
                snippet="The accepted release contains a usable exact Company record.",
                score=1.0,
            ),
        )
    )


def _read(module: Any, vector_lane: Any) -> Any:
    return module.create_ephemeral_knowledge_read(
        lane_adapters={"exact": lambda _: _lane_result(module), "vector": vector_lane},
        universal_web_policy=module.WebSearchPolicy(mode="disabled"),
    )


def _vector_trace(result: Any) -> Any:
    traces = tuple(trace for trace in result.traces if trace.lane == "vector")
    assert len(traces) == 1
    return traces[0]


def test_vector_transport_failure_degrades_the_lane_and_keeps_the_turn() -> None:
    module = _module()
    # ``EmbeddingEndpointRateLimitedError`` is the refusal the rebuild's batch
    # fan-out waits out (HTTP 429): F1's capture must keep treating it as a
    # transport failure, so the lane degrades fail-open, unchanged.
    rate_limited = import_module(
        "src.data_agents.providers.dashscope_embeddings"
    ).EmbeddingEndpointRateLimitedError(
        "embedding endpoint https://gateway.invalid/api/v1 rate limited the batch "
        "(HTTP 429, Retry-After=7s)",
        status_code=429,
        retry_after=7.0,
    )
    failures = (
        (ConnectionError("embedding endpoint is unreachable"), "connection_failure"),
        (rate_limited, "connection_failure"),
        (TimeoutError("embedding read timed out"), "timeout"),
    )
    for error, expected_kind in failures:

        def vector_lane(_: Any, error: BaseException = error) -> Any:
            raise error

        read = _read(module, vector_lane)
        result = read.execute(_plan(module))

        assert isinstance(result, module.EvidenceSet)
        assert tuple(item.evidence_id for item in result.items) == ("local:exact",)
        trace = _vector_trace(result)
        assert trace.status == "unavailable"
        assert trace.failure_kind == expected_kind
        assert trace.candidate_count == 0


def test_vector_integrity_failure_still_fails_closed() -> None:
    module = _module()
    integrity = import_module(ISOLATED_READ_MODULE).IsolatedKnowledgeReadIntegrityError

    def vector_lane(_: Any) -> Any:
        raise integrity("embedding adapter returned the wrong vector dimension")

    read = _read(module, vector_lane)
    with pytest.raises(integrity):
        read.execute(_plan(module))


def test_outer_wait_caps_a_hung_vector_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    monkeypatch.setenv("CANONICAL_V2_VECTOR_LANE_TIMEOUT_SECONDS", "1")
    released = threading.Event()

    def vector_lane(_: Any) -> Any:
        released.wait(timeout=20.0)
        return _lane_result(module)

    read = _read(module, vector_lane)
    started = time.monotonic()
    try:
        result = read.execute(_plan(module))
    finally:
        released.set()

    wall = time.monotonic() - started
    assert wall < 3.0, f"the vector lane held the turn for {wall:.1f}s"
    trace = _vector_trace(result)
    assert trace.status == "unavailable"
    assert trace.failure_kind == "timeout"
    assert tuple(item.evidence_id for item in result.items) == ("local:exact",)


def test_outer_wait_expiry_is_reported_to_the_lane_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    monkeypatch.setenv("CANONICAL_V2_VECTOR_LANE_TIMEOUT_SECONDS", "1")
    released = threading.Event()
    notifications: list[str] = []

    def note_outer_timeout() -> None:
        notifications.append("timeout")

    def vector_lane(_: Any) -> Any:
        released.wait(timeout=20.0)
        return _lane_result(module)

    vector_lane.note_outer_timeout = note_outer_timeout
    read = _read(module, vector_lane)
    try:
        read.execute(_plan(module))
    finally:
        released.set()

    assert notifications == ["timeout"]


def test_a_lane_adapter_without_the_hook_is_unaffected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    monkeypatch.setenv("CANONICAL_V2_VECTOR_LANE_TIMEOUT_SECONDS", "1")
    released = threading.Event()

    def vector_lane(_: Any) -> Any:
        released.wait(timeout=20.0)
        return _lane_result(module)

    read = _read(module, vector_lane)
    try:
        result = read.execute(_plan(module))
    finally:
        released.set()

    assert _vector_trace(result).failure_kind == "timeout"


def test_an_unparsable_cap_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    monkeypatch.setenv("CANONICAL_V2_VECTOR_LANE_TIMEOUT_SECONDS", "not-a-number")

    assert module._vector_lane_outer_wait_seconds() == pytest.approx(8.0)
