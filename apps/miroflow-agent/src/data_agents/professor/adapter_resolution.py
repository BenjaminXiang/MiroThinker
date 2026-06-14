from __future__ import annotations

from urllib.parse import urlparse

from .discovery import _is_cuhk_seed, _is_hit_seed, _is_sigs_seed
from .models import ProfessorRosterSeed
from .roster import _SCHOOL_ROSTER_ADAPTERS
from .school_adapters import find_matching_school_adapter


def resolve_seed_adapter_name(seed: ProfessorRosterSeed) -> str | None:
    """Return the registered adapter/API path name for one roster seed."""
    source_url = seed.roster_url
    if _is_sigs_seed(source_url):
        return "sigs_teacher_api"
    if _is_hit_seed(source_url):
        return "hit_teacher_api"
    if _is_cuhk_seed(source_url):
        return "cuhk_teacher_search"
    if _is_uestc_sias_mentor_seed(source_url):
        return "uestc-yjsjy-mentor-roster"
    if _is_szu_cpoe_teacherfeature_seed(source_url):
        return "szu-cpoe-teacherfeature"
    adapter = find_matching_school_adapter(source_url, _SCHOOL_ROSTER_ADAPTERS)
    return adapter.name if adapter is not None else None


def _is_uestc_sias_mentor_seed(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    return hostname == "sias.uestc.edu.cn" and path.startswith("/rcpy/dsjs1/")


def _is_szu_cpoe_teacherfeature_seed(source_url: str) -> bool:
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/").lower()
    return hostname == "cpoe.szu.edu.cn" and path.endswith("/szdw.jsp")
