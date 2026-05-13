from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from psycopg import Connection
from psycopg.types.json import Jsonb

from .canonical_writer import upsert_source_page_for_url, write_professor_bundle
from .adapter_resolution import resolve_seed_adapter_name
from .models import (
    EnrichedProfessorProfile,
    MergedProfessorProfileRecord,
    ProfessorRosterSeed,
)
from .pipeline import ProfessorPipelineResult, run_professor_pipeline
from ..storage.postgres.connection import connect
from ..storage.postgres.pipeline_run import close_pipeline_run, open_pipeline_run

_REPORTED_BY = "professor_seed_runner"

AdapterResolver = Callable[[ProfessorRosterSeed], str | None]
PipelineRunner = Callable[[ProfessorRosterSeed, float], ProfessorPipelineResult]
ProfileWriter = Callable[
    [Connection],
    None,
]


@dataclass(frozen=True, slots=True)
class SingleSeedRunResult:
    seed_id: int
    run_id: str | None
    status: str
    items_processed: int
    items_failed: int
    adapter_name: str | None = None
    error: str | None = None


def run_single_seed(
    seed_id: int,
    *,
    dsn: str | None = None,
    run_id: str | None = None,
    timeout: float = 20.0,
    adapter_resolver: AdapterResolver | None = None,
    pipeline_runner: PipelineRunner | None = None,
    profile_writer: Callable[
        [Connection],
        None,
    ]
    | None = None,
) -> SingleSeedRunResult:
    """Run one admin-managed professor seed and persist terminal status."""
    with connect(dsn) as conn:
        opened_run = run_id is None
        if opened_run:
            seed = _load_seed(conn, seed_id)
            run_id = str(
                open_pipeline_run(
                    conn,
                    run_kind="roster_crawl",
                    run_scope={
                        "source": "admin-console",
                        "domain": "professor",
                        "action": "single_seed_run",
                        "seed_id": seed_id,
                        "school": seed.institution,
                        "department": seed.department,
                        "seed_url": seed.roster_url,
                    },
                    triggered_by="professor_seed_runner",
                )
            )
            conn.commit()
        try:
            result = run_single_seed_with_conn(
                conn,
                seed_id=seed_id,
                run_id=run_id,
                timeout=timeout,
                adapter_resolver=adapter_resolver,
                pipeline_runner=pipeline_runner,
                profile_writer=profile_writer,
            )
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise


def run_single_seed_with_conn(
    conn: Connection,
    *,
    seed_id: int,
    run_id: str | None = None,
    timeout: float = 20.0,
    adapter_resolver: AdapterResolver | None = None,
    pipeline_runner: PipelineRunner | None = None,
    profile_writer: Callable[..., None] | None = None,
) -> SingleSeedRunResult:
    seed = _load_seed(conn, seed_id)
    resolved_adapter = (adapter_resolver or _default_adapter_resolver)(seed)
    if resolved_adapter is None:
        _set_seed_terminal_status(conn, seed_id=seed_id, status="adapter_missing")
        _file_pipeline_issue(
            conn,
            seed_id=seed_id,
            seed=seed,
            stage="adapter_missing",
            severity="medium",
            description=(
                "adapter_missing: no registered professor roster adapter for "
                f"{seed.institution} / {seed.department or 'school-wide'}"
            ),
            evidence={
                "seed_id": seed_id,
                "school": seed.institution,
                "department": seed.department,
                "seed_url": seed.roster_url,
                "run_id": str(run_id) if run_id is not None else None,
            },
        )
        if run_id is not None:
            close_pipeline_run(
                conn,
                run_id,
                status="failed",
                items_processed=0,
                items_failed=1,
                error_summary={"error": "adapter_missing", "seed_id": seed_id},
            )
        return SingleSeedRunResult(
            seed_id=seed_id,
            run_id=str(run_id) if run_id is not None else None,
            status="adapter_missing",
            items_processed=0,
            items_failed=1,
            adapter_name=None,
            error="adapter_missing",
        )

    try:
        result = (pipeline_runner or _default_pipeline_runner)(seed, timeout)
        if _has_fatal_discovery_result(result):
            return _mark_failure(
                conn,
                seed_id=seed_id,
                seed=seed,
                run_id=run_id,
                description=_discovery_failure_description(result),
                evidence=_discovery_failure_evidence(result),
                items_processed=0,
                items_failed=1,
            )

        writer = profile_writer or _default_profile_writer
        written = 0
        for profile in result.profiles:
            if profile.error or not (profile.name or "").strip():
                continue
            writer(conn, profile=profile, run_id=run_id)
            written += 1

        if written == 0:
            return _mark_failure(
                conn,
                seed_id=seed_id,
                seed=seed,
                run_id=run_id,
                description="discovery produced no writable professor profiles",
                evidence=_discovery_failure_evidence(result),
                items_processed=0,
                items_failed=1,
            )

        _set_seed_terminal_status(conn, seed_id=seed_id, status="success")
        if run_id is not None:
            close_pipeline_run(
                conn,
                run_id,
                status="succeeded",
                items_processed=written,
                items_failed=0,
            )
        return SingleSeedRunResult(
            seed_id=seed_id,
            run_id=str(run_id) if run_id is not None else None,
            status="success",
            items_processed=written,
            items_failed=0,
            adapter_name=resolved_adapter,
        )
    except Exception as exc:
        return _mark_failure(
            conn,
            seed_id=seed_id,
            seed=seed,
            run_id=run_id,
            description=f"single seed pipeline failed: {type(exc).__name__}: {exc}",
            evidence={"error": str(exc), "error_type": type(exc).__name__},
            items_processed=0,
            items_failed=1,
        )


