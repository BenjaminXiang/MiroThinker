from __future__ import annotations

import pytest

from src.data_agents.company.llm_routing import (
    COMPANY_LLM_LITE_TASKS,
    COMPANY_LLM_PRO_TASKS,
    resolve_company_llm_task_settings,
)


@pytest.mark.parametrize(
    "task_type",
    sorted(COMPANY_LLM_LITE_TASKS),
)
def test_low_risk_company_llm_tasks_use_deepseek_v4_lite(
    monkeypatch: pytest.MonkeyPatch,
    task_type: str,
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")

    settings = resolve_company_llm_task_settings(task_type)

    assert settings.llm_profile == "deepseekv4lite"
    assert settings.model == "deepseek-v4-lite"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.api_key == "deepseek-key"
    assert settings.cascade_strategy == "direct"
    assert settings.audit_metadata() == {
        "task_type": task_type,
        "llm_profile": "deepseekv4lite",
        "model": "deepseek-v4-lite",
        "timeout_seconds": settings.timeout_seconds,
        "retry_budget": settings.retry_budget,
        "cascade_strategy": "direct",
    }


@pytest.mark.parametrize(
    "task_type",
    sorted(COMPANY_LLM_PRO_TASKS),
)
def test_judgment_sensitive_company_llm_tasks_use_deepseek_v4_pro_directly(
    monkeypatch: pytest.MonkeyPatch,
    task_type: str,
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")

    settings = resolve_company_llm_task_settings(task_type)

    assert settings.llm_profile == "deepseekv4pro"
    assert settings.model == "deepseek-v4-pro"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.api_key == "deepseek-key"
    assert settings.cascade_strategy == "direct"
    assert settings.audit_metadata()["cascade_strategy"] != "lite_then_pro"


def test_company_llm_task_routing_rejects_unknown_task():
    with pytest.raises(ValueError, match="Unknown Company LLM task"):
        resolve_company_llm_task_settings("unknown_task")
