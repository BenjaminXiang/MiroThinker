from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from importlib import import_module
import inspect
import json
import os
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from sqlalchemy import exc as sa_exc
from sqlalchemy.engine import make_url

from src.data_agents.canonical_v2.contracts import DecisionMethod
from src.data_agents.canonical_v2.contracts import IdentityReference
from src.data_agents.canonical_v2.contracts import IdentitySpace
from src.data_agents.canonical_v2.contracts import PolicyKind
from src.data_agents.canonical_v2.contracts import PolicyReference
from src.data_agents.canonical_v2.contracts import RelationshipAssertion
from src.data_agents.canonical_v2 import domain_projection_models as domain_models
from src.data_agents.canonical_v2.domain_catalog import CATALOG_CONTENT_SHA256
from src.data_agents.canonical_v2.domain_catalog import CATALOG_SCHEMA_VERSION
from src.data_agents.canonical_v2.domain_catalog import CATALOG_VERSION
from src.data_agents.canonical_v2.relationship_projection import (
    RelationshipCatalogIdentity,
)
from src.data_agents.canonical_v2.rebuild_write_gate import RebuildWriteGateError
from src.data_agents.canonical_v2.relationship_projection import (
    RelationshipDecisionInput,
)
from src.data_agents.canonical_v2.relationship_projection import (
    RelationshipEndpointReference,
)
from src.data_agents.canonical_v2.relationship_projection import (
    RelationshipProjectionCandidate,
)
from src.data_agents.canonical_v2.relationship_projection import (
    RelationshipProjectionRequest,
)
from src.data_agents.canonical_v2.relationship_projection import (
    RetainedArtifactReference,
)
from src.data_agents.canonical_v2.relationship_projection import (
    RetainedAssertionReference,
)
from src.data_agents.canonical_v2.relationship_projection import (
    RetainedEvidenceBinding,
)
from src.data_agents.canonical_v2.relationship_projection import (
    SourceCanonicalAssignment,
)
from src.data_agents.canonical_v2.relationship_projection import (
    TypedRelationshipAssertionInput,
)
from src.data_agents.canonical_v2.relationship_projection import (
    create_ephemeral_relationship_projection,
)
from src.data_agents.storage.database_target import set_alembic_database_url


TARGET_MODULE = "src.data_agents.canonical_v2.relationship_projection_postgres"
APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "canonical_v2_alembic.ini"
SCRIPT_LOCATION = APP_ROOT / "canonical_v2_alembic"
EXPECTED_REVISION = "C2_0010"
PREVIOUS_REVISION = "C2_0009"
RELEASE_ID = "relationship-projection-release-r1"
PROJECTION_RUN_ID = "relationship-projection-run-r1"
SOURCE_RECORD_ID = "source-record:artifact-lineage"
NOW = datetime(2026, 7, 13, 12, 45, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class _Target:
    database_url: str
    expected_database: str
    target_kind: str
    backup_gate_root: Path
    config: Config


class _MissingTargetModule(RuntimeError):
    """Exact S6E2 RED sentinel; nested missing dependencies fail normally."""


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


def _explicit_environment() -> tuple[str, str, str, str]:
    names = (
        "CANONICAL_V2_TEST_DATABASE_URL",
        "CANONICAL_V2_TEST_EXPECTED_DATABASE",
        "CANONICAL_V2_TEST_TARGET_KIND",
        "CANONICAL_V2_TEST_BACKUP_GATE_ROOT",
    )
    values = tuple(os.environ.get(name) for name in names)
    if not all(values):
        pytest.skip(
            "relationship persistence requires all four explicit "
            "CANONICAL_V2_TEST_* settings"
        )
    return values  # type: ignore[return-value]


def _psycopg_dsn(database_url: str) -> str:
    return (
        make_url(database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


def _sibling_database_url(database_url: str, database_name: str) -> str:
    return (
        make_url(database_url)
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )


def _migration_config(target: _Target) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    set_alembic_database_url(config, target.database_url)
    config.set_main_option("miroflow.expected_database", target.expected_database)
    config.set_main_option("miroflow.target_kind", target.target_kind)
    config.set_main_option("miroflow.backup_gate_root", str(target.backup_gate_root))
    return config


def _connect(target: _Target, *, autocommit: bool = False) -> Any:
    return psycopg.connect(_psycopg_dsn(target.database_url), autocommit=autocommit)


def _drop_owned_sibling(
    connection: psycopg.Connection[Any],
    *,
    database_name: str,
    expected_marker: str,
) -> None:
    existing = connection.execute(
        "SELECT shobj_description(oid, 'pg_database') "
        "FROM pg_database WHERE datname = %s",
        (database_name,),
    ).fetchone()
    if existing is None:
        return
    assert existing == (expected_marker,)
    connection.execute(
        sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
    )


@pytest.fixture
def target(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> Iterator[_Target]:
    database_url, expected_database, target_kind, backup_gate_root = (
        _explicit_environment()
    )
    assert target_kind == "disposable"
    for name in (
        "ALEMBIC_DATABASE_URL",
        "ALEMBIC_EXPECTED_DATABASE",
        "ALEMBIC_TARGET_KIND",
        "CANONICAL_V2_BACKUP_GATE_ROOT",
        "DATABASE_URL_TEST",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://miroflow:do-not-use@localhost:15432/miroflow_real",
    )
    base_marker = f"miroflow:destructive-target:v1:{target_kind}:{expected_database}"
    sibling_name = (
        f"{expected_database[:38]}_s6e2_"
        f"{hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:8]}"
    )
    sibling_marker = f"miroflow:destructive-target:v1:disposable:{sibling_name}"
    with psycopg.connect(_psycopg_dsn(database_url), autocommit=True) as admin:
        assert admin.execute(
            "SELECT current_database(), shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = current_database()"
        ).fetchone() == (expected_database, base_marker)
        _drop_owned_sibling(
            admin,
            database_name=sibling_name,
            expected_marker=sibling_marker,
        )
        admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(sibling_name))
        )
        admin.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(sibling_name),
                sql.Literal(sibling_marker),
            )
        )
    try:
        provisional = _Target(
            database_url=_sibling_database_url(database_url, sibling_name),
            expected_database=sibling_name,
            target_kind="disposable",
            backup_gate_root=Path(backup_gate_root),
            config=Config(),
        )
        configured = _Target(
            database_url=provisional.database_url,
            expected_database=provisional.expected_database,
            target_kind=provisional.target_kind,
            backup_gate_root=provisional.backup_gate_root,
            config=_migration_config(provisional),
        )
        command.upgrade(configured.config, EXPECTED_REVISION)
        with _connect(configured, autocommit=True) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.canonical_v2_alembic_version"
            ).fetchone() == (EXPECTED_REVISION,)
        yield configured
    finally:
        with psycopg.connect(_psycopg_dsn(database_url), autocommit=True) as admin:
            _drop_owned_sibling(
                admin,
                database_name=sibling_name,
                expected_marker=sibling_marker,
            )


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _content_bound_projection(model: Any, values: dict[str, Any]) -> Any:
    provisional = model.model_validate(
        {**values, "content_sha256": "0" * 64},
        context={"allow_unbound_projection_hash": True},
    )
    return model.model_validate(
        {
            **provisional.model_dump(mode="python"),
            "content_sha256": _canonical_sha256(
                provisional.model_dump(mode="json", exclude={"content_sha256"})
            ),
        }
    )


