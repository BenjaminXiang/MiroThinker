#!/usr/bin/env python3
"""Build the compact frozen Canonical V2 PRD domain catalog deterministically."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import ModuleType
from typing import Any, Protocol, cast


S6_ROOT = Path(__file__).resolve().parent
DEFAULT_CATALOG = S6_ROOT / "domain-catalog-v1.json"
DEFAULT_REPO_ROOT = S6_ROOT.parents[3]


class _ValidatorModule(Protocol):
    def canonical_catalog_bytes(self, catalog: dict[str, Any]) -> bytes: ...

    def catalog_content_sha256(self, catalog: dict[str, Any]) -> str: ...

    def load_and_validate_catalog(
        self, *, repo_root: Path, catalog_path: Path
    ) -> dict[str, Any]: ...


def _load_validator_module() -> _ValidatorModule:
    path = S6_ROOT / "validate_domain_catalog.py"
    spec = importlib.util.spec_from_file_location("canonical_v2_s6_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load catalog validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(_ValidatorModule, cast(ModuleType, module))


_VALIDATOR = _load_validator_module()
canonical_catalog_bytes = _VALIDATOR.canonical_catalog_bytes
catalog_content_sha256 = _VALIDATOR.catalog_content_sha256
load_and_validate_catalog = _VALIDATOR.load_and_validate_catalog

DOMAIN_CITATIONS = {
    "company": ("company.fields_and_personnel", "s2.relationship_families"),
    "paper": ("paper.fields", "paper.review_contract"),
    "patent": ("patent.fields", "s2.relationship_families"),
    "professor": (
        "professor.fields",
        "professor.review_fields_and_lifecycle",
        "openspec.professor_split_projections",
    ),
}

SOURCE_CITATION_ADDITIONS = {
    ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2/source-coverage-matrix.md": (
        {
            "citation_id": "s2.typed_business_facts",
            "line_end": 50,
            "line_start": 41,
            "source_terms": [
                "Professor affiliation/education/work history",
                "Company team/financing/business/product/scenario",
                "Patent applicant/inventor/classification/content",
            ],
        },
    ),
    "docs/Company-Data-Agent-PRD.md": (
        {
            "citation_id": "company.business_sources_and_jumps",
            "line_end": 73,
            "line_start": 26,
            "source_terms": ["企业 → 专利", "企业 → 关键人物", "融资轮次"],
        },
        {
            "citation_id": "company.cross_domain_relationships",
            "line_end": 287,
            "line_start": 259,
            "source_terms": [
                "`company_roles`",
                "标准化企业名",
                "关键人物结构化筛选",
            ],
        },
        {
            "citation_id": "company.web_business_updates",
            "line_end": 228,
            "line_start": 211,
            "source_terms": ["产品页", "`product_description`", "最新公开动态"],
        },
    ),
    "docs/Paper-Data-Agent-PRD.md": (
        {
            "citation_id": "paper.professor_attribution",
            "line_end": 229,
            "line_start": 208,
            "source_terms": [
                "`professor_paper_link",
                "`paper_identity_gate`",
                "不关联",
            ],
        },
        {
            "citation_id": "paper.reference_phase2",
            "line_end": 263,
            "line_start": 245,
            "source_terms": ["引文图谱抽取放 Phase 2", "内容哈希", "pdf_sha256"],
        },
    ),
    "docs/Patent-Data-Agent-PRD.md": (
        {
            "citation_id": "patent.cross_domain_relationships",
            "line_end": 240,
            "line_start": 217,
            "source_terms": ["`company_ids`", "`professor_ids`", "候选关系"],
        },
    ),
    "docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md": (
        {
            "citation_id": "professor.company_relationship",
            "line_end": 230,
            "line_start": 224,
            "source_terms": ["企业域 ID match", "`source_url`", "异步回填"],
        },
    ),
    "docs/Professor-Requirement-Review-2026-05-10.md": (
        {
            "citation_id": "professor.paper_patent_relationships",
            "line_end": 206,
            "line_start": 185,
            "source_terms": [
                "Paper-from-prof-page",
                "Patent-from-prof-page",
                "prof 页列了",
            ],
        },
    ),
    "openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/canonical-v2-knowledge/spec.md": (
        {
            "citation_id": "openspec.domain_inclusion",
            "line_end": 27,
            "line_start": 12,
            "source_terms": [
                "Domain inclusion follows the authoritative PRD",
                "Professor inclusion",
                "Company inclusion",
            ],
        },
        {
            "citation_id": "openspec.relationship_layers",
            "line_end": 102,
            "line_start": 92,
            "source_terms": [
                "release-scoped derived relations",
                "session relations",
                "source-grounded canonical relationship",
            ],
        },
        {
            "citation_id": "openspec.path_eligibility",
            "line_end": 108,
            "line_start": 104,
            "source_terms": [
                "Inclusion and path eligibility are separate",
                "named, versioned path",
                "one global",
            ],
        },
    ),
}

NEW_AUTHORITY_SOURCES = {
    "docs/Multi-turn-Context-Manager-Design.md": {
        "authority_tier": "authoritative_product_design",
        "citations": (
            {
                "citation_id": "multi_turn.cross_domain_directions",
                "line_end": 155,
                "line_start": 144,
                "source_terms": ["教授 → 论文", "企业 → 专利", "专利 → 教授"],
            },
        ),
        "sha256": "a8deec2bc6cacf8753945ce8e34ef83eda3faf7bb3181bf657758fb391e0ac60",
    },
    "openspec/changes/rebuild-canonical-v2-knowledge-platform/design.md": {
        "authority_tier": "openspec_design",
        "citations": (
            {
                "citation_id": "openspec.decision_lineage",
                "line_end": 110,
                "line_start": 105,
                "source_terms": [
                    "source assertion",
                    "canonical decision selects",
                    "policy version",
                ],
            },
        ),
        "sha256": "10e2b8458765a0f9e1cb62564986bc763e7871b6d43ce98e6e83e9c95477a9fc",
    },
    "openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/recovery-evidence-landing/spec.md": {
        "authority_tier": "openspec_behavior",
        "citations": (
            {
                "citation_id": "openspec.artifact_and_record_lineage",
                "line_end": 66,
                "line_start": 46,
                "source_terms": [
                    "content hash",
                    "parent artifact",
                    "parser name/version",
                    "parse run",
                ],
            },
        ),
        "sha256": "b183557aeaed72f1ad65e9688f479d2a192027964e9911daefc6d162005457bd",
    },
}

RELATIONSHIP_FAMILIES = {
    "company_business_product_event": {
        "citation_ids": ("company.fields_and_personnel", "s2.relationship_families"),
        "semantic_scope": "company products capabilities scenarios financing public updates and team",
    },
    "evidence_lineage": {
        "citation_ids": (
            "openspec.canonical_relationships",
            "s2.relationship_families",
        ),
        "semantic_scope": "artifacts source records assertions decisions policies and runs",
    },
    "identity_lifecycle": {
        "citation_ids": ("openspec.canonical_identity", "s2.relationship_families"),
        "semantic_scope": "source resolution aliases merges splits supersession and reversal",
    },
    "intellectual_property": {
        "citation_ids": (
            "company.cross_domain_relationships",
            "patent.cross_domain_relationships",
            "professor.paper_patent_relationships",
            "s2.relationship_families",
        ),
        "semantic_scope": "patent applicants inventors and evidence-qualified page associations",
    },
    "organization_role": {
        "citation_ids": (
            "company.cross_domain_relationships",
            "professor.company_relationship",
            "professor.fields",
            "s2.relationship_families",
        ),
        "semantic_scope": "affiliation department education work company and team roles",
    },
    "scholarly_output": {
        "citation_ids": (
            "paper.professor_attribution",
            "professor.paper_patent_relationships",
            "s2.relationship_families",
        ),
        "semantic_scope": "paper attribution authors publication venue and references",
    },
    "taxonomy_topic_geography": {
        "citation_ids": (
            "shared.domain_contracts_and_filters",
            "s2.relationship_families",
        ),
        "semantic_scope": "research topics industry IPC geography and other versioned taxonomies",
    },
}

LAYER_CONTRACTS = (
    {
        "allowed_time_semantics": (
            "event_time",
            "none",
            "observed_at",
            "validity_interval",
        ),
        "citation_ids": (
            "openspec.canonical_relationships",
            "openspec.relationship_layers",
        ),
        "layer": "canonical",
        "required_evidence_policy": "required",
        "semantic_boundary": "source_grounded_accepted_relationship_facts",
        "type_freeze_status": "frozen_in_task_6_1",
    },
    {
        "allowed_time_semantics": ("computed_at",),
        "citation_ids": ("openspec.relationship_layers", "s2.relationship_families"),
        "layer": "derived",
        "required_evidence_policy": "forbidden",
        "semantic_boundary": "release_scoped_reproducible_computations_not_canonical_facts",
        "type_freeze_status": "deferred_to_s7_s8",
    },
    {
        "allowed_time_semantics": ("session_lifetime",),
        "citation_ids": ("openspec.relationship_layers", "s2.relationship_families"),
        "layer": "session",
        "required_evidence_policy": "forbidden",
        "semantic_boundary": "session_scoped_referents_sets_constraints_and_paths_not_canonical_facts",
        "type_freeze_status": "deferred_to_s9",
    },
)

DIRECTION_SCENARIOS = {
    "company_to_patent": {
        "evidence_outcome": "supported",
        "family": "intellectual_property",
        "relationship_type_ids": ("patent_has_applicant",),
    },
    "company_to_professor": {
        "evidence_outcome": "insufficient_evidence",
        "family": "organization_role",
        "relationship_type_ids": ("professor_company_role",),
    },
    "paper_to_professor": {
        "evidence_outcome": "supported",
        "family": "scholarly_output",
        "relationship_type_ids": ("professor_attributed_to_paper",),
    },
    "patent_to_company": {
        "evidence_outcome": "supported",
        "family": "intellectual_property",
        "relationship_type_ids": ("patent_has_applicant",),
    },
    "patent_to_professor": {
        "evidence_outcome": "insufficient_evidence",
        "family": "intellectual_property",
        "relationship_type_ids": (
            "patent_has_inventor",
            "professor_page_lists_patent",
        ),
    },
    "professor_to_company": {
        "evidence_outcome": "insufficient_evidence",
        "family": "organization_role",
        "relationship_type_ids": ("professor_company_role",),
    },
    "professor_to_paper": {
        "evidence_outcome": "supported",
        "family": "scholarly_output",
        "relationship_type_ids": ("professor_attributed_to_paper",),
    },
    "professor_to_patent": {
        "evidence_outcome": "insufficient_evidence",
        "family": "intellectual_property",
        "relationship_type_ids": (
            "patent_has_inventor",
            "professor_page_lists_patent",
        ),
    },
}

ABSENT_RELATIONSHIP_EVIDENCE = {
    "identity_decision_reverses_identity_decision",
    "paper_references_paper",
}
INSUFFICIENT_RELATIONSHIP_EVIDENCE = {
    "canonical_identity_split_from",
    "patent_has_inventor",
    "professor_page_lists_patent",
}

DEFERRED_OWNERS = {
    "derived_relationship_execution": {
        "citation_ids": ("openspec.relationship_layers",),
        "owner": "s7_s8",
        "scope": "release-scoped similarity ranking trend and representative-result definitions",
    },
    "domain_inclusion_and_projection": {
        "citation_ids": (
            "openspec.domain_inclusion",
            "shared.domain_contracts_and_filters",
        ),
        "owner": "tasks_6_2_6_3",
        "scope": "inclusion scenarios typed current projections physical schema and migrations",
    },
    "path_eligibility": {
        "citation_ids": ("openspec.path_eligibility",),
        "owner": "tasks_6_6_6_7",
        "scope": "versioned per-path admission limitation and policy outcomes",
    },
    "relationship_execution_and_persistence": {
        "citation_ids": ("openspec.canonical_relationships",),
        "owner": "tasks_6_4_6_5",
        "scope": "executable scenarios endpoint binding assertions decisions and integrity",
    },
    "session_relationship_execution": {
        "citation_ids": ("openspec.relationship_layers",),
        "owner": "s9",
        "scope": "session referents displayed sets active constraints and traversed paths",
    },
}

SHARED_FIELDS = {
    "core_facts": "typed_map",
    "display_name": "text",
    "evidence": "evidence_reference_list",
    "id": "canonical_identity_id",
    "last_updated": "aware_datetime",
    "object_type": "domain_discriminator",
    "quality_status": "quality_signal",
    "run_id": "decision_run_id",
    "summary_fields": "typed_summary_map",
}

DOMAIN_FIELD_NAMES = {
    "company": {
        "aliases",
        "credit_code",
        "evidence",
        "founded_at",
        "geography",
        "id",
        "industry",
        "industry_tags",
        "key_personnel",
        "last_updated",
        "latest_public_updates",
        "legal_representative",
        "name",
        "normalized_name",
        "patent_count",
        "product_description",
        "profile_summary",
        "quality_status",
        "registered_address",
        "registered_capital",
        "run_id",
        "team_description",
        "tech_tags",
        "technology_route_summary",
        "website",
    },
    "paper": {
        "abstract",
        "arxiv_id",
        "authors",
        "citation_count",
        "doi",
        "enrichment_sources",
        "evidence",
        "fields_of_study",
        "funders",
        "id",
        "keywords",
        "last_updated",
        "license",
        "oa_status",
        "pdf_path",
        "professor_ids",
        "publication_date",
        "quality_status",
        "reference_count",
        "run_id",
        "summary_text",
        "summary_zh",
        "title",
        "title_zh",
        "tldr",
        "venue",
        "year",
    },
    "patent": {
        "abstract",
        "applicants",
        "company_ids",
        "evidence",
        "filing_date",
        "grant_date",
        "id",
        "inventors",
        "ipc_codes",
        "last_updated",
        "patent_number",
        "patent_type",
        "professor_ids",
        "publication_date",
        "quality_status",
        "run_id",
        "summary_text",
        "technology_effect",
        "title",
        "title_en",
    },
    "professor": {
        "aliases",
        "awards",
        "canonical_name_en",
        "canonical_name_zh",
        "citation_count",
        "company_roles",
        "department",
        "email",
        "evidence",
        "h_index",
        "homepage",
        "id",
        "institution",
        "last_updated",
        "lifecycle_state",
        "manual_override",
        "name",
        "office",
        "paper_count",
        "paper_summary",
        "patent_ids",
        "patent_summary",
        "phone",
        "profile_summary",
        "projects",
        "quality_status",
        "research_directions",
        "run_id",
        "title",
    },
}

REQUIRED_FIELDS = {
    "company": {
        "evidence",
        "id",
        "last_updated",
        "name",
        "normalized_name",
        "profile_summary",
        "quality_status",
        "run_id",
        "technology_route_summary",
    },
    "paper": {
        "authors",
        "evidence",
        "id",
        "last_updated",
        "quality_status",
        "run_id",
        "title",
        "venue",
        "year",
    },
    "patent": {
        "applicants",
        "evidence",
        "id",
        "last_updated",
        "quality_status",
        "run_id",
        "summary_text",
        "title",
    },
    "professor": {
        "canonical_name_zh",
        "company_roles",
        "department",
        "email",
        "evidence",
        "homepage",
        "id",
        "institution",
        "last_updated",
        "name",
        "paper_summary",
        "patent_ids",
        "patent_summary",
        "profile_summary",
        "quality_status",
        "research_directions",
        "run_id",
        "title",
    },
}

QUALITY_READY_ONLY_FIELDS = {"paper": {"summary_text", "summary_zh"}}

CONDITIONAL_FIELDS = {
    "company": {"industry", "key_personnel"},
    "paper": {"professor_ids", "publication_date", "summary_text", "summary_zh"},
    "patent": {
        "company_ids",
        "filing_date",
        "inventors",
        "patent_type",
        "professor_ids",
        "publication_date",
    },
    "professor": {
        "canonical_name_en",
        "lifecycle_state",
        "manual_override",
        "office",
        "phone",
    },
}

MANY_FIELDS = {
    "aliases",
    "applicants",
    "authors",
    "awards",
    "company_ids",
    "company_roles",
    "enrichment_sources",
    "evidence",
    "fields_of_study",
    "funders",
    "industry_tags",
    "inventors",
    "ipc_codes",
    "key_personnel",
    "keywords",
    "latest_public_updates",
    "patent_ids",
    "professor_ids",
    "projects",
    "research_directions",
    "tech_tags",
}

VALUE_SHAPES = {
    "aliases": "text_list",
    "applicants": "applicant_list",
    "authors": "author_list",
    "awards": "award_list",
    "canonical_name_en": "text",
    "canonical_name_zh": "text",
    "company_ids": "canonical_identity_id_list",
    "company_roles": "relationship_projection_list",
    "credit_code": "credit_code",
    "department": "organization_reference",
    "email": "email",
    "enrichment_sources": "enrichment_provenance_list",
    "evidence": "evidence_reference_list",
    "fields_of_study": "taxonomy_reference_list",
    "filing_date": "date",
    "founded_at": "date",
    "funders": "funding_list",
    "geography": "geography_reference",
    "grant_date": "date",
    "homepage": "url",
    "id": "canonical_identity_id",
    "industry": "taxonomy_reference",
    "industry_tags": "taxonomy_reference_list",
    "inventors": "inventor_list",
    "ipc_codes": "ipc_reference_list",
    "key_personnel": "key_personnel_list",
    "keywords": "text_list",
    "last_updated": "aware_datetime",
    "latest_public_updates": "public_update_list",
    "legal_representative": "person_reference",
    "lifecycle_state": "lifecycle_state",
    "manual_override": "field_override_map",
    "oa_status": "open_access_status",
    "office": "text",
    "patent_ids": "canonical_identity_id_list",
    "patent_number": "patent_identifier",
    "patent_type": "patent_type",
    "pdf_path": "content_storage_reference",
    "phone": "phone",
    "professor_ids": "canonical_identity_id_list",
    "projects": "research_project_list",
    "publication_date": "date",
    "quality_status": "quality_signal",
    "registered_address": "text",
    "registered_capital": "money",
    "research_directions": "taxonomy_reference_list",
    "run_id": "decision_run_id",
    "tech_tags": "taxonomy_reference_list",
    "title": "text",
    "title_en": "text",
    "title_zh": "text",
    "venue": "venue_reference",
    "website": "url",
    "year": "year",
}

INTEGER_FIELDS = {
    "citation_count",
    "h_index",
    "paper_count",
    "patent_count",
    "reference_count",
}
SUMMARY_FIELDS = {
    "paper_summary",
    "patent_summary",
    "profile_summary",
    "summary_text",
    "summary_zh",
    "technology_route_summary",
    "tldr",
}
RELATIONSHIP_PROJECTION_FIELDS = {
    "company_ids",
    "company_roles",
    "patent_ids",
    "professor_ids",
}
EVENT_FIELDS = {
    "filing_date",
    "founded_at",
    "grant_date",
    "last_updated",
    "publication_date",
    "year",
}


def _field_requiredness(domain: str, name: str) -> str:
    if name in REQUIRED_FIELDS[domain]:
        return "required"
    if name in CONDITIONAL_FIELDS[domain]:
        return "conditional"
    return "optional"


def _field_requiredness_scope(domain: str, name: str, requiredness: str) -> str:
    if name in QUALITY_READY_ONLY_FIELDS.get(domain, set()):
        return "quality_status_ready_only_not_canonical_inclusion"
    return {
        "conditional": "source_or_path_specific_when_evidenced",
        "optional": "best_effort_when_evidenced",
        "required": "canonical_projection_key",
    }[requiredness]


def _field_shape(name: str) -> str:
    if name in VALUE_SHAPES:
        return VALUE_SHAPES[name]
    if name in INTEGER_FIELDS:
        return "integer"
    if name.endswith("_id") or name in {"arxiv_id", "doi"}:
        return "identifier"
    if name.endswith("_at"):
        return "aware_datetime"
    return "text"


def _field_semantic_use(name: str) -> str:
    if name == "quality_status":
        return "quality_signal_not_path_admission"
    if name in RELATIONSHIP_PROJECTION_FIELDS:
        return "accepted_relationship_projection"
    if name in SUMMARY_FIELDS:
        return "display_and_semantic_retrieval"
    if name in {
        "id",
        "name",
        "normalized_name",
        "canonical_name_zh",
        "canonical_name_en",
        "aliases",
    }:
        return "identity_and_exact_retrieval"
    if name in {
        "industry",
        "geography",
        "department",
        "institution",
        "patent_type",
        "ipc_codes",
        "year",
        "publication_date",
    }:
        return "structured_filter_and_display"
    if name in {"evidence", "run_id", "last_updated", "manual_override"}:
        return "audit_and_provenance"
    return "typed_display_filter_or_assessment_fact"


def _field_evidence_obligation(name: str) -> str:
    if name == "id":
        return "accepted_identity_decision"
    if name == "evidence":
        return "retained_evidence_references"
    if name == "run_id":
        return "producing_decision_run"
    if name == "quality_status":
        return "versioned_quality_policy_decision"
    if name in RELATIONSHIP_PROJECTION_FIELDS:
        return "accepted_relationship_decisions"
    if name in SUMMARY_FIELDS:
        return "supporting_assertions_and_versioned_synthesis_trace"
    return "supporting_source_assertions_or_accepted_derivation"


def _field(domain: str, name: str) -> dict[str, Any]:
    requiredness = _field_requiredness(domain, name)
    return {
        "cardinality": (
            "many"
            if name in MANY_FIELDS
            else "one"
            if requiredness == "required"
            else "optional_one"
        ),
        "catalog_item_id": f"field.{domain}.{name}",
        "citation_ids": list(DOMAIN_CITATIONS[domain]),
        "evidence_obligation": _field_evidence_obligation(name),
        "field_path": name,
        "requiredness": requiredness,
        "requiredness_scope": _field_requiredness_scope(domain, name, requiredness),
        "semantic_use": _field_semantic_use(name),
        "temporal_class": (
            "observation"
            if name == "last_updated"
            else "event"
            if name in EVENT_FIELDS
            else "static"
        ),
        "value_shape": _field_shape(name),
    }


def _member(name: str, shape: str, *, required: bool = True) -> dict[str, Any]:
    return {"member_name": name, "required": required, "value_shape": shape}


SUBOBJECT_DEFINITIONS: dict[str, dict[str, dict[str, Any]]] = {
    "company": {
        "business_scenario": {
            "identity_key": "normalized_name",
            "members": [_member("name", "text"), _member("description", "text")],
            "temporal_class": "validity_interval",
        },
        "capability": {
            "identity_key": "normalized_name",
            "members": [_member("name", "text"), _member("description", "text")],
            "temporal_class": "validity_interval",
        },
        "financing_event": {
            "identity_key": "round+event_date+amount",
            "members": [
                _member("round", "text"),
                _member("amount", "money", required=False),
                _member("investors", "organization_reference_list", required=False),
                _member("event_date", "date", required=False),
            ],
            "temporal_class": "event",
        },
        "key_personnel": {
            "identity_key": "normalized_person_name+role",
            "members": [
                _member("name", "text"),
                _member("role", "text"),
                _member("description", "text", required=False),
            ],
            "temporal_class": "validity_interval",
        },
        "personnel_education": {
            "identity_key": "person+institution+degree+field",
            "members": [
                _member("person", "person_reference"),
                _member("institution", "organization_reference"),
                _member("degree", "text", required=False),
                _member("field", "text", required=False),
                _member("year", "year", required=False),
            ],
            "temporal_class": "validity_interval",
        },
        "personnel_work_experience": {
            "identity_key": "person+organization+role+start",
            "members": [
                _member("person", "person_reference"),
                _member("organization", "organization_reference"),
                _member("role", "text"),
                _member("start", "date", required=False),
                _member("end", "date", required=False),
            ],
            "temporal_class": "validity_interval",
        },
        "product": {
            "identity_key": "normalized_name",
            "members": [
                _member("name", "text"),
                _member("description", "text", required=False),
                _member("technology_tags", "taxonomy_reference_list", required=False),
            ],
            "temporal_class": "validity_interval",
        },
        "public_update": {
            "identity_key": "source_url+event_date",
            "members": [
                _member("headline", "text"),
                _member("source_url", "url"),
                _member("event_date", "date", required=False),
                _member("summary", "text", required=False),
            ],
            "temporal_class": "event",
        },
    },
    "paper": {
        "author": {
            "identity_key": "author_order+normalized_name",
            "members": [
                _member("name", "text"),
                _member("author_order", "integer"),
                _member("orcid", "identifier", required=False),
                _member("affiliations", "organization_reference_list", required=False),
            ],
            "temporal_class": "static",
        },
        "enrichment_provenance": {
            "identity_key": "provider+fetched_at+source_record_id",
            "members": [
                _member("provider", "text"),
                _member("fetched_at", "aware_datetime"),
                _member("source_record_id", "source_record_id"),
            ],
            "temporal_class": "event",
        },
        "full_text": {
            "identity_key": "content_sha256+parser_version",
            "members": [
                _member("content_sha256", "sha256"),
                _member("storage_reference", "content_storage_reference"),
                _member("source_url", "url", required=False),
                _member("parser_version", "text"),
            ],
            "temporal_class": "static",
        },
        "funding": {
            "identity_key": "funder+grant_number",
            "members": [
                _member("funder", "organization_reference"),
                _member("grant_number", "text", required=False),
            ],
            "temporal_class": "static",
        },
        "identifier": {
            "identity_key": "scheme+value",
            "members": [_member("scheme", "text"), _member("value", "text")],
            "temporal_class": "static",
        },
        "publication": {
            "identity_key": "venue+publication_date",
            "members": [
                _member("venue", "venue_reference", required=False),
                _member("publication_date", "date", required=False),
                _member("year", "year"),
            ],
            "temporal_class": "event",
        },
        "reference": {
            "identity_key": "target_paper_id_or_raw_citation",
            "members": [
                _member("target_paper_id", "canonical_identity_id", required=False),
                _member("raw_citation", "text", required=False),
            ],
            "temporal_class": "static",
        },
        "summary": {
            "identity_key": "language+summary_kind+content_hash",
            "members": [
                _member("language", "text"),
                _member("summary_kind", "text"),
                _member("content", "text"),
                _member("content_hash", "sha256"),
            ],
            "temporal_class": "static",
        },
    },
    "patent": {
        "applicant": {
            "identity_key": "normalized_name+applicant_order",
            "members": [
                _member("name", "text"),
                _member("applicant_order", "integer"),
                _member(
                    "canonical_company_id", "canonical_identity_id", required=False
                ),
            ],
            "temporal_class": "static",
        },
        "inventor": {
            "identity_key": "normalized_name+inventor_order",
            "members": [
                _member("name", "text"),
                _member("inventor_order", "integer"),
                _member("affiliation", "organization_reference", required=False),
                _member(
                    "canonical_professor_id", "canonical_identity_id", required=False
                ),
            ],
            "temporal_class": "static",
        },
        "ipc_classification": {
            "identity_key": "version+code",
            "members": [
                _member("code", "text"),
                _member("version", "text"),
                _member("label", "text", required=False),
            ],
            "temporal_class": "static",
        },
        "patent_milestone": {
            "identity_key": "kind+date",
            "members": [_member("kind", "text"), _member("date", "date")],
            "temporal_class": "event",
        },
        "technical_summary": {
            "identity_key": "content_hash+model_version",
            "members": [
                _member("summary_text", "text"),
                _member("technology_effect", "text", required=False),
                _member("content_hash", "sha256"),
                _member("model_version", "text"),
            ],
            "temporal_class": "static",
        },
    },
    "professor": {
        "affiliation_history": {
            "identity_key": "institution+department+title+valid_from",
            "members": [
                _member("institution", "organization_reference"),
                _member("department", "organization_reference", required=False),
                _member("title", "text", required=False),
                _member("valid_from", "date", required=False),
                _member("valid_to", "date", required=False),
            ],
            "temporal_class": "validity_interval",
        },
        "award": {
            "identity_key": "name+issuer+date",
            "members": [
                _member("name", "text"),
                _member("issuer", "organization_reference", required=False),
                _member("date", "date", required=False),
            ],
            "temporal_class": "event",
        },
        "contact": {
            "identity_key": "kind+value",
            "members": [
                _member("kind", "text"),
                _member("value", "text"),
                _member("public_source", "evidence_reference"),
            ],
            "temporal_class": "validity_interval",
        },
        "education_history": {
            "identity_key": "institution+degree+field+start",
            "members": [
                _member("institution", "organization_reference"),
                _member("degree", "text", required=False),
                _member("field", "text", required=False),
                _member("start", "date", required=False),
                _member("end", "date", required=False),
            ],
            "temporal_class": "validity_interval",
        },
        "metric_snapshot": {
            "identity_key": "provider+observed_at",
            "members": [
                _member("provider", "text"),
                _member("observed_at", "aware_datetime"),
                _member("h_index", "integer", required=False),
                _member("citation_count", "integer", required=False),
                _member("paper_count", "integer", required=False),
            ],
            "temporal_class": "event",
        },
        "research_project": {
            "identity_key": "name+funder+valid_from",
            "members": [
                _member("name", "text"),
                _member("funder", "organization_reference", required=False),
                _member("role", "text", required=False),
                _member("valid_from", "date", required=False),
                _member("valid_to", "date", required=False),
            ],
            "temporal_class": "validity_interval",
        },
        "work_history": {
            "identity_key": "organization+role+valid_from",
            "members": [
                _member("organization", "organization_reference"),
                _member("role", "text"),
                _member("valid_from", "date", required=False),
                _member("valid_to", "date", required=False),
            ],
            "temporal_class": "validity_interval",
        },
    },
}


def _shared_field(name: str, shape: str) -> dict[str, Any]:
    return {
        "cardinality": "many" if name == "evidence" else "one",
        "catalog_item_id": f"field.shared.{name}",
        "citation_ids": ["shared.domain_contracts_and_filters"],
        "evidence_obligation": _field_evidence_obligation(name),
        "field_path": name,
        "requiredness": "required",
        "requiredness_scope": "shared_projection_envelope",
        "semantic_use": _field_semantic_use(name),
        "temporal_class": "observation" if name == "last_updated" else "static",
        "value_shape": shape,
    }


def _subobject(domain: str, name: str, definition: dict[str, Any]) -> dict[str, Any]:
    return {
        "cardinality": "many",
        "catalog_item_id": f"subobject.{domain}.{name}",
        "citation_ids": list(DOMAIN_CITATIONS[domain]),
        "evidence_obligation": "supporting_source_assertions_per_member",
        "identity_key": definition["identity_key"],
        "members": definition["members"],
        "parent_domain": domain,
        "subobject_type": name,
        "temporal_class": definition["temporal_class"],
    }


def _role(
    role_id: str,
    description: str,
    *,
    applies_to: str = "relationship",
    required: bool = False,
) -> dict[str, Any]:
    return {
        "applies_to": applies_to,
        "description": description,
        "required": required,
        "role_id": role_id,
    }


def _relationship(
    relationship_type_id: str,
    family: str,
    source_entity_types: tuple[str, ...],
    target_entity_types: tuple[str, ...],
    required_evidence_kinds: tuple[str, ...],
    time_semantics: str,
    eligible_paths: tuple[str, ...],
    citation_ids: tuple[str, ...],
    *,
    endpoint_binding: str | None = None,
    roles: tuple[dict[str, Any], ...] = (),
    role_selection: str = "none",
    semantic_constraints: tuple[str, ...] = (),
) -> dict[str, Any]:
    immutable_lineage = family in {"evidence_lineage", "identity_lifecycle"}
    if family == "identity_lifecycle" and endpoint_binding is None:
        raise ValueError("identity-lifecycle endpoint binding must be row-specific")
    resolved_endpoint_binding = endpoint_binding or (
        "evidence_lineage_metadata"
        if family == "evidence_lineage"
        else "typed_entity_or_subobject"
    )
    return {
        "allowed_states": (
            ("accepted",)
            if immutable_lineage
            else ("accepted", "unresolved", "rejected", "superseded")
        ),
        "citation_ids": tuple(sorted(citation_ids)),
        "direction": "directed",
        "endpoint_binding": resolved_endpoint_binding,
        "eligible_paths": tuple(sorted(set(eligible_paths))),
        "family": family,
        "layer": "canonical",
        "persistence_status": "deferred_to_task_6_5",
        "relationship_type_id": relationship_type_id,
        "required_evidence_kinds": tuple(sorted(required_evidence_kinds)),
        "role_selection": role_selection,
        "roles": roles,
        "scenario_ids": (f"catalog_scenario.{relationship_type_id}",),
        "semantic_constraints": tuple(sorted(semantic_constraints)),
        "source_entity_types": source_entity_types,
        "target_entity_types": target_entity_types,
        "time_semantics": time_semantics,
        "version": "canonical-v2-relationship-v1",
    }


def _relationship_definitions() -> list[dict[str, Any]]:
    identity_citations = ("openspec.canonical_identity", "s2.relationship_families")
    organization_citations = (
        "professor.fields",
        "s2.relationship_families",
        "s2.typed_business_facts",
    )
    scholarly_citations = (
        "paper.professor_attribution",
        "professor.paper_patent_relationships",
        "s2.relationship_families",
    )
    paper_structure_citations = (
        "paper.fields",
        "s2.relationship_families",
        "s2.typed_business_facts",
    )
    patent_citations = (
        "patent.cross_domain_relationships",
        "professor.paper_patent_relationships",
        "s2.relationship_families",
        "s2.typed_business_facts",
    )
    company_citations = (
        "company.business_sources_and_jumps",
        "company.fields_and_personnel",
        "s2.relationship_families",
        "s2.typed_business_facts",
    )
    taxonomy_citations = (
        "shared.domain_contracts_and_filters",
        "s2.relationship_families",
    )
    artifact_lineage_citations = (
        "openspec.artifact_and_record_lineage",
        "openspec.canonical_relationships",
        "s2.relationship_families",
    )
    decision_lineage_citations = (
        "openspec.canonical_relationships",
        "openspec.decision_lineage",
        "s2.relationship_families",
    )
    canonical_domains = ("company", "paper", "patent", "professor")

    definitions = [
        _relationship(
            "source_identity_resolves_to_canonical_identity",
            "identity_lifecycle",
            ("source_identity",),
            canonical_domains,
            ("accepted_identity_decision", "source_identity_assertion"),
            "observed_at",
            ("identity_resolution", "exact_lookup"),
            identity_citations,
            endpoint_binding="source_identity_to_canonical_identity_metadata",
            semantic_constraints=("source_and_target_entity_types_must_match",),
        ),
        _relationship(
            "canonical_identity_merged_into",
            "identity_lifecycle",
            canonical_domains,
            canonical_domains,
            ("accepted_identity_decision", "retained_source_partition"),
            "event_time",
            ("identity_resolution", "audit_lineage"),
            identity_citations,
            endpoint_binding="canonical_identity_lineage",
            semantic_constraints=("source_and_target_entity_types_must_match",),
        ),
        _relationship(
            "canonical_identity_split_from",
            "identity_lifecycle",
            canonical_domains,
            canonical_domains,
            ("accepted_identity_decision", "retained_source_partition"),
            "event_time",
            ("identity_resolution", "audit_lineage"),
            identity_citations,
            endpoint_binding="canonical_identity_lineage",
            semantic_constraints=("source_and_target_entity_types_must_match",),
        ),
        _relationship(
            "identity_decision_supersedes_identity_decision",
            "identity_lifecycle",
            ("identity_decision",),
            ("identity_decision",),
            ("accepted_identity_decision",),
            "event_time",
            ("audit_lineage", "identity_resolution"),
            identity_citations,
            endpoint_binding="identity_decision_lineage_metadata",
            semantic_constraints=(
                "predecessor_and_successor_identity_decisions_share_subject_domain",
            ),
        ),
        _relationship(
            "identity_decision_reverses_identity_decision",
            "identity_lifecycle",
            ("identity_decision",),
            ("identity_decision",),
            ("accepted_reversal_decision",),
            "event_time",
            ("audit_lineage", "identity_resolution"),
            identity_citations,
            endpoint_binding="identity_decision_lineage_metadata",
            semantic_constraints=(
                "predecessor_and_successor_identity_decisions_share_subject_domain",
            ),
        ),
        _relationship(
            "professor_affiliated_with_institution",
            "organization_role",
            ("professor",),
            ("institution",),
            ("public_profile_assertion",),
            "validity_interval",
            ("relationship_traversal", "structured_filter"),
            organization_citations,
        ),
        _relationship(
            "professor_member_of_department",
            "organization_role",
            ("professor",),
            ("department",),
            ("public_profile_assertion",),
            "validity_interval",
            ("relationship_traversal", "structured_filter"),
            organization_citations,
        ),
        _relationship(
            "professor_educated_at_institution",
            "organization_role",
            ("professor",),
            ("institution",),
            ("public_profile_assertion",),
            "validity_interval",
            ("relationship_traversal", "structured_filter"),
            organization_citations,
        ),
        _relationship(
            "professor_held_role_at_non_company_organization",
            "organization_role",
            ("professor",),
            ("institution", "non_company_organization"),
            ("public_profile_assertion",),
            "validity_interval",
            ("relationship_traversal", "structured_filter"),
            organization_citations,
            roles=(
                _role(
                    "position_title",
                    "Source-described role or position",
                    applies_to="source",
                    required=True,
                ),
            ),
            role_selection="exactly_one",
            semantic_constraints=("company_targets_require_professor_company_role",),
        ),
        _relationship(
            "professor_company_role",
            "organization_role",
            ("professor",),
            ("company",),
            ("professor_company_role_assertion",),
            "validity_interval",
            (
                "professor_to_company",
                "company_to_professor",
                "relationship_traversal",
                "structured_filter",
            ),
            (
                "company.cross_domain_relationships",
                "openspec.canonical_relationships",
                "professor.company_relationship",
                "s2.relationship_families",
            ),
            roles=(
                _role("adviser", "Professor advises the Company", applies_to="source"),
                _role(
                    "cooperator",
                    "Professor has evidenced cooperation with the Company",
                    applies_to="source",
                ),
                _role(
                    "employee",
                    "Professor is or was employed by the Company",
                    applies_to="source",
                ),
                _role(
                    "founder",
                    "Professor founded or co-founded the Company",
                    applies_to="source",
                ),
                _role(
                    "investor",
                    "Professor invested in the Company",
                    applies_to="source",
                ),
            ),
            role_selection="exactly_one",
            semantic_constraints=(
                "generic_association_without_a_supported_role_is_not_accepted",
            ),
        ),
        _relationship(
            "company_has_team_member",
            "organization_role",
            ("company",),
            ("person", "professor"),
            ("company_personnel_assertion",),
            "validity_interval",
            ("relationship_traversal", "structured_filter"),
            company_citations,
            roles=(
                _role(
                    "team_role",
                    "Source-described Company team role",
                    applies_to="target",
                    required=True,
                ),
            ),
            role_selection="exactly_one",
        ),
        _relationship(
            "professor_attributed_to_paper",
            "scholarly_output",
            ("professor",),
            ("paper",),
            ("professor_page_or_identity_attribution_assertion",),
            "observed_at",
            (
                "professor_to_paper",
                "paper_to_professor",
                "relationship_traversal",
            ),
            scholarly_citations,
            semantic_constraints=(
                "attribution_basis_is_evidence_metadata_not_business_role",
                "attribution_not_paper_existence",
                "same_name_gate_resolves_person_identity_only",
            ),
        ),
        _relationship(
            "paper_has_author",
            "scholarly_output",
            ("paper",),
            ("person", "professor"),
            ("paper_author_assertion",),
            "none",
            ("relationship_traversal", "structured_filter"),
            paper_structure_citations,
            roles=(
                _role(
                    "author",
                    "Person appears in the Paper author list",
                    applies_to="target",
                    required=True,
                ),
            ),
            role_selection="exactly_one",
        ),
        _relationship(
            "paper_published_in_venue",
            "scholarly_output",
            ("paper",),
            ("venue",),
            ("paper_publication_assertion",),
            "none",
            ("relationship_traversal", "structured_filter"),
            paper_structure_citations,
        ),
        _relationship(
            "paper_references_paper",
            "scholarly_output",
            ("paper",),
            ("paper",),
            ("paper_reference_assertion",),
            "none",
            ("relationship_traversal",),
            paper_structure_citations + ("paper.reference_phase2",),
        ),
        _relationship(
            "patent_has_applicant",
            "intellectual_property",
            ("patent",),
            ("company", "organization", "person"),
            ("patent_applicant_assertion",),
            "none",
            (
                "patent_to_company",
                "company_to_patent",
                "relationship_traversal",
                "structured_filter",
            ),
            patent_citations + ("company.cross_domain_relationships",),
            roles=(
                _role(
                    "applicant",
                    "Named Patent applicant",
                    applies_to="target",
                    required=True,
                ),
            ),
            role_selection="exactly_one",
            semantic_constraints=(
                "applicant_not_owner_or_assignee",
                "company_paths_require_target_type_company_and_accepted_company_identity",
            ),
        ),
        _relationship(
            "patent_has_inventor",
            "intellectual_property",
            ("patent",),
            ("person", "professor"),
            ("patent_inventor_assertion",),
            "none",
            (
                "patent_to_professor",
                "professor_to_patent",
                "relationship_traversal",
                "structured_filter",
            ),
            patent_citations,
            roles=(
                _role(
                    "inventor",
                    "Named Patent inventor",
                    applies_to="target",
                    required=True,
                ),
            ),
            role_selection="exactly_one",
            semantic_constraints=(
                "professor_paths_require_target_type_professor_and_accepted_professor_identity",
            ),
        ),
        _relationship(
            "professor_page_lists_patent",
            "intellectual_property",
            ("professor",),
            ("patent",),
            ("professor_page_declaration",),
            "observed_at",
            (
                "professor_to_patent",
                "patent_to_professor",
                "relationship_traversal",
            ),
            patent_citations,
            semantic_constraints=(
                "page_listing_not_automatically_inventor_identity",
                "no_fuzzy_patent_merge",
            ),
        ),
        _relationship(
            "company_has_product",
            "company_business_product_event",
            ("company",),
            ("product",),
            ("company_source_assertion",),
            "validity_interval",
            ("relationship_traversal", "structured_filter"),
            company_citations + ("company.web_business_updates",),
        ),
        _relationship(
            "company_has_capability",
            "company_business_product_event",
            ("company",),
            ("capability",),
            ("company_source_assertion",),
            "validity_interval",
            ("relationship_traversal", "structured_filter"),
            company_citations + ("company.web_business_updates",),
        ),
        _relationship(
            "company_serves_business_scenario",
            "company_business_product_event",
            ("company",),
            ("business_scenario",),
            ("company_source_assertion",),
            "validity_interval",
            ("relationship_traversal", "structured_filter"),
            company_citations,
        ),
        _relationship(
            "company_has_financing_event",
            "company_business_product_event",
            ("company",),
            ("financing_event",),
            ("company_financing_assertion",),
            "event_time",
            ("relationship_traversal", "structured_filter"),
            company_citations,
        ),
        _relationship(
            "company_has_public_update",
            "company_business_product_event",
            ("company",),
            ("public_update",),
            ("company_public_update_assertion",),
            "event_time",
            ("relationship_traversal", "current_information"),
            company_citations + ("company.web_business_updates",),
        ),
        _relationship(
            "professor_has_research_topic",
            "taxonomy_topic_geography",
            ("professor",),
            ("research_topic",),
            ("source_or_accepted_synthesis_assertion",),
            "validity_interval",
            ("semantic_recall", "structured_filter"),
            taxonomy_citations,
        ),
        _relationship(
            "paper_has_topic",
            "taxonomy_topic_geography",
            ("paper",),
            ("research_topic",),
            ("source_or_accepted_synthesis_assertion",),
            "validity_interval",
            ("semantic_recall", "structured_filter"),
            taxonomy_citations,
        ),
        _relationship(
            "company_in_industry",
            "taxonomy_topic_geography",
            ("company",),
            ("industry",),
            ("company_industry_assertion",),
            "validity_interval",
            ("semantic_recall", "structured_filter"),
            taxonomy_citations,
        ),
        _relationship(
            "company_located_in_geography",
            "taxonomy_topic_geography",
            ("company",),
            ("geography",),
            ("source_geography_assertion",),
            "validity_interval",
            ("relationship_traversal", "structured_filter"),
            taxonomy_citations,
        ),
        _relationship(
            "patent_has_ipc_classification",
            "taxonomy_topic_geography",
            ("patent",),
            ("ipc_classification",),
            ("patent_ipc_assertion",),
            "none",
            ("semantic_recall", "structured_filter"),
            taxonomy_citations,
        ),
        _relationship(
            "artifact_derived_from_artifact",
            "evidence_lineage",
            ("artifact",),
            ("artifact",),
            ("artifact_manifest_reference",),
            "event_time",
            ("audit_lineage",),
            artifact_lineage_citations,
        ),
        _relationship(
            "source_record_parsed_from_artifact",
            "evidence_lineage",
            ("source_record",),
            ("artifact",),
            ("source_record_artifact_reference",),
            "observed_at",
            ("audit_lineage",),
            artifact_lineage_citations,
        ),
        _relationship(
            "assertion_supported_by_source_record",
            "evidence_lineage",
            ("field_assertion", "identity_assertion", "relationship_assertion"),
            ("source_record",),
            ("retained_source_record",),
            "observed_at",
            ("audit_lineage",),
            decision_lineage_citations,
        ),
        _relationship(
            "canonical_decision_selects_assertion",
            "evidence_lineage",
            ("field_decision", "identity_decision", "relationship_decision"),
            ("field_assertion", "identity_assertion", "relationship_assertion"),
            ("accepted_canonical_decision",),
            "event_time",
            ("audit_lineage",),
            decision_lineage_citations,
            semantic_constraints=(
                "decision_and_assertion_families_and_subjects_must_match",
            ),
        ),
        _relationship(
            "canonical_decision_uses_policy",
            "evidence_lineage",
            ("field_decision", "identity_decision", "relationship_decision"),
            ("policy",),
            ("versioned_policy_reference",),
            "event_time",
            ("audit_lineage",),
            decision_lineage_citations,
        ),
        _relationship(
            "canonical_decision_produced_by_run",
            "evidence_lineage",
            ("field_decision", "identity_decision", "relationship_decision"),
            ("decision_run",),
            ("decision_run_reference",),
            "event_time",
            ("audit_lineage",),
            decision_lineage_citations,
        ),
    ]
    for definition in definitions:
        direction_scenarios = {
            f"traversal_scenario.{path}"
            for path in definition["eligible_paths"]
            if path in DIRECTION_SCENARIOS
        }
        definition["scenario_ids"] = tuple(
            sorted({*definition["scenario_ids"], *direction_scenarios})
        )
    return sorted(definitions, key=lambda item: item["relationship_type_id"])


def _scenario_accounting(
    relationships: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    relationship_by_id = {
        relationship["relationship_type_id"]: relationship
        for relationship in relationships
    }
    for relationship_id, relationship in sorted(relationship_by_id.items()):
        if relationship_id in ABSENT_RELATIONSHIP_EVIDENCE:
            outcome = "absent"
            basis = "accepted S2 evidence does not contain a verified local instance"
        elif relationship_id in INSUFFICIENT_RELATIONSHIP_EVIDENCE:
            outcome = "insufficient_evidence"
            basis = "accepted S2 evidence is sparse or not identity-resolved enough for an accepted edge"
        else:
            outcome = "supported"
            basis = "accepted S2 evidence contains source material without implying an accepted edge"
        scenarios.append(
            {
                "citation_ids": relationship["citation_ids"],
                "evidence_basis": basis,
                "evidence_outcome": outcome,
                "family": relationship["family"],
                "relationship_type_ids": (relationship_id,),
                "scenario_id": f"catalog_scenario.{relationship_id}",
                "scenario_kind": "relationship_type",
                "user_effect": (
                    "Users can retrieve or audit "
                    f"{relationship_id.replace('_', ' ')} only from retained evidence."
                ),
            }
        )
    for direction, definition in sorted(DIRECTION_SCENARIOS.items()):
        relation_citations = {
            citation_id
            for relationship_id in definition["relationship_type_ids"]
            for citation_id in relationship_by_id[relationship_id]["citation_ids"]
        }
        outcome = definition["evidence_outcome"]
        scenarios.append(
            {
                "citation_ids": tuple(
                    sorted(
                        {
                            *relation_citations,
                            "multi_turn.cross_domain_directions",
                            "s2.relationship_families",
                        }
                    )
                ),
                "evidence_basis": (
                    "accepted S2 source evidence supports later traversal"
                    if outcome == "supported"
                    else "accepted S2 evidence requires identity-aware fusion or recollection"
                ),
                "evidence_outcome": outcome,
                "family": definition["family"],
                "relationship_type_ids": definition["relationship_type_ids"],
                "scenario_id": f"traversal_scenario.{direction}",
                "scenario_kind": "traversal_direction",
                "traversal_direction": direction,
                "user_effect": (
                    f"Users can progressively traverse {direction.replace('_', ' ')} "
                    "with explicit evidence limitations."
                ),
            }
        )
    return sorted(scenarios, key=lambda item: item["scenario_id"])


def _deferred_owners() -> list[dict[str, Any]]:
    return [
        {
            "citation_ids": tuple(sorted(definition["citation_ids"])),
            "deferred_id": deferred_id,
            "owner": definition["owner"],
            "scope": definition["scope"],
        }
        for deferred_id, definition in sorted(DEFERRED_OWNERS.items())
    ]


def _source_manifest_with_citations(seed: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = seed.get("source_manifest")
    if not isinstance(manifest, list):
        raise ValueError("catalog seed source_manifest must be a list")
    manifest_by_path = {
        source["path"]: dict(source)
        for source in manifest
        if isinstance(source, dict) and isinstance(source.get("path"), str)
    }
    for path, definition in NEW_AUTHORITY_SOURCES.items():
        manifest_by_path[path] = {
            "authority_tier": definition["authority_tier"],
            "citations": list(definition["citations"]),
            "path": path,
            "sha256": definition["sha256"],
        }
    merged_manifest: list[dict[str, Any]] = []
    for source in manifest_by_path.values():
        entry = dict(source)
        citations = {
            citation["citation_id"]: citation for citation in entry.get("citations", [])
        }
        source_path = entry.get("path")
        if not isinstance(source_path, str):
            raise ValueError("catalog seed authority source path must be a string")
        for citation in SOURCE_CITATION_ADDITIONS.get(source_path, ()):
            citations[citation["citation_id"]] = citation
        entry["citations"] = [citations[key] for key in sorted(citations)]
        merged_manifest.append(entry)
    return sorted(merged_manifest, key=lambda entry: entry["path"])


def build_catalog(seed: dict[str, Any]) -> dict[str, Any]:
    catalog = dict(seed)
    catalog["source_manifest"] = _source_manifest_with_citations(seed)
    catalog["shared_projection_fields"] = [
        _shared_field(name, shape) for name, shape in sorted(SHARED_FIELDS.items())
    ]
    catalog["domains"] = [
        {
            "domain": domain,
            "fields": [
                _field(domain, name) for name in sorted(DOMAIN_FIELD_NAMES[domain])
            ],
            "subobjects": [
                _subobject(domain, name, definition)
                for name, definition in sorted(SUBOBJECT_DEFINITIONS[domain].items())
            ],
        }
        for domain in sorted(DOMAIN_FIELD_NAMES)
    ]
    catalog["relationship_families"] = [
        {
            "citation_ids": tuple(sorted(definition["citation_ids"])),
            "family_id": family_id,
            "semantic_scope": definition["semantic_scope"],
        }
        for family_id, definition in sorted(RELATIONSHIP_FAMILIES.items())
    ]
    catalog["layer_contracts"] = sorted(LAYER_CONTRACTS, key=lambda item: item["layer"])
    catalog["relationships"] = _relationship_definitions()
    catalog["scenario_accounting"] = _scenario_accounting(catalog["relationships"])
    catalog["deferred_owners"] = _deferred_owners()
    catalog.pop("content_sha256", None)
    catalog["content_sha256"] = catalog_content_sha256(catalog)
    return catalog


def _load_seed(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("catalog seed must be a JSON object")
    return value


def confined_catalog_path(catalog_path: Path, *, output_root: Path = S6_ROOT) -> Path:
    """Resolve a non-symlink catalog path inside the approved output root."""
    root = output_root.resolve(strict=True)
    if catalog_path.is_symlink():
        raise ValueError(f"catalog output cannot be a symlink: {catalog_path}")
    try:
        parent = catalog_path.parent.resolve(strict=True)
    except OSError as exc:
        raise ValueError(
            f"catalog output parent is unavailable: {catalog_path}"
        ) from exc
    candidate = parent / catalog_path.name
    if not candidate.is_relative_to(root):
        raise ValueError(
            f"catalog output must stay inside the approved output root: {root}"
        )
    return candidate


def write_validated_catalog(
    payload: bytes,
    *,
    catalog_path: Path,
    repo_root: Path,
    output_root: Path = S6_ROOT,
) -> None:
    """Validate a same-filesystem temporary file before atomic replacement."""
    target = confined_catalog_path(catalog_path, output_root=output_root)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        load_and_validate_catalog(
            repo_root=repo_root,
            catalog_path=temporary_path,
        )
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    catalog_path = confined_catalog_path(args.catalog)
    built = build_catalog(_load_seed(catalog_path))
    payload = canonical_catalog_bytes(built)
    if args.write:
        write_validated_catalog(
            payload,
            catalog_path=catalog_path,
            repo_root=args.repo_root,
        )
    else:
        if catalog_path.read_bytes() != payload:
            raise SystemExit("frozen domain catalog does not match deterministic build")
        load_and_validate_catalog(
            repo_root=args.repo_root,
            catalog_path=catalog_path,
        )


if __name__ == "__main__":
    main()