def _load_seed(conn: Connection, seed_id: int) -> ProfessorRosterSeed:
    row = conn.execute(
        """
        SELECT school, department, seed_url
          FROM professor_seed
         WHERE id = %s
        """,
        (seed_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"professor_seed {seed_id} not found")
    if isinstance(row, dict):
        school = row["school"]
        department = row["department"]
        seed_url = row["seed_url"]
    else:
        school, department, seed_url = row
    return ProfessorRosterSeed(
        institution=school,
        department=department,
        roster_url=seed_url,
    )


def _default_adapter_resolver(seed: ProfessorRosterSeed) -> str | None:
    return resolve_seed_adapter_name(seed)


def _default_pipeline_runner(
    seed: ProfessorRosterSeed,
    timeout: float,
) -> ProfessorPipelineResult:
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as tmp:
        seed_doc = Path(tmp.name)
        tmp.write(
            f"{seed.institution or ''} "
            f"{seed.department or ''} "
            f"{seed.roster_url}\n"
        )
    try:
        return run_professor_pipeline(
            seed_doc,
            timeout=timeout,
            include_external_profiles=False,
            max_workers=4,
        )
    finally:
        seed_doc.unlink(missing_ok=True)


def _default_profile_writer(
    conn: Connection,
    *,
    profile: MergedProfessorProfileRecord,
    run_id: str | None,
) -> None:
    if run_id is None:
        raise ValueError("run_id is required for canonical professor writes")
    enriched = _merged_to_enriched(profile)
    fetched_at = datetime.now(timezone.utc)
    primary_page_id = upsert_source_page_for_url(
        conn,
        url=enriched.profile_url,
        page_role="official_profile",
        owner_scope_kind="professor",
        owner_scope_ref=None,
        fetched_at=fetched_at,
        is_official_source=_is_official_source(enriched.profile_url),
        run_id=run_id,
    )
    if enriched.roster_source and enriched.roster_source != enriched.profile_url:
        upsert_source_page_for_url(
            conn,
            url=enriched.roster_source,
            page_role="roster_seed",
            owner_scope_kind="institution",
            owner_scope_ref=enriched.institution,
            fetched_at=fetched_at,
            is_official_source=_is_official_source(enriched.roster_source),
            run_id=run_id,
        )
    write_professor_bundle(
        conn,
        enriched=enriched,
        paper_staging=None,
        official_profile_page_id=primary_page_id,
        run_id=run_id,
    )


def _merged_to_enriched(
    profile: MergedProfessorProfileRecord,
) -> EnrichedProfessorProfile:
    return EnrichedProfessorProfile(
        name=(profile.name or "").strip(),
        institution=(profile.institution or "").strip(),
        department=profile.department,
        title=profile.title,
        email=profile.email,
        homepage=profile.homepage,
        office=profile.office,
        research_directions=list(profile.research_directions),
        research_directions_source="official_only",
        profile_url=profile.profile_url,
        roster_source=profile.roster_source,
        extraction_status=profile.extraction_status,
        enrichment_source="regex_only",
        evidence_urls=list(profile.evidence),
    )


def _is_official_source(url: str | None) -> bool:
    if not url:
        return False
    hostname = (urlparse(url).hostname or "").lower()
    return hostname.endswith(".edu.cn") or hostname.endswith(".gov.cn") or hostname.endswith(".ac.cn")


def _has_fatal_discovery_result(result: ProfessorPipelineResult) -> bool:
    if result.report.unique_professor_count <= 0:
        return True
    return any(
        status.status == "failed" and status.discovered_professor_count <= 0
        for status in result.source_statuses
    )


def _discovery_failure_description(result: ProfessorPipelineResult) -> str:
    if not result.source_statuses:
        return "discovery failed: no source status returned"
    status = result.source_statuses[0]
    return (
        "discovery failed: "
        f"{status.reason}"
        + (f" ({status.error})" if status.error else "")
    )


def _discovery_failure_evidence(result: ProfessorPipelineResult) -> dict[str, Any]:
    return {
        "source_statuses": [
            {
                "seed_url": status.seed_url,
                "status": status.status,
                "reason": status.reason,
                "error": status.error,
                "visited_urls": status.visited_urls,
                "discovered_professor_count": status.discovered_professor_count,
            }
            for status in result.source_statuses
        ],
        "failed_fetch_urls": list(result.failed_fetch_urls),
        "report": {
            "seed_url_count": result.report.seed_url_count,
            "unique_professor_count": result.report.unique_professor_count,
            "failed_roster_fetch_count": result.report.failed_roster_fetch_count,
            "unresolved_seed_source_count": result.report.unresolved_seed_source_count,
        },
    }


def _mark_failure(
    conn: Connection,
    *,
    seed_id: int,
    seed: ProfessorRosterSeed,
    run_id: str | None,
    description: str,
    evidence: dict[str, Any],
    items_processed: int,
    items_failed: int,
) -> SingleSeedRunResult:
    _set_seed_terminal_status(conn, seed_id=seed_id, status="failure")
    _file_pipeline_issue(
        conn,
        seed_id=seed_id,
        seed=seed,
        stage="discovery",
        severity="high",
        description=description,
        evidence={
            **evidence,
            "seed_id": seed_id,
            "school": seed.institution,
            "department": seed.department,
            "seed_url": seed.roster_url,
            "run_id": str(run_id) if run_id is not None else None,
        },
    )
    if run_id is not None:
        close_pipeline_run(
            conn,
            run_id,
            status="failed",
            items_processed=items_processed,
            items_failed=items_failed,
            error_summary={"message": description, "seed_id": seed_id},
        )
    return SingleSeedRunResult(
        seed_id=seed_id,
        run_id=str(run_id) if run_id is not None else None,
        status="failure",
        items_processed=items_processed,
        items_failed=items_failed,
        error=description,
    )


def _set_seed_terminal_status(
    conn: Connection,
    *,
    seed_id: int,
    status: str,
) -> None:
    conn.execute(
        """
        UPDATE professor_seed
           SET last_run_status = %s,
               last_run_at = now(),
               updated_at = now()
         WHERE id = %s
        """,
        (status, seed_id),
    )


def _file_pipeline_issue(
    conn: Connection,
    *,
    seed_id: int,
    seed: ProfessorRosterSeed,
    stage: str,
    severity: str,
    description: str,
    evidence: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO pipeline_issue (
            institution, stage, severity, description, evidence_snapshot, reported_by
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            seed.institution or f"seed:{seed_id}",
            stage,
            severity,
            description,
            Jsonb(json.loads(json.dumps(evidence, ensure_ascii=False, default=str))),
            _REPORTED_BY,
        ),
    )
