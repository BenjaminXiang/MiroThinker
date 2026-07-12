from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from importlib import import_module
import json
import os
from pathlib import Path
from typing import Any, LiteralString, cast

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from pydantic import BaseModel
from pydantic import JsonValue
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from sqlalchemy import exc as sa_exc
from sqlalchemy.engine import make_url

from src.data_agents.canonical_v2.contracts import CanonicalDecision
from src.data_agents.canonical_v2.contracts import CanonicalIdentity
from src.data_agents.canonical_v2.contracts import PolicyDecision
from src.data_agents.canonical_v2.contracts import PolicyKind
from src.data_agents.canonical_v2.contracts import PolicyOutcome
from src.data_agents.canonical_v2.contracts import PolicyReference
from src.data_agents.canonical_v2.contracts import SourceAssertion
from src.data_agents.canonical_v2.contracts import SourceIdentity
from src.data_agents.storage.database_target import set_alembic_database_url


APP_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = APP_ROOT / "canonical_v2_alembic.ini"
SCRIPT_LOCATION = APP_ROOT / "canonical_v2_alembic"
CATALOG_EVIDENCE_PATH = (
    REPO_ROOT
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform/s6/domain-catalog-v1.json"
)
TARGET_MODULE = "src.data_agents.canonical_v2.domain_projection_postgres"
PROJECTION_MODULE = "src.data_agents.canonical_v2.domain_projection"
EXPECTED_REVISION = "C2_0008"
PREVIOUS_REVISION = "C2_0007"
RELEASE_ID = "domain-projection-release-r1"
BUILD_RUN_ID = "domain-projection-build-r1"
DECISION_RUN_ID = "domain-projection-decisions-r1"
NOW = datetime(2026, 7, 12, 18, 30, tzinfo=timezone.utc)
RED_REASON = (
    "Task 6.3 RED: C2_0008 and durable typed domain projections are not implemented"
)


class _MissingTargetSurface(RuntimeError):
    """Exact RED sentinel; nested import and migration defects fail normally."""


pytestmark = pytest.mark.xfail(
    strict=True,
    raises=_MissingTargetSurface,
    reason=RED_REASON,
)


@dataclass(frozen=True, slots=True)
class _Target:
    database_url: str
    expected_database: str
    target_kind: str
    backup_gate_root: Path
    config: Config


@dataclass(frozen=True, slots=True)
class _ProjectionGraph:
    identities: tuple[CanonicalIdentity, ...]
    source_identities: tuple[SourceIdentity, ...]
    field_assertions: tuple[SourceAssertion, ...]
    field_decisions: tuple[CanonicalDecision, ...]
    inclusion_decisions: tuple[PolicyDecision, ...]


