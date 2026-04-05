from __future__ import annotations

from src.data_agents.linking import build_normalized_index, link_normalized_values
from src.data_agents.normalization import normalize_company_name, normalize_person_name


def build_company_name_index(values: dict[str, str]) -> dict[str, str | None]:
    return build_normalized_index(values, normalizer=normalize_company_name)


def build_professor_name_index(values: dict[str, str]) -> dict[str, str | None]:
    return build_normalized_index(values, normalizer=normalize_person_name)


def link_company_ids(applicants: list[str], company_name_to_id: dict[str, str]) -> list[str]:
    return link_normalized_values(
        applicants,
        build_company_name_index(company_name_to_id),
        normalizer=normalize_company_name,
    )


def link_professor_ids(inventors: list[str], professor_name_to_id: dict[str, str]) -> list[str]:
    return link_normalized_values(
        inventors,
        build_professor_name_index(professor_name_to_id),
        normalizer=normalize_person_name,
    )
