# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.19b — rescue professor_affiliation rows with institution='UNKNOWN_INSTITUTION'.

Some scraper paths wrote 'UNKNOWN_INSTITUTION' when the institution
couldn't be canonicalized. After Round 7.19b extended the alias table
(CUHKSZ/港中深/SUSTech variants etc.), many can now be resolved.

Strategy per row:
  1. Look at the SAME professor's other affiliation rows — if any has
     a non-UNKNOWN institution, try `normalize_institution` on it. If it
     matches a canonical SZ institution, use that.
  2. Look at the professor's primary source_page URL. Domain
     → institution map (sustech.edu.cn → 南方科技大学, cuhk.edu.cn →
     香港中文大学, tsinghua.edu.cn w/ 'sigs' or 'gs' in path → SIGS, etc.).
  3. If ≥ 2 signals AGREE on the same canonical → UPDATE.
     If only 1 signal → file pipeline_issue severity=medium; leave row.
     If 0 signals → file pipeline_issue severity=high.

Safe by default: --dry-run, --apply + --confirm-real-db for writes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from src.data_agents.professor.institution_names import normalize_institution
from src.data_agents.storage.postgres.connection import resolve_dsn


_REAL_DB_NAME = "miroflow_real"
_REPORTED_BY = "round_7_19b_unknown_rescue"
_UNKNOWN = "UNKNOWN_INSTITUTION"

# Domain → canonical institution map (reverse-lookup from source_page URL)
_DOMAIN_TO_INSTITUTION: dict[str, str] = {
    "sustech.edu.cn": "南方科技大学",
    "sztu.edu.cn": "深圳技术大学",
    "siat.ac.cn": "中国科学院深圳先进技术研究院",
    "cuhk.edu.cn": "香港中文大学（深圳）",
    "cuhk-shenzhen.edu.cn": "香港中文大学（深圳）",
    "szu.edu.cn": "深圳大学",
    "hitsz.edu.cn": "哈尔滨工业大学（深圳）",
    "sz.tsinghua.edu.cn": "清华大学深圳国际研究生院",
    "sigs.tsinghua.edu.cn": "清华大学深圳国际研究生院",
    "pku.edu.cn": None,  # ambiguous: 北京大学 (Beijing) vs 北大深研 — need path hint
    "pkusz.edu.cn": "北京大学深圳研究生院",
    "szbl.ac.cn": "深圳理工大学",  # 深圳湾实验室，closely tied
    "suat-sz.edu.cn": "深圳理工大学",
    "szpt.edu.cn": "深圳理工大学",  # 深圳理工大学 (alt. domain)
    "sysusz.cn": "中山大学（深圳）",
    "sysu.edu.cn": None,  # Guangzhou main campus, not SZ
}


@dataclass
class Stats:
    examined: int = 0
    rescued: int = 0
    flagged_single_signal: int = 0
    flagged_zero_signal: int = 0
    applied_updates: int = 0
    issues_inserted: int = 0


@dataclass
class Candidate:
    affiliation_id: str
    professor_id: str
    canonical_name: str
    other_affiliations: list[str] = field(default_factory=list)
    source_page_url: str | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Round 7.19b — rescue UNKNOWN_INSTITUTION affiliations."
    )
    parser.add_argument("--database-url")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-real-db", action="store_true")
    return parser.parse_args()


def _fetch_candidates(conn) -> list[Candidate]:
    rows = conn.execute(
        """
        SELECT pa.affiliation_id::text AS affiliation_id,
               pa.professor_id,
               p.canonical_name,
               sp.url AS source_page_url,
               (SELECT array_agg(pa2.institution)
                  FROM professor_affiliation pa2
                 WHERE pa2.professor_id = pa.professor_id
                   AND pa2.affiliation_id <> pa.affiliation_id
                   AND pa2.institution <> 'UNKNOWN_INSTITUTION') AS other_insts
          FROM professor_affiliation pa
          JOIN professor p ON p.professor_id = pa.professor_id
          LEFT JOIN source_page sp
            ON sp.page_id = p.primary_official_profile_page_id
         WHERE pa.institution = 'UNKNOWN_INSTITUTION'
           AND p.identity_status = 'resolved'
        """
    ).fetchall()
    return [
        Candidate(
            affiliation_id=r["affiliation_id"],
            professor_id=r["professor_id"],
            canonical_name=r["canonical_name"],
            other_affiliations=list(r["other_insts"] or []),
            source_page_url=r["source_page_url"],
        )
        for r in rows
    ]


def _domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).hostname
        if not host:
            return None
        parts = host.split(".")
        return ".".join(parts[-3:]) if len(parts) >= 3 else host
    except ValueError:
        return None