def _postgres_module() -> Any:
    try:
        return import_module(TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != TARGET_MODULE:
            raise AssertionError(
                f"{TARGET_MODULE} has an unexpected missing dependency: {exc.name}"
            ) from exc
        raise _MissingTargetSurface(
            f"exact target module is absent: {TARGET_MODULE}"
        ) from exc


def _projection_module() -> Any:
    try:
        return import_module(PROJECTION_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != PROJECTION_MODULE:
            raise AssertionError(
                f"{PROJECTION_MODULE} has an unexpected missing dependency: {exc.name}"
            ) from exc
        raise AssertionError(
            "domain_projection_postgres exists without its required domain_projection "
            "contract"
        ) from exc


def _scripts() -> ScriptDirectory:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    return ScriptDirectory.from_config(config)


def _revision() -> Any:
    try:
        revision = _scripts().get_revision(EXPECTED_REVISION)
    except CommandError as exc:
        if EXPECTED_REVISION not in str(exc):
            raise
        raise _MissingTargetSurface(
            f"exact migration is absent: {EXPECTED_REVISION}"
        ) from exc
    if revision is None:
        raise _MissingTargetSurface(f"exact migration is absent: {EXPECTED_REVISION}")
    return revision


def _accepted_catalog() -> dict[str, Any]:
    value = json.loads(CATALOG_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


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
            "Canonical V2 domain-projection persistence requires all four explicit "
            "CANONICAL_V2_TEST_* settings"
        )
    return cast(tuple[str, str, str, str], values)


def _migration_config(target: _Target) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    set_alembic_database_url(config, target.database_url)
    config.set_main_option("miroflow.expected_database", target.expected_database)
    config.set_main_option("miroflow.target_kind", target.target_kind)
    config.set_main_option("miroflow.backup_gate_root", str(target.backup_gate_root))
    return config


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


def _drop_owned_sibling(
    connection: psycopg.Connection[Any],
    *,
    database_name: str,
    expected_marker: str,
) -> None:
    marker_row = connection.execute(
        "SELECT shobj_description(oid, 'pg_database') "
        "FROM pg_database WHERE datname = %s",
        (database_name,),
    ).fetchone()
    if marker_row is None:
        return
    assert marker_row == (expected_marker,)
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
    _revision()
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

    sibling_name = (
        f"{expected_database[:38]}_s6c_"
        f"{hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:8]}"
    )
    sibling_marker = f"miroflow:destructive-target:v1:disposable:{sibling_name}"
    with psycopg.connect(_psycopg_dsn(database_url), autocommit=True) as admin:
        base_marker = (
            f"miroflow:destructive-target:v1:{target_kind}:{expected_database}"
        )
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
    try:
        command.upgrade(configured.config, EXPECTED_REVISION)
        with _connect(configured, autocommit=True) as connection:
            assert connection.execute(
                "SELECT current_database(), shobj_description(oid, 'pg_database') "
                "FROM pg_database WHERE datname = current_database()"
            ).fetchone() == (sibling_name, sibling_marker)
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


def _connect(target: _Target, *, autocommit: bool = False) -> Any:
    return psycopg.connect(_psycopg_dsn(target.database_url), autocommit=autocommit)


def _store(target: _Target) -> Any:
    module = _postgres_module()
    return module.create_postgres_domain_projection_store(
        database_url=target.database_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
    )


def _hash(value: object) -> str:
    def default(item: object) -> object:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        if isinstance(item, datetime):
            return item.astimezone(timezone.utc).isoformat()
        raise TypeError(f"unsupported canonical JSON value: {type(item).__name__}")

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
        default=default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _field_policy() -> PolicyReference:
    return PolicyReference(
        policy_id="canonical-v2-domain-field-selection",
        policy_version="domain-field-selection-v1",
        policy_kind=PolicyKind.field_selection,
        content_sha256=_hash("domain-field-selection-v1"),
        effective_at=NOW - timedelta(days=1),
    )


def _inclusion_policy(domain: str) -> PolicyReference:
    return PolicyReference(
        policy_id=f"canonical-v2-{domain}-inclusion",
        policy_version=f"{domain}-inclusion-v1",
        policy_kind=PolicyKind.inclusion,
        content_sha256=_hash(f"{domain}-inclusion-v1"),
        effective_at=NOW - timedelta(days=1),
    )


def _identity_request_and_result() -> tuple[Any, Any]:
    module = import_module("src.data_agents.canonical_v2.canonical_identity_resolution")
    identifiers = (
        ("company", "unified_social_credit_code", "91440300S6C000001A"),
        ("paper", "doi", "10.5555/canonical-v2-s6c"),
        ("patent", "publication_number", "CN117873146A"),
        ("professor", "orcid", "0000-0002-1825-0097"),
    )
    sources = tuple(
        module.SourceIdentity(
            source_identity_id=f"source:{domain}",
            source_system="recorded-domain-projection-fixture",
            source_key=f"{domain}:s6c",
            entity_type=domain,
            source_record_ids=(f"record:{domain}",),
            normalized_keys={identifier_key: identifier_value},
            first_observed_at=NOW - timedelta(days=30),
            last_observed_at=NOW,
            state="active",
        )
        for domain, identifier_key, identifier_value in identifiers
    )
    assertions = tuple(
        module.SourceAssertion(
            assertion_id=f"identity-assertion:{domain}",
            source_record_id=f"record:{domain}",
            source_identity_id=f"source:{domain}",
            subject_entity_type=domain,
            field_path=f"identity.{identifier_key}",
            value=identifier_value,
            observed_at=NOW,
            assertion_run_id="domain-projection-identity-assertions",
        )
        for domain, identifier_key, identifier_value in identifiers
    )
    policy = module.PolicyReference(
        policy_id="canonical-v2-domain-projection-identity",
        policy_version="identity-v1",
        policy_kind="identity",
        content_sha256=_hash("domain-projection-identity-v1"),
        effective_at=NOW - timedelta(days=1),
    )
    request = module.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id=BUILD_RUN_ID,
        identity_method_version="canonical-identity-resolution-v1",
        as_of=NOW,
        policy=policy,
        source_identities=sources,
        identity_assertions=assertions,
    )
    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )
    assert {
        identity.entity_type for identity in result.current_canonical_identities
    } == {
        "company",
        "paper",
        "patent",
        "professor",
    }
    return request, result


def _insert_identity_prerequisites(target: _Target, request: Any) -> None:
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO landing.evidence_artifact "
            "(artifact_id, source_kind, source_locator, content_sha256, byte_size, "
            "acquired_at, run_id) VALUES "
            "('domain-projection-artifact', 'recorded_fixture', "
            "'fixture://domain-projection', %s, 4, %s, %s)",
            (_hash("domain-projection-artifact"), NOW, BUILD_RUN_ID),
        )
        connection.execute(
            "INSERT INTO landing.parser_run "
            "(parse_run_id, artifact_id, parser_name, parser_version, schema_version, "
            "run_status, started_at, finished_at) VALUES "
            "('domain-projection-parse', 'domain-projection-artifact', "
            "'recorded_fixture', 'v1', 'domain-projection-source-v1', "
            "'succeeded', %s, %s)",
            (NOW, NOW),
        )
        for ordinal, source in enumerate(request.source_identities):
            record_id = source.source_record_ids[0]
            connection.execute(
                "INSERT INTO landing.source_record "
                "(record_id, artifact_id, source_batch_id, record_locator, "
                "parse_run_id, record_ordinal, parse_status, payload, parsed_at) "
                "VALUES (%s, 'domain-projection-artifact', "
                "'domain-projection-source-batch', %s, 'domain-projection-parse', "
                "%s, 'parsed', %s, %s)",
                (
                    record_id,
                    f"row:{ordinal}",
                    ordinal,
                    Jsonb({"domain": source.entity_type}),
                    NOW,
                ),
            )
        connection.execute(
            "INSERT INTO knowledge.release "
            "(release_id, build_run_id, state, manifest_sha256, created_at) "
            "VALUES (%s, %s, 'candidate', %s, %s)",
            (RELEASE_ID, BUILD_RUN_ID, _hash("release-manifest"), NOW),
        )
        connection.execute(
            "INSERT INTO knowledge.policy "
            "(policy_id, policy_version, policy_kind, content_sha256, effective_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                request.policy.policy_id,
                request.policy.policy_version,
                request.policy.policy_kind.value,
                request.policy.content_sha256,
                request.policy.effective_at,
            ),
        )
        connection.commit()


