# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.18e — re-verify verified links with medium topic_consistency.

534 professor_paper_link rows in miroflow_real are `link_status='verified'`
with `topic_consistency_score ∈ [0.70, 0.85)`. They passed the original
identity gate — usually on a strong name match — but their topic signal
is soft. Some fraction are same-name-different-person (SNDP) contamination
that slipped through; the rest are legit papers in adjacent research areas.

Two-phase re-verification:

  * Phase A — 3 cheap SQL-derived signals per link (coauthor_overlap,
    venue_alignment, year_plausibility). Composite score 0.5/0.25/0.25.
    composite >= 0.7 → keep.  composite <= 0.3 → demote.  mid → Phase B.
  * Phase B — LLM re-verification (batch_verify_paper_identity from
    Round 7.6) for ambiguous links only. Accepts if LLM confidence >= 0.8
    AND is_same_person == True, otherwise demotes.

This is designed to be a long-running overnight task. ~30 min estimated
wallclock with default gemma4 local endpoint.

Usage:

    DATABASE_URL='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real' \
      uv run python scripts/run_medium_consistency_rescan.py
    # apply:
    DATABASE_URL=... uv run python scripts/run_medium_consistency_rescan.py \
      --apply --confirm-real-db
    # Phase A only (fast sanity check — no LLM):
    DATABASE_URL=... uv run python scripts/run_medium_consistency_rescan.py --phase-a-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from src.data_agents.professor.identity_verifier import ProfessorContext
from src.data_agents.professor.llm_profiles import (
    resolve_professor_llm_settings,
)
from src.data_agents.professor.medium_rescan_signals import (
    ProfessorCorpusProfile,
    SignalScores,
    compute_signals,
    _tokenize_authors,
)
from src.data_agents.professor.paper_identity_gate import (
    PaperIdentityCandidate,
    batch_verify_paper_identity,
)
from src.data_agents.storage.postgres.connection import resolve_dsn


_REAL_DB_NAME = "miroflow_real"
_REPORTED_BY = "round_7_18e_medium_rescan"
_LOG_INTERVAL = 50


@dataclass
class RescanStats:
    examined: int = 0
    phase_a_keep: int = 0
    phase_a_demote: int = 0
    phase_b_queued: int = 0
    phase_b_keep: int = 0
    phase_b_demote: int = 0
    phase_b_error: int = 0
    demotes_applied: int = 0
    issues_inserted: int = 0


@dataclass
class CandidateLink:
    link_id: str
    professor_id: str
    paper_id: str
    topic_consistency_score: float
    author_name_match_score: float
    # Paper-side
    title: str
    authors_display: str | None
    venue: str | None
    year: int | None
    abstract: str | None
    # Prof-side (cached)
    professor_name: str = ""
    professor_institution: str = ""
    professor_research_topics: list[str] = field(default_factory=list)
    # Computed
    phase_a: SignalScores | None = None
    final_decision: str = "pending"   # keep | demote | error
    decision_reason: str = ""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Round 7.18e — re-verify medium-confidence verified links."
    )
    parser.add_argument("--database-url")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-real-db", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--phase-a-only",
        action="store_true",
        help="Skip LLM phase B; ambiguous links stay verified as-is.",
    )
    parser.add_argument("--llm-profile", default="gemma4")
    parser.add_argument(
        "--topic-min",
        type=float,
        default=0.70,
        help="Minimum topic_consistency_score to include (inclusive).",
    )
    parser.add_argument(
        "--topic-max",
        type=float,
        default=0.85,
        help="Maximum topic_consistency_score to include (exclusive).",
    )
    return parser.parse_args()


def _clear_proxy_env() -> None:
    for key in (
        "all_proxy",
        "ALL_PROXY",
        "http_proxy",
        "HTTP_PROXY",
        "https_proxy",
        "HTTPS_PROXY",
    ):
        os.environ.pop(key, None)


def _fetch_candidates(
    conn, *, topic_min: float, topic_max: float, limit: int | None
) -> list[CandidateLink]:
    sql = """
        SELECT ppl.link_id::text AS link_id,
               ppl.professor_id,
               ppl.paper_id,
               ppl.topic_consistency_score::float AS topic_consistency_score,
               ppl.author_name_match_score::float AS author_name_match_score,
               p.title_clean AS title,
               p.authors_display,
               p.venue,
               p.year,
               p.abstract_clean AS abstract
          FROM professor_paper_link ppl
          JOIN paper p ON p.paper_id = ppl.paper_id
          JOIN professor pr ON pr.professor_id = ppl.professor_id
         WHERE ppl.link_status = 'verified'
           AND ppl.topic_consistency_score >= %s
           AND ppl.topic_consistency_score < %s
           AND pr.identity_status = 'resolved'
         ORDER BY ppl.professor_id, ppl.topic_consistency_score
    """
    if limit is not None:
        sql += f"\n         LIMIT {int(limit)}"
    rows = conn.execute(sql, (topic_min, topic_max)).fetchall()
    return [CandidateLink(**r) for r in rows]


