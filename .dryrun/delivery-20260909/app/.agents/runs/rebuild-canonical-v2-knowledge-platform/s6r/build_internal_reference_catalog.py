#!/usr/bin/env python3
"""Build the additive Canonical V2 Person/Technology reference catalog."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
from types import ModuleType
from typing import Any, Protocol, cast


S6R_ROOT = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = S6R_ROOT.parents[3]
DEFAULT_EVIDENCE_CATALOG = S6R_ROOT / "internal-reference-catalog-v1.json"
DEFAULT_PACKAGED_CATALOG = (
    DEFAULT_REPO_ROOT
    / "apps/miroflow-agent/src/data_agents/canonical_v2/catalogs"
    / "internal-reference-catalog-v1.json"
)


class _ValidatorModule(Protocol):
    SCHEMA_VERSION: str
    CATALOG_VERSION: str
    BASE_DOMAIN_CATALOG: dict[str, str]
    CatalogValidationError: type[ValueError]

    def canonical_catalog_bytes(self, payload: dict[str, Any]) -> bytes: ...

    def catalog_content_sha256(self, payload: dict[str, Any]) -> str: ...

    def load_and_validate_catalog(
        self, *, repo_root: Path, catalog_path: Path
    ) -> dict[str, Any]: ...

    def validate_catalog_payload(
        self, payload: dict[str, Any], *, repo_root: Path
    ) -> None: ...


def _load_validator_module() -> _ValidatorModule:
    path = S6R_ROOT / "validate_internal_reference_catalog.py"
    spec = importlib.util.spec_from_file_location("canonical_v2_s6r_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load catalog validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(_ValidatorModule, cast(ModuleType, module))


_VALIDATOR = _load_validator_module()

SOURCE_CITATIONS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "docs/architecture-decisions/ADR-014-canonical-v2-internal-person-projection.md": (
        (
            "person.internal_role_neutral_boundary",
            (
                "four public PRD domains",
                "`PersonIdentity`",
                "`PersonProjection`",
                "unresolved source name",
            ),
        ),
    ),
    "docs/architecture-decisions/ADR-015-canonical-v2-internal-technology-model.md": (
        (
            "technology.internal_model",
            (
                "`TechnologyConcept`",
                "`TechnologyRoute`",
                "source assertions",
                "typed adoption/discussion evidence",
            ),
        ),
        (
            "technology.relationship_states",
            (
                "discussion, claimed adoption, and",
                "demonstrated use",
                "Product capability",
            ),
        ),
    ),
    "docs/architecture-decisions/ADR-016-product-capability-remains-answer-scoped.md": (
        (
            "product.capability_answer_boundary",
            (
                "`product_has_capability`",
                "answer-scoped `ProductCapabilityClaim`",
                "Technology relations must not be interpreted",
            ),
        ),
    ),
    "openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/canonical-v2-release/spec.md": (
        (
            "release.internal_auxiliary_scope",
            (
                "scope discriminator",
                "`public_domain`",
                "`internal_auxiliary`",
                "owning",
            ),
        ),
    ),
}


def _citation(
    *,
    citation_id: str,
    source_terms: tuple[str, ...],
    lines: list[str],
) -> dict[str, Any]:
    positions: list[int] = []
    for term in source_terms:
        matches = [index for index, line in enumerate(lines, start=1) if term in line]
        if not matches:
            raise _VALIDATOR.CatalogValidationError(
                f"authority term is missing: {citation_id}: {term}"
            )
        positions.append(matches[0])
    return {
        "citation_id": citation_id,
        "line_start": min(positions),
        "line_end": max(positions),
        "source_terms": list(source_terms),
    }


def _source_manifest(repo_root: Path) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for relative_path, citation_specs in SOURCE_CITATIONS.items():
        source_path = repo_root / relative_path
        source_bytes = source_path.read_bytes()
        lines = source_bytes.decode("utf-8", errors="strict").splitlines()
        manifest.append(
            {
                "path": relative_path,
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "citations": [
                    _citation(
                        citation_id=citation_id,
                        source_terms=source_terms,
                        lines=lines,
                    )
                    for citation_id, source_terms in citation_specs
                ],
            }
        )
    return manifest


def _reference_type(
    *,
    reference_type: str,
    projection_schema_version: str,
    required_projection_fields: tuple[str, ...],
    evidence_obligation: str,
    time_obligation: str,
    unresolved_policy: str,
    citation_ids: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "reference_type": reference_type,
        "identity_entity_type": reference_type,
        "projection_schema_version": projection_schema_version,
        "projection_scope": "internal_auxiliary",
        "required_projection_fields": list(required_projection_fields),
        "evidence_obligation": evidence_obligation,
        "time_obligation": time_obligation,
        "release_obligation": "bind_exact_accepted_release_and_content_hash",
        "unresolved_policy": unresolved_policy,
        "citation_ids": list(citation_ids),
    }


def _relationship(
    *,
    relationship_type_id: str,
    version: str,
    source_entity_types: tuple[str, ...],
    target_entity_types: tuple[str, ...],
    role_id: str,
    required_evidence_kind: str,
    time_semantics: str,
    eligible_paths: tuple[str, ...],
    endpoint_binding: str,
    semantic_state: str,
    predecessor_version: str | None,
    version_coexistence: str,
    resolved_person_reference_required: bool,
    unresolved_reference_not_canonical_endpoint: bool,
    does_not_entail_product_capability: bool,
    citation_ids: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "relationship_type_id": relationship_type_id,
        "version": version,
        "layer": "canonical",
        "source_entity_types": list(source_entity_types),
        "target_entity_types": list(target_entity_types),
        "direction": "directed",
        "role_id": role_id,
        "required_evidence_kinds": [required_evidence_kind],
        "time_semantics": time_semantics,
        "eligible_paths": list(eligible_paths),
        "endpoint_binding": endpoint_binding,
        "semantic_state": semantic_state,
        "predecessor_version": predecessor_version,
        "version_coexistence": version_coexistence,
        "resolved_person_reference_required": resolved_person_reference_required,
        "unresolved_reference_not_canonical_endpoint": (
            unresolved_reference_not_canonical_endpoint
        ),
        "does_not_entail_product_capability": does_not_entail_product_capability,
        "citation_ids": list(citation_ids),
    }


def build_catalog(*, repo_root: Path) -> dict[str, Any]:
    release_citation = "release.internal_auxiliary_scope"
    person_citation = "person.internal_role_neutral_boundary"
    technology_model_citation = "technology.internal_model"
    technology_states_citation = "technology.relationship_states"
    product_boundary_citation = "product.capability_answer_boundary"
    person_fields = (
        "canonical_person_identity_id",
        "display_name",
        "aliases",
        "reference_ids",
        "supporting_assertion_ids",
        "source_anchor_ids",
        "identity_decision_id",
        "as_of",
        "release_id",
        "content_sha256",
    )
    technology_shared_fields = (
        "canonical_technology_identity_id",
        "preferred_name",
        "aliases",
        "definition",
    )
    lineage_fields = (
        "supporting_assertion_ids",
        "source_anchor_ids",
        "observed_at",
        "release_id",
        "content_sha256",
    )
    internal_reference_types = [
        _reference_type(
            reference_type="person",
            projection_schema_version="person-reference-projection-v1",
            required_projection_fields=person_fields,
            evidence_obligation="accepted_four_domain_anchor_and_identity_decision",
            time_obligation="projection_as_of_and_source_observation_time",
            unresolved_policy="retain_reference_without_canonical_identity",
            citation_ids=(person_citation, release_citation),
        ),
        _reference_type(
            reference_type="technology_concept",
            projection_schema_version="technology-concept-projection-v1",
            required_projection_fields=(
                *technology_shared_fields,
                "parent_concept_ids",
                *lineage_fields,
            ),
            evidence_obligation="accepted_public_domain_or_typed_product_anchor",
            time_obligation="source_observed_at_and_optional_validity",
            unresolved_policy="retain_term_or_alias_candidate_until_offline_acceptance",
            citation_ids=(technology_model_citation, release_citation),
        ),
        _reference_type(
            reference_type="technology_route",
            projection_schema_version="technology-route-projection-v1",
            required_projection_fields=(
                *technology_shared_fields,
                "concept_ids",
                *lineage_fields,
            ),
            evidence_obligation="accepted_public_domain_or_typed_product_anchor",
            time_obligation="source_observed_at_and_optional_validity",
            unresolved_policy="retain_term_or_alias_candidate_until_offline_acceptance",
            citation_ids=(technology_model_citation, release_citation),
        ),
    ]
    relationships = [
        _relationship(
            relationship_type_id="company_has_team_member",
            version="canonical-v2-relationship-v2",
            source_entity_types=("company",),
            target_entity_types=("person",),
            role_id="team_role",
            required_evidence_kind="company_personnel_assertion",
            time_semantics="validity_interval",
            eligible_paths=("relationship_traversal", "structured_filter"),
            endpoint_binding="resolved_internal_reference_registry",
            semantic_state="company_personnel_membership",
            predecessor_version="canonical-v2-relationship-v1",
            version_coexistence="required",
            resolved_person_reference_required=True,
            unresolved_reference_not_canonical_endpoint=True,
            does_not_entail_product_capability=False,
            citation_ids=(person_citation,),
        ),
        _relationship(
            relationship_type_id="paper_has_author",
            version="canonical-v2-relationship-v2",
            source_entity_types=("paper",),
            target_entity_types=("person",),
            role_id="author",
            required_evidence_kind="paper_author_assertion",
            time_semantics="none",
            eligible_paths=("relationship_traversal", "structured_filter"),
            endpoint_binding="resolved_internal_reference_registry",
            semantic_state="authorship",
            predecessor_version="canonical-v2-relationship-v1",
            version_coexistence="required",
            resolved_person_reference_required=True,
            unresolved_reference_not_canonical_endpoint=True,
            does_not_entail_product_capability=False,
            citation_ids=(person_citation,),
        ),
        _relationship(
            relationship_type_id="patent_has_inventor",
            version="canonical-v2-relationship-v2",
            source_entity_types=("patent",),
            target_entity_types=("person",),
            role_id="inventor",
            required_evidence_kind="patent_inventor_assertion",
            time_semantics="none",
            eligible_paths=(
                "patent_to_professor",
                "professor_to_patent",
                "relationship_traversal",
                "structured_filter",
            ),
            endpoint_binding="resolved_internal_reference_registry",
            semantic_state="inventorship",
            predecessor_version="canonical-v2-relationship-v1",
            version_coexistence="required",
            resolved_person_reference_required=True,
            unresolved_reference_not_canonical_endpoint=True,
            does_not_entail_product_capability=False,
            citation_ids=(person_citation,),
        ),
    ]
    technology_common = {
        "source_entity_types": ("company", "paper", "patent", "product"),
        "target_entity_types": ("technology_concept", "technology_route"),
        "role_id": "technology",
        "endpoint_binding": "public_or_typed_subobject_to_internal_reference_registry",
        "predecessor_version": None,
        "version_coexistence": "not_applicable",
        "resolved_person_reference_required": False,
        "unresolved_reference_not_canonical_endpoint": True,
        "does_not_entail_product_capability": True,
        "citation_ids": (technology_states_citation, product_boundary_citation),
    }
    relationships.extend(
        (
            _relationship(
                relationship_type_id="entity_discusses_or_mentions_technology",
                version="canonical-v2-relationship-v1",
                required_evidence_kind="technology_discussion_assertion",
                time_semantics="observed_at",
                eligible_paths=(
                    "exact_lookup",
                    "semantic_recall",
                    "relationship_traversal",
                ),
                semantic_state="discussion_or_mention",
                **technology_common,
            ),
            _relationship(
                relationship_type_id="entity_claims_adoption_of_technology",
                version="canonical-v2-relationship-v1",
                required_evidence_kind="technology_adoption_claim_assertion",
                time_semantics="validity_interval",
                eligible_paths=(
                    "exact_lookup",
                    "semantic_recall",
                    "relationship_traversal",
                ),
                semantic_state="claimed_adoption",
                **technology_common,
            ),
            _relationship(
                relationship_type_id="entity_demonstrates_use_of_technology",
                version="canonical-v2-relationship-v1",
                required_evidence_kind="technology_demonstrated_use_assertion",
                time_semantics="validity_interval",
                eligible_paths=(
                    "exact_lookup",
                    "semantic_recall",
                    "relationship_traversal",
                ),
                semantic_state="demonstrated_use",
                **technology_common,
            ),
        )
    )
    payload: dict[str, Any] = {
        "schema_version": _VALIDATOR.SCHEMA_VERSION,
        "catalog_version": _VALIDATOR.CATALOG_VERSION,
        "status": "frozen",
        "base_domain_catalog": dict(_VALIDATOR.BASE_DOMAIN_CATALOG),
        "public_domain_types": ["company", "paper", "patent", "professor"],
        "internal_reference_types": internal_reference_types,
        "relationship_types": relationships,
        "source_manifest": _source_manifest(repo_root),
    }
    payload["content_sha256"] = _VALIDATOR.catalog_content_sha256(payload)
    _VALIDATOR.validate_catalog_payload(payload, repo_root=repo_root)
    return payload


def check_catalog(
    *,
    repo_root: Path,
    catalog_paths: tuple[Path, ...],
) -> None:
    expected = _VALIDATOR.canonical_catalog_bytes(build_catalog(repo_root=repo_root))
    for catalog_path in catalog_paths:
        try:
            actual = catalog_path.read_bytes()
        except OSError as exc:
            raise _VALIDATOR.CatalogValidationError(
                f"catalog bytes drifted: {catalog_path}"
            ) from exc
        if actual != expected:
            raise _VALIDATOR.CatalogValidationError(
                f"catalog bytes drifted: {catalog_path}"
            )
        _VALIDATOR.load_and_validate_catalog(
            repo_root=repo_root,
            catalog_path=catalog_path,
        )


def _approved_catalog_paths(repo_root: Path) -> tuple[Path, Path]:
    return (
        repo_root
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s6r"
        / "internal-reference-catalog-v1.json",
        repo_root
        / "apps/miroflow-agent/src/data_agents/canonical_v2/catalogs"
        / "internal-reference-catalog-v1.json",
    )


def _validated_write_paths(
    *,
    repo_root: Path,
    catalog_paths: tuple[Path, ...],
) -> tuple[Path, ...]:
    lexical_root = Path(os.path.abspath(repo_root))
    if lexical_root.is_symlink():
        raise _VALIDATOR.CatalogValidationError(
            "catalog repo_root must not be a symlink"
        )
    expected = tuple(
        Path(os.path.abspath(path)) for path in _approved_catalog_paths(lexical_root)
    )
    requested = tuple(Path(os.path.abspath(path)) for path in catalog_paths)
    if requested != expected:
        raise _VALIDATOR.CatalogValidationError(
            "catalog writes must target the evidence and packaged S6R paths together"
        )
    resolved_root = lexical_root.resolve()
    for target in requested:
        try:
            relative = target.relative_to(lexical_root)
        except ValueError as exc:
            raise _VALIDATOR.CatalogValidationError(
                "catalog write path escapes repository root"
            ) from exc
        cursor = lexical_root
        for component in relative.parts:
            cursor /= component
            if cursor.is_symlink():
                raise _VALIDATOR.CatalogValidationError(
                    f"catalog write path contains a symlink: {cursor}"
                )
        resolved_parent = target.parent.resolve()
        if (
            resolved_parent != resolved_root
            and resolved_root not in resolved_parent.parents
        ):
            raise _VALIDATOR.CatalogValidationError(
                "catalog write path escapes repository root"
            )
    return requested


def write_catalog(
    *,
    repo_root: Path,
    catalog_paths: tuple[Path, ...],
) -> None:
    validated_paths = _validated_write_paths(
        repo_root=repo_root,
        catalog_paths=catalog_paths,
    )
    content = _VALIDATOR.canonical_catalog_bytes(build_catalog(repo_root=repo_root))
    for catalog_path in validated_paths:
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=catalog_path.parent,
            prefix=f".{catalog_path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary_path = Path(temporary_name)
            _VALIDATOR.load_and_validate_catalog(
                repo_root=repo_root,
                catalog_path=temporary_path,
            )
            os.replace(temporary_path, catalog_path)
        finally:
            Path(temporary_name).unlink(missing_ok=True)
    check_catalog(repo_root=repo_root, catalog_paths=validated_paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true")
    action.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    repo_root = DEFAULT_REPO_ROOT
    catalog_paths = _approved_catalog_paths(repo_root)
    if arguments.write:
        write_catalog(repo_root=repo_root, catalog_paths=catalog_paths)
    else:
        check_catalog(repo_root=repo_root, catalog_paths=catalog_paths)


if __name__ == "__main__":
    main()


__all__ = [
    "build_catalog",
    "check_catalog",
    "main",
    "write_catalog",
]
