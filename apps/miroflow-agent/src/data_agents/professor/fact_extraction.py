"""Structured fact extraction and backfill helpers for professor profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Callable, Iterable, Literal
from uuid import UUID

from .quality_gate import (
    evaluate_professor_quality,
    load_professor_canonical_state,
    persist_professor_quality_evaluation,
)
from .translation_spec import LLM_EXTRA_BODY

TARGET_FACT_TYPES: tuple[str, ...] = (
    "education",
    "work_experience",
    "award",
    "academic_position",
)
_WHITESPACE_RE = re.compile(r"\s+")
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class FactExtractionError(ValueError):
    """Raised when LLM fact extraction output cannot be trusted."""


@dataclass(frozen=True)
class ExtractedProfessorFact:
    fact_type: Literal[
        "education",
        "work_experience",
        "award",
        "academic_position",
    ]
    value_raw: str
    value_normalized: str | None
    evidence_span: str
    confidence: float


@dataclass(frozen=True)
class FactBackfillPreflightReport:
    total_professors: int
    eligible_count: int
    skipped_missing_profile_raw_text: int
    missing_profile_summary_count: int
    missing_fact_counts: dict[str, int]
    existing_active_fact_counts: dict[str, int]


@dataclass(frozen=True)
class FactPersistenceReport:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0


@dataclass
class ProfessorFactBackfillReport:
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    facts_written: int = 0
    summaries_written: int = 0
    re_evaluated: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


def normalized_fact_key(value_raw: str, value_normalized: str | None = None) -> str:
    """Return the active-fact key component for duplicate detection."""
    value = value_normalized if value_normalized and value_normalized.strip() else value_raw
    return _WHITESPACE_RE.sub(" ", value.strip()).casefold()


def parse_fact_extraction_response(content: str) -> list[ExtractedProfessorFact]:
    """Parse and validate LLM structured fact extraction output."""
    cleaned = _FENCE_RE.sub("", content.strip()).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise FactExtractionError("LLM output is not valid JSON") from exc

    raw_facts = payload.get("facts") if isinstance(payload, dict) else payload
    if not isinstance(raw_facts, list):
        raise FactExtractionError("LLM output must contain a facts list")

    facts: list[ExtractedProfessorFact] = []
    for index, raw_item in enumerate(raw_facts):
        if not isinstance(raw_item, dict):
            raise FactExtractionError(f"Fact item {index} is not an object")
        fact_type = str(raw_item.get("fact_type") or "").strip()
        if fact_type not in TARGET_FACT_TYPES:
            raise FactExtractionError(f"Unsupported professor fact_type: {fact_type}")
        value_raw = str(raw_item.get("value_raw") or "").strip()
        evidence_span = str(raw_item.get("evidence_span") or "").strip()
        if not value_raw:
            raise FactExtractionError(f"Fact item {index} is missing value_raw")
        if not evidence_span:
            raise FactExtractionError(f"Fact item {index} is missing evidence_span")
        try:
            confidence = float(raw_item.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise FactExtractionError(f"Fact item {index} has invalid confidence") from exc
        if confidence < 0 or confidence > 1:
            raise FactExtractionError(f"Fact item {index} confidence must be in [0, 1]")
        value_normalized_raw = raw_item.get("value_normalized")
        value_normalized = (
            str(value_normalized_raw).strip()
            if value_normalized_raw is not None and str(value_normalized_raw).strip()
            else None
        )
        facts.append(
            ExtractedProfessorFact(
                fact_type=fact_type,  # type: ignore[arg-type]
                value_raw=value_raw,
                value_normalized=value_normalized,
                evidence_span=evidence_span,
                confidence=confidence,
            )
        )
    return facts


def build_fact_extraction_prompt(profile_raw_text: str, *, professor_name: str | None) -> str:
    name_line = f"Professor name: {professor_name}\n" if professor_name else ""
    return (
        "Extract structured professor experience facts from the profile text.\n"
        f"{name_line}"
        "Return strict JSON with a top-level `facts` array. Each item must have:\n"
        "- fact_type: one of education, work_experience, award, academic_position\n"
        "- value_raw: concise original-language fact text\n"
        "- value_normalized: normalized fact text when clear, otherwise null\n"
        "- evidence_span: exact supporting span from the profile text\n"
        "- confidence: number between 0 and 1\n\n"
        "Do not invent facts. Return an empty facts array if no target facts exist.\n\n"
        f"Profile text:\n{profile_raw_text}"
    )


def extract_structured_facts(
    profile_raw_text: str,
    *,
    professor_name: str | None = None,
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any] | None = None,
) -> list[ExtractedProfessorFact]:
    """Run the injected LLM client and parse structured professor facts."""
    prompt = build_fact_extraction_prompt(profile_raw_text, professor_name=professor_name)
    response = llm_client.chat.completions.create(
        model=llm_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract auditable professor profile facts. "
                    "Return strict JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=2048,
        extra_body=extra_body if extra_body is not None else LLM_EXTRA_BODY,
    )
    content = response.choices[0].message.content
    return parse_fact_extraction_response(str(content or ""))


def preflight_professor_fact_backfill(conn: Any) -> FactBackfillPreflightReport:
    total = _scalar_int(conn, "SELECT count(*) FROM professor")
    eligible = _scalar_int(
        conn,
        """
        SELECT count(*)
          FROM professor
         WHERE profile_raw_text IS NOT NULL
           AND length(trim(profile_raw_text)) > 0
        """,
    )
    missing_summary = _scalar_int(
        conn,
        """
        SELECT count(*)
          FROM professor
         WHERE profile_raw_text IS NOT NULL
           AND length(trim(profile_raw_text)) > 0
           AND (profile_summary IS NULL OR length(trim(profile_summary)) = 0)
        """,
    )

    missing_fact_counts: dict[str, int] = {}
    existing_active_fact_counts: dict[str, int] = {}
    for fact_type in TARGET_FACT_TYPES:
        existing_active_fact_counts[fact_type] = _scalar_int(
            conn,
            """
            SELECT count(DISTINCT p.professor_id)
              FROM professor p
              JOIN professor_fact pf
                ON pf.professor_id = p.professor_id
               AND pf.fact_type = %s
               AND pf.status = 'active'
             WHERE p.profile_raw_text IS NOT NULL
               AND length(trim(p.profile_raw_text)) > 0
            """,
            (fact_type,),
        )
        missing_fact_counts[fact_type] = _scalar_int(
            conn,
            """
            SELECT count(*)
              FROM professor p
             WHERE p.profile_raw_text IS NOT NULL
               AND length(trim(p.profile_raw_text)) > 0
               AND NOT EXISTS (
                    SELECT 1
                      FROM professor_fact pf
                     WHERE pf.professor_id = p.professor_id
                       AND pf.fact_type = %s
                       AND pf.status = 'active'
               )
            """,
            (fact_type,),
        )

    return FactBackfillPreflightReport(
        total_professors=total,
        eligible_count=eligible,
        skipped_missing_profile_raw_text=total - eligible,
        missing_profile_summary_count=missing_summary,
        missing_fact_counts=missing_fact_counts,
        existing_active_fact_counts=existing_active_fact_counts,
    )


def select_eligible_professor_rows(
    conn: Any,
    *,
    limit: int | None = None,
    professor_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    conditions = [
        "p.profile_raw_text IS NOT NULL",
        "length(trim(p.profile_raw_text)) > 0",
    ]
    params: list[Any] = []
    ids = list(professor_ids or [])
    if ids:
        placeholders = ", ".join(["%s"] * len(ids))
        conditions.append(f"p.professor_id IN ({placeholders})")
        params.extend(ids)
    sql = (
        "SELECT p.professor_id, p.canonical_name, p.profile_raw_text, "
        "       p.profile_summary, p.primary_official_profile_page_id, "
        "       sp.url AS primary_source_url "
        "  FROM professor p "
        "  LEFT JOIN source_page sp ON sp.page_id = p.primary_official_profile_page_id "
        f" WHERE {' AND '.join(conditions)} "
        " ORDER BY p.professor_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def persist_extracted_facts(
    conn: Any,
    *,
    professor_id: str,
    source_page_id: UUID,
    run_id: UUID | str,
    facts: list[ExtractedProfessorFact],
) -> FactPersistenceReport:
    inserted = 0
    updated = 0
    skipped = 0
    for fact in facts:
        if not fact.value_raw.strip():
            skipped += 1
            continue
        active_key = normalized_fact_key(fact.value_raw, fact.value_normalized)
        existing = _find_existing_active_fact(
            conn,
            professor_id=professor_id,
            fact_type=fact.fact_type,
            active_key=active_key,
        )
        if existing is not None:
            conn.execute(
                """
                UPDATE professor_fact
                   SET value_raw = %s,
                       value_normalized = %s,
                       source_page_id = %s,
                       evidence_span = %s,
                       confidence = %s,
                       status = 'active',
                       run_id = %s,
                       updated_at = now()
                 WHERE fact_id = %s
                """,
                (
                    fact.value_raw.strip(),
                    fact.value_normalized,
                    source_page_id,
                    fact.evidence_span.strip(),
                    fact.confidence,
                    run_id,
                    _row_get(existing, "fact_id", 0),
                ),
            )
            updated += 1
            continue

        conn.execute(
            """
            INSERT INTO professor_fact (
                professor_id,
                fact_type,
                value_raw,
                value_normalized,
                source_page_id,
                evidence_span,
                confidence,
                status,
                run_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', %s)
            """,
            (
                professor_id,
                fact.fact_type,
                fact.value_raw.strip(),
                fact.value_normalized,
                source_page_id,
                fact.evidence_span.strip(),
                fact.confidence,
                run_id,
            ),
        )
        inserted += 1
    return FactPersistenceReport(inserted=inserted, updated=updated, skipped=skipped)


Extractor = Callable[[dict[str, Any]], list[ExtractedProfessorFact]]
Persister = Callable[..., FactPersistenceReport]
SummaryWriter = Callable[..., bool]
QualityReEvaluator = Callable[[Any, str], None]
IssueLogger = Callable[[Any, str, Exception], None]


def run_professor_fact_backfill(
    conn: Any,
    *,
    llm_client: Any,
    llm_model: str,
    run_id: UUID | str,
    limit: int | None = None,
    professor_ids: Iterable[str] | None = None,
    extra_body: dict[str, Any] | None = None,
    dry_run: bool = False,
    extractor: Extractor | None = None,
    persister: Persister | None = None,
    summary_writer: SummaryWriter | None = None,
    quality_re_evaluator: QualityReEvaluator | None = None,
    issue_logger: IssueLogger | None = None,
) -> ProfessorFactBackfillReport:
    """Run fact extraction over eligible professors with per-row isolation."""
    rows = _select_rows_for_runner(conn, limit=limit, professor_ids=professor_ids)
    report = ProfessorFactBackfillReport()
    for row in rows:
        professor_id = str(_row_get(row, "professor_id", 0))
        try:
            raw_text = str(_row_get(row, "profile_raw_text", 2) or "").strip()
            if not raw_text:
                report.skipped += 1
                continue
            source_page_id = _row_get(row, "primary_official_profile_page_id", 4)
            if source_page_id is None:
                raise RuntimeError("Professor has profile_raw_text but no source_page_id")

            if extractor is not None:
                facts = extractor(dict(row))
            else:
                facts = extract_structured_facts(
                    raw_text,
                    professor_name=str(_row_get(row, "canonical_name", 1) or ""),
                    llm_client=llm_client,
                    llm_model=llm_model,
                    extra_body=extra_body,
                )

            if dry_run:
                report.processed += 1
                report.facts_written += len(facts)
                continue

            persist = persister or persist_extracted_facts
            persist_report = persist(
                conn,
                professor_id=professor_id,
                source_page_id=source_page_id,
                run_id=run_id,
                facts=facts,
            )
            report.facts_written += persist_report.inserted + persist_report.updated

            if _needs_summary(row) and summary_writer is not None:
                if summary_writer(conn, dict(row), run_id=run_id):
                    report.summaries_written += 1

            re_eval = quality_re_evaluator or re_evaluate_professor_quality
            re_eval(conn, professor_id)
            report.re_evaluated += 1
            report.processed += 1
            _commit_if_available(conn)
        except Exception as exc:  # noqa: BLE001
            report.failed += 1
            report.errors.append({"professor_id": professor_id, "error": str(exc)})
            _rollback_if_available(conn)
            logger = issue_logger or log_professor_fact_backfill_issue
            if not dry_run:
                logger(conn, professor_id, exc)
    return report


def re_evaluate_professor_quality(conn: Any, professor_id: str) -> None:
    state = load_professor_canonical_state(conn, professor_id)
    evaluation = evaluate_professor_quality(state)
    persist_professor_quality_evaluation(
        conn,
        professor_id=professor_id,
        evaluation=evaluation,
    )


def log_professor_fact_backfill_issue(
    conn: Any,
    professor_id: str,
    error: Exception,
) -> None:
    conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id,
            stage,
            severity,
            description,
            evidence_snapshot,
            reported_by
        )
        VALUES (%s, 'coverage', 'medium', %s, %s::jsonb, 'professor_fact_backfill')
        ON CONFLICT DO NOTHING
        """,
        (
            professor_id,
            f"[professor_fact_backfill:fact_extraction_failed] {error}",
            json.dumps({"error": str(error)}, ensure_ascii=False),
        ),
    )
    _commit_if_available(conn)


