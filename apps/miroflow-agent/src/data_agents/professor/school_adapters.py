from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Sequence

from .models import DiscoveredProfessorSeed


@dataclass(frozen=True, slots=True)
class SchoolRosterAdapter:
    name: str
    matcher: Callable[[str], bool]
    extractor: Callable[[str, str, str | None, str], list[DiscoveredProfessorSeed]]

    def matches(self, source_url: str) -> bool:
        return self.matcher(source_url)

    def extract(
        self,
        html: str,
        institution: str,
        department: str | None,
        source_url: str,
    ) -> list[DiscoveredProfessorSeed]:
        return self.extractor(html, institution, department, source_url)


def school_adapter_bypass_enabled() -> bool:
    return os.getenv("PROFESSOR_SCHOOL_ADAPTER_BYPASS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def find_matching_school_adapter(
    source_url: str,
    adapters: Sequence[SchoolRosterAdapter],
    *,
    bypass: bool | None = None,
) -> SchoolRosterAdapter | None:
    if bypass is None:
        bypass = school_adapter_bypass_enabled()
    if bypass:
        return None
    for adapter in adapters:
        if adapter.matches(source_url):
            return adapter
    return None
