from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

OPENALEX_API_KEY_ENV_NAMES = ("OPENALEX_API_KEY", "OPENALEX_KEY")
OPENALEX_SKIP_WITHOUT_API_KEY_ENV = "OPENALEX_SKIP_WITHOUT_API_KEY"
DEFAULT_OPENALEX_RATE_LIMIT_COOLDOWN_SECONDS = 600.0
MAX_OPENALEX_RATE_LIMIT_COOLDOWN_SECONDS = 86_400.0


class OpenAlexRateLimitCircuit:
    def __init__(self, *, threshold: int, cooldown_seconds: float) -> None:
        self._threshold = threshold
        self._cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._failure_count = 0
        self._disabled_until: float | None = None

    def can_call(self) -> bool:
        with self._lock:
            if self._disabled_until is None:
                return True
            now = time.monotonic()
            if now < self._disabled_until:
                return False
            self._disabled_until = None
            self._failure_count = 0
            return True

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._disabled_until = None

    def record_rate_limit(self, cooldown_seconds: float | None = None) -> None:
        with self._lock:
            self._failure_count += 1
            if self._failure_count < self._threshold:
                return
            effective_cooldown = (
                cooldown_seconds
                if cooldown_seconds is not None
                else self._cooldown_seconds
            )
            self._disabled_until = time.monotonic() + effective_cooldown
            logger.warning(
                "OpenAlex temporarily disabled for %.0fs after %d consecutive 429 responses",
                effective_cooldown,
                self._failure_count,
            )

    def reset(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._disabled_until = None


OPENALEX_RATE_LIMIT_CIRCUIT = OpenAlexRateLimitCircuit(
    threshold=3,
    cooldown_seconds=DEFAULT_OPENALEX_RATE_LIMIT_COOLDOWN_SECONDS,
)


def openalex_api_key() -> str | None:
    for env_name in OPENALEX_API_KEY_ENV_NAMES:
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return None


def openalex_skip_without_api_key() -> bool:
    raw = os.getenv(OPENALEX_SKIP_WITHOUT_API_KEY_ENV, "").strip().casefold()
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def openalex_request_params(
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    api_key = openalex_api_key()
    if not api_key and openalex_skip_without_api_key():
        return None
    request_params = dict(params or {})
    if api_key:
        request_params["api_key"] = api_key
    return request_params


def openalex_rate_limit_cooldown_seconds(headers: Any) -> float | None:
    if not isinstance(headers, Mapping):
        return None
    for header_name in ("Retry-After", "X-RateLimit-Reset"):
        value = headers.get(header_name)
        if value is None:
            continue
        try:
            seconds = float(str(value).strip())
        except ValueError:
            continue
        if seconds <= 0:
            continue
        return min(seconds, MAX_OPENALEX_RATE_LIMIT_COOLDOWN_SECONDS)
    return None
