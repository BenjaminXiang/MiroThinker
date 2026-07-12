from __future__ import annotations

import base64
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from importlib import import_module
import json
import os
from pathlib import Path
from threading import Event
import time

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from sqlalchemy import exc as sa_exc
from sqlalchemy.engine import make_url

from src.data_agents.canonical_v2.rebuild_write_gate import (
    RebuildWriteGateError,
    require_accepted_backup_gate,
)
from src.data_agents.storage.database_target import set_alembic_database_url


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "canonical_v2_alembic.ini"
SCRIPT_LOCATION = APP_ROOT / "canonical_v2_alembic"
EXPECTED_REVISION = "C2_0007"
RELEASE_ID = "identity-postgres-release-r1"
RUN_ID = "identity-postgres-run-1"
NOW = datetime(2026, 7, 12, 6, 30, tzinfo=timezone.utc)
IDENTITY_LOCK_ORDER = (
    "identity_resolution_run",
    "identity_candidate_verdict",
    "identity_decision",
    "identity_decision_context",
    "canonical_identity",
    "identity_decision_source_identity",
    "identity_decision_input",
    "identity_decision_output",
    "identity_decision_record",
    "identity_decision_assertion",
    "canonical_identity_source_membership",
    "identity_decision_output_source",
    "canonical_identity_lineage",
    "current_source_identity_assignment",
)


@dataclass(frozen=True, slots=True)
class _Target:
    database_url: str
    expected_database: str
    target_kind: str
    backup_gate_root: Path
    config: Config


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
            "Canonical identity persistence requires all four explicit "
            "CANONICAL_V2_TEST_* settings"
        )
    return values  # type: ignore[return-value]


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


def _connect(target: _Target, *, autocommit: bool = False):
    return psycopg.connect(_psycopg_dsn(target.database_url), autocommit=autocommit)


def _sibling_database_url(database_url: str, database_name: str) -> str:
    return (
        make_url(database_url)
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )


def _drop_owned_sibling(
    connection: psycopg.Connection[object],
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
        f"{expected_database[:38]}_s5d_"
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
                sql.Identifier(sibling_name), sql.Literal(sibling_marker)
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
        command.upgrade(configured.config, "head")
        yield configured
    finally:
        with psycopg.connect(_psycopg_dsn(database_url), autocommit=True) as admin:
            _drop_owned_sibling(
                admin,
                database_name=sibling_name,
                expected_marker=sibling_marker,
            )


def _script_directory() -> ScriptDirectory:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    return ScriptDirectory.from_config(config)


def test_c2_0007_is_the_single_canonical_v2_head() -> None:
    scripts = _script_directory()

    assert scripts.get_heads() == [EXPECTED_REVISION]
    revision = scripts.get_revision("C2_0007")
    assert revision is not None
    assert revision.down_revision == "C2_0006"


def test_c2_0006_schema_is_append_only_and_empty_downgrade_is_reversible(
    target: _Target,
) -> None:
    revision = _script_directory().get_revision("C2_0006")
    assert revision is not None
    migration = revision.module
    postgres = _postgres_module()
    assert tuple(migration.IDENTITY_LOCK_ORDER) == IDENTITY_LOCK_ORDER
    assert tuple(postgres.IDENTITY_LOCK_ORDER) == IDENTITY_LOCK_ORDER

    expected_tables = {
        "identity_resolution_run",
        "identity_candidate_verdict",
        "identity_decision_context",
        "identity_decision_assertion",
        "canonical_identity_source_membership",
        "identity_decision_output_source",
        "canonical_identity_lineage",
        "current_source_identity_assignment",
    }
    trigger_tables = (
        expected_tables
        | {"canonical_identity"}
        | set(migration.ACTION_ALLOCATION_TABLES)
        | set(migration.RELEASE_PROJECTION_TABLES)
    )
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == (EXPECTED_REVISION,)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'knowledge'"
            ).fetchall()
        }
        assert expected_tables <= tables
        trigger_rows = connection.execute(
            "SELECT c.relname, t.tgname, t.tgdeferrable, t.tginitdeferred "
            "FROM pg_trigger AS t "
            "JOIN pg_class AS c ON c.oid = t.tgrelid "
            "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'knowledge' AND NOT t.tgisinternal "
            "AND c.relname = ANY(%s)",
            (list(trigger_tables),),
        ).fetchall()
        triggers = {
            (table, trigger): (deferrable, initially_deferred)
            for table, trigger, deferrable, initially_deferred in trigger_rows
        }
        for table in expected_tables | {"canonical_identity"}:
            assert (table, "trg_reject_mutation") in triggers
            assert (table, "trg_reject_truncate") in triggers
        for table in migration.ACTION_ALLOCATION_TABLES:
            assert triggers[(table, "trg_validate_identity_action_allocation")] == (
                True,
                True,
            )
        for table in migration.RELEASE_PROJECTION_TABLES:
            assert triggers[(table, "trg_validate_identity_resolution_release")] == (
                True,
                True,
            )

    command.downgrade(target.config, "C2_0005")
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0005",)
        assert connection.execute(
            "SELECT to_regclass('knowledge.identity_resolution_run')"
        ).fetchone() == (None,)
    command.upgrade(target.config, "head")
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == (EXPECTED_REVISION,)


def _identity_module():
    return import_module("src.data_agents.canonical_v2.canonical_identity_resolution")


def _postgres_module():
    return import_module("src.data_agents.canonical_v2.canonical_identity_postgres")


def _policy(module):
    return module.PolicyReference(
        policy_id="canonical-identity-policy",
        policy_version="identity-v1",
        policy_kind="identity",
        content_sha256=hashlib.sha256(b"canonical-identity-policy").hexdigest(),
        effective_at=NOW - timedelta(days=1),
    )


def _strong_paper_request_and_result(*, as_of: datetime = NOW):
    module = _identity_module()
    sources = tuple(
        module.SourceIdentity(
            source_identity_id=f"paper-source-{suffix}",
            source_system=f"landing-{suffix}",
            source_key=f"paper:{suffix}",
            entity_type="paper",
            source_record_ids=(f"record:paper:{suffix}",),
            normalized_keys={"doi": "10.5555/canonical-v2"},
            first_observed_at=NOW - timedelta(days=30),
            last_observed_at=NOW,
            state="active",
        )
        for suffix in ("a", "b")
    )
    assertions = tuple(
        module.SourceAssertion(
            assertion_id=f"assertion-paper-doi-{suffix}",
            source_record_id=source.source_record_ids[0],
            source_identity_id=source.source_identity_id,
            subject_entity_type="paper",
            field_path="identity.doi",
            value="10.5555/canonical-v2",
            observed_at=NOW,
            assertion_run_id="identity-assertion-run-1",
        )
        for suffix, source in zip(("a", "b"), sources, strict=True)
    )
    request = module.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id=RUN_ID,
        identity_method_version="canonical-identity-resolution-v1",
        as_of=as_of,
        policy=_policy(module),
        source_identities=sources,
        identity_assertions=assertions,
    )
    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )
    return request, result


def _reviewed_company_request_and_result():
    module = _identity_module()
    sources = tuple(
        module.SourceIdentity(
            source_identity_id=f"company-review-{suffix}",
            source_system=f"landing-{suffix}",
            source_key=f"company:{suffix}",
            entity_type="company",
            source_record_ids=(f"record:company-review:{suffix}",),
            normalized_keys={"name_key": "reviewed company"},
            first_observed_at=NOW - timedelta(days=30),
            last_observed_at=NOW,
            state="active",
        )
        for suffix in ("a", "b")
    )
    assertions = tuple(
        module.SourceAssertion(
            assertion_id=f"assertion-company-review-{suffix}",
            source_record_id=source.source_record_ids[0],
            source_identity_id=source.source_identity_id,
            subject_entity_type="company",
            field_path="identity.name",
            value="Reviewed Company",
            observed_at=NOW,
            assertion_run_id="identity-review-assertion-run",
        )
        for suffix, source in zip(("a", "b"), sources, strict=True)
    )
    origin_request = module.IdentityResolutionRequest(
        release_id="identity-postgres-review-origin-r0",
        decision_run_id="identity-postgres-review-run-0",
        identity_method_version="canonical-identity-resolution-v1",
        as_of=NOW,
        policy=_policy(module),
        source_identities=sources,
        identity_assertions=assertions,
    )
    origin_result = (
        module.create_ephemeral_canonical_identity_resolution_engine().resolve(
            origin_request
        )
    )
    review_case = origin_result.review_cases[0]
    resolution = module.create_human_review_resolution(
        review_case=review_case,
        outcome="same_entity",
        source_identity_groups=(
            tuple(source.source_identity_id for source in sources),
        ),
        reviewer_id="reviewer:identity-postgres",
        review_policy_id="canonical-review-policy",
        review_policy_version="review-v1",
        review_policy_content_sha256="7" * 64,
        reviewed_at=NOW + timedelta(hours=1),
        rationale="Reviewed public evidence establishes one Company.",
        confidence=0.98,
    )
    request = module.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id=RUN_ID,
        identity_method_version="canonical-identity-resolution-v1",
        as_of=NOW + timedelta(hours=1),
        policy=_policy(module),
        source_identities=sources,
        identity_assertions=assertions,
        human_review_resolutions=(resolution,),
    )
    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )
    return origin_request, origin_result, request, result


def _source(
    module,
    source_identity_id: str,
    *,
    entity_type: str,
    normalized_keys: dict[str, str],
):
    return module.SourceIdentity(
        source_identity_id=source_identity_id,
        source_system=f"landing-{source_identity_id}",
        source_key=f"key:{source_identity_id}",
        entity_type=entity_type,
        source_record_ids=(f"record:{source_identity_id}",),
        normalized_keys=normalized_keys,
        first_observed_at=NOW - timedelta(days=30),
        last_observed_at=NOW,
        state="active",
    )


