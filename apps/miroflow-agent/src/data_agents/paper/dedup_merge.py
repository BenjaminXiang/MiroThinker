from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from src.data_agents.storage.postgres.paper_merge_alias import (
    PaperMergeAliasInput,
    upsert_paper_merge_alias,
)
from src.data_agents.storage.postgres.pipeline_run import require_real_run_id


def merge_paper_into_canonical(
    conn: Any,
    *,
    old_paper_id: str,
    canonical_paper_id: str,
    run_id: UUID | str,
    merge_reason: str = "exact_title_dedup",
    evidence_source: str = "exact_title+author_list",
    rejected_reason_prefix: str = "merged_into_canonical",
) -> dict[str, int]:
    """Migrate links, write alias, reject old links, then mark old paper merged."""
    old_paper_id = _required_str(old_paper_id, "old_paper_id")
    canonical_paper_id = _required_str(canonical_paper_id, "canonical_paper_id")
    if old_paper_id == canonical_paper_id:
        raise ValueError("old_paper_id must differ from canonical_paper_id")

    real_run_id = require_real_run_id(
        run_id,
        writer_name="merge_paper_into_canonical",
    )
    old_row = _fetch_old_paper(conn, old_paper_id)
    if old_row is None:
        raise ValueError(f"old_paper_id not found: {old_paper_id}")
    if _optional_str(old_row.get("identity_status")) in {"merged", "rejected"}:
        return _empty_counts()

    links_migrated = 0
    for link in _fetch_active_links(conn, old_paper_id):
        links_migrated += _upsert_migrated_link(
            conn,
            link=link,
            old_paper_id=old_paper_id,
            canonical_paper_id=canonical_paper_id,
            run_id=real_run_id,
        )
    merge_aliases_written = _write_merge_alias(
        conn,
        old_paper_id=old_paper_id,
        canonical_paper_id=canonical_paper_id,
        run_id=real_run_id,
        merge_reason=merge_reason,
        evidence_source=evidence_source,
    )
    old_links_rejected = _reject_old_links(
        conn,
        old_paper_id=old_paper_id,
        canonical_paper_id=canonical_paper_id,
        run_id=real_run_id,
        rejected_reason_prefix=rejected_reason_prefix,
    )
    papers_marked_merged = _mark_old_paper_merged(
        conn,
        old_paper_id=old_paper_id,
        canonical_paper_id=canonical_paper_id,
        run_id=real_run_id,
    )
    ready_degraded = (
        papers_marked_merged
        if _optional_str(old_row.get("quality_status")) == "ready"
        else 0
    )
    return {
        "links_migrated": links_migrated,
        "merge_aliases_written": merge_aliases_written,
        "old_links_rejected": old_links_rejected,
        "papers_marked_merged": papers_marked_merged,
        "ready_degraded": ready_degraded,
    }


def flip_paper_canonical(
    conn: Any,
    *,
    old_canonical: str,
    new_canonical: str,
    run_id: UUID | str,
    merge_reason: str = "exact_title_dedup_canonical_correction",
    evidence_source: str = "conf_journal_extension_view_b",
) -> dict[str, int]:
    """Promote a journal canonical and demote the over-merged conference paper."""
    old_canonical = _required_str(old_canonical, "old_canonical")
    new_canonical = _required_str(new_canonical, "new_canonical")
    if old_canonical == new_canonical:
        raise ValueError("old_canonical must differ from new_canonical")

    real_run_id = require_real_run_id(
        run_id,
        writer_name="flip_paper_canonical",
    )
    old_row = _fetch_old_paper(conn, old_canonical)
    if old_row is None:
        raise ValueError(f"old_canonical not found: {old_canonical}")
    if _optional_str(old_row.get("identity_status")) == "merged" and _has_merge_alias(
        conn,
        old_paper_id=old_canonical,
        canonical_paper_id=new_canonical,
    ):
        return _empty_flip_counts()

    aliases_deleted = _delete_wrong_direction_alias(
        conn,
        old_canonical=old_canonical,
        new_canonical=new_canonical,
    )
    aliases_written = _write_flip_merge_alias(
        conn,
        old_canonical=old_canonical,
        new_canonical=new_canonical,
        run_id=real_run_id,
        merge_reason=merge_reason,
        evidence_source=evidence_source,
    )
    papers_promoted = _promote_paper(
        conn,
        paper_id=new_canonical,
        run_id=real_run_id,
    )
    papers_demoted = _demote_paper(
        conn,
        paper_id=old_canonical,
        run_id=real_run_id,
    )
    links_restored = _restore_paper_links(
        conn,
        paper_id=new_canonical,
        run_id=real_run_id,
    )
    links_rejected = _reject_conference_links(
        conn,
        old_canonical=old_canonical,
        new_canonical=new_canonical,
        run_id=real_run_id,
    )
    return {
        "aliases_deleted": aliases_deleted,
        "aliases_written": aliases_written,
        "papers_promoted": papers_promoted,
        "papers_demoted": papers_demoted,
        "links_restored": links_restored,
        "links_rejected": links_rejected,
    }


