from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
from importlib import import_module
import inspect
import json
import os
from pathlib import Path
from threading import Event
import time
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from sqlalchemy import exc as sa_exc
from sqlalchemy.engine import URL, make_url

from src.data_agents.canonical_v2.rebuild_write_gate import (
    RebuildWriteGateError,
    require_accepted_backup_gate,
)
from src.data_agents.storage.database_target import set_alembic_database_url


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "canonical_v2_alembic.ini"
SCRIPT_LOCATION = APP_ROOT / "canonical_v2_alembic"
EXPECTED_REVISION = "C2_0008"
RELEASE_ID = "decision-postgres-release-r1"
RUN_ID = "decision-postgres-run-1"
REVIEWED_RELEASE_ID = "decision-postgres-release-r2"
REVIEWED_RUN_ID = "decision-postgres-run-2"
SNAPSHOT_RELEASE_ID = "decision-postgres-release-r3-snapshot"
SNAPSHOT_RUN_ID = "decision-postgres-run-3-snapshot"
NOW = datetime(2026, 7, 11, 23, 30, tzinfo=timezone.utc)


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
            "Canonical V2 decision persistence requires all four explicit "
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


def _connect(target: _Target, *, autocommit: bool = False) -> Any:
    return psycopg.connect(_psycopg_dsn(target.database_url), autocommit=autocommit)


def _verify_target(target: _Target) -> None:
    with _connect(target, autocommit=True) as connection:
        actual_database, marker = connection.execute(
            "SELECT current_database(), shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = current_database()"
        ).fetchone()
        assert actual_database == target.expected_database
        assert marker == (
            "miroflow:destructive-target:v1:"
            f"{target.target_kind}:{target.expected_database}"
        )
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == (EXPECTED_REVISION,)


def _sibling_database_url(database_url: str, database_name: str) -> str:
    return (
        make_url(database_url)
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )


def test_migration_config_accepts_rendered_sibling_socket_url_without_a_database() -> (
    None
):
    sibling_url = _sibling_database_url(
        URL.create(
            "postgresql+psycopg",
            username="probe",
            password="synthetic",
            database="base",
            query={"host": "/tmp/canonical-v2"},
        ).render_as_string(hide_password=False),
        "sibling",
    )
    target = _Target(
        database_url=sibling_url,
        expected_database="sibling",
        target_kind="disposable",
        backup_gate_root=Path("/synthetic"),
        config=Config(),
    )

    configured = _migration_config(target)

    configured_url = configured.get_main_option("sqlalchemy.url")
    assert configured_url is not None
    assert configured_url == sibling_url
    parsed = make_url(configured_url)
    assert parsed.database == "sibling"
    assert dict(parsed.query) == {"host": "/tmp/canonical-v2"}


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
        f"{expected_database[:42]}_s5b_"
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
        _verify_target(configured)
        yield configured
    finally:
        with psycopg.connect(_psycopg_dsn(database_url), autocommit=True) as admin:
            _drop_owned_sibling(
                admin,
                database_name=sibling_name,
                expected_marker=sibling_marker,
            )


def _engine_module() -> Any:
    return import_module("src.data_agents.canonical_v2.canonical_decision_engine")


def _postgres_module() -> Any:
    return import_module("src.data_agents.canonical_v2.canonical_decision_postgres")


def _store(target: _Target) -> Any:
    return _postgres_module().create_postgres_canonical_decision_store(
        database_url=target.database_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
    )


def _set_database_marker(target: _Target, marker: str) -> None:
    with _connect(target, autocommit=True) as connection:
        connection.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(target.expected_database),
                sql.Literal(marker),
            )
        )


def _policy(module: Any, kind: str, *, version: str = "v1") -> Any:
    return module.PolicyReference(
        policy_id=f"{kind}-policy",
        policy_version=version,
        policy_kind=kind,
        content_sha256=hashlib.sha256(f"policy:{kind}".encode()).hexdigest(),
        effective_at=NOW - timedelta(days=1),
    )


def _source_identity(
    module: Any,
    source_identity_id: str,
    *,
    source_system: str,
    entity_type: str,
    record_ids: tuple[str, ...],
    state: str = "active",
) -> Any:
    return module.SourceIdentity(
        source_identity_id=source_identity_id,
        source_system=source_system,
        source_key=f"key:{source_identity_id}",
        entity_type=entity_type,
        source_record_ids=record_ids,
        normalized_keys={"source_key": source_identity_id},
        first_observed_at=NOW - timedelta(days=30),
        last_observed_at=NOW,
        state=state,
    )


def _canonical_identity(
    module: Any,
    canonical_identity_id: str,
    *,
    entity_type: str,
    source_identity_ids: tuple[str, ...],
) -> Any:
    return module.CanonicalIdentity(
        canonical_identity_id=canonical_identity_id,
        entity_type=entity_type,
        state="active",
        display_name=f"Display {canonical_identity_id}",
        source_identity_ids=source_identity_ids,
        identity_decision_id=f"identity-decision:{canonical_identity_id}",
        release_id=RELEASE_ID,
    )