def _assertion(module, assertion_id: str, source, *, field_path: str, value: str):
    return module.SourceAssertion(
        assertion_id=assertion_id,
        source_record_id=source.source_record_ids[0],
        source_identity_id=source.source_identity_id,
        subject_entity_type=source.entity_type,
        field_path=field_path,
        value=value,
        observed_at=NOW,
        assertion_run_id="identity-assertion-run-1",
    )


def _canonical(
    module,
    canonical_identity_id: str,
    *,
    entity_type: str,
    source_identity_ids: tuple[str, ...],
    identity_decision_id: str,
    state: str = "active",
    predecessor_identity_ids: tuple[str, ...] = (),
    successor_identity_ids: tuple[str, ...] = (),
):
    return module.CanonicalIdentity(
        canonical_identity_id=canonical_identity_id,
        entity_type=entity_type,
        state=state,
        display_name=canonical_identity_id,
        source_identity_ids=source_identity_ids,
        identity_decision_id=identity_decision_id,
        predecessor_identity_ids=predecessor_identity_ids,
        successor_identity_ids=successor_identity_ids,
        release_id=RELEASE_ID,
    )


def _prior_create(module, identity, sources):
    return module.IdentityDecision(
        decision_id=identity.identity_decision_id,
        action="create",
        source_identity_ids=tuple(source.source_identity_id for source in sources),
        output_canonical_identity_ids=(identity.canonical_identity_id,),
        supporting_record_ids=tuple(
            record_id for source in sources for record_id in source.source_record_ids
        ),
        policy=_policy(module),
        method="deterministic",
        method_version="identity-v0",
        decision_run_id="prior-identity-run",
        confidence=1.0,
        rationale="Prior exact canonical identity creation.",
        decided_at=NOW - timedelta(days=2),
    )


def _decision_context(
    module,
    decision,
    *,
    sources,
    assertions,
    input_identities=(),
    output_identities=(),
    input_assignments=(),
    referenced_prior_decision_ids=(),
):
    return module.create_identity_decision_context(
        release_id=RELEASE_ID,
        decision=decision,
        candidate_verdict=None,
        source_identities=sources,
        identity_assertions=assertions,
        input_canonical_identities=input_identities,
        output_canonical_identities=output_identities,
        input_source_assignments=input_assignments,
        referenced_prior_decision_ids=referenced_prior_decision_ids,
        output_allocations=tuple(
            module.IdentityDecisionOutputAllocation(
                canonical_identity_id=identity.canonical_identity_id,
                source_identity_ids=identity.source_identity_ids,
            )
            for identity in output_identities
        ),
    )


def _link_request_and_result():
    module = _identity_module()
    official = _source(
        module,
        "patent-official",
        entity_type="patent",
        normalized_keys={"publication_number": "CN117873146A"},
    )
    recovered = _source(
        module,
        "patent-recovered",
        entity_type="patent",
        normalized_keys={
            "publication_number": "CN117873146A",
            "historical_identity_id": "v042:patent:8291",
        },
    )
    current = _canonical(
        module,
        "patent-current-canonical",
        entity_type="patent",
        source_identity_ids=(official.source_identity_id,),
        identity_decision_id="identity-create-patent-current",
    )
    prior_create = _prior_create(module, current, (official,))
    assertions = (
        _assertion(
            module,
            "assertion-patent-official",
            official,
            field_path="identity.publication_number",
            value="CN117873146A",
        ),
        _assertion(
            module,
            "assertion-patent-recovered",
            recovered,
            field_path="identity.publication_number",
            value="CN 117873146 A",
        ),
    )
    prior_context = _decision_context(
        module,
        prior_create,
        sources=(official,),
        assertions=(assertions[0],),
        output_identities=(current,),
    )
    request = module.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id=RUN_ID,
        identity_method_version="canonical-identity-resolution-v1",
        as_of=NOW,
        policy=_policy(module),
        source_identities=(official, recovered),
        identity_assertions=assertions,
        current_canonical_identities=(current,),
        current_source_identity_assignments=(
            module.SourceIdentityAssignment(
                release_id=RELEASE_ID,
                source_identity_id=official.source_identity_id,
                canonical_identity_id=current.canonical_identity_id,
                identity_decision_id=prior_create.decision_id,
            ),
        ),
        prior_identity_decisions=(prior_create,),
        prior_decision_contexts=(prior_context,),
    )
    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )
    return request, result, prior_create.decision_id


def _reverse_request_and_result():
    module = _identity_module()
    sources = tuple(
        _source(
            module,
            f"company-registry-{suffix}",
            entity_type="company",
            normalized_keys={
                "name_key": "pengcheng innovation",
                "unified_social_credit_code": credit_code,
            },
        )
        for suffix, credit_code in (
            ("a1", "91440300AAA000001A"),
            ("a2", "91440300AAA000001A"),
            ("b", "91440300BBB000002B"),
        )
    )
    prior_identities = tuple(
        _canonical(
            module,
            f"company-prior-{suffix}",
            entity_type="company",
            source_identity_ids=(source.source_identity_id,),
            identity_decision_id=f"identity-create-company-{suffix}",
            state="merged",
            successor_identity_ids=("company-wrong-combined",),
        )
        for source, suffix in zip(sources, ("a1", "a2", "b"), strict=True)
    )
    wrong_combined = _canonical(
        module,
        "company-wrong-combined",
        entity_type="company",
        source_identity_ids=tuple(source.source_identity_id for source in sources),
        identity_decision_id="identity-merge-company-wrong",
        predecessor_identity_ids=tuple(
            identity.canonical_identity_id for identity in prior_identities
        ),
    )
    create_decisions = tuple(
        _prior_create(module, identity, (source,))
        for source, identity in zip(sources, prior_identities, strict=True)
    )
    mistaken_merge = module.IdentityDecision(
        decision_id=wrong_combined.identity_decision_id,
        action="merge",
        source_identity_ids=tuple(source.source_identity_id for source in sources),
        input_canonical_identity_ids=tuple(
            identity.canonical_identity_id for identity in prior_identities
        ),
        output_canonical_identity_ids=(wrong_combined.canonical_identity_id,),
        supporting_record_ids=tuple(source.source_record_ids[0] for source in sources),
        policy=_policy(module),
        method="composite",
        method_version="identity-v0",
        decision_run_id="mistaken-merge-run",
        confidence=0.76,
        rationale="Historical mistaken Company merge.",
        decided_at=NOW - timedelta(days=2),
    )
    assertions = tuple(
        _assertion(
            module,
            f"assertion-company-uscc-{suffix}",
            source,
            field_path="identity.unified_social_credit_code",
            value=source.normalized_keys["unified_social_credit_code"],
        )
        for source, suffix in zip(sources, ("a1", "a2", "b"), strict=True)
    )
    prior_at_create = tuple(
        identity.model_copy(
            update={
                "state": identity.state.__class__.active,
                "successor_identity_ids": (),
            }
        )
        for identity in prior_identities
    )
    create_contexts = tuple(
        _decision_context(
            module,
            decision,
            sources=(source,),
            assertions=(assertion,),
            output_identities=(identity,),
        )
        for source, assertion, identity, decision in zip(
            sources, assertions, prior_at_create, create_decisions, strict=True
        )
    )
    merge_input_assignments = tuple(
        module.SourceIdentityAssignment(
            release_id=RELEASE_ID,
            source_identity_id=source.source_identity_id,
            canonical_identity_id=identity.canonical_identity_id,
            identity_decision_id=decision.decision_id,
        )
        for source, identity, decision in zip(
            sources, prior_identities, create_decisions, strict=True
        )
    )
    merge_context = _decision_context(
        module,
        mistaken_merge,
        sources=sources,
        assertions=assertions,
        input_identities=prior_at_create,
        output_identities=(wrong_combined,),
        input_assignments=merge_input_assignments,
        referenced_prior_decision_ids=tuple(
            decision.decision_id for decision in create_decisions
        ),
    )
    request = module.IdentityResolutionRequest(
        release_id=RELEASE_ID,
        decision_run_id=RUN_ID,
        identity_method_version="canonical-identity-resolution-v1",
        as_of=NOW,
        policy=_policy(module),
        source_identities=sources,
        identity_assertions=assertions,
        current_canonical_identities=(wrong_combined,),
        current_source_identity_assignments=tuple(
            module.SourceIdentityAssignment(
                release_id=RELEASE_ID,
                source_identity_id=source.source_identity_id,
                canonical_identity_id=wrong_combined.canonical_identity_id,
                identity_decision_id=mistaken_merge.decision_id,
            )
            for source in sources
        ),
        canonical_identity_history=prior_identities,
        prior_identity_decisions=(*create_decisions, mistaken_merge),
        prior_decision_contexts=(*create_contexts, merge_context),
    )
    result = module.create_ephemeral_canonical_identity_resolution_engine().resolve(
        request
    )
    return request, result, mistaken_merge.decision_id