def _empty_counts() -> dict[str, int]:
    return {
        "links_migrated": 0,
        "merge_aliases_written": 0,
        "old_links_rejected": 0,
        "papers_marked_merged": 0,
        "ready_degraded": 0,
    }


def _empty_flip_counts() -> dict[str, int]:
    return {
        "aliases_deleted": 0,
        "aliases_written": 0,
        "papers_promoted": 0,
        "papers_demoted": 0,
        "links_restored": 0,
        "links_rejected": 0,
    }


def _fetch_old_paper(conn: Any, old_paper_id: str) -> dict[str, Any] | None:
    return conn.execute(
        """
        SELECT paper_id, identity_status, quality_status
          FROM paper
         WHERE paper_id = %s
        """,
        (old_paper_id,),
    ).fetchone()


def _fetch_active_links(conn: Any, old_paper_id: str) -> list[dict[str, Any]]:
    return list(
        conn.execute(
            """
            SELECT link_id,
                   professor_id,
                   paper_id,
                   link_status,
                   evidence_source_type,
                   evidence_page_id,
                   evidence_api_source,
                   match_reason,
                   author_name_match_score,
                   topic_consistency_score,
                   institution_consistency_score,
                   is_officially_listed
              FROM professor_paper_link
             WHERE paper_id = %s
               AND link_status != 'rejected'
             ORDER BY updated_at DESC NULLS LAST, link_id
            """,
            (old_paper_id,),
        ).fetchall()
    )


