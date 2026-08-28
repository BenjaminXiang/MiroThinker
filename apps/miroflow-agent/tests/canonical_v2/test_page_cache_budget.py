"""Page-text cache + extraction budget (fix-page-cache-extraction-budget, P2-A).

Turn-to-turn evidence drift traced to uncached page re-fetches (fresh
TCP+TLS inside a 2 s race per turn) and a 3000-char extraction cut that
dropped leaderboard tails before the selector ever saw them.
"""

from __future__ import annotations

from importlib import import_module

pf = import_module("src.data_agents.providers.page_fetch")


def _no_browser() -> object:
    raise RuntimeError("no browser in test")


def test_same_url_fetched_once_within_ttl(monkeypatch) -> None:
    calls: list[str] = []

    def direct(url: str) -> str | None:
        calls.append(url)
        return "正文" * 100

    fetcher = pf.create_tiered_page_fetcher(
        browser_factory=_no_browser, direct_fetcher=direct
    )
    first = fetcher("https://example.test/a")
    second = fetcher("https://example.test/a")
    assert first == second
    assert calls == ["https://example.test/a"]


def test_ttl_zero_disables_cache(monkeypatch) -> None:
    monkeypatch.setenv("CANONICAL_V2_PAGE_CACHE_TTL", "0")
    calls: list[str] = []

    def direct(url: str) -> str | None:
        calls.append(url)
        return "正文" * 100

    fetcher = pf.create_tiered_page_fetcher(
        browser_factory=_no_browser, direct_fetcher=direct
    )
    fetcher("https://example.test/a")
    fetcher("https://example.test/a")
    assert calls.count("https://example.test/a") == 2


def test_default_direct_uses_enlarged_budget(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_fetch(url: str, **kwargs: object) -> str | None:
        captured.update(kwargs)
        return "正文" * 200

    monkeypatch.setattr(pf, "fetch_page_text", fake_fetch)
    fetcher = pf.create_tiered_page_fetcher(browser_factory=_no_browser)
    text = fetcher("https://example.test/budget")
    assert text
    assert captured.get("max_chars") == 8000


def test_failed_fetch_not_cached() -> None:
    calls: list[str] = []

    def direct(url: str) -> str | None:
        calls.append(url)
        return None

    fetcher = pf.create_tiered_page_fetcher(
        browser_factory=_no_browser, direct_fetcher=direct
    )
    assert fetcher("https://example.test/none") is None
    assert fetcher("https://example.test/none") is None
    assert len(calls) == 2