def _insert_identity_prerequisites(target: _Target, request) -> None:
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO landing.evidence_artifact "
            "(artifact_id, source_kind, source_locator, content_sha256, byte_size, "
            "acquired_at, run_id) VALUES "
            "('identity-artifact-1', 'recorded_fixture', 'fixture://identity', %s, "
            "1, %s, 'identity-prerequisite-run')",
            (hashlib.sha256(b"identity-artifact").hexdigest(), NOW),
        )
        connection.execute(
            "INSERT INTO landing.parser_run "
            "(parse_run_id, artifact_id, parser_name, parser_version, schema_version, "
            "run_status, started_at, finished_at) VALUES "
            "('identity-parse-run', 'identity-artifact-1', 'recorded_fixture', "
            "'v1', 'identity-source-v1', 'succeeded', %s, %s)",
            (NOW, NOW),
        )
        for ordinal, source in enumerate(request.source_identities):
            record_id = source.source_record_ids[0]
            connection.execute(
                "INSERT INTO landing.source_record "
                "(record_id, artifact_id, source_batch_id, record_locator, "
                "parse_run_id, record_ordinal, parse_status, payload, parsed_at) "
                "VALUES (%s, 'identity-artifact-1', 'identity-source-batch', %s, "
                "'identity-parse-run', %s, 'parsed', %s, %s)",
                (
                    record_id,
                    f"row:{ordinal}",
                    ordinal,
                    Jsonb({"id": record_id}),
                    NOW,
                ),
            )
        connection.execute(
            "INSERT INTO knowledge.release "
            "(release_id, build_run_id, state, manifest_sha256, created_at) "
            "VALUES (%s, %s, 'candidate', %s, %s)",
            (
                request.release_id,
                request.decision_run_id,
                hashlib.sha256(b"identity-release-manifest").hexdigest(),
                NOW,
            ),
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


def _insert_identity_successor_release(
    target: _Target,
    request,
    *,
    previous_release_id: str,
) -> None:
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.release "
            "(release_id, build_run_id, state, manifest_sha256, previous_release_id, "
            "created_at) VALUES (%s, %s, 'candidate', %s, %s, %s)",
            (
                request.release_id,
                request.decision_run_id,
                hashlib.sha256(
                    f"identity-release-manifest:{request.release_id}".encode()
                ).hexdigest(),
                previous_release_id,
                request.as_of,
            ),
        )
        connection.commit()


def _store(target: _Target):
    return _postgres_module().create_postgres_canonical_identity_store(
        database_url=target.database_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
        build_authority="offline_canonical_build",
    )


def _store_with_application_name(target: _Target, application_name: str):
    database_url = (
        make_url(target.database_url)
        .update_query_dict({"application_name": application_name})
        .render_as_string(hide_password=False)
    )
    return _postgres_module().create_postgres_canonical_identity_store(
        database_url=database_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
        build_authority="offline_canonical_build",
    )


def test_identity_result_round_trips_restarts_and_replays_exactly(
    target: _Target,
) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    store = _store(target)

    assert store.persist(request, result) == result
    counts_after_first = None
    with _connect(target) as connection:
        counts_after_first = connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.identity_resolution_run), "
            "(SELECT count(*) FROM knowledge.identity_candidate_verdict), "
            "(SELECT count(*) FROM knowledge.identity_decision_context), "
            "(SELECT count(*) FROM knowledge.identity_decision_assertion), "
            "(SELECT count(*) FROM knowledge.canonical_identity_source_membership), "
            "(SELECT count(*) FROM knowledge.identity_decision_output_source), "
            "(SELECT count(*) FROM knowledge.current_source_identity_assignment)"
        ).fetchone()
    assert counts_after_first == (1, 1, 1, 2, 2, 2, 2)

    restarted = _store(target)
    assert restarted.load(request.release_id, request.decision_run_id) == result
    assert restarted.persist(request, result) == result
    with _connect(target) as connection:
        assert (
            connection.execute(
                "SELECT "
                "(SELECT count(*) FROM knowledge.identity_resolution_run), "
                "(SELECT count(*) FROM knowledge.identity_candidate_verdict), "
                "(SELECT count(*) FROM knowledge.identity_decision_context), "
                "(SELECT count(*) FROM knowledge.identity_decision_assertion), "
                "(SELECT count(*) FROM knowledge.canonical_identity_source_membership), "
                "(SELECT count(*) FROM knowledge.identity_decision_output_source), "
                "(SELECT count(*) FROM knowledge.current_source_identity_assignment)"
            ).fetchone()
            == counts_after_first
        )


def test_non_utc_identity_resolution_restarts_identically_under_shanghai_session(
    target: _Target,
) -> None:
    utc_request, utc_result = _strong_paper_request_and_result()
    offset_request, offset_result = _strong_paper_request_and_result(
        as_of=NOW.astimezone(timezone(timedelta(hours=8)))
    )
    assert offset_request == utc_request
    assert offset_result == utc_result
    assert offset_result.content_sha256 == utc_result.content_sha256
    assert offset_request.as_of.utcoffset() == timedelta(0)

    with _connect(target) as connection:
        connection.execute(
            sql.SQL("ALTER DATABASE {} SET timezone TO 'Asia/Shanghai'").format(
                sql.Identifier(target.expected_database)
            )
        )
        connection.commit()
    with _connect(target) as connection:
        assert connection.execute("SHOW timezone").fetchone() == ("Asia/Shanghai",)

    _insert_identity_prerequisites(target, offset_request)
    assert _store(target).persist(offset_request, offset_result) == offset_result
    restarted = _store(target).load(
        offset_request.release_id,
        offset_request.decision_run_id,
    )
    assert restarted == utc_result
    assert restarted.content_sha256 == utc_result.content_sha256
    assert restarted.as_of.utcoffset() == timedelta(0)


def test_human_reviewed_identity_result_restarts_with_exact_provenance(
    target: _Target,
) -> None:
    origin_request, origin_result, request, result = (
        _reviewed_company_request_and_result()
    )
    _insert_identity_prerequisites(target, origin_request)
    assert _store(target).persist(origin_request, origin_result) == origin_result
    _insert_identity_successor_release(
        target,
        request,
        previous_release_id=origin_request.release_id,
    )

    assert _store(target).persist(request, result) == result
    restarted = _store(target).load(request.release_id, request.decision_run_id)
    assert restarted == result
    decision = result.identity_decisions[0]
    assert decision.method.value == "human_review"
    assert decision.human_review_resolution is not None
    assert restarted.identity_decisions[0].human_review_resolution == (
        decision.human_review_resolution
    )
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT human_review_resolution FROM knowledge.identity_decision "
            "WHERE release_id = %s AND decision_id = %s",
            (request.release_id, decision.decision_id),
        ).fetchone() == (decision.human_review_resolution.model_dump(mode="json"),)
        origin_verdict = origin_result.candidate_verdicts[0]
        assert connection.execute(
            "SELECT verdict, method, verdict_content FROM "
            "knowledge.identity_candidate_verdict WHERE release_id = %s "
            "AND decision_run_id = %s AND verdict_id = %s",
            (
                origin_request.release_id,
                origin_request.decision_run_id,
                origin_verdict.verdict_id,
            ),
        ).fetchone() == (
            "unresolved",
            origin_verdict.method.value,
            origin_verdict.model_dump(mode="json"),
        )


