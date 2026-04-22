"""M6 Unit 2 — CLI to backfill enriched profile_summary via Gemma4.

Iterates professors (default: only those with missing/short profile_summary),
joins their linked papers via professor_paper_link × paper_full_text,
calls summary_reinforcement.generate_reinforced_profile_summary, and
updates professor.profile_summary in place (unless --dry-run).

Per-prof failures are logged and skipped; run never raises to the caller
on content-level issues.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

# Make src/ importable when running from the apps/miroflow-agent dir.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings  # noqa: E402
from src.data_agents.professor.summary_reinforcement import (  # noqa: E402
    PaperContext,
    ReinforcementResult,
    generate_reinforced_profile_summary,
    summary_reinforcement_needed,
)

logger = logging.getLogger("run_profile_summary_reinforcement")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill enriched professor.profile_summary via Gemma4.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max profs to process")
    parser.add_argument(
        "--max-papers",
        type=int,
        default=5,
        help="Max papers per prof fed to LLM (default 5)",
    )
    only_group = parser.add_mutually_exclusive_group()
    only_group.add_argument(
        "--only-missing",
        dest="only_missing",
        action="store_true",
        help="Only process profs with missing/short profile_summary (default)",
    )
    only_group.add_argument(
        "--all",
        dest="only_missing",
        action="store_false",
        help="Process ALL profs (overwrite existing summaries)",
    )
    parser.set_defaults(only_missing=True)
    parser.add_argument(
        "--resume",
        nargs="?",
        const="",
        default=None,
        help="Checkpoint JSONL path to skip already-processed profs",
    )
    parser.add_argument("--dry-run", action="store_true", help="No DB writes")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _open_database_connection(url: str):
    return psycopg.connect(url, row_factory=dict_row)


def _open_llm_client():
    """Returns (openai_client, model_name, extra_body)."""
    from openai import OpenAI

    settings = resolve_professor_llm_settings("gemma4", include_profile=True)
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        timeout=60.0,
    )
    extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
    return client, settings["local_llm_model"], extra_body


def _load_resume_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    ids: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Skipping corrupted resume line: %s", line[:80])
                continue
            if isinstance(row, dict) and isinstance(row.get("prof_id"), str):
                ids.add(row["prof_id"])
    return ids


def _build_select_sql(*, only_missing: bool, limit: int | None) -> tuple[str, tuple]:
    clauses = ["1=1"]
    params: list = []
    if only_missing:
        clauses.append("(profile_summary IS NULL OR length(profile_summary) < 50)")
    sql = (
        "SELECT professor_id, canonical_name, institution, "
        "       research_directions, profile_summary, profile_raw_text "
        "  FROM professor "
        f" WHERE {' AND '.join(clauses)} "
        " ORDER BY professor_id"
    )
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
    return sql, tuple(params)


def _fetch_paper_contexts(conn, professor_id: str, *, max_papers: int) -> list[PaperContext]:
    rows = conn.execute(
        """
        SELECT p.title, pft.abstract, pft.intro, p.year, p.venue
          FROM professor_paper_link ppl
          JOIN paper p ON p.paper_id = ppl.paper_id
          JOIN paper_full_text pft ON pft.paper_id = p.paper_id
         WHERE ppl.professor_id = %s
           AND ppl.link_status IN ('verified', 'candidate')
         ORDER BY COALESCE(p.year, 0) DESC
         LIMIT %s
        """,
        (professor_id, max_papers),
    ).fetchall()
    return [
        PaperContext(
            title=str(r.get("title") or ""),
            abstract=r.get("abstract"),
            intro=r.get("intro"),
            year=r.get("year"),
            venue=r.get("venue"),
        )
        for r in rows
    ]


def _persist_summary(conn, *, professor_id: str, summary: str) -> None:
    conn.execute(
        "UPDATE professor SET profile_summary = %s, updated_at = NOW() "
        "WHERE professor_id = %s",
        (summary, professor_id),
    )


def _append_checkpoint(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _resolve_checkpoint_path(resume_arg: str | None, run_id: str) -> Path:
    base = _REPO_ROOT / "logs" / "data_agents" / "professor" / "summary_reinforcement_runs"
    if resume_arg:
        # Explicit path
        return Path(resume_arg)
    # Implicit new run
    return base / f"{run_id}.jsonl"


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        print(
            "ERROR: DATABASE_URL not set. Run with DATABASE_URL=postgresql://...",
            file=sys.stderr,
        )
        sys.exit(1)

    run_id = str(uuid.uuid4())
    conn = _open_database_connection(dsn)
    llm, llm_model, extra_body = _open_llm_client()

    resume_path: Path | None = None
    if args.resume is not None:
        resume_path = _resolve_checkpoint_path(args.resume, run_id)
    resume_ids = _load_resume_ids(resume_path) if resume_path else set()

    new_checkpoint_path = _resolve_checkpoint_path(None, run_id)

    sql, params = _build_select_sql(only_missing=args.only_missing, limit=args.limit)
    prof_rows = conn.execute(sql, params).fetchall()

    started_at = time.monotonic()
    report = {
        "run_id": run_id,
        "profs_total": len(prof_rows),
        "profs_processed": 0,
        "profs_skipped": 0,
        "summaries_written": 0,
        "summaries_rejected": 0,
        "profs_with_errors": 0,
    }

    for prof in prof_rows:
        prof_id = str(prof["professor_id"])
        if prof_id in resume_ids:
            report["profs_skipped"] += 1
            continue

        if args.only_missing and not summary_reinforcement_needed(prof.get("profile_summary")):
            # Defensive: should have been filtered by SQL already.
            report["profs_skipped"] += 1
            continue

        report["profs_processed"] += 1
        try:
            paper_contexts = _fetch_paper_contexts(
                conn, prof_id, max_papers=args.max_papers
            )
            result: ReinforcementResult = generate_reinforced_profile_summary(
                prof_name=str(prof.get("canonical_name") or ""),
                institution=str(prof.get("institution") or ""),
                research_directions=list(prof.get("research_directions") or []),
                bio=prof.get("profile_raw_text"),
                paper_contexts=paper_contexts,
                llm_client=llm,
                llm_model=llm_model,
                max_papers=args.max_papers,
                extra_body=extra_body,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Prof %s reinforcement crashed: %s", prof_id, exc)
            report["profs_with_errors"] += 1
            _append_checkpoint(
                new_checkpoint_path,
                {"prof_id": prof_id, "status": "error", "error": str(exc)},
            )
            continue

        if result.summary:
            if not args.dry_run:
                try:
                    _persist_summary(
                        conn,
                        professor_id=prof_id,
                        summary=result.summary,
                    )
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Persist failed for prof %s: %s", prof_id, exc)
                    report["profs_with_errors"] += 1
                    _append_checkpoint(
                        new_checkpoint_path,
                        {
                            "prof_id": prof_id,
                            "status": "persist_error",
                            "error": str(exc),
                        },
                    )
                    continue
            report["summaries_written"] += 1
            _append_checkpoint(
                new_checkpoint_path,
                {
                    "prof_id": prof_id,
                    "status": "written" if not args.dry_run else "dry_run_success",
                    "chars": len(result.summary),
                    "source_paper_count": result.source_paper_count,
                },
            )
        else:
            report["summaries_rejected"] += 1
            _append_checkpoint(
                new_checkpoint_path,
                {
                    "prof_id": prof_id,
                    "status": "rejected",
                    "error": result.error,
                    "source_paper_count": result.source_paper_count,
                },
            )

    report["duration_seconds"] = round(time.monotonic() - started_at, 2)
    report["dry_run"] = args.dry_run
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
