from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

import httpx

_HOST_FETCH_GATE_SECONDS: float = 0.5
_HOST_LAST_FETCH: dict[str, float] = {}
_HOST_GATE_LOCK = threading.Lock()


def _reset_host_gate_for_test() -> None:
    with _HOST_GATE_LOCK:
        _HOST_LAST_FETCH.clear()


def _wait_for_host(hostname: str | None) -> None:
    if not hostname:
        return

    with _HOST_GATE_LOCK:
        now = time.monotonic()
        last_called_at = _HOST_LAST_FETCH.get(hostname)
        scheduled_at = now
        if last_called_at is not None:
            scheduled_at = max(now, last_called_at + _HOST_FETCH_GATE_SECONDS)
        _HOST_LAST_FETCH[hostname] = scheduled_at

    sleep_seconds = scheduled_at - now
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)


def fetch_homepage_html(
    url: str,
    *,
    http_client: httpx.Client | None = None,
) -> str:
    hostname = urlparse(url).hostname
    _wait_for_host(hostname)

    if http_client is not None:
        response = http_client.get(url)
        response.raise_for_status()
        return response.text

    client = httpx.Client(
        trust_env=False,
        follow_redirects=True,
    )
    try:
        response = client.get(url)
        response.raise_for_status()
        return response.text
    finally:
        client.close()