def test_direct_sql_identity_review_rejects_null_hash_and_cross_wiring(
    target: _Target,
) -> None:
    origin_request, origin_result, request, result = (
        _reviewed_company_request_and_result()
    )
    _insert_identity_prerequisites(target, origin_request)
    assert _store(target).persist(origin_request, origin_result) == origin_result
    _insert_identity_successor_release(
        target,
        request,
        previous_release_id=origin_request.release_id,
    )
    assert _store(target).persist(request, result) == result
    decision = result.identity_decisions[0]
    resolution = decision.human_review_resolution
    assert resolution is not None
    valid_payload = resolution.model_dump(mode="json")
    wrong_hash = json.loads(json.dumps(valid_payload))
    wrong_hash["content_sha256"] = "0" * 64
    module = _identity_module()
    different_resolution = module.create_human_review_resolution(
        review_case=origin_result.review_cases[0],
        outcome="different_entities",
        source_identity_groups=tuple(
            (source.source_identity_id,) for source in origin_request.source_identities
        ),
        reviewer_id="reviewer:identity-partition",
        review_policy_id="canonical-review-policy",
        review_policy_version="review-v1",
        review_policy_content_sha256="7" * 64,
        reviewed_at=NOW + timedelta(hours=1),
        rationale="Reviewed evidence preserves two distinct Companies.",
        confidence=1.0,
    )
    insert_decision = (
        "INSERT INTO knowledge.identity_decision "
        "(release_id, decision_id, action, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at, "
        "reversal_of_decision_id, llm_trace, human_review_resolution) "
        "SELECT release_id, %s, %s, policy_id, policy_version, method, "
        "method_version, decision_run_id, confidence, rationale, decided_at, NULL, "
        "llm_trace, %s::jsonb FROM knowledge.identity_decision "
        "WHERE release_id = %s AND decision_id = %s"
    )

    current_verdict = result.candidate_verdicts[0]
    valid_verdict_content = current_verdict.model_dump(mode="json")
    null_resolution_content = json.loads(json.dumps(valid_verdict_content))
    null_resolution_content["human_review_resolution"] = None
    wrong_resolution_content = json.loads(json.dumps(valid_verdict_content))
    wrong_resolution_content["human_review_resolution"]["content_sha256"] = "1" * 64
    insert_verdict = (
        "INSERT INTO knowledge.identity_candidate_verdict "
        "(release_id, decision_run_id, verdict_id, verdict, method, confidence, "
        "verdict_content, content_sha256) "
        "SELECT release_id, decision_run_id, %s, %s, method, %s, %s::jsonb, "
        "%s FROM knowledge.identity_candidate_verdict "
        "WHERE release_id = %s AND decision_run_id = %s AND verdict_id = %s"
    )

    def content_sha256(content: dict[str, object]) -> str:
        return hashlib.sha256(
            json.dumps(
                content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

    def rebind_review_hashes(payload: dict[str, object]) -> dict[str, object]:
        review_case = payload["review_case"]
        assert isinstance(review_case, dict)
        case_content = {
            key: value
            for key, value in review_case.items()
            if key not in {"review_case_id", "content_sha256"}
        }
        case_hash = content_sha256(case_content)
        review_case["content_sha256"] = case_hash
        review_case["review_case_id"] = f"review-case:sha256:{case_hash}"
        resolution_content = {
            key: value
            for key, value in payload.items()
            if key not in {"resolution_id", "content_sha256"}
        }
        resolution_hash = content_sha256(resolution_content)
        payload["content_sha256"] = resolution_hash
        payload["resolution_id"] = f"human-review-resolution:sha256:{resolution_hash}"
        return payload

    canonical_group_order = json.loads(
        json.dumps(different_resolution.model_dump(mode="json"))
    )
    canonical_group_order["review_case"]["source_identity_ids"] = [
        '"identity-source',
        "#identity-source",
    ]
    canonical_group_order["source_identity_groups"] = [
        ['"identity-source'],
        ["#identity-source"],
    ]
    rebind_review_hashes(canonical_group_order)
    json_escaped_group_order = json.loads(json.dumps(canonical_group_order))
    json_escaped_group_order["source_identity_groups"].reverse()
    rebind_review_hashes(json_escaped_group_order)

    def changed_verdict_content(suffix: str) -> dict[str, object]:
        content = json.loads(json.dumps(valid_verdict_content))
        content["verdict_id"] = f"direct-identity-verdict-{suffix}"
        return content

    integer_outer_confidence = changed_verdict_content("integer-confidence")
    integer_outer_confidence["confidence"] = 1
    extra_outer_key = changed_verdict_content("extra-key")
    extra_outer_key["unexpected"] = "not part of IdentityCandidateVerdict"
    unicode_outer_rationale = changed_verdict_content("unicode-rationale")
    unicode_outer_rationale["rationale"] = (
        "\u00a0" + str(unicode_outer_rationale["rationale"]) + "\u3000"
    )

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT knowledge.is_valid_human_review_resolution(%s)",
            (Jsonb(different_resolution.model_dump(mode="json")),),
        ).fetchone() == (True,)
        assert connection.execute(
            "SELECT knowledge.is_valid_human_review_resolution(%s)",
            (Jsonb(canonical_group_order),),
        ).fetchone() == (True,)
        assert connection.execute(
            "SELECT knowledge.is_valid_human_review_resolution(%s)",
            (Jsonb(json_escaped_group_order),),
        ).fetchone() == (False,)
        for label, content, confidence in (
            ("integer outer confidence", integer_outer_confidence, 1.0),
            ("extra outer key", extra_outer_key, current_verdict.confidence),
            (
                "Unicode outer rationale",
                unicode_outer_rationale,
                current_verdict.confidence,
            ),
        ):
            with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
                connection.execute(
                    insert_verdict,
                    (
                        content["verdict_id"],
                        current_verdict.verdict.value,
                        confidence,
                        Jsonb(content),
                        content_sha256(content),
                        request.release_id,
                        request.decision_run_id,
                        current_verdict.verdict_id,
                    ),
                )
        for suffix, payload in (("sql-null", None), ("wrong-hash", wrong_hash)):
            with pytest.raises(psycopg.errors.CheckViolation):
                with connection.transaction():
                    connection.execute(
                        insert_decision,
                        (
                            f"direct-identity-{suffix}",
                            decision.action.value,
                            Jsonb(payload) if payload is not None else None,
                            request.release_id,
                            decision.decision_id,
                        ),
                    )
        with pytest.raises(
            psycopg.errors.CheckViolation,
            match="human review|review provenance|review binding",
        ):
            with connection.transaction():
                connection.execute(
                    insert_decision,
                    (
                        "direct-identity-crosswired",
                        "reject",
                        Jsonb(valid_payload),
                        request.release_id,
                        decision.decision_id,
                    ),
                )
                connection.execute(
                    "SET CONSTRAINTS knowledge."
                    "trg_validate_identity_human_review_binding IMMEDIATE"
                )

        for suffix, content in (
            ("null-resolution", null_resolution_content),
            ("wrong-resolution-hash", wrong_resolution_content),
        ):
            with pytest.raises(psycopg.errors.CheckViolation):
                with connection.transaction():
                    connection.execute(
                        insert_verdict,
                        (
                            f"direct-identity-verdict-{suffix}",
                            current_verdict.verdict.value,
                            current_verdict.confidence,
                            Jsonb(content),
                            content_sha256(content),
                            request.release_id,
                            request.decision_run_id,
                            current_verdict.verdict_id,
                        ),
                    )
        duplicate_verdict_id = "direct-identity-verdict-crosswired"
        duplicate_content = json.loads(json.dumps(valid_verdict_content))
        duplicate_content["verdict_id"] = duplicate_verdict_id
        with pytest.raises(
            psycopg.errors.CheckViolation,
            match="human review|review provenance|review binding",
        ):
            with connection.transaction():
                connection.execute(
                    insert_verdict,
                    (
                        duplicate_verdict_id,
                        current_verdict.verdict.value,
                        current_verdict.confidence,
                        Jsonb(duplicate_content),
                        content_sha256(duplicate_content),
                        request.release_id,
                        request.decision_run_id,
                        current_verdict.verdict_id,
                    ),
                )
                connection.execute(
                    "SET CONSTRAINTS knowledge."
                    "trg_validate_identity_human_review_verdict_binding IMMEDIATE"
                )


@pytest.mark.parametrize(
    ("defect", "expected_message"),
    (
        ("create_with_input", "action shape"),
        ("missing_output_allocation", "output allocation"),
    ),
)
def test_deferred_action_shape_and_output_allocation_are_enforced(
    target: _Target,
    defect: str,
    expected_message: str,
) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    assert _store(target).persist(request, result) == result

    canonical_id = result.current_canonical_identities[0].canonical_identity_id
    selected_sources = (
        request.source_identities[:1]
        if defect == "create_with_input"
        else request.source_identities
    )
    assertions_by_source = {
        assertion.source_identity_id: assertion
        for assertion in request.identity_assertions
    }
    decision_id = f"identity-invariant-probe:{defect}"
    supporting_assertion_ids = [
        assertions_by_source[source.source_identity_id].assertion_id
        for source in selected_sources
    ]

    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.identity_decision "
            "(release_id, decision_id, action, policy_id, policy_version, method, "
            "method_version, decision_run_id, confidence, rationale, decided_at) "
            "VALUES (%s, %s, 'create', %s, %s, 'deterministic', "
            "'deferred-invariant-probe-v1', %s, 1.0, %s, %s)",
            (
                RELEASE_ID,
                decision_id,
                request.policy.policy_id,
                request.policy.policy_version,
                RUN_ID,
                f"Probe {defect}.",
                NOW,
            ),
        )
        for source in selected_sources:
            assertion = assertions_by_source[source.source_identity_id]
            connection.execute(
                "INSERT INTO knowledge.identity_decision_source_identity "
                "(release_id, decision_id, source_identity_id) VALUES (%s, %s, %s)",
                (RELEASE_ID, decision_id, source.source_identity_id),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_record "
                "(release_id, decision_id, record_id) VALUES (%s, %s, %s)",
                (RELEASE_ID, decision_id, assertion.source_record_id),
            )
        if defect == "create_with_input":
            connection.execute(
                "INSERT INTO knowledge.identity_decision_input "
                "(release_id, decision_id, canonical_identity_id) "
                "VALUES (%s, %s, %s)",
                (RELEASE_ID, decision_id, canonical_id),
            )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_output "
            "(release_id, decision_id, canonical_identity_id) VALUES (%s, %s, %s)",
            (RELEASE_ID, decision_id, canonical_id),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_context "
            "(release_id, decision_id, decision_run_id, candidate_verdict_id, "
            "context_content, content_sha256, supporting_assertion_ids) "
            "VALUES (%s, %s, %s, NULL, %s, %s, %s)",
            (
                RELEASE_ID,
                decision_id,
                RUN_ID,
                Jsonb({"content_sha256": hashlib.sha256(defect.encode()).hexdigest()}),
                hashlib.sha256(defect.encode()).hexdigest(),
                Jsonb(supporting_assertion_ids),
            ),
        )
        for source in selected_sources:
            assertion = assertions_by_source[source.source_identity_id]
            connection.execute(
                "INSERT INTO knowledge.identity_decision_assertion "
                "(release_id, decision_id, assertion_id, source_identity_id, "
                "source_record_id) VALUES (%s, %s, %s, %s, %s)",
                (
                    RELEASE_ID,
                    decision_id,
                    assertion.assertion_id,
                    source.source_identity_id,
                    assertion.source_record_id,
                ),
            )
        allocated_sources = (
            selected_sources if defect == "create_with_input" else selected_sources[:1]
        )
        for source in allocated_sources:
            connection.execute(
                "INSERT INTO knowledge.identity_decision_output_source "
                "(release_id, decision_id, canonical_identity_id, "
                "source_identity_id) VALUES (%s, %s, %s, %s)",
                (RELEASE_ID, decision_id, canonical_id, source.source_identity_id),
            )

        with pytest.raises(
            psycopg.errors.CheckViolation,
            match=expected_message,
        ):
            connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        connection.rollback()


def test_deferred_active_membership_must_equal_current_assignment(
    target: _Target,
) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    assert _store(target).persist(request, result) == result
    canonical_id = result.current_canonical_identities[0].canonical_identity_id

    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.source_identity "
            "(source_identity_id, source_system, source_key, entity_type, "
            "normalized_keys, first_observed_at, last_observed_at, state) "
            "VALUES ('paper-unassigned-source', 'fixture', 'paper:unassigned', "
            "'paper', '{}'::jsonb, %s, %s, 'active')",
            (NOW, NOW),
        )
        connection.execute(
            "INSERT INTO knowledge.canonical_identity_source_membership "
            "(release_id, canonical_identity_id, source_identity_id) "
            "VALUES (%s, %s, 'paper-unassigned-source')",
            (RELEASE_ID, canonical_id),
        )

        with pytest.raises(
            psycopg.errors.CheckViolation,
            match="active membership.*current assignment",
        ):
            connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        connection.rollback()


