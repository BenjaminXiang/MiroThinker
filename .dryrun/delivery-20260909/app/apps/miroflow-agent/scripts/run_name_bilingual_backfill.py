# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.19a — bilingual professor name backfill.

Scans resolved professor rows where either `canonical_name_en` or
`canonical_name_zh` is missing, infers the missing counterpart via Gemma 4,
verifies cross-language identity with `name_identity_gate`, and then updates
the professor row or files a `pipeline_issue`.

Dry-run is the default. Use `--apply --confirm-real-db` to actually write.

Tech debt: this script intentionally copies the shared arg-parsing / DSN-safety
pattern already used by cleanup scripts because `_cleanup_harness.py` has not
been extracted yet.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, ValidationError

from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings
from src.data_agents.professor.name_identity_gate import (
    NameIdentityCandidate,
    verify_name_identity,
)
from src.data_agents.professor.translation_spec import LLM_EXTRA_BODY
from src.data_agents.storage.postgres.connection import resolve_dsn


_REAL_DB_NAME = "miroflow_real"
_REPORTED_BY = "round_7_19a_name_bilingual"
_CONFIDENCE_THRESHOLD = 0.8
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass(frozen=True, slots=True)
class NameBackfillRow:
    professor_id: str
    canonical_name: str
    canonical_name_en: str | None
    canonical_name_zh: str | None
    institution: str | None
    source_url: str | None


@dataclass(frozen=True, slots=True)
class NameProposal:
    candidate_name: str
    confidence: float
    reasoning: str
    error: str | None = None


@dataclass
class BackfillStats:
    examined: int = 0
    already_filled: int = 0
    mixed_or_other: int = 0
    llm_attempted: int = 0
    updated: int = 0
    issues_inserted: int = 0


class _LLMProposalPayload(BaseModel):
    candidate_name: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _is_ignorable_name_char(ch: str) -> bool:
    category = unicodedata.category(ch)
    return category[0] in {"P", "Z"} or category.startswith("M")


def _meaningful_name_chars(text: str) -> list[str]:
    return [ch for ch in text.strip() if not _is_ignorable_name_char(ch)]


def _is_cjk_char(ch: str) -> bool:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return False
    return "CJK UNIFIED IDEOGRAPH" in name or "CJK COMPATIBILITY IDEOGRAPH" in name


def _is_latin_char(ch: str) -> bool:
    if not unicodedata.category(ch).startswith("L"):
        return False
    try:
        return "LATIN" in unicodedata.name(ch)
    except ValueError:
        return False


def is_cjk_only_name(text: str) -> bool:
    meaningful = _meaningful_name_chars(text)
    return bool(meaningful) and all(_is_cjk_char(ch) for ch in meaningful)


def is_latin_only_name(text: str) -> bool:
    meaningful = _meaningful_name_chars(text)
    return bool(meaningful) and all(_is_latin_char(ch) for ch in meaningful)


def classify_name_shape(
    *,
    canonical_name: str,
    canonical_name_en: str | None,
    canonical_name_zh: str | None,
) -> str:
    if _has_text(canonical_name_en) and _has_text(canonical_name_zh):
        return "already_filled"
    if is_cjk_only_name(canonical_name):
        return "cjk_only"
    if is_latin_only_name(canonical_name):
        return "latin_only"
    return "mixed_or_other"


def _build_llm_settings() -> tuple[object, str]:
    from openai import OpenAI

    settings = resolve_professor_llm_settings("gemma4")
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings.get("local_llm_api_key") or "EMPTY",
    )
    return client, settings["local_llm_model"]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Round 7.19a — backfill bilingual professor names."
    )
    parser.add_argument(
        "--database-url",
        help="Postgres DSN. Defaults to DATABASE_URL env.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only; this is also the default if neither flag is passed.",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="Actually update professor rows and insert pipeline_issue rows.",
    )
    parser.add_argument(
        "--confirm-real-db",
        action="store_true",
        help="Required if the DSN targets miroflow_real.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N matching rows.",
    )
    return parser.parse_args(argv)


