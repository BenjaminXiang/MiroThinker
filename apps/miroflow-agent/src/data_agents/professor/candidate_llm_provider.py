from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from .dataset_candidate_generation import (
    CandidateLLMOutput,
    ProfessorPaperSummaryGenerationInput,
    ProfileSummaryInput,
)
from .llm_profiles import build_non_thinking_extra_body, resolve_professor_llm_settings

ProfessorCandidateLLMTaskType = Literal[
    "profile_summary_synthesis",
    "research_overview_translation",
    "paper_summary_synthesis",
]

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_DEFAULT_PROFILE = "deepseek-v4-pro"
_DEFAULT_TIMEOUT_BY_TASK: dict[str, float] = {
    "profile_summary_synthesis": 90.0,
    "research_overview_translation": 60.0,
    "paper_summary_synthesis": 90.0,
}
_DEFAULT_RETRY_BUDGET_BY_TASK: dict[str, int] = {
    "profile_summary_synthesis": 1,
    "research_overview_translation": 1,
    "paper_summary_synthesis": 1,
}
_OUTPUT_KEY_BY_TASK: dict[str, str] = {
    "profile_summary_synthesis": "candidate_profile_summary",
    "research_overview_translation": "candidate_research_overview_zh",
    "paper_summary_synthesis": "candidate_paper_summary",
}


@dataclass(frozen=True, slots=True)
class ProfessorCandidateLLMTaskSettings:
    task_type: str
    llm_profile: str
    base_url: str
    model: str
    api_key: str
    extra_body: dict[str, Any]
    timeout_seconds: float
    retry_budget: int

    def audit_metadata(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "llm_profile": self.llm_profile,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "retry_budget": self.retry_budget,
        }


class CandidateLLMProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider_metadata: dict[str, Any],
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.provider_metadata = provider_metadata
        self.retryable = retryable


class MissingLLMCredentials(CandidateLLMProviderError):
    pass


class EmptyLLMResponse(CandidateLLMProviderError):
    pass


class MalformedLLMJSON(CandidateLLMProviderError):
    pass


class ProfessorCandidateLLMProvider:
    def __init__(
        self,
        *,
        settings: ProfessorCandidateLLMTaskSettings,
        client: Any | None = None,
    ) -> None:
        self.settings = settings
        self.client = client if client is not None else self._open_client_if_configured()

    @property
    def provider_name(self) -> str:
        return self.settings.model

    def generate_profile_summary(
        self,
        profile_input: ProfileSummaryInput,
    ) -> CandidateLLMOutput:
        return self._call_candidate_json(
            task_type="profile_summary_synthesis",
            output_key="candidate_profile_summary",
            system_prompt=(
                "你是高校教师画像候选生成器。只基于给定官方资料生成中文候选摘要，"
                "必须输出严格 JSON。"
            ),
            user_prompt=_build_profile_summary_prompt(profile_input),
        )

    def translate_research_overview(self, source_text: str) -> CandidateLLMOutput:
        return self._call_candidate_json(
            task_type="research_overview_translation",
            output_key="candidate_research_overview_zh",
            system_prompt=(
                "你是高校教师研究方向翻译器。只翻译和整理给定英文来源，"
                "不要添加来源外事实，必须输出严格 JSON。"
            ),
            user_prompt=_build_research_translation_prompt(source_text),
        )

    def generate_paper_summary(
        self,
        generation_input: ProfessorPaperSummaryGenerationInput,
    ) -> CandidateLLMOutput:
        return self._call_candidate_json(
            task_type="paper_summary_synthesis",
            output_key="candidate_paper_summary",
            system_prompt=(
                "你是高校教师论文产出候选摘要生成器。只基于已验证论文输入生成中文候选，"
                "必须输出严格 JSON。"
            ),
            user_prompt=_build_paper_summary_prompt(generation_input),
        )

    def _open_client_if_configured(self) -> Any | None:
        if not self.settings.api_key.strip():
            return None
        from openai import OpenAI
        import httpx

        return OpenAI(
            base_url=self.settings.base_url,
            api_key=self.settings.api_key,
            http_client=httpx.Client(
                timeout=self.settings.timeout_seconds,
                trust_env=False,
            ),
            timeout=self.settings.timeout_seconds,
            max_retries=self.settings.retry_budget,
        )

    def _call_candidate_json(
        self,
        *,
        task_type: str,
        output_key: str,
        system_prompt: str,
        user_prompt: str,
    ) -> CandidateLLMOutput:
        if self.client is None:
            raise MissingLLMCredentials(
                "LLM API key is not configured.",
                provider_metadata=self.settings.audit_metadata(),
                retryable=True,
            )

        last_metadata = self.settings.audit_metadata()
        max_attempts = 2
        current_user_prompt = user_prompt
        for attempt in range(1, max_attempts + 1):
            prompt_hash = _hash_text(system_prompt + "\n" + current_user_prompt)
            response = self.client.chat.completions.create(
                model=self.settings.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": current_user_prompt},
                ],
                temperature=0.0,
                max_tokens=1024,
                extra_body=self.settings.extra_body,
            )
            choice = response.choices[0]
            raw_text = (choice.message.content or "").strip()
            last_metadata = {
                **self.settings.audit_metadata(),
                "prompt_hash": prompt_hash,
                "raw_response_hash": _hash_text(raw_text),
                "finish_reason": getattr(choice, "finish_reason", None),
                "attempt_count": attempt,
                **_usage_metadata(response),
            }
            if not raw_text:
                raise EmptyLLMResponse(
                    "LLM returned an empty response.",
                    provider_metadata=last_metadata,
                    retryable=True,
                )

            payload = _parse_json_object(raw_text)
            if isinstance(payload, dict) and isinstance(payload.get(output_key), str):
                text = payload[output_key].strip()
                if text:
                    return CandidateLLMOutput(
                        text=text,
                        provider_metadata=last_metadata,
                        llm_self_check=_self_check_payload(payload, task_type=task_type),
                    )

            current_user_prompt = (
                user_prompt
                + "\n\n上次输出无法解析或缺少必需字段。请只输出严格 JSON 对象，"
                f"必须包含字符串字段 {output_key} 和对象字段 llm_self_check。"
            )

        raise MalformedLLMJSON(
            "LLM output was not valid candidate JSON.",
            provider_metadata=last_metadata,
            retryable=True,
        )