def test_deferred_every_identity_decision_requires_exact_context(
    target: _Target,
) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    assert _store(target).persist(request, result) == result
    source = request.source_identities[0]
    assertion = next(
        value
        for value in request.identity_assertions
        if value.source_identity_id == source.source_identity_id
    )
    canonical_id = result.current_canonical_identities[0].canonical_identity_id
    decision_id = "identity-invariant-probe:missing-context"

    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.identity_decision "
            "(release_id, decision_id, action, policy_id, policy_version, method, "
            "method_version, decision_run_id, confidence, rationale, decided_at) "
            "VALUES (%s, %s, 'create', %s, %s, 'deterministic', "
            "'deferred-invariant-probe-v1', %s, 1.0, 'Missing exact context.', %s)",
            (
                RELEASE_ID,
                decision_id,
                request.policy.policy_id,
                request.policy.policy_version,
                RUN_ID,
                NOW,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_source_identity "
            "(release_id, decision_id, source_identity_id) VALUES (%s, %s, %s)",
            (RELEASE_ID, decision_id, source.source_identity_id),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_record "
            "(release_id, decision_id, record_id) VALUES (%s, %s, %s)",
            (RELEASE_ID, decision_id, assertion.source_record_id),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_output "
            "(release_id, decision_id, canonical_identity_id) VALUES (%s, %s, %s)",
            (RELEASE_ID, decision_id, canonical_id),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_output_source "
            "(release_id, decision_id, canonical_identity_id, source_identity_id) "
            "VALUES (%s, %s, %s, %s)",
            (RELEASE_ID, decision_id, canonical_id, source.source_identity_id),
        )

        with pytest.raises(
            psycopg.errors.CheckViolation,
            match="decision.*exact context",
        ):
            connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        connection.rollback()


def test_deferred_context_assertion_set_equals_evidence_edges(
    target: _Target,
) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    assert _store(target).persist(request, result) == result
    source = request.source_identities[0]
    decision = result.identity_decisions[0]
    assertion_id = "identity-invariant-probe:extra-context-edge"

    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.source_assertion "
            "(assertion_id, source_record_id, source_identity_id, "
            "subject_entity_type, field_path, value, "
            "assertion_fingerprint_sha256, observed_at, assertion_run_id) "
            "VALUES (%s, %s, %s, 'paper', 'identity.extra_probe', %s, %s, %s, %s)",
            (
                assertion_id,
                source.source_record_ids[0],
                source.source_identity_id,
                Jsonb("extra evidence"),
                hashlib.sha256(assertion_id.encode()).hexdigest(),
                NOW,
                RUN_ID,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_assertion "
            "(release_id, decision_id, assertion_id, source_identity_id, "
            "source_record_id) VALUES (%s, %s, %s, %s, %s)",
            (
                RELEASE_ID,
                decision.decision_id,
                assertion_id,
                source.source_identity_id,
                source.source_record_ids[0],
            ),
        )

        with pytest.raises(
            psycopg.errors.CheckViolation,
            match="context evidence.*edge",
        ):
            connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        connection.rollback()


def test_deferred_structured_llm_evidence_equals_decision_edges(
    target: _Target,
) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    assert _store(target).persist(request, result) == result
    decision_id = "identity-invariant-probe:llm-evidence-mismatch"
    canonical_id = result.current_canonical_identities[0].canonical_identity_id
    assertion_ids = [
        assertion.assertion_id for assertion in request.identity_assertions
    ]
    raw_output = json.dumps(
        {
            "confidence": 0.95,
            "rationale": "Recorded probe.",
            "source_identity_groups": [
                [source.source_identity_id for source in request.source_identities]
            ],
            "uncertainty": "None.",
            "verdict": "same_entity",
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    llm_trace = {
        "provider": "recorded",
        "model": "identity-probe-v1",
        "prompt_version": "identity-probe-v1",
        "schema_version": "identity-probe-v1",
        "input_evidence_ids": assertion_ids,
        "raw_output_base64": base64.b64encode(raw_output).decode(),
        "output_sha256": hashlib.sha256(raw_output).hexdigest(),
        "validated_output": json.loads(raw_output),
    }
    retained_assertion = request.identity_assertions[0]
    context_hash = hashlib.sha256(decision_id.encode()).hexdigest()

    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.identity_decision "
            "(release_id, decision_id, action, policy_id, policy_version, method, "
            "method_version, decision_run_id, confidence, rationale, decided_at, "
            "llm_trace) VALUES (%s, %s, 'create', %s, %s, 'structured_llm', "
            "'deferred-invariant-probe-v1', %s, 0.95, 'LLM evidence probe.', %s, %s)",
            (
                RELEASE_ID,
                decision_id,
                request.policy.policy_id,
                request.policy.policy_version,
                RUN_ID,
                NOW,
                Jsonb(llm_trace),
            ),
        )
        for source in request.source_identities:
            connection.execute(
                "INSERT INTO knowledge.identity_decision_source_identity "
                "(release_id, decision_id, source_identity_id) VALUES (%s, %s, %s)",
                (RELEASE_ID, decision_id, source.source_identity_id),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_record "
                "(release_id, decision_id, record_id) VALUES (%s, %s, %s)",
                (RELEASE_ID, decision_id, source.source_record_ids[0]),
            )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_output "
            "(release_id, decision_id, canonical_identity_id) VALUES (%s, %s, %s)",
            (RELEASE_ID, decision_id, canonical_id),
        )
        for source in request.source_identities:
            connection.execute(
                "INSERT INTO knowledge.identity_decision_output_source "
                "(release_id, decision_id, canonical_identity_id, "
                "source_identity_id) VALUES (%s, %s, %s, %s)",
                (RELEASE_ID, decision_id, canonical_id, source.source_identity_id),
            )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_context "
            "(release_id, decision_id, decision_run_id, context_content, "
            "content_sha256, supporting_assertion_ids) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                RELEASE_ID,
                decision_id,
                RUN_ID,
                Jsonb({"content_sha256": context_hash}),
                context_hash,
                Jsonb([retained_assertion.assertion_id]),
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_assertion "
            "(release_id, decision_id, assertion_id, source_identity_id, "
            "source_record_id) VALUES (%s, %s, %s, %s, %s)",
            (
                RELEASE_ID,
                decision_id,
                retained_assertion.assertion_id,
                retained_assertion.source_identity_id,
                retained_assertion.source_record_id,
            ),
        )

        with pytest.raises(
            psycopg.errors.CheckViolation,
            match="structured LLM evidence.*edge",
        ):
            connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        connection.rollback()


def test_deferred_canonical_state_matches_current_decision_topology(
    target: _Target,
) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    assert _store(target).persist(request, result) == result
    decision = result.identity_decisions[0]

    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.canonical_identity "
            "(release_id, canonical_identity_id, entity_type, state, "
            "display_name, identity_decision_id) "
            "VALUES (%s, 'paper-invalid-terminal', 'paper', 'merged', "
            "'Invalid terminal projection', %s)",
            (RELEASE_ID, decision.decision_id),
        )

        with pytest.raises(
            psycopg.errors.CheckViolation,
            match="canonical state.*decision topology",
        ):
            connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        connection.rollback()