def _has_merge_alias(
    conn: Any,
    *,
    old_paper_id: str,
    canonical_paper_id: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
          FROM paper_merge_alias
         WHERE old_paper_id = %s
           AND canonical_paper_id = %s
         LIMIT 1
        """,
        (old_paper_id, canonical_paper_id),
    ).fetchone()
    return row is not None


def _delete_wrong_direction_alias(
    conn: Any,
    *,
    old_canonical: str,
    new_canonical: str,
) -> int:
    cursor = conn.execute(
        """
        DELETE FROM paper_merge_alias
         WHERE old_paper_id = %s
           AND canonical_paper_id = %s
           AND merge_reason = 'exact_title_dedup'
        """,
        (new_canonical, old_canonical),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _write_flip_merge_alias(
    conn: Any,
    *,
    old_canonical: str,
    new_canonical: str,
    run_id: UUID | str,
    merge_reason: str,
    evidence_source: str,
) -> int:
    upsert_paper_merge_alias(
        conn,
        PaperMergeAliasInput(
            old_paper_id=old_canonical,
            canonical_paper_id=new_canonical,
            merge_reason=merge_reason,
            evidence_source=evidence_source,
            run_id=require_real_run_id(
                run_id,
                writer_name="flip_paper_canonical",
            ),
        ),
    )
    return 1


def _promote_paper(conn: Any, *, paper_id: str, run_id: UUID | str) -> int:
    cursor = conn.execute(
        """
        UPDATE paper
           SET identity_status = 'confirmed',
               quality_status = 'ready',
               run_id = %s,
               updated_at = now()
         WHERE paper_id = %s
        """,
        (
            require_real_run_id(run_id, writer_name="flip_paper_canonical"),
            paper_id,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _demote_paper(conn: Any, *, paper_id: str, run_id: UUID | str) -> int:
    cursor = conn.execute(
        """
        UPDATE paper
           SET identity_status = 'merged',
               quality_status = 'rejected',
               run_id = %s,
               updated_at = now()
         WHERE paper_id = %s
        """,
        (
            require_real_run_id(run_id, writer_name="flip_paper_canonical"),
            paper_id,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _restore_paper_links(conn: Any, *, paper_id: str, run_id: UUID | str) -> int:
    cursor = conn.execute(
        """
        UPDATE professor_paper_link
           SET link_status = 'verified',
               rejected_at = NULL,
               rejected_reason = NULL,
               run_id = %s,
               updated_at = now()
         WHERE paper_id = %s
           AND link_status = 'rejected'
        """,
        (
            require_real_run_id(run_id, writer_name="flip_paper_canonical"),
            paper_id,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _reject_conference_links(
    conn: Any,
    *,
    old_canonical: str,
    new_canonical: str,
    run_id: UUID | str,
) -> int:
    cursor = conn.execute(
        """
        UPDATE professor_paper_link
           SET link_status = 'rejected',
               rejected_at = now(),
               rejected_reason = %s,
               run_id = %s,
               updated_at = now()
         WHERE paper_id = %s
           AND link_status != 'rejected'
        """,
        (
            f"merged_into_canonical:{new_canonical}",
            require_real_run_id(run_id, writer_name="flip_paper_canonical"),
            old_canonical,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _upsert_migrated_link(
    conn: Any,
    *,
    link: dict[str, Any],
    old_paper_id: str,
    canonical_paper_id: str,
    run_id: UUID | str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO professor_paper_link (
            professor_id,
            paper_id,
            link_status,
            evidence_source_type,
            evidence_page_id,
            evidence_api_source,
            match_reason,
            author_name_match_score,
            topic_consistency_score,
            institution_consistency_score,
            is_officially_listed,
            verified_by,
            verified_at,
            run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'rule_auto', %s, %s)
        ON CONFLICT (professor_id, paper_id) DO UPDATE
           SET link_status                    = EXCLUDED.link_status,
               evidence_source_type           = EXCLUDED.evidence_source_type,
               evidence_page_id               = EXCLUDED.evidence_page_id,
               evidence_api_source            = EXCLUDED.evidence_api_source,
               match_reason                   = EXCLUDED.match_reason,
               author_name_match_score        = EXCLUDED.author_name_match_score,
               topic_consistency_score        = EXCLUDED.topic_consistency_score,
               institution_consistency_score  = EXCLUDED.institution_consistency_score,
               is_officially_listed           = EXCLUDED.is_officially_listed,
               verified_by                    = EXCLUDED.verified_by,
               verified_at                    = EXCLUDED.verified_at,
               run_id                         = COALESCE(EXCLUDED.run_id, professor_paper_link.run_id),
               rejected_at                    = NULL,
               rejected_reason                = NULL,
               updated_at                     = now()
        """,
        (
            _required_str(link.get("professor_id"), "professor_id"),
            canonical_paper_id,
            _optional_str(link.get("link_status")) or "verified",
            _required_str(link.get("evidence_source_type"), "evidence_source_type"),
            _optional_str(link.get("evidence_page_id")),
            _optional_str(link.get("evidence_api_source")),
            _migrated_match_reason(link, old_paper_id),
            _decimal_or_default(link.get("author_name_match_score"), Decimal("0.85")),
            _optional_decimal(link.get("topic_consistency_score")),
            _optional_decimal(link.get("institution_consistency_score")),
            bool(link.get("is_officially_listed", True)),
            datetime.now(timezone.utc),
            require_real_run_id(run_id, writer_name="merge_paper_into_canonical"),
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _migrated_match_reason(link: dict[str, Any], old_paper_id: str) -> str:
    previous_reason = _optional_str(link.get("match_reason"))
    if previous_reason is None:
        previous_reason = "official_homepage_publication"
    return f"{previous_reason}; exact_title_dedup:{old_paper_id}"


def _write_merge_alias(
    conn: Any,
    *,
    old_paper_id: str,
    canonical_paper_id: str,
    run_id: UUID | str,
    merge_reason: str,
    evidence_source: str,
) -> int:
    upsert_paper_merge_alias(
        conn,
        PaperMergeAliasInput(
            old_paper_id=old_paper_id,
            canonical_paper_id=canonical_paper_id,
            merge_reason=merge_reason,
            evidence_source=evidence_source,
            run_id=require_real_run_id(
                run_id,
                writer_name="merge_paper_into_canonical",
            ),
        ),
    )
    return 1


def _reject_old_links(
    conn: Any,
    *,
    old_paper_id: str,
    canonical_paper_id: str,
    run_id: UUID | str,
    rejected_reason_prefix: str,
) -> int:
    cursor = conn.execute(
        """
        UPDATE professor_paper_link
           SET link_status = 'rejected',
               rejected_at = now(),
               rejected_reason = %s,
               run_id = %s,
               updated_at = now()
         WHERE paper_id = %s
           AND link_status != 'rejected'
        """,
        (
            f"{rejected_reason_prefix}:{canonical_paper_id}",
            require_real_run_id(run_id, writer_name="merge_paper_into_canonical"),
            old_paper_id,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _mark_old_paper_merged(
    conn: Any,
    *,
    old_paper_id: str,
    canonical_paper_id: str,
    run_id: UUID | str,
) -> int:
    cursor = conn.execute(
        """
        UPDATE paper
           SET identity_status = 'merged',
               quality_status = 'rejected',
               run_id = %s,
               updated_at = now()
         WHERE paper_id = %s
           AND paper_id != %s
        """,
        (
            require_real_run_id(run_id, writer_name="merge_paper_into_canonical"),
            old_paper_id,
            canonical_paper_id,
        ),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def _required_str(value: object, field_name: str) -> str:
    text = _optional_str(value)
    if text is None:
        raise ValueError(f"{field_name} is required")
    return text


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decimal_or_default(value: object, default: Decimal) -> Decimal:
    parsed = _optional_decimal(value)
    return parsed if parsed is not None else default


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None
