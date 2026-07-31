"""Batched fail-open LLM judgment harness for Canonical V2 recall lanes.

Fail-open philosophy: LLM judgments only ever *add* candidates, facts, or
follow-up queries on top of the deterministic wide-recall path. When the
judge is slow, unreachable, or returns malformed output, every item falls
back to its permissive default (relevant, accepted, no extraction, gap
covered) so a judge outage can never shrink recall below the deterministic
baseline.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from threading import Lock
from time import monotonic, sleep
from typing import Any, Literal

from openai import OpenAI, OpenAIError
from pydantic import ValidationError

from src.data_agents.professor.llm_profiles import (
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)

from .contracts import ContractModel

JudgmentKind = Literal["relevance", "probe_accept", "fact_extract", "gap_check"]


class RelevanceJudgment(ContractModel):
    """Per-item relevance call with attributable entity/fact bindings."""

    item_id: str
    relevant: bool
    entity_ids: tuple[str, ...] = ()
    fact: str = ""


class ProbeAcceptJudgment(ContractModel):
    """Per-item probe acceptance with the bound entity/predicate/value."""

    item_id: str
    accept: bool
    entity_id: str | None = None
    predicate: str | None = None
    value: str = ""


class FactExtraction(ContractModel):
    """Per-item attributable facts extracted from the item body."""

    item_id: str
    facts: tuple[str, ...] = ()
    entity_ids: tuple[str, ...] = ()


class GapCheckResult(ContractModel):
    """Coverage self-check over the collected evidence for one question."""

    covered: bool
    missing_aspects: tuple[str, ...] = ()
    followup_queries: tuple[str, ...] = ()


JudgmentResult = (
    RelevanceJudgment | ProbeAcceptJudgment | FactExtraction | GapCheckResult
)

_DEFAULT_TIMEOUT_SECONDS = 1.8
_DEFAULT_MAX_CALLS_PER_SECOND = 4.0
_DEFAULT_MAX_TOKENS = 2000
_GAP_CHECK_MAX_FOLLOWUP_QUERIES = 2
_JUDGE_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="canonical-v2-llm-judge",
)
_JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

_SYSTEM_PROMPTS: dict[JudgmentKind, str] = {
    "relevance": (
        "你是证据相关性判定助手。给定用户问题和一批候选条目，逐条判定："
        "该条目是否与问题相关（relevant），涉及的规范实体ID（entity_ids），"
        "以及可归因到该条目且与问题相关的一句事实（fact，没有则为空字符串）。"
        "宁多勿漏：宁可把弱相关条目判为相关，也不得漏掉可能相关的条目。"
        '只输出一个JSON对象：{"judgments": [{"item_id": "...", "relevant": true, '
        '"entity_ids": ["..."], "fact": "..."}]}，覆盖每个输入条目；'
        "不要输出JSON之外的任何内容。"
    ),
    "probe_accept": (
        "你是证据验收判定助手。给定一个探测问题（含目标谓词、约束或主题语义）"
        "和一批候选条目，逐条判断该条目是否直接支持问题要求的谓词、约束或主题"
        "语义（accept）；若接受，给出绑定的规范实体ID（entity_id）、谓词"
        "（predicate）与取值（value），无法确定的字段置null或空字符串。"
        '只输出一个JSON对象：{"judgments": [{"item_id": "...", "accept": true, '
        '"entity_id": "...", "predicate": "...", "value": "..."}]}，'
        "覆盖每个输入条目；不要输出JSON之外的任何内容。"
    ),
    "fact_extract": (
        "你是事实抽取助手。给定用户问题和一批条目正文，逐条抽取与问题相关、"
        "可归因到该条目的事实（facts，每条一句，没有则为空列表），并标注涉及的"
        "规范实体ID（entity_ids）。严禁编造正文中不存在的事实或实体。"
        '只输出一个JSON对象：{"judgments": [{"item_id": "...", "facts": ["..."], '
        '"entity_ids": ["..."]}]}，覆盖每个输入条目；不要输出JSON之外的任何内容。'
    ),
    "gap_check": (
        "你是覆盖度自查助手。给定用户问题（可能含多个子意图）和已收集的证据，"
        "判断证据是否覆盖了问题的每个子意图（covered）；若有缺失，列出缺失方面"
        "（missing_aspects），并给出不超过2条简短的中文关键词式补查查询"
        '（followup_queries）。只输出一个JSON对象：{"covered": true, '
        '"missing_aspects": ["..."], "followup_queries": ["..."]}；'
        "不要输出JSON之外的任何内容。"
    ),
}


class _JudgeFailOpen(Exception):
    """Internal signal: the current batch must degrade to fail-open defaults."""

    def __init__(self, outcome: str) -> None:
        super().__init__(outcome)
        self.outcome = outcome


class _TokenBucket:
    """Interval-scheduled rate limiter shared by the judge's callers.

    At most ``max_per_second`` acquires are released per second: the first
    acquire is immediate and later ones are spaced by the interval. The lock
    makes the bucket safe to share across threads inside the process.
    """

    def __init__(self, max_per_second: float) -> None:
        self._interval = 1.0 / max_per_second if max_per_second > 0 else 0.0
        self._next_at = 0.0
        self._lock = Lock()

    def acquire(self) -> None:
        if self._interval <= 0:
            return
        with self._lock:
            now = monotonic()
            slot = max(now, self._next_at)
            self._next_at = slot + self._interval
        delay = slot - now
        if delay > 0:
            sleep(delay)


def _render_user_message(
    kind: JudgmentKind,
    question: str,
    items: Mapping[str, str],
    context: str,
) -> str:
    lines = [f"问题：{question}"]
    if context:
        lines.append(f"上下文：{context}")
    lines.append("已收集证据：" if kind == "gap_check" else "候选条目：")
    for item_id, text in items.items():
        lines.append(f"[{item_id}] {text}")
    return "\n".join(lines)


def _parse_json_object(content: str) -> dict[str, Any]:
    """Extract the first JSON object, tolerating a ```json fence wrapper."""
    text = content.strip()
    fenced = _JSON_FENCE_PATTERN.search(text)
    if fenced is not None:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise _JudgeFailOpen("invalid_output_fail_open")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise _JudgeFailOpen("invalid_output_fail_open") from exc
    if not isinstance(payload, dict):
        raise _JudgeFailOpen("invalid_output_fail_open")
    return payload


def _fail_open_item_default(kind: JudgmentKind, item_id: str) -> JudgmentResult:
    if kind == "probe_accept":
        return ProbeAcceptJudgment(item_id=item_id, accept=True)
    if kind == "fact_extract":
        return FactExtraction(item_id=item_id)
    if kind == "gap_check":
        return GapCheckResult(covered=True)
    return RelevanceJudgment(item_id=item_id, relevant=True)


def _fail_open_defaults(
    kind: JudgmentKind,
    items: Mapping[str, str],
) -> tuple[JudgmentResult, ...]:
    if kind == "gap_check":
        return (GapCheckResult(covered=True),)
    return tuple(_fail_open_item_default(kind, item_id) for item_id in items)


def _parse_item_judgment(
    kind: JudgmentKind,
    item_id: str,
    entry: dict[str, Any] | None,
) -> JudgmentResult:
    if entry is not None:
        candidate = {**entry, "item_id": item_id}
        try:
            if kind == "relevance":
                return RelevanceJudgment.model_validate(candidate)
            if kind == "probe_accept":
                return ProbeAcceptJudgment.model_validate(candidate)
            if kind == "fact_extract":
                return FactExtraction.model_validate(candidate)
        except ValidationError:
            pass
    return _fail_open_item_default(kind, item_id)


def _parse_gap_check(payload: dict[str, Any]) -> GapCheckResult:
    try:
        result = GapCheckResult.model_validate(payload)
    except ValidationError as exc:
        raise _JudgeFailOpen("invalid_output_fail_open") from exc
    capped = result.followup_queries[:_GAP_CHECK_MAX_FOLLOWUP_QUERIES]
    return result.model_copy(update={"followup_queries": capped})


def _parse_results(
    kind: JudgmentKind,
    items: Mapping[str, str],
    payload: dict[str, Any],
) -> tuple[JudgmentResult, ...]:
    if kind == "gap_check":
        return (_parse_gap_check(payload),)
    raw = payload.get("judgments")
    if not isinstance(raw, list):
        raise _JudgeFailOpen("invalid_output_fail_open")
    entries = {
        entry["item_id"]: entry
        for entry in raw
        if isinstance(entry, dict) and isinstance(entry.get("item_id"), str)
    }
    return tuple(
        _parse_item_judgment(kind, item_id, entries.get(item_id))
        for item_id in items
    )


class _LlmJudge:
    """Batched LLM judge with a hard timeout and fail-open degradation.

    Mirrors _EnvironmentProseRenderer's construction and isolation pattern:
    the OpenAI-compatible client is built lazily from the configured chat LLM
    profile, every call runs on a bounded executor under a hard timeout, and
    any failure degrades the batch to permissive defaults so the deterministic
    view stays the floor.
    """

    def __init__(
        self,
        *,
        client_factory: Callable[..., Any] | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_calls_per_second: float = _DEFAULT_MAX_CALLS_PER_SECOND,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self._client_factory = client_factory
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max_tokens
        self._bucket = _TokenBucket(max_calls_per_second)
        self._client: Any | None = None
        self._model = ""
        self._extra_body: dict[str, Any] = {}
        self._client_lock = Lock()
        self._last_outcome = "not_called"

    @property
    def last_outcome(self) -> str:
        """Outcome of the latest batch: not_called, ok, or *_fail_open."""
        return self._last_outcome

    def _configured_client(self) -> tuple[Any, str, dict[str, Any]]:
        with self._client_lock:
            if self._client is not None:
                return self._client, self._model, self._extra_body
            if self._client_factory is not None:
                # Injected seam for tests: env/profile resolution is skipped.
                self._client = self._client_factory(
                    base_url="",
                    api_key="",
                    timeout=self._timeout_seconds,
                    max_retries=0,
                )
                self._model = "injected-judge-model"
                self._extra_body = {}
                return self._client, self._model, self._extra_body
            profile = os.getenv("CHAT_LLM_PROFILE", "gemma4")
            settings = resolve_professor_llm_settings(
                profile,
                apply_endpoint_env_overrides=False,
            )
            api_key = settings.get("local_llm_api_key")
            if not api_key:
                raise ValueError("configured chat LLM API key is unavailable")
            model = str(settings["local_llm_model"])
            self._client = OpenAI(
                base_url=settings["local_llm_base_url"],
                api_key=api_key,
                timeout=self._timeout_seconds,
                max_retries=0,
            )
            self._model = model
            self._extra_body = build_non_thinking_extra_body(model)
            return self._client, self._model, self._extra_body

    def _chat(
        self,
        kind: JudgmentKind,
        question: str,
        items: Mapping[str, str],
        context: str,
    ) -> str:
        client, model, extra_body = self._configured_client()
        self._bucket.acquire()
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPTS[kind]},
                {
                    "role": "user",
                    "content": _render_user_message(kind, question, items, context),
                },
            ],
            extra_body=extra_body,
        )
        choices = getattr(response, "choices", ())
        content = (
            None
            if not choices
            else getattr(getattr(choices[0], "message", None), "content", None)
        )
        if not isinstance(content, str):
            raise ValueError("LLM judgment response is not text")
        return content

    def _call(
        self,
        kind: JudgmentKind,
        question: str,
        items: Mapping[str, str],
        context: str,
    ) -> str:
        try:
            future = _JUDGE_EXECUTOR.submit(self._chat, kind, question, items, context)
            return future.result(timeout=self._timeout_seconds)
        except FutureTimeoutError as exc:
            raise _JudgeFailOpen("timeout_fail_open") from exc
        except _JudgeFailOpen:
            raise
        except (
            ConnectionError,
            TimeoutError,
            OpenAIError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise _JudgeFailOpen("error_fail_open") from exc

    def judge_batch(
        self,
        kind: JudgmentKind,
        question: str,
        items: Mapping[str, str],
        context: str = "",
    ) -> tuple[JudgmentResult, ...]:
        """Judge one batch; any failure returns per-item fail-open defaults."""
        if kind not in _SYSTEM_PROMPTS:
            raise ValueError(f"unknown judgment kind: {kind!r}")
        if kind != "gap_check" and not items:
            return ()
        try:
            content = self._call(kind, question, items, context)
            payload = _parse_json_object(content)
            results = _parse_results(kind, items, payload)
        except _JudgeFailOpen as exc:
            self._last_outcome = exc.outcome
            return _fail_open_defaults(kind, items)
        self._last_outcome = "ok"
        return results


def create_llm_judge(
    *,
    client_factory: Callable[..., Any] | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    max_calls_per_second: float = _DEFAULT_MAX_CALLS_PER_SECOND,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> _LlmJudge:
    """Build the batched fail-open judge shared by the wide-recall lanes."""
    return _LlmJudge(
        client_factory=client_factory,
        timeout_seconds=timeout_seconds,
        max_calls_per_second=max_calls_per_second,
        max_tokens=max_tokens,
    )
