from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.data_agents.professor.llm_profiles import (
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)


CompanyLLMTaskType = Literal[
    "search_hint_generation",
    "identity_alias_extraction",
    "trusted_xlsx_structuring",
    "snippet_triage",
    "source_judgment",
    "generic_product_admission",
    "product_ownership_attribution",
    "financing_extraction",
    "financing_conflict_judgment",
    "multi_source_profile_synthesis",
    "technology_route_synthesis",
    "quality_audit",
]

COMPANY_LLM_LITE_TASKS: frozenset[str] = frozenset(
    {
        "search_hint_generation",
        "identity_alias_extraction",
        "trusted_xlsx_structuring",
    }
)

COMPANY_LLM_PRO_TASKS: frozenset[str] = frozenset(
    {
        "snippet_triage",
        "source_judgment",
        "generic_product_admission",
        "product_ownership_attribution",
        "financing_extraction",
        "financing_conflict_judgment",
        "multi_source_profile_synthesis",
        "technology_route_synthesis",
        "quality_audit",
    }
)

_PROFILE_BY_TASK: dict[str, str] = {
    **{task: "deepseek-v4-lite" for task in COMPANY_LLM_LITE_TASKS},
    **{task: "deepseek-v4-pro" for task in COMPANY_LLM_PRO_TASKS},
}

_DEFAULT_TIMEOUT_BY_TASK: dict[str, float] = {
    "search_hint_generation": 45.0,
    "identity_alias_extraction": 45.0,
    "trusted_xlsx_structuring": 45.0,
    "snippet_triage": 60.0,
    "source_judgment": 60.0,
    "generic_product_admission": 60.0,
    "product_ownership_attribution": 60.0,
    "financing_extraction": 90.0,
    "financing_conflict_judgment": 90.0,
    "multi_source_profile_synthesis": 90.0,
    "technology_route_synthesis": 90.0,
    "quality_audit": 90.0,
}

_DEFAULT_RETRY_BUDGET_BY_TASK: dict[str, int] = {
    "search_hint_generation": 1,
    "identity_alias_extraction": 1,
    "trusted_xlsx_structuring": 1,
    "snippet_triage": 1,
    "source_judgment": 1,
    "generic_product_admission": 1,
    "product_ownership_attribution": 1,
    "financing_extraction": 1,
    "financing_conflict_judgment": 1,
    "multi_source_profile_synthesis": 2,
    "technology_route_synthesis": 2,
    "quality_audit": 1,
}


@dataclass(frozen=True, slots=True)
class CompanyLLMTaskSettings:
    task_type: str
    llm_profile: str
    base_url: str
    model: str
    api_key: str
    extra_body: dict[str, object]
    timeout_seconds: float
    retry_budget: int
    cascade_strategy: str = "direct"

    def audit_metadata(self) -> dict[str, object]:
        return {
            "task_type": self.task_type,
            "llm_profile": self.llm_profile,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "retry_budget": self.retry_budget,
            "cascade_strategy": self.cascade_strategy,
        }


def resolve_company_llm_task_settings(
    task_type: str,
    *,
    timeout_seconds: float | None = None,
    retry_budget: int | None = None,
) -> CompanyLLMTaskSettings:
    profile_name = _PROFILE_BY_TASK.get(task_type)
    if profile_name is None:
        available = ", ".join(sorted(_PROFILE_BY_TASK))
        raise ValueError(
            f"Unknown Company LLM task '{task_type}'. Available tasks: {available}."
        )

    settings = resolve_professor_llm_settings(
        profile_name,
        strict=True,
        include_profile=True,
        apply_endpoint_env_overrides=False,
    )
    model = settings["local_llm_model"]
    return CompanyLLMTaskSettings(
        task_type=task_type,
        llm_profile=settings["llm_profile"],
        base_url=settings["local_llm_base_url"],
        model=model,
        api_key=settings["local_llm_api_key"],
        extra_body=build_non_thinking_extra_body(model),
        timeout_seconds=(
            float(timeout_seconds)
            if timeout_seconds is not None
            else _DEFAULT_TIMEOUT_BY_TASK[task_type]
        ),
        retry_budget=(
            int(retry_budget)
            if retry_budget is not None
            else _DEFAULT_RETRY_BUDGET_BY_TASK[task_type]
        ),
    )
