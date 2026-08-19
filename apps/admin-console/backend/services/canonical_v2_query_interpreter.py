"""Contextual query interpretation layer (Phase 6).

An LLM-backed interpreter that resolves follow-up queries to their session
subjects and intents, with deterministic validation and a hard timeout.

Design: mirrors `_ServingQueryRewriter` isolation — lazy client, bounded
executor, exception-swallowing. The interpretation is only adopted when it
passes all seven deterministic checks; any failure returns None (the
deterministic Phase 3 path runs unchanged).

Gate: default OFF (`CHAT_CONTEXTUAL_INTERPRETATION` env). The GO/NO-GO
decision requires both-direction replay green; until then the layer stays
behind the switch.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
import json
import logging
import os
from threading import Lock
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.data_agents.canonical_v2.followup_referents import (
    has_explicit_named_subject,
    referent_subject_domain,
)
from src.data_agents.professor.llm_profiles import (
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)

_logger = logging.getLogger(__name__)

INTERPRETATION_TIMEOUT_SECONDS = 1.5
_MIN_CONFIDENCE = 0.7


class SubjectRef(BaseModel):
    name: str
    source: Literal["anchor", "displayed", "history", "query_named", "inferred"]
    canonical_id: str | None = None
    evidence_quote: str = ""


class Interpretation(BaseModel):
    subject_ref: SubjectRef | None = None
    intent: Literal[
        "profile",
        "deepen",
        "switch",
        "expand",
        "enumerate",
        "relation",
        "clarify_ambiguous",
    ] = "profile"
    self_contained_query: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    referent_kind: Literal["singular", "set", "none"] = "none"


def interpretation_enabled() -> bool:
    return os.getenv("CHAT_CONTEXTUAL_INTERPRETATION", "").strip().casefold() in {
        "1",
        "on",
        "true",
        "yes",
    }


def is_headline_shaped_name(name: str | None) -> bool:
    """Re-exported from canonical_v2_chat for validation check ④."""
    from backend.services.canonical_v2_chat import is_headline_shaped_name as _check

    return _check(name)


def validate_interpretation(
    interpretation: Interpretation,
    *,
    query: str,
    session_manifest_names: tuple[str, ...],
    query_is_enumeration: bool,
    referent_domain_hint: str | None = None,
) -> Interpretation | None:
    """Seven deterministic checks; any failure → None (deterministic path)."""
    if interpretation.confidence < _MIN_CONFIDENCE:
        return None
    if not interpretation.self_contained_query.strip():
        return None
    subject = interpretation.subject_ref
    if subject is not None:
        # ① subject must hit the session manifest (or be explicitly named
        # in the query itself).
        named_in_query = subject.name in query
        if not named_in_query and subject.name not in session_manifest_names:
            return None
        # ② explicit-named-subject veto: the query names a manifest subject
        # that is NOT the resolved subject — the query's own naming wins.
        named_manifest_subjects = [
            manifest_name
            for manifest_name in session_manifest_names
            if manifest_name in query
        ]
        if (
            named_manifest_subjects
            and subject.name not in named_manifest_subjects
        ):
            return None
        # ③ domain mismatch: personal referent over org-anchored session.
        if (
            referent_domain_hint is not None
            and referent_domain_hint == "professor"
            and subject.source in ("anchor", "displayed")
        ):
            domain = referent_subject_domain(query)
            if domain is not None and domain != "professor":
                return None
        # ④ headline-shaped names never bind.
        if is_headline_shaped_name(subject.name):
            return None
    # ⑥ enumeration turns never single-subject.
    if query_is_enumeration and interpretation.intent != "enumerate":
        return None
    return interpretation


class ContextualQueryInterpreter:
    """LLM-backed follow-up resolver with hard timeout and validation."""

    def __init__(self, *, timeout_seconds: float = INTERPRETATION_TIMEOUT_SECONDS):
        self._timeout = timeout_seconds
        self._client: Any | None = None
        self._model: str | None = None
        self._extra_body: dict[str, Any] | None = None
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ctx-interpreter"
        )

    def _configured(self) -> tuple[Any, str, dict[str, Any]]:
        with self._lock:
            if self._client is None:
                profile = os.getenv("CHAT_LLM_PROFILE", "gemma4")
                settings = resolve_professor_llm_settings(
                    profile, apply_endpoint_env_overrides=False
                )
                from openai import OpenAI

                self._client = OpenAI(
                    base_url=settings["local_llm_base_url"],
                    api_key=settings["local_llm_api_key"],
                    timeout=self._timeout,
                    max_retries=0,
                )
                self._model = str(settings["local_llm_model"])
                self._extra_body = build_non_thinking_extra_body(self._model)
            return self._client, self._model or "", self._extra_body or {}

    def interpret(
        self,
        *,
        query: str,
        history: tuple[dict[str, str], ...] = (),
        manifest_names: tuple[str, ...] = (),
        manifest_ids: tuple[str, ...] = (),
        active_anchor_domain: str | None = None,
    ) -> Interpretation | None:
        """Run the LLM interpretation; validate; return None on any failure."""
        if not interpretation_enabled():
            return None
        try:
            future = self._executor.submit(
                self._llm_call,
                query,
                history,
                manifest_names,
                active_anchor_domain,
            )
            raw = future.result(timeout=self._timeout)
        except (FutureTimeoutError, Exception):
            return None
        if raw is None:
            return None
        try:
            interpretation = Interpretation.model_validate_json(raw)
        except Exception:
            return None
        query_is_enum = any(
            marker in query for marker in ("哪些", "谁", "多少", "几个", "列出")
        )
        return validate_interpretation(
            interpretation,
            query=query,
            session_manifest_names=manifest_names,
            query_is_enumeration=query_is_enum,
            referent_domain_hint=active_anchor_domain,
        )

    def _llm_call(
        self,
        query: str,
        history: tuple[dict[str, str], ...],
        manifest_names: tuple[str, ...],
        active_anchor_domain: str | None,
    ) -> str | None:
        client, model, extra_body = self._configured()
        manifest_lines = "\n".join(f"- {name}" for name in manifest_names) or "（无）"
        history_lines = "\n".join(
            f"用户：{turn.get('query', '')}\n助手：{turn.get('answer_head', '')[:80]}"
            for turn in history[-5:]
        ) or "（无历史）"
        domain_note = (
            f"\n当前会话锚点域：{active_anchor_domain}"
            if active_anchor_domain
            else ""
        )
        system = (
            "你是查询理解助手。根据对话历史与会话主体清单，解析用户当前查询的指代和意图。\n"
            "只输出一个 JSON 对象（不带 markdown），字段：\n"
            '{"subject_ref": {"name": "主体名或null", "source": "anchor|displayed|history|query_named|inferred", '
            '"canonical_id": "id或null", "evidence_quote": "依据"}, '
            '"intent": "profile|deepen|switch|expand|enumerate|relation|clarify_ambiguous", '
            '"self_contained_query": "脱离上下文可独立理解的查询", '
            '"confidence": 0.0-1.0, "referent_kind": "singular|set|none"}\n'
            "规则：主体名必须来自清单或查询原文；清单为空且查询无显式主体时 subject_ref=null；"
            "枚举类查询 intent=enumerate 且 subject_ref=null。"
        )
        user = (
            f"会话主体清单：\n{manifest_lines}\n"
            f"对话历史（最近5轮）：\n{history_lines}\n"
            f"当前查询：{query}{domain_note}\n"
            "请输出 JSON。"
        )
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=300,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            extra_body=extra_body,
        )
        choices = getattr(response, "choices", ())
        if not choices:
            return None
        content = getattr(getattr(choices[0], "message", None), "content", None)
        if not isinstance(content, str) or not content.strip():
            return None
        # Strip potential markdown fences.
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1] if "\n" in text else text
            if text.endswith("```"):
                text = text[:-3]
        return text.strip()


_INTERPRETER: ContextualQueryInterpreter | None = None
_INTERPRETER_LOCK = Lock()


def get_interpreter() -> ContextualQueryInterpreter:
    global _INTERPRETER
    with _INTERPRETER_LOCK:
        if _INTERPRETER is None:
            _INTERPRETER = ContextualQueryInterpreter()
        return _INTERPRETER
