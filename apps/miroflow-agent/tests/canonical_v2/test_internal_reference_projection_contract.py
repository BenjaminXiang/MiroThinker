from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import inspect
from importlib import import_module
import json
import os
from pathlib import Path
import sqlite3
from threading import Barrier
from typing import Any, Callable

from pydantic import TypeAdapter, ValidationError
import psycopg
from psycopg.types.json import Jsonb
import pytest
from sqlalchemy.engine import make_url

from src.data_agents.canonical_v2 import (
    canonical_identity_resolution as identity_models,
)
from src.data_agents.canonical_v2 import domain_inclusion as inclusion_models
from src.data_agents.canonical_v2 import domain_projection as projection_models
from src.data_agents.canonical_v2 import path_eligibility as eligibility_models
from src.data_agents.canonical_v2.canonical_decision_engine import (
    CurrentFieldSelection,
)
from src.data_agents.canonical_v2.canonical_identity_resolution import (
    SourceIdentityAssignment,
)
from src.data_agents.canonical_v2.contracts import CanonicalDecision
from src.data_agents.canonical_v2.contracts import CanonicalIdentity
from src.data_agents.canonical_v2.contracts import CanonicalIdentityState
from src.data_agents.canonical_v2.contracts import DecisionMethod
from src.data_agents.canonical_v2.contracts import DecisionState
from src.data_agents.canonical_v2.contracts import PolicyKind
from src.data_agents.canonical_v2.contracts import PolicyReference
from src.data_agents.canonical_v2.contracts import PolicyDecision
from src.data_agents.canonical_v2.contracts import PolicyOutcome
from src.data_agents.canonical_v2.contracts import RelationshipDecision
from src.data_agents.canonical_v2.contracts import SourceAssertion
from src.data_agents.canonical_v2.contracts import TemporalDateValue
from src.data_agents.canonical_v2.contracts import TemporalInstantValue
from src.data_agents.canonical_v2.domain_catalog import CATALOG_CONTENT_SHA256
from src.data_agents.canonical_v2.domain_catalog import CATALOG_SCHEMA_VERSION
from src.data_agents.canonical_v2.domain_catalog import CATALOG_VERSION
from src.data_agents.canonical_v2.internal_reference_catalog import (
    REFERENCE_CATALOG_CONTENT_SHA256,
)
from src.data_agents.canonical_v2.internal_reference_catalog import (
    REFERENCE_CATALOG_SCHEMA_VERSION,
)
from src.data_agents.canonical_v2.internal_reference_catalog import (
    REFERENCE_CATALOG_VERSION,
)
from src.data_agents.canonical_v2.relationship_projection import (
    RelationshipProjectionRequest,
)
from src.data_agents.canonical_v2.rebuild_write_gate import RebuildWriteGateError


TARGET_MODULE = "src.data_agents.canonical_v2.internal_reference_projection"
RED_REASON = "Task 6.10 RED: Technology/relationship projection is not implemented"
CANDIDATE_PROJECTION_TARGET_MODULE = "src.data_agents.canonical_v2.candidate_projection"
INDEX_PROJECTION_TARGET_MODULE = "src.data_agents.canonical_v2.index_projection"
ISOLATED_INDEX_PROJECTION_TARGET_MODULE = (
    "src.data_agents.canonical_v2.index_projection_isolated"
)
ISOLATED_RELEASE_PUBLICATION_TARGET_MODULE = (
    "src.data_agents.canonical_v2.release_publication_isolated"
)
ISOLATED_KNOWLEDGE_READ_TARGET_MODULE = (
    "src.data_agents.canonical_v2.knowledge_read_isolated"
)
NOW = datetime(2026, 7, 13, 17, 0, tzinfo=timezone.utc)
RELEASE_ID = "candidate-s6r-r1"
PUBLIC_DOMAINS = ("company", "paper", "patent", "professor")
INTERNAL_REFERENCE_TYPES = ("person", "technology_concept", "technology_route")
S8P1_LEGACY_PLAN_CONTENT_SHA256 = (
    "c89a484f9a7fb39ff604859545d98ee76daac77346ab12b589b68d06b45d5675"
)
S8P1_LEGACY_PLAN_SERIALIZED_SHA256 = (
    "e25a67563bd026475affcfc5a7bc20938c860a65dfb764f4da54a5a36bb0fefb"
)
S8P2_LEGACY_PROPOSAL_CONTENT_SHA256 = (
    "935d3c6805603b82339331e82390254ca1f49e8f2b3be9c5e5988fb167dc4acd"
)
S8P2_LEGACY_PROPOSAL_SERIALIZED_SHA256 = (
    "d078246e79cfe8b8c5f6ed1c5d5ef3b4a0eb6923369a41b940cc5794b9e65e1b"
)
S8P2_LEGACY_PLANNING_POLICY_CONTENT_SHA256 = (
    "b16b7e156dce15205104bd2f42d203ad16eaae05cf4c6e69af217c5660ffdefd"
)
S8R1_RELATIONSHIP_LANE_REQUEST_CONTENT_SHA256 = (
    "78d73eb7738c5ddfe839f3404ae58ab7c51ffadf2b4292d2016659692ce026b2"
)
S8R1_RELATIONSHIP_LANE_REQUEST_SERIALIZED_SHA256 = (
    "ad3f18275fba9260ff8e0d5f680276c1fecb74f6e1bb3a8bdce427205b8520c1"
)
S8R1_RELATIONSHIP_TRACE_CONTENT_SHA256 = (
    "196e432d691bf442dd251dd128f37197e8d74154e4ddf327f1ac70d276fc4ca2"
)
S8R1_RELATIONSHIP_TRACE_SERIALIZED_SHA256 = (
    "a1732dff319b84ecae9bd0819ea2d2c0796c80661f660eb6fad5768e4446db1d"
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class _MissingTargetModule(RuntimeError):
    """Exact Task 6.9 RED sentinel; nested missing dependencies fail normally."""


class _MissingRelationshipContract(RuntimeError):
    """Exact RED sentinel for the absent internal-reference registry input."""


class _MissingTechnologyContract(RuntimeError):
    """Exact sentinel while the S6R4 Technology half remains unimplemented."""


class _MissingCandidateProjectionModule(RuntimeError):
    """Exact Task 7.3 RED sentinel; nested missing dependencies fail normally."""


class _MissingIndexProjectionModule(RuntimeError):
    """Exact Task 7.4 RED sentinel; nested missing dependencies fail normally."""


class _MissingIsolatedReleasePublicationModule(RuntimeError):
    """Exact Task 7.7 RED sentinel; nested missing dependencies fail normally."""


class _MissingIsolatedKnowledgeReadModule(RuntimeError):
    """Exact S8L1 RED sentinel; nested missing dependencies fail normally."""


class _MissingIsolatedStructuredLookupAdapter(RuntimeError):
    """Exact S8L2 RED sentinel for the missing structured factory."""


class _MissingIsolatedReleaseQueryPlannerFactory(RuntimeError):
    """Exact S8P1 RED sentinel for the missing release-bound planner factory."""


class _MissingIsolatedReleaseKnowledgeReadFactory(RuntimeError):
    """Exact S8E1 RED sentinel for the missing release-bound read factory."""


class _MissingIsolatedLexicalLookupAdapter(RuntimeError):
    """Exact S8L3 RED sentinel for the missing lexical factory."""


class _MissingIsolatedVectorRecallAdapter(RuntimeError):
    """Exact S8V1 RED sentinel for the missing vector factory."""


class _MissingProfessorVectorViewSelection(RuntimeError):
    """Exact S8V2 RED sentinel for the absent typed Professor selector."""


class _MissingIsolatedInternalReferenceLookupAdapter(RuntimeError):
    """Exact S8IR1 RED sentinel for the missing release-bound internal lane."""


class _MissingIsolatedRelationshipLookupAdapter(RuntimeError):
    """Exact S8R1 RED sentinel for the missing release-bound relationship lane."""


class _MissingS8R2PublicRelationshipTraversal(RuntimeError):
    """Exact S8R2 RED sentinel for the absent public relationship seam."""


class _MissingS8R3ProfessorPaperTraversal(RuntimeError):
    """Exact S8R3 RED sentinel for the absent Professor-to-Paper seam."""


class _MissingS8R4PaperProfessorTraversal(RuntimeError):
    """Exact S8R4 RED sentinel for the absent Paper-to-Professor seam."""


class _MissingS8R5PatentCompanyTraversal(RuntimeError):
    """Exact S8R5 RED sentinel for the absent Patent-to-Company seam."""


class _MissingS8CAggregateRuntimeClosure(RuntimeError):
    """Exact S8C RED sentinel for the absent release-bound composition ports."""


class _MissingS7JSemanticEligibilityLineage(RuntimeError):
    """Exact S7J RED sentinel for missing vector decision effects."""


class _MissingS7KRelationshipPublicationAuthority(RuntimeError):
    """Exact S7K RED sentinel for the absent release relationship authority."""


class _MissingS8P2AssessmentIntentContract(RuntimeError):
    """Exact S8P2 RED sentinel for the absent read-side assessment intent."""


class _MissingS8P2MaterialPartsContract(RuntimeError):
    """Exact Candidate-review RED sentinel for missing material-part planning."""


def _module() -> Any:
    try:
        return import_module(TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != TARGET_MODULE:
            raise AssertionError(
                f"{TARGET_MODULE} has an unexpected missing dependency: {exc.name}"
            ) from exc
        raise _MissingTargetModule(
            f"exact target module is absent: {TARGET_MODULE}"
        ) from exc


def _candidate_projection_module() -> Any:
    try:
        return import_module(CANDIDATE_PROJECTION_TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != CANDIDATE_PROJECTION_TARGET_MODULE:
            raise AssertionError(
                f"{CANDIDATE_PROJECTION_TARGET_MODULE} has an unexpected "
                f"missing dependency: {exc.name}"
            ) from exc
        raise _MissingCandidateProjectionModule(
            f"exact target module is absent: {CANDIDATE_PROJECTION_TARGET_MODULE}"
        ) from exc


def _isolated_release_publication_module() -> Any:
    try:
        return import_module(ISOLATED_RELEASE_PUBLICATION_TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != ISOLATED_RELEASE_PUBLICATION_TARGET_MODULE:
            raise AssertionError(
                f"{ISOLATED_RELEASE_PUBLICATION_TARGET_MODULE} has an unexpected "
                f"missing dependency: {exc.name}"
            ) from exc
        raise _MissingIsolatedReleasePublicationModule(
            "exact target module is absent: "
            f"{ISOLATED_RELEASE_PUBLICATION_TARGET_MODULE}"
        ) from exc


def _isolated_knowledge_read_module() -> Any:
    try:
        return import_module(ISOLATED_KNOWLEDGE_READ_TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != ISOLATED_KNOWLEDGE_READ_TARGET_MODULE:
            raise AssertionError(
                f"{ISOLATED_KNOWLEDGE_READ_TARGET_MODULE} has an unexpected "
                f"missing dependency: {exc.name}"
            ) from exc
        raise _MissingIsolatedKnowledgeReadModule(
            f"exact target module is absent: {ISOLATED_KNOWLEDGE_READ_TARGET_MODULE}"
        ) from exc


def _isolated_structured_lookup_factory() -> Any:
    module = _isolated_knowledge_read_module()
    try:
        return module.create_isolated_structured_lookup_adapter
    except AttributeError as exc:
        if exc.name != "create_isolated_structured_lookup_adapter":
            raise
        raise _MissingIsolatedStructuredLookupAdapter(
            "exact target symbol is absent: "
            f"{ISOLATED_KNOWLEDGE_READ_TARGET_MODULE}."
            "create_isolated_structured_lookup_adapter"
        ) from exc


def _isolated_release_query_planner_factory() -> Any:
    module = _isolated_knowledge_read_module()
    try:
        return module.create_isolated_release_query_planner
    except AttributeError as exc:
        if exc.name != "create_isolated_release_query_planner":
            raise
        raise _MissingIsolatedReleaseQueryPlannerFactory(
            "exact target symbol is absent: "
            f"{ISOLATED_KNOWLEDGE_READ_TARGET_MODULE}."
            "create_isolated_release_query_planner"
        ) from exc


def _isolated_release_knowledge_read_factory() -> Any:
    module = _isolated_knowledge_read_module()
    try:
        return module.create_isolated_release_knowledge_read
    except AttributeError as exc:
        if exc.name != "create_isolated_release_knowledge_read":
            raise
        raise _MissingIsolatedReleaseKnowledgeReadFactory(
            "exact target symbol is absent: "
            f"{ISOLATED_KNOWLEDGE_READ_TARGET_MODULE}."
            "create_isolated_release_knowledge_read"
        ) from exc


def _isolated_lexical_lookup_factory() -> Any:
    module = _isolated_knowledge_read_module()
    try:
        return module.create_isolated_lexical_lookup_adapter
    except AttributeError as exc:
        if exc.name != "create_isolated_lexical_lookup_adapter":
            raise
        raise _MissingIsolatedLexicalLookupAdapter(
            "exact target symbol is absent: "
            f"{ISOLATED_KNOWLEDGE_READ_TARGET_MODULE}."
            "create_isolated_lexical_lookup_adapter"
        ) from exc


def _isolated_vector_recall_factory() -> Any:
    module = _isolated_knowledge_read_module()
    try:
        return module.create_isolated_vector_recall_adapter
    except AttributeError as exc:
        if exc.name != "create_isolated_vector_recall_adapter":
            raise
        raise _MissingIsolatedVectorRecallAdapter(
            "exact target symbol is absent: "
            f"{ISOLATED_KNOWLEDGE_READ_TARGET_MODULE}."
            "create_isolated_vector_recall_adapter"
        ) from exc


def _professor_vector_view_module() -> Any:
    module = import_module("src.data_agents.canonical_v2.knowledge_read")
    owners = (
        module.RecordedPlanningProposal,
        module.RetrievalPlan,
        module.LaneRequest,
    )
    if any("professor_vector_view" not in owner.model_fields for owner in owners):
        raise _MissingProfessorVectorViewSelection(
            "exact typed field is absent from RecordedPlanningProposal, "
            "RetrievalPlan, or LaneRequest: professor_vector_view"
        )
    return module


def _isolated_internal_reference_lookup_contract() -> tuple[Any, Any, Any]:
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    isolated_module = _isolated_knowledge_read_module()
    missing: list[str] = []
    if "internal_reference_queries" not in read_module.LaneRequest.model_fields:
        missing.append("LaneRequest.internal_reference_queries")

    trace_type = getattr(read_module, "LocalInternalReferenceTrace", None)
    required_trace_fields = {
        "target_id",
        "target_marker_sha256",
        "manifest_sha256",
        "index_result_content_sha256",
        "document_id",
        "release_id",
        "projection_id",
        "reference_type",
        "internal_reference_id",
        "internal_projection_content_sha256",
        "reference_record_content_sha256",
        "internal_lookup_content_sha256",
        "internal_lookup_source_evidence_ids",
        "public_origin_domain",
        "public_origin_canonical_id",
        "public_origin_anchor_id",
        "public_origin_anchor_content_sha256",
        "public_origin_root_projection_content_sha256",
        "lane_request_content_sha256",
        "claim_subject_id",
        "claim_predicate",
        "claim_value",
        "claim_evidence_ids",
        "matched_filter_facts",
        "publication_verification_evidence_ids",
        "raw_candidate_id",
        "evidence_id",
        "content_sha256",
        "path",
        "execution_lane",
    }
    if trace_type is None:
        missing.append("LocalInternalReferenceTrace")
    else:
        missing_trace_fields = required_trace_fields - set(trace_type.model_fields)
        if missing_trace_fields:
            missing.extend(
                f"LocalInternalReferenceTrace.{name}"
                for name in sorted(missing_trace_fields)
            )
        elif (
            trace_type.model_fields["path"].default != "internal_reference_lookup"
            or trace_type.model_fields["execution_lane"].default != "internal_reference"
        ):
            missing.append("LocalInternalReferenceTrace discriminator")

    internal_factory = getattr(
        isolated_module,
        "create_isolated_internal_reference_lookup_adapter",
        None,
    )
    if internal_factory is None:
        missing.append("create_isolated_internal_reference_lookup_adapter")
    release_factory = getattr(
        isolated_module,
        "create_isolated_release_knowledge_read",
        None,
    )
    if release_factory is None:
        missing.append("create_isolated_release_knowledge_read")
    else:
        release_parameters = set(inspect.signature(release_factory).parameters)
        for parameter in (
            "index_projection_request",
            "release_institution_catalog",
        ):
            if parameter not in release_parameters:
                missing.append(f"create_isolated_release_knowledge_read.{parameter}")

    if missing:
        raise _MissingIsolatedInternalReferenceLookupAdapter(
            "exact S8IR1 contract is absent: " + ", ".join(missing)
        )
    return read_module, internal_factory, release_factory


def _isolated_relationship_lookup_contract() -> tuple[Any, Any, Any]:
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    isolated_module = _isolated_knowledge_read_module()
    missing: list[str] = []
    for field_name in ("relationship_paths", "relationship_reference_queries"):
        if field_name not in read_module.LaneRequest.model_fields:
            missing.append(f"LaneRequest.{field_name}")

    trace_type = getattr(read_module, "LocalRelationshipTrace", None)
    if trace_type is None:
        missing.append("LocalRelationshipTrace")
    elif not {"path", "execution_lane"} <= set(trace_type.model_fields):
        missing.append("LocalRelationshipTrace discriminator fields")
    elif (
        trace_type.model_fields["path"].default != "relationship_traversal"
        or trace_type.model_fields["execution_lane"].default != "relationship"
    ):
        missing.append("LocalRelationshipTrace discriminator")

    relationship_factory = getattr(
        isolated_module,
        "create_isolated_relationship_lookup_adapter",
        None,
    )
    if relationship_factory is None:
        missing.append("create_isolated_relationship_lookup_adapter")
    release_factory = getattr(
        isolated_module,
        "create_isolated_release_knowledge_read",
        None,
    )
    if release_factory is None:
        missing.append("create_isolated_release_knowledge_read")

    if missing:
        raise _MissingIsolatedRelationshipLookupAdapter(
            "exact S8R1 contract is absent: " + ", ".join(missing)
        )
    return read_module, relationship_factory, release_factory


def _s8r2_public_relationship_contract() -> tuple[Any, Any, Any]:
    read_module, relationship_factory, release_factory = (
        _isolated_relationship_lookup_contract()
    )
    missing: list[str] = []
    enumeration_field = read_module.LaneRequest.model_fields.get(
        "relationship_enumeration_policy"
    )
    if enumeration_field is None:
        missing.append("LaneRequest.relationship_enumeration_policy")
    elif enumeration_field.is_required() or enumeration_field.default is not None:
        missing.append("LaneRequest.relationship_enumeration_policy optional default")

    trace_type = getattr(read_module, "LocalCanonicalRelationshipTrace", None)
    if trace_type is None:
        missing.append("LocalCanonicalRelationshipTrace")
    elif not {"path", "execution_lane"} <= set(trace_type.model_fields):
        missing.append("LocalCanonicalRelationshipTrace discriminator fields")
    elif (
        trace_type.model_fields["path"].default != "canonical_relationship_traversal"
        or trace_type.model_fields["execution_lane"].default != "relationship"
    ):
        missing.append("LocalCanonicalRelationshipTrace discriminator")

    if missing:
        raise _MissingS8R2PublicRelationshipTraversal(
            "exact S8R2 public relationship contract is absent: " + ", ".join(missing)
        )
    return read_module, relationship_factory, release_factory


def _s8r3_public_relationship_contract() -> tuple[Any, Any, Any]:
    read_module, relationship_factory, release_factory = (
        _s8r2_public_relationship_contract()
    )
    missing: list[str] = []
    trace_type = getattr(read_module, "LocalProfessorPaperRelationshipTrace", None)
    if trace_type is None:
        missing.append("LocalProfessorPaperRelationshipTrace")
    elif not {"path", "execution_lane"} <= set(trace_type.model_fields):
        missing.append("LocalProfessorPaperRelationshipTrace discriminator fields")
    elif (
        trace_type.model_fields["path"].default
        != "professor_paper_relationship_traversal"
        or trace_type.model_fields["execution_lane"].default != "relationship"
    ):
        missing.append("LocalProfessorPaperRelationshipTrace discriminator")

    if missing:
        raise _MissingS8R3ProfessorPaperTraversal(
            "exact S8R3 Professor-to-Paper contract is absent: " + ", ".join(missing)
        )
    return read_module, relationship_factory, release_factory


def _s8r4_public_relationship_contract() -> tuple[Any, Any, Any]:
    read_module, relationship_factory, release_factory = (
        _s8r3_public_relationship_contract()
    )
    missing: list[str] = []
    trace_type = getattr(read_module, "LocalPaperProfessorRelationshipTrace", None)
    if trace_type is None:
        missing.append("LocalPaperProfessorRelationshipTrace")
    elif not {"path", "execution_lane"} <= set(trace_type.model_fields):
        missing.append("LocalPaperProfessorRelationshipTrace discriminator fields")
    elif (
        trace_type.model_fields["path"].default
        != "paper_professor_relationship_traversal"
        or trace_type.model_fields["execution_lane"].default != "relationship"
    ):
        missing.append("LocalPaperProfessorRelationshipTrace discriminator")

    if missing:
        raise _MissingS8R4PaperProfessorTraversal(
            "exact S8R4 Paper-to-Professor contract is absent: " + ", ".join(missing)
        )
    return read_module, relationship_factory, release_factory


def _s8r5_public_relationship_contract() -> tuple[Any, Any, Any]:
    read_module, relationship_factory, release_factory = (
        _s8r4_public_relationship_contract()
    )
    missing: list[str] = []
    trace_type = getattr(read_module, "LocalPatentCompanyRelationshipTrace", None)
    if trace_type is None:
        missing.append("LocalPatentCompanyRelationshipTrace")
    elif not {"path", "execution_lane"} <= set(trace_type.model_fields):
        missing.append("LocalPatentCompanyRelationshipTrace discriminator fields")
    elif (
        trace_type.model_fields["path"].default
        != "patent_company_relationship_traversal"
        or trace_type.model_fields["execution_lane"].default != "relationship"
    ):
        missing.append("LocalPatentCompanyRelationshipTrace discriminator")

    if missing:
        raise _MissingS8R5PatentCompanyTraversal(
            "exact S8R5 Patent-to-Company contract is absent: " + ", ".join(missing)
        )
    return read_module, relationship_factory, release_factory


def _s8c_aggregate_runtime_contract() -> tuple[Any, Any, Any]:
    isolated_module = _isolated_knowledge_read_module()
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    release_factory = getattr(
        isolated_module,
        "create_isolated_release_knowledge_read",
        None,
    )
    if release_factory is None:
        raise _MissingS8CAggregateRuntimeClosure(
            "exact S8C release-bound factory is absent: "
            "create_isolated_release_knowledge_read"
        )

    required_ports = {
        "identity_fuser",
        "reranker",
        "sufficiency_decider",
        "supplemental_search",
        "web_handle_resolver",
        "accepted_identity_lookup",
        "web_handle_ttl",
    }
    parameters = inspect.signature(release_factory).parameters
    missing_ports = sorted(
        port
        for port in required_ports
        if port not in parameters
        or parameters[port].kind is not inspect.Parameter.KEYWORD_ONLY
    )
    if missing_ports:
        raise _MissingS8CAggregateRuntimeClosure(
            "exact S8C release-bound composition ports are absent: "
            + ", ".join(missing_ports)
        )
    return read_module, isolated_module, release_factory


def _s8p2_assessment_intent_type() -> Any:
    module = import_module("src.data_agents.canonical_v2.knowledge_read")
    try:
        return module.AssessmentIntent
    except AttributeError as exc:
        if exc.name != "AssessmentIntent":
            raise
        raise _MissingS8P2AssessmentIntentContract(
            "exact target symbol is absent: "
            "src.data_agents.canonical_v2.knowledge_read.AssessmentIntent"
        ) from exc


def _index_projection_module() -> Any:
    try:
        return import_module(INDEX_PROJECTION_TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != INDEX_PROJECTION_TARGET_MODULE:
            raise AssertionError(
                f"{INDEX_PROJECTION_TARGET_MODULE} has an unexpected "
                f"missing dependency: {exc.name}"
            ) from exc
        raise _MissingIndexProjectionModule(
            f"exact target module is absent: {INDEX_PROJECTION_TARGET_MODULE}"
        ) from exc


def _isolated_index_projection_module() -> Any:
    return import_module(ISOLATED_INDEX_PROJECTION_TARGET_MODULE)


def _technology_module() -> Any:
    try:
        module = _module()
    except _MissingTargetModule as exc:
        raise _MissingTechnologyContract(
            "internal reference projection module is not implemented"
        ) from exc
    required = (
        "TechnologyEvidenceLocator",
        "TechnologyConceptProjection",
        "TechnologyRouteProjection",
        "UnresolvedTechnologyReference",
    )
    missing = tuple(name for name in required if not hasattr(module, name))
    if missing:
        raise _MissingTechnologyContract(
            "Technology projection contract is missing: " + ", ".join(missing)
        )
    request_fields = module.InternalReferenceProjectionRequest.model_fields
    required_request_fields = {
        "technology_identity_resolution_request",
        "technology_identity_resolution_result",
        "technology_evidence_locators",
    }
    missing_request_fields = required_request_fields - set(request_fields)
    forbidden_request_fields = {
        "technology_identities",
        "technology_concept_seeds",
        "technology_route_seeds",
        "technology_evidence_relations",
    } & set(request_fields)
    if missing_request_fields or forbidden_request_fields:
        raise _MissingTechnologyContract(
            "Technology projection request is not the closed evidence contract: "
            f"missing={sorted(missing_request_fields)}, "
            f"forbidden={sorted(forbidden_request_fields)}"
        )
    return module


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _person_source(
    source_kind: str,
    name: str,
    *,
    orcid: str | None,
    source_record_id: str,
    source_id_suffix: str | None = None,
) -> tuple[Any, tuple[Any, ...]]:
    source_token = source_id_suffix or source_kind
    source_identity_id = f"source-person:{source_token}"
    normalized_keys = {"name_key": name}
    if orcid is not None:
        normalized_keys["orcid"] = orcid
    source = identity_models.SourceIdentity(
        source_identity_id=source_identity_id,
        source_system=f"fixture:{source_token}",
        source_key=f"person:{source_token}",
        entity_type="person",
        source_record_ids=(source_record_id,),
        normalized_keys=normalized_keys,
        first_observed_at=NOW - timedelta(days=1),
        last_observed_at=NOW,
        state=identity_models.SourceIdentityState.active,
    )
    assertions = [
        identity_models.SourceAssertion(
            assertion_id=f"assertion:person:{source_token}:name",
            source_record_id=source_record_id,
            source_identity_id=source.source_identity_id,
            subject_entity_type="person",
            field_path="identity.name",
            value=name,
            observed_at=NOW,
            assertion_run_id="s6r-person-identity-assertions",
        )
    ]
    if orcid is not None:
        assertions.append(
            identity_models.SourceAssertion(
                assertion_id=f"assertion:person:{source_token}:orcid",
                source_record_id=source_record_id,
                source_identity_id=source.source_identity_id,
                subject_entity_type="person",
                field_path="identity.orcid",
                value=orcid,
                observed_at=NOW,
                assertion_run_id="s6r-person-identity-assertions",
            )
        )
    return source, tuple(assertions)


def _person_crosswalk_assertion(
    source: Any,
    *,
    source_kind: str,
    root_canonical_identity_id: str,
    source_subobject_id: str | None,
) -> Any:
    return identity_models.SourceAssertion(
        assertion_id=f"assertion:{source.source_identity_id}:public-reference",
        source_record_id=source.source_record_ids[0],
        source_identity_id=source.source_identity_id,
        subject_entity_type="person",
        field_path="identity.public_reference_locator",
        value={
            "source_kind": source_kind,
            "root_canonical_identity_id": root_canonical_identity_id,
            "source_subobject_id": source_subobject_id,
        },
        observed_at=NOW,
        assertion_run_id="s6r-person-public-reference-crosswalk",
    )


def _field_assertion_id(identity_id: str, field_path: str) -> str:
    return f"assertion:{identity_id}:{field_path}"


def _field_decision_id(identity_id: str, field_path: str) -> str:
    return f"field-decision:{identity_id}:{field_path}"


def _typed_member(
    *,
    identity_id: str,
    field_path: str,
    subobject_id: str,
    values: dict[str, Any],
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> dict[str, Any]:
    return {
        "subobject_id": subobject_id,
        "parent_canonical_identity_id": identity_id,
        "supporting_assertion_ids": [_field_assertion_id(identity_id, field_path)],
        "decision_ids": [_field_decision_id(identity_id, field_path)],
        "observed_at": NOW.isoformat(),
        "valid_from": valid_from,
        "valid_to": valid_to,
        **values,
    }


def _domain_inputs(
    *,
    domain: str,
    identity_id: str,
    display_name: str,
    selected_values: dict[str, Any],
    source_record_ids: dict[str, str],
) -> dict[str, tuple[Any, ...]]:
    source_identity_id = f"source-domain:{identity_id}"
    identity_decision_id = f"identity-decision:{identity_id}"
    identity = CanonicalIdentity(
        canonical_identity_id=identity_id,
        entity_type=domain,
        state=CanonicalIdentityState.active,
        display_name=display_name,
        source_identity_ids=(source_identity_id,),
        identity_decision_id=identity_decision_id,
        release_id=RELEASE_ID,
    )
    assignment = SourceIdentityAssignment(
        release_id=RELEASE_ID,
        source_identity_id=source_identity_id,
        canonical_identity_id=identity_id,
        identity_decision_id=identity_decision_id,
    )
    assertions: list[SourceAssertion] = []
    decisions: list[CanonicalDecision] = []
    current_fields: list[CurrentFieldSelection] = []
    for field_path, value in selected_values.items():
        assertion_id = _field_assertion_id(identity_id, field_path)
        decision_id = _field_decision_id(identity_id, field_path)
        validity_intervals = (
            {
                (member.get("valid_from"), member.get("valid_to"))
                for member in value
                if isinstance(member, dict)
            }
            if isinstance(value, list) and value
            else {(None, None)}
        )
        member_valid_from, member_valid_to = (
            next(iter(validity_intervals))
            if len(validity_intervals) == 1
            else (None, None)
        )
        valid_from = (
            TemporalDateValue(value=date.fromisoformat(member_valid_from))
            if isinstance(member_valid_from, str) and len(member_valid_from) == 10
            else None
        )
        valid_to = (
            TemporalDateValue(value=date.fromisoformat(member_valid_to))
            if isinstance(member_valid_to, str) and len(member_valid_to) == 10
            else None
        )
        assertion = SourceAssertion(
            assertion_id=assertion_id,
            source_record_id=source_record_ids.get(
                field_path, f"record:domain:{identity_id}"
            ),
            source_identity_id=source_identity_id,
            subject_entity_type=domain,
            field_path=field_path,
            value=value,
            observed_at=NOW,
            valid_from=valid_from,
            valid_to=valid_to,
            assertion_run_id="s6r-person-domain-assertions",
        )
        decision = CanonicalDecision(
            decision_id=decision_id,
            canonical_identity_id=identity_id,
            field_path=field_path,
            state=DecisionState.selected,
            candidate_assertion_ids=(assertion_id,),
            selected_assertion_ids=(assertion_id,),
            conflicting_assertion_ids=(),
            policy=PolicyReference(
                policy_id="s6r-domain-field-selection-policy",
                policy_version="field-selection-v1",
                policy_kind=PolicyKind.field_selection,
                content_sha256="6" * 64,
                effective_at=NOW - timedelta(days=1),
            ),
            method=DecisionMethod.deterministic,
            method_version="field-selection-v1",
            decision_run_id="s6r-person-domain-field-selection",
            confidence=1.0,
            rationale="Single retained fixture assertion.",
            release_id=RELEASE_ID,
            decided_at=NOW,
        )
        current = CurrentFieldSelection(
            release_id=RELEASE_ID,
            canonical_identity_id=identity_id,
            field_path=field_path,
            value=value,
            decision_id=decision_id,
            supporting_assertion_ids=(assertion_id,),
            valid_from=valid_from,
            valid_to=valid_to,
        )
        assertions.append(assertion)
        decisions.append(decision)
        current_fields.append(current)
    inclusion = PolicyDecision(
        decision_id=f"inclusion:{identity_id}",
        policy=_inclusion_policy(),
        subject_identity_id=identity_id,
        release_id=RELEASE_ID,
        outcome=PolicyOutcome.admitted,
        supporting_assertion_ids=tuple(item.assertion_id for item in assertions),
        evaluated_at=NOW,
    )
    return {
        "canonical_identities": (identity,),
        "source_identity_assignments": (assignment,),
        "source_assertions": tuple(assertions),
        "canonical_decisions": tuple(decisions),
        "current_fields": tuple(current_fields),
        "inclusion_decisions": (inclusion,),
    }


def _combine_domain_inputs(
    *inputs: dict[str, tuple[Any, ...]],
) -> dict[str, tuple[Any, ...]]:
    return {
        key: tuple(item for values in inputs for item in values[key])
        for key in inputs[0]
    }


def _domain_projection_pair(
    inputs: dict[str, tuple[Any, ...]],
) -> tuple[Any, Any]:
    request_inputs = dict(inputs)
    inclusion_decisions = request_inputs.pop("inclusion_decisions")
    identities = request_inputs["canonical_identities"]
    inclusion_result = inclusion_models.create_domain_inclusion_result(
        release_id=RELEASE_ID,
        decision_run_id="s6r-domain-inclusion",
        evaluated_at=NOW,
        approved_source_scope_manifest_sha256="7" * 64,
        policy_decisions=inclusion_decisions,
        identity_domains={
            identity.canonical_identity_id: identity.entity_type
            for identity in identities
        },
    )
    request = projection_models.DomainProjectionRequest(
        release_id=RELEASE_ID,
        build_run_id="s6r-domain-projection",
        as_of=NOW,
        projection_version="domain-projection-v1",
        catalog_schema_version=CATALOG_SCHEMA_VERSION,
        catalog_version=CATALOG_VERSION,
        catalog_content_sha256=CATALOG_CONTENT_SHA256,
        inclusion_result=inclusion_result,
        **request_inputs,
    )
    result = projection_models.create_ephemeral_domain_projection_builder().project(
        request
    )
    return request, result


def _technology_product_anchor(
    *,
    include_relationships: bool,
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, str], tuple[Any, ...]]:
    company_id = "company-robotics"
    product_record_id = "record:company-product:robot-arm"
    product = _typed_member(
        identity_id=company_id,
        field_path="product",
        subobject_id="product:robot-arm",
        values={
            "name": "Robot Arm",
            "description": "A visual-control research robot arm.",
            "technology_tags": [],
        },
    )
    crosswalk = {
        "public_domain": "company",
        "root_canonical_identity_id": company_id,
        "source_field_path": "product",
        "source_subobject_type": "product",
        "source_subobject_id": product["subobject_id"],
    }
    relationship_specs = (
        (
            "discussion_or_mention",
            "internal_reference.technology_discussion_or_mention",
            None,
        ),
        (
            "claimed_adoption",
            "internal_reference.technology_claimed_adoption",
            TemporalInstantValue(value=NOW),
        ),
        (
            "demonstrated_use",
            "internal_reference.technology_demonstrated_use",
            TemporalInstantValue(value=NOW),
        ),
    )
    if not include_relationships:
        relationship_specs = ()
    technology_relationship_assertion_ids: dict[str, str] = {}
    relationship_assertions = []
    for semantics, field_path, valid_from in relationship_specs:
        assertion_id = f"assertion:product:technology:{semantics}"
        technology_relationship_assertion_ids[semantics] = assertion_id
        relationship_assertions.append(
            SourceAssertion(
                assertion_id=assertion_id,
                source_record_id=product_record_id,
                source_identity_id=f"source-domain:{company_id}",
                subject_entity_type="company",
                field_path=field_path,
                value={
                    "technology_source_identity_id": "source-tech-route-visual-servo",
                    "root_canonical_identity_id": company_id,
                    "source_subobject_type": "product",
                    "source_subobject_id": product["subobject_id"],
                    "term": "visual servoing",
                },
                observed_at=NOW,
                valid_from=valid_from,
                assertion_run_id="s6r-technology-relationship-assertions",
            )
        )
    return (
        product,
        product_record_id,
        crosswalk,
        technology_relationship_assertion_ids,
        tuple(relationship_assertions),
    )


def _technology_graph(
    module: Any,
    *,
    forbidden_entity_type: str | None = None,
    unresolved_source_identity_id: str | None = None,
) -> dict[str, Any]:
    """Build one closed Company/Product + Technology identity fixture graph."""

    company_id = "company-robotics"
    (
        product,
        product_record_id,
        crosswalk,
        technology_relationship_assertion_ids,
        relationship_assertions,
    ) = _technology_product_anchor(
        include_relationships=forbidden_entity_type is None,
    )
    company_inputs = _domain_inputs(
        domain="company",
        identity_id=company_id,
        display_name="Robotics Co",
        selected_values={
            "name": "Robotics Co",
            "normalized_name": "robotics co",
            "profile_summary": "Builds evidence-backed robotics products.",
            "technology_route_summary": "Uses visual feedback for robot control.",
            "product": [product],
        },
        source_record_ids={"product": product_record_id},
    )

    if forbidden_entity_type is None:
        technology_rows = (
            (
                "source-tech-concept-robotics",
                "technology_concept",
                "robotics",
                ("robotic systems",),
                "Evidence-backed robotics concept",
                (),
            ),
            (
                "source-tech-concept-visual-control",
                "technology_concept",
                "visual control",
                ("vision-based control",),
                "Control methods using visual feedback",
                ("source-tech-concept-robotics",),
            ),
            (
                "source-tech-route-visual-servo",
                "technology_route",
                "visual servoing",
                ("vision servo",),
                "A route using visual feedback",
                ("source-tech-concept-visual-control",),
            ),
        )
    else:
        technology_rows = (
            (
                f"source-forbidden-{forbidden_entity_type}",
                forbidden_entity_type,
                forbidden_entity_type.replace("_", " "),
                (),
                "Forbidden internal reference fixture.",
                (),
            ),
        )
    company_inputs = {
        **company_inputs,
        "source_assertions": (
            *company_inputs["source_assertions"],
            *relationship_assertions,
        ),
    }

    source_pairs = tuple(
        _technology_source(
            source_identity_id=source_id,
            entity_type=entity_type,
            preferred_name=preferred_name,
            aliases=aliases,
            definition=definition,
            public_reference_locator=crosswalk,
            public_source_record_id=product_record_id,
            linked_source_identity_ids=linked_source_ids,
        )
        for (
            source_id,
            entity_type,
            preferred_name,
            aliases,
            definition,
            linked_source_ids,
        ) in technology_rows
    )
    if unresolved_source_identity_id is not None:
        rewritten_pairs = []
        for source, assertions in source_pairs:
            if source.source_identity_id != unresolved_source_identity_id:
                rewritten_pairs.append((source, assertions))
                continue
            rewritten_pairs.append(
                (
                    source.model_copy(
                        update={
                            "normalized_keys": {
                                key: value
                                for key, value in source.normalized_keys.items()
                                if key != "technology_id"
                            }
                        }
                    ),
                    tuple(
                        item
                        for item in assertions
                        if item.field_path != "identity.technology_id"
                    ),
                )
            )
        source_pairs = tuple(rewritten_pairs)
    technology_sources = tuple(pair[0] for pair in source_pairs)
    technology_assertions = tuple(
        assertion for pair in source_pairs for assertion in pair[1]
    )
    technology_request, technology_result = _technology_identity_resolution(
        technology_sources, technology_assertions
    )
    person_request, person_result = _identity_resolution((), ())
    domain_request, domain_result = _domain_projection_pair(company_inputs)
    locators = tuple(
        module.TechnologyEvidenceLocator(
            reference_id=f"technology-ref:{source.source_identity_id}",
            reference_type=(
                source.entity_type
                if source.entity_type
                in {
                    "technology_concept",
                    "technology_route",
                }
                else "technology_concept"
            ),
            technology_source_identity_id=source.source_identity_id,
            **crosswalk,
        )
        for source in technology_sources
    )
    canonical_ids = {
        assignment.source_identity_id: assignment.canonical_identity_id
        for assignment in technology_result.source_identity_assignments
    }
    return {
        "domain_request": domain_request,
        "domain_result": domain_result,
        "person_request": person_request,
        "person_result": person_result,
        "person_locators": (),
        "technology_request": technology_request,
        "technology_result": technology_result,
        "technology_locators": locators,
        "technology_canonical_ids": canonical_ids,
        "company_id": company_id,
        "product_id": product["subobject_id"],
        "product_record_id": product_record_id,
        "technology_relationship_assertion_ids": (
            technology_relationship_assertion_ids
        ),
    }


def _identity_resolution(
    sources: tuple[Any, ...], assertions: tuple[Any, ...]
) -> tuple[Any, Any]:
    request = identity_models.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id="s6r-person-identity-resolution",
        identity_method_version="canonical-identity-resolution-person-v1",
        as_of=NOW,
        policy=PolicyReference(
            policy_id="s6r-person-identity-policy",
            policy_version="person-identity-v1",
            policy_kind=PolicyKind.identity,
            content_sha256="9" * 64,
            effective_at=NOW - timedelta(days=1),
        ),
        source_identities=sources,
        identity_assertions=assertions,
    )
    result = (
        identity_models.create_ephemeral_canonical_identity_resolution_engine().resolve(
            request
        )
    )
    return request, result


def _technology_source(
    *,
    source_identity_id: str,
    entity_type: str,
    preferred_name: str,
    aliases: tuple[str, ...],
    definition: str,
    public_reference_locator: dict[str, Any],
    public_source_record_id: str,
    linked_source_identity_ids: tuple[str, ...] = (),
) -> tuple[Any, tuple[Any, ...]]:
    """Build retained Technology source facts; no canonical ID is caller supplied."""

    source_record_id = f"record:{source_identity_id}"
    source = identity_models.SourceIdentity(
        source_identity_id=source_identity_id,
        source_system="fixture:technology-taxonomy",
        source_key=f"technology:{source_identity_id}",
        entity_type=entity_type,
        source_record_ids=tuple(sorted((source_record_id, public_source_record_id))),
        normalized_keys={
            "name_key": preferred_name,
            "technology_id": source_identity_id,
        },
        first_observed_at=NOW - timedelta(days=1),
        last_observed_at=NOW,
        state=identity_models.SourceIdentityState.active,
    )
    link_field = {
        "technology_concept": "technology.parent_source_identity_ids",
        "technology_route": "technology.concept_source_identity_ids",
    }.get(entity_type)
    assertions = [
        identity_models.SourceAssertion(
            assertion_id=f"assertion:{source_identity_id}:identity-name",
            source_record_id=source_record_id,
            source_identity_id=source_identity_id,
            subject_entity_type=entity_type,
            field_path="technology.preferred_name",
            value=preferred_name,
            observed_at=NOW,
            assertion_run_id="s6r-technology-identity-assertions",
        ),
        identity_models.SourceAssertion(
            assertion_id=f"assertion:{source_identity_id}:technology-id",
            source_record_id=source_record_id,
            source_identity_id=source_identity_id,
            subject_entity_type=entity_type,
            field_path="identity.technology_id",
            value=source_identity_id,
            observed_at=NOW,
            assertion_run_id="s6r-technology-identity-assertions",
        ),
        identity_models.SourceAssertion(
            assertion_id=f"assertion:{source_identity_id}:public-reference",
            source_record_id=public_source_record_id,
            source_identity_id=source_identity_id,
            subject_entity_type=entity_type,
            field_path="technology.public_reference_locator",
            value=public_reference_locator,
            observed_at=NOW,
            assertion_run_id="s6r-technology-public-reference-crosswalk",
        ),
        identity_models.SourceAssertion(
            assertion_id=f"assertion:{source_identity_id}:aliases",
            source_record_id=source_record_id,
            source_identity_id=source_identity_id,
            subject_entity_type=entity_type,
            field_path="technology.aliases",
            value=list(aliases),
            observed_at=NOW,
            assertion_run_id="s6r-technology-identity-assertions",
        ),
        identity_models.SourceAssertion(
            assertion_id=f"assertion:{source_identity_id}:definition",
            source_record_id=source_record_id,
            source_identity_id=source_identity_id,
            subject_entity_type=entity_type,
            field_path="technology.definition",
            value=definition,
            observed_at=NOW,
            assertion_run_id="s6r-technology-identity-assertions",
        ),
    ]
    if link_field is not None:
        assertions.append(
            identity_models.SourceAssertion(
                assertion_id=f"assertion:{source_identity_id}:links",
                source_record_id=source_record_id,
                source_identity_id=source_identity_id,
                subject_entity_type=entity_type,
                field_path=link_field,
                value=list(linked_source_identity_ids),
                observed_at=NOW,
                assertion_run_id="s6r-technology-identity-assertions",
            )
        )
    return source, tuple(assertions)


def _technology_identity_resolution(
    sources: tuple[Any, ...], assertions: tuple[Any, ...]
) -> tuple[Any, Any]:
    request = identity_models.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id="s6r-technology-identity-resolution",
        identity_method_version=(identity_models.TECHNOLOGY_IDENTITY_METHOD_VERSION),
        as_of=NOW,
        policy=PolicyReference(
            policy_id="s6r-technology-identity-policy",
            policy_version="technology-identity-v1",
            policy_kind=PolicyKind.identity,
            content_sha256="5" * 64,
            effective_at=NOW - timedelta(days=1),
        ),
        source_identities=sources,
        identity_assertions=assertions,
    )
    result = (
        identity_models.create_ephemeral_canonical_identity_resolution_engine().resolve(
            request
        )
    )
    return request, result


def _inclusion_policy() -> PolicyReference:
    return PolicyReference(
        policy_id="s6r-domain-inclusion-policy",
        policy_version="domain-inclusion-v1",
        policy_kind=PolicyKind.inclusion,
        content_sha256="8" * 64,
        effective_at=NOW - timedelta(days=1),
    )


def _request(
    module: Any,
    *,
    domain_request: Any | None = None,
    domain_result: Any | None = None,
    identity_request: Any | None = None,
    identity_result: Any | None = None,
    locators: tuple[Any, ...] | None = None,
    **overrides: Any,
) -> Any:
    if (
        domain_request is None
        or domain_result is None
        or identity_request is None
        or identity_result is None
        or locators is None
    ):
        raise _MissingTechnologyContract(
            "S6R4 RED fixture has not migrated to closed domain/identity inputs"
        )
    values = {
        "release_id": RELEASE_ID,
        "build_run_id": "s6r-reference-build-1",
        "as_of": NOW,
        "projection_version": "internal-reference-v1",
        "reference_catalog_identity": module.ReferenceCatalogIdentity(
            schema_version=REFERENCE_CATALOG_SCHEMA_VERSION,
            catalog_version=REFERENCE_CATALOG_VERSION,
            content_sha256=REFERENCE_CATALOG_CONTENT_SHA256,
        ),
        "public_domain_projection_request": domain_request.model_dump(mode="python"),
        "public_domain_projection_result": domain_result.model_dump(mode="python"),
        "person_identity_resolution_request": identity_request.model_dump(
            mode="python"
        ),
        "person_identity_resolution_result": identity_result.model_dump(mode="python"),
        "person_evidence_locators": locators,
    }
    values.update(overrides)
    return module.InternalReferenceProjectionRequest(**values)


def _resolved_person_graph(
    module: Any,
    *,
    include_technology_anchor: bool = False,
    include_shared_institution_alias: bool = False,
    include_company_patent_applicant: bool = False,
) -> tuple[Any, Any, Any, Any, tuple[Any, ...]]:
    names = {
        "company_personnel": "Ada Chen",
        "company_personnel_education": "Ada Chen",
        "company_personnel_work_experience": "Ada Chen",
        "paper_author": "Ada Chen",
        "patent_inventor": "Ada Chen",
        "professor": "陈艾达",
        "professor_education": "陈艾达",
        "professor_work_history": "陈艾达",
    }
    source_pairs = {
        source_kind: _person_source(
            source_kind,
            name,
            orcid="0000-0001-2345-6789",
            source_record_id=f"record:person:{source_kind}",
        )
        for source_kind, name in names.items()
    }
    company_id = "company-robotics"
    company_personnel = _typed_member(
        identity_id=company_id,
        field_path="key_personnel",
        subobject_id="company-personnel:ada",
        values={"name": "Ada Chen", "role": "Founder"},
    )
    company_education = _typed_member(
        identity_id=company_id,
        field_path="personnel_education",
        subobject_id="company-personnel-education:ada",
        values={
            "person": {"reference_id": "person:ada", "name": "Ada Chen"},
            "institution": {
                "reference_id": "institution:sustech",
                "name": "SUSTech",
            },
            "degree": "PhD",
        },
    )
    company_work = _typed_member(
        identity_id=company_id,
        field_path="personnel_work_experience",
        subobject_id="company-personnel-work:ada",
        values={
            "person": {"reference_id": "person:ada", "name": "Ada Chen"},
            "organization": {
                "reference_id": "company:robotics",
                "name": "Robotics Co",
            },
            "role": "Founder",
            "start": "2020-01-01",
        },
        valid_from="2020-01-01",
    )
    selected_company_values: dict[str, Any] = {
        "name": "Robotics Co",
        "normalized_name": "robotics co",
        "profile_summary": "Robotics company.",
        "technology_route_summary": "Robotics route.",
        "key_personnel": [company_personnel],
        "personnel_education": [company_education],
        "personnel_work_experience": [company_work],
    }
    company_source_record_ids = {
        "key_personnel": "record:person:company_personnel",
        "personnel_education": "record:person:company_personnel_education",
        "personnel_work_experience": (
            "record:person:company_personnel_work_experience"
        ),
    }
    technology_relationship_assertions: tuple[Any, ...] = ()
    if include_technology_anchor:
        (
            product,
            product_record_id,
            _,
            _,
            technology_relationship_assertions,
        ) = _technology_product_anchor(include_relationships=True)
        selected_company_values.update(
            {
                "geography": {
                    "reference_id": "geography:shenzhen",
                    "name": "深圳",
                },
                "product": [product],
            }
        )
        company_source_record_ids.update(
            {
                "geography": "record:company:geography:shenzhen",
                "product": product_record_id,
            }
        )
    company_inputs = _domain_inputs(
        domain="company",
        identity_id=company_id,
        display_name="Robotics Co",
        selected_values=selected_company_values,
        source_record_ids=company_source_record_ids,
    )
    if technology_relationship_assertions:
        company_inputs = {
            **company_inputs,
            "source_assertions": (
                *company_inputs["source_assertions"],
                *technology_relationship_assertions,
            ),
        }

    paper_id = "paper-ada"
    paper_author = _typed_member(
        identity_id=paper_id,
        field_path="authors",
        subobject_id="paper-author:ada",
        values={"name": "Ada Chen", "author_order": 1},
    )
    paper_inputs = _domain_inputs(
        domain="paper",
        identity_id=paper_id,
        display_name="Evidence-bound robotics",
        selected_values={
            "authors": [paper_author],
            "title": "Evidence-bound robotics",
            "venue": {
                "reference_id": "venue:robotics",
                "name": "Robotics Journal",
            },
            "year": 2026,
        },
        source_record_ids={"authors": "record:person:paper_author"},
    )

    patent_id = "patent-ada"
    patent_inventor = _typed_member(
        identity_id=patent_id,
        field_path="inventors",
        subobject_id="patent-inventor:ada",
        values={"name": "Ada Chen", "inventor_order": 1},
    )
    patent_applicant = (
        _typed_member(
            identity_id=patent_id,
            field_path="applicants",
            subobject_id="patent-applicant:robotics",
            values={
                "name": "Robotics Co",
                "applicant_order": 1,
                "canonical_company_id": company_id,
            },
        )
        if include_company_patent_applicant
        else None
    )
    patent_source_record_ids = {"inventors": "record:person:patent_inventor"}
    if patent_applicant is not None:
        patent_source_record_ids["applicants"] = "record:patent:applicant:robotics"
    patent_inputs = _domain_inputs(
        domain="patent",
        identity_id=patent_id,
        display_name="Robot control system",
        selected_values={
            "applicants": [patent_applicant] if patent_applicant is not None else [],
            "inventors": [patent_inventor],
            "summary_text": "Robotics patent.",
            "title": "Robot control system",
        },
        source_record_ids=patent_source_record_ids,
    )

    professor_id = "professor-ada"
    professor_education = _typed_member(
        identity_id=professor_id,
        field_path="education_history",
        subobject_id="professor-education:ada",
        values={
            "institution": {
                "reference_id": "institution:sustech",
                "name": ("南方科技大学" if include_technology_anchor else "SUSTech"),
            },
            "degree": "PhD",
        },
    )
    professor_work = _typed_member(
        identity_id=professor_id,
        field_path="work_history",
        subobject_id="professor-work:ada",
        values={
            "organization": {
                "reference_id": "institution:sustech",
                "name": "SUSTech",
            },
            "role": "Professor",
        },
    )
    professor_affiliation = (
        _typed_member(
            identity_id=professor_id,
            field_path="affiliation_history",
            subobject_id="professor-affiliation:ada:shared-sustech",
            values={
                "institution": {
                    "reference_id": "institution:shared-sustech",
                    "name": "SUSTech",
                },
                "title": "Visiting Professor",
            },
        )
        if include_shared_institution_alias
        else None
    )
    professor_selected_values: dict[str, Any] = {
        "canonical_name_zh": "陈艾达",
        "company_roles": [],
        "department": {
            "reference_id": "department:cs",
            "name": "Computer Science",
        },
        "email": "ada@example.edu",
        "homepage": "https://example.edu/ada",
        "institution": "SUSTech",
        "name": "陈艾达",
        "paper_summary": "Robotics papers.",
        "patent_ids": [],
        "patent_summary": "Robotics patents.",
        "profile_summary": "Robotics professor.",
        "research_directions": [],
        "title": "Professor",
        "education_history": [professor_education],
        "work_history": [professor_work],
    }
    professor_source_record_ids = {
        "canonical_name_zh": "record:person:professor",
        "name": "record:person:professor",
        "education_history": "record:person:professor_education",
        "work_history": "record:person:professor_work_history",
    }
    if professor_affiliation is not None:
        professor_selected_values["affiliation_history"] = [professor_affiliation]
        professor_source_record_ids["affiliation_history"] = (
            "record:professor:affiliation:shared-sustech"
        )
    professor_inputs = _domain_inputs(
        domain="professor",
        identity_id=professor_id,
        display_name="陈艾达",
        selected_values=professor_selected_values,
        source_record_ids=professor_source_record_ids,
    )

    domain_request, domain_result = _domain_projection_pair(
        _combine_domain_inputs(
            company_inputs,
            paper_inputs,
            patent_inputs,
            professor_inputs,
        )
    )
    locator_rows = {
        "company_personnel": (company_id, company_personnel["subobject_id"]),
        "company_personnel_education": (
            company_id,
            company_education["subobject_id"],
        ),
        "company_personnel_work_experience": (
            company_id,
            company_work["subobject_id"],
        ),
        "paper_author": (paper_id, paper_author["subobject_id"]),
        "patent_inventor": (patent_id, patent_inventor["subobject_id"]),
        "professor": (professor_id, None),
        "professor_education": (
            professor_id,
            professor_education["subobject_id"],
        ),
        "professor_work_history": (
            professor_id,
            professor_work["subobject_id"],
        ),
    }
    sources = tuple(pair[0] for pair in source_pairs.values())
    assertions = tuple(
        assertion
        for source_kind, pair in source_pairs.items()
        for assertion in (
            *pair[1],
            _person_crosswalk_assertion(
                pair[0],
                source_kind=source_kind,
                root_canonical_identity_id=locator_rows[source_kind][0],
                source_subobject_id=locator_rows[source_kind][1],
            ),
        )
    )
    identity_request, identity_result = _identity_resolution(sources, assertions)
    assert len(identity_result.current_canonical_identities) == 1
    locators = tuple(
        module.PersonEvidenceLocator(
            reference_id=f"person-ref:{source_kind}",
            source_kind=source_kind,
            root_canonical_identity_id=root_id,
            source_subobject_id=subobject_id,
            source_identity_id=source_pairs[source_kind][0].source_identity_id,
        )
        for source_kind, (root_id, subobject_id) in locator_rows.items()
    )
    return domain_request, domain_result, identity_request, identity_result, locators


def _unresolved_person_graph(
    module: Any,
    *,
    identity_token: str | None = None,
) -> tuple[Any, Any, Any, Any, tuple[Any, ...]]:
    token_suffix = f":{identity_token}" if identity_token is not None else ""
    entity_suffix = f"-{identity_token}" if identity_token is not None else ""
    rows = {
        "paper_author": (
            "Wei Zhang",
            f"paper-one{entity_suffix}",
            f"paper-author:wei{token_suffix}",
        ),
        "patent_inventor": (
            "Wei Zhang",
            f"patent-two{entity_suffix}",
            f"patent-inventor:wei{token_suffix}",
        ),
    }
    source_pairs = {
        source_kind: _person_source(
            source_kind,
            name,
            orcid=None,
            source_record_id=f"record:person:{source_kind}{token_suffix}",
            source_id_suffix=(
                f"{source_kind}{token_suffix}" if identity_token is not None else None
            ),
        )
        for source_kind, (name, _, _) in rows.items()
    }
    sources = tuple(pair[0] for pair in source_pairs.values())
    assertions = tuple(
        assertion
        for source_kind, pair in source_pairs.items()
        for assertion in (
            *pair[1],
            _person_crosswalk_assertion(
                pair[0],
                source_kind=source_kind,
                root_canonical_identity_id=rows[source_kind][1],
                source_subobject_id=rows[source_kind][2],
            ),
        )
    )
    identity_request, identity_result = _identity_resolution(sources, assertions)
    assert len(identity_result.candidate_verdicts) == 1
    assert identity_result.candidate_verdicts[0].verdict.value == "unresolved"

    paper_author = _typed_member(
        identity_id=rows["paper_author"][1],
        field_path="authors",
        subobject_id=rows["paper_author"][2],
        values={"name": "Wei Zhang", "author_order": 1},
    )
    paper_inputs = _domain_inputs(
        domain="paper",
        identity_id=rows["paper_author"][1],
        display_name="Unresolved author paper",
        selected_values={
            "authors": [paper_author],
            "title": "Unresolved author paper",
            "venue": {
                "reference_id": "venue:unresolved",
                "name": "Example Venue",
            },
            "year": 2026,
        },
        source_record_ids={"authors": f"record:person:paper_author{token_suffix}"},
    )
    patent_inventor = _typed_member(
        identity_id=rows["patent_inventor"][1],
        field_path="inventors",
        subobject_id=rows["patent_inventor"][2],
        values={"name": "Wei Zhang", "inventor_order": 1},
    )
    patent_inputs = _domain_inputs(
        domain="patent",
        identity_id=rows["patent_inventor"][1],
        display_name="Unresolved inventor patent",
        selected_values={
            "applicants": [],
            "inventors": [patent_inventor],
            "summary_text": "Unresolved inventor patent.",
            "title": "Unresolved inventor patent",
        },
        source_record_ids={"inventors": f"record:person:patent_inventor{token_suffix}"},
    )
    domain_request, domain_result = _domain_projection_pair(
        _combine_domain_inputs(paper_inputs, patent_inputs)
    )
    locators = tuple(
        module.PersonEvidenceLocator(
            reference_id=f"person-ref:{source_kind}{token_suffix}",
            source_kind=source_kind,
            root_canonical_identity_id=root_id,
            source_subobject_id=subobject_id,
            source_identity_id=source_pairs[source_kind][0].source_identity_id,
        )
        for source_kind, (_, root_id, subobject_id) in rows.items()
    )
    return domain_request, domain_result, identity_request, identity_result, locators


def _domain_inputs_from_projection_request(request: Any) -> dict[str, tuple[Any, ...]]:
    return {
        "canonical_identities": request.canonical_identities,
        "source_identity_assignments": request.source_identity_assignments,
        "source_assertions": request.source_assertions,
        "canonical_decisions": request.canonical_decisions,
        "current_fields": request.current_fields,
        "inclusion_decisions": request.inclusion_result.policy_decisions,
    }


def _resolved_and_unresolved_person_graph(
    module: Any,
    *,
    include_shared_institution_alias: bool = False,
) -> tuple[Any, Any, Any, Any, tuple[Any, ...]]:
    (
        resolved_domain_request,
        _,
        resolved_identity_request,
        _,
        resolved_locators,
    ) = _resolved_person_graph(
        module,
        include_technology_anchor=True,
        include_shared_institution_alias=include_shared_institution_alias,
    )
    (
        unresolved_domain_request,
        _,
        unresolved_identity_request,
        _,
        unresolved_locators,
    ) = _unresolved_person_graph(module, identity_token="s8p1")
    domain_request, domain_result = _domain_projection_pair(
        _combine_domain_inputs(
            _domain_inputs_from_projection_request(resolved_domain_request),
            _domain_inputs_from_projection_request(unresolved_domain_request),
        )
    )
    identity_request, identity_result = _identity_resolution(
        (
            *resolved_identity_request.source_identities,
            *unresolved_identity_request.source_identities,
        ),
        (
            *resolved_identity_request.identity_assertions,
            *unresolved_identity_request.identity_assertions,
        ),
    )
    assert any(
        verdict.verdict.value == "unresolved"
        for verdict in identity_result.candidate_verdicts
    )
    return (
        domain_request,
        domain_result,
        identity_request,
        identity_result,
        (*resolved_locators, *unresolved_locators),
    )


def _same_record_author_graph(
    module: Any,
    *,
    domain_orcids: tuple[str | None, str | None],
) -> tuple[Any, Any, Any, Any, tuple[Any, ...]]:
    paper_id = "paper-shared-author-record"
    source_record_id = "record:paper:shared-authors"
    author_rows = (
        ("a", "paper-author:a", "0000-0001-0000-1111", domain_orcids[0]),
        ("b", "paper-author:b", "0000-0001-0000-2222", domain_orcids[1]),
    )
    source_pairs = {
        suffix: _person_source(
            "paper_author",
            "Wei Zhang",
            orcid=person_orcid,
            source_record_id=source_record_id,
            source_id_suffix=f"paper_author:{suffix}",
        )
        for suffix, _, person_orcid, _ in author_rows
    }
    identity_assertions = tuple(
        assertion
        for suffix, subobject_id, _, _ in author_rows
        for assertion in (
            *source_pairs[suffix][1],
            _person_crosswalk_assertion(
                source_pairs[suffix][0],
                source_kind="paper_author",
                root_canonical_identity_id=paper_id,
                source_subobject_id=subobject_id,
            ),
        )
    )
    identity_request, identity_result = _identity_resolution(
        tuple(source_pairs[suffix][0] for suffix, *_ in author_rows),
        identity_assertions,
    )
    assert identity_result.candidate_verdicts[0].verdict.value == ("different_entities")

    authors = [
        _typed_member(
            identity_id=paper_id,
            field_path="authors",
            subobject_id=subobject_id,
            values={
                "name": "Wei Zhang",
                "author_order": index,
                "orcid": domain_orcid,
            },
        )
        for index, (_, subobject_id, _, domain_orcid) in enumerate(author_rows, start=1)
    ]
    domain_request, domain_result = _domain_projection_pair(
        _domain_inputs(
            domain="paper",
            identity_id=paper_id,
            display_name="Shared-record authors",
            selected_values={
                "authors": authors,
                "title": "Shared-record authors",
                "venue": {
                    "reference_id": "venue:shared-record",
                    "name": "Shared Record Journal",
                },
                "year": 2026,
            },
            source_record_ids={"authors": source_record_id},
        )
    )
    locators = tuple(
        module.PersonEvidenceLocator(
            reference_id=f"person-ref:paper-author:{suffix}",
            source_kind="paper_author",
            root_canonical_identity_id=paper_id,
            source_subobject_id=subobject_id,
            source_identity_id=source_pairs[suffix][0].source_identity_id,
        )
        for suffix, subobject_id, _, _ in author_rows
    )
    return domain_request, domain_result, identity_request, identity_result, locators


def test_resolved_four_domain_references_share_one_role_neutral_person() -> None:
    module = _module()
    domain_request, domain_result, identity_request, identity_result, locators = (
        _resolved_person_graph(module)
    )
    request = _request(
        module,
        domain_request=domain_request,
        domain_result=domain_result,
        identity_request=identity_request,
        identity_result=identity_result,
        locators=locators,
    )

    result = module.create_ephemeral_internal_reference_projection_builder().project(
        request
    )

    assert len(result.person_projections) == 1
    projection = result.person_projections[0]
    canonical_identity = identity_result.current_canonical_identities[0]
    assert projection.canonical_person_identity_id == (
        canonical_identity.canonical_identity_id
    )
    assert projection.display_name == "Ada Chen"
    assert projection.aliases == ("陈艾达",)
    assert tuple(item.source_kind for item in projection.references) == (
        "company_personnel",
        "company_personnel_education",
        "company_personnel_work_experience",
        "paper_author",
        "patent_inventor",
        "professor",
        "professor_education",
        "professor_work_history",
    )
    assert projection.source_public_domains == PUBLIC_DOMAINS
    assert projection.identity_decision_id == canonical_identity.identity_decision_id
    assert (
        projection.identity_resolution_content_sha256 == identity_result.content_sha256
    )
    assert projection.projection_scope == "internal_auxiliary"
    assert projection.reference_type == "person"
    assert projection.domain is None
    assert (
        projection.reference_catalog_schema_version,
        projection.reference_catalog_version,
        projection.reference_catalog_content_sha256,
    ) == (
        REFERENCE_CATALOG_SCHEMA_VERSION,
        REFERENCE_CATALOG_VERSION,
        REFERENCE_CATALOG_CONTENT_SHA256,
    )
    assert result.unresolved_person_references == ()
    assert len(result.public_evidence_anchors) == len(locators)
    anchors_by_kind = {
        item.source_kind: item for item in result.public_evidence_anchors
    }
    assert anchors_by_kind["company_personnel"].source_subobject_type == (
        "key_personnel"
    )
    assert anchors_by_kind["paper_author"].source_subobject_type == "author"
    assert anchors_by_kind["patent_inventor"].source_subobject_type == "inventor"
    assert anchors_by_kind["professor"].source_subobject_type is None
    assert anchors_by_kind[
        "company_personnel_work_experience"
    ].valid_from == TemporalDateValue(value=date(2020, 1, 1))
    assert all(
        item.observed_at <= item.root_projection_as_of
        for item in anchors_by_kind.values()
    )
    assert all(
        item.anchor_id == f"public-domain-evidence:sha256:{item.content_sha256}"
        for item in anchors_by_kind.values()
    )

    reversed_result = (
        module.create_ephemeral_internal_reference_projection_builder().project(
            _request(
                module,
                domain_request=domain_request,
                domain_result=domain_result,
                identity_request=identity_request,
                identity_result=identity_result,
                locators=tuple(reversed(locators)),
            )
        )
    )
    assert reversed_result.model_dump(mode="json") == result.model_dump(mode="json")

    fabricated_alias = {
        **projection.model_dump(mode="json"),
        "aliases": ("Fabricated Alias", "陈艾达"),
    }
    with pytest.raises(ValidationError, match="names must derive"):
        module.PersonProjection.model_validate(fabricated_alias)
    with pytest.raises(ValidationError, match="unique and deterministic"):
        module.InternalReferenceProjectionResult.model_validate(
            {
                **result.model_dump(mode="json"),
                "person_projections": (projection, projection),
            }
        )


def test_result_verifier_rejects_fully_rehashed_fabricated_person_names() -> None:
    module = _module()
    domain_request, domain_result, identity_request, identity_result, locators = (
        _resolved_person_graph(module)
    )
    request = _request(
        module,
        domain_request=domain_request,
        domain_result=domain_result,
        identity_request=identity_request,
        identity_result=identity_result,
        locators=locators,
    )
    result = module.create_ephemeral_internal_reference_projection_builder().project(
        request
    )

    fabricated_name = "Fabricated Person"
    anchor_id_map: dict[str, str] = {}
    fabricated_anchors = []
    for anchor in result.public_evidence_anchors:
        anchor_payload = anchor.model_dump(
            mode="python", exclude={"anchor_id", "content_sha256"}
        )
        anchor_payload["person_name"] = fabricated_name
        anchor_hash = _canonical_hash(
            module.PublicDomainEvidenceAnchor.model_validate(
                {
                    **anchor_payload,
                    "anchor_id": "public-domain-evidence:provisional",
                    "content_sha256": "0" * 64,
                },
                context={"allow_unbound_anchor_hash": True},
            ).model_dump(mode="json", exclude={"anchor_id", "content_sha256"})
        )
        fabricated = module.PublicDomainEvidenceAnchor.model_validate(
            {
                **anchor_payload,
                "anchor_id": f"public-domain-evidence:sha256:{anchor_hash}",
                "content_sha256": anchor_hash,
            }
        )
        anchor_id_map[anchor.anchor_id] = fabricated.anchor_id
        fabricated_anchors.append(fabricated)

    original_projection = result.person_projections[0]
    fabricated_references = tuple(
        reference.model_copy(
            update={
                "name": fabricated_name,
                "source_anchor_id": anchor_id_map[reference.source_anchor_id],
            }
        )
        for reference in original_projection.references
    )
    projection_payload = original_projection.model_dump(
        mode="python", exclude={"content_sha256"}
    )
    projection_payload.update(
        {
            "display_name": fabricated_name,
            "aliases": (),
            "references": fabricated_references,
            "source_anchor_ids": tuple(
                sorted(
                    reference.source_anchor_id for reference in fabricated_references
                )
            ),
        }
    )
    provisional_projection = module.PersonProjection.model_validate(
        {**projection_payload, "content_sha256": "0" * 64},
        context={"allow_unbound_projection_hash": True},
    )
    fabricated_projection = module.PersonProjection.model_validate(
        {
            **projection_payload,
            "content_sha256": _canonical_hash(
                provisional_projection.model_dump(
                    mode="json", exclude={"content_sha256"}
                )
            ),
        }
    )
    result_payload = result.model_dump(mode="python", exclude={"content_sha256"})
    result_payload.update(
        {
            "public_evidence_anchors": tuple(
                sorted(fabricated_anchors, key=lambda item: item.anchor_id)
            ),
            "person_projections": (fabricated_projection,),
        }
    )
    provisional_result = module.InternalReferenceProjectionResult.model_validate(
        {**result_payload, "content_sha256": "0" * 64},
        context={"allow_unbound_projection_hash": True},
    )
    fabricated_result = module.InternalReferenceProjectionResult.model_validate(
        {
            **result_payload,
            "content_sha256": _canonical_hash(
                provisional_result.model_dump(mode="json", exclude={"content_sha256"})
            ),
        }
    )

    with pytest.raises(
        module.InternalReferenceProjectionIntegrityError,
        match="cannot be replayed",
    ):
        module.validate_internal_reference_projection_result(request, fabricated_result)


def test_result_model_rejects_two_references_reusing_one_anchor() -> None:
    module = _module()
    domain_request, domain_result, identity_request, identity_result, locators = (
        _resolved_person_graph(module)
    )
    result = module.create_ephemeral_internal_reference_projection_builder().project(
        _request(
            module,
            domain_request=domain_request,
            domain_result=domain_result,
            identity_request=identity_request,
            identity_result=identity_result,
            locators=locators,
        )
    )
    reference = result.person_projections[0].references[0]
    unresolved = reference.model_copy(
        update={
            "resolution_state": "unresolved",
            "canonical_person_identity_id": None,
            "assignment_decision_id": None,
        }
    )
    duplicate = unresolved.model_copy(
        update={"reference_id": f"{unresolved.reference_id}:duplicate"}
    )

    with pytest.raises(ValidationError, match="cannot own two references"):
        module.InternalReferenceProjectionResult.model_validate(
            {
                **result.model_dump(mode="python"),
                "public_evidence_anchors": (result.public_evidence_anchors[0],),
                "person_projections": (),
                "unresolved_person_references": (unresolved, duplicate),
            }
        )


def test_name_only_same_name_references_remain_unresolved_without_person_identity() -> (
    None
):
    module = _module()
    domain_request, domain_result, identity_request, identity_result, locators = (
        _unresolved_person_graph(module)
    )
    verdict = identity_result.candidate_verdicts[0]
    assert verdict.verdict.value == "unresolved"
    assert len(identity_result.review_cases) == 1
    assert identity_result.identity_decisions == ()
    assert identity_result.current_canonical_identities == ()
    assert identity_result.source_identity_assignments == ()

    result = module.create_ephemeral_internal_reference_projection_builder().project(
        _request(
            module,
            domain_request=domain_request,
            domain_result=domain_result,
            identity_request=identity_request,
            identity_result=identity_result,
            locators=locators,
        )
    )

    assert result.person_projections == ()
    assert tuple(item.reference_id for item in result.unresolved_person_references) == (
        "person-ref:paper_author",
        "person-ref:patent_inventor",
    )
    assert all(
        item.canonical_person_identity_id is None
        and item.assignment_decision_id is None
        and item.candidate_verdict_id == verdict.verdict_id
        and item.review_case_id == identity_result.review_cases[0].review_case_id
        for item in result.unresolved_person_references
    )
    assert {
        item.source_identity_id for item in result.unresolved_person_references
    } == {item.source_identity_id for item in locators}


def test_normalized_orcid_without_retained_orcid_assertion_fails_closed() -> None:
    module = _module()
    domain_request, domain_result, identity_request, _identity_result, locators = (
        _resolved_person_graph(module)
    )
    forged_request = identity_models.IdentityResolutionRequest.model_validate(
        {
            **identity_request.model_dump(mode="python"),
            "identity_assertions": tuple(
                assertion
                for assertion in identity_request.identity_assertions
                if assertion.field_path != "identity.orcid"
            ),
        }
    )
    forged_result = (
        identity_models.create_ephemeral_canonical_identity_resolution_engine().resolve(
            forged_request
        )
    )
    assert len(forged_result.current_canonical_identities) == 1

    with pytest.raises(
        module.InternalReferenceProjectionIntegrityError,
        match="normalized ORCID lacks an exact source-bound assertion",
    ):
        module.create_ephemeral_internal_reference_projection_builder().project(
            _request(
                module,
                domain_request=domain_request,
                domain_result=domain_result,
                identity_request=forged_request,
                identity_result=forged_result,
                locators=locators,
            )
        )


def test_same_record_same_name_sources_cannot_swap_author_object_crosswalks() -> None:
    module = _module()
    domain_request, domain_result, identity_request, identity_result, locators = (
        _same_record_author_graph(module, domain_orcids=(None, None))
    )
    swapped_locators = (
        locators[0].model_copy(
            update={"source_identity_id": locators[1].source_identity_id}
        ),
        locators[1].model_copy(
            update={"source_identity_id": locators[0].source_identity_id}
        ),
    )

    with pytest.raises(
        module.InternalReferenceProjectionIntegrityError,
        match="object-level crosswalk",
    ):
        module.create_ephemeral_internal_reference_projection_builder().project(
            _request(
                module,
                domain_request=domain_request,
                domain_result=domain_result,
                identity_request=identity_request,
                identity_result=identity_result,
                locators=swapped_locators,
            )
        )


def test_typed_paper_author_orcid_must_match_person_identity_orcid() -> None:
    module = _module()
    domain_request, domain_result, identity_request, identity_result, locators = (
        _same_record_author_graph(
            module,
            domain_orcids=("0000-0001-0000-9999", "0000-0001-0000-2222"),
        )
    )

    with pytest.raises(
        module.InternalReferenceProjectionIntegrityError,
        match="typed public-reference ORCID differs",
    ):
        module.create_ephemeral_internal_reference_projection_builder().project(
            _request(
                module,
                domain_request=domain_request,
                domain_result=domain_result,
                identity_request=identity_request,
                identity_result=identity_result,
                locators=locators,
            )
        )


def test_orcid_normalization_and_secondary_profile_record_are_accepted() -> None:
    module = _module()
    domain_request, domain_result, identity_request, _identity_result, locators = (
        _resolved_person_graph(module)
    )
    target_source_id = next(
        locator.source_identity_id
        for locator in locators
        if locator.source_kind == "paper_author"
    )
    profile_record_id = "record:person:paper_author:profile"
    updated_sources = tuple(
        source.model_copy(
            update={
                "source_record_ids": (*source.source_record_ids, profile_record_id),
                "normalized_keys": {
                    **source.normalized_keys,
                    "orcid": "https://orcid.org/0000-0001-2345-6789",
                },
            }
        )
        if source.source_identity_id == target_source_id
        else source
        for source in identity_request.source_identities
    )
    updated_assertions = tuple(
        assertion.model_copy(
            update={
                "source_record_id": profile_record_id,
                "value": "https://orcid.org/0000-0001-2345-6789",
            }
        )
        if assertion.source_identity_id == target_source_id
        and assertion.field_path == "identity.orcid"
        else assertion
        for assertion in identity_request.identity_assertions
    )
    normalized_request = identity_models.IdentityResolutionRequest.model_validate(
        {
            **identity_request.model_dump(mode="python"),
            "source_identities": updated_sources,
            "identity_assertions": updated_assertions,
        }
    )
    normalized_result = (
        identity_models.create_ephemeral_canonical_identity_resolution_engine().resolve(
            normalized_request
        )
    )

    result = module.create_ephemeral_internal_reference_projection_builder().project(
        _request(
            module,
            domain_request=domain_request,
            domain_result=domain_result,
            identity_request=normalized_request,
            identity_result=normalized_result,
            locators=locators,
        )
    )

    assert len(result.person_projections) == 1
    paper_reference = next(
        reference
        for reference in result.person_projections[0].references
        if reference.source_kind == "paper_author"
    )
    assert profile_record_id not in paper_reference.shared_source_record_ids
    assert any(
        assertion.assertion_id in paper_reference.identity_assertion_ids
        and assertion.source_record_id == profile_record_id
        for assertion in normalized_result.identity_assertions
    )


def test_current_accepted_verdict_upgrades_prior_unresolved_topology() -> None:
    module = _module()
    domain_request, domain_result, initial_request, initial_result, locators = (
        _unresolved_person_graph(module)
    )
    orcid_by_source = {
        source.source_identity_id: f"0000-0001-0000-000{index}"
        for index, source in enumerate(initial_request.source_identities, start=1)
    }
    updated_sources = tuple(
        source.model_copy(
            update={
                "normalized_keys": {
                    **source.normalized_keys,
                    "orcid": orcid_by_source[source.source_identity_id],
                }
            }
        )
        for source in initial_request.source_identities
    )
    updated_assertions = (
        *initial_request.identity_assertions,
        *(
            identity_models.SourceAssertion(
                assertion_id=f"assertion:{source.source_identity_id}:orcid",
                source_record_id=source.source_record_ids[0],
                source_identity_id=source.source_identity_id,
                subject_entity_type="person",
                field_path="identity.orcid",
                value=orcid_by_source[source.source_identity_id],
                observed_at=NOW,
                assertion_run_id="s6r-person-orcid-separation",
            )
            for source in updated_sources
        ),
    )
    reviewed_request = identity_models.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id="s6r-person-identity-reviewed-separation",
        identity_method_version="canonical-identity-resolution-person-v1",
        as_of=NOW,
        policy=initial_request.policy,
        source_identities=updated_sources,
        identity_assertions=updated_assertions,
        current_canonical_identities=initial_result.current_canonical_identities,
        current_source_identity_assignments=(
            initial_result.source_identity_assignments
        ),
        canonical_identity_history=initial_result.canonical_identity_history,
        prior_identity_decisions=initial_result.identity_decisions,
        prior_decision_contexts=initial_result.decision_contexts,
    )
    reviewed_result = (
        identity_models.create_ephemeral_canonical_identity_resolution_engine().resolve(
            reviewed_request
        )
    )
    accepted_verdict = reviewed_result.candidate_verdicts[0]
    assert accepted_verdict.verdict.value == "different_entities"

    result = module.create_ephemeral_internal_reference_projection_builder().project(
        _request(
            module,
            domain_request=domain_request,
            domain_result=domain_result,
            identity_request=reviewed_request,
            identity_result=reviewed_result,
            locators=locators,
        )
    )

    assert len(result.person_projections) == 2
    assert result.unresolved_person_references == ()
    assert all(
        reference.candidate_verdict_id == accepted_verdict.verdict_id
        for projection in result.person_projections
        for reference in projection.references
    )


def test_current_unresolved_verdict_does_not_downgrade_accepted_topology() -> None:
    module = _module()
    domain_request, domain_result, initial_request, initial_result, locators = (
        _resolved_person_graph(module)
    )
    accepted_identity = initial_result.current_canonical_identities[0]
    accepted_context = next(
        context
        for context in initial_result.decision_contexts
        if context.decision_id == accepted_identity.identity_decision_id
    )
    assert accepted_context.candidate_verdict is not None
    assert accepted_context.candidate_verdict.verdict.value == "same_entity"

    name_only_sources = tuple(
        source.model_copy(
            update={"normalized_keys": {"name_key": source.normalized_keys["name_key"]}}
        )
        for source in initial_request.source_identities
    )
    name_only_request = identity_models.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id="s6r-person-current-unresolved",
        identity_method_version="canonical-identity-resolution-person-v1",
        as_of=NOW,
        policy=initial_request.policy,
        source_identities=name_only_sources,
        identity_assertions=tuple(
            assertion
            for assertion in initial_request.identity_assertions
            if assertion.field_path != "identity.orcid"
        ),
        current_canonical_identities=initial_result.current_canonical_identities,
        current_source_identity_assignments=(
            initial_result.source_identity_assignments
        ),
        canonical_identity_history=initial_result.canonical_identity_history,
        prior_identity_decisions=initial_result.identity_decisions,
        prior_decision_contexts=initial_result.decision_contexts,
    )
    name_only_result = (
        identity_models.create_ephemeral_canonical_identity_resolution_engine().resolve(
            name_only_request
        )
    )
    current_verdict = name_only_result.candidate_verdicts[0]
    assert current_verdict.verdict.value == "unresolved"

    result = module.create_ephemeral_internal_reference_projection_builder().project(
        _request(
            module,
            domain_request=domain_request,
            domain_result=domain_result,
            identity_request=name_only_request,
            identity_result=name_only_result,
            locators=locators,
        )
    )

    assert len(result.person_projections) == 1
    assert result.unresolved_person_references == ()
    assert result.person_projections[0].identity_verdict_ids == (
        accepted_context.candidate_verdict.verdict_id,
    )
    assert current_verdict.verdict_id not in (
        result.person_projections[0].identity_verdict_ids
    )


def test_accepted_person_singleton_survives_later_ambiguous_reference() -> None:
    module = _module()
    domain_request, domain_result, base_request, _, locators = _unresolved_person_graph(
        module
    )
    existing_source = next(
        source
        for source in base_request.source_identities
        if source.source_identity_id.endswith("paper_author")
    )
    new_source = next(
        source
        for source in base_request.source_identities
        if source.source_identity_id.endswith("patent_inventor")
    )
    orcid = "0000-0001-2345-6789"
    accepted_source = existing_source.model_copy(
        update={
            "normalized_keys": {
                **existing_source.normalized_keys,
                "orcid": orcid,
            }
        }
    )
    orcid_assertion = identity_models.SourceAssertion(
        assertion_id=f"assertion:{accepted_source.source_identity_id}:orcid",
        source_record_id=accepted_source.source_record_ids[0],
        source_identity_id=accepted_source.source_identity_id,
        subject_entity_type="person",
        field_path="identity.orcid",
        value=orcid,
        observed_at=NOW,
        assertion_run_id="s6r-person-singleton-identity",
    )
    accepted_assertions = tuple(
        assertion
        for assertion in base_request.identity_assertions
        if assertion.source_identity_id == accepted_source.source_identity_id
    ) + (orcid_assertion,)
    accepted_request = identity_models.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id="s6r-person-singleton-accepted",
        identity_method_version="canonical-identity-resolution-person-v1",
        as_of=NOW,
        policy=base_request.policy,
        source_identities=(accepted_source,),
        identity_assertions=accepted_assertions,
    )
    engine = identity_models.create_ephemeral_canonical_identity_resolution_engine()
    accepted_result = engine.resolve(accepted_request)
    assert accepted_result.candidate_verdicts == ()
    assert len(accepted_result.current_canonical_identities) == 1

    later_request = identity_models.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id="s6r-person-singleton-later-ambiguity",
        identity_method_version="canonical-identity-resolution-person-v1",
        as_of=NOW,
        policy=base_request.policy,
        source_identities=(accepted_source, new_source),
        identity_assertions=(*base_request.identity_assertions, orcid_assertion),
        current_canonical_identities=accepted_result.current_canonical_identities,
        current_source_identity_assignments=(
            accepted_result.source_identity_assignments
        ),
        canonical_identity_history=accepted_result.canonical_identity_history,
        prior_identity_decisions=accepted_result.identity_decisions,
        prior_decision_contexts=accepted_result.decision_contexts,
    )
    later_result = engine.resolve(later_request)
    current_verdict = later_result.candidate_verdicts[0]
    assert current_verdict.verdict.value == "unresolved"
    assert {
        assignment.source_identity_id
        for assignment in later_result.source_identity_assignments
    } == {accepted_source.source_identity_id}

    result = module.create_ephemeral_internal_reference_projection_builder().project(
        _request(
            module,
            domain_request=domain_request,
            domain_result=domain_result,
            identity_request=later_request,
            identity_result=later_result,
            locators=locators,
        )
    )

    assert len(result.person_projections) == 1
    projection = result.person_projections[0]
    assert {item.source_identity_id for item in projection.references} == {
        accepted_source.source_identity_id
    }
    assert projection.identity_verdict_ids == ()
    assert projection.references[0].candidate_verdict_id is None
    assert tuple(
        item.source_identity_id for item in result.unresolved_person_references
    ) == (new_source.source_identity_id,)
    assert (
        result.unresolved_person_references[0].candidate_verdict_id
        == current_verdict.verdict_id
    )


def test_carried_unresolved_topology_stays_unresolved_across_identity_noop() -> None:
    module = _module()
    domain_request, domain_result, initial_request, initial_result, locators = (
        _unresolved_person_graph(module)
    )
    renamed_sources = tuple(
        source.model_copy(
            update={
                "normalized_keys": {
                    "name_key": f"Wei Zhang {source.source_identity_id}"
                }
            }
        )
        for source in initial_request.source_identities
    )
    noop_request = identity_models.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id="s6r-person-identity-noop",
        identity_method_version="canonical-identity-resolution-person-v1",
        as_of=NOW,
        policy=initial_request.policy,
        source_identities=renamed_sources,
        identity_assertions=initial_request.identity_assertions,
        current_canonical_identities=initial_result.current_canonical_identities,
        current_source_identity_assignments=initial_result.source_identity_assignments,
        canonical_identity_history=initial_result.canonical_identity_history,
        prior_identity_decisions=initial_result.identity_decisions,
        prior_decision_contexts=initial_result.decision_contexts,
    )
    noop_result = (
        identity_models.create_ephemeral_canonical_identity_resolution_engine().resolve(
            noop_request
        )
    )
    assert noop_result.candidate_verdicts == ()
    assert noop_result.identity_decisions == ()
    assert noop_result.decision_contexts == ()

    result = module.create_ephemeral_internal_reference_projection_builder().project(
        _request(
            module,
            domain_request=domain_request,
            domain_result=domain_result,
            identity_request=noop_request,
            identity_result=noop_result,
            locators=locators,
        )
    )

    assert result.person_projections == ()
    assert len(result.unresolved_person_references) == 2
    assert all(
        item.canonical_person_identity_id is None
        and item.assignment_decision_id is None
        for item in result.unresolved_person_references
    )


def test_person_projection_rejects_cross_wired_release_type_anchor_and_evidence() -> (
    None
):
    module = _module()
    domain_request, domain_result, identity_request, identity_result, locators = (
        _resolved_person_graph(module)
    )
    builder = module.create_ephemeral_internal_reference_projection_builder()

    mismatched_domain_request, _, _, _, _ = _unresolved_person_graph(module)
    with pytest.raises(
        module.InternalReferenceProjectionIntegrityError,
        match="cannot be rebuilt from its exact request",
    ):
        builder.project(
            _request(
                module,
                domain_request=mismatched_domain_request,
                domain_result=domain_result,
                identity_request=identity_request,
                identity_result=identity_result,
                locators=locators,
            )
        )

    paper_index = next(
        index
        for index, locator in enumerate(locators)
        if locator.source_kind == "paper_author"
    )
    patent_index = next(
        index
        for index, locator in enumerate(locators)
        if locator.source_kind == "patent_inventor"
    )
    wrong_subobject = list(locators)
    wrong_subobject[paper_index] = wrong_subobject[paper_index].model_copy(
        update={"source_subobject_id": "paper-author:missing"}
    )
    with pytest.raises(
        module.InternalReferenceProjectionIntegrityError,
        match="typed subobject",
    ):
        builder.project(
            _request(
                module,
                domain_request=domain_request,
                domain_result=domain_result,
                identity_request=identity_request,
                identity_result=identity_result,
                locators=tuple(wrong_subobject),
            )
        )

    wrong_kind = list(locators)
    wrong_kind[paper_index] = wrong_kind[paper_index].model_copy(
        update={"source_kind": "patent_inventor"}
    )
    with pytest.raises(
        module.InternalReferenceProjectionIntegrityError,
        match="root projection",
    ):
        builder.project(
            _request(
                module,
                domain_request=domain_request,
                domain_result=domain_result,
                identity_request=identity_request,
                identity_result=identity_result,
                locators=tuple(wrong_kind),
            )
        )

    cross_wired_sources = list(locators)
    paper_source_id = cross_wired_sources[paper_index].source_identity_id
    patent_source_id = cross_wired_sources[patent_index].source_identity_id
    cross_wired_sources[paper_index] = cross_wired_sources[paper_index].model_copy(
        update={"source_identity_id": patent_source_id}
    )
    cross_wired_sources[patent_index] = cross_wired_sources[patent_index].model_copy(
        update={"source_identity_id": paper_source_id}
    )
    with pytest.raises(
        module.InternalReferenceProjectionIntegrityError,
        match="does not share a source record",
    ):
        builder.project(
            _request(
                module,
                domain_request=domain_request,
                domain_result=domain_result,
                identity_request=identity_request,
                identity_result=identity_result,
                locators=tuple(cross_wired_sources),
            )
        )

    (
        unresolved_domain_request,
        unresolved_domain,
        unresolved_request,
        _unresolved_result,
        _,
    ) = _unresolved_person_graph(module)
    del unresolved_domain_request
    del unresolved_domain
    with pytest.raises(
        module.InternalReferenceProjectionIntegrityError,
        match="closed domain or identity lineage",
    ):
        builder.project(
            _request(
                module,
                domain_request=domain_request,
                domain_result=domain_result,
                identity_request=unresolved_request,
                identity_result=identity_result,
                locators=locators,
            )
        )

    wrong_release_domain = domain_result.model_copy(
        update={"release_id": "wrong-release"}
    )
    with pytest.raises(ValidationError, match="result envelope"):
        _request(
            module,
            domain_request=domain_request,
            domain_result=wrong_release_domain,
            identity_request=identity_request,
            identity_result=identity_result,
            locators=locators,
        )

    valid_request = _request(
        module,
        domain_request=domain_request,
        domain_result=domain_result,
        identity_request=identity_request,
        identity_result=identity_result,
        locators=locators,
    )
    wrong_catalog_identity = module.ReferenceCatalogIdentity.model_construct(
        schema_version=REFERENCE_CATALOG_SCHEMA_VERSION,
        catalog_version=REFERENCE_CATALOG_VERSION,
        content_sha256="0" * 64,
    )
    with pytest.raises(
        module.InternalReferenceProjectionIntegrityError,
        match="catalog identity",
    ):
        builder.project(
            valid_request.model_copy(
                update={"reference_catalog_identity": wrong_catalog_identity}
            )
        )


def test_technology_concepts_and_routes_preserve_precise_evidence_semantics() -> None:
    module = _technology_module()
    graph = _technology_graph(module)
    request = _request(
        module,
        domain_request=graph["domain_request"],
        domain_result=graph["domain_result"],
        identity_request=graph["person_request"],
        identity_result=graph["person_result"],
        locators=graph["person_locators"],
        technology_identity_resolution_request=graph["technology_request"].model_dump(
            mode="python"
        ),
        technology_identity_resolution_result=graph["technology_result"].model_dump(
            mode="python"
        ),
        technology_evidence_locators=graph["technology_locators"],
    )

    result = module.create_ephemeral_internal_reference_projection_builder().project(
        request
    )

    concepts = {
        item.canonical_technology_identity_id: item
        for item in result.technology_concept_projections
    }
    canonical_ids = graph["technology_canonical_ids"]
    root_id = canonical_ids["source-tech-concept-robotics"]
    child_id = canonical_ids["source-tech-concept-visual-control"]
    route_id = canonical_ids["source-tech-route-visual-servo"]
    root = concepts[root_id]
    child = concepts[child_id]
    route = result.technology_route_projections[0]
    assert root.aliases == ("robotic systems",)
    assert root.definition == "Evidence-backed robotics concept"
    assert child.parent_concept_ids == (root.canonical_technology_identity_id,)
    assert child.source_anchor_ids
    assert set(child.supporting_assertion_ids) >= {
        "assertion:source-tech-concept-visual-control:definition",
        "assertion:source-tech-concept-visual-control:links",
        "assertion:source-tech-concept-visual-control:public-reference",
    }
    assert child.observed_at == NOW
    assert route.definition == "A route using visual feedback"
    assert route.concept_ids == (child.canonical_technology_identity_id,)
    assert route.canonical_technology_identity_id == route_id
    assert route.release_id == RELEASE_ID
    assert len(result.technology_evidence_anchors) == 3
    assert all(
        item.root_canonical_identity_id == graph["company_id"]
        and item.source_subobject_id == graph["product_id"]
        and item.source_subobject_type == "product"
        for item in result.technology_evidence_anchors
    )
    assert result.unresolved_technology_references == ()
    serialized = result.model_dump(mode="json")
    assert "product_capability_projections" not in serialized
    assert "technology_relationships" not in serialized
    module.validate_internal_reference_projection_result(request, result)


def test_unresolved_technology_term_never_materializes_a_route_identity() -> None:
    module = _technology_module()
    unresolved_source_id = "source-tech-route-visual-servo"
    graph = _technology_graph(
        module,
        unresolved_source_identity_id=unresolved_source_id,
    )
    assert all(
        unresolved_source_id not in identity.source_identity_ids
        for identity in graph["technology_result"].current_canonical_identities
    )
    assert all(
        assignment.source_identity_id != unresolved_source_id
        for assignment in graph["technology_result"].source_identity_assignments
    )
    assert all(
        unresolved_source_id not in decision.source_identity_ids
        for decision in graph["technology_result"].identity_decisions
    )
    request = _request(
        module,
        domain_request=graph["domain_request"],
        domain_result=graph["domain_result"],
        identity_request=graph["person_request"],
        identity_result=graph["person_result"],
        locators=graph["person_locators"],
        technology_identity_resolution_request=graph["technology_request"],
        technology_identity_resolution_result=graph["technology_result"],
        technology_evidence_locators=graph["technology_locators"],
    )

    result = module.create_ephemeral_internal_reference_projection_builder().project(
        request
    )

    assert len(result.technology_concept_projections) == 2
    assert result.technology_route_projections == ()
    assert len(result.unresolved_technology_references) == 1
    unresolved = result.unresolved_technology_references[0]
    assert unresolved.technology_source_identity_id == unresolved_source_id
    assert unresolved.resolution_state == "unresolved"
    assert unresolved.reference_type == "technology_route"
    module.validate_internal_reference_projection_result(request, result)


def test_accepted_technology_singleton_survives_later_ambiguous_term() -> None:
    module = _technology_module()
    graph = _technology_graph(module)
    existing_source_id = "source-tech-route-visual-servo"
    new_source_id = "source-tech-route-visual-servo-name-only"
    crosswalk = {
        "public_domain": "company",
        "root_canonical_identity_id": graph["company_id"],
        "source_field_path": "product",
        "source_subobject_type": "product",
        "source_subobject_id": graph["product_id"],
    }
    new_source, new_assertions = _technology_source(
        source_identity_id=new_source_id,
        entity_type="technology_route",
        preferred_name="visual servoing",
        aliases=("visual feedback route",),
        definition="A newly observed unresolved route term.",
        public_reference_locator=crosswalk,
        public_source_record_id=graph["product_record_id"],
        linked_source_identity_ids=("source-tech-concept-visual-control",),
    )
    new_source = new_source.model_copy(
        update={"normalized_keys": {"name_key": "visual servoing"}}
    )
    sparse_new_assertions = tuple(
        assertion
        for assertion in new_assertions
        if assertion.field_path
        in {
            "technology.preferred_name",
            "technology.public_reference_locator",
        }
    )
    initial_request = graph["technology_request"]
    initial_result = graph["technology_result"]
    later_request = identity_models.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id="s6r-technology-singleton-later-ambiguity",
        identity_method_version=(identity_models.TECHNOLOGY_IDENTITY_METHOD_VERSION),
        as_of=NOW,
        policy=initial_request.policy,
        source_identities=(*initial_request.source_identities, new_source),
        identity_assertions=(
            *initial_request.identity_assertions,
            *sparse_new_assertions,
        ),
        current_canonical_identities=initial_result.current_canonical_identities,
        current_source_identity_assignments=(
            initial_result.source_identity_assignments
        ),
        canonical_identity_history=initial_result.canonical_identity_history,
        prior_identity_decisions=initial_result.identity_decisions,
        prior_decision_contexts=initial_result.decision_contexts,
    )
    later_result = (
        identity_models.create_ephemeral_canonical_identity_resolution_engine().resolve(
            later_request
        )
    )
    current_verdict = next(
        verdict
        for verdict in later_result.candidate_verdicts
        if new_source_id in verdict.source_identity_ids
    )
    assert current_verdict.verdict.value == "unresolved"
    assert new_source_id not in {
        assignment.source_identity_id
        for assignment in later_result.source_identity_assignments
    }
    locators = (
        *graph["technology_locators"],
        module.TechnologyEvidenceLocator(
            reference_id=f"technology-ref:{new_source_id}",
            reference_type="technology_route",
            technology_source_identity_id=new_source_id,
            **crosswalk,
        ),
    )
    request = _request(
        module,
        domain_request=graph["domain_request"],
        domain_result=graph["domain_result"],
        identity_request=graph["person_request"],
        identity_result=graph["person_result"],
        locators=graph["person_locators"],
        technology_identity_resolution_request=later_request,
        technology_identity_resolution_result=later_result,
        technology_evidence_locators=locators,
    )

    result = module.create_ephemeral_internal_reference_projection_builder().project(
        request
    )

    assert len(result.technology_route_projections) == 1
    route = result.technology_route_projections[0]
    assert route.source_identity_ids == (existing_source_id,)
    assert route.identity_verdict_ids == ()
    assert tuple(
        item.technology_source_identity_id
        for item in result.unresolved_technology_references
    ) == (new_source_id,)
    assert (
        result.unresolved_technology_references[0].candidate_verdict_id
        == current_verdict.verdict_id
    )


def test_sparse_unresolved_technology_retains_term_and_crosswalk_only() -> None:
    module = _technology_module()
    unresolved_source_id = "source-tech-route-visual-servo"
    graph = _technology_graph(
        module,
        unresolved_source_identity_id=unresolved_source_id,
    )
    sparse_assertions = tuple(
        assertion
        for assertion in graph["technology_request"].identity_assertions
        if assertion.source_identity_id != unresolved_source_id
        or assertion.field_path
        in {
            "technology.preferred_name",
            "technology.public_reference_locator",
        }
    )
    technology_request, technology_result = _technology_identity_resolution(
        graph["technology_request"].source_identities,
        sparse_assertions,
    )
    request = _request(
        module,
        domain_request=graph["domain_request"],
        domain_result=graph["domain_result"],
        identity_request=graph["person_request"],
        identity_result=graph["person_result"],
        locators=graph["person_locators"],
        technology_identity_resolution_request=technology_request,
        technology_identity_resolution_result=technology_result,
        technology_evidence_locators=graph["technology_locators"],
    )

    result = module.create_ephemeral_internal_reference_projection_builder().project(
        request
    )

    assert result.technology_route_projections == ()
    assert len(result.unresolved_technology_references) == 1
    unresolved = result.unresolved_technology_references[0]
    assert unresolved.technology_source_identity_id == unresolved_source_id
    assert unresolved.preferred_name == "visual servoing"
    assert set(unresolved.identity_assertion_ids) == {
        f"assertion:{unresolved_source_id}:identity-name",
        f"assertion:{unresolved_source_id}:public-reference",
    }


def test_repeated_identical_technology_observation_is_retained_in_lineage() -> None:
    module = _technology_module()
    graph = _technology_graph(module)
    source_id = "source-tech-concept-visual-control"
    original_crosswalk = next(
        assertion
        for assertion in graph["technology_request"].identity_assertions
        if assertion.source_identity_id == source_id
        and assertion.field_path == "technology.public_reference_locator"
    )
    repeated_crosswalk = original_crosswalk.model_copy(
        update={"assertion_id": f"{original_crosswalk.assertion_id}:repeat"}
    )
    original_aliases = next(
        assertion
        for assertion in graph["technology_request"].identity_assertions
        if assertion.source_identity_id == source_id
        and assertion.field_path == "technology.aliases"
    )
    retained_aliases = original_aliases.model_copy(
        update={
            "value": ["vision-based control", "visual-feedback control"],
        }
    )
    repeated_aliases = retained_aliases.model_copy(
        update={
            "assertion_id": f"{original_aliases.assertion_id}:repeat",
            "value": ["visual-feedback control", "vision-based control"],
        }
    )
    assertions = tuple(
        retained_aliases
        if assertion.assertion_id == original_aliases.assertion_id
        else assertion
        for assertion in graph["technology_request"].identity_assertions
    )
    technology_request, technology_result = _technology_identity_resolution(
        graph["technology_request"].source_identities,
        (*assertions, repeated_aliases, repeated_crosswalk),
    )
    request = _request(
        module,
        domain_request=graph["domain_request"],
        domain_result=graph["domain_result"],
        identity_request=graph["person_request"],
        identity_result=graph["person_result"],
        locators=graph["person_locators"],
        technology_identity_resolution_request=technology_request,
        technology_identity_resolution_result=technology_result,
        technology_evidence_locators=graph["technology_locators"],
    )

    result = module.create_ephemeral_internal_reference_projection_builder().project(
        request
    )

    concept = next(
        item
        for item in result.technology_concept_projections
        if source_id in item.source_identity_ids
    )
    crosswalk_lineage = next(
        item
        for item in concept.field_lineage
        if item.field_path == "technology.public_reference_locator"
    )
    assert crosswalk_lineage.supporting_assertion_ids == tuple(
        sorted((original_crosswalk.assertion_id, repeated_crosswalk.assertion_id))
    )
    aliases_lineage = next(
        item
        for item in concept.field_lineage
        if item.field_path == "technology.aliases"
    )
    assert aliases_lineage.supporting_assertion_ids == tuple(
        sorted((retained_aliases.assertion_id, repeated_aliases.assertion_id))
    )


def test_technology_crosswalk_and_full_replay_reject_rehashed_fabrication() -> None:
    module = _technology_module()
    graph = _technology_graph(module)
    request = _request(
        module,
        domain_request=graph["domain_request"],
        domain_result=graph["domain_result"],
        identity_request=graph["person_request"],
        identity_result=graph["person_result"],
        locators=graph["person_locators"],
        technology_identity_resolution_request=graph["technology_request"],
        technology_identity_resolution_result=graph["technology_result"],
        technology_evidence_locators=graph["technology_locators"],
    )
    builder = module.create_ephemeral_internal_reference_projection_builder()
    result = builder.project(request)

    route_crosswalk = next(
        assertion
        for assertion in graph["technology_request"].identity_assertions
        if assertion.source_identity_id == "source-tech-route-visual-servo"
        and assertion.field_path == "technology.public_reference_locator"
    )
    assert isinstance(route_crosswalk.value, dict)
    unmatched_crosswalk = route_crosswalk.model_copy(
        update={
            "assertion_id": f"{route_crosswalk.assertion_id}:unmatched",
            "value": {
                **route_crosswalk.value,
                "source_subobject_id": "product:unchecked",
            },
        }
    )
    changed_technology_request, changed_technology_result = (
        _technology_identity_resolution(
            graph["technology_request"].source_identities,
            (*graph["technology_request"].identity_assertions, unmatched_crosswalk),
        )
    )
    with pytest.raises(
        module.InternalReferenceProjectionIntegrityError,
        match="exhaustively covered",
    ):
        builder.project(
            request.model_copy(
                update={
                    "technology_identity_resolution_request": (
                        changed_technology_request
                    ),
                    "technology_identity_resolution_result": (
                        changed_technology_result
                    ),
                }
            )
        )

    route_locator = next(
        item
        for item in request.technology_evidence_locators
        if item.reference_type == "technology_route"
    )
    wrong_locator = route_locator.model_copy(
        update={"source_subobject_id": "product:other"}
    )
    with pytest.raises(
        module.InternalReferenceProjectionIntegrityError,
        match="exact selected Product",
    ):
        builder.project(
            request.model_copy(
                update={
                    "technology_evidence_locators": tuple(
                        wrong_locator if item == route_locator else item
                        for item in request.technology_evidence_locators
                    )
                }
            )
        )

    route = result.technology_route_projections[0]
    fabricated_route_payload = route.model_dump(mode="python")
    fabricated_route_payload["definition"] = "Fabricated capability-like route"
    fabricated_route_payload["content_sha256"] = _canonical_hash(
        {
            key: value
            for key, value in module.TechnologyRouteProjection.model_validate(
                {**fabricated_route_payload, "content_sha256": "0" * 64},
                context={"allow_unbound_projection_hash": True},
            )
            .model_dump(mode="json")
            .items()
            if key != "content_sha256"
        }
    )
    fabricated_route = module.TechnologyRouteProjection.model_validate(
        fabricated_route_payload
    )
    fabricated_result_payload = result.model_dump(mode="python")
    fabricated_result_payload["technology_route_projections"] = (fabricated_route,)
    provisional_result = module.InternalReferenceProjectionResult.model_validate(
        {**fabricated_result_payload, "content_sha256": "0" * 64},
        context={"allow_unbound_projection_hash": True},
    )
    fabricated_result_payload["content_sha256"] = _canonical_hash(
        provisional_result.model_dump(mode="json", exclude={"content_sha256"})
    )
    fabricated_result = module.InternalReferenceProjectionResult.model_validate(
        fabricated_result_payload
    )
    with pytest.raises(
        module.InternalReferenceProjectionIntegrityError,
        match="cannot be replayed",
    ):
        module.validate_internal_reference_projection_result(request, fabricated_result)


def _technology_relationship_fixture_inputs() -> dict[str, Any]:
    internal_module = _technology_module()
    relationship_module: Any = import_module(
        "src.data_agents.canonical_v2.relationship_projection"
    )
    graph = _technology_graph(internal_module)
    internal_request = _request(
        internal_module,
        domain_request=graph["domain_request"],
        domain_result=graph["domain_result"],
        identity_request=graph["person_request"],
        identity_result=graph["person_result"],
        locators=graph["person_locators"],
        technology_identity_resolution_request=graph["technology_request"].model_dump(
            mode="python"
        ),
        technology_identity_resolution_result=graph["technology_result"].model_dump(
            mode="python"
        ),
        technology_evidence_locators=graph["technology_locators"],
    )
    internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
        internal_request
    )
    route = internal_result.technology_route_projections[0]
    source_endpoint = relationship_module.RelationshipEndpointReference(
        reference_kind="typed_subobject",
        endpoint_type="product",
        stable_reference=graph["product_id"],
        parent_canonical_identity_ref=(f"canonical:company:{graph['company_id']}"),
    )
    target_endpoint = relationship_module.RelationshipEndpointReference(
        reference_kind="canonical_identity",
        endpoint_type="technology_route",
        stable_reference=(
            f"canonical:technology_route:{route.canonical_technology_identity_id}"
        ),
        canonical_identity_id=route.canonical_technology_identity_id,
    )
    policy = PolicyReference(
        policy_id="technology-relationship-policy",
        policy_version="technology-relationship-policy-v1",
        policy_kind=PolicyKind.relationship,
        content_sha256="4" * 64,
        effective_at=NOW - timedelta(days=1),
    )
    semantics = {
        "discussion_or_mention": (
            "entity_discusses_or_mentions_technology",
            "technology_discussion_assertion",
            None,
        ),
        "claimed_adoption": (
            "entity_claims_adoption_of_technology",
            "technology_adoption_claim_assertion",
            NOW,
        ),
        "demonstrated_use": (
            "entity_demonstrates_use_of_technology",
            "technology_demonstrated_use_assertion",
            NOW,
        ),
    }
    candidates: list[Any] = []
    typed_assertions: list[Any] = []
    decisions: list[Any] = []
    retained_assertions: list[Any] = []
    for semantic_state, (
        relationship_type_id,
        evidence_kind,
        valid_from,
    ) in semantics.items():
        retained = relationship_module.RetainedAssertionReference(
            reference_id=f"retained:technology:{semantic_state}",
            assertion_id=graph["technology_relationship_assertion_ids"][semantic_state],
            source_record_ref=graph["product_record_id"],
            artifact_refs=(),
        )
        binding = relationship_module.RetainedEvidenceBinding(
            evidence_kind=evidence_kind,
            assertion_refs=(retained.reference_id,),
            artifact_refs=(),
        )
        candidate_id = f"candidate:technology:{semantic_state}"
        typed_assertion_id = f"typed-assertion:technology:{semantic_state}"
        decision_input_id = f"decision-input:technology:{semantic_state}"
        role_bindings = {"technology": target_endpoint.stable_reference}
        candidates.append(
            relationship_module.RelationshipProjectionCandidate(
                candidate_id=candidate_id,
                relationship_type_id=relationship_type_id,
                relationship_type_version="canonical-v2-relationship-v1",
                source_endpoint=source_endpoint,
                target_endpoint=target_endpoint,
                role_bindings=role_bindings,
                evidence_metadata={"semantic_state": semantic_state},
                requested_paths=("relationship_traversal",),
                observed_at=NOW,
                valid_from=valid_from,
                evidence_bindings=(binding,),
                assertion_input_id=typed_assertion_id,
                assertion_input_kind="typed_relationship_assertion",
                decision_input_id=decision_input_id,
            )
        )
        typed_assertions.append(
            relationship_module.TypedRelationshipAssertionInput(
                assertion_id=typed_assertion_id,
                relationship_type_id=relationship_type_id,
                relationship_type_version="canonical-v2-relationship-v1",
                source_record_ref=graph["product_record_id"],
                source_endpoint=source_endpoint,
                target_endpoint=target_endpoint,
                attributes={
                    "candidate_id": candidate_id,
                    "evidence_metadata": {"semantic_state": semantic_state},
                    "role_bindings": role_bindings,
                },
                evidence_bindings=(binding,),
                observed_at=NOW,
                valid_from=valid_from,
                assertion_run_id="technology-relationship-assertion-run",
            )
        )
        decisions.append(
            relationship_module.RelationshipDecisionInput(
                decision_input_id=decision_input_id,
                decision_id=f"relationship-decision:technology:{semantic_state}",
                canonical_relationship_id=(f"relationship:technology:{semantic_state}"),
                state="accepted",
                candidate_assertion_ids=(typed_assertion_id,),
                selected_assertion_ids=(typed_assertion_id,),
                conflicting_assertion_ids=(),
                role_bindings=role_bindings,
                selected_evidence_refs=(retained.reference_id,),
                policy=policy,
                method=DecisionMethod.deterministic,
                method_version="technology-relationship-deterministic-v1",
                confidence=1.0,
                rationale="Exact retained Technology evidence state.",
            )
        )
        retained_assertions.append(retained)

    return {
        "internal_module": internal_module,
        "relationship_module": relationship_module,
        "graph": graph,
        "internal_request": internal_request,
        "internal_result": internal_result,
        "source_endpoint": source_endpoint,
        "target_endpoint": target_endpoint,
        "policy": policy,
        "semantics": semantics,
        "candidates": candidates,
        "typed_assertions": typed_assertions,
        "decisions": decisions,
        "retained_assertions": retained_assertions,
    }


def _technology_relationship_request(
    fixture: dict[str, Any],
    *,
    projection_run_id: str = "technology-relationship-projection-run",
    candidates: Any | None = None,
    typed_assertions: Any | None = None,
    decisions: Any | None = None,
    retained_assertions: Any | None = None,
    retained_artifacts: Any = (),
) -> Any:
    relationship_module = fixture["relationship_module"]
    graph = fixture["graph"]
    return relationship_module.RelationshipProjectionRequest(
        catalog=relationship_module.RelationshipCatalogIdentity(
            schema_version=CATALOG_SCHEMA_VERSION,
            catalog_version=CATALOG_VERSION,
            content_sha256=CATALOG_CONTENT_SHA256,
        ),
        release_id=RELEASE_ID,
        projection_run_id=projection_run_id,
        as_of=NOW,
        decision_policy=fixture["policy"],
        relationship_registry_version=(
            relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_VERSION
        ),
        relationship_registry_content_sha256=(
            relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_CONTENT_SHA256
        ),
        domain_projections=graph["domain_result"].projections,
        internal_reference_projection_request=fixture["internal_request"],
        internal_reference_projection_result=fixture["internal_result"],
        candidates=tuple(fixture["candidates"] if candidates is None else candidates),
        relationship_assertions=(),
        typed_relationship_assertions=tuple(
            fixture["typed_assertions"]
            if typed_assertions is None
            else typed_assertions
        ),
        source_canonical_assignments=(),
        decision_inputs=tuple(fixture["decisions"] if decisions is None else decisions),
        retained_assertions=tuple(
            fixture["retained_assertions"]
            if retained_assertions is None
            else retained_assertions
        ),
        retained_artifacts=tuple(retained_artifacts),
    )


def _technology_relationship_authority(
    *,
    release_id: str,
    authoritative_zero: bool = False,
) -> tuple[Any, Any, Any, Any]:
    global RELEASE_ID

    previous_release_id = RELEASE_ID
    RELEASE_ID = release_id
    try:
        fixture = _technology_relationship_fixture_inputs()
        relationship_module = fixture["relationship_module"]
        relationship_request = _technology_relationship_request(
            fixture,
            projection_run_id=(
                "technology-relationship-zero-run"
                if authoritative_zero
                else "technology-relationship-publication-run"
            ),
            candidates=() if authoritative_zero else None,
            typed_assertions=() if authoritative_zero else None,
            decisions=() if authoritative_zero else None,
            retained_assertions=() if authoritative_zero else None,
        )
        relationship_result = (
            relationship_module.create_ephemeral_relationship_projection().project(
                relationship_request
            )
        )
        candidate_module = _candidate_projection_module()
        candidate_request = _candidate_projection_request(
            candidate_module,
            fixture["internal_request"],
            fixture["internal_result"],
        )
        candidate_result = candidate_module.compose_candidate_projections(
            candidate_request
        )
        return (
            candidate_request,
            candidate_result,
            relationship_request,
            relationship_result,
        )
    finally:
        RELEASE_ID = previous_release_id


def _company_patent_relationship_authority(
    *,
    release_id: str,
    authoritative_zero: bool = False,
) -> tuple[Any, Any, Any, Any]:
    global RELEASE_ID

    previous_release_id = RELEASE_ID
    RELEASE_ID = release_id
    try:
        internal_module = _technology_module()
        relationship_module = import_module(
            "src.data_agents.canonical_v2.relationship_projection"
        )
        (
            domain_request,
            domain_result,
            identity_request,
            identity_result,
            person_locators,
        ) = _resolved_person_graph(
            internal_module,
            include_company_patent_applicant=True,
        )
        internal_request = _request(
            internal_module,
            domain_request=domain_request,
            domain_result=domain_result,
            identity_request=identity_request,
            identity_result=identity_result,
            locators=person_locators,
        )
        internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
            internal_request
        )
        candidate_module = _candidate_projection_module()
        candidate_request = _candidate_projection_request(
            candidate_module,
            internal_request,
            internal_result,
        )
        candidate_result = candidate_module.compose_candidate_projections(
            candidate_request
        )

        source_endpoint = relationship_module.RelationshipEndpointReference(
            reference_kind="canonical_identity",
            endpoint_type="patent",
            stable_reference="canonical:patent:patent-ada",
            canonical_identity_id="patent-ada",
        )
        target_endpoint = relationship_module.RelationshipEndpointReference(
            reference_kind="canonical_identity",
            endpoint_type="company",
            stable_reference="canonical:company:company-robotics",
            canonical_identity_id="company-robotics",
        )
        policy = PolicyReference(
            policy_id="company-patent-relationship-policy",
            policy_version="company-patent-relationship-policy-v1",
            policy_kind=PolicyKind.relationship,
            content_sha256="4" * 64,
            effective_at=NOW - timedelta(days=1),
        )
        retained = relationship_module.RetainedAssertionReference(
            reference_id="retained:patent-applicant:robotics",
            assertion_id="assertion:patent-ada:applicants",
            source_record_ref="record:patent:applicant:robotics",
            artifact_refs=(),
        )
        binding = relationship_module.RetainedEvidenceBinding(
            evidence_kind="patent_applicant_assertion",
            assertion_refs=(retained.reference_id,),
            artifact_refs=(),
        )
        candidate_id = "candidate:patent-applicant:robotics"
        typed_assertion_id = "typed-assertion:patent-applicant:robotics"
        decision_input_id = "decision-input:patent-applicant:robotics"
        decision_id = "relationship-decision:patent-applicant:robotics"
        canonical_relationship_id = "relationship:patent-applicant:robotics"
        role_bindings = {"applicant": target_endpoint.stable_reference}
        candidates = (
            relationship_module.RelationshipProjectionCandidate(
                candidate_id=candidate_id,
                relationship_type_id="patent_has_applicant",
                relationship_type_version="canonical-v2-relationship-v1",
                source_endpoint=source_endpoint,
                target_endpoint=target_endpoint,
                role_bindings=role_bindings,
                evidence_metadata={"semantic_role": "applicant"},
                requested_paths=("company_to_patent", "patent_to_company"),
                catalog_scenario_id="catalog_scenario.patent_has_applicant",
                observed_at=NOW,
                evidence_bindings=(binding,),
                assertion_input_id=typed_assertion_id,
                assertion_input_kind="typed_relationship_assertion",
                decision_input_id=decision_input_id,
            ),
        )
        typed_assertions = (
            relationship_module.TypedRelationshipAssertionInput(
                assertion_id=typed_assertion_id,
                relationship_type_id="patent_has_applicant",
                relationship_type_version="canonical-v2-relationship-v1",
                source_record_ref="record:patent:applicant:robotics",
                source_endpoint=source_endpoint,
                target_endpoint=target_endpoint,
                attributes={
                    "candidate_id": candidate_id,
                    "evidence_metadata": {"semantic_role": "applicant"},
                    "role_bindings": role_bindings,
                },
                evidence_bindings=(binding,),
                observed_at=NOW,
                assertion_run_id="company-patent-relationship-assertion-run",
            ),
        )
        decisions = (
            relationship_module.RelationshipDecisionInput(
                decision_input_id=decision_input_id,
                decision_id=decision_id,
                canonical_relationship_id=canonical_relationship_id,
                state="accepted",
                candidate_assertion_ids=(typed_assertion_id,),
                selected_assertion_ids=(typed_assertion_id,),
                conflicting_assertion_ids=(),
                role_bindings=role_bindings,
                selected_evidence_refs=(retained.reference_id,),
                policy=policy,
                method=DecisionMethod.deterministic,
                method_version="company-patent-relationship-deterministic-v1",
                confidence=1.0,
                rationale="Exact retained Patent applicant evidence.",
            ),
        )
        relationship_request = relationship_module.RelationshipProjectionRequest(
            catalog=relationship_module.RelationshipCatalogIdentity(
                schema_version=CATALOG_SCHEMA_VERSION,
                catalog_version=CATALOG_VERSION,
                content_sha256=CATALOG_CONTENT_SHA256,
            ),
            release_id=release_id,
            projection_run_id=(
                "company-patent-relationship-zero-run"
                if authoritative_zero
                else "company-patent-relationship-publication-run"
            ),
            as_of=NOW,
            decision_policy=policy,
            relationship_registry_version=(
                relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_VERSION
            ),
            relationship_registry_content_sha256=(
                relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_CONTENT_SHA256
            ),
            domain_projections=domain_result.projections,
            internal_reference_projection_request=internal_request,
            internal_reference_projection_result=internal_result,
            candidates=() if authoritative_zero else candidates,
            relationship_assertions=(),
            typed_relationship_assertions=(
                () if authoritative_zero else typed_assertions
            ),
            source_canonical_assignments=(),
            decision_inputs=() if authoritative_zero else decisions,
            retained_assertions=() if authoritative_zero else (retained,),
            retained_artifacts=(),
        )
        relationship_result = (
            relationship_module.create_ephemeral_relationship_projection().project(
                relationship_request
            )
        )
        if not authoritative_zero:
            assert len(relationship_result.candidate_outcomes) == 1
            assert relationship_result.candidate_outcomes[0].admitted is True
            assert len(relationship_result.typed_relationship_decisions) == 1
            assert len(relationship_result.current_relationships) == 1
        return (
            candidate_request,
            candidate_result,
            relationship_request,
            relationship_result,
        )
    finally:
        RELEASE_ID = previous_release_id


def _professor_paper_relationship_authority(
    *,
    release_id: str,
    authoritative_zero: bool = False,
    decision_state: str = "accepted",
    multiple_retained_refs: bool = False,
) -> tuple[Any, Any, Any, Any]:
    global RELEASE_ID

    previous_release_id = RELEASE_ID
    RELEASE_ID = release_id
    try:
        internal_module = _technology_module()
        relationship_module = import_module(
            "src.data_agents.canonical_v2.relationship_projection"
        )
        (
            domain_request,
            domain_result,
            identity_request,
            identity_result,
            person_locators,
        ) = _resolved_person_graph(internal_module)
        internal_request = _request(
            internal_module,
            domain_request=domain_request,
            domain_result=domain_result,
            identity_request=identity_request,
            identity_result=identity_result,
            locators=person_locators,
        )
        internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
            internal_request
        )
        candidate_module = _candidate_projection_module()
        candidate_request = _candidate_projection_request(
            candidate_module,
            internal_request,
            internal_result,
        )
        candidate_result = candidate_module.compose_candidate_projections(
            candidate_request
        )

        professor_id = "professor-ada"
        paper_id = "paper-ada"
        professor_source_identity_id = f"source-domain:{professor_id}"
        paper_source_identity_id = f"source-domain:{paper_id}"
        source_record_id = "record:professor:paper-attribution"
        source_endpoint = relationship_module.RelationshipEndpointReference(
            reference_kind="canonical_identity",
            endpoint_type="professor",
            stable_reference=f"canonical:professor:{professor_id}",
            canonical_identity_id=professor_id,
        )
        target_endpoint = relationship_module.RelationshipEndpointReference(
            reference_kind="canonical_identity",
            endpoint_type="paper",
            stable_reference=f"canonical:paper:{paper_id}",
            canonical_identity_id=paper_id,
        )
        policy = PolicyReference(
            policy_id="professor-paper-attribution-policy",
            policy_version="professor-paper-attribution-policy-v1",
            policy_kind=PolicyKind.relationship,
            content_sha256="5" * 64,
            effective_at=NOW - timedelta(days=1),
        )
        retained = relationship_module.RetainedAssertionReference(
            reference_id="retained:professor-paper:ada",
            assertion_id="source-assertion:professor-paper:ada",
            source_record_ref=source_record_id,
            artifact_refs=(),
        )
        retained_extra = relationship_module.RetainedAssertionReference(
            reference_id="retained:professor-paper:ada:corroborating",
            assertion_id="source-assertion:professor-paper:ada:corroborating",
            source_record_ref="record:professor:paper-attribution:corroborating",
            artifact_refs=(),
        )
        retained_values = (
            (retained, retained_extra) if multiple_retained_refs else (retained,)
        )
        retained_reference_ids = tuple(item.reference_id for item in retained_values)
        binding = relationship_module.RetainedEvidenceBinding(
            evidence_kind="professor_page_or_identity_attribution_assertion",
            assertion_refs=retained_reference_ids,
            artifact_refs=(),
        )
        candidate_id = "candidate:professor-paper:ada"
        shared_assertion_id = "relationship-assertion:professor-paper:ada"
        decision_input_id = "decision-input:professor-paper:ada"
        decision_id = "relationship-decision:professor-paper:ada"
        canonical_relationship_id = "relationship:professor-paper:ada"
        evidence_metadata = {
            "attribution_basis": [
                "professor_page_declaration",
                "verified_author_attribution",
            ]
        }
        candidates = (
            relationship_module.RelationshipProjectionCandidate(
                candidate_id=candidate_id,
                relationship_type_id="professor_attributed_to_paper",
                relationship_type_version="canonical-v2-relationship-v1",
                source_endpoint=source_endpoint,
                target_endpoint=target_endpoint,
                role_bindings={},
                evidence_metadata=evidence_metadata,
                requested_paths=("professor_to_paper", "paper_to_professor"),
                catalog_scenario_id=("catalog_scenario.professor_attributed_to_paper"),
                observed_at=NOW,
                evidence_bindings=(binding,),
                assertion_input_id=shared_assertion_id,
                assertion_input_kind="shared_source_relationship_assertion",
                decision_input_id=decision_input_id,
            ),
        )
        shared_assertions = (
            relationship_module.RelationshipAssertion(
                assertion_id=shared_assertion_id,
                relationship_type_id="professor_attributed_to_paper",
                relationship_type_version="canonical-v2-relationship-v1",
                source_record_id=source_record_id,
                source_endpoint={
                    "identity_id": professor_source_identity_id,
                    "identity_space": "source",
                    "entity_type": "professor",
                },
                target_endpoint={
                    "identity_id": paper_source_identity_id,
                    "identity_space": "source",
                    "entity_type": "paper",
                },
                attributes={
                    "candidate_id": candidate_id,
                    "evidence_refs": list(retained_reference_ids),
                    "evidence_metadata": evidence_metadata,
                    "role_bindings": {},
                },
                observed_at=NOW,
                assertion_run_id="professor-paper-attribution-assertion-run",
            ),
        )
        assignments = (
            relationship_module.SourceCanonicalAssignment(
                assignment_id="relationship-assignment:professor:ada",
                source_identity_id=professor_source_identity_id,
                canonical_identity_id=professor_id,
                entity_type="professor",
                source_record_refs=(source_record_id,),
            ),
            relationship_module.SourceCanonicalAssignment(
                assignment_id="relationship-assignment:paper:ada",
                source_identity_id=paper_source_identity_id,
                canonical_identity_id=paper_id,
                entity_type="paper",
                source_record_refs=(source_record_id,),
            ),
        )
        accepted = decision_state == "accepted"
        decisions = (
            relationship_module.RelationshipDecisionInput(
                decision_input_id=decision_input_id,
                decision_id=decision_id,
                canonical_relationship_id=canonical_relationship_id,
                state=decision_state,
                candidate_assertion_ids=(shared_assertion_id,),
                selected_assertion_ids=(shared_assertion_id,) if accepted else (),
                conflicting_assertion_ids=(),
                role_bindings={},
                selected_evidence_refs=retained_reference_ids if accepted else (),
                policy=policy,
                method=DecisionMethod.deterministic,
                method_version="professor-paper-attribution-deterministic-v1",
                confidence=1.0,
                rationale="Exact retained Professor-to-Paper attribution evidence.",
            ),
        )
        relationship_request = relationship_module.RelationshipProjectionRequest(
            catalog=relationship_module.RelationshipCatalogIdentity(
                schema_version=CATALOG_SCHEMA_VERSION,
                catalog_version=CATALOG_VERSION,
                content_sha256=CATALOG_CONTENT_SHA256,
            ),
            release_id=release_id,
            projection_run_id=(
                "professor-paper-attribution-zero-run"
                if authoritative_zero
                else "professor-paper-attribution-publication-run"
            ),
            as_of=NOW,
            decision_policy=policy,
            relationship_registry_version=(
                relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_VERSION
            ),
            relationship_registry_content_sha256=(
                relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_CONTENT_SHA256
            ),
            domain_projections=domain_result.projections,
            internal_reference_projection_request=internal_request,
            internal_reference_projection_result=internal_result,
            candidates=() if authoritative_zero else candidates,
            relationship_assertions=(() if authoritative_zero else shared_assertions),
            typed_relationship_assertions=(),
            source_canonical_assignments=() if authoritative_zero else assignments,
            decision_inputs=() if authoritative_zero else decisions,
            retained_assertions=() if authoritative_zero else retained_values,
            retained_artifacts=(),
        )
        relationship_result = (
            relationship_module.create_ephemeral_relationship_projection().project(
                relationship_request
            )
        )
        if not authoritative_zero:
            assert len(relationship_result.candidate_outcomes) == 1
            assert relationship_result.candidate_outcomes[0].admitted is True
            assert len(relationship_result.relationship_decisions) == 1
            assert len(relationship_result.current_relationships) == int(accepted)
        return (
            candidate_request,
            candidate_result,
            relationship_request,
            relationship_result,
        )
    finally:
        RELEASE_ID = previous_release_id


def test_technology_relationships_preserve_three_evidence_states_without_capability() -> (
    None
):
    fixture = _technology_relationship_fixture_inputs()
    internal_module = fixture["internal_module"]
    relationship_module = fixture["relationship_module"]
    graph = fixture["graph"]
    internal_request = fixture["internal_request"]
    semantics = fixture["semantics"]
    candidates = fixture["candidates"]
    typed_assertions = fixture["typed_assertions"]
    decisions = fixture["decisions"]
    retained_assertions = fixture["retained_assertions"]

    discussion = candidates[0]
    discussion_with_extra_claimed_evidence = discussion.model_copy(
        update={
            "candidate_id": "candidate:technology:discussion-with-claimed-evidence",
            "evidence_bindings": (
                relationship_module.RetainedEvidenceBinding(
                    evidence_kind="technology_discussion_assertion",
                    assertion_refs=(
                        retained_assertions[0].reference_id,
                        retained_assertions[1].reference_id,
                    ),
                    artifact_refs=(),
                ),
            ),
            "assertion_input_id": None,
            "decision_input_id": None,
        }
    )
    duplicate_retained_alias = retained_assertions[0].model_copy(
        update={"reference_id": "retained:technology:discussion-or-mention:alias"}
    )
    duplicate_retained_alias_candidate = discussion.model_copy(
        update={
            "candidate_id": "candidate:technology:duplicate-retained-alias",
            "evidence_bindings": (
                relationship_module.RetainedEvidenceBinding(
                    evidence_kind="technology_discussion_assertion",
                    assertion_refs=(
                        retained_assertions[0].reference_id,
                        duplicate_retained_alias.reference_id,
                    ),
                    artifact_refs=(),
                ),
            ),
            "assertion_input_id": None,
            "decision_input_id": None,
        }
    )
    retained_assertions.append(duplicate_retained_alias)
    contradictory_semantic_state = discussion.model_copy(
        update={
            "candidate_id": "candidate:technology:contradictory-semantic-state",
            "evidence_metadata": {"semantic_state": "claimed_adoption"},
            "assertion_input_id": None,
            "decision_input_id": None,
        }
    )
    unrelated_artifact = relationship_module.RetainedArtifactReference(
        reference_id="artifact:technology:unrelated",
        artifact_id="artifact-technology-unrelated",
        content_sha256="a" * 64,
    )
    unrelated_artifact_candidate = discussion.model_copy(
        update={
            "candidate_id": "candidate:technology:unrelated-artifact",
            "evidence_bindings": (
                relationship_module.RetainedEvidenceBinding(
                    evidence_kind="technology_discussion_assertion",
                    assertion_refs=(retained_assertions[0].reference_id,),
                    artifact_refs=(unrelated_artifact.reference_id,),
                ),
            ),
            "assertion_input_id": None,
            "decision_input_id": None,
        }
    )
    forged_typed_assertion_id = "typed-assertion:technology:forged-source-record"
    forged_typed_candidate = discussion.model_copy(
        update={
            "candidate_id": "candidate:technology:forged-source-record",
            "assertion_input_id": forged_typed_assertion_id,
            "decision_input_id": None,
        }
    )
    forged_typed_assertion = typed_assertions[0].model_copy(
        update={
            "assertion_id": forged_typed_assertion_id,
            "source_record_ref": "record:forged-technology-source",
            "attributes": {
                **typed_assertions[0].attributes,
                "candidate_id": forged_typed_candidate.candidate_id,
            },
        }
    )
    claimed_type_with_discussion_evidence = discussion.model_copy(
        update={
            "candidate_id": "candidate:technology:relabel-discussion-as-claimed",
            "relationship_type_id": "entity_claims_adoption_of_technology",
            "assertion_input_id": None,
            "decision_input_id": None,
        }
    )
    fabricated_capability = discussion.model_copy(
        update={
            "candidate_id": "candidate:technology:product-capability",
            "relationship_type_id": "product_has_capability",
            "assertion_input_id": None,
            "decision_input_id": None,
        }
    )
    unresolved_target = relationship_module.RelationshipEndpointReference(
        reference_kind="registry_entity",
        endpoint_type="technology_route",
        stable_reference="unresolved-technology:visual-servoing",
    )
    unresolved_candidate = discussion.model_copy(
        update={
            "candidate_id": "candidate:technology:unresolved-target",
            "target_endpoint": unresolved_target,
            "role_bindings": {"technology": unresolved_target.stable_reference},
            "assertion_input_id": None,
            "decision_input_id": None,
        }
    )
    request = _technology_relationship_request(
        fixture,
        candidates=(
            *candidates,
            discussion_with_extra_claimed_evidence,
            duplicate_retained_alias_candidate,
            contradictory_semantic_state,
            unrelated_artifact_candidate,
            forged_typed_candidate,
            claimed_type_with_discussion_evidence,
            fabricated_capability,
            unresolved_candidate,
        ),
        typed_assertions=(*typed_assertions, forged_typed_assertion),
        decisions=decisions,
        retained_assertions=tuple(retained_assertions),
        retained_artifacts=(unrelated_artifact,),
    )
    result = relationship_module.create_ephemeral_relationship_projection().project(
        request
    )
    outcomes = {item.candidate_id: item for item in result.candidate_outcomes}

    assert all(outcomes[item.candidate_id].admitted for item in candidates)
    assert {item.relationship_type_id for item in result.current_relationships} == {
        item[0] for item in semantics.values()
    }
    assert (
        outcomes[claimed_type_with_discussion_evidence.candidate_id].admitted is False
    )
    assert (
        "technology_relationship_evidence_not_in_internal_graph"
        in outcomes[claimed_type_with_discussion_evidence.candidate_id].reason_codes
    )
    assert (
        outcomes[discussion_with_extra_claimed_evidence.candidate_id].admitted is False
    )
    assert "technology_relationship_evidence_not_in_internal_graph" in (
        outcomes[discussion_with_extra_claimed_evidence.candidate_id].reason_codes
    )
    assert outcomes[duplicate_retained_alias_candidate.candidate_id].admitted is False
    assert "technology_relationship_evidence_not_in_internal_graph" in (
        outcomes[duplicate_retained_alias_candidate.candidate_id].reason_codes
    )
    assert outcomes[contradictory_semantic_state.candidate_id].admitted is False
    assert "technology_relationship_semantic_state_mismatch" in (
        outcomes[contradictory_semantic_state.candidate_id].reason_codes
    )
    assert outcomes[unrelated_artifact_candidate.candidate_id].admitted is False
    assert "technology_relationship_evidence_not_in_internal_graph" in (
        outcomes[unrelated_artifact_candidate.candidate_id].reason_codes
    )
    assert outcomes[forged_typed_candidate.candidate_id].admitted is False
    assert "typed_relationship_assertion_continuity_mismatch" in (
        outcomes[forged_typed_candidate.candidate_id].reason_codes
    )
    assert outcomes[fabricated_capability.candidate_id].admitted is False
    assert (
        "relationship_type_not_registered"
        in outcomes[fabricated_capability.candidate_id].reason_codes
    )
    assert outcomes[unresolved_candidate.candidate_id].admitted is False
    assert (
        "unresolved_internal_reference_endpoint"
        in outcomes[unresolved_candidate.candidate_id].reason_codes
    )
    assert result.inferred_relationship_type_ids == ()
    assert all(
        "capability" not in item.relationship_type_id
        for item in result.current_relationships
    )

    discussion_source_assertion_id = graph["technology_relationship_assertion_ids"][
        "discussion_or_mention"
    ]

    def project_changed_discussion_assertion(
        *,
        suffix: str,
        assertion_update: dict[str, Any],
    ) -> Any:
        original_source_assertion = next(
            item
            for item in graph["domain_request"].source_assertions
            if item.assertion_id == discussion_source_assertion_id
        )
        changed_source_assertion = original_source_assertion.model_copy(
            update=assertion_update
        )
        changed_domain_request = graph["domain_request"].model_copy(
            update={
                "source_assertions": tuple(
                    changed_source_assertion
                    if item.assertion_id == discussion_source_assertion_id
                    else item
                    for item in graph["domain_request"].source_assertions
                )
            }
        )
        changed_domain_result = (
            projection_models.create_ephemeral_domain_projection_builder().project(
                changed_domain_request
            )
        )
        changed_internal_request = internal_request.model_copy(
            update={
                "public_domain_projection_request": changed_domain_request,
                "public_domain_projection_result": changed_domain_result,
            }
        )
        changed_internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
            changed_internal_request
        )
        changed_candidate = discussion.model_copy(
            update={
                "candidate_id": f"candidate:technology:{suffix}",
                "assertion_input_id": None,
                "decision_input_id": None,
            }
        )
        changed_request = request.model_copy(
            update={
                "domain_projections": changed_domain_result.projections,
                "internal_reference_projection_request": changed_internal_request,
                "internal_reference_projection_result": changed_internal_result,
                "candidates": (changed_candidate,),
                "typed_relationship_assertions": (),
                "decision_inputs": (),
            }
        )
        changed_result = (
            relationship_module.create_ephemeral_relationship_projection().project(
                changed_request
            )
        )
        return changed_result.candidate_outcomes[0]

    original_discussion_assertion = next(
        item
        for item in graph["domain_request"].source_assertions
        if item.assertion_id == discussion_source_assertion_id
    )
    assert isinstance(original_discussion_assertion.value, dict)
    fabricated_term = project_changed_discussion_assertion(
        suffix="fabricated-term",
        assertion_update={
            "value": {
                **original_discussion_assertion.value,
                "term": "unrelated technology",
            }
        },
    )
    dropped_source_event_time = project_changed_discussion_assertion(
        suffix="dropped-source-event-time",
        assertion_update={"source_event_time": NOW - timedelta(hours=1)},
    )
    assert fabricated_term.admitted is False
    assert "technology_relationship_evidence_not_in_internal_graph" in (
        fabricated_term.reason_codes
    )
    assert dropped_source_event_time.admitted is False
    assert "technology_relationship_evidence_not_in_internal_graph" in (
        dropped_source_event_time.reason_codes
    )


def test_technology_relationship_accepts_declared_canonical_root_sources() -> None:
    internal_module = _technology_module()
    relationship_module: Any = import_module(
        "src.data_agents.canonical_v2.relationship_projection"
    )
    graph = _technology_graph(internal_module)
    paper_id = "paper-technology-root"
    paper_inputs = _domain_inputs(
        domain="paper",
        identity_id=paper_id,
        display_name="Visual servo evidence",
        selected_values={
            "authors": [],
            "title": "Visual servo evidence",
            "venue": {
                "reference_id": "venue:robotics",
                "name": "Robotics Journal",
            },
            "year": 2026,
        },
        source_record_ids={},
    )
    patent_id = "patent-technology-root"
    patent_inputs = _domain_inputs(
        domain="patent",
        identity_id=patent_id,
        display_name="Visual servo patent",
        selected_values={
            "applicants": [],
            "inventors": [],
            "summary_text": "Visual servo patent evidence.",
            "title": "Visual servo patent",
        },
        source_record_ids={},
    )
    professor_id = "professor-technology-root"
    professor_inputs = _domain_inputs(
        domain="professor",
        identity_id=professor_id,
        display_name="Professor Technology Root",
        selected_values={
            "canonical_name_zh": "技术根教授",
            "company_roles": [],
            "department": {
                "reference_id": "department:robotics",
                "name": "Robotics",
            },
            "email": "technology-root@example.edu",
            "homepage": "https://example.edu/technology-root",
            "institution": "SUSTech",
            "name": "Professor Technology Root",
            "paper_summary": "Robotics papers.",
            "patent_ids": [],
            "patent_summary": "Robotics patents.",
            "profile_summary": "Robotics professor.",
            "research_directions": [],
            "title": "Professor",
        },
        source_record_ids={},
    )
    relationship_assertion = SourceAssertion(
        assertion_id="assertion:paper:technology:discussion",
        source_record_id=f"record:domain:{paper_id}",
        source_identity_id=f"source-domain:{paper_id}",
        subject_entity_type="paper",
        field_path="internal_reference.technology_discussion_or_mention",
        value={
            "technology_source_identity_id": "source-tech-route-visual-servo",
            "root_canonical_identity_id": paper_id,
            "source_subobject_type": None,
            "source_subobject_id": None,
            "term": "visual servoing",
        },
        observed_at=NOW,
        assertion_run_id="s6r-technology-root-relationship-assertions",
    )
    relationship_value = relationship_assertion.value
    assert isinstance(relationship_value, dict)

    def root_relationship_assertion(domain: str, identity_id: str) -> SourceAssertion:
        return relationship_assertion.model_copy(
            update={
                "assertion_id": f"assertion:{domain}:technology:discussion",
                "source_record_id": f"record:domain:{identity_id}",
                "source_identity_id": f"source-domain:{identity_id}",
                "subject_entity_type": domain,
                "value": {
                    **relationship_value,
                    "root_canonical_identity_id": identity_id,
                },
            }
        )

    company_relationship_assertion = root_relationship_assertion(
        "company", graph["company_id"]
    )
    patent_relationship_assertion = root_relationship_assertion("patent", patent_id)
    professor_relationship_assertion = root_relationship_assertion(
        "professor", professor_id
    )
    paper_inputs = {
        **paper_inputs,
        "source_assertions": (
            *paper_inputs["source_assertions"],
            relationship_assertion,
        ),
    }
    patent_inputs = {
        **patent_inputs,
        "source_assertions": (
            *patent_inputs["source_assertions"],
            patent_relationship_assertion,
        ),
    }
    professor_inputs = {
        **professor_inputs,
        "source_assertions": (
            *professor_inputs["source_assertions"],
            professor_relationship_assertion,
        ),
    }
    base_domain_request = graph["domain_request"]
    base_inputs = {
        "canonical_identities": base_domain_request.canonical_identities,
        "source_identity_assignments": (
            base_domain_request.source_identity_assignments
        ),
        "source_assertions": (
            *base_domain_request.source_assertions,
            company_relationship_assertion,
        ),
        "canonical_decisions": base_domain_request.canonical_decisions,
        "current_fields": base_domain_request.current_fields,
        "inclusion_decisions": (base_domain_request.inclusion_result.policy_decisions),
    }
    domain_request, domain_result = _domain_projection_pair(
        _combine_domain_inputs(
            base_inputs,
            paper_inputs,
            patent_inputs,
            professor_inputs,
        )
    )
    internal_request = _request(
        internal_module,
        domain_request=domain_request,
        domain_result=domain_result,
        identity_request=graph["person_request"],
        identity_result=graph["person_result"],
        locators=graph["person_locators"],
        technology_identity_resolution_request=graph["technology_request"],
        technology_identity_resolution_result=graph["technology_result"],
        technology_evidence_locators=graph["technology_locators"],
    )
    internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
        internal_request
    )
    route = internal_result.technology_route_projections[0]
    source_endpoint = relationship_module.RelationshipEndpointReference(
        reference_kind="canonical_identity",
        endpoint_type="paper",
        stable_reference=f"canonical:paper:{paper_id}",
        canonical_identity_id=paper_id,
    )
    target_endpoint = relationship_module.RelationshipEndpointReference(
        reference_kind="canonical_identity",
        endpoint_type="technology_route",
        stable_reference=(
            f"canonical:technology_route:{route.canonical_technology_identity_id}"
        ),
        canonical_identity_id=route.canonical_technology_identity_id,
    )
    registry = relationship_module.create_installed_relationship_type_registry()
    relationship_type = registry.resolve(
        "entity_discusses_or_mentions_technology",
        "canonical-v2-relationship-v1",
    )
    assert set(relationship_type.source_entity_types) == {
        "company",
        "paper",
        "patent",
        "product",
    }
    retained = relationship_module.RetainedAssertionReference(
        reference_id="retained:paper:technology:discussion",
        assertion_id=relationship_assertion.assertion_id,
        source_record_ref=relationship_assertion.source_record_id,
        artifact_refs=(),
    )
    binding = relationship_module.RetainedEvidenceBinding(
        evidence_kind="technology_discussion_assertion",
        assertion_refs=(retained.reference_id,),
        artifact_refs=(),
    )
    candidate_id = "candidate:paper:technology:discussion"
    assertion_id = "typed-assertion:paper:technology:discussion"
    decision_input_id = "decision-input:paper:technology:discussion"
    role_bindings = {"technology": target_endpoint.stable_reference}
    candidate = relationship_module.RelationshipProjectionCandidate(
        candidate_id=candidate_id,
        relationship_type_id=relationship_type.relationship_type_id,
        relationship_type_version=relationship_type.version,
        source_endpoint=source_endpoint,
        target_endpoint=target_endpoint,
        role_bindings=role_bindings,
        evidence_metadata={"semantic_state": "discussion_or_mention"},
        requested_paths=("relationship_traversal",),
        observed_at=NOW,
        evidence_bindings=(binding,),
        assertion_input_id=assertion_id,
        assertion_input_kind="typed_relationship_assertion",
        decision_input_id=decision_input_id,
    )
    typed_assertion = relationship_module.TypedRelationshipAssertionInput(
        assertion_id=assertion_id,
        relationship_type_id=relationship_type.relationship_type_id,
        relationship_type_version=relationship_type.version,
        source_record_ref=relationship_assertion.source_record_id,
        source_endpoint=source_endpoint,
        target_endpoint=target_endpoint,
        attributes={
            "candidate_id": candidate_id,
            "evidence_metadata": {"semantic_state": "discussion_or_mention"},
            "role_bindings": role_bindings,
        },
        evidence_bindings=(binding,),
        observed_at=NOW,
        assertion_run_id="s6r-technology-root-typed-assertions",
    )
    policy = PolicyReference(
        policy_id="technology-root-relationship-policy",
        policy_version="technology-root-relationship-policy-v1",
        policy_kind=PolicyKind.relationship,
        content_sha256="3" * 64,
        effective_at=NOW - timedelta(days=1),
    )
    decision = relationship_module.RelationshipDecisionInput(
        decision_input_id=decision_input_id,
        decision_id="relationship-decision:paper:technology:discussion",
        canonical_relationship_id="relationship:paper:technology:discussion",
        state="accepted",
        candidate_assertion_ids=(assertion_id,),
        selected_assertion_ids=(assertion_id,),
        conflicting_assertion_ids=(),
        role_bindings=role_bindings,
        selected_evidence_refs=(retained.reference_id,),
        policy=policy,
        method=DecisionMethod.deterministic,
        method_version="technology-relationship-deterministic-v1",
        confidence=1.0,
        rationale="Exact retained root Technology evidence.",
    )

    def root_bundle(
        domain: str,
        identity_id: str,
        source_assertion: SourceAssertion,
    ) -> tuple[Any, Any, Any, Any]:
        root_endpoint = relationship_module.RelationshipEndpointReference(
            reference_kind="canonical_identity",
            endpoint_type=domain,
            stable_reference=f"canonical:{domain}:{identity_id}",
            canonical_identity_id=identity_id,
        )
        root_retained = retained.model_copy(
            update={
                "reference_id": f"retained:{domain}:technology:discussion",
                "assertion_id": source_assertion.assertion_id,
                "source_record_ref": source_assertion.source_record_id,
            }
        )
        root_binding = binding.model_copy(
            update={"assertion_refs": (root_retained.reference_id,)}
        )
        root_candidate_id = f"candidate:{domain}:technology:discussion"
        root_assertion_id = f"typed-assertion:{domain}:technology:discussion"
        root_decision_input_id = f"decision-input:{domain}:technology:discussion"
        root_candidate = candidate.model_copy(
            update={
                "candidate_id": root_candidate_id,
                "source_endpoint": root_endpoint,
                "evidence_bindings": (root_binding,),
                "assertion_input_id": root_assertion_id,
                "decision_input_id": root_decision_input_id,
            }
        )
        root_typed_assertion = typed_assertion.model_copy(
            update={
                "assertion_id": root_assertion_id,
                "source_record_ref": source_assertion.source_record_id,
                "source_endpoint": root_endpoint,
                "attributes": {
                    **typed_assertion.attributes,
                    "candidate_id": root_candidate_id,
                },
                "evidence_bindings": (root_binding,),
            }
        )
        root_decision = decision.model_copy(
            update={
                "decision_input_id": root_decision_input_id,
                "decision_id": f"relationship-decision:{domain}:technology:discussion",
                "canonical_relationship_id": (
                    f"relationship:{domain}:technology:discussion"
                ),
                "candidate_assertion_ids": (root_assertion_id,),
                "selected_assertion_ids": (root_assertion_id,),
                "selected_evidence_refs": (root_retained.reference_id,),
            }
        )
        return (
            root_candidate,
            root_typed_assertion,
            root_decision,
            root_retained,
        )

    company_bundle = root_bundle(
        "company",
        graph["company_id"],
        company_relationship_assertion,
    )
    patent_bundle = root_bundle(
        "patent",
        patent_id,
        patent_relationship_assertion,
    )
    professor_bundle = root_bundle(
        "professor",
        professor_id,
        professor_relationship_assertion,
    )
    request = relationship_module.RelationshipProjectionRequest(
        catalog=relationship_module.RelationshipCatalogIdentity(
            schema_version=CATALOG_SCHEMA_VERSION,
            catalog_version=CATALOG_VERSION,
            content_sha256=CATALOG_CONTENT_SHA256,
        ),
        relationship_registry_version=(
            relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_VERSION
        ),
        relationship_registry_content_sha256=(
            relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_CONTENT_SHA256
        ),
        release_id=RELEASE_ID,
        projection_run_id="technology-root-relationship-projection-run",
        as_of=NOW,
        decision_policy=policy,
        domain_projections=domain_result.projections,
        internal_reference_projection_request=internal_request,
        internal_reference_projection_result=internal_result,
        candidates=(
            candidate,
            company_bundle[0],
            patent_bundle[0],
            professor_bundle[0],
        ),
        relationship_assertions=(),
        typed_relationship_assertions=(
            typed_assertion,
            company_bundle[1],
            patent_bundle[1],
            professor_bundle[1],
        ),
        source_canonical_assignments=(),
        decision_inputs=(
            decision,
            company_bundle[2],
            patent_bundle[2],
            professor_bundle[2],
        ),
        retained_assertions=(
            retained,
            company_bundle[3],
            patent_bundle[3],
            professor_bundle[3],
        ),
        retained_artifacts=(),
    )

    result = relationship_module.create_ephemeral_relationship_projection().project(
        request
    )

    outcomes = {item.candidate_id: item for item in result.candidate_outcomes}
    assert all(
        outcomes[f"candidate:{domain}:technology:discussion"].admitted is True
        for domain in ("company", "paper", "patent")
    )
    professor_outcome = outcomes["candidate:professor:technology:discussion"]
    assert professor_outcome.admitted is False
    assert "endpoint_type_not_allowed" in professor_outcome.reason_codes
    assert {
        item.source_endpoint.endpoint_type for item in result.current_relationships
    } == {
        "company",
        "paper",
        "patent",
    }


def test_relationship_projection_requires_explicit_internal_reference_registry() -> (
    None
):
    fields = RelationshipProjectionRequest.model_fields
    relationship_module: Any = import_module(
        "src.data_agents.canonical_v2.relationship_projection"
    )
    internal_module: Any | None = None

    missing = []
    try:
        internal_module = import_module(TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != TARGET_MODULE:
            raise AssertionError(
                f"{TARGET_MODULE} has an unexpected missing dependency: {exc.name}"
            ) from exc
        missing.append("internal reference projection interface")
    if "internal_reference_projection_request" not in fields:
        missing.append("closed internal-reference request input")
    if "internal_reference_projection_result" not in fields:
        missing.append("closed internal-reference result input")
    if not hasattr(relationship_module, "RelationshipTypeRegistry"):
        missing.append("exact-version RelationshipTypeRegistry")
    if not hasattr(relationship_module, "create_installed_relationship_type_registry"):
        missing.append("installed exact-version registry factory")
    if missing:
        raise _MissingRelationshipContract(
            "relationship contract is missing: " + ", ".join(missing)
        )
    assert internal_module is not None
    assert "domain_projections" in fields
    registry = relationship_module.create_installed_relationship_type_registry()
    assert registry.registry_version == (
        relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_VERSION
    )
    assert registry.content_sha256 == (
        relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_CONTENT_SHA256
    )
    assert len(registry.relationship_types) == 40
    v1_type = registry.resolve("paper_has_author", "canonical-v2-relationship-v1")
    v2_type = registry.resolve("paper_has_author", "canonical-v2-relationship-v2")
    assert v1_type.version == "canonical-v2-relationship-v1"
    assert v2_type.version == "canonical-v2-relationship-v2"
    assert v1_type.target_entity_types == ("person", "professor")
    assert v2_type.target_entity_types == ("person",)
    with pytest.raises(KeyError, match="canonical-v2-relationship-v3"):
        registry.resolve("paper_has_author", "canonical-v2-relationship-v3")

    (
        domain_request,
        domain_result,
        identity_request,
        identity_result,
        locators,
    ) = _resolved_person_graph(internal_module)
    internal_request = _request(
        internal_module,
        domain_request=domain_request,
        domain_result=domain_result,
        identity_request=identity_request,
        identity_result=identity_result,
        locators=locators,
    )
    internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
        internal_request
    )
    person_projection = internal_result.person_projections[0]
    paper_reference = next(
        item
        for item in person_projection.references
        if item.source_kind == "paper_author"
    )
    paper_anchor = next(
        item
        for item in internal_result.public_evidence_anchors
        if item.anchor_id == paper_reference.source_anchor_id
    )
    patent_reference = next(
        item
        for item in person_projection.references
        if item.source_kind == "patent_inventor"
    )
    patent_anchor = next(
        item
        for item in internal_result.public_evidence_anchors
        if item.anchor_id == patent_reference.source_anchor_id
    )
    paper_projection = next(
        item for item in domain_result.projections if item.entity_type == "paper"
    )
    patent_projection = next(
        item for item in domain_result.projections if item.entity_type == "patent"
    )
    source_endpoint = relationship_module.RelationshipEndpointReference(
        reference_kind="canonical_identity",
        endpoint_type="paper",
        stable_reference=(f"canonical:paper:{paper_projection.canonical_identity_id}"),
        canonical_identity_id=paper_projection.canonical_identity_id,
    )
    target_endpoint = relationship_module.RelationshipEndpointReference(
        reference_kind="canonical_identity",
        endpoint_type="person",
        stable_reference=(
            f"canonical:person:{person_projection.canonical_person_identity_id}"
        ),
        canonical_identity_id=person_projection.canonical_person_identity_id,
    )
    policy = PolicyReference(
        policy_id="relationship-policy",
        policy_version="relationship-policy-v1",
        policy_kind=PolicyKind.relationship,
        content_sha256="7" * 64,
        effective_at=NOW,
    )

    def relationship_bundle(version: str) -> tuple[Any, Any, Any, Any]:
        suffix = version.rsplit("-", maxsplit=1)[-1]
        retained_reference = relationship_module.RetainedAssertionReference(
            reference_id=f"retained:paper-author:{suffix}",
            assertion_id=paper_anchor.supporting_assertion_ids[0],
            source_record_ref=paper_anchor.source_record_ids[0],
            artifact_refs=(),
        )
        binding = relationship_module.RetainedEvidenceBinding(
            evidence_kind="paper_author_assertion",
            assertion_refs=(retained_reference.reference_id,),
            artifact_refs=(),
        )
        role_bindings = {"author": target_endpoint.stable_reference}
        candidate_id = f"candidate:paper-author:{suffix}"
        assertion_id = f"typed-assertion:paper-author:{suffix}"
        decision_input_id = f"decision-input:paper-author:{suffix}"
        candidate = relationship_module.RelationshipProjectionCandidate(
            candidate_id=candidate_id,
            relationship_type_id="paper_has_author",
            relationship_type_version=version,
            source_endpoint=source_endpoint,
            target_endpoint=target_endpoint,
            role_bindings=role_bindings,
            evidence_metadata={},
            requested_paths=("verified_relationship_traversal",),
            observed_at=NOW,
            evidence_bindings=(binding,),
            assertion_input_id=assertion_id,
            assertion_input_kind="typed_relationship_assertion",
            decision_input_id=decision_input_id,
        )
        typed_assertion = relationship_module.TypedRelationshipAssertionInput(
            assertion_id=assertion_id,
            relationship_type_id="paper_has_author",
            relationship_type_version=version,
            source_record_ref=paper_anchor.source_record_ids[0],
            source_endpoint=source_endpoint,
            target_endpoint=target_endpoint,
            attributes={
                "candidate_id": candidate_id,
                "evidence_metadata": {},
                "role_bindings": role_bindings,
            },
            evidence_bindings=(binding,),
            observed_at=NOW,
            assertion_run_id="relationship-assertion-run",
        )
        decision_input = relationship_module.RelationshipDecisionInput(
            decision_input_id=decision_input_id,
            decision_id=f"relationship-decision:paper-author:{suffix}",
            canonical_relationship_id=f"relationship:paper-author:{suffix}",
            state="accepted",
            candidate_assertion_ids=(assertion_id,),
            selected_assertion_ids=(assertion_id,),
            conflicting_assertion_ids=(),
            role_bindings=role_bindings,
            selected_evidence_refs=(retained_reference.reference_id,),
            policy=policy,
            method=DecisionMethod.deterministic,
            method_version="relationship-deterministic-v1",
            confidence=1.0,
            rationale="Exact version coexistence fixture",
        )
        return candidate, typed_assertion, decision_input, retained_reference

    v1 = relationship_bundle("canonical-v2-relationship-v1")
    v2 = relationship_bundle("canonical-v2-relationship-v2")
    patent_source_endpoint = relationship_module.RelationshipEndpointReference(
        reference_kind="canonical_identity",
        endpoint_type="patent",
        stable_reference=(
            f"canonical:patent:{patent_projection.canonical_identity_id}"
        ),
        canonical_identity_id=patent_projection.canonical_identity_id,
    )
    patent_retained = relationship_module.RetainedAssertionReference(
        reference_id="retained:patent-inventor:v2",
        assertion_id=patent_anchor.supporting_assertion_ids[0],
        source_record_ref=patent_anchor.source_record_ids[0],
        artifact_refs=(),
    )
    patent_binding = relationship_module.RetainedEvidenceBinding(
        evidence_kind="patent_inventor_assertion",
        assertion_refs=(patent_retained.reference_id,),
        artifact_refs=(),
    )
    patent_role_bindings = {"inventor": target_endpoint.stable_reference}
    patent_candidate = relationship_module.RelationshipProjectionCandidate(
        candidate_id="candidate:patent-inventor:v2-professor-path",
        relationship_type_id="patent_has_inventor",
        relationship_type_version="canonical-v2-relationship-v2",
        source_endpoint=patent_source_endpoint,
        target_endpoint=target_endpoint,
        role_bindings=patent_role_bindings,
        evidence_metadata={},
        requested_paths=(
            "patent_to_professor",
            "professor_to_patent",
            "relationship_traversal",
        ),
        observed_at=NOW,
        evidence_bindings=(patent_binding,),
        assertion_input_id="typed-assertion:patent-inventor:v2",
        assertion_input_kind="typed_relationship_assertion",
        decision_input_id="decision-input:patent-inventor:v2",
    )
    patent_typed_assertion = relationship_module.TypedRelationshipAssertionInput(
        assertion_id="typed-assertion:patent-inventor:v2",
        relationship_type_id="patent_has_inventor",
        relationship_type_version="canonical-v2-relationship-v2",
        source_record_ref=patent_anchor.source_record_ids[0],
        source_endpoint=patent_source_endpoint,
        target_endpoint=target_endpoint,
        attributes={
            "candidate_id": patent_candidate.candidate_id,
            "evidence_metadata": {},
            "role_bindings": patent_role_bindings,
        },
        evidence_bindings=(patent_binding,),
        observed_at=NOW,
        assertion_run_id="relationship-assertion-run",
    )
    patent_decision = relationship_module.RelationshipDecisionInput(
        decision_input_id="decision-input:patent-inventor:v2",
        decision_id="relationship-decision:patent-inventor:v2",
        canonical_relationship_id="relationship:patent-inventor:v2",
        state="accepted",
        candidate_assertion_ids=(patent_typed_assertion.assertion_id,),
        selected_assertion_ids=(patent_typed_assertion.assertion_id,),
        conflicting_assertion_ids=(),
        role_bindings=patent_role_bindings,
        selected_evidence_refs=(patent_retained.reference_id,),
        policy=policy,
        method=DecisionMethod.deterministic,
        method_version="relationship-deterministic-v1",
        confidence=1.0,
        rationale="Resolved Person includes an exact Professor reference.",
    )
    unknown = relationship_module.RelationshipProjectionCandidate(
        **{
            **v2[0].model_dump(),
            "candidate_id": "candidate:paper-author:v3",
            "relationship_type_version": "canonical-v2-relationship-v3",
            "assertion_input_id": None,
            "decision_input_id": None,
        }
    )
    unchecked_registry_target = relationship_module.RelationshipEndpointReference(
        reference_kind="registry_entity",
        endpoint_type="person",
        stable_reference="unresolved-person-ref:unchecked",
    )
    unchecked_registry_candidate = relationship_module.RelationshipProjectionCandidate(
        **{
            **v2[0].model_dump(),
            "candidate_id": "candidate:paper-author:unchecked-registry-person",
            "target_endpoint": unchecked_registry_target,
            "role_bindings": {
                "author": unchecked_registry_target.stable_reference,
            },
            "assertion_input_id": None,
            "decision_input_id": None,
        }
    )
    lineage_person_target = relationship_module.RelationshipEndpointReference(
        reference_kind="lineage_record",
        endpoint_type="person",
        stable_reference="lineage:person:unchecked",
        lineage_family="person-source-observation",
        subject_reference="source-person:unchecked",
        subject_entity_type="person",
    )
    lineage_person_candidate = relationship_module.RelationshipProjectionCandidate(
        **{
            **v2[0].model_dump(),
            "candidate_id": "candidate:paper-author:lineage-person",
            "target_endpoint": lineage_person_target,
            "role_bindings": {"author": lineage_person_target.stable_reference},
            "assertion_input_id": None,
            "decision_input_id": None,
        }
    )
    wrong_person_anchor = next(
        item
        for item in internal_result.public_evidence_anchors
        if item.source_kind == "professor"
    )
    wrong_person_retained = relationship_module.RetainedAssertionReference(
        reference_id="retained:paper-author:wrong-person-anchor",
        assertion_id=wrong_person_anchor.supporting_assertion_ids[0],
        source_record_ref=wrong_person_anchor.source_record_ids[0],
        artifact_refs=(),
    )
    wrong_person_evidence_candidate = v2[0].model_copy(
        update={
            "candidate_id": "candidate:paper-author:wrong-person-anchor",
            "evidence_bindings": (
                relationship_module.RetainedEvidenceBinding(
                    evidence_kind="paper_author_assertion",
                    assertion_refs=(wrong_person_retained.reference_id,),
                    artifact_refs=(),
                ),
            ),
            "assertion_input_id": None,
            "decision_input_id": None,
        }
    )
    unrelated_person_artifact = relationship_module.RetainedArtifactReference(
        reference_id="artifact:paper-author:unrelated",
        artifact_id="artifact-paper-author-unrelated",
        content_sha256="b" * 64,
    )
    unrelated_person_artifact_candidate = v2[0].model_copy(
        update={
            "candidate_id": "candidate:paper-author:unrelated-artifact",
            "evidence_bindings": (
                relationship_module.RetainedEvidenceBinding(
                    evidence_kind="paper_author_assertion",
                    assertion_refs=(v2[3].reference_id,),
                    artifact_refs=(unrelated_person_artifact.reference_id,),
                ),
            ),
            "assertion_input_id": None,
            "decision_input_id": None,
        }
    )
    absent_internal_target = relationship_module.RelationshipEndpointReference(
        reference_kind="canonical_identity",
        endpoint_type="person",
        stable_reference="canonical:person:person-missing",
        canonical_identity_id="person-missing",
    )
    absent_internal_candidate = relationship_module.RelationshipProjectionCandidate(
        **{
            **v2[0].model_dump(),
            "candidate_id": "candidate:paper-author:absent-internal-person",
            "target_endpoint": absent_internal_target,
            "role_bindings": {
                "author": absent_internal_target.stable_reference,
            },
            "assertion_input_id": None,
            "decision_input_id": None,
        }
    )
    request = relationship_module.RelationshipProjectionRequest(
        catalog=relationship_module.RelationshipCatalogIdentity(
            schema_version=CATALOG_SCHEMA_VERSION,
            catalog_version=CATALOG_VERSION,
            content_sha256=CATALOG_CONTENT_SHA256,
        ),
        release_id=RELEASE_ID,
        projection_run_id="relationship-version-run",
        as_of=NOW,
        decision_policy=policy,
        relationship_registry_version=(
            relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_VERSION
        ),
        relationship_registry_content_sha256=(
            relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_CONTENT_SHA256
        ),
        domain_projections=domain_result.projections,
        internal_reference_projection_request=internal_request.model_dump(
            mode="python"
        ),
        internal_reference_projection_result=internal_result.model_dump(mode="python"),
        candidates=(
            v1[0],
            v2[0],
            patent_candidate,
            unknown,
            unchecked_registry_candidate,
            lineage_person_candidate,
            wrong_person_evidence_candidate,
            unrelated_person_artifact_candidate,
            absent_internal_candidate,
        ),
        relationship_assertions=(),
        typed_relationship_assertions=(
            v1[1],
            v2[1],
            patent_typed_assertion,
        ),
        source_canonical_assignments=(),
        decision_inputs=(v1[2], v2[2], patent_decision),
        retained_assertions=(
            v1[3],
            v2[3],
            patent_retained,
            wrong_person_retained,
        ),
        retained_artifacts=(unrelated_person_artifact,),
    )
    projector = relationship_module.create_ephemeral_relationship_projection(
        relationship_type_registry=registry
    )
    result = projector.project(request)
    outcomes = {item.candidate_id: item for item in result.candidate_outcomes}

    missing_version_payload = result.model_dump(mode="python")
    first_outcome = dict(missing_version_payload["candidate_outcomes"][0])
    first_outcome.pop("relationship_type_version")
    missing_version_payload["candidate_outcomes"] = (
        first_outcome,
        *missing_version_payload["candidate_outcomes"][1:],
    )
    with pytest.raises(ValidationError, match="exact type version"):
        relationship_module.RelationshipProjectionResult.model_validate(
            missing_version_payload
        )

    assert outcomes[v1[0].candidate_id].admitted is True
    assert outcomes[v2[0].candidate_id].admitted is True
    assert outcomes[patent_candidate.candidate_id].admitted is True
    assert outcomes[unknown.candidate_id].admitted is False
    assert outcomes[v1[0].candidate_id].relationship_type_version == (
        "canonical-v2-relationship-v1"
    )
    assert outcomes[v2[0].candidate_id].relationship_type_version == (
        "canonical-v2-relationship-v2"
    )
    assert outcomes[unknown.candidate_id].relationship_type_version == (
        "canonical-v2-relationship-v3"
    )
    assert (
        "relationship_type_version_not_registered"
        in outcomes[unknown.candidate_id].reason_codes
    )
    assert outcomes[unchecked_registry_candidate.candidate_id].admitted is False
    assert (
        "unresolved_internal_reference_endpoint"
        in outcomes[unchecked_registry_candidate.candidate_id].reason_codes
    )
    assert outcomes[lineage_person_candidate.candidate_id].admitted is False
    assert "unresolved_internal_reference_endpoint" in (
        outcomes[lineage_person_candidate.candidate_id].reason_codes
    )
    assert outcomes[wrong_person_evidence_candidate.candidate_id].admitted is False
    assert "person_relationship_evidence_not_in_internal_graph" in (
        outcomes[wrong_person_evidence_candidate.candidate_id].reason_codes
    )
    assert outcomes[unrelated_person_artifact_candidate.candidate_id].admitted is False
    assert "person_relationship_evidence_not_in_internal_graph" in (
        outcomes[unrelated_person_artifact_candidate.candidate_id].reason_codes
    )
    assert outcomes[absent_internal_candidate.candidate_id].admitted is False
    assert (
        "canonical_endpoint_not_in_internal_reference_projection"
        in outcomes[absent_internal_candidate.candidate_id].reason_codes
    )
    assert {
        item.relationship_type_version for item in result.current_relationships
    } == {
        "canonical-v2-relationship-v1",
        "canonical-v2-relationship-v2",
    }

    patent_locator = next(
        item for item in locators if item.source_kind == "patent_inventor"
    )
    patent_person_source = next(
        item
        for item in identity_request.source_identities
        if item.source_identity_id == patent_locator.source_identity_id
    )
    patent_person_assertions = tuple(
        item
        for item in identity_request.identity_assertions
        if item.source_identity_id == patent_person_source.source_identity_id
    )
    restricted_identity_request, restricted_identity_result = _identity_resolution(
        (patent_person_source,),
        patent_person_assertions,
    )
    restricted_internal_request = _request(
        internal_module,
        domain_request=domain_request,
        domain_result=domain_result,
        identity_request=restricted_identity_request,
        identity_result=restricted_identity_result,
        locators=(patent_locator,),
    )
    restricted_internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
        restricted_internal_request
    )
    restricted_person = restricted_internal_result.person_projections[0]
    assert {item.source_kind for item in restricted_person.references} == {
        "patent_inventor"
    }
    restricted_target = target_endpoint.model_copy(
        update={
            "stable_reference": (
                f"canonical:person:{restricted_person.canonical_person_identity_id}"
            ),
            "canonical_identity_id": restricted_person.canonical_person_identity_id,
        }
    )
    restricted_roles = {"inventor": restricted_target.stable_reference}
    restricted_candidate = patent_candidate.model_copy(
        update={
            "candidate_id": "candidate:patent-inventor:v2-missing-professor",
            "target_endpoint": restricted_target,
            "role_bindings": restricted_roles,
            "assertion_input_id": "typed-assertion:patent-inventor:v2-restricted",
            "decision_input_id": "decision-input:patent-inventor:v2-restricted",
        }
    )
    restricted_typed_assertion = patent_typed_assertion.model_copy(
        update={
            "assertion_id": "typed-assertion:patent-inventor:v2-restricted",
            "target_endpoint": restricted_target,
            "attributes": {
                **patent_typed_assertion.attributes,
                "candidate_id": restricted_candidate.candidate_id,
                "role_bindings": restricted_roles,
            },
        }
    )
    restricted_decision = patent_decision.model_copy(
        update={
            "decision_input_id": "decision-input:patent-inventor:v2-restricted",
            "decision_id": "relationship-decision:patent-inventor:v2-restricted",
            "canonical_relationship_id": ("relationship:patent-inventor:v2-restricted"),
            "candidate_assertion_ids": (restricted_typed_assertion.assertion_id,),
            "selected_assertion_ids": (restricted_typed_assertion.assertion_id,),
            "role_bindings": restricted_roles,
        }
    )
    restricted_request = request.model_copy(
        update={
            "projection_run_id": "relationship-version-run-restricted-person",
            "internal_reference_projection_request": restricted_internal_request,
            "internal_reference_projection_result": restricted_internal_result,
            "candidates": (restricted_candidate,),
            "typed_relationship_assertions": (restricted_typed_assertion,),
            "decision_inputs": (restricted_decision,),
            "retained_assertions": (patent_retained,),
            "retained_artifacts": (),
        }
    )
    restricted_result = projector.project(restricted_request)

    assert restricted_result.candidate_outcomes[0].admitted is False
    assert "professor_paths_require_person_with_professor_reference" in (
        restricted_result.candidate_outcomes[0].reason_codes
    )


def test_person_relationship_rejects_assertion_record_crosswire() -> None:
    internal_module = _module()
    relationship_module: Any = import_module(
        "src.data_agents.canonical_v2.relationship_projection"
    )
    (
        domain_request,
        _,
        identity_request,
        identity_result,
        locators,
    ) = _resolved_person_graph(internal_module)
    paper_assertion = next(
        item
        for item in domain_request.source_assertions
        if item.subject_entity_type == "paper" and item.field_path == "authors"
    )
    secondary_record_id = "record:person:paper_author:secondary"
    repeated_assertion_id = f"{paper_assertion.assertion_id}:secondary"
    repeated_assertion_ids = tuple(
        sorted((paper_assertion.assertion_id, repeated_assertion_id))
    )
    assert isinstance(paper_assertion.value, list)
    changed_paper_value = [
        {**item, "supporting_assertion_ids": list(repeated_assertion_ids)}
        if isinstance(item, dict)
        else item
        for item in paper_assertion.value
    ]
    changed_primary_assertion = paper_assertion.model_copy(
        update={"value": changed_paper_value}
    )
    repeated_assertion = changed_primary_assertion.model_copy(
        update={
            "assertion_id": repeated_assertion_id,
            "source_record_id": secondary_record_id,
        }
    )
    paper_decision = next(
        item
        for item in domain_request.canonical_decisions
        if item.canonical_identity_id == "paper-ada" and item.field_path == "authors"
    )
    changed_decision = paper_decision.model_copy(
        update={
            "candidate_assertion_ids": repeated_assertion_ids,
            "selected_assertion_ids": repeated_assertion_ids,
        }
    )
    paper_current = next(
        item
        for item in domain_request.current_fields
        if item.canonical_identity_id == "paper-ada" and item.field_path == "authors"
    )
    changed_current = paper_current.model_copy(
        update={
            "value": changed_paper_value,
            "supporting_assertion_ids": repeated_assertion_ids,
        }
    )
    changed_domain_request = domain_request.model_copy(
        update={
            "source_assertions": (
                *(
                    changed_primary_assertion if item == paper_assertion else item
                    for item in domain_request.source_assertions
                ),
                repeated_assertion,
            ),
            "canonical_decisions": tuple(
                changed_decision if item == paper_decision else item
                for item in domain_request.canonical_decisions
            ),
            "current_fields": tuple(
                changed_current if item == paper_current else item
                for item in domain_request.current_fields
            ),
        }
    )
    changed_domain_result = (
        projection_models.create_ephemeral_domain_projection_builder().project(
            changed_domain_request
        )
    )
    internal_request = _request(
        internal_module,
        domain_request=changed_domain_request,
        domain_result=changed_domain_result,
        identity_request=identity_request,
        identity_result=identity_result,
        locators=locators,
    )
    internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
        internal_request
    )
    person = internal_result.person_projections[0]
    paper_reference = next(
        item for item in person.references if item.source_kind == "paper_author"
    )
    anchor = next(
        item
        for item in internal_result.public_evidence_anchors
        if item.anchor_id == paper_reference.source_anchor_id
    )
    assert set(anchor.supporting_assertion_ids) == set(repeated_assertion_ids)
    assert set(anchor.source_record_ids) == {
        paper_assertion.source_record_id,
        secondary_record_id,
    }
    source_endpoint = relationship_module.RelationshipEndpointReference(
        reference_kind="canonical_identity",
        endpoint_type="paper",
        stable_reference="canonical:paper:paper-ada",
        canonical_identity_id="paper-ada",
    )
    target_endpoint = relationship_module.RelationshipEndpointReference(
        reference_kind="canonical_identity",
        endpoint_type="person",
        stable_reference=f"canonical:person:{person.canonical_person_identity_id}",
        canonical_identity_id=person.canonical_person_identity_id,
    )
    swapped_retained = (
        relationship_module.RetainedAssertionReference(
            reference_id="retained:paper-author:primary-as-secondary",
            assertion_id=paper_assertion.assertion_id,
            source_record_ref=secondary_record_id,
            artifact_refs=(),
        ),
        relationship_module.RetainedAssertionReference(
            reference_id="retained:paper-author:secondary-as-primary",
            assertion_id=repeated_assertion.assertion_id,
            source_record_ref=paper_assertion.source_record_id,
            artifact_refs=(),
        ),
    )
    binding = relationship_module.RetainedEvidenceBinding(
        evidence_kind="paper_author_assertion",
        assertion_refs=tuple(item.reference_id for item in swapped_retained),
        artifact_refs=(),
    )
    policy = PolicyReference(
        policy_id="person-crosswire-relationship-policy",
        policy_version="person-crosswire-relationship-policy-v1",
        policy_kind=PolicyKind.relationship,
        content_sha256="c" * 64,
        effective_at=NOW - timedelta(days=1),
    )
    candidate = relationship_module.RelationshipProjectionCandidate(
        candidate_id="candidate:paper-author:record-crosswire",
        relationship_type_id="paper_has_author",
        relationship_type_version="canonical-v2-relationship-v2",
        source_endpoint=source_endpoint,
        target_endpoint=target_endpoint,
        role_bindings={"author": target_endpoint.stable_reference},
        evidence_metadata={},
        requested_paths=("relationship_traversal",),
        observed_at=NOW,
        evidence_bindings=(binding,),
    )
    request = relationship_module.RelationshipProjectionRequest(
        catalog=relationship_module.RelationshipCatalogIdentity(
            schema_version=CATALOG_SCHEMA_VERSION,
            catalog_version=CATALOG_VERSION,
            content_sha256=CATALOG_CONTENT_SHA256,
        ),
        relationship_registry_version=(
            relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_VERSION
        ),
        relationship_registry_content_sha256=(
            relationship_module.INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_CONTENT_SHA256
        ),
        release_id=RELEASE_ID,
        projection_run_id="person-record-crosswire-relationship-run",
        as_of=NOW,
        decision_policy=policy,
        domain_projections=changed_domain_result.projections,
        internal_reference_projection_request=internal_request,
        internal_reference_projection_result=internal_result,
        candidates=(candidate,),
        relationship_assertions=(),
        typed_relationship_assertions=(),
        source_canonical_assignments=(),
        decision_inputs=(),
        retained_assertions=swapped_retained,
        retained_artifacts=(),
    )

    result = relationship_module.create_ephemeral_relationship_projection().project(
        request
    )

    assert result.candidate_outcomes[0].admitted is False
    assert "person_relationship_evidence_not_in_internal_graph" in (
        result.candidate_outcomes[0].reason_codes
    )


def test_internal_references_never_widen_public_domains_or_store_derived_claims() -> (
    None
):
    module = _technology_module()

    assert module.PUBLIC_DOMAIN_TYPES == PUBLIC_DOMAINS
    assert module.INTERNAL_REFERENCE_TYPES == INTERNAL_REFERENCE_TYPES
    assert "person" not in module.PUBLIC_DOMAIN_TYPES
    assert "technology_concept" not in module.PUBLIC_DOMAIN_TYPES
    assert "technology_route" not in module.PUBLIC_DOMAIN_TYPES
    assert "industry_brief" not in module.INTERNAL_REFERENCE_TYPES
    assert "product_capability" not in module.INTERNAL_REFERENCE_TYPES
    request_fields = module.InternalReferenceProjectionRequest.model_fields
    assert not {
        "technology_identities",
        "technology_concept_seeds",
        "technology_route_seeds",
        "technology_evidence_relations",
    } & set(request_fields)
    for entity_type in ("industry_brief", "product_capability"):
        with pytest.raises(
            ValidationError,
            match="Technology identity method only accepts Technology sources",
        ):
            _technology_graph(module, forbidden_entity_type=entity_type)


def _candidate_projection_request(
    candidate_module: Any,
    internal_request: Any,
    internal_result: Any,
    *,
    release_id: str | None = None,
) -> Any:
    release_id = release_id or RELEASE_ID
    return candidate_module.CandidateProjectionRequest(
        release_id=release_id,
        build_run_id=internal_request.build_run_id,
        as_of=internal_request.as_of,
        projection_schema_version="canonical-v2-candidate-projection-v1",
        internal_reference_projection_request=internal_request,
        internal_reference_projection_result=internal_result,
    )


def _resolved_person_candidate_bundle() -> tuple[Any, Any]:
    candidate_module = _candidate_projection_module()
    internal_module = _module()
    domain_request, domain_result, identity_request, identity_result, locators = (
        _resolved_person_graph(internal_module)
    )
    internal_request = _request(
        internal_module,
        domain_request=domain_request,
        domain_result=domain_result,
        identity_request=identity_request,
        identity_result=identity_result,
        locators=locators,
    )
    internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
        internal_request
    )
    candidate_request = _candidate_projection_request(
        candidate_module,
        internal_request,
        internal_result,
    )
    return candidate_request, candidate_module.compose_candidate_projections(
        candidate_request
    )


def _technology_candidate_bundle() -> tuple[Any, Any]:
    candidate_module = _candidate_projection_module()
    internal_module = _module()
    graph = _technology_graph(internal_module)
    internal_request = _request(
        internal_module,
        domain_request=graph["domain_request"],
        domain_result=graph["domain_result"],
        identity_request=graph["person_request"],
        identity_result=graph["person_result"],
        locators=graph["person_locators"],
        technology_identity_resolution_request=graph["technology_request"].model_dump(
            mode="python"
        ),
        technology_identity_resolution_result=graph["technology_result"].model_dump(
            mode="python"
        ),
        technology_evidence_locators=graph["technology_locators"],
    )
    internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
        internal_request
    )
    candidate_request = _candidate_projection_request(
        candidate_module,
        internal_request,
        internal_result,
    )
    return candidate_request, candidate_module.compose_candidate_projections(
        candidate_request
    )


def _resolved_person_technology_candidate_bundle(
    *,
    include_shared_institution_alias: bool = False,
) -> tuple[Any, Any]:
    candidate_module = _candidate_projection_module()
    internal_module = _module()
    (
        domain_request,
        domain_result,
        identity_request,
        identity_result,
        locators,
    ) = _resolved_and_unresolved_person_graph(
        internal_module,
        include_shared_institution_alias=include_shared_institution_alias,
    )
    technology_graph = _technology_graph(internal_module)
    internal_request = _request(
        internal_module,
        domain_request=domain_request,
        domain_result=domain_result,
        identity_request=identity_request,
        identity_result=identity_result,
        locators=locators,
        technology_identity_resolution_request=technology_graph[
            "technology_request"
        ].model_dump(mode="python"),
        technology_identity_resolution_result=technology_graph[
            "technology_result"
        ].model_dump(mode="python"),
        technology_evidence_locators=technology_graph["technology_locators"],
    )
    internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
        internal_request
    )
    assert internal_result.person_projections
    assert internal_result.unresolved_person_references
    assert internal_result.technology_route_projections
    candidate_request = _candidate_projection_request(
        candidate_module,
        internal_request,
        internal_result,
    )
    return candidate_request, candidate_module.compose_candidate_projections(
        candidate_request
    )


def _public_path_eligibility_pairs(
    candidate_request: Any,
    *,
    policy_version: str = "path-eligibility-v1",
    semantic_excluded_identity_id: str | None = None,
    exact_limitation_identity_id: str | None = None,
    semantic_limitation_identity_id: str | None = None,
    relationship_limitation_identity_id: str | None = None,
    relationship_excluded_identity_id: str | None = None,
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    public_result = candidate_request.internal_reference_projection_request.public_domain_projection_result
    inclusions = {
        decision.subject_identity_id: decision
        for decision in public_result.inclusion_decisions
    }
    policy = PolicyReference(
        policy_id="canonical-v2-public-path-eligibility",
        policy_version=policy_version,
        policy_kind=PolicyKind.path_eligibility,
        content_sha256=hashlib.sha256(policy_version.encode("utf-8")).hexdigest(),
        effective_at=NOW - timedelta(days=1),
    )
    requests: list[Any] = []
    results: list[Any] = []
    for projection in public_result.projections:
        field_assertion_ids = {
            lineage.field_path: lineage.supporting_assertion_ids
            for lineage in projection.field_lineage
        }
        limited_paths: list[eligibility_models.PublishedPath] = []
        if projection.canonical_identity_id == exact_limitation_identity_id:
            limited_paths.append("exact_lookup")
        if projection.canonical_identity_id == semantic_limitation_identity_id:
            limited_paths.append("semantic_recall")
        if projection.canonical_identity_id == relationship_limitation_identity_id:
            limited_paths.append("verified_relationship_traversal")
        typed_projection = eligibility_models.TypedProjectionInput(
            projection_id=(
                f"typed:{projection.entity_type}:{projection.canonical_identity_id}"
            ),
            canonical_identity_id=projection.canonical_identity_id,
            domain=projection.entity_type,
            release_id=projection.release_id,
            canonical_identity_state=CanonicalIdentityState.active,
            domain_identity_status=(
                "confirmed" if projection.entity_type == "paper" else None
            ),
            usable_field_paths=tuple(field_assertion_ids),
            field_assertion_ids=field_assertion_ids,
            quality_signals=(
                (
                    eligibility_models.QualitySignal(
                        code="profile_incomplete",
                        affected_paths=tuple(limited_paths),
                        supporting_assertion_ids=(
                            min(
                                assertion_id
                                for assertion_ids in field_assertion_ids.values()
                                for assertion_id in assertion_ids
                            ),
                        ),
                    ),
                )
                if limited_paths
                else ()
            ),
        )
        hard_invariant_decisions: list[Any] = []
        if projection.canonical_identity_id == semantic_excluded_identity_id:
            hard_invariant_decisions.append(
                eligibility_models.HardInvariantDecisionInput(
                    decision_id=(
                        "hard-invariant:test-semantic-exclusion:"
                        f"{projection.canonical_identity_id}"
                    ),
                    code="test_semantic_recall_exclusion",
                    affected_paths=("semantic_recall",),
                    supporting_assertion_ids=(
                        next(iter(field_assertion_ids.values()))[0],
                    ),
                    release_id=projection.release_id,
                )
            )
        if projection.canonical_identity_id == relationship_excluded_identity_id:
            hard_invariant_decisions.append(
                eligibility_models.HardInvariantDecisionInput(
                    decision_id=(
                        "hard-invariant:test-relationship-exclusion:"
                        f"{projection.canonical_identity_id}"
                    ),
                    code="test_relationship_traversal_exclusion",
                    affected_paths=("verified_relationship_traversal",),
                    supporting_assertion_ids=(
                        next(iter(field_assertion_ids.values()))[0],
                    ),
                    release_id=projection.release_id,
                )
            )
        request = eligibility_models.PathEligibilityRequest(
            release_id=projection.release_id,
            policy=policy,
            projection=typed_projection,
            inclusion_decision=inclusions[projection.canonical_identity_id],
            relationship_decisions=(),
            hard_invariant_decisions=tuple(hard_invariant_decisions),
            published_paths=eligibility_models.PUBLISHED_USER_PATHS,
            evaluated_at=NOW,
        )
        result = eligibility_models.PathEligibilityEngine().evaluate(request)
        semantic_recall = next(
            decision
            for decision in result.decisions
            if decision.path == "semantic_recall"
        )
        relationship_traversal = next(
            decision
            for decision in result.decisions
            if decision.path == "verified_relationship_traversal"
        )
        expected_inclusion_outcome = inclusions[
            projection.canonical_identity_id
        ].outcome
        assert semantic_recall.outcome is (
            PolicyOutcome.excluded
            if projection.canonical_identity_id == semantic_excluded_identity_id
            else expected_inclusion_outcome
        )
        assert relationship_traversal.outcome is (
            PolicyOutcome.excluded
            if projection.canonical_identity_id == relationship_excluded_identity_id
            else expected_inclusion_outcome
        )
        requests.append(request)
        results.append(result)
    return tuple(requests), tuple(results)


def _index_projection_request(
    module: Any,
    candidate_request: Any,
    candidate_result: Any,
    *,
    path_policy_version: str = "path-eligibility-v1",
    vector_schema_version: str = "canonical-v2-vector-schema-v1",
    embedding_model: str = "recorded-embedding-v1",
    build_mode: str = "full",
    prior_accepted_snapshot: Any | None = None,
    exact_limitation_identity_id: str | None = None,
    semantic_limitation_identity_id: str | None = None,
    relationship_limitation_identity_id: str | None = None,
    relationship_excluded_identity_id: str | None = None,
) -> Any:
    eligibility_requests, eligibility_results = _public_path_eligibility_pairs(
        candidate_request,
        policy_version=path_policy_version,
        exact_limitation_identity_id=exact_limitation_identity_id,
        semantic_limitation_identity_id=semantic_limitation_identity_id,
        relationship_limitation_identity_id=relationship_limitation_identity_id,
        relationship_excluded_identity_id=relationship_excluded_identity_id,
    )
    return module.IndexProjectionRequest(
        candidate_projection_request=candidate_request,
        candidate_projection_result=candidate_result,
        public_path_eligibility_requests=eligibility_requests,
        public_path_eligibility_results=eligibility_results,
        index_projection_version="canonical-v2-index-projection-v1",
        vector_schema_version=vector_schema_version,
        embedding_model=embedding_model,
        internal_auxiliary_policy_version="internal-evidence-anchor-v1",
        build_mode=build_mode,
        prior_accepted_snapshot=prior_accepted_snapshot,
    )


def _s8r2_index_projection_request(
    module: Any,
    authority: tuple[Any, Any, Any, Any],
    *,
    limited_endpoint_ids: tuple[str, ...] = (),
    excluded_endpoint_ids: tuple[str, ...] = (),
) -> Any:
    candidate_request, candidate_result, _, relationship_result = authority
    base = _index_projection_request(module, candidate_request, candidate_result)
    if not relationship_result.typed_relationship_decisions:
        assert relationship_result.current_relationships == ()
        assert not limited_endpoint_ids
        assert not excluded_endpoint_ids
        return base
    typed_decision = relationship_result.typed_relationship_decisions[0]
    assert typed_decision.source_endpoint.canonical_identity_id == "patent-ada"
    assert typed_decision.target_endpoint.canonical_identity_id == "company-robotics"
    eligibility_decision = RelationshipDecision(
        decision_id=typed_decision.decision_id,
        canonical_relationship_id=typed_decision.canonical_relationship_id,
        relationship_type_id=typed_decision.relationship_type_id,
        relationship_type_version=typed_decision.relationship_type_version,
        source_canonical_identity_id="patent-ada",
        target_canonical_identity_id="company-robotics",
        state=typed_decision.state,
        candidate_assertion_ids=typed_decision.candidate_assertion_ids,
        selected_assertion_ids=typed_decision.selected_assertion_ids,
        conflicting_assertion_ids=typed_decision.conflicting_assertion_ids,
        role_bindings=typed_decision.role_bindings,
        policy=typed_decision.policy,
        method=typed_decision.method,
        method_version=typed_decision.method_version,
        decision_run_id=typed_decision.decision_run_id,
        confidence=typed_decision.confidence,
        rationale=typed_decision.rationale,
        valid_from=typed_decision.valid_from,
        valid_to=typed_decision.valid_to,
        release_id=typed_decision.release_id,
        decided_at=typed_decision.decided_at,
        supersedes_decision_id=typed_decision.supersedes_decision_id,
    )
    base_pairs = {
        request.projection.canonical_identity_id: (request, result)
        for request, result in zip(
            base.public_path_eligibility_requests,
            base.public_path_eligibility_results,
            strict=True,
        )
        if request.projection is not None
    }
    company_request, _ = base_pairs["company-robotics"]
    patent_request, _ = base_pairs["patent-ada"]
    assert company_request.projection is not None
    assert patent_request.projection is not None

    def endpoint_projection(source_request: Any) -> Any:
        projection = source_request.projection
        assert projection is not None
        if projection.canonical_identity_id not in limited_endpoint_ids:
            return projection
        supporting_assertion_id = min(
            assertion_id
            for assertion_ids in projection.field_assertion_ids.values()
            for assertion_id in assertion_ids
        )
        return projection.model_copy(
            update={
                "quality_signals": (
                    *projection.quality_signals,
                    eligibility_models.QualitySignal(
                        code=(
                            "s8r2_relationship_limited_"
                            f"{projection.canonical_identity_id}"
                        ),
                        affected_paths=("verified_relationship_traversal",),
                        supporting_assertion_ids=(supporting_assertion_id,),
                    ),
                )
            }
        )

    endpoint_projections = {
        "company-robotics": endpoint_projection(company_request),
        "patent-ada": endpoint_projection(patent_request),
    }

    replacements: dict[str, tuple[Any, Any]] = {}
    for source_request, target_request, direction in (
        (company_request, patent_request, "company_to_patent"),
        (patent_request, company_request, "patent_to_company"),
    ):
        assert source_request.projection is not None
        assert target_request.projection is not None
        source_id = source_request.projection.canonical_identity_id
        target_id = target_request.projection.canonical_identity_id
        hard_invariants = source_request.hard_invariant_decisions
        if source_id in excluded_endpoint_ids:
            source_projection = endpoint_projections[source_id]
            supporting_assertion_id = min(
                assertion_id
                for assertion_ids in source_projection.field_assertion_ids.values()
                for assertion_id in assertion_ids
            )
            hard_invariants = (
                *hard_invariants,
                eligibility_models.HardInvariantDecisionInput(
                    decision_id=f"hard-invariant:s8r2:{source_id}",
                    code=f"s8r2_relationship_excluded_{source_id}",
                    affected_paths=("verified_relationship_traversal",),
                    supporting_assertion_ids=(supporting_assertion_id,),
                    release_id=source_projection.release_id,
                ),
            )
        directional_request = source_request.model_copy(
            update={
                "projection": endpoint_projections[source_id],
                "related_projections": (endpoint_projections[target_id],),
                "relationship_decisions": (eligibility_decision,),
                "hard_invariant_decisions": hard_invariants,
                "requested_traversal_direction": direction,
            }
        )
        directional_request = eligibility_models.PathEligibilityRequest.model_validate(
            directional_request.model_dump(mode="python")
        )
        directional_result = eligibility_models.PathEligibilityEngine().evaluate(
            directional_request
        )
        traversal = next(
            decision
            for decision in directional_result.decisions
            if decision.path == "verified_relationship_traversal"
        )
        expected_outcome = (
            PolicyOutcome.excluded
            if source_id in excluded_endpoint_ids
            else PolicyOutcome.admitted
        )
        assert traversal.outcome is expected_outcome
        assert directional_result.relationship_decision_ids == (
            typed_decision.decision_id,
        )
        assert directional_result.traversal_directions == (direction,)
        replacements[directional_result.subject_identity_id] = (
            directional_request,
            directional_result,
        )

    eligibility_requests = tuple(
        replacements.get(
            request.projection.canonical_identity_id
            if request.projection is not None
            else "",
            (request, result),
        )[0]
        for request, result in zip(
            base.public_path_eligibility_requests,
            base.public_path_eligibility_results,
            strict=True,
        )
    )
    eligibility_results = tuple(
        replacements.get(result.subject_identity_id, (request, result))[1]
        for request, result in zip(
            base.public_path_eligibility_requests,
            base.public_path_eligibility_results,
            strict=True,
        )
    )
    provisional = base.model_copy(
        update={
            "public_path_eligibility_requests": eligibility_requests,
            "public_path_eligibility_results": eligibility_results,
        }
    )
    return module.IndexProjectionRequest.model_validate(
        provisional.model_dump(mode="python")
    )


def _s8r3_index_projection_request(
    module: Any,
    authority: tuple[Any, Any, Any, Any],
    *,
    paper_identity_status: str = "confirmed",
    limited_endpoint_ids: tuple[str, ...] = (),
    excluded_endpoint_ids: tuple[str, ...] = (),
) -> Any:
    candidate_request, candidate_result, _, relationship_result = authority
    base = _index_projection_request(module, candidate_request, candidate_result)
    if not relationship_result.current_relationships:
        assert not limited_endpoint_ids
        assert not excluded_endpoint_ids
        return base
    assert len(relationship_result.relationship_decisions) == 1
    relationship_decision = relationship_result.relationship_decisions[0]
    assert relationship_decision.source_canonical_identity_id == "professor-ada"
    assert relationship_decision.target_canonical_identity_id == "paper-ada"
    base_pairs = {
        request.projection.canonical_identity_id: (request, result)
        for request, result in zip(
            base.public_path_eligibility_requests,
            base.public_path_eligibility_results,
            strict=True,
        )
        if request.projection is not None
    }
    professor_request, _ = base_pairs["professor-ada"]
    paper_request, _ = base_pairs["paper-ada"]
    assert professor_request.projection is not None
    assert paper_request.projection is not None

    def endpoint_projection(source_request: Any) -> Any:
        projection = source_request.projection
        assert projection is not None
        update: dict[str, Any] = {}
        if projection.domain == "paper":
            update["domain_identity_status"] = paper_identity_status
        if projection.canonical_identity_id in limited_endpoint_ids:
            supporting_assertion_id = min(
                assertion_id
                for assertion_ids in projection.field_assertion_ids.values()
                for assertion_id in assertion_ids
            )
            update["quality_signals"] = (
                *projection.quality_signals,
                eligibility_models.QualitySignal(
                    code=(
                        f"s8r3_relationship_limited_{projection.canonical_identity_id}"
                    ),
                    affected_paths=("verified_relationship_traversal",),
                    supporting_assertion_ids=(supporting_assertion_id,),
                ),
            )
        return projection.model_copy(update=update) if update else projection

    endpoint_projections = {
        "professor-ada": endpoint_projection(professor_request),
        "paper-ada": endpoint_projection(paper_request),
    }
    replacements: dict[str, tuple[Any, Any]] = {}
    for source_request, target_request, direction in (
        (professor_request, paper_request, "professor_to_paper"),
        (paper_request, professor_request, "paper_to_professor"),
    ):
        assert source_request.projection is not None
        assert target_request.projection is not None
        source_id = source_request.projection.canonical_identity_id
        target_id = target_request.projection.canonical_identity_id
        hard_invariants = source_request.hard_invariant_decisions
        if source_id in excluded_endpoint_ids:
            source_projection = endpoint_projections[source_id]
            supporting_assertion_id = min(
                assertion_id
                for assertion_ids in source_projection.field_assertion_ids.values()
                for assertion_id in assertion_ids
            )
            hard_invariants = (
                *hard_invariants,
                eligibility_models.HardInvariantDecisionInput(
                    decision_id=f"hard-invariant:s8r3:{source_id}",
                    code=f"s8r3_relationship_excluded_{source_id}",
                    affected_paths=("verified_relationship_traversal",),
                    supporting_assertion_ids=(supporting_assertion_id,),
                    release_id=source_projection.release_id,
                ),
            )
        directional_request = source_request.model_copy(
            update={
                "projection": endpoint_projections[source_id],
                "related_projections": (endpoint_projections[target_id],),
                "relationship_decisions": (relationship_decision,),
                "hard_invariant_decisions": hard_invariants,
                "requested_traversal_direction": direction,
            }
        )
        directional_request = eligibility_models.PathEligibilityRequest.model_validate(
            directional_request.model_dump(mode="python")
        )
        directional_result = eligibility_models.PathEligibilityEngine().evaluate(
            directional_request
        )
        traversal = next(
            decision
            for decision in directional_result.decisions
            if decision.path == "verified_relationship_traversal"
        )
        expected_outcome = (
            PolicyOutcome.excluded
            if source_id in excluded_endpoint_ids
            else source_request.inclusion_decision.outcome
        )
        assert traversal.outcome is expected_outcome, (
            source_id,
            traversal.outcome,
            expected_outcome,
            traversal.limitations,
        )
        if source_id == "paper-ada" and paper_identity_status == "unverified":
            assert "identity_unverified" in traversal.limitations
        if source_id in limited_endpoint_ids:
            assert f"s8r3_relationship_limited_{source_id}" in traversal.limitations
        assert directional_result.relationship_decision_ids == (
            relationship_decision.decision_id,
        )
        assert directional_result.traversal_directions == (direction,)
        replacements[directional_result.subject_identity_id] = (
            directional_request,
            directional_result,
        )

    eligibility_requests = tuple(
        replacements.get(
            request.projection.canonical_identity_id
            if request.projection is not None
            else "",
            (request, result),
        )[0]
        for request, result in zip(
            base.public_path_eligibility_requests,
            base.public_path_eligibility_results,
            strict=True,
        )
    )
    eligibility_results = tuple(
        replacements.get(result.subject_identity_id, (request, result))[1]
        for request, result in zip(
            base.public_path_eligibility_requests,
            base.public_path_eligibility_results,
            strict=True,
        )
    )
    provisional = base.model_copy(
        update={
            "public_path_eligibility_requests": eligibility_requests,
            "public_path_eligibility_results": eligibility_results,
        }
    )
    return module.IndexProjectionRequest.model_validate(
        provisional.model_dump(mode="python")
    )


def test_candidate_projection_materializes_complete_public_and_person_matrix() -> None:
    candidate_module = _candidate_projection_module()
    internal_module = _module()
    domain_request, domain_result, identity_request, identity_result, locators = (
        _resolved_person_graph(internal_module)
    )
    internal_request = _request(
        internal_module,
        domain_request=domain_request,
        domain_result=domain_result,
        identity_request=identity_request,
        identity_result=identity_result,
        locators=locators,
    )
    internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
        internal_request
    )

    result = candidate_module.compose_candidate_projections(
        _candidate_projection_request(
            candidate_module,
            internal_request,
            internal_result,
        )
    )

    assert result.release_id == RELEASE_ID
    assert result.public_domain_projections == domain_result.projections
    assert result.person_projections == internal_result.person_projections
    assert result.technology_concept_projections == ()
    assert result.technology_route_projections == ()
    assert result.public_domain_projection_result_content_sha256 == (
        domain_result.content_sha256
    )
    assert result.internal_reference_projection_result_content_sha256 == (
        internal_result.content_sha256
    )
    assert {
        (
            item.projection_scope.value,
            item.domain,
            item.reference_type,
            item.record_count,
        )
        for item in result.published_projections
    } == {
        ("public_domain", "company", None, 1),
        ("public_domain", "paper", None, 1),
        ("public_domain", "patent", None, 1),
        ("public_domain", "professor", None, 1),
        ("internal_auxiliary", None, "person", 1),
        ("internal_auxiliary", None, "technology_concept", 0),
        ("internal_auxiliary", None, "technology_route", 0),
    }
    assert {
        (item.projection_scope.value, item.projection_kind, item.path)
        for item in result.published_projections
    } == {
        ("public_domain", "typed_current", None),
        ("internal_auxiliary", "internal_reference", None),
    }
    assert {
        "decision_set",
        "relationship_set",
        "eligibility_sets",
        "expected_index_projections",
    }.isdisjoint(type(result).model_fields)


def test_candidate_projection_materializes_versioned_technology_auxiliaries_without_fifth_domain() -> (
    None
):
    candidate_module = _candidate_projection_module()
    internal_module = _technology_module()
    graph = _technology_graph(internal_module)
    internal_request = _request(
        internal_module,
        domain_request=graph["domain_request"],
        domain_result=graph["domain_result"],
        identity_request=graph["person_request"],
        identity_result=graph["person_result"],
        locators=graph["person_locators"],
        technology_identity_resolution_request=graph["technology_request"].model_dump(
            mode="python"
        ),
        technology_identity_resolution_result=graph["technology_result"].model_dump(
            mode="python"
        ),
        technology_evidence_locators=graph["technology_locators"],
    )
    internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
        internal_request
    )
    request = _candidate_projection_request(
        candidate_module,
        internal_request,
        internal_result,
    )

    result = candidate_module.compose_candidate_projections(request)
    repeated = candidate_module.compose_candidate_projections(request)

    assert result.public_domain_projections == graph["domain_result"].projections
    assert result.person_projections == ()
    assert result.technology_concept_projections == (
        internal_result.technology_concept_projections
    )
    assert result.technology_route_projections == (
        internal_result.technology_route_projections
    )
    assert {
        (
            item.projection_scope.value,
            item.domain,
            item.reference_type,
            item.record_count,
        )
        for item in result.published_projections
    } == {
        ("public_domain", "company", None, 1),
        ("public_domain", "paper", None, 0),
        ("public_domain", "patent", None, 0),
        ("public_domain", "professor", None, 0),
        ("internal_auxiliary", None, "person", 0),
        ("internal_auxiliary", None, "technology_concept", 2),
        ("internal_auxiliary", None, "technology_route", 1),
    }
    assert {
        item.domain
        for item in result.published_projections
        if item.projection_scope.value == "public_domain"
    } == set(PUBLIC_DOMAINS)
    assert {
        item.reference_type
        for item in result.published_projections
        if item.projection_scope.value == "internal_auxiliary"
    } == set(INTERNAL_REFERENCE_TYPES)
    assert repeated.model_dump_json() == result.model_dump_json()

    unresolved_graph = _technology_graph(
        internal_module,
        unresolved_source_identity_id="source-tech-route-visual-servo",
    )
    unresolved_internal_request = _request(
        internal_module,
        domain_request=unresolved_graph["domain_request"],
        domain_result=unresolved_graph["domain_result"],
        identity_request=unresolved_graph["person_request"],
        identity_result=unresolved_graph["person_result"],
        locators=unresolved_graph["person_locators"],
        technology_identity_resolution_request=unresolved_graph[
            "technology_request"
        ].model_dump(mode="python"),
        technology_identity_resolution_result=unresolved_graph[
            "technology_result"
        ].model_dump(mode="python"),
        technology_evidence_locators=unresolved_graph["technology_locators"],
    )
    unresolved_internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
        unresolved_internal_request
    )
    unresolved_result = candidate_module.compose_candidate_projections(
        _candidate_projection_request(
            candidate_module,
            unresolved_internal_request,
            unresolved_internal_result,
        )
    )
    public_hashes = {
        item.domain: item.content_sha256
        for item in result.published_projections
        if item.projection_scope.value == "public_domain"
    }
    unresolved_public_hashes = {
        item.domain: item.content_sha256
        for item in unresolved_result.published_projections
        if item.projection_scope.value == "public_domain"
    }
    assert unresolved_public_hashes == public_hashes
    resolved_route_manifest = next(
        item
        for item in result.published_projections
        if item.reference_type == "technology_route"
    )
    unresolved_route_manifest = next(
        item
        for item in unresolved_result.published_projections
        if item.reference_type == "technology_route"
    )
    assert resolved_route_manifest.record_count == 1
    assert unresolved_route_manifest.record_count == 0
    assert unresolved_route_manifest.content_sha256 != (
        resolved_route_manifest.content_sha256
    )
    assert unresolved_result.content_sha256 != result.content_sha256

    tampered = result.model_dump(mode="python")
    tampered["published_projections"][0]["content_sha256"] = "f" * 64
    with pytest.raises(ValidationError, match="published projection manifests"):
        candidate_module.CandidateProjectionResult(**tampered)


def test_candidate_projection_keeps_unresolved_references_out_of_public_domains() -> (
    None
):
    candidate_module = _candidate_projection_module()
    internal_module = _module()
    domain_request, domain_result, identity_request, identity_result, locators = (
        _unresolved_person_graph(internal_module)
    )
    internal_request = _request(
        internal_module,
        domain_request=domain_request,
        domain_result=domain_result,
        identity_request=identity_request,
        identity_result=identity_result,
        locators=locators,
    )
    internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
        internal_request
    )

    result = candidate_module.compose_candidate_projections(
        _candidate_projection_request(
            candidate_module,
            internal_request,
            internal_result,
        )
    )

    assert len(internal_result.unresolved_person_references) == 2
    assert result.person_projections == ()
    person_manifest = next(
        item for item in result.published_projections if item.reference_type == "person"
    )
    assert person_manifest.record_count == 0
    assert {
        item.domain
        for item in result.published_projections
        if item.projection_scope.value == "public_domain"
    } == set(PUBLIC_DOMAINS)
    assert not {
        "person",
        "technology_concept",
        "technology_route",
        "product",
        "industry_brief",
        "product_capability",
    } & {
        item.domain for item in result.published_projections if item.domain is not None
    }


def test_candidate_projection_rejects_cross_release_or_unreplayable_inputs() -> None:
    candidate_module = _candidate_projection_module()
    internal_module = _module()
    domain_request, domain_result, identity_request, identity_result, locators = (
        _resolved_person_graph(internal_module)
    )
    internal_request = _request(
        internal_module,
        domain_request=domain_request,
        domain_result=domain_result,
        identity_request=identity_request,
        identity_result=identity_result,
        locators=locators,
    )
    internal_result = internal_module.create_ephemeral_internal_reference_projection_builder().project(
        internal_request
    )

    with pytest.raises(ValidationError, match="one candidate release"):
        _candidate_projection_request(
            candidate_module,
            internal_request,
            internal_result,
            release_id="candidate-other",
        )

    tampered_result = internal_result.model_copy(update={"content_sha256": "f" * 64})
    valid_request = _candidate_projection_request(
        candidate_module,
        internal_request,
        internal_result,
    )
    tampered_request = valid_request.model_copy(
        update={"internal_reference_projection_result": tampered_result}
    )
    with pytest.raises(
        candidate_module.CandidateProjectionIntegrityError,
        match="exact replay",
    ):
        candidate_module.compose_candidate_projections(tampered_request)


def test_index_projection_binds_versioned_metadata_and_professor_intent_split() -> None:
    module = _index_projection_module()
    candidate_request, candidate_result = _resolved_person_candidate_bundle()
    request = _index_projection_request(
        module,
        candidate_request,
        candidate_result,
    )

    builder = module.create_ephemeral_index_projection_builder()
    assert isinstance(builder, module.IndexProjectionBuilder)
    result = builder.build(request)
    repeated = module.create_ephemeral_index_projection_builder().build(request)

    assert result.release_id == RELEASE_ID
    assert result.model_dump_json() == repeated.model_dump_json()
    assert result.expected_index_projections == result.actual_index_projections
    assert len(result.expected_index_projections) == 8
    assert len(
        {manifest.projection_id for manifest in result.expected_index_projections}
    ) == len(result.expected_index_projections)
    assert {
        manifest.domain
        for manifest in result.expected_index_projections
        if manifest.projection_scope.value == "public_domain"
    } == set(PUBLIC_DOMAINS)
    assert {
        manifest.reference_type
        for manifest in result.expected_index_projections
        if manifest.projection_scope.value == "internal_auxiliary"
    } == set(INTERNAL_REFERENCE_TYPES)
    assert (
        sum(manifest.point_count for manifest in result.expected_index_projections) == 6
    )
    assert all(
        manifest.release_id == RELEASE_ID
        and manifest.projection_version == "canonical-v2-index-projection-v1"
        and manifest.schema_version == "canonical-v2-vector-schema-v1"
        and manifest.embedding_model == "recorded-embedding-v1"
        and manifest.eligibility_policy_version
        == (
            "path-eligibility-v1"
            if manifest.projection_scope.value == "public_domain"
            else "internal-evidence-anchor-v1"
        )
        and manifest.full_rebuild is True
        for manifest in result.expected_index_projections
    )

    source_hashes = {
        projection.canonical_identity_id: projection.content_sha256
        for projection in candidate_result.public_domain_projections
    }
    source_hashes.update(
        {
            projection.canonical_person_identity_id: projection.content_sha256
            for projection in candidate_result.person_projections
        }
    )
    assert len(result.points) == 6
    assert len({point.point_id for point in result.points}) == 6
    person_id = candidate_result.person_projections[0].canonical_person_identity_id
    assert {
        (
            point.projection_scope.value,
            point.domain,
            point.reference_type,
            point.canonical_object_id,
            point.projection_view.value,
        )
        for point in result.points
    } == {
        ("public_domain", "company", None, "company-robotics", "default"),
        ("public_domain", "paper", None, "paper-ada", "default"),
        ("public_domain", "patent", None, "patent-ada", "default"),
        ("public_domain", "professor", None, "professor-ada", "identity"),
        ("public_domain", "professor", None, "professor-ada", "research"),
        ("internal_auxiliary", None, "person", person_id, "default"),
    }
    person_point = next(
        point for point in result.points if point.reference_type == "person"
    )
    assert set(candidate_result.person_projections[0].source_anchor_ids) <= set(
        person_point.source_evidence_ids
    )
    for manifest in result.expected_index_projections:
        owned_points = tuple(
            point
            for point in result.points
            if point.projection_id == manifest.projection_id
        )
        assert len(owned_points) == manifest.point_count
        assert all(
            point.eligibility_policy_version == manifest.eligibility_policy_version
            for point in owned_points
        )
    for point in result.points:
        assert point.release_id == RELEASE_ID
        assert point.path == "semantic_recall"
        assert point.projection_version == "canonical-v2-index-projection-v1"
        assert point.schema_version == "canonical-v2-vector-schema-v1"
        assert point.embedding_model == "recorded-embedding-v1"
        assert point.eligibility_policy_version in {
            "path-eligibility-v1",
            "internal-evidence-anchor-v1",
        }
        assert (
            point.source_projection_content_sha256
            == source_hashes[point.canonical_object_id]
        )
        assert (
            point.embedded_content_sha256
            == hashlib.sha256(point.embedded_content.encode("utf-8")).hexdigest()
        )
        assert point.source_evidence_ids

    professor_points = tuple(
        point for point in result.points if point.domain == "professor"
    )
    assert {point.projection_view.value for point in professor_points} == {
        "identity",
        "research",
    }
    professor_projection_ids = {point.projection_id for point in professor_points}
    professor_manifests = tuple(
        manifest
        for manifest in result.expected_index_projections
        if manifest.domain == "professor"
    )
    assert len(professor_projection_ids) == len(professor_manifests) == 2
    assert {manifest.projection_id for manifest in professor_manifests} == (
        professor_projection_ids
    )
    assert all(manifest.point_count == 1 for manifest in professor_manifests)
    identity_point = next(
        point for point in professor_points if point.projection_view.value == "identity"
    )
    research_point = next(
        point for point in professor_points if point.projection_view.value == "research"
    )
    assert (
        identity_point.canonical_object_id
        == research_point.canonical_object_id
        == ("professor-ada")
    )
    assert all(
        value in identity_point.embedded_content
        for value in ("陈艾达", "SUSTech", "Computer Science", "Professor")
    )
    assert all(
        value not in identity_point.embedded_content
        for value in (
            "Robotics professor.",
            "Robotics papers.",
            "Robotics patents.",
        )
    )
    assert all(
        value in research_point.embedded_content
        for value in (
            "Robotics professor.",
            "Robotics papers.",
            "Robotics patents.",
        )
    )
    assert all(
        value not in research_point.embedded_content
        for value in ("ada@example.edu", "https://example.edu/ada")
    )

    denied_requests, denied_results = _public_path_eligibility_pairs(
        candidate_request,
        semantic_excluded_identity_id="paper-ada",
    )
    denied = module.create_ephemeral_index_projection_builder().build(
        request.model_copy(
            update={
                "public_path_eligibility_requests": denied_requests,
                "public_path_eligibility_results": denied_results,
            }
        )
    )
    assert len(denied.points) == 5
    assert not any(
        point.domain == "paper" and point.canonical_object_id == "paper-ada"
        for point in denied.points
    )
    admitted_paper_manifest = next(
        manifest
        for manifest in result.expected_index_projections
        if manifest.domain == "paper"
    )
    denied_paper_manifest = next(
        manifest
        for manifest in denied.expected_index_projections
        if manifest.domain == "paper"
    )
    assert admitted_paper_manifest.point_count == 1
    assert denied_paper_manifest.point_count == 0
    assert denied_paper_manifest.entity_ids_sha256 != (
        admitted_paper_manifest.entity_ids_sha256
    )
    assert denied_paper_manifest.content_sha256 != (
        admitted_paper_manifest.content_sha256
    )

    tampered_candidate = candidate_result.model_copy(
        update={"content_sha256": "f" * 64}
    )
    with pytest.raises(
        module.IndexProjectionIntegrityError,
        match="candidate projection.*replay",
    ):
        builder.build(
            request.model_copy(
                update={"candidate_projection_result": tampered_candidate}
            )
        )

    tampered_eligibility_results = list(request.public_path_eligibility_results)
    tampered_eligibility_results[0] = tampered_eligibility_results[0].model_copy(
        update={"content_sha256": "f" * 64}
    )
    with pytest.raises(
        module.IndexProjectionIntegrityError,
        match="path eligibility.*replay",
    ):
        builder.build(
            request.model_copy(
                update={
                    "public_path_eligibility_results": tuple(
                        tampered_eligibility_results
                    )
                }
            )
        )

    substituted_requests = list(request.public_path_eligibility_requests)
    substituted_results = list(request.public_path_eligibility_results)
    substituted_inclusion = substituted_requests[0].inclusion_decision.model_copy(
        update={"decision_id": "inclusion:substituted-lineage"}
    )
    substituted_requests[0] = substituted_requests[0].model_copy(
        update={"inclusion_decision": substituted_inclusion}
    )
    substituted_results[0] = eligibility_models.PathEligibilityEngine().evaluate(
        substituted_requests[0]
    )
    with pytest.raises(
        module.IndexProjectionIntegrityError,
        match="exact candidate inclusion",
    ):
        builder.build(
            request.model_copy(
                update={
                    "public_path_eligibility_requests": tuple(substituted_requests),
                    "public_path_eligibility_results": tuple(substituted_results),
                }
            )
        )


def test_index_projection_materializes_release_scoped_public_lookup_documents() -> None:
    module = _index_projection_module()
    candidate_request, candidate_result = _resolved_person_candidate_bundle()
    request = _index_projection_request(
        module,
        candidate_request,
        candidate_result,
    )

    builder = module.create_ephemeral_index_projection_builder()
    result = builder.build(request)
    repeated = module.create_ephemeral_index_projection_builder().build(request)

    assert result.model_dump_json() == repeated.model_dump_json()
    assert result.expected_lookup_projections == result.actual_lookup_projections
    assert len(result.expected_lookup_projections) == 7
    assert len({item.projection_id for item in result.expected_lookup_projections}) == 7
    assert {
        item.domain
        for item in result.expected_lookup_projections
        if item.projection_scope.value == "public_domain"
    } == set(PUBLIC_DOMAINS)
    assert {
        item.reference_type
        for item in result.expected_lookup_projections
        if item.projection_scope.value == "internal_auxiliary"
    } == set(INTERNAL_REFERENCE_TYPES)
    assert all(
        item.release_id == RELEASE_ID
        and item.path == "exact_lookup"
        and item.projection_version == "canonical-v2-lookup-projection-v1"
        and item.schema_version == "canonical-v2-lookup-schema-v1"
        and item.eligibility_policy_version
        == (
            "path-eligibility-v1"
            if item.projection_scope.value == "public_domain"
            else "internal-evidence-anchor-v1"
        )
        and item.full_rebuild is True
        for item in result.expected_lookup_projections
    )

    assert len(result.lookup_documents) == 5
    assert {
        (
            item.projection_scope.value,
            item.domain,
            item.reference_type,
            item.canonical_object_id,
            item.projection_view.value,
        )
        for item in result.lookup_documents
    } == {
        ("public_domain", "company", None, "company-robotics", "default"),
        ("public_domain", "paper", None, "paper-ada", "default"),
        ("public_domain", "patent", None, "patent-ada", "default"),
        ("public_domain", "professor", None, "professor-ada", "identity"),
        (
            "internal_auxiliary",
            None,
            "person",
            candidate_result.person_projections[0].canonical_person_identity_id,
            "default",
        ),
    }
    source_hashes = {
        item.canonical_identity_id: item.content_sha256
        for item in candidate_result.public_domain_projections
    }
    source_hashes.update(
        {
            item.canonical_person_identity_id: item.content_sha256
            for item in candidate_result.person_projections
        }
    )
    for manifest in result.expected_lookup_projections:
        owned_documents = tuple(
            item
            for item in result.lookup_documents
            if item.projection_id == manifest.projection_id
        )
        assert len(owned_documents) == manifest.document_count
        assert all(
            item.eligibility_policy_version == manifest.eligibility_policy_version
            for item in owned_documents
        )
    for document in result.lookup_documents:
        assert document.release_id == RELEASE_ID
        assert document.path == "exact_lookup"
        assert (
            document.source_projection_content_sha256
            == source_hashes[document.canonical_object_id]
        )
        assert (
            document.lookup_content_sha256
            == hashlib.sha256(document.lookup_content.encode("utf-8")).hexdigest()
        )
        assert document.source_evidence_ids

    person_document = next(
        item for item in result.lookup_documents if item.reference_type == "person"
    )
    assert set(candidate_result.person_projections[0].source_anchor_ids) <= set(
        person_document.source_evidence_ids
    )

    denied_requests, denied_results = _public_path_eligibility_pairs(
        candidate_request,
        semantic_excluded_identity_id="paper-ada",
    )
    denied = builder.build(
        request.model_copy(
            update={
                "public_path_eligibility_requests": denied_requests,
                "public_path_eligibility_results": denied_results,
            }
        )
    )
    assert not any(
        point.domain == "paper" and point.canonical_object_id == "paper-ada"
        for point in denied.points
    )
    assert any(
        item.domain == "paper" and item.canonical_object_id == "paper-ada"
        for item in denied.lookup_documents
    )


def test_lookup_projection_retains_exact_eligibility_lineage_and_manifest_binding() -> (
    None
):
    module = _index_projection_module()
    candidate_request, candidate_result = _resolved_person_candidate_bundle()
    request = _index_projection_request(
        module,
        candidate_request,
        candidate_result,
        exact_limitation_identity_id="paper-ada",
    )

    result = module.create_ephemeral_index_projection_builder().build(request)
    exact_decisions = {
        eligibility_result.subject_identity_id: next(
            decision
            for decision in eligibility_result.decisions
            if decision.path == "exact_lookup"
        )
        for eligibility_result in request.public_path_eligibility_results
    }
    public_documents = tuple(
        document
        for document in result.lookup_documents
        if document.projection_scope.value == "public_domain"
    )

    assert len(public_documents) == 4
    for document in public_documents:
        decision = exact_decisions[document.canonical_object_id]
        assert document.eligibility_decision_id == decision.decision_id
        assert document.eligibility_outcome == decision.outcome.value
        assert document.eligibility_limitations == decision.limitations

    paper_document = next(
        document
        for document in public_documents
        if document.canonical_object_id == "paper-ada"
    )
    assert paper_document.eligibility_limitations == ("profile_incomplete",)
    for document in result.lookup_documents:
        if document.projection_scope.value == "internal_auxiliary":
            assert document.eligibility_decision_id is None
            assert document.eligibility_outcome == "admitted"
            assert document.eligibility_limitations == ()

    with pytest.raises(ValidationError, match="limited.*limitation"):
        module.LookupProjectionDocument.model_validate(
            {
                **paper_document.model_dump(mode="json"),
                "eligibility_outcome": "limited",
                "eligibility_limitations": (),
            }
        )

    changed_document = module.LookupProjectionDocument.model_validate(
        {
            **paper_document.model_dump(mode="json"),
            "eligibility_limitations": ("different_visible_limitation",),
        }
    )
    changed_documents = tuple(
        changed_document
        if document.document_id == paper_document.document_id
        else document
        for document in result.lookup_documents
    )
    changed_manifests = module.build_lookup_projection_manifests(
        request=request,
        documents=changed_documents,
        full_rebuild=True,
    )
    original_manifest = next(
        manifest
        for manifest in result.expected_lookup_projections
        if manifest.projection_id == paper_document.projection_id
    )
    changed_manifest = next(
        manifest
        for manifest in changed_manifests
        if manifest.projection_id == paper_document.projection_id
    )

    assert changed_document.document_id == paper_document.document_id
    assert (
        changed_document.lookup_content_sha256 == paper_document.lookup_content_sha256
    )
    assert changed_manifest.content_sha256 != original_manifest.content_sha256


def test_vector_projection_retains_semantic_eligibility_lineage_and_full_manifest_binding() -> (
    None
):
    module = _index_projection_module()
    required_fields = {
        "eligibility_decision_id",
        "eligibility_outcome",
        "eligibility_limitations",
    }
    missing_fields = required_fields - set(module.IndexProjectionPoint.model_fields)
    if missing_fields:
        raise _MissingS7JSemanticEligibilityLineage(
            "IndexProjectionPoint lacks exact semantic eligibility fields: "
            + ", ".join(sorted(missing_fields))
        )

    publication_module = import_module(
        "src.data_agents.canonical_v2.release_publication"
    )
    request, result, manifest = _task7_7_release_values(
        publication_module,
        release_id=RELEASE_ID,
        semantic_limitation_identity_id="paper-ada",
        candidate_bundle_factory=_resolved_person_technology_candidate_bundle,
    )
    semantic_decisions = {
        eligibility_result.subject_identity_id: next(
            decision
            for decision in eligibility_result.decisions
            if decision.path == "semantic_recall"
        )
        for eligibility_result in request.public_path_eligibility_results
    }
    public_points = tuple(
        point
        for point in result.points
        if point.projection_scope.value == "public_domain"
    )
    assert public_points
    for point in public_points:
        decision = semantic_decisions[point.canonical_object_id]
        assert point.eligibility_decision_id == decision.decision_id
        assert point.eligibility_outcome == decision.outcome.value
        assert point.eligibility_limitations == decision.limitations

    paper_point = next(
        point for point in public_points if point.canonical_object_id == "paper-ada"
    )
    assert paper_point.eligibility_outcome == "admitted"
    assert paper_point.eligibility_limitations == ("profile_incomplete",)
    internal_point = next(
        point
        for point in result.points
        if point.projection_scope.value == "internal_auxiliary"
    )
    for point in result.points:
        if point.projection_scope.value == "internal_auxiliary":
            assert point.eligibility_decision_id is None
            assert point.eligibility_outcome == "admitted"
            assert point.eligibility_limitations == ()

    paper_payload = paper_point.model_dump(mode="json")
    with pytest.raises(ValidationError, match="public.*decision"):
        module.IndexProjectionPoint.model_validate(
            {**paper_payload, "eligibility_decision_id": None}
        )
    with pytest.raises(ValidationError, match="limited.*limitation"):
        module.IndexProjectionPoint.model_validate(
            {
                **paper_payload,
                "eligibility_outcome": "limited",
                "eligibility_limitations": (),
            }
        )
    with pytest.raises(ValidationError, match="internal"):
        module.IndexProjectionPoint.model_validate(
            {
                **internal_point.model_dump(mode="json"),
                "eligibility_decision_id": "path-decision:forbidden-internal",
                "eligibility_limitations": ("forbidden_internal_limitation",),
            }
        )
    with pytest.raises(ValidationError, match="sorted.*unique"):
        module.IndexProjectionPoint.model_validate(
            {
                **paper_payload,
                "eligibility_limitations": ("z-last", "a-first", "a-first"),
            }
        )

    changed_content = paper_point.embedded_content + " Changed."
    mutation_matrix: tuple[tuple[str, dict[str, Any]], ...] = (
        (
            "eligibility_decision_id",
            {"eligibility_decision_id": "path-decision:s7j-mutated"},
        ),
        ("eligibility_outcome", {"eligibility_outcome": "limited"}),
        (
            "eligibility_limitations",
            {"eligibility_limitations": ("different_visible_limitation",)},
        ),
        ("canonical_object_id", {"canonical_object_id": "paper-ada-mutated"}),
        ("domain", {"domain": "company"}),
        (
            "projection_scope",
            {
                "projection_scope": "internal_auxiliary",
                "domain": None,
                "reference_type": "person",
                "eligibility_decision_id": None,
                "eligibility_outcome": "admitted",
                "eligibility_limitations": (),
            },
        ),
        ("projection_view", {"projection_view": "research"}),
        ("projection_version", {"projection_version": "s7j-mutated-version"}),
        ("schema_version", {"schema_version": "s7j-mutated-schema"}),
        ("embedding_model", {"embedding_model": "s7j-mutated-embedding"}),
        (
            "eligibility_policy_version",
            {"eligibility_policy_version": "s7j-mutated-policy"},
        ),
        (
            "embedded_content",
            {
                "embedded_content": changed_content,
                "embedded_content_sha256": hashlib.sha256(
                    changed_content.encode("utf-8")
                ).hexdigest(),
            },
        ),
        (
            "source_projection_content_sha256",
            {"source_projection_content_sha256": "f" * 64},
        ),
        (
            "source_evidence_ids",
            {
                "source_evidence_ids": tuple(
                    sorted(
                        {
                            *paper_point.source_evidence_ids,
                            "evidence:s7j-mutated",
                        }
                    )
                )
            },
        ),
    )
    original_manifest = next(
        item
        for item in result.expected_index_projections
        if item.projection_id == paper_point.projection_id
    )
    mutated_by_label: dict[str, Any] = {}
    for label, updates in mutation_matrix:
        mutated_point = module.IndexProjectionPoint.model_validate(
            {**paper_payload, **updates}
        )
        assert mutated_point.point_id == paper_point.point_id
        mutated_points = tuple(
            mutated_point if point.point_id == paper_point.point_id else point
            for point in result.points
        )
        mutated_manifests = module.build_index_projection_manifests(
            request=request,
            points=mutated_points,
            full_rebuild=True,
        )
        mutated_manifest = next(
            item
            for item in mutated_manifests
            if item.projection_id == paper_point.projection_id
        )
        assert mutated_manifest.content_sha256 != original_manifest.content_sha256
        mutated_by_label[label] = mutated_point

    eligibility_mutation = mutated_by_label["eligibility_limitations"]
    equal_mutated_points = tuple(
        eligibility_mutation if point.point_id == paper_point.point_id else point
        for point in result.points
    )
    built_manifests = result.expected_index_projections
    old_manifests = manifest.expected_index_projections
    assert tuple(sorted(built_manifests, key=lambda item: item.projection_id)) == tuple(
        sorted(old_manifests, key=lambda item: item.projection_id)
    )
    expected_points = equal_mutated_points
    actual_points = equal_mutated_points
    expected_manifests = old_manifests
    actual_manifests = old_manifests
    assert expected_points == actual_points
    assert expected_manifests == actual_manifests

    verification_store: dict[str, Any] = {}
    discrepancy_store: dict[str, tuple[Any, ...]] = {}
    publication = publication_module.create_ephemeral_release_publication(
        candidate_manifests={RELEASE_ID: manifest},
        actual_index_projections={RELEASE_ID: actual_manifests},
        expected_index_points={RELEASE_ID: expected_points},
        actual_index_points={RELEASE_ID: actual_points},
        active_release_state={
            "canonical_release_id": "accepted-bootstrap",
            "published_projection_release_id": "accepted-bootstrap",
            "index_release_id": "accepted-bootstrap",
        },
        verification_store=verification_store,
        discrepancy_store=discrepancy_store,
        publication_history=[],
        clock=lambda: NOW,
    )
    verification = publication.verify(RELEASE_ID)
    assert verification.accepted is False
    assert verification.canonical_index_parity is False
    assert (
        verification.missing_points,
        verification.extra_points,
        verification.stale_points,
        verification.cross_release_points,
    ) == (0, 0, 0, 0)
    assert discrepancy_store[RELEASE_ID] == ()
    assert verification_store[RELEASE_ID] == verification
    assert any(
        evidence_id.startswith("index-inventory:expected:")
        for evidence_id in verification.evidence_ids
    )
    assert any(
        evidence_id.startswith("index-inventory:actual:")
        for evidence_id in verification.evidence_ids
    )
    assert not any(
        evidence_id.startswith("index-manifest:")
        for evidence_id in verification.evidence_ids
    )


@pytest.fixture(scope="module")
def isolated_lookup_target_bundle(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, Any]:
    isolated = _isolated_index_projection_module()
    release_module = _isolated_release_publication_module()
    request, expected_result, manifest = _task7_7_release_values(
        release_module,
        release_id=RELEASE_ID,
        exact_limitation_identity_id="company-robotics",
        semantic_limitation_identity_id="paper-ada",
        candidate_bundle_factory=_resolved_person_technology_candidate_bundle,
    )
    repository_root = Path(__file__).resolve().parents[4]
    evidence_root = (
        repository_root / ".agents" / "runs" / "rebuild-canonical-v2-knowledge-platform"
    )
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    original_sha256 = _file_sha256(original_milvus)
    active_release_ids = {
        "canonical": "accepted-r0",
        "published": "accepted-r0",
        "index": "accepted-r0",
    }
    active_before = dict(active_release_ids)
    fixture_root = tmp_path_factory.mktemp("canonical-v2-s8l1")
    target = isolated.prepare_isolated_index_target(
        root=fixture_root / "canonical-v2-s7e-index",
        target_id="canonical-v2-s7e-fixture",
        release_id=RELEASE_ID,
        backup_gate_root=evidence_root,
        forbidden_milvus_paths=(original_milvus,),
    )
    builder = isolated.create_isolated_index_projection_builder(
        target=target,
        backup_gate_root=evidence_root,
        embedding_adapter=isolated.RecordedEmbeddingAdapter(
            model_id="recorded-embedding-v1",
            dimension=32,
        ),
        clock=lambda: NOW,
    )

    result = builder.build(request)
    receipt = builder.last_materialization_receipt
    assert result == expected_result
    assert receipt is not None
    bundle = release_module.IsolatedReleaseBundle(
        manifest=manifest,
        index_result=result,
        index_target=target,
    )
    target_hashes = {
        name: _file_sha256(target.root / name)
        for name in (
            ".canonical-v2-isolated-index-target.json",
            "lookup.sqlite3",
            "milvus.db",
        )
    }
    return {
        "target": target,
        "result": result,
        "receipt": receipt,
        "bundle": bundle,
        "index_request": request,
        "original_milvus": original_milvus,
        "original_sha256": original_sha256,
        "active_release_ids": active_release_ids,
        "active_before": active_before,
        "target_hashes": target_hashes,
    }


def test_index_projection_performs_full_readback_on_marked_isolated_target(
    isolated_lookup_target_bundle: dict[str, Any],
) -> None:
    isolated = _isolated_index_projection_module()
    target = isolated_lookup_target_bundle["target"]
    result = isolated_lookup_target_bundle["result"]
    receipt = isolated_lookup_target_bundle["receipt"]
    original_milvus = isolated_lookup_target_bundle["original_milvus"]
    original_sha256 = isolated_lookup_target_bundle["original_sha256"]
    active_release_ids = isolated_lookup_target_bundle["active_release_ids"]
    active_before = isolated_lookup_target_bundle["active_before"]

    assert receipt.release_id == RELEASE_ID
    assert receipt.target_id == "canonical-v2-s7e-fixture"
    assert receipt.target_kind == "isolated-candidate"
    assert receipt.vector_backend == "milvus-lite"
    assert receipt.lookup_backend == "sqlite"
    assert receipt.point_ids == tuple(sorted(item.point_id for item in result.points))
    assert receipt.lookup_document_ids == tuple(
        sorted(item.document_id for item in result.lookup_documents)
    )
    assert receipt.index_projections == result.expected_index_projections
    assert receipt.lookup_projections == result.expected_lookup_projections
    assert all(item.full_rebuild for item in receipt.index_projections)
    assert all(item.full_rebuild for item in receipt.lookup_projections)
    assert isolated.read_isolated_index_points(target) == result.points
    assert isolated.read_isolated_lookup_documents(target) == result.lookup_documents
    assert (target.root / "milvus.db").is_file()
    assert (target.root / "lookup.sqlite3").is_file()
    assert active_release_ids == active_before
    assert _file_sha256(original_milvus) == original_sha256


def test_release_scoped_exact_lookup_binds_physical_bundle_and_public_trace(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    exact_module = _isolated_knowledge_read_module()
    fixture = request.getfixturevalue("isolated_lookup_target_bundle")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    release_module = _isolated_release_publication_module()
    index_module = _index_projection_module()
    isolated = _isolated_index_projection_module()
    bundle = fixture["bundle"]
    published = contracts_module.PublishedRelease(
        release_id=RELEASE_ID,
        previous_release_id="accepted-before-s8l1",
        canonical_release_id=RELEASE_ID,
        published_projection_release_id=RELEASE_ID,
        index_release_id=RELEASE_ID,
        state="active",
        changed_at=NOW,
        verification_evidence_ids=("release-verification:s8l1",),
    )
    exact_requests: list[Any] = []
    exact_adapter = exact_module.create_isolated_exact_lookup_adapter(
        release_bundle=bundle,
        published_release=published,
    )

    def captured_exact_adapter(lane_request: Any) -> Any:
        exact_requests.append(lane_request)
        return exact_adapter(lane_request)

    service = read_module.create_ephemeral_knowledge_read(
        universal_web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=1,
        ),
        lane_adapters={"exact": captured_exact_adapter},
        web_search=lambda _: read_module.RetrievalLaneResult(),
        clock=lambda: NOW,
    )
    explicit_name = read_module.ProtectedSlot(
        kind="explicit_name",
        value="Robotics Co",
        raw_text="Robotics Co",
    )
    displayed_constraint = read_module.StructuredConstraints(
        displayed_entity_ids=("company-robotics",),
    )
    plan = read_module.RetrievalPlan(
        plan_id="retrieval-plan:s8l1-exact",
        plan_version="canonical-v2-s8l1-plan-v1",
        original_query="Please introduce Robotics Co",
        behavior_class="A",
        interaction_mode="information_retrieval",
        release_id=RELEASE_ID,
        as_of=NOW,
        domains=("company",),
        protected_slots=(explicit_name,),
        lanes=("exact",),
        max_candidates=1,
        web_required=True,
        web_policy=read_module.WebSearchPolicy(mode="disabled"),
        structured_constraints=displayed_constraint,
        lane_queries=(
            read_module.LaneQuery(
                lane="exact",
                release_id=RELEASE_ID,
                catalog_sha256=CATALOG_CONTENT_SHA256,
                pure_topic_text="Robotics Co",
                query_text="Robotics Co",
            ),
        ),
    )

    def plan_with_lane_queries(lane_queries: tuple[dict[str, Any], ...]) -> Any:
        payload = plan.model_dump(mode="json")
        payload["lane_queries"] = lane_queries
        payload["content_sha256"] = "0" * 64
        return read_module.RetrievalPlan.model_validate(payload)

    exact_lane_query = plan.lane_queries[0].model_dump(mode="json")
    with pytest.raises(ValidationError, match="unique lanes"):
        plan_with_lane_queries((exact_lane_query, exact_lane_query))
    with pytest.raises(ValidationError, match="another release"):
        plan_with_lane_queries(
            ({**exact_lane_query, "release_id": "cross-release-query"},)
        )
    with pytest.raises(ValidationError, match="does not belong"):
        plan_with_lane_queries(({**exact_lane_query, "lane": "lexical"},))

    evidence_set = service.execute(plan)

    assert len(exact_requests) == 1
    lane_request = exact_requests[0]
    assert lane_request.query_text == "Robotics Co"
    assert lane_request.query_view == "view:original"
    assert lane_request.domains == ("company",)
    assert lane_request.protected_slots == (explicit_name,)
    assert lane_request.structured_constraints == displayed_constraint
    assert lane_request.max_candidates == 1
    assert lane_request.release_id == RELEASE_ID
    assert len(evidence_set.fused_candidates) == 1
    fused = evidence_set.fused_candidates[0]
    assert fused.canonical_id == "company-robotics"
    assert fused.domain == "company"
    assert fused.display_name == "Robotics Co"
    assert fused.origin_lane == "exact"
    assert fused.raw_score == 1.0
    assert len(evidence_set.items) == 1
    item = evidence_set.items[0]
    company_document = next(
        document
        for document in bundle.index_result.lookup_documents
        if document.canonical_object_id == "company-robotics"
    )
    assert item.object_id == "company-robotics"
    assert item.domain == "company"
    assert item.lane == "exact"
    assert item.source_nature == "local"
    assert item.snippet == company_document.lookup_content
    assert item.score == 1.0
    assert item.claim_binding is not None
    assert item.claim_binding.subject_id == "company-robotics"
    assert item.claim_binding.predicate == "canonical_projection"
    assert item.claim_binding.value == company_document.lookup_content_sha256
    assert item.claim_binding.status == company_document.eligibility_outcome
    trace = item.local_projection_trace
    assert trace is not None
    assert trace.target_id == bundle.index_target.target_id
    assert trace.target_marker_sha256 == bundle.index_target.marker_sha256
    assert trace.manifest_sha256 == bundle.manifest.manifest_sha256
    assert trace.index_result_content_sha256 == bundle.index_result.content_sha256
    assert trace.document_id == company_document.document_id
    assert trace.canonical_object_id == "company-robotics"
    assert trace.release_id == RELEASE_ID
    assert trace.domain == "company"
    assert trace.projection_id == company_document.projection_id
    assert trace.eligibility_decision_id == company_document.eligibility_decision_id
    assert trace.eligibility_outcome == company_document.eligibility_outcome
    assert trace.eligibility_limitations == company_document.eligibility_limitations
    assert trace.source_evidence_ids == company_document.source_evidence_ids
    assert trace.lookup_content_sha256 == company_document.lookup_content_sha256
    assert item.evidence_id == trace.evidence_id
    assert fused.raw_candidate_ids == (trace.raw_candidate_id,)
    assert fused.evidence_ids == (trace.evidence_id,)
    assert fused.quality_flags == company_document.eligibility_limitations
    assert evidence_set.entity_handles == (
        read_module.CanonicalEntityHandle(
            canonical_id="company-robotics",
            domain="company",
            display_name="Robotics Co",
            evidence_ids=(trace.evidence_id,),
        ),
    )
    assert len(evidence_set.candidate_traces) == 1
    assert evidence_set.candidate_traces[0].raw_candidate_id == trace.raw_candidate_id
    assert evidence_set.candidate_traces[0].disposition == "selected"
    assert evidence_set.candidate_traces[0].selected_result_id == "company-robotics"

    raw_result = exact_adapter(lane_request)
    assert len(raw_result.candidates) == 1
    assert raw_result.candidates[0].origin_public_evidence_ids == (
        company_document.source_evidence_ids
    )
    assert raw_result.candidates[0].quality_flags == (
        company_document.eligibility_limitations
    )

    def lane_request_with(**updates: Any) -> Any:
        payload = lane_request.model_dump(mode="json")
        payload.update(updates)
        payload["content_sha256"] = "0" * 64
        return read_module.LaneRequest.model_validate(payload)

    no_lane_query_plan = plan_with_lane_queries(())
    no_lane_query_result = service.execute(no_lane_query_plan)
    assert no_lane_query_result.entity_handles[0].canonical_id == "company-robotics"
    assert exact_requests[-1].query_text == plan.original_query
    assert (
        len(
            exact_adapter(
                lane_request_with(query_text="Robotics Co [lane=exact]")
            ).candidates
        )
        == 1
    )

    identifier_request = lane_request_with(
        query_text="company-robotics",
        protected_slots=(
            read_module.ProtectedSlot(
                kind="exact_identifier",
                value="company-robotics",
                raw_text="company-robotics",
            ).model_dump(mode="json"),
        ),
    )
    assert len(exact_adapter(identifier_request).candidates) == 1
    assert (
        exact_adapter(
            lane_request_with(domains=("paper",), protected_slots=())
        ).candidates
        == ()
    )
    assert (
        exact_adapter(lane_request_with(domains=(), protected_slots=())).candidates
        == ()
    )
    assert exact_adapter(lane_request_with(max_candidates=0)).candidates == ()
    assert (
        exact_adapter(
            lane_request_with(
                structured_constraints=read_module.StructuredConstraints(
                    excluded_terms=("Robotics",),
                ).model_dump(mode="json"),
            )
        ).candidates
        == ()
    )
    assert (
        exact_adapter(
            lane_request_with(
                structured_constraints=read_module.StructuredConstraints(
                    excluded_terms=("Robotics route",),
                ).model_dump(mode="json"),
            )
        ).candidates
        == ()
    )

    paper_request = lane_request_with(
        query_text="Evidence-bound robotics",
        domains=("paper",),
        protected_slots=(
            read_module.ProtectedSlot(
                kind="explicit_name",
                value="Evidence-bound robotics",
                raw_text="Evidence-bound robotics",
            ).model_dump(mode="json"),
        ),
        structured_constraints=read_module.StructuredConstraints().model_dump(
            mode="json"
        ),
    )
    paper_result = exact_adapter(paper_request)
    assert len(paper_result.candidates) == 1
    cross_domain_service = read_module.create_ephemeral_knowledge_read(
        universal_web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=1,
        ),
        lane_adapters={"exact": lambda _: paper_result},
        web_search=lambda _: read_module.RetrievalLaneResult(),
        clock=lambda: NOW,
    )
    cross_domain_evidence = cross_domain_service.execute(plan)
    assert cross_domain_evidence.items == ()
    assert cross_domain_evidence.entity_handles == ()
    exact_cross_domain_trace = next(
        trace for trace in cross_domain_evidence.traces if trace.lane == "exact"
    )
    assert exact_cross_domain_trace.status == "unavailable"
    assert exact_cross_domain_trace.failure_kind == "invalid_output"

    internal_id = next(
        document.canonical_object_id
        for document in bundle.index_result.lookup_documents
        if document.projection_scope.value == "internal_auxiliary"
    )
    assert (
        exact_adapter(
            lane_request_with(
                query_text=internal_id,
                domains=("professor",),
                protected_slots=(),
                structured_constraints=read_module.StructuredConstraints().model_dump(
                    mode="json"
                ),
            )
        ).candidates
        == ()
    )
    with pytest.raises(ValueError, match="request release"):
        exact_adapter(lane_request_with(release_id="cross-release-request"))

    rolled_back = published.model_copy(
        update={"state": contracts_module.ReleaseState.rolled_back}
    )
    rolled_back_adapter = exact_module.create_isolated_exact_lookup_adapter(
        release_bundle=bundle,
        published_release=rolled_back,
    )
    assert len(rolled_back_adapter(lane_request).candidates) == 1

    wrong_release = published.model_copy(
        update={
            "release_id": "cross-release-r0",
            "canonical_release_id": "cross-release-r0",
            "published_projection_release_id": "cross-release-r0",
            "index_release_id": "cross-release-r0",
        }
    )
    unmarked_root = tmp_path / "unmarked-read-target"
    unmarked_root.mkdir()
    unmarked_target = bundle.index_target.model_copy(update={"root": unmarked_root})
    unmarked_bundle = release_module.IsolatedReleaseBundle(
        manifest=bundle.manifest,
        index_result=bundle.index_result,
        index_target=unmarked_target,
    )
    with pytest.raises(ValueError, match="published release.*bundle"):
        exact_module.create_isolated_exact_lookup_adapter(
            release_bundle=unmarked_bundle,
            published_release=wrong_release,
        )
    assert not (unmarked_root / "lookup.sqlite3").exists()
    assert not (unmarked_root / "milvus.db").exists()

    hostile_values = published.model_dump(mode="python")
    hostile_values["index_release_id"] = "hostile-cross-release"
    hostile_publication = contracts_module.PublishedRelease.model_construct(
        **hostile_values
    )
    with pytest.raises(ValidationError, match="same release"):
        exact_module.create_isolated_exact_lookup_adapter(
            release_bundle=bundle,
            published_release=hostile_publication,
        )

    unmarked_adapter = exact_module.create_isolated_exact_lookup_adapter(
        release_bundle=unmarked_bundle,
        published_release=published,
    )
    with pytest.raises(isolated.IsolatedIndexTargetSafetyError, match="marker"):
        unmarked_adapter(lane_request)
    assert not (unmarked_root / "lookup.sqlite3").exists()
    assert not (unmarked_root / "milvus.db").exists()

    reduced_documents = tuple(
        document
        for document in bundle.index_result.lookup_documents
        if document.canonical_object_id != "company-robotics"
    )
    mismatched_payload = bundle.index_result.model_dump(mode="json")
    mismatched_payload["lookup_documents"] = [
        document.model_dump(mode="json") for document in reduced_documents
    ]
    mismatched_payload["content_sha256"] = hashlib.sha256(
        json.dumps(
            {
                key: value
                for key, value in mismatched_payload.items()
                if key != "content_sha256"
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    mismatched_result = index_module.IndexProjectionResult.model_validate(
        mismatched_payload
    )
    mismatched_bundle = release_module.IsolatedReleaseBundle(
        manifest=bundle.manifest,
        index_result=mismatched_result,
        index_target=bundle.index_target,
    )
    mismatched_adapter = exact_module.create_isolated_exact_lookup_adapter(
        release_bundle=mismatched_bundle,
        published_release=published,
    )
    with pytest.raises(
        index_module.IndexProjectionIntegrityError,
        match="physical lookup.*bundle",
    ):
        mismatched_adapter(lane_request)

    assert isolated.read_isolated_lookup_documents(bundle.index_target) == (
        bundle.index_result.lookup_documents
    )
    assert {
        name: _file_sha256(bundle.index_target.root / name)
        for name in fixture["target_hashes"]
    } == fixture["target_hashes"]
    assert _file_sha256(fixture["original_milvus"]) == fixture["original_sha256"]


def test_s8v1_release_scoped_vector_recall_uses_audited_physical_points_and_trace(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vector_factory = _isolated_vector_recall_factory()
    fixture = request.getfixturevalue("isolated_lookup_target_bundle")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    index_module = _index_projection_module()
    isolated_index_module = _isolated_index_projection_module()
    release_module = _isolated_release_publication_module()
    isolated_read_module = _isolated_knowledge_read_module()
    bundle = fixture["bundle"]
    published = _s8p1_published_release(contracts_module, release_id=RELEASE_ID)
    embedding_adapter = isolated_index_module.RecordedEmbeddingAdapter(
        model_id="recorded-embedding-v1",
        dimension=32,
    )
    paper_point = next(
        point
        for point in bundle.index_result.points
        if point.canonical_object_id == "paper-ada"
        and point.projection_view.value == "default"
    )

    vector_adapter = vector_factory(
        release_bundle=bundle,
        published_release=published,
        embedding_adapter=embedding_adapter,
    )
    vector_request = read_module.LaneRequest(
        lane="vector",
        release_id=RELEASE_ID,
        query_view="view:original",
        original_query="semantic evidence-bound robotics paper",
        behavior_class="G",
        interaction_mode="information_retrieval",
        web_policy=read_module.WebSearchPolicy(mode="disabled"),
        query_text=f"{paper_point.embedded_content} [lane=vector]",
        domains=("paper",),
        protected_slots=(),
        structured_constraints=read_module.StructuredConstraints(),
        max_candidates=2,
    )
    direct = vector_adapter(vector_request)
    assert direct.candidates
    candidate = direct.candidates[0]
    assert candidate.canonical_id == "paper-ada"
    assert candidate.domain == "paper"
    assert candidate.lane == "vector"
    assert candidate.adapter_version == "canonical-v2-isolated-vector-recall-v1"
    assert candidate.raw_score == pytest.approx(1.0)
    assert candidate.quality_flags == ("profile_incomplete",)
    assert len(candidate.evidence) == 1
    vector_item = candidate.evidence[0]
    vector_trace = vector_item.local_projection_trace
    assert isinstance(vector_trace, read_module.LocalVectorTrace)
    assert vector_trace.path == "semantic_recall"
    assert vector_trace.execution_lane == "vector"
    assert vector_trace.point_id == paper_point.point_id
    assert vector_trace.canonical_object_id == "paper-ada"
    assert vector_trace.release_id == RELEASE_ID
    assert vector_trace.domain == "paper"
    assert vector_trace.projection_id == paper_point.projection_id
    assert vector_trace.projection_view == paper_point.projection_view.value
    assert vector_trace.projection_version == paper_point.projection_version
    assert vector_trace.schema_version == paper_point.schema_version
    assert vector_trace.embedding_model == paper_point.embedding_model
    assert (
        vector_trace.eligibility_policy_version
        == paper_point.eligibility_policy_version
    )
    assert vector_trace.eligibility_decision_id == paper_point.eligibility_decision_id
    assert vector_trace.eligibility_outcome == paper_point.eligibility_outcome
    assert vector_trace.eligibility_limitations == paper_point.eligibility_limitations
    assert (
        vector_trace.source_projection_content_sha256
        == paper_point.source_projection_content_sha256
    )
    assert vector_trace.embedded_content_sha256 == paper_point.embedded_content_sha256
    assert vector_trace.source_evidence_ids == paper_point.source_evidence_ids
    assert vector_trace.target_id == bundle.index_target.target_id
    assert vector_trace.target_marker_sha256 == bundle.index_target.marker_sha256
    assert vector_trace.manifest_sha256 == bundle.manifest.manifest_sha256
    assert (
        vector_trace.index_result_content_sha256 == bundle.index_result.content_sha256
    )
    assert vector_trace.publication_verification_evidence_ids == tuple(
        sorted(published.verification_evidence_ids)
    )
    assert (
        vector_trace.lane_query_text_sha256
        == hashlib.sha256(vector_request.query_text.encode("utf-8")).hexdigest()
    )
    query_vector = embedding_adapter.embed_batch((paper_point.embedded_content,))[0]
    assert vector_trace.query_embedding_sha256 == _canonical_json_sha256(query_vector)
    assert vector_trace.similarity_score == pytest.approx(1.0)
    assert vector_item.evidence_id == vector_trace.evidence_id
    assert candidate.raw_candidate_id == vector_trace.raw_candidate_id
    assert vector_item.object_id == "paper-ada"
    assert vector_item.domain == "paper"
    assert vector_item.lane == "vector"
    assert vector_item.source_nature == "local"
    assert vector_item.source_authority == "canonical_release"
    assert vector_item.source_locator == (
        f"canonical-v2-isolated:{bundle.index_target.target_id}:{paper_point.point_id}"
    )
    assert vector_item.snippet == paper_point.embedded_content
    assert vector_item.score == pytest.approx(1.0)
    assert vector_item.claim_binding is not None
    assert (
        vector_item.claim_binding.subject_id,
        vector_item.claim_binding.predicate,
        vector_item.claim_binding.value,
        vector_item.claim_binding.status,
    ) == (
        "paper-ada",
        "semantic_recall",
        paper_point.embedded_content_sha256,
        paper_point.eligibility_outcome,
    )
    vector_lineage = vector_trace.model_dump(
        mode="json",
        exclude={"raw_candidate_id", "evidence_id", "content_sha256"},
    )
    assert vector_trace.raw_candidate_id == (
        f"local-vector-candidate:sha256:{_canonical_json_sha256(vector_lineage)}"
    )
    assert vector_trace.evidence_id == (
        "local-vector-evidence:sha256:"
        f"{_canonical_json_sha256((vector_lineage, vector_trace.raw_candidate_id))}"
    )
    assert vector_trace.content_sha256 == _canonical_json_sha256(
        vector_trace.model_dump(mode="json", exclude={"content_sha256"})
    )

    paper_title = json.loads(paper_point.embedded_content)["title"]
    planning_request = read_module.QueryPlanningRequest(
        request_id="query-request:s8v1-vector",
        release_id=RELEASE_ID,
        original_query=f"请核对已展示的“{paper_title}”",
        as_of=NOW,
        displayed_entity_ids=("paper-ada",),
    )

    def proposal_provider(value: Any) -> Any:
        assert value == planning_request
        return read_module.RecordedPlanningProposal(
            proposal_id="planning-proposal:s8v1-vector",
            request_sha256=value.content_sha256,
            schema_version="retrieval-plan-proposal-v1",
            model_id="recorded-planner-s8v1",
            prompt_version="query-plan-prompt-v1",
            behavior_class="G",
            interaction_mode="information_retrieval",
            domains=("paper",),
            lanes=("exact", "vector", "web"),
            max_candidates=1,
            max_provider_calls=1,
            web_mode="universal",
            max_web_results=1,
        )

    plan = _isolated_release_query_planner_factory()(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=fixture["index_request"],
        release_institution_catalog=_s8p1_institution_catalog(read_module),
        planning_policy=_s8p1_planning_policy(read_module),
        proposal_provider=proposal_provider,
    ).plan(planning_request)
    assert plan.lanes == ("exact", "vector", "web")
    service = _isolated_release_knowledge_read_factory()(
        release_bundle=bundle,
        published_release=published,
        universal_web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=1,
        ),
        web_search=lambda _: read_module.RetrievalLaneResult(),
        web_snapshot_policy=read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8v1",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        embedding_adapter=embedding_adapter,
        clock=lambda: NOW,
    )
    composed = service.execute(plan)
    assert {trace.lane for trace in composed.traces} == {"exact", "vector", "web"}
    assert all(trace.status == "succeeded" for trace in composed.traces)
    assert len(composed.fused_candidates) == 1
    fused = composed.fused_candidates[0]
    assert fused.canonical_id == "paper-ada"
    assert {item.lane for item in fused.evidence} == {"exact", "vector"}
    assert len(fused.raw_candidate_ids) == 2
    assert len(set(fused.raw_candidate_ids)) == 2
    assert len(fused.evidence_ids) == 2
    assert len(set(fused.evidence_ids)) == 2
    exact_item = next(item for item in fused.evidence if item.lane == "exact")
    assert exact_item.local_projection_trace is not None
    assert exact_item.local_projection_trace.path == "exact_lookup"
    assert "local_vector_trace" not in exact_item.model_dump(mode="json")
    assert (
        read_module.EvidenceItem.model_validate(exact_item.model_dump(mode="json"))
        == exact_item
    )

    captured_vector_requests: list[Any] = []
    captured_vector_results: list[Any] = []

    def capture_vector(lane_request: Any) -> Any:
        lane_result = vector_adapter(lane_request)
        captured_vector_requests.append(lane_request)
        captured_vector_results.append(lane_result)
        return lane_result

    capture_result = read_module.create_ephemeral_knowledge_read(
        universal_web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=1,
        ),
        lane_adapters={"vector": capture_vector},
        web_search=lambda _: read_module.RetrievalLaneResult(),
        clock=lambda: NOW,
    ).execute(plan)
    assert captured_vector_requests
    assert next(
        trace for trace in capture_result.traces if trace.lane == "vector"
    ).status == ("succeeded")
    trusted_candidate = captured_vector_results[0].candidates[0]
    trusted_item = trusted_candidate.evidence[0]
    trusted_trace = trusted_item.local_projection_trace
    assert isinstance(trusted_trace, read_module.LocalVectorTrace)

    def vector_trace_with(**updates: Any) -> Any:
        payload = trusted_trace.model_dump(mode="json")
        payload.update(updates)
        payload.update(
            raw_candidate_id="",
            evidence_id="",
            content_sha256="0" * 64,
        )
        return read_module.LocalVectorTrace.model_validate(payload)

    def hostile_candidate(
        trace: Any,
        *,
        item_updates: dict[str, Any] | None = None,
        candidate_updates: dict[str, Any] | None = None,
    ) -> Any:
        item_payload = trusted_item.model_dump(mode="json")
        item_payload.update(
            evidence_id=trace.evidence_id,
            local_projection_trace=trace.model_dump(mode="json"),
        )
        item_payload.update(item_updates or {})
        item = read_module.EvidenceItem.model_validate(item_payload)
        candidate_payload = trusted_candidate.model_dump(mode="json")
        candidate_payload.update(
            raw_candidate_id=trace.raw_candidate_id,
            raw_score=item.score,
            evidence=[item.model_dump(mode="json")],
        )
        candidate_payload.update(candidate_updates or {})
        return read_module.RecallCandidate.model_validate(candidate_payload)

    exact_trace = exact_item.local_projection_trace
    assert isinstance(exact_trace, read_module.LocalProjectionTrace)
    path_payload = trusted_candidate.model_dump(mode="json")
    path_payload.update(
        raw_candidate_id=exact_trace.raw_candidate_id,
        raw_score=exact_item.score,
        evidence=[exact_item.model_dump(mode="json")],
    )
    hostile_results = (
        read_module.RetrievalLaneResult(
            candidates=(read_module.RecallCandidate.model_validate(path_payload),)
        ),
        read_module.RetrievalLaneResult(
            candidates=(
                hostile_candidate(
                    trusted_trace,
                    item_updates={"lane": "exact"},
                ),
            )
        ),
        read_module.RetrievalLaneResult(
            candidates=(
                hostile_candidate(vector_trace_with(embedded_content_sha256="0" * 64)),
            )
        ),
        read_module.RetrievalLaneResult(
            candidates=(
                hostile_candidate(vector_trace_with(lane_query_text_sha256="0" * 64)),
            )
        ),
        read_module.RetrievalLaneResult(
            candidates=(hostile_candidate(vector_trace_with(similarity_score=0.5)),)
        ),
        read_module.RetrievalLaneResult(
            candidates=(
                hostile_candidate(
                    trusted_trace,
                    candidate_updates={"raw_candidate_id": "hostile-raw-id"},
                ),
            )
        ),
        read_module.RetrievalLaneResult(
            candidates=(
                hostile_candidate(
                    trusted_trace,
                    item_updates={"evidence_id": "hostile-evidence-id"},
                ),
            )
        ),
        read_module.RetrievalLaneResult(
            candidates=(
                hostile_candidate(
                    trusted_trace,
                    item_updates={"source_locator": "hostile-vector-locator"},
                ),
            )
        ),
    )
    for hostile_result in hostile_results:
        rejected = read_module.create_ephemeral_knowledge_read(
            universal_web_policy=read_module.WebSearchPolicy(
                mode="universal",
                max_provider_calls=1,
                timeout_ms=1_000,
                max_results=1,
            ),
            lane_adapters={"vector": lambda _, value=hostile_result: value},
            web_search=lambda _: read_module.RetrievalLaneResult(),
            clock=lambda: NOW,
        ).execute(plan)
        rejected_trace = next(
            trace for trace in rejected.traces if trace.lane == "vector"
        )
        assert (rejected_trace.status, rejected_trace.failure_kind) == (
            "unavailable",
            "invalid_output",
        )
        assert not any(item.lane == "vector" for item in rejected.items)
        assert not any(
            candidate.origin_lane == "vector" for candidate in rejected.fused_candidates
        )

    opaque_hostile_results = (
        read_module.RetrievalLaneResult(
            candidates=(
                hostile_candidate(vector_trace_with(query_embedding_sha256="0" * 64)),
            )
        ),
        read_module.RetrievalLaneResult(
            candidates=(
                hostile_candidate(
                    vector_trace_with(source_projection_content_sha256="0" * 64)
                ),
            )
        ),
        read_module.RetrievalLaneResult(
            candidates=(
                hostile_candidate(
                    vector_trace_with(similarity_score=0.5),
                    item_updates={"score": 0.5},
                ),
            )
        ),
    )
    original_vector_factory = isolated_read_module.create_isolated_vector_recall_adapter
    try:
        for hostile_result in opaque_hostile_results:
            monkeypatch.setattr(
                isolated_read_module,
                "create_isolated_vector_recall_adapter",
                lambda **kwargs: lambda lane_request, value=hostile_result: value,
            )
            hostile_release_service = _isolated_release_knowledge_read_factory()(
                release_bundle=bundle,
                published_release=published,
                universal_web_policy=read_module.WebSearchPolicy(
                    mode="universal",
                    max_provider_calls=1,
                    timeout_ms=1_000,
                    max_results=1,
                ),
                web_search=lambda _: read_module.RetrievalLaneResult(),
                web_snapshot_policy=read_module.WebSnapshotPolicy(
                    policy_id="web-snapshot-policy:s8v1-hostile-trace",
                    policy_version="web-snapshot-policy-v1",
                    max_bytes=8_192,
                ),
                embedding_adapter=embedding_adapter,
                clock=lambda: NOW,
            )
            with pytest.raises(
                isolated_read_module.IsolatedKnowledgeReadIntegrityError,
                match="vector.*trace|trace.*vector",
            ):
                hostile_release_service.execute(plan)
    finally:
        monkeypatch.setattr(
            isolated_read_module,
            "create_isolated_vector_recall_adapter",
            original_vector_factory,
        )

    def request_with(**updates: Any) -> Any:
        payload = vector_request.model_dump(mode="json")
        payload.update(updates)
        payload["content_sha256"] = "0" * 64
        return read_module.LaneRequest.model_validate(payload)

    assert vector_adapter(vector_request) == vector_adapter(vector_request)
    assert len(vector_adapter(request_with(max_candidates=1)).candidates) == 1
    displayed = vector_adapter(
        request_with(
            structured_constraints=read_module.StructuredConstraints(
                displayed_entity_ids=("paper-ada",),
            ).model_dump(mode="json")
        )
    )
    assert tuple(item.canonical_id for item in displayed.candidates) == ("paper-ada",)
    assert (
        vector_adapter(
            request_with(
                structured_constraints=read_module.StructuredConstraints(
                    displayed_entity_ids=("paper-ada",),
                    excluded_terms=("robotics",),
                ).model_dump(mode="json")
            )
        ).candidates
        == ()
    )
    company_only = vector_adapter(request_with(domains=("company",), max_candidates=2))
    assert company_only.candidates
    assert all(item.domain == "company" for item in company_only.candidates)
    internal_point = next(
        point
        for point in bundle.index_result.points
        if point.projection_scope.value == "internal_auxiliary"
    )
    internal_attempt = vector_adapter(
        request_with(
            query_text=f"{internal_point.embedded_content} [lane=vector]",
            domains=("company", "paper", "patent"),
            structured_constraints=read_module.StructuredConstraints().model_dump(
                mode="json"
            ),
        )
    )
    assert all(
        item.canonical_id != internal_point.canonical_object_id
        for item in internal_attempt.candidates
    )
    assert all(item.domain in PUBLIC_DOMAINS for item in internal_attempt.candidates)

    company_point = next(
        point
        for point in bundle.index_result.points
        if point.canonical_object_id == "company-robotics"
    )
    patent_point = next(
        point
        for point in bundle.index_result.points
        if point.canonical_object_id == "patent-ada"
    )

    def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        left_norm = sum(value * value for value in left) ** 0.5
        right_norm = sum(value * value for value in right) ** 0.5
        return sum(a * b for a, b in zip(left, right, strict=True)) / (
            left_norm * right_norm
        )

    company_vector, patent_vector = embedding_adapter.embed_batch(
        (company_point.embedded_content, patent_point.embedded_content)
    )
    tie_query = ""
    for index in range(10_000):
        candidate_query = f"s8v1tie{index}"
        candidate_vector = embedding_adapter.embed_batch((candidate_query,))[0]
        if cosine(candidate_vector, company_vector) == cosine(
            candidate_vector, patent_vector
        ):
            tie_query = candidate_query
            break
    assert tie_query
    tied = vector_adapter(
        request_with(
            query_text=f"{tie_query} [lane=vector]",
            domains=("company", "patent"),
            structured_constraints=read_module.StructuredConstraints(
                displayed_entity_ids=("company-robotics", "patent-ada"),
            ).model_dump(mode="json"),
            max_candidates=2,
        )
    )
    assert tuple(item.canonical_id for item in tied.candidates) == (
        "company-robotics",
        "patent-ada",
    )
    assert tied.candidates[0].raw_score == pytest.approx(tied.candidates[1].raw_score)

    class ProbeEmbeddingAdapter:
        def __init__(
            self,
            mode: str = "valid",
            *,
            model_id: str = "recorded-embedding-v1",
            dimension: int | bool = 32,
        ) -> None:
            self.model_id = model_id
            self.dimension = dimension
            self.mode = mode
            self.calls: list[tuple[str, ...]] = []
            self.counts: dict[str, int] = {}

        def embed_batch(self, texts: tuple[str, ...]) -> tuple[Any, ...]:
            self.calls.append(texts)
            if self.mode == "exception":
                raise RuntimeError("hostile embedding exception")
            vectors: tuple[Any, ...] = embedding_adapter.embed_batch(texts)
            if self.mode == "cardinality":
                return vectors[:-1]
            if not vectors:
                return vectors
            first = list(vectors[0])
            if self.mode == "dimension":
                first = first[:-1]
            elif self.mode == "boolean":
                first[0] = True
            elif self.mode == "nonnumeric":
                first[0] = "not-a-number"
            elif self.mode == "nonfinite":
                first[0] = float("nan")
            elif self.mode == "zero":
                first = [0.0] * len(first)
            changed = (tuple(first), *vectors[1:])
            if self.mode == "model_drift":
                self.model_id = "drifted-recorded-embedding-v1"
                return changed
            if self.mode == "dimension_drift":
                self.dimension = 31
                return changed
            if self.mode != "nondeterministic":
                return changed
            drifted: list[tuple[float, ...]] = []
            for text, vector in zip(texts, vectors, strict=True):
                count = self.counts.get(text, 0)
                self.counts[text] = count + 1
                if count:
                    shifted = tuple((*vector[1:], vector[0]))
                    drifted.append(shifted)
                else:
                    drifted.append(vector)
            return tuple(drifted)

    original_audit = isolated_read_module.audit_isolated_index_snapshot
    audit_attempts: list[Path] = []

    def unexpected_audit(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        audit_attempts.append(bundle.index_target.root)
        raise AssertionError("invalid vector request must fail before physical audit")

    monkeypatch.setattr(
        isolated_read_module,
        "audit_isolated_index_snapshot",
        unexpected_audit,
    )
    pre_effect_adapter = ProbeEmbeddingAdapter()
    pre_effect_vector = vector_factory(
        release_bundle=bundle,
        published_release=published,
        embedding_adapter=pre_effect_adapter,
    )
    with pytest.raises(ValueError, match="vector"):
        pre_effect_vector(request_with(lane="lexical"))
    with pytest.raises(ValueError, match="release"):
        pre_effect_vector(request_with(release_id="cross-release-s8v1"))
    with pytest.raises(ValueError, match="non-public"):
        pre_effect_vector(request_with(domains=("person",)))
    with pytest.raises(Exception, match="Professor|professor"):
        pre_effect_vector(request_with(domains=("professor",)))
    assert pre_effect_vector(request_with(query_text=" [lane=vector]")).candidates == ()
    assert pre_effect_vector(request_with(max_candidates=0)).candidates == ()
    assert pre_effect_adapter.calls == []
    assert audit_attempts == []
    with pytest.raises(Exception, match="model"):
        vector_factory(
            release_bundle=bundle,
            published_release=published,
            embedding_adapter=ProbeEmbeddingAdapter(model_id="wrong-model"),
        )
    for invalid_dimension in (0, True):
        with pytest.raises(Exception, match="dimension"):
            vector_factory(
                release_bundle=bundle,
                published_release=published,
                embedding_adapter=ProbeEmbeddingAdapter(dimension=invalid_dimension),
            )
    assert audit_attempts == []
    blocked_web: list[Any] = []
    service_without_embedding = _isolated_release_knowledge_read_factory()(
        release_bundle=bundle,
        published_release=published,
        universal_web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=1,
        ),
        web_search=lambda value: blocked_web.append(value),
        web_snapshot_policy=read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8v1-no-vector",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        clock=lambda: NOW,
    )
    with pytest.raises(Exception, match="unsupported lane"):
        service_without_embedding.execute(plan)
    assert blocked_web == []
    assert audit_attempts == []
    monkeypatch.setattr(
        isolated_read_module,
        "audit_isolated_index_snapshot",
        original_audit,
    )

    integrity_error = isolated_read_module.IsolatedKnowledgeReadIntegrityError
    for mode in (
        "exception",
        "cardinality",
        "dimension",
        "boolean",
        "nonnumeric",
        "nonfinite",
        "zero",
        "model_drift",
        "dimension_drift",
        "nondeterministic",
    ):
        hostile = vector_factory(
            release_bundle=bundle,
            published_release=published,
            embedding_adapter=ProbeEmbeddingAdapter(mode),
        )
        with pytest.raises(integrity_error, match="embedding"):
            hostile(vector_request)

    dimension_mismatch = vector_factory(
        release_bundle=bundle,
        published_release=published,
        embedding_adapter=ProbeEmbeddingAdapter(dimension=31),
    )
    with pytest.raises(Exception, match="dimension|vector"):
        dimension_mismatch(vector_request)

    real_snapshot = isolated_index_module.audit_isolated_index_snapshot(
        bundle.index_target,
        embedding_adapter=embedding_adapter,
    )

    monkeypatch.setattr(
        isolated_read_module,
        "audit_isolated_index_snapshot",
        lambda *args, **kwargs: real_snapshot,
    )
    for mode in (
        "exception",
        "cardinality",
        "dimension",
        "boolean",
        "nonnumeric",
        "nonfinite",
        "zero",
        "model_drift",
        "dimension_drift",
    ):
        hostile_query_batch = vector_factory(
            release_bundle=bundle,
            published_release=published,
            embedding_adapter=ProbeEmbeddingAdapter(mode),
        )
        with pytest.raises(integrity_error, match="embedding"):
            hostile_query_batch(vector_request)

    def receipt_with(**updates: Any) -> Any:
        payload = real_snapshot.receipt.model_dump(mode="json")
        payload.update(
            {
                key: [
                    item.model_dump(mode="json")
                    if hasattr(item, "model_dump")
                    else item
                    for item in value
                ]
                if isinstance(value, tuple)
                else value
                for key, value in updates.items()
            }
        )
        payload["content_sha256"] = _canonical_json_sha256(
            {key: value for key, value in payload.items() if key != "content_sha256"}
        )
        return index_module.IndexProjectionMaterializationReceipt.model_validate(
            payload
        )

    changed_index_manifests = list(real_snapshot.receipt.index_projections)
    changed_index_manifests[0] = changed_index_manifests[0].model_copy(
        update={"content_sha256": "0" * 64}
    )
    changed_lookup_manifests = list(real_snapshot.receipt.lookup_projections)
    changed_lookup_manifests[0] = changed_lookup_manifests[0].model_copy(
        update={"content_sha256": "1" * 64}
    )
    extra_point = real_snapshot.points[0].model_copy(
        update={"point_id": "index-point:s8v1-extra"}
    )
    cross_release_point = real_snapshot.points[0].model_copy(
        update={"release_id": "cross-release-s8v1-snapshot"}
    )
    snapshot_variants = (
        real_snapshot.model_copy(
            update={"receipt": receipt_with(target_id="isolated-target:s8v1-hostile")}
        ),
        real_snapshot.model_copy(
            update={
                "receipt": receipt_with(point_ids=real_snapshot.receipt.point_ids[:-1])
            }
        ),
        real_snapshot.model_copy(
            update={
                "receipt": receipt_with(
                    lookup_document_ids=(real_snapshot.receipt.lookup_document_ids[:-1])
                )
            }
        ),
        real_snapshot.model_copy(
            update={
                "receipt": receipt_with(
                    index_projections=tuple(changed_index_manifests)
                )
            }
        ),
        real_snapshot.model_copy(
            update={
                "receipt": receipt_with(
                    lookup_projections=tuple(changed_lookup_manifests)
                )
            }
        ),
        real_snapshot.model_copy(update={"points": real_snapshot.points[:-1]}),
        real_snapshot.model_copy(
            update={"points": (*real_snapshot.points, extra_point)}
        ),
        real_snapshot.model_copy(
            update={"points": (cross_release_point, *real_snapshot.points[1:])}
        ),
        real_snapshot.model_copy(
            update={"lookup_documents": real_snapshot.lookup_documents[:-1]}
        ),
    )
    for hostile_snapshot in snapshot_variants:
        monkeypatch.setattr(
            isolated_read_module,
            "audit_isolated_index_snapshot",
            lambda *args, value=hostile_snapshot, **kwargs: value,
        )
        with pytest.raises(Exception, match="snapshot|bundle|receipt|physical"):
            vector_adapter(vector_request)

    def stored_vector_mismatch(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise index_module.IndexProjectionIntegrityError(
            "isolated Milvus vector differs from deterministic embedding"
        )

    monkeypatch.setattr(
        isolated_read_module,
        "audit_isolated_index_snapshot",
        stored_vector_mismatch,
    )
    with pytest.raises(index_module.IndexProjectionIntegrityError, match="vector"):
        vector_adapter(vector_request)
    monkeypatch.setattr(
        isolated_read_module,
        "audit_isolated_index_snapshot",
        lambda *args, **kwargs: real_snapshot,
    )

    def bundle_with_index_payload(payload: dict[str, Any]) -> Any:
        payload["content_sha256"] = _canonical_json_sha256(
            {key: value for key, value in payload.items() if key != "content_sha256"}
        )
        return release_module.IsolatedReleaseBundle(
            manifest=bundle.manifest,
            index_result=index_module.IndexProjectionResult.model_validate(payload),
            index_target=bundle.index_target,
        )

    reduced_points_payload = bundle.index_result.model_dump(mode="json")
    reduced_points_payload["points"] = reduced_points_payload["points"][:-1]
    reduced_documents_payload = bundle.index_result.model_dump(mode="json")
    reduced_documents_payload["lookup_documents"] = reduced_documents_payload[
        "lookup_documents"
    ][:-1]
    for mismatched_bundle in (
        bundle_with_index_payload(reduced_points_payload),
        bundle_with_index_payload(reduced_documents_payload),
    ):
        mismatched_vector = vector_factory(
            release_bundle=mismatched_bundle,
            published_release=published,
            embedding_adapter=embedding_adapter,
        )
        with pytest.raises(Exception, match="snapshot|bundle|physical"):
            mismatched_vector(vector_request)

    monkeypatch.setattr(
        isolated_read_module,
        "audit_isolated_index_snapshot",
        original_audit,
    )
    rolled_back_vector = vector_factory(
        release_bundle=bundle,
        published_release=published.model_copy(
            update={"state": contracts_module.ReleaseState.rolled_back}
        ),
        embedding_adapter=embedding_adapter,
    )
    assert rolled_back_vector(vector_request).candidates

    unmarked_root = tmp_path / "s8v1-unmarked-target"
    unmarked_root.mkdir()
    unmarked_bundle = release_module.IsolatedReleaseBundle(
        manifest=bundle.manifest,
        index_result=bundle.index_result,
        index_target=bundle.index_target.model_copy(update={"root": unmarked_root}),
    )
    unmarked_vector = vector_factory(
        release_bundle=unmarked_bundle,
        published_release=published,
        embedding_adapter=embedding_adapter,
    )
    assert unmarked_vector(request_with(query_text=" [lane=vector]")).candidates == ()
    with pytest.raises(
        isolated_index_module.IsolatedIndexTargetSafetyError,
        match="marker",
    ):
        unmarked_vector(vector_request)
    assert not (unmarked_root / "milvus.db").exists()
    assert not (unmarked_root / "lookup.sqlite3").exists()

    assert {
        name: _file_sha256(bundle.index_target.root / name)
        for name in fixture["target_hashes"]
    } == fixture["target_hashes"]
    assert _file_sha256(fixture["original_milvus"]) == fixture["original_sha256"]


def test_s8v2_absent_selector_preserves_literal_legacy_payloads_and_hashes() -> None:
    module = import_module("src.data_agents.canonical_v2.knowledge_read")
    proposal = module.RecordedPlanningProposal(
        proposal_id="planning-proposal:s8v2-legacy-baseline",
        request_sha256="a" * 64,
        schema_version="retrieval-plan-proposal-v1",
        model_id="recorded-planner-s8v2-baseline",
        prompt_version="query-plan-prompt-v1",
        behavior_class="B",
        interaction_mode="information_retrieval",
        domains=("paper",),
        lanes=("vector", "web"),
        max_candidates=2,
        max_provider_calls=1,
        web_mode="universal",
        max_web_results=2,
    )
    plan = module.RetrievalPlan(
        plan_id="retrieval-plan:s8v2-legacy-baseline",
        plan_version="retrieval-plan-v1",
        original_query="robotics papers",
        behavior_class="B",
        interaction_mode="information_retrieval",
        release_id="release:s8v2-baseline",
        as_of=datetime(2026, 7, 19, tzinfo=timezone.utc),
        domains=("paper",),
        protected_slots=(),
        lanes=("vector", "web"),
        max_candidates=2,
        web_required=True,
        web_policy=module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_500,
            max_results=2,
        ),
        freshness_material=True,
    )
    lane_request = module.LaneRequest(
        lane="vector",
        release_id="release:s8v2-baseline",
        query_view="view:original",
        original_query="robotics papers",
        behavior_class="B",
        interaction_mode="information_retrieval",
        web_policy=module.WebSearchPolicy(mode="disabled"),
        query_text="robotics papers [lane=vector]",
        domains=("paper",),
        protected_slots=(),
        structured_constraints=module.StructuredConstraints(),
        max_candidates=2,
    )

    assert proposal.model_dump_json() == (
        '{"content_sha256":"39c06fde7f7e1b7a4204a74ba8a433555a2d0acc29f05fe7c9811afb59f9bf4f",'
        '"proposal_id":"planning-proposal:s8v2-legacy-baseline",'
        '"request_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        '"schema_version":"retrieval-plan-proposal-v1",'
        '"model_id":"recorded-planner-s8v2-baseline",'
        '"prompt_version":"query-plan-prompt-v1","behavior_class":"B",'
        '"interaction_mode":"information_retrieval","domains":["paper"],'
        '"lanes":["vector","web"],"query_views":[],"relationship_paths":[],'
        '"max_candidates":2,"max_provider_calls":1,"enumeration_mode":null,'
        '"internal_reference_targets":[],"web_mode":"universal",'
        '"allowed_web_domains":[],"max_web_results":2}'
    )
    assert proposal.content_sha256 == (
        "39c06fde7f7e1b7a4204a74ba8a433555a2d0acc29f05fe7c9811afb59f9bf4f"
    )
    assert plan.model_dump_json() == (
        '{"content_sha256":"02903acca487b8b924c2ab2a2a22618fbb2ad236b544954941689a07f37c7c8b",'
        '"plan_id":"retrieval-plan:s8v2-legacy-baseline",'
        '"plan_version":"retrieval-plan-v1","request_sha256":null,'
        '"original_query":"robotics papers","behavior_class":"B",'
        '"interaction_mode":"information_retrieval",'
        '"release_id":"release:s8v2-baseline","as_of":"2026-07-19T00:00:00Z",'
        '"domains":["paper"],"protected_slots":[],"lanes":["vector","web"],'
        '"max_candidates":2,"web_required":true,'
        '"web_policy":{"mode":"universal","max_provider_calls":1,'
        '"timeout_ms":1500,"max_results":2,"allowed_domains":[]},'
        '"freshness_material":true,"query_views":[],"relationship_paths":[],'
        '"structured_constraints":{"displayed_entity_ids":[],"geography":[],'
        '"excluded_terms":[]},"enumeration_policy":null,"material_parts":[],'
        '"supplemental_budget":null,"retained_web_handles":[],'
        '"web_handle_replays":[],"handle_operation":null,"session_id":null,'
        '"planning_trace":null,"allowed_operations":[],"institution_slots":[],'
        '"rewrite_policy":{"generic_topic_stopwords":[]},"pure_topic_text":null,'
        '"lane_queries":[],"ambiguity_decision":null,'
        '"internal_reference_queries":[],"unresolved_technology_terms":[]}'
    )
    assert plan.content_sha256 == (
        "02903acca487b8b924c2ab2a2a22618fbb2ad236b544954941689a07f37c7c8b"
    )
    assert lane_request.model_dump_json() == (
        '{"content_sha256":"e1ea60fcc7a275be3bb12d76ec0dea6f0c4809592571c9484cf8bf481aa73783",'
        '"lane":"vector","release_id":"release:s8v2-baseline",'
        '"query_view":"view:original","original_query":"robotics papers",'
        '"behavior_class":"B","interaction_mode":"information_retrieval",'
        '"web_policy":{"mode":"disabled","max_provider_calls":0,"timeout_ms":0,'
        '"max_results":0,"allowed_domains":[]},'
        '"query_text":"robotics papers [lane=vector]","domains":["paper"],'
        '"protected_slots":[],"structured_constraints":{"displayed_entity_ids":[],'
        '"geography":[],"excluded_terms":[]},"max_candidates":2}'
    )
    assert lane_request.content_sha256 == (
        "e1ea60fcc7a275be3bb12d76ec0dea6f0c4809592571c9484cf8bf481aa73783"
    )


def test_s8v2_professor_typed_vector_view_selection_is_release_authoritative(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_module = _professor_vector_view_module()
    vector_factory = _isolated_vector_recall_factory()
    release_planner_factory = _isolated_release_query_planner_factory()
    release_read_factory = _isolated_release_knowledge_read_factory()
    fixture = request.getfixturevalue("isolated_lookup_target_bundle")
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    domain_models = import_module(
        "src.data_agents.canonical_v2.domain_projection_models"
    )
    index_module = _index_projection_module()
    isolated_index_module = _isolated_index_projection_module()
    isolated_read_module = _isolated_knowledge_read_module()
    release_module = _isolated_release_publication_module()
    bundle = fixture["bundle"]
    published = _s8p1_published_release(contracts_module, release_id=RELEASE_ID)
    embedding_adapter = isolated_index_module.RecordedEmbeddingAdapter(
        model_id="recorded-embedding-v1",
        dimension=32,
    )

    professor_points = tuple(
        point
        for point in bundle.index_result.points
        if point.domain == "professor" and point.canonical_object_id == "professor-ada"
    )
    assert {point.projection_view.value for point in professor_points} == {
        "identity",
        "research",
    }
    professor_lookup_manifest = next(
        manifest
        for manifest in bundle.index_result.expected_lookup_projections
        if manifest.projection_scope.value == "public_domain"
        and manifest.domain == "professor"
    )
    professor_lookup_documents = tuple(
        document
        for document in bundle.index_result.lookup_documents
        if document.projection_scope.value == "public_domain"
        and document.domain == "professor"
        and document.canonical_object_id == "professor-ada"
    )
    assert len(professor_lookup_documents) == 1
    professor_document = professor_lookup_documents[0]
    professor_projection = domain_models.ProfessorProjection.model_validate_json(
        professor_document.lookup_content
    )
    professor_name = professor_projection.name
    assert professor_name == "陈艾达"
    assert (
        professor_document.projection_id
        == professor_lookup_manifest.projection_id
        == "lookup:exact-lookup:professor"
    )
    assert professor_document.projection_view.value == "identity"
    assert {point.source_projection_content_sha256 for point in professor_points} == {
        professor_document.source_projection_content_sha256,
        professor_projection.content_sha256,
    }

    scenario_specs = (
        ("identity", "“陈艾达”是谁？", "identity", "A"),
        ("research", "哪些教授研究机器人？", "research", "B"),
        ("both", "“陈艾达”是否研究机器人？", "both", "G"),
    )
    planning_requests: dict[str, Any] = {}
    proposals: dict[str, Any] = {}
    plans: dict[str, Any] = {}

    def make_release_plan(
        *,
        token: str,
        query: str,
        professor_vector_view: str,
        behavior_class: str,
        max_candidates: int = 2,
    ) -> Any:
        planning_request = read_module.QueryPlanningRequest(
            request_id=f"query-request:s8v2-{token}",
            release_id=RELEASE_ID,
            original_query=query,
            as_of=NOW,
        )

        def proposal_provider(value: Any) -> Any:
            assert value == planning_request
            proposal = read_module.RecordedPlanningProposal(
                proposal_id=f"planning-proposal:s8v2-{token}",
                request_sha256=value.content_sha256,
                schema_version="retrieval-plan-proposal-v1",
                model_id="recorded-planner-s8v2",
                prompt_version="query-plan-prompt-v1",
                behavior_class=behavior_class,
                interaction_mode="information_retrieval",
                domains=("professor",),
                lanes=("vector", "web"),
                max_candidates=max_candidates,
                max_provider_calls=1,
                web_mode="universal",
                max_web_results=max_candidates,
                professor_vector_view=professor_vector_view,
            )
            proposals[token] = proposal
            return proposal

        plan = release_planner_factory(
            release_bundle=bundle,
            published_release=published,
            index_projection_request=fixture["index_request"],
            release_institution_catalog=_s8p1_institution_catalog(read_module),
            planning_policy=_s8p1_planning_policy(read_module),
            proposal_provider=proposal_provider,
        ).plan(planning_request)
        planning_requests[token] = planning_request
        plans[token] = plan
        assert proposals[token].professor_vector_view == professor_vector_view
        assert plan.professor_vector_view == professor_vector_view
        assert plan.original_query == query
        assert plan.domains == ("professor",)
        assert plan.lanes == ("vector", "web")
        assert plan.release_binding is not None
        assert (
            plan.model_dump(mode="json")["professor_vector_view"]
            == professor_vector_view
        )
        return plan

    for token, query, view, behavior_class in scenario_specs:
        make_release_plan(
            token=token,
            query=query,
            professor_vector_view=view,
            behavior_class=behavior_class,
        )

    def direct_request(
        plan: Any,
        *,
        professor_vector_view: str | None,
        max_candidates: int | None = None,
    ) -> Any:
        lane_query = next(
            query for query in plan.lane_queries if query.lane == "vector"
        )
        return read_module.LaneRequest(
            lane="vector",
            release_id=plan.release_id,
            query_view="view:original",
            original_query=plan.original_query,
            behavior_class=plan.behavior_class,
            interaction_mode=plan.interaction_mode,
            web_policy=read_module.WebSearchPolicy(mode="disabled"),
            query_text=lane_query.query_text,
            domains=plan.domains,
            protected_slots=plan.protected_slots,
            structured_constraints=plan.structured_constraints,
            max_candidates=(
                plan.max_candidates if max_candidates is None else max_candidates
            ),
            professor_vector_view=professor_vector_view,
        )

    vector_adapter = vector_factory(
        release_bundle=bundle,
        published_release=published,
        embedding_adapter=embedding_adapter,
    )
    direct_results: dict[str, Any] = {}
    for token, _, view, _ in scenario_specs:
        lane_request = direct_request(
            plans[token],
            professor_vector_view=view,
        )
        direct_result = vector_adapter(lane_request)
        direct_results[token] = direct_result
        assert lane_request.professor_vector_view == view
        trace_views = {
            candidate.evidence[0].local_projection_trace.projection_view
            for candidate in direct_result.candidates
        }
        assert trace_views == ({view} if view != "both" else {"identity", "research"})
        assert all(
            candidate.display_name == professor_name
            for candidate in direct_result.candidates
        )
        assert all(
            candidate.canonical_id == "professor-ada"
            for candidate in direct_result.candidates
        )
        assert len(direct_result.candidates) == (2 if view == "both" else 1)

    one_point_both = vector_adapter(
        direct_request(
            plans["both"],
            professor_vector_view="both",
            max_candidates=1,
        )
    )
    assert len(one_point_both.candidates) == 1
    assert one_point_both == vector_adapter(
        direct_request(
            plans["both"],
            professor_vector_view="both",
            max_candidates=1,
        )
    )
    assert {
        one_point_both.candidates[0].evidence[0].local_projection_trace.projection_view
    } <= {"identity", "research"}

    captured_vector_requests: list[Any] = []
    captured_web_requests: list[Any] = []
    original_vector_factory = isolated_read_module.create_isolated_vector_recall_adapter

    def capturing_vector_factory(**kwargs: Any) -> Any:
        adapter = original_vector_factory(**kwargs)

        def capture(lane_request: Any) -> Any:
            captured_vector_requests.append(lane_request)
            return adapter(lane_request)

        return capture

    def empty_web(lane_request: Any) -> Any:
        captured_web_requests.append(lane_request)
        return read_module.RetrievalLaneResult()

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_vector_recall_adapter",
        capturing_vector_factory,
    )
    service = release_read_factory(
        release_bundle=bundle,
        published_release=published,
        universal_web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=2,
        ),
        web_search=empty_web,
        web_snapshot_policy=read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8v2",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        embedding_adapter=embedding_adapter,
        clock=lambda: NOW,
    )
    evidence_by_token: dict[str, Any] = {}
    for token, _, view, _ in scenario_specs:
        evidence_set = service.execute(plans[token])
        evidence_by_token[token] = evidence_set
        assert {(trace.lane, trace.status) for trace in evidence_set.traces} == {
            ("vector", "succeeded"),
            ("web", "succeeded"),
        }
        vector_items = tuple(
            item for item in evidence_set.items if item.lane == "vector"
        )
        vector_views = {
            item.local_projection_trace.projection_view for item in vector_items
        }
        assert vector_views == ({view} if view != "both" else {"identity", "research"})
        assert len(evidence_set.fused_candidates) == 1
        fused = evidence_set.fused_candidates[0]
        assert fused.canonical_id == "professor-ada"
        assert fused.display_name == professor_name
        assert evidence_set.entity_handles == (
            read_module.CanonicalEntityHandle(
                canonical_id="professor-ada",
                domain="professor",
                display_name=professor_name,
                evidence_ids=fused.evidence_ids,
            ),
        )

    assert tuple(
        lane_request.professor_vector_view
        for lane_request in captured_vector_requests[:3]
    ) == ("identity", "research", "both")
    assert all(
        lane_request.professor_vector_view is None
        and "professor_vector_view" not in lane_request.model_dump(mode="json")
        for lane_request in captured_web_requests[:3]
    )
    both_evidence = evidence_by_token["both"]
    both_fused = both_evidence.fused_candidates[0]
    assert len(both_fused.raw_candidate_ids) == 2
    assert len(set(both_fused.raw_candidate_ids)) == 2
    assert len(both_fused.evidence_ids) == 2
    assert len(set(both_fused.evidence_ids)) == 2
    assert {
        item.local_projection_trace.projection_view
        for item in both_fused.evidence
        if item.lane == "vector"
    } == {"identity", "research"}

    one_bound_plan = make_release_plan(
        token="both-bound-one",
        query="“陈艾达”是否研究机器人？",
        professor_vector_view="both",
        behavior_class="G",
        max_candidates=1,
    )
    one_bound_evidence = service.execute(one_bound_plan)
    assert (
        len(tuple(item for item in one_bound_evidence.items if item.lane == "vector"))
        == 1
    )
    assert len(one_bound_evidence.fused_candidates) == 1

    valid_proposal = proposals["research"]

    def proposal_payload(**updates: Any) -> dict[str, Any]:
        payload = valid_proposal.model_dump(mode="json")
        payload.update(updates)
        payload["content_sha256"] = "0" * 64
        return payload

    missing_proposal = proposal_payload()
    missing_proposal.pop("professor_vector_view")
    for payload in (
        missing_proposal,
        proposal_payload(domains=["paper"]),
        proposal_payload(lanes=["web"]),
        proposal_payload(professor_vector_view="untyped"),
    ):
        with pytest.raises(ValidationError, match="Professor|professor|vector|literal"):
            read_module.RecordedPlanningProposal.model_validate(payload)

    hostile_values = valid_proposal.model_dump(mode="python")
    hostile_values.update(
        professor_vector_view="untyped",
        content_sha256="0" * 64,
    )
    hostile_same_class = read_module.RecordedPlanningProposal.model_construct(
        **hostile_values
    )
    with pytest.raises(
        read_module.InvalidRetrievalPlanError,
        match="invalid_planning_proposal",
    ):
        read_module.create_ephemeral_query_planner(
            planning_policy=_s8p1_planning_policy(read_module),
            institution_catalog=_s8p1_institution_catalog(read_module),
            proposal_provider=lambda _: hostile_same_class,
        ).plan(planning_requests["research"])

    valid_plan = plans["research"]

    def plan_payload(**updates: Any) -> dict[str, Any]:
        payload = valid_plan.model_dump(mode="json")
        payload.update(updates)
        payload["content_sha256"] = "0" * 64
        return payload

    missing_plan = plan_payload()
    missing_plan.pop("professor_vector_view")
    without_vector = plan_payload(
        lanes=["web"],
        lane_queries=[
            query.model_dump(mode="json")
            for query in valid_plan.lane_queries
            if query.lane == "web"
        ],
    )
    for payload in (
        missing_plan,
        plan_payload(domains=["paper"]),
        without_vector,
        plan_payload(professor_vector_view="untyped"),
    ):
        with pytest.raises(ValidationError, match="Professor|professor|vector|literal"):
            read_module.RetrievalPlan.model_validate(payload)

    ambiguous_catalog = read_module.InstitutionCatalog(
        catalog_id="institution-catalog:s8v2-ambiguous",
        catalog_version="institution-catalog-v1",
        release_id=RELEASE_ID,
        entries=(
            read_module.InstitutionCatalogEntry(
                canonical_id="institution:s8v2-a",
                canonical_name="共同大学甲",
                aliases=("共同大学",),
            ),
            read_module.InstitutionCatalogEntry(
                canonical_id="institution:s8v2-b",
                canonical_name="共同大学乙",
                aliases=("共同大学",),
            ),
        ),
    )
    blocking_request = read_module.QueryPlanningRequest(
        request_id="query-request:s8v2-blocking",
        release_id=RELEASE_ID,
        original_query="共同大学有哪些研究机器人的教授？",
        as_of=NOW,
    )

    def blocking_provider(value: Any) -> Any:
        return read_module.RecordedPlanningProposal(
            proposal_id="planning-proposal:s8v2-blocking",
            request_sha256=value.content_sha256,
            schema_version="retrieval-plan-proposal-v1",
            model_id="recorded-planner-s8v2",
            prompt_version="query-plan-prompt-v1",
            behavior_class="B",
            interaction_mode="information_retrieval",
            domains=("professor",),
            lanes=("vector", "web"),
            max_candidates=2,
            max_provider_calls=1,
            web_mode="universal",
            max_web_results=2,
            professor_vector_view="research",
        )

    blocking_plan = read_module.create_ephemeral_query_planner(
        planning_policy=_s8p1_planning_policy(read_module),
        institution_catalog=ambiguous_catalog,
        proposal_provider=blocking_provider,
    ).plan(blocking_request)
    assert blocking_plan.interaction_mode == "blocking_clarification"
    assert blocking_plan.lanes == ()
    assert blocking_plan.professor_vector_view is None
    assert "professor_vector_view" not in blocking_plan.model_dump(mode="json")

    legacy_unbound_plan = read_module.RetrievalPlan(
        plan_id="retrieval-plan:s8v2-legacy-professor",
        plan_version="retrieval-plan-v1",
        original_query="legacy synthetic Professor vector request",
        behavior_class="B",
        interaction_mode="information_retrieval",
        release_id=RELEASE_ID,
        as_of=NOW,
        domains=("professor",),
        protected_slots=(),
        lanes=("vector", "web"),
        max_candidates=2,
        web_required=True,
        web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=2,
        ),
        freshness_material=True,
    )
    assert legacy_unbound_plan.professor_vector_view is None
    assert "professor_vector_view" not in legacy_unbound_plan.model_dump(mode="json")
    legacy_lane_request = read_module.LaneRequest(
        lane="vector",
        release_id=RELEASE_ID,
        query_view="view:original",
        original_query=legacy_unbound_plan.original_query,
        behavior_class="B",
        interaction_mode="information_retrieval",
        web_policy=read_module.WebSearchPolicy(mode="disabled"),
        query_text="legacy synthetic Professor vector request [lane=vector]",
        domains=("professor",),
        protected_slots=(),
        structured_constraints=read_module.StructuredConstraints(),
        max_candidates=2,
    )
    assert legacy_lane_request.professor_vector_view is None
    assert "professor_vector_view" not in legacy_lane_request.model_dump(mode="json")

    direct_research_request = direct_request(
        plans["research"],
        professor_vector_view="research",
    )

    def lane_payload(**updates: Any) -> dict[str, Any]:
        payload = direct_research_request.model_dump(mode="json")
        payload.update(updates)
        payload["content_sha256"] = "0" * 64
        return payload

    for payload in (
        lane_payload(lane="lexical"),
        lane_payload(domains=["paper"]),
        lane_payload(professor_vector_view="untyped"),
    ):
        with pytest.raises(ValidationError, match="Professor|professor|vector|literal"):
            read_module.LaneRequest.model_validate(payload)

    original_audit = isolated_read_module.audit_isolated_index_snapshot
    audit_attempts: list[Any] = []

    def unexpected_audit(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        audit_attempts.append("audit")
        raise AssertionError(
            "missing Professor selector must fail before physical audit"
        )

    class ProbeEmbeddingAdapter:
        model_id = "recorded-embedding-v1"
        dimension = 32

        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        def embed_batch(self, texts: tuple[str, ...]) -> tuple[Any, ...]:
            self.calls.append(texts)
            return embedding_adapter.embed_batch(texts)

    monkeypatch.setattr(
        isolated_read_module,
        "audit_isolated_index_snapshot",
        unexpected_audit,
    )
    probe_embedding = ProbeEmbeddingAdapter()
    pre_effect_adapter = vector_factory(
        release_bundle=bundle,
        published_release=published,
        embedding_adapter=probe_embedding,
    )
    with pytest.raises(Exception, match="Professor|professor|selector|view"):
        pre_effect_adapter(legacy_lane_request)
    assert audit_attempts == []
    assert probe_embedding.calls == []
    monkeypatch.setattr(
        isolated_read_module,
        "audit_isolated_index_snapshot",
        original_audit,
    )

    vector_calls_before = len(captured_vector_requests)
    web_calls_before = len(captured_web_requests)
    invalid_release_plan = plans["research"].model_copy(
        update={"professor_vector_view": None}
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="plan|Professor|professor|selector|view",
    ):
        service.execute(invalid_release_plan)
    assert len(captured_vector_requests) == vector_calls_before
    assert len(captured_web_requests) == web_calls_before

    real_snapshot = isolated_index_module.audit_isolated_index_snapshot(
        bundle.index_target,
        embedding_adapter=embedding_adapter,
    )

    def bundle_and_snapshot_with_documents(
        documents: tuple[Any, ...],
    ) -> tuple[Any, Any]:
        ordered_documents = tuple(
            sorted(
                documents,
                key=lambda document: (
                    document.projection_id,
                    document.canonical_object_id,
                ),
            )
        )
        lookup_manifests = index_module.build_lookup_projection_manifests(
            request=fixture["index_request"],
            documents=ordered_documents,
            full_rebuild=True,
        )
        result_payload = bundle.index_result.model_dump(mode="json")
        result_payload.update(
            lookup_documents=[
                document.model_dump(mode="json") for document in ordered_documents
            ],
            expected_lookup_projections=[
                manifest.model_dump(mode="json") for manifest in lookup_manifests
            ],
            actual_lookup_projections=[
                manifest.model_dump(mode="json") for manifest in lookup_manifests
            ],
        )
        result_payload["content_sha256"] = _canonical_json_sha256(
            {
                key: value
                for key, value in result_payload.items()
                if key != "content_sha256"
            }
        )
        mutated_result = index_module.IndexProjectionResult.model_validate(
            result_payload
        )

        receipt_payload = real_snapshot.receipt.model_dump(mode="json")
        receipt_payload.update(
            lookup_document_ids=sorted(
                document.document_id for document in ordered_documents
            ),
            lookup_projections=[
                manifest.model_dump(mode="json") for manifest in lookup_manifests
            ],
        )
        receipt_payload["content_sha256"] = _canonical_json_sha256(
            {
                key: value
                for key, value in receipt_payload.items()
                if key != "content_sha256"
            }
        )
        mutated_receipt = (
            index_module.IndexProjectionMaterializationReceipt.model_validate(
                receipt_payload
            )
        )
        mutated_bundle = release_module.IsolatedReleaseBundle(
            manifest=bundle.manifest,
            index_result=mutated_result,
            index_target=bundle.index_target,
        )
        mutated_snapshot = isolated_index_module.IsolatedIndexSnapshot(
            receipt=mutated_receipt,
            points=mutated_result.points,
            lookup_documents=mutated_result.lookup_documents,
        )
        return mutated_bundle, mutated_snapshot

    def replace_professor_document(replacement: Any | None) -> tuple[Any, ...]:
        return tuple(
            replacement
            if document.document_id == professor_document.document_id
            and replacement is not None
            else document
            for document in bundle.index_result.lookup_documents
            if replacement is not None
            or document.document_id != professor_document.document_id
        )

    modified_projection_payload = json.loads(professor_document.lookup_content)
    modified_projection_payload.update(
        name="伪造教授名",
        canonical_name_zh="伪造教授名",
    )
    modified_projection_payload["content_sha256"] = _canonical_json_sha256(
        {
            key: value
            for key, value in modified_projection_payload.items()
            if key != "content_sha256"
        }
    )
    modified_projection = domain_models.ProfessorProjection.model_validate(
        modified_projection_payload
    )
    modified_lookup_content = modified_projection.model_dump_json()
    self_consistent_but_point_mismatched = professor_document.model_copy(
        update={
            "lookup_content": modified_lookup_content,
            "lookup_content_sha256": hashlib.sha256(
                modified_lookup_content.encode("utf-8")
            ).hexdigest(),
            "source_projection_content_sha256": modified_projection.content_sha256,
        }
    )
    assert (
        self_consistent_but_point_mismatched.source_projection_content_sha256
        != next(
            point.source_projection_content_sha256
            for point in professor_points
            if point.projection_view.value == "research"
        )
    )

    duplicate_document = professor_document.model_copy(
        update={"document_id": f"{professor_document.document_id}:duplicate"}
    )
    different_hash_duplicate = self_consistent_but_point_mismatched.model_copy(
        update={
            "document_id": f"{professor_document.document_id}:different-source-duplicate"
        }
    )
    display_authority_variants = (
        ("missing", replace_professor_document(None)),
        (
            "duplicate",
            (*bundle.index_result.lookup_documents, duplicate_document),
        ),
        (
            "duplicate_different_source_hash",
            (*bundle.index_result.lookup_documents, different_hash_duplicate),
        ),
        (
            "cross_release",
            replace_professor_document(
                professor_document.model_copy(
                    update={"release_id": "cross-release-s8v2"}
                )
            ),
        ),
        (
            "wrong_domain",
            replace_professor_document(
                professor_document.model_copy(update={"domain": "company"})
            ),
        ),
        (
            "mismatched_canonical",
            replace_professor_document(
                professor_document.model_copy(
                    update={"canonical_object_id": "professor-other"}
                )
            ),
        ),
        (
            "wrong_view",
            replace_professor_document(
                professor_document.model_copy(
                    update={
                        "projection_view": type(
                            professor_document.projection_view
                        ).research
                    }
                )
            ),
        ),
        (
            "wrong_projection_id",
            replace_professor_document(
                professor_document.model_copy(
                    update={"projection_id": "lookup:exact-lookup:professor:hostile"}
                )
            ),
        ),
        (
            "source_projection_hash",
            replace_professor_document(
                professor_document.model_copy(
                    update={"source_projection_content_sha256": "f" * 64}
                )
            ),
        ),
        (
            "point_source_projection_hash",
            replace_professor_document(self_consistent_but_point_mismatched),
        ),
    )
    for label, documents in display_authority_variants:
        mutated_bundle, mutated_snapshot = bundle_and_snapshot_with_documents(
            tuple(documents)
        )
        monkeypatch.setattr(
            isolated_read_module,
            "audit_isolated_index_snapshot",
            lambda *args, value=mutated_snapshot, **kwargs: value,
        )
        hostile_adapter = vector_factory(
            release_bundle=mutated_bundle,
            published_release=published,
            embedding_adapter=embedding_adapter,
        )
        with pytest.raises(
            Exception,
            match="Professor|professor|lookup|projection|lineage|authority",
        ) as rejected:
            hostile_adapter(direct_research_request)
        assert label
        assert rejected.value is not None

    monkeypatch.setattr(
        isolated_read_module,
        "audit_isolated_index_snapshot",
        original_audit,
    )

    identity_request_payload = direct_research_request.model_dump(mode="json")
    identity_request_payload.update(
        professor_vector_view="identity",
        content_sha256="0" * 64,
    )
    identity_on_research_request = read_module.LaneRequest.model_validate(
        identity_request_payload
    )
    identity_on_research_result = vector_adapter(identity_on_research_request)
    assert {
        candidate.evidence[0].local_projection_trace.projection_view
        for candidate in identity_on_research_result.candidates
    } == {"identity"}

    trusted_research_candidate = direct_results["research"].candidates[0]
    forged_candidate_payload = trusted_research_candidate.model_dump(mode="json")
    forged_candidate_payload["display_name"] = "伪造教授名"
    forged_display_result = read_module.RetrievalLaneResult(
        candidates=(
            read_module.RecallCandidate.model_validate(forged_candidate_payload),
        )
    )
    hostile_release_results = (
        ("wrong selected view", identity_on_research_result),
        ("forged Professor display name", forged_display_result),
    )
    for label, hostile_result in hostile_release_results:
        monkeypatch.setattr(
            isolated_read_module,
            "create_isolated_vector_recall_adapter",
            lambda **kwargs: lambda lane_request, value=hostile_result: value,
        )
        hostile_service = release_read_factory(
            release_bundle=bundle,
            published_release=published,
            universal_web_policy=read_module.WebSearchPolicy(
                mode="universal",
                max_provider_calls=1,
                timeout_ms=1_000,
                max_results=2,
            ),
            web_search=lambda _: read_module.RetrievalLaneResult(),
            web_snapshot_policy=read_module.WebSnapshotPolicy(
                policy_id=f"web-snapshot-policy:s8v2-hostile:{label}",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
            embedding_adapter=embedding_adapter,
            clock=lambda: NOW,
        )
        with pytest.raises(
            isolated_read_module.IsolatedKnowledgeReadIntegrityError,
            match="Professor|professor|view|display|name|authority",
        ):
            hostile_service.execute(plans["research"])

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_vector_recall_adapter",
        original_vector_factory,
    )
    assert {
        name: _file_sha256(bundle.index_target.root / name)
        for name in fixture["target_hashes"]
    } == fixture["target_hashes"]
    assert _file_sha256(fixture["original_milvus"]) == fixture["original_sha256"]


def test_release_scoped_structured_lookup_dereferences_displayed_set_by_lane(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    structured_factory = _isolated_structured_lookup_factory()
    fixture = request.getfixturevalue("isolated_lookup_target_bundle")
    exact_module = _isolated_knowledge_read_module()
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    release_module = _isolated_release_publication_module()
    index_module = _index_projection_module()
    isolated = _isolated_index_projection_module()
    bundle = fixture["bundle"]
    published = contracts_module.PublishedRelease(
        release_id=RELEASE_ID,
        previous_release_id="accepted-before-s8l2",
        canonical_release_id=RELEASE_ID,
        published_projection_release_id=RELEASE_ID,
        index_release_id=RELEASE_ID,
        state="active",
        changed_at=NOW,
        verification_evidence_ids=("release-verification:s8l2",),
    )
    displayed_ids = ("company-robotics", "paper-ada")
    displayed_slot = read_module.ProtectedSlot(
        kind="displayed_entity_set",
        entity_ids=displayed_ids,
    )
    displayed_constraints = read_module.StructuredConstraints(
        displayed_entity_ids=displayed_ids,
    )
    structured_requests: list[Any] = []
    structured_adapter = structured_factory(
        release_bundle=bundle,
        published_release=published,
    )

    def captured_structured_adapter(lane_request: Any) -> Any:
        structured_requests.append(lane_request)
        return structured_adapter(lane_request)

    service = read_module.create_ephemeral_knowledge_read(
        universal_web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=1,
        ),
        lane_adapters={"structured": captured_structured_adapter},
        web_search=lambda _: read_module.RetrievalLaneResult(),
        clock=lambda: NOW,
    )
    plan = read_module.RetrievalPlan(
        plan_id="retrieval-plan:s8l2-structured",
        plan_version="canonical-v2-s8l2-plan-v1",
        original_query="Which of the displayed results should we inspect?",
        behavior_class="G",
        interaction_mode="information_retrieval",
        release_id=RELEASE_ID,
        as_of=NOW,
        domains=("company", "paper"),
        protected_slots=(displayed_slot,),
        lanes=("structured",),
        max_candidates=2,
        web_required=True,
        web_policy=read_module.WebSearchPolicy(mode="disabled"),
        structured_constraints=displayed_constraints,
        lane_queries=(
            read_module.LaneQuery(
                lane="structured",
                release_id=RELEASE_ID,
                catalog_sha256=CATALOG_CONTENT_SHA256,
                pure_topic_text="displayed results",
                query_text="displayed results [lane=structured]",
            ),
        ),
    )

    evidence_set = service.execute(plan)

    assert len(structured_requests) == 1
    lane_request = structured_requests[0]
    assert lane_request.lane == "structured"
    assert lane_request.query_text == "displayed results [lane=structured]"
    assert lane_request.domains == ("company", "paper")
    assert lane_request.protected_slots == (displayed_slot,)
    assert lane_request.structured_constraints == displayed_constraints
    assert lane_request.max_candidates == 2
    assert {handle.canonical_id for handle in evidence_set.entity_handles} == set(
        displayed_ids
    )
    assert {candidate.canonical_id for candidate in evidence_set.fused_candidates} == (
        set(displayed_ids)
    )
    assert len(evidence_set.items) == 2
    assert all(item.lane == "structured" for item in evidence_set.items)
    assert all(
        item.local_projection_trace is not None
        and item.local_projection_trace.execution_lane == "structured"
        and item.local_projection_trace.path == "exact_lookup"
        and item.evidence_id == item.local_projection_trace.evidence_id
        for item in evidence_set.items
    )

    raw_result = structured_adapter(lane_request)
    assert tuple(candidate.canonical_id for candidate in raw_result.candidates) == (
        "company-robotics",
        "paper-ada",
    )
    assert all(candidate.lane == "structured" for candidate in raw_result.candidates)
    assert all(
        candidate.raw_candidate_id
        == candidate.evidence[0].local_projection_trace.raw_candidate_id
        for candidate in raw_result.candidates
    )

    def lane_request_with(**updates: Any) -> Any:
        payload = lane_request.model_dump(mode="json")
        payload.update(updates)
        payload["content_sha256"] = "0" * 64
        return read_module.LaneRequest.model_validate(payload)

    assert (
        structured_adapter(
            lane_request_with(
                protected_slots=(),
                structured_constraints=read_module.StructuredConstraints().model_dump(
                    mode="json"
                ),
            )
        ).candidates
        == ()
    )
    assert (
        structured_adapter(
            lane_request_with(
                protected_slots=(),
                structured_constraints=read_module.StructuredConstraints(
                    displayed_entity_ids=("unknown-object",),
                ).model_dump(mode="json"),
            )
        ).candidates
        == ()
    )
    internal_id = next(
        document.canonical_object_id
        for document in bundle.index_result.lookup_documents
        if document.projection_scope.value == "internal_auxiliary"
    )
    assert (
        structured_adapter(
            lane_request_with(
                protected_slots=(),
                structured_constraints=read_module.StructuredConstraints(
                    displayed_entity_ids=(internal_id,),
                ).model_dump(mode="json"),
            )
        ).candidates
        == ()
    )
    assert (
        structured_adapter(
            lane_request_with(
                domains=("company",),
                protected_slots=(),
                structured_constraints=read_module.StructuredConstraints(
                    displayed_entity_ids=("paper-ada",),
                ).model_dump(mode="json"),
            )
        ).candidates
        == ()
    )
    bounded = structured_adapter(lane_request_with(max_candidates=1))
    assert tuple(candidate.canonical_id for candidate in bounded.candidates) == (
        "company-robotics",
    )
    excluded = structured_adapter(
        lane_request_with(
            structured_constraints=read_module.StructuredConstraints(
                displayed_entity_ids=displayed_ids,
                excluded_terms=("Robotics route",),
            ).model_dump(mode="json"),
        )
    )
    assert tuple(candidate.canonical_id for candidate in excluded.candidates) == (
        "paper-ada",
    )

    rolled_back_adapter = structured_factory(
        release_bundle=bundle,
        published_release=published.model_copy(
            update={"state": contracts_module.ReleaseState.rolled_back}
        ),
    )
    assert len(rolled_back_adapter(lane_request).candidates) == 2
    wrong_release = published.model_copy(
        update={
            "release_id": "cross-release-s8l2",
            "canonical_release_id": "cross-release-s8l2",
            "published_projection_release_id": "cross-release-s8l2",
            "index_release_id": "cross-release-s8l2",
        }
    )
    with pytest.raises(ValueError, match="published release.*bundle"):
        structured_factory(
            release_bundle=bundle,
            published_release=wrong_release,
        )

    unmarked_root = tmp_path / "s8l2-unmarked-target"
    unmarked_root.mkdir()
    unmarked_bundle = release_module.IsolatedReleaseBundle(
        manifest=bundle.manifest,
        index_result=bundle.index_result,
        index_target=bundle.index_target.model_copy(update={"root": unmarked_root}),
    )
    unmarked_adapter = structured_factory(
        release_bundle=unmarked_bundle,
        published_release=published,
    )
    assert (
        unmarked_adapter(
            lane_request_with(
                protected_slots=(),
                structured_constraints=read_module.StructuredConstraints().model_dump(
                    mode="json"
                ),
            )
        ).candidates
        == ()
    )
    with pytest.raises(ValueError, match="protected displayed set"):
        unmarked_adapter(
            lane_request_with(
                protected_slots=(
                    read_module.ProtectedSlot(
                        kind="displayed_entity_set",
                        entity_ids=("company-robotics",),
                    ).model_dump(mode="json"),
                ),
            )
        )
    with pytest.raises(isolated.IsolatedIndexTargetSafetyError, match="marker"):
        unmarked_adapter(lane_request)
    assert not (unmarked_root / "lookup.sqlite3").exists()
    assert not (unmarked_root / "milvus.db").exists()

    reduced_documents = tuple(
        document
        for document in bundle.index_result.lookup_documents
        if document.canonical_object_id != "paper-ada"
    )
    mismatched_payload = bundle.index_result.model_dump(mode="json")
    mismatched_payload["lookup_documents"] = [
        document.model_dump(mode="json") for document in reduced_documents
    ]
    mismatched_payload["content_sha256"] = hashlib.sha256(
        json.dumps(
            {
                key: value
                for key, value in mismatched_payload.items()
                if key != "content_sha256"
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    mismatched_bundle = release_module.IsolatedReleaseBundle(
        manifest=bundle.manifest,
        index_result=index_module.IndexProjectionResult.model_validate(
            mismatched_payload
        ),
        index_target=bundle.index_target,
    )
    mismatched_adapter = structured_factory(
        release_bundle=mismatched_bundle,
        published_release=published,
    )
    with pytest.raises(
        index_module.IndexProjectionIntegrityError,
        match="physical lookup.*bundle",
    ):
        mismatched_adapter(lane_request)

    exact_adapter = exact_module.create_isolated_exact_lookup_adapter(
        release_bundle=bundle,
        published_release=published,
    )
    explicit_name = read_module.ProtectedSlot(
        kind="explicit_name",
        value="Robotics Co",
        raw_text="Robotics Co",
    )
    company_displayed_slot = read_module.ProtectedSlot(
        kind="displayed_entity_set",
        entity_ids=("company-robotics",),
    )
    combined_plan = read_module.RetrievalPlan(
        plan_id="retrieval-plan:s8l2-combined",
        plan_version="canonical-v2-s8l2-plan-v1",
        original_query="Inspect Robotics Co from the displayed results",
        behavior_class="G",
        interaction_mode="information_retrieval",
        release_id=RELEASE_ID,
        as_of=NOW,
        domains=("company",),
        protected_slots=(explicit_name, company_displayed_slot),
        lanes=("exact", "structured"),
        max_candidates=2,
        web_required=True,
        web_policy=read_module.WebSearchPolicy(mode="disabled"),
        structured_constraints=read_module.StructuredConstraints(
            displayed_entity_ids=("company-robotics",),
        ),
        lane_queries=(
            read_module.LaneQuery(
                lane="exact",
                release_id=RELEASE_ID,
                catalog_sha256=CATALOG_CONTENT_SHA256,
                pure_topic_text="Robotics Co",
                query_text="Robotics Co [lane=exact]",
            ),
            read_module.LaneQuery(
                lane="structured",
                release_id=RELEASE_ID,
                catalog_sha256=CATALOG_CONTENT_SHA256,
                pure_topic_text="displayed results",
                query_text="displayed results [lane=structured]",
            ),
        ),
    )
    exact_results: list[Any] = []

    def captured_exact_adapter(lane_request: Any) -> Any:
        result = exact_adapter(lane_request)
        exact_results.append(result)
        return result

    combined_service = read_module.create_ephemeral_knowledge_read(
        universal_web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=1,
        ),
        lane_adapters={
            "exact": captured_exact_adapter,
            "structured": structured_adapter,
        },
        web_search=lambda _: read_module.RetrievalLaneResult(),
        clock=lambda: NOW,
    )
    combined = combined_service.execute(combined_plan)
    assert len(combined.fused_candidates) == 1
    fused = combined.fused_candidates[0]
    assert fused.canonical_id == "company-robotics"
    assert len(fused.raw_candidate_ids) == 2
    assert len(set(fused.raw_candidate_ids)) == 2
    assert len(fused.evidence_ids) == 2
    assert len(set(fused.evidence_ids)) == 2
    assert {item.lane for item in fused.evidence} == {"exact", "structured"}
    assert {item.local_projection_trace.execution_lane for item in fused.evidence} == {
        "exact",
        "structured",
    }
    exact_item = next(item for item in fused.evidence if item.lane == "exact")
    exact_trace = exact_item.local_projection_trace
    assert exact_trace is not None
    legacy_lineage = exact_trace.model_dump(
        mode="json",
        exclude={
            "execution_lane",
            "raw_candidate_id",
            "evidence_id",
            "content_sha256",
        },
    )
    assert exact_trace.raw_candidate_id == (
        "local-exact-candidate:sha256:"
        + hashlib.sha256(
            json.dumps(
                legacy_lineage,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
    )
    legacy_evidence_id = (
        "local-projection-evidence:sha256:"
        + hashlib.sha256(
            json.dumps(
                (legacy_lineage, exact_trace.raw_candidate_id),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
    )
    assert exact_trace.evidence_id == legacy_evidence_id
    legacy_content = exact_trace.model_dump(
        mode="json",
        exclude={"execution_lane", "content_sha256"},
    )
    assert (
        exact_trace.content_sha256
        == hashlib.sha256(
            json.dumps(
                legacy_content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
    )
    legacy_exact_payload = exact_trace.model_dump(
        mode="json",
        exclude={"execution_lane"},
    )
    assert (
        read_module.LocalProjectionTrace.model_validate(legacy_exact_payload)
        == exact_trace
    )
    structured_item = next(item for item in fused.evidence if item.lane == "structured")
    structured_trace = structured_item.local_projection_trace
    assert structured_trace is not None
    with pytest.raises(ValidationError, match="raw_candidate_id"):
        read_module.LocalProjectionTrace.model_validate(
            {
                **structured_trace.model_dump(mode="json"),
                "execution_lane": "exact",
            }
        )

    assert len(exact_results) == 1
    cross_lane_payload = exact_results[0].model_dump(mode="json")
    for item in cross_lane_payload["items"]:
        item["lane"] = "structured"
    for candidate in cross_lane_payload["candidates"]:
        candidate["lane"] = "structured"
        for item in candidate["evidence"]:
            item["lane"] = "structured"
    cross_lane_result = read_module.RetrievalLaneResult.model_validate(
        cross_lane_payload
    )
    assert all(
        candidate.lane == "structured"
        and all(item.lane == "structured" for item in candidate.evidence)
        and all(
            item.local_projection_trace is not None
            and item.local_projection_trace.execution_lane == "exact"
            for item in candidate.evidence
        )
        for candidate in cross_lane_result.candidates
    )
    cross_lane_service = read_module.create_ephemeral_knowledge_read(
        universal_web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=1,
        ),
        lane_adapters={"structured": lambda _: cross_lane_result},
        web_search=lambda _: read_module.RetrievalLaneResult(),
        clock=lambda: NOW,
    )
    cross_lane_evidence = cross_lane_service.execute(plan)
    assert cross_lane_evidence.items == ()
    assert cross_lane_evidence.fused_candidates == ()
    assert cross_lane_evidence.entity_handles == ()
    structured_cross_lane_trace = next(
        trace for trace in cross_lane_evidence.traces if trace.lane == "structured"
    )
    assert structured_cross_lane_trace.status == "unavailable"
    assert structured_cross_lane_trace.failure_kind == "invalid_output"

    assert len(combined.entity_handles) == 1
    assert combined.entity_handles[0].canonical_id == "company-robotics"
    assert len(combined.candidate_traces) == 2
    assert all(trace.disposition == "selected" for trace in combined.candidate_traces)
    assert all(
        trace.selected_result_id == "company-robotics"
        for trace in combined.candidate_traces
    )

    assert {
        name: _file_sha256(bundle.index_target.root / name)
        for name in fixture["target_hashes"]
    } == fixture["target_hashes"]
    assert _file_sha256(fixture["original_milvus"]) == fixture["original_sha256"]


def _s8p1_legacy_ephemeral_plan(read_module: Any) -> Any:
    snapshot_time = datetime(2026, 7, 16, 6, 30, tzinfo=timezone.utc)
    planning_policy = read_module.QueryPlanningPolicy(
        policy_id="planning-policy:s8p1-legacy-snapshot",
        policy_version="query-planning-policy-v1",
        public_domains=PUBLIC_DOMAINS,
        supported_lanes=("exact", "web"),
        supported_relationship_paths=(),
        max_candidates=5,
        max_provider_calls=1,
        max_planning_attempts=1,
    )
    institution_catalog = read_module.InstitutionCatalog(
        catalog_id="institution-catalog:s8p1-legacy-empty",
        catalog_version="institution-catalog-v1",
        release_id=RELEASE_ID,
        entries=(),
    )
    planning_request = read_module.QueryPlanningRequest(
        request_id="query-request:s8p1-legacy-snapshot",
        release_id=RELEASE_ID,
        original_query="Robotics Co",
        as_of=snapshot_time,
    )

    def proposal_provider(value: Any) -> Any:
        return read_module.RecordedPlanningProposal(
            proposal_id="planning-proposal:s8p1-legacy-snapshot",
            request_sha256=value.content_sha256,
            schema_version="retrieval-plan-proposal-v1",
            model_id="recorded-planner-fixture",
            prompt_version="query-plan-prompt-v1",
            behavior_class="A",
            interaction_mode="information_retrieval",
            domains=("company",),
            lanes=("exact", "web"),
            max_candidates=5,
            max_provider_calls=1,
            web_mode="universal",
            max_web_results=5,
        )

    return read_module.create_ephemeral_query_planner(
        planning_policy=planning_policy,
        institution_catalog=institution_catalog,
        proposal_provider=proposal_provider,
    ).plan(planning_request)


def _s8p1_planning_policy(read_module: Any) -> Any:
    return read_module.QueryPlanningPolicy(
        policy_id="planning-policy:s8p1-release-bound",
        policy_version="query-planning-policy-v1",
        public_domains=PUBLIC_DOMAINS,
        supported_lanes=(
            "exact",
            "structured",
            "lexical",
            "vector",
            "relationship",
            "internal_reference",
            "web",
        ),
        supported_relationship_paths=(
            ("technology_company_relationship", "technology_to_company"),
        ),
        max_candidates=20,
        max_provider_calls=2,
        max_planning_attempts=2,
    )


def _s8p1_institution_catalog(read_module: Any) -> Any:
    return read_module.InstitutionCatalog(
        catalog_id="institution-catalog:s8p1-release-bound",
        catalog_version="institution-catalog-v1",
        release_id=RELEASE_ID,
        entries=(
            read_module.InstitutionCatalogEntry(
                canonical_id="institution:sustech",
                canonical_name="南方科技大学",
                aliases=("SUSTech",),
            ),
        ),
    )


def _s8p1_published_release(contracts_module: Any, *, release_id: str) -> Any:
    return contracts_module.PublishedRelease(
        release_id=release_id,
        previous_release_id="accepted-before-s8p1",
        canonical_release_id=release_id,
        published_projection_release_id=release_id,
        index_release_id=release_id,
        state="active",
        changed_at=NOW,
        verification_evidence_ids=("release-verification:s8p1",),
    )


def _s8p1_planning_request(read_module: Any, *, release_id: str = RELEASE_ID) -> Any:
    return read_module.QueryPlanningRequest(
        request_id="query-request:s8p1-release-bound",
        release_id=release_id,
        original_query=(
            "找出SUSTech毕业并在深圳企业担任创始人的人，并比较vision servo路线的代表性企业"
        ),
        as_of=NOW,
        enumeration_context=read_module.EnumerationPlanningContext(
            requested=True,
            scope="representative Companies related to one accepted Technology route",
            as_of=NOW,
            finite_universe=None,
            required_member_ids=(),
        ),
    )


def _s8p1_proposal(read_module: Any, value: Any) -> Any:
    return read_module.RecordedPlanningProposal(
        proposal_id="planning-proposal:s8p1-release-bound",
        request_sha256=value.content_sha256,
        schema_version="retrieval-plan-proposal-v1",
        model_id="recorded-planner-fixture",
        prompt_version="query-plan-prompt-v1",
        behavior_class="E",
        interaction_mode="information_retrieval",
        domains=("company",),
        lanes=("internal_reference", "relationship", "web"),
        relationship_paths=(
            read_module.RelationshipPathProposal(
                relationship_type_id="technology_company_relationship",
                direction="technology_to_company",
                source_type="technology_route",
                target_type="company",
            ),
        ),
        max_candidates=20,
        max_provider_calls=1,
        enumeration_mode="representative",
        internal_reference_targets=("person", "technology_route"),
        web_mode="universal",
        max_web_results=5,
    )


def _canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def test_release_scoped_query_planner_binds_replayed_person_technology_and_catalog(
    request: pytest.FixtureRequest,
) -> None:
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    legacy_plan = _s8p1_legacy_ephemeral_plan(read_module)
    assert legacy_plan.content_sha256 == S8P1_LEGACY_PLAN_CONTENT_SHA256
    assert (
        hashlib.sha256(legacy_plan.model_dump_json().encode("utf-8")).hexdigest()
        == S8P1_LEGACY_PLAN_SERIALIZED_SHA256
    )
    release_planner_factory = _isolated_release_query_planner_factory()
    fixture = request.getfixturevalue("isolated_lookup_target_bundle")
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    bundle = fixture["bundle"]
    index_request = fixture["index_request"]
    published = _s8p1_published_release(contracts_module, release_id=RELEASE_ID)
    institution_catalog = _s8p1_institution_catalog(read_module)
    planning_policy = _s8p1_planning_policy(read_module)
    planning_request = _s8p1_planning_request(read_module)
    provider_requests: list[Any] = []

    def proposal_provider(value: Any) -> Any:
        provider_requests.append(value)
        return _s8p1_proposal(read_module, value)

    planner = release_planner_factory(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=institution_catalog,
        planning_policy=planning_policy,
        proposal_provider=proposal_provider,
    )
    plan = planner.plan(planning_request)
    assert provider_requests == [planning_request]
    assert plan.release_id == RELEASE_ID
    assert plan.release_binding is not None
    binding = plan.release_binding
    candidate_result = index_request.candidate_projection_result
    internal_result = (
        index_request.candidate_projection_request.internal_reference_projection_result
    )
    assert binding.release_id == RELEASE_ID
    assert binding.publication_state == "active"
    assert binding.published_release_sha256 == _canonical_json_sha256(
        published.model_dump(mode="json")
    )
    assert binding.publication_verification_evidence_ids == (
        "release-verification:s8p1",
    )
    assert binding.manifest_sha256 == bundle.manifest.manifest_sha256
    assert binding.index_projection_request_sha256 == _canonical_json_sha256(
        index_request.model_dump(mode="json")
    )
    assert binding.index_projection_result_sha256 == bundle.index_result.content_sha256
    assert binding.candidate_projection_result_sha256 == candidate_result.content_sha256
    assert (
        binding.internal_reference_projection_result_sha256
        == internal_result.content_sha256
    )
    assert binding.institution_catalog_sha256 == institution_catalog.content_sha256
    assert binding.planning_policy_sha256 == planning_policy.content_sha256
    assert plan.content_sha256 != legacy_plan.content_sha256

    institution_slot = next(
        slot for slot in plan.institution_slots if slot.resolution_state == "resolved"
    )
    assert institution_slot.canonical_id == "institution:sustech"
    assert institution_slot.catalog_sha256 == institution_catalog.content_sha256
    assert institution_slot.occurrences[0].raw_text == "SUSTech"
    person_query = next(
        item
        for item in plan.internal_reference_queries
        if item.reference_type == "person"
    )
    person_projection = candidate_result.person_projections[0]
    resolved_anchor_ids = tuple(
        sorted(reference.source_anchor_id for reference in person_projection.references)
    )
    expected_person_fact_evidence = {
        ("education", "南方科技大学"): (
            "assertion:company-robotics:personnel_education",
            "assertion:professor-ada:education_history",
        ),
        ("company_role", "founder"): (
            "assertion:company-robotics:key_personnel",
            "assertion:company-robotics:personnel_work_experience",
        ),
        ("geography", "深圳"): ("assertion:company-robotics:geography",),
    }
    assert person_query.eligible_reference_ids == (
        person_projection.canonical_person_identity_id,
    )
    person_facts = {
        (fact.field, fact.value): fact.evidence_ids
        for fact in person_query.typed_filters
    }
    assert person_facts == expected_person_fact_evidence
    expected_typed_facts = tuple(
        read_module.InternalReferenceFact(
            field=field,
            value=value,
            evidence_ids=evidence_ids,
        )
        for (field, value), evidence_ids in expected_person_fact_evidence.items()
    )
    expected_person_records = [
        read_module.PersonReferenceRecord(
            reference_id=person_projection.canonical_person_identity_id,
            release_id=RELEASE_ID,
            resolution_state="resolved",
            canonical_person_id=person_projection.canonical_person_identity_id,
            public_domain_evidence_ids=resolved_anchor_ids,
            typed_facts=expected_typed_facts,
        )
    ]
    expected_unresolved_evidence = {
        reference.reference_id: (reference.source_anchor_id,)
        for reference in internal_result.unresolved_person_references
    }
    expected_person_records.extend(
        read_module.PersonReferenceRecord(
            reference_id=reference.reference_id,
            release_id=RELEASE_ID,
            resolution_state="unresolved",
            canonical_person_id=None,
            public_domain_evidence_ids=(reference.source_anchor_id,),
            typed_facts=(),
        )
        for reference in internal_result.unresolved_person_references
    )
    expected_person_records.sort(key=lambda record: record.reference_id)
    assert person_query.originating_public_evidence_ids == resolved_anchor_ids
    assert person_query.nonmatching_reference_traces == ()
    assert {
        trace.reference_id: trace.evidence_ids
        for trace in person_query.unresolved_reference_traces
    } == expected_unresolved_evidence
    assert all(
        not trace.eligible_for_identity_filter and not trace.eligible_for_traversal
        for trace in person_query.unresolved_reference_traces
    )
    assert person_query.reference_content_sha256s == tuple(
        (record.reference_id, record.content_sha256)
        for record in expected_person_records
    )
    assert person_query.public_population is False

    technology_query = next(
        item
        for item in plan.internal_reference_queries
        if item.reference_type == "technology_route"
    )
    route_projection = candidate_result.technology_route_projections[0]
    expected_definition_evidence = next(
        lineage.supporting_assertion_ids
        for lineage in route_projection.field_lineage
        if lineage.field_path == "technology.definition"
    )
    assert technology_query.canonical_route_ids == (
        route_projection.canonical_technology_identity_id,
    )
    assert technology_query.resolved_aliases == (
        (
            "vision servo",
            route_projection.canonical_technology_identity_id,
        ),
    )
    assert technology_query.definition_evidence_ids == expected_definition_evidence
    expected_route_record = read_module.TechnologyRouteRecord(
        reference_id=route_projection.canonical_technology_identity_id,
        release_id=RELEASE_ID,
        canonical_route_id=route_projection.canonical_technology_identity_id,
        canonical_name=route_projection.preferred_name,
        aliases=route_projection.aliases,
        definition_evidence_ids=expected_definition_evidence,
    )
    assert expected_route_record.content_sha256 == (
        "cffb4b03c37f7f658eb5ea303de6b80d9f95d925ac7769ef6316cdefe5f6b256"
    )
    assert technology_query.route_content_sha256s == (
        (
            route_projection.canonical_technology_identity_id,
            expected_route_record.content_sha256,
        ),
    )
    assert technology_query.public_population is False
    assert set(plan.domains) <= set(PUBLIC_DOMAINS)

    cross_release_binding = read_module.PlanningReleaseBinding.model_validate(
        {
            **binding.model_dump(mode="json", exclude={"content_sha256"}),
            "release_id": "candidate-cross-release",
        }
    )
    with pytest.raises(ValidationError, match="release binding.*release"):
        read_module.RetrievalPlan.model_validate(
            {
                **plan.model_dump(mode="json", exclude={"content_sha256"}),
                "release_binding": cross_release_binding.model_dump(mode="json"),
            }
        )
    cross_catalog_lane = plan.lane_queries[0].model_copy(
        update={"catalog_sha256": "f" * 64}
    )
    with pytest.raises(ValidationError, match="catalog"):
        read_module.RetrievalPlan.model_validate(
            {
                **plan.model_dump(mode="json", exclude={"content_sha256"}),
                "lane_queries": (
                    cross_catalog_lane,
                    *plan.lane_queries[1:],
                ),
            }
        )
    cross_catalog_slot = plan.institution_slots[0].model_copy(
        update={"catalog_sha256": "e" * 64}
    )
    with pytest.raises(ValidationError, match="institution slot.*catalog"):
        read_module.RetrievalPlan.model_validate(
            {
                **plan.model_dump(mode="json", exclude={"content_sha256"}),
                "institution_slots": (
                    cross_catalog_slot,
                    *plan.institution_slots[1:],
                ),
            }
        )
    cross_release_slot = plan.institution_slots[0].model_copy(
        update={"release_id": "candidate-cross-release"}
    )
    with pytest.raises(ValidationError, match="institution slot.*catalog"):
        read_module.RetrievalPlan.model_validate(
            {
                **plan.model_dump(mode="json", exclude={"content_sha256"}),
                "institution_slots": (
                    cross_release_slot,
                    *plan.institution_slots[1:],
                ),
            }
        )
    cross_release_internal_query = plan.internal_reference_queries[0].model_copy(
        update={"release_id": "candidate-cross-release"}
    )
    with pytest.raises(ValidationError, match="internal reference query.*release"):
        read_module.RetrievalPlan.model_validate(
            {
                **plan.model_dump(mode="json", exclude={"content_sha256"}),
                "internal_reference_queries": (
                    cross_release_internal_query,
                    *plan.internal_reference_queries[1:],
                ),
            }
        )
    public_internal_query = plan.internal_reference_queries[0].model_copy(
        update={"public_population": True}
    )
    with pytest.raises(ValidationError, match="internal reference query.*public"):
        read_module.RetrievalPlan.model_validate(
            {
                **plan.model_dump(mode="json", exclude={"content_sha256"}),
                "internal_reference_queries": (
                    public_internal_query,
                    *plan.internal_reference_queries[1:],
                ),
            }
        )
    assert "release_binding" not in legacy_plan.model_dump(mode="json")


def test_s8p2_release_bound_planner_captures_open_assessment_intent_and_user_criteria(
    request: pytest.FixtureRequest,
) -> None:
    assessment_intent_type = _s8p2_assessment_intent_type()
    release_planner_factory = _isolated_release_query_planner_factory()
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    if "material_parts" not in read_module.RecordedPlanningProposal.model_fields:
        raise _MissingS8P2MaterialPartsContract(
            "RecordedPlanningProposal cannot carry expected material answer parts"
        )
    fixture = request.getfixturevalue("isolated_lookup_target_bundle")
    answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    assert assessment_intent_type is read_module.AssessmentIntent
    assert answer_module.AssessmentIntent is read_module.AssessmentIntent

    planning_request = _s8p1_planning_request(read_module)
    legacy_proposal = _s8p1_proposal(read_module, planning_request)
    assert legacy_proposal.content_sha256 == S8P2_LEGACY_PROPOSAL_CONTENT_SHA256
    assert (
        hashlib.sha256(legacy_proposal.model_dump_json().encode("utf-8")).hexdigest()
        == S8P2_LEGACY_PROPOSAL_SERIALIZED_SHA256
    )
    assert "assessment_intent" not in legacy_proposal.model_dump(mode="json")

    intent = assessment_intent_type(
        kind=" route_scale_readiness ",
        user_criteria=(" 公开部署规模 ", "维护成本"),
    )
    assert intent.kind == "route_scale_readiness"
    assert intent.user_criteria == ("公开部署规模", "维护成本")

    material_parts = (
        read_module.MaterialQuestionPart(
            part_id="material-part:public-deployment-scale",
            text="What public deployment scale is evidenced for the route?",
            subject_id="technology-route:visual-servoing",
            predicate="public_deployment_scale",
            requested_value="公开部署规模",
        ),
        read_module.MaterialQuestionPart(
            part_id="material-part:maintenance-cost",
            text="What maintenance cost is evidenced for the route?",
            subject_id="technology-route:visual-servoing",
            predicate="maintenance_cost",
            requested_value="维护成本",
        ),
    )

    proposal_payload = legacy_proposal.model_dump(
        mode="json",
        exclude={"content_sha256"},
    )
    proposal_payload["assessment_intent"] = intent.model_dump(mode="json")
    proposal_payload["material_parts"] = [
        part.model_dump(mode="json") for part in material_parts
    ]
    recorded_proposals: list[Any] = []

    def intent_provider(value: Any) -> Any:
        assert value == planning_request
        proposal = read_module.RecordedPlanningProposal.model_validate(proposal_payload)
        recorded_proposals.append(proposal)
        return proposal

    bundle = fixture["bundle"]
    index_request = fixture["index_request"]
    published = _s8p1_published_release(contracts_module, release_id=RELEASE_ID)
    institution_catalog = _s8p1_institution_catalog(read_module)
    planning_policy = _s8p1_planning_policy(read_module)
    assert planning_policy.content_sha256 == S8P2_LEGACY_PLANNING_POLICY_CONTENT_SHA256
    assert "official_web_domains" not in planning_policy.model_dump(mode="json")
    factory_kwargs = {
        "release_bundle": bundle,
        "published_release": published,
        "index_projection_request": index_request,
        "release_institution_catalog": institution_catalog,
        "planning_policy": planning_policy,
    }
    baseline_plan = release_planner_factory(
        **factory_kwargs,
        proposal_provider=lambda value: _s8p1_proposal(read_module, value),
    ).plan(planning_request)
    plan = release_planner_factory(
        **factory_kwargs,
        proposal_provider=intent_provider,
    ).plan(planning_request)

    assert len(recorded_proposals) == 1
    recorded = recorded_proposals[0]
    assert recorded.assessment_intent == intent
    assert recorded.material_parts == material_parts
    assert recorded.content_sha256 != legacy_proposal.content_sha256
    assert plan.assessment_intent == intent
    assert plan.material_parts == material_parts
    assert plan.planning_trace.proposal_id == recorded.proposal_id
    assert plan.planning_trace.proposal_sha256 == recorded.content_sha256
    assert plan.release_binding == baseline_plan.release_binding
    assert plan.institution_slots == baseline_plan.institution_slots
    assert plan.internal_reference_queries == baseline_plan.internal_reference_queries
    assert plan.unresolved_technology_terms == baseline_plan.unresolved_technology_terms
    assert plan.enumeration_policy == baseline_plan.enumeration_policy
    assert plan.domains == baseline_plan.domains
    assert plan.lanes == baseline_plan.lanes
    assert plan.lane_queries == baseline_plan.lane_queries
    assert plan.content_sha256 != baseline_plan.content_sha256
    assert "assessment_intent" not in baseline_plan.model_dump(mode="json")
    assert plan.model_dump(mode="json")["assessment_intent"] == {
        "kind": "route_scale_readiness",
        "user_criteria": ["公开部署规模", "维护成本"],
    }
    assert plan.model_dump(mode="json")["material_parts"] == [
        part.model_dump(mode="json") for part in material_parts
    ]
    assert (
        read_module.RetrievalPlan.model_validate(plan.model_dump(mode="json")) == plan
    )

    for invalid_intent in (
        {"kind": " ", "user_criteria": ()},
        {"kind": "route_scale_readiness", "user_criteria": (" ",)},
        {
            "kind": "route_scale_readiness",
            "user_criteria": ("维护成本", " 维护成本 "),
        },
    ):
        with pytest.raises(ValidationError):
            assessment_intent_type.model_validate(invalid_intent)

    duplicate_material_parts = dict(proposal_payload)
    duplicate_material_parts["material_parts"] = [
        material_parts[0].model_dump(mode="json"),
        material_parts[0].model_dump(mode="json"),
    ]
    duplicate_parts_planner = release_planner_factory(
        **factory_kwargs,
        proposal_provider=lambda _: duplicate_material_parts,
    )
    with pytest.raises(read_module.InvalidRetrievalPlanError) as caught:
        duplicate_parts_planner.plan(planning_request)
    assert caught.value.reason_code == "invalid_planning_proposal"

    non_information_payload = dict(proposal_payload)
    non_information_payload.update(
        {
            "behavior_class": "F",
            "interaction_mode": "ordinary_refusal",
            "domains": [],
            "lanes": [],
            "web_mode": None,
            "allowed_web_domains": [],
            "max_web_results": 0,
        }
    )
    non_information_planner = release_planner_factory(
        **factory_kwargs,
        proposal_provider=lambda _: non_information_payload,
    )
    with pytest.raises(read_module.InvalidRetrievalPlanError) as caught:
        non_information_planner.plan(planning_request)
    assert caught.value.reason_code == "invalid_planning_proposal"

    hostile_intent = assessment_intent_type.model_construct(
        kind=" ",
        user_criteria=("维护成本",),
    )
    hostile_proposal_payload = {
        name: getattr(recorded, name)
        for name in read_module.RecordedPlanningProposal.model_fields
        if name != "content_sha256"
    }
    hostile_proposal_payload["assessment_intent"] = hostile_intent
    hostile_same_class = read_module.RecordedPlanningProposal.model_construct(
        **hostile_proposal_payload
    )
    hostile_planner = release_planner_factory(
        **factory_kwargs,
        proposal_provider=lambda _: hostile_same_class,
    )
    with pytest.raises(read_module.InvalidRetrievalPlanError) as caught:
        hostile_planner.plan(planning_request)
    assert caught.value.reason_code == "invalid_planning_proposal"

    legacy_plan = _s8p1_legacy_ephemeral_plan(read_module)
    assert legacy_plan.content_sha256 == S8P1_LEGACY_PLAN_CONTENT_SHA256
    assert (
        hashlib.sha256(legacy_plan.model_dump_json().encode("utf-8")).hexdigest()
        == S8P1_LEGACY_PLAN_SERIALIZED_SHA256
    )
    assert "assessment_intent" not in legacy_plan.model_dump(mode="json")


def test_release_scoped_query_planner_rejects_release_graph_catalog_and_policy_crosswires_before_provider(
    request: pytest.FixtureRequest,
) -> None:
    release_planner_factory = _isolated_release_query_planner_factory()
    fixture = request.getfixturevalue("isolated_lookup_target_bundle")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    release_module = _isolated_release_publication_module()
    index_module = _index_projection_module()
    bundle = fixture["bundle"]
    published = _s8p1_published_release(contracts_module, release_id=RELEASE_ID)
    index_request = fixture["index_request"]
    institution_catalog = _s8p1_institution_catalog(read_module)
    planning_policy = _s8p1_planning_policy(read_module)
    provider_requests: list[Any] = []

    def forbidden_provider(value: Any) -> Any:
        provider_requests.append(value)
        raise AssertionError("proposal provider must not run for invalid release input")

    factory_kwargs = {
        "release_bundle": bundle,
        "published_release": published,
        "index_projection_request": index_request,
        "release_institution_catalog": institution_catalog,
        "planning_policy": planning_policy,
        "proposal_provider": forbidden_provider,
    }

    cross_release = _s8p1_published_release(
        contracts_module,
        release_id="candidate-s8p1-cross-release",
    )
    with pytest.raises(ValueError, match="release"):
        release_planner_factory(
            **{**factory_kwargs, "published_release": cross_release}
        )

    person_request, person_result = _resolved_person_candidate_bundle()
    person_index_request = _index_projection_request(
        index_module,
        person_request,
        person_result,
        exact_limitation_identity_id="company-robotics",
    )
    with pytest.raises(ValueError, match="replay|graph|bundle"):
        release_planner_factory(
            **{
                **factory_kwargs,
                "index_projection_request": person_index_request,
            }
        )

    technology_request, technology_result = _technology_candidate_bundle()
    technology_index_request = _index_projection_request(
        index_module,
        technology_request,
        technology_result,
        exact_limitation_identity_id="company-robotics",
    )
    with pytest.raises(ValueError, match="replay|graph|bundle"):
        release_planner_factory(
            **{
                **factory_kwargs,
                "index_projection_request": technology_index_request,
            }
        )

    empty_catalog = read_module.InstitutionCatalog(
        catalog_id="institution-catalog:s8p1-empty",
        catalog_version="institution-catalog-v1",
        release_id=RELEASE_ID,
        entries=(),
    )
    with pytest.raises(ValueError, match="institution catalog"):
        release_planner_factory(
            **{
                **factory_kwargs,
                "release_institution_catalog": empty_catalog,
            }
        )
    missing_alias_catalog = read_module.InstitutionCatalog(
        catalog_id="institution-catalog:s8p1-missing-alias",
        catalog_version="institution-catalog-v1",
        release_id=RELEASE_ID,
        entries=(
            read_module.InstitutionCatalogEntry(
                canonical_id="institution:sustech",
                canonical_name="南方科技大学",
                aliases=(),
            ),
        ),
    )
    with pytest.raises(ValueError, match="institution catalog"):
        release_planner_factory(
            **{
                **factory_kwargs,
                "release_institution_catalog": missing_alias_catalog,
            }
        )
    invented_alias_catalog = read_module.InstitutionCatalog(
        catalog_id="institution-catalog:s8p1-invented-alias",
        catalog_version="institution-catalog-v1",
        release_id=RELEASE_ID,
        entries=(
            read_module.InstitutionCatalogEntry(
                canonical_id="institution:sustech",
                canonical_name="南方科技大学",
                aliases=("Invented SUSTech alias", "SUSTech"),
            ),
        ),
    )
    with pytest.raises(ValueError, match="institution catalog"):
        release_planner_factory(
            **{
                **factory_kwargs,
                "release_institution_catalog": invented_alias_catalog,
            }
        )
    shared_index_request, shared_index_result, shared_manifest = (
        _task7_7_release_values(
            release_module,
            release_id=RELEASE_ID,
            exact_limitation_identity_id="company-robotics",
            candidate_bundle_factory=lambda: (
                _resolved_person_technology_candidate_bundle(
                    include_shared_institution_alias=True
                )
            ),
        )
    )
    shared_alias_bundle = release_module.IsolatedReleaseBundle(
        manifest=shared_manifest,
        index_result=shared_index_result,
        index_target=bundle.index_target,
    )
    shared_alias_catalog = read_module.InstitutionCatalog(
        catalog_id="institution-catalog:s8p1-shared-alias",
        catalog_version="institution-catalog-v1",
        release_id=RELEASE_ID,
        entries=(
            read_module.InstitutionCatalogEntry(
                canonical_id="institution:shared-sustech",
                canonical_name="SUSTech",
            ),
            read_module.InstitutionCatalogEntry(
                canonical_id="institution:sustech",
                canonical_name="南方科技大学",
                aliases=("SUSTech",),
            ),
        ),
    )
    shared_alias_planner = release_planner_factory(
        **{
            **factory_kwargs,
            "release_bundle": shared_alias_bundle,
            "index_projection_request": shared_index_request,
            "release_institution_catalog": shared_alias_catalog,
        }
    )
    assert shared_alias_planner is not None

    fifth_domain_policy = read_module.QueryPlanningPolicy.model_validate(
        {
            **planning_policy.model_dump(mode="json", exclude={"content_sha256"}),
            "public_domains": (*PUBLIC_DOMAINS, "person"),
        }
    )
    with pytest.raises(ValueError, match="public domain"):
        release_planner_factory(
            **{**factory_kwargs, "planning_policy": fifth_domain_policy}
        )
    unsupported_lane_policy = read_module.QueryPlanningPolicy.model_validate(
        {
            **planning_policy.model_dump(mode="json", exclude={"content_sha256"}),
            "supported_lanes": (*planning_policy.supported_lanes, "sql"),
        }
    )
    with pytest.raises(ValueError, match="lane"):
        release_planner_factory(
            **{**factory_kwargs, "planning_policy": unsupported_lane_policy}
        )

    stale_manifest = bundle.manifest.model_copy(
        update={"parser_versions": {"historical": "tampered-parser-v2"}}
    )
    stale_manifest_bundle = release_module.IsolatedReleaseBundle(
        manifest=stale_manifest,
        index_result=bundle.index_result,
        index_target=bundle.index_target,
    )
    with pytest.raises(ValueError, match="manifest.*hash"):
        release_planner_factory(
            **{**factory_kwargs, "release_bundle": stale_manifest_bundle}
        )

    planner = release_planner_factory(**factory_kwargs)
    with pytest.raises(ValueError, match="planning request.*release"):
        planner.plan(
            _s8p1_planning_request(
                read_module,
                release_id="candidate-s8p1-cross-release",
            )
        )
    assert provider_requests == []


def test_isolated_index_projection_rejects_unsafe_targets_before_client_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolated = _isolated_index_projection_module()
    repository_root = Path(__file__).resolve().parents[4]
    evidence_root = (
        repository_root / ".agents" / "runs" / "rebuild-canonical-v2-knowledge-platform"
    )
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    client_opens: list[Path] = []

    def _unexpected_open(path: Path) -> None:
        client_opens.append(path)
        raise AssertionError("unsafe target must fail before Milvus client open")

    monkeypatch.setattr(isolated, "_open_milvus_client", _unexpected_open)
    with pytest.raises(isolated.IsolatedIndexTargetSafetyError, match="absolute"):
        isolated.prepare_isolated_index_target(
            root=Path("relative/candidate-index"),
            target_id="relative-target",
            release_id=RELEASE_ID,
            backup_gate_root=evidence_root,
            forbidden_milvus_paths=(original_milvus,),
        )
    with pytest.raises(
        isolated.IsolatedIndexTargetSafetyError, match="original|exists"
    ):
        isolated.prepare_isolated_index_target(
            root=original_milvus,
            target_id="original-target",
            release_id=RELEASE_ID,
            backup_gate_root=evidence_root,
            forbidden_milvus_paths=(original_milvus,),
        )

    target = isolated.prepare_isolated_index_target(
        root=tmp_path / "marked-candidate-index",
        target_id="marked-target",
        release_id=RELEASE_ID,
        backup_gate_root=evidence_root,
        forbidden_milvus_paths=(original_milvus,),
    )
    unmarked_root = tmp_path / "unmarked-candidate-index"
    unmarked_root.mkdir()
    unmarked = target.model_copy(update={"root": unmarked_root})
    with pytest.raises(isolated.IsolatedIndexTargetSafetyError, match="marker"):
        isolated.create_isolated_index_projection_builder(
            target=unmarked,
            backup_gate_root=evidence_root,
            embedding_adapter=isolated.RecordedEmbeddingAdapter(
                model_id="recorded-embedding-v1",
                dimension=32,
            ),
            clock=lambda: NOW,
        )
    with pytest.raises(RebuildWriteGateError, match="missing|unreadable|accepted"):
        isolated.create_isolated_index_projection_builder(
            target=target,
            backup_gate_root=tmp_path / "missing-gate",
            embedding_adapter=isolated.RecordedEmbeddingAdapter(
                model_id="recorded-embedding-v1",
                dimension=32,
            ),
            clock=lambda: NOW,
        )
    assert client_opens == []


def test_isolated_index_projection_rejects_dangling_lookup_symlink_before_client_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _index_projection_module()
    isolated = _isolated_index_projection_module()
    candidate_request, candidate_result = _resolved_person_candidate_bundle()
    request = _index_projection_request(
        module,
        candidate_request,
        candidate_result,
    )
    repository_root = Path(__file__).resolve().parents[4]
    evidence_root = (
        repository_root / ".agents" / "runs" / "rebuild-canonical-v2-knowledge-platform"
    )
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    target = isolated.prepare_isolated_index_target(
        root=tmp_path / "dangling-lookup-target",
        target_id="dangling-lookup-target",
        release_id=RELEASE_ID,
        backup_gate_root=evidence_root,
        forbidden_milvus_paths=(original_milvus,),
    )
    outside_lookup = tmp_path / "outside-target.sqlite3"
    (target.root / "lookup.sqlite3").symlink_to(outside_lookup)
    client_opens: list[Path] = []

    def _unexpected_open(path: Path) -> None:
        client_opens.append(path)
        raise AssertionError("lookup symlink must fail before Milvus client open")

    monkeypatch.setattr(isolated, "_open_milvus_client", _unexpected_open)
    builder = isolated.create_isolated_index_projection_builder(
        target=target,
        backup_gate_root=evidence_root,
        embedding_adapter=isolated.RecordedEmbeddingAdapter(
            model_id="recorded-embedding-v1",
            dimension=32,
        ),
        clock=lambda: NOW,
    )

    with pytest.raises(isolated.IsolatedIndexTargetSafetyError, match="symlink"):
        builder.build(request)
    assert client_opens == []
    assert not outside_lookup.exists()


@pytest.mark.parametrize(
    "overrides",
    (
        {"target_id": ""},
        {"release_id": ""},
    ),
)
def test_isolated_index_target_rejects_invalid_identity_before_marker_write(
    tmp_path: Path,
    overrides: dict[str, str],
) -> None:
    isolated = _isolated_index_projection_module()
    repository_root = Path(__file__).resolve().parents[4]
    evidence_root = (
        repository_root / ".agents" / "runs" / "rebuild-canonical-v2-knowledge-platform"
    )
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    target_root = tmp_path / ("invalid-" + next(iter(overrides)))
    values = {
        "root": target_root,
        "target_id": "valid-target-id",
        "release_id": RELEASE_ID,
        "backup_gate_root": evidence_root,
        "forbidden_milvus_paths": (original_milvus,),
        **overrides,
    }

    with pytest.raises(ValidationError):
        isolated.prepare_isolated_index_target(**values)
    assert not target_root.exists()


@pytest.mark.parametrize("tamper", ("metadata", "vector"))
def test_isolated_index_projection_rejects_physical_point_crosswire(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    module = _index_projection_module()
    isolated = _isolated_index_projection_module()
    candidate_request, candidate_result = _resolved_person_candidate_bundle()
    request = _index_projection_request(
        module,
        candidate_request,
        candidate_result,
    )
    repository_root = Path(__file__).resolve().parents[4]
    evidence_root = (
        repository_root / ".agents" / "runs" / "rebuild-canonical-v2-knowledge-platform"
    )
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    target = isolated.prepare_isolated_index_target(
        root=tmp_path / f"crosswired-{tamper}-target",
        target_id=f"crosswired-{tamper}-target",
        release_id=RELEASE_ID,
        backup_gate_root=evidence_root,
        forbidden_milvus_paths=(original_milvus,),
    )
    real_open = isolated._open_milvus_client

    class _CrosswiredClient:
        def __init__(self, delegate: Any) -> None:
            self._delegate = delegate

        def __getattr__(self, name: str) -> Any:
            return getattr(self._delegate, name)

        def get(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            rows = [dict(row) for row in self._delegate.get(*args, **kwargs)]
            if not rows:
                return rows
            if tamper == "metadata":
                rows[0]["release_id"] = "crosswired-r0"
                rows[0]["projection_id"] = "index:crosswired"
                rows[0]["canonical_object_id"] = "crosswired-object"
                rows[0]["embedded_content_sha256"] = "0" * 64
            else:
                rows[0]["vector"] = [0.0] * 32
            return rows

    def _crosswired_open(path: Path) -> Any:
        return _CrosswiredClient(real_open(path))

    monkeypatch.setattr(isolated, "_open_milvus_client", _crosswired_open)
    builder = isolated.create_isolated_index_projection_builder(
        target=target,
        backup_gate_root=evidence_root,
        embedding_adapter=isolated.RecordedEmbeddingAdapter(
            model_id="recorded-embedding-v1",
            dimension=32,
        ),
        clock=lambda: NOW,
    )

    with pytest.raises(
        module.IndexProjectionIntegrityError,
        match="physical metadata|vector",
    ):
        builder.build(request)


def test_isolated_lookup_readback_requires_receipt_and_scalar_column_parity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _index_projection_module()
    isolated = _isolated_index_projection_module()
    candidate_request, candidate_result = _resolved_person_candidate_bundle()
    request = _index_projection_request(
        module,
        candidate_request,
        candidate_result,
    )
    repository_root = Path(__file__).resolve().parents[4]
    evidence_root = (
        repository_root / ".agents" / "runs" / "rebuild-canonical-v2-knowledge-platform"
    )
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    target = isolated.prepare_isolated_index_target(
        root=tmp_path / "lookup-parity-target",
        target_id="lookup-parity-target",
        release_id=RELEASE_ID,
        backup_gate_root=evidence_root,
        forbidden_milvus_paths=(original_milvus,),
    )
    builder = isolated.create_isolated_index_projection_builder(
        target=target,
        backup_gate_root=evidence_root,
        embedding_adapter=isolated.RecordedEmbeddingAdapter(
            model_id="recorded-embedding-v1",
            dimension=32,
        ),
        clock=lambda: NOW,
    )
    result = builder.build(request)
    receipt = builder.last_materialization_receipt
    assert receipt is not None
    lookup_path = target.root / "lookup.sqlite3"

    with sqlite3.connect(lookup_path) as connection:
        connection.execute("DELETE FROM build_receipt")
    with pytest.raises(module.IndexProjectionIntegrityError, match="receipt"):
        isolated.read_isolated_lookup_documents(target)

    with sqlite3.connect(lookup_path) as connection:
        connection.execute(
            "INSERT INTO build_receipt (release_id, receipt_json) VALUES (?, ?)",
            (receipt.release_id, receipt.model_dump_json()),
        )
        first_document = result.lookup_documents[0]
        connection.execute(
            "UPDATE lookup_document SET release_id = ?, projection_id = ?, "
            "canonical_object_id = ? WHERE document_id = ?",
            (
                "crosswired-r0",
                "lookup:crosswired",
                "crosswired-object",
                first_document.document_id,
            ),
        )
    with pytest.raises(
        module.IndexProjectionIntegrityError,
        match="physical metadata",
    ):
        isolated.read_isolated_lookup_documents(target)

    with sqlite3.connect(lookup_path) as connection:
        connection.execute(
            "UPDATE lookup_document SET release_id = ?, projection_id = ?, "
            "canonical_object_id = ? WHERE document_id = ?",
            (
                first_document.release_id,
                first_document.projection_id,
                first_document.canonical_object_id,
                first_document.document_id,
            ),
        )
        first_manifest = result.expected_lookup_projections[0]
        connection.execute(
            "UPDATE lookup_manifest SET release_id = ? WHERE projection_id = ?",
            ("crosswired-r0", first_manifest.projection_id),
        )
    with pytest.raises(
        module.IndexProjectionIntegrityError,
        match="physical metadata",
    ):
        isolated.read_isolated_lookup_documents(target)

    with sqlite3.connect(lookup_path) as connection:
        connection.execute(
            "UPDATE lookup_manifest SET release_id = ? WHERE projection_id = ?",
            (first_manifest.release_id, first_manifest.projection_id),
        )
        connection.execute(
            "UPDATE build_metadata SET value = 'crosswired-r0' WHERE key = 'release_id'"
        )
    milvus_client_opens: list[Path] = []

    def _unexpected_milvus_open(path: Path) -> Any:
        milvus_client_opens.append(path)
        raise AssertionError("cross-release metadata must fail before Milvus open")

    monkeypatch.setattr(isolated, "_open_milvus_client", _unexpected_milvus_open)
    with pytest.raises(
        module.IndexProjectionIntegrityError,
        match="metadata release",
    ):
        isolated.audit_isolated_index_snapshot(
            target,
            embedding_adapter=isolated.RecordedEmbeddingAdapter(
                model_id="recorded-embedding-v1",
                dimension=32,
            ),
        )
    assert milvus_client_opens == []


def test_index_projection_keeps_technology_as_evidence_anchored_internal_auxiliary() -> (
    None
):
    module = _index_projection_module()
    candidate_request, candidate_result = _technology_candidate_bundle()
    result = module.create_ephemeral_index_projection_builder().build(
        _index_projection_request(
            module,
            candidate_request,
            candidate_result,
        )
    )

    manifests = result.expected_index_projections
    assert len(manifests) == 8
    assert {
        manifest.domain
        for manifest in manifests
        if manifest.projection_scope.value == "public_domain"
    } == set(PUBLIC_DOMAINS)
    assert {
        manifest.reference_type
        for manifest in manifests
        if manifest.projection_scope.value == "internal_auxiliary"
    } == set(INTERNAL_REFERENCE_TYPES)
    assert all(
        manifest.eligibility_policy_version
        == (
            "path-eligibility-v1"
            if manifest.projection_scope.value == "public_domain"
            else "internal-evidence-anchor-v1"
        )
        for manifest in manifests
    )
    assert sum(manifest.point_count for manifest in manifests) == 4
    assert (
        sum(
            manifest.point_count
            for manifest in manifests
            if manifest.domain in {"paper", "patent", "professor"}
            or manifest.reference_type == "person"
        )
        == 0
    )

    public_points = tuple(
        point
        for point in result.points
        if point.projection_scope.value == "public_domain"
    )
    internal_points = tuple(
        point
        for point in result.points
        if point.projection_scope.value == "internal_auxiliary"
    )
    assert len(public_points) == 1
    assert public_points[0].domain == "company"
    assert len(internal_points) == 3
    assert {point.reference_type for point in internal_points} == {
        "technology_concept",
        "technology_route",
    }
    for manifest in manifests:
        owned_points = tuple(
            point
            for point in result.points
            if point.projection_id == manifest.projection_id
        )
        assert len(owned_points) == manifest.point_count
        assert all(
            point.eligibility_policy_version == manifest.eligibility_policy_version
            for point in owned_points
        )
    technology_sources = {
        (projection.reference_type, projection.canonical_technology_identity_id): (
            projection
        )
        for projection in (
            *candidate_result.technology_concept_projections,
            *candidate_result.technology_route_projections,
        )
    }
    for point in internal_points:
        source = technology_sources[(point.reference_type, point.canonical_object_id)]
        assert point.domain is None
        assert point.release_id == RELEASE_ID
        assert point.eligibility_policy_version == "internal-evidence-anchor-v1"
        assert point.source_projection_content_sha256 == source.content_sha256
        assert set(source.source_anchor_ids) <= set(point.source_evidence_ids)

    assert not {
        "person",
        "technology_concept",
        "technology_route",
        "product",
        "industry_brief",
        "product_capability",
    } & {manifest.domain for manifest in manifests if manifest.domain is not None}

    lookup_manifests = result.expected_lookup_projections
    assert result.actual_lookup_projections == lookup_manifests
    assert len(lookup_manifests) == 7
    assert sum(item.document_count for item in lookup_manifests) == 4
    assert {
        item.domain
        for item in lookup_manifests
        if item.projection_scope.value == "public_domain"
    } == set(PUBLIC_DOMAINS)
    assert {
        item.reference_type
        for item in lookup_manifests
        if item.projection_scope.value == "internal_auxiliary"
    } == set(INTERNAL_REFERENCE_TYPES)
    technology_lookup_documents = tuple(
        item
        for item in result.lookup_documents
        if item.reference_type in {"technology_concept", "technology_route"}
    )
    assert len(technology_lookup_documents) == 3
    assert {item.reference_type for item in technology_lookup_documents} == {
        "technology_concept",
        "technology_route",
    }
    for document in technology_lookup_documents:
        source = technology_sources[
            (document.reference_type, document.canonical_object_id)
        ]
        assert document.domain is None
        assert document.release_id == RELEASE_ID
        assert document.path == "exact_lookup"
        assert document.eligibility_policy_version == "internal-evidence-anchor-v1"
        assert document.source_projection_content_sha256 == source.content_sha256
        assert set(source.source_anchor_ids) <= set(document.source_evidence_ids)
    assert not {
        "person",
        "technology_concept",
        "technology_route",
        "product",
        "industry_brief",
        "product_capability",
    } & {
        manifest.domain for manifest in lookup_manifests if manifest.domain is not None
    }


def test_index_projection_derives_full_rebuild_admission_from_prior_versions() -> None:
    module = _index_projection_module()
    candidate_request, candidate_result = _resolved_person_candidate_bundle()
    builder = module.create_ephemeral_index_projection_builder()
    initial_incremental = _index_projection_request(
        module,
        candidate_request,
        candidate_result,
        build_mode="incremental",
    )

    with pytest.raises(module.FullRebuildRequiredError, match="full rebuild"):
        builder.build(initial_incremental)

    initial = builder.build(
        initial_incremental.model_copy(update={"build_mode": "full"})
    )
    assert all(
        manifest.full_rebuild is True for manifest in initial.expected_index_projections
    )
    assert "initial_release" in {
        reason
        for decision in initial.rebuild_decisions
        for reason in decision.reason_codes
    }
    prior_snapshot = initial.policy_snapshot.model_copy(
        update={"release_id": "accepted-r0"}
    )

    changed_cases = (
        (
            {"vector_schema_version": "canonical-v2-vector-schema-v2"},
            "schema_version_changed",
        ),
        ({"embedding_model": "recorded-embedding-v2"}, "embedding_model_changed"),
        ({"path_policy_version": "path-eligibility-v2"}, "eligibility_changed"),
    )
    for changes, expected_reason in changed_cases:
        incremental = _index_projection_request(
            module,
            candidate_request,
            candidate_result,
            build_mode="incremental",
            prior_accepted_snapshot=prior_snapshot,
            **changes,
        )
        with pytest.raises(module.FullRebuildRequiredError, match="full rebuild"):
            builder.build(incremental)

        full = builder.build(incremental.model_copy(update={"build_mode": "full"}))
        assert all(
            manifest.full_rebuild is True
            for manifest in full.expected_index_projections
        )
        assert expected_reason in {
            reason
            for decision in full.rebuild_decisions
            for reason in decision.reason_codes
        }


def _task7_7_database_target(
    module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    database_url = os.environ.get("CANONICAL_V2_TEST_DATABASE_URL")
    expected_database = os.environ.get("CANONICAL_V2_TEST_EXPECTED_DATABASE")
    target_kind = os.environ.get("CANONICAL_V2_TEST_TARGET_KIND")
    backup_gate_root = os.environ.get("CANONICAL_V2_TEST_BACKUP_GATE_ROOT")
    if not all((database_url, expected_database, target_kind, backup_gate_root)):
        pytest.skip(
            "Task 7.7 isolated publication requires all four explicit "
            "CANONICAL_V2_TEST_* settings"
        )
    assert database_url is not None
    assert expected_database is not None
    assert target_kind is not None
    assert backup_gate_root is not None
    assert target_kind == "disposable"
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://miroflow:do-not-use@localhost:15432/miroflow_real",
    )
    return module.prepare_isolated_release_database_target(
        database_url=database_url,
        expected_database=expected_database,
        target_kind=target_kind,
        backup_gate_root=Path(backup_gate_root),
    )


def _task7_7_psycopg_dsn(database_url: str) -> str:
    return (
        make_url(database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


def _task7_7_release_values(
    module: Any,
    *,
    release_id: str,
    exact_limitation_identity_id: str | None = None,
    semantic_limitation_identity_id: str | None = None,
    relationship_limitation_identity_id: str | None = None,
    relationship_excluded_identity_id: str | None = None,
    candidate_bundle_factory: Callable[[], tuple[Any, Any]] | None = None,
    relationship_projection_pair: tuple[Any, Any] | None = None,
    exact_index_projection_request: Any | None = None,
) -> tuple[Any, Any, Any]:
    global RELEASE_ID

    prior_fixture_release_id = RELEASE_ID
    RELEASE_ID = release_id
    try:
        index_module = _index_projection_module()
        knowledge_module = import_module("src.data_agents.canonical_v2.knowledge_build")
        contracts_module = import_module("src.data_agents.canonical_v2.contracts")
        candidate_request, candidate_result = (
            candidate_bundle_factory or _resolved_person_candidate_bundle
        )()
        if exact_index_projection_request is None:
            index_request = _index_projection_request(
                index_module,
                candidate_request,
                candidate_result,
                exact_limitation_identity_id=exact_limitation_identity_id,
                semantic_limitation_identity_id=semantic_limitation_identity_id,
                relationship_limitation_identity_id=(
                    relationship_limitation_identity_id
                ),
                relationship_excluded_identity_id=relationship_excluded_identity_id,
            )
        else:
            if any(
                value is not None
                for value in (
                    exact_limitation_identity_id,
                    semantic_limitation_identity_id,
                    relationship_limitation_identity_id,
                    relationship_excluded_identity_id,
                )
            ):
                raise AssertionError(
                    "exact index authority cannot mix fixture limitation overrides"
                )
            index_request = index_module.IndexProjectionRequest.model_validate(
                exact_index_projection_request.model_dump(mode="python")
            )
            assert index_request.candidate_projection_request == candidate_request
            assert index_request.candidate_projection_result == candidate_result
        index_result = index_module.create_ephemeral_index_projection_builder().build(
            index_request
        )
        object_count = sum(
            len(group)
            for group in (
                candidate_result.public_domain_projections,
                candidate_result.person_projections,
                candidate_result.technology_concept_projections,
                candidate_result.technology_route_projections,
            )
        )
        if relationship_projection_pair is None:
            relationship_set = contracts_module.ManifestSection(
                section_id="relationships",
                release_id=release_id,
                version="canonical-v2-s7g-relationships-v1",
                record_count=0,
                content_sha256=hashlib.sha256(
                    f"{release_id}:relationships".encode("utf-8")
                ).hexdigest(),
            )
        else:
            relationship_request, relationship_result = relationship_projection_pair
            assert relationship_request.release_id == release_id
            assert relationship_result.release_id == release_id
            relationship_set = contracts_module.ManifestSection(
                section_id="relationships",
                release_id=release_id,
                version=relationship_result.projection_schema_version,
                record_count=len(relationship_result.current_relationships),
                content_sha256=relationship_result.content_sha256,
            )
        materialization = {
            "decision_set": contracts_module.ManifestSection(
                section_id="decisions",
                release_id=release_id,
                version="canonical-v2-s7g-decision-v1",
                record_count=1,
                content_sha256=candidate_result.content_sha256,
            ),
            "object_sets": (
                contracts_module.ManifestSection(
                    section_id="objects:projection-bundle",
                    release_id=release_id,
                    version="canonical-v2-s7g-objects-v1",
                    record_count=object_count,
                    content_sha256=candidate_result.content_sha256,
                ),
            ),
            "relationship_set": relationship_set,
            "eligibility_sets": (
                contracts_module.ManifestSection(
                    section_id="eligibility:semantic_recall",
                    release_id=release_id,
                    version="path-eligibility-v1",
                    record_count=len(index_result.points),
                    content_sha256=index_result.content_sha256,
                ),
            ),
            "published_projections": candidate_result.published_projections,
            "expected_index_projections": index_result.expected_index_projections,
        }
        candidate_store: dict[str, Any] = {}
        manifest_store: dict[str, Any] = {}
        builder = knowledge_module.create_ephemeral_knowledge_build(
            materialize=lambda _: materialization,
            candidate_store=candidate_store,
            manifest_store=manifest_store,
            failure_store={},
            active_release_state={
                "canonical_release_id": "accepted-bootstrap",
                "published_projection_release_id": "accepted-bootstrap",
                "index_release_id": "accepted-bootstrap",
            },
            clock=lambda: NOW,
        )
        builder.build(
            knowledge_module.BuildCandidateRequest(
                run_id=f"build-{release_id}",
                candidate_release_id=release_id,
                source_batch_ids=("accepted-s2b-source-batch",),
                parser_versions={"historical": "parser-v1"},
                policy_versions={"eligibility": "path-eligibility-v1"},
                model_versions={"embedding": "recorded-embedding-v1"},
            )
        )
        return index_request, index_result, manifest_store[release_id]
    finally:
        RELEASE_ID = prior_fixture_release_id


def _task7_7_physical_release_bundle(
    module: Any,
    *,
    root: Path,
    target_id: str,
    release_id: str,
    candidate_bundle_factory: Callable[[], tuple[Any, Any]] | None = None,
    relationship_projection_pair: tuple[Any, Any] | None = None,
) -> Any:
    isolated = _isolated_index_projection_module()
    index_request, expected_result, manifest = _task7_7_release_values(
        module,
        release_id=release_id,
        candidate_bundle_factory=candidate_bundle_factory,
        relationship_projection_pair=relationship_projection_pair,
    )
    repository_root = Path(__file__).resolve().parents[4]
    evidence_root = (
        repository_root / ".agents" / "runs" / "rebuild-canonical-v2-knowledge-platform"
    )
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    target = isolated.prepare_isolated_index_target(
        root=root,
        target_id=target_id,
        release_id=release_id,
        backup_gate_root=evidence_root,
        forbidden_milvus_paths=(original_milvus,),
    )
    physical_result = isolated.create_isolated_index_projection_builder(
        target=target,
        backup_gate_root=evidence_root,
        embedding_adapter=isolated.RecordedEmbeddingAdapter(
            model_id="recorded-embedding-v1",
            dimension=32,
        ),
        clock=lambda: NOW,
    ).build(index_request)
    assert physical_result == expected_result
    bundle_payload = {
        "manifest": manifest,
        "index_result": physical_result,
        "index_target": target,
    }
    if relationship_projection_pair is not None:
        bundle_payload.update(
            {
                "relationship_projection_request": relationship_projection_pair[0],
                "relationship_projection_result": relationship_projection_pair[1],
            }
        )
    return module.IsolatedReleaseBundle(**bundle_payload)


def _s7k_release_bundle(
    module: Any,
    *,
    tmp_path: Path,
    release_id: str,
    authority: tuple[Any, Any, Any, Any] | None = None,
    include_relationship_authority: bool = True,
    relationship_limitation_identity_id: str | None = None,
    relationship_excluded_identity_id: str | None = None,
    exact_index_projection_request: Any | None = None,
) -> Any:
    isolated = _isolated_index_projection_module()
    candidate_pair = None if authority is None else authority[:2]
    relationship_pair = (
        None
        if authority is None or not include_relationship_authority
        else authority[2:]
    )
    _, index_result, manifest = _task7_7_release_values(
        module,
        release_id=release_id,
        candidate_bundle_factory=(
            None if candidate_pair is None else lambda: candidate_pair
        ),
        relationship_projection_pair=relationship_pair,
        relationship_limitation_identity_id=relationship_limitation_identity_id,
        relationship_excluded_identity_id=relationship_excluded_identity_id,
        exact_index_projection_request=exact_index_projection_request,
    )
    target = isolated.IsolatedIndexTarget(
        root=(tmp_path / release_id).resolve(strict=False),
        target_id=f"s7k-target:{release_id}",
        release_id=release_id,
        forbidden_milvus_paths=(
            Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db"),
        ),
        marker_sha256=hashlib.sha256(
            f"s7k-target:{release_id}".encode("utf-8")
        ).hexdigest(),
    )
    payload: dict[str, Any] = {
        "manifest": manifest,
        "index_result": index_result,
        "index_target": target,
    }
    if relationship_pair is not None:
        payload.update(
            {
                "relationship_projection_request": relationship_pair[0],
                "relationship_projection_result": relationship_pair[1],
            }
        )
    return module.IsolatedReleaseBundle(**payload)


def _s7k_rehashed_manifest(manifest: Any, **updates: Any) -> Any:
    changed = manifest.model_copy(update=updates)
    return changed.model_copy(
        update={
            "manifest_sha256": _canonical_hash(
                changed.model_dump(mode="json", exclude={"manifest_sha256"})
            )
        }
    )


def _s7k_constructed_bundle(module: Any, bundle: Any, **updates: Any) -> Any:
    payload = {
        "manifest": bundle.manifest,
        "index_result": bundle.index_result,
        "index_target": bundle.index_target,
        "relationship_projection_request": (bundle.relationship_projection_request),
        "relationship_projection_result": bundle.relationship_projection_result,
    }
    payload.update(updates)
    return module.IsolatedReleaseBundle.model_construct(**payload)


def test_release_bundle_binds_exact_relationship_publication_authority_before_effects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _isolated_release_publication_module()
    required_fields = {
        "relationship_projection_request",
        "relationship_projection_result",
    }
    missing_fields = required_fields - set(module.IsolatedReleaseBundle.model_fields)
    if missing_fields:
        raise _MissingS7KRelationshipPublicationAuthority(
            "IsolatedReleaseBundle lacks exact relationship authority fields: "
            + ", ".join(sorted(missing_fields))
        )

    candidate_release_id = "candidate-s7k-relationship-authority"
    candidate_authority = _technology_relationship_authority(
        release_id=candidate_release_id
    )
    candidate = _s7k_release_bundle(
        module,
        tmp_path=tmp_path,
        release_id=candidate_release_id,
        authority=candidate_authority,
    )
    relationship_request = candidate.relationship_projection_request
    relationship_result = candidate.relationship_projection_result
    assert relationship_request is not None
    assert relationship_result is not None
    assert len(relationship_result.current_relationships) == 3
    assert {
        item.relationship_type_id for item in relationship_result.current_relationships
    } == {
        "entity_discusses_or_mentions_technology",
        "entity_claims_adoption_of_technology",
        "entity_demonstrates_use_of_technology",
    }
    assert candidate.manifest.relationship_set.section_id == "relationships"
    assert (
        candidate.manifest.relationship_set.version
        == relationship_result.projection_schema_version
    )
    assert candidate.manifest.relationship_set.record_count == 3
    assert (
        candidate.manifest.relationship_set.content_sha256
        == relationship_result.content_sha256
    )
    assert (
        module.IsolatedReleaseBundle.model_validate(candidate.model_dump(mode="json"))
        == candidate
    )

    prior = _s7k_release_bundle(
        module,
        tmp_path=tmp_path,
        release_id="accepted-s7k-legacy-zero",
    )
    assert prior.manifest.relationship_set.record_count == 0
    assert prior.relationship_projection_request is None
    assert prior.relationship_projection_result is None

    zero_authority = _technology_relationship_authority(
        release_id="candidate-s7k-authoritative-zero",
        authoritative_zero=True,
    )
    authoritative_zero = _s7k_release_bundle(
        module,
        tmp_path=tmp_path,
        release_id="candidate-s7k-authoritative-zero",
        authority=zero_authority,
    )
    assert authoritative_zero.relationship_projection_request is not None
    assert authoritative_zero.relationship_projection_result is not None
    assert authoritative_zero.relationship_projection_result.current_relationships == ()
    assert authoritative_zero.manifest.relationship_set.record_count == 0

    same_release_zero_authority = _technology_relationship_authority(
        release_id=candidate_release_id,
        authoritative_zero=True,
    )
    same_release_zero = _s7k_release_bundle(
        module,
        tmp_path=tmp_path,
        release_id=candidate_release_id,
        authority=same_release_zero_authority,
    )

    candidate_payload = candidate.model_dump(mode="python")
    invalid_bundles: list[Any] = []
    partial_pair_payload = {
        **candidate_payload,
        "relationship_projection_result": None,
    }
    with pytest.raises(ValidationError, match="together"):
        module.IsolatedReleaseBundle.model_validate(partial_pair_payload)
    invalid_bundles.append(
        _s7k_constructed_bundle(
            module,
            candidate,
            relationship_projection_result=None,
        )
    )

    absent_nonzero_payload = {
        **candidate_payload,
        "relationship_projection_request": None,
        "relationship_projection_result": None,
    }
    with pytest.raises(ValidationError, match="zero"):
        module.IsolatedReleaseBundle.model_validate(absent_nonzero_payload)
    invalid_bundles.append(
        _s7k_constructed_bundle(
            module,
            candidate,
            relationship_projection_request=None,
            relationship_projection_result=None,
        )
    )

    without_internal_pair = relationship_request.model_copy(
        update={
            "internal_reference_projection_request": None,
            "internal_reference_projection_result": None,
        }
    )
    with pytest.raises(ValidationError, match="internal|combined"):
        module.IsolatedReleaseBundle.model_validate(
            {
                **candidate_payload,
                "relationship_projection_request": without_internal_pair,
            }
        )
    invalid_bundles.append(
        _s7k_constructed_bundle(
            module,
            candidate,
            relationship_projection_request=without_internal_pair,
        )
    )

    legacy_registry_request = relationship_request.model_copy(
        update={
            "relationship_registry_version": "canonical-v2-domain-relationship-registry-v1",
            "relationship_registry_content_sha256": CATALOG_CONTENT_SHA256,
        }
    )
    with pytest.raises(ValidationError, match="combined|internal reference"):
        module.IsolatedReleaseBundle.model_validate(
            {
                **candidate_payload,
                "relationship_projection_request": legacy_registry_request,
            }
        )
    invalid_bundles.append(
        _s7k_constructed_bundle(
            module,
            candidate,
            relationship_projection_request=legacy_registry_request,
        )
    )

    wrong_release_request = relationship_request.model_copy(
        update={"release_id": "candidate-s7k-crosswired"}
    )
    with pytest.raises(ValidationError, match="release|envelope"):
        module.IsolatedReleaseBundle.model_validate(
            {
                **candidate_payload,
                "relationship_projection_request": wrong_release_request,
            }
        )
    invalid_bundles.append(
        _s7k_constructed_bundle(
            module,
            candidate,
            relationship_projection_request=wrong_release_request,
        )
    )

    wrong_as_of_result = relationship_result.model_copy(
        update={"as_of": NOW + timedelta(days=1)}
    )
    with pytest.raises(ValidationError, match="hash|replay|equal|result"):
        module.IsolatedReleaseBundle.model_validate(
            {
                **candidate_payload,
                "relationship_projection_result": wrong_as_of_result,
            }
        )
    invalid_bundles.append(
        _s7k_constructed_bundle(
            module,
            candidate,
            relationship_projection_result=wrong_as_of_result,
        )
    )

    with pytest.raises(ValidationError, match="replay|equal|result"):
        module.IsolatedReleaseBundle.model_validate(
            {
                **candidate_payload,
                "relationship_projection_result": (
                    same_release_zero.relationship_projection_result
                ),
            }
        )
    invalid_bundles.append(
        _s7k_constructed_bundle(
            module,
            candidate,
            relationship_projection_result=(
                same_release_zero.relationship_projection_result
            ),
        )
    )

    legacy_wrong_section = prior.manifest.relationship_set.model_copy(
        update={"section_id": "legacy-relationship-results"}
    )
    legacy_wrong_manifest = _s7k_rehashed_manifest(
        prior.manifest,
        relationship_set=legacy_wrong_section,
    )
    with pytest.raises(ValidationError, match="section_id|relationship"):
        module.IsolatedReleaseBundle.model_validate(
            {
                **prior.model_dump(mode="python"),
                "manifest": legacy_wrong_manifest,
            }
        )
    invalid_bundles.append(
        _s7k_constructed_bundle(
            module,
            prior,
            manifest=legacy_wrong_manifest,
        )
    )

    relationship_section = candidate.manifest.relationship_set
    section_mutations = (
        {"section_id": "relationship-results"},
        {"release_id": "candidate-s7k-crosswired-section"},
        {"version": "relationship-projection-result-v999"},
        {"record_count": relationship_section.record_count + 1},
        {"content_sha256": "f" * 64},
    )
    for mutation in section_mutations:
        changed_section = relationship_section.model_copy(update=mutation)
        changed_manifest = _s7k_rehashed_manifest(
            candidate.manifest,
            relationship_set=changed_section,
        )
        with pytest.raises(ValidationError, match="relationship|manifest"):
            module.IsolatedReleaseBundle.model_validate(
                {**candidate_payload, "manifest": changed_manifest}
            )
        invalid_bundles.append(
            _s7k_constructed_bundle(
                module,
                candidate,
                manifest=changed_manifest,
            )
        )

    changed_projection = candidate.manifest.published_projections[0].model_copy(
        update={"content_sha256": "e" * 64}
    )
    changed_projection_manifest = _s7k_rehashed_manifest(
        candidate.manifest,
        published_projections=(
            changed_projection,
            *candidate.manifest.published_projections[1:],
        ),
    )
    with pytest.raises(ValidationError, match="projection|manifest"):
        module.IsolatedReleaseBundle.model_validate(
            {**candidate_payload, "manifest": changed_projection_manifest}
        )
    invalid_bundles.append(
        _s7k_constructed_bundle(
            module,
            candidate,
            manifest=changed_projection_manifest,
        )
    )

    stale_zero_manifest = same_release_zero.manifest.model_copy(
        update={"manifest_sha256": candidate.manifest.manifest_sha256}
    )
    stale_zero_bundle = module.IsolatedReleaseBundle.model_validate(
        {
            **same_release_zero.model_dump(mode="python"),
            "manifest": stale_zero_manifest,
        }
    )
    invalid_bundles.extend((stale_zero_bundle,))

    class _S7KBundleSubclass(module.IsolatedReleaseBundle):
        pass

    subclass_bundle = _S7KBundleSubclass.model_validate(
        candidate.model_dump(mode="python")
    )
    invalid_bundles.append(subclass_bundle)

    effect_calls: list[str] = []

    def forbidden_effect(name: str) -> Callable[..., Any]:
        def invoke(*args: Any, **kwargs: Any) -> Any:
            del args, kwargs
            effect_calls.append(name)
            raise AssertionError(f"external effect ran before S7K validation: {name}")

        return invoke

    effect_names = (
        "require_accepted_backup_gate",
        "_validate_target_marker",
        "_validate_database_target",
        "_PostgresActiveReleaseState",
        "_validate_database_release_registry",
        "audit_isolated_index_snapshot",
    )
    with monkeypatch.context() as hostile_patch:
        for name in effect_names:
            hostile_patch.setattr(module, name, forbidden_effect(name))
        for invalid_bundle in invalid_bundles:
            with pytest.raises(module.IsolatedReleaseTargetSafetyError):
                module.create_isolated_release_publication(
                    database_target=object(),
                    prior_release=prior,
                    candidate_release=invalid_bundle,
                    backup_gate_root=tmp_path,
                    embedding_adapter=object(),
                    verification_store={},
                    discrepancy_store={},
                    publication_history=[],
                    clock=lambda: NOW,
                )
            assert effect_calls == []

    class _FreshBundlesObserved(RuntimeError):
        pass

    observed: dict[str, Any] = {}

    def observe_registry(
        target: Any,
        *,
        prior_release: Any,
        candidate_release: Any,
    ) -> None:
        observed.update(
            {
                "target": target,
                "prior": prior_release,
                "candidate": candidate_release,
            }
        )
        raise _FreshBundlesObserved

    with monkeypatch.context() as fresh_patch:
        fresh_patch.setattr(module, "require_accepted_backup_gate", lambda _: None)
        fresh_patch.setattr(module, "_validate_target_marker", lambda _: None)
        fresh_patch.setattr(module, "_validate_database_target", lambda target: target)
        fresh_patch.setattr(module, "_PostgresActiveReleaseState", lambda **_: {})
        fresh_patch.setattr(
            module, "_validate_database_release_registry", observe_registry
        )
        with pytest.raises(_FreshBundlesObserved):
            module.create_isolated_release_publication(
                database_target=object(),
                prior_release=prior,
                candidate_release=candidate,
                backup_gate_root=tmp_path,
                embedding_adapter=object(),
                verification_store={},
                discrepancy_store={},
                publication_history=[],
                clock=lambda: NOW,
            )

    assert observed["prior"] == prior
    assert observed["candidate"] == candidate
    assert observed["prior"] is not prior
    assert observed["candidate"] is not candidate


def _task7_7_seed_database(
    database_target: Any,
    *,
    prior_bundle: Any,
    candidate_bundle: Any,
) -> None:
    with psycopg.connect(
        _task7_7_psycopg_dsn(database_target.url),
        autocommit=False,
    ) as connection:
        identity_row = connection.execute(
            "SELECT current_database(), "
            "shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = current_database()"
        ).fetchone()
        assert identity_row is not None
        actual_database, marker = identity_row
        assert actual_database == database_target.expected_database
        assert marker == database_target.database_marker
        for bundle, previous_release_id in (
            (prior_bundle, None),
            (candidate_bundle, prior_bundle.release_id),
        ):
            manifest = bundle.manifest
            connection.execute(
                "INSERT INTO knowledge.release "
                "(release_id, build_run_id, state, manifest_sha256, "
                "previous_release_id, created_at) "
                "VALUES (%s, %s, 'accepted', %s, %s, %s) "
                "ON CONFLICT (release_id) DO NOTHING",
                (
                    bundle.release_id,
                    manifest.build_run_id,
                    manifest.manifest_sha256,
                    previous_release_id,
                    NOW,
                ),
            )
            connection.execute(
                "INSERT INTO publish.build_manifest "
                "(release_id, manifest_version, build_run_id, source_batch_ids, "
                "source_batches_sha256, parser_versions, policy_versions, "
                "model_versions, manifest_sha256, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (release_id) DO NOTHING",
                (
                    manifest.release_id,
                    manifest.manifest_version,
                    manifest.build_run_id,
                    Jsonb(list(manifest.source_batch_ids)),
                    manifest.source_batches_sha256,
                    Jsonb(dict(manifest.parser_versions)),
                    Jsonb(dict(manifest.policy_versions)),
                    Jsonb(dict(manifest.model_versions)),
                    manifest.manifest_sha256,
                    manifest.created_at,
                ),
            )
        connection.execute(
            "INSERT INTO publish.active_release "
            "(singleton, release_id, canonical_release_id, "
            "published_projection_release_id, index_release_id, "
            "previous_release_id, changed_at) "
            "VALUES (TRUE, %s, %s, %s, %s, NULL, %s) "
            "ON CONFLICT (singleton) DO NOTHING",
            (
                prior_bundle.release_id,
                prior_bundle.release_id,
                prior_bundle.release_id,
                prior_bundle.release_id,
                NOW,
            ),
        )
        state = connection.execute(
            "SELECT release_id, canonical_release_id, "
            "published_projection_release_id, index_release_id "
            "FROM publish.active_release WHERE singleton = TRUE"
        ).fetchone()
        assert state == (prior_bundle.release_id,) * 4
        stored = connection.execute(
            "SELECT release_id, manifest_sha256 FROM publish.build_manifest "
            "WHERE release_id IN (%s, %s) ORDER BY release_id",
            (prior_bundle.release_id, candidate_bundle.release_id),
        ).fetchall()
        assert stored == sorted(
            (
                (prior_bundle.release_id, prior_bundle.manifest.manifest_sha256),
                (
                    candidate_bundle.release_id,
                    candidate_bundle.manifest.manifest_sha256,
                ),
            )
        )
        connection.commit()


def _task7_7_evidence_sha256(database_target: Any) -> str:
    with psycopg.connect(
        _task7_7_psycopg_dsn(database_target.url),
        autocommit=True,
    ) as connection:
        release_rows = connection.execute(
            "SELECT release_id, build_run_id, state, manifest_sha256, "
            "previous_release_id, created_at::text FROM knowledge.release "
            "WHERE release_id IN ('accepted-s7g-r0', 'candidate-s7g-r1') "
            "ORDER BY release_id"
        ).fetchall()
        manifest_rows = connection.execute(
            "SELECT release_id, manifest_version, build_run_id, "
            "source_batch_ids::text, source_batches_sha256, "
            "parser_versions::text, policy_versions::text, model_versions::text, "
            "manifest_sha256, created_at::text FROM publish.build_manifest "
            "WHERE release_id IN ('accepted-s7g-r0', 'candidate-s7g-r1') "
            "ORDER BY release_id"
        ).fetchall()
        landing_counts = connection.execute(
            "SELECT (SELECT count(*) FROM landing.evidence_artifact), "
            "(SELECT count(*) FROM landing.source_record), "
            "(SELECT count(*) FROM landing.source_error)"
        ).fetchone()
    encoded = json.dumps(
        {
            "releases": release_rows,
            "manifests": manifest_rows,
            "landing_counts": landing_counts,
        },
        default=str,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _task7_7_bundle_hashes(bundle: Any) -> tuple[str, str]:
    return (
        _file_sha256(bundle.index_target.root / "lookup.sqlite3"),
        _file_sha256(bundle.index_target.root / "milvus.db"),
    )


def _task7_7_inject_extra_point(bundle: Any) -> Any:
    isolated = _isolated_index_projection_module()
    source = bundle.index_result.points[0]
    content = "Unexpected physical Task 7.7 point."
    extra = source.model_copy(
        update={
            "point_id": f"{source.point_id}:extra",
            "canonical_object_id": f"{source.canonical_object_id}:extra",
            "embedded_content": content,
            "embedded_content_sha256": hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest(),
            "source_evidence_ids": ("evidence:task7.7-extra",),
        }
    )
    with sqlite3.connect(
        f"file:{bundle.index_target.root / 'lookup.sqlite3'}?mode=ro",
        uri=True,
    ) as connection:
        collection_row = connection.execute(
            "SELECT value FROM build_metadata WHERE key = 'collection_name'"
        ).fetchone()
    assert collection_row is not None
    collection_name = collection_row[0]
    embedding = isolated.RecordedEmbeddingAdapter(
        model_id="recorded-embedding-v1",
        dimension=32,
    ).embed_batch((extra.embedded_content,))[0]
    client = isolated._open_milvus_client(bundle.index_target.root / "milvus.db")
    try:
        client.insert(
            collection_name=collection_name,
            data=[
                {
                    "point_id": extra.point_id,
                    "vector": list(embedding),
                    "release_id": extra.release_id,
                    "projection_id": extra.projection_id,
                    "canonical_object_id": extra.canonical_object_id,
                    "embedded_content_sha256": extra.embedded_content_sha256,
                    "point_json": extra.model_dump_json(),
                }
            ],
        )
        client.flush(collection_name=collection_name)
    finally:
        client.close()
    return extra


def test_isolated_release_publication_verifies_promotes_and_rolls_back_physical_releases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _isolated_release_publication_module()
    isolated = _isolated_index_projection_module()
    database_target = _task7_7_database_target(module, monkeypatch)
    prior = _task7_7_physical_release_bundle(
        module,
        root=tmp_path / "accepted-r0-index",
        target_id="canonical-v2-s7g-prior",
        release_id="accepted-s7g-r0",
    )
    candidate = _task7_7_physical_release_bundle(
        module,
        root=tmp_path / "candidate-r1-index",
        target_id="canonical-v2-s7g-candidate",
        release_id="candidate-s7g-r1",
    )
    _task7_7_seed_database(
        database_target,
        prior_bundle=prior,
        candidate_bundle=candidate,
    )
    immutable_evidence_before = _task7_7_evidence_sha256(database_target)
    physical_hashes_before = {
        prior.release_id: _task7_7_bundle_hashes(prior),
        candidate.release_id: _task7_7_bundle_hashes(candidate),
    }
    verification_store: dict[str, Any] = {}
    discrepancy_store: dict[str, tuple[Any, ...]] = {}
    publication_history: list[Any] = []
    publication = module.create_isolated_release_publication(
        database_target=database_target,
        prior_release=prior,
        candidate_release=candidate,
        backup_gate_root=(
            Path(__file__).resolve().parents[4]
            / ".agents"
            / "runs"
            / "rebuild-canonical-v2-knowledge-platform"
        ),
        embedding_adapter=isolated.RecordedEmbeddingAdapter(
            model_id="recorded-embedding-v1",
            dimension=32,
        ),
        verification_store=verification_store,
        discrepancy_store=discrepancy_store,
        publication_history=publication_history,
        clock=lambda: NOW,
    )

    verification = publication.verify(candidate.release_id)
    assert verification.accepted is True
    assert module.read_isolated_active_release(database_target) == {
        "canonical_release_id": prior.release_id,
        "published_projection_release_id": prior.release_id,
        "index_release_id": prior.release_id,
    }
    promoted = publication.promote(candidate.release_id)
    promoted_state = module.read_isolated_active_release(database_target)
    assert set(promoted_state.values()) == {candidate.release_id}
    candidate_audit = isolated.audit_isolated_index_snapshot(
        candidate.index_target,
        embedding_adapter=isolated.RecordedEmbeddingAdapter(
            model_id="recorded-embedding-v1",
            dimension=32,
        ),
    )
    assert candidate_audit.receipt.release_id == promoted_state["index_release_id"]
    assert candidate_audit.points == candidate.index_result.points
    assert candidate_audit.lookup_documents == candidate.index_result.lookup_documents

    rolled_back = publication.rollback(promoted.release_id)
    rolled_back_state = module.read_isolated_active_release(database_target)
    assert set(rolled_back_state.values()) == {prior.release_id}
    prior_audit = isolated.audit_isolated_index_snapshot(
        prior.index_target,
        embedding_adapter=isolated.RecordedEmbeddingAdapter(
            model_id="recorded-embedding-v1",
            dimension=32,
        ),
    )
    assert prior_audit.receipt.release_id == rolled_back_state["index_release_id"]
    assert prior_audit.points == prior.index_result.points
    assert rolled_back.release_id == prior.release_id
    assert verification_store[candidate.release_id] == verification
    assert [event.release_id for event in publication_history] == [
        candidate.release_id,
        prior.release_id,
    ]
    assert _task7_7_evidence_sha256(database_target) == immutable_evidence_before
    assert {
        prior.release_id: _task7_7_bundle_hashes(prior),
        candidate.release_id: _task7_7_bundle_hashes(candidate),
    } == physical_hashes_before


def test_isolated_release_publication_blocks_unreceipted_physical_extra_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _isolated_release_publication_module()
    isolated = _isolated_index_projection_module()
    database_target = _task7_7_database_target(module, monkeypatch)
    prior = _task7_7_physical_release_bundle(
        module,
        root=tmp_path / "accepted-r0-index",
        target_id="canonical-v2-s7g-prior-extra",
        release_id="accepted-s7g-r0",
    )
    candidate = _task7_7_physical_release_bundle(
        module,
        root=tmp_path / "candidate-r1-index",
        target_id="canonical-v2-s7g-candidate-extra",
        release_id="candidate-s7g-r1",
    )
    _task7_7_seed_database(
        database_target,
        prior_bundle=prior,
        candidate_bundle=candidate,
    )
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    original_sha256 = _file_sha256(original_milvus)
    extra_point = _task7_7_inject_extra_point(candidate)
    verification_store: dict[str, Any] = {}
    discrepancy_store: dict[str, tuple[Any, ...]] = {}
    publication = module.create_isolated_release_publication(
        database_target=database_target,
        prior_release=prior,
        candidate_release=candidate,
        backup_gate_root=(
            Path(__file__).resolve().parents[4]
            / ".agents"
            / "runs"
            / "rebuild-canonical-v2-knowledge-platform"
        ),
        embedding_adapter=isolated.RecordedEmbeddingAdapter(
            model_id="recorded-embedding-v1",
            dimension=32,
        ),
        verification_store=verification_store,
        discrepancy_store=discrepancy_store,
        publication_history=[],
        clock=lambda: NOW,
    )

    verification = publication.verify(candidate.release_id)

    assert verification.accepted is False
    assert verification.extra_points == 1
    assert any(
        detail.point_id == extra_point.point_id and detail.kind.value == "extra"
        for detail in discrepancy_store[candidate.release_id]
    )
    assert verification_store[candidate.release_id] == verification
    with pytest.raises(ValueError, match="not accepted"):
        publication.promote(candidate.release_id)
    assert set(module.read_isolated_active_release(database_target).values()) == {
        prior.release_id
    }
    assert _file_sha256(original_milvus) == original_sha256


def test_isolated_release_publication_rejects_implicit_and_crosswired_targets_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _isolated_release_publication_module()
    isolated = _isolated_index_projection_module()
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    original_sha256 = _file_sha256(original_milvus)
    connection_attempts: list[str] = []
    milvus_client_opens: list[Path] = []

    def _unexpected_connect(database_url: str) -> None:
        connection_attempts.append(database_url)
        raise AssertionError("invalid target must fail before PostgreSQL connect")

    def _unexpected_milvus_open(path: Path) -> None:
        milvus_client_opens.append(path)
        raise AssertionError("cross-wired target must fail before Milvus client open")

    monkeypatch.setattr(module, "_connect_postgres", _unexpected_connect)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://miroflow:do-not-use@localhost:15432/miroflow_real",
    )
    evidence_root = (
        Path(__file__).resolve().parents[4]
        / ".agents"
        / "runs"
        / "rebuild-canonical-v2-knowledge-platform"
    )
    with pytest.raises(module.IsolatedReleaseTargetSafetyError, match="explicit"):
        module.prepare_isolated_release_database_target(
            database_url="",
            expected_database="",
            target_kind="disposable",
            backup_gate_root=evidence_root,
        )
    with pytest.raises(module.IsolatedReleaseTargetSafetyError, match="disposable"):
        module.prepare_isolated_release_database_target(
            database_url=(
                "postgresql+psycopg://miroflow:unused@localhost:55432/canonical_v2_s7g"
            ),
            expected_database="canonical_v2_s7g",
            target_kind="isolated-candidate",
            backup_gate_root=evidence_root,
        )
    _, index_result, manifest = _task7_7_release_values(
        module,
        release_id="candidate-s7g-safety",
    )
    monkeypatch.setattr(isolated, "_open_milvus_client", _unexpected_milvus_open)
    crosswired_target = isolated.IsolatedIndexTarget.model_construct(
        root=tmp_path / "never-opened-index",
        target_id="crosswired-target",
        release_id="other-release",
        target_kind="isolated-candidate",
        forbidden_milvus_paths=(original_milvus,),
        marker_sha256="0" * 64,
    )
    with pytest.raises(ValidationError, match="release"):
        module.IsolatedReleaseBundle(
            manifest=manifest,
            index_result=index_result,
            index_target=crosswired_target,
        )

    assert connection_attempts == []
    assert milvus_client_opens == []
    assert not (crosswired_target.root / "milvus.db").exists()
    assert _file_sha256(original_milvus) == original_sha256


def test_s8e1_release_bound_knowledge_read_composes_physical_lanes_without_caller_map(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _isolated_release_knowledge_read_factory()
    fixture = request.getfixturevalue("isolated_lookup_target_bundle")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    release_module = _isolated_release_publication_module()
    bundle = fixture["bundle"]
    published = _s8p1_published_release(contracts_module, release_id=RELEASE_ID)

    planning_request = read_module.QueryPlanningRequest(
        request_id="query-request:s8e1-release-bound-execution",
        release_id=RELEASE_ID,
        original_query="请核对已展示的“Robotics Co”",
        as_of=NOW,
        displayed_entity_ids=("company-robotics",),
    )

    def proposal_provider(value: Any) -> Any:
        assert value == planning_request
        return read_module.RecordedPlanningProposal(
            proposal_id="planning-proposal:s8e1-release-bound-execution",
            request_sha256=value.content_sha256,
            schema_version="retrieval-plan-proposal-v1",
            model_id="recorded-planner-s8e1",
            prompt_version="query-plan-prompt-v1",
            behavior_class="G",
            interaction_mode="information_retrieval",
            domains=("company",),
            lanes=("exact", "structured", "web"),
            max_candidates=2,
            max_provider_calls=1,
            web_mode="universal",
            max_web_results=1,
        )

    planner = _isolated_release_query_planner_factory()(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=fixture["index_request"],
        release_institution_catalog=_s8p1_institution_catalog(read_module),
        planning_policy=_s8p1_planning_policy(read_module),
        proposal_provider=proposal_provider,
    )
    plan = planner.plan(planning_request)
    assert plan.release_binding is not None
    assert plan.lanes == ("exact", "structured", "web")

    web_payload = b"Recorded current-Web profile for Robotics Co."
    web_digest = hashlib.sha256(web_payload).hexdigest()
    web_snapshot = read_module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:s8e1:sha256:{web_digest}",
        content_sha256=web_digest,
        retrieved_at=NOW,
        byte_length=len(web_payload),
    )
    web_item = read_module.EvidenceItem(
        evidence_id="evidence:web:s8e1:robotics-co",
        object_id="company-robotics",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_locator="https://current.example/robotics-co",
        snippet="Robotics Co current Web profile",
        score=0.75,
        web_snapshot=web_snapshot,
    )
    web_result = read_module.RetrievalLaneResult(
        items=(web_item,),
        web_snapshot_payloads=(
            read_module.WebSnapshotPayload(
                snapshot_id=web_snapshot.snapshot_id,
                content=web_payload,
            ),
        ),
    )
    web_requests: list[Any] = []

    def recorded_web_search(lane_request: Any) -> Any:
        web_requests.append(lane_request)
        return web_result

    universal_web_policy = read_module.WebSearchPolicy(
        mode="universal",
        max_provider_calls=1,
        timeout_ms=1_000,
        max_results=1,
    )
    snapshot_policy = read_module.WebSnapshotPolicy(
        policy_id="web-snapshot-policy:s8e1",
        policy_version="web-snapshot-policy-v1",
        max_bytes=8_192,
    )
    factory_kwargs = {
        "release_bundle": bundle,
        "published_release": published,
        "universal_web_policy": universal_web_policy,
        "web_search": recorded_web_search,
        "web_snapshot_policy": snapshot_policy,
        "clock": lambda: NOW,
    }
    with pytest.raises(TypeError, match="lane_adapters"):
        factory(**factory_kwargs, lane_adapters={})

    service = factory(**factory_kwargs)
    result = service.execute(plan)

    assert len(web_requests) == 1
    assert web_requests[0].lane == "web"
    assert web_requests[0].release_id == RELEASE_ID
    trace_by_lane = {trace.lane: trace for trace in result.traces}
    assert set(trace_by_lane) == {"exact", "structured", "web"}
    assert all(trace.status == "succeeded" for trace in trace_by_lane.values())
    assert result.snapshot_receipts == (
        read_module.SnapshotReceipt(
            snapshot_id=web_snapshot.snapshot_id,
            status="accepted",
            observed_byte_length=len(web_payload),
        ),
    )
    retained_web_item = next(
        item for item in result.items if item.evidence_id == web_item.evidence_id
    )
    assert retained_web_item.web_snapshot == web_snapshot
    assert len(result.fused_candidates) == 1
    fused = result.fused_candidates[0]
    assert fused.canonical_id == "company-robotics"
    assert {item.lane for item in fused.evidence} == {"exact", "structured"}
    assert len(fused.raw_candidate_ids) == 2
    assert len(set(fused.raw_candidate_ids)) == 2
    assert len(fused.evidence_ids) == 2
    assert len(set(fused.evidence_ids)) == 2
    assert len(result.entity_handles) == 1
    assert result.entity_handles[0].canonical_id == "company-robotics"
    assert len(result.candidate_traces) == 2
    assert all(trace.disposition == "selected" for trace in result.candidate_traces)
    assert all(
        trace.selected_result_id == "company-robotics"
        for trace in result.candidate_traces
    )

    oversize_result = factory(
        **{
            **factory_kwargs,
            "web_snapshot_policy": read_module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8e1-oversize",
                policy_version="web-snapshot-policy-v1",
                max_bytes=len(web_payload) - 1,
            ),
        }
    ).execute(plan)
    assert oversize_result.snapshot_receipts[0].status == "rejected"
    assert oversize_result.snapshot_receipts[0].reason_code == "max_bytes_exceeded"
    assert all(
        item.evidence_id != web_item.evidence_id for item in oversize_result.items
    )

    missing_payload_result = factory(
        **{
            **factory_kwargs,
            "web_search": lambda _: read_module.RetrievalLaneResult(items=(web_item,)),
        }
    ).execute(plan)
    assert missing_payload_result.snapshot_receipts[0].status == "rejected"
    assert missing_payload_result.snapshot_receipts[0].reason_code == "payload_missing"
    assert all(
        item.evidence_id != web_item.evidence_id
        for item in missing_payload_result.items
    )
    for degraded_web_result in (oversize_result, missing_payload_result):
        assert len(degraded_web_result.fused_candidates) == 1
        degraded_fused = degraded_web_result.fused_candidates[0]
        assert degraded_fused.canonical_id == "company-robotics"
        assert {item.lane for item in degraded_fused.evidence} == {
            "exact",
            "structured",
        }
        assert {
            item.lane
            for item in degraded_web_result.items
            if item.source_nature == "local"
        } == {"exact", "structured"}
        assert len(degraded_web_result.entity_handles) == 1
        assert degraded_web_result.entity_handles[0].canonical_id == "company-robotics"

    def plan_with(**updates: Any) -> Any:
        payload = plan.model_dump(mode="json", exclude={"content_sha256"})
        payload.update(updates)
        return read_module.RetrievalPlan.model_validate(payload)

    binding = plan.release_binding
    assert binding is not None

    def binding_with(**updates: Any) -> Any:
        payload = binding.model_dump(mode="json", exclude={"content_sha256"})
        payload.update(updates)
        return read_module.PlanningReleaseBinding.model_validate(payload)

    invalid_plans = (
        plan_with(release_binding=None),
        *(
            plan_with(release_binding=changed.model_dump(mode="json"))
            for changed in (
                binding_with(publication_state="rolled_back"),
                binding_with(published_release_sha256="e" * 64),
                binding_with(
                    publication_verification_evidence_ids=(
                        "release-verification:other",
                    )
                ),
                binding_with(manifest_sha256="f" * 64),
                binding_with(index_projection_result_sha256="d" * 64),
            )
        ),
        plan_with(
            lanes=("exact", "structured", "vector", "web"),
            lane_queries=(
                *plan.model_dump(mode="json")["lane_queries"],
                read_module.LaneQuery(
                    lane="vector",
                    release_id=RELEASE_ID,
                    catalog_sha256=_s8p1_institution_catalog(
                        read_module
                    ).content_sha256,
                    pure_topic_text="Robotics Co",
                    query_text="Robotics Co [lane=vector]",
                ).model_dump(mode="json"),
            ),
        ),
        plan.model_copy(update={"release_id": "cross-release-s8e1"}),
    )

    unmarked_root = tmp_path / "s8e1-must-not-open"
    unmarked_bundle = release_module.IsolatedReleaseBundle(
        manifest=bundle.manifest,
        index_result=bundle.index_result,
        index_target=bundle.index_target.model_copy(update={"root": unmarked_root}),
    )
    physical_read_attempts: list[Path] = []

    def unexpected_physical_read(value: Any) -> Any:
        physical_read_attempts.append(value.index_target.root)
        raise AssertionError("invalid execution must fail before physical lookup")

    monkeypatch.setattr(
        _isolated_knowledge_read_module(),
        "_read_bound_documents",
        unexpected_physical_read,
    )
    blocked_web_requests: list[Any] = []
    blocked_service = factory(
        release_bundle=unmarked_bundle,
        published_release=published,
        universal_web_policy=universal_web_policy,
        web_search=lambda lane_request: blocked_web_requests.append(lane_request),
        web_snapshot_policy=snapshot_policy,
        clock=lambda: NOW,
    )
    integrity_error = (
        _isolated_knowledge_read_module().IsolatedKnowledgeReadIntegrityError
    )
    for invalid_plan in invalid_plans:
        with pytest.raises(integrity_error):
            blocked_service.execute(invalid_plan)
    assert physical_read_attempts == []
    assert blocked_web_requests == []
    assert not unmarked_root.exists()

    invalid_web_policies = (
        read_module.WebSearchPolicy(
            mode="disabled",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=1,
        ),
        read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=0,
            timeout_ms=1_000,
            max_results=1,
        ),
        read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=0,
            max_results=1,
        ),
        read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=0,
        ),
        read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=1,
            allowed_domains=("current.example",),
        ),
    )
    for invalid_web_policy in invalid_web_policies:
        with pytest.raises(integrity_error, match="Universal Web policy"):
            factory(
                release_bundle=unmarked_bundle,
                published_release=published,
                universal_web_policy=invalid_web_policy,
                web_search=lambda lane_request: blocked_web_requests.append(
                    lane_request
                ),
                web_snapshot_policy=snapshot_policy,
                clock=lambda: NOW,
            )
    assert physical_read_attempts == []
    assert blocked_web_requests == []
    assert not unmarked_root.exists()

    with pytest.raises(integrity_error, match="published release"):
        factory(
            release_bundle=unmarked_bundle,
            published_release=published.model_copy(
                update={"state": contracts_module.ReleaseState.candidate}
            ),
            universal_web_policy=universal_web_policy,
            web_search=lambda lane_request: blocked_web_requests.append(lane_request),
            web_snapshot_policy=snapshot_policy,
            clock=lambda: NOW,
        )
    assert blocked_web_requests == []
    assert physical_read_attempts == []
    assert not unmarked_root.exists()
    assert {
        name: _file_sha256(bundle.index_target.root / name)
        for name in fixture["target_hashes"]
    } == fixture["target_hashes"]
    assert _file_sha256(fixture["original_milvus"]) == fixture["original_sha256"]


def test_s8l3_release_scoped_lexical_phrase_recall_uses_release_bound_composition(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lexical_factory = _isolated_lexical_lookup_factory()
    fixture = request.getfixturevalue("isolated_lookup_target_bundle")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    index_module = _index_projection_module()
    isolated_index_module = _isolated_index_projection_module()
    release_module = _isolated_release_publication_module()
    isolated_read_module = _isolated_knowledge_read_module()
    bundle = fixture["bundle"]
    published = _s8p1_published_release(contracts_module, release_id=RELEASE_ID)

    planning_request = read_module.QueryPlanningRequest(
        request_id="query-request:s8l3-lexical-phrase",
        release_id=RELEASE_ID,
        original_query="“Evidence-bound robotics”",
        as_of=NOW,
    )

    def proposal_provider(value: Any) -> Any:
        assert value == planning_request
        return read_module.RecordedPlanningProposal(
            proposal_id="planning-proposal:s8l3-lexical-phrase",
            request_sha256=value.content_sha256,
            schema_version="retrieval-plan-proposal-v1",
            model_id="recorded-planner-s8l3",
            prompt_version="query-plan-prompt-v1",
            behavior_class="G",
            interaction_mode="information_retrieval",
            domains=("paper",),
            lanes=("exact", "lexical", "web"),
            max_candidates=2,
            max_provider_calls=1,
            web_mode="universal",
            max_web_results=1,
        )

    plan = _isolated_release_query_planner_factory()(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=fixture["index_request"],
        release_institution_catalog=_s8p1_institution_catalog(read_module),
        planning_policy=_s8p1_planning_policy(read_module),
        proposal_provider=proposal_provider,
    ).plan(planning_request)
    assert plan.release_binding is not None
    assert plan.lanes == ("exact", "lexical", "web")

    service = _isolated_release_knowledge_read_factory()(
        release_bundle=bundle,
        published_release=published,
        universal_web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=1,
        ),
        web_search=lambda _: read_module.RetrievalLaneResult(),
        web_snapshot_policy=read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8l3",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        clock=lambda: NOW,
    )
    result = service.execute(plan)

    trace_by_lane = {trace.lane: trace for trace in result.traces}
    assert set(trace_by_lane) == {"exact", "lexical", "web"}
    assert all(trace.status == "succeeded" for trace in trace_by_lane.values())
    assert len(result.fused_candidates) == 1
    fused = result.fused_candidates[0]
    assert fused.canonical_id == "paper-ada"
    assert fused.domain == "paper"
    assert {item.lane for item in fused.evidence} == {"exact", "lexical"}
    assert len(fused.raw_candidate_ids) == 2
    assert len(set(fused.raw_candidate_ids)) == 2
    assert len(fused.evidence_ids) == 2
    assert len(set(fused.evidence_ids)) == 2
    assert len(result.entity_handles) == 1
    assert result.entity_handles[0].canonical_id == "paper-ada"
    assert len(result.candidate_traces) == 2
    assert all(trace.disposition == "selected" for trace in result.candidate_traces)

    lexical_adapter = lexical_factory(
        release_bundle=bundle,
        published_release=published,
    )
    lexical_request = read_module.LaneRequest(
        lane="lexical",
        release_id=RELEASE_ID,
        query_view="view:original",
        original_query=planning_request.original_query,
        behavior_class="G",
        interaction_mode="information_retrieval",
        web_policy=read_module.WebSearchPolicy(mode="disabled"),
        query_text="“bound robotics” [lane=lexical]",
        domains=("paper",),
        protected_slots=(),
        structured_constraints=plan.structured_constraints,
        max_candidates=2,
    )
    raw_result = lexical_adapter(lexical_request)
    assert len(raw_result.candidates) == 1
    candidate = raw_result.candidates[0]
    assert candidate.canonical_id == "paper-ada"
    assert candidate.lane == "lexical"
    assert candidate.adapter_version == "canonical-v2-isolated-lexical-lookup-v1"
    assert len(candidate.evidence) == 1
    lexical_item = candidate.evidence[0]
    lexical_trace = lexical_item.local_projection_trace
    assert lexical_trace is not None
    assert lexical_trace.execution_lane == "lexical"
    assert lexical_trace.path == "exact_lookup"
    assert lexical_item.evidence_id == lexical_trace.evidence_id
    assert candidate.raw_candidate_id == lexical_trace.raw_candidate_id
    assert lexical_trace.release_id == RELEASE_ID
    assert lexical_trace.target_id == bundle.index_target.target_id
    assert lexical_trace.target_marker_sha256 == bundle.index_target.marker_sha256
    assert lexical_trace.manifest_sha256 == bundle.manifest.manifest_sha256
    assert (
        lexical_trace.index_result_content_sha256 == bundle.index_result.content_sha256
    )

    def request_with(**updates: Any) -> Any:
        payload = lexical_request.model_dump(mode="json")
        payload.update(updates)
        payload["content_sha256"] = "0" * 64
        return read_module.LaneRequest.model_validate(payload)

    def lexical_candidate_ids(query_text: str) -> tuple[str | None, ...]:
        return tuple(
            item.canonical_id
            for item in lexical_adapter(request_with(query_text=query_text)).candidates
        )

    for normalized_equivalent in (
        '"bound robotics" [lane=lexical]',
        '  "ＢＯＵＮＤ   ＲｏＢｏＴｉＣｓ" [lane=lexical]  ',
    ):
        assert lexical_candidate_ids(normalized_equivalent) == ("paper-ada",)
    for intentionally_literal in (
        "'bound robotics' [lane=lexical]",
        "““bound robotics”” [lane=lexical]",
        "“bound robotics” [lane = lexical]",
        "[lane=lexical] “bound robotics”",
        "“bound robotics” [lane=lexical] trailing",
    ):
        assert lexical_candidate_ids(intentionally_literal) == ()

    original_reader = isolated_read_module._read_bound_documents
    read_attempts: list[Path] = []

    def unexpected_read(value: Any) -> Any:
        read_attempts.append(value.index_target.root)
        raise AssertionError("empty or wrong-lane lexical input must fail before read")

    monkeypatch.setattr(isolated_read_module, "_read_bound_documents", unexpected_read)
    with pytest.raises(ValueError, match="lexical"):
        lexical_adapter(request_with(lane="vector"))
    with pytest.raises(ValueError, match="release"):
        lexical_adapter(request_with(release_id="cross-release-s8l3-request"))
    with pytest.raises(ValueError, match="non-public"):
        lexical_adapter(request_with(domains=("person",)))
    assert (
        lexical_adapter(request_with(query_text="“” [lane=lexical]")).candidates == ()
    )
    assert read_attempts == []
    monkeypatch.setattr(isolated_read_module, "_read_bound_documents", original_reader)

    assert lexical_adapter(request_with(domains=("company",))).candidates == ()
    assert lexical_adapter(request_with(max_candidates=0)).candidates == ()
    assert (
        lexical_adapter(
            request_with(
                structured_constraints=read_module.StructuredConstraints(
                    excluded_terms=("robotics",),
                ).model_dump(mode="json")
            )
        ).candidates
        == ()
    )
    internal_document = next(
        document
        for document in bundle.index_result.lookup_documents
        if document.projection_scope.value == "internal_auxiliary"
    )
    internal_attempt = lexical_adapter(
        request_with(
            query_text=f"{internal_document.canonical_object_id} [lane=lexical]",
            domains=PUBLIC_DOMAINS,
            protected_slots=(),
        )
    )
    assert all(
        item.canonical_id != internal_document.canonical_object_id
        for item in internal_attempt.candidates
    )
    assert all(item.domain in PUBLIC_DOMAINS for item in internal_attempt.candidates)

    rolled_back_adapter = lexical_factory(
        release_bundle=bundle,
        published_release=published.model_copy(
            update={"state": contracts_module.ReleaseState.rolled_back}
        ),
    )
    assert len(rolled_back_adapter(lexical_request).candidates) == 1
    wrong_release = published.model_copy(
        update={
            "release_id": "cross-release-s8l3",
            "canonical_release_id": "cross-release-s8l3",
            "published_projection_release_id": "cross-release-s8l3",
            "index_release_id": "cross-release-s8l3",
        }
    )
    with pytest.raises(ValueError, match="published release.*bundle"):
        lexical_factory(
            release_bundle=bundle,
            published_release=wrong_release,
        )

    unmarked_root = tmp_path / "s8l3-unmarked-target"
    unmarked_root.mkdir()
    unmarked_bundle = release_module.IsolatedReleaseBundle(
        manifest=bundle.manifest,
        index_result=bundle.index_result,
        index_target=bundle.index_target.model_copy(update={"root": unmarked_root}),
    )
    unmarked_adapter = lexical_factory(
        release_bundle=unmarked_bundle,
        published_release=published,
    )
    assert (
        unmarked_adapter(request_with(query_text="“” [lane=lexical]")).candidates == ()
    )
    with pytest.raises(
        isolated_index_module.IsolatedIndexTargetSafetyError, match="marker"
    ):
        unmarked_adapter(lexical_request)
    assert not (unmarked_root / "lookup.sqlite3").exists()
    assert not (unmarked_root / "milvus.db").exists()

    reduced_documents = tuple(
        document
        for document in bundle.index_result.lookup_documents
        if document.canonical_object_id != "paper-ada"
    )
    mismatched_payload = bundle.index_result.model_dump(mode="json")
    mismatched_payload["lookup_documents"] = [
        document.model_dump(mode="json") for document in reduced_documents
    ]
    mismatched_payload["content_sha256"] = _canonical_json_sha256(
        {
            key: value
            for key, value in mismatched_payload.items()
            if key != "content_sha256"
        }
    )
    mismatched_bundle = release_module.IsolatedReleaseBundle(
        manifest=bundle.manifest,
        index_result=index_module.IndexProjectionResult.model_validate(
            mismatched_payload
        ),
        index_target=bundle.index_target,
    )
    mismatched_adapter = lexical_factory(
        release_bundle=mismatched_bundle,
        published_release=published,
    )
    with pytest.raises(
        index_module.IndexProjectionIntegrityError,
        match="physical lookup.*bundle",
    ):
        mismatched_adapter(lexical_request)

    assert {
        name: _file_sha256(bundle.index_target.root / name)
        for name in fixture["target_hashes"]
    } == fixture["target_hashes"]
    assert _file_sha256(fixture["original_milvus"]) == fixture["original_sha256"]


def test_s8ir1_release_scoped_internal_reference_filter_and_definition_lookup(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        read_module,
        internal_factory,
        release_read_factory,
    ) = _isolated_internal_reference_lookup_contract()
    fixture = request.getfixturevalue("isolated_lookup_target_bundle")
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    isolated_read_module = _isolated_knowledge_read_module()
    bundle = fixture["bundle"]
    index_request = fixture["index_request"]
    institution_catalog = _s8p1_institution_catalog(read_module)
    published = _s8p1_published_release(contracts_module, release_id=RELEASE_ID)
    planning_request = _s8p1_planning_request(read_module)

    def proposal_provider(value: Any) -> Any:
        proposal = _s8p1_proposal(read_module, value)
        return read_module.RecordedPlanningProposal.model_validate(
            {
                **proposal.model_dump(mode="json", exclude={"content_sha256"}),
                "proposal_id": "planning-proposal:s8ir1-definition-only",
                "lanes": ("internal_reference", "web"),
                "relationship_paths": (),
            }
        )

    plan = _isolated_release_query_planner_factory()(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=institution_catalog,
        planning_policy=_s8p1_planning_policy(read_module),
        proposal_provider=proposal_provider,
    ).plan(planning_request)
    assert plan.release_binding is not None
    assert plan.lanes == ("internal_reference", "web")
    assert plan.relationship_paths == ()
    assert tuple(query.reference_type for query in plan.internal_reference_queries) == (
        "person",
        "technology_route",
    )
    person_query, technology_query = plan.internal_reference_queries
    assert technology_query.relationship_evidence_required is True
    assert technology_query.allowed_state_promotions == ()
    assert technology_query.state_semantics == (
        ("discussion_or_mention", "non_adoption"),
        ("claimed_adoption", "claimed_only"),
        ("demonstrated_use", "demonstrated_only"),
    )

    captured_internal_requests: list[Any] = []
    captured_internal_results: list[Any] = []
    captured_web_requests: list[Any] = []

    def capturing_internal_factory(**kwargs: Any) -> Any:
        adapter = internal_factory(**kwargs)

        def captured_adapter(value: Any) -> Any:
            captured_internal_requests.append(value)
            result = adapter(value)
            captured_internal_results.append(result)
            return result

        return captured_adapter

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_internal_reference_lookup_adapter",
        capturing_internal_factory,
    )
    service_kwargs = {
        "release_bundle": bundle,
        "published_release": published,
        "index_projection_request": index_request,
        "release_institution_catalog": institution_catalog,
        "universal_web_policy": plan.web_policy,
        "web_search": lambda value: (
            captured_web_requests.append(value) or read_module.RetrievalLaneResult()
        ),
        "web_snapshot_policy": read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8ir1",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        "clock": lambda: NOW,
    }
    evidence_set = release_read_factory(**service_kwargs).execute(plan)

    assert len(captured_internal_requests) == 1
    internal_request = captured_internal_requests[0]
    assert internal_request.lane == "internal_reference"
    assert (
        internal_request.internal_reference_queries == plan.internal_reference_queries
    )
    assert internal_request.model_dump(mode="json")["internal_reference_queries"] == [
        query.model_dump(mode="json") for query in plan.internal_reference_queries
    ]
    assert len(captured_web_requests) == 1
    assert captured_web_requests[0].lane == "web"
    assert captured_web_requests[0].internal_reference_queries == ()
    assert "internal_reference_queries" not in captured_web_requests[0].model_dump(
        mode="json"
    )

    assert len(captured_internal_results) == 1
    raw_result = captured_internal_results[0]
    assert tuple(candidate.reference_type for candidate in raw_result.candidates) == (
        "person",
        "technology_route",
    )
    assert len(raw_result.candidates) == 2
    assert all(
        candidate.canonical_id == "company-robotics"
        and candidate.domain == "company"
        and candidate.display_name == "Robotics Co"
        and candidate.identity_kind == "canonical"
        and candidate.resolution_state == "resolved"
        and candidate.relationship_state is None
        and candidate.lane == "internal_reference"
        and candidate.adapter_version == "canonical-v2-isolated-internal-reference-v1"
        and candidate.raw_score == 1.0
        and candidate.quality_flags == ()
        for candidate in raw_result.candidates
    )

    candidate_result = index_request.candidate_projection_result
    internal_result = (
        index_request.candidate_projection_request.internal_reference_projection_result
    )
    person_projection = next(
        projection
        for projection in candidate_result.person_projections
        if projection.canonical_person_identity_id
        == person_query.eligible_reference_ids[0]
    )
    route_projection = next(
        projection
        for projection in candidate_result.technology_route_projections
        if projection.canonical_technology_identity_id
        == technology_query.canonical_route_ids[0]
    )
    person_anchors = {
        anchor.anchor_id: anchor for anchor in internal_result.public_evidence_anchors
    }
    technology_anchors = {
        anchor.anchor_id: anchor
        for anchor in internal_result.technology_evidence_anchors
    }
    expected_person_anchor_ids = tuple(
        sorted(
            reference.source_anchor_id
            for reference in person_projection.references
            if person_anchors[reference.source_anchor_id].public_domain == "company"
        )
    )
    expected_route_anchor_ids = tuple(
        sorted(
            anchor_id
            for anchor_id in route_projection.source_anchor_ids
            if technology_anchors[anchor_id].public_domain == "company"
        )
    )
    assert len(expected_person_anchor_ids) == 3
    assert len(expected_route_anchor_ids) == 1

    candidates_by_type = {
        candidate.reference_type: candidate for candidate in raw_result.candidates
    }
    assert candidates_by_type["person"].origin_public_evidence_ids == (
        expected_person_anchor_ids
    )
    assert candidates_by_type["technology_route"].origin_public_evidence_ids == (
        expected_route_anchor_ids
    )
    company_projection = next(
        projection
        for projection in candidate_result.public_domain_projections
        if projection.entity_type == "company"
        and projection.canonical_identity_id == "company-robotics"
    )
    expected_record_hashes = {
        "person": dict(person_query.reference_content_sha256s)[
            person_projection.canonical_person_identity_id
        ],
        "technology_route": dict(technology_query.route_content_sha256s)[
            route_projection.canonical_technology_identity_id
        ],
    }
    expected_projection_hashes = {
        "person": person_projection.content_sha256,
        "technology_route": route_projection.content_sha256,
    }
    expected_claims = {
        "person": (
            person_projection.canonical_person_identity_id,
            "internal_person_filter_match",
            person_projection.content_sha256,
            tuple(
                sorted(
                    {
                        evidence_id
                        for fact in person_query.typed_filters
                        for evidence_id in fact.evidence_ids
                    }
                )
            ),
        ),
        "technology_route": (
            route_projection.canonical_technology_identity_id,
            "definition",
            route_projection.definition,
            technology_query.definition_evidence_ids,
        ),
    }
    expected_anchors_by_type = {
        "person": person_anchors,
        "technology_route": technology_anchors,
    }

    for reference_type, candidate in candidates_by_type.items():
        expected_anchor_ids = (
            expected_person_anchor_ids
            if reference_type == "person"
            else expected_route_anchor_ids
        )
        assert len(candidate.evidence) == len(expected_anchor_ids)
        assert (
            tuple(
                item.local_projection_trace.public_origin_anchor_id
                for item in candidate.evidence
            )
            == expected_anchor_ids
        )
        document = next(
            item
            for item in bundle.index_result.lookup_documents
            if item.projection_scope.value == "internal_auxiliary"
            and item.reference_type == reference_type
            and item.canonical_object_id == expected_claims[reference_type][0]
        )
        assert document.source_evidence_ids != expected_anchor_ids
        assert (
            candidate.raw_candidate_id
            == candidate.evidence[0].local_projection_trace.raw_candidate_id
        )
        assert {
            item.local_projection_trace.raw_candidate_id for item in candidate.evidence
        } == {candidate.raw_candidate_id}
        for item in candidate.evidence:
            trace = item.local_projection_trace
            assert isinstance(trace, read_module.LocalInternalReferenceTrace)
            anchor = expected_anchors_by_type[reference_type][
                trace.public_origin_anchor_id
            ]
            assert trace.path == "internal_reference_lookup"
            assert trace.execution_lane == "internal_reference"
            assert trace.target_id == bundle.index_target.target_id
            assert trace.target_marker_sha256 == bundle.index_target.marker_sha256
            assert trace.manifest_sha256 == bundle.manifest.manifest_sha256
            assert (
                trace.index_result_content_sha256 == bundle.index_result.content_sha256
            )
            assert trace.document_id == document.document_id
            assert trace.release_id == RELEASE_ID
            assert trace.projection_id == document.projection_id
            assert trace.reference_type == reference_type
            assert trace.internal_reference_id == expected_claims[reference_type][0]
            assert (
                trace.internal_projection_content_sha256
                == expected_projection_hashes[reference_type]
            )
            assert (
                trace.reference_record_content_sha256
                == expected_record_hashes[reference_type]
            )
            assert (
                trace.internal_lookup_content_sha256 == document.lookup_content_sha256
            )
            assert (
                trace.internal_lookup_source_evidence_ids
                == document.source_evidence_ids
            )
            assert trace.public_origin_domain == "company"
            assert trace.public_origin_canonical_id == "company-robotics"
            assert trace.public_origin_anchor_content_sha256 == anchor.content_sha256
            assert (
                trace.public_origin_root_projection_content_sha256
                == anchor.root_projection_content_sha256
                == company_projection.content_sha256
            )
            assert trace.lane_request_content_sha256 == internal_request.content_sha256
            assert (
                trace.claim_subject_id,
                trace.claim_predicate,
                trace.claim_value,
                trace.claim_evidence_ids,
            ) == expected_claims[reference_type]
            assert trace.matched_filter_facts == (
                person_query.typed_filters if reference_type == "person" else ()
            )
            assert trace.publication_verification_evidence_ids == (
                "release-verification:s8p1",
            )
            assert item.evidence_id == trace.evidence_id
            assert item.object_id == "company-robotics"
            assert item.domain == "company"
            assert item.lane == "internal_reference"
            assert item.source_nature == "local"
            assert item.source_authority == "canonical_release"
            assert item.score == 1.0
            assert item.claim_binding is not None
            assert (
                item.claim_binding.subject_id,
                item.claim_binding.predicate,
                item.claim_binding.value,
                item.claim_binding.status,
            ) == (*expected_claims[reference_type][:3], None)
            assert item.source_locator.endswith(f":{document.document_id}")
            if reference_type == "technology_route":
                assert item.snippet == route_projection.definition

    assert len(evidence_set.fused_candidates) == 1
    fused = evidence_set.fused_candidates[0]
    assert fused.canonical_id == "company-robotics"
    assert fused.domain == "company"
    assert fused.display_name == "Robotics Co"
    assert fused.raw_candidate_ids == tuple(
        candidate.raw_candidate_id for candidate in raw_result.candidates
    )
    assert len(fused.evidence_ids) == 4
    assert evidence_set.entity_handles == (
        read_module.CanonicalEntityHandle(
            canonical_id="company-robotics",
            domain="company",
            display_name="Robotics Co",
            evidence_ids=fused.evidence_ids,
        ),
    )
    assert all(
        candidate.domain in PUBLIC_DOMAINS
        for candidate in evidence_set.fused_candidates
    )
    assert all(
        trace.disposition == "selected"
        and trace.selected_result_id == "company-robotics"
        for trace in evidence_set.candidate_traces
    )

    direct_adapter = internal_factory(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=institution_catalog,
    )

    def lane_request_with(
        *,
        internal_reference_queries: tuple[Any, ...] | None = None,
        **updates: Any,
    ) -> Any:
        payload = internal_request.model_dump(mode="json", exclude={"content_sha256"})
        if internal_reference_queries is not None:
            payload["internal_reference_queries"] = [
                query.model_dump(mode="json") for query in internal_reference_queries
            ]
        payload.update(updates)
        return read_module.LaneRequest.model_validate(payload)

    assert direct_adapter(lane_request_with(max_candidates=0)).candidates == ()
    bounded = direct_adapter(lane_request_with(max_candidates=1))
    assert tuple(candidate.reference_type for candidate in bounded.candidates) == (
        "person",
    )
    no_match_person_query = read_module.InternalReferenceQuery(
        reference_type="person",
        release_id=RELEASE_ID,
        typed_filters=(
            read_module.InternalReferenceFact(
                field="education",
                value="不存在机构",
                evidence_ids=(),
            ),
        ),
        eligible_reference_ids=(),
        excluded_reference_ids=(
            person_projection.canonical_person_identity_id,
            *(trace.reference_id for trace in person_query.unresolved_reference_traces),
        ),
        originating_public_evidence_ids=(),
        nonmatching_reference_traces=(
            read_module.ReferenceTrace(
                reference_id=person_projection.canonical_person_identity_id,
                resolution_state="resolved",
                failed_filter_fields=("education",),
                evidence_ids=person_query.originating_public_evidence_ids,
            ),
        ),
        unresolved_reference_traces=person_query.unresolved_reference_traces,
        reference_content_sha256s=person_query.reference_content_sha256s,
        public_population=False,
    )
    no_match_result = direct_adapter(
        lane_request_with(
            internal_reference_queries=(
                no_match_person_query,
                technology_query,
            )
        )
    )
    assert tuple(
        candidate.reference_type for candidate in no_match_result.candidates
    ) == ("technology_route",)
    assert all(
        candidate.reference_type != "person"
        and candidate.canonical_id != person_projection.canonical_person_identity_id
        for candidate in no_match_result.candidates
    )
    with pytest.raises(ValidationError, match="internal reference"):
        lane_request_with(lane="web")

    unresolved_person_id = person_query.unresolved_reference_traces[0].reference_id
    changed_fact = person_query.typed_filters[0].model_copy(
        update={"value": "cross-wired institution"}
    )
    invalid_query_pairs = (
        (
            "empty",
            (),
        ),
        (
            "unsupported reference",
            (
                person_query.model_copy(
                    update={"reference_type": "technology_concept"}
                ),
                technology_query,
            ),
        ),
        (
            "cross release",
            (
                person_query.model_copy(update={"release_id": "cross-release-s8ir1"}),
                technology_query,
            ),
        ),
        (
            "duplicate eligible",
            (
                person_query.model_copy(
                    update={
                        "eligible_reference_ids": (
                            *person_query.eligible_reference_ids,
                            *person_query.eligible_reference_ids,
                        )
                    }
                ),
                technology_query,
            ),
        ),
        (
            "eligible excluded overlap",
            (
                person_query.model_copy(
                    update={
                        "excluded_reference_ids": (
                            *person_query.excluded_reference_ids,
                            *person_query.eligible_reference_ids,
                        )
                    }
                ),
                technology_query,
            ),
        ),
        (
            "unresolved admission",
            (
                person_query.model_copy(
                    update={"eligible_reference_ids": (unresolved_person_id,)}
                ),
                technology_query,
            ),
        ),
        (
            "typed filter",
            (
                person_query.model_copy(
                    update={
                        "typed_filters": (
                            changed_fact,
                            *person_query.typed_filters[1:],
                        )
                    }
                ),
                technology_query,
            ),
        ),
        (
            "person record hash",
            (
                person_query.model_copy(
                    update={
                        "reference_content_sha256s": (
                            (
                                person_query.reference_content_sha256s[0][0],
                                "f" * 64,
                            ),
                            *person_query.reference_content_sha256s[1:],
                        )
                    }
                ),
                technology_query,
            ),
        ),
        (
            "person origin",
            (
                person_query.model_copy(update={"originating_public_evidence_ids": ()}),
                technology_query,
            ),
        ),
        (
            "route alias",
            (
                person_query,
                technology_query.model_copy(
                    update={"resolved_aliases": (("other alias", "other-route"),)}
                ),
            ),
        ),
        (
            "route definition evidence",
            (
                person_query,
                technology_query.model_copy(update={"definition_evidence_ids": ()}),
            ),
        ),
        (
            "route record hash",
            (
                person_query,
                technology_query.model_copy(
                    update={
                        "route_content_sha256s": (
                            (technology_query.route_content_sha256s[0][0], "e" * 64),
                        )
                    }
                ),
            ),
        ),
        (
            "route scope",
            (
                person_query,
                technology_query.model_copy(update={"scope": "other scope"}),
            ),
        ),
        (
            "route as of",
            (
                person_query,
                technology_query.model_copy(update={"as_of": NOW - timedelta(days=1)}),
            ),
        ),
    )
    original_reader = isolated_read_module._read_bound_documents
    premature_reads: list[Any] = []

    def unexpected_read(value: Any) -> Any:
        premature_reads.append(value)
        raise AssertionError("invalid internal query must fail before physical lookup")

    monkeypatch.setattr(isolated_read_module, "_read_bound_documents", unexpected_read)
    for _, invalid_queries in invalid_query_pairs:
        with pytest.raises(
            (ValueError, isolated_read_module.IsolatedKnowledgeReadIntegrityError)
        ):
            direct_adapter(
                lane_request_with(internal_reference_queries=invalid_queries)
            )
    with pytest.raises(ValueError, match="internal_reference"):
        direct_adapter(lane_request_with(lane="vector"))
    with pytest.raises(ValueError, match="release"):
        direct_adapter(lane_request_with(release_id="cross-release-s8ir1"))
    with pytest.raises(ValueError, match="non-public"):
        direct_adapter(lane_request_with(domains=("person",)))
    assert premature_reads == []
    monkeypatch.setattr(isolated_read_module, "_read_bound_documents", original_reader)

    internal_documents = tuple(
        document
        for document in bundle.index_result.lookup_documents
        if document.projection_scope.value == "internal_auxiliary"
        and document.reference_type in {"person", "technology_route"}
    )
    person_document = next(
        document
        for document in internal_documents
        if document.reference_type == "person"
    )
    physical_document_mutations = (
        tuple(
            document
            for document in bundle.index_result.lookup_documents
            if document.document_id != person_document.document_id
        ),
        (*bundle.index_result.lookup_documents, person_document),
        tuple(
            person_document.model_copy(update={"release_id": "cross-release-s8ir1"})
            if document.document_id == person_document.document_id
            else document
            for document in bundle.index_result.lookup_documents
        ),
        tuple(
            person_document.model_copy(update={"reference_type": "technology_route"})
            if document.document_id == person_document.document_id
            else document
            for document in bundle.index_result.lookup_documents
        ),
        tuple(
            person_document.model_copy(update={"projection_id": "projection:wrong"})
            if document.document_id == person_document.document_id
            else document
            for document in bundle.index_result.lookup_documents
        ),
        tuple(
            person_document.model_copy(
                update={"source_projection_content_sha256": "d" * 64}
            )
            if document.document_id == person_document.document_id
            else document
            for document in bundle.index_result.lookup_documents
        ),
        tuple(
            person_document.model_copy(update={"lookup_content": "{}"})
            if document.document_id == person_document.document_id
            else document
            for document in bundle.index_result.lookup_documents
        ),
    )
    for hostile_documents in physical_document_mutations:
        monkeypatch.setattr(
            isolated_read_module,
            "_read_bound_documents",
            lambda _value, documents=hostile_documents: documents,
        )
        with pytest.raises(isolated_read_module.IsolatedKnowledgeReadIntegrityError):
            direct_adapter(internal_request)
    monkeypatch.setattr(isolated_read_module, "_read_bound_documents", original_reader)

    integrity_error = isolated_read_module.IsolatedKnowledgeReadIntegrityError
    factory_without_pair = {
        key: value
        for key, value in service_kwargs.items()
        if key not in {"index_projection_request", "release_institution_catalog"}
    }
    with pytest.raises(integrity_error, match="pair|both"):
        release_read_factory(
            **factory_without_pair,
            index_projection_request=index_request,
        )
    with pytest.raises(integrity_error, match="pair|both"):
        release_read_factory(
            **factory_without_pair,
            release_institution_catalog=institution_catalog,
        )

    blocked_reads: list[Any] = []

    def blocked_read(value: Any) -> Any:
        blocked_reads.append(value)
        raise AssertionError("invalid release binding must fail before lookup")

    monkeypatch.setattr(isolated_read_module, "_read_bound_documents", blocked_read)
    service_without_pair = release_read_factory(**factory_without_pair)
    with pytest.raises(integrity_error, match="unsupported lane"):
        service_without_pair.execute(plan)

    binding = plan.release_binding
    assert binding is not None

    def plan_with_binding_field(field: str) -> Any:
        binding_payload = binding.model_dump(mode="json", exclude={"content_sha256"})
        binding_payload[field] = "f" * 64
        changed_binding = read_module.PlanningReleaseBinding.model_validate(
            binding_payload
        )
        plan_payload = plan.model_dump(mode="json", exclude={"content_sha256"})
        plan_payload["release_binding"] = changed_binding.model_dump(mode="json")
        if field == "institution_catalog_sha256":
            plan_payload["institution_slots"] = [
                {
                    **slot,
                    "catalog_sha256": binding_payload[field],
                }
                for slot in plan_payload["institution_slots"]
            ]
            plan_payload["lane_queries"] = [
                {
                    **query,
                    "catalog_sha256": binding_payload[field],
                }
                for query in plan_payload["lane_queries"]
            ]
        return read_module.RetrievalPlan.model_validate(plan_payload)

    for binding_field in (
        "index_projection_request_sha256",
        "candidate_projection_result_sha256",
        "internal_reference_projection_result_sha256",
        "institution_catalog_sha256",
    ):
        with pytest.raises(integrity_error, match="release binding"):
            release_read_factory(**service_kwargs).execute(
                plan_with_binding_field(binding_field)
            )
    assert blocked_reads == []
    monkeypatch.setattr(isolated_read_module, "_read_bound_documents", original_reader)

    physical_reads: list[Any] = []

    def counted_read(value: Any) -> Any:
        physical_reads.append(value)
        return original_reader(value)

    def forged_internal_factory(**kwargs: Any) -> Any:
        adapter = internal_factory(**kwargs)

        def forged_adapter(value: Any) -> Any:
            result = adapter(value)
            forged_candidates = tuple(
                read_module.RecallCandidate.model_validate(
                    {
                        **candidate.model_dump(mode="json"),
                        "display_name": "Forged public display",
                    }
                )
                for candidate in result.candidates
            )
            return read_module.RetrievalLaneResult(candidates=forged_candidates)

        return forged_adapter

    person_trace = candidates_by_type["person"].evidence[0].local_projection_trace
    assert isinstance(person_trace, read_module.LocalInternalReferenceTrace)
    person_trace_payload = person_trace.model_dump(
        mode="json",
        exclude={"raw_candidate_id", "evidence_id", "content_sha256"},
    )
    with pytest.raises(ValidationError, match="Person internal reference trace"):
        read_module.LocalInternalReferenceTrace.model_validate(
            {
                **person_trace_payload,
                "claim_predicate": "geography",
            }
        )
    with pytest.raises(ValidationError, match="Technology internal reference trace"):
        read_module.LocalInternalReferenceTrace.model_validate(
            {
                **person_trace_payload,
                "reference_type": "technology_route",
            }
        )

    def filter_forging_factory(
        forged_filters: tuple[Any, ...],
    ) -> Callable[..., Any]:
        def factory(**kwargs: Any) -> Any:
            adapter = internal_factory(**kwargs)

            def forged_adapter(value: Any) -> Any:
                result = adapter(value)
                forged_candidates: list[Any] = []
                for candidate in result.candidates:
                    if candidate.reference_type != "person":
                        forged_candidates.append(candidate)
                        continue
                    claim_evidence_ids = tuple(
                        sorted(
                            {
                                evidence_id
                                for fact in forged_filters
                                for evidence_id in fact.evidence_ids
                            }
                        )
                    )
                    forged_evidence: list[Any] = []
                    for item in candidate.evidence:
                        trace = item.local_projection_trace
                        assert isinstance(
                            trace,
                            read_module.LocalInternalReferenceTrace,
                        )
                        trace_payload = trace.model_dump(
                            mode="json",
                            exclude={
                                "raw_candidate_id",
                                "evidence_id",
                                "content_sha256",
                            },
                        )
                        trace_payload.update(
                            {
                                "matched_filter_facts": [
                                    fact.model_dump(mode="json")
                                    for fact in forged_filters
                                ],
                                "claim_evidence_ids": claim_evidence_ids,
                            }
                        )
                        forged_trace = (
                            read_module.LocalInternalReferenceTrace.model_validate(
                                trace_payload
                            )
                        )
                        forged_evidence.append(
                            read_module.EvidenceItem.model_validate(
                                {
                                    **item.model_dump(mode="json"),
                                    "evidence_id": forged_trace.evidence_id,
                                    "local_projection_trace": forged_trace.model_dump(
                                        mode="json"
                                    ),
                                }
                            )
                        )
                    raw_ids = {
                        item.local_projection_trace.raw_candidate_id
                        for item in forged_evidence
                    }
                    assert len(raw_ids) == 1
                    forged_candidates.append(
                        read_module.RecallCandidate.model_validate(
                            {
                                **candidate.model_dump(mode="json"),
                                "raw_candidate_id": next(iter(raw_ids)),
                                "evidence": [
                                    item.model_dump(mode="json")
                                    for item in forged_evidence
                                ],
                            }
                        )
                    )
                return read_module.RetrievalLaneResult(
                    candidates=tuple(forged_candidates)
                )

            return forged_adapter

        return factory

    without_geography = tuple(
        fact for fact in person_query.typed_filters if fact.field != "geography"
    )
    changed_geography = tuple(
        read_module.InternalReferenceFact(
            field=fact.field,
            value=("广州" if fact.field == "geography" else fact.value),
            evidence_ids=fact.evidence_ids,
        )
        for fact in person_query.typed_filters
    )

    monkeypatch.setattr(isolated_read_module, "_read_bound_documents", counted_read)
    hostile_factories = (
        forged_internal_factory,
        filter_forging_factory(without_geography),
        filter_forging_factory(changed_geography),
    )
    for expected_read_count, hostile_factory in enumerate(hostile_factories, start=1):
        monkeypatch.setattr(
            isolated_read_module,
            "create_isolated_internal_reference_lookup_adapter",
            hostile_factory,
        )
        with pytest.raises(integrity_error, match="display|internal reference"):
            release_read_factory(**service_kwargs).execute(plan)
        assert len(physical_reads) == expected_read_count
    monkeypatch.setattr(isolated_read_module, "_read_bound_documents", original_reader)

    assert {
        name: _file_sha256(bundle.index_target.root / name)
        for name in fixture["target_hashes"]
    } == fixture["target_hashes"]
    assert _file_sha256(fixture["original_milvus"]) == fixture["original_sha256"]


S8R1_SCOPE = "representative Companies related to one accepted Technology route"
S8R1_SNAPSHOT_FLAG = "relationship_snapshot_as_of:2026-07-13T17:00:00Z"


def _s8r1_institution_catalog(read_module: Any, *, release_id: str) -> Any:
    return read_module.InstitutionCatalog(
        catalog_id=f"institution-catalog:s8r1:{release_id}",
        catalog_version="institution-catalog-v1",
        release_id=release_id,
        entries=(),
    )


def _s8r1_planning_policy(read_module: Any) -> Any:
    return read_module.QueryPlanningPolicy(
        policy_id="planning-policy:s8r1-release-bound",
        policy_version="query-planning-policy-v1",
        public_domains=PUBLIC_DOMAINS,
        supported_lanes=("relationship", "web"),
        supported_relationship_paths=(
            ("technology_company_relationship", "technology_to_company"),
        ),
        max_candidates=20,
        max_provider_calls=1,
        max_planning_attempts=1,
    )


def _s8r1_planning_request(
    read_module: Any,
    *,
    release_id: str,
    as_of: datetime = NOW,
) -> Any:
    return read_module.QueryPlanningRequest(
        request_id=f"query-request:s8r1:{release_id}:{as_of.isoformat()}",
        release_id=release_id,
        original_query="列出vision servo路线的代表性企业",
        as_of=as_of,
        enumeration_context=read_module.EnumerationPlanningContext(
            requested=True,
            scope=S8R1_SCOPE,
            as_of=as_of,
            finite_universe=None,
            required_member_ids=(),
        ),
    )


def _s8r1_proposal(read_module: Any, value: Any) -> Any:
    return read_module.RecordedPlanningProposal(
        proposal_id="planning-proposal:s8r1-release-bound",
        request_sha256=value.content_sha256,
        schema_version="retrieval-plan-proposal-v1",
        model_id="recorded-planner-fixture",
        prompt_version="query-plan-prompt-v1",
        behavior_class="E",
        interaction_mode="information_retrieval",
        domains=("company",),
        lanes=("relationship", "web"),
        relationship_paths=(
            read_module.RelationshipPathProposal(
                relationship_type_id="technology_company_relationship",
                direction="technology_to_company",
                source_type="technology_route",
                target_type="company",
            ),
        ),
        max_candidates=20,
        max_provider_calls=1,
        enumeration_mode="representative",
        internal_reference_targets=("technology_route",),
        web_mode="universal",
        max_web_results=5,
    )


def _s8r1_plan(
    *,
    read_module: Any,
    isolated_read_module: Any,
    bundle: Any,
    published: Any,
    index_request: Any,
    institution_catalog: Any,
    as_of: datetime = NOW,
) -> Any:
    return isolated_read_module.create_isolated_release_query_planner(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=institution_catalog,
        planning_policy=_s8r1_planning_policy(read_module),
        proposal_provider=lambda value: _s8r1_proposal(read_module, value),
    ).plan(
        _s8r1_planning_request(
            read_module,
            release_id=bundle.release_id,
            as_of=as_of,
        )
    )


def _s8r1_lane_request(read_module: Any, plan: Any) -> Any:
    lane_query = next(
        (query for query in plan.lane_queries if query.lane == "relationship"),
        None,
    )
    return read_module.LaneRequest(
        lane="relationship",
        release_id=plan.release_id,
        query_view="view:original",
        original_query=plan.original_query,
        behavior_class=plan.behavior_class,
        interaction_mode=plan.interaction_mode,
        web_policy=plan.web_policy,
        query_text=(
            lane_query.query_text if lane_query is not None else plan.original_query
        ),
        domains=plan.domains,
        protected_slots=plan.protected_slots,
        structured_constraints=plan.structured_constraints,
        max_candidates=plan.max_candidates,
        relationship_paths=plan.relationship_paths,
        relationship_reference_queries=tuple(
            query
            for query in plan.internal_reference_queries
            if query.reference_type == "technology_route"
        ),
    )


S8R2_SCOPE = "representative Patents naming one displayed Company as applicant"


def _s8r2_institution_catalog(read_module: Any, *, release_id: str) -> Any:
    return read_module.InstitutionCatalog(
        catalog_id=f"institution-catalog:s8r2:{release_id}",
        catalog_version="institution-catalog-v1",
        release_id=release_id,
        entries=(
            read_module.InstitutionCatalogEntry(
                canonical_id="institution:sustech",
                canonical_name="SUSTech",
                aliases=(),
            ),
        ),
    )


def _s8r2_planning_policy(read_module: Any) -> Any:
    return read_module.QueryPlanningPolicy(
        policy_id="planning-policy:s8r2-release-bound",
        policy_version="query-planning-policy-v1",
        public_domains=PUBLIC_DOMAINS,
        supported_lanes=("relationship", "web"),
        supported_relationship_paths=(("company_has_patent", "company_to_patent"),),
        max_candidates=20,
        max_provider_calls=1,
        max_planning_attempts=1,
    )


def _s8r2_planning_request(
    read_module: Any,
    *,
    release_id: str,
    as_of: datetime = NOW,
) -> Any:
    return read_module.QueryPlanningRequest(
        request_id=f"query-request:s8r2:{release_id}:{as_of.isoformat()}",
        release_id=release_id,
        original_query="列出已展示 Robotics Co 作为申请人的代表性专利",
        as_of=as_of,
        displayed_entity_ids=("company-robotics",),
        enumeration_context=read_module.EnumerationPlanningContext(
            requested=True,
            scope=S8R2_SCOPE,
            as_of=as_of,
            finite_universe=None,
            required_member_ids=(),
        ),
    )


def _s8r2_proposal(read_module: Any, value: Any) -> Any:
    return read_module.RecordedPlanningProposal(
        proposal_id="planning-proposal:s8r2-release-bound",
        request_sha256=value.content_sha256,
        schema_version="retrieval-plan-proposal-v1",
        model_id="recorded-planner-fixture",
        prompt_version="query-plan-prompt-v1",
        behavior_class="E",
        interaction_mode="information_retrieval",
        domains=("patent",),
        lanes=("relationship", "web"),
        relationship_paths=(
            read_module.RelationshipPathProposal(
                relationship_type_id="company_has_patent",
                direction="company_to_patent",
                source_type="company",
                target_type="patent",
            ),
        ),
        max_candidates=20,
        max_provider_calls=1,
        enumeration_mode="representative",
        internal_reference_targets=(),
        web_mode="universal",
        max_web_results=5,
    )


def _s8r2_plan(
    *,
    read_module: Any,
    isolated_read_module: Any,
    bundle: Any,
    published: Any,
    index_request: Any,
    institution_catalog: Any,
    as_of: datetime = NOW,
) -> Any:
    return isolated_read_module.create_isolated_release_query_planner(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=institution_catalog,
        planning_policy=_s8r2_planning_policy(read_module),
        proposal_provider=lambda value: _s8r2_proposal(read_module, value),
    ).plan(
        _s8r2_planning_request(
            read_module,
            release_id=bundle.release_id,
            as_of=as_of,
        )
    )


def _s8r2_scenario(
    *,
    tmp_path: Path,
    release_id: str,
    authoritative_zero: bool = False,
    nonmatching_relationship_authority: bool = False,
    limited_endpoint_ids: tuple[str, ...] = (),
    excluded_endpoint_ids: tuple[str, ...] = (),
    as_of: datetime = NOW,
) -> dict[str, Any]:
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    isolated_read_module = _isolated_knowledge_read_module()
    release_module = _isolated_release_publication_module()
    index_module = _index_projection_module()
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    if nonmatching_relationship_authority:
        assert not authoritative_zero
        assert not limited_endpoint_ids
        assert not excluded_endpoint_ids
        authority = _technology_relationship_authority(release_id=release_id)
        index_request = _index_projection_request(
            index_module,
            authority[0],
            authority[1],
        )
    else:
        authority = _company_patent_relationship_authority(
            release_id=release_id,
            authoritative_zero=authoritative_zero,
        )
        index_request = _s8r2_index_projection_request(
            index_module,
            authority,
            limited_endpoint_ids=limited_endpoint_ids,
            excluded_endpoint_ids=excluded_endpoint_ids,
        )
    bundle = _s7k_release_bundle(
        release_module,
        tmp_path=tmp_path,
        release_id=release_id,
        authority=authority,
        exact_index_projection_request=index_request,
    )
    published = _s8p1_published_release(contracts_module, release_id=release_id)
    catalog = (
        _s8r1_institution_catalog(read_module, release_id=release_id)
        if nonmatching_relationship_authority
        else _s8r2_institution_catalog(read_module, release_id=release_id)
    )
    plan = _s8r2_plan(
        read_module=read_module,
        isolated_read_module=isolated_read_module,
        bundle=bundle,
        published=published,
        index_request=index_request,
        institution_catalog=catalog,
        as_of=as_of,
    )
    return {
        "authority": authority,
        "index_request": index_request,
        "bundle": bundle,
        "published": published,
        "catalog": catalog,
        "plan": plan,
    }


S8R3_SCOPE = "representative Papers attributed to one displayed Professor"


def _s8r3_planning_policy(read_module: Any) -> Any:
    return read_module.QueryPlanningPolicy(
        policy_id="planning-policy:s8r3-release-bound",
        policy_version="query-planning-policy-v1",
        public_domains=PUBLIC_DOMAINS,
        supported_lanes=("relationship", "web"),
        supported_relationship_paths=(
            ("professor_authored_paper", "professor_to_paper"),
        ),
        max_candidates=20,
        max_provider_calls=1,
        max_planning_attempts=1,
    )


def _s8r3_planning_request(
    read_module: Any,
    *,
    release_id: str,
    as_of: datetime = NOW,
) -> Any:
    return read_module.QueryPlanningRequest(
        request_id=f"query-request:s8r3:{release_id}:{as_of.isoformat()}",
        release_id=release_id,
        original_query="列出已展示陈艾达教授有证据归属的代表性论文",
        as_of=as_of,
        displayed_entity_ids=("professor-ada",),
        enumeration_context=read_module.EnumerationPlanningContext(
            requested=True,
            scope=S8R3_SCOPE,
            as_of=as_of,
            finite_universe=None,
            required_member_ids=(),
        ),
    )


def _s8r3_proposal(read_module: Any, value: Any) -> Any:
    return read_module.RecordedPlanningProposal(
        proposal_id="planning-proposal:s8r3-release-bound",
        request_sha256=value.content_sha256,
        schema_version="retrieval-plan-proposal-v1",
        model_id="recorded-planner-fixture",
        prompt_version="query-plan-prompt-v1",
        behavior_class="E",
        interaction_mode="information_retrieval",
        domains=("paper",),
        lanes=("relationship", "web"),
        relationship_paths=(
            read_module.RelationshipPathProposal(
                relationship_type_id="professor_authored_paper",
                direction="professor_to_paper",
                source_type="professor",
                target_type="paper",
            ),
        ),
        max_candidates=20,
        max_provider_calls=1,
        enumeration_mode="representative",
        internal_reference_targets=(),
        web_mode="universal",
        max_web_results=5,
    )


def _s8r3_plan(
    *,
    read_module: Any,
    isolated_read_module: Any,
    bundle: Any,
    published: Any,
    index_request: Any,
    institution_catalog: Any,
    as_of: datetime = NOW,
) -> Any:
    return isolated_read_module.create_isolated_release_query_planner(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=institution_catalog,
        planning_policy=_s8r3_planning_policy(read_module),
        proposal_provider=lambda value: _s8r3_proposal(read_module, value),
    ).plan(
        _s8r3_planning_request(
            read_module,
            release_id=bundle.release_id,
            as_of=as_of,
        )
    )


def _s8r3_scenario(
    *,
    tmp_path: Path,
    release_id: str,
    authoritative_zero: bool = False,
    nonmatching_relationship_authority: bool = False,
    decision_state: str = "accepted",
    multiple_retained_refs: bool = False,
    paper_identity_status: str = "confirmed",
    limited_endpoint_ids: tuple[str, ...] = (),
    excluded_endpoint_ids: tuple[str, ...] = (),
    as_of: datetime = NOW,
) -> dict[str, Any]:
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    isolated_read_module = _isolated_knowledge_read_module()
    release_module = _isolated_release_publication_module()
    index_module = _index_projection_module()
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    if nonmatching_relationship_authority:
        assert not authoritative_zero
        assert decision_state == "accepted"
        assert not multiple_retained_refs
        assert paper_identity_status == "confirmed"
        assert not limited_endpoint_ids
        assert not excluded_endpoint_ids
        authority = _company_patent_relationship_authority(release_id=release_id)
        index_request = _s8r2_index_projection_request(
            index_module,
            authority,
        )
    else:
        authority = _professor_paper_relationship_authority(
            release_id=release_id,
            authoritative_zero=authoritative_zero,
            decision_state=decision_state,
            multiple_retained_refs=multiple_retained_refs,
        )
        index_request = _s8r3_index_projection_request(
            index_module,
            authority,
            paper_identity_status=paper_identity_status,
            limited_endpoint_ids=limited_endpoint_ids,
            excluded_endpoint_ids=excluded_endpoint_ids,
        )
    bundle = _s7k_release_bundle(
        release_module,
        tmp_path=tmp_path,
        release_id=release_id,
        authority=authority,
        exact_index_projection_request=index_request,
    )
    published = _s8p1_published_release(contracts_module, release_id=release_id)
    catalog = _s8r2_institution_catalog(read_module, release_id=release_id)
    plan = _s8r3_plan(
        read_module=read_module,
        isolated_read_module=isolated_read_module,
        bundle=bundle,
        published=published,
        index_request=index_request,
        institution_catalog=catalog,
        as_of=as_of,
    )
    return {
        "authority": authority,
        "index_request": index_request,
        "bundle": bundle,
        "published": published,
        "catalog": catalog,
        "plan": plan,
    }


S8R4_SCOPE = "representative Professors attributed to one displayed Paper"


def _s8r4_planning_policy(read_module: Any) -> Any:
    return read_module.QueryPlanningPolicy(
        policy_id="planning-policy:s8r4-release-bound",
        policy_version="query-planning-policy-v1",
        public_domains=PUBLIC_DOMAINS,
        supported_lanes=("relationship", "web"),
        supported_relationship_paths=(
            ("professor_authored_paper", "paper_to_professor"),
        ),
        max_candidates=20,
        max_provider_calls=1,
        max_planning_attempts=1,
    )


def _s8r4_planning_request(
    read_module: Any,
    *,
    release_id: str,
    as_of: datetime = NOW,
) -> Any:
    return read_module.QueryPlanningRequest(
        request_id=f"query-request:s8r4:{release_id}:{as_of.isoformat()}",
        release_id=release_id,
        original_query="列出与已展示论文存在证据归属关系的代表性教授",
        as_of=as_of,
        displayed_entity_ids=("paper-ada",),
        enumeration_context=read_module.EnumerationPlanningContext(
            requested=True,
            scope=S8R4_SCOPE,
            as_of=as_of,
            finite_universe=None,
            required_member_ids=(),
        ),
    )


def _s8r4_proposal(read_module: Any, value: Any) -> Any:
    return read_module.RecordedPlanningProposal(
        proposal_id="planning-proposal:s8r4-release-bound",
        request_sha256=value.content_sha256,
        schema_version="retrieval-plan-proposal-v1",
        model_id="recorded-planner-fixture",
        prompt_version="query-plan-prompt-v1",
        behavior_class="E",
        interaction_mode="information_retrieval",
        domains=("professor",),
        lanes=("relationship", "web"),
        relationship_paths=(
            read_module.RelationshipPathProposal(
                relationship_type_id="professor_authored_paper",
                direction="paper_to_professor",
                source_type="paper",
                target_type="professor",
            ),
        ),
        max_candidates=20,
        max_provider_calls=1,
        enumeration_mode="representative",
        internal_reference_targets=(),
        web_mode="universal",
        max_web_results=5,
    )


def _s8r4_plan(
    *,
    read_module: Any,
    isolated_read_module: Any,
    bundle: Any,
    published: Any,
    index_request: Any,
    institution_catalog: Any,
    as_of: datetime = NOW,
) -> Any:
    return isolated_read_module.create_isolated_release_query_planner(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=institution_catalog,
        planning_policy=_s8r4_planning_policy(read_module),
        proposal_provider=lambda value: _s8r4_proposal(read_module, value),
    ).plan(
        _s8r4_planning_request(
            read_module,
            release_id=bundle.release_id,
            as_of=as_of,
        )
    )


def _s8r4_scenario(
    *,
    tmp_path: Path,
    release_id: str,
    authoritative_zero: bool = False,
    nonmatching_relationship_authority: bool = False,
    decision_state: str = "accepted",
    multiple_retained_refs: bool = False,
    paper_identity_status: str = "confirmed",
    limited_endpoint_ids: tuple[str, ...] = (),
    excluded_endpoint_ids: tuple[str, ...] = (),
    as_of: datetime = NOW,
) -> dict[str, Any]:
    scenario = _s8r3_scenario(
        tmp_path=tmp_path,
        release_id=release_id,
        authoritative_zero=authoritative_zero,
        nonmatching_relationship_authority=nonmatching_relationship_authority,
        decision_state=decision_state,
        multiple_retained_refs=multiple_retained_refs,
        paper_identity_status=paper_identity_status,
        limited_endpoint_ids=limited_endpoint_ids,
        excluded_endpoint_ids=excluded_endpoint_ids,
        as_of=as_of,
    )
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    scenario["plan"] = _s8r4_plan(
        read_module=read_module,
        isolated_read_module=_isolated_knowledge_read_module(),
        bundle=scenario["bundle"],
        published=scenario["published"],
        index_request=scenario["index_request"],
        institution_catalog=scenario["catalog"],
        as_of=as_of,
    )
    return scenario


S8R5_SCOPE = "representative Companies named as applicants by one displayed Patent"


def _s8r5_planning_policy(read_module: Any) -> Any:
    return read_module.QueryPlanningPolicy(
        policy_id="planning-policy:s8r5-release-bound",
        policy_version="query-planning-policy-v1",
        public_domains=PUBLIC_DOMAINS,
        supported_lanes=("relationship", "web"),
        supported_relationship_paths=(("company_has_patent", "patent_to_company"),),
        max_candidates=20,
        max_provider_calls=1,
        max_planning_attempts=1,
    )


def _s8r5_planning_request(
    read_module: Any,
    *,
    release_id: str,
    as_of: datetime = NOW,
) -> Any:
    return read_module.QueryPlanningRequest(
        request_id=f"query-request:s8r5:{release_id}:{as_of.isoformat()}",
        release_id=release_id,
        original_query="列出已展示专利中有证据记载为申请人的代表性企业",
        as_of=as_of,
        displayed_entity_ids=("patent-ada",),
        enumeration_context=read_module.EnumerationPlanningContext(
            requested=True,
            scope=S8R5_SCOPE,
            as_of=as_of,
            finite_universe=None,
            required_member_ids=(),
        ),
    )


def _s8r5_proposal(read_module: Any, value: Any) -> Any:
    return read_module.RecordedPlanningProposal(
        proposal_id="planning-proposal:s8r5-release-bound",
        request_sha256=value.content_sha256,
        schema_version="retrieval-plan-proposal-v1",
        model_id="recorded-planner-fixture",
        prompt_version="query-plan-prompt-v1",
        behavior_class="E",
        interaction_mode="information_retrieval",
        domains=("company",),
        lanes=("relationship", "web"),
        relationship_paths=(
            read_module.RelationshipPathProposal(
                relationship_type_id="company_has_patent",
                direction="patent_to_company",
                source_type="patent",
                target_type="company",
            ),
        ),
        max_candidates=20,
        max_provider_calls=1,
        enumeration_mode="representative",
        internal_reference_targets=(),
        web_mode="universal",
        max_web_results=5,
    )


def _s8r5_plan(
    *,
    read_module: Any,
    isolated_read_module: Any,
    bundle: Any,
    published: Any,
    index_request: Any,
    institution_catalog: Any,
    as_of: datetime = NOW,
) -> Any:
    return isolated_read_module.create_isolated_release_query_planner(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=institution_catalog,
        planning_policy=_s8r5_planning_policy(read_module),
        proposal_provider=lambda value: _s8r5_proposal(read_module, value),
    ).plan(
        _s8r5_planning_request(
            read_module,
            release_id=bundle.release_id,
            as_of=as_of,
        )
    )


def _s8r5_scenario(
    *,
    tmp_path: Path,
    release_id: str,
    authoritative_zero: bool = False,
    nonmatching_relationship_authority: bool = False,
    limited_endpoint_ids: tuple[str, ...] = (),
    excluded_endpoint_ids: tuple[str, ...] = (),
    as_of: datetime = NOW,
) -> dict[str, Any]:
    scenario = _s8r2_scenario(
        tmp_path=tmp_path,
        release_id=release_id,
        authoritative_zero=authoritative_zero,
        nonmatching_relationship_authority=nonmatching_relationship_authority,
        limited_endpoint_ids=limited_endpoint_ids,
        excluded_endpoint_ids=excluded_endpoint_ids,
        as_of=as_of,
    )
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    scenario["plan"] = _s8r5_plan(
        read_module=read_module,
        isolated_read_module=_isolated_knowledge_read_module(),
        bundle=scenario["bundle"],
        published=scenario["published"],
        index_request=scenario["index_request"],
        institution_catalog=scenario["catalog"],
        as_of=as_of,
    )
    return scenario


def _s8r1_literal_lane_request(read_module: Any) -> Any:
    enumeration = read_module.EnumerationPolicy(
        mode="representative",
        scope="Companies using robotics",
        as_of=NOW,
        exhaustive=False,
        continuation_state="available",
    )
    relationship_query = read_module.InternalReferenceQuery(
        reference_type="technology_route",
        release_id="candidate-s8r1-literal",
        canonical_route_ids=("technology-route:robotics",),
        resolved_aliases=(("robotics", "technology-route:robotics"),),
        relationship_states=(
            "discussion_or_mention",
            "claimed_adoption",
            "demonstrated_use",
        ),
        scope="Companies using robotics",
        as_of=NOW,
        definition_evidence_ids=("evidence:technology:robotics",),
        route_content_sha256s=(("technology-route:robotics", "1" * 64),),
        definition_evidence_required=True,
        relationship_evidence_required=True,
        state_semantics=(
            ("claimed_adoption", "claim"),
            ("demonstrated_use", "demonstration"),
            ("discussion_or_mention", "mention"),
        ),
        enumeration_policy=enumeration,
    )
    return read_module.LaneRequest(
        lane="relationship",
        release_id="candidate-s8r1-literal",
        query_view="view:original",
        original_query="Which companies use robotics?",
        behavior_class="D",
        interaction_mode="information_retrieval",
        web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=5,
        ),
        query_text="Which companies use robotics?",
        domains=("company",),
        protected_slots=(
            read_module.ProtectedSlot(
                kind="technology",
                value="robotics",
                entity_ids=("technology-route:robotics",),
            ),
        ),
        structured_constraints=read_module.StructuredConstraints(),
        max_candidates=10,
        relationship_paths=(
            read_module.RelationshipPathProposal(
                relationship_type_id="technology_company_relationship",
                direction="technology_to_company",
                source_type="technology_route",
                target_type="company",
            ),
        ),
        relationship_reference_queries=(relationship_query,),
    )


def _s8r1_literal_relationship_trace(read_module: Any, lane_request: Any) -> Any:
    return read_module.LocalRelationshipTrace(
        target_id="target:s8r1-literal",
        target_marker_sha256="2" * 64,
        manifest_sha256="3" * 64,
        index_result_content_sha256="4" * 64,
        publication_verification_evidence_ids=("publication:evidence:1",),
        release_id="candidate-s8r1-literal",
        lane_request_content_sha256=lane_request.content_sha256,
        relationship_request_sha256="5" * 64,
        relationship_result_sha256="6" * 64,
        relationship_projection_run_id="relationship-run:s8r1-literal",
        relationship_projection_schema_version=(
            "canonical-v2-relationship-projection-v1"
        ),
        relationship_registry_version="canonical-v2-relationship-v1",
        relationship_registry_content_sha256="7" * 64,
        relationship_snapshot_as_of=NOW,
        query_as_of=NOW,
        technology_route_id="technology-route:robotics",
        technology_route_projection_id="technology-route:robotics",
        technology_route_projection_content_sha256="8" * 64,
        canonical_relationship_id="relationship:s8r1-literal",
        current_relationship_content_sha256="9" * 64,
        relationship_decision_id="relationship-decision:s8r1-literal",
        relationship_decision_content_sha256="a" * 64,
        relationship_type_id="entity_claims_adoption_of_technology",
        relationship_type_version="canonical-v2-relationship-v1",
        relationship_source_endpoint="product:robot-arm",
        relationship_source_endpoint_content_sha256="b" * 64,
        relationship_source_parent_canonical_identity_ref=(
            "canonical:company:company-robotics"
        ),
        relationship_target_endpoint=(
            "canonical:technology_route:technology-route:robotics"
        ),
        relationship_target_endpoint_content_sha256="c" * 64,
        relationship_role_bindings=(
            ("product", "product:robot-arm"),
            (
                "technology",
                "canonical:technology_route:technology-route:robotics",
            ),
        ),
        selected_evidence_refs=("retained-reference:s8r1-literal",),
        relationship_state="claimed_adoption",
        retained_reference_id="retained-reference:s8r1-literal",
        retained_reference_content_sha256="d" * 64,
        retained_assertion_id="assertion:s8r1-literal",
        retained_source_record_id="source-record:s8r1-literal",
        public_assertion_id="assertion:s8r1-literal",
        public_assertion_content_sha256="e" * 64,
        source_record_id="source-record:s8r1-literal",
        technology_anchor_id="technology-anchor:s8r1-literal",
        technology_anchor_content_sha256="f" * 64,
        technology_anchor_source_identity_id="source-identity:s8r1-literal",
        product_subobject_id="product:robot-arm",
        product_subobject_content_sha256="0" * 64,
        root_company_id="company-robotics",
        root_company_projection_content_sha256="1" * 64,
        root_company_display_name="Robotics Co",
        path_eligibility_result_content_sha256="2" * 64,
        eligibility_decision_id="eligibility-decision:s8r1-literal",
        eligibility_policy_id="eligibility-policy:s8r1-literal",
        eligibility_policy_version="eligibility-policy-v1",
        eligibility_policy_content_sha256="3" * 64,
        eligibility_policy_effective_at=NOW,
        eligibility_outcome="admitted",
        eligibility_supporting_assertion_ids=("assertion:s8r1-literal",),
        claim_subject_id="product:robot-arm",
        claim_predicate="entity_claims_adoption_of_technology",
        claim_value="canonical:technology_route:technology-route:robotics",
        claim_status="claimed_adoption",
        snippet_sha256="4" * 64,
    )


def _serialized_contract_sha256(value: Any) -> str:
    serialized = json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def test_s8r1_relationship_request_and_trace_literal_compatibility() -> None:
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    lane_request = _s8r1_literal_lane_request(read_module)
    lane_payload = lane_request.model_dump(mode="json")
    assert "relationship_enumeration_policy" not in lane_payload
    assert lane_request.content_sha256 == S8R1_RELATIONSHIP_LANE_REQUEST_CONTENT_SHA256
    assert (
        _serialized_contract_sha256(lane_request)
        == S8R1_RELATIONSHIP_LANE_REQUEST_SERIALIZED_SHA256
    )
    assert read_module.LaneRequest.model_validate(lane_payload) == lane_request

    relationship_trace = _s8r1_literal_relationship_trace(
        read_module,
        lane_request,
    )
    trace_payload = relationship_trace.model_dump(mode="json")
    assert relationship_trace.content_sha256 == S8R1_RELATIONSHIP_TRACE_CONTENT_SHA256
    assert (
        _serialized_contract_sha256(relationship_trace)
        == S8R1_RELATIONSHIP_TRACE_SERIALIZED_SHA256
    )
    assert (
        read_module.LocalRelationshipTrace.model_validate(trace_payload)
        == relationship_trace
    )
    trace_adapter = TypeAdapter(read_module.LocalEvidenceTrace)
    union_trace = trace_adapter.validate_python(trace_payload)
    assert type(union_trace) is read_module.LocalRelationshipTrace
    assert json.loads(trace_adapter.dump_json(union_trace)) == trace_payload


def test_s8r2_executes_release_scoped_company_to_patent_relationship_traversal(
    request: pytest.FixtureRequest,
) -> None:
    read_module, relationship_factory, release_factory = (
        _s8r2_public_relationship_contract()
    )
    tmp_path: Path = request.getfixturevalue("tmp_path")
    monkeypatch: pytest.MonkeyPatch = request.getfixturevalue("monkeypatch")
    isolated_read_module = _isolated_knowledge_read_module()
    index_module = _index_projection_module()

    release_id = "candidate-s8r2-company-patent"
    positive = _s8r2_scenario(
        tmp_path=tmp_path,
        release_id=release_id,
    )
    authority = positive["authority"]
    index_request = positive["index_request"]
    bundle = positive["bundle"]
    published = positive["published"]
    catalog = positive["catalog"]
    plan = positive["plan"]
    internal_person_id = authority[1].person_projections[0].canonical_person_identity_id
    assert (
        index_module.create_ephemeral_index_projection_builder().build(index_request)
        == bundle.index_result
    )
    assert plan.domains == ("patent",)
    assert plan.lanes == ("relationship", "web")
    assert plan.relationship_paths == (
        read_module.RelationshipPathProposal(
            relationship_type_id="company_has_patent",
            direction="company_to_patent",
            source_type="company",
            target_type="patent",
        ),
    )
    assert plan.structured_constraints.displayed_entity_ids == ("company-robotics",)
    assert tuple(
        slot.entity_ids
        for slot in plan.protected_slots
        if slot.kind == "displayed_entity_set"
    ) == (("company-robotics",),)
    assert plan.internal_reference_queries == ()
    assert plan.enumeration_policy is not None
    assert plan.enumeration_policy.mode == "representative"
    assert plan.enumeration_policy.scope == S8R2_SCOPE
    assert plan.enumeration_policy.as_of == NOW
    assert plan.enumeration_policy.finite_universe_id is None
    assert plan.enumeration_policy.eligible_member_ids == ()
    assert plan.enumeration_policy.required_member_ids == ()
    assert plan.enumeration_policy.exhaustive is False
    assert plan.enumeration_policy.continuation_state == "available"

    captured_relationship_requests: list[Any] = []
    captured_relationship_results: list[Any] = []
    captured_web_requests: list[Any] = []
    real_relationship_factory = relationship_factory

    def capturing_relationship_factory(**kwargs: Any) -> Any:
        adapter = real_relationship_factory(**kwargs)

        def captured_adapter(value: Any) -> Any:
            captured_relationship_requests.append(value)
            result = adapter(value)
            captured_relationship_results.append(result)
            return result

        return captured_adapter

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        capturing_relationship_factory,
    )
    physical_reads: list[Any] = []

    def forbidden_physical_read(value: Any) -> Any:
        physical_reads.append(value)
        raise AssertionError("S8R2 relationship traversal must remain in memory")

    monkeypatch.setattr(
        isolated_read_module,
        "_read_bound_documents",
        forbidden_physical_read,
    )
    evidence_set = release_factory(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=catalog,
        universal_web_policy=plan.web_policy,
        web_search=lambda value: (
            captured_web_requests.append(value) or read_module.RetrievalLaneResult()
        ),
        web_snapshot_policy=read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8r2",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        clock=lambda: NOW,
    ).execute(plan)

    def plan_with_relationship_paths(paths: tuple[Any, ...]) -> Any:
        payload = plan.model_dump(mode="json", exclude={"content_sha256"})
        payload["relationship_paths"] = [path.model_dump(mode="json") for path in paths]
        return read_module.RetrievalPlan.model_validate(payload)

    boundary_read = read_module.create_ephemeral_knowledge_read(
        lane_adapters={
            "relationship": lambda _: read_module.RetrievalLaneResult(),
            "web": lambda _: read_module.RetrievalLaneResult(),
        },
        universal_web_policy=plan.web_policy,
        clock=lambda: NOW,
    )
    other_public_path = read_module.RelationshipPathProposal(
        relationship_type_id="company_has_patent",
        direction="patent_to_company",
        source_type="patent",
        target_type="company",
    )
    unknown_path = read_module.RelationshipPathProposal(
        relationship_type_id="unknown_public_relationship",
        direction="unknown_direction",
        source_type="company",
        target_type="paper",
    )
    technology_path = read_module.RelationshipPathProposal(
        relationship_type_id="technology_company_relationship",
        direction="technology_to_company",
        source_type="technology_route",
        target_type="company",
    )
    negative_path_cases = (
        (),
        (plan.relationship_paths[0], other_public_path),
        (unknown_path,),
        (technology_path,),
    )
    for paths in negative_path_cases:
        assert (
            boundary_read.execute(
                plan_with_relationship_paths(paths)
            ).requested_traversal
            is None
        )
    assert evidence_set.requested_traversal == read_module.TypedTraversalRequest(
        path_id="company_to_patent",
        source_domain="company",
        target_domain="patent",
        relationship_type="patent_has_applicant",
        direction="inverse",
    )

    answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
    source_item = read_module.EvidenceItem(
        evidence_id="evidence:s8x:setup:company-robotics",
        object_id="company-robotics",
        domain="company",
        lane="exact",
        source_nature="local",
        source_locator="fixture:s8x#company-robotics",
        snippet="Evidence-bound setup authority for Robotics Co.",
        score=1.0,
        observed_at=NOW,
        claim_binding=read_module.EvidenceClaimBinding(
            subject_id="company-robotics",
            predicate="preferred_name",
            value="Robotics Co",
            status="accepted",
        ),
    )
    source_handle = read_module.CanonicalEntityHandle(
        canonical_id="company-robotics",
        domain="company",
        display_name="Robotics Co",
        evidence_ids=(source_item.evidence_id,),
    )
    setup_evidence_set = read_module.EvidenceSet(
        release_id=evidence_set.release_id,
        original_query="Establish the displayed company anchor",
        protected_slots=(),
        items=(source_item,),
        traces=(),
        limitations=(),
        entity_handles=(source_handle,),
    )
    assert setup_evidence_set.requested_traversal is None
    assert tuple(
        handle.canonical_id
        for handle in evidence_set.entity_handles
        if handle.kind == "canonical"
    ) == ("patent-ada",)
    untouched_traversal_json = evidence_set.model_dump_json()

    def answer_selector(value: Any) -> Any:
        displayed_handle_ids = (
            ("company-robotics",)
            if value.turn_id == "turn:s8x:s8r2:setup"
            else ("patent-ada",)
        )
        return answer_module.AnswerSelectionProposal(
            selection_input_sha256=value.content_sha256,
            schema_version="answer-selection-v1",
            decision_id=f"answer-selection:s8x:{value.turn_id}",
            model_id="recorded-s8x-traversal-selector",
            prompt_version="answer-selector-s8x-traversal-v1",
            decision_run_id=f"answer-selection-run:s8x:{value.turn_id}",
            answer_text="Untrusted selector draft.",
            claims=(),
            displayed_handle_ids=displayed_handle_ids,
        )

    answer = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=answer_selector
    )
    session_id = "session:s8x:s8r2-traversal"
    setup_answer = answer.answer(
        answer_module.TurnRequest(
            session_id=session_id,
            turn_id="turn:s8x:s8r2:setup",
            query=setup_evidence_set.original_query,
            release_id=evidence_set.release_id,
            evidence_set=setup_evidence_set,
        )
    )
    assert setup_answer.context_receipt is not None
    assert setup_answer.context_receipt.active_anchor == source_handle
    assert setup_answer.context_receipt.displayed_result_set is not None
    assert setup_answer.context_receipt.displayed_result_set.handle_ids == (
        "company-robotics",
    )

    traversal_answer = answer.answer(
        answer_module.TurnRequest(
            session_id=session_id,
            turn_id="turn:s8x:s8r2:traversal",
            query=evidence_set.original_query,
            release_id=evidence_set.release_id,
            evidence_set=evidence_set,
            session_directive=answer_module.SessionDirective(referent="active_anchor"),
        )
    )
    assert evidence_set.model_dump_json() == untouched_traversal_json
    receipt = traversal_answer.traversal_receipt
    assert receipt is not None
    assert receipt.path_id == "company_to_patent"
    assert receipt.source_handle_ids == ("company-robotics",)
    assert receipt.target_handle_ids == ("patent-ada",)

    physical_item = evidence_set.items[0]
    physical_handle = evidence_set.entity_handles[0]
    physical_traversal = evidence_set.requested_traversal
    assert physical_traversal is not None
    assert physical_item.claim_binding is not None

    def revalidated_item(**updates: Any) -> Any:
        return read_module.EvidenceItem.model_validate(
            physical_item.model_copy(update=updates).model_dump(mode="json")
        )

    def revalidated_handle(*, canonical_id: str, evidence_id: str) -> Any:
        return read_module.CanonicalEntityHandle.model_validate(
            physical_handle.model_copy(
                update={
                    "canonical_id": canonical_id,
                    "evidence_ids": (evidence_id,),
                }
            ).model_dump(mode="json")
        )

    def revalidated_traversal(**updates: Any) -> Any:
        return read_module.TypedTraversalRequest.model_validate(
            physical_traversal.model_copy(update=updates).model_dump(mode="json")
        )

    def rejected_physical_target(
        *,
        token: str,
        source_id: str = "company-robotics",
        poisoned_item: Any = physical_item,
        poisoned_handle: Any = physical_handle,
        poisoned_traversal: Any = physical_traversal,
    ) -> Any:
        # Negative-only synthetic envelopes isolate the Answer authorization guard;
        # they do not claim to replay the release-bound producer authority.
        setup_item = read_module.EvidenceItem(
            evidence_id=f"evidence:s8x:poison-setup:{token}",
            object_id=source_id,
            domain="company",
            lane="exact",
            source_nature="local",
            source_locator=f"fixture:s8x#poison-setup-{token}",
            snippet=f"Evidence-bound negative setup for {source_id}.",
            score=1.0,
            observed_at=NOW,
            claim_binding=read_module.EvidenceClaimBinding(
                subject_id=source_id,
                predicate="preferred_name",
                value=source_id,
                status="accepted",
            ),
        )
        setup_handle = read_module.CanonicalEntityHandle(
            canonical_id=source_id,
            domain="company",
            display_name=source_id,
            evidence_ids=(setup_item.evidence_id,),
        )
        setup_fixture = read_module.EvidenceSet(
            release_id=evidence_set.release_id,
            original_query=f"Negative setup {token}",
            protected_slots=(),
            items=(setup_item,),
            traces=(),
            limitations=(),
            entity_handles=(setup_handle,),
        )
        poison_fixture = read_module.EvidenceSet(
            release_id=evidence_set.release_id,
            original_query=f"Negative traversal {token}",
            protected_slots=(),
            items=(poisoned_item,),
            traces=(),
            limitations=(),
            entity_handles=(poisoned_handle,),
            requested_traversal=poisoned_traversal,
        )
        poison_answer = answer_module.create_ephemeral_knowledge_answer(
            answer_selector=lambda value: answer_module.AnswerSelectionProposal(
                selection_input_sha256=value.content_sha256,
                schema_version="answer-selection-v1",
                decision_id=f"answer-selection:s8x:poison:{token}:{value.turn_id}",
                model_id="recorded-s8x-poison-selector",
                prompt_version="answer-selector-s8x-poison-v1",
                decision_run_id=(
                    f"answer-selection-run:s8x:poison:{token}:{value.turn_id}"
                ),
                answer_text="Untrusted poison selector draft.",
                claims=(),
                displayed_handle_ids=(
                    (source_id,)
                    if value.turn_id.endswith(":setup")
                    else (poisoned_handle.canonical_id,)
                ),
            )
        )
        poison_session_id = f"session:s8x:poison:{token}"
        poison_answer.answer(
            answer_module.TurnRequest(
                session_id=poison_session_id,
                turn_id=f"turn:s8x:poison:{token}:setup",
                query=setup_fixture.original_query,
                release_id=evidence_set.release_id,
                evidence_set=setup_fixture,
            )
        )
        return poison_answer.answer(
            answer_module.TurnRequest(
                session_id=poison_session_id,
                turn_id=f"turn:s8x:poison:{token}:traversal",
                query=poison_fixture.original_query,
                release_id=evidence_set.release_id,
                evidence_set=poison_fixture,
                session_directive=answer_module.SessionDirective(
                    referent="active_anchor"
                ),
            )
        ).traversal_receipt

    other_target_item = revalidated_item(object_id="patent-other")
    other_target_handle = revalidated_handle(
        canonical_id="patent-other",
        evidence_id=other_target_item.evidence_id,
    )
    wrong_object_item = revalidated_item(object_id="patent-other")
    wrong_claim_item = revalidated_item(
        claim_binding=physical_item.claim_binding.model_copy(
            update={"value": "canonical:company:company-other"}
        )
    )
    zero_sha256 = "0" * 64
    wrong_class_trace = read_module.LocalProjectionTrace(
        target_id="target:s8x:wrong-trace-class",
        target_marker_sha256=zero_sha256,
        manifest_sha256=zero_sha256,
        index_result_content_sha256=zero_sha256,
        document_id="document:s8x:wrong-trace-class",
        canonical_object_id="patent-ada",
        release_id=evidence_set.release_id,
        domain="patent",
        projection_id="projection:s8x:wrong-trace-class",
        projection_view="public-patent",
        projection_version="projection-v1",
        schema_version="projection-schema-v1",
        eligibility_policy_version="eligibility-policy-v1",
        eligibility_decision_id="eligibility-decision:s8x:wrong-trace-class",
        eligibility_outcome="admitted",
        source_projection_content_sha256=zero_sha256,
        lookup_content_sha256=zero_sha256,
        source_evidence_ids=("evidence:s8x:wrong-trace-class:source",),
        publication_verification_evidence_ids=(
            "evidence:s8x:wrong-trace-class:publication",
        ),
    )
    wrong_class_item = read_module.EvidenceItem(
        evidence_id=wrong_class_trace.evidence_id,
        object_id="patent-ada",
        domain="patent",
        lane="exact",
        source_nature="local",
        source_locator="fixture:s8x#wrong-trace-class",
        snippet="A valid non-relationship local trace must not authorize traversal.",
        score=1.0,
        observed_at=NOW,
        claim_binding=physical_item.claim_binding,
        local_projection_trace=wrong_class_trace,
    )
    wrong_class_handle = revalidated_handle(
        canonical_id="patent-ada",
        evidence_id=wrong_class_item.evidence_id,
    )
    poisoned_cases = (
        (
            "trace-class",
            rejected_physical_target(
                token="trace-class",
                poisoned_item=wrong_class_item,
                poisoned_handle=wrong_class_handle,
            ),
        ),
        (
            "source-endpoint",
            rejected_physical_target(
                token="source-endpoint",
                source_id="company-other",
            ),
        ),
        (
            "target-endpoint",
            rejected_physical_target(
                token="target-endpoint",
                poisoned_item=other_target_item,
                poisoned_handle=other_target_handle,
            ),
        ),
        (
            "path-tuple",
            rejected_physical_target(
                token="path-tuple",
                poisoned_traversal=revalidated_traversal(direction="forward"),
            ),
        ),
        (
            "item-object",
            rejected_physical_target(
                token="item-object",
                poisoned_item=wrong_object_item,
            ),
        ),
        (
            "claim-binding",
            rejected_physical_target(
                token="claim-binding",
                poisoned_item=wrong_claim_item,
            ),
        ),
    )
    for token, poison_receipt in poisoned_cases:
        assert poison_receipt is not None, token
        assert poison_receipt.target_handle_ids == (), token
    assert physical_reads == []
    assert len(captured_relationship_requests) == 1
    relationship_request = captured_relationship_requests[0]
    assert relationship_request.domains == ("patent",)
    assert relationship_request.relationship_paths == plan.relationship_paths
    assert relationship_request.relationship_reference_queries == ()
    assert relationship_request.relationship_enumeration_policy == (
        plan.enumeration_policy
    )
    assert relationship_request.structured_constraints.displayed_entity_ids == (
        "company-robotics",
    )
    assert len(captured_web_requests) == 1
    assert captured_web_requests[0].relationship_paths == ()
    assert captured_web_requests[0].relationship_enumeration_policy is None

    assert len(captured_relationship_results) == 1
    raw_result = captured_relationship_results[0]
    assert len(raw_result.candidates) == 1
    candidate = raw_result.candidates[0]
    assert candidate.domain == "patent"
    assert candidate.canonical_id == "patent-ada"
    assert candidate.display_name == "Robot control system"
    assert candidate.reference_type is None
    assert candidate.identity_kind == "canonical"
    assert candidate.resolution_state == "resolved"
    assert candidate.relationship_state == "accepted"
    assert candidate.origin_public_evidence_ids == ("assertion:patent-ada:applicants",)
    assert candidate.quality_flags == ()
    assert len(candidate.evidence) == 1
    item = candidate.evidence[0]
    trace = item.local_projection_trace
    assert isinstance(trace, read_module.LocalCanonicalRelationshipTrace)
    assert trace.displayed_company_id == "company-robotics"
    assert trace.company_stable_reference == "canonical:company:company-robotics"
    assert trace.patent_id == "patent-ada"
    assert trace.patent_stable_reference == "canonical:patent:patent-ada"
    assert trace.canonical_relationship_id == ("relationship:patent-applicant:robotics")
    assert trace.relationship_type_id == "patent_has_applicant"
    assert trace.relationship_role_bindings == (
        ("applicant", "canonical:company:company-robotics"),
    )
    assert trace.company_traversal_directions == ("company_to_patent",)
    assert trace.patent_traversal_directions == ("patent_to_company",)
    assert trace.relationship_decision_id == (
        "relationship-decision:patent-applicant:robotics"
    )
    assert trace.query_as_of == trace.relationship_snapshot_as_of == NOW
    assert trace.lane_request_content_sha256 == relationship_request.content_sha256
    relationship_request_authority = authority[2]
    relationship_result_authority = authority[3]
    projection_candidate = relationship_request_authority.candidates[0]
    typed_assertion = relationship_request_authority.typed_relationship_assertions[0]
    decision_input = relationship_request_authority.decision_inputs[0]
    retained_reference = relationship_request_authority.retained_assertions[0]
    candidate_outcome = relationship_result_authority.candidate_outcomes[0]
    typed_decision = relationship_result_authority.typed_relationship_decisions[0]
    current_relationship = relationship_result_authority.current_relationships[0]
    public_projection_request = relationship_request_authority.internal_reference_projection_request.public_domain_projection_request
    public_assertion = next(
        assertion
        for assertion in public_projection_request.source_assertions
        if assertion.assertion_id == retained_reference.assertion_id
    )
    company_projection = next(
        projection
        for projection in authority[1].public_domain_projections
        if projection.entity_type == "company"
        if projection.canonical_identity_id == "company-robotics"
    )
    patent_projection = next(
        projection
        for projection in authority[1].public_domain_projections
        if projection.entity_type == "patent"
        if projection.canonical_identity_id == "patent-ada"
    )
    applicant = patent_projection.applicants[0]
    path_results = {
        result.subject_identity_id: result
        for result in index_request.public_path_eligibility_results
    }
    company_path_result = path_results["company-robotics"]
    patent_path_result = path_results["patent-ada"]
    assert trace.relationship_request_sha256 == _canonical_hash(
        relationship_request_authority.model_dump(mode="json")
    )
    assert (
        trace.relationship_result_sha256 == relationship_result_authority.content_sha256
    )
    assert trace.relationship_projection_run_id == (
        relationship_result_authority.projection_run_id
    )
    assert trace.relationship_projection_schema_version == (
        relationship_result_authority.projection_schema_version
    )
    assert trace.relationship_registry_content_sha256 == (
        relationship_result_authority.relationship_registry_content_sha256
    )
    assert trace.current_relationship_content_sha256 == _canonical_hash(
        current_relationship.model_dump(mode="json")
    )
    assert trace.relationship_decision_input_id == decision_input.decision_input_id
    assert trace.projection_candidate_id == projection_candidate.candidate_id
    assert trace.projection_candidate_content_sha256 == _canonical_hash(
        projection_candidate.model_dump(mode="json")
    )
    assert trace.projection_candidate_observed_at == projection_candidate.observed_at
    assert (
        trace.projection_candidate_source_event_time
        == projection_candidate.source_event_time
    )
    assert (
        trace.projection_candidate_assertion_input_id
        == projection_candidate.assertion_input_id
    )
    assert (
        trace.projection_candidate_decision_input_id
        == projection_candidate.decision_input_id
    )
    assert trace.typed_assertion_id == typed_assertion.assertion_id
    assert trace.typed_assertion_content_sha256 == _canonical_hash(
        typed_assertion.model_dump(mode="json")
    )
    assert trace.typed_assertion_observed_at == typed_assertion.observed_at
    assert trace.typed_assertion_source_event_time == typed_assertion.source_event_time
    assert trace.typed_assertion_source_record_ref == typed_assertion.source_record_ref
    assert trace.candidate_outcome_candidate_id == candidate_outcome.candidate_id
    assert trace.candidate_outcome_content_sha256 == _canonical_hash(
        candidate_outcome.model_dump(mode="json")
    )
    assert (
        trace.candidate_outcome_retained_assertion_id
        == candidate_outcome.retained_assertion_id
    )
    assert trace.candidate_outcome_decision_id == candidate_outcome.decision_id
    assert (
        trace.candidate_outcome_projected_relationship_id
        == candidate_outcome.projected_relationship_id
    )
    assert trace.typed_decision_id == typed_decision.decision_id
    assert trace.typed_decision_content_sha256 == _canonical_hash(
        typed_decision.model_dump(mode="json")
    )
    assert trace.typed_decision_selected_assertion_ids == (
        typed_decision.selected_assertion_ids
    )
    assert trace.typed_decision_selected_evidence_refs == (
        typed_decision.selected_evidence_refs
    )
    assert trace.current_selected_evidence_refs == (
        current_relationship.selected_evidence_refs
    )
    assert trace.retained_reference_id == retained_reference.reference_id
    assert trace.retained_reference_content_sha256 == _canonical_hash(
        retained_reference.model_dump(mode="json")
    )
    assert trace.retained_assertion_id == retained_reference.assertion_id
    assert trace.retained_source_record_id == retained_reference.source_record_ref
    assert trace.public_assertion_id == public_assertion.assertion_id
    assert trace.public_assertion_content_sha256 == _canonical_hash(
        public_assertion.model_dump(mode="json")
    )
    assert trace.public_assertion_observed_at == public_assertion.observed_at
    assert (
        trace.public_assertion_source_event_time == public_assertion.source_event_time
    )
    assert trace.source_record_id == public_assertion.source_record_id
    assert trace.company_projection_content_sha256 == company_projection.content_sha256
    assert trace.company_display_name == company_projection.name
    assert trace.patent_projection_content_sha256 == patent_projection.content_sha256
    assert trace.patent_display_name == patent_projection.title
    assert trace.applicant_subobject_id == applicant.subobject_id
    assert trace.applicant_subobject_projection_content_sha256 == (
        applicant.projection_content_sha256
    )
    assert trace.applicant_parent_patent_id == applicant.parent_canonical_identity_id
    assert trace.applicant_canonical_company_id == applicant.canonical_company_id
    assert trace.applicant_supporting_assertion_ids == (
        applicant.supporting_assertion_ids
    )
    assert trace.applicant_source_record_id == public_assertion.source_record_id
    assert (
        trace.company_path_result_content_sha256 == company_path_result.content_sha256
    )
    assert trace.company_eligibility_outcome == "admitted"
    assert trace.company_eligibility_limitations == ()
    assert trace.patent_path_result_content_sha256 == patent_path_result.content_sha256
    assert trace.patent_eligibility_outcome == "admitted"
    assert trace.patent_eligibility_limitations == ()
    assert item.object_id == "patent-ada"
    assert item.domain == "patent"
    assert item.lane == "relationship"
    assert item.source_nature == "local"
    assert item.source_authority == "canonical_release"
    assert item.claim_binding == read_module.EvidenceClaimBinding(
        subject_id="canonical:patent:patent-ada",
        predicate="patent_has_applicant",
        value="canonical:company:company-robotics",
        status="accepted",
    )

    assert len(evidence_set.fused_candidates) == 1
    fused = evidence_set.fused_candidates[0]
    assert fused.canonical_id == "patent-ada"
    assert fused.domain == "patent"
    assert fused.display_name == "Robot control system"
    assert fused.quality_flags == ()
    assert evidence_set.entity_handles == (
        read_module.CanonicalEntityHandle(
            canonical_id="patent-ada",
            domain="patent",
            display_name="Robot control system",
            evidence_ids=fused.evidence_ids,
        ),
    )
    coverage = evidence_set.enumeration_coverage
    assert coverage is not None
    assert coverage.mode == "representative"
    assert coverage.scope == S8R2_SCOPE
    assert coverage.as_of == NOW
    assert coverage.unknown_scope is True
    assert coverage.exhaustive is False
    assert coverage.continuation_state == "open_world"
    assert coverage.continuation_required is True

    direct_adapter = real_relationship_factory(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=catalog,
    )
    direct_request = isolated_read_module._lane_request(
        plan,
        "relationship",
        plan.web_policy,
    )
    assert len(direct_adapter(direct_request).candidates) == 1

    def direct_request_with(
        *,
        displayed_ids: tuple[str, ...] | None = None,
        protected_sets: tuple[tuple[str, ...], ...] | None = None,
        **updates: Any,
    ) -> Any:
        payload = direct_request.model_dump(mode="json", exclude={"content_sha256"})
        if displayed_ids is not None:
            payload["structured_constraints"]["displayed_entity_ids"] = list(
                displayed_ids
            )
        else:
            displayed_ids = direct_request.structured_constraints.displayed_entity_ids
        if protected_sets is not None:
            payload["protected_slots"] = [
                read_module.ProtectedSlot(
                    kind="displayed_entity_set",
                    value="displayed_entity_set",
                    entity_ids=values,
                ).model_dump(mode="json")
                for values in protected_sets
            ]
        payload.update(updates)
        return read_module.LaneRequest.model_validate(payload)

    assert direct_adapter(direct_request_with(max_candidates=0)).candidates == ()
    assert (
        direct_adapter(
            direct_request_with(displayed_ids=(), protected_sets=())
        ).candidates
        == ()
    )
    for source_id in ("company-unknown", "patent-ada", internal_person_id):
        assert (
            direct_adapter(
                direct_request_with(
                    displayed_ids=(source_id,),
                    protected_sets=((source_id,),),
                )
            ).candidates
            == ()
        )
    invalid_direct_requests = (
        direct_request_with(
            displayed_ids=("company-robotics", "company-other"),
            protected_sets=(("company-robotics", "company-other"),),
        ),
        direct_request_with(protected_sets=()),
        direct_request_with(protected_sets=(("company-other",),)),
        direct_request_with(
            protected_sets=(("company-robotics",), ("company-robotics",))
        ),
        direct_request_with(release_id="cross-release-s8r2"),
        direct_request_with(relationship_enumeration_policy=None),
    )
    for invalid_request in invalid_direct_requests:
        with pytest.raises(
            (ValueError, isolated_read_module.IsolatedKnowledgeReadIntegrityError)
        ):
            direct_adapter(invalid_request)

    exhaustive_policy = plan.enumeration_policy.model_copy(
        update={"mode": "exhaustive_bounded", "exhaustive": True}
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="enumeration",
    ):
        direct_adapter(
            direct_request_with(
                relationship_enumeration_policy=exhaustive_policy.model_dump(
                    mode="json"
                )
            )
        )

    def execute_scenario(
        value: dict[str, Any],
        *,
        plan_override: Any | None = None,
        web_calls: list[Any] | None = None,
    ) -> Any:
        calls = web_calls if web_calls is not None else []
        return release_factory(
            release_bundle=value["bundle"],
            published_release=value["published"],
            index_projection_request=value["index_request"],
            release_institution_catalog=value["catalog"],
            universal_web_policy=value["plan"].web_policy,
            web_search=lambda lane_request: (
                calls.append(lane_request) or read_module.RetrievalLaneResult()
            ),
            web_snapshot_policy=read_module.WebSnapshotPolicy(
                policy_id=f"web-snapshot-policy:{value['bundle'].release_id}",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
            clock=lambda: NOW,
        ).execute(plan_override or value["plan"])

    authoritative_zero = _s8r2_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r2-authoritative-zero",
        authoritative_zero=True,
    )
    zero_web_calls: list[Any] = []
    zero_result = execute_scenario(
        authoritative_zero,
        web_calls=zero_web_calls,
    )
    assert zero_result.fused_candidates == ()
    assert len(zero_web_calls) == 1

    valid_company_no_edge = _s8r2_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r2-valid-company-no-applicant-edge",
        nonmatching_relationship_authority=True,
    )
    assert valid_company_no_edge["authority"][2].candidates
    assert valid_company_no_edge["authority"][3].current_relationships
    no_edge_web_calls: list[Any] = []
    no_edge_result = execute_scenario(
        valid_company_no_edge,
        web_calls=no_edge_web_calls,
    )
    assert no_edge_result.fused_candidates == ()
    assert no_edge_result.entity_handles == ()
    assert len(no_edge_web_calls) == 1

    for excluded_id in ("company-robotics", "patent-ada"):
        excluded = _s8r2_scenario(
            tmp_path=tmp_path,
            release_id=f"candidate-s8r2-excluded-{excluded_id}",
            excluded_endpoint_ids=(excluded_id,),
        )
        excluded_result = execute_scenario(excluded)
        assert excluded_result.fused_candidates == ()

    limited = _s8r2_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r2-both-limited",
        limited_endpoint_ids=("company-robotics", "patent-ada"),
    )
    limited_result = execute_scenario(limited)
    assert len(limited_result.fused_candidates) == 1
    assert limited_result.fused_candidates[0].quality_flags == (
        "s8r2_relationship_limited_company-robotics",
        "s8r2_relationship_limited_patent-ada",
    )

    max_zero_payload = plan.model_dump(mode="json", exclude={"content_sha256"})
    max_zero_payload["max_candidates"] = 0
    max_zero_plan = read_module.RetrievalPlan.model_validate(max_zero_payload)
    assert (
        execute_scenario(positive, plan_override=max_zero_plan).fused_candidates == ()
    )

    target_rejected_payload = plan.model_dump(
        mode="json",
        exclude={"content_sha256"},
    )
    target_rejected_payload["protected_slots"].append(
        read_module.ProtectedSlot(
            kind="exact_identifier",
            value="CN000000000A",
        ).model_dump(mode="json")
    )
    target_rejected_plan = read_module.RetrievalPlan.model_validate(
        target_rejected_payload
    )
    target_rejected_result = execute_scenario(
        positive,
        plan_override=target_rejected_plan,
    )
    assert target_rejected_result.items == ()
    assert target_rejected_result.entity_handles == ()
    assert any(
        receipt.outcome == "rejected"
        and any(
            failure.slot_kind == "exact_identifier" for failure in receipt.failed_slots
        )
        for receipt in target_rejected_result.constraint_receipts
    )
    assert any(
        trace.disposition == "hard_constraint_rejected"
        for trace in target_rejected_result.candidate_traces
        if trace.lane == "relationship"
    )

    valid_web_payload = b"S8R2 current Web evidence for the returned Patent"
    valid_web_digest = hashlib.sha256(valid_web_payload).hexdigest()
    valid_web_snapshot = read_module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:s8r2-patent:sha256:{valid_web_digest}",
        content_sha256=valid_web_digest,
        retrieved_at=NOW,
        byte_length=len(valid_web_payload),
    )
    valid_web_calls: list[Any] = []

    def valid_patent_web_search(value: Any) -> Any:
        valid_web_calls.append(value)
        web_item = read_module.EvidenceItem(
            evidence_id="evidence:web:s8r2:patent-ada",
            object_id="patent-ada",
            domain="patent",
            lane="web",
            source_nature="current_web",
            source_locator="https://current.example/s8r2-patent-ada",
            snippet="Current Web evidence for Robot control system",
            score=0.5,
            web_snapshot=valid_web_snapshot,
        )
        return read_module.RetrievalLaneResult(
            candidates=(
                read_module.RecallCandidate(
                    raw_candidate_id="raw:web:s8r2:patent-ada",
                    display_name="Robot control system",
                    domain="patent",
                    identity_kind="canonical",
                    canonical_id="patent-ada",
                    resolution_state="resolved",
                    query_view=value.query_view,
                    lane="web",
                    attempt=1,
                    release_id=value.release_id,
                    adapter_version="s8r2-web-fixture-v1",
                    provider_version="s8r2-web-provider-v1",
                    raw_score=0.5,
                    evidence=(web_item,),
                ),
            ),
            web_snapshot_payloads=(
                read_module.WebSnapshotPayload(
                    snapshot_id=valid_web_snapshot.snapshot_id,
                    content=valid_web_payload,
                ),
            ),
        )

    valid_web_result = release_factory(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=catalog,
        universal_web_policy=plan.web_policy,
        web_search=valid_patent_web_search,
        web_snapshot_policy=read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8r2-valid-patent",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        clock=lambda: NOW,
    ).execute(plan)
    assert len(valid_web_calls) == 1
    assert len(valid_web_result.fused_candidates) == 1
    assert {item.lane for item in valid_web_result.fused_candidates[0].evidence} == {
        "relationship",
        "web",
    }
    assert valid_web_result.entity_handles[0].domain == "patent"
    assert valid_web_result.entity_handles[0].canonical_id == "patent-ada"

    def plan_with_source(
        source_ids: tuple[str, ...],
        *,
        protected_sets: tuple[tuple[str, ...], ...] | None = None,
    ) -> Any:
        payload = plan.model_dump(mode="json", exclude={"content_sha256"})
        payload["structured_constraints"]["displayed_entity_ids"] = list(source_ids)
        effective_sets = protected_sets if protected_sets is not None else (source_ids,)
        payload["protected_slots"] = [
            read_module.ProtectedSlot(
                kind="displayed_entity_set",
                value="displayed_entity_set",
                entity_ids=values,
            ).model_dump(mode="json")
            for values in effective_sets
        ]
        return read_module.RetrievalPlan.model_validate(payload)

    unknown_web_calls: list[Any] = []
    unknown_result = execute_scenario(
        positive,
        plan_override=plan_with_source(("company-unknown",)),
        web_calls=unknown_web_calls,
    )
    assert unknown_result.fused_candidates == ()
    assert len(unknown_web_calls) == 1

    invalid_plan_cases = (
        plan_with_source(()),
        plan_with_source(("",)),
        plan_with_source(("company-robotics", "company-other")),
        plan_with_source(("patent-ada",)),
        plan_with_source((internal_person_id,)),
        plan_with_source(("company-robotics",), protected_sets=()),
        plan_with_source(
            ("company-robotics",),
            protected_sets=(("company-robotics",), ("company-robotics",)),
        ),
        plan_with_source(
            ("company-robotics",),
            protected_sets=(("company-other",),),
        ),
    )
    for invalid_plan in invalid_plan_cases:
        invalid_web_calls: list[Any] = []
        with pytest.raises(isolated_read_module.IsolatedKnowledgeReadIntegrityError):
            execute_scenario(
                positive,
                plan_override=invalid_plan,
                web_calls=invalid_web_calls,
            )
        assert invalid_web_calls == []

    def plan_with_enumeration(**updates: Any) -> Any:
        payload = plan.model_dump(mode="json", exclude={"content_sha256"})
        enumeration_payload = dict(payload["enumeration_policy"])
        enumeration_payload.update(updates)
        payload["enumeration_policy"] = enumeration_payload
        return read_module.RetrievalPlan.model_validate(payload)

    wrong_path = read_module.RelationshipPathProposal(
        relationship_type_id="company_has_patent",
        direction="patent_to_company",
        source_type="patent",
        target_type="company",
    )
    injected_reference_query = read_module.InternalReferenceQuery(
        reference_type="technology_route",
        release_id=release_id,
    )
    invalid_request_plan_payloads: list[dict[str, Any]] = []
    for updates in (
        {
            "finite_universe_id": "finite-universe:s8r2-invalid",
            "finite_universe_source": "source:s8r2-invalid",
            "finite_universe_ids": ["patent-ada"],
        },
        {
            "mode": "required_members",
            "required_member_ids": ["patent-ada"],
        },
        {"eligible_member_ids": ["patent-ada"]},
        {"continuation_state": "complete"},
    ):
        invalid_request_plan_payloads.append(
            plan_with_enumeration(**updates).model_dump(
                mode="json",
                exclude={"content_sha256"},
            )
        )
    for plan_updates in (
        {"relationship_paths": []},
        {
            "relationship_paths": [
                plan.relationship_paths[0].model_dump(mode="json"),
                wrong_path.model_dump(mode="json"),
            ]
        },
        {"relationship_paths": [wrong_path.model_dump(mode="json")]},
        {"domains": ["company"]},
        {"enumeration_policy": None},
        {
            "internal_reference_queries": [
                injected_reference_query.model_dump(mode="json")
            ]
        },
    ):
        payload = plan.model_dump(mode="json", exclude={"content_sha256"})
        payload.update(plan_updates)
        invalid_request_plan_payloads.append(payload)
    for invalid_payload in invalid_request_plan_payloads:
        invalid_request_plan = read_module.RetrievalPlan.model_validate(invalid_payload)
        invalid_request_web_calls: list[Any] = []
        with pytest.raises(isolated_read_module.IsolatedKnowledgeReadIntegrityError):
            execute_scenario(
                positive,
                plan_override=invalid_request_plan,
                web_calls=invalid_request_web_calls,
            )
        assert invalid_request_web_calls == []

    later = NOW + timedelta(days=1)
    later_scenario = _s8r2_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r2-later-query",
        as_of=later,
    )
    later_result = execute_scenario(later_scenario)
    assert len(later_result.fused_candidates) == 1
    assert later_result.fused_candidates[0].quality_flags == (S8R1_SNAPSHOT_FLAG,)
    later_trace = later_result.fused_candidates[0].evidence[0].local_projection_trace
    assert isinstance(later_trace, read_module.LocalCanonicalRelationshipTrace)
    assert later_trace.query_as_of == later
    assert later_trace.relationship_snapshot_as_of == NOW

    later_limited = _s8r2_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r2-later-both-limited",
        as_of=later,
        limited_endpoint_ids=("company-robotics", "patent-ada"),
    )
    later_limited_result = execute_scenario(later_limited)
    assert len(later_limited_result.fused_candidates) == 1
    assert later_limited_result.fused_candidates[0].quality_flags == tuple(
        sorted(
            (
                S8R1_SNAPSHOT_FLAG,
                "s8r2_relationship_limited_company-robotics",
                "s8r2_relationship_limited_patent-ada",
            )
        )
    )

    earlier_scenario = _s8r2_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r2-earlier-query",
        as_of=NOW - timedelta(days=1),
    )
    earlier_web_calls: list[Any] = []
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="earlier|as_of|snapshot",
    ):
        execute_scenario(earlier_scenario, web_calls=earlier_web_calls)
    assert earlier_web_calls == []

    drifted_plan_payload = plan.model_dump(mode="json", exclude={"content_sha256"})
    drifted_plan_payload["as_of"] = later.isoformat()
    drifted_plan = read_module.RetrievalPlan.model_validate(drifted_plan_payload)
    drifted_web_calls: list[Any] = []
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="source/policy|as_of|plan",
    ):
        execute_scenario(
            positive,
            plan_override=drifted_plan,
            web_calls=drifted_web_calls,
        )
    assert drifted_web_calls == []

    hostile_web_payload = b"S8R2 hostile displayed Company Web witness"
    hostile_web_digest = hashlib.sha256(hostile_web_payload).hexdigest()
    hostile_web_snapshot = read_module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:s8r2-hostile:sha256:{hostile_web_digest}",
        content_sha256=hostile_web_digest,
        retrieved_at=NOW,
        byte_length=len(hostile_web_payload),
    )
    hostile_web_item = read_module.EvidenceItem(
        evidence_id="evidence:web:s8r2:displayed-company-witness",
        object_id="company-robotics",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_locator="https://current.example/s8r2-company-witness",
        snippet="Displayed Company Web witness",
        score=0.5,
        web_snapshot=hostile_web_snapshot,
    )
    hostile_web_result = read_module.RetrievalLaneResult(
        items=(hostile_web_item,),
        web_snapshot_payloads=(
            read_module.WebSnapshotPayload(
                snapshot_id=hostile_web_snapshot.snapshot_id,
                content=hostile_web_payload,
            ),
        ),
    )
    hostile_web_calls: list[Any] = []
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="S8R2 Web source witness must not satisfy displayed Company authority",
    ):
        release_factory(
            release_bundle=bundle,
            published_release=published,
            index_projection_request=index_request,
            release_institution_catalog=catalog,
            universal_web_policy=plan.web_policy,
            web_search=lambda value: (
                hostile_web_calls.append(value) or hostile_web_result
            ),
            web_snapshot_policy=read_module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8r2-hostile-company",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
            clock=lambda: NOW,
        ).execute(plan)
    assert len(hostile_web_calls) == 1
    assert physical_reads == []

    def forged_source_witness_factory(**kwargs: Any) -> Any:
        adapter = real_relationship_factory(**kwargs)

        def forged(value: Any) -> Any:
            result = adapter(value)
            candidate = result.candidates[0]
            item = candidate.evidence[0]
            trace = item.local_projection_trace
            assert isinstance(trace, read_module.LocalCanonicalRelationshipTrace)
            trace_payload = trace.model_dump(mode="python")
            trace_payload.update(
                {
                    "displayed_entity_ids": ("company-forged",),
                    "displayed_company_id": "company-forged",
                    "company_id": "company-forged",
                    "company_stable_reference": "canonical:company:company-forged",
                    "relationship_target_endpoint": (
                        "canonical:company:company-forged"
                    ),
                    "relationship_role_bindings": (
                        ("applicant", "canonical:company:company-forged"),
                    ),
                    "applicant_canonical_company_id": "company-forged",
                    "claim_value": "canonical:company:company-forged",
                    "raw_candidate_id": "",
                    "evidence_id": "",
                    "content_sha256": "0" * 64,
                }
            )
            forged_trace = read_module.LocalCanonicalRelationshipTrace.model_validate(
                trace_payload
            )
            forged_item = item.model_copy(
                update={
                    "evidence_id": forged_trace.evidence_id,
                    "source_locator": isolated_read_module._local_projection_locator(
                        forged_trace
                    ),
                    "claim_binding": item.claim_binding.model_copy(
                        update={"value": "canonical:company:company-forged"}
                    ),
                    "local_projection_trace": forged_trace,
                }
            )
            forged_candidate = candidate.model_copy(
                update={
                    "raw_candidate_id": forged_trace.raw_candidate_id,
                    "evidence": (forged_item,),
                }
            )
            return read_module.RetrievalLaneResult(candidates=(forged_candidate,))

        return forged

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        forged_source_witness_factory,
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="relationship top-level evidence differs from replay authority",
    ):
        execute_scenario(positive)

    def extra_relationship_factory(**kwargs: Any) -> Any:
        adapter = real_relationship_factory(**kwargs)

        def with_extra(value: Any) -> Any:
            result = adapter(value)
            candidate = result.candidates[0]
            item = candidate.evidence[0]
            trace = item.local_projection_trace
            assert isinstance(trace, read_module.LocalCanonicalRelationshipTrace)
            trace_payload = trace.model_dump(mode="python")
            trace_payload.update(
                {
                    "canonical_relationship_id": "relationship:fabricated:s8r2",
                    "candidate_outcome_projected_relationship_id": (
                        "relationship:fabricated:s8r2"
                    ),
                    "raw_candidate_id": "",
                    "evidence_id": "",
                    "content_sha256": "0" * 64,
                }
            )
            extra_trace = read_module.LocalCanonicalRelationshipTrace.model_validate(
                trace_payload
            )
            extra_item = item.model_copy(
                update={
                    "evidence_id": extra_trace.evidence_id,
                    "source_locator": isolated_read_module._local_projection_locator(
                        extra_trace
                    ),
                    "local_projection_trace": extra_trace,
                }
            )
            extra_candidate = candidate.model_copy(
                update={
                    "raw_candidate_id": extra_trace.raw_candidate_id,
                    "evidence": (extra_item,),
                }
            )
            return read_module.RetrievalLaneResult(
                candidates=(candidate, extra_candidate)
            )

        return with_extra

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        extra_relationship_factory,
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="evidence differs|replay authority|candidate trace set",
    ):
        execute_scenario(positive)

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        real_relationship_factory,
    )
    real_ephemeral_read_factory = isolated_read_module.create_ephemeral_knowledge_read

    def hostile_delegate_factory(
        mutation: Callable[[Any], dict[str, Any]],
    ) -> Callable[..., Any]:
        def factory(**kwargs: Any) -> Any:
            delegate = real_ephemeral_read_factory(**kwargs)

            class _HostileDelegate:
                def execute(self, value: Any) -> Any:
                    result = delegate.execute(value)
                    return read_module.EvidenceSet.model_validate(mutation(result))

            return _HostileDelegate()

        return factory

    def duplicate_candidate_trace(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        relationship_trace = next(
            trace
            for trace in payload["candidate_traces"]
            if trace["lane"] == "relationship"
        )
        payload["candidate_traces"].append(relationship_trace)
        return payload

    def reuse_candidate_trace_identity_from_web(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        relationship_trace = next(
            trace
            for trace in payload["candidate_traces"]
            if trace["lane"] == "relationship"
        )
        payload["candidate_traces"].append({**relationship_trace, "lane": "web"})
        return payload

    def drift_evidence_envelope(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        payload.update(
            {
                "release_id": "release:s8r2-hostile-envelope",
                "original_query": "hostile S8R2 query envelope",
                "protected_slots": [],
            }
        )
        return payload

    def remove_top_level_relationship_item(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        payload["items"] = [
            item for item in payload["items"] if item["lane"] != "relationship"
        ]
        return payload

    def duplicate_top_level_relationship_item(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        relationship_item = next(
            item for item in payload["items"] if item["lane"] == "relationship"
        )
        payload["items"].append(relationship_item)
        return payload

    def reuse_relationship_evidence_identity_from_web(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        relationship_item = next(
            item for item in payload["items"] if item["lane"] == "relationship"
        )
        payload["items"].append(
            {
                **relationship_item,
                "lane": "web",
                "snippet": "Hostile Web reuse of relationship evidence identity",
            }
        )
        return payload

    def add_unrelated_auxiliary_trace(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        payload["auxiliary_traces"].append(
            read_module.AuxiliaryTrace(
                raw_candidate_id="raw:s8r2:unrelated-auxiliary",
                reference_type="person",
                origin_public_evidence_ids=("assertion:s8r2:unrelated-auxiliary",),
                relationship_state="accepted",
            ).model_dump(mode="json")
        )
        return payload

    def forge_exhaustive_coverage(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        coverage = payload["enumeration_coverage"]
        assert coverage is not None
        payload["enumeration_coverage"] = {
            **coverage,
            "mode": "exhaustive_bounded",
            "unknown_scope": False,
            "exhaustive": True,
            "accounting_complete": True,
            "continuation_state": "complete",
            "continuation_required": False,
        }
        return payload

    hostile_delegate_cases = (
        (
            drift_evidence_envelope,
            "relationship evidence envelope differs from the plan",
        ),
        (
            duplicate_candidate_trace,
            "relationship candidate trace identity is duplicated",
        ),
        (
            reuse_candidate_trace_identity_from_web,
            "relationship candidate trace identity is duplicated",
        ),
        (
            remove_top_level_relationship_item,
            "relationship top-level evidence differs from replay authority",
        ),
        (
            duplicate_top_level_relationship_item,
            "relationship top-level evidence identity is duplicated",
        ),
        (
            reuse_relationship_evidence_identity_from_web,
            "relationship top-level evidence identity is duplicated",
        ),
        (
            add_unrelated_auxiliary_trace,
            "canonical relationship output contains an auxiliary trace",
        ),
        (
            forge_exhaustive_coverage,
            "enumeration coverage differs from the release-bound plan",
        ),
    )
    for mutation, expected_error in hostile_delegate_cases:
        monkeypatch.setattr(
            isolated_read_module,
            "create_ephemeral_knowledge_read",
            hostile_delegate_factory(mutation),
        )
        hostile_delegate_web_calls: list[Any] = []
        with pytest.raises(
            isolated_read_module.IsolatedKnowledgeReadIntegrityError,
            match=expected_error,
        ):
            execute_scenario(positive, web_calls=hostile_delegate_web_calls)
        assert len(hostile_delegate_web_calls) == 1

    monkeypatch.setattr(
        isolated_read_module,
        "create_ephemeral_knowledge_read",
        real_ephemeral_read_factory,
    )


def test_s8r4_executes_release_scoped_paper_to_professor_attribution_traversal(
    request: pytest.FixtureRequest,
) -> None:
    read_module, relationship_factory, release_factory = (
        _s8r4_public_relationship_contract()
    )
    tmp_path: Path = request.getfixturevalue("tmp_path")
    monkeypatch: pytest.MonkeyPatch = request.getfixturevalue("monkeypatch")
    isolated_read_module = _isolated_knowledge_read_module()

    positive = _s8r4_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r4-paper-professor",
    )
    authority = positive["authority"]
    plan = positive["plan"]
    assert plan.domains == ("professor",)
    assert plan.lanes == ("relationship", "web")
    assert plan.relationship_paths == (
        read_module.RelationshipPathProposal(
            relationship_type_id="professor_authored_paper",
            direction="paper_to_professor",
            source_type="paper",
            target_type="professor",
        ),
    )
    assert plan.structured_constraints.displayed_entity_ids == ("paper-ada",)
    assert tuple(
        slot.entity_ids
        for slot in plan.protected_slots
        if slot.kind == "displayed_entity_set"
    ) == (("paper-ada",),)
    assert plan.enumeration_policy is not None
    assert plan.enumeration_policy.mode == "representative"
    assert plan.enumeration_policy.scope == S8R4_SCOPE
    assert plan.enumeration_policy.as_of == NOW
    assert plan.enumeration_policy.finite_universe_id is None
    assert plan.enumeration_policy.eligible_member_ids == ()
    assert plan.enumeration_policy.required_member_ids == ()
    assert plan.enumeration_policy.exhaustive is False
    assert plan.enumeration_policy.continuation_state == "available"

    captured_relationship_requests: list[Any] = []
    captured_web_requests: list[Any] = []
    real_relationship_factory = relationship_factory

    def capturing_relationship_factory(**kwargs: Any) -> Any:
        adapter = real_relationship_factory(**kwargs)

        def captured_adapter(value: Any) -> Any:
            captured_relationship_requests.append(value)
            return adapter(value)

        return captured_adapter

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        capturing_relationship_factory,
    )
    physical_reads: list[Any] = []

    def forbidden_physical_read(value: Any) -> Any:
        physical_reads.append(value)
        raise AssertionError("S8R4 relationship traversal must remain in memory")

    monkeypatch.setattr(
        isolated_read_module,
        "_read_bound_documents",
        forbidden_physical_read,
    )
    service_kwargs = {
        "release_bundle": positive["bundle"],
        "published_release": positive["published"],
        "index_projection_request": positive["index_request"],
        "release_institution_catalog": positive["catalog"],
        "universal_web_policy": plan.web_policy,
        "web_search": lambda value: (
            captured_web_requests.append(value) or read_module.RetrievalLaneResult()
        ),
        "web_snapshot_policy": read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8r4",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        "clock": lambda: NOW,
    }
    evidence_set = release_factory(**service_kwargs).execute(plan)

    assert evidence_set.requested_traversal == read_module.TypedTraversalRequest(
        path_id="paper_to_professor",
        source_domain="paper",
        target_domain="professor",
        relationship_type="professor_attributed_to_paper",
        direction="inverse",
    )
    assert physical_reads == []
    assert len(captured_relationship_requests) == 1
    relationship_request = captured_relationship_requests[0]
    assert relationship_request.domains == ("professor",)
    assert relationship_request.relationship_paths == plan.relationship_paths
    assert relationship_request.relationship_reference_queries == ()
    assert relationship_request.relationship_enumeration_policy == (
        plan.enumeration_policy
    )
    assert relationship_request.structured_constraints.displayed_entity_ids == (
        "paper-ada",
    )
    assert len(captured_web_requests) == 1
    assert captured_web_requests[0].relationship_paths == ()
    assert captured_web_requests[0].relationship_enumeration_policy is None

    assert len(evidence_set.items) == 1
    item = evidence_set.items[0]
    trace = item.local_projection_trace
    assert isinstance(trace, read_module.LocalPaperProfessorRelationshipTrace)
    assert trace.displayed_entity_ids == ("paper-ada",)
    assert trace.displayed_paper_id == "paper-ada"
    assert trace.professor_id == "professor-ada"
    assert trace.paper_id == "paper-ada"
    assert trace.candidate_domain == "professor"
    assert trace.candidate_canonical_id == "professor-ada"
    assert trace.candidate_display_name == "陈艾达"
    assert trace.relationship_type_id == "professor_attributed_to_paper"
    assert trace.relationship_source_endpoint == ("canonical:professor:professor-ada")
    assert trace.relationship_target_endpoint == "canonical:paper:paper-ada"
    assert trace.relationship_role_bindings == ()
    assert trace.claim_subject_id == "canonical:professor:professor-ada"
    assert trace.claim_predicate == "professor_attributed_to_paper"
    assert trace.claim_value == "canonical:paper:paper-ada"
    assert trace.professor_traversal_directions == ("professor_to_paper",)
    assert trace.paper_traversal_directions == ("paper_to_professor",)
    assert trace.paper_domain_identity_status == "confirmed"
    assert trace.query_as_of == trace.relationship_snapshot_as_of == NOW
    assert trace.lane_request_content_sha256 == relationship_request.content_sha256
    assert trace.retained_artifact_refs == ()
    assert trace.selected_evidence_refs == (trace.retained_reference_id,)
    assert item.object_id == "professor-ada"
    assert item.domain == "professor"
    assert item.claim_binding == read_module.EvidenceClaimBinding(
        subject_id="canonical:professor:professor-ada",
        predicate="professor_attributed_to_paper",
        value="canonical:paper:paper-ada",
        status="accepted",
    )
    assert len(evidence_set.fused_candidates) == 1
    fused = evidence_set.fused_candidates[0]
    assert fused.canonical_id == "professor-ada"
    assert fused.domain == "professor"
    assert fused.display_name == "陈艾达"
    assert fused.evidence_ids == (trace.evidence_id,)
    assert evidence_set.entity_handles == (
        read_module.CanonicalEntityHandle(
            canonical_id="professor-ada",
            domain="professor",
            display_name="陈艾达",
            evidence_ids=(trace.evidence_id,),
        ),
    )
    assert evidence_set.constraint_receipts == (
        read_module.ConstraintReceipt(
            raw_candidate_ids=(trace.raw_candidate_id,),
            outcome="accepted",
            failed_slots=(),
            aggregated_evidence_ids=(trace.evidence_id,),
        ),
    )
    assert len(evidence_set.candidate_traces) == 1
    assert evidence_set.candidate_traces[0].selected_result_id == "professor-ada"
    coverage = evidence_set.enumeration_coverage
    assert coverage is not None
    assert coverage.checked_ids == ("professor-ada",)
    assert coverage.eligible_ids == ("professor-ada",)
    assert coverage.retrieved_ids == ("professor-ada",)
    assert coverage.displayed_ids == ("professor-ada",)
    assert coverage.omitted_ids == ()
    assert coverage.unknown_ids == ()
    assert coverage.unknown_scope is True
    assert coverage.exhaustive is False
    assert coverage.accounting_complete is True
    assert coverage.continuation_state == "open_world"
    assert coverage.continuation_required is True

    relationship_request_authority = authority[2]
    relationship_result_authority = authority[3]
    assert trace.relationship_request_sha256 == read_module._canonical_sha256(
        relationship_request_authority.model_dump(mode="json")
    )
    assert trace.relationship_result_sha256 == (
        relationship_result_authority.content_sha256
    )
    assert trace.shared_assertion_id == (
        relationship_request_authority.relationship_assertions[0].assertion_id
    )
    assert trace.decision_release_id == plan.release_id

    direct_authority = isolated_read_module._replay_relationship_authority(
        release_bundle=positive["bundle"],
        published_release=positive["published"],
        index_projection_request=positive["index_request"],
        release_institution_catalog=positive["catalog"],
    )
    inverse_request_payload = read_module._lane_request(
        plan,
        "relationship",
        plan.web_policy,
    ).model_dump(mode="json", exclude={"content_sha256"})
    inverse_request_payload["max_candidates"] = 1
    inverse_request = read_module.LaneRequest.model_validate(inverse_request_payload)
    target_current = direct_authority.relationship_result.current_relationships[0]
    non_target_current = target_current.model_copy(
        update={
            "canonical_relationship_id": (
                "relationship:professor-paper:non-target-first"
            ),
            "target_endpoint": target_current.target_endpoint.model_copy(
                update={
                    "canonical_identity_id": "paper-non-target-first",
                    "stable_reference": "canonical:paper:paper-non-target-first",
                }
            ),
        }
    )
    expanded_relationship_result = direct_authority.relationship_result.model_copy(
        update={"current_relationships": (non_target_current, target_current)}
    )
    expanded_authority = isolated_read_module._RelationshipAuthority(
        internal_authority=direct_authority.internal_authority,
        relationship_request=direct_authority.relationship_request,
        relationship_result=expanded_relationship_result,
        candidate_result=direct_authority.candidate_result,
    )
    real_forward_candidates = (
        isolated_read_module._professor_to_paper_relationship_candidates
    )
    observed_internal_forward_caps: list[int] = []

    def ordered_forward_candidates(*, request: Any, authority: Any) -> Any:
        observed_internal_forward_caps.append(request.max_candidates)
        full_request_payload = request.model_dump(
            mode="json",
            exclude={"content_sha256"},
        )
        full_request_payload["max_candidates"] = 2
        target_candidates = real_forward_candidates(
            request=read_module.LaneRequest.model_validate(full_request_payload),
            authority=direct_authority,
        )
        assert len(target_candidates) == 1
        target_candidate = target_candidates[0]
        non_target_candidate = target_candidate.model_copy(
            update={
                "canonical_id": "paper-non-target-first",
                "display_name": "Non-target Paper first",
            }
        )
        return (non_target_candidate, target_candidate)[: request.max_candidates]

    monkeypatch.setattr(
        isolated_read_module,
        "_professor_to_paper_relationship_candidates",
        ordered_forward_candidates,
    )
    early_cap_candidates = (
        isolated_read_module._paper_to_professor_relationship_candidates(
            request=inverse_request,
            authority=expanded_authority,
        )
    )
    assert observed_internal_forward_caps == [2]
    assert len(early_cap_candidates) == 1
    assert early_cap_candidates[0].canonical_id == "professor-ada"
    monkeypatch.setattr(
        isolated_read_module,
        "_professor_to_paper_relationship_candidates",
        real_forward_candidates,
    )

    def execute_scenario(value: dict[str, Any]) -> Any:
        value_plan = value["plan"]
        return release_factory(
            release_bundle=value["bundle"],
            published_release=value["published"],
            index_projection_request=value["index_request"],
            release_institution_catalog=value["catalog"],
            universal_web_policy=value_plan.web_policy,
            web_search=lambda _: read_module.RetrievalLaneResult(),
            web_snapshot_policy=read_module.WebSnapshotPolicy(
                policy_id=f"web-snapshot-policy:{value['bundle'].release_id}",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
            clock=lambda: NOW,
        ).execute(value_plan)

    zero_scenarios: tuple[tuple[str, dict[str, Any]], ...] = (
        ("authoritative-zero", {"authoritative_zero": True}),
        ("wrong-family", {"nonmatching_relationship_authority": True}),
        ("rejected", {"decision_state": "rejected"}),
        ("multi-reference", {"multiple_retained_refs": True}),
        ("excluded-professor", {"excluded_endpoint_ids": ("professor-ada",)}),
        ("excluded-paper", {"excluded_endpoint_ids": ("paper-ada",)}),
    )
    for scenario_name, scenario_kwargs in zero_scenarios:
        zero_scenario = _s8r4_scenario(
            tmp_path=tmp_path,
            release_id=f"candidate-s8r4-{scenario_name}",
            **scenario_kwargs,
        )
        zero_result = execute_scenario(zero_scenario)
        assert zero_result.items == ()
        assert zero_result.fused_candidates == ()
        assert zero_result.entity_handles == ()
        assert zero_result.enumeration_coverage is not None
        assert zero_result.enumeration_coverage.unknown_scope is True
        assert zero_result.enumeration_coverage.exhaustive is False

    limited = _s8r4_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r4-limited",
        limited_endpoint_ids=("professor-ada", "paper-ada"),
    )
    limited_result = execute_scenario(limited)
    assert len(limited_result.items) == 1
    limited_trace = limited_result.items[0].local_projection_trace
    assert isinstance(limited_trace, read_module.LocalPaperProfessorRelationshipTrace)
    assert limited_trace.professor_eligibility_outcome in {"admitted", "limited"}
    assert limited_trace.paper_eligibility_outcome in {"admitted", "limited"}
    assert limited_trace.professor_eligibility_limitations
    assert limited_trace.paper_eligibility_limitations
    assert limited_trace.candidate_quality_flags == tuple(
        sorted(
            {
                *limited_trace.professor_eligibility_limitations,
                *limited_trace.paper_eligibility_limitations,
            }
        )
    )

    later = _s8r4_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r4-later",
        as_of=NOW + timedelta(days=1),
    )
    later_result = execute_scenario(later)
    later_trace = later_result.items[0].local_projection_trace
    assert isinstance(later_trace, read_module.LocalPaperProfessorRelationshipTrace)
    assert later_trace.candidate_quality_flags == (S8R1_SNAPSHOT_FLAG,)
    earlier = _s8r4_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r4-earlier",
        as_of=NOW - timedelta(days=1),
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="earlier than the authoritative snapshot",
    ):
        execute_scenario(earlier)

    def plan_with_displayed_ids(ids: tuple[str, ...]) -> Any:
        payload = plan.model_dump(mode="json", exclude={"content_sha256"})
        payload["structured_constraints"]["displayed_entity_ids"] = list(ids)
        payload["protected_slots"] = [
            read_module.ProtectedSlot(
                kind="displayed_entity_set",
                value="displayed_entity_set",
                entity_ids=ids,
            ).model_dump(mode="json")
        ]
        return read_module.RetrievalPlan.model_validate(payload)

    for displayed_ids, expected_error in (
        (("paper-ada", "paper-other"), "one displayed Paper"),
        (("professor-ada",), "not an accepted Paper"),
    ):
        invalid_web_calls: list[Any] = []
        with pytest.raises(
            isolated_read_module.IsolatedKnowledgeReadIntegrityError,
            match=expected_error,
        ):
            release_factory(
                **{
                    **service_kwargs,
                    "web_search": lambda value: (
                        invalid_web_calls.append(value)
                        or read_module.RetrievalLaneResult()
                    ),
                }
            ).execute(plan_with_displayed_ids(displayed_ids))
        assert invalid_web_calls == []

    unknown_result = release_factory(**service_kwargs).execute(
        plan_with_displayed_ids(("paper-unknown",))
    )
    assert unknown_result.items == ()
    assert unknown_result.fused_candidates == ()

    max_zero_payload = plan.model_dump(mode="json", exclude={"content_sha256"})
    max_zero_payload["max_candidates"] = 0
    max_zero = read_module.RetrievalPlan.model_validate(max_zero_payload)
    max_zero_result = release_factory(**service_kwargs).execute(max_zero)
    assert max_zero_result.items == ()
    assert max_zero_result.fused_candidates == ()

    lane_drift_payload = plan.model_dump(mode="json", exclude={"content_sha256"})
    lane_drift_payload["lanes"] = ["web"]
    lane_drift_payload["lane_queries"] = [
        query for query in lane_drift_payload["lane_queries"] if query["lane"] == "web"
    ]
    lane_drift = read_module.RetrievalPlan.model_validate(lane_drift_payload)
    lane_drift_web_calls: list[Any] = []
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="relationship paths require the relationship lane",
    ):
        release_factory(
            **{
                **service_kwargs,
                "web_search": lambda value: (
                    lane_drift_web_calls.append(value)
                    or read_module.RetrievalLaneResult()
                ),
            }
        ).execute(lane_drift)
    assert lane_drift_web_calls == []

    def assert_planning_error(
        relationship_type_id: str,
        direction: str,
        source_type: str,
        target_type: str,
        reason_code: str,
    ) -> None:
        request_value = _s8r4_planning_request(
            read_module,
            release_id=positive["bundle"].release_id,
        )
        base = _s8r4_proposal(read_module, request_value)
        proposal_payload = base.model_dump(mode="json", exclude={"content_sha256"})
        proposal_payload["relationship_paths"] = [
            {
                "relationship_type_id": relationship_type_id,
                "direction": direction,
                "source_type": source_type,
                "target_type": target_type,
            }
        ]
        proposal = read_module.RecordedPlanningProposal.model_validate(proposal_payload)
        planner = isolated_read_module.create_isolated_release_query_planner(
            release_bundle=positive["bundle"],
            published_release=positive["published"],
            index_projection_request=positive["index_request"],
            release_institution_catalog=positive["catalog"],
            planning_policy=_s8r4_planning_policy(read_module),
            proposal_provider=lambda _: proposal,
        )
        with pytest.raises(read_module.InvalidRetrievalPlanError) as exc_info:
            planner.plan(request_value)
        assert exc_info.value.reason_code == reason_code

    assert_planning_error(
        "professor_authored_paper",
        "professor_to_paper",
        "professor",
        "paper",
        "unsupported_relationship_direction",
    )
    assert_planning_error(
        "professor_authored_paper",
        "paper_to_professor",
        "professor",
        "paper",
        "unsupported_relationship_path",
    )
    assert_planning_error(
        "paper_has_author",
        "paper_to_professor",
        "paper",
        "professor",
        "unsupported_relationship_path",
    )

    professor_ref = "canonical:professor:professor-ada"
    paper_only_term = "professor_page_declaration"
    assert paper_only_term in item.snippet
    exact_identifier = "PROFESSOR-EXACT-S8R4"
    constrained_payload = plan.model_dump(mode="json", exclude={"content_sha256"})
    constrained_payload["protected_slots"].extend(
        (
            read_module.ProtectedSlot(
                kind="exact_identifier",
                value=exact_identifier,
                raw_text=exact_identifier,
            ).model_dump(mode="json"),
            read_module.ProtectedSlot(
                kind="negation",
                value=paper_only_term,
                raw_text=paper_only_term,
            ).model_dump(mode="json"),
        )
    )
    constrained_payload["structured_constraints"]["excluded_terms"] = [paper_only_term]
    constrained_plan = read_module.RetrievalPlan.model_validate(constrained_payload)
    web_payload = b"Current Web Professor identifier PROFESSOR-EXACT-S8R4"
    web_digest = hashlib.sha256(web_payload).hexdigest()
    web_snapshot = read_module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:s8r4-professor:sha256:{web_digest}",
        content_sha256=web_digest,
        retrieved_at=NOW,
        byte_length=len(web_payload),
    )

    def same_professor_web_search(value: Any) -> Any:
        web_item = read_module.EvidenceItem(
            evidence_id="evidence:web:s8r4:professor-ada:exact-identifier",
            object_id="professor-ada",
            domain="professor",
            lane="web",
            source_nature="current_web",
            source_locator="https://current.example/s8r4-professor-ada",
            snippet=web_payload.decode(),
            score=0.5,
            claim_binding=read_module.EvidenceClaimBinding(
                subject_id=professor_ref,
                predicate="exact_identifier",
                value=exact_identifier,
                status="accepted",
            ),
            web_snapshot=web_snapshot,
        )
        return read_module.RetrievalLaneResult(
            candidates=(
                read_module.RecallCandidate(
                    raw_candidate_id="raw:web:s8r4:professor-ada:exact-identifier",
                    display_name="陈艾达",
                    domain="professor",
                    identity_kind="canonical",
                    canonical_id="professor-ada",
                    resolution_state="resolved",
                    query_view=value.query_view,
                    lane="web",
                    attempt=1,
                    release_id=value.release_id,
                    adapter_version="s8r4-web-fixture-v1",
                    provider_version="s8r4-web-provider-v1",
                    raw_score=0.5,
                    evidence=(web_item,),
                ),
            ),
            web_snapshot_payloads=(
                read_module.WebSnapshotPayload(
                    snapshot_id=web_snapshot.snapshot_id,
                    content=web_payload,
                ),
            ),
        )

    constrained_result = release_factory(
        **{
            **service_kwargs,
            "web_search": same_professor_web_search,
            "web_snapshot_policy": read_module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8r4-same-professor",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
        }
    ).execute(constrained_plan)
    assert len(constrained_result.fused_candidates) == 1
    constrained_fused = constrained_result.fused_candidates[0]
    assert constrained_fused.canonical_id == "professor-ada"
    assert {evidence.lane for evidence in constrained_fused.evidence} == {
        "relationship",
        "web",
    }
    assert constrained_result.constraint_receipts[0].outcome == "accepted"
    assert constrained_result.constraint_receipts[0].failed_slots == ()
    assert constrained_result.entity_handles[0].domain == "professor"
    assert constrained_result.enumeration_coverage is not None
    assert constrained_result.enumeration_coverage.displayed_ids == ("professor-ada",)

    def same_professor_web_alias_search(value: Any) -> Any:
        result = same_professor_web_search(value)
        alias_object_id = "web-object:s8r4:professor-ada"
        canonical_item = result.candidates[0].evidence[0]
        alias_item = canonical_item.model_copy(
            update={
                "evidence_id": "evidence:web:s8r4:professor-ada:alias",
                "object_id": alias_object_id,
                "claim_binding": read_module.EvidenceClaimBinding(
                    subject_id=alias_object_id,
                    predicate="exact_identifier",
                    value=exact_identifier,
                    status="accepted",
                ),
            }
        )
        alias_candidate = result.candidates[0].model_copy(
            update={
                "raw_candidate_id": "raw:web:s8r4:professor-ada:alias",
                "identity_kind": "web_candidate",
                "evidence": (alias_item,),
            }
        )
        return result.model_copy(update={"candidates": (alias_candidate,)})

    alias_result = release_factory(
        **{
            **service_kwargs,
            "web_search": same_professor_web_alias_search,
            "web_snapshot_policy": read_module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8r4-same-professor-alias",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
        }
    ).execute(constrained_plan)
    assert len(alias_result.fused_candidates) == 1
    assert alias_result.fused_candidates[0].canonical_id == "professor-ada"
    assert {
        evidence.object_id for evidence in alias_result.fused_candidates[0].evidence
    } == {"professor-ada", "web-object:s8r4:professor-ada"}
    assert alias_result.entity_handles[0].canonical_id == "professor-ada"

    crosswire_payload = b"Hostile Web Professor identity crosswire"
    crosswire_digest = hashlib.sha256(crosswire_payload).hexdigest()
    crosswire_snapshot = read_module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:s8r4-crosswire:sha256:{crosswire_digest}",
        content_sha256=crosswire_digest,
        retrieved_at=NOW,
        byte_length=len(crosswire_payload),
    )

    def crosswired_professor_web_search(value: Any) -> Any:
        crosswired_item = read_module.EvidenceItem(
            evidence_id="evidence:web:s8r4:professor-identity-crosswire",
            object_id="professor-other",
            domain="professor",
            lane="web",
            source_nature="current_web",
            source_locator="https://current.example/s8r4-professor-crosswire",
            snippet=crosswire_payload.decode(),
            score=0.5,
            claim_binding=read_module.EvidenceClaimBinding(
                subject_id="canonical:professor:professor-other",
                predicate="display_name",
                value="Other Professor",
                status="accepted",
            ),
            web_snapshot=crosswire_snapshot,
        )
        return read_module.RetrievalLaneResult(
            candidates=(
                read_module.RecallCandidate(
                    raw_candidate_id="raw:web:s8r4:professor-identity-crosswire",
                    display_name="陈艾达",
                    domain="professor",
                    identity_kind="canonical",
                    canonical_id="professor-ada",
                    resolution_state="resolved",
                    query_view=value.query_view,
                    lane="web",
                    attempt=1,
                    release_id=value.release_id,
                    adapter_version="s8r4-web-fixture-v1",
                    provider_version="s8r4-web-provider-v1",
                    raw_score=0.5,
                    evidence=(crosswired_item,),
                ),
            ),
            web_snapshot_payloads=(
                read_module.WebSnapshotPayload(
                    snapshot_id=crosswire_snapshot.snapshot_id,
                    content=crosswire_payload,
                ),
            ),
        )

    crosswire_result = release_factory(
        **{
            **service_kwargs,
            "web_search": crosswired_professor_web_search,
            "web_snapshot_policy": read_module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8r4-crosswire",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
        }
    ).execute(plan)
    crosswire_trace_by_lane = {trace.lane: trace for trace in crosswire_result.traces}
    assert crosswire_trace_by_lane["web"].status == "unavailable"
    assert crosswire_trace_by_lane["web"].failure_kind == "invalid_output"
    assert all(
        evidence.evidence_id != "evidence:web:s8r4:professor-identity-crosswire"
        for candidate in crosswire_result.fused_candidates
        for evidence in candidate.evidence
    )
    assert len(crosswire_result.fused_candidates) == 1
    assert crosswire_result.fused_candidates[0].canonical_id == "professor-ada"

    def crosswired_web_only_professor_search(value: Any) -> Any:
        result = crosswired_professor_web_search(value)
        candidate = result.candidates[0].model_copy(
            update={"identity_kind": "web_only"}
        )
        return result.model_copy(update={"candidates": (candidate,)})

    web_only_crosswire_result = release_factory(
        **{
            **service_kwargs,
            "web_search": crosswired_web_only_professor_search,
            "web_snapshot_policy": read_module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8r4-web-only-crosswire",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
        }
    ).execute(plan)
    web_only_trace_by_lane = {
        trace.lane: trace for trace in web_only_crosswire_result.traces
    }
    assert web_only_trace_by_lane["web"].status == "unavailable"
    assert web_only_trace_by_lane["web"].failure_kind == "invalid_output"
    assert all(
        evidence.evidence_id != "evidence:web:s8r4:professor-identity-crosswire"
        for candidate in web_only_crosswire_result.fused_candidates
        for evidence in candidate.evidence
    )

    def crosswired_unknown_kind_professor_search(value: Any) -> Any:
        result = crosswired_professor_web_search(value)
        candidate = result.candidates[0].model_copy(
            update={"identity_kind": "hostile_identity_kind"}
        )
        return result.model_copy(update={"candidates": (candidate,)})

    unknown_kind_crosswire_result = release_factory(
        **{
            **service_kwargs,
            "web_search": crosswired_unknown_kind_professor_search,
            "web_snapshot_policy": read_module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8r4-unknown-kind-crosswire",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
        }
    ).execute(plan)
    unknown_kind_trace_by_lane = {
        trace.lane: trace for trace in unknown_kind_crosswire_result.traces
    }
    assert unknown_kind_trace_by_lane["web"].status == "unavailable"
    assert unknown_kind_trace_by_lane["web"].failure_kind == "invalid_output"
    assert all(
        evidence.evidence_id != "evidence:web:s8r4:professor-identity-crosswire"
        for candidate in unknown_kind_crosswire_result.fused_candidates
        for evidence in candidate.evidence
    )

    def crosswired_web_candidate_professor_search(value: Any) -> Any:
        result = crosswired_professor_web_search(value)
        candidate = result.candidates[0].model_copy(
            update={"identity_kind": "web_candidate"}
        )
        return result.model_copy(update={"candidates": (candidate,)})

    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="Web Professor claim subject differs from canonical authority",
    ):
        release_factory(
            **{
                **service_kwargs,
                "web_search": crosswired_web_candidate_professor_search,
                "web_snapshot_policy": read_module.WebSnapshotPolicy(
                    policy_id="web-snapshot-policy:s8r4-web-candidate-crosswire",
                    policy_version="web-snapshot-policy-v1",
                    max_bytes=8_192,
                ),
            }
        ).execute(plan)

    real_ephemeral_read_factory = isolated_read_module.create_ephemeral_knowledge_read

    def hostile_web_claim_delegate_factory(**kwargs: Any) -> Any:
        delegate = real_ephemeral_read_factory(**kwargs)

        class _HostileWebClaimDelegate:
            def execute(self, value: Any) -> Any:
                payload = delegate.execute(value).model_dump(mode="json")
                fused_evidence = payload["fused_candidates"][0]["evidence"]
                web_evidence = next(
                    evidence for evidence in fused_evidence if evidence["lane"] == "web"
                )
                web_evidence["claim_binding"]["subject_id"] = (
                    "canonical:professor:professor-other"
                )
                return read_module.EvidenceSet.model_validate(payload)

        return _HostileWebClaimDelegate()

    monkeypatch.setattr(
        isolated_read_module,
        "create_ephemeral_knowledge_read",
        hostile_web_claim_delegate_factory,
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="Web Professor claim subject differs from canonical authority",
    ):
        release_factory(
            **{
                **service_kwargs,
                "web_search": same_professor_web_search,
                "web_snapshot_policy": read_module.WebSnapshotPolicy(
                    policy_id="web-snapshot-policy:s8r4-hostile-claim",
                    policy_version="web-snapshot-policy-v1",
                    max_bytes=8_192,
                ),
            }
        ).execute(constrained_plan)
    monkeypatch.setattr(
        isolated_read_module,
        "create_ephemeral_knowledge_read",
        real_ephemeral_read_factory,
    )

    hostile_paper_payload = b"Hostile displayed Paper Web witness"
    hostile_paper_digest = hashlib.sha256(hostile_paper_payload).hexdigest()
    hostile_paper_snapshot = read_module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:s8r4-paper:sha256:{hostile_paper_digest}",
        content_sha256=hostile_paper_digest,
        retrieved_at=NOW,
        byte_length=len(hostile_paper_payload),
    )
    hostile_paper_result = read_module.RetrievalLaneResult(
        items=(
            read_module.EvidenceItem(
                evidence_id="evidence:web:s8r4:displayed-paper-witness",
                object_id="paper-ada",
                domain="paper",
                lane="web",
                source_nature="current_web",
                source_locator="https://current.example/s8r4-paper-witness",
                snippet=hostile_paper_payload.decode(),
                score=0.5,
                web_snapshot=hostile_paper_snapshot,
            ),
        ),
        web_snapshot_payloads=(
            read_module.WebSnapshotPayload(
                snapshot_id=hostile_paper_snapshot.snapshot_id,
                content=hostile_paper_payload,
            ),
        ),
    )
    hostile_paper_calls: list[Any] = []
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="Web source witness must not satisfy displayed Paper authority",
    ):
        release_factory(
            **{
                **service_kwargs,
                "web_search": lambda value: (
                    hostile_paper_calls.append(value) or hostile_paper_result
                ),
                "web_snapshot_policy": read_module.WebSnapshotPolicy(
                    policy_id="web-snapshot-policy:s8r4-hostile-paper",
                    policy_version="web-snapshot-policy-v1",
                    max_bytes=8_192,
                ),
            }
        ).execute(plan)
    assert len(hostile_paper_calls) == 1

    fabricated_payload = b"Fabricated Web Professor-Paper attribution"
    fabricated_digest = hashlib.sha256(fabricated_payload).hexdigest()
    fabricated_snapshot = read_module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:s8r4-fabricated:sha256:{fabricated_digest}",
        content_sha256=fabricated_digest,
        retrieved_at=NOW,
        byte_length=len(fabricated_payload),
    )

    def fabricated_attribution_web_search(value: Any) -> Any:
        fabricated_item = read_module.EvidenceItem(
            evidence_id="evidence:web:s8r4:fabricated-attribution",
            object_id="professor-ada",
            domain="professor",
            lane="web",
            source_nature="current_web",
            source_locator="https://current.example/s8r4-fabricated-attribution",
            snippet=fabricated_payload.decode(),
            score=0.5,
            claim_binding=read_module.EvidenceClaimBinding(
                subject_id=professor_ref,
                predicate="professor_attributed_to_paper",
                value="canonical:paper:paper-ada",
                status="accepted",
            ),
            web_snapshot=fabricated_snapshot,
        )
        return read_module.RetrievalLaneResult(
            candidates=(
                read_module.RecallCandidate(
                    raw_candidate_id="raw:web:s8r4:fabricated-attribution",
                    display_name="陈艾达",
                    domain="professor",
                    identity_kind="canonical",
                    canonical_id="professor-ada",
                    resolution_state="resolved",
                    query_view=value.query_view,
                    lane="web",
                    attempt=1,
                    release_id=value.release_id,
                    adapter_version="s8r4-web-fixture-v1",
                    provider_version="s8r4-web-provider-v1",
                    raw_score=0.5,
                    evidence=(fabricated_item,),
                ),
            ),
            web_snapshot_payloads=(
                read_module.WebSnapshotPayload(
                    snapshot_id=fabricated_snapshot.snapshot_id,
                    content=fabricated_payload,
                ),
            ),
        )

    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="non-local evidence cannot assert a Professor-Paper relationship",
    ):
        release_factory(
            **{
                **service_kwargs,
                "web_search": fabricated_attribution_web_search,
                "web_snapshot_policy": read_module.WebSnapshotPolicy(
                    policy_id="web-snapshot-policy:s8r4-fabricated",
                    policy_version="web-snapshot-policy-v1",
                    max_bytes=8_192,
                ),
            }
        ).execute(plan)

    def forged_trace_factory(**kwargs: Any) -> Any:
        adapter = real_relationship_factory(**kwargs)

        def forged(value: Any) -> Any:
            result = adapter(value)
            candidate = result.candidates[0]
            evidence = candidate.evidence[0]
            local_trace = evidence.local_projection_trace
            assert isinstance(
                local_trace,
                read_module.LocalPaperProfessorRelationshipTrace,
            )
            trace_payload = local_trace.model_dump(mode="python")
            trace_payload.update(
                {
                    "source_assignment_id": (
                        "relationship-assignment:professor:s8r4-crosswire"
                    ),
                    "raw_candidate_id": "",
                    "evidence_id": "",
                    "content_sha256": "0" * 64,
                }
            )
            forged_trace = (
                read_module.LocalPaperProfessorRelationshipTrace.model_validate(
                    trace_payload
                )
            )
            forged_evidence = evidence.model_copy(
                update={
                    "evidence_id": forged_trace.evidence_id,
                    "source_locator": (
                        isolated_read_module._local_projection_locator(forged_trace)
                    ),
                    "local_projection_trace": forged_trace,
                }
            )
            forged_candidate = candidate.model_copy(
                update={
                    "raw_candidate_id": forged_trace.raw_candidate_id,
                    "evidence": (forged_evidence,),
                }
            )
            return read_module.RetrievalLaneResult(candidates=(forged_candidate,))

        return forged

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        forged_trace_factory,
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="top-level evidence differs from replay authority",
    ):
        release_factory(**service_kwargs).execute(plan)

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        real_relationship_factory,
    )


def test_s8r1_release_scoped_technology_relationship_traversal(
    request: pytest.FixtureRequest,
) -> None:
    read_module, relationship_factory, release_read_factory = (
        _isolated_relationship_lookup_contract()
    )
    tmp_path: Path = request.getfixturevalue("tmp_path")
    monkeypatch: pytest.MonkeyPatch = request.getfixturevalue("monkeypatch")
    isolated_read_module = _isolated_knowledge_read_module()
    release_module = _isolated_release_publication_module()
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    index_module = _index_projection_module()
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    original_milvus_sha256 = _file_sha256(original_milvus)

    def scenario(
        *,
        release_id: str,
        authoritative_zero: bool = False,
        include_relationship_authority: bool = True,
        relationship_limitation: bool = False,
        relationship_excluded: bool = False,
        as_of: datetime = NOW,
    ) -> dict[str, Any]:
        authority = _technology_relationship_authority(
            release_id=release_id,
            authoritative_zero=authoritative_zero,
        )
        candidate_request, candidate_result = authority[:2]
        relationship_limitation_id = (
            "company-robotics" if relationship_limitation else None
        )
        relationship_excluded_id = "company-robotics" if relationship_excluded else None
        index_request = _index_projection_request(
            index_module,
            candidate_request,
            candidate_result,
            relationship_limitation_identity_id=relationship_limitation_id,
            relationship_excluded_identity_id=relationship_excluded_id,
        )
        bundle = _s7k_release_bundle(
            release_module,
            tmp_path=tmp_path,
            release_id=release_id,
            authority=authority,
            include_relationship_authority=include_relationship_authority,
            relationship_limitation_identity_id=relationship_limitation_id,
            relationship_excluded_identity_id=relationship_excluded_id,
        )
        assert (
            index_module.create_ephemeral_index_projection_builder().build(
                index_request
            )
            == bundle.index_result
        )
        published = _s8p1_published_release(
            contracts_module,
            release_id=release_id,
        )
        catalog = _s8r1_institution_catalog(
            read_module,
            release_id=release_id,
        )
        plan = _s8r1_plan(
            read_module=read_module,
            isolated_read_module=isolated_read_module,
            bundle=bundle,
            published=published,
            index_request=index_request,
            institution_catalog=catalog,
            as_of=as_of,
        )
        return {
            "authority": authority,
            "index_request": index_request,
            "bundle": bundle,
            "published": published,
            "catalog": catalog,
            "plan": plan,
        }

    positive = scenario(release_id="candidate-s8r1-relationship")
    plan = positive["plan"]
    bundle = positive["bundle"]
    index_request = positive["index_request"]
    published = positive["published"]
    catalog = positive["catalog"]
    assert plan.lanes == ("relationship", "web")
    assert len(plan.relationship_paths) == 1
    assert plan.relationship_paths[0] == read_module.RelationshipPathProposal(
        relationship_type_id="technology_company_relationship",
        direction="technology_to_company",
        source_type="technology_route",
        target_type="company",
    )
    relationship_queries = tuple(
        query
        for query in plan.internal_reference_queries
        if query.reference_type == "technology_route"
    )
    assert len(relationship_queries) == 1
    relationship_query = relationship_queries[0]
    assert relationship_query.relationship_evidence_required is True
    assert relationship_query.relationship_states == (
        "discussion_or_mention",
        "claimed_adoption",
        "demonstrated_use",
    )
    assert relationship_query.allowed_state_promotions == ()
    assert relationship_query.scope == S8R1_SCOPE
    assert relationship_query.enumeration_policy == plan.enumeration_policy
    assert relationship_query.as_of == NOW

    captured_relationship_requests: list[Any] = []
    captured_relationship_results: list[Any] = []
    captured_web_requests: list[Any] = []
    real_relationship_factory = relationship_factory

    def capturing_relationship_factory(**kwargs: Any) -> Any:
        adapter = real_relationship_factory(**kwargs)

        def captured_adapter(value: Any) -> Any:
            captured_relationship_requests.append(value)
            result = adapter(value)
            captured_relationship_results.append(result)
            return result

        return captured_adapter

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        capturing_relationship_factory,
    )

    physical_reads: list[Any] = []

    def forbidden_physical_read(value: Any) -> Any:
        physical_reads.append(value)
        raise AssertionError("S8R1 relationship retrieval must remain in memory")

    monkeypatch.setattr(
        isolated_read_module,
        "_read_bound_documents",
        forbidden_physical_read,
    )
    service_kwargs = {
        "release_bundle": bundle,
        "published_release": published,
        "index_projection_request": index_request,
        "release_institution_catalog": catalog,
        "universal_web_policy": plan.web_policy,
        "web_search": lambda value: (
            captured_web_requests.append(value) or read_module.RetrievalLaneResult()
        ),
        "web_snapshot_policy": read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8r1",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        "clock": lambda: NOW,
    }
    evidence_set = release_read_factory(**service_kwargs).execute(plan)
    assert physical_reads == []
    assert len(captured_relationship_requests) == 1
    relationship_request = captured_relationship_requests[0]
    assert relationship_request.relationship_paths == plan.relationship_paths
    assert relationship_request.relationship_reference_queries == relationship_queries
    assert relationship_request.internal_reference_queries == ()
    assert len(captured_web_requests) == 1
    assert captured_web_requests[0].relationship_paths == ()
    assert captured_web_requests[0].relationship_reference_queries == ()
    assert "relationship_paths" not in captured_web_requests[0].model_dump(mode="json")
    assert "relationship_reference_queries" not in captured_web_requests[0].model_dump(
        mode="json"
    )

    assert len(captured_relationship_results) == 1
    raw_result = captured_relationship_results[0]
    assert len(raw_result.candidates) == 3
    expected_states = {
        "entity_discusses_or_mentions_technology": "discussion_or_mention",
        "entity_claims_adoption_of_technology": "claimed_adoption",
        "entity_demonstrates_use_of_technology": "demonstrated_use",
    }
    observed_states: dict[str, str] = {}
    route_anchor = next(
        anchor
        for anchor in bundle.relationship_projection_request.internal_reference_projection_result.technology_evidence_anchors
        if anchor.reference_type == "technology_route"
    )
    route_id = relationship_query.canonical_route_ids[0]
    route_target = f"canonical:technology_route:{route_id}"
    for candidate in raw_result.candidates:
        assert candidate.domain == "company"
        assert candidate.canonical_id == "company-robotics"
        assert candidate.display_name == "Robotics Co"
        assert candidate.reference_type == "technology_route"
        assert candidate.identity_kind == "canonical"
        assert candidate.resolution_state == "resolved"
        assert candidate.origin_public_evidence_ids == (route_anchor.anchor_id,)
        assert candidate.adapter_version == "canonical-v2-isolated-relationship-v1"
        assert candidate.quality_flags == ()
        assert len(candidate.evidence) == 1
        item = candidate.evidence[0]
        trace = item.local_projection_trace
        assert isinstance(trace, read_module.LocalRelationshipTrace)
        claim = item.claim_binding
        assert claim is not None
        assert item.object_id == "company-robotics"
        assert item.domain == "company"
        assert item.lane == "relationship"
        assert item.source_nature == "local"
        assert item.source_authority == "canonical_release"
        assert claim.subject_id == "product:robot-arm"
        assert claim.predicate in expected_states
        assert claim.value == route_target
        assert claim.status == expected_states[claim.predicate]
        assert candidate.relationship_state == claim.status
        assert trace.path == "relationship_traversal"
        assert trace.execution_lane == "relationship"
        assert trace.root_company_id == "company-robotics"
        assert trace.product_subobject_id == "product:robot-arm"
        assert trace.technology_route_id == route_id
        assert trace.technology_anchor_id == route_anchor.anchor_id
        assert trace.relationship_type_id == claim.predicate
        assert trace.relationship_state == claim.status
        assert trace.claim_subject_id == claim.subject_id
        assert trace.claim_predicate == claim.predicate
        assert trace.claim_value == claim.value
        assert trace.claim_status == claim.status
        assert trace.eligibility_outcome == "admitted"
        assert trace.eligibility_limitations == ()
        assert trace.query_as_of == NOW
        assert trace.relationship_snapshot_as_of == NOW
        assert trace.lane_request_content_sha256 == relationship_request.content_sha256
        observed_states[claim.predicate] = claim.status
    assert observed_states == expected_states
    assert all(
        item.claim_binding is None
        or item.claim_binding.predicate != "product_has_capability"
        for candidate in raw_result.candidates
        for item in candidate.evidence
    )
    assert len(evidence_set.fused_candidates) == 1
    fused = evidence_set.fused_candidates[0]
    assert fused.canonical_id == "company-robotics"
    assert fused.domain == "company"
    assert fused.display_name == "Robotics Co"
    assert len(fused.raw_candidate_ids) == 3
    assert len(fused.evidence_ids) == 3
    assert len(evidence_set.entity_handles) == 1
    assert evidence_set.entity_handles[0].canonical_id == "company-robotics"
    relationship_lane_trace = next(
        trace for trace in evidence_set.traces if trace.lane == "relationship"
    )
    assert relationship_lane_trace.status == "succeeded"
    assert relationship_lane_trace.candidate_count == 3
    relationship_candidate_traces = tuple(
        trace for trace in evidence_set.candidate_traces if trace.lane == "relationship"
    )
    assert len(relationship_candidate_traces) == 3
    assert all(
        trace.disposition == "selected"
        and trace.selected_result_id == "company-robotics"
        for trace in relationship_candidate_traces
    )
    relationship_auxiliary = tuple(
        trace
        for trace in evidence_set.auxiliary_traces
        if trace.raw_candidate_id in fused.raw_candidate_ids
    )
    assert {trace.relationship_state for trace in relationship_auxiliary} == set(
        expected_states.values()
    )

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        real_relationship_factory,
    )

    assert relationship_query.enumeration_policy is not None
    drifted_plan_as_of = NOW + timedelta(days=1)
    drifted_plan_scope = f"{S8R1_SCOPE} (drifted query only)"
    drifted_plan_enumeration = relationship_query.enumeration_policy.model_copy(
        update={"scope": drifted_plan_scope, "as_of": drifted_plan_as_of}
    )
    drifted_plan_query = relationship_query.model_copy(
        update={
            "scope": drifted_plan_scope,
            "as_of": drifted_plan_as_of,
            "enumeration_policy": drifted_plan_enumeration,
        }
    )
    drifted_plan_payload = plan.model_dump(
        mode="json",
        exclude={"content_sha256"},
    )
    drifted_plan_payload["internal_reference_queries"] = [
        drifted_plan_query.model_dump(mode="json")
    ]
    drifted_plan = read_module.RetrievalPlan.model_validate(drifted_plan_payload)
    drifted_plan_web_calls: list[Any] = []
    drifted_plan_service = release_read_factory(
        **{
            **service_kwargs,
            "web_search": lambda value: (
                drifted_plan_web_calls.append(value)
                or read_module.RetrievalLaneResult()
            ),
        }
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="relationship.*plan|plan.*relationship|scope|as_of|enumeration",
    ):
        drifted_plan_service.execute(drifted_plan)
    assert drifted_plan_web_calls == []

    direct_adapter = real_relationship_factory(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=catalog,
    )
    direct_request = _s8r1_lane_request(read_module, plan)
    assert direct_request == relationship_request
    assert (
        direct_adapter(
            read_module.LaneRequest.model_validate(
                {
                    **direct_request.model_dump(
                        mode="json",
                        exclude={"content_sha256"},
                    ),
                    "max_candidates": 0,
                }
            )
        ).candidates
        == ()
    )
    bounded = direct_adapter(
        read_module.LaneRequest.model_validate(
            {
                **direct_request.model_dump(
                    mode="json",
                    exclude={"content_sha256"},
                ),
                "max_candidates": 1,
            }
        )
    )
    assert len(bounded.candidates) == 1
    assert bounded.candidates[0].relationship_state == "claimed_adoption"

    def request_with(
        *,
        paths: tuple[Any, ...] | None = None,
        queries: tuple[Any, ...] | None = None,
    ) -> Any:
        payload = direct_request.model_dump(mode="json", exclude={"content_sha256"})
        if paths is not None:
            payload["relationship_paths"] = [
                path.model_dump(mode="json") for path in paths
            ]
        if queries is not None:
            payload["relationship_reference_queries"] = [
                query.model_dump(mode="json") for query in queries
            ]
        return read_module.LaneRequest.model_validate(payload)

    changed_path = plan.relationship_paths[0].model_copy(
        update={"direction": "company_to_technology"}
    )
    person_query = relationship_query.model_copy(update={"reference_type": "person"})
    changed_alias = relationship_query.model_copy(
        update={"resolved_aliases": (("other route", route_id),)}
    )
    changed_states = relationship_query.model_copy(
        update={"relationship_states": ("demonstrated_use",)}
    )
    promoted_state = relationship_query.model_copy(
        update={"allowed_state_promotions": ("mention_to_adoption",)}
    )
    changed_scope = relationship_query.model_copy(update={"scope": "other scope"})
    with pytest.raises(ValueError, match="technology_route"):
        request_with(queries=(person_query,))
    invalid_requests = (
        request_with(paths=()),
        request_with(paths=(changed_path,)),
        request_with(queries=()),
        request_with(queries=(relationship_query, relationship_query)),
        request_with(queries=(changed_alias,)),
        request_with(queries=(changed_states,)),
        request_with(queries=(promoted_state,)),
        request_with(queries=(changed_scope,)),
    )
    for invalid_request in invalid_requests:
        with pytest.raises(
            (ValueError, isolated_read_module.IsolatedKnowledgeReadIntegrityError)
        ):
            direct_adapter(invalid_request)

    earlier = NOW - timedelta(days=1)
    earlier_enumeration = relationship_query.enumeration_policy.model_copy(
        update={"as_of": earlier}
    )
    earlier_query = relationship_query.model_copy(
        update={"as_of": earlier, "enumeration_policy": earlier_enumeration}
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="as_of|snapshot",
    ):
        direct_adapter(request_with(queries=(earlier_query,)))

    later = NOW + timedelta(days=1)
    later_enumeration = relationship_query.enumeration_policy.model_copy(
        update={"as_of": later}
    )
    later_query = relationship_query.model_copy(
        update={"as_of": later, "enumeration_policy": later_enumeration}
    )
    later_result = direct_adapter(request_with(queries=(later_query,)))
    assert len(later_result.candidates) == 3
    assert all(
        candidate.quality_flags == (S8R1_SNAPSHOT_FLAG,)
        and all(
            isinstance(item.local_projection_trace, read_module.LocalRelationshipTrace)
            and item.local_projection_trace.query_as_of == later
            and item.local_projection_trace.relationship_snapshot_as_of == NOW
            for item in candidate.evidence
        )
        for candidate in later_result.candidates
    )
    later_plan_enumeration = plan.enumeration_policy.model_copy(update={"as_of": later})
    later_plan_query = relationship_query.model_copy(
        update={
            "as_of": later,
            "enumeration_policy": later_plan_enumeration,
        }
    )
    later_plan_payload = plan.model_dump(mode="json", exclude={"content_sha256"})
    later_plan_payload.update(
        {
            "as_of": later,
            "enumeration_policy": later_plan_enumeration.model_dump(mode="json"),
            "internal_reference_queries": [later_plan_query.model_dump(mode="json")],
        }
    )
    later_plan = read_module.RetrievalPlan.model_validate(later_plan_payload)
    assert later_plan.as_of == later
    assert later_plan.enumeration_policy == later_plan_enumeration
    assert later_plan.internal_reference_queries == (later_plan_query,)
    later_plan_result = release_read_factory(**service_kwargs).execute(later_plan)
    later_fused = next(
        candidate
        for candidate in later_plan_result.fused_candidates
        if candidate.canonical_id == "company-robotics"
    )
    assert later_fused.quality_flags == (S8R1_SNAPSHOT_FLAG,)
    assert all(
        isinstance(item.local_projection_trace, read_module.LocalRelationshipTrace)
        and item.local_projection_trace.query_as_of == later
        and item.local_projection_trace.relationship_snapshot_as_of == NOW
        for item in later_fused.evidence
        if item.lane == "relationship"
    )

    zero = scenario(
        release_id="candidate-s8r1-authoritative-zero",
        authoritative_zero=True,
    )
    zero_web_calls: list[Any] = []
    zero_result = release_read_factory(
        release_bundle=zero["bundle"],
        published_release=zero["published"],
        index_projection_request=zero["index_request"],
        release_institution_catalog=zero["catalog"],
        universal_web_policy=zero["plan"].web_policy,
        web_search=lambda value: (
            zero_web_calls.append(value) or read_module.RetrievalLaneResult()
        ),
        web_snapshot_policy=read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8r1-zero",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        clock=lambda: NOW,
    ).execute(zero["plan"])
    assert len(zero_web_calls) == 1
    assert zero_result.items == ()
    assert zero_result.fused_candidates == ()
    zero_relationship_trace = next(
        trace for trace in zero_result.traces if trace.lane == "relationship"
    )
    assert zero_relationship_trace.status == "succeeded"
    assert zero_relationship_trace.candidate_count == 0

    legacy = scenario(
        release_id="candidate-s8r1-legacy-zero",
        include_relationship_authority=False,
    )
    legacy_web_calls: list[Any] = []
    legacy_service = release_read_factory(
        release_bundle=legacy["bundle"],
        published_release=legacy["published"],
        index_projection_request=legacy["index_request"],
        release_institution_catalog=legacy["catalog"],
        universal_web_policy=legacy["plan"].web_policy,
        web_search=lambda value: (
            legacy_web_calls.append(value) or read_module.RetrievalLaneResult()
        ),
        web_snapshot_policy=read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8r1-legacy",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        clock=lambda: NOW,
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="unsupported lane",
    ):
        legacy_service.execute(legacy["plan"])
    assert legacy_web_calls == []

    no_index_web_calls: list[Any] = []
    no_index_service = release_read_factory(
        release_bundle=bundle,
        published_release=published,
        universal_web_policy=plan.web_policy,
        web_search=lambda value: (
            no_index_web_calls.append(value) or read_module.RetrievalLaneResult()
        ),
        web_snapshot_policy=read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8r1-no-index",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        clock=lambda: NOW,
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="unsupported lane",
    ):
        no_index_service.execute(plan)
    assert no_index_web_calls == []

    limited = scenario(
        release_id="candidate-s8r1-limited",
        relationship_limitation=True,
    )
    limited_adapter = real_relationship_factory(
        release_bundle=limited["bundle"],
        published_release=limited["published"],
        index_projection_request=limited["index_request"],
        release_institution_catalog=limited["catalog"],
    )
    limited_request = _s8r1_lane_request(read_module, limited["plan"])
    limited_result = limited_adapter(limited_request)
    limited_path_result = next(
        result
        for result in limited["index_request"].public_path_eligibility_results
        if result.subject_identity_id == "company-robotics"
    )
    limited_decision = next(
        decision
        for decision in limited_path_result.decisions
        if decision.path == "verified_relationship_traversal"
    )
    assert limited_decision.outcome is PolicyOutcome.admitted
    assert limited_decision.limitations
    assert all(
        candidate.quality_flags == limited_decision.limitations
        for candidate in limited_result.candidates
    )

    excluded = scenario(
        release_id="candidate-s8r1-excluded",
        relationship_excluded=True,
    )
    excluded_adapter = real_relationship_factory(
        release_bundle=excluded["bundle"],
        published_release=excluded["published"],
        index_projection_request=excluded["index_request"],
        release_institution_catalog=excluded["catalog"],
    )
    assert (
        excluded_adapter(_s8r1_lane_request(read_module, excluded["plan"])).candidates
        == ()
    )

    zero_same_release_authority = _technology_relationship_authority(
        release_id=bundle.release_id,
        authoritative_zero=True,
    )
    mismatched_bundle = _s7k_constructed_bundle(
        release_module,
        bundle,
        relationship_projection_result=zero_same_release_authority[3],
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="relationship|authority|replay",
    ):
        real_relationship_factory(
            release_bundle=mismatched_bundle,
            published_release=published,
            index_projection_request=index_request,
            release_institution_catalog=catalog,
        )

    forged_web_calls: list[Any] = []

    def forged_display_factory(**kwargs: Any) -> Any:
        adapter = real_relationship_factory(**kwargs)

        def forged_adapter(value: Any) -> Any:
            result = adapter(value)
            return read_module.RetrievalLaneResult(
                candidates=tuple(
                    read_module.RecallCandidate.model_validate(
                        {
                            **candidate.model_dump(mode="json"),
                            "display_name": "Forged Company display",
                        }
                    )
                    for candidate in result.candidates
                )
            )

        return forged_adapter

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        forged_display_factory,
    )
    forged_service = release_read_factory(
        **{
            **service_kwargs,
            "web_search": lambda value: (
                forged_web_calls.append(value) or read_module.RetrievalLaneResult()
            ),
        }
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="relationship|display|authority",
    ):
        forged_service.execute(plan)
    assert len(forged_web_calls) == 1

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        real_relationship_factory,
    )
    real_ephemeral_read_factory = isolated_read_module.create_ephemeral_knowledge_read

    def hostile_delegate_factory(
        mutation: Callable[[Any], dict[str, Any]],
    ) -> Callable[..., Any]:
        def factory(**kwargs: Any) -> Any:
            delegate = real_ephemeral_read_factory(**kwargs)

            class _HostileDelegate:
                def execute(self, value: Any) -> Any:
                    result = delegate.execute(value)
                    return read_module.EvidenceSet.model_validate(mutation(result))

            return _HostileDelegate()

        return factory

    def drift_fused_resolution(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        fused_payload = payload["fused_candidates"][0]
        payload["fused_candidates"][0] = {
            **fused_payload,
            "identity_kind": "hostile_identity_kind",
            "resolution_state": "hostile_resolution_state",
        }
        return payload

    def strip_fused_relationship_snapshot_flag(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        fused_payload = payload["fused_candidates"][0]
        payload["fused_candidates"][0] = {
            **fused_payload,
            "quality_flags": tuple(
                flag
                for flag in fused_payload["quality_flags"]
                if flag != S8R1_SNAPSHOT_FLAG
            ),
        }
        return payload

    def drift_relationship_retrieval_trace(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        trace_index = next(
            index
            for index, trace in enumerate(payload["traces"])
            if trace["lane"] == "relationship"
        )
        payload["traces"][trace_index] = {
            **payload["traces"][trace_index],
            "query_view": "view:hostile-relationship",
            "attempt": 2,
            "release_id": "hostile-relationship-release",
        }
        return payload

    def prepend_conflicting_relationship_auxiliary_trace(
        result: Any,
    ) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        authoritative_trace = next(
            trace
            for trace in payload["auxiliary_traces"]
            if trace["reference_type"] == "technology_route"
            and trace["relationship_state"] is not None
        )
        payload["auxiliary_traces"].insert(
            0,
            read_module.AuxiliaryTrace(
                raw_candidate_id=authoritative_trace["raw_candidate_id"],
                reference_type="person",
                origin_public_evidence_ids=("anchor:hostile-relationship",),
                relationship_state=authoritative_trace["relationship_state"],
                eligible=False,
            ).model_dump(mode="json"),
        )
        return payload

    def add_evidence_reusing_fused_candidate(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        fused_payload = payload["fused_candidates"][0]
        payload["fused_candidates"].append(
            {
                **fused_payload,
                "result_id": "fused-result:hostile-relationship-evidence-reuse",
                "canonical_id": "company-hostile-evidence-reuse",
                "display_name": "Hostile evidence reuse",
                "raw_candidate_ids": ("hostile-unrelated-raw-candidate",),
            }
        )
        return payload

    def add_evidence_reusing_canonical_handle(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        fused_payload = payload["fused_candidates"][0]
        payload["entity_handles"].append(
            read_module.CanonicalEntityHandle(
                canonical_id="company-hostile-handle-reuse",
                domain="company",
                display_name="Hostile canonical handle",
                evidence_ids=tuple(fused_payload["evidence_ids"]),
            ).model_dump(mode="json")
        )
        return payload

    def add_evidence_reusing_web_handle(result: Any) -> dict[str, Any]:
        payload = result.model_dump(mode="json")
        fused_payload = payload["fused_candidates"][0]
        payload["entity_handles"].append(
            read_module.WebEntityHandle(
                handle_id="web-handle:hostile-relationship-evidence-reuse",
                domain="company",
                display_name="Hostile Web handle",
                evidence_snapshot_ids=(),
                evidence_ids=tuple(fused_payload["evidence_ids"]),
                resolution_state="unresolved",
                candidate_canonical_ids=(),
                originating_query=plan.original_query,
                origin_lane="web",
                origin_attempt=1,
            ).model_dump(mode="json")
        )
        return payload

    later_hostile_web_calls: list[Any] = []
    monkeypatch.setattr(
        isolated_read_module,
        "create_ephemeral_knowledge_read",
        hostile_delegate_factory(strip_fused_relationship_snapshot_flag),
    )
    later_hostile_service = release_read_factory(
        **{
            **service_kwargs,
            "web_search": lambda value: (
                later_hostile_web_calls.append(value)
                or read_module.RetrievalLaneResult()
            ),
        }
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="relationship|fused|quality|limitation|snapshot|freshness",
    ):
        later_hostile_service.execute(later_plan)
    assert len(later_hostile_web_calls) == 1
    monkeypatch.setattr(
        isolated_read_module,
        "create_ephemeral_knowledge_read",
        real_ephemeral_read_factory,
    )

    hostile_delegate_mutations = (
        drift_fused_resolution,
        drift_relationship_retrieval_trace,
        prepend_conflicting_relationship_auxiliary_trace,
        add_evidence_reusing_fused_candidate,
        add_evidence_reusing_canonical_handle,
        add_evidence_reusing_web_handle,
    )
    for mutation in hostile_delegate_mutations:
        hostile_web_calls: list[Any] = []
        monkeypatch.setattr(
            isolated_read_module,
            "create_ephemeral_knowledge_read",
            hostile_delegate_factory(mutation),
        )
        hostile_service = release_read_factory(
            **{
                **service_kwargs,
                "web_search": lambda value, calls=hostile_web_calls: (
                    calls.append(value) or read_module.RetrievalLaneResult()
                ),
            }
        )
        with pytest.raises(
            isolated_read_module.IsolatedKnowledgeReadIntegrityError,
            match="relationship|fused|handle|identity|resolution|authority",
        ):
            hostile_service.execute(plan)
        assert len(hostile_web_calls) == 1
    monkeypatch.setattr(
        isolated_read_module,
        "create_ephemeral_knowledge_read",
        real_ephemeral_read_factory,
    )

    assert _file_sha256(original_milvus) == original_milvus_sha256


def test_s8r5_executes_release_scoped_patent_to_company_applicant_traversal(
    request: pytest.FixtureRequest,
) -> None:
    read_module, relationship_factory, release_factory = (
        _s8r5_public_relationship_contract()
    )
    tmp_path: Path = request.getfixturevalue("tmp_path")
    monkeypatch: pytest.MonkeyPatch = request.getfixturevalue("monkeypatch")
    isolated_read_module = _isolated_knowledge_read_module()

    positive = _s8r5_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r5-patent-company",
    )
    plan = positive["plan"]
    assert plan.domains == ("company",)
    assert plan.lanes == ("relationship", "web")
    assert plan.relationship_paths == (
        read_module.RelationshipPathProposal(
            relationship_type_id="company_has_patent",
            direction="patent_to_company",
            source_type="patent",
            target_type="company",
        ),
    )
    assert plan.structured_constraints.displayed_entity_ids == ("patent-ada",)
    assert tuple(
        slot.entity_ids
        for slot in plan.protected_slots
        if slot.kind == "displayed_entity_set"
    ) == (("patent-ada",),)
    assert plan.enumeration_policy is not None
    assert plan.enumeration_policy.mode == "representative"
    assert plan.enumeration_policy.scope == S8R5_SCOPE
    assert plan.enumeration_policy.as_of == NOW
    assert plan.enumeration_policy.finite_universe_id is None
    assert plan.enumeration_policy.eligible_member_ids == ()
    assert plan.enumeration_policy.required_member_ids == ()
    assert plan.enumeration_policy.exhaustive is False
    assert plan.enumeration_policy.continuation_state == "available"

    captured_relationship_requests: list[Any] = []
    real_relationship_factory = relationship_factory

    def capturing_relationship_factory(**kwargs: Any) -> Any:
        adapter = real_relationship_factory(**kwargs)

        def captured_adapter(value: Any) -> Any:
            captured_relationship_requests.append(value)
            return adapter(value)

        return captured_adapter

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        capturing_relationship_factory,
    )
    physical_reads: list[Any] = []

    def forbidden_physical_read(value: Any) -> Any:
        physical_reads.append(value)
        raise AssertionError("S8R5 relationship traversal must remain in memory")

    monkeypatch.setattr(
        isolated_read_module,
        "_read_bound_documents",
        forbidden_physical_read,
    )
    service_kwargs = {
        "release_bundle": positive["bundle"],
        "published_release": positive["published"],
        "index_projection_request": positive["index_request"],
        "release_institution_catalog": positive["catalog"],
        "universal_web_policy": plan.web_policy,
        "web_search": lambda _: read_module.RetrievalLaneResult(),
        "web_snapshot_policy": read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8r5",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        "clock": lambda: NOW,
    }
    evidence_set = release_factory(**service_kwargs).execute(plan)
    assert evidence_set.requested_traversal == read_module.TypedTraversalRequest(
        path_id="patent_to_company",
        source_domain="patent",
        target_domain="company",
        relationship_type="patent_has_applicant",
        direction="forward",
    )
    assert physical_reads == []
    assert len(captured_relationship_requests) == 1
    relationship_request = captured_relationship_requests[0]
    assert relationship_request.domains == ("company",)
    assert relationship_request.relationship_paths == plan.relationship_paths
    assert relationship_request.relationship_reference_queries == ()
    assert relationship_request.relationship_enumeration_policy == (
        plan.enumeration_policy
    )
    assert relationship_request.structured_constraints.displayed_entity_ids == (
        "patent-ada",
    )
    assert len(evidence_set.items) == 1
    item = evidence_set.items[0]
    trace = item.local_projection_trace
    assert isinstance(trace, read_module.LocalPatentCompanyRelationshipTrace)
    assert trace.displayed_entity_ids == ("patent-ada",)
    assert trace.displayed_patent_id == "patent-ada"
    assert trace.patent_id == "patent-ada"
    assert trace.company_id == "company-robotics"
    assert trace.candidate_domain == "company"
    assert trace.candidate_canonical_id == "company-robotics"
    assert trace.candidate_display_name == "Robotics Co"
    assert trace.relationship_type_id == "patent_has_applicant"
    assert trace.relationship_source_endpoint == "canonical:patent:patent-ada"
    assert trace.relationship_target_endpoint == ("canonical:company:company-robotics")
    assert trace.relationship_role_bindings == (
        ("applicant", "canonical:company:company-robotics"),
    )
    assert trace.claim_subject_id == "canonical:patent:patent-ada"
    assert trace.claim_predicate == "patent_has_applicant"
    assert trace.claim_value == "canonical:company:company-robotics"
    assert trace.company_traversal_directions == ("company_to_patent",)
    assert trace.patent_traversal_directions == ("patent_to_company",)
    assert trace.query_as_of == trace.relationship_snapshot_as_of == NOW
    assert trace.lane_request_content_sha256 == relationship_request.content_sha256
    assert item.object_id == "company-robotics"
    assert item.domain == "company"
    assert item.claim_binding == read_module.EvidenceClaimBinding(
        subject_id="canonical:patent:patent-ada",
        predicate="patent_has_applicant",
        value="canonical:company:company-robotics",
        status="accepted",
    )
    assert len(evidence_set.fused_candidates) == 1
    fused = evidence_set.fused_candidates[0]
    assert fused.canonical_id == "company-robotics"
    assert fused.domain == "company"
    assert fused.display_name == "Robotics Co"
    assert fused.evidence_ids == (trace.evidence_id,)
    assert evidence_set.entity_handles == (
        read_module.CanonicalEntityHandle(
            canonical_id="company-robotics",
            domain="company",
            display_name="Robotics Co",
            evidence_ids=(trace.evidence_id,),
        ),
    )
    assert len(evidence_set.candidate_traces) == 1
    assert evidence_set.candidate_traces[0].selected_result_id == "company-robotics"
    coverage = evidence_set.enumeration_coverage
    assert coverage is not None
    assert coverage.checked_ids == ("company-robotics",)
    assert coverage.eligible_ids == ("company-robotics",)
    assert coverage.retrieved_ids == ("company-robotics",)
    assert coverage.displayed_ids == ("company-robotics",)
    assert coverage.omitted_ids == ()
    assert coverage.unknown_ids == ()
    assert coverage.unknown_scope is True
    assert coverage.exhaustive is False
    assert coverage.accounting_complete is True
    assert coverage.continuation_state == "open_world"
    assert coverage.continuation_required is True

    direct_authority = isolated_read_module._replay_relationship_authority(
        release_bundle=positive["bundle"],
        published_release=positive["published"],
        index_projection_request=positive["index_request"],
        release_institution_catalog=positive["catalog"],
    )
    inverse_request_payload = read_module._lane_request(
        plan,
        "relationship",
        plan.web_policy,
    ).model_dump(mode="json", exclude={"content_sha256"})
    inverse_request_payload["max_candidates"] = 1
    inverse_request = read_module.LaneRequest.model_validate(inverse_request_payload)
    target_current = direct_authority.relationship_result.current_relationships[0]
    non_target_current = target_current.model_copy(
        update={
            "canonical_relationship_id": (
                "relationship:patent-applicant:non-target-first"
            ),
            "source_endpoint": target_current.source_endpoint.model_copy(
                update={
                    "canonical_identity_id": "patent-non-target-first",
                    "stable_reference": "canonical:patent:patent-non-target-first",
                }
            ),
        }
    )
    expanded_relationship_result = direct_authority.relationship_result.model_copy(
        update={"current_relationships": (non_target_current, target_current)}
    )
    expanded_authority = isolated_read_module._RelationshipAuthority(
        internal_authority=direct_authority.internal_authority,
        relationship_request=direct_authority.relationship_request,
        relationship_result=expanded_relationship_result,
        candidate_result=direct_authority.candidate_result,
    )
    real_forward_candidates = (
        isolated_read_module._company_to_patent_relationship_candidates
    )
    observed_internal_forward_caps: list[int] = []

    def ordered_forward_candidates(*, request: Any, authority: Any) -> Any:
        observed_internal_forward_caps.append(request.max_candidates)
        full_request_payload = request.model_dump(
            mode="json",
            exclude={"content_sha256"},
        )
        full_request_payload["max_candidates"] = 2
        target_candidates = real_forward_candidates(
            request=read_module.LaneRequest.model_validate(full_request_payload),
            authority=direct_authority,
        )
        assert len(target_candidates) == 1
        target_candidate = target_candidates[0]
        non_target_candidate = target_candidate.model_copy(
            update={
                "canonical_id": "patent-non-target-first",
                "display_name": "Non-target Patent first",
            }
        )
        return (non_target_candidate, target_candidate)[: request.max_candidates]

    monkeypatch.setattr(
        isolated_read_module,
        "_company_to_patent_relationship_candidates",
        ordered_forward_candidates,
    )
    early_cap_candidates = (
        isolated_read_module._patent_to_company_relationship_candidates(
            request=inverse_request,
            authority=expanded_authority,
        )
    )
    # The old caller-cap seam would observe [1], keep only the non-target Patent,
    # and return zero. The authoritative replay count must be two before filtering.
    assert observed_internal_forward_caps == [2]
    assert len(early_cap_candidates) == 1
    assert early_cap_candidates[0].canonical_id == "company-robotics"
    monkeypatch.setattr(
        isolated_read_module,
        "_company_to_patent_relationship_candidates",
        real_forward_candidates,
    )

    def s8r5_web_result(
        value: Any,
        *,
        case_id: str,
        object_id: str,
        subject_id: str,
        identity_kind: Any,
    ) -> Any:
        web_payload = f"S8R5 Web Company evidence: {case_id}".encode()
        web_digest = hashlib.sha256(web_payload).hexdigest()
        web_snapshot = read_module.WebEvidenceSnapshot(
            snapshot_id=f"web-snapshot:s8r5:{case_id}:sha256:{web_digest}",
            content_sha256=web_digest,
            retrieved_at=NOW,
            byte_length=len(web_payload),
        )
        evidence_id = f"evidence:web:s8r5:{case_id}"
        web_item = read_module.EvidenceItem(
            evidence_id=evidence_id,
            object_id=object_id,
            domain="company",
            lane="web",
            source_nature="current_web",
            source_locator=f"https://current.example/s8r5/{case_id}",
            snippet=web_payload.decode(),
            score=0.5,
            claim_binding=read_module.EvidenceClaimBinding(
                subject_id=subject_id,
                predicate="display_name",
                value="Robotics Co",
                status="accepted",
            ),
            web_snapshot=web_snapshot,
        )
        return read_module.RetrievalLaneResult(
            candidates=(
                read_module.RecallCandidate(
                    raw_candidate_id=f"raw:web:s8r5:{case_id}",
                    display_name="Robotics Co",
                    domain="company",
                    identity_kind=identity_kind,
                    canonical_id="company-robotics",
                    resolution_state="resolved",
                    query_view=value.query_view,
                    lane="web",
                    attempt=1,
                    release_id=value.release_id,
                    adapter_version="s8r5-web-fixture-v1",
                    provider_version="s8r5-web-provider-v1",
                    raw_score=0.5,
                    evidence=(web_item,),
                ),
            ),
            web_snapshot_payloads=(
                read_module.WebSnapshotPayload(
                    snapshot_id=web_snapshot.snapshot_id,
                    content=web_payload,
                ),
            ),
        )

    alias_object_id = "web-object:s8r5:company-robotics"
    alias_result = release_factory(
        **{
            **service_kwargs,
            "web_search": lambda value: s8r5_web_result(
                value,
                case_id="same-company-alias",
                object_id=alias_object_id,
                subject_id=alias_object_id,
                identity_kind="web_candidate",
            ),
            "web_snapshot_policy": read_module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8r5-same-company-alias",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
        }
    ).execute(plan)
    assert len(alias_result.fused_candidates) == 1
    assert alias_result.fused_candidates[0].canonical_id == "company-robotics"
    assert {
        evidence.object_id for evidence in alias_result.fused_candidates[0].evidence
    } == {"company-robotics", alias_object_id}
    assert {
        evidence.lane for evidence in alias_result.fused_candidates[0].evidence
    } == {
        "relationship",
        "web",
    }
    assert alias_result.entity_handles[0].canonical_id == "company-robotics"

    canonical_crosswire_evidence_id = "evidence:web:s8r5:canonical-crosswire"
    canonical_crosswire_result = release_factory(
        **{
            **service_kwargs,
            "web_search": lambda value: s8r5_web_result(
                value,
                case_id="canonical-crosswire",
                object_id="company-other",
                subject_id="canonical:company:company-other",
                identity_kind="canonical",
            ),
            "web_snapshot_policy": read_module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8r5-canonical-crosswire",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
        }
    ).execute(plan)
    canonical_crosswire_trace_by_lane = {
        lane_trace.lane: lane_trace for lane_trace in canonical_crosswire_result.traces
    }
    assert canonical_crosswire_trace_by_lane["web"].status == "unavailable"
    assert canonical_crosswire_trace_by_lane["web"].failure_kind == "invalid_output"
    assert len(canonical_crosswire_result.fused_candidates) == 1
    assert (
        canonical_crosswire_result.fused_candidates[0].canonical_id
        == "company-robotics"
    )
    assert all(
        evidence.evidence_id != canonical_crosswire_evidence_id
        for candidate in canonical_crosswire_result.fused_candidates
        for evidence in candidate.evidence
    )

    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="Web Company claim subject differs from canonical authority",
    ):
        release_factory(
            **{
                **service_kwargs,
                "web_search": lambda value: s8r5_web_result(
                    value,
                    case_id="web-candidate-other-canonical-subject",
                    object_id=alias_object_id,
                    subject_id="canonical:company:company-other",
                    identity_kind="web_candidate",
                ),
                "web_snapshot_policy": read_module.WebSnapshotPolicy(
                    policy_id=(
                        "web-snapshot-policy:s8r5-web-candidate-other-canonical-subject"
                    ),
                    policy_version="web-snapshot-policy-v1",
                    max_bytes=8_192,
                ),
            }
        ).execute(plan)


def test_s8c_closes_release_bound_knowledge_read_runtime(
    request: pytest.FixtureRequest,
) -> None:
    read_module, isolated_read_module, release_factory = (
        _s8c_aggregate_runtime_contract()
    )
    tmp_path: Path = request.getfixturevalue("tmp_path")
    monkeypatch: pytest.MonkeyPatch = request.getfixturevalue("monkeypatch")
    isolated_index_module = _isolated_index_projection_module()
    release_module = _isolated_release_publication_module()
    scenario = _s8r5_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8c-runtime",
    )
    source_plan = scenario["plan"]
    assert source_plan.release_binding is not None

    repository_root = Path(__file__).resolve().parents[4]
    evidence_root = (
        repository_root / ".agents" / "runs" / "rebuild-canonical-v2-knowledge-platform"
    )
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    original_milvus_sha256 = _file_sha256(original_milvus)
    target = isolated_index_module.prepare_isolated_index_target(
        root=tmp_path / "canonical-v2-s8c-runtime-index",
        target_id="canonical-v2-s8c-runtime-index",
        release_id=scenario["bundle"].release_id,
        backup_gate_root=evidence_root,
        forbidden_milvus_paths=(original_milvus,),
    )
    build_embedding = isolated_index_module.RecordedEmbeddingAdapter(
        model_id="recorded-embedding-v1",
        dimension=32,
    )
    physical_result = isolated_index_module.create_isolated_index_projection_builder(
        target=target,
        backup_gate_root=evidence_root,
        embedding_adapter=build_embedding,
        clock=lambda: NOW,
    ).build(scenario["index_request"])
    assert physical_result == scenario["bundle"].index_result
    bundle = release_module.IsolatedReleaseBundle(
        manifest=scenario["bundle"].manifest,
        index_result=physical_result,
        index_target=target,
        relationship_projection_request=(
            scenario["bundle"].relationship_projection_request
        ),
        relationship_projection_result=(
            scenario["bundle"].relationship_projection_result
        ),
    )

    supported_part = read_module.MaterialQuestionPart(
        part_id="material-part:s8c-patent-applicant",
        text="确认已展示专利的申请人企业",
        subject_id="canonical:patent:patent-ada",
        predicate="patent_has_applicant",
        requested_value="canonical:company:company-robotics",
    )
    missing_part = read_module.MaterialQuestionPart(
        part_id="material-part:s8c-current-revenue",
        text="核实该企业 2026 年当前营收",
        subject_id="canonical:company:company-robotics",
        predicate="current_revenue",
        requested_value="2026",
    )
    all_lanes = (
        "exact",
        "structured",
        "lexical",
        "vector",
        "relationship",
        "internal_reference",
        "web",
    )
    planning_policy = read_module.QueryPlanningPolicy(
        policy_id="planning-policy:s8c-release-bound",
        policy_version="query-planning-policy-v1",
        public_domains=PUBLIC_DOMAINS,
        supported_lanes=all_lanes,
        supported_relationship_paths=(("company_has_patent", "patent_to_company"),),
        max_candidates=20,
        max_provider_calls=2,
        max_planning_attempts=1,
    )
    planning_request = read_module.QueryPlanningRequest(
        request_id="query-request:s8c-release-bound",
        release_id=bundle.release_id,
        original_query=(
            "列出已展示专利中有证据记载为申请人的代表性企业，并核对SUSTech毕业且"
            "担任首席科学家的人"
        ),
        as_of=NOW,
        displayed_entity_ids=("patent-ada",),
        enumeration_context=read_module.EnumerationPlanningContext(
            requested=True,
            scope=S8R5_SCOPE,
            as_of=NOW,
            finite_universe=None,
            required_member_ids=(),
        ),
    )

    def proposal_provider(value: Any) -> Any:
        assert value == planning_request
        return read_module.RecordedPlanningProposal(
            proposal_id="planning-proposal:s8c-release-bound",
            request_sha256=value.content_sha256,
            schema_version="retrieval-plan-proposal-v1",
            model_id="recorded-planner-s8c",
            prompt_version="query-plan-prompt-v1",
            behavior_class="E",
            interaction_mode="information_retrieval",
            domains=("company",),
            lanes=all_lanes,
            relationship_paths=(
                read_module.RelationshipPathProposal(
                    relationship_type_id="company_has_patent",
                    direction="patent_to_company",
                    source_type="patent",
                    target_type="company",
                ),
            ),
            material_parts=(supported_part, missing_part),
            max_candidates=20,
            max_provider_calls=1,
            enumeration_mode="representative",
            internal_reference_targets=("person",),
            web_mode="universal",
            max_web_results=5,
        )

    plan = isolated_read_module.create_isolated_release_query_planner(
        release_bundle=bundle,
        published_release=scenario["published"],
        index_projection_request=scenario["index_request"],
        release_institution_catalog=scenario["catalog"],
        planning_policy=planning_policy,
        proposal_provider=proposal_provider,
    ).plan(planning_request)
    assert len(plan.internal_reference_queries) == 1
    person_query = plan.internal_reference_queries[0]
    assert len(person_query.eligible_reference_ids) == 1
    assert person_query.nonmatching_reference_traces == ()
    assert person_query.unresolved_reference_traces == ()
    nonmatching_person_id = person_query.eligible_reference_ids[0]
    nonmatching_person_query = person_query.model_copy(
        update={
            "typed_filters": (
                *(
                    read_module.InternalReferenceFact(
                        field=fact.field,
                        value=fact.value,
                        evidence_ids=(),
                    )
                    for fact in person_query.typed_filters
                ),
                read_module.InternalReferenceFact(
                    field="company_role",
                    value="chief_scientist",
                    evidence_ids=(),
                ),
            ),
            "eligible_reference_ids": (),
            "excluded_reference_ids": (nonmatching_person_id,),
            "originating_public_evidence_ids": (),
            "nonmatching_reference_traces": (
                read_module.ReferenceTrace(
                    reference_id=nonmatching_person_id,
                    resolution_state="resolved",
                    failed_filter_fields=("company_role",),
                    evidence_ids=person_query.originating_public_evidence_ids,
                ),
            ),
        }
    )
    plan = read_module.RetrievalPlan.model_validate(
        {
            **plan.model_dump(mode="json", exclude={"content_sha256"}),
            "internal_reference_queries": (
                nonmatching_person_query.model_dump(mode="json"),
            ),
            "supplemental_budget": read_module.SupplementalBudget(
                max_wall_time_ms=1_000,
                max_provider_calls=2,
                max_retries=1,
                max_cost_units=5.0,
            ).model_dump(mode="json"),
        }
    )
    assert plan.lanes == all_lanes
    assert plan.release_binding is not None
    assert plan.structured_constraints.displayed_entity_ids == ("patent-ada",)
    assert tuple(slot.kind for slot in plan.protected_slots) == (
        "displayed_entity_set",
    )
    assert tuple(
        slot.entity_ids
        for slot in plan.protected_slots
        if slot.kind == "displayed_entity_set"
    ) == (("patent-ada",),)
    assert plan.relationship_paths == source_plan.relationship_paths
    assert plan.enumeration_policy == source_plan.enumeration_policy
    assert tuple(query.reference_type for query in plan.internal_reference_queries) == (
        "person",
    )
    assert plan.internal_reference_queries[0].eligible_reference_ids == ()

    session_id = "session:s8c-release-bound"
    retained_payload = b"Recorded S8C Web-only Company snapshot."
    retained_digest = hashlib.sha256(retained_payload).hexdigest()
    retained_snapshot_id = f"web-snapshot:s8c:sha256:{retained_digest}"
    retained_handle = read_module.WebEntityHandle(
        handle_id=f"web-handle:s8c:sha256:{retained_digest}",
        domain="company",
        display_name="Recorded Web Company",
        evidence_snapshot_ids=(retained_snapshot_id,),
        evidence_ids=("evidence:web:s8c:recorded-company",),
        resolution_state="unresolved",
        candidate_canonical_ids=(),
        originating_query="Recorded S8RF handle fixture",
        origin_lane="web",
        origin_attempt=1,
        session_id=session_id,
        expires_at=NOW + timedelta(hours=1),
    )
    replay = read_module.WebHandleReplay(
        handle=retained_handle,
        snapshot_payloads=(
            read_module.WebSnapshotPayload(
                snapshot_id=retained_snapshot_id,
                content=retained_payload,
            ),
        ),
        observed_live_content_sha256=retained_digest,
        replayed_at=NOW,
    )
    replay_plan = read_module.RetrievalPlan(
        plan_id="retrieval-plan:s8c-release-bound-handle-replay",
        plan_version=source_plan.plan_version,
        request_sha256=source_plan.request_sha256,
        original_query="继续查看已保留的 Web Company",
        behavior_class="A",
        interaction_mode="handle_replay",
        release_id=bundle.release_id,
        as_of=NOW,
        domains=("company",),
        protected_slots=(),
        lanes=(),
        max_candidates=1,
        web_required=False,
        web_policy=read_module.WebSearchPolicy(mode="disabled"),
        freshness_material=False,
        retained_web_handles=(retained_handle,),
        web_handle_replays=(replay,),
        handle_operation="resolve_read_only",
        session_id=session_id,
        planning_trace=source_plan.planning_trace,
        release_binding=source_plan.release_binding,
    )

    fusion_requests: list[Any] = []
    rerank_requests: list[Any] = []
    sufficiency_requests: list[Any] = []
    supplemental_requests: list[Any] = []
    resolver_requests: list[Any] = []
    lookup_requests: list[Any] = []
    web_requests: list[Any] = []
    callback_lists = (
        fusion_requests,
        rerank_requests,
        sufficiency_requests,
        supplemental_requests,
        resolver_requests,
        lookup_requests,
        web_requests,
    )

    ttl_probe_calls: list[Any] = []

    def unexpected_ttl_probe_callback(value: Any) -> Any:
        ttl_probe_calls.append(value)
        raise AssertionError("negative TTL validation must precede callback effects")

    with pytest.raises(ValueError, match="web_handle_ttl must be non-negative"):
        release_factory(
            release_bundle=bundle,
            published_release=scenario["published"],
            universal_web_policy=plan.web_policy,
            web_search=unexpected_ttl_probe_callback,
            web_snapshot_policy=read_module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8c-negative-ttl",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
            identity_fuser=unexpected_ttl_probe_callback,
            reranker=unexpected_ttl_probe_callback,
            sufficiency_decider=unexpected_ttl_probe_callback,
            supplemental_search=unexpected_ttl_probe_callback,
            web_handle_resolver=unexpected_ttl_probe_callback,
            accepted_identity_lookup=unexpected_ttl_probe_callback,
            web_handle_ttl=timedelta(microseconds=-1),
            clock=lambda: NOW,
        )
    assert ttl_probe_calls == []

    replay_json = replay_plan.model_dump(mode="json", exclude={"content_sha256"})
    cross_session_handle = retained_handle.model_copy(
        update={"session_id": "session:s8c-cross-wired"}
    )
    cross_session_replay = replay.model_copy(update={"handle": cross_session_handle})
    invalid_replay_updates = (
        {"lanes": ("web",)},
        {
            "web_policy": read_module.WebSearchPolicy(
                mode="universal",
                max_provider_calls=1,
                timeout_ms=1_000,
                max_results=1,
            ).model_dump(mode="json")
        },
        {"freshness_material": True},
        {
            "assessment_intent": read_module.AssessmentIntent(
                kind="forbidden_replay_assessment"
            ).model_dump(mode="json")
        },
        {"material_parts": (missing_part.model_dump(mode="json"),)},
        {"session_id": ""},
        {"retained_web_handles": (cross_session_handle.model_dump(mode="json"),)},
        {"web_handle_replays": (cross_session_replay.model_dump(mode="json"),)},
        {"release_binding": None},
    )
    for updates in invalid_replay_updates:
        with pytest.raises(ValidationError):
            read_module.RetrievalPlan.model_validate(
                {
                    **replay_json,
                    **updates,
                }
            )
    assert all(not calls for calls in callback_lists)

    overlap = Barrier(2)
    overlapping_lanes: list[str] = []
    real_exact_factory = isolated_read_module.create_isolated_exact_lookup_adapter
    real_lexical_factory = isolated_read_module.create_isolated_lexical_lookup_adapter

    def overlapping_factory(
        lane: str,
        factory: Callable[..., Any],
    ) -> Callable[..., Any]:
        def create(**kwargs: Any) -> Any:
            adapter = factory(**kwargs)

            def invoke(value: Any) -> Any:
                overlapping_lanes.append(lane)
                overlap.wait(timeout=5)
                return adapter(value)

            return invoke

        return create

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_exact_lookup_adapter",
        overlapping_factory("exact", real_exact_factory),
    )
    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_lexical_lookup_adapter",
        overlapping_factory("lexical", real_lexical_factory),
    )

    web_payload = b"Recorded current-Web corroboration for Robotics Co."
    web_digest = hashlib.sha256(web_payload).hexdigest()
    web_snapshot = read_module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:s8c:corroboration:sha256:{web_digest}",
        content_sha256=web_digest,
        retrieved_at=NOW,
        byte_length=len(web_payload),
    )
    web_object_id = "web-object:s8c:company-robotics"
    web_evidence = read_module.EvidenceItem(
        evidence_id="evidence:web:s8c:company-robotics",
        object_id=web_object_id,
        domain="company",
        lane="web",
        source_nature="current_web",
        source_locator="https://current.example/s8c/robotics-co",
        snippet=web_payload.decode(),
        score=0.75,
        claim_binding=read_module.EvidenceClaimBinding(
            subject_id="canonical:company:company-robotics",
            predicate="display_name",
            value="Robotics Co",
            status="accepted",
        ),
        web_snapshot=web_snapshot,
    )

    def web_search(value: Any) -> Any:
        web_requests.append(value)
        return read_module.RetrievalLaneResult(
            candidates=(
                read_module.RecallCandidate(
                    raw_candidate_id="raw:web:s8c:company-robotics",
                    display_name="Robotics Co",
                    domain="company",
                    identity_kind="web_candidate",
                    canonical_id="company-robotics",
                    resolution_state="resolved",
                    query_view=value.query_view,
                    lane="web",
                    attempt=1,
                    release_id=value.release_id,
                    adapter_version="s8c-web-fixture-v1",
                    provider_version="s8c-web-provider-v1",
                    raw_score=0.75,
                    evidence=(web_evidence,),
                ),
            ),
            web_snapshot_payloads=(
                read_module.WebSnapshotPayload(
                    snapshot_id=web_snapshot.snapshot_id,
                    content=web_payload,
                ),
            ),
        )

    fusion_evidence_ids: list[tuple[str, ...]] = []

    def identity_fuser(value: Any) -> Any:
        fusion_requests.append(value)
        grouped: dict[str, list[Any]] = {}
        for candidate in value.candidates:
            assert candidate.canonical_id is not None
            grouped.setdefault(candidate.canonical_id, []).append(candidate)
        groups = []
        for canonical_id, candidates in grouped.items():
            evidence_ids = tuple(
                dict.fromkeys(
                    item.evidence_id
                    for candidate in candidates
                    for item in candidate.evidence
                )
            )
            fusion_evidence_ids.append(evidence_ids)
            groups.append(
                read_module.IdentityFusionGroup(
                    canonical_id=canonical_id,
                    raw_candidate_ids=tuple(
                        candidate.raw_candidate_id for candidate in candidates
                    ),
                    evidence_ids=evidence_ids,
                    confidence=1.0,
                    rationale="Accepted Canonical IDs bind the same release identity.",
                )
            )
        return read_module.IdentityFusionProposal(
            decision_input_sha256=value.content_sha256,
            schema_version="identity-fusion-v1",
            model_id="recorded-identity-fuser-s8c",
            prompt_version="identity-fusion-prompt-v1",
            groups=tuple(groups),
        )

    def reranker(value: Any) -> Any:
        rerank_requests.append(value)
        selected = next(
            candidate
            for candidate in value.eligible_candidates
            if candidate.canonical_id == "company-robotics"
        )
        return read_module.RerankProposal(
            decision_input_sha256=value.content_sha256,
            schema_version="late-rerank-v1",
            model_id="recorded-reranker-s8c",
            prompt_version="late-rerank-prompt-v1",
            ordered_result_ids=(selected.result_id,),
            rationale="Select only the existing evidence-backed applicant Company.",
        )

    supported_evidence_ids: list[str] = []

    def sufficiency_decider(value: Any) -> Any:
        sufficiency_requests.append(value)
        supporting = tuple(
            item.evidence_id
            for item in value.evidence
            if item.claim_binding is not None
            and item.claim_binding.subject_id == supported_part.subject_id
            and item.claim_binding.predicate == supported_part.predicate
            and item.claim_binding.value == supported_part.requested_value
        )
        assert len(supporting) == 1
        supported_evidence_ids[:] = supporting
        return read_module.SufficiencyProposal(
            decision_input_sha256=value.content_sha256,
            schema_version="sufficiency-v1",
            decision_id="sufficiency:s8c-release-bound",
            parts=(
                read_module.MaterialPartProposal(
                    part_id=supported_part.part_id,
                    outcome="supported",
                    evidence_ids=supporting,
                    rationale="Accepted Patent-applicant evidence directly binds the claim.",
                    uncertainty="low",
                    confidence=1.0,
                ),
                read_module.MaterialPartProposal(
                    part_id=missing_part.part_id,
                    outcome="missing",
                    evidence_ids=(),
                    rationale="No retained evidence establishes current revenue.",
                    uncertainty="high",
                    confidence=0.0,
                ),
            ),
        )

    def supplemental_search(value: Any) -> Any:
        supplemental_requests.append(value)
        assert value.material_part_ids == (missing_part.part_id,)
        assert value.query_view == missing_part.text
        return read_module.SupplementalLaneResult(
            items=(),
            elapsed_ms=1,
            cost_units=0.1,
            retryable=False,
        )

    accepted_identity_evidence_ids = tuple(
        scenario["published"].verification_evidence_ids
    )

    def web_handle_resolver(value: Any) -> Any:
        resolver_requests.append(value)
        assert value.handle == retained_handle
        assert value.accepted_release_id == bundle.release_id
        assert value.evidence_snapshot_ids == (retained_snapshot_id,)
        return read_module.WebHandleResolutionProposal(
            decision_input_sha256=value.content_sha256,
            schema_version="web-handle-resolution-v1",
            handle_id=retained_handle.handle_id,
            accepted_release_id=bundle.release_id,
            canonical_id="company-robotics",
            canonical_evidence_ids=accepted_identity_evidence_ids,
            retained_snapshot_ids=(retained_snapshot_id,),
            resolution_state="resolved",
            rationale="Accepted release evidence resolves the retained Company handle.",
        )

    def accepted_identity_lookup(value: Any) -> Any:
        lookup_requests.append(value)
        assert value.release_id == bundle.release_id
        assert value.canonical_id == "company-robotics"
        return read_module.AcceptedIdentityLookupResult(
            release_id=bundle.release_id,
            canonical_id="company-robotics",
            accepted=True,
            evidence_ids=accepted_identity_evidence_ids,
        )

    target_hashes_before = {
        name: _file_sha256(target.root / name)
        for name in (
            ".canonical-v2-isolated-index-target.json",
            "lookup.sqlite3",
            "milvus.db",
        )
    }
    active_release_pointer = {
        "canonical": scenario["published"].canonical_release_id,
        "published": scenario["published"].published_projection_release_id,
        "index": scenario["published"].index_release_id,
    }
    active_release_pointer_before = dict(active_release_pointer)
    source_inventory_before = tuple(
        item.model_dump_json() for item in scenario["authority"]
    )
    published_before = scenario["published"].model_dump_json()

    service = release_factory(
        release_bundle=bundle,
        published_release=scenario["published"],
        index_projection_request=scenario["index_request"],
        release_institution_catalog=scenario["catalog"],
        embedding_adapter=isolated_index_module.RecordedEmbeddingAdapter(
            model_id="recorded-embedding-v1",
            dimension=32,
        ),
        universal_web_policy=plan.web_policy,
        web_search=web_search,
        web_snapshot_policy=read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8c",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        identity_fuser=identity_fuser,
        reranker=reranker,
        sufficiency_decider=sufficiency_decider,
        supplemental_search=supplemental_search,
        web_handle_resolver=web_handle_resolver,
        accepted_identity_lookup=accepted_identity_lookup,
        web_handle_ttl=timedelta(hours=1),
        clock=lambda: NOW,
    )
    evidence_set = service.execute(plan)

    initial_traces = tuple(
        trace for trace in evidence_set.traces if trace.phase == "initial"
    )
    assert {trace.lane for trace in initial_traces} == set(all_lanes)
    assert all(trace.status == "succeeded" for trace in initial_traces)
    internal_trace = next(
        trace for trace in initial_traces if trace.lane == "internal_reference"
    )
    assert internal_trace.candidate_count == 0
    assert sorted(overlapping_lanes) == ["exact", "lexical"]
    assert len(web_requests) == 1
    assert web_requests[0].release_id == bundle.release_id
    assert evidence_set.snapshot_receipts == (
        read_module.SnapshotReceipt(
            snapshot_id=web_snapshot.snapshot_id,
            status="accepted",
            observed_byte_length=len(web_payload),
        ),
    )
    assert {item.source_nature for item in evidence_set.items} >= {
        "local",
        "current_web",
    }
    assert fusion_requests and fusion_requests[0].release_id == bundle.release_id
    assert evidence_set.fusion_receipt is not None
    assert evidence_set.fusion_receipt.mode == "recorded_structured"
    assert evidence_set.fusion_receipt.decision_input_sha256 == (
        fusion_requests[0].content_sha256
    )
    assert len(rerank_requests) == 1
    assert evidence_set.rerank_receipt is not None
    assert evidence_set.rerank_receipt.mode == "recorded_structured"
    assert evidence_set.rerank_receipt.decision_input_sha256 == (
        rerank_requests[0].content_sha256
    )
    selected = next(
        candidate
        for candidate in evidence_set.fused_candidates
        if candidate.canonical_id == "company-robotics"
    )
    assert set(selected.evidence_ids) == set(
        evidence_id
        for group_evidence_ids in fusion_evidence_ids
        for evidence_id in group_evidence_ids
    )
    assert any(
        receipt.outcome == "accepted"
        and set(receipt.raw_candidate_ids) == set(selected.raw_candidate_ids)
        and set(receipt.aggregated_evidence_ids) == set(selected.evidence_ids)
        for receipt in evidence_set.constraint_receipts
    )
    assert evidence_set.candidate_traces
    assert all(
        trace.release_id == bundle.release_id
        and trace.lane in all_lanes
        and trace.attempt == 1
        and trace.evidence_ids
        for trace in evidence_set.candidate_traces
    )
    coverage = evidence_set.enumeration_coverage
    assert coverage is not None
    assert coverage.mode == "representative"
    assert coverage.scope == S8R5_SCOPE
    assert coverage.exhaustive is False
    assert coverage.accounting_complete is True
    assert coverage.continuation_required is True
    assert len(sufficiency_requests) == 1
    assert sufficiency_requests[0].plan_id == plan.plan_id
    assert sufficiency_requests[0].release_id == bundle.release_id
    assert evidence_set.sufficiency_report is not None
    sufficiency_by_part = {
        part.part_id: part for part in evidence_set.sufficiency_report.parts
    }
    assert sufficiency_by_part[supported_part.part_id].outcome == "supported"
    assert sufficiency_by_part[missing_part.part_id].outcome == "missing"
    assert len(supplemental_requests) == 1
    assert evidence_set.supplemental_budget_receipt is not None
    assert evidence_set.supplemental_budget_receipt.exhausted is False
    assert evidence_set.supplemental_budget_receipt.provider_calls == 1
    assert evidence_set.continuation_reasons == ("evidence_gap",)
    assert supported_evidence_ids
    assert set(supported_evidence_ids) <= {
        item.evidence_id for item in evidence_set.items
    }

    retained_handle_before = retained_handle.model_dump(mode="json")
    replay_result = service.execute(replay_plan)
    assert len(resolver_requests) == 1
    assert len(lookup_requests) == 1
    assert replay_result.handle_replay_receipts == (
        read_module.HandleReplayReceipt(
            handle_id=retained_handle.handle_id,
            status="accepted",
            accepted_snapshot_sha256=retained_digest,
            observed_live_content_sha256=retained_digest,
            continuity_established=True,
        ),
    )
    assert len(replay_result.handle_resolution_receipts) == 1
    resolution_receipt = replay_result.handle_resolution_receipts[0]
    assert resolution_receipt.status == "accepted"
    assert resolution_receipt.accepted_release_id == bundle.release_id
    assert resolution_receipt.canonical_id == "company-robotics"
    assert resolution_receipt.retained_snapshot_ids == (retained_snapshot_id,)
    assert resolution_receipt.read_only is True
    assert resolution_receipt.canonical_mutation_count == 0
    assert resolution_receipt.index_mutation_count == 0
    assert resolution_receipt.source_mapping_mutation_count == 0
    assert replay_result.entity_handles[0].handle_id == retained_handle.handle_id
    assert replay_result.entity_handles[0].resolution_state == "resolved"
    assert replay_result.entity_handles[0].candidate_canonical_ids == (
        "company-robotics",
    )
    assert retained_handle.model_dump(mode="json") == retained_handle_before

    assert {
        name: _file_sha256(target.root / name) for name in target_hashes_before
    } == target_hashes_before
    assert _file_sha256(original_milvus) == original_milvus_sha256
    assert active_release_pointer == active_release_pointer_before
    assert tuple(item.model_dump_json() for item in scenario["authority"]) == (
        source_inventory_before
    )
    assert scenario["published"].model_dump_json() == published_before


def test_s8r3_executes_release_scoped_professor_to_paper_attribution_traversal(
    request: pytest.FixtureRequest,
) -> None:
    read_module, relationship_factory, release_factory = (
        _s8r3_public_relationship_contract()
    )
    tmp_path: Path = request.getfixturevalue("tmp_path")
    monkeypatch: pytest.MonkeyPatch = request.getfixturevalue("monkeypatch")
    isolated_read_module = _isolated_knowledge_read_module()
    index_module = _index_projection_module()

    release_id = "candidate-s8r3-professor-paper"
    positive = _s8r3_scenario(
        tmp_path=tmp_path,
        release_id=release_id,
    )
    authority = positive["authority"]
    index_request = positive["index_request"]
    bundle = positive["bundle"]
    published = positive["published"]
    catalog = positive["catalog"]
    plan = positive["plan"]
    assert (
        index_module.create_ephemeral_index_projection_builder().build(index_request)
        == bundle.index_result
    )
    assert plan.domains == ("paper",)
    assert plan.lanes == ("relationship", "web")
    assert plan.relationship_paths == (
        read_module.RelationshipPathProposal(
            relationship_type_id="professor_authored_paper",
            direction="professor_to_paper",
            source_type="professor",
            target_type="paper",
        ),
    )
    assert plan.structured_constraints.displayed_entity_ids == ("professor-ada",)
    assert tuple(
        slot.entity_ids
        for slot in plan.protected_slots
        if slot.kind == "displayed_entity_set"
    ) == (("professor-ada",),)
    assert plan.internal_reference_queries == ()
    assert plan.enumeration_policy is not None
    assert plan.enumeration_policy.mode == "representative"
    assert plan.enumeration_policy.scope == S8R3_SCOPE
    assert plan.enumeration_policy.as_of == NOW
    assert plan.enumeration_policy.finite_universe_id is None
    assert plan.enumeration_policy.eligible_member_ids == ()
    assert plan.enumeration_policy.required_member_ids == ()
    assert plan.enumeration_policy.exhaustive is False
    assert plan.enumeration_policy.continuation_state == "available"

    captured_relationship_requests: list[Any] = []
    captured_relationship_results: list[Any] = []
    captured_web_requests: list[Any] = []
    real_relationship_factory = relationship_factory

    def capturing_relationship_factory(**kwargs: Any) -> Any:
        adapter = real_relationship_factory(**kwargs)

        def captured_adapter(value: Any) -> Any:
            captured_relationship_requests.append(value)
            result = adapter(value)
            captured_relationship_results.append(result)
            return result

        return captured_adapter

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        capturing_relationship_factory,
    )
    physical_reads: list[Any] = []

    def forbidden_physical_read(value: Any) -> Any:
        physical_reads.append(value)
        raise AssertionError("S8R3 relationship traversal must remain in memory")

    monkeypatch.setattr(
        isolated_read_module,
        "_read_bound_documents",
        forbidden_physical_read,
    )
    service_kwargs = {
        "release_bundle": bundle,
        "published_release": published,
        "index_projection_request": index_request,
        "release_institution_catalog": catalog,
        "universal_web_policy": plan.web_policy,
        "web_search": lambda value: (
            captured_web_requests.append(value) or read_module.RetrievalLaneResult()
        ),
        "web_snapshot_policy": read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s8r3",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        "clock": lambda: NOW,
    }
    evidence_set = release_factory(**service_kwargs).execute(plan)

    assert evidence_set.requested_traversal == read_module.TypedTraversalRequest(
        path_id="professor_to_paper",
        source_domain="professor",
        target_domain="paper",
        relationship_type="professor_attributed_to_paper",
        direction="forward",
    )
    assert physical_reads == []
    assert len(captured_relationship_requests) == 1
    relationship_request = captured_relationship_requests[0]
    assert relationship_request.domains == ("paper",)
    assert relationship_request.relationship_paths == plan.relationship_paths
    assert relationship_request.relationship_reference_queries == ()
    assert relationship_request.relationship_enumeration_policy == (
        plan.enumeration_policy
    )
    assert relationship_request.structured_constraints.displayed_entity_ids == (
        "professor-ada",
    )
    assert len(captured_web_requests) == 1
    assert captured_web_requests[0].relationship_paths == ()
    assert captured_web_requests[0].relationship_enumeration_policy is None

    assert len(captured_relationship_results) == 1
    raw_result = captured_relationship_results[0]
    assert len(raw_result.candidates) == 1
    candidate = raw_result.candidates[0]
    assert candidate.domain == "paper"
    assert candidate.canonical_id == "paper-ada"
    assert candidate.display_name == "Evidence-bound robotics"
    assert candidate.reference_type is None
    assert candidate.identity_kind == "canonical"
    assert candidate.resolution_state == "resolved"
    assert candidate.relationship_state == "accepted"
    assert candidate.origin_public_evidence_ids == (
        "relationship-assertion:professor-paper:ada",
    )
    assert candidate.quality_flags == ()
    assert len(candidate.evidence) == 1
    item = candidate.evidence[0]
    trace = item.local_projection_trace
    assert isinstance(trace, read_module.LocalProfessorPaperRelationshipTrace)
    assert trace.displayed_professor_id == "professor-ada"
    assert trace.professor_stable_reference == "canonical:professor:professor-ada"
    assert trace.paper_id == "paper-ada"
    assert trace.paper_stable_reference == "canonical:paper:paper-ada"
    assert trace.canonical_relationship_id == "relationship:professor-paper:ada"
    assert trace.relationship_type_id == "professor_attributed_to_paper"
    assert trace.relationship_role_bindings == ()
    assert trace.relationship_effective_time_semantics == "observed_at"
    assert trace.relationship_evidence_kind == (
        "professor_page_or_identity_attribution_assertion"
    )
    assert trace.professor_traversal_directions == ("professor_to_paper",)
    assert trace.paper_traversal_directions == ("paper_to_professor",)
    assert trace.paper_domain_identity_status == "confirmed"
    assert trace.query_as_of == trace.relationship_snapshot_as_of == NOW
    assert trace.lane_request_content_sha256 == relationship_request.content_sha256

    relationship_request_authority = authority[2]
    relationship_result_authority = authority[3]
    projection_candidate = relationship_request_authority.candidates[0]
    shared_assertion = relationship_request_authority.relationship_assertions[0]
    assignments = {
        assignment.entity_type: assignment
        for assignment in relationship_request_authority.source_canonical_assignments
    }
    decision_input = relationship_request_authority.decision_inputs[0]
    retained_reference = relationship_request_authority.retained_assertions[0]
    candidate_outcome = relationship_result_authority.candidate_outcomes[0]
    relationship_decision = relationship_result_authority.relationship_decisions[0]
    current_relationship = relationship_result_authority.current_relationships[0]
    professor_projection = next(
        projection
        for projection in authority[1].public_domain_projections
        if projection.entity_type == "professor"
        if projection.canonical_identity_id == "professor-ada"
    )
    paper_projection = next(
        projection
        for projection in authority[1].public_domain_projections
        if projection.entity_type == "paper"
        if projection.canonical_identity_id == "paper-ada"
    )
    path_pairs = {
        result.subject_identity_id: (path_request, result)
        for path_request, result in zip(
            index_request.public_path_eligibility_requests,
            index_request.public_path_eligibility_results,
            strict=True,
        )
    }
    professor_path_request, professor_path_result = path_pairs["professor-ada"]
    paper_path_request, paper_path_result = path_pairs["paper-ada"]
    assert professor_path_request.projection is not None
    assert paper_path_request.projection is not None
    assert professor_path_request.projection.domain_identity_status is None
    assert paper_path_request.projection.domain_identity_status == "confirmed"
    assert trace.relationship_request_sha256 == _canonical_hash(
        relationship_request_authority.model_dump(mode="json")
    )
    assert trace.relationship_result_sha256 == (
        relationship_result_authority.content_sha256
    )
    assert trace.current_relationship_content_sha256 == _canonical_hash(
        current_relationship.model_dump(mode="json")
    )
    assert trace.projection_candidate_id == projection_candidate.candidate_id
    assert trace.projection_candidate_content_sha256 == _canonical_hash(
        projection_candidate.model_dump(mode="json")
    )
    assert trace.projection_candidate_evidence_metadata == (
        projection_candidate.evidence_metadata
    )
    assert trace.shared_assertion_id == shared_assertion.assertion_id
    assert trace.shared_assertion_content_sha256 == _canonical_hash(
        shared_assertion.model_dump(mode="json")
    )
    assert trace.source_assignment_id == assignments["professor"].assignment_id
    assert trace.target_assignment_id == assignments["paper"].assignment_id
    assert trace.relationship_decision_input_id == decision_input.decision_input_id
    assert trace.candidate_outcome_candidate_id == candidate_outcome.candidate_id
    assert trace.candidate_outcome_content_sha256 == _canonical_hash(
        candidate_outcome.model_dump(mode="json")
    )
    assert trace.relationship_decision_id == relationship_decision.decision_id
    assert trace.relationship_decision_content_sha256 == _canonical_hash(
        relationship_decision.model_dump(mode="json")
    )
    assert trace.retained_reference_id == retained_reference.reference_id
    assert trace.retained_reference_content_sha256 == _canonical_hash(
        retained_reference.model_dump(mode="json")
    )
    assert trace.professor_projection_content_sha256 == (
        professor_projection.content_sha256
    )
    assert trace.paper_projection_content_sha256 == paper_projection.content_sha256
    assert trace.professor_path_result_content_sha256 == (
        professor_path_result.content_sha256
    )
    assert trace.paper_path_result_content_sha256 == (paper_path_result.content_sha256)
    assert item.object_id == "paper-ada"
    assert item.domain == "paper"
    assert item.lane == "relationship"
    assert item.source_nature == "local"
    assert item.source_authority == "canonical_release"
    assert item.claim_binding == read_module.EvidenceClaimBinding(
        subject_id="canonical:professor:professor-ada",
        predicate="professor_attributed_to_paper",
        value="canonical:paper:paper-ada",
        status="accepted",
    )
    assert item.snippet == json.dumps(
        shared_assertion.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    assert "professor_authored_paper" not in item.snippet
    assert "paper_has_author" not in item.snippet
    assert item.source_locator == (
        f"canonical-v2-isolated:{bundle.index_target.target_id}:"
        "relationship:professor-paper:ada"
    )
    assert item.observed_at == trace.relationship_snapshot_as_of

    assert len(evidence_set.fused_candidates) == 1
    fused = evidence_set.fused_candidates[0]
    assert fused.canonical_id == "paper-ada"
    assert fused.domain == "paper"
    assert fused.display_name == "Evidence-bound robotics"
    assert fused.quality_flags == ()
    assert evidence_set.entity_handles == (
        read_module.CanonicalEntityHandle(
            canonical_id="paper-ada",
            domain="paper",
            display_name="Evidence-bound robotics",
            evidence_ids=fused.evidence_ids,
        ),
    )
    coverage = evidence_set.enumeration_coverage
    assert coverage is not None
    assert coverage.mode == "representative"
    assert coverage.scope == S8R3_SCOPE
    assert coverage.as_of == NOW
    assert coverage.checked_ids == ("paper-ada",)
    assert coverage.eligible_ids == ("paper-ada",)
    assert coverage.retrieved_ids == ("paper-ada",)
    assert coverage.displayed_ids == ("paper-ada",)
    assert coverage.unknown_scope is True
    assert coverage.exhaustive is False
    assert coverage.continuation_state == "open_world"
    assert coverage.continuation_required is True

    direct_adapter = real_relationship_factory(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=catalog,
    )
    direct_request = isolated_read_module._lane_request(
        plan,
        "relationship",
        plan.web_policy,
    )
    assert len(direct_adapter(direct_request).candidates) == 1

    def direct_request_with(
        *,
        displayed_ids: tuple[str, ...] | None = None,
        protected_sets: tuple[tuple[str, ...], ...] | None = None,
        **updates: Any,
    ) -> Any:
        payload = direct_request.model_dump(mode="json", exclude={"content_sha256"})
        if displayed_ids is not None:
            payload["structured_constraints"]["displayed_entity_ids"] = list(
                displayed_ids
            )
        if protected_sets is not None:
            payload["protected_slots"] = [
                read_module.ProtectedSlot(
                    kind="displayed_entity_set",
                    value="displayed_entity_set",
                    entity_ids=values,
                ).model_dump(mode="json")
                for values in protected_sets
            ]
        payload.update(updates)
        return read_module.LaneRequest.model_validate(payload)

    assert direct_adapter(direct_request_with(max_candidates=0)).candidates == ()
    assert (
        direct_adapter(
            direct_request_with(displayed_ids=(), protected_sets=())
        ).candidates
        == ()
    )
    internal_person_id = authority[1].person_projections[0].canonical_person_identity_id

    replayed_authority = isolated_read_module._replay_relationship_authority(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=catalog,
    )
    relationship_projection_module = import_module(
        "src.data_agents.canonical_v2.relationship_projection"
    )

    def crosswired_authority(
        mutation: Callable[[dict[str, Any]], None],
    ) -> Any:
        request_payload = replayed_authority.relationship_request.model_dump(
            mode="json"
        )
        mutation(request_payload)
        changed_request = (
            relationship_projection_module.RelationshipProjectionRequest.model_validate(
                request_payload
            )
        )
        changed_result = relationship_projection_module.create_ephemeral_relationship_projection().project(
            changed_request
        )
        return isolated_read_module._RelationshipAuthority(
            internal_authority=replayed_authority.internal_authority,
            relationship_request=changed_request,
            relationship_result=changed_result,
            candidate_result=replayed_authority.candidate_result,
        )

    def crosswire_shared_source_type(payload: dict[str, Any]) -> None:
        payload["relationship_assertions"][0]["source_endpoint"]["entity_type"] = (
            "company"
        )

    def crosswire_retained_source_record(payload: dict[str, Any]) -> None:
        payload["retained_assertions"][0]["source_record_ref"] = (
            "record:professor:unrelated"
        )

    for mutation in (
        crosswire_shared_source_type,
        crosswire_retained_source_record,
    ):
        with pytest.raises(
            isolated_read_module.IsolatedKnowledgeReadIntegrityError,
            match="candidate/assertion/decision continuity differs",
        ):
            isolated_read_module._professor_to_paper_relationship_candidates(
                request=direct_request,
                authority=crosswired_authority(mutation),
            )

    for source_id in ("professor-unknown", "paper-ada", internal_person_id):
        assert (
            direct_adapter(
                direct_request_with(
                    displayed_ids=(source_id,),
                    protected_sets=((source_id,),),
                )
            ).candidates
            == ()
        )
    invalid_direct_requests = (
        direct_request_with(
            displayed_ids=("professor-ada", "professor-other"),
            protected_sets=(("professor-ada", "professor-other"),),
        ),
        direct_request_with(protected_sets=()),
        direct_request_with(protected_sets=(("professor-other",),)),
        direct_request_with(protected_sets=(("professor-ada",), ("professor-ada",))),
        direct_request_with(release_id="cross-release-s8r3"),
        direct_request_with(relationship_enumeration_policy=None),
    )
    for invalid_request in invalid_direct_requests:
        with pytest.raises(
            (ValueError, isolated_read_module.IsolatedKnowledgeReadIntegrityError)
        ):
            direct_adapter(invalid_request)

    exhaustive_policy = plan.enumeration_policy.model_copy(
        update={"mode": "exhaustive_bounded", "exhaustive": True}
    )
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="enumeration",
    ):
        direct_adapter(
            direct_request_with(
                relationship_enumeration_policy=exhaustive_policy.model_dump(
                    mode="json"
                )
            )
        )

    def execute_scenario(
        value: dict[str, Any],
        *,
        plan_override: Any | None = None,
        web_calls: list[Any] | None = None,
    ) -> Any:
        calls = [] if web_calls is None else web_calls
        return release_factory(
            release_bundle=value["bundle"],
            published_release=value["published"],
            index_projection_request=value["index_request"],
            release_institution_catalog=value["catalog"],
            universal_web_policy=value["plan"].web_policy,
            web_search=lambda web_request: (
                calls.append(web_request) or read_module.RetrievalLaneResult()
            ),
            web_snapshot_policy=read_module.WebSnapshotPolicy(
                policy_id=f"web-snapshot-policy:{value['bundle'].release_id}",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
            clock=lambda: NOW,
        ).execute(plan_override or value["plan"])

    authoritative_zero = _s8r3_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r3-authoritative-zero",
        authoritative_zero=True,
    )
    zero_web_calls: list[Any] = []
    zero_result = execute_scenario(
        authoritative_zero,
        web_calls=zero_web_calls,
    )
    assert authoritative_zero["authority"][1].person_projections
    assert any(
        projection.entity_type == "paper"
        for projection in authoritative_zero["authority"][1].public_domain_projections
    )
    assert authoritative_zero["authority"][3].current_relationships == ()
    assert zero_result.fused_candidates == ()
    assert len(zero_web_calls) == 1

    rejected = _s8r3_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r3-rejected-attribution",
        decision_state="rejected",
    )
    assert any(
        projection.entity_type == "paper"
        and projection.canonical_identity_id == "paper-ada"
        for projection in rejected["authority"][1].public_domain_projections
    )
    assert execute_scenario(rejected).fused_candidates == ()

    nonmatching = _s8r3_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r3-nonmatching-current-relation",
        nonmatching_relationship_authority=True,
    )
    assert execute_scenario(nonmatching).fused_candidates == ()

    max_zero_payload = plan.model_dump(mode="json", exclude={"content_sha256"})
    max_zero_payload["max_candidates"] = 0
    max_zero_plan = read_module.RetrievalPlan.model_validate(max_zero_payload)
    assert (
        execute_scenario(
            positive,
            plan_override=max_zero_plan,
        ).fused_candidates
        == ()
    )

    def plan_with_source(
        source_ids: tuple[str, ...],
        *,
        protected_sets: tuple[tuple[str, ...], ...] | None = None,
    ) -> Any:
        payload = plan.model_dump(mode="json", exclude={"content_sha256"})
        payload["structured_constraints"]["displayed_entity_ids"] = list(source_ids)
        effective_sets = protected_sets if protected_sets is not None else (source_ids,)
        payload["protected_slots"] = [
            read_module.ProtectedSlot(
                kind="displayed_entity_set",
                value="displayed_entity_set",
                entity_ids=values,
            ).model_dump(mode="json")
            for values in effective_sets
        ]
        return read_module.RetrievalPlan.model_validate(payload)

    unknown_web_calls: list[Any] = []
    unknown_result = execute_scenario(
        positive,
        plan_override=plan_with_source(("professor-unknown",)),
        web_calls=unknown_web_calls,
    )
    assert unknown_result.fused_candidates == ()
    assert len(unknown_web_calls) == 1

    invalid_source_plans = (
        plan_with_source(()),
        plan_with_source(("",)),
        plan_with_source(("professor-ada", "professor-other")),
        plan_with_source(("paper-ada",)),
        plan_with_source((internal_person_id,)),
        plan_with_source(("professor-ada",), protected_sets=()),
        plan_with_source(
            ("professor-ada",),
            protected_sets=(("professor-ada",), ("professor-ada",)),
        ),
        plan_with_source(
            ("professor-ada",),
            protected_sets=(("professor-other",),),
        ),
    )
    for invalid_plan in invalid_source_plans:
        invalid_web_calls: list[Any] = []
        with pytest.raises(isolated_read_module.IsolatedKnowledgeReadIntegrityError):
            execute_scenario(
                positive,
                plan_override=invalid_plan,
                web_calls=invalid_web_calls,
            )
        assert invalid_web_calls == []

    wrong_path = read_module.RelationshipPathProposal(
        relationship_type_id="professor_authored_paper",
        direction="paper_to_professor",
        source_type="paper",
        target_type="professor",
    )
    exhaustive_enumeration = plan.enumeration_policy.model_copy(
        update={"mode": "exhaustive_bounded", "exhaustive": True}
    )
    invalid_request_payloads: list[dict[str, Any]] = []
    for updates in (
        {"relationship_paths": [wrong_path.model_dump(mode="json")]},
        {
            "relationship_paths": [
                plan.relationship_paths[0].model_dump(mode="json"),
                wrong_path.model_dump(mode="json"),
            ]
        },
        {
            "lanes": ["web"],
            "lane_queries": [
                query.model_dump(mode="json")
                for query in plan.lane_queries
                if query.lane == "web"
            ],
        },
        {"domains": ["professor"]},
        {"enumeration_policy": exhaustive_enumeration.model_dump(mode="json")},
    ):
        payload = plan.model_dump(mode="json", exclude={"content_sha256"})
        payload.update(updates)
        invalid_request_payloads.append(payload)
    for invalid_payload in invalid_request_payloads:
        invalid_plan = read_module.RetrievalPlan.model_validate(invalid_payload)
        invalid_web_calls = []
        with pytest.raises(isolated_read_module.IsolatedKnowledgeReadIntegrityError):
            execute_scenario(
                positive,
                plan_override=invalid_plan,
                web_calls=invalid_web_calls,
            )
        assert invalid_web_calls == []

    drifted_as_of_payload = plan.model_dump(mode="json", exclude={"content_sha256"})
    drifted_as_of_payload["as_of"] = (NOW + timedelta(days=1)).isoformat()
    drifted_as_of_plan = read_module.RetrievalPlan.model_validate(drifted_as_of_payload)
    drifted_web_calls: list[Any] = []
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="source/policy|as_of|plan",
    ):
        execute_scenario(
            positive,
            plan_override=drifted_as_of_plan,
            web_calls=drifted_web_calls,
        )
    assert drifted_web_calls == []

    for excluded_id in ("professor-ada", "paper-ada"):
        excluded = _s8r3_scenario(
            tmp_path=tmp_path,
            release_id=f"candidate-s8r3-excluded-{excluded_id}",
            excluded_endpoint_ids=(excluded_id,),
        )
        assert execute_scenario(excluded).fused_candidates == ()

    unverified = _s8r3_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r3-unverified-paper",
        paper_identity_status="unverified",
    )
    unverified_result = execute_scenario(unverified)
    assert len(unverified_result.fused_candidates) == 1
    assert unverified_result.fused_candidates[0].quality_flags == (
        "identity_unverified",
    )
    unverified_trace = unverified_result.items[0].local_projection_trace
    assert isinstance(
        unverified_trace,
        read_module.LocalProfessorPaperRelationshipTrace,
    )
    assert unverified_trace.paper_domain_identity_status == "unverified"

    limited = _s8r3_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r3-limited-endpoints",
        paper_identity_status="unverified",
        limited_endpoint_ids=("professor-ada", "paper-ada"),
    )
    limited_result = execute_scenario(limited)
    assert len(limited_result.fused_candidates) == 1
    assert limited_result.fused_candidates[0].quality_flags == (
        "identity_unverified",
        "s8r3_relationship_limited_paper-ada",
        "s8r3_relationship_limited_professor-ada",
    )

    multiple_refs = _s8r3_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r3-multiple-retained-refs",
        multiple_retained_refs=True,
    )
    assert len(multiple_refs["authority"][3].current_relationships) == 1
    assert (
        len(
            multiple_refs["authority"][3]
            .current_relationships[0]
            .selected_evidence_refs
        )
        == 2
    )
    multiple_refs_web_calls: list[Any] = []
    multiple_refs_result = execute_scenario(
        multiple_refs,
        web_calls=multiple_refs_web_calls,
    )
    assert multiple_refs_result.fused_candidates == ()
    assert len(multiple_refs_web_calls) == 1
    multiple_refs_coverage = multiple_refs_result.enumeration_coverage
    assert multiple_refs_coverage is not None
    assert multiple_refs_coverage.mode == "representative"
    assert multiple_refs_coverage.unknown_scope is True
    assert multiple_refs_coverage.exhaustive is False
    assert multiple_refs_coverage.continuation_state == "open_world"
    assert multiple_refs_coverage.continuation_required is True

    later = NOW + timedelta(days=1)
    later_scenario = _s8r3_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r3-later-query",
        as_of=later,
    )
    later_result = execute_scenario(later_scenario)
    assert len(later_result.fused_candidates) == 1
    assert later_result.fused_candidates[0].quality_flags == (S8R1_SNAPSHOT_FLAG,)
    later_trace = later_result.fused_candidates[0].evidence[0].local_projection_trace
    assert isinstance(later_trace, read_module.LocalProfessorPaperRelationshipTrace)
    assert later_trace.query_as_of == later
    assert later_trace.relationship_snapshot_as_of == NOW

    later_limited = _s8r3_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r3-later-unverified-limited",
        as_of=later,
        paper_identity_status="unverified",
        limited_endpoint_ids=("professor-ada", "paper-ada"),
    )
    later_limited_result = execute_scenario(later_limited)
    assert len(later_limited_result.fused_candidates) == 1
    assert later_limited_result.fused_candidates[0].quality_flags == tuple(
        sorted(
            (
                S8R1_SNAPSHOT_FLAG,
                "identity_unverified",
                "s8r3_relationship_limited_paper-ada",
                "s8r3_relationship_limited_professor-ada",
            )
        )
    )

    earlier_scenario = _s8r3_scenario(
        tmp_path=tmp_path,
        release_id="candidate-s8r3-earlier-query",
        as_of=NOW - timedelta(days=1),
    )
    earlier_web_calls: list[Any] = []
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="earlier|as_of|snapshot",
    ):
        execute_scenario(earlier_scenario, web_calls=earlier_web_calls)
    assert earlier_web_calls == []

    paper_id = "paper-ada"
    paper_ref = "canonical:paper:paper-ada"
    paper_title = "Evidence-bound robotics"
    paper_exact_identifier = "PAPER-EXACT-S8R3"
    professor_only_term = "professor_page_declaration"
    assert professor_only_term in item.snippet

    def plan_with_paper_identifier(identifier: str) -> Any:
        payload = plan.model_dump(mode="json", exclude={"content_sha256"})
        payload["protected_slots"].extend(
            (
                read_module.ProtectedSlot(
                    kind="exact_identifier",
                    value=identifier,
                    raw_text=identifier,
                ).model_dump(mode="json"),
                read_module.ProtectedSlot(
                    kind="negation",
                    value=professor_only_term,
                    raw_text=professor_only_term,
                ).model_dump(mode="json"),
            )
        )
        payload["structured_constraints"]["excluded_terms"] = [professor_only_term]
        return read_module.RetrievalPlan.model_validate(payload)

    same_paper_web_payload = b"Current Web Paper identifier PAPER-EXACT-S8R3"
    same_paper_web_digest = hashlib.sha256(same_paper_web_payload).hexdigest()
    same_paper_web_snapshot = read_module.WebEvidenceSnapshot(
        snapshot_id=(f"web-snapshot:s8r3-paper:sha256:{same_paper_web_digest}"),
        content_sha256=same_paper_web_digest,
        retrieved_at=NOW,
        byte_length=len(same_paper_web_payload),
    )
    same_paper_web_calls: list[Any] = []

    def same_paper_web_search(value: Any) -> Any:
        same_paper_web_calls.append(value)
        web_item = read_module.EvidenceItem(
            evidence_id="evidence:web:s8r3:paper-ada:exact-identifier",
            object_id=paper_id,
            domain="paper",
            lane="web",
            source_nature="current_web",
            source_locator="https://current.example/s8r3-paper-ada",
            snippet="Current Web Paper identifier PAPER-EXACT-S8R3",
            score=0.5,
            claim_binding=read_module.EvidenceClaimBinding(
                subject_id=paper_ref,
                predicate="exact_identifier",
                value=paper_exact_identifier,
                status="accepted",
            ),
            web_snapshot=same_paper_web_snapshot,
        )
        return read_module.RetrievalLaneResult(
            candidates=(
                read_module.RecallCandidate(
                    raw_candidate_id=("raw:web:s8r3:paper-ada:exact-identifier"),
                    display_name=paper_title,
                    domain="paper",
                    identity_kind="canonical",
                    canonical_id=paper_id,
                    resolution_state="resolved",
                    query_view=value.query_view,
                    lane="web",
                    attempt=1,
                    release_id=value.release_id,
                    adapter_version="s8r3-web-fixture-v1",
                    provider_version="s8r3-web-provider-v1",
                    raw_score=0.5,
                    evidence=(web_item,),
                ),
            ),
            web_snapshot_payloads=(
                read_module.WebSnapshotPayload(
                    snapshot_id=same_paper_web_snapshot.snapshot_id,
                    content=same_paper_web_payload,
                ),
            ),
        )

    constrained_plan = plan_with_paper_identifier(paper_exact_identifier)
    constrained_result = release_factory(
        **{
            **service_kwargs,
            "web_search": same_paper_web_search,
            "web_snapshot_policy": read_module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8r3-same-paper",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
        }
    ).execute(constrained_plan)
    assert len(same_paper_web_calls) == 1
    assert constrained_result.protected_slots == constrained_plan.protected_slots
    trace_by_lane = {trace.lane: trace for trace in constrained_result.traces}
    assert set(trace_by_lane) == {"relationship", "web"}
    assert all(trace.status == "succeeded" for trace in trace_by_lane.values())
    assert trace_by_lane["relationship"].candidate_count == 1
    assert trace_by_lane["web"].candidate_count == 1
    assert constrained_result.snapshot_receipts == (
        read_module.SnapshotReceipt(
            snapshot_id=same_paper_web_snapshot.snapshot_id,
            status="accepted",
            observed_byte_length=len(same_paper_web_payload),
        ),
    )
    assert len(constrained_result.fused_candidates) == 1
    constrained_fused = constrained_result.fused_candidates[0]
    assert constrained_fused.canonical_id == paper_id
    assert constrained_fused.domain == "paper"
    assert constrained_fused.display_name == paper_title
    assert (
        len(constrained_fused.raw_candidate_ids)
        == len(set(constrained_fused.raw_candidate_ids))
        == 2
    )
    assert (
        len(constrained_fused.evidence_ids)
        == len(set(constrained_fused.evidence_ids))
        == 2
    )
    assert {evidence.lane for evidence in constrained_fused.evidence} == {
        "relationship",
        "web",
    }
    relationship_evidence = next(
        evidence
        for evidence in constrained_fused.evidence
        if evidence.lane == "relationship"
    )
    web_evidence = next(
        evidence for evidence in constrained_fused.evidence if evidence.lane == "web"
    )
    assert professor_only_term in relationship_evidence.snippet
    assert professor_only_term not in web_evidence.snippet
    assert web_evidence.claim_binding == read_module.EvidenceClaimBinding(
        subject_id=paper_ref,
        predicate="exact_identifier",
        value=paper_exact_identifier,
        status="accepted",
    )
    assert constrained_result.constraint_receipts == (
        read_module.ConstraintReceipt(
            raw_candidate_ids=constrained_fused.raw_candidate_ids,
            outcome="accepted",
            failed_slots=(),
            aggregated_evidence_ids=constrained_fused.evidence_ids,
        ),
    )
    assert {
        candidate_trace.lane for candidate_trace in constrained_result.candidate_traces
    } == {
        "relationship",
        "web",
    }
    assert all(
        candidate_trace.disposition == "selected"
        for candidate_trace in constrained_result.candidate_traces
    )
    assert all(
        candidate_trace.selected_result_id == paper_id
        for candidate_trace in constrained_result.candidate_traces
    )
    assert constrained_result.entity_handles == (
        read_module.CanonicalEntityHandle(
            canonical_id=paper_id,
            domain="paper",
            display_name=paper_title,
            evidence_ids=constrained_fused.evidence_ids,
        ),
    )
    assert not any(
        isinstance(handle, read_module.WebEntityHandle)
        for handle in constrained_result.entity_handles
    )
    assert constrained_result.handle_resolution_receipts == ()
    assert constrained_result.fusion_receipt == read_module.DecisionReceipt(
        mode="deterministic_fallback"
    )
    assert constrained_result.rerank_receipt == read_module.DecisionReceipt(
        mode="deterministic_fallback"
    )
    assert constrained_result.auxiliary_traces == ()
    assert constrained_result.limitations == ()
    constrained_coverage = constrained_result.enumeration_coverage
    assert constrained_coverage is not None
    assert constrained_coverage.checked_ids == (paper_id,)
    assert constrained_coverage.eligible_ids == (paper_id,)
    assert constrained_coverage.retrieved_ids == (paper_id,)
    assert constrained_coverage.displayed_ids == (paper_id,)
    assert constrained_coverage.checked_count == 1
    assert constrained_coverage.eligible_count == 1
    assert constrained_coverage.retrieved_count == 1
    assert constrained_coverage.displayed_count == 1
    assert constrained_coverage.omitted_ids == ()
    assert constrained_coverage.unknown_ids == ()
    assert constrained_coverage.omitted_count == 0
    assert constrained_coverage.unknown_count is None
    assert constrained_coverage.unknown_scope is True
    assert constrained_coverage.exhaustive is False
    assert constrained_coverage.accounting_complete is True
    assert constrained_coverage.continuation_state == "open_world"
    assert constrained_coverage.continuation_required is True

    wrong_identifier = "PAPER-WRONG-S8R3"
    wrong_identifier_result = release_factory(
        **{
            **service_kwargs,
            "web_search": same_paper_web_search,
            "web_snapshot_policy": read_module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8r3-same-paper-wrong-id",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
        }
    ).execute(plan_with_paper_identifier(wrong_identifier))
    assert len(same_paper_web_calls) == 2
    assert wrong_identifier_result.snapshot_receipts[0].status == "accepted"
    assert len(wrong_identifier_result.constraint_receipts) == 1
    wrong_receipt = wrong_identifier_result.constraint_receipts[0]
    assert wrong_receipt.outcome == "rejected"
    assert len(wrong_receipt.failed_slots) == 1
    wrong_failure = wrong_receipt.failed_slots[0]
    assert wrong_failure.slot_kind == "exact_identifier"
    assert wrong_failure.required_value == wrong_identifier
    assert wrong_failure.observed_values == (paper_exact_identifier,)
    assert all(
        failure.slot_kind != "negation" for failure in wrong_receipt.failed_slots
    )
    assert wrong_identifier_result.items == ()
    assert wrong_identifier_result.entity_handles == ()
    assert len(wrong_identifier_result.candidate_traces) == 2
    assert all(
        candidate_trace.disposition == "hard_constraint_rejected"
        for candidate_trace in wrong_identifier_result.candidate_traces
    )
    assert all(
        candidate_trace.selected_result_id is None
        for candidate_trace in wrong_identifier_result.candidate_traces
    )

    fabricated_payload = b"Fabricated Web Professor-Paper attribution"
    fabricated_digest = hashlib.sha256(fabricated_payload).hexdigest()
    fabricated_snapshot = read_module.WebEvidenceSnapshot(
        snapshot_id=f"web-snapshot:s8r3-fabricated:sha256:{fabricated_digest}",
        content_sha256=fabricated_digest,
        retrieved_at=NOW,
        byte_length=len(fabricated_payload),
    )

    def fabricated_attribution_web_search(value: Any) -> Any:
        fabricated_item = read_module.EvidenceItem(
            evidence_id="evidence:web:s8r3:fabricated-attribution",
            object_id=paper_id,
            domain="paper",
            lane="web",
            source_nature="current_web",
            source_locator="https://current.example/s8r3-fabricated-attribution",
            snippet="Fabricated Web Professor-Paper attribution",
            score=0.5,
            claim_binding=read_module.EvidenceClaimBinding(
                subject_id="canonical:professor:professor-ada",
                predicate="professor_attributed_to_paper",
                value=paper_ref,
                status="accepted",
            ),
            web_snapshot=fabricated_snapshot,
        )
        return read_module.RetrievalLaneResult(
            candidates=(
                read_module.RecallCandidate(
                    raw_candidate_id="raw:web:s8r3:fabricated-attribution",
                    display_name=paper_title,
                    domain="paper",
                    identity_kind="canonical",
                    canonical_id=paper_id,
                    resolution_state="resolved",
                    query_view=value.query_view,
                    lane="web",
                    attempt=1,
                    release_id=value.release_id,
                    adapter_version="s8r3-web-fixture-v1",
                    provider_version="s8r3-web-provider-v1",
                    raw_score=0.5,
                    evidence=(fabricated_item,),
                ),
            ),
            web_snapshot_payloads=(
                read_module.WebSnapshotPayload(
                    snapshot_id=fabricated_snapshot.snapshot_id,
                    content=fabricated_payload,
                ),
            ),
        )

    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="S8R3 non-local evidence cannot assert a Professor-Paper relationship",
    ):
        release_factory(
            release_bundle=authoritative_zero["bundle"],
            published_release=authoritative_zero["published"],
            index_projection_request=authoritative_zero["index_request"],
            release_institution_catalog=authoritative_zero["catalog"],
            universal_web_policy=authoritative_zero["plan"].web_policy,
            web_search=fabricated_attribution_web_search,
            web_snapshot_policy=read_module.WebSnapshotPolicy(
                policy_id="web-snapshot-policy:s8r3-fabricated-attribution",
                policy_version="web-snapshot-policy-v1",
                max_bytes=8_192,
            ),
            clock=lambda: NOW,
        ).execute(authoritative_zero["plan"])

    hostile_professor_payload = b"Hostile displayed Professor Web witness"
    hostile_professor_digest = hashlib.sha256(hostile_professor_payload).hexdigest()
    hostile_professor_snapshot = read_module.WebEvidenceSnapshot(
        snapshot_id=(f"web-snapshot:s8r3-professor:sha256:{hostile_professor_digest}"),
        content_sha256=hostile_professor_digest,
        retrieved_at=NOW,
        byte_length=len(hostile_professor_payload),
    )
    hostile_professor_item = read_module.EvidenceItem(
        evidence_id="evidence:web:s8r3:displayed-professor-witness",
        object_id="professor-ada",
        domain="professor",
        lane="web",
        source_nature="current_web",
        source_locator="https://current.example/s8r3-professor-witness",
        snippet="Displayed Professor Web witness",
        score=0.5,
        web_snapshot=hostile_professor_snapshot,
    )
    hostile_professor_result = read_module.RetrievalLaneResult(
        items=(hostile_professor_item,),
        web_snapshot_payloads=(
            read_module.WebSnapshotPayload(
                snapshot_id=hostile_professor_snapshot.snapshot_id,
                content=hostile_professor_payload,
            ),
        ),
    )
    hostile_professor_calls: list[Any] = []
    with pytest.raises(
        isolated_read_module.IsolatedKnowledgeReadIntegrityError,
        match="S8R3 Web source witness must not satisfy displayed Professor authority",
    ):
        release_factory(
            **{
                **service_kwargs,
                "web_search": lambda value: (
                    hostile_professor_calls.append(value) or hostile_professor_result
                ),
                "web_snapshot_policy": read_module.WebSnapshotPolicy(
                    policy_id="web-snapshot-policy:s8r3-hostile-professor",
                    policy_version="web-snapshot-policy-v1",
                    max_bytes=8_192,
                ),
            }
        ).execute(plan)
    assert len(hostile_professor_calls) == 1

    def forged_trace_factory(
        trace_updates: dict[str, Any],
    ) -> Callable[..., Any]:
        def factory(**kwargs: Any) -> Any:
            adapter = real_relationship_factory(**kwargs)

            def forged(value: Any) -> Any:
                result = adapter(value)
                candidate = result.candidates[0]
                evidence = candidate.evidence[0]
                local_trace = evidence.local_projection_trace
                assert isinstance(
                    local_trace,
                    read_module.LocalProfessorPaperRelationshipTrace,
                )
                trace_payload = local_trace.model_dump(mode="python")
                trace_payload.update(trace_updates)
                trace_payload.update(
                    {
                        "raw_candidate_id": "",
                        "evidence_id": "",
                        "content_sha256": "0" * 64,
                    }
                )
                forged_trace = (
                    read_module.LocalProfessorPaperRelationshipTrace.model_validate(
                        trace_payload
                    )
                )
                forged_evidence = evidence.model_copy(
                    update={
                        "evidence_id": forged_trace.evidence_id,
                        "source_locator": (
                            isolated_read_module._local_projection_locator(forged_trace)
                        ),
                        "local_projection_trace": forged_trace,
                    }
                )
                forged_candidate = candidate.model_copy(
                    update={
                        "raw_candidate_id": forged_trace.raw_candidate_id,
                        "evidence": (forged_evidence,),
                    }
                )
                return read_module.RetrievalLaneResult(candidates=(forged_candidate,))

            return forged

        return factory

    for trace_updates in (
        {"paper_domain_identity_status": "unverified"},
        {"source_assignment_id": "relationship-assignment:professor:crosswire"},
    ):
        monkeypatch.setattr(
            isolated_read_module,
            "create_isolated_relationship_lookup_adapter",
            forged_trace_factory(trace_updates),
        )
        with pytest.raises(
            isolated_read_module.IsolatedKnowledgeReadIntegrityError,
            match="top-level evidence differs from replay authority",
        ):
            execute_scenario(positive)

    monkeypatch.setattr(
        isolated_read_module,
        "create_isolated_relationship_lookup_adapter",
        real_relationship_factory,
    )
    real_ephemeral_read_factory = isolated_read_module.create_ephemeral_knowledge_read

    def hostile_delegate_factory(
        mutation: Callable[[dict[str, Any]], None],
    ) -> Callable[..., Any]:
        def factory(**kwargs: Any) -> Any:
            delegate = real_ephemeral_read_factory(**kwargs)

            class _HostileDelegate:
                def execute(self, value: Any) -> Any:
                    payload = delegate.execute(value).model_dump(mode="json")
                    mutation(payload)
                    return read_module.EvidenceSet.model_validate(payload)

            return _HostileDelegate()

        return factory

    def drift_fused_provenance(payload: dict[str, Any]) -> None:
        payload["fused_candidates"][0].update(
            {"origin_lane": "web", "origin_attempt": 99, "raw_score": 0.123}
        )

    def append_receipt_ownership(payload: dict[str, Any]) -> None:
        receipt = payload["constraint_receipts"][0]
        receipt["raw_candidate_ids"].append("raw:s8r3:nonexistent")
        receipt["aggregated_evidence_ids"].append("evidence:s8r3:nonexistent")

    def append_handle_ownership(payload: dict[str, Any]) -> None:
        payload["entity_handles"][0]["evidence_ids"].append("evidence:s8r3:nonexistent")

    hostile_delegate_cases = (
        (drift_fused_provenance, "fused provenance differs"),
        (append_receipt_ownership, "constraint receipts differ"),
        (append_handle_ownership, "handle differs from canonical authority"),
    )
    for mutation, expected_error in hostile_delegate_cases:
        monkeypatch.setattr(
            isolated_read_module,
            "create_ephemeral_knowledge_read",
            hostile_delegate_factory(mutation),
        )
        with pytest.raises(
            isolated_read_module.IsolatedKnowledgeReadIntegrityError,
            match=expected_error,
        ):
            execute_scenario(positive)

    monkeypatch.setattr(
        isolated_read_module,
        "create_ephemeral_knowledge_read",
        real_ephemeral_read_factory,
    )
