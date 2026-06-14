"""Professor structured fact backfill helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from src.data_agents.storage.postgres.pipeline_run import require_real_run_id

TARGET_FACT_TYPES = (
    "education",
    "work_experience",
    "award",
    "academic_position",
)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class FactBackfillPreflightReport:
    total_professors: int = 0
    eligible_professor_count: int = 0
    skipped_no_profile_raw_text_count: int = 0
    missing_profile_summary_count: int = 0
    active_fact_counts: dict[str, int] = field(default_factory=dict)
    missing_fact_counts: dict[str, int] = field(default_factory=dict)
    eligible_professor_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtractedProfessorFact:
    professor_id: str
    fact_type: str
    value_raw: str
    value_normalized: str | None
    evidence_span: str
    confidence: float
    source_profile_raw_text_len: int


@dataclass(frozen=True, slots=True)
class ProfessorFactExtractionResult:
    facts: tuple[ExtractedProfessorFact, ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ProfessorFactPersistenceReport:
    facts_written: int = 0
    facts_updated: int = 0
    facts_skipped: int = 0


def extract_professor_facts(
    *,
    professor_id: str,
    professor_name: str,
    institution: str,
    profile_raw_text: str,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any] | None = None,
) -> ProfessorFactExtractionResult:
    if not profile_raw_text.strip():
        return ProfessorFactExtractionResult(error="missing profile_raw_text")

    prompt = _build_fact_extraction_prompt(
        professor_id=professor_id,
        professor_name=professor_name,
        institution=institution,
        profile_raw_text=profile_raw_text,
    )
    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是教授画像结构化事实抽取器。只输出JSON，不要补充解释。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=2048,
            extra_body=extra_body or {},
        )
    except Exception as exc:
        return ProfessorFactExtractionResult(error=str(exc))

    try:
        payload = _parse_json_payload(response.choices[0].message.content)
        facts = tuple(
            _parse_extracted_fact(
                item,
                professor_id=professor_id,
                source_profile_raw_text_len=len(profile_raw_text),
            )
            for item in payload["facts"]
        )
    except Exception as exc:
        return ProfessorFactExtractionResult(error=f"malformed output: {exc}")

    return ProfessorFactExtractionResult(facts=facts)


def persist_extracted_professor_facts(
    conn: Any,
    *,
    facts: tuple[ExtractedProfessorFact, ...],
    source_page_id: Any,
    run_id: Any,
) -> ProfessorFactPersistenceReport:
    run_id = require_real_run_id(
        run_id,
        writer_name="persist_extracted_professor_facts",
    )
    written = 0
    updated = 0
    skipped = 0

    from .canonical_writer import _upsert_fact

    for fact in facts:
        if fact.fact_type not in TARGET_FACT_TYPES:
            skipped += 1
            continue
        value_raw = _normalize_text(fact.value_raw)
        evidence_span = _normalize_text(fact.evidence_span)
        if not value_raw or not evidence_span:
            skipped += 1
            continue

        result = _upsert_fact(
            conn,
            professor_id=fact.professor_id,
            fact_type=fact.fact_type,
            value_raw=value_raw,
            value_normalized=_optional_text(fact.value_normalized),
            source_page_id=source_page_id,
            evidence_span=evidence_span,
            confidence=_confidence_decimal(fact.confidence),
            run_id=run_id,
        )
        if result == "inserted":
            written += 1
        else:
            updated += 1

    return ProfessorFactPersistenceReport(
        facts_written=written,
        facts_updated=updated,
        facts_skipped=skipped,
    )


def _confidence_decimal(confidence: float) -> Decimal:
    return Decimal(str(confidence)).quantize(Decimal("0.01"))


def _build_fact_extraction_prompt(
    *,
    professor_id: str,
    professor_name: str,
    institution: str,
    profile_raw_text: str,
) -> str:
    fact_types = ", ".join(TARGET_FACT_TYPES)
    return f"""请从教授个人主页正文中抽取结构化事实。

只抽取以下 fact_type：{fact_types}

输出必须是严格 JSON，格式如下：
{{
  "facts": [
    {{
      "fact_type": "education",
      "value_raw": "原文中的事实短语",
      "value_normalized": "可用于去重的规范事实；无法规范化则为 null",
      "evidence_span": "支持该事实的原文片段",
      "confidence": 0.0
    }}
  ]
}}

要求：
- evidence_span 必须来自原文，不要臆造。
- 低置信度事实也要保留，并用 confidence 表示。
- 没有可抽取事实时返回 {{"facts": []}}。

教授ID：{professor_id}
姓名：{professor_name}
学校：{institution}

