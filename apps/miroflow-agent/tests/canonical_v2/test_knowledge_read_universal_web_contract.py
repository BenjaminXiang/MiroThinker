from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib import import_module
from typing import Any

TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_read"
INFORMATION_CLASSES = ("A", "B", "C", "D", "E", "G")
NOW = datetime(2026, 7, 15, 2, 35, tzinfo=timezone.utc)


class _MissingKnowledgeReadModule(RuntimeError):
    """Exact Task 8.4 RED sentinel; nested missing dependencies fail normally."""


def _module() -> Any:
    try:
        return import_module(TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != TARGET_MODULE:
            raise AssertionError(
                f"{TARGET_MODULE} has an unexpected missing dependency: {exc.name}"
            ) from exc
        raise _MissingKnowledgeReadModule(
            f"exact target module is absent: {TARGET_MODULE}"
        ) from exc


def _web_policy(
    module: Any,
    mode: str,
    *,
    allowed_domains: tuple[str, ...] = (),
) -> Any:
    if mode == "disabled":
        return module.WebSearchPolicy(mode=mode)
    return module.WebSearchPolicy(
        mode=mode,
        max_provider_calls=1,
        timeout_ms=1_500,
        max_results=(3 if mode == "official_only" else 5),
        allowed_domains=allowed_domains,
    )


def _plan(
    module: Any,
    *,
    behavior_class: str,
    interaction_mode: str,
    query: str,
    web_mode: str,
    freshness_material: bool = False,
    allowed_domains: tuple[str, ...] = (),
) -> Any:
    information_retrieval = interaction_mode == "information_retrieval"
    official_lookup = web_mode == "official_only"
    if information_retrieval:
        lanes = ("exact", "web") if web_mode == "universal" else ("exact",)
    else:
        lanes = ("web",) if official_lookup else ()
    return module.RetrievalPlan(
        plan_version="retrieval-plan-v1",
        original_query=query,
        behavior_class=behavior_class,
        interaction_mode=interaction_mode,
        release_id="candidate-r1",
        domains=(("company",) if information_retrieval else ()),
        protected_slots=(),
        lanes=lanes,
        max_candidates=10,
        web_required=web_mode != "disabled",
        web_policy=_web_policy(
            module,
            web_mode,
            allowed_domains=allowed_domains,
        ),
        freshness_material=freshness_material,
    )


def _local_item(module: Any, token: str) -> Any:
    return module.EvidenceItem(
        evidence_id=f"local:{token}",
        object_id="company:1",
        domain="company",
        lane="exact",
        source_nature="local",
        source_locator=f"artifact:company-release#item:{token}",
        snippet="The accepted release contains a usable exact Company record.",
        score=1.0,
    )


def _web_item(
    module: Any,
    token: str,
    source_locator: str,
    *,
    source_authority: str = "other",
) -> Any:
    snapshot_bytes = f"recorded Web snapshot:{token}".encode()
    snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
    return module.EvidenceItem(
        evidence_id=f"web:{token}",
        object_id="company:1",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_authority=source_authority,
        source_locator=source_locator,
        snippet="Recorded current-Web corroboration for the synthetic fixture.",
        score=0.9,
        web_snapshot=module.WebEvidenceSnapshot(
            snapshot_id=f"web-snapshot:sha256:{snapshot_sha256}",
            content_sha256=snapshot_sha256,
            retrieved_at=NOW,
            byte_length=len(snapshot_bytes),
        ),
    )


def _lane_result(module: Any, *items: Any) -> Any:
    return module.RetrievalLaneResult(items=items)


def test_all_information_classes_run_web_even_after_usable_exact_local_evidence() -> (
    None
):
    module = _module()

    def local_search(request: Any) -> Any:
        return _lane_result(module, _local_item(module, request.behavior_class))

    def web_search(request: Any) -> Any:
        assert request.behavior_class in INFORMATION_CLASSES
        assert request.web_policy.mode == "universal"
        assert request.web_policy.max_provider_calls == 1
        return _lane_result(
            module,
            _web_item(
                module,
                request.behavior_class,
                f"https://current.example/{request.behavior_class.lower()}",
            ),
        )

    read = module.create_ephemeral_knowledge_read(
        local_search=local_search,
        web_search=web_search,
        universal_web_policy=_web_policy(module, "universal"),
    )
    for behavior_class in INFORMATION_CLASSES:
        plan = _plan(
            module,
            behavior_class=behavior_class,
            interaction_mode="information_retrieval",
            query=f"synthetic {behavior_class} information request",
            web_mode="disabled",
        )
        assert plan.web_required is False
        assert "web" not in plan.lanes
        assert plan.web_policy.mode == "disabled"

        result = read.execute(plan)

        assert isinstance(result, module.EvidenceSet)
        assert {item.source_nature for item in result.items} == {
            "local",
            "current_web",
        }
        web_traces = tuple(trace for trace in result.traces if trace.lane == "web")
        assert len(web_traces) == 1
        assert web_traces[0].status == "succeeded"
        assert web_traces[0].candidate_count == 1
        assert web_traces[0].release_id == plan.release_id
        assert tuple(
            item.evidence_id
            for item in result.items
            if item.source_nature == "current_web"
        ) == (f"web:{behavior_class}",)


def test_non_retrieval_skips_web_and_explicit_safety_lookup_is_official_only() -> None:
    module = _module()

    def local_search(_: Any) -> Any:
        return _lane_result(module)

    def fail_on_web(_: Any) -> Any:
        raise AssertionError("non-retrieval input invoked the Web adapter")

    skip_read = module.create_ephemeral_knowledge_read(
        local_search=local_search,
        web_search=fail_on_web,
        universal_web_policy=_web_policy(module, "universal"),
    )
    skip_inputs = (
        ("F", "ordinary_refusal", "unrelated out-of-scope request"),
        ("G", "blocking_clarification", "ambiguous entity needs clarification"),
        ("control", "interface_control", "change the display layout"),
        ("F", "safety_guidance", "give conservative local safety guidance"),
    )

    for behavior_class, interaction_mode, query in skip_inputs:
        result = skip_read.execute(
            _plan(
                module,
                behavior_class=behavior_class,
                interaction_mode=interaction_mode,
                query=query,
                web_mode="disabled",
            )
        )
        assert result.items == ()
        assert all(trace.lane != "web" for trace in result.traces)
        assert all(
            limitation.code != "current_web_unavailable"
            for limitation in result.limitations
        )

    def official_web_search(request: Any) -> Any:
        assert request.web_policy.mode == "official_only"
        assert request.web_policy.allowed_domains == ("sz.gov.cn",)
        assert request.web_policy.max_provider_calls == 1
        assert request.web_policy.max_results == 3
        return _lane_result(
            module,
            _web_item(
                module,
                "official",
                "https://www.sz.gov.cn/official-help",
                source_authority="official",
            ),
            _web_item(
                module,
                "unverified",
                "https://unverified.example/claim",
            ),
        )

    official_read = module.create_ephemeral_knowledge_read(
        local_search=local_search,
        web_search=official_web_search,
        universal_web_policy=_web_policy(module, "universal"),
    )
    official_plan = _plan(
        module,
        behavior_class="F",
        interaction_mode="safety_guidance",
        query="请查深圳当前官方求助电话和政策页面",
        web_mode="official_only",
        freshness_material=True,
        allowed_domains=("sz.gov.cn",),
    )
    official_result = official_read.execute(official_plan)

    assert tuple(item.source_locator for item in official_result.items) == (
        "https://www.sz.gov.cn/official-help",
    )
    assert all(item.source_nature == "current_web" for item in official_result.items)
    official_evidence = official_result.items[0]
    assert official_evidence.source_authority == "official"
    assert official_evidence.web_snapshot.snapshot_id == (
        f"web-snapshot:sha256:{official_evidence.web_snapshot.content_sha256}"
    )
    assert official_evidence.web_snapshot.retrieved_at == NOW
    assert official_evidence.web_snapshot.byte_length > 0
    official_web_traces = tuple(
        trace for trace in official_result.traces if trace.lane == "web"
    )
    assert len(official_web_traces) == 1
    assert official_web_traces[0].status == "succeeded"
    assert official_web_traces[0].source_scope == "official_only"

    def missing_snapshot(_: Any) -> dict[str, Any]:
        return {
            "items": (
                {
                    "evidence_id": "web:missing-snapshot",
                    "object_id": "official-resource:1",
                    "domain": "company",
                    "lane": "web",
                    "source_nature": "current_web",
                    "source_authority": "official",
                    "source_locator": "https://www.sz.gov.cn/missing-snapshot",
                    "snippet": "Current official information without retained bytes.",
                    "score": 0.9,
                },
            )
        }

    invalid_read = module.create_ephemeral_knowledge_read(
        local_search=local_search,
        web_search=missing_snapshot,
        universal_web_policy=_web_policy(module, "universal"),
    )
    invalid_result = invalid_read.execute(
        _plan(
            module,
            behavior_class="F",
            interaction_mode="safety_guidance",
            query="请查深圳当前官方求助电话和政策页面",
            web_mode="official_only",
            freshness_material=True,
            allowed_domains=("sz.gov.cn",),
        )
    )
    assert all(item.source_nature != "current_web" for item in invalid_result.items)
    invalid_web_traces = tuple(
        trace for trace in invalid_result.traces if trace.lane == "web"
    )
    assert len(invalid_web_traces) == 1
    assert invalid_web_traces[0].status == "unavailable"
    assert invalid_web_traces[0].failure_kind == "invalid_output"


def test_web_failures_retain_local_evidence_and_record_material_limitation() -> None:
    module = _module()

    def local_search(request: Any) -> Any:
        return _lane_result(module, _local_item(module, request.behavior_class))

    def timeout(_: Any) -> Any:
        raise TimeoutError("recorded Web timeout")

    def connection_failure(_: Any) -> Any:
        raise ConnectionError("recorded Web connection failure")

    def invalid_output(_: Any) -> dict[str, Any]:
        return {"items": "not-a-sequence", "unexpected": True}

    failures = (
        (timeout, "timeout"),
        (connection_failure, "connection_failure"),
        (invalid_output, "invalid_output"),
    )
    for web_search, expected_failure_kind in failures:
        read = module.create_ephemeral_knowledge_read(
            local_search=local_search,
            web_search=web_search,
            universal_web_policy=_web_policy(module, "universal"),
        )
        plan = _plan(
            module,
            behavior_class="A",
            interaction_mode="information_retrieval",
            query="这家公司的最新状态是什么？",
            web_mode="universal",
            freshness_material=True,
        )

        result = read.execute(plan)
        local_items = tuple(
            item for item in result.items if item.source_nature == "local"
        )
        web_traces = tuple(trace for trace in result.traces if trace.lane == "web")
        limitations = tuple(
            limitation
            for limitation in result.limitations
            if limitation.code == "current_web_unavailable"
        )

        assert local_items == (_local_item(module, "A"),)
        assert all(item.source_nature != "current_web" for item in result.items)
        assert len(web_traces) == 1
        assert web_traces[0].status == "unavailable"
        assert web_traces[0].failure_kind == expected_failure_kind
        assert web_traces[0].candidate_count == 0
        assert all(trace.status != "succeeded" for trace in web_traces)
        assert len(limitations) == 1
        assert limitations[0].lane == "web"
        assert limitations[0].material is True
        assert limitations[0].impact == "freshness"
