from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import TypeVar

DEFAULT_CROSSREF_USER_AGENT = "MiroThinkerDataAgent/0.1"
CROSSREF_MAILTO_ENV_NAMES = (
    "CROSSREF_MAILTO",
    "SCHOLARLY_API_CONTACT_EMAIL",
    "UNPAYWALL_EMAIL",
    "OPENALEX_EMAIL",
    "OPENALEX_MAILTO",
)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ParamValue = TypeVar("_ParamValue", str, int)


def crossref_mailto() -> str | None:
    for env_name in CROSSREF_MAILTO_ENV_NAMES:
        value = os.getenv(env_name, "").strip()
        if value and _EMAIL_RE.match(value):
            return value
    return None


def crossref_user_agent() -> str:
    configured = os.getenv("CROSSREF_USER_AGENT", "").strip()
    if configured:
        return configured
    mailto = crossref_mailto()
    if mailto:
        return f"{DEFAULT_CROSSREF_USER_AGENT} (mailto:{mailto})"
    return DEFAULT_CROSSREF_USER_AGENT


def crossref_request_headers() -> dict[str, str]:
    return {"User-Agent": crossref_user_agent()}


def crossref_request_params(
    params: Mapping[str, _ParamValue],
) -> dict[str, _ParamValue | str]:
    request_params: dict[str, _ParamValue | str] = dict(params)
    mailto = crossref_mailto()
    if mailto:
        request_params["mailto"] = mailto
    return request_params
