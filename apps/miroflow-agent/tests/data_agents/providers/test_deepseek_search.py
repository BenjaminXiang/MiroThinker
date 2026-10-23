from __future__ import annotations

import pytest

from src.data_agents.providers.deepseek_search import DeepSeekSearchProvider


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class _Session:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> _Response:
        self.calls.append({"url": url, **kwargs})
        return _Response(self.payload)


def test_deepseek_search_normalizes_results() -> None:
    session = _Session(
        {
            "results": [
                {
                    "title": "Xspark AI（无界智航）完成天使轮融资",
                    "url": "https://example.com/xspark",
                    "summary": "丁文伯为联合创始人。",
                    "authority": 4,
                },
                {"title": "", "url": "https://example.com/empty"},
            ]
        }
    )
    provider = DeepSeekSearchProvider(
        api_key="test-key",
        session=session,
        timeout=3.0,
    )

    payload = provider.search("丁文伯创办的公司")

    assert payload == {
        "organic": [
            {
                "link": "https://example.com/xspark",
                "url": "https://example.com/xspark",
                "title": "Xspark AI（无界智航）完成天使轮融资",
                "snippet": "丁文伯为联合创始人。",
                "summary": "丁文伯为联合创始人。",
            }
        ]
    }
    assert session.calls[0]["url"] == "https://api.deepseek.com/v1/tools/search"
    assert session.calls[0]["timeout"] == 3.0


def test_deepseek_search_requires_api_key() -> None:
    provider = DeepSeekSearchProvider(api_key="", session=_Session({}))
    with pytest.raises(RuntimeError, match="missing api key"):
        provider.search("丁文伯")