def _recorded_response(
    module: Any,
    *,
    decision_kind: str,
    subject_id: str,
    path: str,
    assertions: tuple[Any, ...],
    state: str,
    selected_assertion_ids: tuple[str, ...],
    conflicting_assertion_ids: tuple[str, ...],
    rationale: str,
    role_bindings: dict[str, str] | None = None,
) -> Any:
    validated_output: dict[str, Any] = {
        "state": state,
        "selected_assertion_ids": list(selected_assertion_ids),
        "conflicting_assertion_ids": list(conflicting_assertion_ids),
        "confidence": 0.9,
        "rationale": rationale,
        "uncertainty": "The competing assertion remains retained for audit.",
    }
    if role_bindings is not None:
        validated_output["role_bindings"] = role_bindings
    raw_output = json.dumps(
        validated_output,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    ordered_assertions = tuple(
        sorted(assertions, key=lambda assertion: assertion.assertion_id)
    )
    return module.RecordedAdjudication(
        input_evidence_ids=tuple(
            assertion.assertion_id for assertion in ordered_assertions
        ),
        input_evidence_sha256=module.canonical_adjudication_input_sha256(
            decision_kind=decision_kind,
            subject_id=subject_id,
            path=path,
            assertions=ordered_assertions,
        ),
        raw_output=raw_output,
        expected_output_sha256=hashlib.sha256(raw_output).hexdigest(),
    )


def _decision_result(
    *,
    changed: bool = False,
    temporal_history: bool = False,
    non_utc_temporal: bool = False,
    field_unresolved: bool = False,
    relationship_unresolved: bool = False,
    date_only_field: bool = False,
) -> Any:
    module = _engine_module()
    input_zone = timezone(timedelta(hours=8)) if non_utc_temporal else timezone.utc

    def input_time(value: datetime | None) -> datetime | None:
        return None if value is None else value.astimezone(input_zone)

    changed_field_id = "field-b-changed" if changed else "field-b"
    sources = (
        _source_identity(
            module,
            "prof-source-a",
            source_system="official_profile_a",
            entity_type="professor",
            record_ids=("record:prof-source-a", "record:relationship"),
        ),
        _source_identity(
            module,
            "prof-source-b",
            source_system="official_profile_b",
            entity_type="professor",
            record_ids=("record:prof-source-b",),
        ),
        _source_identity(
            module,
            "company-source",
            source_system="company_registry",
            entity_type="company",
            record_ids=("record:company-source", "record:relationship"),
        ),
        _source_identity(
            module,
            "rejected-source",
            source_system="rejected_source",
            entity_type="professor",
            record_ids=("record:rejected-source",),
            state="rejected",
        ),
    )
    professor = _canonical_identity(
        module,
        "professor-c1",
        entity_type="professor",
        source_identity_ids=("prof-source-a", "prof-source-b", "rejected-source"),
    )
    company = _canonical_identity(
        module,
        "company-c1",
        entity_type="company",
        source_identity_ids=("company-source",),
    )
    field_assertions = (
        module.SourceAssertion(
            assertion_id="field-a",
            source_record_id="record:prof-source-a",
            source_identity_id="prof-source-a",
            subject_entity_type="professor",
            field_path="employment.current_title",
            value="Professor",
            observed_at=NOW - timedelta(hours=2),
            assertion_run_id="field-assertion-run-1",
        ),
        module.SourceAssertion(
            assertion_id=changed_field_id,
            source_record_id="record:prof-source-b",
            source_identity_id="prof-source-b",
            subject_entity_type="professor",
            field_path="employment.current_title",
            value="Distinguished Professor" if changed else "Chair Professor",
            observed_at=NOW - timedelta(hours=1),
            valid_from=date(2024, 9, 1) if date_only_field else None,
            assertion_run_id="field-assertion-run-1",
        ),
        module.SourceAssertion(
            assertion_id="field-rejected",
            source_record_id="record:rejected-source",
            source_identity_id="rejected-source",
            subject_entity_type="professor",
            field_path="employment.current_title",
            value="Dean",
            observed_at=NOW - timedelta(minutes=30),
            assertion_run_id="field-assertion-run-1",
        ),
    )
    endpoints = {
        "source_endpoint": module.IdentityReference(
            identity_id="prof-source-a",
            identity_space="source",
            entity_type="professor",
        ),
        "target_endpoint": module.IdentityReference(
            identity_id="company-source",
            identity_space="source",
            entity_type="company",
        ),
    }
    relationship_rows = (
        (
            (
                "relation-role-old",
                "founder",
                60 * 24 * 400,
                NOW - timedelta(days=365),
                NOW - timedelta(days=365),
                NOW,
            ),
            (
                "relation-role-current",
                "founder",
                60 * 24,
                NOW,
                NOW,
                None,
            ),
        )
        if temporal_history
        else (
            (
                "relation-founder",
                "founder",
                50,
                NOW - timedelta(days=365),
                NOW - timedelta(days=365),
                None,
            ),
            ("relation-advisor", "advisor", 40, None, None, None),
        )
    )
    relationship_assertions = tuple(
        module.RelationshipAssertion(
            assertion_id=assertion_id,
            relationship_type_id="professor_company_role",
            relationship_type_version="v1",
            source_record_id="record:relationship",
            attributes={"role": role},
            observed_at=(NOW - timedelta(minutes=minutes)).astimezone(input_zone),
            source_event_time=input_time(source_event_time),
            valid_from=input_time(valid_from),
            valid_to=input_time(valid_to),
            assertion_run_id="relationship-assertion-run-1",
            **endpoints,
        )
        for (
            assertion_id,
            role,
            minutes,
            source_event_time,
            valid_from,
            valid_to,
        ) in relationship_rows
    )
    field_response = _recorded_response(
        module,
        decision_kind="field",
        subject_id="professor-c1",
        path="employment.current_title",
        assertions=field_assertions[:2],
        state="unresolved" if field_unresolved else "selected",
        selected_assertion_ids=() if field_unresolved else (changed_field_id,),
        conflicting_assertion_ids=(
            ("field-a", changed_field_id) if field_unresolved else ("field-a",)
        ),
        rationale=(
            "The retained title evidence remains materially ambiguous."
            if field_unresolved
            else "Changed replay content must conflict."
            if changed
            else "The newer official profile supports the chair title."
        ),
    )
    relationship_groups = (
        tuple(
            module.RelationshipAssertionGroup(
                canonical_relationship_id=canonical_relationship_id,
                relationship_type_id="professor_company_role",
                relationship_type_version="v1",
                source_canonical_identity_id="professor-c1",
                target_canonical_identity_id="company-c1",
                assertions=(assertion,),
                policy=_policy(module, "relationship", version="v2"),
            )
            for canonical_relationship_id, assertion in (
                ("canonical-relationship-old", relationship_assertions[0]),
                ("canonical-relationship-current", relationship_assertions[1]),
            )
        )
        if temporal_history
        else (
            module.RelationshipAssertionGroup(
                canonical_relationship_id="canonical-relationship-1",
                relationship_type_id="professor_company_role",
                relationship_type_version="v1",
                source_canonical_identity_id="professor-c1",
                target_canonical_identity_id="company-c1",
                assertions=relationship_assertions,
                policy=_policy(module, "relationship", version="v2"),
            ),
        )
    )
    recorded_responses = [field_response]
    if not temporal_history:
        recorded_responses.append(
            _recorded_response(
                module,
                decision_kind="relationship",
                subject_id="canonical-relationship-1",
                path="professor_company_role",
                assertions=relationship_assertions,
                state="unresolved" if relationship_unresolved else "selected",
                selected_assertion_ids=(
                    () if relationship_unresolved else ("relation-founder",)
                ),
                conflicting_assertion_ids=(
                    ("relation-advisor", "relation-founder")
                    if relationship_unresolved
                    else ("relation-advisor",)
                ),
                rationale=(
                    "The retained relationship roles remain materially ambiguous."
                    if relationship_unresolved
                    else "The official evidence supports the founder role."
                ),
                role_bindings=(
                    None if relationship_unresolved else {"source": "founder"}
                ),
            )
        )
    request = module.DecisionBatchRequest(
        release_id=RELEASE_ID,
        decision_run_id=RUN_ID,
        decision_method_version="canonical-decision-v1",
        as_of=NOW.astimezone(input_zone),
        temporal_comparison_context=(
            module.TemporalComparisonContext(
                policy_version="explicit-calendar-v1",
                calendar="gregorian",
                timezone="Asia/Shanghai",
            )
            if date_only_field
            else None
        ),
        source_identities=sources,
        canonical_identities=(professor, company),
        field_groups=(
            module.FieldAssertionGroup(
                canonical_identity_id="professor-c1",
                field_path="employment.current_title",
                assertions=field_assertions,
                policy=_policy(module, "field_selection"),
            ),
        ),
        relationship_groups=relationship_groups,
    )
    adjudicator = module.create_recorded_structured_adjudicator(
        provider="recorded",
        model="canonical-judge-fixture-v1",
        prompt_version="canonical-adjudication-v1",
        schema_version="canonical-adjudication-output-v1",
        responses=tuple(recorded_responses),
    )
    return module.create_ephemeral_canonical_decision_engine(
        adjudicator=adjudicator
    ).decide(request)


def _reviewed_field_result(
    initial: Any,
    *,
    decision_run_id: str = REVIEWED_RUN_ID,
    as_of: datetime = NOW + timedelta(hours=1),
) -> Any:
    module = _engine_module()
    review_case = next(
        case for case in initial.review_cases if case.family.value == "field"
    )
    resolution = module.create_human_review_resolution(
        review_case=review_case,
        outcome="selected",
        selected_evidence_ids=("field-b",),
        reviewer_id="reviewer:postgres-restart",
        review_policy_id="canonical-review-policy",
        review_policy_version="review-v1",
        review_policy_content_sha256="7" * 64,
        reviewed_at=NOW + timedelta(hours=1),
        rationale="Reviewed official evidence supports Chair Professor.",
        confidence=0.99,
    )
    professor_context = next(
        context
        for context in initial.canonical_identity_contexts
        if context.canonical_identity_id == "professor-c1"
    )
    professor = module.CanonicalIdentity(
        canonical_identity_id=professor_context.canonical_identity_id,
        entity_type=professor_context.entity_type,
        state=professor_context.state,
        display_name="Display professor-c1",
        source_identity_ids=professor_context.source_identity_ids,
        identity_decision_id="identity-decision:professor-c1:r2",
        release_id=REVIEWED_RELEASE_ID,
    )
    decision = initial.canonical_decisions[0]
    request = module.DecisionBatchRequest(
        release_id=REVIEWED_RELEASE_ID,
        decision_run_id=decision_run_id,
        decision_method_version="canonical-decision-v1",
        as_of=as_of,
        source_identities=initial.source_identity_contexts,
        canonical_identities=(professor,),
        field_groups=(
            module.FieldAssertionGroup(
                canonical_identity_id="professor-c1",
                field_path="employment.current_title",
                assertions=initial.field_assertions,
                policy=decision.policy,
            ),
        ),
        human_review_resolutions=(resolution,),
        previous_history=module.project_decision_history((initial,), as_of=NOW),
    )
    return module.create_ephemeral_canonical_decision_engine().decide(request)


def _reviewed_relationship_result(initial: Any) -> Any:
    module = _engine_module()
    review_case = next(
        case for case in initial.review_cases if case.family.value == "relationship"
    )
    resolution = module.create_human_review_resolution(
        review_case=review_case,
        outcome="accepted",
        selected_evidence_ids=("relation-founder",),
        role_bindings={"source": "founder"},
        reviewer_id="reviewer:postgres-relationship",
        review_policy_id="canonical-review-policy",
        review_policy_version="review-v1",
        review_policy_content_sha256="7" * 64,
        reviewed_at=NOW + timedelta(hours=1),
        rationale="Reviewed official evidence supports the founder relationship.",
        confidence=0.99,
    )
    contexts = {
        context.canonical_identity_id: context
        for context in initial.canonical_identity_contexts
    }
    canonical_identities = tuple(
        module.CanonicalIdentity(
            canonical_identity_id=canonical_identity_id,
            entity_type=context.entity_type,
            state=context.state,
            display_name=f"Display {canonical_identity_id}",
            source_identity_ids=context.source_identity_ids,
            identity_decision_id=f"identity-decision:{canonical_identity_id}:r2",
            release_id=REVIEWED_RELEASE_ID,
        )
        for canonical_identity_id, context in sorted(contexts.items())
    )
    prior = initial.relationship_decisions[0]
    request = module.DecisionBatchRequest(
        release_id=REVIEWED_RELEASE_ID,
        decision_run_id=REVIEWED_RUN_ID,
        decision_method_version="canonical-decision-v1",
        as_of=NOW + timedelta(hours=1),
        source_identities=initial.source_identity_contexts,
        canonical_identities=canonical_identities,
        relationship_groups=(
            module.RelationshipAssertionGroup(
                canonical_relationship_id=prior.canonical_relationship_id,
                relationship_type_id=prior.relationship_type_id,
                relationship_type_version=prior.relationship_type_version,
                source_canonical_identity_id=prior.source_canonical_identity_id,
                target_canonical_identity_id=prior.target_canonical_identity_id,
                assertions=initial.relationship_assertions,
                policy=prior.policy,
            ),
        ),
        human_review_resolutions=(resolution,),
        previous_history=module.project_decision_history((initial,), as_of=NOW),
    )
    return module.create_ephemeral_canonical_decision_engine().decide(request)


def _ordinary_field_replacement_result(
    initial: Any,
    reviewed: Any,
    *,
    linked: bool = True,
) -> Any:
    module = _engine_module()
    selected_assertion = next(
        assertion
        for assertion in initial.field_assertions
        if assertion.assertion_id == "field-b"
    )
    prior = reviewed.canonical_decisions[0]
    prior_context = reviewed.canonical_identity_contexts[0]
    canonical = module.CanonicalIdentity(
        canonical_identity_id=prior_context.canonical_identity_id,
        entity_type=prior_context.entity_type,
        state=prior_context.state,
        display_name="Display professor-c1",
        source_identity_ids=prior_context.source_identity_ids,
        identity_decision_id="identity-decision:professor-c1:r3-snapshot",
        release_id=SNAPSHOT_RELEASE_ID,
    )
    request = module.DecisionBatchRequest(
        release_id=SNAPSHOT_RELEASE_ID,
        decision_run_id=SNAPSHOT_RUN_ID,
        decision_method_version="canonical-decision-v1",
        as_of=NOW + timedelta(hours=2),
        source_identities=initial.source_identity_contexts,
        canonical_identities=(canonical,),
        field_groups=(
            module.FieldAssertionGroup(
                canonical_identity_id=prior.canonical_identity_id,
                field_path=prior.field_path,
                assertions=(selected_assertion,),
                policy=prior.policy,
            ),
        ),
        previous_history=(
            module.project_decision_history(
                (initial, reviewed),
                as_of=NOW + timedelta(hours=1),
            )
            if linked
            else None
        ),
    )
    return module.create_ephemeral_canonical_decision_engine().decide(request)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _insert_prerequisites(
    target: _Target,
    *,
    omitted_membership: str | None = None,
) -> None:
    record_ids = (
        "record:prof-source-a",
        "record:prof-source-b",
        "record:company-source",
        "record:relationship",
        "record:rejected-source",
    ) + (
        ("record:company-source-alt",) if omitted_membership == "company-source" else ()
    )
    with _connect(target) as connection:
        has_explicit_membership = connection.execute(
            "SELECT to_regclass('knowledge.canonical_identity_source_membership') "
            "IS NOT NULL"
        ).fetchone() == (True,)
        has_output_allocation = connection.execute(
            "SELECT to_regclass('knowledge.identity_decision_output_source') "
            "IS NOT NULL"
        ).fetchone() == (True,)
        has_identity_resolution_projection = connection.execute(
            "SELECT to_regclass('knowledge.identity_resolution_run') IS NOT NULL"
        ).fetchone() == (True,)
        connection.execute(
            "INSERT INTO landing.evidence_artifact "
            "(artifact_id, source_kind, source_locator, content_sha256, byte_size, "
            "acquired_at, run_id) VALUES "
            "('decision-artifact-1', 'recorded_fixture', 'fixture://decision', %s, "
            "1, %s, 'decision-prerequisite-run')",
            (_fingerprint("decision-artifact"), NOW),
        )
        connection.execute(
            "INSERT INTO landing.parser_run "
            "(parse_run_id, artifact_id, parser_name, parser_version, schema_version, "
            "run_status, started_at, finished_at) VALUES "
            "('decision-parse-run', 'decision-artifact-1', 'recorded_fixture', 'v1', "
            "'decision-source-v1', 'succeeded', %s, %s)",
            (NOW, NOW),
        )
        for ordinal, record_id in enumerate(record_ids):
            connection.execute(
                "INSERT INTO landing.source_record "
                "(record_id, artifact_id, source_batch_id, record_locator, parse_run_id, "
                "record_ordinal, parse_status, payload, parsed_at) VALUES "
                "(%s, 'decision-artifact-1', 'decision-source-batch', %s, "
                "'decision-parse-run', %s, 'parsed', %s, %s)",
                (record_id, f"row:{ordinal}", ordinal, Jsonb({"id": record_id}), NOW),
            )
        source_identity_rows = (
            (
                "prof-source-a",
                "official_profile_a",
                "professor",
                ("record:prof-source-a", "record:relationship"),
                "active",
            ),
            (
                "prof-source-b",
                "official_profile_b",
                "professor",
                ("record:prof-source-b",),
                "active",
            ),
            (
                "company-source",
                "company_registry",
                "company",
                ("record:company-source", "record:relationship"),
                "active",
            ),
            (
                "rejected-source",
                "rejected_source",
                "professor",
                ("record:rejected-source",),
                "rejected",
            ),
        ) + (
            (
                (
                    "company-source-alt",
                    "company_registry_alt",
                    "company",
                    ("record:company-source-alt",),
                    "active",
                ),
            )
            if omitted_membership == "company-source"
            else ()
        )
        for (
            source_identity_id,
            source_system,
            entity_type,
            linked_records,
            state,
        ) in source_identity_rows:
            connection.execute(
                "INSERT INTO knowledge.source_identity "
                "(source_identity_id, source_system, source_key, entity_type, "
                "normalized_keys, first_observed_at, last_observed_at, state) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    source_identity_id,
                    source_system,
                    f"key:{source_identity_id}",
                    entity_type,
                    Jsonb({"source_key": source_identity_id}),
                    NOW - timedelta(days=30),
                    NOW,
                    state,
                ),
            )
            for record_id in linked_records:
                connection.execute(
                    "INSERT INTO knowledge.source_identity_record "
                    "(source_identity_id, record_id) VALUES (%s, %s)",
                    (source_identity_id, record_id),
                )
        connection.execute(
            "INSERT INTO knowledge.release "
            "(release_id, build_run_id, state, manifest_sha256, created_at) "
            "VALUES (%s, %s, 'candidate', %s, %s)",
            (RELEASE_ID, RUN_ID, _fingerprint("decision-manifest"), NOW),
        )
        for kind, version in (
            ("identity", "v1"),
            ("field_selection", "v1"),
            ("relationship", "v2"),
        ):
            connection.execute(
                "INSERT INTO knowledge.policy "
                "(policy_id, policy_version, policy_kind, content_sha256, effective_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    f"{kind}-policy",
                    version,
                    kind,
                    _fingerprint(f"policy:{kind}"),
                    NOW - timedelta(days=1),
                ),
            )
        if has_identity_resolution_projection:
            connection.execute(
                "INSERT INTO knowledge.identity_resolution_run "
                "(release_id, decision_run_id, identity_method_version, as_of, "
                "policy_id, policy_version, build_authority, request_content, "
                "request_content_sha256, result_content, result_content_sha256) "
                "VALUES (%s, %s, 'identity-v1', %s, 'identity-policy', 'v1', "
                "'offline_canonical_build', %s, %s, %s, %s)",
                (
                    RELEASE_ID,
                    RUN_ID,
                    NOW,
                    Jsonb({"fixture": "decision prerequisites request"}),
                    _fingerprint("decision-prerequisites-request"),
                    Jsonb({"fixture": "decision prerequisites result"}),
                    _fingerprint("decision-prerequisites-result"),
                ),
            )
        for canonical_identity_id, entity_type, source_identity_ids in (
            (
                "professor-c1",
                "professor",
                ("prof-source-a", "prof-source-b", "rejected-source"),
            ),
            (
                "company-c1",
                "company",
                (
                    ("company-source-alt",)
                    if omitted_membership == "company-source"
                    else ("company-source",)
                ),
            ),
        ):
            decision_id = f"identity-decision:{canonical_identity_id}"
            supporting_source_identity_id = source_identity_ids[0]
            supporting_record_id = f"record:{supporting_source_identity_id}"
            supporting_assertion_id = f"identity-assertion:{canonical_identity_id}"
            if has_identity_resolution_projection:
                connection.execute(
                    "INSERT INTO knowledge.source_assertion "
                    "(assertion_id, source_record_id, source_identity_id, "
                    "subject_entity_type, field_path, value, "
                    "assertion_fingerprint_sha256, observed_at, assertion_run_id) "
                    "VALUES (%s, %s, %s, %s, 'identity.fixture', %s, %s, %s, %s)",
                    (
                        supporting_assertion_id,
                        supporting_record_id,
                        supporting_source_identity_id,
                        entity_type,
                        Jsonb(canonical_identity_id),
                        _fingerprint(supporting_assertion_id),
                        NOW,
                        RUN_ID,
                    ),
                )
            connection.execute(
                "INSERT INTO knowledge.identity_decision "
                "(release_id, decision_id, action, policy_id, policy_version, method, "
                "method_version, decision_run_id, confidence, rationale, decided_at) "
                "VALUES (%s, %s, 'create', 'identity-policy', 'v1', 'deterministic', "
                "'identity-v1', %s, 1.0, 'fixture identity', %s)",
                (RELEASE_ID, decision_id, RUN_ID, NOW),
            )
            connection.execute(
                "INSERT INTO knowledge.canonical_identity "
                "(release_id, canonical_identity_id, entity_type, state, display_name, "
                "identity_decision_id) VALUES (%s, %s, %s, 'active', %s, %s)",
                (
                    RELEASE_ID,
                    canonical_identity_id,
                    entity_type,
                    f"Display {canonical_identity_id}",
                    decision_id,
                ),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_output "
                "(release_id, decision_id, canonical_identity_id) "
                "VALUES (%s, %s, %s)",
                (RELEASE_ID, decision_id, canonical_identity_id),
            )
            if has_identity_resolution_projection:
                context_sha256 = _fingerprint(
                    f"identity-context:{canonical_identity_id}"
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
                        Jsonb({"content_sha256": context_sha256}),
                        context_sha256,
                        Jsonb([supporting_assertion_id]),
                    ),
                )
                connection.execute(
                    "INSERT INTO knowledge.identity_decision_record "
                    "(release_id, decision_id, record_id) VALUES (%s, %s, %s)",
                    (RELEASE_ID, decision_id, supporting_record_id),
                )
            for source_identity_id in source_identity_ids:
                if source_identity_id == omitted_membership:
                    continue
                connection.execute(
                    "INSERT INTO knowledge.identity_decision_source_identity "
                    "(release_id, decision_id, source_identity_id) "
                    "VALUES (%s, %s, %s)",
                    (RELEASE_ID, decision_id, source_identity_id),
                )
                if (
                    has_identity_resolution_projection
                    and source_identity_id == supporting_source_identity_id
                ):
                    connection.execute(
                        "INSERT INTO knowledge.identity_decision_assertion "
                        "(release_id, decision_id, assertion_id, source_identity_id, "
                        "source_record_id) VALUES (%s, %s, %s, %s, %s)",
                        (
                            RELEASE_ID,
                            decision_id,
                            supporting_assertion_id,
                            supporting_source_identity_id,
                            supporting_record_id,
                        ),
                    )
                if has_explicit_membership:
                    connection.execute(
                        "INSERT INTO knowledge.canonical_identity_source_membership "
                        "(release_id, canonical_identity_id, source_identity_id) "
                        "VALUES (%s, %s, %s)",
                        (RELEASE_ID, canonical_identity_id, source_identity_id),
                    )
                if has_output_allocation:
                    connection.execute(
                        "INSERT INTO knowledge.identity_decision_output_source "
                        "(release_id, decision_id, canonical_identity_id, "
                        "source_identity_id) VALUES (%s, %s, %s, %s)",
                        (
                            RELEASE_ID,
                            decision_id,
                            canonical_identity_id,
                            source_identity_id,
                        ),
                    )
                if has_identity_resolution_projection:
                    connection.execute(
                        "INSERT INTO knowledge.current_source_identity_assignment "
                        "(release_id, source_identity_id, canonical_identity_id, "
                        "identity_decision_id) VALUES (%s, %s, %s, %s)",
                        (
                            RELEASE_ID,
                            source_identity_id,
                            canonical_identity_id,
                            decision_id,
                        ),
                    )
        connection.execute(
            "INSERT INTO knowledge.relationship_type "
            "(relationship_type_id, version, layer, source_entity_types, "
            "target_entity_types, direction, roles, required_evidence_kinds, "
            "time_semantics, allowed_states, eligible_paths) VALUES "
            "('professor_company_role', 'v1', 'canonical', %s, %s, 'directed', %s, "
            "%s, 'validity_interval', %s, %s)",
            (
                Jsonb(["professor"]),
                Jsonb(["company"]),
                Jsonb([{"role_id": "founder", "applies_to": "source"}]),
                Jsonb(["official_profile"]),
                Jsonb(["accepted", "unresolved", "rejected"]),
                Jsonb(["relationship_traversal"]),
            ),
        )
        connection.commit()