def _persist_identity_graph(target: _Target) -> Any:
    request, result = _identity_request_and_result()
    _insert_identity_prerequisites(target, request)
    module = import_module("src.data_agents.canonical_v2.canonical_identity_postgres")
    store = module.create_postgres_canonical_identity_store(
        database_url=target.database_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
        build_authority="offline_canonical_build",
    )
    assert store.persist(request, result) == result
    return result


def _required_field_values(domain: str, canonical_id: str) -> dict[str, JsonValue]:
    common: dict[str, JsonValue] = {
        "evidence": [f"evidence:{domain}"],
        "id": canonical_id,
        "last_updated": NOW.isoformat(),
        "quality_status": "source_grounded_partial",
        "run_id": BUILD_RUN_ID,
    }
    domain_values: dict[str, dict[str, JsonValue]] = {
        "company": {
            "key_personnel": [
                {
                    "name": "Lin Qiming",
                    "role": "Founder",
                    "description": "Recorded fixture person",
                }
            ],
            "name": "Shenzhen Projection Technology Co., Ltd.",
            "normalized_name": "shenzhen projection technology",
            "profile_summary": "Typed Company fixture.",
            "technology_route_summary": "Evidence-bound projection systems.",
        },
        "paper": {
            "authors": [
                {
                    "name": "Chen Yan",
                    "author_order": 1,
                    "orcid": "0000-0002-1825-0097",
                    "affiliations": ["Shenzhen Projection University"],
                }
            ],
            "title": "Deterministic Typed Domain Projections",
            "venue": "Canonical Systems Journal",
            "year": 2026,
        },
        "patent": {
            "applicants": [
                {
                    "name": "Shenzhen Projection Technology Co., Ltd.",
                    "applicant_order": 1,
                }
            ],
            "summary_text": "A source-grounded typed projection technique.",
            "title": "Typed Knowledge Projection Method",
        },
        "professor": {
            "canonical_name_zh": "陈妍",
            "company_roles": [],
            "department": "Computer Science",
            "email": "chen.yan@example.edu",
            "homepage": "https://example.edu/chen-yan",
            "institution": "Shenzhen Projection University",
            "name": "陈妍",
            "paper_summary": "Research on deterministic knowledge systems.",
            "patent_ids": [],
            "patent_summary": "No additional accepted Patent enrichment.",
            "profile_summary": "Typed Professor fixture.",
            "projects": [
                {
                    "name": "Canonical V2",
                    "funder": "Shenzhen Research Fund",
                    "role": "Principal investigator",
                    "valid_from": "2025-01-01",
                    "valid_to": "2027-12-31",
                }
            ],
            "research_directions": ["knowledge representation"],
            "title": "Professor",
        },
    }
    return {**common, **domain_values[domain]}


def _decision_result(identity_result: Any) -> Any:
    module = import_module("src.data_agents.canonical_v2.canonical_decision_engine")
    source_by_domain = {
        source.entity_type: source for source in identity_result.source_identities
    }
    identities = identity_result.current_canonical_identities
    assertions: list[Any] = []
    groups: list[Any] = []
    policy = _field_policy()
    for identity in identities:
        source = source_by_domain[identity.entity_type]
        for field_path, value in sorted(
            _required_field_values(
                identity.entity_type,
                identity.canonical_identity_id,
            ).items()
        ):
            assertion = module.SourceAssertion(
                assertion_id=f"field-assertion:{identity.entity_type}:{field_path}",
                source_record_id=source.source_record_ids[0],
                source_identity_id=source.source_identity_id,
                subject_entity_type=identity.entity_type,
                field_path=field_path,
                value=value,
                observed_at=NOW,
                assertion_run_id="domain-projection-field-assertions",
            )
            assertions.append(assertion)
            groups.append(
                module.FieldAssertionGroup(
                    canonical_identity_id=identity.canonical_identity_id,
                    field_path=field_path,
                    assertions=(assertion,),
                    policy=policy,
                )
            )
    request = module.DecisionBatchRequest(
        release_id=RELEASE_ID,
        decision_run_id=DECISION_RUN_ID,
        decision_method_version="canonical-decision-v1",
        as_of=NOW,
        source_identities=identity_result.source_identities,
        canonical_identities=identities,
        field_groups=tuple(reversed(groups)),
    )
    result = module.create_ephemeral_canonical_decision_engine().decide(request)
    assert len(result.field_assertions) == len(assertions)
    return result


