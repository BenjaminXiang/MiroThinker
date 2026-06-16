from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse
from uuid import UUID

import requests
from bs4 import BeautifulSoup
from psycopg import Connection
from psycopg.types.json import Jsonb

from .canonical_writer import upsert_source_page_for_url, write_professor_bundle
from .adapter_resolution import resolve_seed_adapter_name
from .homepage_source_filter import is_homepage_publication_ingest_url
from .models import (
    EnrichedProfessorProfile,
    MergedProfessorProfileRecord,
    ProfessorRosterSeed,
)
from .pipeline import ProfessorPipelineResult, run_professor_pipeline
from .publish_helpers import build_professor_id
from .summary_generator import _build_fallback_profile_summary
from ..storage.postgres.connection import connect
from ..storage.postgres.homepage_recursion_ledger import (
    record_homepage_recursion_processed,
)
from ..storage.postgres.pipeline_run import close_pipeline_run, open_pipeline_run

logger = logging.getLogger(__name__)

_REPORTED_BY = "professor_seed_runner"
_CHINESE_CHAR_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF]")
_HTML_ANCHOR_RE = re.compile(r"<a\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SIAS_CHALLENGE_MARKERS = ("$_ts", "_ts", "token", "wzws", "challenge")
_UESTC_YJSJY_MENTOR_ROSTER_BASE_URL = "https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc"
_UESTC_YJSJY_YXSH_SHENZHEN = "28"
_UESTC_SIAS_ZYDM_BY_PATH = {
    "/rcpy/dsjs1/dzxx2.htm": "085400",
    "/rcpy/dsjs1/jsjjs/jsjjs.htm": "085404",
    "/rcpy/dsjs1/rjgc/rjgc.htm": "085405",
    "/rcpy/dsjs1/jx/gyhlwyznzz.htm": "085500",
}
_UESTC_SIAS_ZYDM_BY_DEPARTMENT = {
    "电子信息": "085400",
    "计算机技术": "085404",
    "软件工程": "085405",
    "机械": "085500",
}
_SOURCE_PAGE_ROLE_PROVENANCE_PREFIX = "source_page_role:"
_OWNED_HOMEPAGE_SOURCE_PAGE_ROLES = frozenset(
    {"official_publication_page", "personal_homepage", "lab_homepage"}
)
_SZU_CSSE_OFFICIAL_SUPPLEMENT_SOURCE_URLS = (
    "https://bigdata.szu.edu.cn/kytd.htm",
    "https://aisc.szu.edu.cn/AISC/Faculty.htm",
    "https://csse.szu.edu.cn/se/team-Staff",
)
_SZU_CSSE_SUPPLEMENT_SOURCE_TIMEOUT = 5.0
_CUHK_TEACHER_SEARCH_SUPPLEMENT_MAX_PAGES = 30
_SEED_PROFILE_ENRICHMENT_MIN_TIMEOUT = 0.5
_SZU_CSSE_SUPPLEMENT_NON_PERSON_LABELS = {
    "About",
    "AISC",
    "Alliances",
    "Careers",
    "Faculty",
    "Graduate student",
    "News",
    "Ph.D student",
    "Projects",
    "Research",
    "Students",
    "博士后",
    "博士生导师",
    "对外合作",
    "副教授",
    "管理团队",
    "国际合作",
    "合作项目",
    "讲师",
    "教授",
    "科研成果",
    "科研技术岗",
    "科研团队",
    "人才培养",
    "硕士生导师",
    "文化建设",
    "新闻资讯",
    "研究方向",
    "研究所概况",
    "招贤纳士",
    "助理教授",
    "专职研究人员",
    "专职研究员",
}
_CUHK_TEACHER_SEARCH_NON_PERSON_TOKENS = (
    "about",
    "career",
    "event",
    "highlight",
    "homepage",
    "introduction",
    "lab",
    "news",
    "research",
    "school",
    "学院",
    "实验室",
    "主页",
    "新闻",
)
_CUHK_PROFILE_FIELD_POLLUTION_MARKERS = (
    "URL Source",
    "Markdown Content",
    "Published Time",
    "教育背景",
    "个人简介",
    "联系方式",
)
TriggerMode = Literal["full", "sample", "preview"]
FailureClass = Literal[
    "adapter_missing",
    "fetch_blocked",
    "parser_low_quality",
    "pipeline_exception",
    "success",
]

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
    failure_class: FailureClass = "success"


def run_single_seed(
    seed_id: int,
    *,
    dsn: str | None = None,
    run_id: str | None = None,
    timeout: float = 20.0,
    trigger_mode: TriggerMode = "full",
    limit: int | None = None,
    adapter_resolver: AdapterResolver | None = None,
    pipeline_runner: PipelineRunner | None = None,
    profile_writer: Callable[
        [Connection],
        None,
    ]
    | None = None,
) -> SingleSeedRunResult:
    """Run one admin-managed professor seed and persist terminal status."""
    _validate_trigger_scope(trigger_mode=trigger_mode, limit=limit)
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
                        "trigger_mode": trigger_mode,
                        "limit": limit,
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
                trigger_mode=trigger_mode,
                limit=limit,
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
    trigger_mode: TriggerMode = "full",
    limit: int | None = None,
    adapter_resolver: AdapterResolver | None = None,
    pipeline_runner: PipelineRunner | None = None,
    profile_writer: Callable[..., None] | None = None,
) -> SingleSeedRunResult:
    _validate_trigger_scope(trigger_mode=trigger_mode, limit=limit)
    run_deadline = _deadline_for_timeout(timeout)
    seed = _load_seed(conn, seed_id)
    fallback_audit_fields: dict[str, Any] | None = None
    if adapter_resolver is None:
        original_seed = seed
        replacement_seed = resolve_uestc_yjsjy_replacement_seed(original_seed)
        if replacement_seed is not None:
            fallback_audit_fields = _uestc_yjsjy_fallback_audit_fields(
                original_seed,
                replacement_seed,
            )
            seed = replacement_seed
    resolved_adapter = (adapter_resolver or _default_adapter_resolver)(seed)
    if resolved_adapter is None:
        fetch_blocked_evidence = _detect_known_fetch_blocked_seed(seed, timeout)
        if fetch_blocked_evidence is not None:
            return _mark_failure(
                conn,
                seed_id=seed_id,
                seed=seed,
                run_id=run_id,
                trigger_mode=trigger_mode,
                limit=limit,
                fallback_audit_fields=fallback_audit_fields,
                failure_class="fetch_blocked",
                description=(
                    "fetch_blocked: "
                    f"{fetch_blocked_evidence.get('response_shape', 'known_blocked_seed')}"
                ),
                evidence=fetch_blocked_evidence,
                items_processed=0,
                items_failed=1,
            )
        _set_seed_terminal_status(conn, seed_id=seed_id, status="adapter_missing")
        _file_pipeline_issue(
            conn,
            seed_id=seed_id,
            seed=seed,
            stage="adapter_missing",
            severity="medium",
            description=_seed_scoped_issue_description(
                seed_id,
                (
                    "adapter_missing: no registered professor roster adapter for "
                    f"{seed.institution} / {seed.department or 'school-wide'}"
                ),
            ),
            evidence={
                "seed_id": seed_id,
                "school": seed.institution,
                "department": seed.department,
                "seed_url": seed.roster_url,
                "run_id": str(run_id) if run_id is not None else None,
                "trigger_mode": trigger_mode,
                "limit": limit,
                "failure_class": "adapter_missing",
            },
        )
        if run_id is not None:
            _merge_pipeline_run_scope(
                conn,
                run_id=run_id,
                trigger_mode=trigger_mode,
                limit=limit,
                failure_class="adapter_missing",
                fallback_audit_fields=fallback_audit_fields,
            )
            close_pipeline_run(
                conn,
                run_id,
                status="failed",
                items_processed=0,
                items_failed=1,
                error_summary={
                    "error": "adapter_missing",
                    "seed_id": seed_id,
                    "failure_class": "adapter_missing",
                },
            )
        return SingleSeedRunResult(
            seed_id=seed_id,
            run_id=str(run_id) if run_id is not None else None,
            status="adapter_missing",
            items_processed=0,
            items_failed=1,
            adapter_name=None,
            error="adapter_missing",
            failure_class="adapter_missing",
        )

    try:
        result = _run_pipeline(
            seed,
            timeout=timeout,
            trigger_mode=trigger_mode,
            limit=limit,
            pipeline_runner=pipeline_runner,
        )
        supplement_profiles: list[MergedProfessorProfileRecord] = []
        if _has_fatal_discovery_result(result):
            supplement_profiles = _collect_szu_csse_official_supplement_profiles(
                seed,
                timeout=_remaining_timeout_or_original(run_deadline, timeout),
            )
            if not supplement_profiles:
                failure_class = _classify_discovery_failure(result)
                return _mark_failure(
                    conn,
                    seed_id=seed_id,
                    seed=seed,
                    run_id=run_id,
                    trigger_mode=trigger_mode,
                    limit=limit,
                    fallback_audit_fields=fallback_audit_fields,
                    failure_class=failure_class,
                    description=_discovery_failure_description(result),
                    evidence=_discovery_failure_evidence(result),
                    items_processed=0,
                    items_failed=1,
                )

        writer = profile_writer or _default_profile_writer
        written = 0
        discovered_profiles = [
            profile
            for profile in [*result.profiles, *supplement_profiles]
            if (profile.name or "").strip()
        ]
        writable_profiles = [
            profile
            for profile in discovered_profiles
            if _profile_matches_seed_scope(seed, profile)
        ]
        writable_profiles = _attach_szu_csse_official_supplement_sources(
            seed,
            writable_profiles,
            timeout=_remaining_timeout_or_original(run_deadline, timeout),
        )
        writable_profiles = _attach_cuhk_teacher_search_roster_supplements(
            seed,
            writable_profiles,
            timeout=_remaining_timeout_or_original(run_deadline, timeout),
        )
        if discovered_profiles and not writable_profiles:
            return _mark_failure(
                conn,
                seed_id=seed_id,
                seed=seed,
                run_id=run_id,
                trigger_mode=trigger_mode,
                limit=limit,
                fallback_audit_fields=fallback_audit_fields,
                failure_class="parser_low_quality",
                description="discovery produced only out-of-scope professor profiles",
                evidence={
                    **_discovery_failure_evidence(result),
                    "rejected_profile_urls": _profile_primary_urls(discovered_profiles),
                    "rejected_profile_evidence_urls": _profile_scope_urls(
                        discovered_profiles
                    ),
                },
                items_processed=0,
                items_failed=1,
            )
        if trigger_mode == "preview":
            _set_seed_terminal_status(conn, seed_id=seed_id, status="success")
            if run_id is not None:
                _merge_pipeline_run_scope(
                    conn,
                    run_id=run_id,
                    trigger_mode=trigger_mode,
                    limit=limit,
                    failure_class="success",
                    diagnostic_profile_count=len(writable_profiles),
                    written_profile_count=0,
                    fallback_audit_fields=fallback_audit_fields,
                )
                close_pipeline_run(
                    conn,
                    run_id,
                    status="succeeded",
                    items_processed=0,
                    items_failed=0,
                )
            return SingleSeedRunResult(
                seed_id=seed_id,
                run_id=str(run_id) if run_id is not None else None,
                status="success",
                items_processed=0,
                items_failed=0,
                adapter_name=resolved_adapter,
                failure_class="success",
            )

        profiles_to_write = writable_profiles
        if trigger_mode == "sample" and limit is not None:
            profiles_to_write = writable_profiles[:limit]
        default_writer_budget = _default_writer_enrichment_budget(
            timeout=timeout,
            profile_count=len(profiles_to_write),
        )
        for profile in profiles_to_write:
            if not (profile.name or "").strip():
                continue
            if profile_writer is None:
                _default_profile_writer(
                    conn,
                    profile=profile,
                    run_id=run_id,
                    enrichment_timeout=_bounded_writer_enrichment_timeout(
                        run_deadline=run_deadline,
                        per_profile_budget=default_writer_budget,
                    ),
                )
            else:
                writer(conn, profile=profile, run_id=run_id)
            written += 1

        if written == 0:
            return _mark_failure(
                conn,
                seed_id=seed_id,
                seed=seed,
                run_id=run_id,
                trigger_mode=trigger_mode,
                limit=limit,
                fallback_audit_fields=fallback_audit_fields,
                failure_class="parser_low_quality",
                description="discovery produced no writable professor profiles",
                evidence=_discovery_failure_evidence(result),
                items_processed=0,
                items_failed=1,
            )

        _set_seed_terminal_status(conn, seed_id=seed_id, status="success")
        if run_id is not None:
            _merge_pipeline_run_scope(
                conn,
                run_id=run_id,
                trigger_mode=trigger_mode,
                limit=limit,
                failure_class="success",
                diagnostic_profile_count=len(writable_profiles),
                written_profile_count=written,
                fallback_audit_fields=fallback_audit_fields,
            )
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
            failure_class="success",
        )
    except Exception as exc:
        return _mark_failure(
            conn,
            seed_id=seed_id,
            seed=seed,
            run_id=run_id,
            trigger_mode=trigger_mode,
            limit=limit,
            fallback_audit_fields=fallback_audit_fields,
            failure_class="pipeline_exception",
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


def _detect_known_fetch_blocked_seed(
    seed: ProfessorRosterSeed,
    timeout: float,
) -> dict[str, Any] | None:
    if not _is_uestc_sias_seed(seed.roster_url):
        return None
    try:
        response = _fetch_direct_no_env(seed.roster_url, timeout=timeout)
    except requests.RequestException as exc:
        return {
            "failure_class": "fetch_blocked",
            "fetch_method": "direct_no_env",
            "transport_error": str(exc),
            "response_shape": "transport_error",
        }
    return _build_sias_fetch_blocked_evidence(
        seed,
        http_status=response.status_code,
        response_body=response.text,
        fetch_method="direct_no_env",
    )


def _is_uestc_sias_seed(seed_url: str) -> bool:
    parsed = urlparse(seed_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname == "sias.uestc.edu.cn" and path.startswith("/rcpy/dsjs1/")


def resolve_uestc_yjsjy_replacement_seed(
    seed: ProfessorRosterSeed,
) -> ProfessorRosterSeed | None:
    if not _is_uestc_sias_seed(seed.roster_url):
        return None
    zydm = _resolve_uestc_yjsjy_program_code(seed)
    if zydm is None:
        return None
    return ProfessorRosterSeed(
        institution=seed.institution,
        department=seed.department,
        roster_url=(
            f"{_UESTC_YJSJY_MENTOR_ROSTER_BASE_URL}"
            f"?yxsh={_UESTC_YJSJY_YXSH_SHENZHEN}&zydm={zydm}"
        ),
        label=seed.label,
    )


def _uestc_yjsjy_fallback_audit_fields(
    original_seed: ProfessorRosterSeed,
    replacement_seed: ProfessorRosterSeed,
) -> dict[str, Any]:
    return {
        "effective_seed_url": replacement_seed.roster_url,
        "effective_department": replacement_seed.department,
        "fallback_adapter": "uestc-yjsjy-mentor-roster",
        "fallback_source_url": original_seed.roster_url,
        "fallback_program_code": _resolve_uestc_yjsjy_program_code(original_seed),
    }


def _resolve_uestc_yjsjy_program_code(seed: ProfessorRosterSeed) -> str | None:
    parsed = urlparse(seed.roster_url)
    path = parsed.path.lower()
    if path in _UESTC_SIAS_ZYDM_BY_PATH:
        return _UESTC_SIAS_ZYDM_BY_PATH[path]
    department = (seed.department or "").strip()
    return _UESTC_SIAS_ZYDM_BY_DEPARTMENT.get(department)


def _fetch_direct_no_env(seed_url: str, *, timeout: float) -> requests.Response:
    with requests.Session() as session:
        session.trust_env = False
        return session.get(
            seed_url,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )


def _fetch_szu_csse_supplement_source_page_no_env(url: str, *, timeout: float) -> str:
    response = _fetch_direct_no_env(url, timeout=timeout)
    response.raise_for_status()
    if _response_declares_utf8(response):
        response.encoding = "utf-8-sig"
    return response.text


def _response_declares_utf8(response: requests.Response) -> bool:
    encoding = (response.encoding or "").lower()
    if encoding not in {"", "iso-8859-1"}:
        return False
    sample = response.content[:2048].lower()
    if (
        sample.startswith(b"\xef\xbb\xbf")
        or b'charset="utf-8"' in sample
        or b"charset=utf-8" in sample
    ):
        return True
    try:
        response.content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _build_sias_fetch_blocked_evidence(
    seed: ProfessorRosterSeed,
    *,
    http_status: int,
    response_body: str,
    fetch_method: str,
    browser_diagnostic: str | None = None,
) -> dict[str, Any] | None:
    if not _is_uestc_sias_seed(seed.roster_url):
        return None
    char_count = len(response_body)
    chinese_char_count = len(_CHINESE_CHAR_RE.findall(response_body))
    anchor_count = len(_HTML_ANCHOR_RE.findall(response_body))
    if not (
        http_status == 202
        and chinese_char_count == 0
        and anchor_count == 0
        and _looks_like_sias_tokenized_challenge(response_body)
    ):
        return None
    evidence: dict[str, Any] = {
        "failure_class": "fetch_blocked",
        "fetch_method": fetch_method,
        "http_status": http_status,
        "response_char_count": char_count,
        "response_chinese_char_count": chinese_char_count,
        "response_anchor_count": anchor_count,
        "response_shape": "tokenized_202_challenge",
    }
    if browser_diagnostic:
        evidence["browser_diagnostic"] = browser_diagnostic
    return evidence


def _looks_like_sias_tokenized_challenge(response_body: str) -> bool:
    lowered = response_body.lower()
    return any(marker in lowered for marker in _SIAS_CHALLENGE_MARKERS)


def _default_pipeline_runner(
    seed: ProfessorRosterSeed,
    timeout: float,
    *,
    max_profile_fetch: int | None = None,
) -> ProfessorPipelineResult:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", encoding="utf-8", delete=False
    ) as tmp:
        seed_doc = Path(tmp.name)
        tmp.write(_render_temp_seed_markdown(seed))
    try:
        return run_professor_pipeline(
            seed_doc,
            timeout=timeout,
            include_external_profiles=False,
            skip_profile_fetch=_should_skip_profile_fetch(seed),
            max_profile_fetch=max_profile_fetch,
            max_workers=4,
        )
    finally:
        seed_doc.unlink(missing_ok=True)


def _render_temp_seed_markdown(seed: ProfessorRosterSeed) -> str:
    lines: list[str] = []
    if seed.institution:
        lines.append(f"## {seed.institution.strip()}")
    if seed.department:
        lines.append(f"### {seed.department.strip()}")
    lines.append(f"- {seed.roster_url}")
    return "\n".join(lines) + "\n"


def _escape_seed_markdown_cell(value: str | None) -> str:
    return (value or "").replace("|", "\\|").strip()


def _default_profile_writer(
    conn: Connection,
    *,
    profile: MergedProfessorProfileRecord,
    run_id: str | None,
    enrichment_timeout: float | None = None,
) -> None:
    if run_id is None:
        raise ValueError("run_id is required for canonical professor writes")
    enriched, paper_staging = _enrich_profile_for_seed_write(
        profile,
        run_id=run_id,
        timeout=enrichment_timeout,
    )
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
    _persist_owned_homepage_recursion_sources(
        conn,
        enriched=enriched,
        parent_source_page_id=primary_page_id,
        fetched_at=fetched_at,
        run_id=run_id,
    )
    write_professor_bundle(
        conn,
        enriched=enriched,
        paper_staging=paper_staging,
        official_profile_page_id=primary_page_id,
        run_id=run_id,
    )


def _persist_owned_homepage_recursion_sources(
    conn: Connection,
    *,
    enriched: EnrichedProfessorProfile,
    parent_source_page_id: UUID,
    fetched_at: datetime,
    run_id: str,
) -> None:
    professor_id = build_professor_id(enriched)
    persisted_urls = {
        (enriched.profile_url or "").strip().rstrip("/"),
        (enriched.roster_source or "").strip().rstrip("/"),
    }
    for url, page_role in _iter_owned_homepage_source_page_roles(enriched):
        normalized_url = url.rstrip("/")
        if not normalized_url or normalized_url in persisted_urls:
            continue
        if not is_homepage_publication_ingest_url(url):
            continue
        source_page_id = upsert_source_page_for_url(
            conn,
            url=url,
            page_role=page_role,
            owner_scope_kind="professor",
            owner_scope_ref=professor_id,
            fetched_at=fetched_at,
            is_official_source=_is_official_source(url),
            run_id=run_id,
        )
        record_homepage_recursion_processed(
            conn,
            run_id=run_id,
            professor_id=professor_id,
            url=url,
            page_role=page_role,
            discovery_source="official_profile_anchor",
            recursion_depth=1,
            parent_source_page_id=parent_source_page_id,
            source_page_id=source_page_id,
        )
        persisted_urls.add(normalized_url)


def _iter_owned_homepage_source_page_roles(
    enriched: EnrichedProfessorProfile,
) -> list[tuple[str, str]]:
    urls_and_roles: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in sorted(enriched.field_provenance.items()):
        if not key.startswith(_SOURCE_PAGE_ROLE_PROVENANCE_PREFIX):
            continue
        url = key.removeprefix(_SOURCE_PAGE_ROLE_PROVENANCE_PREFIX).strip()
        page_role = str(value).strip()
        if page_role not in _OWNED_HOMEPAGE_SOURCE_PAGE_ROLES:
            continue
        normalized_url = url.rstrip("/")
        if not normalized_url or normalized_url in seen:
            continue
        seen.add(normalized_url)
        urls_and_roles.append((url, page_role))
    return urls_and_roles


def _enrich_profile_for_seed_write(
    profile: MergedProfessorProfileRecord,
    *,
    run_id: str,
    timeout: float | None = None,
) -> tuple[EnrichedProfessorProfile, list[Any]]:
    """Run official-chain personal-homepage enrichment before Postgres writes.

    The admin seed path remains synchronous and resilient: if the LLM homepage
    crawl or paper staging step fails, the original official-profile extraction
    is still written and the batch continues.
    """
    enriched = _merged_to_enriched(profile)
    if (
        _llm_homepage_crawl_disabled()
        or (timeout is not None and timeout <= 0)
        or _budgeted_llm_homepage_crawl_disabled(timeout)
    ):
        return enriched, []

    try:
        return asyncio.run(
            _enrich_profile_for_seed_write_async(
                enriched,
                run_id=run_id,
                timeout=timeout,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "LLM homepage enrichment skipped for %s (%s): %s",
            profile.name,
            profile.profile_url,
            exc,
        )
        return enriched, []


def _llm_homepage_crawl_disabled() -> bool:
    value = os.environ.get("PROFESSOR_SEED_ENABLE_LLM_HOMEPAGE_CRAWL", "").strip()
    return value.lower() in {"0", "false", "no", "off"}


def _budgeted_llm_homepage_crawl_disabled(timeout: float | None) -> bool:
    if timeout is None:
        return False
    value = os.environ.get(
        "PROFESSOR_SEED_ENABLE_BOUNDED_LLM_HOMEPAGE_CRAWL",
        "",
    ).strip()
    return value.lower() not in {"1", "true", "yes", "on"}


async def _enrich_profile_for_seed_write_async(
    enriched: EnrichedProfessorProfile,
    *,
    run_id: str,
    timeout: float | None = None,
) -> tuple[EnrichedProfessorProfile, list[Any]]:
    from .discovery import fetch_html_with_fallback
    from .homepage_crawler import crawl_homepage
    from .llm_profiles import resolve_professor_llm_settings
    from .paper_collector import enrich_from_papers
    from .publish_helpers import build_professor_id

    overall_timeout = _optional_enrichment_timeout(timeout)
    enrichment_deadline = (
        time.monotonic() + overall_timeout if overall_timeout is not None else None
    )
    llm_client, llm_model = _build_seed_llm_client(
        resolve_professor_llm_settings,
        timeout_seconds=overall_timeout,
    )
    homepage_timeout = _homepage_enrichment_timeout(overall_timeout)
    fetch_timeout = _fetch_timeout_for_enrichment(homepage_timeout)

    homepage_result = await asyncio.wait_for(
        crawl_homepage(
            profile=enriched,
            fetch_html_fn=lambda url, timeout=fetch_timeout: fetch_html_with_fallback(
                url,
                timeout=timeout,
            ),
            llm_client=llm_client,
            llm_model=llm_model,
            timeout=fetch_timeout,
            run_id=run_id,
        ),
        timeout=homepage_timeout,
    )
    if homepage_result.success:
        enriched = homepage_result.profile

    if not (enriched.official_top_papers or enriched.publication_evidence_urls):
        return enriched, []

    def fetch_html_str(url: str, timeout: float) -> str:
        result = fetch_html_with_fallback(url, timeout=timeout)
        if result.html is not None:
            return result.html
        raise RuntimeError(f"unable to fetch html from {url}")

    remaining_timeout = _remaining_optional_timeout(enrichment_deadline)
    if remaining_timeout is not None and remaining_timeout <= 0:
        return enriched, []
    paper_timeout = _fetch_timeout_for_enrichment(remaining_timeout)
    paper_result = await asyncio.wait_for(
        enrich_from_papers(
            name=enriched.name,
            name_en=enriched.name_en,
            institution=enriched.institution,
            institution_en=None,
            official_directions=enriched.research_directions,
            official_paper_count=enriched.official_paper_count,
            official_top_papers=enriched.official_top_papers,
            official_anchor_profile=enriched.official_anchor_profile,
            publication_evidence_urls=enriched.publication_evidence_urls,
            scholarly_profile_urls=enriched.scholarly_profile_urls,
            cv_urls=enriched.cv_urls,
            professor_id=build_professor_id(enriched),
            homepage_url=enriched.profile_url or enriched.homepage,
            fetch_html=fetch_html_str,
            llm_client=llm_client,
            llm_model=llm_model,
            timeout=paper_timeout,
            identity_gate_enabled=False,
        ),
        timeout=remaining_timeout
        or float(os.environ.get("PROFESSOR_SEED_LLM_HOMEPAGE_TIMEOUT", "180")),
    )
    if paper_result.staging_records:
        enriched = enriched.model_copy(
            update={
                "research_directions": paper_result.research_directions,
                "research_directions_source": paper_result.research_directions_source,
                "h_index": paper_result.h_index,
                "citation_count": paper_result.citation_count,
                "paper_count": paper_result.paper_count,
                "top_papers": paper_result.top_papers,
                "enrichment_source": "paper_enriched",
            }
        )
    return enriched, list(paper_result.staging_records)


def _optional_enrichment_timeout(timeout: float | None) -> float | None:
    if timeout is None:
        return None
    return max(float(timeout), 0.0)


def _homepage_enrichment_timeout(timeout: float | None) -> float:
    configured = float(os.environ.get("PROFESSOR_SEED_LLM_HOMEPAGE_TIMEOUT", "180"))
    if timeout is None:
        return configured
    return max(_SEED_PROFILE_ENRICHMENT_MIN_TIMEOUT, min(configured, timeout))


def _remaining_optional_timeout(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    return max(0.0, deadline - time.monotonic())


def _fetch_timeout_for_enrichment(timeout: float | None) -> float:
    if timeout is None:
        return 20.0
    return max(_SEED_PROFILE_ENRICHMENT_MIN_TIMEOUT, min(20.0, timeout))


def _build_seed_llm_client(
    resolve_settings: Callable[..., dict[str, Any]],
    *,
    timeout_seconds: float | None = None,
) -> tuple[Any, str]:
    import httpx
    from openai import OpenAI

    settings = resolve_settings("gemma4", include_profile=True)
    client_timeout = _llm_client_timeout(timeout_seconds)
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        http_client=httpx.Client(timeout=client_timeout, trust_env=False),
        timeout=client_timeout,
        max_retries=0,
    )
    return client, settings["local_llm_model"]


def _llm_client_timeout(timeout_seconds: float | None) -> float:
    if timeout_seconds is None:
        return 90.0
    return max(_SEED_PROFILE_ENRICHMENT_MIN_TIMEOUT, min(90.0, timeout_seconds))


def _merged_to_enriched(
    profile: MergedProfessorProfileRecord,
) -> EnrichedProfessorProfile:
    enriched = EnrichedProfessorProfile(
        name=(profile.name or "").strip(),
        institution=(profile.institution or "").strip(),
        department=profile.department,
        title=profile.title,
        email=profile.email,
        homepage=profile.homepage,
        office=profile.office,
        research_directions=list(profile.research_directions),
        research_directions_source="official_only",
        education_structured=list(profile.education_structured),
        work_experience=list(profile.work_experience),
        awards=list(profile.awards),
        academic_positions=list(profile.academic_positions),
        profile_raw_text=profile.profile_raw_text,
        profile_url=profile.profile_url,
        roster_source=profile.roster_source,
        extraction_status=profile.extraction_status,
        enrichment_source="regex_only",
        evidence_urls=list(profile.evidence),
    )
    publication_evidence_urls = [
        source_url
        for source_url in _dedupe_texts([*profile.source_urls, *profile.evidence])
        if _is_szu_csse_publication_evidence_source_url(source_url)
    ]
    if publication_evidence_urls:
        enriched = enriched.model_copy(
            update={
                "publication_evidence_urls": publication_evidence_urls,
                "field_provenance": {
                    **enriched.field_provenance,
                    **{
                        f"{_SOURCE_PAGE_ROLE_PROVENANCE_PREFIX}{source_url}": (
                            "official_publication_page"
                        )
                        for source_url in publication_evidence_urls
                    },
                },
            }
        )
    if not enriched.profile_summary.strip():
        enriched.profile_summary = _build_fallback_profile_summary(enriched)
    return enriched


def _is_official_source(url: str | None) -> bool:
    if not url:
        return False
    hostname = (urlparse(url).hostname or "").lower()
    return (
        hostname.endswith(".edu.cn")
        or hostname.endswith(".gov.cn")
        or hostname.endswith(".ac.cn")
    )


def _should_skip_profile_fetch(seed: ProfessorRosterSeed) -> bool:
    del seed
    return False


def _profile_matches_seed_scope(
    seed: ProfessorRosterSeed,
    profile: MergedProfessorProfileRecord,
) -> bool:
    if not _is_szu_csse_seed(seed):
        return True

    if any(_is_szu_csse_profile_url(url) for url in _profile_scope_urls([profile])):
        return True
    return _is_szu_csse_official_supplement_profile(profile)


def _is_szu_csse_official_supplement_profile(
    profile: MergedProfessorProfileRecord,
) -> bool:
    if not _is_szu_csse_official_supplement_source_url(profile.roster_source):
        return False
    if not _is_szu_csse_probable_person_name(profile.name):
        return False
    return any(
        _is_szu_csse_supplement_profile_url(url, profile.roster_source)
        for url in _profile_scope_urls([profile])
    )


def _attach_cuhk_teacher_search_roster_supplements(
    seed: ProfessorRosterSeed,
    profiles: list[MergedProfessorProfileRecord],
    *,
    timeout: float,
    fetch_source_page: Callable[[str, float], str] | None = None,
) -> list[MergedProfessorProfileRecord]:
    if not profiles or not _is_cuhk_teacher_search_seed(seed):
        return profiles
    fetcher = fetch_source_page or _fetch_cuhk_teacher_search_roster_page
    supplements = _collect_cuhk_teacher_search_roster_profiles(
        seed,
        timeout=timeout,
        fetch_source_page=fetcher,
    )
    if not supplements:
        return profiles
    supplement_by_name = {
        _cuhk_person_match_key(supplement.name): supplement
        for supplement in supplements
        if _cuhk_person_match_key(supplement.name)
    }
    return [
        _merge_cuhk_teacher_search_roster_supplement(
            profile,
            supplement_by_name.get(_cuhk_person_match_key(profile.name)),
        )
        for profile in profiles
    ]


def _collect_cuhk_teacher_search_roster_profiles(
    seed: ProfessorRosterSeed,
    *,
    timeout: float,
    fetch_source_page: Callable[[str, float], str],
) -> list[MergedProfessorProfileRecord]:
    if not _is_cuhk_teacher_search_seed(seed):
        return []
    fetch_timeout = _cuhk_teacher_search_roster_fetch_timeout(timeout)
    profiles: list[MergedProfessorProfileRecord] = []
    seen_keys: set[tuple[str, str]] = set()
    for page_index in range(_CUHK_TEACHER_SEARCH_SUPPLEMENT_MAX_PAGES):
        source_url = _cuhk_teacher_search_page_url(seed.roster_url, page_index)
        try:
            html = fetch_source_page(source_url, fetch_timeout)
        except requests.RequestException as exc:
            logger.info(
                "CUHK(SZ) teacher-search supplement fetch failed for %s: %s",
                source_url,
                exc,
            )
            break
        except Exception as exc:  # noqa: BLE001 - supplement pages are optional.
            logger.info(
                "CUHK(SZ) teacher-search supplement skipped for %s: %s",
                source_url,
                exc,
            )
            break
        page_profiles = _extract_cuhk_teacher_search_roster_profiles(
            seed,
            source_url=source_url,
            html=html,
        )
        if not page_profiles:
            break
        new_profiles_found = False
        for profile in page_profiles:
            key = (_cuhk_person_match_key(profile.name), profile.profile_url.casefold())
            if not key[0] or key in seen_keys:
                continue
            seen_keys.add(key)
            profiles.append(profile)
            new_profiles_found = True
        if not new_profiles_found:
            break
    return profiles


def _extract_cuhk_teacher_search_roster_profiles(
    seed: ProfessorRosterSeed,
    *,
    source_url: str,
    html: str,
) -> list[MergedProfessorProfileRecord]:
    if not html or not _is_cuhk_teacher_search_seed(seed):
        return []
    soup = BeautifulSoup(html, "html.parser")
    profiles: list[MergedProfessorProfileRecord] = []
    for card in soup.select(".list-text"):
        title_anchor = card.select_one(".list-title a[href]")
        if title_anchor is None:
            continue
        name = _clean_cuhk_teacher_search_text(title_anchor.get_text(" ", strip=True))
        if not _is_cuhk_teacher_search_probable_person_name(name):
            continue
        raw_profile_url = str(title_anchor.get("href", "")).strip()
        if not raw_profile_url:
            continue
        profile_url = urljoin(source_url, raw_profile_url)
        title = _extract_cuhk_teacher_search_title(card)
        email = _extract_cuhk_teacher_search_email(card)
        research_directions = _extract_cuhk_teacher_search_research_directions(card)
        homepage = (
            _extract_cuhk_teacher_search_homepage(card, source_url) or profile_url
        )
        profile_raw_text = _clean_cuhk_teacher_search_text(
            card.get_text(" ", strip=True)
        )
        urls = _dedupe_texts(
            [
                source_url,
                profile_url,
                homepage if homepage.rstrip("/") != profile_url.rstrip("/") else None,
            ]
        )
        profiles.append(
            MergedProfessorProfileRecord(
                name=name,
                institution=seed.institution or "香港中文大学（深圳）",
                department=seed.department,
                title=title,
                email=email,
                office=None,
                homepage=homepage,
                profile_url=profile_url,
                source_urls=tuple(urls),
                evidence=tuple(urls),
                research_directions=research_directions,
                extraction_status="structured",
                skip_reason=None,
                error=None,
                roster_source=source_url,
                profile_raw_text=profile_raw_text,
            )
        )
    return profiles


def _merge_cuhk_teacher_search_roster_supplement(
    profile: MergedProfessorProfileRecord,
    supplement: MergedProfessorProfileRecord | None,
) -> MergedProfessorProfileRecord:
    if supplement is None:
        return profile
    title = profile.title
    if _cuhk_profile_field_missing_or_polluted(title):
        title = supplement.title
    homepage = profile.homepage
    if supplement.homepage and _cuhk_should_replace_homepage(
        profile.homepage, profile.profile_url
    ):
        homepage = supplement.homepage
    return replace(
        profile,
        title=title,
        email=profile.email or supplement.email,
        homepage=homepage,
        source_urls=tuple(
            _dedupe_texts([*profile.source_urls, *supplement.source_urls])
        ),
        evidence=tuple(_dedupe_texts([*profile.evidence, *supplement.evidence])),
        research_directions=profile.research_directions
        or supplement.research_directions,
        profile_raw_text=profile.profile_raw_text or supplement.profile_raw_text,
    )


def _fetch_cuhk_teacher_search_roster_page(url: str, timeout: float) -> str:
    from .discovery import fetch_html_with_fallback

    result = fetch_html_with_fallback(url, timeout=timeout)
    if result.html is not None:
        return result.html
    raise RuntimeError(
        result.request_error or result.browser_error or "empty CUHK(SZ) roster page"
    )


def _cuhk_teacher_search_roster_fetch_timeout(timeout: float) -> float:
    return max(1.0, min(10.0, timeout))


def _cuhk_teacher_search_page_url(seed_url: str, page_index: int) -> str:
    if page_index == 0:
        return seed_url
    parsed = urlparse(seed_url)
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != "page"
    ]
    query_items.append(("page", str(page_index)))
    return parsed._replace(query=urlencode(query_items)).geturl()


def _is_cuhk_teacher_search_seed(seed: ProfessorRosterSeed) -> bool:
    parsed = urlparse(seed.roster_url)
    hostname = (parsed.hostname or "").lower()
    return hostname.endswith("cuhk.edu.cn") and "teacher-search" in parsed.path.lower()


def _extract_cuhk_teacher_search_title(card: Any) -> str | None:
    for node in card.select(".list-des"):
        text = _clean_cuhk_teacher_search_text(node.get_text(" ", strip=True))
        if _cuhk_teacher_search_title_is_usable(text):
            return text
    return None


def _extract_cuhk_teacher_search_email(card: Any) -> str | None:
    node = card.select_one(".list-email")
    if node is None:
        return None
    match = _EMAIL_RE.search(node.get_text(" ", strip=True))
    return match.group(0).lower() if match else None


def _extract_cuhk_teacher_search_research_directions(card: Any) -> tuple[str, ...]:
    topics: list[str] = []
    for node in card.select(".list-area"):
        label_node = node.find("span")
        label = _clean_cuhk_teacher_search_text(
            label_node.get_text(" ", strip=True) if label_node is not None else ""
        )
        if "研究领域" not in label:
            continue
        text = _clean_cuhk_teacher_search_text(node.get_text(" ", strip=True))
        text = re.sub(r"^研究领域\s*[:：]?\s*", "", text)
        for item in re.split(r"[;；、]", text):
            topic = _clean_cuhk_teacher_search_text(item).strip(" .。；;，,、")
            if topic:
                topics.append(topic)
    return tuple(_dedupe_texts(topics))


def _extract_cuhk_teacher_search_homepage(card: Any, source_url: str) -> str | None:
    for node in card.select(".list-website a[href]"):
        href = str(node.get("href", "")).strip()
        if href:
            return urljoin(source_url, href)
    return None


def _clean_cuhk_teacher_search_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _is_cuhk_teacher_search_probable_person_name(name: str | None) -> bool:
    text = _clean_cuhk_teacher_search_text(name)
    if not text or len(text) > 48:
        return False
    lowered = text.casefold()
    if any(token in lowered for token in _CUHK_TEACHER_SEARCH_NON_PERSON_TOKENS):
        return False
    chinese_chars = _CHINESE_CHAR_RE.findall(text)
    if chinese_chars:
        if text.endswith(("大学", "学院", "实验室", "中心", "研究院", "主页")):
            return False
        return 2 <= len(chinese_chars) <= 4 and len(text) <= 12
    tokens = text.replace("'", "").replace("’", "").replace("-", " ").split()
    if not 2 <= len(tokens) <= 4:
        return False
    return all(re.fullmatch(r"[A-Za-z.]+", token) for token in tokens)


def _cuhk_teacher_search_title_is_usable(value: str | None) -> bool:
    text = _clean_cuhk_teacher_search_text(value)
    if not text or len(text) > 80:
        return False
    lowered = text.casefold()
    if any(token in lowered for token in ("email", "http", "研究领域", "学术领域")):
        return False
    return True


def _cuhk_profile_field_missing_or_polluted(value: str | None) -> bool:
    text = _clean_cuhk_teacher_search_text(value)
    if not text:
        return True
    if len(text) < 2:
        return True
    if re.fullmatch(r"[A-Za-z.]+", text) and text.casefold() not in {
        "professor",
        "lecturer",
    }:
        return True
    if len(text) > 80:
        return True
    return any(marker in text for marker in _CUHK_PROFILE_FIELD_POLLUTION_MARKERS)


def _cuhk_should_replace_homepage(
    homepage: str | None, profile_url: str | None
) -> bool:
    if not homepage:
        return True
    return homepage.rstrip("/") == (profile_url or "").rstrip("/")


def _cuhk_person_match_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[\s\-_.·•,，()（）'’]+", "", value).casefold()


def _attach_szu_csse_official_supplement_sources(
    seed: ProfessorRosterSeed,
    profiles: list[MergedProfessorProfileRecord],
    *,
    timeout: float,
    fetch_source_page: Callable[[str, float], str] | None = None,
) -> list[MergedProfessorProfileRecord]:
    if not profiles or not _is_szu_csse_seed(seed):
        return profiles

    page_html_by_url = _fetch_szu_csse_official_supplement_pages(
        timeout=timeout,
        fetch_source_page=fetch_source_page,
    )
    if not page_html_by_url:
        return profiles

    return [
        _attach_szu_csse_supplement_sources_to_profile(profile, page_html_by_url)
        for profile in profiles
    ]


def _collect_szu_csse_official_supplement_profiles(
    seed: ProfessorRosterSeed,
    *,
    timeout: float,
    fetch_source_page: Callable[[str, float], str] | None = None,
) -> list[MergedProfessorProfileRecord]:
    if not _is_szu_csse_seed(seed):
        return []

    page_html_by_url = _fetch_szu_csse_official_supplement_pages(
        timeout=timeout,
        fetch_source_page=fetch_source_page,
    )
    profiles: list[MergedProfessorProfileRecord] = []
    for source_url, html in page_html_by_url.items():
        profiles.extend(
            _extract_szu_csse_supplement_profiles_from_page(seed, source_url, html)
        )
    return _dedupe_szu_csse_supplement_profiles(profiles)


def _fetch_szu_csse_official_supplement_pages(
    *,
    timeout: float,
    fetch_source_page: Callable[[str, float], str] | None = None,
) -> dict[str, str]:
    page_fetcher = fetch_source_page or (
        lambda url, fetch_timeout: _fetch_szu_csse_supplement_source_page_no_env(
            url,
            timeout=fetch_timeout,
        )
    )
    page_html_by_url: dict[str, str] = {}
    source_timeout = min(max(timeout, 0.0), _SZU_CSSE_SUPPLEMENT_SOURCE_TIMEOUT)
    if source_timeout <= 0:
        return page_html_by_url
    for source_url in _SZU_CSSE_OFFICIAL_SUPPLEMENT_SOURCE_URLS:
        try:
            page_html_by_url[source_url] = page_fetcher(source_url, source_timeout)
        except requests.RequestException as exc:
            logger.info("SZU CSSE supplement fetch failed for %s: %s", source_url, exc)
        except Exception as exc:  # noqa: BLE001 - supplement pages are optional.
            logger.info("SZU CSSE supplement skipped for %s: %s", source_url, exc)
    return page_html_by_url


def _extract_szu_csse_supplement_profiles_from_page(
    seed: ProfessorRosterSeed,
    source_url: str,
    html: str,
) -> list[MergedProfessorProfileRecord]:
    if not html or not _is_szu_csse_official_supplement_source_url(source_url):
        return []
    normalized_source_url = (
        urlparse(source_url)._replace(fragment="").geturl().rstrip("/")
    )
    if normalized_source_url == "https://bigdata.szu.edu.cn/kytd.htm":
        return _extract_szu_bigdata_supplement_profiles(seed, source_url, html)
    if normalized_source_url == "https://aisc.szu.edu.cn/AISC/Faculty.htm":
        return _extract_szu_aisc_supplement_profiles(seed, source_url, html)
    if normalized_source_url == "https://csse.szu.edu.cn/se/team-Staff":
        return _extract_szu_csse_team_staff_supplement_profiles(seed, source_url, html)
    return []


def _extract_szu_bigdata_supplement_profiles(
    seed: ProfessorRosterSeed,
    source_url: str,
    html: str,
) -> list[MergedProfessorProfileRecord]:
    soup = BeautifulSoup(html, "html.parser")
    profiles: list[MergedProfessorProfileRecord] = []
    for card in soup.select(".gbteam1"):
        name_node = card.find(["h3", "h2", "strong"])
        link_node = card.find("a", href=True)
        if name_node is None or link_node is None:
            continue
        name = _clean_szu_csse_supplement_text(name_node.get_text(" ", strip=True))
        profile_url = urljoin(source_url, str(link_node["href"]))
        if not _is_szu_csse_supplement_profile_url(profile_url, source_url):
            continue
        if not _is_szu_csse_probable_person_name(name):
            continue
        research_directions = _extract_szu_bigdata_card_research_directions(card)
        profiles.append(
            _build_szu_csse_supplement_profile(
                seed,
                name=name,
                profile_url=profile_url,
                source_url=source_url,
                research_directions=research_directions,
                profile_raw_text=card.get_text("\n", strip=True),
            )
        )
    return profiles


def _extract_szu_aisc_supplement_profiles(
    seed: ProfessorRosterSeed,
    source_url: str,
    html: str,
) -> list[MergedProfessorProfileRecord]:
    soup = BeautifulSoup(html, "html.parser")
    profiles: list[MergedProfessorProfileRecord] = []
    for link_node in soup.find_all("a", href=True):
        name = _clean_szu_csse_supplement_text(link_node.get_text(" ", strip=True))
        profile_url = urljoin(source_url, str(link_node["href"]))
        if not _is_szu_csse_supplement_profile_url(profile_url, source_url):
            continue
        if not _is_szu_csse_probable_person_name(name):
            continue
        profiles.append(
            _build_szu_csse_supplement_profile(
                seed,
                name=name,
                profile_url=profile_url,
                source_url=source_url,
                research_directions=(),
                profile_raw_text=name,
            )
        )
    return profiles


def _extract_szu_csse_team_staff_supplement_profiles(
    seed: ProfessorRosterSeed,
    source_url: str,
    html: str,
) -> list[MergedProfessorProfileRecord]:
    soup = BeautifulSoup(html, "html.parser")
    profiles: list[MergedProfessorProfileRecord] = []
    for card in soup.select("article, li, .staff-list .item, .staff-list .card"):
        name_node = card.find(["h3", "h2", "strong"])
        link_node = _find_szu_csse_team_staff_profile_link(card)
        if name_node is None or link_node is None:
            continue
        name = _clean_szu_csse_supplement_text(name_node.get_text(" ", strip=True))
        profile_url = urljoin(source_url, str(link_node["href"]))
        if not _is_szu_csse_supplement_profile_url(profile_url, source_url):
            continue
        if not _is_szu_csse_probable_person_name(name):
            continue
        research_directions = _extract_szu_bigdata_card_research_directions(card)
        profiles.append(
            _build_szu_csse_supplement_profile(
                seed,
                name=name,
                profile_url=profile_url,
                source_url=source_url,
                research_directions=research_directions,
                profile_raw_text=card.get_text("\n", strip=True),
            )
        )
    return profiles


def _find_szu_csse_team_staff_profile_link(card: Any) -> Any | None:
    fallback = None
    for link_node in card.find_all("a", href=True):
        href = str(link_node.get("href", "")).strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        label = _clean_szu_csse_supplement_text(link_node.get_text(" ", strip=True))
        label_key = label.casefold()
        if any(token in label_key for token in ("个人主页", "homepage", "personal")):
            return link_node
        if fallback is None and any(
            token in href.casefold() for token in ("/member/", "/people/", "/staff/")
        ):
            fallback = link_node
    return fallback


def _extract_szu_bigdata_card_research_directions(card: Any) -> tuple[str, ...]:
    paragraph = card.find("p")
    if paragraph is None:
        return ()
    text = _clean_szu_csse_supplement_text(paragraph.get_text(" ", strip=True))
    text = re.sub(r"^研究方向\s*[:：]?\s*", "", text)
    return (text,) if text else ()


def _build_szu_csse_supplement_profile(
    seed: ProfessorRosterSeed,
    *,
    name: str,
    profile_url: str,
    source_url: str,
    research_directions: tuple[str, ...],
    profile_raw_text: str | None,
) -> MergedProfessorProfileRecord:
    return MergedProfessorProfileRecord(
        name=name,
        institution=seed.institution or "深圳大学",
        department=seed.department,
        title=None,
        email=None,
        office=None,
        homepage=profile_url,
        profile_url=profile_url,
        source_urls=(source_url, profile_url),
        evidence=(source_url, profile_url),
        research_directions=research_directions,
        extraction_status="structured",
        skip_reason=None,
        error=None,
        roster_source=source_url,
        profile_raw_text=profile_raw_text,
    )


def _dedupe_szu_csse_supplement_profiles(
    profiles: list[MergedProfessorProfileRecord],
) -> list[MergedProfessorProfileRecord]:
    seen: set[tuple[str, str]] = set()
    deduped: list[MergedProfessorProfileRecord] = []
    for profile in profiles:
        key = (_szu_csse_person_match_key(profile.name), profile.profile_url.casefold())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(profile)
    return deduped


def _attach_szu_csse_supplement_sources_to_profile(
    profile: MergedProfessorProfileRecord,
    page_html_by_url: dict[str, str],
) -> MergedProfessorProfileRecord:
    matched_urls: list[str] = []
    for source_url, html in page_html_by_url.items():
        if not _szu_csse_supplement_page_matches_profile(profile, source_url, html):
            continue
        matched_urls.append(source_url)
        matched_urls.extend(
            _discover_szu_csse_supplement_publication_source_urls(source_url, html)
        )
    if not matched_urls:
        return profile
    return replace(
        profile,
        source_urls=tuple(_dedupe_texts([*profile.source_urls, *matched_urls])),
        evidence=tuple(_dedupe_texts([*profile.evidence, *matched_urls])),
    )


def _discover_szu_csse_supplement_publication_source_urls(
    source_url: str,
    html: str,
) -> list[str]:
    if not html or not _is_szu_csse_official_supplement_source_url(source_url):
        return []
    soup = BeautifulSoup(html, "html.parser")
    discovered: list[str] = []
    for link_node in soup.find_all("a", href=True):
        href = str(link_node.get("href", "")).strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        absolute_url = (
            urlparse(urljoin(source_url, href))._replace(fragment="").geturl()
        )
        absolute_url = absolute_url.rstrip("/")
        if not _is_szu_csse_supplement_publication_source_url(absolute_url):
            continue
        discovered.append(absolute_url)
    return _dedupe_texts(discovered)


def _szu_csse_supplement_page_matches_profile(
    profile: MergedProfessorProfileRecord,
    source_url: str,
    html: str,
) -> bool:
    if not _is_szu_csse_official_supplement_source_url(source_url):
        return False
    name_key = _szu_csse_person_match_key(profile.name)
    if not name_key:
        return False
    return name_key in _szu_csse_page_match_key(html)


def _is_szu_csse_official_supplement_source_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if not (hostname == "szu.edu.cn" or hostname.endswith(".szu.edu.cn")):
        return False
    normalized = parsed._replace(fragment="").geturl().rstrip("/")
    return normalized in {
        source_url.rstrip("/")
        for source_url in _SZU_CSSE_OFFICIAL_SUPPLEMENT_SOURCE_URLS
    }


def _is_szu_csse_publication_evidence_source_url(url: str | None) -> bool:
    return _is_szu_csse_official_supplement_source_url(
        url
    ) or _is_szu_csse_supplement_publication_source_url(url)


def _is_szu_csse_supplement_publication_source_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    if hostname == "bigdata.szu.edu.cn":
        return path == "/kycg/lwfb.htm" or bool(
            re.fullmatch(r"/kycg/lwfb/\d+\.htm", path)
        )
    if hostname == "aisc.szu.edu.cn":
        return path == "/kycg.htm" or bool(re.fullmatch(r"/kycg/a20\d{2}\.htm", path))
    return False


def _szu_csse_person_match_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[\s\-_.·•,，()（）]+", "", value).casefold()


def _szu_csse_page_match_key(value: str) -> str:
    return re.sub(r"[\s\-_.·•,，()（）]+", "", value).casefold()


def _clean_szu_csse_supplement_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _is_szu_csse_probable_person_name(name: str | None) -> bool:
    text = _clean_szu_csse_supplement_text(name)
    if not text or len(text) > 48:
        return False
    if text in _SZU_CSSE_SUPPLEMENT_NON_PERSON_LABELS:
        return False
    banned_labels = {
        label.casefold() for label in _SZU_CSSE_SUPPLEMENT_NON_PERSON_LABELS
    }
    if text.casefold() in banned_labels:
        return False
    chinese_chars = _CHINESE_CHAR_RE.findall(text)
    if chinese_chars:
        return len(chinese_chars) in {2, 3, 4} and len(text) <= 8
    tokens = text.replace("'", "").replace("-", " ").split()
    if not 2 <= len(tokens) <= 4:
        return False
    return all(token.isalpha() and len(token) >= 2 for token in tokens)


def _dedupe_texts(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = (value or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _is_szu_csse_seed(seed: ProfessorRosterSeed) -> bool:
    parsed = urlparse(seed.roster_url)
    hostname = (parsed.hostname or "").lower()
    department = seed.department or ""
    return hostname == "csse.szu.edu.cn" and "计算机与软件学院" in department


def _is_szu_csse_profile_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    if hostname != "csse.szu.edu.cn" or path != "/pages/user/index":
        return False
    return any(
        key.lower() == "id" and value.isdigit()
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    )


def _is_szu_csse_supplement_profile_url(
    profile_url: str | None,
    source_url: str,
) -> bool:
    if not profile_url:
        return False
    source_hostname = (urlparse(source_url).hostname or "").lower()
    parsed = urlparse(profile_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if hostname != source_hostname:
        return False
    if source_hostname == "bigdata.szu.edu.cn":
        return re.fullmatch(r"/info/\d+/\d+\.htm", path) is not None
    if source_hostname == "aisc.szu.edu.cn":
        return re.fullmatch(r"/info/1060/\d+\.htm", path) is not None
    if source_hostname == "csse.szu.edu.cn":
        normalized_path = path.lower()
        if not normalized_path.startswith("/se/"):
            return False
        blocked_parts = {"", "se", "index", "team", "team-staff", "news"}
        path_parts = [part for part in normalized_path.split("/") if part]
        if any(part in blocked_parts for part in path_parts[1:]):
            return False
        return any(part in {"member", "people", "staff"} for part in path_parts)
    return False


def _profile_scope_urls(
    profiles: list[MergedProfessorProfileRecord],
) -> list[str]:
    urls: list[str] = []
    for profile in profiles:
        for value in (
            profile.profile_url,
            profile.homepage,
            profile.roster_source,
            *profile.source_urls,
            *profile.evidence,
        ):
            if value and value not in urls:
                urls.append(value)
    return urls


def _profile_primary_urls(
    profiles: list[MergedProfessorProfileRecord],
) -> list[str]:
    urls: list[str] = []
    for profile in profiles:
        for value in (profile.profile_url, profile.homepage):
            if value and value not in urls:
                urls.append(value)
    return urls


def _hostname_matches(url: str, expected_hostname: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname == expected_hostname or hostname.endswith(f".{expected_hostname}")


def _has_fatal_discovery_result(result: ProfessorPipelineResult) -> bool:
    if result.report.unique_professor_count <= 0:
        return True
    return any(
        status.status == "failed" and status.discovered_professor_count <= 0
        for status in result.source_statuses
    )


def _deadline_for_timeout(timeout: float) -> float:
    return time.monotonic() + max(timeout, 0.0)


def _remaining_timeout_or_original(deadline: float, original_timeout: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return _SEED_PROFILE_ENRICHMENT_MIN_TIMEOUT
    return min(original_timeout, remaining)


def _default_writer_enrichment_budget(*, timeout: float, profile_count: int) -> float:
    if profile_count <= 0:
        return max(timeout, _SEED_PROFILE_ENRICHMENT_MIN_TIMEOUT)
    return max(timeout / profile_count, _SEED_PROFILE_ENRICHMENT_MIN_TIMEOUT)


def _bounded_writer_enrichment_timeout(
    *,
    run_deadline: float,
    per_profile_budget: float,
) -> float:
    remaining = run_deadline - time.monotonic()
    if remaining <= 0:
        return 0.0
    return max(
        0.0,
        min(remaining, per_profile_budget),
    )


def _run_pipeline(
    seed: ProfessorRosterSeed,
    *,
    timeout: float,
    trigger_mode: TriggerMode,
    limit: int | None,
    pipeline_runner: PipelineRunner | None,
) -> ProfessorPipelineResult:
    if pipeline_runner is not None:
        return pipeline_runner(seed, timeout)
    max_profile_fetch = limit if trigger_mode in {"sample", "preview"} else None
    return _default_pipeline_runner(
        seed,
        timeout,
        max_profile_fetch=max_profile_fetch,
    )


def _validate_trigger_scope(
    *,
    trigger_mode: TriggerMode,
    limit: int | None,
) -> None:
    if trigger_mode not in {"full", "sample", "preview"}:
        raise ValueError(f"unknown trigger_mode: {trigger_mode}")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    if trigger_mode == "sample" and limit is None:
        raise ValueError("sample mode requires limit")


def _classify_discovery_failure(result: ProfessorPipelineResult) -> FailureClass:
    diagnostic_parts: list[str] = []
    for status in result.source_statuses:
        diagnostic_parts.extend(
            [
                status.status,
                status.reason,
                status.error or "",
            ]
        )
    diagnostic_parts.extend(result.failed_fetch_urls)
    diagnostic_text = " ".join(diagnostic_parts).lower()
    fetch_blocked_tokens = (
        "403",
        "412",
        "waf",
        "javascript",
        "js challenge",
        "browser",
        "connection closed",
        "err_connection_closed",
        "fetch_failed",
        "blocked",
    )
    if result.failed_fetch_urls or any(
        token in diagnostic_text for token in fetch_blocked_tokens
    ):
        return "fetch_blocked"
    return "parser_low_quality"


def _discovery_failure_description(result: ProfessorPipelineResult) -> str:
    if not result.source_statuses:
        return "discovery failed: no source status returned"
    status = result.source_statuses[0]
    return f"discovery failed: {status.reason}" + (
        f" ({status.error})" if status.error else ""
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
    trigger_mode: TriggerMode,
    limit: int | None,
    failure_class: FailureClass,
    description: str,
    evidence: dict[str, Any],
    items_processed: int,
    items_failed: int,
    fallback_audit_fields: dict[str, Any] | None = None,
) -> SingleSeedRunResult:
    _set_seed_terminal_status(conn, seed_id=seed_id, status="failure")
    issue_description = _seed_scoped_issue_description(seed_id, description)
    enriched_evidence = _with_source_remediation_context(
        seed,
        failure_class=failure_class,
        evidence=evidence,
    )
    _file_pipeline_issue(
        conn,
        seed_id=seed_id,
        seed=seed,
        stage="discovery",
        severity="high",
        description=issue_description,
        evidence={
            **enriched_evidence,
            "seed_id": seed_id,
            "school": seed.institution,
            "department": seed.department,
            "seed_url": seed.roster_url,
            "run_id": str(run_id) if run_id is not None else None,
            "trigger_mode": trigger_mode,
            "limit": limit,
            "failure_class": failure_class,
        },
    )
    if run_id is not None:
        _merge_pipeline_run_scope(
            conn,
            run_id=run_id,
            trigger_mode=trigger_mode,
            limit=limit,
            failure_class=failure_class,
            fallback_audit_fields=fallback_audit_fields,
        )
        close_pipeline_run(
            conn,
            run_id,
            status="failed",
            items_processed=items_processed,
            items_failed=items_failed,
            error_summary={
                "message": description,
                "seed_id": seed_id,
                "failure_class": failure_class,
            },
        )
    return SingleSeedRunResult(
        seed_id=seed_id,
        run_id=str(run_id) if run_id is not None else None,
        status="failure",
        items_processed=items_processed,
        items_failed=items_failed,
        error=description,
        failure_class=failure_class,
    )


def _seed_scoped_issue_description(seed_id: int, description: str) -> str:
    return f"{description} [seed_id={seed_id}]"


def _merge_pipeline_run_scope(
    conn: Connection,
    *,
    run_id: str | UUID,
    trigger_mode: TriggerMode,
    limit: int | None,
    failure_class: FailureClass,
    diagnostic_profile_count: int | None = None,
    written_profile_count: int | None = None,
    fallback_audit_fields: dict[str, Any] | None = None,
) -> None:
    patch: dict[str, Any] = {
        "trigger_mode": trigger_mode,
        "limit": limit,
        "failure_class": failure_class,
    }
    if fallback_audit_fields is not None:
        patch.update(fallback_audit_fields)
    if diagnostic_profile_count is not None:
        patch["diagnostic_profile_count"] = diagnostic_profile_count
    if written_profile_count is not None:
        patch["written_profile_count"] = written_profile_count
    conn.execute(
        """
        UPDATE pipeline_run
           SET run_scope = COALESCE(run_scope, '{}'::jsonb) || %s::jsonb
         WHERE run_id = %s
        """,
        (Jsonb(json.loads(json.dumps(patch, ensure_ascii=False, default=str))), run_id),
    )


def _with_source_remediation_context(
    seed: ProfessorRosterSeed,
    *,
    failure_class: FailureClass,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    context = _source_remediation_context(seed, failure_class=failure_class)
    if context is None:
        return evidence
    return {**evidence, "source_remediation": context}


def _source_remediation_context(
    seed: ProfessorRosterSeed,
    *,
    failure_class: FailureClass,
) -> dict[str, Any] | None:
    if failure_class != "fetch_blocked":
        return None
    parsed = urlparse(seed.roster_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    if hostname != "csse.szu.edu.cn" or path != "/pages/teacherteam/index":
        return None
    return {
        "decision": "official_replacement_not_found",
        "original_url": seed.roster_url,
        "accepted_replacement_url": None,
        "rejected_candidates": [
            {
                "url": "https://www.szu.edu.cn/szdw/jsjj.htm",
                "reason": "official_gateway_only_links_to_blocked_csse_url",
            },
            {
                "url": "https://aisc.szu.edu.cn/AISC/Faculty.htm",
                "reason": "official_research_center_roster_not_full_csse_roster",
            },
            {
                "url": "https://hr.szu.edu.cn/",
                "reason": "official_hr_page_without_csse_roster",
            },
        ],
        "operator_action": "provide_or_wait_for_official_full_csse_roster_or_api",
    }


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
    institution = seed.institution or f"seed:{seed_id}"
    evidence_snapshot = Jsonb(
        json.loads(json.dumps(evidence, ensure_ascii=False, default=str))
    )
    existing = conn.execute(
        """
        SELECT issue_id
          FROM pipeline_issue
         WHERE professor_id IS NULL
           AND link_id IS NULL
           AND institution = %s
           AND stage = %s
           AND reported_by = %s
           AND description_hash = md5(%s)
           AND resolved = false
         LIMIT 1
        """,
        (institution, stage, _REPORTED_BY, description),
    ).fetchone()
    if existing is not None:
        issue_id = existing["issue_id"] if isinstance(existing, dict) else existing[0]
        conn.execute(
            """
            UPDATE pipeline_issue
               SET evidence_snapshot = %s,
                   severity = %s,
                   reported_at = now()
             WHERE issue_id = %s
            """,
            (evidence_snapshot, severity, issue_id),
        )
        return

    conn.execute(
        """
        INSERT INTO pipeline_issue (
            institution, stage, severity, description, evidence_snapshot, reported_by
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            institution,
            stage,
            severity,
            description,
            evidence_snapshot,
            _REPORTED_BY,
        ),
    )
