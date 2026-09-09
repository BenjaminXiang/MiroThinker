"""Hermetic tests for the batched fail-open LLM judgment harness.

The judge only ever *adds* recall on top of the deterministic path, so every
failure mode (timeout, unreachable provider, malformed JSON) must degrade to
permissive per-item defaults instead of shrinking recall. These tests inject
a stub OpenAI-compatible client through ``client_factory``; no network, env
settings, or real LLM is involved.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any

from src.data_agents.canonical_v2.llm_judgments import (
    GapCheckResult,
    RelevanceJudgment,
    _LlmJudge,
)


def _fake_client(content: str, *, sleep_seconds: float = 0.0) -> Any:
    def _create(**kwargs: Any) -> Any:
        del kwargs
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    completions = SimpleNamespace(create=_create)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_relevance_batch_parses_structured_results() -> None:
    payload = json.dumps(
        {
            "judgments": [
                {
                    "item_id": "a",
                    "relevant": True,
                    "entity_ids": ["company-c-1"],
                    "fact": "某公司由某教授参与创立。",
                },
                {"item_id": "b", "relevant": False},
            ]
        },
        ensure_ascii=False,
    )
    judge = _LlmJudge(client_factory=lambda **kw: _fake_client(payload))

    results = judge.judge_batch(
        "relevance",
        "某公司的创始人是谁？",
        {"a": "某公司由某教授参与创立。", "b": "无关条目。"},
    )

    assert results == (
        RelevanceJudgment(
            item_id="a",
            relevant=True,
            entity_ids=("company-c-1",),
            fact="某公司由某教授参与创立。",
        ),
        RelevanceJudgment(item_id="b", relevant=False),
    )
    assert judge.last_outcome == "ok"


def test_timeout_fails_open_with_attributed_defaults() -> None:
    judge = _LlmJudge(
        client_factory=lambda **kw: _fake_client("{}", sleep_seconds=2.5),
        timeout_seconds=0.2,
    )

    results = judge.judge_batch(
        "relevance",
        "某公司的创始人是谁？",
        {"a": "正文甲。", "b": "正文乙。"},
    )

    assert results == (
        RelevanceJudgment(item_id="a", relevant=True),
        RelevanceJudgment(item_id="b", relevant=True),
    )
    assert judge.last_outcome == "timeout_fail_open"


def test_invalid_json_fails_open() -> None:
    judge = _LlmJudge(client_factory=lambda **kw: _fake_client("not json at all"))

    results = judge.judge_batch("relevance", "某公司的创始人是谁？", {"a": "正文。"})

    assert results == (RelevanceJudgment(item_id="a", relevant=True),)
    assert judge.last_outcome == "invalid_output_fail_open"


def test_gap_check_parses_followup_queries_capped_at_two() -> None:
    payload = json.dumps(
        {
            "covered": False,
            "missing_aspects": ["融资信息"],
            "followup_queries": ["补查一", "补查二", "补查三"],
        },
        ensure_ascii=False,
    )
    judge = _LlmJudge(client_factory=lambda **kw: _fake_client(payload))

    results = judge.judge_batch(
        "gap_check",
        "某公司创始团队与融资情况如何？",
        {"e-1": "证据：某公司由某教授参与创立。"},
    )

    assert results == (
        GapCheckResult(
            covered=False,
            missing_aspects=("融资信息",),
            followup_queries=("补查一", "补查二"),
        ),
    )
    assert judge.last_outcome == "ok"


def test_token_bucket_limits_calls_per_second() -> None:
    payload = json.dumps(
        {"covered": True, "missing_aspects": [], "followup_queries": []},
        ensure_ascii=False,
    )
    judge = _LlmJudge(
        client_factory=lambda **kw: _fake_client(payload),
        max_calls_per_second=2,
    )

    started = time.monotonic()
    for _ in range(3):
        judge.judge_batch("gap_check", "问题", {"e-1": "证据。"})
    elapsed = time.monotonic() - started

    assert elapsed >= 0.5
