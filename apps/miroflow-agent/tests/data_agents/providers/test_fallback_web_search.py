from __future__ import annotations

from src.data_agents.providers.fallback_web_search import FallbackWebSearchProvider


class _Provider:
    def __init__(self, name: str, payload: object, *, api_key: str = "") -> None:
        self.name = name
        self.payload = payload
        self.api_key = api_key
        self.calls = 0

    def search(self, query: str, **kwargs: object) -> object:
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_fallback_uses_first_provider_with_results() -> None:
    first = _Provider(
        "deepseek",
        {"organic": [{"title": "A", "link": "https://example.com/a"}]},
        api_key="key",
    )
    second = _Provider("bocha", {"organic": [{"title": "B"}]})
    provider = FallbackWebSearchProvider(providers=(first, second))

    result = provider.search("丁文伯 专利")

    assert result["organic"][0]["title"] == "A"
    assert first.calls == 1
    assert second.calls == 0
    assert provider.api_key == "key"


def test_fallback_tries_next_on_error_or_empty() -> None:
    failing = _Provider("deepseek", RuntimeError("no credits"))
    empty = _Provider("bocha", {"organic": []})
    working = _Provider("serper", {"organic": [{"title": "C"}]})
    provider = FallbackWebSearchProvider(providers=(failing, empty, working))

    result = provider.search("优必选 专利")

    assert result["organic"] == [{"title": "C"}]
    assert failing.calls == 1
    assert empty.calls == 1
    assert working.calls == 1


def test_fallback_returns_empty_when_all_fail() -> None:
    provider = FallbackWebSearchProvider(
        providers=(
            _Provider("deepseek", RuntimeError("down")),
            _Provider("bocha", {"organic": []}),
        )
    )

    assert provider.search("anything") == {"organic": []}
