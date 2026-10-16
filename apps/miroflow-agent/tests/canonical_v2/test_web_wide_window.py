"""Slice ①min — Web-only list-shaped window + its kill switch.

Fixture source: the round-42 reported ask (verbatim) plus the sibling suite's
window assertions (`test_knowledge_serving_isolated.py`). The bundle here is the
synthetic one (max_candidates=12, max_web_results=5), so the branch assertions
stay readable: bundle width / bundle sum / enumeration width.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving_module
from src.data_agents.canonical_v2.knowledge_read import QueryPlanningRequest
from src.data_agents.canonical_v2.knowledge_serving_isolated import (
    RecordedServingBundle,
)

NOW = datetime(2026, 10, 16, 4, 0, tzinfo=timezone.utc)
RELEASE_ID = "candidate-s12b-test"
LOCAL_LANES = ("exact", "structured", "lexical", "vector", "web")


def _bundle(tmp_path: Path) -> RecordedServingBundle:
    return RecordedServingBundle(
        schema_version="canonical-v2-serving-bundle-v1",
        bundle_id="serving-bundle:candidate-s12b-test",
        release_id=RELEASE_ID,
        database_name="miroflow_candidate_s12b_test",
        database_target_kind="disposable",
        index_target_id=f"index:{RELEASE_ID}",
        index_root=(tmp_path / "index").resolve(),
        envelope_path=(tmp_path / "envelope.json").resolve(),
        embedding_model_id="recorded-embedding-v1",
        planner_model_id="canonical-v2-deterministic-planner-v1",
        answer_model_id="canonical-v2-deterministic-answer-v1",
        web_provider="bocha-serper-v1",
        bocha_api_key_env="BOCHA_API_KEY",
        serper_api_key_env="SERPER_API_KEY",
        max_candidates=12,
        max_web_results=5,
        web_timeout_ms=1500,
        web_snapshot_max_bytes=16384,
    )


def _proposal(
    tmp_path: Path, query: str
) -> tuple[RecordedServingBundle, object]:
    bundle = _bundle(tmp_path)
    proposal = serving_module._proposal_provider(bundle=bundle)(
        QueryPlanningRequest(
            request_id="query-request:web-wide-window",
            release_id=RELEASE_ID,
            original_query=query,
            as_of=NOW,
        )
    )
    return bundle, proposal


@pytest.mark.parametrize(
    ("query", "lanes", "expected"),
    (
        # The reported case: Web-only and list-shaped -> the lane's own width.
        ("目前有哪几种主流的JEPA变体？", ("web",), "bundle_sum"),
        # Same family, different subject: the marker carries it, not the topic.
        ("目前有哪几种主流的联邦学习框架？", ("web",), "bundle_sum"),
        # Bare question word 谁 is not list-shaped -> the bundle width, as before.
        ("世界上最美丽的女人是谁", ("web",), "bundle"),
        # Local list turn -> the enumeration window, unchanged.
        ("深圳有哪些做具身智能的公司", LOCAL_LANES, "enumeration"),
    ),
)
def test_web_window_gate(
    tmp_path: Path, query: str, lanes: tuple[str, ...], expected: str
) -> None:
    bundle, proposal = _proposal(tmp_path, query)
    assert proposal.lanes == lanes
    # Candidates are never widened by this slice: the Web-only case keeps the
    # bundle sum it already had, and local turns keep their own rule.
    assert proposal.max_candidates == (
        serving_module._ENUMERATION_CANDIDATE_WINDOW
        if expected == "enumeration"
        else bundle.max_candidates + bundle.max_web_results
    )
    expected_window = {
        "bundle": bundle.max_web_results,
        "bundle_sum": bundle.max_candidates + bundle.max_web_results,
        "enumeration": serving_module._ENUMERATION_CANDIDATE_WINDOW,
    }[expected]
    assert proposal.max_web_results == expected_window


def test_kill_switch_restores_the_bundle_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = "目前有哪几种主流的JEPA变体？"
    bundle, _ = _proposal(tmp_path, query)  # default: on
    assert serving_module._web_wide_window_enabled() is True

    for value in ("0", "false", "OFF", "no"):
        monkeypatch.setenv(serving_module._WEB_WIDE_WINDOW_ENV, value)
        assert serving_module._web_wide_window_enabled() is False
        _, proposal = _proposal(tmp_path, query)
        assert proposal.max_web_results == bundle.max_web_results
        assert proposal.lanes == ("web",)
    monkeypatch.delenv(serving_module._WEB_WIDE_WINDOW_ENV)
    assert serving_module._web_wide_window_enabled() is True


def test_rewrite_prompt_keeps_an_english_view_for_abbreviations() -> None:
    prompt = serving_module._QUERY_REWRITE_SYSTEM_PROMPT
    assert "英文全称" in prompt and "英文关键词" in prompt
    assert "joint embedding predictive architecture variants" in prompt
    # The Chinese length rule stays scoped to Chinese queries only.
    assert "中文查询每条不超过30个字" in prompt


def _web_item(name: str, url: str) -> object:
    return serving_module._NormalizedWebResult(
        title=name,
        url=url,
        snippet="",
        summary="",
        primary_provider_version="bocha-v1",
        corroborating_provider_versions=(),
    )


def test_merge_cap_lets_every_view_into_the_window() -> None:
    """The list-shaped merge splits the window across views.

    Locked against the measured failure (2026-10-16): a junk-filled view 1 owned
    every kept slot and the rewrite views' material never reached the renderer.
    """
    view1 = tuple(_web_item(f"junk{i}", f"https://junk.test/{i}") for i in range(10))
    view2 = tuple(_web_item(f"real{i}", f"https://real.test/{i}") for i in range(3))

    capped = [
        item.title
        for item in serving_module._merge_web_results_across_views(
            [view1, view2], per_view_head=4
        )
    ]
    assert capped[:4] == ["junk0", "junk1", "junk2", "junk3"]
    assert "real0" in capped[:8], "view 2 must land inside a 16-wide window"

    plain = [
        item.title
        for item in serving_module._merge_web_results_across_views([view1, view2])
    ]
    assert "real0" not in plain[:8], "pre-slice behaviour buries view 2 behind junk"
