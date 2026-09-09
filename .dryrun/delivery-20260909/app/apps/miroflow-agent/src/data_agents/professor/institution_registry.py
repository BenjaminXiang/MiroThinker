# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Static OpenAlex institution registry for Shenzhen professor pipelines."""
from __future__ import annotations

from dataclasses import dataclass

from .institution_names import _ALIASES, normalize_institution_text


@dataclass(frozen=True, slots=True)
class InstitutionRegistryEntry:
    key: str
    name_zh: str
    name_en: str
    openalex_id: str | None
    notes: str | None = None


_REGISTRY: tuple[InstitutionRegistryEntry, ...] = (
    InstitutionRegistryEntry(
        key="sustech",
        name_zh="南方科技大学",
        name_en="Southern University of Science and Technology",
        openalex_id="I3045169105",
        notes="Verified against OpenAlex institutions search on 2026-04-08.",
    ),
    InstitutionRegistryEntry(
        key="tsinghua_sigs",
        name_zh="清华大学深圳国际研究生院",
        name_en="Tsinghua Shenzhen International Graduate School",
        openalex_id="I4405263052",
        notes="Verified against OpenAlex institutions search on 2026-04-13.",
    ),
    InstitutionRegistryEntry(
        key="pkusz",
        name_zh="北京大学深圳研究生院",
        name_en="Peking University Shenzhen Graduate School",
        openalex_id="I20231570",
        notes="Verified parent university OpenAlex ID on 2026-04-13; Shenzhen campus currently falls back to the parent institution entry.",
    ),
    InstitutionRegistryEntry(
        key="szu",
        name_zh="深圳大学",
        name_en="Shenzhen University",
        openalex_id="I180726961",
        notes="Verified against OpenAlex institutions search on 2026-04-13.",
    ),
    InstitutionRegistryEntry(
        key="suat",
        name_zh="深圳理工大学",
        name_en="Shenzhen University of Advanced Technology",
        openalex_id="I4405255904",
        notes="Verified against OpenAlex institutions search on 2026-04-13.",
    ),
    InstitutionRegistryEntry(
        key="hitsz",
        name_zh="哈尔滨工业大学（深圳）",
        name_en="Harbin Institute of Technology, Shenzhen",
        openalex_id="I204983213",
        notes="Verified parent university OpenAlex ID on 2026-04-13; Shenzhen campus currently falls back to the parent institution entry.",
    ),
    InstitutionRegistryEntry(
        key="sysu",
        name_zh="中山大学（深圳）",
        name_en="Sun Yat-sen University",
        openalex_id="I157773358",
        notes="Verified parent university OpenAlex ID on 2026-04-08; Shenzhen campus may share the parent institution entry.",
    ),
    InstitutionRegistryEntry(
        key="sztu",
        name_zh="深圳技术大学",
        name_en="Shenzhen Technology University",
        openalex_id="I4210152380",
        notes="Verified against OpenAlex institutions search on 2026-04-13.",
    ),
    InstitutionRegistryEntry(
        key="cuhksz",
        name_zh="香港中文大学（深圳）",
        name_en="The Chinese University of Hong Kong, Shenzhen",
        openalex_id="I4210116924",
        notes="Verified against OpenAlex institutions search on 2026-04-13.",
    ),
)

_BY_ALIAS: dict[str, InstitutionRegistryEntry] = {}
for entry in _REGISTRY:
    alias_group = _ALIASES.get(entry.name_zh, (entry.name_zh, entry.name_en))
    for alias in alias_group:
        normalized = normalize_institution_text(alias)
        if normalized:
            _BY_ALIAS[normalized] = entry


def get_institution_registry_entry(
    institution_name: str | None,
) -> InstitutionRegistryEntry | None:
    normalized = normalize_institution_text(institution_name)
    if not normalized:
        return None
    return _BY_ALIAS.get(normalized)


def resolve_openalex_institution_id(institution_name: str | None) -> str | None:
    entry = get_institution_registry_entry(institution_name)
    if entry is None:
        return None
    return entry.openalex_id