def _persist_decision_graph(target: _Target, identity_result: Any) -> Any:
    result = _decision_result(identity_result)
    module = import_module("src.data_agents.canonical_v2.canonical_decision_postgres")
    store = module.create_postgres_canonical_decision_store(
        database_url=target.database_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
    )
    assert store.persist(result) == result
    return result


def _prepare_graph(target: _Target) -> _ProjectionGraph:
    identity_result = _persist_identity_graph(target)
    decision_result = _persist_decision_graph(target, identity_result)
    assertions_by_identity: dict[str, list[str]] = {}
    for decision in decision_result.canonical_decisions:
        assertions_by_identity.setdefault(decision.canonical_identity_id, []).extend(
            decision.selected_assertion_ids
        )
    inclusion = tuple(
        PolicyDecision(
            decision_id=f"inclusion:{identity.canonical_identity_id}",
            policy=_inclusion_policy(identity.entity_type),
            subject_identity_id=identity.canonical_identity_id,
            release_id=RELEASE_ID,
            outcome=PolicyOutcome.admitted,
            supporting_assertion_ids=tuple(
                sorted(assertions_by_identity[identity.canonical_identity_id])
            ),
            evaluated_at=NOW,
        )
        for identity in identity_result.current_canonical_identities
    )
    return _ProjectionGraph(
        identities=identity_result.current_canonical_identities,
        source_identities=identity_result.source_identities,
        field_assertions=decision_result.field_assertions,
        field_decisions=decision_result.canonical_decisions,
        inclusion_decisions=inclusion,
    )


def _model_validate_from_candidates(
    model: type[BaseModel],
    candidates: Mapping[str, object],
) -> BaseModel:
    payload = {
        name: candidates[name]
        for name in model.model_fields
        if name in candidates and name != "content_sha256"
    }
    if "content_sha256" in model.model_fields:
        payload["content_sha256"] = _hash(payload)
    return model.model_validate(payload)


def _representative_subobjects(
    module: Any,
    identities_by_domain: Mapping[str, CanonicalIdentity],
    decisions_by_domain_field: Mapping[tuple[str, str], CanonicalDecision],
    *,
    changed: bool,
) -> tuple[BaseModel, ...]:
    definitions: tuple[tuple[str, str, str, dict[str, object]], ...] = (
        (
            "company",
            "key_personnel",
            "key_personnel",
            {
                "name": "Lin Qiming",
                "role": "Founder",
                "description": "Changed fixture person"
                if changed
                else "Fixture person",
            },
        ),
        (
            "paper",
            "author",
            "authors",
            {
                "name": "Chen Yan",
                "author_order": 1,
                "orcid": "0000-0002-1825-0097",
                "affiliations": ("Shenzhen Projection University",),
            },
        ),
        (
            "patent",
            "applicant",
            "applicants",
            {
                "name": "Shenzhen Projection Technology Co., Ltd.",
                "applicant_order": 1,
                "canonical_company_id": identities_by_domain[
                    "company"
                ].canonical_identity_id,
            },
        ),
        (
            "professor",
            "research_project",
            "projects",
            {
                "name": "Canonical V2",
                "funder": "Shenzhen Research Fund",
                "role": "Principal investigator",
                "valid_from": "2025-01-01",
                "valid_to": "2027-12-31",
            },
        ),
    )
    values: list[BaseModel] = []
    for ordinal, (domain, subobject_type, field_path, members) in enumerate(
        definitions
    ):
        identity = identities_by_domain[domain]
        decision = decisions_by_domain_field[(domain, field_path)]
        model = module.DOMAIN_SUBOBJECT_MODELS[domain][subobject_type]
        candidates: dict[str, object] = {
            **members,
            "subobject_id": f"subobject:{domain}:{subobject_type}:1",
            "projection_id": f"projection:{identity.canonical_identity_id}",
            "parent_projection_id": f"projection:{identity.canonical_identity_id}",
            "release_id": RELEASE_ID,
            "build_run_id": BUILD_RUN_ID,
            "canonical_identity_id": identity.canonical_identity_id,
            "entity_type": domain,
            "domain": domain,
            "subobject_type": subobject_type,
            "ordinal": ordinal,
            "assertion_ids": decision.selected_assertion_ids,
            "decision_ids": (decision.decision_id,),
            "observed_at": NOW,
            "last_updated": NOW,
            "quality_signals": (("changed-after-first-persist",) if changed else ()),
            "projection_schema_version": "canonical-v2-domain-projection-v1",
            "catalog_version": _accepted_catalog()["catalog_version"],
            "catalog_content_sha256": _accepted_catalog()["content_sha256"],
        }
        values.append(_model_validate_from_candidates(model, candidates))
    return tuple(values)


