from __future__ import annotations

import json
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

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
