"""Professor paper/patent output-summary input selection."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass(frozen=True, slots=True)
class PaperSummaryInput:
    paper_id: str
    title: str
    year: int | None
    venue: str | None
    abstract_clean: str | None
    summary_zh: str | None
    authors_display: str | None
    citation_count: int | None
    canonical_source: str
    link_status: str
    match_reason: str


@dataclass(frozen=True, slots=True)
class PatentSummaryInput:
    patent_id: str
    patent_number: str
    title: str
    patent_type: str | None
    status: str | None
    abstract_clean: str | None
    technology_effect: str | None
    ipc_codes: tuple[str, ...]
    summary_text: str | None
    link_status: str
    match_reason: str | None


@dataclass(frozen=True, slots=True)
class ProfessorOutputSummaryResult:
    paper_summary: str | None
    patent_summary: str | None
    no_summary_reason: str | None = None


@dataclass(frozen=True, slots=True)
class OutputSummaryPersistenceResult:
    changed_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OutputSummaryBackfillReport:
    eligible: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    paper_summaries_written: int = 0
    patent_summaries_written: int = 0
    refresh_professor_ids: tuple[str, ...] = ()
    dry_run: bool = False


def generate_professor_output_summaries(
    *,
    professor_name: str,
    paper_inputs: tuple[PaperSummaryInput, ...],
    patent_inputs: tuple[PatentSummaryInput, ...],
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any] | None = None,
) -> ProfessorOutputSummaryResult:
    """Generate durable professor output summaries from accepted outputs."""
    if not paper_inputs and not patent_inputs:
        return ProfessorOutputSummaryResult(
            paper_summary=None,
            patent_summary=None,
            no_summary_reason="no eligible papers or patents",
        )

    prompt = _build_output_summary_prompt(
        professor_name=professor_name,
        paper_inputs=paper_inputs,
        patent_inputs=patent_inputs,
    )
    response = llm_client.chat.completions.create(
        model=llm_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You summarize professor research outputs. Return strict JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=1024,
        extra_body=extra_body or {},
    )
    payload = _parse_json_payload(response.choices[0].message.content)
    return ProfessorOutputSummaryResult(
        paper_summary=_optional_str(payload.get("paper_summary")),
        patent_summary=_optional_str(payload.get("patent_summary")),
    )


def run_output_summary_backfill(
    conn: Any,
    *,
    run_id: str,
    llm_client: Any,
    llm_model: str,
    dry_run: bool,
    limit: int | None = None,
    professor_ids: tuple[str, ...] = (),
    extra_body: dict[str, Any] | None = None,
) -> OutputSummaryBackfillReport:
    professors = select_professors_for_output_summary_backfill(
        conn,
        limit=limit,
        professor_ids=professor_ids,
    )
    processed = 0
    skipped = 0
    failed = 0
    paper_written = 0
    patent_written = 0
    refresh_ids: list[str] = []

    for professor_id, professor_name in professors:
        processed += 1
        try:
            paper_inputs = select_eligible_paper_summary_inputs(
                conn,
                professor_id=professor_id,
            )
            patent_inputs = select_eligible_patent_summary_inputs(
                conn,
                professor_id=professor_id,
            )
            result = generate_professor_output_summaries(
                professor_name=professor_name,
                paper_inputs=paper_inputs,
                patent_inputs=patent_inputs,
                llm_client=llm_client,
                llm_model=llm_model,
                extra_body=extra_body,
            )
            if result.no_summary_reason:
                skipped += 1
                continue

            if dry_run:
                paper_written += int(result.paper_summary is not None)
                patent_written += int(result.patent_summary is not None)
                continue

            persistence = persist_professor_output_summaries(
                conn,
                professor_id=professor_id,
                paper_summary=result.paper_summary,
                patent_summary=result.patent_summary,
                run_id=run_id,
            )
            if "paper_summary" in persistence.changed_fields:
                paper_written += 1
            if "patent_summary" in persistence.changed_fields:
                patent_written += 1
            if persistence.changed_fields:
                refresh_ids.append(professor_id)
        except Exception:  # noqa: BLE001
            failed += 1
            continue

    return OutputSummaryBackfillReport(
        eligible=len(professors),
        processed=processed,
        skipped=skipped,
        failed=failed,
        paper_summaries_written=paper_written,
        patent_summaries_written=patent_written,
        refresh_professor_ids=tuple(refresh_ids),
        dry_run=bool(dry_run),
    )


def select_professors_for_output_summary_backfill(
    conn: Any,
    *,
    limit: int | None = None,
    professor_ids: tuple[str, ...] = (),
) -> tuple[tuple[str, str], ...]:
    params: list[Any] = []
    conditions = ["p.identity_status <> 'merged_into'"]
    if professor_ids:
        conditions.append("p.professor_id = ANY(%s)")
        params.append(list(professor_ids))

    sql = f"""
        SELECT p.professor_id, p.canonical_name
          FROM professor AS p
         WHERE {' AND '.join(conditions)}
           AND (
               EXISTS (
                   SELECT 1
                     FROM professor_paper_link AS ppl
                     JOIN paper AS paper ON paper.paper_id = ppl.paper_id
                    WHERE ppl.professor_id = p.professor_id
                      AND ppl.link_status = 'verified'
                      AND paper.identity_status NOT IN ('rejected', 'merged')
               )
               OR EXISTS (
                   SELECT 1
                     FROM professor_patent_link AS ppl
                     JOIN patent AS patent ON patent.patent_id = ppl.patent_id
                    WHERE ppl.professor_id = p.professor_id
                      AND ppl.link_status = 'verified'
                      AND patent.identity_status NOT IN ('rejected', 'merged')
               )
           )
         ORDER BY p.professor_id
    """
    if limit is not None:
        sql += " LIMIT %s"
        params.append(_normalize_limit(limit))

    rows = conn.execute(sql, tuple(params)).fetchall()
    return tuple(
        (
            str(_row_value(row, "professor_id", 0)),
            str(_row_value(row, "canonical_name", 1)),
        )
        for row in rows
    )


def persist_professor_output_summaries(
    conn: Any,
    *,
    professor_id: str,
    paper_summary: str | None,
    patent_summary: str | None,
    run_id: str,
) -> OutputSummaryPersistenceResult:
    row = conn.execute(
        """
        SELECT paper_summary, patent_summary
          FROM professor
         WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchone()
    if row is None:
        return OutputSummaryPersistenceResult()

    current_paper = _optional_str(_row_value(row, "paper_summary", 0))
    current_patent = _optional_str(_row_value(row, "patent_summary", 1))
    next_paper = _optional_str(paper_summary)
    next_patent = _optional_str(patent_summary)
    changed_fields: list[str] = []

    if next_paper is not None and next_paper != current_paper:
        changed_fields.append("paper_summary")
    else:
        next_paper = current_paper

    if next_patent is not None and next_patent != current_patent:
        changed_fields.append("patent_summary")
    else:
        next_patent = current_patent

    if not changed_fields:
        return OutputSummaryPersistenceResult()

    conn.execute(
        """
        UPDATE professor
           SET paper_summary = %s,
               patent_summary = %s,
               run_id = %s,
               updated_at = now()
         WHERE professor_id = %s
        """,
        (next_paper, next_patent, run_id, professor_id),
    )
    return OutputSummaryPersistenceResult(changed_fields=tuple(changed_fields))