def _projection_result(
    graph: _ProjectionGraph,
    *,
    changed: bool = False,
    reverse: bool = False,
) -> Any:
    """One local adapter point to the independently frozen projection contract."""

    module = _projection_module()
    catalog = _accepted_catalog()
    identities_by_domain = {
        identity.entity_type: identity for identity in graph.identities
    }
    assertions_by_id = {
        assertion.assertion_id: assertion for assertion in graph.field_assertions
    }
    decisions_by_identity: dict[str, list[CanonicalDecision]] = {}
    decisions_by_domain_field: dict[tuple[str, str], CanonicalDecision] = {}
    for decision in graph.field_decisions:
        decisions_by_identity.setdefault(decision.canonical_identity_id, []).append(
            decision
        )
        domain = next(
            identity.entity_type
            for identity in graph.identities
            if identity.canonical_identity_id == decision.canonical_identity_id
        )
        decisions_by_domain_field[(domain, decision.field_path)] = decision
    inclusion_by_identity = {
        decision.subject_identity_id: decision for decision in graph.inclusion_decisions
    }
    root_models = {
        "company": module.CompanyProjection,
        "paper": module.PaperProjection,
        "patent": module.PatentProjection,
        "professor": module.ProfessorProjection,
    }
    roots: dict[str, BaseModel] = {}
    lineages: list[dict[str, object]] = []
    for domain, model in root_models.items():
        identity = identities_by_domain[domain]
        decisions = tuple(
            sorted(
                decisions_by_identity[identity.canonical_identity_id],
                key=lambda decision: decision.field_path,
            )
        )
        selected_values = {
            decision.field_path: assertions_by_id[
                decision.selected_assertion_ids[0]
            ].value
            for decision in decisions
        }
        candidates: dict[str, object] = {
            **selected_values,
            "projection_id": f"projection:{identity.canonical_identity_id}",
            "release_id": RELEASE_ID,
            "build_run_id": BUILD_RUN_ID,
            "canonical_identity_id": identity.canonical_identity_id,
            "entity_type": domain,
            "domain": domain,
            "display_name": (
                selected_values.get("name")
                or selected_values.get("title")
                or selected_values.get("canonical_name_zh")
                or identity.display_name
            ),
            "inclusion_decision_id": inclusion_by_identity[
                identity.canonical_identity_id
            ].decision_id,
            "assertion_ids": tuple(
                sorted(
                    assertion_id
                    for decision in decisions
                    for assertion_id in decision.selected_assertion_ids
                )
            ),
            "decision_ids": tuple(decision.decision_id for decision in decisions),
            "observed_at": NOW,
            "last_updated": NOW,
            "quality_signals": (
                ("changed-after-first-persist",)
                if changed and domain == "company"
                else ()
            ),
            "projection_schema_version": "canonical-v2-domain-projection-v1",
            "catalog_schema_version": catalog["schema_version"],
            "catalog_version": catalog["catalog_version"],
            "catalog_content_sha256": catalog["content_sha256"],
        }
        roots[domain] = _model_validate_from_candidates(model, candidates)
        lineages.extend(
            {
                "lineage_id": f"lineage:{domain}:{decision.field_path}",
                "release_id": RELEASE_ID,
                "build_run_id": BUILD_RUN_ID,
                "projection_id": f"projection:{identity.canonical_identity_id}",
                "canonical_identity_id": identity.canonical_identity_id,
                "entity_type": domain,
                "field_path": decision.field_path,
                "decision_id": decision.decision_id,
                "assertion_ids": decision.selected_assertion_ids,
                "observed_at": NOW,
            }
            for decision in decisions
        )

    subobjects = _representative_subobjects(
        module,
        identities_by_domain,
        decisions_by_domain_field,
        changed=changed,
    )
    ordered_domains = (
        tuple(reversed(sorted(roots))) if reverse else tuple(sorted(roots))
    )
    ordered_subobjects = tuple(reversed(subobjects)) if reverse else subobjects
    ordered_lineages = tuple(reversed(lineages)) if reverse else tuple(lineages)
    root_counts = {domain: 1 for domain in sorted(roots)}
    subobject_counts = {
        f"{getattr(value, 'entity_type', getattr(value, 'domain', ''))}."
        f"{getattr(value, 'subobject_type')}": 1
        for value in subobjects
    }
    manifest_payload = {
        "release_id": RELEASE_ID,
        "build_run_id": BUILD_RUN_ID,
        "projection_schema_version": "canonical-v2-domain-projection-v1",
        "catalog_schema_version": catalog["schema_version"],
        "catalog_version": catalog["catalog_version"],
        "catalog_content_sha256": catalog["content_sha256"],
        "root_counts": root_counts,
        "subobject_counts": subobject_counts,
        "projection_hashes": {
            domain: getattr(roots[domain], "content_sha256") for domain in sorted(roots)
        },
        "created_at": NOW,
    }
    manifest_payload["content_sha256"] = _hash(manifest_payload)
    result_candidates: dict[str, object] = {
        "release_id": RELEASE_ID,
        "build_run_id": BUILD_RUN_ID,
        "as_of": NOW,
        "projection_schema_version": "canonical-v2-domain-projection-v1",
        "catalog_schema_version": catalog["schema_version"],
        "catalog_version": catalog["catalog_version"],
        "catalog_content_sha256": catalog["content_sha256"],
        "professors": tuple(
            roots[domain] for domain in ordered_domains if domain == "professor"
        ),
        "companies": tuple(
            roots[domain] for domain in ordered_domains if domain == "company"
        ),
        "papers": tuple(
            roots[domain] for domain in ordered_domains if domain == "paper"
        ),
        "patents": tuple(
            roots[domain] for domain in ordered_domains if domain == "patent"
        ),
        "roots": tuple(roots[domain] for domain in ordered_domains),
        "subobjects": ordered_subobjects,
        "field_lineage": ordered_lineages,
        "inclusion_decisions": (
            tuple(reversed(graph.inclusion_decisions))
            if reverse
            else graph.inclusion_decisions
        ),
        "rejected_projections": (),
        "manifest": manifest_payload,
        "projection_manifest": manifest_payload,
        "manifest_content_sha256": manifest_payload["content_sha256"],
    }
    payload = {
        name: result_candidates[name]
        for name in module.DomainProjectionResult.model_fields
        if name in result_candidates and name != "content_sha256"
    }
    if "content_sha256" in module.DomainProjectionResult.model_fields:
        payload["content_sha256"] = _hash(payload)
    return module.DomainProjectionResult.model_validate(payload)