def test_deferred_lifecycle_lineage_equals_decision_topology(
    target: _Target,
) -> None:
    module = _identity_module()
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    assert _store(target).persist(request, result) == result
    predecessor = result.current_canonical_identities[0]
    reversed_decision = result.identity_decisions[0]
    source = _source(
        module,
        "paper-lineage-probe-source",
        entity_type="paper",
        normalized_keys={"doi": "10.5555/lineage-probe"},
    )
    assertion = _assertion(
        module,
        "assertion-paper-lineage-probe",
        source,
        field_path="identity.doi",
        value="10.5555/lineage-probe",
    )
    provisional = module.IdentityDecision(
        decision_id="identity-lineage-probe-placeholder",
        action="reverse",
        source_identity_ids=(source.source_identity_id,),
        input_canonical_identity_ids=(predecessor.canonical_identity_id,),
        output_canonical_identity_ids=("paper-lineage-probe-successor",),
        supporting_record_ids=source.source_record_ids,
        policy=request.policy,
        method="deterministic",
        method_version=request.identity_method_version,
        decision_run_id=RUN_ID,
        confidence=1.0,
        rationale="Typed missing-lineage database probe.",
        decided_at=NOW,
        reversal_of_decision_id=reversed_decision.decision_id,
    )
    decision = provisional.model_copy(
        update={
            "decision_id": module.canonical_identity_applied_decision_id(
                decision=provisional,
                candidate_verdict_id=None,
            )
        }
    )
    successor = _canonical(
        module,
        "paper-lineage-probe-successor",
        entity_type="paper",
        source_identity_ids=(source.source_identity_id,),
        identity_decision_id=decision.decision_id,
    )
    context = _decision_context(
        module,
        decision,
        sources=(source,),
        assertions=(assertion,),
        input_identities=(predecessor,),
        output_identities=(successor,),
        referenced_prior_decision_ids=(reversed_decision.decision_id,),
    )

    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO landing.source_record "
            "(record_id, artifact_id, source_batch_id, record_locator, "
            "parse_run_id, record_ordinal, parse_status, payload, parsed_at) "
            "VALUES (%s, 'identity-artifact-1', 'identity-source-batch', "
            "'row:lineage-probe', 'identity-parse-run', 999, 'parsed', %s, %s)",
            (
                source.source_record_ids[0],
                Jsonb({"id": source.source_record_ids[0]}),
                NOW,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.source_identity "
            "(source_identity_id, source_system, source_key, entity_type, "
            "normalized_keys, first_observed_at, last_observed_at, state) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                source.source_identity_id,
                source.source_system,
                source.source_key,
                source.entity_type,
                Jsonb(source.normalized_keys),
                source.first_observed_at,
                source.last_observed_at,
                source.state.value,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.source_identity_record "
            "(source_identity_id, record_id) VALUES (%s, %s)",
            (source.source_identity_id, source.source_record_ids[0]),
        )
        connection.execute(
            "INSERT INTO knowledge.source_assertion "
            "(assertion_id, source_record_id, source_identity_id, "
            "subject_entity_type, field_path, value, "
            "assertion_fingerprint_sha256, observed_at, source_event_time, "
            "valid_from, valid_to, assertion_run_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                assertion.assertion_id,
                assertion.source_record_id,
                assertion.source_identity_id,
                assertion.subject_entity_type,
                assertion.field_path,
                Jsonb(assertion.value),
                _postgres_module()._assertion_fingerprint(assertion),
                assertion.observed_at,
                assertion.source_event_time,
                assertion.valid_from,
                assertion.valid_to,
                assertion.assertion_run_id,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision "
            "(release_id, decision_id, action, policy_id, policy_version, method, "
            "method_version, decision_run_id, confidence, rationale, decided_at, "
            "reversal_of_decision_id, llm_trace) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)",
            (
                RELEASE_ID,
                decision.decision_id,
                decision.action.value,
                decision.policy.policy_id,
                decision.policy.policy_version,
                decision.method.value,
                decision.method_version,
                decision.decision_run_id,
                decision.confidence,
                decision.rationale,
                decision.decided_at,
                decision.reversal_of_decision_id,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_source_identity "
            "(release_id, decision_id, source_identity_id) VALUES (%s, %s, %s)",
            (RELEASE_ID, decision.decision_id, source.source_identity_id),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_input "
            "(release_id, decision_id, canonical_identity_id) VALUES (%s, %s, %s)",
            (RELEASE_ID, decision.decision_id, predecessor.canonical_identity_id),
        )
        connection.execute(
            "INSERT INTO knowledge.canonical_identity "
            "(release_id, canonical_identity_id, entity_type, state, "
            "display_name, identity_decision_id) VALUES (%s, %s, %s, 'active', %s, %s)",
            (
                RELEASE_ID,
                successor.canonical_identity_id,
                successor.entity_type,
                successor.display_name,
                decision.decision_id,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_output "
            "(release_id, decision_id, canonical_identity_id) VALUES (%s, %s, %s)",
            (RELEASE_ID, decision.decision_id, successor.canonical_identity_id),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_record "
            "(release_id, decision_id, record_id) VALUES (%s, %s, %s)",
            (RELEASE_ID, decision.decision_id, assertion.source_record_id),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_context "
            "(release_id, decision_id, decision_run_id, context_content, "
            "content_sha256, supporting_assertion_ids) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                RELEASE_ID,
                decision.decision_id,
                RUN_ID,
                Jsonb(context.model_dump(mode="json")),
                context.content_sha256,
                Jsonb([assertion.assertion_id]),
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_assertion "
            "(release_id, decision_id, assertion_id, source_identity_id, "
            "source_record_id) VALUES (%s, %s, %s, %s, %s)",
            (
                RELEASE_ID,
                decision.decision_id,
                assertion.assertion_id,
                source.source_identity_id,
                assertion.source_record_id,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.canonical_identity_source_membership "
            "(release_id, canonical_identity_id, source_identity_id) "
            "VALUES (%s, %s, %s)",
            (RELEASE_ID, successor.canonical_identity_id, source.source_identity_id),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_output_source "
            "(release_id, decision_id, canonical_identity_id, source_identity_id) "
            "VALUES (%s, %s, %s, %s)",
            (
                RELEASE_ID,
                decision.decision_id,
                successor.canonical_identity_id,
                source.source_identity_id,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.current_source_identity_assignment "
            "(release_id, source_identity_id, canonical_identity_id, "
            "identity_decision_id) VALUES (%s, %s, %s, %s)",
            (
                RELEASE_ID,
                source.source_identity_id,
                successor.canonical_identity_id,
                decision.decision_id,
            ),
        )

        with pytest.raises(
            psycopg.errors.CheckViolation,
            match="lineage.*decision topology",
        ):
            connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        connection.rollback()


def test_link_persists_output_specific_allocation_and_mixed_assignment_provenance(
    target: _Target,
) -> None:
    module = _identity_module()
    request, result, prior_decision_id = _link_request_and_result()
    _insert_identity_prerequisites(target, request)

    assert _store(target).persist(request, result) == result

    link_decision = result.identity_decisions[0]
    with _connect(target) as connection:
        allocations = {
            (row[0], row[1])
            for row in connection.execute(
                "SELECT decision_id, source_identity_id FROM "
                "knowledge.identity_decision_output_source WHERE release_id = %s",
                (RELEASE_ID,),
            ).fetchall()
        }
        assert allocations == {
            (prior_decision_id, "patent-official"),
            (link_decision.decision_id, "patent-official"),
            (link_decision.decision_id, "patent-recovered"),
        }
        assignments = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT source_identity_id, identity_decision_id FROM "
                "knowledge.current_source_identity_assignment WHERE release_id = %s",
                (RELEASE_ID,),
            ).fetchall()
        }
        assert assignments == {
            "patent-official": prior_decision_id,
            "patent-recovered": link_decision.decision_id,
        }
        durable_contexts = {
            row[0]: module.IdentityDecisionContext.model_validate(row[1])
            for row in connection.execute(
                "SELECT decision_id, context_content FROM "
                "knowledge.identity_decision_context WHERE release_id = %s",
                (RELEASE_ID,),
            ).fetchall()
        }
        assert durable_contexts == {
            context.decision_id: context
            for context in (
                *request.prior_decision_contexts,
                *result.decision_contexts,
            )
        }
    assert _store(target).load(RELEASE_ID, RUN_ID) == result


def test_reverse_persists_terminal_history_lineage_and_exact_split_allocation(
    target: _Target,
) -> None:
    request, result, reversed_decision_id = _reverse_request_and_result()
    _insert_identity_prerequisites(target, request)

    assert _store(target).persist(request, result) == result

    reversal = result.identity_decisions[0]
    expected_allocations = {
        (
            reversal.decision_id,
            identity.canonical_identity_id,
            source_identity_id,
        )
        for identity in result.current_canonical_identities
        for source_identity_id in identity.source_identity_ids
    }
    assert {
        identity.source_identity_ids for identity in result.current_canonical_identities
    } == {
        ("company-registry-a1", "company-registry-a2"),
        ("company-registry-b",),
    }
    with _connect(target) as connection:
        reverse_allocations = {
            tuple(row)
            for row in connection.execute(
                "SELECT decision_id, canonical_identity_id, source_identity_id "
                "FROM knowledge.identity_decision_output_source "
                "WHERE release_id = %s AND decision_id = %s",
                (RELEASE_ID, reversal.decision_id),
            ).fetchall()
        }
        assert reverse_allocations == expected_allocations
        lineage = {
            tuple(row)
            for row in connection.execute(
                "SELECT predecessor_identity_id, successor_identity_id, transition "
                "FROM knowledge.canonical_identity_lineage "
                "WHERE release_id = %s AND decision_id = %s",
                (RELEASE_ID, reversal.decision_id),
            ).fetchall()
        }
        assert lineage == {
            ("company-wrong-combined", output_id, "reverse")
            for output_id in reversal.output_canonical_identity_ids
        }
        assert connection.execute(
            "SELECT count(*) FROM knowledge.current_source_identity_assignment "
            "WHERE release_id = %s AND canonical_identity_id = %s",
            (RELEASE_ID, "company-wrong-combined"),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT state FROM knowledge.canonical_identity WHERE release_id = %s "
            "AND canonical_identity_id = %s",
            (RELEASE_ID, "company-wrong-combined"),
        ).fetchone() == ("split",)
        assert connection.execute(
            "SELECT count(*) FROM knowledge.identity_decision_output_source "
            "WHERE release_id = %s AND decision_id = %s",
            (RELEASE_ID, reversed_decision_id),
        ).fetchone() == (len(request.source_identities),)
    assert _store(target).load(RELEASE_ID, RUN_ID) == result


def test_changed_same_release_content_conflicts_without_new_rows(
    target: _Target,
) -> None:
    module = _identity_module()
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    store = _store(target)
    assert store.persist(request, result) == result
    changed_assertions = (
        request.identity_assertions[0].model_copy(
            update={"value": "10.5555/canonical-v2-altered"}
        ),
        request.identity_assertions[1],
    )
    changed_request = module.IdentityResolutionRequest(
        **{
            **request.model_dump(mode="python"),
            "identity_assertions": changed_assertions,
        }
    )
    changed_result = (
        module.create_ephemeral_canonical_identity_resolution_engine().resolve(
            changed_request
        )
    )

    with pytest.raises(
        _postgres_module().CanonicalIdentityPersistenceError,
        match="changed identity content|one release",
    ):
        store.persist(changed_request, changed_result)

    assert store.load(RELEASE_ID, RUN_ID) == result
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT count(*) FROM knowledge.identity_resolution_run"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM knowledge.source_assertion"
        ).fetchone() == (2,)


@pytest.mark.parametrize("defect", ("source", "record_set", "assertion"))
def test_same_id_base_content_conflicts_before_identity_run(
    target: _Target,
    defect: str,
) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    source = request.source_identities[0]
    assertion = next(
        value
        for value in request.identity_assertions
        if value.source_identity_id == source.source_identity_id
    )

    with _connect(target) as connection:
        stored_source = (
            source.model_copy(update={"source_system": "conflicting-source-system"})
            if defect == "source"
            else source
        )
        connection.execute(
            "INSERT INTO knowledge.source_identity "
            "(source_identity_id, source_system, source_key, entity_type, "
            "normalized_keys, first_observed_at, last_observed_at, state) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                stored_source.source_identity_id,
                stored_source.source_system,
                stored_source.source_key,
                stored_source.entity_type,
                Jsonb(stored_source.normalized_keys),
                stored_source.first_observed_at,
                stored_source.last_observed_at,
                stored_source.state.value,
            ),
        )
        if defect == "record_set":
            extra_record_id = "record:paper:unexpected-extra"
            connection.execute(
                "INSERT INTO landing.source_record "
                "(record_id, artifact_id, source_batch_id, record_locator, "
                "parse_run_id, record_ordinal, parse_status, payload, parsed_at) "
                "VALUES (%s, 'identity-artifact-1', 'identity-source-batch', "
                "'row:unexpected-extra', 'identity-parse-run', 998, 'parsed', %s, %s)",
                (extra_record_id, Jsonb({"id": extra_record_id}), NOW),
            )
            connection.execute(
                "INSERT INTO knowledge.source_identity_record "
                "(source_identity_id, record_id) VALUES (%s, %s)",
                (source.source_identity_id, extra_record_id),
            )
        elif defect == "assertion":
            connection.execute(
                "INSERT INTO knowledge.source_identity_record "
                "(source_identity_id, record_id) VALUES (%s, %s)",
                (source.source_identity_id, source.source_record_ids[0]),
            )
            conflicting_assertion = assertion.model_copy(
                update={"value": "10.5555/conflicting-immutable-content"}
            )
            connection.execute(
                "INSERT INTO knowledge.source_assertion "
                "(assertion_id, source_record_id, source_identity_id, "
                "subject_entity_type, field_path, value, "
                "assertion_fingerprint_sha256, observed_at, source_event_time, "
                "valid_from, valid_to, assertion_run_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    conflicting_assertion.assertion_id,
                    conflicting_assertion.source_record_id,
                    conflicting_assertion.source_identity_id,
                    conflicting_assertion.subject_entity_type,
                    conflicting_assertion.field_path,
                    Jsonb(conflicting_assertion.value),
                    _postgres_module()._assertion_fingerprint(conflicting_assertion),
                    conflicting_assertion.observed_at,
                    conflicting_assertion.source_event_time,
                    conflicting_assertion.valid_from,
                    conflicting_assertion.valid_to,
                    conflicting_assertion.assertion_run_id,
                ),
            )
        connection.commit()

    with pytest.raises(
        _postgres_module().CanonicalIdentityPersistenceError,
        match="immutable source|base projection|record set|assertion",
    ):
        _store(target).persist(request, result)

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.identity_resolution_run), "
            "(SELECT count(*) FROM knowledge.identity_decision)"
        ).fetchone() == (0, 0)


