from __future__ import annotations

import pytest

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving_module


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    """Keep destructive Canonical V2 migration tests on one database process."""
    del config
    return 0


@pytest.fixture(autouse=True)
def _disable_environment_llm_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep probe acceptance deterministic across the canonical_v2 suite.

    The production wiring builds a real LLM judge inside
    ``load_recorded_serving_inputs``, and an API key is resolvable in dev
    environments, so unpatched tests would make live LLM calls. Disabling
    the judge keeps every test on the deterministic rule path; the LLM
    rescue itself is covered by dedicated tests with test-owned judges.
    """
    monkeypatch.setattr(serving_module, "create_llm_judge", lambda *a, **kw: None)
