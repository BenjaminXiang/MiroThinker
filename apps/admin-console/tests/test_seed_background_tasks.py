from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.api import seeds as seeds_api


def test_run_seed_task_runs_quality_closure_after_successful_full_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.data_agents.professor.seed_runner as seed_runner

    seed_calls: list[dict[str, Any]] = []
    closure_calls: list[dict[str, Any]] = []

    def fake_run_single_seed(**kwargs: Any):
        seed_calls.append(kwargs)
        return SimpleNamespace(status="success")

    def fake_closure(**kwargs: Any) -> None:
        closure_calls.append(kwargs)

    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setattr(seed_runner, "run_single_seed", fake_run_single_seed)
    monkeypatch.setattr(
        seeds_api,
        "_run_seed_quality_closure_for_seed",
        fake_closure,
    )

    seeds_api._run_seed_task(seed_id=25, run_id="run-25", trigger_mode="full")

    assert seed_calls == [
        {
            "seed_id": 25,
            "dsn": "postgresql://example/db",
            "run_id": "run-25",
            "trigger_mode": "full",
            "limit": None,
        }
    ]
    assert closure_calls == [
        {
            "dsn": "postgresql://example/db",
            "seed_id": 25,
            "run_id": "run-25",
            "trigger_mode": "full",
            "limit": None,
        }
    ]


def test_run_seed_task_skips_quality_closure_for_sample_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.data_agents.professor.seed_runner as seed_runner

    closure_calls: list[dict[str, Any]] = []

    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setattr(
        seed_runner,
        "run_single_seed",
        lambda **_kwargs: SimpleNamespace(status="success"),
    )
    monkeypatch.setattr(
        seeds_api,
        "_run_seed_quality_closure_for_seed",
        lambda **kwargs: closure_calls.append(kwargs),
    )

    seeds_api._run_seed_task(
        seed_id=25,
        run_id="run-25",
        trigger_mode="sample",
        limit=3,
    )

    assert closure_calls == []


def test_run_seed_task_skips_quality_closure_for_limited_full_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.data_agents.professor.seed_runner as seed_runner

    closure_calls: list[dict[str, Any]] = []

    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setattr(
        seed_runner,
        "run_single_seed",
        lambda **_kwargs: SimpleNamespace(status="success"),
    )
    monkeypatch.setattr(
        seeds_api,
        "_run_seed_quality_closure_for_seed",
        lambda **kwargs: closure_calls.append(kwargs),
    )

    seeds_api._run_seed_task(
        seed_id=25,
        run_id="run-25",
        trigger_mode="full",
        limit=3,
    )

    assert closure_calls == []


def test_run_seed_task_skips_quality_closure_when_seed_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.data_agents.professor.seed_runner as seed_runner

    closure_calls: list[dict[str, Any]] = []

    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.setattr(
        seed_runner,
        "run_single_seed",
        lambda **_kwargs: SimpleNamespace(status="failure"),
    )
    monkeypatch.setattr(
        seeds_api,
        "_run_seed_quality_closure_for_seed",
        lambda **kwargs: closure_calls.append(kwargs),
    )

    seeds_api._run_seed_task(seed_id=25, run_id="run-25", trigger_mode="full")

    assert closure_calls == []


def test_run_seed_quality_closure_for_seed_uses_shared_llm_publication_extractor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.data_agents.professor import (
        core_profile_paper_quality_closure as closure_module,
    )

    conn = SimpleNamespace(commit=lambda: None)

    class _ConnectContext:
        def __enter__(self) -> Any:
            return conn

        def __exit__(self, *_args: Any) -> None:
            return None

    connect_context = _ConnectContext()
    called_kwargs: dict[str, Any] = {}
    sentinel_extractor = object()

    def fake_run_seed_quality_closure(**kwargs: Any) -> object:
        conn_arg = kwargs.pop("conn")
        assert conn_arg is conn
        called_kwargs.update(kwargs)
        return SimpleNamespace(status="success", stage_counts={})

    monkeypatch.setattr(
        seeds_api.psycopg,
        "connect",
        lambda *_args, **_kwargs: connect_context,
    )
    monkeypatch.setattr(
        closure_module,
        "run_seed_quality_closure",
        fake_run_seed_quality_closure,
    )
    monkeypatch.setattr(
        seeds_api,
        "_build_seed_followup_publication_extractor",
        lambda: sentinel_extractor,
        raising=False,
    )

    seeds_api._run_seed_quality_closure_for_seed(
        dsn="postgresql://example/db",
        seed_id=25,
        run_id="run-25",
        trigger_mode="full",
        limit=None,
    )

    assert called_kwargs["seed_id"] == 25
    assert called_kwargs["run_id"] == "run-25"
    assert called_kwargs["trigger_mode"] == "full"
    assert called_kwargs["limit"] is None
    assert called_kwargs["dsn"] == "postgresql://example/db"
    assert called_kwargs["commit_after_stage"] is True
    assert called_kwargs["publication_extractor"] is sentinel_extractor