def test_load_rejects_snapshot_row_key_substitution(target: _Target) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    store = _store(target)
    assert store.persist(request, result) == result
    substituted_run_id = "identity-postgres-substituted-run"

    with _connect(target) as connection:
        try:
            connection.execute("SET session_replication_role = 'replica'")
            connection.execute(
                "UPDATE knowledge.identity_resolution_run "
                "SET decision_run_id = %s WHERE release_id = %s",
                (substituted_run_id, RELEASE_ID),
            )
            connection.execute("SET session_replication_role = 'origin'")
            connection.commit()
        finally:
            if connection.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                connection.rollback()

    with pytest.raises(
        _postgres_module().CanonicalIdentityPersistenceError,
        match="snapshot row key",
    ):
        store.load(RELEASE_ID, substituted_run_id)


def test_mid_transaction_failure_rolls_back_every_identity_row(
    target: _Target,
) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    with _connect(target) as connection:
        connection.execute(
            "CREATE FUNCTION knowledge.fail_identity_context_insert() "
            "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'forced identity context failure'; END; $$"
        )
        connection.execute(
            "CREATE TRIGGER fail_identity_context_insert BEFORE INSERT ON "
            "knowledge.identity_decision_context FOR EACH ROW EXECUTE FUNCTION "
            "knowledge.fail_identity_context_insert()"
        )
        connection.commit()

    with pytest.raises(
        _postgres_module().CanonicalIdentityPersistenceError,
        match="transaction failed|persisted exactly",
    ):
        _store(target).persist(request, result)

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.source_identity), "
            "(SELECT count(*) FROM knowledge.source_assertion), "
            "(SELECT count(*) FROM knowledge.identity_resolution_run), "
            "(SELECT count(*) FROM knowledge.identity_decision), "
            "(SELECT count(*) FROM knowledge.canonical_identity), "
            "(SELECT count(*) FROM knowledge.identity_decision_context), "
            "(SELECT count(*) FROM knowledge.current_source_identity_assignment)"
        ).fetchone() == (0, 0, 0, 0, 0, 0, 0)


def test_factory_rejects_non_offline_authority_before_connect(target: _Target) -> None:
    module = _postgres_module()

    with pytest.raises(
        module.CanonicalIdentityPersistenceError, match="offline build authority"
    ):
        module.create_postgres_canonical_identity_store(
            database_url=(
                "postgresql+psycopg://nobody@invalid.invalid/"
                "identity_unreachable_disposable"
            ),
            expected_database="identity_unreachable_disposable",
            target_kind="disposable",
            backup_gate_root=target.backup_gate_root,
            build_authority="query_runtime",
        )


def test_factory_checks_backup_gate_before_any_connection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _postgres_module()

    def unexpected_connect(*args, **kwargs):
        raise AssertionError("database connection attempted before backup admission")

    monkeypatch.setattr(module.psycopg, "connect", unexpected_connect)
    with pytest.raises(RebuildWriteGateError):
        module.create_postgres_canonical_identity_store(
            database_url=(
                "postgresql+psycopg://nobody@invalid.invalid/"
                "identity_unreachable_disposable"
            ),
            expected_database="identity_unreachable_disposable",
            target_kind="disposable",
            backup_gate_root=tmp_path,
            build_authority="offline_canonical_build",
        )


def test_factory_rejects_non_disposable_and_low_revision_targets(
    target: _Target,
) -> None:
    module = _postgres_module()
    with pytest.raises(
        module.CanonicalIdentityPersistenceError, match="restricted to a disposable"
    ):
        module.create_postgres_canonical_identity_store(
            database_url=target.database_url,
            expected_database=target.expected_database,
            target_kind="isolated-candidate",
            backup_gate_root=target.backup_gate_root,
            build_authority="offline_canonical_build",
        )
    command.downgrade(target.config, "C2_0005")
    with pytest.raises(
        module.CanonicalIdentityPersistenceError, match="minimum revision C2_0007"
    ):
        module.create_postgres_canonical_identity_store(
            database_url=target.database_url,
            expected_database=target.expected_database,
            target_kind=target.target_kind,
            backup_gate_root=target.backup_gate_root,
            build_authority="offline_canonical_build",
        )


def test_factory_rejects_wrong_database_marker(target: _Target) -> None:
    module = _postgres_module()
    expected_marker = (
        "miroflow:destructive-target:v1:"
        f"{target.target_kind}:{target.expected_database}"
    )
    with _connect(target, autocommit=True) as connection:
        connection.execute(
            sql.SQL("COMMENT ON DATABASE {} IS 'wrong-marker'").format(
                sql.Identifier(target.expected_database)
            )
        )
    try:
        with pytest.raises(
            module.CanonicalIdentityPersistenceError, match="target identity"
        ):
            _store(target)
    finally:
        with _connect(target, autocommit=True) as connection:
            connection.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(target.expected_database),
                    sql.Literal(expected_marker),
                )
            )


def test_backup_gate_is_rechecked_immediately_before_first_write(
    target: _Target,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, result = _strong_paper_request_and_result()
    module = _postgres_module()
    calls = 0

    def expiring_gate(root: Path):
        nonlocal calls
        calls += 1
        receipt = require_accepted_backup_gate(root)
        if calls == 5:
            raise RebuildWriteGateError("synthetic gate expiry before first write")
        return receipt

    monkeypatch.setattr(module, "require_accepted_backup_gate", expiring_gate)
    store = _store(target)
    _insert_identity_prerequisites(target, request)

    with pytest.raises(RebuildWriteGateError, match="before first write"):
        store.persist(request, result)
    assert calls == 5
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.source_identity), "
            "(SELECT count(*) FROM knowledge.identity_resolution_run), "
            "(SELECT count(*) FROM knowledge.identity_decision)"
        ).fetchone() == (0, 0, 0)


def test_nonempty_c2_0006_downgrade_refuses_without_data_loss(
    target: _Target,
) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    store = _store(target)
    assert store.persist(request, result) == result

    with pytest.raises(sa_exc.DBAPIError) as error:
        command.downgrade(target.config, "C2_0005")
    assert getattr(error.value.orig, "sqlstate", None) == "55000"
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == (EXPECTED_REVISION,)
    assert store.load(RELEASE_ID, RUN_ID) == result


def _config_with_application_name(target: _Target, application_name: str) -> Config:
    migration_url = (
        make_url(target.database_url)
        .update_query_dict({"application_name": application_name})
        .render_as_string(hide_password=False)
    )
    configured = _Target(
        database_url=migration_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
        config=Config(),
    )
    return _migration_config(configured)


def _wait_for_migration_lock(
    target: _Target,
    *,
    application_name: str,
    future,
) -> tuple[str, str]:
    poll = Event()
    deadline = time.monotonic() + 10.0
    lock_wait = None
    with _connect(target, autocommit=True) as observer:
        while time.monotonic() < deadline:
            lock_wait = observer.execute(
                "SELECT wait_event_type, wait_event FROM pg_stat_activity "
                "WHERE datname = current_database() AND application_name = %s",
                (application_name,),
            ).fetchone()
            if lock_wait is not None and lock_wait[0] == "Lock":
                break
            if future.done():
                break
            poll.wait(0.01)
    assert lock_wait is not None
    assert lock_wait[0] == "Lock"
    assert not future.done()
    return lock_wait