def _domain_projection(entity_type: str, canonical_identity_id: str) -> Any:
    assertion_id = f"projection-assertion:{canonical_identity_id}"
    decision_id = f"projection-decision:{canonical_identity_id}"
    field_path = "name"
    common = {
        "release_id": RELEASE_ID,
        "canonical_identity_id": canonical_identity_id,
        "identity_decision_id": f"identity-decision:{canonical_identity_id}",
        "inclusion_decision_id": f"inclusion:{canonical_identity_id}",
        "projection_version": "domain-projection-v1",
        "catalog_schema_version": CATALOG_SCHEMA_VERSION,
        "catalog_version": CATALOG_VERSION,
        "catalog_content_sha256": CATALOG_CONTENT_SHA256,
        "as_of": NOW,
        "field_lineage": (
            domain_models.FieldProjectionLineage(
                field_path=field_path,
                decision_id=decision_id,
                supporting_assertion_ids=(assertion_id,),
            ),
        ),
        "evidence": (
            domain_models.ProjectionEvidenceReference(
                assertion_id=assertion_id,
                decision_id=decision_id,
                field_path=field_path,
            ),
        ),
        "id": canonical_identity_id,
        "last_updated": NOW,
        "quality_status": "partial",
        "run_id": "relationship-shared-domain-fixture",
    }
    if entity_type == "company":
        return _content_bound_projection(
            domain_models.CompanyProjection,
            {
                **common,
                "name": "Shared Company",
                "normalized_name": "shared company",
                "profile_summary": "Shared company endpoint fixture.",
                "technology_route_summary": "Shared technology route.",
                **{
                    attribute: ()
                    for attribute in domain_models.DOMAIN_SUBOBJECT_ATTRIBUTES[
                        "company"
                    ].values()
                },
            },
        )
    if entity_type == "professor":
        return _content_bound_projection(
            domain_models.ProfessorProjection,
            {
                **common,
                "canonical_name_zh": "共享教授",
                "company_roles": (),
                "department": domain_models.NamedReference(
                    reference_id="department:shared",
                    name="Shared Department",
                ),
                "email": "shared@example.edu",
                "homepage": "https://example.edu/shared",
                "institution": "Shared Institution",
                "name": "Shared Professor",
                "paper_summary": "Shared paper summary.",
                "patent_ids": (),
                "patent_summary": "Shared patent summary.",
                "profile_summary": "Shared professor endpoint fixture.",
                "research_directions": (),
                "title": "Professor",
            },
        )
    raise AssertionError(f"unsupported shared projection entity: {entity_type}")


def _seed_prerequisites(target: _Target) -> None:
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO landing.evidence_artifact "
            "(artifact_id, source_kind, source_locator, content_sha256, byte_size, "
            "acquired_at, run_id) VALUES "
            "('relationship-artifact', 'recorded_fixture', "
            "'fixture://relationship', %s, 1, %s, 'relationship-fixture-run')",
            (_fingerprint("relationship-artifact"), NOW),
        )
        connection.execute(
            "INSERT INTO landing.parser_run "
            "(parse_run_id, artifact_id, parser_name, parser_version, schema_version, "
            "run_status, started_at, finished_at) VALUES "
            "('relationship-parser', 'relationship-artifact', 'recorded_fixture', "
            "'v1', 'relationship-source-v1', 'succeeded', %s, %s)",
            (NOW, NOW),
        )
        connection.execute(
            "INSERT INTO landing.source_record "
            "(record_id, artifact_id, source_batch_id, record_locator, parse_run_id, "
            "record_ordinal, parse_status, payload, parsed_at) VALUES "
            "(%s, 'relationship-artifact', 'relationship-source-batch', 'row:0', "
            "'relationship-parser', 0, 'parsed', %s, %s)",
            (SOURCE_RECORD_ID, Jsonb({"id": SOURCE_RECORD_ID}), NOW),
        )
        connection.execute(
            "INSERT INTO knowledge.release "
            "(release_id, build_run_id, state, manifest_sha256, created_at) "
            "VALUES (%s, 'relationship-domain-build', 'candidate', %s, %s)",
            (RELEASE_ID, _fingerprint("relationship-release-manifest"), NOW),
        )
        connection.commit()


