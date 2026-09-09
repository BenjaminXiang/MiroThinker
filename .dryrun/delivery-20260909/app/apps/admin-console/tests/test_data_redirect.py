from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from starlette.datastructures import QueryParams

from backend.api.data import _legacy_data_redirect_url


def test_legacy_professor_list_redirects_to_domain_filters() -> None:
    location = _legacy_data_redirect_url(
        "professors",
        SimpleNamespace(
            query_params=QueryParams(
                {"institution": "清华大学深圳国际研究生院", "page_size": "10"}
            )
        ),
    )

    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert parsed.path == "/api/professor"
    assert query["page_size"] == ["10"]
    assert json.loads(query["filters"][0]) == {
        "institution": "清华大学深圳国际研究生院"
    }


def test_legacy_professor_detail_redirects_to_domain_detail() -> None:
    location = _legacy_data_redirect_url(
        "professors/PROF-123",
        SimpleNamespace(query_params=QueryParams()),
    )

    assert location == "/api/professor/PROF-123"


def test_legacy_facets_redirect_to_domain_filters() -> None:
    location = _legacy_data_redirect_url(
        "facets/industries",
        SimpleNamespace(query_params=QueryParams()),
    )

    assert location == "/api/company/filters/industry"
