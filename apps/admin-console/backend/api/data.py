from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from backend.deps import get_pg_conn

router = APIRouter(prefix="/api/data")

_DOMAIN_ALIASES = {
    "professors": "professor",
    "companies": "company",
    "papers": "paper",
    "patents": "patent",
}

_LIST_FILTER_PARAMS = {
    "professors": {"institution", "department", "title", "discipline_family"},
    "companies": {"industry", "hq_city", "is_shenzhen"},
    "papers": {"year", "venue"},
    "patents": {"patent_type"},
}

_PASSTHROUGH_QUERY_PARAMS = {
    "q",
    "page",
    "page_size",
    "sort_by",
    "sort_order",
    "filters",
}

_FACET_REDIRECTS = {
    "professor-institutions": "/api/professor/filters/institution",
    "research-topics": "/api/professor/filters/research_topic",
    "industries": "/api/company/filters/industry",
}


@router.get("/facets/industries", include_in_schema=False)
def legacy_industry_facets(conn: Any = Depends(get_pg_conn)) -> list[dict[str, Any]]:
    return _legacy_fetchall(
        conn,
        """
        SELECT latest_snapshot.industry AS industry,
               count(*)::int AS count
          FROM company c
          JOIN LATERAL (
            SELECT cs.industry
              FROM company_snapshot cs
             WHERE cs.company_id = c.company_id
               AND cs.industry IS NOT NULL
               AND cs.industry != ''
             ORDER BY cs.snapshot_created_at DESC NULLS LAST, cs.snapshot_id DESC
             LIMIT 1
          ) latest_snapshot ON TRUE
         WHERE c.identity_status != 'inactive'
         GROUP BY latest_snapshot.industry
         ORDER BY count DESC, latest_snapshot.industry ASC
         LIMIT 100
        """,
    )


@router.get("/facets/professor-institutions", include_in_schema=False)
def legacy_professor_institution_facets(
    conn: Any = Depends(get_pg_conn),
) -> list[dict[str, Any]]:
    return _legacy_fetchall(
        conn,
        """
        SELECT pa.institution AS institution,
               count(DISTINCT p.professor_id)::int AS count
          FROM professor p
          JOIN professor_affiliation pa ON pa.professor_id = p.professor_id
         WHERE p.identity_status = 'resolved'
           AND pa.institution IS NOT NULL
           AND pa.institution != ''
         GROUP BY pa.institution
         ORDER BY count DESC, pa.institution ASC
         LIMIT 100
        """,
    )


@router.get("/facets/research-topics", include_in_schema=False)
def legacy_research_topic_facets(
    conn: Any = Depends(get_pg_conn),
) -> list[dict[str, Any]]:
    return _legacy_fetchall(
        conn,
        """
        SELECT pf.value_raw AS topic,
               count(DISTINCT pf.professor_id)::int AS count
          FROM professor_fact pf
          JOIN professor p ON p.professor_id = pf.professor_id
         WHERE p.identity_status = 'resolved'
           AND pf.fact_type = 'research_topic'
           AND pf.status = 'active'
           AND pf.value_raw IS NOT NULL
           AND pf.value_raw != ''
         GROUP BY pf.value_raw
         ORDER BY count DESC, pf.value_raw ASC
         LIMIT 100
        """,
    )


def _legacy_fetchall(conn: Any, query: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query).fetchall()]


@router.api_route(
    "/{legacy_path:path}",
    methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
def redirect_legacy_data_route(
    legacy_path: str,
    request: Request,
) -> RedirectResponse:
    return RedirectResponse(
        url=_legacy_data_redirect_url(legacy_path, request),
        status_code=301,
    )


def _legacy_data_redirect_url(legacy_path: str, request: Request) -> str:
    parts = [part for part in legacy_path.split("/") if part]
    if len(parts) == 2 and parts[0] == "facets" and parts[1] in _FACET_REDIRECTS:
        return _append_query(_FACET_REDIRECTS[parts[1]], request.query_params)

    if not parts or parts[0] not in _DOMAIN_ALIASES:
        return _append_query("/api", request.query_params)

    plural_domain = parts[0]
    domain = _DOMAIN_ALIASES[plural_domain]
    target = f"/api/{domain}"
    if len(parts) > 1:
        target += "/" + "/".join(parts[1:])

    return _append_query(
        target,
        _rewrite_list_query(plural_domain, request.query_params),
    )


def _rewrite_list_query(plural_domain: str, query_params) -> dict[str, str]:
    rewritten: dict[str, str] = {}
    filters: dict[str, str] = {}
    filter_params = _LIST_FILTER_PARAMS[plural_domain]

    for key, value in query_params.multi_items():
        if key in _PASSTHROUGH_QUERY_PARAMS:
            rewritten[key] = value
        elif key in filter_params:
            filters[key] = value
        elif plural_domain == "patents" and key == "applicant":
            rewritten["q"] = value

    if filters and "filters" not in rewritten:
        rewritten["filters"] = json.dumps(filters, ensure_ascii=False)
    return rewritten


def _append_query(path: str, query_params) -> str:
    params = (
        query_params
        if isinstance(query_params, dict)
        else dict(query_params.multi_items())
    )
    if not params:
        return path
    return f"{path}?{urlencode(params)}"
