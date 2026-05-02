from __future__ import annotations

from src.data_agents.linking import build_normalized_index, link_normalized_values
from src.data_agents.normalization import normalize_company_name, normalize_person_name

from .import_xlsx import _split_tokens


CompanyPatentLinkCandidate = tuple[str, str, str]
_EXACT_EVIDENCE_SOURCE_TYPE = "patent_xlsx_applicant_exact_match"
_NORMALIZED_EVIDENCE_SOURCE_TYPE = "patent_xlsx_applicant_normalized_match"
_MAX_MATCH_REASON_CHARS = 200


def build_company_name_index(values: dict[str, str]) -> dict[str, str | None]:
    return build_normalized_index(values, normalizer=normalize_company_name)


def build_professor_name_index(values: dict[str, str]) -> dict[str, str | None]:
    return build_normalized_index(values, normalizer=normalize_person_name)


def link_company_ids(
    applicants: list[str],
    company_name_to_id: dict[str, str],
) -> list[CompanyPatentLinkCandidate]:
    exact_index = {
        name.strip(): company_id
        for name, company_id in company_name_to_id.items()
        if name.strip()
    }
    normalized_index = build_company_name_index(company_name_to_id)
    matched: list[CompanyPatentLinkCandidate] = []
    seen_company_ids: set[str] = set()

    for index, applicant in enumerate(_split_applicants(applicants)):
        exact_company_id = exact_index.get(applicant)
        if exact_company_id and exact_company_id not in seen_company_ids:
            seen_company_ids.add(exact_company_id)
            matched.append(
                (
                    exact_company_id,
                    _EXACT_EVIDENCE_SOURCE_TYPE,
                    _trim_match_reason(
                        f"applicants_parsed[{index}]='{applicant}' exact match "
                        f"-> {exact_company_id}"
                    ),
                )
            )
            continue

        normalized = normalize_company_name(applicant)
        company_id = normalized_index.get(normalized)
        if not company_id or company_id in seen_company_ids:
            continue
        seen_company_ids.add(company_id)
        matched.append(
            (
                company_id,
                _NORMALIZED_EVIDENCE_SOURCE_TYPE,
                _trim_match_reason(
                    f"applicants_parsed[{index}]='{applicant}' normalized to "
                    f"'{normalized}' -> {company_id}"
                ),
            )
        )
    return matched


def link_professor_ids(inventors: list[str], professor_name_to_id: dict[str, str]) -> list[str]:
    return link_normalized_values(
        inventors,
        build_professor_name_index(professor_name_to_id),
        normalizer=normalize_person_name,
    )


def _split_applicants(applicants: list[str]) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for applicant in applicants:
        for token in _split_tokens(applicant):
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return tokens


def _trim_match_reason(reason: str) -> str:
    if len(reason) <= _MAX_MATCH_REASON_CHARS:
        return reason
    return reason[: _MAX_MATCH_REASON_CHARS - 1].rstrip() + "…"
