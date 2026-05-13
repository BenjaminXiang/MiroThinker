from __future__ import annotations

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
    adapter = find_matching_school_adapter(source_url, _SCHOOL_ROSTER_ADAPTERS)
    return adapter.name if adapter is not None else None