def _root_tables(migration: Any) -> dict[str, tuple[str, str]]:
    return {
        str(domain): tuple(value)
        for domain, value in migration.DOMAIN_ROOT_TABLES.items()
    }


def _subobject_tables(
    migration: Any,
) -> dict[str, dict[str, tuple[str, str]]]:
    return {
        str(domain): {
            str(subobject): tuple(value) for subobject, value in domain_tables.items()
        }
        for domain, domain_tables in migration.DOMAIN_SUBOBJECT_TABLES.items()
    }


def _table_count(
    connection: psycopg.Connection[Any],
    table: tuple[str, str],
) -> int:
    row = connection.execute(
        sql.SQL("SELECT count(*) FROM {}.{}").format(
            sql.Identifier(table[0]),
            sql.Identifier(table[1]),
        )
    ).fetchone()
    assert row is not None
    return int(row[0])


def _projection_table_counts(
    connection: psycopg.Connection[Any], migration: Any
) -> dict[str, int]:
    tables = {
        f"root:{domain}": table for domain, table in _root_tables(migration).items()
    }
    tables.update(
        {
            f"subobject:{domain}.{subobject}": table
            for domain, domain_tables in _subobject_tables(migration).items()
            for subobject, table in domain_tables.items()
        }
    )
    tables["manifest"] = tuple(migration.DOMAIN_PROJECTION_MANIFEST_TABLE)
    tables["lineage"] = tuple(migration.DOMAIN_PROJECTION_LINEAGE_TABLE)
    return {
        name: _table_count(connection, table) for name, table in sorted(tables.items())
    }


def _publish_row_count(connection: psycopg.Connection[Any]) -> int:
    tables = connection.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'publish' ORDER BY table_name"
    ).fetchall()
    total = 0
    for (table_name,) in tables:
        row = connection.execute(
            sql.SQL("SELECT count(*) FROM publish.{}").format(
                sql.Identifier(str(table_name))
            )
        ).fetchone()
        assert row is not None
        total += int(row[0])
    return total


def _assert_database_error(
    connection: psycopg.Connection[Any],
    error_type: type[BaseException],
    statement: LiteralString | sql.SQL | sql.Composed,
    parameters: tuple[Any, ...] | None = None,
) -> None:
    connection.execute("SAVEPOINT expected_domain_projection_error")
    try:
        with pytest.raises(error_type):
            connection.execute(statement, parameters)
    finally:
        connection.execute("ROLLBACK TO SAVEPOINT expected_domain_projection_error")
        connection.execute("RELEASE SAVEPOINT expected_domain_projection_error")


def _clone_first_row(
    connection: psycopg.Connection[Any],
    *,
    table: tuple[str, str],
    overrides: Mapping[str, object],
) -> None:
    columns = tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position",
            table,
        ).fetchall()
        if str(row[0]) not in {"created_at", "persisted_at"}
    )
    expressions = [
        sql.Placeholder(column) if column in overrides else sql.Identifier(column)
        for column in columns
    ]
    statement = sql.SQL("INSERT INTO {}.{} ({}) SELECT {} FROM {}.{} LIMIT 1").format(
        sql.Identifier(table[0]),
        sql.Identifier(table[1]),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        sql.SQL(", ").join(expressions),
        sql.Identifier(table[0]),
        sql.Identifier(table[1]),
    )
    connection.execute(statement, dict(overrides))