def _insert_reviewed_release_prerequisites(target: _Target) -> None:
    source_identity_ids = ("prof-source-a", "prof-source-b", "rejected-source")
    identity_decision_id = "identity-decision:professor-c1:r2"
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.release "
            "(release_id, build_run_id, state, previous_release_id, manifest_sha256, "
            "created_at) VALUES (%s, %s, 'candidate', %s, %s, %s)",
            (
                REVIEWED_RELEASE_ID,
                REVIEWED_RUN_ID,
                RELEASE_ID,
                _fingerprint("decision-manifest-r2"),
                NOW + timedelta(hours=1),
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_resolution_run "
            "(release_id, decision_run_id, identity_method_version, as_of, policy_id, "
            "policy_version, build_authority, request_content, "
            "request_content_sha256, result_content, result_content_sha256) "
            "VALUES (%s, %s, 'identity-v1', %s, 'identity-policy', 'v1', "
            "'offline_canonical_build', %s, %s, %s, %s)",
            (
                REVIEWED_RELEASE_ID,
                REVIEWED_RUN_ID,
                NOW + timedelta(hours=1),
                Jsonb({"fixture": "reviewed decision prerequisites request"}),
                _fingerprint("reviewed-decision-prerequisites-request"),
                Jsonb({"fixture": "reviewed decision prerequisites result"}),
                _fingerprint("reviewed-decision-prerequisites-result"),
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision "
            "(release_id, decision_id, action, policy_id, policy_version, method, "
            "method_version, decision_run_id, confidence, rationale, decided_at) "
            "VALUES (%s, %s, 'create', 'identity-policy', 'v1', 'deterministic', "
            "'identity-v1', %s, 1.0, 'reviewed release identity fixture', %s)",
            (
                REVIEWED_RELEASE_ID,
                identity_decision_id,
                REVIEWED_RUN_ID,
                NOW + timedelta(hours=1),
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.canonical_identity "
            "(release_id, canonical_identity_id, entity_type, state, display_name, "
            "identity_decision_id) VALUES (%s, 'professor-c1', 'professor', 'active', "
            "'Display professor-c1', %s)",
            (REVIEWED_RELEASE_ID, identity_decision_id),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_output "
            "(release_id, decision_id, canonical_identity_id) "
            "VALUES (%s, %s, 'professor-c1')",
            (REVIEWED_RELEASE_ID, identity_decision_id),
        )
        context_sha256 = _fingerprint("identity-context:professor-c1:r2")
        connection.execute(
            "INSERT INTO knowledge.identity_decision_context "
            "(release_id, decision_id, decision_run_id, context_content, "
            "content_sha256, supporting_assertion_ids) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                REVIEWED_RELEASE_ID,
                identity_decision_id,
                REVIEWED_RUN_ID,
                Jsonb({"content_sha256": context_sha256}),
                context_sha256,
                Jsonb(["identity-assertion:professor-c1"]),
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_record "
            "(release_id, decision_id, record_id) "
            "VALUES (%s, %s, 'record:prof-source-a')",
            (REVIEWED_RELEASE_ID, identity_decision_id),
        )
        for source_identity_id in source_identity_ids:
            connection.execute(
                "INSERT INTO knowledge.identity_decision_source_identity "
                "(release_id, decision_id, source_identity_id) VALUES (%s, %s, %s)",
                (REVIEWED_RELEASE_ID, identity_decision_id, source_identity_id),
            )
            if source_identity_id == "prof-source-a":
                connection.execute(
                    "INSERT INTO knowledge.identity_decision_assertion "
                    "(release_id, decision_id, assertion_id, source_identity_id, "
                    "source_record_id) VALUES (%s, %s, "
                    "'identity-assertion:professor-c1', 'prof-source-a', "
                    "'record:prof-source-a')",
                    (REVIEWED_RELEASE_ID, identity_decision_id),
                )
            connection.execute(
                "INSERT INTO knowledge.canonical_identity_source_membership "
                "(release_id, canonical_identity_id, source_identity_id) "
                "VALUES (%s, 'professor-c1', %s)",
                (REVIEWED_RELEASE_ID, source_identity_id),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_output_source "
                "(release_id, decision_id, canonical_identity_id, source_identity_id) "
                "VALUES (%s, %s, 'professor-c1', %s)",
                (REVIEWED_RELEASE_ID, identity_decision_id, source_identity_id),
            )
            connection.execute(
                "INSERT INTO knowledge.current_source_identity_assignment "
                "(release_id, source_identity_id, canonical_identity_id, "
                "identity_decision_id) VALUES (%s, %s, 'professor-c1', %s)",
                (REVIEWED_RELEASE_ID, source_identity_id, identity_decision_id),
            )
        company_decision_id = "identity-decision:company-c1:r2"
        connection.execute(
            "INSERT INTO knowledge.identity_decision "
            "(release_id, decision_id, action, policy_id, policy_version, method, "
            "method_version, decision_run_id, confidence, rationale, decided_at) "
            "VALUES (%s, %s, 'create', 'identity-policy', 'v1', 'deterministic', "
            "'identity-v1', %s, 1.0, 'reviewed release Company fixture', %s)",
            (
                REVIEWED_RELEASE_ID,
                company_decision_id,
                REVIEWED_RUN_ID,
                NOW + timedelta(hours=1),
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.canonical_identity "
            "(release_id, canonical_identity_id, entity_type, state, display_name, "
            "identity_decision_id) VALUES (%s, 'company-c1', 'company', 'active', "
            "'Display company-c1', %s)",
            (REVIEWED_RELEASE_ID, company_decision_id),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_output "
            "(release_id, decision_id, canonical_identity_id) "
            "VALUES (%s, %s, 'company-c1')",
            (REVIEWED_RELEASE_ID, company_decision_id),
        )
        company_context_sha256 = _fingerprint("identity-context:company-c1:r2")
        connection.execute(
            "INSERT INTO knowledge.identity_decision_context "
            "(release_id, decision_id, decision_run_id, context_content, "
            "content_sha256, supporting_assertion_ids) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                REVIEWED_RELEASE_ID,
                company_decision_id,
                REVIEWED_RUN_ID,
                Jsonb({"content_sha256": company_context_sha256}),
                company_context_sha256,
                Jsonb(["identity-assertion:company-c1"]),
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_record "
            "(release_id, decision_id, record_id) "
            "VALUES (%s, %s, 'record:company-source')",
            (REVIEWED_RELEASE_ID, company_decision_id),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_source_identity "
            "(release_id, decision_id, source_identity_id) "
            "VALUES (%s, %s, 'company-source')",
            (REVIEWED_RELEASE_ID, company_decision_id),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_assertion "
            "(release_id, decision_id, assertion_id, source_identity_id, "
            "source_record_id) VALUES (%s, %s, 'identity-assertion:company-c1', "
            "'company-source', 'record:company-source')",
            (REVIEWED_RELEASE_ID, company_decision_id),
        )
        connection.execute(
            "INSERT INTO knowledge.canonical_identity_source_membership "
            "(release_id, canonical_identity_id, source_identity_id) "
            "VALUES (%s, 'company-c1', 'company-source')",
            (REVIEWED_RELEASE_ID,),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_output_source "
            "(release_id, decision_id, canonical_identity_id, source_identity_id) "
            "VALUES (%s, %s, 'company-c1', 'company-source')",
            (REVIEWED_RELEASE_ID, company_decision_id),
        )
        connection.execute(
            "INSERT INTO knowledge.current_source_identity_assignment "
            "(release_id, source_identity_id, canonical_identity_id, "
            "identity_decision_id) VALUES (%s, 'company-source', 'company-c1', %s)",
            (REVIEWED_RELEASE_ID, company_decision_id),
        )
        connection.commit()


def _insert_snapshot_release_prerequisites(target: _Target) -> None:
    source_identity_ids = ("prof-source-a", "prof-source-b", "rejected-source")
    identity_decision_id = "identity-decision:professor-c1:r3-snapshot"
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.release "
            "(release_id, build_run_id, state, previous_release_id, manifest_sha256, "
            "created_at) VALUES (%s, %s, 'candidate', %s, %s, %s)",
            (
                SNAPSHOT_RELEASE_ID,
                SNAPSHOT_RUN_ID,
                REVIEWED_RELEASE_ID,
                _fingerprint("decision-manifest-r3-snapshot"),
                NOW + timedelta(hours=2),
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_resolution_run "
            "(release_id, decision_run_id, identity_method_version, as_of, policy_id, "
            "policy_version, build_authority, request_content, "
            "request_content_sha256, result_content, result_content_sha256) "
            "VALUES (%s, %s, 'identity-v1', %s, 'identity-policy', 'v1', "
            "'offline_canonical_build', %s, %s, %s, %s)",
            (
                SNAPSHOT_RELEASE_ID,
                SNAPSHOT_RUN_ID,
                NOW + timedelta(hours=2),
                Jsonb({"fixture": "snapshot release identity request"}),
                _fingerprint("snapshot-release-identity-request"),
                Jsonb({"fixture": "snapshot release identity result"}),
                _fingerprint("snapshot-release-identity-result"),
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision "
            "(release_id, decision_id, action, policy_id, policy_version, method, "
            "method_version, decision_run_id, confidence, rationale, decided_at) "
            "VALUES (%s, %s, 'create', 'identity-policy', 'v1', 'deterministic', "
            "'identity-v1', %s, 1.0, 'snapshot release identity fixture', %s)",
            (
                SNAPSHOT_RELEASE_ID,
                identity_decision_id,
                SNAPSHOT_RUN_ID,
                NOW + timedelta(hours=2),
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.canonical_identity "
            "(release_id, canonical_identity_id, entity_type, state, display_name, "
            "identity_decision_id) VALUES (%s, 'professor-c1', 'professor', 'active', "
            "'Display professor-c1', %s)",
            (SNAPSHOT_RELEASE_ID, identity_decision_id),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_output "
            "(release_id, decision_id, canonical_identity_id) "
            "VALUES (%s, %s, 'professor-c1')",
            (SNAPSHOT_RELEASE_ID, identity_decision_id),
        )
        context_sha256 = _fingerprint("identity-context:professor-c1:r3-snapshot")
        connection.execute(
            "INSERT INTO knowledge.identity_decision_context "
            "(release_id, decision_id, decision_run_id, context_content, "
            "content_sha256, supporting_assertion_ids) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                SNAPSHOT_RELEASE_ID,
                identity_decision_id,
                SNAPSHOT_RUN_ID,
                Jsonb({"content_sha256": context_sha256}),
                context_sha256,
                Jsonb(["identity-assertion:professor-c1"]),
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.identity_decision_record "
            "(release_id, decision_id, record_id) "
            "VALUES (%s, %s, 'record:prof-source-a')",
            (SNAPSHOT_RELEASE_ID, identity_decision_id),
        )
        for source_identity_id in source_identity_ids:
            connection.execute(
                "INSERT INTO knowledge.identity_decision_source_identity "
                "(release_id, decision_id, source_identity_id) VALUES (%s, %s, %s)",
                (SNAPSHOT_RELEASE_ID, identity_decision_id, source_identity_id),
            )
            if source_identity_id == "prof-source-a":
                connection.execute(
                    "INSERT INTO knowledge.identity_decision_assertion "
                    "(release_id, decision_id, assertion_id, source_identity_id, "
                    "source_record_id) VALUES (%s, %s, "
                    "'identity-assertion:professor-c1', 'prof-source-a', "
                    "'record:prof-source-a')",
                    (SNAPSHOT_RELEASE_ID, identity_decision_id),
                )
            connection.execute(
                "INSERT INTO knowledge.canonical_identity_source_membership "
                "(release_id, canonical_identity_id, source_identity_id) "
                "VALUES (%s, 'professor-c1', %s)",
                (SNAPSHOT_RELEASE_ID, source_identity_id),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_output_source "
                "(release_id, decision_id, canonical_identity_id, source_identity_id) "
                "VALUES (%s, %s, 'professor-c1', %s)",
                (SNAPSHOT_RELEASE_ID, identity_decision_id, source_identity_id),
            )
            connection.execute(
                "INSERT INTO knowledge.current_source_identity_assignment "
                "(release_id, source_identity_id, canonical_identity_id, "
                "identity_decision_id) VALUES (%s, %s, 'professor-c1', %s)",
                (SNAPSHOT_RELEASE_ID, source_identity_id, identity_decision_id),
            )
        connection.commit()


def _persisted_counts(target: _Target) -> tuple[int, ...]:
    with _connect(target) as connection:
        return connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.source_assertion), "
            "(SELECT count(*) FROM knowledge.relationship_assertion), "
            "(SELECT count(*) FROM knowledge.canonical_decision), "
            "(SELECT count(*) FROM knowledge.canonical_decision_assertion), "
            "(SELECT count(*) FROM knowledge.canonical_decision_constraint_outcome), "
            "(SELECT count(*) FROM knowledge.canonical_decision_identity_context), "
            "(SELECT count(*) FROM knowledge.relationship_decision), "
            "(SELECT count(*) FROM knowledge.relationship_decision_assertion), "
            "(SELECT count(*) FROM knowledge.relationship_decision_constraint_outcome), "
            "(SELECT count(*) FROM knowledge.relationship_decision_identity_context)"
        ).fetchone()


def test_c2_0007_adds_review_provenance_without_a_mutable_queue_table(
    target: _Target,
) -> None:
    revision = ScriptDirectory.from_config(target.config).get_revision("C2_0007")
    assert revision is not None
    assert revision.down_revision == "C2_0006"
    with _connect(target) as connection:
        columns = connection.execute(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'knowledge' "
            "AND column_name = 'human_review_resolution' ORDER BY table_name"
        ).fetchall()
        assert columns == [
            ("canonical_decision",),
            ("identity_decision",),
            ("relationship_decision",),
        ]
        assert connection.execute(
            "SELECT to_regclass('knowledge.review_case'), "
            "to_regclass('ops.review_case')"
        ).fetchone() == (None, None)

    command.downgrade(target.config, "C2_0006")
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'knowledge' "
            "AND column_name = 'human_review_resolution'"
        ).fetchone() == (0,)
    command.upgrade(target.config, "head")


def test_c2_0007_upgrade_refuses_legacy_human_review_without_provenance(
    target: _Target,
) -> None:
    command.downgrade(target.config, "C2_0006")
    _insert_prerequisites(target)
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.canonical_decision "
            "(release_id, decision_id, canonical_identity_id, field_path, state, "
            "policy_id, policy_version, method, method_version, decision_run_id, "
            "confidence, rationale, decided_at) VALUES "
            "(%s, 'legacy-human-review', 'professor-c1', "
            "'employment.current_title', 'unresolved', 'field_selection-policy', "
            "'v1', 'human_review', 'review-v0', %s, 0.0, "
            "'Legacy review lacks immutable reviewer provenance.', %s)",
            (RELEASE_ID, RUN_ID, NOW),
        )
        connection.commit()

    with pytest.raises(sa_exc.DBAPIError) as caught:
        command.upgrade(target.config, "head")
    assert getattr(caught.value.orig, "sqlstate", None) == "55000"
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0006",)
        assert connection.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'knowledge' "
            "AND column_name = 'human_review_resolution'"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT method FROM knowledge.canonical_decision "
            "WHERE decision_id = 'legacy-human-review'"
        ).fetchone() == ("human_review",)