def _projection_request(*, rationale: str = "retained relationship fixture") -> Any:
    source_endpoint = RelationshipEndpointReference(
        reference_kind="lineage_record",
        endpoint_type="artifact",
        stable_reference="lineage:artifact:derived",
        canonical_identity_id=None,
        parent_canonical_identity_ref=None,
    )
    target_endpoint = RelationshipEndpointReference(
        reference_kind="lineage_record",
        endpoint_type="artifact",
        stable_reference="lineage:artifact:parent",
        canonical_identity_id=None,
        parent_canonical_identity_ref=None,
    )
    retained_artifact = RetainedArtifactReference(
        reference_id="artifact:relationship-fixture",
        artifact_id="relationship-artifact",
        content_sha256=_fingerprint("relationship-artifact"),
    )
    retained_assertion = RetainedAssertionReference(
        reference_id="assertion:relationship-fixture",
        assertion_id="retained-assertion:relationship-fixture",
        source_record_ref=SOURCE_RECORD_ID,
        artifact_refs=(retained_artifact.reference_id,),
    )
    evidence_binding = RetainedEvidenceBinding(
        evidence_kind="artifact_manifest_reference",
        assertion_refs=(retained_assertion.reference_id,),
        artifact_refs=(retained_artifact.reference_id,),
    )
    assertion_id = "relationship-assertion:artifact-lineage"
    decision_input_id = "relationship-decision-input:artifact-lineage"
    decision_id = "relationship-decision:artifact-lineage"
    canonical_relationship_id = "canonical-relationship:artifact-lineage"
    candidate = RelationshipProjectionCandidate(
        candidate_id="valid:artifact_derived_from_artifact",
        relationship_type_id="artifact_derived_from_artifact",
        relationship_type_version="canonical-v2-relationship-v1",
        source_endpoint=source_endpoint,
        target_endpoint=target_endpoint,
        role_bindings={},
        evidence_metadata={},
        requested_paths=(),
        observed_at=NOW,
        source_event_time=NOW,
        valid_from=None,
        valid_to=None,
        evidence_bindings=(evidence_binding,),
        assertion_input_id=assertion_id,
        assertion_input_kind="typed_relationship_assertion",
        decision_input_id=decision_input_id,
    )
    typed_assertion = TypedRelationshipAssertionInput(
        assertion_id=assertion_id,
        relationship_type_id=candidate.relationship_type_id,
        relationship_type_version=candidate.relationship_type_version,
        source_record_ref=SOURCE_RECORD_ID,
        source_endpoint=source_endpoint,
        target_endpoint=target_endpoint,
        attributes={
            "candidate_id": candidate.candidate_id,
            "evidence_metadata": {},
            "role_bindings": {},
        },
        evidence_bindings=(evidence_binding,),
        observed_at=NOW,
        source_event_time=NOW,
        valid_from=None,
        valid_to=None,
        assertion_run_id="relationship-assertion-run",
    )
    policy = PolicyReference(
        policy_id="relationship-projection-policy",
        policy_version="relationship-v1",
        policy_kind=PolicyKind.relationship,
        content_sha256=_fingerprint("relationship-projection-policy"),
        effective_at=NOW - timedelta(days=1),
    )
    selected_evidence_refs = tuple(
        sorted((retained_assertion.reference_id, retained_artifact.reference_id))
    )
    decision_input = RelationshipDecisionInput(
        decision_input_id=decision_input_id,
        decision_id=decision_id,
        canonical_relationship_id=canonical_relationship_id,
        state="accepted",
        candidate_assertion_ids=(assertion_id,),
        selected_assertion_ids=(assertion_id,),
        conflicting_assertion_ids=(),
        role_bindings={},
        selected_evidence_refs=selected_evidence_refs,
        policy=policy,
        method=DecisionMethod.deterministic,
        method_version="relationship-v1",
        confidence=1.0,
        rationale=rationale,
    )
    return RelationshipProjectionRequest(
        catalog=RelationshipCatalogIdentity(
            schema_version=CATALOG_SCHEMA_VERSION,
            catalog_version=CATALOG_VERSION,
            content_sha256=CATALOG_CONTENT_SHA256,
        ),
        release_id=RELEASE_ID,
        projection_run_id=PROJECTION_RUN_ID,
        as_of=NOW,
        decision_policy=policy,
        domain_projections=(),
        candidates=(candidate,),
        relationship_assertions=(),
        typed_relationship_assertions=(typed_assertion,),
        source_canonical_assignments=(),
        decision_inputs=(decision_input,),
        retained_assertions=(retained_assertion,),
        retained_artifacts=(retained_artifact,),
    )


