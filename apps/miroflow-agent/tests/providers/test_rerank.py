"""RED-phase tests for M0.1 RerankerClient.

Source of truth: docs/plans/2026-04-20-004-m0.1-reranker-client.md Unit 2.
Requirements: R1-R5 (sort, empty, top_n, missing-key, trust_env).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.data_agents.providers.rerank import RerankerClient, RerankResult


def _mock_response(results_payload):
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = {"results": results_payload}
    resp.raise_for_status.return_value = None
    return resp


def _fake_http_client(response):
    client = MagicMock(spec=httpx.Client)
    client.post.return_value = response
    client.trust_env = False
    client.is_closed = False
    return client


def test_returns_sorted_results_happy_path():
    """Response parses index/score/document, three document shapes covered."""
    response = _mock_response(
        [
            {"index": 0, "relevance_score": 0.9, "document": {"text": "doc-a"}},
            {"index": 2, "relevance_score": 0.5, "document": "doc-c-str"},
            {"index": 1, "relevance_score": 0.1},  # no document field
        ]
    )
    http = _fake_http_client(response)
    client = RerankerClient(api_key="k", client=http)
    results = client.rerank("query", ["orig-a", "orig-b", "orig-c"])
    assert len(results) == 3
    assert [r.index for r in results] == [0, 2, 1]
    assert [r.score for r in results] == [0.9, 0.5, 0.1]
    assert results[0].document == "doc-a"
    assert results[1].document == "doc-c-str"
    assert results[2].document == "orig-b"  # fallback to documents[index]
    assert isinstance(results[0], RerankResult)


def test_top_n_is_sent_in_payload():
    response = _mock_response(
        [{"index": 0, "relevance_score": 0.9, "document": "a"}]
    )
    http = _fake_http_client(response)
    client = RerankerClient(api_key="k", client=http)
    client.rerank("q", ["a", "b", "c"], top_n=2)
    body = http.post.call_args.kwargs["json"]
    assert body["top_n"] == 2
    assert body["query"] == "q"
    assert body["documents"] == ["a", "b", "c"]


def test_empty_documents_returns_empty_without_http():
    http = _fake_http_client(_mock_response([]))
    client = RerankerClient(api_key="k", client=http)
    result = client.rerank("q", [])
    assert result == []
    http.post.assert_not_called()


def test_top_n_exceeds_len_documents_truncates():
    response = _mock_response(
        [
            {"index": 0, "relevance_score": 0.8, "document": "a"},
            {"index": 1, "relevance_score": 0.3, "document": "b"},
        ]
    )
    http = _fake_http_client(response)
    client = RerankerClient(api_key="k", client=http)
    client.rerank("q", ["a", "b"], top_n=10)
    body = http.post.call_args.kwargs["json"]
    assert body["top_n"] == 2


def test_missing_api_key_raises_runtime_error():
    http = _fake_http_client(_mock_response([]))
    client = RerankerClient(api_key="", client=http)
    with pytest.raises(RuntimeError, match="API key"):
        client.rerank("q", ["a"])
    http.post.assert_not_called()


def test_http_error_propagates():
    resp = MagicMock(spec=httpx.Response)
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Server Error",
        request=MagicMock(),
        response=MagicMock(status_code=500),
    )
    http = _fake_http_client(resp)
    client = RerankerClient(api_key="k", client=http)
    with pytest.raises(httpx.HTTPStatusError):
        client.rerank("q", ["a"])


def test_context_manager_closes_owned_client():
    """Internally owned httpx.Client must be closed on __exit__."""
    with patch("src.data_agents.providers.rerank.httpx.Client") as ClientCls:
        owned = MagicMock(spec=httpx.Client)
        owned.is_closed = False
        ClientCls.return_value = owned
        with RerankerClient(api_key="k"):
            pass
        owned.close.assert_called_once()


def test_does_not_close_injected_client():
    """Caller-provided httpx.Client must NOT be closed by context manager."""
    injected = MagicMock(spec=httpx.Client)
    with RerankerClient(api_key="k", client=injected):
        pass
    injected.close.assert_not_called()


def test_trust_env_false_on_owned_client():
    """Internally owned httpx.Client must be constructed with trust_env=False."""
    with patch("src.data_agents.providers.rerank.httpx.Client") as ClientCls:
        RerankerClient(api_key="k")
        assert ClientCls.called
        _, kwargs = ClientCls.call_args
        assert kwargs.get("trust_env") is False
