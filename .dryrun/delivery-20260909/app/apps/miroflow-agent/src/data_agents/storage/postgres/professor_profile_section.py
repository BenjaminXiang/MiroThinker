from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID


_SECTION_TYPES = {
    "research_overview",
    "research_progress",
    "education_narrative",
    "work_narrative",
    "honors_narrative",
    "academic_service_narrative",
    "student_work_narrative",
}
_LANGUAGES = {"zh", "en", "mixed", "unknown"}
_GENERATION_METHODS = {
    "official_extract",
    "llm_translation",
    "llm_summary",
    "manual",
}


@dataclass(frozen=True, slots=True)
class ProfessorProfileSectionInput:
    professor_id: str
    section_type: str
    language: str
    content: str
    source_page_id: UUID | str | None = None
    source_language: str | None = None
    source_text: str | None = None
    source_text_hash: str | None = None
    source_span: str | None = None
    generation_method: str = "official_extract"
    run_id: UUID | str | None = None


@dataclass(frozen=True, slots=True)
class ProfessorProfileSectionRecord:
    section_id: UUID | str
    professor_id: str
    section_type: str
    language: str
    content: str
    source_page_id: UUID | str | None
    source_language: str | None
    source_text_hash: str | None
    source_span: str | None
    generation_method: str
    run_id: UUID | str | None


@dataclass(frozen=True, slots=True)
class ProfessorProfileSectionUpsertResult:
    section_id: UUID | str


def upsert_professor_profile_section(
    conn: Any,
    section: ProfessorProfileSectionInput,
) -> ProfessorProfileSectionUpsertResult:
    _validate_section(section)
    source_text_hash = _source_text_hash(section)
    row = conn.execute(
        """
        INSERT INTO professor_profile_section (
            professor_id,
            section_type,
            language,
            content,
            source_page_id,
            source_language,
            source_text_hash,
            source_span,
            generation_method,
            run_id
        )
        VALUES (
            %(professor_id)s,
            %(section_type)s,
            %(language)s,
            %(content)s,
            %(source_page_id)s,
            %(source_language)s,
            %(source_text_hash)s,
            %(source_span)s,
            %(generation_method)s,
            %(run_id)s
        )
        ON CONFLICT ON CONSTRAINT uq_professor_profile_section_source
        DO UPDATE
           SET content = EXCLUDED.content,
               source_page_id = COALESCE(
                   EXCLUDED.source_page_id,
                   professor_profile_section.source_page_id
               ),
               source_language = COALESCE(
                   EXCLUDED.source_language,
                   professor_profile_section.source_language
               ),
               source_span = COALESCE(
                   EXCLUDED.source_span,
                   professor_profile_section.source_span
               ),
               generation_method = EXCLUDED.generation_method,
               run_id = COALESCE(EXCLUDED.run_id, professor_profile_section.run_id),
               updated_at = now()
        RETURNING section_id
        """,
        {
            "professor_id": section.professor_id.strip(),
            "section_type": section.section_type.strip(),
            "language": section.language.strip(),
            "content": section.content.strip(),
            "source_page_id": section.source_page_id,
            "source_language": _optional_clean(section.source_language),
            "source_text_hash": source_text_hash,
            "source_span": _optional_clean(section.source_span),
            "generation_method": section.generation_method.strip(),
            "run_id": section.run_id,
        },
    ).fetchone()
    return ProfessorProfileSectionUpsertResult(
        section_id=_row_value(row, "section_id", 0)
    )


def load_professor_profile_section(
    conn: Any,
    *,
    professor_id: str,
    section_type: str,
    language: str = "zh",
) -> ProfessorProfileSectionRecord | None:
    row = conn.execute(
        """
        SELECT section_id,
               professor_id,
               section_type,
               language,
               content,
               source_page_id,
               source_language,
               source_text_hash,
               source_span,
               generation_method,
               run_id
          FROM professor_profile_section
         WHERE professor_id = %(professor_id)s
           AND section_type = %(section_type)s
           AND language = %(language)s
         ORDER BY updated_at DESC, created_at DESC
         LIMIT 1
        """,
        {
            "professor_id": professor_id,
            "section_type": section_type,
            "language": language,
        },
    ).fetchone()
    if row is None:
        return None
    return ProfessorProfileSectionRecord(
        section_id=_row_value(row, "section_id", 0),
        professor_id=str(_row_value(row, "professor_id", 1)),
        section_type=str(_row_value(row, "section_type", 2)),
        language=str(_row_value(row, "language", 3)),
        content=str(_row_value(row, "content", 4)),
        source_page_id=_row_value(row, "source_page_id", 5),
        source_language=_optional_str(_row_value(row, "source_language", 6)),
        source_text_hash=_optional_str(_row_value(row, "source_text_hash", 7)),
        source_span=_optional_str(_row_value(row, "source_span", 8)),
        generation_method=str(_row_value(row, "generation_method", 9)),
        run_id=_row_value(row, "run_id", 10),
    )


def _validate_section(section: ProfessorProfileSectionInput) -> None:
    if not section.professor_id.strip():
        raise ValueError("professor_id is required")
    if section.section_type not in _SECTION_TYPES:
        raise ValueError(f"unsupported section_type: {section.section_type}")
    if section.language not in _LANGUAGES:
        raise ValueError(f"unsupported language: {section.language}")
    if not section.content.strip():
        raise ValueError("content is required")
    if section.generation_method not in _GENERATION_METHODS:
        raise ValueError(f"unsupported generation_method: {section.generation_method}")


def _source_text_hash(section: ProfessorProfileSectionInput) -> str:
    if section.source_text_hash and section.source_text_hash.strip():
        return section.source_text_hash.strip()
    source = section.source_text or section.source_span or section.content
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _optional_clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError):
        return row[index]