def _shared_projection_request() -> RelationshipProjectionRequest:
    source_endpoint = RelationshipEndpointReference(
        reference_kind="canonical_identity",
        endpoint_type="professor",
        stable_reference="canonical:professor:professor-c1",
        canonical_identity_id="professor-c1",
        parent_canonical_identity_ref=None,
    )
    target_endpoint = RelationshipEndpointReference(
        reference_kind="canonical_identity",
        endpoint_type="company",
        stable_reference="canonical:company:company-c1",
        canonical_identity_id="company-c1",
        parent_canonical_identity_ref=None,
    )
    retained_artifact = RetainedArtifactReference(
        reference_id="artifact:shared-professor-company",
        artifact_id="relationship-artifact",
        content_sha256=_fingerprint("relationship-artifact"),
    )
    retained_reference = RetainedAssertionReference(
        reference_id="assertion:shared-professor-company",
        assertion_id="shared-relationship-assertion",
        source_record_ref=SOURCE_RECORD_ID,
        artifact_refs=(retained_artifact.reference_id,),
    )
    evidence_binding = RetainedEvidenceBinding(
        evidence_kind="professor_company_role_assertion",
        assertion_refs=(retained_reference.reference_id,),
        artifact_refs=(retained_artifact.reference_id,),
    )
    candidate_id = "valid:shared-professor-company"
    assertion_id = "shared-relationship-assertion"
    decision_input_id = "shared-relationship-decision-input"
    evidence_refs = tuple(
        sorted((retained_reference.reference_id, retained_artifact.reference_id))
    )
    candidate = RelationshipProjectionCandidate(
        candidate_id=candidate_id,
        relationship_type_id="professor_company_role",
        relationship_type_version="canonical-v2-relationship-v1",
        source_endpoint=source_endpoint,
        target_endpoint=target_endpoint,
        role_bindings={"founder": source_endpoint.stable_reference},
        evidence_metadata={"fixture": "shared-ledger"},
        requested_paths=(),
        observed_at=NOW,
        source_event_time=None,
        valid_from=None,
        valid_to=None,
        evidence_bindings=(evidence_binding,),
        assertion_input_id=assertion_id,
        assertion_input_kind="shared_source_relationship_assertion",
        decision_input_id=decision_input_id,
    )
    assertion = RelationshipAssertion(
        assertion_id=assertion_id,
        relationship_type_id=candidate.relationship_type_id,
        relationship_type_version=candidate.relationship_type_version,
        source_record_id=SOURCE_RECORD_ID,
        source_endpoint=IdentityReference(
            identity_id="professor-source",
            identity_space=IdentitySpace.source,
            entity_type="professor",
        ),
        target_endpoint=IdentityReference(
            identity_id="company-source",
            identity_space=IdentitySpace.source,
            entity_type="company",
        ),
        attributes={
            "candidate_id": candidate_id,
            "evidence_refs": list(evidence_refs),
            "evidence_metadata": {"fixture": "shared-ledger"},
            "role_bindings": {"founder": source_endpoint.stable_reference},
        },
        observed_at=NOW,
        source_event_time=None,
        valid_from=None,
        valid_to=None,
        assertion_run_id="shared-relationship-assertion-run",
    )
    policy = PolicyReference(
        policy_id="relationship-projection-policy",
        policy_version="relationship-v1",
        policy_kind=PolicyKind.relationship,
        content_sha256=_fingerprint("relationship-projection-policy"),
        effective_at=NOW - timedelta(days=1),
    )
    decision_input = RelationshipDecisionInput(
        decision_input_id=decision_input_id,
        decision_id="shared-relationship-decision",
        canonical_relationship_id="canonical-relationship:shared-professor-company",
        state="accepted",
        candidate_assertion_ids=(assertion_id,),
        selected_assertion_ids=(assertion_id,),
        conflicting_assertion_ids=(),
        role_bindings=candidate.role_bindings,
        selected_evidence_refs=evidence_refs,
        policy=policy,
        method=DecisionMethod.deterministic,
        method_version="relationship-v1",
        confidence=1.0,
        rationale="Shared Canonical V2 relationship ledger fixture.",
    )
    return RelationshipProjectionRequest(
        catalog=RelationshipCatalogIdentity(
            schema_version=CATALOG_SCHEMA_VERSION,
            catalog_version=CATALOG_VERSION,
            content_sha256=CATALOG_CONTENT_SHA256,
        ),
        release_id=RELEASE_ID,
        projection_run_id=PROJECTION_RUN_ID,
        as_of=NOW,
        decision_policy=policy,
        domain_projections=(
            _domain_projection("company", "company-c1"),
            _domain_projection("professor", "professor-c1"),
        ),
        candidates=(candidate,),
        relationship_assertions=(assertion,),
        typed_relationship_assertions=(),
        source_canonical_assignments=(
            SourceCanonicalAssignment(
                assignment_id="assignment:shared-professor",
                source_identity_id="professor-source",
                canonical_identity_id="professor-c1",
                entity_type="professor",
                source_record_refs=(SOURCE_RECORD_ID,),
            ),
            SourceCanonicalAssignment(
                assignment_id="assignment:shared-company",
                source_identity_id="company-source",
                canonical_identity_id="company-c1",
                entity_type="company",
                source_record_refs=(SOURCE_RECORD_ID,),
            ),
        ),
        decision_inputs=(decision_input,),
        retained_assertions=(retained_reference,),
        retained_artifacts=(retained_artifact,),
    )


