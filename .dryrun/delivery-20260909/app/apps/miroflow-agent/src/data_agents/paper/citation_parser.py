# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.15 — LLM-based citation string parser.

The ``official_site`` scraper in the professor pipeline didn't extract
structured fields: it dumped the entire publication bullet point into
``paper_staging.title``. Downstream this produced 1400 ``paper`` rows in
``miroflow_real`` whose ``title_clean`` looks like::

    Zheng X*, Zhang N, Wu HJ, Wu H*. (2017) Estimating and accounting for
    tumor purity in cancer methylation microarray analysis. Genome
    Biology 18:17

and whose ``authors_display`` / ``year`` / ``venue`` are NULL. This
module asks Gemma to parse one citation string into structured fields.

Precision-first: if the LLM can't confidently identify a paper
(confidence < 0.7) or the string doesn't look like a paper at all
(education entry, mere venue name, empty), return ``ParsedCitation``
with ``is_paper=False`` so the caller can flag for human review.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from src.data_agents.professor.translation_spec import LLM_EXTRA_BODY

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.7
BATCH_SIZE = 10

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass(frozen=True, slots=True)
class CitationInput:
    """One citation string to parse."""

    index: int
    raw_string: str
    hint_year: int | None = None
    hint_venue: str | None = None


class _ParsedItem(BaseModel):
    index: int
    is_paper: bool
    confidence: float = Field(ge=0.0, le=1.0)
    authors: list[str] = Field(default_factory=list)
    title: str | None = None
    venue: str | None = None
    year: int | None = None
    reasoning: str = ""

    @field_validator("authors", mode="before")
    @classmethod
    def _coerce_null_authors(cls, value):
        # Gemma occasionally emits ``"authors": null`` for non-paper entries;
        # treat that as an empty list rather than a type error.
        if value is None:
            return []
        return value

    @field_validator("reasoning", mode="before")
    @classmethod
    def _coerce_null_reasoning(cls, value):
        if value is None:
            return ""
        return value


class _BatchParsed(BaseModel):
    results: list[_ParsedItem]


@dataclass(frozen=True, slots=True)
class ParsedCitation:
    """Per-input output."""

    index: int
    is_paper: bool
    authors: list[str]
    title: str | None
    venue: str | None
    year: int | None
    confidence: float
    reasoning: str
    error: str | None = None


def _render_item(item: CitationInput) -> str:
    hint_bits: list[str] = []
    if item.hint_year:
        hint_bits.append(f"hint_year={item.hint_year}")
    if item.hint_venue:
        hint_bits.append(f"hint_venue={item.hint_venue[:60]}")
    hints = f" ({'; '.join(hint_bits)})" if hint_bits else ""
    return f"[{item.index}] raw{hints}: {item.raw_string[:600]}"


def _build_prompt(items: list[CitationInput]) -> str:
    return (
        "## 任务\n"
        "下面是一组引用字符串，每条可能是一篇论文的完整引用，也可能是教育经历、会议任职、纯期刊名等\n"
        "非论文条目。对每一条输出：\n"
        "  - is_paper：是否为同行评议论文（true/false）\n"
        "  - confidence：0.0-1.0\n"
        "  - authors：作者姓名数组（姓名保留原文，不要缩写）\n"
        "  - title：论文标题（剥离作者/期刊/年份后的纯标题）\n"
        "  - venue：期刊或会议名\n"
        "  - year：发表年份（整数）\n"
        "  - reasoning：一句话说明\n\n"
        "## 判断规则\n"
        "1. 看到 'Ph.D.' / 'Master' / 'Fellow,' / 'Associate Editor' / 'Workshop' 等 → is_paper=false\n"
        "2. 纯期刊名（如 'Journal of Hazardous Materials'）无论上下文 → is_paper=false\n"
        "3. 日期区间（'2011 - 2016, ...'）+ 学位/职位 → is_paper=false\n"
        "4. 作者列表 + 标题 + 期刊 三要素齐全 → is_paper=true\n"
        "5. 任一字段无法识别 → 对应输出 null；但仍要尝试解析其余字段\n"
        "6. 中文 + 英文混排保持原样，不要翻译\n"
        "7. confidence < 0.7 的整条记录视为不可用\n\n"
        "## 输入\n"
        f"{chr(10).join(_render_item(i) for i in items)}\n\n"
        "## 输出\n"
        "```json\n"
        "{\n"
        '  "results": [\n'
        '    {"index": 0, "is_paper": true, "confidence": 0.9,\n'
        '     "authors": ["Zhang Wei", "Li Ming"], "title": "...", "venue": "...",\n'
        '     "year": 2023, "reasoning": "..."},\n'
        "    ...\n"
        "  ]\n"
        "}\n"
        "```"
    )