def resolve_professor_candidate_llm_task_settings(
    task_type: str,
    *,
    llm_profile: str | None = None,
    timeout_seconds: float | None = None,
    retry_budget: int | None = None,
) -> ProfessorCandidateLLMTaskSettings:
    if task_type not in _OUTPUT_KEY_BY_TASK:
        available = ", ".join(sorted(_OUTPUT_KEY_BY_TASK))
        raise ValueError(
            f"Unknown Professor candidate LLM task '{task_type}'. "
            f"Available tasks: {available}."
        )
    settings = resolve_professor_llm_settings(
        llm_profile or _DEFAULT_PROFILE,
        strict=True,
        include_profile=True,
        apply_endpoint_env_overrides=False,
    )
    model = settings["local_llm_model"]
    return ProfessorCandidateLLMTaskSettings(
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


def open_professor_candidate_llm_provider(
    task_type: ProfessorCandidateLLMTaskType,
    *,
    llm_profile: str | None = None,
    timeout_seconds: float | None = None,
    retry_budget: int | None = None,
) -> ProfessorCandidateLLMProvider:
    return ProfessorCandidateLLMProvider(
        settings=resolve_professor_candidate_llm_task_settings(
            task_type,
            llm_profile=llm_profile,
            timeout_seconds=timeout_seconds,
            retry_budget=retry_budget,
        )
    )


def _build_profile_summary_prompt(profile_input: ProfileSummaryInput) -> str:
    return "\n".join(
        [
            "任务：生成 candidate_profile_summary，中文，目标 200-300 字。",
            "要求：只使用输入中的官方资料、结构化事实和已验证产出；不要补充企业任职或创业经历。",
            "输出 JSON：candidate_profile_summary, llm_self_check。",
            f"Professor ID: {profile_input.professor_id}",
            f"Name: {profile_input.canonical_name}",
            f"Institution: {profile_input.institution}",
            f"Department: {profile_input.department or ''}",
            f"Title: {profile_input.title or ''}",
            f"Source IDs: {', '.join(profile_input.source_ids)}",
            "Input facts:",
            "\n".join(profile_input.input_facts[:30]),
            f"Existing paper summary: {profile_input.paper_summary or ''}",
            "Linked output titles:",
            "\n".join(profile_input.linked_output_titles[:8]),
            "Official raw profile text:",
            (profile_input.profile_raw_text or "")[:5000],
        ]
    )


def _build_research_translation_prompt(source_text: str) -> str:
    return "\n".join(
        [
            "任务：将英文研究方向/研究概况翻译整理为中文 candidate_research_overview_zh。",
            "要求：保留原意，只基于 source text，不添加新事实。",
            "输出 JSON：candidate_research_overview_zh, llm_self_check。",
            "Source text:",
            source_text[:5000],
        ]
    )


def _build_paper_summary_prompt(
    generation_input: ProfessorPaperSummaryGenerationInput,
) -> str:
    papers = []
    for paper in generation_input.eligible_papers[:12]:
        papers.append(
            {
                "paper_id": paper.paper_id,
                "title": paper.title,
                "year": paper.year,
                "venue": paper.venue,
                "summary_zh": paper.summary_zh,
                "abstract_clean": paper.abstract_clean,
                "canonical_source": paper.canonical_source,
                "link_status": paper.link_status,
                "match_reason": paper.match_reason,
            }
        )
    return "\n".join(
        [
            "任务：基于已验证教师论文生成 candidate_paper_summary，中文。",
            "要求：只使用 verified Professor-seeded Paper 输入，不使用姓名搜索外部论文。",
            "输出 JSON：candidate_paper_summary, llm_self_check。",
            f"Professor ID: {generation_input.professor_id}",
            f"Professor name: {generation_input.professor_name}",
            f"Duplicate status: {generation_input.duplicate_status}",
            f"Source page IDs: {', '.join(generation_input.source_page_ids)}",
            "Eligible papers JSON:",
            json.dumps(papers, ensure_ascii=False),
            "Excluded paper ids:",
            json.dumps(generation_input.exclusion_reasons, ensure_ascii=False),
        ]
    )


def _parse_json_object(raw_text: str) -> Any:
    cleaned = raw_text.strip()
    fence = _JSON_FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def _self_check_payload(payload: dict[str, Any], *, task_type: str) -> dict[str, Any]:
    raw = payload.get("llm_self_check") or payload.get("self_check") or {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        **raw,
        "task_type": task_type,
    }


def _usage_metadata(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
    }


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