def test_c2_0007_upgrade_refuses_an_existing_supersession_fork(
    target: _Target,
) -> None:
    command.downgrade(target.config, "C2_0006")
    _insert_prerequisites(target)
    with _connect(target) as connection:
        for decision_id, supersedes_decision_id in (
            ("fork-origin", None),
            ("fork-child-a", "fork-origin"),
            ("fork-child-b", "fork-origin"),
        ):
            connection.execute(
                "INSERT INTO knowledge.canonical_decision "
                "(release_id, decision_id, canonical_identity_id, field_path, state, "
                "policy_id, policy_version, method, method_version, decision_run_id, "
                "confidence, rationale, decided_at, supersedes_decision_id) VALUES "
                "(%s, %s, 'professor-c1', 'employment.current_title', 'unresolved', "
                "'field_selection-policy', 'v1', 'deterministic', 'rules-v1', %s, "
                "0.0, 'Migration fork preflight fixture.', %s, %s)",
                (
                    RELEASE_ID,
                    decision_id,
                    f"fork-preflight-{decision_id}",
                    NOW,
                    supersedes_decision_id,
                ),
            )
        connection.commit()

    with pytest.raises(sa_exc.DBAPIError) as caught:
        command.upgrade(target.config, "head")
    assert getattr(caught.value.orig, "sqlstate", None) == "55000"
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0006",)
        assert connection.execute(
            "SELECT decision_id FROM knowledge.canonical_decision "
            "WHERE supersedes_decision_id = 'fork-origin' ORDER BY decision_id"
        ).fetchall() == [("fork-child-a",), ("fork-child-b",)]


def test_c2_0007_upgrade_refuses_duplicate_existing_roots(
    target: _Target,
) -> None:
    command.downgrade(target.config, "C2_0006")
    _insert_prerequisites(target)
    with _connect(target) as connection:
        for decision_id in ("duplicate-root-a", "duplicate-root-b"):
            connection.execute(
                "INSERT INTO knowledge.canonical_decision "
                "(release_id, decision_id, canonical_identity_id, field_path, state, "
                "policy_id, policy_version, method, method_version, decision_run_id, "
                "confidence, rationale, decided_at) VALUES "
                "(%s, %s, 'professor-c1', 'employment.duplicate_root', "
                "'unresolved', 'field_selection-policy', 'v1', 'deterministic', "
                "'rules-v1', %s, 0.0, 'Duplicate root preflight fixture.', %s)",
                (RELEASE_ID, decision_id, f"run-{decision_id}", NOW),
            )
        connection.commit()

    with pytest.raises(sa_exc.DBAPIError) as caught:
        command.upgrade(target.config, "head")
    assert getattr(caught.value.orig, "sqlstate", None) == "55000"
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0006",)
        assert connection.execute(
            "SELECT decision_id FROM knowledge.canonical_decision "
            "WHERE field_path = 'employment.duplicate_root' ORDER BY decision_id"
        ).fetchall() == [("duplicate-root-a",), ("duplicate-root-b",)]


def test_c2_0007_upgrade_refuses_existing_release_cycle(
    target: _Target,
) -> None:
    command.downgrade(target.config, "C2_0006")
    _insert_prerequisites(target)
    cycle_release_id = "decision-postgres-release-cycle-r2"
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.release "
            "(release_id, build_run_id, state, previous_release_id, manifest_sha256, "
            "created_at) VALUES (%s, 'release-cycle-run-r2', 'candidate', %s, %s, %s)",
            (
                cycle_release_id,
                RELEASE_ID,
                _fingerprint("release-cycle-manifest-r2"),
                NOW + timedelta(hours=1),
            ),
        )
        connection.execute(
            "UPDATE knowledge.release SET previous_release_id = %s "
            "WHERE release_id = %s",
            (cycle_release_id, RELEASE_ID),
        )
        connection.commit()

    with pytest.raises(sa_exc.DBAPIError) as caught:
        command.upgrade(target.config, "head")
    assert getattr(caught.value.orig, "sqlstate", None) == "55000"
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0006",)
        assert connection.execute(
            "SELECT previous_release_id FROM knowledge.release WHERE release_id = %s",
            (RELEASE_ID,),
        ).fetchone() == (cycle_release_id,)


def test_c2_0007_upgrade_refuses_non_ancestral_decision_lineage(
    target: _Target,
) -> None:
    command.downgrade(target.config, "C2_0006")
    _insert_prerequisites(target)
    _insert_reviewed_release_prerequisites(target)
    with _connect(target) as connection:
        connection.execute(
            "UPDATE knowledge.release SET previous_release_id = NULL "
            "WHERE release_id = %s",
            (REVIEWED_RELEASE_ID,),
        )
        for release_id, decision_id, supersedes_decision_id in (
            (RELEASE_ID, "non-ancestral-root", None),
            (
                REVIEWED_RELEASE_ID,
                "non-ancestral-child",
                "non-ancestral-root",
            ),
        ):
            connection.execute(
                "INSERT INTO knowledge.canonical_decision "
                "(release_id, decision_id, canonical_identity_id, field_path, state, "
                "policy_id, policy_version, method, method_version, decision_run_id, "
                "confidence, rationale, decided_at, supersedes_decision_id) VALUES "
                "(%s, %s, 'professor-c1', 'employment.non_ancestral', "
                "'unresolved', 'field_selection-policy', 'v1', 'deterministic', "
                "'rules-v1', %s, 0.0, 'Non-ancestral lineage fixture.', %s, %s)",
                (
                    release_id,
                    decision_id,
                    f"run-{decision_id}",
                    NOW,
                    supersedes_decision_id,
                ),
            )
        connection.commit()

    with pytest.raises(sa_exc.DBAPIError) as caught:
        command.upgrade(target.config, "head")
    assert getattr(caught.value.orig, "sqlstate", None) == "55000"
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0006",)
        assert connection.execute(
            "SELECT supersedes_decision_id FROM knowledge.canonical_decision "
            "WHERE decision_id = 'non-ancestral-child'"
        ).fetchone() == ("non-ancestral-root",)


def test_c2_0007_upgrade_refuses_relationship_lineage_metadata_change(
    target: _Target,
) -> None:
    command.downgrade(target.config, "C2_0006")
    _insert_prerequisites(target)
    _insert_reviewed_release_prerequisites(target)
    with _connect(target) as connection:
        for (
            release_id,
            decision_id,
            source_id,
            target_id,
            supersedes_decision_id,
        ) in (
            (
                RELEASE_ID,
                "relationship-metadata-root",
                "professor-c1",
                "company-c1",
                None,
            ),
            (
                REVIEWED_RELEASE_ID,
                "relationship-metadata-child",
                "company-c1",
                "professor-c1",
                "relationship-metadata-root",
            ),
        ):
            connection.execute(
                "INSERT INTO knowledge.relationship_decision "
                "(release_id, decision_id, canonical_relationship_id, "
                "relationship_type_id, relationship_type_version, "
                "source_canonical_identity_id, target_canonical_identity_id, state, "
                "role_bindings, policy_id, policy_version, method, method_version, "
                "decision_run_id, confidence, rationale, decided_at, "
                "supersedes_decision_id) VALUES "
                "(%s, %s, 'relationship-metadata-lineage', "
                "'professor_company_role', 'v1', %s, %s, 'unresolved', '{}'::jsonb, "
                "'relationship-policy', 'v2', 'deterministic', 'rules-v1', %s, "
                "0.0, 'Relationship metadata lineage fixture.', %s, %s)",
                (
                    release_id,
                    decision_id,
                    source_id,
                    target_id,
                    f"run-{decision_id}",
                    NOW,
                    supersedes_decision_id,
                ),
            )
        connection.commit()

    with pytest.raises(sa_exc.DBAPIError) as caught:
        command.upgrade(target.config, "head")
    assert getattr(caught.value.orig, "sqlstate", None) == "55000"
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0006",)
        assert connection.execute(
            "SELECT source_canonical_identity_id, target_canonical_identity_id "
            "FROM knowledge.relationship_decision "
            "WHERE decision_id = 'relationship-metadata-child'"
        ).fetchone() == ("company-c1", "professor-c1")


def test_complete_field_and_relationship_result_round_trips_and_replays_exactly(
    target: _Target,
) -> None:
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == (EXPECTED_REVISION,)
        assert connection.execute(
            "SELECT to_regclass('knowledge.canonical_identity_source_membership')"
        ).fetchone() == ("knowledge.canonical_identity_source_membership",)
    result = _decision_result()
    _insert_prerequisites(target)
    module = _postgres_module()
    store = _store(target)
    assert isinstance(store, module.CanonicalDecisionStore)

    first = store.persist(result)
    counts = _persisted_counts(target)
    replayed = _store(target).persist(result)
    loaded = _store(target).load(RELEASE_ID, RUN_ID)

    assert first == replayed == loaded == result
    assert loaded.model_dump(mode="json") == result.model_dump(mode="json")
    assert loaded.content_sha256 == result.content_sha256
    assert len(loaded.field_assertions) == 3
    assert len(loaded.relationship_assertions) == 2
    assert len(loaded.canonical_decisions) == 1
    assert len(loaded.relationship_decisions) == 1
    assert len(loaded.current_fields) == 1
    assert len(loaded.current_relationships) == 1
    field_outcomes = tuple(
        outcome
        for outcome in loaded.constraint_outcomes
        if outcome.assertion_id.startswith("field-")
    )
    relationship_outcomes = tuple(
        outcome
        for outcome in loaded.constraint_outcomes
        if outcome.assertion_id.startswith("relation-")
    )
    assert len(field_outcomes) == 3
    assert len(relationship_outcomes) == 2
    assert {outcome.policy_version for outcome in field_outcomes} == {"v1"}
    assert {outcome.policy_version for outcome in relationship_outcomes} == {"v2"}
    rejected = next(
        outcome
        for outcome in field_outcomes
        if outcome.assertion_id == "field-rejected"
    )
    assert rejected.admitted is False
    assert rejected.reason_codes == ("source_identity_rejected",)
    assert rejected.policy_version == "v1"
    admitted = tuple(
        outcome
        for outcome in loaded.constraint_outcomes
        if outcome.assertion_id != "field-rejected"
    )
    assert all(outcome.admitted for outcome in admitted)
    assert all(outcome.reason_codes == () for outcome in admitted)
    field_decision = loaded.canonical_decisions[0]
    assert "field-rejected" not in field_decision.candidate_assertion_ids
    assert "field-rejected" not in field_decision.llm_trace.input_evidence_ids
    assert _persisted_counts(target) == counts

    with pytest.raises(
        sa_exc.DBAPIError,
        match=(
            "non-empty|not empty|constraint outcome|outcome|identity-context|"
            "identity resolution|identity history"
        ),
    ):
        command.downgrade(target.config, "C2_0004")
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == (EXPECTED_REVISION,)
    assert _store(target).load(RELEASE_ID, RUN_ID) == result


def test_human_review_provenance_and_release_history_restart_exactly(
    target: _Target,
) -> None:
    initial = _decision_result(field_unresolved=True)
    reviewed = _reviewed_field_result(initial)
    _insert_prerequisites(target)
    _insert_reviewed_release_prerequisites(target)

    store = _store(target)
    assert store.persist(initial) == initial
    assert store.persist(reviewed) == reviewed
    assert _store(target).load(REVIEWED_RELEASE_ID, REVIEWED_RUN_ID) == reviewed

    expected_history = _engine_module().project_decision_history(
        (initial, reviewed),
        as_of=NOW + timedelta(hours=1),
    )
    restarted_history = _store(target).load_history(
        REVIEWED_RELEASE_ID,
        as_of=NOW + timedelta(hours=1),
    )
    assert restarted_history == expected_history
    assert restarted_history.open_review_cases == ()
    assert restarted_history.review_case_history == initial.review_cases
    assert restarted_history.current_fields == reviewed.current_fields
    assert len(restarted_history.relationship_decision_history) == 1
    assert len(restarted_history.current_relationships) == 1

    reviewed_decision = reviewed.canonical_decisions[0]
    with _connect(target) as connection:
        durable_review = connection.execute(
            "SELECT human_review_resolution FROM knowledge.canonical_decision "
            "WHERE decision_id = %s",
            (reviewed_decision.decision_id,),
        ).fetchone()
        assert durable_review == (
            reviewed_decision.human_review_resolution.model_dump(mode="json"),
        )

    with pytest.raises(sa_exc.DBAPIError) as caught:
        command.downgrade(target.config, "C2_0006")
    assert getattr(caught.value.orig, "sqlstate", None) == "55000"
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == (EXPECTED_REVISION,)