def test_c2_0008_declares_complete_typed_domain_storage_without_publish_pointer() -> (
    None
):
    revision = _revision()
    migration = revision.module
    catalog = _accepted_catalog()
    expected_subobjects = {
        item["domain"]: {
            subobject["subobject_type"] for subobject in item["subobjects"]
        }
        for item in catalog["domains"]
    }

    assert revision.down_revision == PREVIOUS_REVISION
    root_tables = _root_tables(migration)
    assert set(root_tables) == {"company", "paper", "patent", "professor"}
    assert all(
        schema == domain and table for domain, (schema, table) in root_tables.items()
    )
    assert len(set(root_tables.values())) == 4
    assert {
        domain: set(domain_tables)
        for domain, domain_tables in _subobject_tables(migration).items()
    } == expected_subobjects
    all_projection_tables = {
        *_root_tables(migration).values(),
        *(
            table
            for domain_tables in _subobject_tables(migration).values()
            for table in domain_tables.values()
        ),
        tuple(migration.DOMAIN_PROJECTION_MANIFEST_TABLE),
        tuple(migration.DOMAIN_PROJECTION_LINEAGE_TABLE),
    }
    assert all_projection_tables <= {
        tuple(value) for value in migration.APPEND_ONLY_TABLES
    }
    assert all(schema != "publish" for schema, _ in all_projection_tables)
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_factory_fails_closed_before_connect_for_non_disposable_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _postgres_module()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://miroflow:do-not-use@localhost:15432/miroflow_real",
    )
    monkeypatch.setattr(module, "require_accepted_backup_gate", lambda _: None)

    def unexpected_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError("invalid target must fail before PostgreSQL connect")

    monkeypatch.setattr(module.psycopg, "connect", unexpected_connect)
    with pytest.raises(
        module.DomainProjectionPersistenceError,
        match="disposable|target",
    ):
        module.create_postgres_domain_projection_store(
            database_url=(
                "postgresql+psycopg://nobody@unresolvable.invalid/"
                "domain_projection_candidate"
            ),
            expected_database="domain_projection_candidate",
            target_kind="candidate",
            backup_gate_root=tmp_path,
        )


def test_c2_0008_materializes_all_catalog_fields_and_typed_subobjects(
    target: _Target,
) -> None:
    migration = _revision().module
    catalog = _accepted_catalog()
    forbidden_untyped_columns = {
        "field_value",
        "fields",
        "payload",
        "projection_json",
        "properties",
    }
    with _connect(target) as connection:
        for domain in catalog["domains"]:
            domain_name = domain["domain"]
            root_table = _root_tables(migration)[domain_name]
            root_columns = {
                str(row[0])
                for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s",
                    root_table,
                ).fetchall()
            }
            expected_fields = {field["field_path"] for field in domain["fields"]}
            assert expected_fields <= root_columns
            assert {
                "release_id",
                "build_run_id",
                "canonical_identity_id",
                "entity_type",
                "projection_id",
                "catalog_content_sha256",
                "content_sha256",
            } <= root_columns
            assert root_columns.isdisjoint(forbidden_untyped_columns)

            for subobject in domain["subobjects"]:
                table = _subobject_tables(migration)[domain_name][
                    subobject["subobject_type"]
                ]
                columns = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = %s AND table_name = %s",
                        table,
                    ).fetchall()
                }
                assert {
                    member["member_name"] for member in subobject["members"]
                } <= columns
                assert {
                    "release_id",
                    "canonical_identity_id",
                    "parent_projection_id",
                    "subobject_id",
                    "content_sha256",
                } <= columns
                assert columns.isdisjoint(forbidden_untyped_columns)


def test_projection_round_trips_atomically_restarts_replays_and_never_activates(
    target: _Target,
) -> None:
    graph = _prepare_graph(target)
    result = _projection_result(graph)
    reordered = _projection_result(graph, reverse=True)
    assert reordered == result
    before_publish_rows = None
    with _connect(target) as connection:
        before_publish_rows = _publish_row_count(connection)

    first = _store(target).persist(result)
    restarted = _store(target)
    assert restarted.load(RELEASE_ID) == result
    replay = restarted.persist(reordered)

    assert first.release_id == RELEASE_ID
    assert first.build_run_id == BUILD_RUN_ID
    assert first.manifest_content_sha256 == replay.manifest_content_sha256
    assert first.root_counts == {
        "company": 1,
        "paper": 1,
        "patent": 1,
        "professor": 1,
    }
    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True

    migration = _revision().module
    with _connect(target) as connection:
        counts = _projection_table_counts(connection, migration)
        assert all(counts[f"root:{domain}"] == 1 for domain in first.root_counts)
        assert counts["manifest"] == 1
        assert counts["lineage"] == len(graph.field_decisions)
        assert (
            sum(
                count for name, count in counts.items() if name.startswith("subobject:")
            )
            == 4
        )
        assert connection.execute(
            "SELECT state FROM knowledge.release WHERE release_id = %s",
            (RELEASE_ID,),
        ).fetchone() == ("candidate",)
        assert _publish_row_count(connection) == before_publish_rows


def test_conflicting_same_release_replay_fails_without_partial_rewrite(
    target: _Target,
) -> None:
    graph = _prepare_graph(target)
    original = _projection_result(graph)
    conflicting = _projection_result(graph, changed=True)
    assert conflicting != original
    store = _store(target)
    store.persist(original)
    migration = _revision().module
    with _connect(target) as connection:
        before = _projection_table_counts(connection, migration)

    with pytest.raises(
        _postgres_module().DomainProjectionPersistenceError,
        match="conflict|content|immutable|replay",
    ):
        store.persist(conflicting)

    with _connect(target) as connection:
        assert _projection_table_counts(connection, migration) == before
    assert _store(target).load(RELEASE_ID) == original