def select_professors_for_research_vector_refresh(
    conn: Any,
    *,
    run_id: str,
) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT professor_id
          FROM professor
         WHERE run_id = %s
           AND (paper_summary IS NOT NULL OR patent_summary IS NOT NULL)
         ORDER BY professor_id
        """,
        (run_id,),
    ).fetchall()
    return tuple(str(_row_value(row, "professor_id", 0)) for row in rows)


def select_eligible_paper_summary_inputs(
    conn: Any,
    *,
    professor_id: str,
    limit: int = 50,
) -> tuple[PaperSummaryInput, ...]:
    """Return accepted paper rows eligible for professor paper summaries."""
    professor_id = _require_non_empty("professor_id", professor_id)
    limit = _normalize_limit(limit)
    if limit == 0:
        return ()

    rows = conn.execute(
        """
        WITH resolved_links AS (
            SELECT
                COALESCE(pma.canonical_paper_id, ppl.paper_id) AS resolved_paper_id,
                ppl.link_status,
                ppl.match_reason
              FROM professor_paper_link AS ppl
              LEFT JOIN paper_merge_alias AS pma
                ON pma.old_paper_id = ppl.paper_id
             WHERE ppl.professor_id = %s
               AND ppl.link_status = 'verified'
        ),
        ranked AS (
            SELECT
                p.paper_id,
                p.title_clean,
                p.year,
                p.venue,
                p.abstract_clean,
                p.summary_zh,
                p.authors_display,
                p.citation_count,
                p.canonical_source,
                rl.link_status,
                rl.match_reason,
                row_number() OVER (
                    PARTITION BY
                        lower(regexp_replace(COALESCE(p.title_clean, ''), '\\s+', '', 'g')),
                        p.year
                    ORDER BY
                        CASE WHEN p.canonical_source = 'prof_page_only' THEN 1 ELSE 0 END,
                        p.citation_count DESC NULLS LAST,
                        p.paper_id ASC
                ) AS duplicate_rank
              FROM resolved_links AS rl
              JOIN paper AS p ON p.paper_id = rl.resolved_paper_id
             WHERE p.identity_status NOT IN ('rejected', 'merged')
               AND p.quality_status = 'ready'
        )
        SELECT
            paper_id,
            title_clean,
            year,
            venue,
            abstract_clean,
            summary_zh,
            authors_display,
            citation_count,
            canonical_source,
            link_status,
            match_reason
          FROM ranked
         WHERE duplicate_rank = 1
         ORDER BY year DESC NULLS LAST, title_clean ASC, paper_id ASC
         LIMIT %s
        """,
        (professor_id, limit),
    ).fetchall()

    return tuple(
        PaperSummaryInput(
            paper_id=str(_row_value(row, "paper_id", 0)),
            title=str(_row_value(row, "title_clean", 1)),
            year=_optional_int(_row_value(row, "year", 2)),
            venue=_optional_str(_row_value(row, "venue", 3)),
            abstract_clean=_optional_str(_row_value(row, "abstract_clean", 4)),
            summary_zh=_optional_str(_row_value(row, "summary_zh", 5)),
            authors_display=_optional_str(_row_value(row, "authors_display", 6)),
            citation_count=_optional_int(_row_value(row, "citation_count", 7)),
            canonical_source=str(_row_value(row, "canonical_source", 8)),
            link_status=str(_row_value(row, "link_status", 9)),
            match_reason=str(_row_value(row, "match_reason", 10)),
        )
        for row in rows
    )


def select_eligible_patent_summary_inputs(
    conn: Any,
    *,
    professor_id: str,
    limit: int = 50,
) -> tuple[PatentSummaryInput, ...]:
    """Return accepted patent rows eligible for professor patent summaries."""
    professor_id = _require_non_empty("professor_id", professor_id)
    limit = _normalize_limit(limit)
    if limit == 0:
        return ()

    rows = conn.execute(
        """
        SELECT
            p.patent_id,
            p.patent_number,
            p.title_clean,
            p.patent_type,
            p.status,
            p.abstract_clean,
            p.technology_effect,
            p.ipc_codes,
            p.summary_text,
            ppl.link_status,
            ppl.match_reason
          FROM professor_patent_link AS ppl
          JOIN patent AS p ON p.patent_id = ppl.patent_id
         WHERE ppl.professor_id = %s
           AND ppl.link_status = 'verified'
           AND p.identity_status NOT IN ('rejected', 'merged')
         ORDER BY COALESCE(p.publication_date, p.filing_date, p.grant_date) DESC NULLS LAST,
                  p.title_clean ASC,
                  p.patent_id ASC
         LIMIT %s
        """,
        (professor_id, limit),
    ).fetchall()

    return tuple(
        PatentSummaryInput(
            patent_id=str(_row_value(row, "patent_id", 0)),
            patent_number=str(_row_value(row, "patent_number", 1)),
            title=str(_row_value(row, "title_clean", 2)),
            patent_type=_optional_str(_row_value(row, "patent_type", 3)),
            status=_optional_str(_row_value(row, "status", 4)),
            abstract_clean=_optional_str(_row_value(row, "abstract_clean", 5)),
            technology_effect=_optional_str(_row_value(row, "technology_effect", 6)),
            ipc_codes=tuple(_row_value(row, "ipc_codes", 7) or ()),
            summary_text=_optional_str(_row_value(row, "summary_text", 8)),
            link_status=str(_row_value(row, "link_status", 9)),
            match_reason=_optional_str(_row_value(row, "match_reason", 10)),
        )
        for row in rows
    )


def _normalize_limit(limit: int) -> int:
    return max(0, min(int(limit), 200))


def _require_non_empty(name: str, value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{name} must be non-empty")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _build_output_summary_prompt(
    *,
    professor_name: str,
    paper_inputs: tuple[PaperSummaryInput, ...],
    patent_inputs: tuple[PatentSummaryInput, ...],
) -> str:
    paper_lines = "\n".join(_paper_prompt_line(item) for item in paper_inputs) or "None"
    patent_lines = (
        "\n".join(_patent_prompt_line(item) for item in patent_inputs) or "None"
    )
    return f"""Create concise source-grounded output summaries for a professor.