def test_review_json_validator_rejects_null_weak_and_hash_tampered_payloads(
    target: _Target,
) -> None:
    initial = _decision_result(field_unresolved=True)
    reviewed = _reviewed_field_result(initial)
    resolution = reviewed.canonical_decisions[0].human_review_resolution
    assert resolution is not None
    valid_payload = resolution.model_dump(mode="json")
    module = _engine_module()
    edge_case_values = resolution.review_case.model_dump(mode="python")
    edge_case_values.pop("review_case_id")
    edge_case_values.pop("content_sha256")
    edge_case_values.update(
        method="deterministic",
        confidence=1e-6,
        rationale='中文 "quoted" \\ path\nretained ambiguity',
        uncertainty=None,
        trace_content_sha256=None,
    )
    edge_case = module.create_review_case(**edge_case_values)
    edge_resolution = module.create_human_review_resolution(
        review_case=edge_case,
        outcome="selected",
        selected_evidence_ids=("field-b",),
        reviewer_id='审核员:"甲"\\一',
        review_policy_id="canonical-review-policy",
        review_policy_version="review-v1",
        review_policy_content_sha256="7" * 64,
        reviewed_at=NOW + timedelta(hours=1),
        rationale='核验 "引用"、反斜线 \\ 与换行\n均保留。',
        confidence=1e-6,
    )
    guc_case_values = dict(edge_case_values)
    guc_case_values["confidence"] = 0.123456789012345
    guc_case = module.create_review_case(**guc_case_values)
    guc_resolution = module.create_human_review_resolution(
        review_case=guc_case,
        outcome="selected",
        selected_evidence_ids=("field-b",),
        reviewer_id="reviewer:float-guc-parity",
        review_policy_id="canonical-review-policy",
        review_policy_version="review-v1",
        review_policy_content_sha256="7" * 64,
        reviewed_at=NOW + timedelta(hours=1),
        rationale="High-precision confidence must hash independently of session GUCs.",
        confidence=0.123456789012345,
    )
    null_family = json.loads(json.dumps(valid_payload))
    null_family["review_case"]["family"] = None
    null_policy_id = json.loads(json.dumps(valid_payload))
    null_policy_id["review_case"]["policy"]["policy_id"] = None
    wrong_case_hash = json.loads(json.dumps(valid_payload))
    wrong_case_hash["review_case"]["content_sha256"] = "0" * 64
    wrong_resolution_hash = json.loads(json.dumps(valid_payload))
    wrong_resolution_hash["content_sha256"] = "1" * 64

    def raw_content_sha256(payload: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

    def rebind_raw_review_hashes(payload: dict[str, Any]) -> dict[str, Any]:
        review_case = payload["review_case"]
        case_content = {
            key: value
            for key, value in review_case.items()
            if key not in {"review_case_id", "content_sha256"}
        }
        case_hash = raw_content_sha256(case_content)
        review_case["content_sha256"] = case_hash
        review_case["review_case_id"] = f"review-case:sha256:{case_hash}"
        resolution_content = {
            key: value
            for key, value in payload.items()
            if key not in {"resolution_id", "content_sha256"}
        }
        resolution_hash = raw_content_sha256(resolution_content)
        payload["content_sha256"] = resolution_hash
        payload["resolution_id"] = f"human-review-resolution:sha256:{resolution_hash}"
        return payload

    plus_eight = timezone(timedelta(hours=8))

    def noncanonical_offset(value: str) -> str:
        return (
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            .astimezone(plus_eight)
            .isoformat()
        )

    noncanonical_case_time = json.loads(json.dumps(valid_payload))
    noncanonical_case_time["review_case"]["created_at"] = noncanonical_offset(
        noncanonical_case_time["review_case"]["created_at"]
    )
    rebind_raw_review_hashes(noncanonical_case_time)
    noncanonical_policy_time = json.loads(json.dumps(valid_payload))
    policy_time = noncanonical_policy_time["review_case"]["policy"]["effective_at"]
    noncanonical_policy_time["review_case"]["policy"]["effective_at"] = (
        noncanonical_offset(policy_time)
    )
    rebind_raw_review_hashes(noncanonical_policy_time)
    noncanonical_reviewed_time = json.loads(json.dumps(valid_payload))
    noncanonical_reviewed_time["reviewed_at"] = noncanonical_offset(
        noncanonical_reviewed_time["reviewed_at"]
    )
    rebind_raw_review_hashes(noncanonical_reviewed_time)
    whitespace_uncertainty = json.loads(json.dumps(valid_payload))
    whitespace_uncertainty["review_case"]["uncertainty"] = (
        "  " + whitespace_uncertainty["review_case"]["uncertainty"] + "  "
    )
    rebind_raw_review_hashes(whitespace_uncertainty)
    integer_case_confidence = json.loads(json.dumps(valid_payload))
    integer_case_confidence["review_case"]["confidence"] = 1
    rebind_raw_review_hashes(integer_case_confidence)
    integer_resolution_confidence = json.loads(json.dumps(valid_payload))
    integer_resolution_confidence["confidence"] = 1
    rebind_raw_review_hashes(integer_resolution_confidence)
    unicode_reviewer_whitespace = json.loads(json.dumps(valid_payload))
    unicode_reviewer_whitespace["reviewer_id"] = (
        "\u00a0" + unicode_reviewer_whitespace["reviewer_id"] + "\u00a0"
    )
    rebind_raw_review_hashes(unicode_reviewer_whitespace)
    unicode_array_whitespace = json.loads(json.dumps(valid_payload))
    for field_name in (
        "candidate_evidence_ids",
        "conflicting_evidence_ids",
    ):
        unicode_array_whitespace["review_case"][field_name] = [
            "\u3000field-b" if value == "field-b" else value
            for value in unicode_array_whitespace["review_case"][field_name]
        ]
    unicode_array_whitespace["selected_evidence_ids"] = ("\u3000field-b",)
    rebind_raw_review_hashes(unicode_array_whitespace)
    relationship_initial = _decision_result(relationship_unresolved=True)
    relationship_resolution = (
        _reviewed_relationship_result(relationship_initial)
        .relationship_decisions[0]
        .human_review_resolution
    )
    assert relationship_resolution is not None
    unicode_role_whitespace = relationship_resolution.model_dump(mode="json")
    unicode_role_whitespace["role_bindings"] = {"source": "\u3000founder"}
    rebind_raw_review_hashes(unicode_role_whitespace)

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT COALESCE(knowledge.is_valid_human_review_resolution(%s), FALSE)",
            (Jsonb(valid_payload),),
        ).fetchone() == (True,)
        assert connection.execute(
            "SELECT COALESCE(knowledge.is_valid_human_review_resolution(%s), FALSE)",
            (Jsonb(edge_resolution.model_dump(mode="json")),),
        ).fetchone() == (True,)
        assert connection.execute(
            "SELECT COALESCE(knowledge.is_valid_human_review_resolution(%s), FALSE)",
            (Jsonb(guc_resolution.model_dump(mode="json")),),
        ).fetchone() == (True,)
        connection.execute("SET LOCAL extra_float_digits = -15")
        assert connection.execute(
            "SELECT COALESCE(knowledge.is_valid_human_review_resolution(%s), FALSE)",
            (Jsonb(guc_resolution.model_dump(mode="json")),),
        ).fetchone() == (True,)
        connection.execute("SET LOCAL extra_float_digits = 3")
        for label, payload in (
            ("null family", null_family),
            ("null policy ID", null_policy_id),
            ("wrong case hash", wrong_case_hash),
            ("wrong resolution hash", wrong_resolution_hash),
            ("noncanonical case time", noncanonical_case_time),
            ("noncanonical policy time", noncanonical_policy_time),
            ("noncanonical reviewed time", noncanonical_reviewed_time),
            ("whitespace uncertainty", whitespace_uncertainty),
            ("integer case confidence", integer_case_confidence),
            ("integer resolution confidence", integer_resolution_confidence),
            ("Unicode reviewer whitespace", unicode_reviewer_whitespace),
            ("Unicode array whitespace", unicode_array_whitespace),
            ("Unicode role whitespace", unicode_role_whitespace),
        ):
            assert connection.execute(
                "SELECT COALESCE("
                "knowledge.is_valid_human_review_resolution(%s), FALSE)",
                (Jsonb(payload),),
            ).fetchone() == (False,), label


@pytest.mark.parametrize("family", ("field", "relationship"))
def test_direct_sql_review_rows_reject_null_hash_and_relational_cross_wiring(
    target: _Target,
    family: str,
) -> None:
    initial = _decision_result(
        field_unresolved=family == "field",
        relationship_unresolved=family == "relationship",
    )
    reviewed = (
        _reviewed_field_result(initial)
        if family == "field"
        else _reviewed_relationship_result(initial)
    )
    _insert_prerequisites(target)
    _insert_reviewed_release_prerequisites(target)
    assert _store(target).persist(initial) == initial
    assert _store(target).persist(reviewed) == reviewed

    if family == "field":
        decision = reviewed.canonical_decisions[0]
        table = "canonical_decision"
        insert_sql = (
            "INSERT INTO knowledge.canonical_decision "
            "(release_id, decision_id, canonical_identity_id, field_path, state, "
            "policy_id, policy_version, method, method_version, decision_run_id, "
            "confidence, rationale, decided_at, supersedes_decision_id, llm_trace, "
            "human_review_resolution) "
            "SELECT release_id, %s, canonical_identity_id, %s, %s, "
            "policy_id, policy_version, method, method_version, decision_run_id, "
            "confidence, rationale, decided_at, NULL, llm_trace, "
            "%s::jsonb FROM knowledge.canonical_decision WHERE decision_id = %s"
        )
        crosswired_state = "rejected"
        trigger = "trg_validate_field_human_review_binding"
    else:
        decision = reviewed.relationship_decisions[0]
        table = "relationship_decision"
        insert_sql = (
            "INSERT INTO knowledge.relationship_decision "
            "(release_id, decision_id, canonical_relationship_id, "
            "relationship_type_id, relationship_type_version, "
            "source_canonical_identity_id, target_canonical_identity_id, state, "
            "role_bindings, policy_id, policy_version, method, method_version, "
            "decision_run_id, confidence, rationale, valid_from, valid_to, decided_at, "
            "valid_from_temporal, valid_to_temporal, supersedes_decision_id, "
            "llm_trace, human_review_resolution) "
            "SELECT release_id, %s, %s, relationship_type_id, "
            "relationship_type_version, source_canonical_identity_id, "
            "target_canonical_identity_id, %s, role_bindings, policy_id, "
            "policy_version, method, method_version, decision_run_id, confidence, "
            "rationale, valid_from, valid_to, decided_at, valid_from_temporal, "
            "valid_to_temporal, NULL, "
            "llm_trace, %s::jsonb FROM knowledge.relationship_decision "
            "WHERE decision_id = %s"
        )
        crosswired_state = "rejected"
        trigger = "trg_validate_relationship_human_review_binding"
    resolution = decision.human_review_resolution
    assert resolution is not None
    valid_payload = resolution.model_dump(mode="json")
    wrong_hash = json.loads(json.dumps(valid_payload))
    wrong_hash["content_sha256"] = "0" * 64

    def direct_insert_params(
        decision_id: str,
        state: str,
        payload: dict[str, Any] | None,
    ) -> tuple[Any, ...]:
        review_json = Jsonb(payload) if payload is not None else None
        if family == "relationship":
            return (
                decision_id,
                f"canonical-relationship:{decision_id}",
                state,
                review_json,
                decision.decision_id,
            )
        return (
            decision_id,
            f"employment.invalid_review.{decision_id}",
            state,
            review_json,
            decision.decision_id,
        )

    with _connect(target) as connection:
        for suffix, payload in (("sql-null", None), ("wrong-hash", wrong_hash)):
            with pytest.raises(psycopg.errors.CheckViolation):
                with connection.transaction():
                    connection.execute(
                        insert_sql,
                        direct_insert_params(
                            f"direct-{family}-{suffix}",
                            decision.state.value,
                            payload,
                        ),
                    )

        with pytest.raises(
            psycopg.errors.CheckViolation,
            match="human review|review provenance|review binding",
        ):
            with connection.transaction():
                connection.execute(
                    insert_sql,
                    direct_insert_params(
                        f"direct-{family}-crosswired",
                        crosswired_state,
                        valid_payload,
                    ),
                )
                connection.execute(f"SET CONSTRAINTS knowledge.{trigger} IMMEDIATE")

        if family == "field":
            origin = initial.canonical_decisions[0]
            with pytest.raises(
                psycopg.errors.CheckViolation,
                match="human review|review provenance|review binding|origin evidence",
            ):
                with connection.transaction():
                    connection.execute(
                        "INSERT INTO knowledge.canonical_decision_assertion "
                        "(release_id, decision_id, assertion_id, assertion_role) "
                        "VALUES (%s, %s, 'field-rejected', 'candidate')",
                        (origin.release_id, origin.decision_id),
                    )
                    connection.execute(
                        "SET CONSTRAINTS knowledge."
                        "trg_validate_field_human_review_assertion_binding IMMEDIATE"
                    )
        assert connection.execute(
            f"SELECT count(*) FROM knowledge.{table} WHERE decision_id LIKE 'direct-%'"
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    (
        "family",
        "edge_table",
        "decision_table",
        "assertion_id",
        "assertion_role",
        "edge_trigger",
    ),
    (
        (
            "field",
            "canonical_decision_assertion",
            "canonical_decision",
            "field-rejected",
            "candidate",
            "trg_validate_field_human_review_assertion_binding",
        ),
        (
            "relationship",
            "relationship_decision_assertion",
            "relationship_decision",
            "relation-late-review-race",
            "candidate",
            "trg_validate_relationship_human_review_assertion_binding",
        ),
    ),
)
def test_concurrent_late_origin_edge_and_review_cannot_both_commit(
    target: _Target,
    family: str,
    edge_table: str,
    decision_table: str,
    assertion_id: str,
    assertion_role: str,
    edge_trigger: str,
) -> None:
    initial = _decision_result(
        field_unresolved=family == "field",
        relationship_unresolved=family == "relationship",
    )
    reviewed = (
        _reviewed_field_result(initial)
        if family == "field"
        else _reviewed_relationship_result(initial)
    )
    origin = (
        initial.canonical_decisions[0]
        if family == "field"
        else initial.relationship_decisions[0]
    )
    _insert_prerequisites(target)
    _insert_reviewed_release_prerequisites(target)
    assert _store(target).persist(initial) == initial

    application_name = f"canonical_v2_{family}_late_edge_review_race"
    store_url = (
        make_url(target.database_url)
        .update_query_dict({"application_name": application_name})
        .render_as_string(hide_password=False)
    )
    store = _postgres_module().create_postgres_canonical_decision_store(
        database_url=store_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
    )
    late_edge = _connect(target)
    controller = _connect(target, autocommit=True)
    executor = ThreadPoolExecutor(max_workers=1)
    persist = None
    edge_released = False
    persist_consumed = False
    try:
        if family == "relationship":
            late_edge.execute(
                "INSERT INTO knowledge.relationship_assertion "
                "(assertion_id, relationship_type_id, relationship_type_version, "
                "source_record_id, source_identity_id, target_identity_id, "
                "attributes, assertion_fingerprint_sha256, observed_at, "
                "source_event_time, valid_from, valid_to, valid_from_temporal, "
                "valid_to_temporal, assertion_run_id) "
                "SELECT %s, relationship_type_id, relationship_type_version, "
                "source_record_id, source_identity_id, target_identity_id, "
                "attributes, %s, observed_at, source_event_time, valid_from, "
                "valid_to, valid_from_temporal, valid_to_temporal, "
                "assertion_run_id FROM knowledge.relationship_assertion "
                "WHERE assertion_id = 'relation-founder'",
                (assertion_id, _fingerprint(assertion_id)),
            )
        late_edge.execute(
            f"INSERT INTO knowledge.{edge_table} "
            "(release_id, decision_id, assertion_id, assertion_role) "
            "VALUES (%s, %s, %s, %s)",
            (
                origin.release_id,
                origin.decision_id,
                assertion_id,
                assertion_role,
            ),
        )
        late_edge.execute(f"SET CONSTRAINTS knowledge.{edge_trigger} IMMEDIATE")

        persist = executor.submit(store.persist, reviewed)
        poll = Event()
        deadline = time.monotonic() + 10.0
        lock_wait = None
        while time.monotonic() < deadline:
            lock_wait = controller.execute(
                "SELECT wait_event_type, wait_event FROM pg_stat_activity "
                "WHERE datname = current_database() AND application_name = %s",
                (application_name,),
            ).fetchone()
            if lock_wait is not None and lock_wait[0] == "Lock":
                break
            if persist.done():
                break
            poll.wait(0.01)

        if persist.done():
            assert persist.result(timeout=10.0) == reviewed
            persist_consumed = True
            late_edge.commit()
            edge_released = True
            pytest.fail("concurrent late origin edge and review both committed")

        assert lock_wait is not None
        assert lock_wait[0] == "Lock"
        late_edge.commit()
        edge_released = True
        with pytest.raises(
            _postgres_module().CanonicalDecisionPersistenceError,
            match="transaction|verification|persist|human review|evidence",
        ):
            persist.result(timeout=10.0)
        persist_consumed = True

        with _connect(target) as connection:
            assert connection.execute(
                f"SELECT count(*) FROM knowledge.{decision_table} "
                "WHERE release_id = %s",
                (REVIEWED_RELEASE_ID,),
            ).fetchone() == (0,)
            assert connection.execute(
                f"SELECT count(*) FROM knowledge.{edge_table} "
                "WHERE release_id = %s AND decision_id = %s "
                "AND assertion_id = %s AND assertion_role = %s",
                (
                    origin.release_id,
                    origin.decision_id,
                    assertion_id,
                    assertion_role,
                ),
            ).fetchone() == (1,)
    finally:
        if not edge_released:
            late_edge.rollback()
        late_edge.close()
        controller.close()
        if persist is not None and not persist_consumed:
            try:
                persist.result(timeout=10.0)
            except _postgres_module().CanonicalDecisionPersistenceError:
                pass
        executor.shutdown(wait=True, cancel_futures=True)