def _canonical_name_zh_column_exists(conn: psycopg.Connection) -> bool:
    row = conn.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = 'professor'
           AND column_name = 'canonical_name_zh'
        """
    ).fetchone()
    return bool(row)


def _fetch_rows(conn: psycopg.Connection, *, limit: int | None) -> list[NameBackfillRow]:
    sql = """
        SELECT p.professor_id,
               p.canonical_name,
               p.canonical_name_en,
               p.canonical_name_zh,
               pa.institution,
               COALESCE(sp_primary.url, sp_aff.url) AS source_url
          FROM professor p
          LEFT JOIN professor_affiliation pa
            ON pa.professor_id = p.professor_id
           AND pa.is_primary = true
          LEFT JOIN source_page sp_primary
            ON sp_primary.page_id = p.primary_official_profile_page_id
          LEFT JOIN source_page sp_aff
            ON sp_aff.page_id = pa.source_page_id
         WHERE p.identity_status = 'resolved'
           AND (
                p.canonical_name_en IS NULL OR btrim(p.canonical_name_en) = ''
                OR p.canonical_name_zh IS NULL OR btrim(p.canonical_name_zh) = ''
           )
         ORDER BY COALESCE(pa.institution, ''), p.professor_id
    """
    if limit is not None:
        sql += f"\n         LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    return [
        NameBackfillRow(
            professor_id=row["professor_id"],
            canonical_name=row["canonical_name"],
            canonical_name_en=row["canonical_name_en"],
            canonical_name_zh=row["canonical_name_zh"],
            institution=row["institution"],
            source_url=row["source_url"],
        )
        for row in rows
    ]


def _source_domain(source_url: str | None) -> str | None:
    if not source_url:
        return None
    try:
        return urlsplit(source_url).hostname or None
    except ValueError:
        return None


def _normalize_candidate_name(name: str) -> str:
    return " ".join(name.strip().split())


def _parse_proposal(text: str) -> _LLMProposalPayload:
    body = text.strip()
    match = _JSON_FENCE_RE.search(body)
    if match:
        body = match.group(1).strip()
    payload = json.loads(body)
    return _LLMProposalPayload.model_validate(payload)


def _prompt_for_row(row: NameBackfillRow, classification: str) -> str:
    institution = row.institution or "未知机构"
    source_domain = _source_domain(row.source_url) or "未知域名"
    if classification == "cjk_only":
        return f"""你是一位中国高校教授姓名互补助手。
给定中文教授姓名和机构上下文，请输出该教授最可能使用的英文姓名或标准汉语拼音。
如果不确定，不要编造；返回空字符串并给低置信度。

输出 JSON（不要 markdown fence）：
{{
  "candidate_name": "<英文姓名或拼音；不确定时为空字符串>",
  "confidence": 0.0-1.0,
  "reasoning": "<= 60 字"
}}

现在判断：
- 中文姓名: {row.canonical_name}
- 机构: {institution}
"""
    return f"""你是一位中国高校教授姓名互补助手。
给定英文教授姓名、机构和官网域名上下文，请输出该教授最可能的中文姓名。
如果不确定，不要编造；返回空字符串并给低置信度。

输出 JSON（不要 markdown fence）：
{{
  "candidate_name": "<中文姓名；不确定时为空字符串>",
  "confidence": 0.0-1.0,
  "reasoning": "<= 60 字"
}}