def _insert_shared_ledger(
    target: _Target,
    request: RelationshipProjectionRequest,
    result: Any,
    *,
    tamper_assertion_row: bool = False,
) -> None:
    assertion = request.relationship_assertions[0]
    decision = result.relationship_decisions[0]
    relationship_type = next(
        item
        for item in result.relationship_types
        if item.relationship_type_id == assertion.relationship_type_id
    )
    canonical_contexts = [
        {
            "canonical_identity_id": assignment.canonical_identity_id,
            "entity_type": assignment.entity_type,
            "state": "active",
            "source_identity_ids": [assignment.source_identity_id],
        }
        for assignment in request.source_canonical_assignments
    ]
    source_contexts = [
        {
            "source_identity_id": assignment.source_identity_id,
            "source_system": f"fixture:{assignment.entity_type}",
            "source_key": assignment.source_identity_id,
            "entity_type": assignment.entity_type,
            "normalized_keys": {"fixture": assignment.source_identity_id},
            "first_observed_at": (NOW - timedelta(days=1)).isoformat(),
            "last_observed_at": NOW.isoformat(),
            "state": "active",
        }
        for assignment in request.source_canonical_assignments
    ]
    context_payload = {
        "canonical_identity_contexts": canonical_contexts,
        "source_identity_contexts": source_contexts,
    }
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.policy "
            "(policy_id, policy_version, policy_kind, content_sha256, effective_at) "
            "VALUES ('identity-policy', 'v1', 'identity', %s, %s), "
            "(%s, %s, 'relationship', %s, %s)",
            (
                _fingerprint("identity-policy"),
                NOW - timedelta(days=1),
                request.decision_policy.policy_id,
                request.decision_policy.policy_version,
                request.decision_policy.content_sha256,
                request.decision_policy.effective_at,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_resolution_run "
            "(release_id, decision_run_id, identity_method_version, as_of, "
            "policy_id, policy_version, build_authority, request_content, "
            "request_content_sha256, result_content, result_content_sha256) "
            "VALUES (%s, %s, 'identity-v1', %s, 'identity-policy', 'v1', "
            "'offline_canonical_build', %s, %s, %s, %s)",
            (
                RELEASE_ID,
                PROJECTION_RUN_ID,
                NOW,
                Jsonb({"fixture": "shared identity request"}),
                _fingerprint("shared-identity-request"),
                Jsonb({"fixture": "shared identity result"}),
                _fingerprint("shared-identity-result"),
            ),
        )
        for assignment in request.source_canonical_assignments:
            connection.execute(
                "INSERT INTO knowledge.source_identity "
                "(source_identity_id, source_system, source_key, entity_type, "
                "normalized_keys, first_observed_at, last_observed_at, state) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, 'active')",
                (
                    assignment.source_identity_id,
                    f"fixture:{assignment.entity_type}",
                    assignment.source_identity_id,
                    assignment.entity_type,
                    Jsonb({"fixture": assignment.source_identity_id}),
                    NOW - timedelta(days=1),
                    NOW,
                ),
            )
            connection.execute(
                "INSERT INTO knowledge.source_identity_record "
                "(source_identity_id, record_id) VALUES (%s, %s)",
                (assignment.source_identity_id, SOURCE_RECORD_ID),
            )
            identity_decision_id = (
                f"identity-decision:{assignment.canonical_identity_id}"
            )
            identity_assertion_id = (
                f"identity-assertion:{assignment.canonical_identity_id}"
            )
            connection.execute(
                "INSERT INTO knowledge.source_assertion "
                "(assertion_id, source_record_id, source_identity_id, "
                "subject_entity_type, field_path, value, "
                "assertion_fingerprint_sha256, observed_at, assertion_run_id) "
                "VALUES (%s, %s, %s, %s, 'identity.fixture', %s, %s, %s, %s)",
                (
                    identity_assertion_id,
                    SOURCE_RECORD_ID,
                    assignment.source_identity_id,
                    assignment.entity_type,
                    Jsonb(assignment.canonical_identity_id),
                    _fingerprint(identity_assertion_id),
                    NOW,
                    PROJECTION_RUN_ID,
                ),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision "
                "(release_id, decision_id, action, policy_id, policy_version, method, "
                "method_version, decision_run_id, confidence, rationale, decided_at) "
                "VALUES (%s, %s, 'create', 'identity-policy', 'v1', "
                "'deterministic', 'identity-v1', %s, 1.0, 'shared fixture', %s)",
                (RELEASE_ID, identity_decision_id, PROJECTION_RUN_ID, NOW),
            )
            connection.execute(
                "INSERT INTO knowledge.canonical_identity "
                "(release_id, canonical_identity_id, entity_type, state, display_name, "
                "identity_decision_id) VALUES (%s, %s, %s, 'active', %s, %s)",
                (
                    RELEASE_ID,
                    assignment.canonical_identity_id,
                    assignment.entity_type,
                    assignment.canonical_identity_id,
                    identity_decision_id,
                ),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_source_identity "
                "(release_id, decision_id, source_identity_id) VALUES (%s, %s, %s)",
                (RELEASE_ID, identity_decision_id, assignment.source_identity_id),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_output "
                "(release_id, decision_id, canonical_identity_id) VALUES (%s, %s, %s)",
                (RELEASE_ID, identity_decision_id, assignment.canonical_identity_id),
            )
            context_sha256 = _fingerprint(
                f"identity-context:{assignment.canonical_identity_id}"
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_context "
                "(release_id, decision_id, decision_run_id, context_content, "
                "content_sha256, supporting_assertion_ids) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    RELEASE_ID,
                    identity_decision_id,
                    PROJECTION_RUN_ID,
                    Jsonb({"content_sha256": context_sha256}),
                    context_sha256,
                    Jsonb([identity_assertion_id]),
                ),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_record "
                "(release_id, decision_id, record_id) VALUES (%s, %s, %s)",
                (RELEASE_ID, identity_decision_id, SOURCE_RECORD_ID),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_assertion "
                "(release_id, decision_id, assertion_id, source_identity_id, "
                "source_record_id) VALUES (%s, %s, %s, %s, %s)",
                (
                    RELEASE_ID,
                    identity_decision_id,
                    identity_assertion_id,
                    assignment.source_identity_id,
                    SOURCE_RECORD_ID,
                ),
            )
            connection.execute(
                "INSERT INTO knowledge.canonical_identity_source_membership "
                "(release_id, canonical_identity_id, source_identity_id) "
                "VALUES (%s, %s, %s)",
                (
                    RELEASE_ID,
                    assignment.canonical_identity_id,
                    assignment.source_identity_id,
                ),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_output_source "
                "(release_id, decision_id, canonical_identity_id, source_identity_id) "
                "VALUES (%s, %s, %s, %s)",
                (
                    RELEASE_ID,
                    identity_decision_id,
                    assignment.canonical_identity_id,
                    assignment.source_identity_id,
                ),
            )
            connection.execute(
                "INSERT INTO knowledge.current_source_identity_assignment "
                "(release_id, source_identity_id, canonical_identity_id, "
                "identity_decision_id) VALUES (%s, %s, %s, %s)",
                (
                    RELEASE_ID,
                    assignment.source_identity_id,
                    assignment.canonical_identity_id,
                    identity_decision_id,
                ),
            )
        connection.execute(
            "INSERT INTO knowledge.relationship_type "
            "(relationship_type_id, version, layer, source_entity_types, "
            "target_entity_types, direction, roles, required_evidence_kinds, "
            "time_semantics, allowed_states, eligible_paths) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                relationship_type.relationship_type_id,
                relationship_type.version,
                relationship_type.layer.value,
                Jsonb(list(relationship_type.source_entity_types)),
                Jsonb(list(relationship_type.target_entity_types)),
                relationship_type.direction.value,
                Jsonb(
                    [role.model_dump(mode="json") for role in relationship_type.roles]
                ),
                Jsonb(list(relationship_type.required_evidence_kinds)),
                relationship_type.time_semantics.value,
                Jsonb(list(relationship_type.allowed_states)),
                Jsonb(list(relationship_type.eligible_paths)),
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.relationship_assertion "
            "(assertion_id, relationship_type_id, relationship_type_version, "
            "source_record_id, source_identity_id, target_identity_id, attributes, "
            "assertion_fingerprint_sha256, observed_at, source_event_time, "
            "valid_from_temporal, valid_to_temporal, assertion_run_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                assertion.assertion_id,
                assertion.relationship_type_id,
                assertion.relationship_type_version,
                assertion.source_record_id,
                assertion.source_endpoint.identity_id,
                assertion.target_endpoint.identity_id,
                Jsonb(
                    {"tampered": True} if tamper_assertion_row else assertion.attributes
                ),
                _canonical_sha256(assertion.model_dump(mode="json")),
                assertion.observed_at,
                assertion.source_event_time,
                None,
                None,
                assertion.assertion_run_id,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.relationship_decision "
            "(release_id, decision_id, canonical_relationship_id, "
            "relationship_type_id, relationship_type_version, "
            "source_canonical_identity_id, target_canonical_identity_id, state, "
            "role_bindings, policy_id, policy_version, method, method_version, "
            "decision_run_id, confidence, rationale, valid_from_temporal, "
            "valid_to_temporal, decided_at, supersedes_decision_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
            "%s, %s, %s, %s, %s, %s, %s)",
            (
                decision.release_id,
                decision.decision_id,
                decision.canonical_relationship_id,
                decision.relationship_type_id,
                decision.relationship_type_version,
                decision.source_canonical_identity_id,
                decision.target_canonical_identity_id,
                decision.state.value,
                Jsonb(decision.role_bindings),
                decision.policy.policy_id,
                decision.policy.policy_version,
                decision.method.value,
                decision.method_version,
                decision.decision_run_id,
                decision.confidence,
                decision.rationale,
                None,
                None,
                decision.decided_at,
                decision.supersedes_decision_id,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.relationship_decision_identity_context "
            "(release_id, decision_id, canonical_identity_contexts, "
            "source_identity_contexts, content_sha256) VALUES (%s, %s, %s, %s, %s)",
            (
                RELEASE_ID,
                decision.decision_id,
                Jsonb(canonical_contexts),
                Jsonb(source_contexts),
                _canonical_sha256(context_payload),
            ),
        )
        for role in ("candidate", "selected"):
            connection.execute(
                "INSERT INTO knowledge.relationship_decision_assertion "
                "(release_id, decision_id, assertion_id, assertion_role) "
                "VALUES (%s, %s, %s, %s)",
                (RELEASE_ID, decision.decision_id, assertion.assertion_id, role),
            )
        connection.execute(
            "INSERT INTO knowledge.relationship_decision_constraint_outcome "
            "(release_id, decision_id, assertion_id, admitted, reason_codes) "
            "VALUES (%s, %s, %s, TRUE, '[]'::jsonb)",
            (RELEASE_ID, decision.decision_id, assertion.assertion_id),
        )
        connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        connection.commit()


def _store(target: _Target) -> Any:
    return _module().create_postgres_relationship_projection_store(
        database_url=target.database_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
    )


def _counts(target: _Target) -> tuple[int, ...]:
    with _connect(target) as connection:
        return connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.relationship_projection_run), "
            "(SELECT count(*) FROM knowledge.typed_relationship_assertion), "
            "(SELECT count(*) FROM knowledge.typed_relationship_decision), "
            "(SELECT count(*) FROM knowledge.typed_relationship_decision_assertion), "
            "(SELECT count(*) FROM knowledge.relationship_projection_outcome), "
            "(SELECT count(*) FROM knowledge.current_relationship_projection), "
            "(SELECT count(*) FROM knowledge.relationship_assertion), "
            "(SELECT count(*) FROM knowledge.relationship_decision)"
        ).fetchone()