def test_release_lineage_is_immutable_while_state_progress_can_continue(
    target: _Target,
) -> None:
    initial = _decision_result(field_unresolved=True)
    reviewed = _reviewed_field_result(initial)
    _insert_prerequisites(target)
    _insert_reviewed_release_prerequisites(target)
    store = _store(target)
    assert store.persist(initial) == initial
    assert store.persist(reviewed) == reviewed
    before = store.load_history(
        REVIEWED_RELEASE_ID,
        as_of=NOW + timedelta(hours=1),
    )

    with pytest.raises(
        psycopg.errors.ObjectNotInPrerequisiteState,
        match="release history|immutable",
    ):
        with _connect(target) as connection:
            connection.execute(
                "UPDATE knowledge.release SET previous_release_id = NULL "
                "WHERE release_id = %s",
                (REVIEWED_RELEASE_ID,),
            )
            connection.commit()
    with pytest.raises(
        psycopg.errors.ObjectNotInPrerequisiteState,
        match="release history|immutable",
    ):
        with _connect(target) as connection:
            connection.execute(
                "DELETE FROM knowledge.release WHERE release_id = %s",
                (REVIEWED_RELEASE_ID,),
            )
            connection.commit()

    with _connect(target) as connection:
        connection.execute(
            "UPDATE knowledge.release SET state = 'verified' WHERE release_id = %s",
            (REVIEWED_RELEASE_ID,),
        )
        connection.commit()
    after = _store(target).load_history(
        REVIEWED_RELEASE_ID,
        as_of=NOW + timedelta(hours=1),
    )
    assert after == before
    assert after.content_sha256 == before.content_sha256


def test_stale_supersession_branch_rolls_back_before_commit(
    target: _Target,
) -> None:
    initial = _decision_result(field_unresolved=True)
    reviewed = _reviewed_field_result(initial)
    stale_branch = _reviewed_field_result(
        initial,
        decision_run_id="decision-postgres-run-3-stale-branch",
        as_of=NOW + timedelta(hours=2),
    )
    _insert_prerequisites(target)
    _insert_reviewed_release_prerequisites(target)
    store = _store(target)
    assert store.persist(initial) == initial
    assert store.persist(reviewed) == reviewed
    counts = _persisted_counts(target)
    expected_history = _engine_module().project_decision_history(
        (initial, reviewed),
        as_of=NOW + timedelta(hours=2),
    )

    with pytest.raises(
        _postgres_module().CanonicalDecisionPersistenceError,
        match="branch|head|supersed|lineage|transaction|persist",
    ):
        store.persist(stale_branch)

    assert _persisted_counts(target) == counts
    assert (
        store.load_history(
            REVIEWED_RELEASE_ID,
            as_of=NOW + timedelta(hours=2),
        )
        == expected_history
    )


def test_unlinked_later_root_rolls_back_before_commit(
    target: _Target,
) -> None:
    initial = _decision_result(field_unresolved=True)
    reviewed = _reviewed_field_result(initial)
    unlinked_root = _ordinary_field_replacement_result(
        initial,
        reviewed,
        linked=False,
    )
    assert unlinked_root.canonical_decisions[0].supersedes_decision_id is None
    _insert_prerequisites(target)
    _insert_reviewed_release_prerequisites(target)
    _insert_snapshot_release_prerequisites(target)
    store = _store(target)
    assert store.persist(initial) == initial
    assert store.persist(reviewed) == reviewed
    counts = _persisted_counts(target)
    expected_history = _engine_module().project_decision_history(
        (initial, reviewed),
        as_of=NOW + timedelta(hours=2),
    )

    with pytest.raises(
        _postgres_module().CanonicalDecisionPersistenceError,
        match="root|head|lineage|ancestry|transaction|persist",
    ):
        store.persist(unlinked_root)

    assert _persisted_counts(target) == counts
    assert (
        store.load_history(
            SNAPSHOT_RELEASE_ID,
            as_of=NOW + timedelta(hours=2),
        )
        == expected_history
    )


def test_concurrent_duplicate_roots_cannot_both_commit(
    target: _Target,
) -> None:
    _insert_prerequisites(target)
    first_connection = _connect(target)
    second_started = Event()

    def insert_second_root() -> None:
        with _connect(target) as connection:
            second_started.set()
            connection.execute(
                "INSERT INTO knowledge.canonical_decision "
                "(release_id, decision_id, canonical_identity_id, field_path, state, "
                "policy_id, policy_version, method, method_version, decision_run_id, "
                "confidence, rationale, decided_at) VALUES "
                "(%s, 'concurrent-root-b', 'professor-c1', "
                "'employment.concurrent_root', 'unresolved', "
                "'field_selection-policy', 'v1', 'deterministic', 'rules-v1', "
                "'concurrent-root-run-b', 0.0, 'Concurrent root B.', %s)",
                (RELEASE_ID, NOW),
            )
            connection.commit()

    try:
        first_connection.execute(
            "INSERT INTO knowledge.canonical_decision "
            "(release_id, decision_id, canonical_identity_id, field_path, state, "
            "policy_id, policy_version, method, method_version, decision_run_id, "
            "confidence, rationale, decided_at) VALUES "
            "(%s, 'concurrent-root-a', 'professor-c1', "
            "'employment.concurrent_root', 'unresolved', "
            "'field_selection-policy', 'v1', 'deterministic', 'rules-v1', "
            "'concurrent-root-run-a', 0.0, 'Concurrent root A.', %s)",
            (RELEASE_ID, NOW),
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            second = executor.submit(insert_second_root)
            assert second_started.wait(timeout=10.0)
            time.sleep(0.1)
            assert not second.done()
            first_connection.commit()
            with pytest.raises(psycopg.errors.UniqueViolation):
                second.result(timeout=10.0)
    finally:
        if not first_connection.closed:
            first_connection.rollback()
            first_connection.close()

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT decision_id FROM knowledge.canonical_decision "
            "WHERE canonical_identity_id = 'professor-c1' "
            "AND field_path = 'employment.concurrent_root'"
        ).fetchall() == [("concurrent-root-a",)]


def test_c2_0007_direct_sql_rejects_non_ancestral_and_metadata_lineage(
    target: _Target,
) -> None:
    _insert_prerequisites(target)
    _insert_reviewed_release_prerequisites(target)
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.canonical_decision "
            "(release_id, decision_id, canonical_identity_id, field_path, state, "
            "policy_id, policy_version, method, method_version, decision_run_id, "
            "confidence, rationale, decided_at) VALUES "
            "(%s, 'same-release-root', 'professor-c1', "
            "'employment.same_release_lineage', 'unresolved', "
            "'field_selection-policy', 'v1', 'deterministic', 'rules-v1', "
            "'same-release-root-run', 0.0, 'Same release root.', %s)",
            (RELEASE_ID, NOW),
        )
        connection.commit()
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "INSERT INTO knowledge.canonical_decision "
                "(release_id, decision_id, canonical_identity_id, field_path, state, "
                "policy_id, policy_version, method, method_version, decision_run_id, "
                "confidence, rationale, decided_at, supersedes_decision_id) VALUES "
                "(%s, 'same-release-child', 'professor-c1', "
                "'employment.same_release_lineage', 'unresolved', "
                "'field_selection-policy', 'v1', 'deterministic', 'rules-v1', "
                "'same-release-child-run', 0.0, 'Same release child.', %s, "
                "'same-release-root')",
                (RELEASE_ID, NOW),
            )
        connection.rollback()

        connection.execute(
            "INSERT INTO knowledge.relationship_decision "
            "(release_id, decision_id, canonical_relationship_id, "
            "relationship_type_id, relationship_type_version, "
            "source_canonical_identity_id, target_canonical_identity_id, state, "
            "role_bindings, policy_id, policy_version, method, method_version, "
            "decision_run_id, confidence, rationale, decided_at) VALUES "
            "(%s, 'metadata-direct-root', 'metadata-direct-lineage', "
            "'professor_company_role', 'v1', 'professor-c1', 'company-c1', "
            "'unresolved', '{}'::jsonb, 'relationship-policy', 'v2', "
            "'deterministic', 'rules-v1', 'metadata-direct-root-run', 0.0, "
            "'Metadata direct root.', %s)",
            (RELEASE_ID, NOW),
        )
        connection.commit()
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                "INSERT INTO knowledge.relationship_decision "
                "(release_id, decision_id, canonical_relationship_id, "
                "relationship_type_id, relationship_type_version, "
                "source_canonical_identity_id, target_canonical_identity_id, state, "
                "role_bindings, policy_id, policy_version, method, method_version, "
                "decision_run_id, confidence, rationale, decided_at, "
                "supersedes_decision_id) VALUES "
                "(%s, 'metadata-direct-child', 'metadata-direct-lineage', "
                "'professor_company_role', 'v1', 'company-c1', 'professor-c1', "
                "'unresolved', '{}'::jsonb, 'relationship-policy', 'v2', "
                "'deterministic', 'rules-v1', 'metadata-direct-child-run', 0.0, "
                "'Metadata direct child.', %s, 'metadata-direct-root')",
                (REVIEWED_RELEASE_ID, NOW + timedelta(hours=1)),
            )
        connection.rollback()

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT count(*) FROM knowledge.canonical_decision "
            "WHERE decision_id = 'same-release-child'"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM knowledge.relationship_decision "
            "WHERE decision_id = 'metadata-direct-child'"
        ).fetchone() == (0,)


def test_history_load_uses_one_repeatable_read_only_snapshot(
    target: _Target,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = _decision_result(field_unresolved=True)
    reviewed = _reviewed_field_result(initial)
    replacement = _ordinary_field_replacement_result(initial, reviewed)
    _insert_prerequisites(target)
    _insert_reviewed_release_prerequisites(target)
    _insert_snapshot_release_prerequisites(target)
    store = _store(target)
    assert store.persist(initial) == initial
    assert store.persist(reviewed) == reviewed
    expected = _engine_module().project_decision_history(
        (initial, reviewed),
        as_of=NOW + timedelta(hours=2),
    )

    module = _postgres_module()
    store_type = module._PostgresCanonicalDecisionStore
    original = store_type._release_decision_runs
    load_paused = Event()
    resume_load = Event()
    pause_once = True

    def pause_before_reviewed_runs(
        connection: Any,
        *,
        release_id: str,
    ) -> tuple[str, ...]:
        nonlocal pause_once
        if release_id == SNAPSHOT_RELEASE_ID and pause_once:
            pause_once = False
            load_paused.set()
            assert resume_load.wait(timeout=10.0)
        return original(connection, release_id=release_id)

    monkeypatch.setattr(
        store_type,
        "_release_decision_runs",
        staticmethod(pause_before_reviewed_runs),
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            _store(target).load_history,
            SNAPSHOT_RELEASE_ID,
            as_of=NOW + timedelta(hours=2),
        )
        assert load_paused.wait(timeout=10.0)
        assert _store(target).persist(replacement) == replacement
        resume_load.set()
        snapshot = future.result(timeout=10.0)

    assert snapshot == expected
    assert _store(target).load_history(
        SNAPSHOT_RELEASE_ID,
        as_of=NOW + timedelta(hours=2),
    ) == _engine_module().project_decision_history(
        (initial, reviewed, replacement),
        as_of=NOW + timedelta(hours=2),
    )


def test_temporal_relationship_history_restarts_with_only_as_of_current(
    target: _Target,
) -> None:
    result = _decision_result(temporal_history=True)
    changed = _decision_result(changed=True, temporal_history=True)
    _insert_prerequisites(target)

    persisted = _store(target).persist(result)
    counts = _persisted_counts(target)
    loaded = _store(target).load(RELEASE_ID, RUN_ID)

    assert persisted == loaded == result
    assert len(loaded.relationship_assertions) == 2
    assert len(loaded.relationship_decisions) == 2
    assert tuple(
        current.canonical_relationship_id for current in loaded.current_relationships
    ) == ("canonical-relationship-current",)
    assert {
        decision.canonical_relationship_id: (
            decision.valid_from,
            decision.valid_to,
        )
        for decision in loaded.relationship_decisions
    } == {
        "canonical-relationship-current": (
            _engine_module().TemporalInstantValue(value=NOW),
            None,
        ),
        "canonical-relationship-old": (
            _engine_module().TemporalInstantValue(value=NOW - timedelta(days=365)),
            _engine_module().TemporalInstantValue(value=NOW),
        ),
    }
    assert {
        assertion.assertion_id: (
            assertion.observed_at,
            assertion.source_event_time,
            assertion.valid_from,
            assertion.valid_to,
        )
        for assertion in loaded.relationship_assertions
    } == {
        "relation-role-current": (
            NOW - timedelta(days=1),
            NOW,
            _engine_module().TemporalInstantValue(value=NOW),
            None,
        ),
        "relation-role-old": (
            NOW - timedelta(days=400),
            NOW - timedelta(days=365),
            _engine_module().TemporalInstantValue(value=NOW - timedelta(days=365)),
            _engine_module().TemporalInstantValue(value=NOW),
        ),
    }

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT assertion_id, observed_at, source_event_time, valid_from, valid_to "
            "FROM knowledge.relationship_assertion ORDER BY assertion_id"
        ).fetchall() == [
            (
                "relation-role-current",
                NOW - timedelta(days=1),
                NOW,
                NOW,
                None,
            ),
            (
                "relation-role-old",
                NOW - timedelta(days=400),
                NOW - timedelta(days=365),
                NOW - timedelta(days=365),
                NOW,
            ),
        ]
        assert connection.execute(
            "SELECT canonical_relationship_id, valid_from, valid_to "
            "FROM knowledge.relationship_decision "
            "ORDER BY canonical_relationship_id"
        ).fetchall() == [
            ("canonical-relationship-current", NOW, None),
            (
                "canonical-relationship-old",
                NOW - timedelta(days=365),
                NOW,
            ),
        ]

    with pytest.raises(
        _postgres_module().CanonicalDecisionPersistenceError,
        match="content|conflict|replay|decision_run_id|run",
    ):
        _store(target).persist(changed)

    assert _store(target).load(RELEASE_ID, RUN_ID) == result
    assert _persisted_counts(target) == counts
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT count(*) FROM knowledge.source_assertion "
            "WHERE assertion_id = 'field-b-changed'"
        ).fetchone() == (0,)


def test_date_only_temporal_precision_restarts_without_utc_midnight_coercion(
    target: _Target,
) -> None:
    result = _decision_result(date_only_field=True)
    _insert_prerequisites(target)

    persisted = _store(target).persist(result)
    restarted = _store(target).load(RELEASE_ID, RUN_ID)
    selected = next(
        assertion
        for assertion in restarted.field_assertions
        if assertion.assertion_id == "field-b"
    )

    assert persisted == restarted == result
    assert selected.valid_from == _engine_module().TemporalDateValue(
        value=date(2024, 9, 1)
    )
    assert restarted.current_fields[0].valid_from == selected.valid_from
    assert restarted.temporal_comparison_context == result.temporal_comparison_context
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT valid_from_temporal, valid_from FROM knowledge.source_assertion "
            "WHERE assertion_id = 'field-b'"
        ).fetchone() == (
            {"precision": "date", "value": "2024-09-01"},
            None,
        )


