from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from typing import Any

from src.data_agents.professor.homepage_publications import (
    build_llm_publication_extraction_messages,
    extract_publications_from_html_with_llm_fallback,
    parse_llm_publication_extraction_response,
)
from src.data_agents.professor.llm_profiles import (
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)

logger = logging.getLogger(__name__)

LLM_PUBLICATION_EXTRACTION_TIMEOUT_SECONDS = 20.0
LLM_PUBLICATION_EXTRACTION_RETRY_BACKOFF_SECONDS = (1.0,)
LLM_PUBLICATION_EXTRACTION_MAX_CONSECUTIVE_FAILURES = 3


def build_llm_publication_extractor(
    profile_name: str | None,
    *,
    force_llm: bool = False,
    resolve_settings: Callable[..., dict[str, Any]] = resolve_professor_llm_settings,
    timeout_seconds: float = LLM_PUBLICATION_EXTRACTION_TIMEOUT_SECONDS,
    retry_backoff_seconds: Sequence[float] = (
        LLM_PUBLICATION_EXTRACTION_RETRY_BACKOFF_SECONDS
    ),
    max_consecutive_failures: int | None = (
        LLM_PUBLICATION_EXTRACTION_MAX_CONSECUTIVE_FAILURES
    ),
):
    import httpx
    from openai import OpenAI

    settings = resolve_settings(
        profile_name,
        include_profile=True,
        strict=True,
    )
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        http_client=httpx.Client(
            timeout=timeout_seconds,
            trust_env=False,
        ),
        timeout=timeout_seconds,
        max_retries=0,
    )
    model = settings["local_llm_model"]
    extra_body = build_non_thinking_extra_body(model)
    consecutive_failures = 0

    def _llm_temporarily_disabled() -> bool:
        if max_consecutive_failures is None:
            return False
        return consecutive_failures >= max_consecutive_failures

    def _extract_from_section(section_text: str, page_url: str):
        nonlocal consecutive_failures
        messages = build_llm_publication_extraction_messages(
            section_text=section_text,
            page_url=page_url,
        )
        try:
            response = create_llm_publication_completion_with_retry(
                client,
                model=model,
                messages=messages,
                extra_body=extra_body,
                retry_backoff_seconds=retry_backoff_seconds,
            )
        except Exception:
            consecutive_failures += 1
            if _llm_temporarily_disabled():
                logger.warning(
                    "LLM publication extraction disabled after %s consecutive failures",
                    consecutive_failures,
                )
            raise
        consecutive_failures = 0
        content = response.choices[0].message.content or ""
        return parse_llm_publication_extraction_response(content)

    def _extract_from_html(html: str, *, page_url: str):
        llm_extractor = None if _llm_temporarily_disabled() else _extract_from_section
        return extract_publications_from_html_with_llm_fallback(
            html,
            page_url=page_url,
            llm_extractor=llm_extractor,
            force_llm=force_llm,
        )

    return _extract_from_html


def create_llm_publication_completion_with_retry(
    client,
    *,
    model: str,
    messages,
    extra_body: dict,
    retry_backoff_seconds: Sequence[float] = (
        LLM_PUBLICATION_EXTRACTION_RETRY_BACKOFF_SECONDS
    ),
):
    max_attempts = len(retry_backoff_seconds) + 1
    for attempt_index in range(max_attempts):
        try:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=8192,
                extra_body=extra_body,
            )
        except Exception as exc:
            if attempt_index >= len(retry_backoff_seconds):
                raise
            sleep_seconds = retry_backoff_seconds[attempt_index]
            logger.warning(
                "LLM publication extraction request failed on attempt %s/%s; "
                "retrying in %.1fs (%s)",
                attempt_index + 1,
                max_attempts,
                sleep_seconds,
                exc.__class__.__name__,
            )
            time.sleep(sleep_seconds)
    raise RuntimeError("unreachable LLM publication extraction retry state")
