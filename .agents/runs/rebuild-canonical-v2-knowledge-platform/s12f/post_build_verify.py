"""Read-only post-build audit for the exact s12f candidate artifacts.

The verifier is deliberately pinned to one disposable PostgreSQL database, one
complete-candidate envelope, and one isolated index root.  It validates the
content-addressed envelope, dogfoods the physical index snapshot against that
envelope, runs release-scoped SELECT-only acceptance queries, and proves the
observable professor-backfill merge/provenance statistics.

It writes a machine-readable JSON report plus a short Markdown summary and
returns non-zero when any acceptance check fails.  It never builds, mutates, or
serves an artifact.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[4]
AGENT_APP = ROOT / "apps/miroflow-agent"
sys.path.insert(0, str(AGENT_APP))

from src.data_agents.canonical_v2 import (  # noqa: E402
    knowledge_build_isolated as build,
)
from src.data_agents.canonical_v2 import (  # noqa: E402
    knowledge_read_isolated as isolated_read,
)
from src.data_agents.canonical_v2.index_projection_isolated import (  # noqa: E402
    open_manifest_verified_index_snapshot,
)


GATE = ROOT / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
EXPECTED_ENVELOPE = GATE / "s12f/complete-candidate-build-envelope.json"
EXPECTED_INDEX_ROOT = Path("/var/tmp/mirothinker-canonical-v2-s12f/index-v1")
DEFAULT_JSON_OUTPUT = Path(__file__).with_name("post-build-verification-s12f.json")
DEFAULT_MARKDOWN_OUTPUT = Path(__file__).with_name("post-build-verification-s12f.md")
DEFAULT_DSN = (
    "postgresql://miroflow@127.0.0.1:55458/miroflow_candidate_s12f_20260801_v1"
)

EXPECTED_RELEASE_ID = "candidate-s12f-20260801-v1"
EXPECTED_RUN_ID = "s12f-build-20260801-v1"
EXPECTED_DATABASE = "miroflow_candidate_s12f_20260801_v1"
EXPECTED_DATABASE_USER = "miroflow"
EXPECTED_DATABASE_HOST = "127.0.0.1"
EXPECTED_DATABASE_PORT = "55458"
EXPECTED_DATABASE_MARKER = (
    "miroflow:destructive-target:v1:disposable:miroflow_candidate_s12f_20260801_v1"
)
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "7908db3925c8450bc93aa9543b9c94b7cf37a4bae8f796cf0cdd007ac77c0f97"
)
EXPECTED_INDEX_MARKER_SHA256 = (
    "e4314c15518980aaa75a0069dce14c3857df43b74705ce600c6741af74d49f51"
)
EXPECTED_INDEX_TARGET_ID = f"index:{EXPECTED_RELEASE_ID}"
EXPECTED_SOURCE_BATCH_IDS = tuple(
    sorted(
        (
            "s12a-released-objects-full-v1",
            "s12c-r7-company-knowledge-v1",
            "s12c-r7-company-workbook-supplement-v1",
            "s12c-r7-paper-identifiers-v1",
            "s12c-r7-patent-identifiers-v1",
            "s12c-r7-professor-company-roles-v1",
            "s12e-professor-backfill-v1",
        )
    )
)
EXPECTED_OBJECT_COUNTS = {
    "company": 1037,
    "paper": 563,
    "patent": 1931,
    "professor": 1428,
}
EXPECTED_RELATIONSHIP_COUNT = 692
EXPECTED_BACKFILL_STATS = {
    "records_seen": 16,
    "records_merged": 16,
    "records_unmatched": 0,
    "fields_merged": 21,
    "fields_kept_existing": 0,
    "fields_unsupported": 31,
    "fields_invalid": 0,
}
EXPECTED_BACKFILL_FIELD_COUNTS = {"department": 6, "email": 9, "title": 6}
BACKFILL_SOURCE_BATCH_ID = "s12e-professor-backfill-v1"
POLLUTION_NAMES = (
    "师资列表",
    "师资介绍",
    "教育经历",
    "相关教师",
    "教师名录",
    "科研成果",
)
INDEX_MARKER_FILENAME = ".canonical-v2-isolated-index-target.json"


class PostBuildAuditError(RuntimeError):
    """The requested audit cannot safely inspect the exact s12f artifacts."""


@dataclass(frozen=True, slots=True)
class Check:
    check_id: str
    ok: bool
    expected: Any
    actual: Any
    detail: str = ""

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def _check(
    checks: list[Check],
    check_id: str,
    *,
    expected: Any,
    actual: Any,
    ok: bool | None = None,
    detail: str = "",
) -> None:
    checks.append(
        Check(
            check_id=check_id,
            ok=(actual == expected if ok is None else ok),
            expected=expected,
            actual=actual,
            detail=detail,
        )
    )


def evaluate_metrics(metrics: Mapping[str, Any]) -> tuple[Check, ...]:
    """Evaluate the stable s12f acceptance matrix over collected observations."""

    checks: list[Check] = []
    database = metrics["database"]
    envelope = metrics["envelope"]
    index = metrics["index"]
    wang = metrics["wang_xueqian"]
    company = metrics["company"]
    pfedgpa = metrics["pfedgpa"]
    patent_dates = metrics["patent_dates"]
    applicant = metrics["patent_has_applicant"]
    backfill = metrics["backfill_merge"]

    _check(
        checks,
        "database.identity",
        expected=EXPECTED_DATABASE,
        actual=database["database_name"],
    )
    _check(
        checks,
        "database.disposable_marker",
        expected=EXPECTED_DATABASE_MARKER,
        actual=database["database_marker"],
    )
    _check(
        checks,
        "database.read_only",
        expected=True,
        actual=database["transaction_read_only"],
    )
    database_release = database["release"]
    _check(
        checks,
        "database.release.release_id",
        expected=EXPECTED_RELEASE_ID,
        actual=database_release["release_id"],
    )
    _check(
        checks,
        "database.release.build_run_id",
        expected=EXPECTED_RUN_ID,
        actual=database_release["build_run_id"],
    )
    _check(
        checks,
        "database.release.state",
        expected="candidate",
        actual=database_release["state"],
    )
    _check(
        checks,
        "database.release.manifest_sha256",
        expected=envelope["manifest_sha256"],
        actual=database_release["manifest_sha256"],
    )
    _check(
        checks,
        "envelope.release_id",
        expected=EXPECTED_RELEASE_ID,
        actual=envelope["release_id"],
    )
    _check(
        checks,
        "envelope.run_id",
        expected=EXPECTED_RUN_ID,
        actual=envelope["run_id"],
    )
    _check(
        checks,
        "envelope.source_manifest_sha256",
        expected=EXPECTED_SOURCE_MANIFEST_SHA256,
        actual=envelope["source_manifest_sha256"],
    )
    _check(
        checks,
        "envelope.source_batch_ids",
        expected=list(EXPECTED_SOURCE_BATCH_IDS),
        actual=envelope["source_batch_ids"],
    )
    _check(
        checks,
        "envelope.object_counts",
        expected=EXPECTED_OBJECT_COUNTS,
        actual=envelope["object_counts"],
    )
    _check(
        checks,
        "database.object_counts",
        expected=EXPECTED_OBJECT_COUNTS,
        actual=database["object_counts"],
    )
    _check(
        checks,
        "envelope.relationship_count",
        expected=EXPECTED_RELATIONSHIP_COUNT,
        actual=envelope["relationship_count"],
    )
    _check(
        checks,
        "database.relationship_count",
        expected=EXPECTED_RELATIONSHIP_COUNT,
        actual=database["relationship_count"],
    )
    verification = envelope["release_verification"]
    _check(
        checks,
        "envelope.release_verification",
        expected={
            "accepted": True,
            "canonical_index_parity": True,
            "missing_points": 0,
            "extra_points": 0,
            "stale_points": 0,
            "cross_release_points": 0,
        },
        actual=verification,
    )
    target = envelope["index_target"]
    _check(
        checks,
        "envelope.index_root",
        expected=str(EXPECTED_INDEX_ROOT),
        actual=target["root"],
    )
    _check(
        checks,
        "envelope.index_target_id",
        expected=EXPECTED_INDEX_TARGET_ID,
        actual=target["target_id"],
    )
    _check(
        checks,
        "envelope.index_release_id",
        expected=EXPECTED_RELEASE_ID,
        actual=target["release_id"],
    )
    _check(
        checks,
        "envelope.index_marker_sha256",
        expected=EXPECTED_INDEX_MARKER_SHA256,
        actual=target["marker_sha256"],
    )
    _check(
        checks,
        "index.root",
        expected=str(EXPECTED_INDEX_ROOT),
        actual=index["root"],
    )
    _check(
        checks,
        "index.marker_sha256",
        expected=EXPECTED_INDEX_MARKER_SHA256,
        actual=index["marker_sha256"],
    )
    _check(
        checks,
        "index.snapshot_matches_envelope",
        expected=True,
        actual=index["snapshot_matches_envelope"],
    )

    _check(
        checks,
        "wang_xueqian.match_count",
        expected=1,
        actual=wang.get("match_count"),
    )
    _check(
        checks,
        "wang_xueqian.canonical_identity_id",
        expected=wang.get("canonical_identity_id"),
        actual=wang.get("canonical_identity_id"),
    )
    _check(
        checks,
        "wang_xueqian.institution",
        expected="清华大学深圳国际研究生院",
        actual=wang.get("institution"),
    )
    _check(
        checks,
        "wang_xueqian.department",
        expected="数据与信息研究院",
        actual=wang.get("department"),
    )
    _check(
        checks,
        "wang_xueqian.title",
        expected="教授、博士生导师",
        actual=wang.get("title"),
    )
    _check(
        checks,
        "wang_xueqian.research_direction_count",
        expected=7,
        actual=wang.get("research_direction_count"),
    )

    _check(checks, "company.total", expected=1037, actual=company["total"])
    for field, baseline in (
        ("industry_nonempty", 1037),
        ("website_nonempty", 625),
        ("key_personnel_nonempty", 851),
    ):
        actual = company[field]
        _check(
            checks,
            f"company.{field}",
            expected={"minimum": baseline},
            actual=actual,
            ok=isinstance(actual, int) and actual >= baseline,
            detail="must not regress below the accepted s12e count",
        )

    _check(
        checks,
        "pfedgpa.match_count",
        expected=1,
        actual=pfedgpa.get("match_count"),
    )
    _check(
        checks,
        "pfedgpa.doi",
        expected="10.1609/aaai.v39i17.33980",
        actual=pfedgpa.get("doi"),
    )
    _check(
        checks,
        "pfedgpa.arxiv_id",
        expected="2409.05701",
        actual=pfedgpa.get("arxiv_id"),
    )

    _check(
        checks,
        "patent_dates.total",
        expected=1931,
        actual=patent_dates["total"],
    )
    _check(
        checks,
        "patent_dates.filing_date_coverage",
        expected=1931,
        actual=patent_dates["filing_date_nonempty"],
    )
    _check(
        checks,
        "patent_dates.publication_date_coverage",
        expected=1931,
        actual=patent_dates["publication_date_nonempty"],
    )

    _check(
        checks,
        "database.patent_has_applicant",
        expected=121,
        actual=applicant["count"],
    )
    _check(
        checks,
        "database.patent_has_applicant_decision_kind",
        expected=["typed"],
        actual=applicant["decision_kinds"],
    )
    _check(
        checks,
        "database.patent_has_applicant_version",
        expected=["canonical-v2-relationship-v1"],
        actual=applicant["relationship_type_versions"],
    )
    _check(
        checks,
        "envelope.patent_has_applicant",
        expected=121,
        actual=envelope["patent_has_applicant"],
    )
    _check(
        checks,
        "professor.pollution",
        expected=0,
        actual=metrics["pollution"]["count"],
    )
    _check(
        checks,
        "professor.reversed_emails",
        expected=0,
        actual=metrics["reversed_emails"]["count"],
    )

    _check(
        checks,
        "professor_backfill.stats",
        expected=EXPECTED_BACKFILL_STATS,
        actual=backfill["stats"],
    )
    _check(
        checks,
        "professor_backfill.field_counts",
        expected=EXPECTED_BACKFILL_FIELD_COUNTS,
        actual=backfill["field_counts"],
    )
    _check(
        checks,
        "professor_backfill.selected_lineage_count",
        expected=21,
        actual=backfill["selected_lineage_count"],
    )
    _check(
        checks,
        "professor_backfill.unselected_assertions",
        expected=[],
        actual=backfill["unselected_assertion_ids"],
    )
    _check(
        checks,
        "professor_backfill.value_mismatches",
        expected=[],
        actual=backfill["value_mismatches"],
    )
    return tuple(checks)


def _normalized_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _require_exact_input_path(path: Path, expected: Path, *, owner: str) -> Path:
    normalized = _normalized_path(path)
    expected_normalized = _normalized_path(expected)
    if normalized != expected_normalized:
        raise PostBuildAuditError(
            f"{owner} must be the pinned s12f path: {expected_normalized}"
        )
    for candidate in (normalized, *normalized.parents):
        if candidate.is_symlink():
            raise PostBuildAuditError(f"{owner} path ancestry contains a symlink")
    return normalized


def _require_exact_dsn(dsn: str) -> None:
    try:
        values = conninfo_to_dict(dsn)
    except Exception as exc:
        raise PostBuildAuditError("database DSN cannot be parsed") from exc
    identity = {
        "user": values.get("user"),
        "host": values.get("host"),
        "hostaddr": values.get("hostaddr"),
        "port": values.get("port", "5432"),
        "dbname": values.get("dbname"),
    }
    if (
        identity["user"] != EXPECTED_DATABASE_USER
        or identity["host"] != EXPECTED_DATABASE_HOST
        or identity["hostaddr"] not in (None, EXPECTED_DATABASE_HOST)
        or identity["port"] != EXPECTED_DATABASE_PORT
        or identity["dbname"] != EXPECTED_DATABASE
    ):
        raise PostBuildAuditError(
            "refusing to connect: DSN is not the pinned s12f user/host/port/database"
        )


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _require_regular_file(path: Path, *, owner: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise PostBuildAuditError(f"{owner} must be an explicit regular file")


def _load_envelope(path: Path) -> tuple[Any, dict[str, Any]]:
    _require_regular_file(path, owner="complete-candidate envelope")
    content = path.read_bytes()
    envelope = build.CompleteCandidateBuildEnvelope.model_validate_json(
        content,
        context={"external_content_addressed": True},
    )
    handoff = envelope.consumer_handoff
    candidate = handoff.candidate
    target = handoff.release_bundle.index_target
    relationship_result = handoff.release_bundle.relationship_projection_result
    if relationship_result is None:
        raise PostBuildAuditError("envelope lacks relationship projection authority")

    metrics = {
        "path": str(path),
        "byte_size": len(content),
        "file_sha256": _sha256_bytes(content),
        "content_sha256": envelope.content_sha256,
        "release_id": candidate.release_id,
        "run_id": candidate.run_id,
        "manifest_sha256": candidate.manifest_sha256,
        "source_manifest_sha256": envelope.receipt.source_manifest_sha256,
        "source_batch_ids": sorted(candidate.source_batch_ids),
        "object_counts": dict(candidate.object_counts),
        "relationship_count": candidate.relationship_count,
        "release_verification": {
            "accepted": handoff.release_verification.accepted,
            "canonical_index_parity": (
                handoff.release_verification.canonical_index_parity
            ),
            "missing_points": handoff.release_verification.missing_points,
            "extra_points": handoff.release_verification.extra_points,
            "stale_points": handoff.release_verification.stale_points,
            "cross_release_points": (handoff.release_verification.cross_release_points),
        },
        "index_target": {
            "root": str(target.root),
            "target_id": target.target_id,
            "release_id": target.release_id,
            "marker_sha256": target.marker_sha256,
        },
        "patent_has_applicant": sum(
            item.relationship_type_id == "patent_has_applicant"
            for item in relationship_result.current_relationships
        ),
    }
    if (
        candidate.release_id != EXPECTED_RELEASE_ID
        or candidate.run_id != EXPECTED_RUN_ID
        or envelope.receipt.source_manifest_sha256 != EXPECTED_SOURCE_MANIFEST_SHA256
        or tuple(sorted(candidate.source_batch_ids)) != EXPECTED_SOURCE_BATCH_IDS
        or _normalized_path(target.root) != _normalized_path(EXPECTED_INDEX_ROOT)
        or target.target_id != EXPECTED_INDEX_TARGET_ID
        or target.release_id != EXPECTED_RELEASE_ID
        or target.marker_sha256 != EXPECTED_INDEX_MARKER_SHA256
    ):
        raise PostBuildAuditError(
            "envelope identity differs from the pinned s12f release/run/source/index"
        )
    return envelope, metrics


def _audit_index(envelope: Any, index_root: Path) -> dict[str, Any]:
    marker_path = index_root / INDEX_MARKER_FILENAME
    _require_regular_file(marker_path, owner="isolated index marker")
    marker_sha256 = _sha256_bytes(marker_path.read_bytes())
    bundle = envelope.consumer_handoff.release_bundle
    snapshot = open_manifest_verified_index_snapshot(
        bundle.index_target,
        expected_embedding_model_id=bundle.index_result.policy_snapshot.embedding_model,
    )
    isolated_read._require_snapshot_matches_bundle(snapshot, bundle)
    return {
        "root": str(index_root),
        "marker_path": str(marker_path),
        "marker_sha256": marker_sha256,
        "snapshot_matches_envelope": True,
        "point_count": len(snapshot.points),
        "lookup_document_count": len(snapshot.lookup_documents),
    }


def _fetchone(
    connection: Any, query: str, params: tuple[Any, ...] = ()
) -> dict[str, Any]:
    row = connection.execute(query, params).fetchone()
    if row is None:
        raise PostBuildAuditError("database audit query returned no row")
    return dict(row)


def _load_database_observations(
    dsn: str, *, release_id: str
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    connection = psycopg.connect(
        dsn,
        options=(
            "-c default_transaction_read_only=on -c timezone=UTC "
            "-c statement_timeout=120000"
        ),
        row_factory=dict_row,
        connect_timeout=10,
    )
    try:
        identity = _fetchone(
            connection,
            "SELECT current_database() AS database_name, "
            "shobj_description(oid, 'pg_database') AS database_marker "
            "FROM pg_database WHERE datname = current_database()",
        )
        read_only = _fetchone(
            connection,
            "SELECT current_setting('transaction_read_only') AS value",
        )["value"]
        if (
            identity["database_name"] != EXPECTED_DATABASE
            or identity["database_marker"] != EXPECTED_DATABASE_MARKER
            or read_only != "on"
        ):
            raise PostBuildAuditError(
                "connected database is not the pinned read-only disposable s12f target"
            )
        release = _fetchone(
            connection,
            "SELECT release_id, build_run_id, state, manifest_sha256 "
            "FROM knowledge.release WHERE release_id = %s",
            (release_id,),
        )

        count_rows = connection.execute(
            "SELECT 'professor' AS domain, count(*)::bigint AS row_count "
            "FROM professor.current_projection WHERE release_id = %s "
            "UNION ALL SELECT 'company', count(*)::bigint "
            "FROM company.current_projection WHERE release_id = %s "
            "UNION ALL SELECT 'paper', count(*)::bigint "
            "FROM paper.current_projection WHERE release_id = %s "
            "UNION ALL SELECT 'patent', count(*)::bigint "
            "FROM patent.current_projection WHERE release_id = %s",
            (release_id, release_id, release_id, release_id),
        ).fetchall()
        object_counts = {
            str(row["domain"]): int(row["row_count"]) for row in count_rows
        }

        company = _fetchone(
            connection,
            "SELECT count(*)::bigint AS total, "
            "count(*) FILTER (WHERE industry IS NOT NULL AND "
            "NULLIF(btrim(industry ->> 'name'), '') IS NOT NULL)::bigint "
            "AS industry_nonempty, "
            "count(*) FILTER (WHERE NULLIF(btrim(website), '') IS NOT NULL)::bigint "
            "AS website_nonempty, "
            "count(*) FILTER (WHERE COALESCE(cardinality(key_personnel), 0) > 0)"
            "::bigint AS key_personnel_nonempty "
            "FROM company.current_projection WHERE release_id = %s",
            (release_id,),
        )

        wang_rows = connection.execute(
            "SELECT canonical_identity_id, name, canonical_name_zh, institution, "
            "department ->> 'name' AS department, title, email, homepage, "
            "jsonb_array_length(research_directions) AS research_direction_count "
            "FROM professor.current_projection WHERE release_id = %s "
            "AND (name = %s OR canonical_name_zh = %s) "
            "ORDER BY canonical_identity_id",
            (release_id, "王学谦", "王学谦"),
        ).fetchall()
        wang = dict(wang_rows[0]) if len(wang_rows) == 1 else {}
        wang["match_count"] = len(wang_rows)
        wang["matches"] = [dict(row) for row in wang_rows]

        paper_rows = connection.execute(
            "SELECT canonical_identity_id, title, doi, arxiv_id "
            "FROM paper.current_projection WHERE release_id = %s "
            "AND title ILIKE %s ORDER BY canonical_identity_id",
            (release_id, "%pFedGPA%"),
        ).fetchall()
        pfedgpa = dict(paper_rows[0]) if len(paper_rows) == 1 else {}
        pfedgpa["match_count"] = len(paper_rows)
        pfedgpa["matches"] = [dict(row) for row in paper_rows]

        patent_dates = _fetchone(
            connection,
            "SELECT count(*)::bigint AS total, "
            "count(filing_date)::bigint AS filing_date_nonempty, "
            "count(publication_date)::bigint AS publication_date_nonempty "
            "FROM patent.current_projection WHERE release_id = %s",
            (release_id,),
        )
        relationship_count = int(
            _fetchone(
                connection,
                "SELECT count(*)::bigint AS count "
                "FROM knowledge.current_relationship_projection "
                "WHERE release_id = %s",
                (release_id,),
            )["count"]
        )
        applicant = _fetchone(
            connection,
            "SELECT count(*)::bigint AS count, "
            "array_agg(DISTINCT decision_kind ORDER BY decision_kind) "
            "AS decision_kinds, "
            "array_agg(DISTINCT relationship_type_version "
            "ORDER BY relationship_type_version) AS relationship_type_versions "
            "FROM knowledge.current_relationship_projection "
            "WHERE release_id = %s AND relationship_type_id = %s",
            (release_id, "patent_has_applicant"),
        )
        applicant["decision_kinds"] = list(applicant["decision_kinds"] or [])
        applicant["relationship_type_versions"] = list(
            applicant["relationship_type_versions"] or []
        )

        pollution_rows = connection.execute(
            "SELECT canonical_identity_id, name, canonical_name_zh "
            "FROM professor.current_projection WHERE release_id = %s "
            "AND (btrim(name) = ANY(%s::text[]) OR "
            "btrim(canonical_name_zh) = ANY(%s::text[])) "
            "ORDER BY canonical_identity_id",
            (release_id, list(POLLUTION_NAMES), list(POLLUTION_NAMES)),
        ).fetchall()
        email_rows = connection.execute(
            "SELECT canonical_identity_id, email "
            "FROM professor.current_projection WHERE release_id = %s "
            "ORDER BY canonical_identity_id",
            (release_id,),
        ).fetchall()
        reversed_rows = [
            {
                "canonical_identity_id": row["canonical_identity_id"],
                "email": row["email"],
                "classification": build._decode_reversed_professor_email(row["email"])[
                    1
                ],
            }
            for row in email_rows
            if build._decode_reversed_professor_email(row["email"])[1] is not None
        ]
        backfill_rows = tuple(
            dict(row)
            for row in connection.execute(
                "SELECT record_id, parse_status, payload "
                "FROM landing.source_record WHERE source_batch_id = %s "
                "ORDER BY record_locator",
                (BACKFILL_SOURCE_BATCH_ID,),
            ).fetchall()
        )
    finally:
        connection.rollback()
        connection.close()

    database = {
        "database_name": identity["database_name"],
        "database_marker": identity["database_marker"],
        "transaction_read_only": read_only == "on",
        "release": release,
        "object_counts": object_counts,
        "relationship_count": relationship_count,
    }
    return (
        {
            "database": database,
            "company": {key: int(value) for key, value in company.items()},
            "wang_xueqian": wang,
            "pfedgpa": pfedgpa,
            "patent_dates": {key: int(value) for key, value in patent_dates.items()},
            "patent_has_applicant": {
                "count": int(applicant["count"]),
                "decision_kinds": applicant["decision_kinds"],
                "relationship_type_versions": applicant["relationship_type_versions"],
            },
            "pollution": {
                "count": len(pollution_rows),
                "rows": [dict(row) for row in pollution_rows],
            },
            "reversed_emails": {
                "count": len(reversed_rows),
                "rows": reversed_rows,
            },
        },
        backfill_rows,
    )


def _unwrapped_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    payload_json = payload.get("payload_json")
    if isinstance(payload_json, str):
        value = json.loads(payload_json)
        return value if isinstance(value, dict) else {}
    return payload


def _audit_backfill(envelope: Any, rows: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    handoff = envelope.consumer_handoff
    candidate_request = handoff.index_projection_request.candidate_projection_request
    internal_request = candidate_request.internal_reference_projection_request
    domain_request = internal_request.public_domain_projection_request
    candidate_result = handoff.index_projection_request.candidate_projection_result

    assignments = {
        assignment.source_identity_id: assignment.canonical_identity_id
        for assignment in domain_request.source_identity_assignments
    }
    professor_projections = {
        projection.canonical_identity_id: projection
        for projection in candidate_result.public_domain_projections
        if projection.entity_type == "professor"
    }
    backfill_record_ids = {str(row["record_id"]) for row in rows}
    merged_assertions = tuple(
        assertion
        for assertion in domain_request.source_assertions
        if assertion.source_record_id in backfill_record_ids
    )
    assertions_by_pair: dict[tuple[str, str], list[Any]] = {}
    for assertion in merged_assertions:
        assertions_by_pair.setdefault(
            (assertion.source_record_id, assertion.field_path), []
        ).append(assertion)

    records_merged: set[str] = set()
    records_unmatched = 0
    fields_merged = 0
    fields_kept_existing = 0
    fields_unsupported = 0
    fields_invalid = 0
    expected_pairs: set[tuple[str, str]] = set()
    value_mismatches: list[str] = []
    parse_status_counts: Counter[str] = Counter()

    for row in rows:
        record_id = str(row["record_id"])
        parse_status = str(row["parse_status"])
        parse_status_counts[parse_status] += 1
        payload = _unwrapped_payload(row["payload"])
        professor_id = payload.get("professor_id")
        fields = payload.get("fields")
        source_identity_id = (
            f"source-released-object:{professor_id}"
            if isinstance(professor_id, str)
            else ""
        )
        canonical_id = assignments.get(source_identity_id)
        projection = professor_projections.get(canonical_id or "")
        raw_name = payload.get("professor_name")
        name_matches = (
            not isinstance(raw_name, str)
            or not raw_name.strip()
            or (
                projection is not None
                and build._identity_lookup_key(raw_name)
                == build._identity_lookup_key(projection.name)
            )
        )
        if (
            parse_status != "parsed"
            or projection is None
            or not name_matches
            or not isinstance(fields, dict)
        ):
            records_unmatched += 1
            continue

        projection_payload = projection.model_dump(mode="json")
        merged_here = False
        for field_name in sorted(fields):
            if field_name not in build._PROFESSOR_BACKFILL_MERGE_FIELDS:
                fields_unsupported += 1
                continue
            spec = fields[field_name]
            observed_at = build._professor_backfill_field_provenance(
                spec, now=domain_request.as_of
            )
            expected_value = (
                build._professor_backfill_projection_value(
                    field_name, spec.get("value")
                )
                if observed_at is not None and isinstance(spec, dict)
                else None
            )
            if observed_at is None or expected_value is None:
                fields_invalid += 1
                continue
            pair = (record_id, field_name)
            expected_pairs.add(pair)
            assertions = assertions_by_pair.get(pair, [])
            if not assertions:
                fields_kept_existing += 1
                continue
            fields_merged += 1
            merged_here = True
            if len(assertions) != 1:
                value_mismatches.append(f"{record_id}:{field_name}:duplicate")
                continue
            assertion = assertions[0]
            if (
                assertion.assertion_id
                != f"assertion:{professor_id}:{field_name}"
                or assertion.value != expected_value
                or assertion.observed_at != observed_at
                or assertion.subject_entity_type != "professor"
                or assertion.source_identity_id != source_identity_id
                or assertion.assertion_run_id != f"assertions:{EXPECTED_RUN_ID}"
                or projection_payload.get(field_name) != expected_value
            ):
                value_mismatches.append(assertion.assertion_id)
        if merged_here:
            records_merged.add(record_id)

    actual_pairs = set(assertions_by_pair)
    for record_id, field_name in sorted(actual_pairs - expected_pairs):
        value_mismatches.append(f"{record_id}:{field_name}:orphan")

    selected_assertion_ids = {
        assertion_id
        for projection in candidate_result.public_domain_projections
        if projection.entity_type == "professor"
        for lineage in projection.field_lineage
        for assertion_id in lineage.supporting_assertion_ids
    }
    merged_assertion_ids = {item.assertion_id for item in merged_assertions}
    unselected = sorted(merged_assertion_ids - selected_assertion_ids)
    stats = {
        "records_seen": len(rows),
        "records_merged": len(records_merged),
        "records_unmatched": records_unmatched,
        "fields_merged": fields_merged,
        "fields_kept_existing": fields_kept_existing,
        "fields_unsupported": fields_unsupported,
        "fields_invalid": fields_invalid,
    }
    return {
        "source_batch_id": BACKFILL_SOURCE_BATCH_ID,
        "parse_status_counts": dict(sorted(parse_status_counts.items())),
        "stats": stats,
        "field_counts": dict(
            sorted(Counter(item.field_path for item in merged_assertions).items())
        ),
        "selected_lineage_count": len(merged_assertion_ids & selected_assertion_ids),
        "unselected_assertion_ids": unselected,
        "value_mismatches": sorted(set(value_mismatches)),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--envelope", type=Path, default=EXPECTED_ENVELOPE)
    parser.add_argument("--index-root", type=Path, default=EXPECTED_INDEX_ROOT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    parser.add_argument(
        "--envelope-identity-only",
        action="store_true",
        help="validate only the pinned envelope identity for the pack preflight",
    )
    return parser


def _render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# S12F post-build verification",
        "",
        f"- Status: **{report['status'].upper()}**",
        f"- Release: `{EXPECTED_RELEASE_ID}`; run: `{EXPECTED_RUN_ID}`",
        f"- Checks: {summary['passed']}/{summary['total']} passed; "
        f"{summary['failed']} failed.",
    ]
    error = report.get("error")
    if error:
        lines.append(f"- Error: `{error['type']}: {error['message']}`")
    metrics = report.get("metrics") or {}
    if metrics:
        company = metrics["company"]
        lines.extend(
            [
                "",
                "## Core observations",
                "",
                "- Objects: `"
                + json.dumps(
                    metrics["database"]["object_counts"],
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "`",
                "- 王学谦 local department: "
                f"`{metrics['wang_xueqian'].get('department')}`",
                "- Company non-empty: "
                f"industry {company['industry_nonempty']}/{company['total']}; "
                f"website {company['website_nonempty']}/{company['total']}; "
                "key_personnel "
                f"{company['key_personnel_nonempty']}/{company['total']}.",
                "- Backfill merge: `"
                + json.dumps(
                    metrics["backfill_merge"]["stats"],
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "`",
            ]
        )
    failed_ids = [item["check_id"] for item in report["checks"] if not item["ok"]]
    lines.extend(
        [
            "",
            "## Failed checks",
            "",
            *(f"- `{check_id}`" for check_id in failed_ids),
        ]
    )
    if not failed_ids:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def _write_reports(
    *, json_path: Path, markdown_path: Path, report: Mapping[str, Any]
) -> None:
    if _normalized_path(json_path) == _normalized_path(markdown_path):
        raise PostBuildAuditError("JSON and Markdown report paths must differ")
    for path in (json_path, markdown_path):
        if not path.parent.is_dir() or path.parent.is_symlink():
            raise PostBuildAuditError(
                f"report parent must be an existing non-symlink directory: {path.parent}"
            )
        if path.is_symlink():
            raise PostBuildAuditError(f"refusing to overwrite symlink report: {path}")
    json_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")


def main(args: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(args)
    if options.envelope_identity_only:
        try:
            envelope_path = _require_exact_input_path(
                options.envelope, EXPECTED_ENVELOPE, owner="envelope"
            )
            _require_exact_input_path(
                options.index_root, EXPECTED_INDEX_ROOT, owner="index root"
            )
            _load_envelope(envelope_path)
        except Exception as exc:
            print(
                f"s12f envelope identity preflight failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 2
        print(
            f"s12f envelope identity verified: release={EXPECTED_RELEASE_ID} "
            f"run={EXPECTED_RUN_ID}",
            flush=True,
        )
        return 0

    generated_at = datetime.now(timezone.utc).isoformat()
    inputs = {
        "database": f"{EXPECTED_DATABASE_HOST}:{EXPECTED_DATABASE_PORT}/{EXPECTED_DATABASE}",
        "envelope": str(_normalized_path(options.envelope)),
        "index_root": str(_normalized_path(options.index_root)),
        "expected_source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "expected_index_marker_sha256": EXPECTED_INDEX_MARKER_SHA256,
    }
    metrics: dict[str, Any] = {}
    checks: tuple[Check, ...] = ()
    error: dict[str, str] | None = None
    status = "error"
    exit_code = 2
    try:
        _require_exact_dsn(options.dsn)
        envelope_path = _require_exact_input_path(
            options.envelope, EXPECTED_ENVELOPE, owner="envelope"
        )
        index_root = _require_exact_input_path(
            options.index_root, EXPECTED_INDEX_ROOT, owner="index root"
        )
        envelope, envelope_metrics = _load_envelope(envelope_path)
        index_metrics = _audit_index(envelope, index_root)
        database_metrics, backfill_rows = _load_database_observations(
            options.dsn, release_id=EXPECTED_RELEASE_ID
        )
        metrics = {
            **database_metrics,
            "envelope": envelope_metrics,
            "index": index_metrics,
            "backfill_merge": _audit_backfill(envelope, backfill_rows),
        }
        checks = evaluate_metrics(metrics)
        status = "pass" if all(check.ok for check in checks) else "fail"
        exit_code = 0 if status == "pass" else 1
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}

    failed = sum(not check.ok for check in checks)
    report: dict[str, Any] = {
        "schema_version": "canonical-v2-s12f-post-build-audit-v1",
        "generated_at": generated_at,
        "status": status,
        "release_id": EXPECTED_RELEASE_ID,
        "run_id": EXPECTED_RUN_ID,
        "inputs": inputs,
        "summary": {
            "total": len(checks),
            "passed": len(checks) - failed,
            "failed": failed,
        },
        "checks": [check.model_dump() for check in checks],
        "metrics": metrics,
    }
    if error is not None:
        report["error"] = error
    try:
        _write_reports(
            json_path=options.json_output,
            markdown_path=options.markdown_output,
            report=report,
        )
    except Exception as exc:
        print(f"post-build audit report write failed: {type(exc).__name__}: {exc}")
        return 2

    print(
        f"status={status} checks={len(checks) - failed}/{len(checks)} "
        f"json={options.json_output} markdown={options.markdown_output}",
        flush=True,
    )
    if error is not None:
        print(f"audit_error={error['type']}: {error['message']}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