def test_c2_0008_backfills_and_rehashes_existing_instant_assertions(
    target: _Target,
) -> None:
    command.downgrade(target.config, "C2_0007")
    _insert_prerequisites(target)
    module = _engine_module()
    field_assertion = module.SourceAssertion(
        assertion_id="legacy-field-instant",
        source_record_id="record:prof-source-a",
        source_identity_id="prof-source-a",
        subject_entity_type="professor",
        field_path="employment.started_at",
        value="Chair Professor",
        observed_at=NOW,
        valid_from=NOW - timedelta(days=365),
        assertion_run_id="legacy-temporal-run",
    )
    relationship_assertion = module.RelationshipAssertion(
        assertion_id="legacy-relationship-instant",
        relationship_type_id="professor_company_role",
        relationship_type_version="v1",
        source_record_id="record:relationship",
        source_endpoint=module.IdentityReference(
            identity_id="prof-source-a",
            identity_space="source",
            entity_type="professor",
        ),
        target_endpoint=module.IdentityReference(
            identity_id="company-source",
            identity_space="source",
            entity_type="company",
        ),
        attributes={"role": "founder"},
        observed_at=NOW,
        valid_from=NOW - timedelta(days=365),
        assertion_run_id="legacy-temporal-run",
    )
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.source_assertion "
            "(assertion_id, source_record_id, source_identity_id, "
            "subject_entity_type, field_path, value, assertion_fingerprint_sha256, "
            "observed_at, source_event_time, valid_from, valid_to, assertion_run_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, NULL, %s)",
            (
                field_assertion.assertion_id,
                field_assertion.source_record_id,
                field_assertion.source_identity_id,
                field_assertion.subject_entity_type,
                field_assertion.field_path,
                Jsonb(field_assertion.value),
                "a" * 64,
                field_assertion.observed_at,
                field_assertion.valid_from.value,
                field_assertion.assertion_run_id,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.relationship_assertion "
            "(assertion_id, relationship_type_id, relationship_type_version, "
            "source_record_id, source_identity_id, target_identity_id, attributes, "
            "assertion_fingerprint_sha256, observed_at, source_event_time, "
            "valid_from, valid_to, assertion_run_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, NULL, %s)",
            (
                relationship_assertion.assertion_id,
                relationship_assertion.relationship_type_id,
                relationship_assertion.relationship_type_version,
                relationship_assertion.source_record_id,
                relationship_assertion.source_endpoint.identity_id,
                relationship_assertion.target_endpoint.identity_id,
                Jsonb(relationship_assertion.attributes),
                "b" * 64,
                relationship_assertion.observed_at,
                relationship_assertion.valid_from.value,
                relationship_assertion.assertion_run_id,
            ),
        )
        connection.commit()

    for _ in range(2):
        command.upgrade(target.config, EXPECTED_REVISION)
        with _connect(target) as connection:
            assert connection.execute(
                "SELECT assertion_fingerprint_sha256, valid_from_temporal "
                "FROM knowledge.source_assertion WHERE assertion_id = %s",
                (field_assertion.assertion_id,),
            ).fetchone() == (
                _postgres_module()._assertion_fingerprint(field_assertion),
                {
                    "precision": "instant",
                    "value": "2025-07-11T23:30:00Z",
                },
            )
            assert connection.execute(
                "SELECT assertion_fingerprint_sha256, valid_from_temporal "
                "FROM knowledge.relationship_assertion WHERE assertion_id = %s",
                (relationship_assertion.assertion_id,),
            ).fetchone() == (
                _postgres_module()._assertion_fingerprint(relationship_assertion),
                {
                    "precision": "instant",
                    "value": "2025-07-11T23:30:00Z",
                },
            )
        command.downgrade(target.config, "C2_0007")


def test_c2_0008_refuses_to_rehash_referenced_temporal_evidence(
    target: _Target,
) -> None:
    result = _decision_result(temporal_history=True)
    _insert_prerequisites(target)
    assert _store(target).persist(result) == result
    command.downgrade(target.config, "C2_0007")

    with pytest.raises(sa_exc.DBAPIError, match="referenced decision evidence"):
        command.upgrade(target.config, EXPECTED_REVISION)

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0007",)


def test_temporal_precision_tampering_is_rejected_on_restart(target: _Target) -> None:
    result = _decision_result(date_only_field=True)
    _insert_prerequisites(target)
    assert _store(target).persist(result) == result

    with _connect(target, autocommit=True) as connection:
        connection.execute(
            "ALTER TABLE knowledge.source_assertion DISABLE TRIGGER USER"
        )
        try:
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    "UPDATE knowledge.source_assertion SET valid_from_temporal = "
                    "jsonb_set(valid_from_temporal, '{precision}', '\"instant\"') "
                    "WHERE assertion_id = 'field-b'"
                )
        finally:
            connection.execute(
                "ALTER TABLE knowledge.source_assertion ENABLE TRIGGER USER"
            )

    assert _store(target).load(RELEASE_ID, RUN_ID) == result


def test_c2_0008_downgrade_refuses_to_discard_date_precision(
    target: _Target,
) -> None:
    result = _decision_result(date_only_field=True)
    _insert_prerequisites(target)
    assert _store(target).persist(result) == result

    with pytest.raises(sa_exc.DBAPIError, match="date precision|temporal context"):
        command.downgrade(target.config, "C2_0007")

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == (EXPECTED_REVISION,)
    assert _store(target).load(RELEASE_ID, RUN_ID) == result


def test_direct_sql_cannot_cross_wire_relationship_temporal_precision(
    target: _Target,
) -> None:
    result = _decision_result(temporal_history=True)
    _insert_prerequisites(target)
    assert _store(target).persist(result) == result

    with _connect(target) as connection:
        with pytest.raises(psycopg.errors.CheckViolation, match="temporal validity"):
            with connection.transaction():
                connection.execute(
                    "INSERT INTO knowledge.relationship_decision "
                    "(release_id, decision_id, canonical_relationship_id, "
                    "relationship_type_id, relationship_type_version, "
                    "source_canonical_identity_id, target_canonical_identity_id, "
                    "state, role_bindings, policy_id, policy_version, method, "
                    "method_version, decision_run_id, confidence, rationale, "
                    "valid_from, valid_to, valid_from_temporal, valid_to_temporal, "
                    "decided_at, supersedes_decision_id, llm_trace, "
                    "human_review_resolution) "
                    "SELECT release_id, 'temporal-crosswire-decision', "
                    "'temporal-crosswire-relationship', relationship_type_id, "
                    "relationship_type_version, source_canonical_identity_id, "
                    "target_canonical_identity_id, state, role_bindings, policy_id, "
                    "policy_version, method, method_version, decision_run_id, "
                    "confidence, rationale, valid_from - interval '1 day', valid_to, "
                    "knowledge.temporal_instant_value(valid_from - interval '1 day'), "
                    "valid_to_temporal, decided_at, NULL, llm_trace, "
                    "human_review_resolution FROM knowledge.relationship_decision "
                    "WHERE canonical_relationship_id = "
                    "'canonical-relationship-current'"
                )
                connection.execute(
                    "INSERT INTO knowledge.relationship_decision_assertion "
                    "(release_id, decision_id, assertion_id, assertion_role) "
                    "VALUES (%s, 'temporal-crosswire-decision', "
                    "'relation-role-current', 'selected')",
                    (RELEASE_ID,),
                )
                connection.execute(
                    "SET CONSTRAINTS "
                    "knowledge.trg_validate_relationship_temporal_binding, "
                    "knowledge.trg_validate_relationship_assertion_temporal_binding "
                    "IMMEDIATE"
                )


def test_non_utc_temporal_inputs_restart_as_one_canonical_instant(
    target: _Target,
) -> None:
    result = _decision_result(
        temporal_history=True,
        non_utc_temporal=True,
    )
    _insert_prerequisites(target)
    with _connect(target, autocommit=True) as connection:
        connection.execute(
            sql.SQL("ALTER DATABASE {} SET timezone TO 'Asia/Shanghai'").format(
                sql.Identifier(target.expected_database)
            )
        )
    with _connect(target) as connection:
        assert connection.execute("SHOW timezone").fetchone() == ("Asia/Shanghai",)

    persisted = _store(target).persist(result)
    loaded = _store(target).load(RELEASE_ID, RUN_ID)

    assert persisted == loaded == result
    for assertion in loaded.relationship_assertions:
        assert assertion.observed_at.utcoffset() == timedelta(0)
        if assertion.source_event_time is not None:
            assert assertion.source_event_time.utcoffset() == timedelta(0)
        if assertion.valid_from is not None:
            assert assertion.valid_from.value.utcoffset() == timedelta(0)
        if assertion.valid_to is not None:
            assert assertion.valid_to.value.utcoffset() == timedelta(0)
    assert all(
        decision.valid_from is None
        or decision.valid_from.value.utcoffset() == timedelta(0)
        for decision in loaded.relationship_decisions
    )
    assert loaded.content_sha256 == result.content_sha256


def test_corrupt_temporal_restart_is_wrapped_by_store_abstraction(
    target: _Target,
) -> None:
    result = _decision_result(temporal_history=True)
    _insert_prerequisites(target)
    assert _store(target).persist(result) == result

    with _connect(target, autocommit=True) as connection:
        connection.execute(
            "ALTER TABLE knowledge.relationship_assertion DISABLE TRIGGER USER"
        )
        try:
            connection.execute(
                "UPDATE knowledge.relationship_assertion "
                "SET valid_from = valid_from - interval '1 day', "
                "valid_from_temporal = knowledge.temporal_instant_value("
                "valid_from - interval '1 day') "
                "WHERE assertion_id = 'relation-role-current'"
            )
        finally:
            connection.execute(
                "ALTER TABLE knowledge.relationship_assertion ENABLE TRIGGER USER"
            )

    module = _postgres_module()
    with pytest.raises(
        module.CanonicalDecisionPersistenceError,
        match="incomplete|corrupt",
    ) as caught:
        _store(target).load(RELEASE_ID, RUN_ID)
    assert isinstance(caught.value.__cause__, ValueError)
    assert not isinstance(
        caught.value.__cause__,
        _engine_module().DecisionBatchIntegrityError,
    )


@pytest.mark.parametrize("omitted_membership", ("prof-source-b", "company-source"))
def test_missing_authoritative_identity_membership_fails_before_decision_writes(
    target: _Target,
    omitted_membership: str,
) -> None:
    result = _decision_result()
    _insert_prerequisites(target, omitted_membership=omitted_membership)
    counts_before = _persisted_counts(target)

    with pytest.raises(
        _postgres_module().CanonicalDecisionPersistenceError,
        match="identity|ownership|context|membership",
    ):
        _store(target).persist(result)

    assert _persisted_counts(target) == counts_before


def test_c2_0006_action_shape_rejects_multi_output_create_identity_decision(
    target: _Target,
) -> None:
    _insert_prerequisites(target)
    counts_before = _persisted_counts(target)
    with pytest.raises(
        psycopg.errors.CheckViolation,
        match="action shape",
    ):
        with _connect(target) as connection:
            connection.execute(
                "INSERT INTO knowledge.canonical_identity "
                "(release_id, canonical_identity_id, entity_type, state, display_name, "
                "identity_decision_id) VALUES (%s, 'professor-c2', 'professor', "
                "'active', 'Ambiguous second output', "
                "'identity-decision:professor-c1')",
                (RELEASE_ID,),
            )
            connection.execute(
                "INSERT INTO knowledge.identity_decision_output "
                "(release_id, decision_id, canonical_identity_id) VALUES "
                "(%s, 'identity-decision:professor-c1', 'professor-c2')",
                (RELEASE_ID,),
            )
            connection.commit()

    assert _persisted_counts(target) == counts_before
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT count(*) FROM knowledge.canonical_identity "
            "WHERE canonical_identity_id = 'professor-c2'"
        ).fetchone() == (0,)


def test_historical_load_uses_immutable_decision_time_identity_context(
    target: _Target,
) -> None:
    result = _decision_result()
    _insert_prerequisites(target)
    assert _store(target).persist(result) == result

    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO landing.source_record "
            "(record_id, artifact_id, source_batch_id, record_locator, parse_run_id, "
            "record_ordinal, parse_status, payload, parsed_at) VALUES "
            "('record:prof-source-a:later', 'decision-artifact-1', "
            "'later-source-batch', 'row:later', 'decision-parse-run', 99, "
            "'parsed', %s, %s)",
            (Jsonb({"id": "later"}), NOW + timedelta(days=1)),
        )
        connection.execute(
            "INSERT INTO knowledge.source_identity_record "
            "(source_identity_id, record_id) "
            "VALUES ('prof-source-a', 'record:prof-source-a:later')"
        )
        connection.execute(
            "UPDATE knowledge.source_identity SET last_observed_at = %s, "
            "state = 'superseded' WHERE source_identity_id = 'prof-source-a'",
            (NOW + timedelta(days=1),),
        )
        connection.commit()

    assert _store(target).load(RELEASE_ID, RUN_ID) == result


def test_factory_interface_and_explicit_target_safety_are_enforced(
    target: _Target,
    tmp_path: Path,
) -> None:
    module = _postgres_module()
    factory = module.create_postgres_canonical_decision_store
    parameters = inspect.signature(factory).parameters
    assert tuple(parameters) == (
        "database_url",
        "expected_database",
        "target_kind",
        "backup_gate_root",
    )
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and parameter.default is inspect.Parameter.empty
        for parameter in parameters.values()
    )
    with pytest.raises(TypeError):
        factory()
    assert isinstance(_store(target), module.CanonicalDecisionStore)

    gate_module = import_module("src.data_agents.canonical_v2.rebuild_write_gate")
    with pytest.raises(gate_module.RebuildWriteGateError):
        factory(
            database_url=(
                "postgresql+psycopg://miroflow@unresolvable.invalid/"
                "canonical_decision_must_not_connect"
            ),
            expected_database="canonical_decision_must_not_connect",
            target_kind="disposable",
            backup_gate_root=tmp_path / "unaccepted-gate",
        )

    disposable_marker = (
        f"miroflow:destructive-target:v1:disposable:{target.expected_database}"
    )
    try:
        _set_database_marker(target, "miroflow:destructive-target:v1:disposable:wrong")
        with pytest.raises(
            module.CanonicalDecisionPersistenceError,
            match="marker|identity|target|database",
        ):
            _store(target)

        _set_database_marker(
            target,
            "miroflow:destructive-target:v1:isolated-candidate:"
            f"{target.expected_database}",
        )
        with pytest.raises(
            module.CanonicalDecisionPersistenceError,
            match="disposable|target",
        ):
            factory(
                database_url=target.database_url,
                expected_database=target.expected_database,
                target_kind="isolated-candidate",
                backup_gate_root=target.backup_gate_root,
            )
    finally:
        _set_database_marker(target, disposable_marker)


def test_decision_backup_gate_is_rechecked_immediately_before_first_write(
    target: _Target,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _decision_result()
    module = _postgres_module()
    calls = 0

    def expiring_gate(root: Path):
        nonlocal calls
        calls += 1
        receipt = require_accepted_backup_gate(root)
        if calls == 4:
            raise RebuildWriteGateError("synthetic gate expiry before first write")
        return receipt

    monkeypatch.setattr(module, "require_accepted_backup_gate", expiring_gate)
    store = _store(target)
    _insert_prerequisites(target)

    with pytest.raises(RebuildWriteGateError, match="before first write"):
        store.persist(result)
    assert calls == 4
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.canonical_decision), "
            "(SELECT count(*) FROM knowledge.relationship_decision), "
            "(SELECT count(*) FROM knowledge.canonical_decision_identity_context), "
            "(SELECT count(*) FROM knowledge.relationship_decision_identity_context)"
        ).fetchone() == (0, 0, 0, 0)


def test_changed_content_conflicts_and_rolls_back_every_new_row(
    target: _Target,
) -> None:
    original = _decision_result()
    changed = _decision_result(changed=True)
    _insert_prerequisites(target)
    store = _store(target)
    assert store.persist(original) == original
    counts = _persisted_counts(target)

    with pytest.raises(
        _postgres_module().CanonicalDecisionPersistenceError,
        match="content|conflict|replay|decision_run_id|run",
    ):
        _store(target).persist(changed)

    assert _store(target).load(RELEASE_ID, RUN_ID) == original
    assert _persisted_counts(target) == counts
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT count(*) FROM knowledge.source_assertion "
            "WHERE assertion_id = 'field-b-changed'"
        ).fetchone() == (0,)