def test_direct_sql_cannot_bypass_release_domain_lineage_time_hash_or_uniqueness(
    target: _Target,
) -> None:
    graph = _prepare_graph(target)
    _store(target).persist(_projection_result(graph))
    migration = _revision().module
    roots = _root_tables(migration)
    subobjects = _subobject_tables(migration)
    manifest_table = tuple(migration.DOMAIN_PROJECTION_MANIFEST_TABLE)
    lineage_table = tuple(migration.DOMAIN_PROJECTION_LINEAGE_TABLE)

    with _connect(target) as connection:
        constraints = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE connamespace IN ("
                "SELECT oid FROM pg_namespace WHERE nspname = ANY(%s))",
                (["knowledge", "professor", "company", "paper", "patent"],),
            ).fetchall()
        }
        constraint_text = "\n".join(constraints.values()).lower()
        for required_fragment in (
            "content_sha256",
            "canonical_identity",
            "decision",
            "source_assertion",
            "valid_from",
            "valid_to",
        ):
            assert required_fragment in constraint_text

        root_table = roots["professor"]
        _assert_database_error(
            connection,
            psycopg.errors.UniqueViolation,
            sql.SQL("INSERT INTO {}.{} SELECT * FROM {}.{} LIMIT 1").format(
                sql.Identifier(root_table[0]),
                sql.Identifier(root_table[1]),
                sql.Identifier(root_table[0]),
                sql.Identifier(root_table[1]),
            ),
        )
        _assert_database_error(
            connection,
            psycopg.Error,
            sql.SQL("UPDATE {}.{} SET entity_type = 'company'").format(
                sql.Identifier(root_table[0]),
                sql.Identifier(root_table[1]),
            ),
        )
        _assert_database_error(
            connection,
            psycopg.Error,
            sql.SQL("DELETE FROM {}.{}").format(
                sql.Identifier(manifest_table[0]),
                sql.Identifier(manifest_table[1]),
            ),
        )

        connection.execute("SAVEPOINT invalid_domain_projection_hash")
        try:
            with pytest.raises(psycopg.Error):
                _clone_first_row(
                    connection,
                    table=manifest_table,
                    overrides={
                        "release_id": "missing-release",
                        "build_run_id": "missing-build",
                        "manifest_content_sha256": "not-a-sha256",
                    },
                )
        finally:
            connection.execute("ROLLBACK TO SAVEPOINT invalid_domain_projection_hash")
            connection.execute("RELEASE SAVEPOINT invalid_domain_projection_hash")

        connection.execute("SAVEPOINT dangling_domain_projection_lineage")
        try:
            with pytest.raises(psycopg.Error):
                _clone_first_row(
                    connection,
                    table=lineage_table,
                    overrides={
                        "lineage_id": "lineage:dangling",
                        "assertion_id": "missing-assertion",
                        "decision_id": "missing-decision",
                    },
                )
        finally:
            connection.execute(
                "ROLLBACK TO SAVEPOINT dangling_domain_projection_lineage"
            )
            connection.execute("RELEASE SAVEPOINT dangling_domain_projection_lineage")

        temporal_table = subobjects["professor"]["research_project"]
        temporal_columns = {
            str(row[0])
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s",
                temporal_table,
            ).fetchall()
        }
        assert {"valid_from", "valid_to"} <= temporal_columns
        connection.execute("SAVEPOINT invalid_domain_projection_time")
        try:
            with pytest.raises(psycopg.Error):
                _clone_first_row(
                    connection,
                    table=temporal_table,
                    overrides={
                        "subobject_id": "subobject:invalid-time",
                        "valid_from": "2027-01-01",
                        "valid_to": "2026-01-01",
                        "content_sha256": _hash("invalid-time-row"),
                    },
                )
        finally:
            connection.execute("ROLLBACK TO SAVEPOINT invalid_domain_projection_time")
            connection.execute("RELEASE SAVEPOINT invalid_domain_projection_time")


def test_c2_0008_empty_round_trip_and_populated_downgrade_refuses_loss(
    target: _Target,
) -> None:
    migration = _revision().module
    all_tables = {
        *_root_tables(migration).values(),
        *(
            table
            for domain_tables in _subobject_tables(migration).values()
            for table in domain_tables.values()
        ),
        tuple(migration.DOMAIN_PROJECTION_MANIFEST_TABLE),
        tuple(migration.DOMAIN_PROJECTION_LINEAGE_TABLE),
    }
    command.downgrade(target.config, PREVIOUS_REVISION)
    with _connect(target) as connection:
        for schema_name, table_name in all_tables:
            assert connection.execute(
                "SELECT to_regclass(%s)",
                (f"{schema_name}.{table_name}",),
            ).fetchone() == (None,)
    command.upgrade(target.config, EXPECTED_REVISION)

    graph = _prepare_graph(target)
    result = _projection_result(graph)
    _store(target).persist(result)
    with pytest.raises(
        sa_exc.DBAPIError,
        match="projection|populated|retain|refus|loss",
    ):
        command.downgrade(target.config, PREVIOUS_REVISION)
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == (EXPECTED_REVISION,)
    assert _store(target).load(RELEASE_ID) == result
