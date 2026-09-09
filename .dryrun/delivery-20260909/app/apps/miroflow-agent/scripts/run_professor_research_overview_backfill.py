#!/usr/bin/env python3
"""Build or persist durable Chinese Professor research-overview sections."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence, TextIO

import psycopg
from psycopg.rows import dict_row

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.data_agents.professor.profile_sections import (  # noqa: E402
    build_research_overview_section,
    persist_research_overview_section,
)
from src.data_agents.storage.postgres.connection import resolve_dsn  # noqa: E402


def run(
    *,
    conn,
    professor_ids: Sequence[str] | None = None,
    translation_overrides: dict[str, str] | None = None,
    write: bool = False,
    limit: int | None = None,
    output: TextIO = sys.stdout,
) -> int:
    overrides = translation_overrides or {}
    rows = _load_professor_rows(conn, professor_ids=professor_ids, limit=limit)
    results: list[dict[str, Any]] = []
    written = 0
    translated = 0
    section_ready = 0

    for row in rows:
        professor_id = str(_row_value(row, "professor_id", 0))
        override = overrides.get(professor_id)
        translator = (lambda _text, override=override: override) if override else None
        result = build_research_overview_section(
            professor_id=professor_id,
            profile_raw_text=_optional_str(_row_value(row, "profile_raw_text", 2)),
            source_page_id=_row_value(row, "primary_official_profile_page_id", 3),
            run_id=_row_value(row, "run_id", 4),
            translator=translator,
        )
        section = result.section
        row_payload: dict[str, Any] = {
            "professor_id": professor_id,
            "canonical_name": _optional_str(_row_value(row, "canonical_name", 1)),
            "status": result.status,
            "reason": result.reason,
        }
        if section is not None:
            section_ready += 1
            if section.generation_method == "llm_translation":
                translated += 1
            row_payload.update(
                {
                    "language": section.language,
                    "source_language": section.source_language,
                    "generation_method": section.generation_method,
                    "source_text_hash": section.source_text_hash,
                    "content_preview": section.content[:180],
                }
            )
            if write:
                section_id = persist_research_overview_section(conn, result)
                row_payload["section_id"] = str(section_id) if section_id else None
                if section_id is not None:
                    written += 1
        results.append(row_payload)

    output.write(
        json.dumps(
            {
                "dry_run": not write,
                "processed": len(rows),
                "section_ready": section_ready,
                "translated": translated,
                "written": written,
                "rows": results,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = args.database_url or os.environ.get("DATABASE_URL") or os.environ.get(
        "DATABASE_URL_TEST"
    )
    if not dsn:
        sys.stderr.write("DATABASE_URL or --database-url is required.\n")
        return 2
    overrides = _load_translation_overrides(
        json_payload=args.translation_overrides_json,
        file_path=args.translation_overrides_file,
    )
    with psycopg.connect(resolve_dsn(dsn), row_factory=dict_row) as conn:
        exit_code = run(
            conn=conn,
            professor_ids=args.professor_id,
            translation_overrides=overrides,
            write=args.write,
            limit=args.limit,
        )
        if args.write:
            conn.commit()
        return exit_code


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build durable Chinese Professor research-overview sections. Defaults "
            "to dry-run; pass --write to persist sections."
        )
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres DSN. Defaults to DATABASE_URL, then DATABASE_URL_TEST.",
    )
    parser.add_argument(
        "--professor-id",
        action="append",
        default=None,
        help="Professor id to process. Can be repeated.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--translation-overrides-json",
        default=None,
        help="JSON object mapping professor_id to Chinese translation text.",
    )
    parser.add_argument(
        "--translation-overrides-file",
        default=None,
        help="Path to JSON object mapping professor_id to Chinese translation text.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist section rows. Default is read-only dry-run.",
    )
    return parser.parse_args(argv)


def _load_professor_rows(
    conn,
    *,
    professor_ids: Sequence[str] | None,
    limit: int | None,
) -> list[Any]:
    conditions = [
        "profile_raw_text ~* '(research|研究领域|研究方向|研究兴趣|研究概况|研究简介)'"
    ]
    params: dict[str, Any] = {}
    if professor_ids:
        conditions.append("professor_id = ANY(%(professor_ids)s)")
        params["professor_ids"] = list(professor_ids)
    sql = f"""
        SELECT professor_id,
               canonical_name,
               profile_raw_text,
               primary_official_profile_page_id,
               run_id
          FROM professor
         WHERE {' AND '.join(conditions)}
         ORDER BY updated_at DESC NULLS LAST, professor_id ASC
    """
    if limit is not None:
        sql += " LIMIT %(limit)s"
        params["limit"] = int(limit)
    return list(conn.execute(sql, params).fetchall())


def _load_translation_overrides(
    *,
    json_payload: str | None,
    file_path: str | None,
) -> dict[str, str]:
    merged: dict[str, str] = {}
    if file_path:
        merged.update(_parse_override_payload(Path(file_path).read_text(encoding="utf-8")))
    if json_payload:
        merged.update(_parse_override_payload(json_payload))
    return merged


def _parse_override_payload(payload: str) -> dict[str, str]:
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("translation overrides must be a JSON object")
    return {str(key): str(value) for key, value in parsed.items()}


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


if __name__ == "__main__":
    raise SystemExit(main())