def _select_rows_for_runner(
    conn: Any,
    *,
    limit: int | None,
    professor_ids: Iterable[str] | None,
) -> list[dict[str, Any]]:
    if hasattr(conn, "rows"):
        return [dict(row) for row in getattr(conn, "rows")]
    return select_eligible_professor_rows(
        conn,
        limit=limit,
        professor_ids=professor_ids,
    )


def _find_existing_active_fact(
    conn: Any,
    *,
    professor_id: str,
    fact_type: str,
    active_key: str,
) -> Any | None:
    rows = conn.execute(
        """
        SELECT fact_id, value_raw, value_normalized
          FROM professor_fact
         WHERE professor_id = %s
           AND fact_type = %s
           AND status = 'active'
        """,
        (professor_id, fact_type),
    ).fetchall()
    for row in rows:
        if (
            normalized_fact_key(
                str(_row_get(row, "value_raw", 1) or ""),
                _optional_row_text(row, "value_normalized", 2),
            )
            == active_key
        ):
            return row
    return None


def _needs_summary(row: Any) -> bool:
    value = _row_get(row, "profile_summary", 3)
    return value is None or not str(value).strip()


def _scalar_int(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(_row_get(row, "count", 0) or 0)


def _optional_row_text(row: Any, key: str, index: int) -> str | None:
    value = _row_get(row, key, index)
    return str(value) if value is not None else None


def _row_get(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[index]
    except (IndexError, TypeError):
        return None


def _commit_if_available(conn: Any) -> None:
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()


def _rollback_if_available(conn: Any) -> None:
    rollback = getattr(conn, "rollback", None)
    if callable(rollback):
        rollback()