个人主页正文：
{profile_raw_text[:8000]}
"""


def _parse_json_payload(text: object) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty response")
    body = text.strip()
    match = _JSON_FENCE_RE.search(body)
    if match:
        body = match.group(1).strip()
    else:
        start = body.find("{")
        end = body.rfind("}")
        if start >= 0 and end > start:
            body = body[start : end + 1]

    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON must be an object")
    facts = payload.get("facts")
    if not isinstance(facts, list):
        raise ValueError("facts must be a list")
    return payload


def _parse_extracted_fact(
    item: object,
    *,
    professor_id: str,
    source_profile_raw_text_len: int,
) -> ExtractedProfessorFact:
    if not isinstance(item, dict):
        raise ValueError("fact item must be an object")
    fact_type = _required_text(item, "fact_type")
    if fact_type not in TARGET_FACT_TYPES:
        raise ValueError(f"unsupported fact_type: {fact_type}")
    confidence = item.get("confidence")
    if not isinstance(confidence, int | float):
        raise ValueError("confidence must be numeric")
    confidence_value = float(confidence)
    if confidence_value < 0.0 or confidence_value > 1.0:
        raise ValueError("confidence must be between 0 and 1")

    return ExtractedProfessorFact(
        professor_id=professor_id,
        fact_type=fact_type,
        value_raw=_required_text(item, "value_raw"),
        value_normalized=_optional_text(item.get("value_normalized")),
        evidence_span=_required_text(item, "evidence_span"),
        confidence=confidence_value,
        source_profile_raw_text_len=source_profile_raw_text_len,
    )


def _required_text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    normalized = _normalize_text(value)
    if not normalized:
        raise ValueError(f"{key} must not be empty")
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("value_normalized must be text or null")
    normalized = _normalize_text(value)
    return normalized or None


def _normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


def compute_fact_backfill_preflight(conn: Any) -> FactBackfillPreflightReport:
    eligible_rows = conn.execute(
        """
        SELECT professor_id
          FROM professor
         WHERE identity_status <> 'merged_into'
           AND profile_raw_text IS NOT NULL
           AND length(trim(profile_raw_text)) > 0
         ORDER BY professor_id
        """
    ).fetchall()
    eligible_professor_ids = tuple(str(_row_get(row, "professor_id", 0)) for row in eligible_rows)
    eligible_count = len(eligible_professor_ids)

    total_professors = _scalar_int(
        conn,
        """
        SELECT count(*)::int AS n
          FROM professor
         WHERE identity_status <> 'merged_into'
        """,
    )
    skipped_no_profile_raw_text_count = _scalar_int(
        conn,
        """
        SELECT count(*)::int AS n
          FROM professor
         WHERE identity_status <> 'merged_into'
           AND (
                profile_raw_text IS NULL
                OR length(trim(profile_raw_text)) = 0
           )
        """,
    )
    missing_profile_summary_count = _scalar_int(
        conn,
        """
        SELECT count(*)::int AS n
          FROM professor
         WHERE identity_status <> 'merged_into'
           AND profile_raw_text IS NOT NULL
           AND length(trim(profile_raw_text)) > 0
           AND (
                profile_summary IS NULL
                OR length(trim(profile_summary)) = 0
           )
        """,
    )

    active_fact_counts = {fact_type: 0 for fact_type in TARGET_FACT_TYPES}
    fact_rows = conn.execute(
        """
        WITH eligible AS (
            SELECT professor_id
              FROM professor
             WHERE identity_status <> 'merged_into'
               AND profile_raw_text IS NOT NULL
               AND length(trim(profile_raw_text)) > 0
        )
        SELECT pf.fact_type, count(DISTINCT pf.professor_id)::int AS n
          FROM professor_fact pf
          JOIN eligible e ON e.professor_id = pf.professor_id
         WHERE pf.status = 'active'
           AND pf.fact_type = ANY(%s)
         GROUP BY pf.fact_type
        """,
        (list(TARGET_FACT_TYPES),),
    ).fetchall()
    for row in fact_rows:
        fact_type = str(_row_get(row, "fact_type", 0))
        if fact_type in active_fact_counts:
            active_fact_counts[fact_type] = int(_row_get(row, "n", 1) or 0)

    missing_fact_counts = {
        fact_type: eligible_count - active_fact_counts[fact_type]
        for fact_type in TARGET_FACT_TYPES
    }
    return FactBackfillPreflightReport(
        total_professors=total_professors,
        eligible_professor_count=eligible_count,
        skipped_no_profile_raw_text_count=skipped_no_profile_raw_text_count,
        missing_profile_summary_count=missing_profile_summary_count,
        active_fact_counts=active_fact_counts,
        missing_fact_counts=missing_fact_counts,
        eligible_professor_ids=eligible_professor_ids,
    )


def _scalar_int(conn: Any, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    if row is None:
        return 0
    return int(_row_get(row, "n", 0) or 0)


def _row_get(row: object, key: str, index: int) -> object:
    if isinstance(row, dict):
        return row.get(key)
    return row[index]  # type: ignore[index]
