from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading
import time
from types import SimpleNamespace

from src.data_agents.company.provider_rate_limit import (
    ProviderRateLimiter,
    RateLimitedRequestsSession,
    wrap_openai_client,
)


def test_wrap_openai_client_rate_limits_chat_completion_create():
    calls: list[str] = []

    class _Limiter:
        def __enter__(self):
            calls.append("enter")

        def __exit__(self, exc_type, exc, tb):
            calls.append("exit")

    class _Completions:
        def create(self, **_kwargs):
            calls.append("create")
            return "ok"

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=_Completions()),
        other_attr="kept",
    )

    wrapped = wrap_openai_client(
        client,
        provider_key="deepseek",
        limiter_factory=lambda _provider_key: _Limiter(),
    )

    assert wrapped.chat.completions.create(model="deepseek-v4-pro") == "ok"
    assert wrapped.other_attr == "kept"
    assert calls == ["enter", "create", "exit"]


def test_rate_limited_requests_session_wraps_get_and_post():
    calls: list[str] = []

    class _Limiter:
        def __enter__(self):
            calls.append("enter")

        def __exit__(self, exc_type, exc, tb):
            calls.append("exit")

    class _Session:
        def get(self, url, **_kwargs):
            calls.append(f"get:{url}")
            return "get-ok"

        def post(self, url, **_kwargs):
            calls.append(f"post:{url}")
            return "post-ok"

    session = RateLimitedRequestsSession(
        _Session(),
        provider_key="serper",
        limiter_factory=lambda _provider_key: _Limiter(),
    )

    assert session.post("https://google.serper.dev/search") == "post-ok"
    assert session.get("https://example.com/page") == "get-ok"
    assert calls == [
        "enter",
        "post:https://google.serper.dev/search",
        "exit",
        "enter",
        "get:https://example.com/page",
        "exit",
    ]


def test_provider_rate_limiter_reads_provider_specific_env(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPANY_DEEPSEEK_MAX_CONCURRENCY", "7")
    monkeypatch.setenv("COMPANY_DEEPSEEK_MIN_INTERVAL_SECONDS", "0")

    limiter = ProviderRateLimiter("deepseek", lock_dir=tmp_path)

    assert limiter.max_concurrency == 7
    assert limiter.min_interval_seconds == 0.0


def test_provider_rate_limiter_defaults_to_eight_for_company_upload_scaleout(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv("COMPANY_DEEPSEEK_MAX_CONCURRENCY", raising=False)
    monkeypatch.delenv("COMPANY_SERPER_MAX_CONCURRENCY", raising=False)

    assert ProviderRateLimiter("deepseek", lock_dir=tmp_path).max_concurrency == 8
    assert ProviderRateLimiter("serper", lock_dir=tmp_path).max_concurrency == 8


def test_provider_rate_limiter_does_not_serialize_call_body(tmp_path):
    active = 0
    max_active = 0
    lock = threading.Lock()

    class _Completions:
        def create(self, **_kwargs):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.15)
            with lock:
                active -= 1
            return "ok"

    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    wrapped = wrap_openai_client(
        client,
        provider_key="deepseek",
        limiter_factory=lambda provider_key: ProviderRateLimiter(
            provider_key,
            lock_dir=tmp_path,
            max_concurrency=2,
            min_interval_seconds=0.0,
        ),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: wrapped.chat.completions.create(model="deepseek-v4-pro"),
                range(2),
            )
        )

    assert results == ["ok", "ok"]
    assert max_active == 2
