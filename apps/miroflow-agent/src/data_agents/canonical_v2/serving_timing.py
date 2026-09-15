"""Env-gated serving timing probe (serving-index-process-scope T1).

Set ``CANONICAL_V2_SERVING_TIMING_PATH`` to a file path and the serving
process appends one JSON line per instrumented step (step name, wall seconds,
pid, thread). Unset → every helper is a no-op that only reads an env var, so
production behavior and timing are unchanged.
"""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_LOCK = threading.Lock()


def serving_timing_path() -> str | None:
    value = os.environ.get("CANONICAL_V2_SERVING_TIMING_PATH", "").strip()
    return value or None


def record_step(name: str, seconds: float, **fields: object) -> None:
    path = serving_timing_path()
    if path is None:
        return
    payload = {
        "name": name,
        "seconds": round(seconds, 6),
        "pid": os.getpid(),
        "thread": threading.current_thread().name,
        "at": round(time.time(), 3),
    }
    payload.update(fields)
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    try:
        with _LOCK:
            with Path(path).open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
    except OSError:  # noqa: BLE001 - the probe must never fail the request
        return


class _Step:
    __slots__ = ("_name", "_started", "_fields")

    def __init__(self, name: str, fields: dict[str, object]) -> None:
        self._name = name
        self._fields = fields
        self._started = time.monotonic()

    def annotate(self, **fields: object) -> None:
        self._fields.update(fields)

    def stop(self) -> None:
        self._fields.setdefault("count", 1)
        record_step(self._name, time.monotonic() - self._started, **self._fields)

    def __enter__(self) -> "_Step":
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


@contextmanager
def timed_step(name: str, **fields: object) -> Iterator[_Step]:
    if serving_timing_path() is None:
        yield _NoopStep()
        return
    step = _Step(name, dict(fields))
    try:
        yield step
    finally:
        step.stop()


class _NoopStep:
    __slots__ = ()

    def annotate(self, **fields: object) -> None:
        return

    def stop(self) -> None:
        return


def bump_counter(name: str, **fields: object) -> None:
    if serving_timing_path() is None:
        return
    record_step(name, 0.0, **fields)
