from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import time
from typing import Any, Callable


_DEFAULT_MAX_CONCURRENCY: dict[str, int] = {
    "deepseek": 8,
    "serper": 8,
}
_DEFAULT_MIN_INTERVAL_SECONDS: dict[str, float] = {
    "deepseek": 0.05,
    "serper": 0.10,
}
_DEFAULT_LOCK_DIR = Path(
    os.environ.get("COMPANY_PROVIDER_RATE_LIMIT_DIR", "/tmp/mirothinker-company-rate-limit")
)


def _env_key(provider_key: str, suffix: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in provider_key.upper())
    return f"COMPANY_{cleaned}_{suffix}"


def _read_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _read_float_env(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, str(default))))
    except ValueError:
        return default


@dataclass(slots=True)
class ProviderRateLimiter(AbstractContextManager["ProviderRateLimiter"]):
    provider_key: str
    lock_dir: Path = _DEFAULT_LOCK_DIR
    max_concurrency: int | None = None
    min_interval_seconds: float | None = None

    def __post_init__(self) -> None:
        key = self.provider_key.strip().lower() or "default"
        self.provider_key = key
        default_max = _DEFAULT_MAX_CONCURRENCY.get(key, 2)
        default_interval = _DEFAULT_MIN_INTERVAL_SECONDS.get(key, 0.0)
        if self.max_concurrency is None:
            self.max_concurrency = _read_int_env(
                _env_key(key, "MAX_CONCURRENCY"),
                default_max,
            )
        if self.min_interval_seconds is None:
            self.min_interval_seconds = _read_float_env(
                _env_key(key, "MIN_INTERVAL_SECONDS"),
                default_interval,
            )
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self._slot_handle: Any | None = None
        self._interval_handle: Any | None = None

    def __enter__(self) -> "ProviderRateLimiter":
        self._acquire_slot()
        try:
            self._respect_interval()
        except Exception:
            self._release_interval_lock()
            self._release_slot_lock()
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._release_interval_lock()
        self._release_slot_lock()

    def _acquire_slot(self) -> None:
        slot_count = max(1, int(self.max_concurrency or 1))
        while True:
            for index in range(slot_count):
                handle = (self.lock_dir / f"{self.provider_key}.{index}.slot").open("a+")
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    handle.close()
                    continue
                self._slot_handle = handle
                return
            time.sleep(0.05)

    def _respect_interval(self) -> None:
        handle = (self.lock_dir / f"{self.provider_key}.interval").open("a+")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        self._interval_handle = handle
        try:
            interval = float(self.min_interval_seconds or 0.0)
            if interval <= 0:
                handle.seek(0)
                handle.truncate()
                handle.write(str(time.monotonic()))
                handle.flush()
                return
            handle.seek(0)
            raw = handle.read().strip()
            try:
                previous = float(raw)
            except ValueError:
                previous = 0.0
            wait_for = interval - (time.monotonic() - previous)
            if wait_for > 0:
                time.sleep(wait_for)
            handle.seek(0)
            handle.truncate()
            handle.write(str(time.monotonic()))
            handle.flush()
        finally:
            self._release_interval_lock()

    def _release_interval_lock(self) -> None:
        if self._interval_handle is not None:
            fcntl.flock(self._interval_handle.fileno(), fcntl.LOCK_UN)
            self._interval_handle.close()
            self._interval_handle = None

    def _release_slot_lock(self) -> None:
        if self._slot_handle is not None:
            fcntl.flock(self._slot_handle.fileno(), fcntl.LOCK_UN)
            self._slot_handle.close()
            self._slot_handle = None


class _RateLimitedCompletions:
    def __init__(
        self,
        completions: Any,
        *,
        provider_key: str,
        limiter_factory: Callable[[str], AbstractContextManager[Any]],
    ) -> None:
        self._completions = completions
        self._provider_key = provider_key
        self._limiter_factory = limiter_factory

    def create(self, *args: Any, **kwargs: Any) -> Any:
        with self._limiter_factory(self._provider_key):
            return self._completions.create(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._completions, name)


class _RateLimitedChat:
    def __init__(
        self,
        chat: Any,
        *,
        provider_key: str,
        limiter_factory: Callable[[str], AbstractContextManager[Any]],
    ) -> None:
        self._chat = chat
        self.completions = _RateLimitedCompletions(
            chat.completions,
            provider_key=provider_key,
            limiter_factory=limiter_factory,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._chat, name)


class _RateLimitedOpenAIClient:
    def __init__(
        self,
        client: Any,
        *,
        provider_key: str,
        limiter_factory: Callable[[str], AbstractContextManager[Any]],
    ) -> None:
        self._client = client
        self.chat = _RateLimitedChat(
            client.chat,
            provider_key=provider_key,
            limiter_factory=limiter_factory,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def wrap_openai_client(
    client: Any,
    *,
    provider_key: str,
    limiter_factory: Callable[[str], AbstractContextManager[Any]] = ProviderRateLimiter,
) -> Any:
    if not hasattr(client, "chat") or not hasattr(client.chat, "completions"):
        return client
    return _RateLimitedOpenAIClient(
        client,
        provider_key=provider_key,
        limiter_factory=limiter_factory,
    )


class RateLimitedRequestsSession:
    def __init__(
        self,
        session: Any,
        *,
        provider_key: str,
        limiter_factory: Callable[[str], AbstractContextManager[Any]] = ProviderRateLimiter,
    ) -> None:
        self._session = session
        self._provider_key = provider_key
        self._limiter_factory = limiter_factory

    def get(self, *args: Any, **kwargs: Any) -> Any:
        with self._limiter_factory(self._provider_key):
            return self._session.get(*args, **kwargs)

    def post(self, *args: Any, **kwargs: Any) -> Any:
        with self._limiter_factory(self._provider_key):
            return self._session.post(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)