def _set_database_marker(target: _Target, marker: str) -> None:
    with _connect(target, autocommit=True) as connection:
        connection.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(target.expected_database),
                sql.Literal(marker),
            )
        )


def test_postgres_store_requires_complete_explicit_target_identity() -> None:
    module = _module()

    signature = inspect.signature(module.create_postgres_relationship_projection_store)

    assert tuple(signature.parameters) == (
        "database_url",
        "expected_database",
        "target_kind",
        "backup_gate_root",
    )
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and parameter.default is inspect.Parameter.empty
        for parameter in signature.parameters.values()
    )


def test_c2_0010_empty_downgrade_and_upgrade_cycle(target: _Target) -> None:
    command.downgrade(target.config, PREVIOUS_REVISION)
    with _connect(target, autocommit=True) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == (PREVIOUS_REVISION,)
        assert connection.execute(
            "SELECT to_regclass('knowledge.relationship_projection_run')"
        ).fetchone() == (None,)
    command.upgrade(target.config, EXPECTED_REVISION)


def test_store_rejects_an_incomplete_c2_0010_schema(target: _Target) -> None:
    with _connect(target, autocommit=True) as connection:
        connection.execute("DROP TABLE knowledge.relationship_projection_outcome")

    with pytest.raises(
        _module().RelationshipProjectionPersistenceError,
        match="schema is incomplete",
    ):
        _store(target)