def test_c2_0006_upgrade_serializes_with_late_identity_history(
    target: _Target,
) -> None:
    request, _ = _strong_paper_request_and_result()
    command.downgrade(target.config, "C2_0005")
    _insert_identity_prerequisites(target, request)
    application_name = "canonical_v2_c2_0006_upgrade_race"
    migration_config = _config_with_application_name(target, application_name)
    writer = _connect(target)
    executor = ThreadPoolExecutor(max_workers=1)
    upgrade = None
    writer_released = False
    try:
        writer.execute(
            "INSERT INTO knowledge.identity_decision "
            "(release_id, decision_id, action, policy_id, policy_version, method, "
            "method_version, decision_run_id, confidence, rationale, decided_at) "
            "VALUES (%s, 'identity-upgrade-race-decision', 'create', %s, %s, "
            "'deterministic', 'identity-v0', %s, 1.0, 'late identity history', %s)",
            (
                RELEASE_ID,
                request.policy.policy_id,
                request.policy.policy_version,
                RUN_ID,
                NOW,
            ),
        )
        upgrade = executor.submit(command.upgrade, migration_config, "head")
        _wait_for_migration_lock(
            target,
            application_name=application_name,
            future=upgrade,
        )
        writer.commit()
        writer_released = True
        with pytest.raises(sa_exc.DBAPIError) as error:
            upgrade.result(timeout=10.0)
        assert getattr(error.value.orig, "sqlstate", None) == "55000"
        with _connect(target) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.canonical_v2_alembic_version"
            ).fetchone() == ("C2_0005",)
            assert connection.execute(
                "SELECT count(*) FROM knowledge.identity_decision WHERE "
                "decision_id = 'identity-upgrade-race-decision'"
            ).fetchone() == (1,)
    finally:
        if not writer_released:
            writer.rollback()
        writer.close()
        if upgrade is not None and not upgrade.done():
            upgrade.result(timeout=10.0)
        executor.shutdown(wait=True, cancel_futures=True)


def test_c2_0006_downgrade_serializes_with_late_resolution_run(
    target: _Target,
) -> None:
    module = _identity_module()
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    application_name = "canonical_v2_c2_0006_downgrade_race"
    migration_config = _config_with_application_name(target, application_name)
    writer = _connect(target)
    executor = ThreadPoolExecutor(max_workers=1)
    downgrade = None
    writer_released = False
    try:
        writer.execute(
            "INSERT INTO knowledge.identity_resolution_run "
            "(release_id, decision_run_id, identity_method_version, as_of, "
            "policy_id, policy_version, build_authority, request_content, "
            "request_content_sha256, result_content, result_content_sha256) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'offline_canonical_build', "
            "%s, %s, %s, %s)",
            (
                request.release_id,
                request.decision_run_id,
                request.identity_method_version,
                request.as_of,
                request.policy.policy_id,
                request.policy.policy_version,
                Jsonb(request.model_dump(mode="json")),
                module.canonical_identity_resolution_request_sha256(request),
                Jsonb(result.model_dump(mode="json")),
                result.content_sha256,
            ),
        )
        downgrade = executor.submit(command.downgrade, migration_config, "C2_0005")
        _wait_for_migration_lock(
            target,
            application_name=application_name,
            future=downgrade,
        )
        writer.commit()
        writer_released = True
        with pytest.raises(sa_exc.DBAPIError) as error:
            downgrade.result(timeout=10.0)
        assert getattr(error.value.orig, "sqlstate", None) == "55000"
        with _connect(target) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.canonical_v2_alembic_version"
            ).fetchone() == (EXPECTED_REVISION,)
            assert connection.execute(
                "SELECT count(*) FROM knowledge.identity_resolution_run"
            ).fetchone() == (1,)
    finally:
        if not writer_released:
            writer.rollback()
        writer.close()
        if downgrade is not None and not downgrade.done():
            downgrade.result(timeout=10.0)
        executor.shutdown(wait=True, cancel_futures=True)


def test_store_and_downgrade_share_parent_first_lock_order(
    target: _Target,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    store_application_name = "canonical_v2_identity_store_lock_race"
    migration_application_name = "canonical_v2_identity_downgrade_lock_race"
    migration_config = _config_with_application_name(target, migration_application_name)
    module = _postgres_module()
    store_type = module._PostgresCanonicalIdentityStore
    original_lock_release = store_type._lock_release_boundary
    release_locked = Event()
    resume_writer = Event()

    def pause_after_release_before_identity(connection) -> None:
        original_lock_release(connection)
        release_locked.set()
        assert resume_writer.wait(timeout=10.0)

    monkeypatch.setattr(
        store_type,
        "_lock_release_boundary",
        staticmethod(pause_after_release_before_identity),
    )
    controller = _connect(target, autocommit=True)
    executor = ThreadPoolExecutor(max_workers=2)
    persist = None
    downgrade = None
    try:
        store = _store_with_application_name(target, store_application_name)
        persist = executor.submit(store.persist, request, result)
        assert release_locked.wait(timeout=10.0)
        assert not persist.done()
        granted_locks = {
            (row[0], row[1])
            for row in controller.execute(
                "SELECT relation.relname, lock.mode FROM pg_locks AS lock "
                "JOIN pg_stat_activity AS activity ON activity.pid = lock.pid "
                "JOIN pg_class AS relation ON relation.oid = lock.relation "
                "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
                "WHERE activity.datname = current_database() "
                "AND activity.application_name = %s "
                "AND namespace.nspname = 'knowledge' "
                "AND lock.granted",
                (store_application_name,),
            ).fetchall()
        }
        assert ("release", "RowShareLock") in granted_locks
        assert not {
            relation_name
            for relation_name, _ in granted_locks
            if relation_name in IDENTITY_LOCK_ORDER
        }

        downgrade = executor.submit(command.downgrade, migration_config, "C2_0005")
        _wait_for_migration_lock(
            target,
            application_name=migration_application_name,
            future=downgrade,
        )

        resume_writer.set()
        assert persist.result(timeout=10.0) == result
        with pytest.raises(sa_exc.DBAPIError) as error:
            downgrade.result(timeout=10.0)
        assert getattr(error.value.orig, "sqlstate", None) == "55000"

        with _connect(target) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.canonical_v2_alembic_version"
            ).fetchone() == (EXPECTED_REVISION,)
        assert store.load(RELEASE_ID, RUN_ID) == result
    finally:
        resume_writer.set()
        controller.close()
        if persist is not None and not persist.done():
            persist.result(timeout=10.0)
        if downgrade is not None and not downgrade.done():
            downgrade.result(timeout=10.0)
        executor.shutdown(wait=True, cancel_futures=True)


def test_concurrent_exact_replay_commits_once(target: _Target) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_store(target).persist, request, result) for _ in range(2)
        ]
        assert [future.result(timeout=10.0) for future in futures] == [result, result]

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT count(*) FROM knowledge.identity_resolution_run"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM knowledge.identity_decision"
        ).fetchone() == (1,)


def test_identity_history_and_projection_tables_reject_mutation(
    target: _Target,
) -> None:
    request, result = _strong_paper_request_and_result()
    _insert_identity_prerequisites(target, request)
    assert _store(target).persist(request, result) == result

    statements = (
        "UPDATE knowledge.canonical_identity SET display_name = 'rewritten'",
        "DELETE FROM knowledge.current_source_identity_assignment",
        "TRUNCATE knowledge.identity_candidate_verdict",
    )
    for statement in statements:
        with _connect(target) as connection:
            with pytest.raises(psycopg.Error):
                connection.execute(statement)
            connection.rollback()
    assert _store(target).load(RELEASE_ID, RUN_ID) == result


def test_missing_release_policy_and_records_are_never_invented(
    target: _Target,
) -> None:
    request, result = _strong_paper_request_and_result()

    with pytest.raises(
        _postgres_module().CanonicalIdentityPersistenceError,
        match="pre-existing candidate release",
    ):
        _store(target).persist(request, result)

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.release), "
            "(SELECT count(*) FROM knowledge.policy), "
            "(SELECT count(*) FROM knowledge.source_identity), "
            "(SELECT count(*) FROM knowledge.identity_resolution_run)"
        ).fetchone() == (0, 0, 0, 0)


def test_database_rejects_cross_entity_membership_and_terminal_current_owner(
    target: _Target,
) -> None:
    request, result, mistaken_merge_id = _reverse_request_and_result()
    _insert_identity_prerequisites(target, request)
    assert _store(target).persist(request, result) == result

    with _connect(target) as connection:
        connection.execute("SAVEPOINT invalid_identity_projection")
        try:
            connection.execute(
                "INSERT INTO knowledge.source_identity "
                "(source_identity_id, source_system, source_key, entity_type, "
                "normalized_keys, first_observed_at, last_observed_at, state) "
                "VALUES ('company-terminal-extra', 'fixture', 'company:terminal-extra', "
                "'company', '{}'::jsonb, %s, %s, 'active')",
                (NOW, NOW),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_source_identity "
                "(release_id, decision_id, source_identity_id) VALUES (%s, %s, %s)",
                (RELEASE_ID, mistaken_merge_id, "company-terminal-extra"),
            )
            connection.execute(
                "INSERT INTO knowledge.canonical_identity_source_membership "
                "(release_id, canonical_identity_id, source_identity_id) "
                "VALUES (%s, 'company-wrong-combined', 'company-terminal-extra')",
                (RELEASE_ID,),
            )
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    "INSERT INTO knowledge.current_source_identity_assignment "
                    "(release_id, source_identity_id, canonical_identity_id, "
                    "identity_decision_id) VALUES "
                    "(%s, 'company-terminal-extra', 'company-wrong-combined', %s)",
                    (RELEASE_ID, mistaken_merge_id),
                )
        finally:
            connection.execute("ROLLBACK TO SAVEPOINT invalid_identity_projection")
            connection.execute("RELEASE SAVEPOINT invalid_identity_projection")

        connection.execute("SAVEPOINT cross_entity_membership")
        try:
            connection.execute(
                "INSERT INTO knowledge.source_identity "
                "(source_identity_id, source_system, source_key, entity_type, "
                "normalized_keys, first_observed_at, last_observed_at, state) "
                "VALUES ('patent-cross-entity', 'fixture', 'patent:cross-entity', "
                "'patent', '{}'::jsonb, %s, %s, 'active')",
                (NOW, NOW),
            )
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    "INSERT INTO knowledge.canonical_identity_source_membership "
                    "(release_id, canonical_identity_id, source_identity_id) "
                    "VALUES (%s, 'company-wrong-combined', 'patent-cross-entity')",
                    (RELEASE_ID,),
                )
        finally:
            connection.execute("ROLLBACK TO SAVEPOINT cross_entity_membership")
            connection.execute("RELEASE SAVEPOINT cross_entity_membership")