def _load_prof_contexts(
    conn, *, professor_ids: list[str]
) -> dict[str, dict]:
    """Load canonical_name, institution, research topics keyed by prof_id."""
    if not professor_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(professor_ids))
    sql = f"""
        SELECT p.professor_id,
               p.canonical_name,
               pa.institution,
               COALESCE(
                 (SELECT array_agg(f.value_raw ORDER BY f.created_at)
                    FROM professor_fact f
                   WHERE f.professor_id = p.professor_id
                     AND f.fact_type = 'research_topic'
                     AND f.status = 'active'),
                 ARRAY[]::text[]
               ) AS topics
          FROM professor p
          LEFT JOIN professor_affiliation pa
            ON pa.professor_id = p.professor_id AND pa.is_primary = true
         WHERE p.professor_id IN ({placeholders})
    """
    return {
        row["professor_id"]: row
        for row in conn.execute(sql, professor_ids).fetchall()
    }


def _load_prof_corpus_profiles(
    conn, *, professor_ids: list[str], exclude_paper_ids_by_prof: dict[str, list[str]]
) -> dict[str, ProfessorCorpusProfile]:
    """For each prof, gather coauthor tokens / venues / year range from their
    OTHER verified papers (excluding the candidate papers being rescanned)."""
    if not professor_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(professor_ids))
    sql = f"""
        SELECT ppl.professor_id,
               ppl.paper_id,
               p.authors_display,
               p.venue,
               p.year
          FROM professor_paper_link ppl
          JOIN paper p ON p.paper_id = ppl.paper_id
         WHERE ppl.professor_id IN ({placeholders})
           AND ppl.link_status = 'verified'
    """
    per_prof_tokens: dict[str, set[str]] = defaultdict(set)
    per_prof_venues: dict[str, set[str]] = defaultdict(set)
    per_prof_years: dict[str, list[int]] = defaultdict(list)
    for row in conn.execute(sql, professor_ids).fetchall():
        pid = row["professor_id"]
        # Skip the candidate paper itself — we want OTHER papers
        if row["paper_id"] in exclude_paper_ids_by_prof.get(pid, []):
            continue
        per_prof_tokens[pid].update(_tokenize_authors(row["authors_display"]))
        if row["venue"]:
            per_prof_venues[pid].add(row["venue"])
        if row["year"] is not None:
            per_prof_years[pid].append(row["year"])

    profiles: dict[str, ProfessorCorpusProfile] = {}
    for pid in professor_ids:
        years = per_prof_years.get(pid) or []
        profiles[pid] = ProfessorCorpusProfile(
            professor_id=pid,
            coauthor_tokens=frozenset(per_prof_tokens.get(pid, set())),
            venues=frozenset(per_prof_venues.get(pid, set())),
            year_min=min(years) if years else None,
            year_max=max(years) if years else None,
        )
    return profiles


def _demote(conn, link_id: str, reason: str) -> None:
    conn.execute(
        """
        UPDATE professor_paper_link
           SET link_status = 'rejected',
               rejected_at = now(),
               rejected_reason = %s,
               updated_at = now()
         WHERE link_id = %s::uuid
        """,
        (reason, link_id),
    )