def test_typed_relationship_batch_round_trips_replays_and_restarts(
    target: _Target,
) -> None:
    _seed_prerequisites(target)
    request = _projection_request()
    result = create_ephemeral_relationship_projection().project(request)
    store = _store(target)

    durable = store.persist(request, result)

    assert durable == result
    assert store.load(RELEASE_ID, PROJECTION_RUN_ID) == result
    assert _counts(target) == (1, 1, 1, 2, 1, 1, 0, 0)
    assert store.persist(request, result) == result
    assert _counts(target) == (1, 1, 1, 2, 1, 1, 0, 0)
    restarted = _store(target)
    assert restarted.load(RELEASE_ID, PROJECTION_RUN_ID) == result

    changed_retained = request.retained_assertions[0].model_copy(
        update={"source_record_ref": "source-record:same-result-different-lineage"}
    )
    request_only_changed = request.model_copy(
        update={"retained_assertions": (changed_retained,)}
    )
    same_result = create_ephemeral_relationship_projection().project(
        request_only_changed
    )
    assert same_result == result
    with pytest.raises(
        _module().RelationshipProjectionPersistenceError,
        match="request content",
    ):
        store.persist(request_only_changed, same_result)

    changed_request = _projection_request(rationale="changed replay content")
    changed_result = create_ephemeral_relationship_projection().project(changed_request)
    with pytest.raises(
        _module().RelationshipProjectionPersistenceError,
        match="cannot identify changed request content",
    ):
        store.persist(changed_request, changed_result)
    assert _counts(target) == (1, 1, 1, 2, 1, 1, 0, 0)


def test_shared_relationship_batch_reuses_existing_canonical_ledgers(
    target: _Target,
) -> None:
    _seed_prerequisites(target)
    request = _shared_projection_request()
    result = create_ephemeral_relationship_projection().project(request)
    assert len(result.relationship_decisions) == 1
    assert result.typed_relationship_decisions == ()
    _insert_shared_ledger(target, request, result)
    with _connect(target) as connection:
        before = connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.relationship_assertion), "
            "(SELECT count(*) FROM knowledge.relationship_decision)"
        ).fetchone()

    assert _store(target).persist(request, result) == result
    assert _store(target).load(RELEASE_ID, PROJECTION_RUN_ID) == result

    with _connect(target) as connection:
        after = connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.relationship_assertion), "
            "(SELECT count(*) FROM knowledge.relationship_decision), "
            "(SELECT count(*) FROM "
            "knowledge.relationship_projection_shared_assertion), "
            "(SELECT count(*) FROM "
            "knowledge.relationship_projection_shared_decision), "
            "(SELECT count(*) FROM knowledge.current_relationship_projection)"
        ).fetchone()
    assert before == (1, 1)
    assert after == (1, 1, 1, 1, 1)


def test_shared_assertion_requires_exact_durable_content_not_only_its_hash(
    target: _Target,
) -> None:
    _seed_prerequisites(target)
    request = _shared_projection_request()
    result = create_ephemeral_relationship_projection().project(request)
    _insert_shared_ledger(
        target,
        request,
        result,
        tamper_assertion_row=True,
    )

    with pytest.raises(
        _module().RelationshipProjectionPersistenceError,
        match="assertion is not already durable exactly",
    ):
        _store(target).persist(request, result)


def test_restart_rejects_result_payload_cross_wired_to_another_run(
    target: _Target,
) -> None:
    _seed_prerequisites(target)
    request = _projection_request()
    result = create_ephemeral_relationship_projection().project(request)
    _store(target).persist(request, result)
    provisional = result.model_copy(
        update={
            "projection_run_id": "cross-wired-projection-run",
            "content_sha256": "0" * 64,
        }
    )
    tampered = result.__class__.model_validate(
        {
            **provisional.model_dump(mode="python"),
            "content_sha256": _canonical_sha256(
                provisional.model_dump(mode="json", exclude={"content_sha256"})
            ),
        }
    )
    with _connect(target, autocommit=True) as connection:
        connection.execute(
            "ALTER TABLE knowledge.relationship_projection_run "
            "DISABLE TRIGGER trg_reject_mutation"
        )
        try:
            connection.execute(
                "UPDATE knowledge.relationship_projection_run "
                "SET result_payload = %s, result_content_sha256 = %s "
                "WHERE release_id = %s AND projection_run_id = %s",
                (
                    Jsonb(tampered.model_dump(mode="json")),
                    tampered.content_sha256,
                    RELEASE_ID,
                    PROJECTION_RUN_ID,
                ),
            )
        finally:
            connection.execute(
                "ALTER TABLE knowledge.relationship_projection_run "
                "ENABLE TRIGGER trg_reject_mutation"
            )

    with pytest.raises(
        _module().RelationshipProjectionPersistenceError,
        match="run envelope",
    ):
        _store(target).load(RELEASE_ID, PROJECTION_RUN_ID)


def test_concurrent_exact_replay_converges_to_one_batch(target: _Target) -> None:
    _seed_prerequisites(target)
    request = _projection_request()
    result = create_ephemeral_relationship_projection().project(request)
    store = _store(target)

    with ThreadPoolExecutor(max_workers=2) as executor:
        durable = tuple(
            executor.map(
                lambda _: store.persist(request, result),
                range(2),
            )
        )

    assert durable == (result, result)
    assert _counts(target) == (1, 1, 1, 2, 1, 1, 0, 0)


def test_failed_typed_insert_rolls_back_complete_batch(target: _Target) -> None:
    _seed_prerequisites(target)
    request = _projection_request()
    missing_record_assertion = request.typed_relationship_assertions[0].model_copy(
        update={"source_record_ref": "source-record:missing"}
    )
    invalid_request = request.model_copy(
        update={"typed_relationship_assertions": (missing_record_assertion,)}
    )
    result = create_ephemeral_relationship_projection().project(invalid_request)

    with pytest.raises(
        _module().RelationshipProjectionPersistenceError,
        match="verification or transaction failed",
    ):
        _store(target).persist(invalid_request, result)

    assert _counts(target) == (0, 0, 0, 0, 0, 0, 0, 0)
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT count(*) FROM knowledge.relationship_type"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM knowledge.policy WHERE policy_kind = 'relationship'"
        ).fetchone() == (0,)