现在判断：
- 英文姓名: {row.canonical_name}
- 机构: {institution}
- 官网域名: {source_domain}
"""


def propose_name(
    row: NameBackfillRow,
    classification: str,
    *,
    llm_client: Any,
    llm_model: str,
) -> NameProposal:
    prompt = _prompt_for_row(row, classification)
    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "你是教授中英姓名互补助手。只输出符合要求的 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=256,
            extra_body=LLM_EXTRA_BODY,
        )
        text = response.choices[0].message.content
        parsed = _parse_proposal(text)
    except (ValidationError, TypeError, json.JSONDecodeError) as exc:
        return NameProposal(
            candidate_name="",
            confidence=0.0,
            reasoning="LLM response did not parse; defaulting to reject.",
            error=f"parse:{exc.__class__.__name__}",
        )
    except Exception as exc:  # pragma: no cover - network / upstream fault
        return NameProposal(
            candidate_name="",
            confidence=0.0,
            reasoning="LLM call failed; defaulting to reject.",
            error=f"llm_exception:{exc.__class__.__name__}",
        )

    candidate_name = _normalize_candidate_name(parsed.candidate_name)
    if not candidate_name:
        return NameProposal(
            candidate_name="",
            confidence=parsed.confidence,
            reasoning=parsed.reasoning,
            error="empty_candidate",
        )
    if classification == "cjk_only" and not is_latin_only_name(candidate_name):
        return NameProposal(
            candidate_name=candidate_name,
            confidence=parsed.confidence,
            reasoning=parsed.reasoning,
            error="invalid_script",
        )
    if classification == "latin_only" and not is_cjk_only_name(candidate_name):
        return NameProposal(
            candidate_name=candidate_name,
            confidence=parsed.confidence,
            reasoning=parsed.reasoning,
            error="invalid_script",
        )
    return NameProposal(
        candidate_name=candidate_name,
        confidence=parsed.confidence,
        reasoning=parsed.reasoning,
    )


def _update_professor_fields(
    conn: psycopg.Connection,
    *,
    professor_id: str,
    updates: dict[str, str],
) -> int:
    assignments = ", ".join(f"{column} = %s" for column in updates)
    params = tuple(updates.values()) + (professor_id,)
    cursor = conn.execute(
        f"""
        UPDATE professor
           SET {assignments},
               updated_at = now()
         WHERE professor_id = %s
        """,
        params,
    )
    return cursor.rowcount


def _issue_snapshot(
    row: NameBackfillRow,
    *,
    classification: str,
    proposal: NameProposal | None,
    gate_decision: Any | None,
) -> dict[str, object]:
    gate_payload = None
    if gate_decision is not None:
        gate_payload = {
            "accepted": bool(gate_decision.accepted),
            "confidence": float(gate_decision.confidence),
            "reasoning": gate_decision.reasoning,
            "error": gate_decision.error,
        }
    return {
        "type": "name_bilingual_backfill_report",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "professor": {
            "professor_id": row.professor_id,
            "canonical_name": row.canonical_name,
            "canonical_name_en": row.canonical_name_en,
            "canonical_name_zh": row.canonical_name_zh,
            "institution": row.institution,
            "source_url": row.source_url,
            "source_domain": _source_domain(row.source_url),
        },
        "classification": classification,
        "proposal": None
        if proposal is None
        else {
            "candidate_name": proposal.candidate_name,
            "confidence": proposal.confidence,
            "reasoning": proposal.reasoning,
            "error": proposal.error,
        },
        "gate_decision": gate_payload,
    }


def _file_issue(
    conn: psycopg.Connection,
    *,
    row: NameBackfillRow,
    classification: str,
    proposal: NameProposal | None,
    gate_decision: Any | None,
) -> int:
    proposal_name = proposal.candidate_name if proposal is not None else ""
    description = (
        f"name bilingual backfill unresolved ({classification}): "
        f"{row.canonical_name!r} -> {proposal_name!r}"
    )
    snapshot = json.dumps(
        _issue_snapshot(
            row,
            classification=classification,
            proposal=proposal,
            gate_decision=gate_decision,
        ),
        ensure_ascii=False,
    )
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, institution, stage, severity,
            description, evidence_snapshot, reported_by
        )
        VALUES (%s, %s, 'name_extraction', %s, %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            row.professor_id,
            row.institution,
            "medium",
            description,
            snapshot,
            _REPORTED_BY,
        ),
    )
    return cursor.rowcount


def process_rows(
    conn: psycopg.Connection,
    rows: list[NameBackfillRow],
    *,
    apply: bool,
    llm_client: Any,
    llm_model: str,
    propose_name_fn=propose_name,
    verify_name_identity_fn=verify_name_identity,
) -> BackfillStats:
    stats = BackfillStats()
    for row in rows:
        stats.examined += 1
        classification = classify_name_shape(
            canonical_name=row.canonical_name,
            canonical_name_en=row.canonical_name_en,
            canonical_name_zh=row.canonical_name_zh,
        )
        if classification == "already_filled":
            stats.already_filled += 1
            continue
        if classification == "mixed_or_other":
            stats.mixed_or_other += 1
            if apply:
                stats.issues_inserted += _file_issue(
                    conn,
                    row=row,
                    classification=classification,
                    proposal=None,
                    gate_decision=None,
                )
            continue

        missing_en = not _has_text(row.canonical_name_en)
        missing_zh = not _has_text(row.canonical_name_zh)

        if classification == "cjk_only" and not missing_en and missing_zh:
            if apply:
                stats.updated += _update_professor_fields(
                    conn,
                    professor_id=row.professor_id,
                    updates={"canonical_name_zh": row.canonical_name},
                )
            continue
        if classification == "latin_only" and missing_en and not missing_zh:
            if apply:
                stats.updated += _update_professor_fields(
                    conn,
                    professor_id=row.professor_id,
                    updates={"canonical_name_en": row.canonical_name},
                )
            continue

        stats.llm_attempted += 1
        proposal = propose_name_fn(
            row,
            classification,
            llm_client=llm_client,
            llm_model=llm_model,
        )

        gate_decision = None
        if proposal.error is None and proposal.confidence >= _CONFIDENCE_THRESHOLD:
            gate_candidate = (
                NameIdentityCandidate(
                    canonical_name=row.canonical_name,
                    candidate_name_en=proposal.candidate_name,
                    source_url=row.source_url,
                )
                if classification == "cjk_only"
                else NameIdentityCandidate(
                    canonical_name=proposal.candidate_name,
                    candidate_name_en=row.canonical_name,
                    source_url=row.source_url,
                )
            )
            gate_decision = verify_name_identity_fn(
                gate_candidate,
                llm_client=llm_client,
                llm_model=llm_model,
            )

        if (
            proposal.error is None
            and proposal.confidence >= _CONFIDENCE_THRESHOLD
            and gate_decision is not None
            and gate_decision.accepted
        ):
            updates: dict[str, str] = {}
            if classification == "cjk_only":
                updates["canonical_name_en"] = proposal.candidate_name
                if missing_zh:
                    updates["canonical_name_zh"] = row.canonical_name
            else:
                updates["canonical_name_zh"] = proposal.candidate_name
                if missing_en:
                    updates["canonical_name_en"] = row.canonical_name
            if apply:
                stats.updated += _update_professor_fields(
                    conn,
                    professor_id=row.professor_id,
                    updates=updates,
                )
        else:
            if apply:
                stats.issues_inserted += _file_issue(
                    conn,
                    row=row,
                    classification=classification,
                    proposal=proposal,
                    gate_decision=gate_decision,
                )
    return stats


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    apply = bool(args.apply)

    dsn = resolve_dsn(args.database_url)
    if _REAL_DB_NAME in dsn and not args.confirm_real_db:
        print(
            "Refusing to run against miroflow_real without --confirm-real-db.",
            file=sys.stderr,
        )
        return 2
    if "miroflow_test_mock" in dsn and os.environ.get("ALLOW_MOCK_BACKFILL") != "1":
        print(
            "Refusing mock DB by default. Set ALLOW_MOCK_BACKFILL=1 "
            "(pytest fixtures do this).",
            file=sys.stderr,
        )
        return 3

    llm_client, llm_model = _build_llm_settings()

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        if not _canonical_name_zh_column_exists(conn):
            print(
                "Refusing to run because professor.canonical_name_zh does not exist. "
                "Apply migration V009 first.",
                file=sys.stderr,
            )
            return 4
        rows = _fetch_rows(conn, limit=args.limit)
        stats = process_rows(
            conn,
            rows,
            apply=apply,
            llm_client=llm_client,
            llm_model=llm_model,
        )
        if not apply:
            conn.rollback()

    print()
    print("=== bilingual-name backfill summary ===")
    print(f"  examined            : {stats.examined}")
    print(f"  already_filled      : {stats.already_filled}")
    print(f"  mixed_or_other      : {stats.mixed_or_other}")
    print(f"  llm_attempted       : {stats.llm_attempted}")
    print(f"  updated             : {stats.updated}")
    print(f"  pipeline_issue rows : {stats.issues_inserted}")
    print(f"  apply               : {apply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