def _file_issue(
    conn,
    *,
    link: CandidateLink,
    signals: SignalScores | None,
    decision: str,
    reason: str,
    llm_confidence: float | None = None,
) -> int:
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "cleanup_round": "round_7_18e",
        "link_id": link.link_id,
        "professor_id": link.professor_id,
        "paper_id": link.paper_id,
        "paper_title": link.title,
        "paper_year": link.year,
        "paper_venue": link.venue,
        "original_topic_consistency": link.topic_consistency_score,
        "decision": decision,
        "reason": reason,
        "llm_confidence": llm_confidence,
    }
    if signals is not None:
        snapshot["signals"] = {
            "coauthor_overlap": signals.coauthor_overlap,
            "venue_alignment": signals.venue_alignment,
            "year_plausibility": signals.year_plausibility,
            "composite": signals.composite,
            "verdict": signals.verdict,
        }
    severity = "medium" if decision == "demote" else "low"
    description = (
        f"medium-rescan {decision}: {link.title[:60]!r} "
        f"(prof={link.professor_id}, reason={reason})"
    )
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, link_id, stage, severity,
            description, evidence_snapshot, reported_by, resolved
        )
        VALUES (%s, %s::uuid, 'paper_attribution', %s, %s, %s::jsonb, %s, true)
        ON CONFLICT DO NOTHING
        """,
        (
            link.professor_id,
            link.link_id,
            severity,
            description,
            json.dumps(snapshot, ensure_ascii=False),
            _REPORTED_BY,
        ),
    )
    return cursor.rowcount


async def _run_phase_b_for_prof(
    *,
    professor_id: str,
    prof_ctx_row: dict,
    queued_links: list[CandidateLink],
    llm_client,
    llm_model: str,
) -> None:
    """Run LLM batch verification for all ambiguous links under one professor."""
    ctx = ProfessorContext(
        name=prof_ctx_row["canonical_name"],
        institution=prof_ctx_row.get("institution") or "",
        department=None,
        email=None,
        research_directions=prof_ctx_row.get("topics") or [],
    )
    candidates = [
        PaperIdentityCandidate(
            index=i,
            title=link.title,
            authors=[
                a.strip()
                for a in (link.authors_display or "").split(",")
                if a.strip()
            ][:8],
            year=link.year,
            venue=link.venue,
            abstract=link.abstract,
        )
        for i, link in enumerate(queued_links)
    ]
    decisions = await batch_verify_paper_identity(
        professor_context=ctx,
        candidates=candidates,
        llm_client=llm_client,
        llm_model=llm_model,
    )
    for link, dec in zip(queued_links, decisions):
        if dec.error:
            link.final_decision = "error"
            link.decision_reason = f"llm_error: {dec.error[:80]}"
        elif dec.accepted:
            link.final_decision = "keep"
            link.decision_reason = f"llm_keep: conf={dec.confidence:.2f}"
        else:
            link.final_decision = "demote"
            link.decision_reason = f"llm_demote: conf={dec.confidence:.2f}"


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    args = _parse_args()

    _clear_proxy_env()

    dsn = resolve_dsn(args.database_url)
    if _REAL_DB_NAME in dsn and not args.confirm_real_db:
        print(
            "Refusing miroflow_real without --confirm-real-db.",
            file=sys.stderr,
        )
        return 2
    if "miroflow_test_mock" in dsn and os.environ.get("ALLOW_MOCK_BACKFILL") != "1":
        print("ALLOW_MOCK_BACKFILL=1 required.", file=sys.stderr)
        return 3

    # LLM client (only used in phase B)
    llm_client = None
    llm_model = ""
    if not args.phase_a_only:
        llm_settings = resolve_professor_llm_settings(
            profile_name=args.llm_profile, include_profile=True
        )
        from openai import OpenAI  # local import — keeps phase-a-only fast

        base_url = llm_settings["local_llm_base_url"]
        api_key = llm_settings["local_llm_api_key"]
        llm_model = llm_settings["local_llm_model"]
        print(f"[rescan] llm profile={llm_settings['llm_profile']} model={llm_model}")
        llm_client = OpenAI(
            base_url=base_url, api_key=api_key or "EMPTY", timeout=60.0
        )

    stats = RescanStats()
    samples: list[tuple[str, str, SignalScores, str]] = []

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        candidates = _fetch_candidates(
            conn,
            topic_min=args.topic_min,
            topic_max=args.topic_max,
            limit=args.limit,
        )
        print(f"[rescan] candidates fetched: {len(candidates)}")

        prof_ids = sorted({c.professor_id for c in candidates})
        prof_ctx_rows = _load_prof_contexts(conn, professor_ids=prof_ids)
        print(f"[rescan] professor contexts loaded: {len(prof_ctx_rows)}")

        # Exclude candidate papers from their own corpus
        exclude_by_prof: dict[str, list[str]] = defaultdict(list)
        for link in candidates:
            exclude_by_prof[link.professor_id].append(link.paper_id)
        profiles = _load_prof_corpus_profiles(
            conn,
            professor_ids=prof_ids,
            exclude_paper_ids_by_prof=exclude_by_prof,
        )
        print(f"[rescan] corpus profiles loaded: {len(profiles)}")

        # --- Phase A ---
        phase_b_queue_by_prof: dict[str, list[CandidateLink]] = defaultdict(list)
        for i, link in enumerate(candidates, 1):
            stats.examined += 1
            prof_ctx = prof_ctx_rows.get(link.professor_id)
            if not prof_ctx:
                link.final_decision = "error"
                link.decision_reason = "missing_prof_context"
                continue
            link.professor_name = prof_ctx["canonical_name"]
            link.professor_institution = prof_ctx.get("institution") or ""
            link.professor_research_topics = prof_ctx.get("topics") or []
            prof_name_tokens = _tokenize_authors(link.professor_name)
            profile = profiles[link.professor_id]
            sigs = compute_signals(
                paper_authors_display=link.authors_display,
                paper_venue=link.venue,
                paper_year=link.year,
                profile=profile,
                prof_name_tokens=frozenset(prof_name_tokens),
            )
            link.phase_a = sigs
            if sigs.verdict == "keep":
                link.final_decision = "keep"
                link.decision_reason = f"phase_a_keep: comp={sigs.composite:.2f}"
                stats.phase_a_keep += 1
            elif sigs.verdict == "demote":
                link.final_decision = "demote"
                link.decision_reason = f"phase_a_demote: comp={sigs.composite:.2f}"
                stats.phase_a_demote += 1
            else:
                phase_b_queue_by_prof[link.professor_id].append(link)
                stats.phase_b_queued += 1

            if i % _LOG_INTERVAL == 0:
                print(
                    f"[rescan] phase A: {i}/{len(candidates)} "
                    f"(keep={stats.phase_a_keep} demote={stats.phase_a_demote} "
                    f"queued={stats.phase_b_queued})"
                )
            if len(samples) < 10 and sigs.verdict == "demote":
                samples.append(
                    (link.professor_name, link.title[:50], sigs, link.decision_reason)
                )

        # --- Phase B ---
        if not args.phase_a_only and phase_b_queue_by_prof:
            print(
                f"[rescan] phase B: {stats.phase_b_queued} links across "
                f"{len(phase_b_queue_by_prof)} profs"
            )
            processed = 0
            for pid, queued in phase_b_queue_by_prof.items():
                prof_ctx = prof_ctx_rows[pid]
                try:
                    asyncio.run(
                        _run_phase_b_for_prof(
                            professor_id=pid,
                            prof_ctx_row=prof_ctx,
                            queued_links=queued,
                            llm_client=llm_client,
                            llm_model=llm_model,
                        )
                    )
                except Exception as exc:  # pragma: no cover — defensive
                    for link in queued:
                        link.final_decision = "error"
                        link.decision_reason = f"phase_b_error: {exc!s:.80}"
                for link in queued:
                    if link.final_decision == "keep":
                        stats.phase_b_keep += 1
                    elif link.final_decision == "demote":
                        stats.phase_b_demote += 1
                    else:
                        stats.phase_b_error += 1
                processed += len(queued)
                print(
                    f"[rescan] phase B progress: {processed}/{stats.phase_b_queued} "
                    f"(keep={stats.phase_b_keep} demote={stats.phase_b_demote} "
                    f"err={stats.phase_b_error})"
                )

        # --- Apply ---
        if args.apply:
            for link in candidates:
                if link.final_decision == "demote":
                    _demote(conn, link.link_id, reason=link.decision_reason[:200])
                    stats.demotes_applied += 1
                stats.issues_inserted += _file_issue(
                    conn,
                    link=link,
                    signals=link.phase_a,
                    decision=link.final_decision,
                    reason=link.decision_reason,
                )
        else:
            conn.rollback()

    print()
    print("=== medium-consistency rescan summary ===")
    print(f"  examined             : {stats.examined}")
    print(f"  phase A keep         : {stats.phase_a_keep}")
    print(f"  phase A demote       : {stats.phase_a_demote}")
    print(f"  phase B queued       : {stats.phase_b_queued}")
    if not args.phase_a_only:
        print(f"  phase B keep         : {stats.phase_b_keep}")
        print(f"  phase B demote       : {stats.phase_b_demote}")
        print(f"  phase B error        : {stats.phase_b_error}")
    total_demote = stats.phase_a_demote + stats.phase_b_demote
    total_keep = stats.phase_a_keep + stats.phase_b_keep
    print(f"  TOTAL keep           : {total_keep}")
    print(f"  TOTAL demote         : {total_demote}")
    if args.apply:
        print(f"  demotes applied      : {stats.demotes_applied}")
        print(f"  pipeline_issue rows  : {stats.issues_inserted}")
    if samples:
        print("\nsample demotions (Phase A):")
        for name, title, sigs, reason in samples:
            print(
                f"  {name!s:12.12} | {title!r:50s} | "
                f"coauth={sigs.coauthor_overlap:.2f} venue={sigs.venue_alignment:.0f} "
                f"year={sigs.year_plausibility:.0f} comp={sigs.composite:.2f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
