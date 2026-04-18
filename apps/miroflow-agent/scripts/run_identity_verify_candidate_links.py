"""Round 7.6 — run the LLM identity gate over existing professor_paper_link
rows and reconcile ``link_status``.

For every professor with at least one link in ``link_status IN
('candidate', 'verified')``, the script:

1. Loads the professor's canonical name, primary institution, and active
   ``research_topic`` facts to build a :class:`ProfessorContext`.
2. Loads the linked papers (title, authors, venue, year, abstract) and
   passes them through :func:`batch_verify_paper_identity`.
3. Promotes accepted links to ``verified`` (``verified_by='llm_auto'``)
   and demotes rejected ones to ``rejected`` with reasoning captured in
   ``rejected_reason``.

Usage::

    DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \\
      uv run python scripts/run_identity_verify_candidate_links.py \\
        [--limit N] [--professor-id PROF-xxx PROF-yyy ...] [--dry-run]

Safety: refuses to write to ``miroflow_test_mock`` unless
``ALLOW_MOCK_BACKFILL=1`` is set (pytest fixtures do that).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import traceback
from dataclasses import dataclass, field
from typing import Iterable

import psycopg
from psycopg.rows import tuple_row

from src.data_agents.professor.identity_verifier import ProfessorContext
from src.data_agents.professor.llm_profiles import (
    render_professor_llm_profile_names,
    resolve_professor_llm_settings,
)
from src.data_agents.professor.paper_identity_gate import (
    PaperIdentityCandidate,
    PaperIdentityDecision,
    batch_verify_paper_identity,
)
from src.data_agents.storage.postgres.connection import resolve_dsn

_DEFAULT_LLM_PROFILE = "gemma4"


@dataclass
class GateStats:
    professors_processed: int = 0
    links_examined: int = 0
    links_promoted: int = 0
    links_rejected: int = 0
    links_unchanged: int = 0
    llm_errors: int = 0
    per_prof_errors: int = 0
    rejected_samples: list[tuple[str, str, str]] = field(default_factory=list)


def _iter_professor_ids(
    conn,
    *,
    limit: int | None,
    filter_ids: list[str] | None,
    missing_topic_score_only: bool = False,
) -> Iterable[str]:
    if missing_topic_score_only:
        clauses = [
            "ppl.link_status = 'verified'",
            "ppl.topic_consistency_score IS NULL",
        ]
    else:
        clauses = ["ppl.link_status IN ('candidate', 'verified')"]
    params: list[object] = []
    if filter_ids:
        clauses.append("ppl.professor_id = ANY(%s)")
        params.append(filter_ids)
    sql = f"""
        SELECT ppl.professor_id
          FROM professor_paper_link ppl
         WHERE {" AND ".join(clauses)}
         GROUP BY ppl.professor_id
         ORDER BY ppl.professor_id
    """
    if limit is not None:
        sql += f"\n         LIMIT {int(limit)}"
    for (pid,) in conn.execute(sql, params).fetchall():
        yield pid


def _load_context(conn, professor_id: str) -> ProfessorContext | None:
    row = conn.execute(
        """
        SELECT p.canonical_name,
               pa.institution,
               pa.title
          FROM professor p
          LEFT JOIN professor_affiliation pa
            ON pa.professor_id=p.professor_id AND pa.is_primary=true
         WHERE p.professor_id=%s
        """,
        (professor_id,),
    ).fetchone()
    if row is None or not row[0]:
        return None
    name, institution, department = row
    topics = [
        t[0]
        for t in conn.execute(
            """
            SELECT value_raw
              FROM professor_fact
             WHERE professor_id=%s AND fact_type='research_topic' AND status='active'
             ORDER BY created_at
            """,
            (professor_id,),
        ).fetchall()
        if t[0]
    ]
    return ProfessorContext(
        name=name,
        institution=institution or "未知",
        department=department,
        research_directions=topics[:12] or None,
    )


def _load_candidates(
    conn,
    professor_id: str,
    *,
    missing_topic_score_only: bool = False,
) -> list[tuple[str, PaperIdentityCandidate, str]]:
    """Return (link_id, candidate, current_status) tuples."""
    if missing_topic_score_only:
        status_filter = (
            "ppl.link_status='verified' AND ppl.topic_consistency_score IS NULL"
        )
    else:
        status_filter = "ppl.link_status IN ('candidate', 'verified')"
    rows = conn.execute(
        f"""
        SELECT ppl.link_id::text,
               ppl.link_status,
               paper.title_clean,
               paper.authors_display,
               paper.year,
               paper.venue,
               paper.abstract_clean
          FROM professor_paper_link ppl
          JOIN paper ON paper.paper_id=ppl.paper_id
         WHERE ppl.professor_id=%s
           AND {status_filter}
         ORDER BY paper.citation_count DESC NULLS LAST, paper.year DESC NULLS LAST
        """,
        (professor_id,),
    ).fetchall()
    out: list[tuple[str, PaperIdentityCandidate, str]] = []
    for idx, (link_id, status, title, authors_csv, year, venue, abstract) in enumerate(rows):
        authors = [a.strip() for a in (authors_csv or "").split(",") if a.strip()]
        out.append(
            (
                link_id,
                PaperIdentityCandidate(
                    index=idx,
                    title=title or "",
                    authors=authors,
                    year=year,
                    venue=venue,
                    abstract=abstract,
                ),
                status,
            )
        )
    return out


def _apply_decision(
    conn,
    *,
    link_id: str,
    decision: PaperIdentityDecision,
    current_status: str,
    dry_run: bool,
) -> str:
    """Return one of 'promoted' | 'rejected' | 'unchanged'."""
    target_status = "verified" if decision.accepted else "rejected"
    topic_score = decision.topic_consistency
    if target_status == current_status:
        # Already in the right bucket; update reasoning + score anyway (for verified).
        if target_status == "verified" and not dry_run:
            conn.execute(
                """
                UPDATE professor_paper_link
                   SET verified_by='llm_auto',
                       verified_at=COALESCE(verified_at, now()),
                       match_reason=%s,
                       topic_consistency_score=COALESCE(%s, topic_consistency_score),
                       updated_at=now()
                 WHERE link_id=%s::uuid
                """,
                (
                    decision.reasoning[:400] or "llm identity gate confirmed",
                    topic_score,
                    link_id,
                ),
            )
        return "unchanged"

    if decision.accepted:
        if not dry_run:
            conn.execute(
                """
                UPDATE professor_paper_link
                   SET link_status='verified',
                       verified_by='llm_auto',
                       verified_at=now(),
                       match_reason=%s,
                       topic_consistency_score=%s,
                       rejected_at=NULL,
                       rejected_reason=NULL,
                       updated_at=now()
                 WHERE link_id=%s::uuid
                """,
                (
                    decision.reasoning[:400] or "llm identity gate accepted",
                    topic_score,
                    link_id,
                ),
            )
        return "promoted"
    else:
        if not dry_run:
            conn.execute(
                """
                UPDATE professor_paper_link
                   SET link_status='rejected',
                       rejected_at=now(),
                       rejected_reason=%s,
                       topic_consistency_score=%s,
                       updated_at=now()
                 WHERE link_id=%s::uuid
                """,
                (
                    decision.reasoning[:400] or "llm identity gate rejected",
                    topic_score,
                    link_id,
                ),
            )
        return "rejected"


async def _process_professor(
    conn,
    professor_id: str,
    *,
    llm_client,
    llm_model: str,
    dry_run: bool,
    stats: GateStats,
    missing_topic_score_only: bool = False,
) -> None:
    context = _load_context(conn, professor_id)
    if context is None:
        return
    triples = _load_candidates(
        conn, professor_id, missing_topic_score_only=missing_topic_score_only
    )
    if not triples:
        return
    candidates = [t[1] for t in triples]
    stats.links_examined += len(candidates)

    try:
        decisions = await batch_verify_paper_identity(
            professor_context=context,
            candidates=candidates,
            llm_client=llm_client,
            llm_model=llm_model,
        )
    except Exception as exc:  # pragma: no cover - runtime LLM faults
        stats.per_prof_errors += 1
        print(
            f"  [err] gate failed for {professor_id} ({context.name}): {exc}",
            file=sys.stderr,
        )
        traceback.print_exc()
        return

    for (link_id, cand, current_status), decision in zip(triples, decisions):
        if decision.error is not None:
            stats.llm_errors += 1
        outcome = _apply_decision(
            conn,
            link_id=link_id,
            decision=decision,
            current_status=current_status,
            dry_run=dry_run,
        )
        if outcome == "promoted":
            stats.links_promoted += 1
        elif outcome == "rejected":
            stats.links_rejected += 1
            if len(stats.rejected_samples) < 15:
                stats.rejected_samples.append(
                    (context.name, cand.title[:80], decision.reasoning[:120])
                )
        else:
            stats.links_unchanged += 1
    stats.professors_processed += 1


async def _run(args: argparse.Namespace) -> int:
    dsn_sa = resolve_dsn()
    if (
        "miroflow_test_mock" in dsn_sa
        and os.environ.get("ALLOW_MOCK_BACKFILL") != "1"
    ):
        print(
            "ERROR: refusing to run against miroflow_test_mock by default. "
            "Set ALLOW_MOCK_BACKFILL=1 (pytest does this) or point "
            "DATABASE_URL at miroflow_real.",
            file=sys.stderr,
        )
        return 3
    pg_dsn = dsn_sa.replace("postgresql+psycopg://", "postgresql://", 1)

    # Internal LLM endpoints reject SOCKS/HTTP proxies set in the ambient env.
    for key in ("all_proxy", "ALL_PROXY", "http_proxy", "HTTP_PROXY",
                "https_proxy", "HTTPS_PROXY"):
        os.environ.pop(key, None)

    llm_settings = resolve_professor_llm_settings(
        profile_name=args.llm_profile, include_profile=True
    )
    profile = llm_settings["llm_profile"]
    print(f"[gate] llm profile = {profile}")

    from openai import OpenAI

    if args.use_online:
        base_url = llm_settings["online_llm_base_url"]
        api_key = llm_settings["online_llm_api_key"]
        model = llm_settings["online_llm_model"]
    else:
        base_url = llm_settings["local_llm_base_url"]
        api_key = llm_settings["local_llm_api_key"]
        model = llm_settings["local_llm_model"]

    print(f"[gate] endpoint = {base_url}  model = {model}")
    client = OpenAI(
        base_url=base_url,
        api_key=api_key or "EMPTY",
        timeout=60.0,
    )

    stats = GateStats()
    with psycopg.connect(pg_dsn, row_factory=tuple_row) as conn:
        prof_ids = list(
            _iter_professor_ids(
                conn,
                limit=args.limit,
                filter_ids=args.professor_id,
                missing_topic_score_only=args.backfill_topic_scores,
            )
        )
        mode_desc = (
            "topic-score backfill (verified w/ NULL score only)"
            if args.backfill_topic_scores
            else "full identity gate"
        )
        print(f"[gate] mode = {mode_desc}")
        print(f"[gate] professors to process: {len(prof_ids)}")
        for i, pid in enumerate(prof_ids, 1):
            await _process_professor(
                conn,
                pid,
                llm_client=client,
                llm_model=model,
                dry_run=args.dry_run,
                stats=stats,
                missing_topic_score_only=args.backfill_topic_scores,
            )
            if i % args.commit_every == 0 and not args.dry_run:
                conn.commit()
            if i % 20 == 0:
                print(
                    f"  [progress] {i}/{len(prof_ids)}  promoted={stats.links_promoted} "
                    f"rejected={stats.links_rejected} unchanged={stats.links_unchanged}"
                )
        if not args.dry_run:
            conn.commit()

    print()
    print("=== identity gate summary ===")
    print(f"  professors_processed : {stats.professors_processed}")
    print(f"  links_examined       : {stats.links_examined}")
    print(f"  links_promoted       : {stats.links_promoted}")
    print(f"  links_rejected       : {stats.links_rejected}")
    print(f"  links_unchanged      : {stats.links_unchanged}")
    print(f"  per_professor_errors : {stats.per_prof_errors}")
    print(f"  llm_parse_errors     : {stats.llm_errors}")
    if stats.rejected_samples:
        print("\nrejected samples (prof | title | reason):")
        for name, title, reason in stats.rejected_samples:
            print(f"  {name} | {title!r} | {reason!r}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Round 7.6 LLM identity gate backfill.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process first N professors (for smoke tests).")
    parser.add_argument("--professor-id", nargs="*", default=None,
                        help="Restrict to these professor IDs.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print decisions without updating the DB.")
    parser.add_argument("--commit-every", type=int, default=25,
                        help="Commit DB after every N professors processed.")
    parser.add_argument(
        "--llm-profile",
        type=str,
        default=_DEFAULT_LLM_PROFILE,
        help=f"LLM profile (default {_DEFAULT_LLM_PROFILE}). "
             f"Available: {render_professor_llm_profile_names()}",
    )
    parser.add_argument(
        "--use-online",
        action="store_true",
        help="Use the profile's online endpoint instead of the local one "
             "(default is local for faster/free Gemma-4 verification).",
    )
    parser.add_argument(
        "--backfill-topic-scores",
        action="store_true",
        help="Second-pass mode: only re-examine currently-verified links "
             "whose topic_consistency_score is NULL, keep the decision but "
             "fill the score. Use after an initial gate run to populate "
             "topic_consistency_score on existing rows.",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