def test_late_human_review_failure_rolls_back_the_complete_new_release(
    target: _Target,
) -> None:
    initial = _decision_result(field_unresolved=True)
    reviewed = _reviewed_field_result(initial)
    _insert_prerequisites(target)
    _insert_reviewed_release_prerequisites(target)
    assert _store(target).persist(initial) == initial

    with _connect(target, autocommit=True) as connection:
        connection.execute(
            "CREATE FUNCTION knowledge.fail_s5f_review_outcome_for_test() "
            "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "IF NEW.release_id = 'decision-postgres-release-r2' THEN "
            "RAISE EXCEPTION 'synthetic late review persistence failure'; "
            "END IF; RETURN NEW; END; $$"
        )
        connection.execute(
            "CREATE TRIGGER trg_fail_s5f_review_outcome_for_test "
            "BEFORE INSERT ON knowledge.canonical_decision_constraint_outcome "
            "FOR EACH ROW EXECUTE FUNCTION "
            "knowledge.fail_s5f_review_outcome_for_test()"
        )
    try:
        with pytest.raises(
            _postgres_module().CanonicalDecisionPersistenceError,
            match="transaction|persist|synthetic|failed",
        ):
            _store(target).persist(reviewed)
    finally:
        with _connect(target, autocommit=True) as connection:
            connection.execute(
                "DROP TRIGGER trg_fail_s5f_review_outcome_for_test ON "
                "knowledge.canonical_decision_constraint_outcome"
            )
            connection.execute(
                "DROP FUNCTION knowledge.fail_s5f_review_outcome_for_test()"
            )

    assert _store(target).load(RELEASE_ID, RUN_ID) == initial
    with _connect(target) as connection:
        assert connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.canonical_decision "
            " WHERE release_id = %s), "
            "(SELECT count(*) FROM knowledge.canonical_decision_assertion "
            " WHERE release_id = %s), "
            "(SELECT count(*) FROM knowledge.canonical_decision_identity_context "
            " WHERE release_id = %s), "
            "(SELECT count(*) FROM knowledge.canonical_decision_constraint_outcome "
            " WHERE release_id = %s)",
            (REVIEWED_RELEASE_ID,) * 4,
        ).fetchone() == (0, 0, 0, 0)


def test_empty_c2_0005_round_trips_through_c2_0004_on_owned_sibling(
    target: _Target,
) -> None:
    revision = ScriptDirectory.from_config(target.config).get_revision("C2_0005")
    assert revision is not None
    assert revision.down_revision == "C2_0004"

    try:
        command.downgrade(target.config, "C2_0004")
        with _connect(target) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.canonical_v2_alembic_version"
            ).fetchone() == ("C2_0004",)
            assert connection.execute(
                "SELECT "
                "to_regclass('knowledge.canonical_decision_constraint_outcome'), "
                "to_regclass('knowledge.relationship_decision_constraint_outcome'), "
                "to_regclass('knowledge.canonical_decision_identity_context'), "
                "to_regclass('knowledge.relationship_decision_identity_context')"
            ).fetchone() == (None, None, None, None)

        command.upgrade(target.config, "C2_0005")
        with _connect(target) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.canonical_v2_alembic_version"
            ).fetchone() == ("C2_0005",)
            assert connection.execute(
                "SELECT "
                "to_regclass('knowledge.canonical_decision_constraint_outcome'), "
                "to_regclass('knowledge.relationship_decision_constraint_outcome'), "
                "to_regclass('knowledge.canonical_decision_identity_context'), "
                "to_regclass('knowledge.relationship_decision_identity_context')"
            ).fetchone() == (
                "knowledge.canonical_decision_constraint_outcome",
                "knowledge.relationship_decision_constraint_outcome",
                "knowledge.canonical_decision_identity_context",
                "knowledge.relationship_decision_identity_context",
            )
    finally:
        command.upgrade(target.config, "head")


@pytest.mark.parametrize("decision_family", ("field", "relationship"))
def test_c2_0005_refuses_existing_decisions_without_inventing_context_snapshots(
    target: _Target,
    decision_family: str,
) -> None:
    command.downgrade(target.config, "C2_0004")
    _insert_prerequisites(target)
    with _connect(target) as connection:
        if decision_family == "field":
            connection.execute(
                "INSERT INTO knowledge.canonical_decision "
                "(release_id, decision_id, canonical_identity_id, field_path, state, "
                "policy_id, policy_version, method, method_version, decision_run_id, "
                "confidence, rationale, decided_at) VALUES "
                "(%s, 'legacy-field-decision', 'professor-c1', "
                "'employment.current_title', 'unresolved', "
                "'field_selection-policy', 'v1', 'deterministic', "
                "'canonical-decision-v0', %s, 0.0, 'legacy field decision', %s)",
                (RELEASE_ID, RUN_ID, NOW),
            )
        else:
            connection.execute(
                "INSERT INTO knowledge.relationship_decision "
                "(release_id, decision_id, canonical_relationship_id, "
                "relationship_type_id, relationship_type_version, "
                "source_canonical_identity_id, target_canonical_identity_id, state, "
                "role_bindings, policy_id, policy_version, method, method_version, "
                "decision_run_id, confidence, rationale, decided_at) VALUES "
                "(%s, 'legacy-relationship-decision', 'legacy-relationship', "
                "'professor_company_role', 'v1', 'professor-c1', 'company-c1', "
                "'unresolved', '{}'::jsonb, 'relationship-policy', 'v2', "
                "'deterministic', 'canonical-decision-v0', %s, 0.0, "
                "'legacy relationship decision', %s)",
                (RELEASE_ID, RUN_ID, NOW),
            )
        connection.commit()

    with pytest.raises(sa_exc.DBAPIError) as caught:
        command.upgrade(target.config, "head")
    assert getattr(caught.value.orig, "sqlstate", None) == "55000"

    with _connect(target) as connection:
        assert connection.execute(
            "SELECT version_num FROM public.canonical_v2_alembic_version"
        ).fetchone() == ("C2_0004",)
        assert connection.execute(
            "SELECT "
            "(SELECT count(*) FROM knowledge.canonical_decision), "
            "(SELECT count(*) FROM knowledge.relationship_decision), "
            "to_regclass('knowledge.canonical_decision_identity_context'), "
            "to_regclass('knowledge.relationship_decision_identity_context')"
        ).fetchone() == (
            1 if decision_family == "field" else 0,
            1 if decision_family == "relationship" else 0,
            None,
            None,
        )


def test_downgrade_serializes_with_an_uncommitted_outcome_insert(
    target: _Target,
) -> None:
    command.downgrade(target.config, "C2_0005")
    _insert_prerequisites(target)
    assertion_id = "downgrade-race-assertion"
    decision_id = "downgrade-race-decision"
    with _connect(target) as connection:
        connection.execute(
            "INSERT INTO knowledge.source_assertion "
            "(assertion_id, source_record_id, source_identity_id, "
            "subject_entity_type, field_path, value, "
            "assertion_fingerprint_sha256, observed_at, assertion_run_id) "
            "VALUES (%s, 'record:prof-source-a', 'prof-source-a', 'professor', "
            "'employment.current_title', %s, %s, %s, 'downgrade-race-run')",
            (
                assertion_id,
                Jsonb("Professor"),
                _fingerprint(assertion_id),
                NOW,
            ),
        )
        connection.execute(
            "INSERT INTO knowledge.canonical_decision "
            "(release_id, decision_id, canonical_identity_id, field_path, state, "
            "policy_id, policy_version, method, method_version, decision_run_id, "
            "confidence, rationale, decided_at) VALUES "
            "(%s, %s, 'professor-c1', 'employment.current_title', 'selected', "
            "'field_selection-policy', 'v1', 'deterministic', 'field-v1', %s, "
            "1.0, 'downgrade race fixture', %s)",
            (RELEASE_ID, decision_id, RUN_ID, NOW),
        )
        connection.commit()

    application_name = "canonical_v2_c2_0005_downgrade_race"
    migration_url = (
        make_url(target.database_url)
        .update_query_dict({"application_name": application_name})
        .render_as_string(hide_password=False)
    )
    migration_target = _Target(
        database_url=migration_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
        config=Config(),
    )
    migration_config = _migration_config(migration_target)
    writer = _connect(target)
    executor = ThreadPoolExecutor(max_workers=1)
    downgrade = None
    writer_released = False
    try:
        writer.execute(
            "INSERT INTO knowledge.canonical_decision_constraint_outcome "
            "(release_id, decision_id, assertion_id, admitted, reason_codes) "
            "VALUES (%s, %s, %s, TRUE, '[]'::jsonb)",
            (RELEASE_ID, decision_id, assertion_id),
        )
        downgrade = executor.submit(command.downgrade, migration_config, "C2_0004")

        poll_interval = Event()
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
                if downgrade.done():
                    break
                poll_interval.wait(0.01)
        assert lock_wait is not None
        assert lock_wait[0] == "Lock"
        assert not downgrade.done()

        writer.commit()
        writer_released = True
        with pytest.raises(sa_exc.DBAPIError) as caught:
            downgrade.result(timeout=10.0)
        assert getattr(caught.value.orig, "sqlstate", None) == "55000"

        with _connect(target) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.canonical_v2_alembic_version"
            ).fetchone() == ("C2_0005",)
            assert connection.execute(
                "SELECT admitted, reason_codes FROM "
                "knowledge.canonical_decision_constraint_outcome "
                "WHERE release_id = %s AND decision_id = %s AND assertion_id = %s",
                (RELEASE_ID, decision_id, assertion_id),
            ).fetchone() == (True, [])
    finally:
        if not writer_released:
            writer.rollback()
        writer.close()
        if downgrade is not None and not downgrade.done():
            downgrade.result(timeout=10.0)
        executor.shutdown(wait=True, cancel_futures=True)


def test_store_and_c2_0007_downgrade_share_release_first_lock_order(
    target: _Target,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = _decision_result(field_unresolved=True)
    reviewed = _reviewed_field_result(initial)
    _insert_prerequisites(target)
    _insert_reviewed_release_prerequisites(target)
    assert _store(target).persist(initial) == initial

    store_application_name = "canonical_v2_decision_store_lock_race"
    migration_application_name = "canonical_v2_decision_downgrade_lock_race"
    module = _postgres_module()
    store_type = module._PostgresCanonicalDecisionStore
    original_batch_decision_count = store_type._batch_decision_count
    lookup_reached = Event()
    resume_writer = Event()

    def pause_before_decision_lookup(
        connection,
        *,
        release_id: str,
        decision_run_id: str,
    ) -> int:
        lookup_reached.set()
        assert resume_writer.wait(timeout=10.0)
        return original_batch_decision_count(
            connection,
            release_id=release_id,
            decision_run_id=decision_run_id,
        )

    monkeypatch.setattr(
        store_type,
        "_batch_decision_count",
        staticmethod(pause_before_decision_lookup),
    )
    store_url = (
        make_url(target.database_url)
        .update_query_dict({"application_name": store_application_name})
        .render_as_string(hide_password=False)
    )
    store = module.create_postgres_canonical_decision_store(
        database_url=store_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
    )
    migration_url = (
        make_url(target.database_url)
        .update_query_dict({"application_name": migration_application_name})
        .render_as_string(hide_password=False)
    )
    migration_target = _Target(
        database_url=migration_url,
        expected_database=target.expected_database,
        target_kind=target.target_kind,
        backup_gate_root=target.backup_gate_root,
        config=Config(),
    )
    migration_config = _migration_config(migration_target)
    controller = _connect(target, autocommit=True)
    executor = ThreadPoolExecutor(max_workers=2)
    persist = None
    downgrade = None
    try:
        persist = executor.submit(store.persist, reviewed)
        assert lookup_reached.wait(timeout=10.0)
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
                "AND namespace.nspname = 'knowledge' AND lock.granted",
                (store_application_name,),
            ).fetchall()
        }
        assert ("release", "RowShareLock") in granted_locks
        assert not {
            relation_name
            for relation_name, _ in granted_locks
            if relation_name in {"canonical_decision", "relationship_decision"}
        }

        downgrade = executor.submit(command.downgrade, migration_config, "C2_0006")
        poll = Event()
        deadline = time.monotonic() + 10.0
        lock_wait = None
        while time.monotonic() < deadline:
            lock_wait = controller.execute(
                "SELECT wait_event_type, wait_event FROM pg_stat_activity "
                "WHERE datname = current_database() AND application_name = %s",
                (migration_application_name,),
            ).fetchone()
            if lock_wait is not None and lock_wait[0] == "Lock":
                break
            if downgrade.done():
                break
            poll.wait(0.01)
        assert lock_wait is not None
        assert lock_wait[0] == "Lock"
        assert not downgrade.done()

        resume_writer.set()
        assert persist.result(timeout=10.0) == reviewed
        with pytest.raises(sa_exc.DBAPIError) as error:
            downgrade.result(timeout=10.0)
        assert getattr(error.value.orig, "sqlstate", None) == "55000"
        with _connect(target) as connection:
            assert connection.execute(
                "SELECT version_num FROM public.canonical_v2_alembic_version"
            ).fetchone() == (EXPECTED_REVISION,)
        assert store.load(REVIEWED_RELEASE_ID, REVIEWED_RUN_ID) == reviewed
    finally:
        resume_writer.set()
        controller.close()
        if persist is not None and not persist.done():
            persist.result(timeout=10.0)
        if downgrade is not None and not downgrade.done():
            downgrade.result(timeout=10.0)
        executor.shutdown(wait=True, cancel_futures=True)


def test_missing_parents_are_not_created_and_no_current_projection_is_durable(
    target: _Target,
) -> None:
    result = _decision_result()
    module = _postgres_module()
    store = _store(target)

    with pytest.raises(module.CanonicalDecisionPersistenceError):
        store.persist(result)
    with pytest.raises(module.CanonicalDecisionNotFoundError):
        store.load(RELEASE_ID, RUN_ID)

    with _connect(target) as connection:
        assert (
            connection.execute(
                "SELECT "
                "(SELECT count(*) FROM landing.evidence_artifact), "
                "(SELECT count(*) FROM landing.parser_run), "
                "(SELECT count(*) FROM landing.source_record), "
                "(SELECT count(*) FROM landing.source_error), "
                "(SELECT count(*) FROM landing.ingest_run), "
                "(SELECT count(*) FROM knowledge.release), "
                "(SELECT count(*) FROM knowledge.policy), "
                "(SELECT count(*) FROM knowledge.source_identity), "
                "(SELECT count(*) FROM knowledge.source_identity_record), "
                "(SELECT count(*) FROM knowledge.identity_decision), "
                "(SELECT count(*) FROM knowledge.canonical_identity), "
                "(SELECT count(*) FROM knowledge.relationship_type), "
                "(SELECT count(*) FROM knowledge.source_assertion), "
                "(SELECT count(*) FROM knowledge.relationship_assertion), "
                "(SELECT count(*) FROM knowledge.canonical_decision), "
                "(SELECT count(*) FROM knowledge.canonical_decision_assertion), "
                "(SELECT count(*) FROM knowledge.canonical_decision_constraint_outcome), "
                "(SELECT count(*) FROM knowledge.relationship_decision), "
                "(SELECT count(*) FROM knowledge.relationship_decision_assertion), "
                "(SELECT count(*) FROM "
                " knowledge.relationship_decision_constraint_outcome)"
            ).fetchone()
            == (0,) * 20
        )
        current_tables = connection.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema = ANY(%s) AND table_name ILIKE %s",
            (
                [
                    "landing",
                    "knowledge",
                    "publish",
                    "professor",
                    "company",
                    "paper",
                    "patent",
                    "ops",
                ],
                "%current%",
            ),
        ).fetchall()
        assert current_tables == [("knowledge", "current_source_identity_assignment")]
