"""Unit tests for the remote relevance reranker adapter."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from src.data_agents.canonical_v2 import rerank_client as rc


def _transport(response: Any) -> tuple[Any, dict[str, Any]]:
    calls: dict[str, Any] = {}

    def call(url: str, payload: dict[str, Any], api_key: str, timeout: float) -> Any:
        calls["url"] = url
        calls["payload"] = payload
        calls["api_key"] = api_key
        calls["timeout"] = timeout
        return response

    return call, calls


def _scores(*pairs: tuple[int, float]) -> dict[str, Any]:
    return {
        "results": [
            {"index": index, "relevance_score": score} for index, score in pairs
        ]
    }


@pytest.fixture(autouse=True)
def _clear_configured_cache() -> Any:
    rc.configured_reranker.cache_clear()
    yield
    rc.configured_reranker.cache_clear()


def test_configured_reranker_is_absent_without_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(rc.ENV_BASE_URL, raising=False)
    assert rc.configured_reranker() is None


def test_configured_reranker_reads_env_and_key_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key_file = tmp_path / "rerank.key"
    key_file.write_text("file-secret\n", encoding="utf-8")
    monkeypatch.setenv(rc.ENV_BASE_URL, "http://127.0.0.1:18006/")
    monkeypatch.setenv(rc.ENV_MODEL, "qwen3-reranker-8b")
    monkeypatch.setenv(rc.ENV_API_KEY_FILE, str(key_file))
    monkeypatch.setenv(rc.ENV_TIMEOUT_SECONDS, "1.5")
    monkeypatch.setenv(rc.ENV_MAX_DOCUMENTS, "32")
    monkeypatch.delenv(rc.ENV_API_KEY, raising=False)

    reranker = rc.configured_reranker()

    assert reranker is not None
    assert reranker.endpoint == "http://127.0.0.1:18006/v1/rerank"
    assert reranker.model_id == "qwen3-reranker-8b"
    assert reranker.max_documents == 32
    assert reranker._api_key == "file-secret"
    assert reranker._timeout_seconds == 1.5


def test_score_sends_query_documents_and_model() -> None:
    call, calls = _transport(_scores((0, 0.9), (1, 0.1)))
    reranker = rc.RemoteReranker(
        base_url="http://rerank.test",
        model="qwen3-reranker-8b",
        api_key="secret",
        transport=call,
    )

    scores = reranker.score("深圳有哪些做机器人的公司", ("优必选", "招商银行"))

    assert scores == (0.9, 0.1)
    assert calls["url"] == "http://rerank.test/v1/rerank"
    assert calls["payload"] == {
        "model": "qwen3-reranker-8b",
        "query": "深圳有哪些做机器人的公司",
        "documents": ["优必选", "招商银行"],
        "top_n": 2,
    }
    assert calls["api_key"] == "secret"


def test_score_realigns_results_by_index() -> None:
    call, _ = _transport(_scores((1, 0.8), (0, 0.2)))
    reranker = rc.RemoteReranker(base_url="http://rerank.test", transport=call)

    assert reranker.score("q", ("a", "b")) == (0.2, 0.8)


@pytest.mark.parametrize(
    "response",
    [
        pytest.param({"results": []}, id="empty-results"),
        pytest.param({"results": [{"index": 0, "relevance_score": 0.5}]}, id="missing-doc"),
        pytest.param(
            {"results": [{"index": 0, "relevance_score": 0.5}, {"index": 0, "relevance_score": 0.4}]},
            id="duplicate-index",
        ),
        pytest.param({"results": [{"index": 5, "relevance_score": 0.5}]}, id="out-of-range"),
        pytest.param(
            {"results": [{"index": 0, "relevance_score": "high"}]},
            id="non-numeric",
        ),
        pytest.param(
            {"results": [{"index": 0, "relevance_score": float("nan")}]},
            id="non-finite",
        ),
        pytest.param({"results": [{"relevance_score": 0.5}]}, id="missing-index"),
        pytest.param([{"index": 0, "relevance_score": 0.5}], id="not-an-object"),
        pytest.param({"results": "nope"}, id="results-not-a-list"),
    ],
)
def test_score_rejects_malformed_responses(response: Any) -> None:
    call, _ = _transport(response)
    reranker = rc.RemoteReranker(base_url="http://rerank.test", transport=call)

    with pytest.raises(rc.RerankUnavailable):
        reranker.score("q", ("a", "b"))


def test_score_wraps_transport_failures() -> None:
    def failing(url: str, payload: dict[str, Any], api_key: str, timeout: float) -> Any:
        raise OSError("connection refused")

    reranker = rc.RemoteReranker(base_url="http://rerank.test", transport=failing)

    with pytest.raises(rc.RerankUnavailable):
        reranker.score("q", ("a",))


def test_score_enforces_document_cap() -> None:
    call, _ = _transport(_scores((0, 0.5)))
    reranker = rc.RemoteReranker(
        base_url="http://rerank.test",
        max_documents=2,
        transport=call,
    )

    with pytest.raises(rc.RerankUnavailable):
        reranker.score("q", ("a", "b", "c"))


def test_score_returns_empty_without_documents() -> None:
    call, calls = _transport({})
    reranker = rc.RemoteReranker(base_url="http://rerank.test", transport=call)

    assert reranker.score("q", ()) == ()
    assert calls == {}


def test_debug_logging_omits_query_and_document_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    call, _ = _transport(_scores((0, 0.7)))
    reranker = rc.RemoteReranker(
        base_url="http://rerank.test",
        transport=call,
        debug=True,
    )
    with caplog.at_level(logging.INFO, logger=rc.__name__):
        reranker.score(
            "深圳有哪些做机器人的公司",
            ("深圳市优必选科技股份有限公司 人形机器人",),
        )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "http://rerank.test/v1/rerank" in rendered
    assert "深圳有哪些做机器人的公司" not in rendered
    assert "优必选" not in rendered


def test_post_json_never_logs_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(_scores((0, 0.4))).encode("utf-8")

    def fake_urlopen(request: Any, timeout: float) -> Any:
        captured["headers"] = dict(request.headers)
        captured["body"] = request.data
        return _Response()

    monkeypatch.setattr(rc.urllib.request, "urlopen", fake_urlopen)

    scores = rc._post_json("http://rerank.test/v1/rerank", {"query": "q"}, "top-secret", 2.0)

    assert scores == {"results": [{"index": 0, "relevance_score": 0.4}]}
    assert captured["headers"]["Authorization"] == "Bearer top-secret"