def test_retained_artifact_content_must_match_durable_landing_lineage(
    target: _Target,
) -> None:
    _seed_prerequisites(target)
    request = _projection_request()
    wrong_artifact = request.retained_artifacts[0].model_copy(
        update={"content_sha256": "0" * 64}
    )
    invalid_request = request.model_copy(
        update={"retained_artifacts": (wrong_artifact,)}
    )
    result = create_ephemeral_relationship_projection().project(invalid_request)

    with pytest.raises(
        _module().RelationshipProjectionPersistenceError,
        match="retained artifact is not durable exactly",
    ):
        _store(target).persist(invalid_request, result)

    assert _counts(target) == (0, 0, 0, 0, 0, 0, 0, 0)


def test_persisted_relationship_rows_are_append_only_candidate_scoped(
    target: _Target,
) -> None:
    _seed_prerequisites(target)
    request = _projection_request()
    result = create_ephemeral_relationship_projection().project(request)
    _store(target).persist(request, result)

    with _connect(target) as connection:
        with pytest.raises(psycopg.Error, match="append-only"):
            connection.execute(
                "UPDATE knowledge.typed_relationship_assertion "
                "SET assertion_run_id = 'mutated'"
            )
        connection.rollback()
        with pytest.raises(psycopg.Error, match="append-only"):
            connection.execute("DELETE FROM knowledge.relationship_projection_outcome")
        connection.rollback()
        with pytest.raises(psycopg.Error, match="append-only"):
            connection.execute("TRUNCATE knowledge.current_relationship_projection")
        connection.rollback()
        connection.execute(
            "UPDATE knowledge.release SET state = 'active' WHERE release_id = %s",
            (RELEASE_ID,),
        )
        connection.commit()
        with pytest.raises(psycopg.Error, match="candidate release"):
            connection.execute(
                "INSERT INTO knowledge.relationship_projection_outcome "
                "(release_id, projection_run_id, candidate_id, "
                "relationship_type_id, admitted, outcome_payload, content_sha256) "
                "VALUES (%s, %s, 'late', 'artifact_derived_from_artifact', true, "
                "%s, %s)",
                (
                    RELEASE_ID,
                    PROJECTION_RUN_ID,
                    Jsonb({"candidate_id": "late"}),
                    _fingerprint("late-outcome"),
                ),
            )
        connection.rollback()
        with pytest.raises(psycopg.Error, match="candidate release"):
            connection.execute(
                "INSERT INTO knowledge.relationship_decision "
                "(release_id, decision_id, canonical_relationship_id, "
                "relationship_type_id, relationship_type_version, "
                "source_canonical_identity_id, target_canonical_identity_id, state, "
                "role_bindings, policy_id, policy_version, method, method_version, "
                "decision_run_id, confidence, rationale, decided_at) "
                "VALUES (%s, 'late-shared-decision', 'late-shared-relationship', "
                "'artifact_derived_from_artifact', "
                "'canonical-v2-relationship-v1', 'late-source', 'late-target', "
                "'accepted', '{}'::jsonb, 'relationship-projection-policy', "
                "'relationship-v1', 'deterministic', 'relationship-v1', "
                "'late-run', 1.0, 'must stay candidate scoped', %s)",
                (RELEASE_ID, NOW),
            )
        connection.rollback()
        with pytest.raises(psycopg.Error, match="candidate release"):
            connection.execute(
                "INSERT INTO knowledge.relationship_decision_assertion "
                "(release_id, decision_id, assertion_id, assertion_role) "
                "VALUES (%s, 'late-shared-decision', 'late-assertion', 'candidate')",
                (RELEASE_ID,),
            )
        connection.rollback()

    with pytest.raises(sa_exc.DBAPIError, match="requires empty"):
        command.downgrade(target.config, PREVIOUS_REVISION)


def test_store_fails_closed_on_target_and_backup_identity(
    target: _Target,
    tmp_path: Path,
) -> None:
    module = _module()
    with pytest.raises(
        module.RelationshipProjectionPersistenceError,
        match="target selection failed",
    ):
        module.create_postgres_relationship_projection_store(
            database_url=target.database_url,
            expected_database=f"{target.expected_database}_wrong",
            target_kind=target.target_kind,
            backup_gate_root=target.backup_gate_root,
        )
    with pytest.raises(
        module.RelationshipProjectionPersistenceError,
        match="target selection failed|restricted to a disposable target",
    ):
        module.create_postgres_relationship_projection_store(
            database_url=target.database_url,
            expected_database=target.expected_database,
            target_kind="production",
            backup_gate_root=target.backup_gate_root,
        )
    with pytest.raises(RebuildWriteGateError):
        module.create_postgres_relationship_projection_store(
            database_url=target.database_url,
            expected_database=target.expected_database,
            target_kind=target.target_kind,
            backup_gate_root=tmp_path,
        )

    valid_marker = (
        f"miroflow:destructive-target:v1:disposable:{target.expected_database}"
    )
    _set_database_marker(target, "miroflow:wrong-marker")
    try:
        with pytest.raises(
            module.RelationshipProjectionPersistenceError,
            match="target identity is invalid",
        ):
            module.create_postgres_relationship_projection_store(
                database_url=target.database_url,
                expected_database=target.expected_database,
                target_kind=target.target_kind,
                backup_gate_root=target.backup_gate_root,
            )
    finally:
        _set_database_marker(target, valid_marker)


def test_database_endpoint_validator_rejects_unpersisted_typed_subobject(
    target: _Target,
) -> None:
    _seed_prerequisites(target)
    endpoint = {
        "reference_kind": "typed_subobject",
        "endpoint_type": "product",
        "stable_reference": "subobject:product:missing",
        "canonical_identity_id": None,
        "parent_canonical_identity_ref": "canonical:company:missing",
        "lineage_family": None,
        "subject_reference": None,
        "subject_entity_type": None,
    }
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT knowledge.relationship_endpoint_exists(%s, %s)",
            (RELEASE_ID, Jsonb(endpoint)),
        ).fetchone() == (False,)