Return strict JSON with exactly these keys:
{{
  "paper_summary": string or null,
  "patent_summary": string or null
}}

Rules:
- Use only the linked paper and patent rows below.
- Do not invent claims beyond titles, abstracts, summaries, venues, patent
  effects, or other listed fields.
- Use null for a section with no eligible inputs.
- Keep each summary under 500 Chinese characters or 300 English words.

Professor: {professor_name}

Accepted papers:
{paper_lines}

Accepted patents:
{patent_lines}
"""


def _paper_prompt_line(item: PaperSummaryInput) -> str:
    parts = [
        f"id={item.paper_id}",
        f"title={item.title}",
        f"year={item.year}" if item.year is not None else None,
        f"venue={item.venue}" if item.venue else None,
        f"authors={item.authors_display}" if item.authors_display else None,
        f"citations={item.citation_count}" if item.citation_count is not None else None,
        f"summary={item.summary_zh}" if item.summary_zh else None,
        f"abstract={item.abstract_clean}" if item.abstract_clean else None,
        f"source={item.canonical_source}",
    ]
    return "- " + "; ".join(part for part in parts if part)


def _patent_prompt_line(item: PatentSummaryInput) -> str:
    parts = [
        f"id={item.patent_id}",
        f"number={item.patent_number}",
        f"title={item.title}",
        f"type={item.patent_type}" if item.patent_type else None,
        f"status={item.status}" if item.status else None,
        f"ipc={','.join(item.ipc_codes)}" if item.ipc_codes else None,
        f"summary={item.summary_text}" if item.summary_text else None,
        f"effect={item.technology_effect}" if item.technology_effect else None,
        f"abstract={item.abstract_clean}" if item.abstract_clean else None,
    ]
    return "- " + "; ".join(part for part in parts if part)


def _parse_json_payload(text: object) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("LLM response must contain JSON")
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
        raise ValueError("LLM JSON response must be an object")
    return payload


def _row_value(row: object, key: str, index: int) -> object:
    if isinstance(row, dict):
        return row[key]
    return row[index]  # type: ignore[index]
