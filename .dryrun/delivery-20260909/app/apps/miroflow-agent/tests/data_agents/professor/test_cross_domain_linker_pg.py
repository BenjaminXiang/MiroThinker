from __future__ import annotations

from src.data_agents.professor.cross_domain import CompanyLink
from src.data_agents.professor.cross_domain_linker import (
    build_company_role_link_records,
)
from src.data_agents.professor.models import (
    EnrichedProfessorProfile,
    OfficialAnchorProfile,
)


def _profile(**overrides) -> EnrichedProfessorProfile:
    values = {
        "name": "李志",
        "institution": "南方科技大学",
        "department": "计算机科学与工程系",
        "profile_url": "https://sustech.edu.cn/faculty/lizhi",
        "roster_source": "https://sustech.edu.cn/roster",
        "extraction_status": "success",
        "company_roles": [],
        "evidence_urls": ["https://sustech.edu.cn/faculty/lizhi"],
    }
    values.update(overrides)
    return EnrichedProfessorProfile(**values)


def _anchor(bio_text: str) -> OfficialAnchorProfile:
    return OfficialAnchorProfile(
        source_url="https://sustech.edu.cn/faculty/lizhi",
        bio_text=bio_text,
    )


def test_build_company_role_link_records_maps_official_bio_founder_signal():
    profile = _profile(
        official_anchor_profile=_anchor(
            "Professor Li is founder of 广和通 and works on IoT chips."
        ),
        company_roles=[
            CompanyLink(
                company_id="COMP-XXX",
                company_name="广和通",
                role="",
                evidence_url="https://sustech.edu.cn/faculty/lizhi",
                source="web_scrape",
            )
        ],
    )

    records = build_company_role_link_records(profile, source_ref="PROF-XXX")

    assert records == [
        {
            "professor_id": "PROF-XXX",
            "company_id": "COMP-XXX",
            "role_type": "founder",
            "link_status": "candidate",
            "evidence_source_type": "professor_official_profile",
            "evidence_url": "https://sustech.edu.cn/faculty/lizhi",
            "match_reason": records[0]["match_reason"],
            "source_ref": "PROF-XXX",
        }
    ]
    assert "founder" in records[0]["match_reason"]
    assert len(records[0]["match_reason"]) <= 200


def test_build_company_role_link_records_maps_xlsx_team_chief_scientist_signal():
    profile = _profile(
        company_roles=[
            CompanyLink(
                company_id="COMP-TEAM",
                company_name="深圳点联传感科技有限公司",
                role="Chief Scientist",
                evidence_url="file://company.xlsx#team_raw",
                source="xlsx_team_with_explicit_role",
            )
        ],
    )

    records = build_company_role_link_records(profile, source_ref="PROF-TEAM")

    assert len(records) == 1
    assert records[0]["role_type"] == "chief_scientist"
    assert records[0]["evidence_source_type"] == "xlsx_team_with_explicit_role"
    assert records[0]["source_ref"] == "PROF-TEAM"


def test_build_company_role_link_records_emits_multiple_companies():
    profile = _profile(
        company_roles=[
            CompanyLink(
                company_id="COMP-A",
                company_name="深圳A科技有限公司",
                role="联合创始人",
                evidence_url="https://news.example.com/a",
                source="trusted_media",
            ),
            CompanyLink(
                company_id="COMP-B",
                company_name="深圳B科技有限公司",
                role="学术顾问",
                evidence_url="https://news.example.com/b",
                source="trusted_media",
            ),
        ],
    )

    records = build_company_role_link_records(profile, source_ref="PROF-MULTI")

    assert [(record["company_id"], record["role_type"]) for record in records] == [
        ("COMP-A", "cofounder"),
        ("COMP-B", "advisor"),
    ]


def test_build_company_role_link_records_skips_missing_evidence_url():
    profile = _profile(
        company_roles=[
            CompanyLink(
                company_id="COMP-NO-EVIDENCE",
                company_name="深圳无证据科技有限公司",
                role="创始人",
                evidence_url=None,
                source="trusted_media",
            )
        ],
    )

    assert build_company_role_link_records(profile, source_ref="PROF-SKIP") == []