def _vote(candidate: Candidate) -> tuple[str | None, list[str]]:
    """Return (canonical_institution, signal_list) after voting across signals."""
    signals: list[str] = []
    votes: Counter[str] = Counter()

    # Signal 1: other affiliation rows on this professor
    for inst in candidate.other_affiliations:
        canonical = normalize_institution(inst)
        if canonical:
            votes[canonical] += 1
            signals.append(f"other_affiliation:{inst}→{canonical}")

    # Signal 2: source_page URL domain
    host = _domain_from_url(candidate.source_page_url)
    for suffix, canonical in _DOMAIN_TO_INSTITUTION.items():
        if host and canonical and host.endswith(suffix):
            votes[canonical] += 1
            signals.append(f"url_domain:{host}→{canonical}")
            break

    if not votes:
        return None, signals
    winner, winner_count = votes.most_common(1)[0]
    # Require either 2+ agreeing signals or 1 signal with no contradiction
    if winner_count >= 2 or (winner_count == 1 and len(votes) == 1):
        return winner, signals
    return None, signals


def _update_institution(conn, affiliation_id: str, new_institution: str) -> None:
    conn.execute(
        """
        UPDATE professor_affiliation
           SET institution = %s, updated_at = now()
         WHERE affiliation_id = %s::uuid
           AND institution = 'UNKNOWN_INSTITUTION'
        """,
        (new_institution, affiliation_id),
    )


def _file_issue(
    conn,
    candidate: Candidate,
    *,
    severity: str,
    signals: list[str],
    winner: str | None,
) -> int:
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "cleanup_round": "round_7_19b",
        "affiliation_id": candidate.affiliation_id,
        "professor_id": candidate.professor_id,
        "canonical_name": candidate.canonical_name,
        "source_page_url": candidate.source_page_url,
        "other_affiliations": candidate.other_affiliations,
        "signals": signals,
        "proposed_canonical": winner,
    }
    description = (
        f"UNKNOWN_INSTITUTION rescue: prof={candidate.professor_id} "
        f"({candidate.canonical_name!r}); signals={len(signals)}, "
        f"proposed={winner!r}"
    )
    cursor = conn.execute(
        """
        INSERT INTO pipeline_issue (
            professor_id, institution, stage, severity,
            description, evidence_snapshot, reported_by
        )
        VALUES (%s, 'UNKNOWN_INSTITUTION', 'affiliation', %s, %s, %s::jsonb, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            candidate.professor_id,
            severity,
            description,
            json.dumps(snapshot, ensure_ascii=False),
            _REPORTED_BY,
        ),
    )
    return cursor.rowcount


def main() -> int:
    args = _parse_args()

    dsn = resolve_dsn(args.database_url)
    if _REAL_DB_NAME in dsn and not args.confirm_real_db:
        print("Refusing miroflow_real without --confirm-real-db.", file=sys.stderr)
        return 2
    if "miroflow_test_mock" in dsn and os.environ.get("ALLOW_MOCK_BACKFILL") != "1":
        print("ALLOW_MOCK_BACKFILL=1 required.", file=sys.stderr)
        return 3

    stats = Stats()
    samples: list[tuple[str, str, str | None, list[str]]] = []

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        candidates = _fetch_candidates(conn)
        for c in candidates:
            stats.examined += 1
            winner, signals = _vote(c)
            if winner:
                stats.rescued += 1
                samples.append((c.canonical_name, winner, c.source_page_url, signals))
                if args.apply:
                    _update_institution(conn, c.affiliation_id, winner)
                    stats.applied_updates += 1
                    # Still file a low-sev audit trail
                    stats.issues_inserted += _file_issue(
                        conn, c, severity="low", signals=signals, winner=winner
                    )
            elif signals:
                stats.flagged_single_signal += 1
                if args.apply:
                    stats.issues_inserted += _file_issue(
                        conn, c, severity="medium", signals=signals, winner=None
                    )
            else:
                stats.flagged_zero_signal += 1
                if args.apply:
                    stats.issues_inserted += _file_issue(
                        conn, c, severity="high", signals=signals, winner=None
                    )
        if not args.apply:
            conn.rollback()

    print()
    print("=== UNKNOWN_INSTITUTION rescue summary ===")
    print(f"  examined                 : {stats.examined}")
    print(f"  rescued (canonical found): {stats.rescued}")
    print(f"  flagged (1 weak signal)  : {stats.flagged_single_signal}")
    print(f"  flagged (0 signal)       : {stats.flagged_zero_signal}")
    print(f"  apply                    : {args.apply}")
    if args.apply:
        print(f"  UPDATEs applied          : {stats.applied_updates}")
        print(f"  pipeline_issue rows      : {stats.issues_inserted}")
    if samples:
        print("\nsample rescues (prof | → canonical | url | signals):")
        for name, winner, url, signals in samples[:10]:
            url_s = url or "(none)"
            print(f"  {name!s:12.12} | {winner} | {url_s[:40]} | {len(signals)} signals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