def _parse(text: str) -> _BatchParsed:
    match = _JSON_FENCE_RE.search(text)
    body = match.group(1).strip() if match else text.strip()
    start, end = body.find("{"), body.rfind("}")
    if start != -1 and end != -1 and end > start:
        body = body[start : end + 1]
    return _BatchParsed.model_validate_json(body)


def _reject_all(
    items: list[CitationInput], *, reason: str, error: str | None = None
) -> list[ParsedCitation]:
    return [
        ParsedCitation(
            index=i.index,
            is_paper=False,
            authors=[],
            title=None,
            venue=None,
            year=None,
            confidence=0.0,
            reasoning=reason,
            error=error,
        )
        for i in items
    ]


def _parse_single_batch(
    *,
    items: list[CitationInput],
    llm_client: Any,
    llm_model: str,
) -> list[ParsedCitation]:
    if not items:
        return []
    prompt = _build_prompt(items)
    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "你是学术引用解析助手。只输出符合要求的 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
            extra_body=LLM_EXTRA_BODY,
        )
        text = response.choices[0].message.content
        parsed = _parse(text)
    except (ValidationError, json.JSONDecodeError) as exc:
        logger.warning("citation_parser JSON parse failure: %s", exc)
        return _reject_all(
            items,
            reason="LLM response did not parse.",
            error=str(exc),
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("citation_parser LLM call failed: %s", exc)
        return _reject_all(
            items, reason="LLM call failed.", error=str(exc)
        )

    by_index: dict[int, _ParsedItem] = {r.index: r for r in parsed.results}
    out: list[ParsedCitation] = []
    for item in items:
        r = by_index.get(item.index)
        if r is None:
            out.append(
                ParsedCitation(
                    index=item.index,
                    is_paper=False,
                    authors=[],
                    title=None,
                    venue=None,
                    year=None,
                    confidence=0.0,
                    reasoning="LLM returned no result for this item.",
                )
            )
            continue
        usable = r.is_paper and r.confidence >= CONFIDENCE_THRESHOLD
        out.append(
            ParsedCitation(
                index=item.index,
                is_paper=usable,
                authors=list(r.authors) if usable else [],
                title=r.title if usable else None,
                venue=r.venue if usable else None,
                year=r.year if usable else None,
                confidence=r.confidence,
                reasoning=r.reasoning or "",
            )
        )
    return out


def parse_citations(
    *,
    items: list[CitationInput],
    llm_client: Any,
    llm_model: str,
    batch_size: int = BATCH_SIZE,
) -> list[ParsedCitation]:
    """Parse citation strings in batches.

    Ordered output: one ParsedCitation per input, preserving order.
    """
    if not items:
        return []
    results: list[ParsedCitation] = []
    for start in range(0, len(items), batch_size):
        chunk = items[start : start + batch_size]
        results.extend(
            _parse_single_batch(
                items=chunk,
                llm_client=llm_client,
                llm_model=llm_model,
            )
        )
    by_index = {r.index: r for r in results}
    return [by_index[i.index] for i in items]
