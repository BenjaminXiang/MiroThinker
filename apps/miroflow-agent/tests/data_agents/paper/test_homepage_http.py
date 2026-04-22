"""RED-phase tests for M2.4 Unit 5 — homepage HTTP fetcher.

Sync helper that fetches a single prof homepage URL with trust_env=False and
a per-host rate-limit gate (0.5s). Hermetic tests only.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.data_agents.paper.homepage_http import (
    _HOST_FETCH_GATE_SECONDS,
    _reset_host_gate_for_test,
    fetch_homepage_html,
)

# Capture real class references BEFORE any test patch runs (M0.1 learning).
_REAL_HTTPX_CLIENT = httpx.Client
_REAL_HTTPX_RESPONSE = httpx.Response


@pytest.fixture(autouse=True)
def _reset_gate():
    """Each test starts with a clean rate-limit dict."""
    _reset_host_gate_for_test()
    yield
    _reset_host_gate_for_test()


def _mock_response(text: str, *, status: int = 200, encoding: str | None = "utf-8"):
    resp = MagicMock(spec=_REAL_HTTPX_RESPONSE)
    resp.text = text
    resp.content = text.encode("utf-8")
    resp.status_code = status
    resp.encoding = encoding
    if 200 <= status < 300:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status}", request=MagicMock(), response=MagicMock(status_code=status)
        )
    return resp


def _fake_client(response):
    client = MagicMock(spec=_REAL_HTTPX_CLIENT)
    client.get.return_value = response
    client.trust_env = False
    return client


def test_fetch_returns_text_on_200():
    http = _fake_client(_mock_response("<html><body>hi</body></html>"))
    result = fetch_homepage_html("https://example.edu/prof", http_client=http)
    assert "<html>" in result
    assert "hi" in result


def test_fetch_raises_on_404():
    http = _fake_client(_mock_response("", status=404))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_homepage_html("https://example.edu/missing", http_client=http)


def test_fetch_raises_on_500():
    http = _fake_client(_mock_response("server error", status=500))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_homepage_html("https://example.edu/broken", http_client=http)


def test_fetch_uses_response_text_when_encoding_known():
    """If response.encoding is set, use response.text directly."""
    http = _fake_client(_mock_response("UTF-8 body ✓", encoding="utf-8"))
    result = fetch_homepage_html("https://example.edu/p", http_client=http)
    assert "UTF-8 body" in result


def test_fetch_owned_client_uses_trust_env_false_and_follow_redirects():
    with patch("src.data_agents.paper.homepage_http.httpx.Client") as ClientCls:
        owned = MagicMock(spec=_REAL_HTTPX_CLIENT)
        owned.get.return_value = _mock_response("<html></html>")
        ClientCls.return_value = owned
        fetch_homepage_html("https://example.edu/prof")
        _, kwargs = ClientCls.call_args
        assert kwargs.get("trust_env") is False
        assert kwargs.get("follow_redirects") is True


def test_fetch_passes_url_to_get():
    http = _fake_client(_mock_response("<html></html>"))
    fetch_homepage_html("https://example.edu/prof/doe", http_client=http)
    url_arg = http.get.call_args[0][0]
    assert url_arg == "https://example.edu/prof/doe"


# --- per-host rate-limit gate ---


def test_fetch_rate_limits_same_host():
    """Two calls to same host: second waits ≥ 0.5s after first."""
    http = _fake_client(_mock_response("<html></html>"))
    t0 = time.monotonic()
    fetch_homepage_html("https://example.edu/prof/a", http_client=http)
    fetch_homepage_html("https://example.edu/prof/b", http_client=http)
    elapsed = time.monotonic() - t0
    assert elapsed >= _HOST_FETCH_GATE_SECONDS


def test_fetch_does_not_rate_limit_across_different_hosts():
    """Two calls to different hosts should not wait for each other."""
    http = _fake_client(_mock_response("<html></html>"))
    t0 = time.monotonic()
    fetch_homepage_html("https://alpha.edu/prof/a", http_client=http)
    fetch_homepage_html("https://beta.edu/prof/b", http_client=http)
    elapsed = time.monotonic() - t0
    # Both calls should complete well under the 0.5s gate cumulatively.
    assert elapsed < _HOST_FETCH_GATE_SECONDS


def test_fetch_thread_safe_gate():
    """Concurrent callers against same host should serialize via lock."""
    http = _fake_client(_mock_response("<html></html>"))
    errors: list[Exception] = []

    def _call():
        try:
            fetch_homepage_html("https://concurrent.edu/prof", http_client=http)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_call) for _ in range(3)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    elapsed = time.monotonic() - t0
    assert errors == []
    # 3 serialized calls at 0.5s apart = at least 2 * 0.5 = 1.0s elapsed.
    assert elapsed >= _HOST_FETCH_GATE_SECONDS * 2 - 0.05  # small tolerance
