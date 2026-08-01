"""Executable S12A RED owner for the complete isolated knowledge build.

Every test imports the one target module before constructing a fixture or touching
an external boundary.  While the module is absent, normal RED is therefore six
strict xfails and forced RED is six exact missing-target failures.

The local platform below exposes only boundary primitives: accepted-copy staging,
landing/store readback, candidate registry rows, and physical index materialization
and audit.  It cannot return a prebuilt candidate, projection graph, verification,
handoff, receipt, or envelope.  Those remain owned by the deep builder.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from importlib import import_module
import inspect
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
from typing import Any

import pytest


TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_build_isolated"
TARGET_PATH = (
    Path(__file__).resolve().parents[2]
    / "src/data_agents/canonical_v2/knowledge_build_isolated.py"
)
NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
RUN_ID = "s12a-test-build-run"
RELEASE_ID = "candidate-s12a-test"
SOURCE_BATCH_ID = "s12a-released-objects-full-v1"
RECOLLECTION_BATCH_ID = "s12a-approved-recollection-v1"

SOURCE_INVENTORY_SHA256 = (
    "83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09"
)
BACKUP_MANIFEST_SHA256 = (
    "a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8"
)
RESTORE_VERIFICATION_SHA256 = (
    "98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231"
)
ACCEPTANCE_RECORD_SHA256 = (
    "3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b"
)
RELEASED_OBJECTS_SOURCE_ID = (
    "inventory:ffe87de3fe5cefe929194235d43fe7bcf09be406976a81cea23efb464d4d34a0"
)
RELEASED_OBJECTS_SHA256 = (
    "7637d808559685f1bcf0316cd22cfeac4e50bd0850c53652ec95b3dbb5e43bce"
)
RELEASED_OBJECTS_RESTORE_MEMBER_PATH = "workspace/logs/data_agents/released_objects.db"
RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_PATH = (
    "manifests/inventory/"
    "027-ffe87de3fe5cefe929194235d43fe7bcf09be406976a81cea23efb464d4d34a0.jsonl"
)
RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_SHA256 = (
    "6820786a2e055def2828c82de60f3b90cad9ac5dcc8f1477943a9f46a02777ae"
)
RELEASED_OBJECTS_SOURCE_MEMBER_MANIFEST_SHA256 = (
    "4c91d1d7dce88e5c9d9924b2c21d6f3111292eb3e5c30a60e688fd40ccf8b594"
)
ORIGINAL_MILVUS_SHA256 = (
    "43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc"
)
RECORDED_DECISION_BUNDLE_SHA256 = (
    "6d7fa297838812bf6e3692bb32ff1133239be692d675ad8be749aeca9c7487b4"
)
RECORDED_EMBEDDING_BUNDLE_SHA256 = (
    "a5b57005eb48a0692ae946d83c02ce54df0280a8274527f94c29d79d81266200"
)
QWEN_EMBEDDING_BUNDLE_SHA256 = (
    "05473fabc8055e9ce3ebca9d846761cab7cb8c89eb51c96607172c402d1f46db"
)
PROTECTED_ORIGINAL_MILVUS_PATH = Path(
    "/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db"
)


class _MissingIsolatedKnowledgeBuildModule(AssertionError):
    """Exact S12A RED sentinel; nested missing dependencies fail normally."""


class _BoundaryFailure(RuntimeError):
    """Controlled failure at a real physical/store boundary primitive."""


class _BoundaryConflict(RuntimeError):
    """Controlled append-only store conflict."""


@dataclass(frozen=True)
class _ConflictingStoredValue:
    store_name: str
    content_identity: str
    marker: str = "pre-existing-different-content"


def _module() -> Any:
    protected_guard = _ProtectedOpenGuard(PROTECTED_ORIGINAL_MILVUS_PATH)
    protected_guard.install()
    try:
        try:
            module = import_module(TARGET_MODULE)
        except ModuleNotFoundError as exc:
            if exc.name != TARGET_MODULE:
                raise AssertionError(
                    f"{TARGET_MODULE} has an unexpected missing dependency: {exc.name}"
                ) from exc
            raise _MissingIsolatedKnowledgeBuildModule(
                f"exact target module is absent: {TARGET_MODULE}"
            ) from exc
        assert protected_guard.attempts == []
        return module
    finally:
        protected_guard.close()


_S12A_MISSING_TARGET = pytest.mark.xfail(
    not TARGET_PATH.is_file(),
    strict=True,
    raises=_MissingIsolatedKnowledgeBuildModule,
    reason="S12A RED: complete isolated KnowledgeBuild target is absent",
)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


RELEASED_OBJECTS_EXPECTED_ROW_COUNTS = {
    "company": 1037,
    "paper": 574,
    "patent": 1931,
    "professor": 1439,
    "professor_paper_link": 580,
}
RELEASED_OBJECTS_MAPPER_POLICY = {
    "schema_version": "canonical-v2-released-objects-mapper-policy-v2",
    "policy_version": "canonical-v2-released-objects-mapper-v2",
    "allowed_fields_by_object_type": {
        "company": [
            "core_facts.aliases",
            "core_facts.industry",
            "core_facts.key_personnel",
            "core_facts.name",
            "core_facts.normalized_name",
            "core_facts.website",
            "summary_fields.profile_summary",
            "summary_fields.technology_route_summary",
        ],
        "paper": [
            "core_facts.arxiv_id",
            "core_facts.authors",
            "core_facts.doi",
            "core_facts.pdf_path",
            "core_facts.title",
            "core_facts.venue",
            "core_facts.year",
            "summary_fields.summary_text",
        ],
        "patent": [
            "core_facts.applicants",
            "core_facts.company_ids",
            "core_facts.filing_date",
            "core_facts.inventors",
            "core_facts.patent_number",
            "core_facts.publication_date",
            "core_facts.title",
            "summary_fields.summary_text",
        ],
        "professor": [
            "core_facts.canonical_name_zh",
            "core_facts.company_roles",
            "core_facts.department",
            "core_facts.email",
            "core_facts.homepage",
            "core_facts.institution",
            "core_facts.name",
            "core_facts.paper_summary",
            "core_facts.patent_ids",
            "core_facts.patent_summary",
            "core_facts.research_directions",
            "core_facts.title",
            "summary_fields.profile_summary",
        ],
        "professor_paper_link": [
            "core_facts.paper_id",
            "core_facts.professor_id",
        ],
    },
    "expected_row_counts": RELEASED_OBJECTS_EXPECTED_ROW_COUNTS,
    "product_capability": "answer_scoped_only",
    "public_domains": ["company", "paper", "patent", "professor"],
}
RELEASED_OBJECTS_MAPPER_POLICY_SHA256 = _canonical_hash(RELEASED_OBJECTS_MAPPER_POLICY)


def _model_content_hash(value: Any) -> str:
    return _canonical_hash(value.model_dump(mode="json", exclude={"content_sha256"}))


def test_boundary_contract_uses_exact_accepted_owner_shapes_and_real_defaults() -> None:
    module = _module()

    assert not hasattr(module._Boundary, "persist_typed_result")
    assert {
        "persist_candidate_registry_and_identity_policy",
        "persist_identity_resolution",
        "persist_decision_batch",
        "persist_domain_projection",
        "persist_relationship_projection",
        "persist_gap",
    } <= set(module._Boundary.__dict__)

    signature = inspect.signature(module.create_isolated_knowledge_build)
    assert signature.parameters["boundary"].default is None
    assert (
        signature.parameters["accepted_original_milvus_sha256"].default
        is inspect._empty
    )
    assert (
        signature.parameters["accepted_original_milvus_record_sha256"].default
        is inspect._empty
    )
    assert module.FileCompleteCandidateEnvelopeSink


def test_real_boundary_rejects_forbidden_database_endpoint_before_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    targets = _target_config(
        module,
        root=tmp_path,
        source_manifest_sha256="f" * 64,
        release_id=RELEASE_ID,
    )
    targets = targets.model_copy(
        update={
            "database": module.DestructiveDatabaseTarget(
                url=(
                    "postgresql+psycopg://miroflow@127.0.0.1:15432/"
                    f"miroflow_{RELEASE_ID.replace('-', '_')}"
                ),
                expected_database=f"miroflow_{RELEASE_ID.replace('-', '_')}",
                target_kind="disposable",
            )
        }
    )
    connect_attempts: list[object] = []

    def forbidden_connect(*args: object, **kwargs: object) -> None:
        connect_attempts.append((args, kwargs))
        raise AssertionError("forbidden endpoint must be rejected before connect")

    monkeypatch.setattr(module.psycopg, "connect", forbidden_connect)

    with pytest.raises(
        module.IsolatedKnowledgeBuildSafetyError,
        match="database target",
    ):
        module.create_isolated_knowledge_build(
            target_config=targets,
            accepted_backup_gate_root=tmp_path / "accepted-gate",
            source_manifest_path=tmp_path / "source-manifest.json",
            accepted_original_milvus_sha256=ORIGINAL_MILVUS_SHA256,
            accepted_original_milvus_record_sha256=_canonical_hash(
                {
                    "record_kind": "accepted-original-milvus-identity",
                    "content_sha256": ORIGINAL_MILVUS_SHA256,
                }
            ),
            decision_adapter=_RecordingDecisionAdapter(),
            embedding_adapter=_RecordingEmbeddingAdapter(),
            envelope_sink=_AtomicEnvelopeSink(module, tmp_path / "envelope.json"),
            clock=lambda: NOW,
        )

    assert connect_attempts == []


def test_complete_candidate_rejects_non_loopback_database_before_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    database_name = f"miroflow_{RELEASE_ID.replace('-', '_')}"
    target = module.DestructiveDatabaseTarget(
        url=(
            "postgresql+psycopg://miroflow:unused@candidate.invalid.example:5432/"
            f"{database_name}"
        ),
        expected_database=database_name,
        target_kind="disposable",
    )
    connect_attempts = 0

    def forbidden_connect(*args: object, **kwargs: object) -> None:
        nonlocal connect_attempts
        del args, kwargs
        connect_attempts += 1
        raise AssertionError("non-loopback target reached psycopg")

    monkeypatch.setattr(module.psycopg, "connect", forbidden_connect)

    with pytest.raises(
        module.IsolatedKnowledgeBuildSafetyError,
        match="local|loopback|endpoint",
    ):
        module._resolve_explicit_database_target(target)

    assert connect_attempts == 0


@pytest.mark.parametrize(
    ("url_template", "environment_key"),
    (
        (
            "postgresql+psycopg://miroflow@127.0.0.1:5432/{database}"
            "?options=-csession_replication_role%3Dreplica",
            None,
        ),
        ("postgresql+psycopg://miroflow@127.0.0.1/{database}", None),
        ("postgresql+psycopg://127.0.0.1:5432/{database}", None),
        (
            "postgresql+psycopg://miroflow@127.0.0.1:5432/{database}",
            "PGHOSTADDR",
        ),
        (
            "postgresql+psycopg://miroflow@127.0.0.1:5432/{database}",
            "PGOPTIONS",
        ),
        (
            "postgresql+psycopg://miroflow@127.0.0.1:5432/{database}",
            "PGGEQO",
        ),
    ),
)
def test_complete_candidate_rejects_implicit_or_caller_owned_libpq_configuration(
    monkeypatch: pytest.MonkeyPatch,
    url_template: str,
    environment_key: str | None,
) -> None:
    module = _module()
    database_name = f"miroflow_{RELEASE_ID.replace('-', '_')}"
    if environment_key is not None:
        monkeypatch.setenv(environment_key, "unsafe-test-value")
    target = module.DestructiveDatabaseTarget(
        url=url_template.format(database=database_name),
        expected_database=database_name,
        target_kind="disposable",
    )

    with pytest.raises(
        module.IsolatedKnowledgeBuildSafetyError,
        match="local database target",
    ):
        module._resolve_explicit_database_target(target)


def test_complete_candidate_normalizes_one_explicit_loopback_libpq_session() -> None:
    module = _module()
    database_name = f"miroflow_{RELEASE_ID.replace('-', '_')}"
    resolved = module._resolve_explicit_database_target(
        module.DestructiveDatabaseTarget(
            url=(f"postgresql+psycopg://miroflow@127.0.0.1:5432/{database_name}"),
            expected_database=database_name,
            target_kind="disposable",
        )
    )
    parsed = module.make_url(resolved.url)

    assert parsed.host == "127.0.0.1"
    assert parsed.port == 5432
    assert parsed.query["hostaddr"] == "127.0.0.1"
    assert parsed.query["options"] == (
        "-csession_replication_role=origin\t-ctimezone=UTC"
        "\t-cgeqo=on\t-cDateStyle=ISO,YMD"
        "\t-csearch_path=pg_catalog,public"
    )
    assert parsed.query["client_encoding"] == "UTF8"
    assert parsed.query["target_session_attrs"] == "read-write"


def test_factory_rejects_self_consistent_nonaccepted_original_milvus_identity(
    tmp_path: Path,
) -> None:
    module = _module()
    supplied_sha256 = "9" * 64
    boundary = _RecordingBoundary(module=module, rows_by_source={})

    with pytest.raises(
        module.IsolatedKnowledgeBuildSafetyError,
        match="Accepted original-Milvus",
    ):
        module.create_isolated_knowledge_build(
            target_config=_target_config(
                module,
                root=tmp_path,
                source_manifest_sha256="f" * 64,
                release_id=RELEASE_ID,
            ),
            accepted_backup_gate_root=tmp_path / "accepted-gate",
            source_manifest_path=tmp_path / "source-manifest.json",
            accepted_original_milvus_sha256=supplied_sha256,
            accepted_original_milvus_record_sha256=_canonical_hash(
                {
                    "record_kind": "accepted-original-milvus-identity",
                    "content_sha256": supplied_sha256,
                }
            ),
            decision_adapter=_RecordingDecisionAdapter(),
            embedding_adapter=_RecordingEmbeddingAdapter(),
            boundary=boundary,
            envelope_sink=_AtomicEnvelopeSink(module, tmp_path / "envelope.json"),
            clock=lambda: NOW,
        )


def test_released_objects_reader_orders_by_introspected_single_primary_key(
    tmp_path: Path,
) -> None:
    module = _module()
    source = tmp_path / "released-objects.db"
    payload = _released_object_payload("company", 1)
    with sqlite3.connect(source) as connection:
        connection.execute(
            "CREATE TABLE released_objects ("
            "row_key TEXT PRIMARY KEY, object_type TEXT NOT NULL, "
            "display_name TEXT NOT NULL, payload_json TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO released_objects VALUES (?, ?, ?, ?)",
            (
                payload["id"],
                payload["object_type"],
                payload["display_name"],
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )

    adapter = module._ReleasedObjectsSqliteAdapter()
    value = module.AdapterInput(
        content=source.read_bytes(),
        source_kind="released_objects_sqlite",
        source_locator=str(source),
        parser=module.ParserReference(
            parser_name="released_objects_sqlite",
            parser_version="canonical-v2-s12a-full-table-v1",
            schema_version="released-objects-v1",
            options={
                "table": "released_objects",
                "order": "primary_key",
                "limit": None,
            },
        ),
    )

    adapter.validate_source(value)
    source.unlink()
    replacement = _released_object_payload("company", 2)
    with sqlite3.connect(source) as connection:
        connection.execute(
            "CREATE TABLE released_objects ("
            "row_key TEXT PRIMARY KEY, object_type TEXT NOT NULL, "
            "display_name TEXT NOT NULL, payload_json TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO released_objects VALUES (?, ?, ?, ?)",
            (
                replacement["id"],
                replacement["object_type"],
                replacement["display_name"],
                json.dumps(replacement, ensure_ascii=False, sort_keys=True),
            ),
        )
    records = adapter.parse(value)

    assert len(records) == 1
    assert records[0].record_locator == f"released_objects:{payload['id']}"
    assert records[0].payload["id"] == payload["id"]
    assert tuple(tmp_path.glob(".*.parse.*.sqlite")) == ()


def test_released_objects_reader_rejects_generated_or_hidden_schema_columns(
    tmp_path: Path,
) -> None:
    module = _module()
    source = tmp_path / "released-objects-hidden.db"
    payload = _released_object_payload("company", 3)
    with sqlite3.connect(source) as connection:
        connection.execute(
            "CREATE TABLE released_objects ("
            "row_key TEXT PRIMARY KEY, object_type TEXT NOT NULL, "
            "display_name TEXT NOT NULL, payload_json TEXT NOT NULL, "
            "hidden_extra TEXT GENERATED ALWAYS AS (display_name) VIRTUAL)"
        )
        connection.execute(
            "INSERT INTO released_objects "
            "(row_key, object_type, display_name, payload_json) VALUES (?, ?, ?, ?)",
            (
                payload["id"],
                payload["object_type"],
                payload["display_name"],
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
    value = module.AdapterInput(
        content=source.read_bytes(),
        source_kind="released_objects_sqlite",
        source_locator=str(source),
        parser=module.ParserReference(
            parser_name="released_objects_sqlite",
            parser_version="canonical-v2-s12a-full-table-v1",
            schema_version="released-objects-v1",
            options={"table": "released_objects", "order": "primary_key"},
        ),
    )

    with pytest.raises(ValueError, match="schema|primary key"):
        module._ReleasedObjectsSqliteAdapter().parse(value)


@pytest.mark.parametrize(
    ("primary_key_declaration", "table_suffix"),
    (
        ("TEXT COLLATE NOCASE PRIMARY KEY", ""),
        ("TEXT PRIMARY KEY", " WITHOUT ROWID"),
        ("TEXT PRIMARY KEY", " STRICT"),
    ),
)
def test_released_objects_reader_rejects_primary_key_or_table_mode_drift(
    tmp_path: Path,
    primary_key_declaration: str,
    table_suffix: str,
) -> None:
    module = _module()
    source = tmp_path / "released-objects-mode-drift.db"
    payload = _released_object_payload("company", 6)
    with sqlite3.connect(source) as connection:
        connection.execute(
            "CREATE TABLE released_objects ("
            f"row_key {primary_key_declaration}, object_type TEXT NOT NULL, "
            "display_name TEXT NOT NULL, payload_json TEXT NOT NULL)"
            f"{table_suffix}"
        )
        connection.execute(
            "INSERT INTO released_objects VALUES (?, ?, ?, ?)",
            (
                payload["id"],
                payload["object_type"],
                payload["display_name"],
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
    value = module.AdapterInput(
        content=source.read_bytes(),
        source_kind="released_objects_sqlite",
        source_locator=str(source),
        parser=module.ParserReference(
            parser_name="released_objects_sqlite",
            parser_version="canonical-v2-s12a-full-table-v1",
            schema_version="released-objects-v1",
            options={"table": "released_objects", "order": "primary_key"},
        ),
    )

    with pytest.raises(ValueError, match="schema|primary.key|table mode"):
        module._ReleasedObjectsSqliteAdapter().parse(value)


def test_released_objects_reader_quarantines_top_level_and_nested_duplicate_json_keys(
    tmp_path: Path,
) -> None:
    module = _module()
    source = tmp_path / "released-objects-duplicate-json.db"
    first_payload = _released_object_payload("company", 4)
    second_payload = _released_object_payload("company", 5)
    first_json = json.dumps(first_payload, ensure_ascii=False, sort_keys=True)
    first_json = '{"id":"shadowed-id",' + first_json[1:]
    second_json = json.dumps(second_payload, ensure_ascii=False, sort_keys=True)
    second_json = second_json.replace(
        '"core_facts": {',
        '"core_facts": {"name":"shadowed-name", ',
        1,
    )
    third_payload = _released_object_payload("company", 7)
    third_json = json.dumps(third_payload, ensure_ascii=False, sort_keys=True)
    third_json = '{"deep":' + "[" * 10000 + "0" + "]" * 10000 + "," + third_json[1:]
    with sqlite3.connect(source) as connection:
        connection.execute(
            "CREATE TABLE released_objects ("
            "row_key TEXT PRIMARY KEY, object_type TEXT NOT NULL, "
            "display_name TEXT NOT NULL, payload_json TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO released_objects VALUES (?, ?, ?, ?)",
            (
                (
                    first_payload["id"],
                    first_payload["object_type"],
                    first_payload["display_name"],
                    first_json,
                ),
                (
                    second_payload["id"],
                    second_payload["object_type"],
                    second_payload["display_name"],
                    second_json,
                ),
                (
                    third_payload["id"],
                    third_payload["object_type"],
                    third_payload["display_name"],
                    third_json,
                ),
            ),
        )
    value = module.AdapterInput(
        content=source.read_bytes(),
        source_kind="released_objects_sqlite",
        source_locator=str(source),
        parser=module.ParserReference(
            parser_name="released_objects_sqlite",
            parser_version="canonical-v2-s12a-full-table-v1",
            schema_version="released-objects-v1",
            options={"table": "released_objects", "order": "primary_key"},
        ),
    )

    drafts = module._ReleasedObjectsSqliteAdapter().parse(value)
    record = module._source_record(
        row={
            "id": first_payload["id"],
            "object_type": first_payload["object_type"],
            "display_name": first_payload["display_name"],
            "payload_json": first_json,
        },
        source_batch_id=SOURCE_BATCH_ID,
        member=module.SourceBuildMember.model_validate(_evidence_member()),
        parsed_at=NOW,
    )

    assert len(drafts) == 3
    assert all(draft.parse_status is module.ParseStatus.quarantined for draft in drafts)
    assert all(
        draft.errors[0].error_code == "released_objects_duplicate_json_key"
        and draft.errors[0].field_path == "payload_json"
        for draft in drafts[:2]
    )
    assert drafts[2].errors[0].error_code == "released_objects_malformed_json"
    assert drafts[2].errors[0].field_path == "payload_json"
    assert record.parse_status is module.ParseStatus.quarantined
    assert record.errors[0].error_code == "released_objects_duplicate_json_key"


def test_released_objects_reader_parses_bound_content_during_source_path_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    source = tmp_path / "released-objects.db"
    original_payload = _released_object_payload("company", 40)
    replacement_payload = _released_object_payload("company", 41)

    def create_snapshot(
        path: Path,
        payload: dict[str, Any],
        connector: Any = sqlite3.connect,
    ) -> None:
        with connector(path) as connection:
            connection.execute(
                "CREATE TABLE released_objects ("
                "row_key TEXT PRIMARY KEY, object_type TEXT NOT NULL, "
                "display_name TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO released_objects VALUES (?, ?, ?, ?)",
                (
                    payload["id"],
                    payload["object_type"],
                    payload["display_name"],
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )

    create_snapshot(source, original_payload)
    value = module.AdapterInput(
        content=source.read_bytes(),
        source_kind="released_objects_sqlite",
        source_locator=str(source),
        parser=module.ParserReference(
            parser_name="released_objects_sqlite",
            parser_version="canonical-v2-s12a-full-table-v1",
            schema_version="released-objects-v1",
            options={
                "table": "released_objects",
                "order": "primary_key",
                "limit": None,
            },
        ),
    )
    original_connect = module.sqlite3.connect
    raced = False
    sqlite_targets: list[str] = []

    def raced_connect(database: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal raced
        if isinstance(database, str) and "mode=ro&immutable=1" in database:
            assert kwargs.get("uri") is True
            sqlite_targets.append(database)
            source.unlink()
            create_snapshot(source, replacement_payload)
            raced = True
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(module.sqlite3, "connect", raced_connect)

    records = module._ReleasedObjectsSqliteAdapter().parse(value)

    assert [record.payload["id"] for record in records] == [original_payload["id"]]
    assert raced is True
    assert len(sqlite_targets) == 1
    with original_connect(source) as connection:
        assert connection.execute(
            "SELECT row_key FROM released_objects"
        ).fetchone() == (replacement_payload["id"],)


def test_released_objects_reader_rejects_private_snapshot_path_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    source = tmp_path / "released-objects.db"
    accepted_payload = _released_object_payload("company", 42)
    replacement_payload = _released_object_payload("company", 43)

    def create_snapshot(
        path: Path,
        payload: dict[str, Any],
        connector: Any = sqlite3.connect,
    ) -> None:
        with connector(path) as connection:
            connection.execute(
                "CREATE TABLE released_objects ("
                "row_key TEXT PRIMARY KEY, object_type TEXT NOT NULL, "
                "display_name TEXT NOT NULL, payload_json TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO released_objects VALUES (?, ?, ?, ?)",
                (
                    payload["id"],
                    payload["object_type"],
                    payload["display_name"],
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )

    create_snapshot(source, accepted_payload)
    value = module.AdapterInput(
        content=source.read_bytes(),
        source_kind="released_objects_sqlite",
        source_locator=str(source),
        parser=module.ParserReference(
            parser_name="released_objects_sqlite",
            parser_version="canonical-v2-s12a-full-table-v1",
            schema_version="released-objects-v1",
            options={
                "table": "released_objects",
                "order": "primary_key",
                "limit": None,
            },
        ),
    )
    original_open = module.os.open
    original_connect = module.sqlite3.connect
    private_snapshot_paths: list[Path] = []
    sqlite_targets: list[object] = []

    def tracking_open(path: Any, *args: Any, **kwargs: Any) -> int:
        descriptor = original_open(path, *args, **kwargs)
        candidate = Path(path)
        if ".parse." in candidate.name:
            private_snapshot_paths.append(candidate)
        return descriptor

    def raced_connect(database: Any, *args: Any, **kwargs: Any) -> Any:
        sqlite_targets.append(database)
        if isinstance(database, str) and "mode=ro&immutable=1" in database:
            assert len(private_snapshot_paths) == 1
            private_snapshot_paths[0].unlink()
            create_snapshot(
                private_snapshot_paths[0],
                replacement_payload,
                connector=original_connect,
            )
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", tracking_open)
    monkeypatch.setattr(module.sqlite3, "connect", raced_connect)

    with pytest.raises(ValueError, match="opened.*bytes differ"):
        module._ReleasedObjectsSqliteAdapter().parse(value)

    assert len(sqlite_targets) == 1
    assert isinstance(sqlite_targets[0], str)
    assert "mode=ro&immutable=1" in sqlite_targets[0]
    assert len(private_snapshot_paths) == 1


def test_real_landing_binds_staged_copy_to_accepted_restore_parent(
    tmp_path: Path,
) -> None:
    module = _module()
    content = b"accepted restore bytes"
    content_sha256 = hashlib.sha256(content).hexdigest()
    staged_path = tmp_path / "staged.source"
    staged_path.write_bytes(content)
    member = module.SourceBuildMember.model_construct(
        member_id="member:accepted-restore",
        source_batch_id="batch:accepted-restore",
        source_kind="released_objects_sqlite",
        content_path=Path("/accepted/restore/released_objects.db"),
        byte_size=len(content),
        content_sha256=content_sha256,
        parser=module.ParserReference(
            parser_name="released_objects_sqlite",
            parser_version="canonical-v2-s12a-full-table-v1",
            schema_version="released-objects-v1",
            options={"table": "released_objects", "order": "primary_key"},
        ),
        observed_at=NOW,
        parent_source_id=RELEASED_OBJECTS_SOURCE_ID,
    )
    staged = module._StagedSource(
        path=staged_path,
        source_id=RELEASED_OBJECTS_SOURCE_ID,
        member_id=member.member_id,
        source_batch_id=member.source_batch_id,
        content_sha256=content_sha256,
        byte_size=len(content),
    )
    parent = module.EvidenceArtifact(
        artifact_id="artifact:accepted-restore-parent",
        source_kind="verified_restore_copy",
        source_locator=str(member.content_path),
        content_sha256=content_sha256,
        byte_size=len(content),
        acquired_at=NOW,
        run_id="landing:parent",
    )

    class Landing:
        register_request: Any | None = None
        ingest_request: Any | None = None

        def register_artifact(self, request: Any) -> Any:
            self.register_request = request
            return parent

        def ingest(self, request: Any) -> Any:
            self.ingest_request = request
            return module.LandingReceipt(
                run_id=request.run_id,
                source_batch_id=request.source_batch_id,
                artifact_id="artifact:staged-child",
                content_sha256=content_sha256,
                bytes_written=len(content),
                status="accepted",
                parse_run_id="parse:staged-child",
                parent_artifact_id=request.parent_artifact_id,
                parent_content_sha256=request.parent_content_sha256,
            )

        def stream(self, source_batch_id: str) -> tuple[Any, ...]:
            assert source_batch_id == member.source_batch_id
            return ()

    landing = Landing()
    boundary = object.__new__(module._RealBoundary)
    boundary._landing = landing

    readback = boundary.land_released_objects(
        entry=object(),
        member=member,
        staged_member=staged,
        run_id="landing:child",
        observed_at=NOW,
    )

    register_request = landing.register_request
    ingest_request = landing.ingest_request
    assert register_request is not None
    assert ingest_request is not None
    assert register_request.content_path == staged_path
    assert register_request.source_locator == str(member.content_path)
    assert ingest_request.parent_artifact_id == parent.artifact_id
    assert ingest_request.parent_content_sha256 == parent.content_sha256
    assert readback.artifact.parent_artifact_id == parent.artifact_id
    assert readback.artifact.parent_content_sha256 == parent.content_sha256


@pytest.mark.parametrize("hazard", ("parent_symlink", "hardlink"))
def test_real_source_staging_rejects_link_hazards_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hazard: str,
) -> None:
    module = _module()
    original = tmp_path / "protected-original.db"
    original.write_bytes(b"accepted restore fixture")
    if hazard == "parent_symlink":
        real_parent = tmp_path / "real-parent"
        real_parent.mkdir()
        (real_parent / "released.db").write_bytes(original.read_bytes())
        linked_parent = tmp_path / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        source = linked_parent / "released.db"
    else:
        source = tmp_path / "hardlinked-restore.db"
        os.link(original, source)

    member = module.SourceBuildMember(
        member_id="hazard-member",
        source_batch_id=SOURCE_BATCH_ID,
        source_kind="released_objects_sqlite",
        content_path=source,
        byte_size=source.stat().st_size,
        content_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        parser=module.ParserReference(
            parser_name="released_objects_sqlite",
            parser_version="canonical-v2-s12a-full-table-v1",
            schema_version="released-objects-v1",
            options={
                "table": "released_objects",
                "order": "primary_key",
                "limit": None,
            },
        ),
        observed_at=NOW,
        parent_source_id=RELEASED_OBJECTS_SOURCE_ID,
    )
    entry = module.SourceBuildEntry(
        source_id=RELEASED_OBJECTS_SOURCE_ID,
        disposition="evidence_input",
        source_family="sqlite_snapshot",
        members=(member,),
        approval_reference=None,
        gap_id=None,
        rationale="link-hazard regression",
    )
    boundary = object.__new__(module._RealBoundary)
    boundary._gate_root = tmp_path / "accepted-gate"
    original_os_open = module.os.open
    source_open_attempts: list[object] = []

    def recording_open(path: Any, *args: object, **kwargs: object) -> int:
        if not isinstance(path, int) and os.path.abspath(os.fspath(path)) == (
            os.path.abspath(source)
        ):
            source_open_attempts.append(path)
        return original_os_open(path, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", recording_open)

    with pytest.raises(ValueError, match="symlink|hard link|lineage"):
        boundary.stage_verified_member(
            entry=entry,
            member=member,
            destination=tmp_path / "staged.db",
        )

    assert source_open_attempts == []


def test_real_source_staging_rejects_tampered_accepted_lineage_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    gate_root = (
        Path(__file__).resolve().parents[4]
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
    )
    source = Path(
        "/var/tmp/mirothinker-restores/"
        "canonical-v2-s2b-20260711T152222Z/"
        "workspace/logs/data_agents/released_objects.db"
    )
    member_payload = _evidence_member()
    member_payload["content_path"] = str(source)
    member = module.SourceBuildMember.model_validate(member_payload).model_copy(
        update={"backup_member_manifest_sha256": "0" * 64}
    )
    entry = module.SourceBuildEntry(
        source_id=RELEASED_OBJECTS_SOURCE_ID,
        disposition="evidence_input",
        source_family="sqlite_snapshot",
        members=(member,),
        approval_reference=None,
        gap_id=None,
        rationale="accepted lineage tamper regression",
    )
    boundary = object.__new__(module._RealBoundary)
    boundary._gate_root = gate_root
    original_os_open = module.os.open
    source_open_attempts: list[object] = []

    def recording_open(path: Any, *args: object, **kwargs: object) -> int:
        if not isinstance(path, int) and os.path.abspath(os.fspath(path)) == (
            os.path.abspath(source)
        ):
            source_open_attempts.append(path)
        return original_os_open(path, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", recording_open)

    with pytest.raises(ValueError, match="lineage"):
        boundary.stage_verified_member(
            entry=entry,
            member=member,
            destination=tmp_path / "staged.db",
        )

    assert source_open_attempts == []


def test_real_source_staging_collision_never_deletes_independent_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    source = tmp_path / "source.db"
    source.write_bytes(b"accepted-source")
    destination = tmp_path / "staged.db"
    independent = b"independent-owner"
    member = module.SourceBuildMember.model_validate(_evidence_member()).model_copy(
        update={
            "content_path": source,
            "byte_size": source.stat().st_size,
            "content_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    )
    entry = module.SourceBuildEntry(
        source_id=RELEASED_OBJECTS_SOURCE_ID,
        disposition="evidence_input",
        source_family="sqlite_snapshot",
        members=(member,),
        approval_reference=None,
        gap_id=None,
        rationale="no-overwrite collision regression",
    )
    boundary = object.__new__(module._RealBoundary)
    boundary._gate_root = Path("/accepted/gate")
    monkeypatch.setattr(
        module, "_verify_accepted_released_objects_lineage", lambda **_: None
    )
    original_open = module.os.open

    def raced_open(path: Any, flags: int, mode: int = 0o777, **kwargs: Any) -> int:
        if os.path.abspath(os.fspath(path)) == os.path.abspath(destination):
            destination.write_bytes(independent)
            raise FileExistsError(destination)
        return original_open(path, flags, mode, **kwargs)

    monkeypatch.setattr(module.os, "open", raced_open)

    with pytest.raises(FileExistsError):
        boundary.stage_verified_member(
            entry=entry,
            member=member,
            destination=destination,
        )

    assert destination.read_bytes() == independent


def test_preflight_accepts_one_fresh_prepared_marker_only_index_root(
    tmp_path: Path,
) -> None:
    module = _module()
    gate_root = (
        Path(__file__).resolve().parents[4]
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
    )
    payload = _manifest_payload()
    manifest_path = tmp_path / "source-manifest.json"
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    index_target = module.prepare_isolated_index_target(
        root=tmp_path / "index",
        target_id=f"index:{RELEASE_ID}",
        release_id=RELEASE_ID,
        backup_gate_root=gate_root,
        forbidden_milvus_paths=(Path("/protected/original/milvus.db"),),
    )
    database_name = f"miroflow_{RELEASE_ID.replace('-', '_')}"
    targets = module.CompleteCandidateTargetConfig(
        database=module.DestructiveDatabaseTarget(
            url=f"postgresql+psycopg://miroflow@127.0.0.1:5432/{database_name}",
            expected_database=database_name,
            target_kind="disposable",
        ),
        index=index_target,
        staging=module.CandidateStagingTarget(
            root=tmp_path / "staging",
            marker=module.CandidateStagingMarker(
                schema_version="canonical-v2-candidate-staging-marker-v1",
                run_id=RUN_ID,
                candidate_release_id=RELEASE_ID,
                source_manifest_sha256=payload["content_sha256"],
            ),
        ),
    )
    boundary = _RecordingBoundary(module=module, rows_by_source={})
    builder = module.create_isolated_knowledge_build(
        target_config=targets,
        accepted_backup_gate_root=Path("/accepted/gate"),
        source_manifest_path=manifest_path,
        accepted_original_milvus_sha256=ORIGINAL_MILVUS_SHA256,
        accepted_original_milvus_record_sha256=_canonical_hash(
            {
                "record_kind": "accepted-original-milvus-identity",
                "content_sha256": ORIGINAL_MILVUS_SHA256,
            }
        ),
        decision_adapter=_RecordingDecisionAdapter(),
        embedding_adapter=_RecordingEmbeddingAdapter(),
        boundary=boundary,
        envelope_sink=_AtomicEnvelopeSink(module, tmp_path / "envelope.json"),
        clock=lambda: NOW,
    )

    manifest, _ = builder._preflight(_request(module))

    assert manifest.content_sha256 == payload["content_sha256"]
    assert tuple(path.name for path in index_target.root.iterdir()) == (
        ".canonical-v2-isolated-index-target.json",
    )


@pytest.mark.parametrize("mutation", ("missing", "zero"))
def test_external_source_manifest_requires_explicit_nonzero_content_sha256(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = _module()
    payload = _manifest_payload()
    boundary = _RecordingBoundary(module=module, rows_by_source={})
    sink = _AtomicEnvelopeSink(module, tmp_path / "envelope.json")
    builder, _, _ = _build_fixture(
        module,
        root=tmp_path,
        manifest_payload=payload,
        boundary=boundary,
        sink=sink,
    )
    external_payload = json.loads(json.dumps(payload))
    if mutation == "missing":
        external_payload.pop("content_sha256")
    else:
        external_payload["content_sha256"] = "0" * 64
    (tmp_path / "source-build-manifest.json").write_text(
        json.dumps(external_payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(module.SourceBuildManifestError, match="manifest|content"):
        builder._load_manifest()

    assert boundary.external_effects == []
    assert sink.writes == []


@pytest.mark.parametrize("hazard", ("symlink", "hardlink"))
def test_source_manifest_rejects_linked_protected_file_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hazard: str,
) -> None:
    module = _module()
    payload = _manifest_payload()
    boundary = _RecordingBoundary(module=module, rows_by_source={})
    sink = _AtomicEnvelopeSink(module, tmp_path / "envelope.json")
    builder, _, _ = _build_fixture(
        module,
        root=tmp_path,
        manifest_payload=payload,
        boundary=boundary,
        sink=sink,
    )
    manifest_path = tmp_path / "source-build-manifest.json"
    protected = tmp_path / "protected-original.db"
    protected.write_bytes(b"protected-original-bytes")
    manifest_path.unlink()
    if hazard == "symlink":
        manifest_path.symlink_to(protected)
    else:
        os.link(protected, manifest_path)
    original_open = module.os.open
    open_attempts: list[Path] = []

    def recording_open(path: Any, *args: Any, **kwargs: Any) -> int:
        if os.path.abspath(os.fspath(path)) == os.path.abspath(manifest_path):
            open_attempts.append(Path(path))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", recording_open)

    with pytest.raises(
        module.SourceBuildManifestError, match="manifest|authority|validation"
    ):
        builder._load_manifest()

    assert open_attempts == []
    assert boundary.external_effects == []


def test_stable_file_reader_rejects_inode_swap_before_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    source = tmp_path / "source.json"
    replacement = tmp_path / "replacement.json"
    source.write_bytes(b"accepted")
    replacement.write_bytes(b"replacement")
    original_open = module.os.open
    original_read = module.os.read
    swapped_fd: int | None = None
    reads: list[int] = []

    def raced_open(path: Any, *args: Any, **kwargs: Any) -> int:
        nonlocal swapped_fd
        if os.path.abspath(os.fspath(path)) == os.path.abspath(source):
            source.unlink()
            replacement.rename(source)
            opened = original_open(path, *args, **kwargs)
            swapped_fd = opened
            return opened
        return original_open(path, *args, **kwargs)

    def recording_read(fd: int, size: int) -> bytes:
        if fd == swapped_fd:
            reads.append(fd)
        return original_read(fd, size)

    monkeypatch.setattr(module.os, "open", raced_open)
    monkeypatch.setattr(module.os, "read", recording_read)

    with pytest.raises(ValueError, match="changed before"):
        module._read_stable_unlinked_regular_file(source)

    assert reads == []


@pytest.mark.parametrize(
    "protected_staging",
    (
        Path("/accepted/gate/candidate-staging"),
        Path("/accepted/backup/candidate-staging"),
        Path("/accepted/restore/candidate-staging"),
        Path("/protected/evidence/candidate-staging"),
        Path("/protected/original"),
    ),
)
def test_preflight_rejects_staging_overlap_with_protected_roots(
    tmp_path: Path,
    protected_staging: Path,
) -> None:
    module = _module()
    payload = _manifest_payload()
    boundary = _RecordingBoundary(module=module, rows_by_source={})
    sink = _AtomicEnvelopeSink(module, tmp_path / "envelope.json")
    builder, _, _ = _build_fixture(
        module,
        root=tmp_path,
        manifest_payload=payload,
        boundary=boundary,
        sink=sink,
        staging_root=protected_staging,
    )

    with pytest.raises(
        module.IsolatedKnowledgeBuildSafetyError, match="staging|target"
    ):
        builder._preflight(_request(module))

    assert boundary.external_effects == []
    assert sink.writes == []


@pytest.mark.parametrize(
    "protected_index",
    (
        Path("/accepted/gate/candidate-index"),
        Path("/accepted/backup/candidate-index"),
        Path("/accepted/restore/candidate-index"),
        Path("/protected/evidence/candidate-index"),
    ),
)
def test_preflight_rejects_index_overlap_with_accepted_immutable_roots(
    tmp_path: Path,
    protected_index: Path,
) -> None:
    module = _module()
    payload = _manifest_payload()
    boundary = _RecordingBoundary(module=module, rows_by_source={})
    sink = _AtomicEnvelopeSink(module, tmp_path / "envelope.json")
    builder, _, _ = _build_fixture(
        module,
        root=tmp_path,
        manifest_payload=payload,
        boundary=boundary,
        sink=sink,
        index_root=protected_index,
    )

    with pytest.raises(
        module.IsolatedKnowledgeBuildSafetyError, match="index|staging|target"
    ):
        builder._preflight(_request(module))

    assert boundary.external_effects == []
    assert sink.writes == []


def test_preflight_rejects_index_with_late_symlink_ancestor_before_any_effect(
    tmp_path: Path,
) -> None:
    module = _module()
    payload = _manifest_payload()
    boundary = _RecordingBoundary(module=module, rows_by_source={})
    sink = _AtomicEnvelopeSink(module, tmp_path / "envelope.json")
    linked_parent = tmp_path / "late-index-parent"
    builder, _, _ = _build_fixture(
        module,
        root=tmp_path,
        manifest_payload=payload,
        boundary=boundary,
        sink=sink,
        index_root=linked_parent / "index",
    )
    real_parent = tmp_path / "real-index-parent"
    real_parent.mkdir()
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(
        module.IsolatedKnowledgeBuildSafetyError, match="symlink|target|ancestry"
    ):
        builder._preflight(_request(module))

    assert boundary.external_effects == []
    assert sink.writes == []


def test_build_rejects_active_release_race_before_source_staging(
    tmp_path: Path,
) -> None:
    module = _module()
    payload = _manifest_payload()
    boundary = _RecordingBoundary(
        module=module,
        rows_by_source={},
        active_release={
            "canonical_release_id": "raced-active",
            "published_projection_release_id": "raced-active",
            "index_release_id": "raced-active",
        },
    )
    sink = _AtomicEnvelopeSink(module, tmp_path / "envelope.json")
    builder, decision, embedding = _build_fixture(
        module,
        root=tmp_path,
        manifest_payload=payload,
        boundary=boundary,
        sink=sink,
    )

    with pytest.raises(
        module.IsolatedKnowledgeBuildSafetyError, match="active release"
    ):
        builder.build(_request(module))

    assert boundary.staged_source_ids == []
    assert decision.calls == []
    assert embedding.calls == []
    assert sink.writes == []


def test_preflight_rejects_decoy_original_milvus_path_before_any_effect(
    tmp_path: Path,
) -> None:
    module = _module()
    payload = _manifest_payload()
    boundary = _RecordingBoundary(module=module, rows_by_source={})
    sink = _AtomicEnvelopeSink(module, tmp_path / "envelope.json")
    builder, _, _ = _build_fixture(
        module,
        root=tmp_path,
        manifest_payload=payload,
        boundary=boundary,
        sink=sink,
        forbidden_milvus_path=Path("/decoy/original/milvus.db"),
    )

    with pytest.raises(
        module.IsolatedKnowledgeBuildSafetyError,
        match="target|Milvus|identit",
    ):
        builder._preflight(_request(module))

    assert boundary.external_effects == []
    assert sink.writes == []


def test_preflight_rejects_preexisting_envelope_before_any_effect(
    tmp_path: Path,
) -> None:
    module = _module()
    payload = _manifest_payload()
    boundary = _RecordingBoundary(module=module, rows_by_source={})
    destination = tmp_path / "envelope.json"
    destination.write_text("independent owner\n", encoding="utf-8")
    sink = _AtomicEnvelopeSink(module, destination)
    builder, _, _ = _build_fixture(
        module,
        root=tmp_path,
        manifest_payload=payload,
        boundary=boundary,
        sink=sink,
    )

    with pytest.raises(
        module.IsolatedKnowledgeBuildSafetyError,
        match="envelope|preflight",
    ):
        builder._preflight(_request(module))

    assert destination.read_text(encoding="utf-8") == "independent owner\n"
    assert boundary.external_effects == []
    assert sink.writes == []


@pytest.mark.parametrize(
    ("evidence_slice", "release_id"),
    (
        ("s12a", RELEASE_ID),
        ("s12b", "candidate-s12b-test"),
    ),
)
def test_preflight_allows_fixed_candidate_envelope_beneath_broad_evidence_root(
    tmp_path: Path,
    evidence_slice: str,
    release_id: str,
) -> None:
    module = _module()
    evidence_root = tmp_path / "repository"
    gate_root = evidence_root / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
    evidence_slice_root = gate_root / evidence_slice
    evidence_slice_root.mkdir(parents=True)
    manifest_payload = _manifest_payload()
    manifest_path = evidence_slice_root / "source-build-manifest-v1.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    targets = _target_config(
        module,
        root=tmp_path / "targets",
        source_manifest_sha256=manifest_payload["content_sha256"],
        release_id=release_id,
    )

    @dataclass
    class Boundary(_RecordingBoundary):
        def verify_accepted_control_files_safe(self, *, gate_root: Path) -> None:
            assert gate_root == self_gate_root

        def resolve_accepted_immutable_paths(
            self, *, gate_root: Path, expected_sha256: str
        ) -> Any:
            assert gate_root == self_gate_root
            assert expected_sha256 == ORIGINAL_MILVUS_SHA256
            return module._AcceptedImmutablePaths(
                backup_root=Path("/accepted/backup"),
                restore_root=Path("/accepted/restore"),
                evidence_root=evidence_root,
                original_milvus_path=Path("/protected/original/milvus.db"),
            )

        def resolve_accepted_original_milvus_path(
            self, *, gate_root: Path, expected_sha256: str
        ) -> Path:
            assert gate_root == self_gate_root
            assert expected_sha256 == ORIGINAL_MILVUS_SHA256
            return Path("/protected/original/milvus.db")

        def verify_accepted_gate(self, *, gate_root: Path) -> Any:
            assert gate_root == self_gate_root
            return _AcceptedGateSnapshot(
                source_inventory_sha256=SOURCE_INVENTORY_SHA256,
                backup_manifest_sha256=BACKUP_MANIFEST_SHA256,
                restore_verification_sha256=RESTORE_VERIFICATION_SHA256,
                acceptance_record_sha256=ACCEPTANCE_RECORD_SHA256,
                accepted_original_milvus_sha256=ORIGINAL_MILVUS_SHA256,
            )

    self_gate_root = gate_root
    boundary = Boundary(module=module, rows_by_source={})

    @dataclass
    class Sink(_AtomicEnvelopeSink):
        def validate_fresh(
            self,
            *,
            required_destination: Path,
            protected_paths: tuple[Path, ...],
        ) -> None:
            assert required_destination == self.destination
            assert not any(
                self.module._paths_overlap(self.destination, path)
                for path in protected_paths
            )

    sink = Sink(
        module,
        evidence_slice_root / "complete-candidate-build-envelope.json",
    )
    builder = module.create_isolated_knowledge_build(
        target_config=targets,
        accepted_backup_gate_root=gate_root,
        source_manifest_path=manifest_path,
        accepted_original_milvus_sha256=ORIGINAL_MILVUS_SHA256,
        accepted_original_milvus_record_sha256=_canonical_hash(
            {
                "record_kind": "accepted-original-milvus-identity",
                "content_sha256": ORIGINAL_MILVUS_SHA256,
            }
        ),
        decision_adapter=_RecordingDecisionAdapter(),
        embedding_adapter=_RecordingEmbeddingAdapter(),
        boundary=boundary,
        envelope_sink=sink,
        clock=lambda: NOW,
    )

    manifest, _ = builder._preflight(_request(module, release_id=release_id))

    assert manifest.content_sha256 == manifest_payload["content_sha256"]
    assert boundary.external_effects == []
    assert sink.writes == []


def test_preflight_gate_failure_does_not_prepare_index_or_staging(
    tmp_path: Path,
) -> None:
    module = _module()

    @dataclass
    class GateFailureBoundary(_RecordingBoundary):
        prepare_calls: int = 0

        def verify_accepted_gate(self, *, gate_root: Path) -> Any:
            raise _BoundaryFailure(f"gate rejected at {gate_root}")

        def prepare_fresh_targets(self, *, target_config: Any) -> None:
            self.prepare_calls += 1
            raise AssertionError("target preparation must follow the accepted gate")

    payload = _manifest_payload()
    boundary = GateFailureBoundary(module=module, rows_by_source={})
    sink = _AtomicEnvelopeSink(module, tmp_path / "envelope.json")
    builder, _, _ = _build_fixture(
        module,
        root=tmp_path,
        manifest_payload=payload,
        boundary=boundary,
        sink=sink,
    )

    with pytest.raises(module.IsolatedKnowledgeBuildSafetyError, match="gate|target"):
        builder._preflight(_request(module))

    assert boundary.prepare_calls == 0
    assert not (tmp_path / "index").exists()
    assert not (tmp_path / "staging").exists()


@pytest.mark.parametrize("race", (False, True), ids=("preexisting", "raced"))
def test_file_envelope_sink_never_overwrites_existing_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    race: bool,
) -> None:
    module = _module()
    destination = tmp_path / "complete-candidate-envelope.json"
    original = b"independent-owner\n"
    if not race:
        destination.write_bytes(original)

    class ProbeEnvelope:
        def model_dump_json(self, *, indent: int) -> str:
            assert indent == 2
            if race:
                destination.write_bytes(original)
            return "{}"

    probe = ProbeEnvelope()
    monkeypatch.setattr(
        module.CompleteCandidateBuildEnvelope,
        "model_validate_json",
        lambda value, **kwargs: probe,
    )
    sink = module.FileCompleteCandidateEnvelopeSink(destination)

    with pytest.raises(ValueError, match="fresh|owner|exist"):
        sink.write_and_readback(probe)

    assert destination.read_bytes() == original
    assert tuple(tmp_path.glob(".*.tmp")) == ()


@pytest.mark.parametrize(
    "hazard",
    (
        "publish.active_release",
        "publish.build_manifest",
        "publish.manifest_section",
        "knowledge.policy",
        "knowledge.canonical_identity",
        "knowledge.canonical_decision",
        "knowledge.relationship_projection_run",
        "landing.source_record",
        "company.current_projection",
        "ops.knowledge_gap",
    ),
)
def test_real_boundary_rejects_nonfresh_database_before_source_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hazard: str,
) -> None:
    module = _module()
    gate_root = (
        Path(__file__).resolve().parents[4]
        / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
    )
    index_target = module.prepare_isolated_index_target(
        root=tmp_path / "index",
        target_id=f"index:{RELEASE_ID}",
        release_id=RELEASE_ID,
        backup_gate_root=gate_root,
        forbidden_milvus_paths=(Path("/protected/original/milvus.db"),),
    )
    database_name = f"miroflow_{RELEASE_ID.replace('-', '_')}"
    targets = module.CompleteCandidateTargetConfig(
        database=module.DestructiveDatabaseTarget(
            url=f"postgresql+psycopg://miroflow@127.0.0.1:5432/{database_name}",
            expected_database=database_name,
            target_kind="disposable",
        ),
        index=index_target,
        staging=module.CandidateStagingTarget(
            root=tmp_path / "staging",
            marker=module.CandidateStagingMarker(
                schema_version="canonical-v2-candidate-staging-marker-v1",
                run_id=RUN_ID,
                candidate_release_id=RELEASE_ID,
                source_manifest_sha256="f" * 64,
            ),
        ),
    )

    class Cursor:
        def __init__(self, rows: tuple[object, ...]) -> None:
            self._rows = rows

        def fetchone(self) -> object:
            return self._rows[0] if self._rows else None

        def fetchall(self) -> tuple[object, ...]:
            return self._rows

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, query: object, parameters: object = None) -> Cursor:
            del parameters
            text = str(query)
            if "canonical_v2_alembic_version" in text:
                return Cursor(({"version_num": "C2_0011"},))
            if "information_schema.tables" in text:
                return Cursor(
                    tuple(
                        {
                            "table_schema": identity.split(".", maxsplit=1)[0],
                            "table_name": identity.split(".", maxsplit=1)[1],
                        }
                        for identity in sorted(module._EXPECTED_OWNER_TABLES)
                    )
                )
            return Cursor(({"has_rows": True},))

        def rollback(self) -> None:
            return None

    connection = Connection()
    monkeypatch.setattr(
        module._RealBoundary,
        "_connect",
        lambda self: connection,
    )
    monkeypatch.setattr(
        module,
        "_live_schema_catalog_sha256",
        lambda observed_connection: module._EXPECTED_LIVE_SCHEMA_CATALOG_SHA256,
    )
    boundary = object.__new__(module._RealBoundary)
    boundary._targets = targets
    boundary._gate_root = gate_root

    marker_before = index_target.root.joinpath(
        ".canonical-v2-isolated-index-target.json"
    ).read_bytes()
    with pytest.raises(ValueError, match="fresh"):
        boundary.validate_fresh_targets(target_config=targets)
    assert not targets.staging.root.exists()
    assert (
        index_target.root.joinpath(
            ".canonical-v2-isolated-index-target.json"
        ).read_bytes()
        == marker_before
    )


@pytest.mark.parametrize("drift", ("revision", "schema"))
def test_real_boundary_requires_exact_live_migration_schema_before_source_read(
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    module = _module()

    class Cursor:
        def __init__(self, rows: tuple[object, ...]) -> None:
            self._rows = rows

        def fetchall(self) -> tuple[object, ...]:
            return self._rows

        def fetchone(self) -> object:
            return self._rows[0] if self._rows else None

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, query: object, parameters: object = None) -> Cursor:
            del parameters
            text = str(query)
            if "canonical_v2_alembic_version" in text:
                revision = "C2_0010" if drift == "revision" else "C2_0011"
                return Cursor(({"version_num": revision},))
            if "information_schema.tables" in text:
                schemas = (
                    "company",
                    "knowledge",
                    "landing",
                    "ops",
                    "paper",
                    "patent",
                    "professor",
                    "publish",
                )
                if drift == "schema":
                    schemas = schemas[:-1]
                return Cursor(
                    tuple(
                        {"table_schema": schema, "table_name": "placeholder"}
                        for schema in schemas
                    )
                )
            return Cursor(({"has_rows": False},))

        def rollback(self) -> None:
            return None

    boundary = object.__new__(module._RealBoundary)
    monkeypatch.setattr(
        module._RealBoundary,
        "_connect",
        lambda self: Connection(),
    )

    with pytest.raises(ValueError, match="migration|schema|inventory|revision"):
        boundary._assert_fresh_database()


@pytest.mark.parametrize(
    "object_kind",
    (
        "server",
        "relation",
        "column",
        "constraint",
        "index",
        "trigger",
        "routine",
        "view",
    ),
)
def test_live_schema_fingerprint_binds_every_behavioral_object_class(
    object_kind: str,
) -> None:
    module = _module()
    baseline = tuple(
        {
            "object_kind": kind,
            "object_identity": f"knowledge.example:{kind}",
            "definition": {"value": "accepted"},
        }
        for kind in (
            "server",
            "relation",
            "column",
            "constraint",
            "index",
            "trigger",
            "routine",
            "view",
        )
    )
    drifted = tuple(
        {
            **row,
            "definition": (
                {"value": "drifted"}
                if row["object_kind"] == object_kind
                else row["definition"]
            ),
        }
        for row in baseline
    )

    baseline_sha256 = module._schema_catalog_sha256(baseline)
    assert baseline_sha256 == module._schema_catalog_sha256(tuple(reversed(baseline)))
    assert baseline_sha256 != module._schema_catalog_sha256(drifted)


def test_real_boundary_rejects_live_schema_fingerprint_drift_before_row_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()

    class Cursor:
        def __init__(self, rows: tuple[object, ...]) -> None:
            self._rows = rows

        def fetchall(self) -> tuple[object, ...]:
            return self._rows

        def fetchone(self) -> object:
            return self._rows[0] if self._rows else None

    class Connection:
        row_probe_attempted = False

        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, query: object, parameters: object = None) -> Cursor:
            del parameters
            text = str(query)
            if "canonical_v2_alembic_version" in text:
                return Cursor(({"version_num": "C2_0011"},))
            if "information_schema.tables" in text:
                return Cursor(
                    tuple(
                        {
                            "table_schema": identity.split(".", maxsplit=1)[0],
                            "table_name": identity.split(".", maxsplit=1)[1],
                        }
                        for identity in sorted(module._EXPECTED_OWNER_TABLES)
                    )
                )
            self.row_probe_attempted = True
            return Cursor(({"has_rows": False},))

        def rollback(self) -> None:
            return None

    connection = Connection()
    boundary = object.__new__(module._RealBoundary)
    monkeypatch.setattr(module._RealBoundary, "_connect", lambda self: connection)
    monkeypatch.setattr(
        module,
        "_live_schema_catalog_sha256",
        lambda observed_connection: "f" * 64,
        raising=False,
    )

    with pytest.raises(ValueError, match="schema.*fingerprint"):
        boundary._assert_fresh_database()

    assert connection.row_probe_attempted is False


def test_real_boundary_rejects_staging_with_symlink_ancestor_before_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    real_root = tmp_path / "real"
    (real_root / "nested").mkdir(parents=True)
    (tmp_path / "targets").mkdir()
    late_link = tmp_path / "late-link"
    staging_root = late_link / "nested" / "staging"
    targets = _target_config(
        module,
        root=tmp_path / "targets",
        source_manifest_sha256="f" * 64,
        release_id=RELEASE_ID,
        staging_root=staging_root,
    )
    late_link.symlink_to(real_root, target_is_directory=True)
    monkeypatch.setattr(
        module,
        "prepare_isolated_index_target",
        lambda **kwargs: targets.index,
    )
    connect_attempts = 0

    def forbidden_connect(self: object) -> None:
        nonlocal connect_attempts
        connect_attempts += 1
        raise AssertionError("database connect must not follow a staging symlink")

    monkeypatch.setattr(module._RealBoundary, "_connect", forbidden_connect)
    boundary = object.__new__(module._RealBoundary)
    boundary._targets = targets
    boundary._gate_root = Path("/accepted/gate")

    with pytest.raises(ValueError, match="symlink|ancestry"):
        boundary.validate_fresh_targets(target_config=targets)

    assert connect_attempts == 0
    assert not (real_root / "nested" / "staging").exists()


def test_real_boundary_rereads_exact_staging_marker_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    targets = _target_config(
        module,
        root=tmp_path,
        source_manifest_sha256="f" * 64,
        release_id=RELEASE_ID,
    )
    boundary = object.__new__(module._RealBoundary)
    boundary._targets = targets
    boundary._gate_root = Path("/accepted/gate")
    monkeypatch.setattr(
        module._RealBoundary,
        "validate_fresh_targets",
        lambda self, *, target_config: None,
    )
    monkeypatch.setattr(
        module,
        "prepare_isolated_index_target",
        lambda **kwargs: targets.index,
    )
    real_read = module._read_stable_unlinked_regular_file

    def tampered_readback(path: Path) -> bytes:
        if path.name == ".canonical-v2-staging.json":
            return b'{"schema_version":"tampered"}\n'
        return real_read(path)

    monkeypatch.setattr(
        module,
        "_read_stable_unlinked_regular_file",
        tampered_readback,
    )

    with pytest.raises((ValueError, module.ValidationError), match="marker|schema"):
        boundary.prepare_fresh_targets(target_config=targets)

    assert not targets.staging.root.exists()


def test_real_boundary_rejects_network_filesystem_targets_before_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    targets = _target_config(
        module,
        root=tmp_path,
        source_manifest_sha256="f" * 64,
        release_id=RELEASE_ID,
    )
    boundary = object.__new__(module._RealBoundary)
    boundary._targets = targets
    boundary._gate_root = Path("/accepted/gate")
    monkeypatch.setattr(
        module,
        "_filesystem_type_for_path",
        lambda path: "nfs4",
        raising=False,
    )
    connect_attempts = 0

    def forbidden_database_check(self: object) -> None:
        nonlocal connect_attempts
        connect_attempts += 1

    monkeypatch.setattr(
        module._RealBoundary,
        "_assert_fresh_database",
        forbidden_database_check,
    )

    with pytest.raises(ValueError, match="network filesystem"):
        boundary.validate_fresh_targets(target_config=targets)

    assert connect_attempts == 0


def test_public_authority_routes_inclusion_through_accepted_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    member = module.SourceBuildMember.model_validate(_evidence_member())
    raw_rows = [
        {
            "id": payload["id"],
            "object_type": payload["object_type"],
            "display_name": payload["display_name"],
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        }
        for payload in (
            _released_object_payload("company", 0),
            _released_object_payload("paper", 0),
            _released_object_payload("patent", 0),
            _released_object_payload("professor", 0),
        )
    ]
    link_payload = {
        "id": "professor-paper-link:00000",
        "object_type": "professor_paper_link",
        "display_name": "Professor-paper link 00000",
        "core_facts": {
            "professor_id": "professor:00000",
            "paper_id": "paper:00000",
        },
        "summary_fields": {},
        "evidence": [
            {
                "source_type": "xlsx_import",
                "source_url": "https://evidence.invalid/link/00000",
                "fetched_at": "2026-07-21T00:00:00Z",
            }
        ],
        "last_updated": "2026-07-21T00:00:00Z",
        "quality_status": "ready",
    }
    raw_rows.append(
        {
            "id": link_payload["id"],
            "object_type": link_payload["object_type"],
            "display_name": link_payload["display_name"],
            "payload_json": json.dumps(
                link_payload, ensure_ascii=False, sort_keys=True
            ),
        }
    )
    rows = tuple(
        (
            lambda record: module._ParsedReleasedObject(
                source_id=RELEASED_OBJECTS_SOURCE_ID,
                source_batch_id=SOURCE_BATCH_ID,
                record=record,
                artifact=module.EvidenceArtifact(
                    artifact_id=record.artifact_id,
                    source_kind=member.source_kind,
                    source_locator=str(member.content_path),
                    content_sha256=member.content_sha256,
                    byte_size=member.byte_size,
                    acquired_at=NOW,
                    run_id=RUN_ID,
                ),
                payload=json.loads(row["payload_json"]),
            )
        )(
            module._source_record(
                row=row,
                source_batch_id=SOURCE_BATCH_ID,
                member=member,
                parsed_at=NOW,
            )
        )
        for row in raw_rows
    )

    class InclusionSentinel(RuntimeError):
        pass

    class Engine:
        def evaluate(self, request: object) -> None:
            assert request.__class__.__name__ == "InclusionBatchRequest"
            raise InclusionSentinel("accepted inclusion engine reached")

    monkeypatch.setattr(
        module,
        "create_ephemeral_domain_inclusion_engine",
        lambda: Engine(),
        raising=False,
    )

    with pytest.raises(InclusionSentinel, match="accepted inclusion engine reached"):
        module._map_public_authority(
            request=_request(module),
            rows=rows,
            initial_gaps=(),
            decision_adapter=_RecordingDecisionAdapter(),
            now=NOW,
        )


def test_public_authority_records_invalid_relationship_endpoint_as_typed_gap() -> None:
    module = _module()
    member = module.SourceBuildMember.model_validate(_evidence_member())
    company_payload = _released_object_payload("company", 0)
    company_payload["core_facts"].pop("key_personnel")
    link_payload = {
        "id": "professor-paper-link:missing-endpoints",
        "object_type": "professor_paper_link",
        "display_name": "Missing relationship endpoints",
        "core_facts": {
            "professor_id": "professor:not-projectable",
            "paper_id": "paper:not-projectable",
            "professor_name": "Unallowlisted historical name",
        },
        "summary_fields": {},
        "evidence": [
            {
                "source_type": "xlsx_import",
                "source_url": "https://evidence.invalid/link/missing-endpoints",
                "fetched_at": "2026-07-21T00:00:00Z",
            }
        ],
        "last_updated": "2026-07-21T00:00:00",
        "quality_status": "ready",
        "private_link_top": "must not disappear",
    }
    link_payload["evidence"][0]["private_link_evidence"] = "must not disappear"
    raw_rows = tuple(
        {
            "id": payload["id"],
            "object_type": payload["object_type"],
            "display_name": payload["display_name"],
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        }
        for payload in (company_payload, link_payload)
    )
    parsed_rows = tuple(
        (
            lambda record, payload: module._ParsedReleasedObject(
                source_id=RELEASED_OBJECTS_SOURCE_ID,
                source_batch_id=SOURCE_BATCH_ID,
                record=record,
                artifact=module.EvidenceArtifact(
                    artifact_id=record.artifact_id,
                    source_kind=member.source_kind,
                    source_locator=str(member.content_path),
                    content_sha256=member.content_sha256,
                    byte_size=member.byte_size,
                    acquired_at=NOW,
                    run_id=RUN_ID,
                ),
                payload=payload,
            )
        )(
            module._source_record(
                row=row,
                source_batch_id=SOURCE_BATCH_ID,
                member=member,
                parsed_at=NOW,
            ),
            json.loads(row["payload_json"]),
        )
        for row in raw_rows
    )

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    domain_result = result[4]
    valid_links = result[5]
    gaps = result[6]
    assert domain_result.counts_by_domain == {
        "company": 1,
        "paper": 0,
        "patent": 0,
        "professor": 0,
    }
    assert valid_links == ()
    assert len(gaps) == 1
    assert gaps[0].result.evidence_ids == (parsed_rows[1].record.record_id,)
    assert {
        "core_facts.professor_id",
        "core_facts.paper_id",
        "core_facts.professor_name",
        "evidence[0].private_link_evidence",
        "last_updated",
        "private_link_top",
    } <= set(gaps[0].signal.affected_paths)
    internal = module._internal_candidate_authority(
        request=_request(module),
        domain_request=result[3],
        domain_result=domain_result,
        now=NOW,
    )
    relationship_request, relationship_result = module._relationship_authority(
        request=_request(module),
        identity_result=result[1],
        decision_result=result[2],
        domain_result=domain_result,
        internal_request=internal[0],
        internal_result=internal[1],
        links=valid_links,
        now=NOW,
    )
    assert (
        relationship_request.relationship_registry_version
        == "canonical-v2-domain-relationship-registry-v1"
    )
    assert relationship_request.internal_reference_projection_request is None
    assert relationship_request.internal_reference_projection_result is None
    assert relationship_result.current_relationships == ()


def test_typed_gap_requires_specific_affected_paths() -> None:
    module = _module()
    record = _parsed_released_objects(
        module,
        (_released_object_payload("company", 0),),
    )[0].record

    with pytest.raises(ValueError, match="affected path"):
        module._gap(
            release_id=RELEASE_ID,
            run_id=RUN_ID,
            record=record,
            domain="company",
            reason="missing exact field audit",
            now=NOW,
        )


def test_public_authority_aggregates_mixed_container_field_and_endpoint_paths() -> None:
    module = _module()
    malformed_company = _released_object_payload("company", 30)
    malformed_company["core_facts"].pop("key_personnel")
    malformed_company["summary_fields"] = "invalid-summary-container"
    valid_company = _released_object_payload("company", 31)
    valid_company["core_facts"].pop("key_personnel")
    malformed_link = {
        "id": "professor-paper-link:mixed-container",
        "object_type": "professor_paper_link",
        "display_name": "Mixed-container relationship",
        "core_facts": {
            "professor_id": "professor:missing",
            "paper_id": "paper:missing",
            "professor_name": "Unallowlisted name",
        },
        "summary_fields": "invalid-summary-container",
        "evidence": [
            {
                "source_type": "xlsx_import",
                "source_url": "https://evidence.invalid/mixed-container",
                "fetched_at": "2026-07-21T00:00:00Z",
            }
        ],
        "last_updated": "2026-07-21T00:00:00Z",
        "quality_status": "ready",
    }
    parsed_rows = _parsed_released_objects(
        module, (malformed_company, valid_company, malformed_link)
    )

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["company"] == 1
    assert result[5] == ()
    gaps_by_record = {gap.signal.evidence_ids[0]: gap for gap in result[6]}
    assert len(gaps_by_record) == 2
    company_paths = set(
        gaps_by_record[parsed_rows[0].record.record_id].signal.affected_paths
    )
    assert {
        "summary_fields",
        "summary_fields.profile_summary",
        "summary_fields.technology_route_summary",
    } <= company_paths
    relationship_paths = set(
        gaps_by_record[parsed_rows[2].record.record_id].signal.affected_paths
    )
    assert {
        "summary_fields",
        "core_facts.professor_id",
        "core_facts.paper_id",
        "core_facts.professor_name",
    } <= relationship_paths


def test_public_authority_audits_all_disallowed_and_invalid_field_paths_without_dropping_valid_projection() -> (
    None
):
    module = _module()
    company = _released_object_payload("company", 0)
    company["core_facts"].update(
        {"industry": "robotics", "website": "https://company.invalid"}
    )
    company["summary_fields"]["evaluation_summary"] = "Historical evaluation."
    paper = _released_object_payload("paper", 0)
    paper["core_facts"].update(
        {
            "abstract": "Historical abstract.",
            "authors": [{"name": "Unmapped Author"}],
            "title": "",
            "venue": "Legacy venue string",
        }
    )
    paper["summary_fields"] = {"summary_text": "Historical summary."}
    parsed_rows = _parsed_released_objects(module, (company, paper))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain == {
        "company": 1,
        "paper": 0,
        "patent": 0,
        "professor": 0,
    }
    gaps_by_record = {gap.signal.evidence_ids[0]: gap for gap in result[6]}
    assert set(gaps_by_record) == {
        parsed_rows[0].record.record_id,
        parsed_rows[1].record.record_id,
    }
    company_gap = gaps_by_record[parsed_rows[0].record.record_id]
    assert {"summary_fields.evaluation_summary"} <= set(
        company_gap.signal.affected_paths
    )
    # industry/website/key_personnel moved from disallowed drops to projected
    # fields when the s12e company whitelist widened.
    assert "core_facts.industry" not in company_gap.signal.affected_paths
    assert "core_facts.website" not in company_gap.signal.affected_paths
    company_projection = next(
        item for item in result[4].projections if item.entity_type == "company"
    )
    assert company_projection.industry is not None
    assert company_projection.industry.name == "robotics"
    assert company_projection.website == "https://company.invalid"
    paper_gap = gaps_by_record[parsed_rows[1].record.record_id]
    assert {
        "core_facts.abstract",
        "core_facts.name",
        "core_facts.title",
    } <= set(paper_gap.signal.affected_paths)
    assert '"disallowed_paths"' in paper_gap.signal.observed_symptom
    assert '"invalid_allowed_paths"' in paper_gap.signal.observed_symptom


def test_public_authority_turns_malformed_reference_time_and_evidence_into_one_gap_per_row() -> (
    None
):
    module = _module()
    malformed_venue = _released_object_payload("paper", 10)
    malformed_venue["core_facts"]["venue"] = {
        "reference_id": "",
        "name": "",
    }
    invalid_year = _released_object_payload("paper", 11)
    invalid_year["core_facts"]["year"] = 10000
    malformed_department = _released_object_payload("professor", 12)
    malformed_department["core_facts"]["department"] = {"reference_id": "only-id"}
    naive_time = _released_object_payload("company", 13)
    naive_time["last_updated"] = "2026-07-21T00:00:00"
    future_time = _released_object_payload("company", 14)
    future_time["last_updated"] = "2026-07-23T00:00:00Z"
    malformed_evidence = _released_object_payload("company", 15)
    malformed_evidence["evidence"] = [
        {
            "source_type": "xlsx_import",
            "source_url": None,
            "source_file": None,
            "fetched_at": "not-a-timestamp",
        }
    ]
    payloads = (
        malformed_venue,
        invalid_year,
        malformed_department,
        naive_time,
        future_time,
        malformed_evidence,
    )
    parsed_rows = _parsed_released_objects(module, payloads)

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain == {
        "company": 0,
        "paper": 0,
        "patent": 0,
        "professor": 0,
    }
    assert len(result[6]) == len(parsed_rows)
    gaps_by_record = {gap.signal.evidence_ids[0]: gap for gap in result[6]}
    assert len(gaps_by_record) == len(parsed_rows)
    expected_paths = (
        "core_facts.venue.reference_id",
        "core_facts.year",
        "core_facts.department.name",
        "last_updated",
        "last_updated",
        "evidence[0].fetched_at",
    )
    for row, expected_path in zip(parsed_rows, expected_paths, strict=True):
        assert (
            expected_path in gaps_by_record[row.record.record_id].signal.affected_paths
        )
    malformed_evidence_gap = gaps_by_record[parsed_rows[-1].record.record_id]
    assert "evidence[0].locator" in malformed_evidence_gap.signal.affected_paths


def test_public_authority_aggregates_unsupported_schema_and_metadata_paths() -> None:
    module = _module()
    unsupported = _released_object_payload("company", 20)
    unsupported["object_type"] = "product"
    unsupported["last_updated"] = "not-a-timestamp"
    unsupported["core_facts"]["private_product_path"] = "must not project"
    valid_company = _released_object_payload("company", 21)
    valid_company["core_facts"].pop("key_personnel")
    parsed_rows = _parsed_released_objects(module, (unsupported, valid_company))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain == {
        "company": 1,
        "paper": 0,
        "patent": 0,
        "professor": 0,
    }
    assert len(result[6]) == 1
    assert {
        "object_type",
        "last_updated",
        "core_facts.private_product_path",
        "summary_fields.profile_summary",
    } <= set(result[6][0].signal.affected_paths)


def test_public_authority_admits_professor_on_name_and_institution_with_quality_signals() -> (
    None
):
    """name+institution 即可入投影；缺 department/email/title 降级为质量信号。"""
    module = _module()
    professor = _released_object_payload("professor", 30)
    professor["display_name"] = "王学谦"
    professor["core_facts"].update(
        {
            "name": "王学谦",
            "canonical_name_zh": "王学谦",
            "institution": "清华大学深圳国际研究生院",
        }
    )
    for field_name in ("department", "email", "title"):
        professor["core_facts"].pop(field_name)
    parsed_rows = _parsed_released_objects(module, (professor,))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["professor"] == 1
    projection = next(
        item for item in result[4].projections if item.entity_type == "professor"
    )
    assert projection.name == "王学谦"
    assert projection.institution == "清华大学深圳国际研究生院"
    gaps_by_record = {gap.signal.evidence_ids[0]: gap for gap in result[6]}
    gap = gaps_by_record[parsed_rows[0].record.record_id]
    for signal in ("missing_department", "missing_email", "missing_title"):
        assert signal in gap.signal.observed_symptom
    assert {
        "core_facts.department",
        "core_facts.email",
        "core_facts.title",
    } <= set(gap.signal.affected_paths)
    # Defaulted fields must not feed identity keys; otherwise unrelated
    # same-name professors would auto-merge on the shared fallback value.
    source_identity = next(
        item for item in result[0].source_identities if item.entity_type == "professor"
    )
    assert "name_key" in source_identity.normalized_keys
    assert "institution_key" in source_identity.normalized_keys
    assert "department_key" not in source_identity.normalized_keys
    assert "email_key" not in source_identity.normalized_keys


def test_public_authority_still_rejects_professor_missing_name_or_institution() -> (
    None
):
    module = _module()
    missing_institution = _released_object_payload("professor", 31)
    missing_institution["core_facts"].pop("institution")
    missing_name = _released_object_payload("professor", 32)
    missing_name["core_facts"].pop("name")
    missing_name["core_facts"].pop("canonical_name_zh")
    parsed_rows = _parsed_released_objects(
        module, (missing_institution, missing_name)
    )

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["professor"] == 0
    assert not [
        item for item in result[4].projections if item.entity_type == "professor"
    ]
    gaps_by_record = {gap.signal.evidence_ids[0]: gap for gap in result[6]}
    institution_gap = gaps_by_record[parsed_rows[0].record.record_id]
    assert "core_facts.institution" in institution_gap.signal.affected_paths
    name_gap = gaps_by_record[parsed_rows[1].record.record_id]
    assert "core_facts.name" in name_gap.signal.affected_paths


def test_public_authority_projects_company_industry_website_and_key_personnel() -> (
    None
):
    """source 已有的 industry/website/key_personnel 应进入公司投影而非被白名单丢弃。"""
    module = _module()
    company = _released_object_payload("company", 40)
    company["core_facts"].update(
        {
            "industry": "智能机器人",
            "key_personnel": [
                {"name": "刘先勇", "role": "执行董事&总经理"},
                {"name": "王五", "role": "首席技术官", "unused": "dropped"},
            ],
            "website": "https://company.invalid/",
        }
    )
    parsed_rows = _parsed_released_objects(module, (company,))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["company"] == 1
    projection = next(
        item for item in result[4].projections if item.entity_type == "company"
    )
    assert projection.industry is not None
    assert projection.industry.name == "智能机器人"
    assert projection.website == "https://company.invalid/"
    assert [(item.name, item.role) for item in projection.key_personnel] == [
        ("刘先勇", "执行董事&总经理"),
        ("王五", "首席技术官"),
    ]


def test_public_authority_keeps_company_projection_when_optional_fields_absent() -> (
    None
):
    module = _module()
    company = _released_object_payload("company", 41)
    company["core_facts"].pop("key_personnel")
    parsed_rows = _parsed_released_objects(module, (company,))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["company"] == 1
    projection = next(
        item for item in result[4].projections if item.entity_type == "company"
    )
    assert projection.industry is None
    assert projection.website is None
    assert projection.key_personnel == ()
    assert result[6] == ()


def test_public_authority_projects_paper_doi_and_arxiv_identifiers() -> None:
    """landing 已有的 doi/arxiv_id/pdf_path 应进入论文投影（s12e 论文审计实证）。"""
    module = _module()
    professor = _released_object_payload("professor", 50)
    paper = _released_object_payload("paper", 50)
    paper["core_facts"].update(
        {
            "title": "pFedGPA",
            "authors": ["Wenbo Ding", "Example Author"],
            "doi": "10.1609/aaai.v39i17.33980",
            "arxiv_id": "2409.05701",
            "pdf_path": "papers/pfedgpa.pdf",
        }
    )
    paper["summary_fields"] = {"summary_text": "Source-grounded paper summary."}
    link = _professor_paper_link_payload(professor, paper, "paper-identifiers")
    parsed_rows = _parsed_released_objects(module, (professor, paper, link))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["paper"] == 1
    projection = next(
        item for item in result[4].projections if item.entity_type == "paper"
    )
    assert projection.doi == "10.1609/aaai.v39i17.33980"
    assert projection.arxiv_id == "2409.05701"
    assert projection.pdf_path == "papers/pfedgpa.pdf"


def test_public_authority_keeps_paper_projection_when_identifiers_null() -> None:
    module = _module()
    professor = _released_object_payload("professor", 51)
    paper = _released_object_payload("paper", 51)
    paper["core_facts"].update(
        {"doi": None, "arxiv_id": None, "pdf_path": None}
    )
    paper["summary_fields"] = {"summary_text": "Source-grounded paper summary."}
    link = _professor_paper_link_payload(professor, paper, "paper-null-identifiers")
    parsed_rows = _parsed_released_objects(module, (professor, paper, link))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["paper"] == 1
    projection = next(
        item for item in result[4].projections if item.entity_type == "paper"
    )
    assert projection.doi is None
    assert projection.arxiv_id is None
    assert projection.pdf_path is None
    # The only residual gap is the historical core_facts.name drop; explicit
    # null identifiers must not add disallowed or invalid paths.
    gaps_by_record = {gap.signal.evidence_ids[0]: gap for gap in result[6]}
    paper_gap = gaps_by_record[parsed_rows[1].record.record_id]
    assert not {
        "core_facts.doi",
        "core_facts.arxiv_id",
        "core_facts.pdf_path",
    } & set(paper_gap.signal.affected_paths)


def test_public_authority_projects_patent_filing_and_publication_dates() -> None:
    """landing 已有的 filing_date/publication_date 应进入专利投影（s12e 专利审计）。"""
    module = _module()
    patent = _released_object_payload("patent", 60)
    patent["core_facts"].pop("summary_text")
    patent["core_facts"].update(
        {"filing_date": "2023-07-26", "publication_date": "2024-01-09"}
    )
    patent["summary_fields"] = {"summary_text": "Source-grounded patent summary."}
    parsed_rows = _parsed_released_objects(module, (patent,))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["patent"] == 1
    projection = next(
        item for item in result[4].projections if item.entity_type == "patent"
    )
    assert projection.filing_date is not None
    assert projection.filing_date.isoformat() == "2023-07-26"
    assert projection.publication_date is not None
    assert projection.publication_date.isoformat() == "2024-01-09"


def test_public_authority_rejects_patent_with_malformed_filing_date() -> None:
    module = _module()
    patent = _released_object_payload("patent", 61)
    patent["core_facts"].pop("summary_text")
    patent["core_facts"].update({"filing_date": "26/07/2023"})
    patent["summary_fields"] = {"summary_text": "Source-grounded patent summary."}
    parsed_rows = _parsed_released_objects(module, (patent,))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["patent"] == 0
    gaps_by_record = {gap.signal.evidence_ids[0]: gap for gap in result[6]}
    patent_gap = gaps_by_record[parsed_rows[0].record.record_id]
    assert "core_facts.filing_date" in patent_gap.signal.affected_paths


def test_public_authority_keeps_patent_projection_when_dates_null() -> None:
    module = _module()
    patent = _released_object_payload("patent", 62)
    patent["core_facts"].pop("summary_text")
    patent["core_facts"].update({"filing_date": None, "publication_date": None})
    patent["summary_fields"] = {"summary_text": "Source-grounded patent summary."}
    parsed_rows = _parsed_released_objects(module, (patent,))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["patent"] == 1
    projection = next(
        item for item in result[4].projections if item.entity_type == "patent"
    )
    assert projection.filing_date is None
    assert projection.publication_date is None
    # The only residual gap is the historical core_facts.name drop; explicit
    # null dates must not add disallowed or invalid paths.
    gaps_by_record = {gap.signal.evidence_ids[0]: gap for gap in result[6]}
    patent_gap = gaps_by_record[parsed_rows[0].record.record_id]
    assert not {
        "core_facts.filing_date",
        "core_facts.publication_date",
    } & set(patent_gap.signal.affected_paths)


@pytest.mark.parametrize(
    "polluted_name",
    ("师资列表", "教育经历", "师资介绍", "相关教师", "教师名录", "科研成果"),
    ids=(
        "faculty_list",
        "education_history",
        "faculty_intro",
        "related_teachers",
        "teacher_directory",
        "research_outputs",
    ),
)
def test_public_authority_rejects_professor_named_as_generic_section_label(
    polluted_name: str,
) -> None:
    """栏目名抽取污染（s12e 教授审计 6 条记录及同类标签）必须硬拒绝而非放行。"""
    module = _module()
    professor = _released_object_payload("professor", 90)
    professor["display_name"] = polluted_name
    professor["core_facts"].update(
        {"name": polluted_name, "canonical_name_zh": polluted_name}
    )
    parsed_rows = _parsed_released_objects(module, (professor,))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["professor"] == 0
    assert not [
        item for item in result[4].projections if item.entity_type == "professor"
    ]
    gaps_by_record = {gap.signal.evidence_ids[0]: gap for gap in result[6]}
    name_gap = gaps_by_record[parsed_rows[0].record.record_id]
    assert "core_facts.name" in name_gap.signal.affected_paths


def test_public_authority_decodes_reversed_professor_email() -> None:
    """反爬倒置邮箱在选拔期确定性反转解码并带质量信号（s12e 教授审计 41 条）。"""
    module = _module()
    professor = _released_object_payload("professor", 95)
    professor["core_facts"]["email"] = "moc.liamxof@6102gnahz.ieloaix"
    parsed_rows = _parsed_released_objects(module, (professor,))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["professor"] == 1
    projection = next(
        item for item in result[4].projections if item.entity_type == "professor"
    )
    assert projection.email == "xiaolei.zhang2016@foxmail.com"
    gaps_by_record = {gap.signal.evidence_ids[0]: gap for gap in result[6]}
    gap = gaps_by_record[parsed_rows[0].record.record_id]
    assert "decoded_reversed_email" in gap.signal.observed_symptom
    # The decoded address is the identity evidence, not the reversed string.
    source_identity = next(
        item for item in result[0].source_identities if item.entity_type == "professor"
    )
    assert source_identity.normalized_keys["email_key"] == (
        "xiaolei.zhang2016@foxmail.com"
    )


def test_public_authority_flags_undecodable_reversed_professor_email() -> None:
    module = _module()
    professor = _released_object_payload("professor", 96)
    professor["core_facts"]["email"] = "moc.foo@bar!"
    parsed_rows = _parsed_released_objects(module, (professor,))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["professor"] == 1
    projection = next(
        item for item in result[4].projections if item.entity_type == "professor"
    )
    # Unverifiable reversals stay as sourced instead of being guessed.
    assert projection.email == "moc.foo@bar!"
    gaps_by_record = {gap.signal.evidence_ids[0]: gap for gap in result[6]}
    gap = gaps_by_record[parsed_rows[0].record.record_id]
    assert "reversed_email_undecodable" in gap.signal.observed_symptom
    assert "decoded_reversed_email" not in gap.signal.observed_symptom


def test_public_authority_keeps_normal_professor_email_without_signal() -> None:
    module = _module()
    professor = _released_object_payload("professor", 97)
    professor["core_facts"]["email"] = "ding.wenbo@sz.tsinghua.edu.cn"
    parsed_rows = _parsed_released_objects(module, (professor,))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["professor"] == 1
    projection = next(
        item for item in result[4].projections if item.entity_type == "professor"
    )
    assert projection.email == "ding.wenbo@sz.tsinghua.edu.cn"
    assert result[6] == ()


def test_four_domain_mapper_normalizes_restored_source_shapes() -> None:
    module = _module()
    company, professor, paper, patent, link = _restored_shape_payloads()

    result = module._map_public_authority(
        request=_request(module),
        rows=_parsed_released_objects(
            module, (company, professor, paper, patent, link)
        ),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain == {
        "company": 1,
        "paper": 1,
        "patent": 1,
        "professor": 1,
    }
    projections = {item.entity_type: item for item in result[4].projections}
    assert [item.name for item in projections["paper"].authors] == [
        "Wenbo Ding",
        "Example Author",
    ]
    assert projections["paper"].venue.name == "IEEE Robotics and Automation Letters"
    assert [item.name for item in projections["patent"].applicants] == [
        company["core_facts"]["name"]
    ]
    assert projections["patent"].summary_text == "Source-grounded patent summary."
    assert projections["professor"].canonical_name_zh == professor["core_facts"]["name"]
    assert projections["professor"].department.name == "机器人研究院"
    assert [item.name for item in projections["professor"].research_directions] == [
        "机器人控制",
        "智能感知",
    ]
    assert projections["professor"].paper_summary
    assert projections["professor"].patent_summary


def test_mapper_merges_professor_snapshots_and_derives_unique_author_anchor() -> None:
    module = _module()
    older = _released_object_payload("professor", 801)
    current = _released_object_payload("professor", 802)
    for payload, department, updated_at in (
        (older, "数据与信息研究院", "2026-04-17T07:43:03Z"),
        (current, "数据与信息学院", "2026-05-05T05:07:34Z"),
    ):
        payload["display_name"] = "丁文伯"
        payload["core_facts"].update(
            {
                "name": "丁文伯",
                "canonical_name_zh": "丁文伯",
                "institution": "清华大学深圳国际研究生院",
                "department": department,
                "email": "ding.wenbo@sz.tsinghua.edu.cn",
                "homepage": "http://www.sigs.tsinghua.edu.cn/dwb/main.htm",
            }
        )
        payload["last_updated"] = updated_at
        payload["evidence"][0]["fetched_at"] = updated_at

    paper = _released_object_payload("paper", 803)
    paper["display_name"] = "pFedGPA"
    paper["core_facts"].update(
        {
            "title": "pFedGPA",
            "authors": ["Wenbo Ding", "Example Author"],
            "doi": "10.1609/aaai.v39i17.33980",
        }
    )

    result = module._map_public_authority(
        request=_request(module),
        rows=_parsed_released_objects(module, (older, current, paper)),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain == {
        "company": 0,
        "paper": 1,
        "patent": 0,
        "professor": 1,
    }
    assignments = {
        item.source_identity_id: item.canonical_identity_id
        for item in result[1].source_identity_assignments
    }
    assert assignments[f"source-released-object:{older['id']}"] == assignments[
        f"source-released-object:{current['id']}"
    ]
    professor = next(
        item for item in result[4].projections if item.entity_type == "professor"
    )
    assert professor.department.name == "数据与信息学院"
    assert any(
        item.payload["id"].startswith("derived-professor-paper-link:")
        for item in result[5]
    )


def test_mapper_binds_all_fixed_supplements_and_uses_role_record_as_evidence() -> None:
    module = _module()
    company, professor, paper, patent, link = _restored_shape_payloads()
    company["display_name"] = "深圳无界智航科技有限公司"
    company["core_facts"].update(
        {
            "name": "深圳无界智航科技有限公司",
            "normalized_name": "深圳无界智航科技有限公司",
        }
    )
    professor["display_name"] = "丁文伯"
    professor["core_facts"].update(
        {
            "name": "丁文伯",
            "institution": "清华大学深圳国际研究生院",
            "email": "ding.wenbo@sz.tsinghua.edu.cn",
        }
    )
    paper["display_name"] = "pFedGPA"
    paper["core_facts"].update(
        {
            "title": "pFedGPA",
            "doi": "10.1609/aaai.v39i17.33980",
        }
    )
    patent["core_facts"]["patent_number"] = "CN117873146A"
    released_rows = _parsed_released_objects(
        module, (company, professor, paper, patent, link)
    )

    def supplemental(
        *, source_id: str, source_batch_id: str, payload: dict[str, Any], index: int
    ) -> Any:
        basis = released_rows[0]
        artifact_id = f"artifact:fixed-supplement:{index}"
        record = basis.record.model_copy(
            update={
                "record_id": f"fixed-supplement-record:{index}",
                "artifact_id": artifact_id,
                "source_batch_id": source_batch_id,
                "record_locator": f"fixed-supplement:{index}",
                "payload": payload,
            },
            deep=True,
        )
        artifact = basis.artifact.model_copy(
            update={
                "artifact_id": artifact_id,
                "source_kind": "historical_jsonl",
                "source_locator": f"fixed-supplement:{index}",
                "content_sha256": f"{index + 1:064x}",
                "run_id": f"fixed-supplement-run:{index}",
            }
        )
        return module._ParsedReleasedObject(
            source_id=source_id,
            source_batch_id=source_batch_id,
            record=record,
            artifact=artifact,
            payload=payload,
        )

    support_rows = (
        supplemental(
            source_id=next(
                key
                for key, value in module._SUPPLEMENTAL_SOURCE_PURPOSES.items()
                if value == "company_knowledge"
            ),
            source_batch_id="support-company-knowledge",
            payload={"company_name": company["core_facts"]["name"]},
            index=0,
        ),
        supplemental(
            source_id=next(
                key
                for key, value in module._SUPPLEMENTAL_SOURCE_PURPOSES.items()
                if value == "paper_identifier"
            ),
            source_batch_id="support-paper",
            payload={
                "title": paper["core_facts"]["title"],
                "doi": paper["core_facts"]["doi"],
            },
            index=1,
        ),
        supplemental(
            source_id=next(
                key
                for key, value in module._SUPPLEMENTAL_SOURCE_PURPOSES.items()
                if value == "professor_company_role"
            ),
            source_batch_id="support-professor-company-role",
            payload={
                "professor_name": professor["core_facts"]["name"],
                "company_name": company["core_facts"]["name"],
                "role": "发起人",
            },
            index=2,
        ),
        supplemental(
            source_id=next(
                key
                for key, value in module._SUPPLEMENTAL_SOURCE_PURPOSES.items()
                if value == "company_workbook"
            ),
            source_batch_id="support-company-workbook",
            payload={"公司名称": company["core_facts"]["name"]},
            index=3,
        ),
        supplemental(
            source_id=next(
                key
                for key, value in module._SUPPLEMENTAL_SOURCE_PURPOSES.items()
                if value == "patent_identifier"
            ),
            source_batch_id="support-patent",
            payload={"公开（公告）号": patent["core_facts"]["patent_number"]},
            index=4,
        ),
    )
    rows = (*released_rows, *support_rows)
    request = _request(module)

    public = module._map_public_authority(
        request=request,
        rows=rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    source_by_key = {
        source.source_key: source for source in public[1].source_identities
    }
    assert support_rows[0].record.record_id in source_by_key[
        company["id"]
    ].source_record_ids
    assert support_rows[3].record.record_id in source_by_key[
        company["id"]
    ].source_record_ids
    assert support_rows[2].record.record_id in source_by_key[
        professor["id"]
    ].source_record_ids
    assert support_rows[1].record.record_id in source_by_key[
        paper["id"]
    ].source_record_ids
    assert support_rows[4].record.record_id in source_by_key[
        patent["id"]
    ].source_record_ids

    internal = module._internal_candidate_authority(
        request=request,
        domain_request=public[3],
        domain_result=public[4],
        now=NOW,
    )
    relationship_request, _ = module._relationship_authority(
        request=request,
        identity_result=public[1],
        decision_result=public[2],
        domain_result=public[4],
        internal_request=internal[0],
        internal_result=internal[1],
        links=public[5],
        now=NOW,
        source_rows=rows,
    )
    assert any(
        assertion.relationship_type_id == "professor_company_role"
        and assertion.source_record_ref == support_rows[2].record.record_id
        for assertion in relationship_request.typed_relationship_assertions
    )


def test_professor_patent_ids_resolve_only_to_active_candidate_patents() -> None:
    module = _module()
    company, professor, paper, patent, link = _restored_shape_payloads()
    patent_number = patent["core_facts"]["patent_number"]
    professor["core_facts"]["patent_ids"] = [
        patent["id"],
        patent_number,
        "missing-patent-reference",
    ]

    result = module._map_public_authority(
        request=_request(module),
        rows=_parsed_released_objects(
            module, (company, professor, paper, patent, link)
        ),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    patent_projection = next(
        item for item in result[4].projections if item.entity_type == "patent"
    )
    professor_projection = next(
        item for item in result[4].projections if item.entity_type == "professor"
    )
    assert professor_projection.patent_ids == (
        patent_projection.canonical_identity_id,
    )
    reference_gaps = [
        gap
        for gap in result[6]
        if "core_facts.patent_ids[2]" in gap.signal.affected_paths
    ]
    assert len(reference_gaps) == 1
    assert "missing-patent-reference" in reference_gaps[0].signal.observed_symptom


def test_server_owned_subobject_ids_are_unique_across_parent_projections() -> None:
    module = _module()
    company, professor, paper, patent, link = _restored_shape_payloads()
    paper_sibling = _released_object_payload("paper", 71)
    paper_sibling["core_facts"].update(
        {
            "authors": list(paper["core_facts"]["authors"]),
            "venue": paper["core_facts"]["venue"],
            "professor_ids": [professor["id"]],
        }
    )
    paper_sibling["summary_fields"] = dict(paper["summary_fields"])
    patent["core_facts"]["inventors"] = ["Wenbo Ding"]
    patent_sibling = _released_object_payload("patent", 71)
    patent_sibling["core_facts"].pop("summary_text")
    patent_sibling["core_facts"].update(
        {
            "applicants": list(patent["core_facts"]["applicants"]),
            "company_ids": [company["id"]],
            "inventors": list(patent["core_facts"]["inventors"]),
        }
    )
    patent_sibling["summary_fields"] = dict(patent["summary_fields"])
    link_sibling = json.loads(json.dumps(link))
    link_sibling.update(
        {
            "id": "professor-paper-link:four-domain-sibling",
            "display_name": "Four-domain professor-paper sibling link",
        }
    )
    link_sibling["core_facts"]["paper_id"] = paper_sibling["id"]
    rows = _parsed_released_objects(
        module,
        (
            company,
            professor,
            paper,
            paper_sibling,
            patent,
            patent_sibling,
            link,
            link_sibling,
        ),
    )

    def projected_subobjects() -> tuple[tuple[str, str, str], ...]:
        result = module._map_public_authority(
            request=_request(module),
            rows=rows,
            initial_gaps=(),
            decision_adapter=_RecordingDecisionAdapter(),
            now=NOW,
        )[4]
        return tuple(
            sorted(
                (
                    projection.canonical_identity_id,
                    attribute,
                    subobject.subobject_id,
                )
                for projection in result.projections
                for attribute in ("authors", "applicants", "inventors")
                for subobject in getattr(projection, attribute, ())
            )
        )

    first = projected_subobjects()
    second = projected_subobjects()

    assert len(first) == 8
    assert len({subobject_id for _, _, subobject_id in first}) == len(first)
    assert first == second


def test_customer_relationship_authority_projects_three_supported_paths() -> None:
    module = _module()
    payloads = _restored_shape_payloads(professor_company_role=True)
    rows = _parsed_released_objects(module, payloads)
    public = module._map_public_authority(
        request=_request(module),
        rows=rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )
    internal = module._internal_candidate_authority(
        request=_request(module),
        domain_request=public[3],
        domain_result=public[4],
        now=NOW,
    )

    relationship_request, result = module._relationship_authority(
        request=_request(module),
        identity_result=public[1],
        decision_result=public[2],
        domain_result=public[4],
        internal_request=internal[0],
        internal_result=internal[1],
        links=public[5],
        source_rows=rows,
        now=NOW,
    )

    assert Counter(
        item.relationship_type_id for item in result.current_relationships
    ) == {
        "patent_has_applicant": 1,
        "professor_attributed_to_paper": 1,
        "professor_company_role": 1,
    }
    assert relationship_request.internal_reference_projection_result is not None
    internal_result = relationship_request.internal_reference_projection_result
    assert not any(
        (
            internal_result.person_projections,
            internal_result.technology_concept_projections,
            internal_result.technology_route_projections,
        )
    )
    postgres_module = import_module(
        "src.data_agents.canonical_v2.relationship_projection_postgres"
    )
    assert not postgres_module._request_uses_internal_reference(relationship_request)
    professor_company = next(
        item
        for item in result.current_relationships
        if item.relationship_type_id == "professor_company_role"
    )
    assert set(professor_company.role_bindings) == {"founder"}


@pytest.mark.parametrize(
    ("direction", "source_domain", "target_domain"),
    (
        ("professor_to_company", "professor", "company"),
        ("company_to_professor", "company", "professor"),
    ),
)
def test_customer_professor_company_relationship_is_source_bound_and_queryable(
    direction: str,
    source_domain: str,
    target_domain: str,
) -> None:
    module = _module()
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    isolated_read_module = import_module(
        "src.data_agents.canonical_v2.knowledge_read_isolated"
    )
    payloads = _restored_shape_payloads(professor_company_role=True)
    rows = _parsed_released_objects(module, payloads)
    public = module._map_public_authority(
        request=_request(module),
        rows=rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )
    internal = module._internal_candidate_authority(
        request=_request(module),
        domain_request=public[3],
        domain_result=public[4],
        now=NOW,
    )
    relationship_request, relationship_result = module._relationship_authority(
        request=_request(module),
        identity_result=public[1],
        decision_result=public[2],
        domain_result=public[4],
        internal_request=internal[0],
        internal_result=internal[1],
        links=public[5],
        source_rows=rows,
        now=NOW,
    )
    identities = {
        projection.entity_type: projection.canonical_identity_id
        for projection in internal[3].public_domain_projections
    }
    displayed_id = identities[source_domain]
    expected_id = identities[target_domain]
    protected_slot = read_module.ProtectedSlot(
        kind="displayed_entity_set",
        value="displayed_entity_set",
        entity_ids=(displayed_id,),
    )
    lane_request = read_module.LaneRequest(
        lane="relationship",
        release_id=RELEASE_ID,
        query_view="view:original",
        original_query="关系查询",
        behavior_class="D",
        interaction_mode="information_retrieval",
        web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=5,
        ),
        query_text="关系查询",
        domains=(target_domain,),
        protected_slots=(protected_slot,),
        structured_constraints=read_module.StructuredConstraints(
            displayed_entity_ids=(displayed_id,)
        ),
        max_candidates=10,
        relationship_paths=(
            read_module.RelationshipPathProposal(
                relationship_type_id="professor_company_role",
                direction=direction,
                source_type=source_domain,
                target_type=target_domain,
            ),
        ),
        relationship_enumeration_policy=read_module.EnumerationPolicy(
            mode="representative",
            scope="关系查询",
            as_of=NOW,
        ),
    )
    authority = SimpleNamespace(
        relationship_request=relationship_request,
        relationship_result=relationship_result,
        candidate_result=internal[3],
        internal_authority=SimpleNamespace(
            bundle=SimpleNamespace(
                release_id=RELEASE_ID,
                index_target=SimpleNamespace(
                    target_id="index:s12b-test",
                    marker_sha256="a" * 64,
                ),
                manifest=SimpleNamespace(manifest_sha256="b" * 64),
                index_result=SimpleNamespace(content_sha256="c" * 64),
            ),
            publication=SimpleNamespace(
                verification_evidence_ids=("verification:s12b-test",)
            ),
        ),
    )

    candidates = isolated_read_module._source_bound_relationship_candidates(
        request=lane_request,
        authority=authority,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.canonical_id == expected_id
    assert candidate.domain == target_domain
    assert candidate.relationship_state == "accepted"
    assert len(candidate.evidence) == 1
    trace = candidate.evidence[0].local_projection_trace
    assert isinstance(trace, read_module.LocalSourceRelationshipTrace)
    assert trace.displayed_entity_id == displayed_id
    assert trace.candidate_canonical_id == expected_id
    assert trace.query_direction == direction
    assert trace.relationship_type_id == "professor_company_role"
    assert trace.relationship_role_bindings[0][0] == "founder"
    assert read_module._valid_local_projection_candidate(candidate, lane_request)


def test_public_authority_records_every_unknown_payload_path_without_suppressing_allowed_projection() -> (
    None
):
    module = _module()
    company = _released_object_payload("company", 22)
    company["private_top_level"] = "must not disappear"
    company["evidence"][0]["private_evidence_note"] = "must not disappear"
    company["core_facts"].pop("key_personnel")
    paper = _released_object_payload("paper", 22)
    paper["core_facts"]["venue"]["private_venue_code"] = "must not disappear"
    parsed_rows = _parsed_released_objects(module, (company, paper))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    def paths_for(record_id: str) -> set[str]:
        return {
            path
            for gap in result[6]
            if gap.signal.evidence_ids == (record_id,)
            for path in gap.signal.affected_paths
        }

    company_paths = paths_for(parsed_rows[0].record.record_id)
    paper_paths = paths_for(parsed_rows[1].record.record_id)
    assert {"private_top_level", "evidence[0].private_evidence_note"} <= company_paths
    assert "core_facts.venue.private_venue_code" in paper_paths
    assert result[4].counts_by_domain["company"] == 1


def test_public_authority_records_invalid_known_metadata_and_evidence_leaf_paths() -> (
    None
):
    module = _module()
    company = _released_object_payload("company", 23)
    company["quality_status"] = "not-a-quality-status"
    company["evidence"][0].update(
        {
            "source_type": "not-a-source-type",
            "snippet": "",
            "confidence": 2.0,
        }
    )
    parsed_row = _parsed_released_objects(module, (company,))[0]

    result = module._map_public_authority(
        request=_request(module),
        rows=(parsed_row,),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain["company"] == 0
    assert len(result[6]) == 1
    assert {
        "quality_status",
        "evidence[0].source_type",
        "evidence[0].snippet",
        "evidence[0].confidence",
    } <= set(result[6][0].signal.affected_paths)


def test_public_authority_crosswire_gap_keeps_full_payload_and_display_audit() -> None:
    module = _module()
    paper = _released_object_payload("paper", 24)
    paper["private_top_level"] = "must not disappear"
    paper["evidence"][0]["private_evidence_note"] = "must not disappear"
    paper["core_facts"]["venue"]["private_venue_code"] = "must not disappear"
    admitted = _parsed_released_objects(module, (paper,))[0]
    crosswired_payload = json.loads(json.dumps(paper))
    crosswired_payload["id"] = "paper:crosswired-inner"
    crosswired_payload["display_name"] = "Crosswired inner display"
    crosswired = module._ParsedReleasedObject(
        source_id=admitted.source_id,
        source_batch_id=admitted.source_batch_id,
        record=admitted.record,
        artifact=admitted.artifact,
        payload=crosswired_payload,
    )

    result = module._map_public_authority(
        request=_request(module),
        rows=(crosswired,),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain == {
        "company": 0,
        "paper": 0,
        "patent": 0,
        "professor": 0,
    }
    assert len(result[6]) == 1
    assert {
        "id",
        "payload_json.id",
        "display_name",
        "payload_json.display_name",
        "private_top_level",
        "evidence[0].private_evidence_note",
        "core_facts.venue.private_venue_code",
    } <= set(result[6][0].signal.affected_paths)


def test_public_authority_relationship_crosswire_keeps_missing_endpoint_paths() -> None:
    module = _module()
    link = {
        "id": "professor-paper-link:crosswired",
        "object_type": "professor_paper_link",
        "display_name": "Crosswired relationship",
        "core_facts": {
            "professor_id": "   ",
            "private_link_field": "must not disappear",
        },
        "summary_fields": {},
        "evidence": [
            {
                "source_type": "xlsx_import",
                "source_url": "https://evidence.invalid/link/crosswired",
                "fetched_at": "2026-07-21T00:00:00Z",
            }
        ],
        "last_updated": "2026-07-21T00:00:00Z",
        "quality_status": "ready",
    }
    company = _released_object_payload("company", 25)
    company["core_facts"].pop("key_personnel")
    admitted_company, admitted = _parsed_released_objects(module, (company, link))
    crosswired_payload = json.loads(json.dumps(link))
    crosswired_payload["id"] = "professor-paper-link:crosswired-inner"
    crosswired = module._ParsedReleasedObject(
        source_id=admitted.source_id,
        source_batch_id=admitted.source_batch_id,
        record=admitted.record,
        artifact=admitted.artifact,
        payload=crosswired_payload,
    )

    result = module._map_public_authority(
        request=_request(module),
        rows=(admitted_company, crosswired),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert len(result[6]) == 1
    assert {
        "id",
        "payload_json.id",
        "core_facts.private_link_field",
        "core_facts.professor_id",
        "core_facts.paper_id",
    } <= set(result[6][0].signal.affected_paths)


def test_public_authority_records_missing_paper_anchor_as_typed_path_gap() -> None:
    module = _module()
    paper = _released_object_payload("paper", 0)
    paper["core_facts"].pop("name")
    paper["summary_fields"] = {}
    parsed_rows = _parsed_released_objects(module, (paper,))

    result = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain == {
        "company": 0,
        "paper": 0,
        "patent": 0,
        "professor": 0,
    }
    assert len(result[6]) == 1
    assert result[6][0].signal.affected_paths == (
        "offline_candidate_build",
        "discovery.professor_anchor_identity_id",
    )
    assert result[6][0].result.evidence_ids == (parsed_rows[0].record.record_id,)


def test_public_authority_gaps_every_duplicate_object_identity_without_overwrite() -> (
    None
):
    module = _module()
    company = _released_object_payload("company", 0)
    company["core_facts"].pop("key_personnel")
    first = _parsed_released_objects(module, (company,))[0]
    second = module._ParsedReleasedObject(
        source_id=first.source_id,
        source_batch_id="second-admitted-batch",
        record=first.record.model_copy(
            update={
                "record_id": "released-object:second-admitted-batch:company:00000",
                "source_batch_id": "second-admitted-batch",
            },
            deep=True,
        ),
        artifact=first.artifact,
        payload=company,
    )

    result = module._map_public_authority(
        request=_request(module),
        rows=(first, second),
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )

    assert result[4].counts_by_domain == {
        "company": 0,
        "paper": 0,
        "patent": 0,
        "professor": 0,
    }
    assert len(result[6]) == 2
    assert {gap.signal.evidence_ids[0] for gap in result[6]} == {
        first.record.record_id,
        second.record.record_id,
    }
    assert all("identity.object_id" in gap.signal.affected_paths for gap in result[6])


def test_real_boundary_replays_gap_with_the_signal_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    company = _released_object_payload("company", 0)
    parsed = _parsed_released_objects(module, (company,))[0]
    recorded = module._gap(
        release_id=RELEASE_ID,
        run_id=RUN_ID,
        record=parsed.record,
        domain="company",
        reason="field audit fixture",
        affected_paths=("core_facts.key_personnel",),
        now=NOW,
    )
    captured_clocks: list[Any] = []

    class Operations:
        def __init__(self, clock: Any) -> None:
            self.clock = clock

        def record(self, signal: Any) -> Any:
            return module.create_ephemeral_knowledge_gap_feedback(
                clock=self.clock
            ).record(signal)

    def create_operations(**kwargs: Any) -> Operations:
        captured_clocks.append(kwargs["clock"])
        return Operations(kwargs["clock"])

    monkeypatch.setattr(
        module,
        "create_postgres_knowledge_gap_operations",
        create_operations,
    )
    boundary = object.__new__(module._RealBoundary)
    boundary._targets = _target_config(
        module,
        root=tmp_path,
        source_manifest_sha256="f" * 64,
        release_id=RELEASE_ID,
    )
    boundary._gate_root = Path("/accepted/gate")

    assert (
        boundary.persist_gap(
            signal=recorded.signal,
            expected=recorded.result,
        )
        == recorded.result
    )
    assert len(captured_clocks) == 1
    assert captured_clocks[0]() == NOW


def test_zero_relationship_authority_is_omitted_from_release_bundle() -> None:
    module = _module()
    company = _released_object_payload("company", 0)
    company["core_facts"].pop("key_personnel")
    parsed_rows = _parsed_released_objects(module, (company,))
    public = module._map_public_authority(
        request=_request(module),
        rows=parsed_rows,
        initial_gaps=(),
        decision_adapter=_RecordingDecisionAdapter(),
        now=NOW,
    )
    internal = module._internal_candidate_authority(
        request=_request(module),
        domain_request=public[3],
        domain_result=public[4],
        now=NOW,
    )
    relationship_request, relationship_result = module._relationship_authority(
        request=_request(module),
        identity_result=public[1],
        decision_result=public[2],
        domain_result=public[4],
        internal_request=internal[0],
        internal_result=internal[1],
        links=(),
        now=NOW,
    )

    assert module._release_bundle_relationship_authority(
        relationship_request, relationship_result
    ) == (None, None)


def test_consumer_handoff_rejects_cross_release_artifact_graph() -> None:
    module = _module()
    candidate = module.CandidateRelease.model_construct(
        release_id=RELEASE_ID,
        manifest_sha256="a" * 64,
    )
    release_bundle = module.IsolatedReleaseBundle.model_construct(
        manifest=module.BuildManifest.model_construct(
            release_id="different-release",
            manifest_sha256="b" * 64,
        ),
        index_result=module.IndexProjectionResult.model_construct(
            release_id="different-release",
        ),
        index_target=module.IsolatedIndexTarget.model_construct(
            release_id="different-release",
        ),
        relationship_projection_request=None,
        relationship_projection_result=None,
    )
    index_request = module.IndexProjectionRequest.model_construct(
        candidate_projection_request=module.CandidateProjectionRequest.model_construct(
            release_id=RELEASE_ID,
        ),
        candidate_projection_result=module.CandidateProjectionResult.model_construct(
            release_id=RELEASE_ID,
        ),
    )
    handoff = module.CompleteCandidateConsumerHandoff.model_construct(
        schema_version="canonical-v2-complete-candidate-handoff-v1",
        candidate=candidate,
        release_bundle=release_bundle,
        index_projection_request=index_request,
        institution_catalog=module.InstitutionCatalog.model_construct(
            release_id=RELEASE_ID,
        ),
        release_verification=module.ReleaseVerification.model_construct(
            candidate_release_id=RELEASE_ID,
            manifest_sha256="a" * 64,
        ),
        content_sha256="c" * 64,
    )

    assert hasattr(handoff, "validate_artifact_graph"), (
        "handoff requires a cross-model artifact validator"
    )
    with pytest.raises(ValueError, match="release|manifest"):
        handoff.validate_artifact_graph()


def test_complete_envelope_rejects_receipt_handoff_verification_crosswire() -> None:
    module = _module()
    candidate = module.CandidateRelease.model_construct(release_id=RELEASE_ID)
    handoff = module.CompleteCandidateConsumerHandoff.model_construct(
        candidate=candidate,
        release_verification=module.ReleaseVerification.model_construct(
            candidate_release_id=RELEASE_ID,
            manifest_sha256="a" * 64,
            accepted=True,
        ),
        content_sha256="b" * 64,
    )
    receipt = module.CompleteCandidateBuildReceipt.model_construct(
        candidate=candidate,
        consumer_handoff_sha256="b" * 64,
        release_verification=module.ReleaseVerification.model_construct(
            candidate_release_id=RELEASE_ID,
            manifest_sha256="a" * 64,
            accepted=False,
        ),
    )
    envelope = module.CompleteCandidateBuildEnvelope.model_construct(
        receipt=receipt,
        consumer_handoff=handoff,
    )

    with pytest.raises(ValueError, match="verification"):
        envelope.validate_cross_binding()


def test_recorded_adapter_loaders_require_content_addressed_offline_bundles(
    tmp_path: Path,
) -> None:
    module = _module()
    decision_payload: dict[str, Any] = {
        "schema_version": "canonical-v2-recorded-decision-bundle-v1",
        "provider": "recorded-offline",
        "model": "recorded-decision-v1",
        "prompt_version": "canonical-v2-s12a-decision-v1",
        "output_schema_version": "canonical-v2-decision-output-v1",
        "responses": [],
    }
    decision_payload["content_sha256"] = _canonical_hash(decision_payload)
    embedding_payload: dict[str, Any] = {
        "schema_version": "canonical-v2-recorded-embedding-bundle-v1",
        "model_id": "recorded-embedding-v1",
        "dimension": 32,
        "algorithm": "canonical-v2-token-hash-l2-v1",
    }
    embedding_payload["content_sha256"] = _canonical_hash(embedding_payload)
    decision_path = tmp_path / "recorded-decisions.json"
    embedding_path = tmp_path / "recorded-embeddings.json"
    decision_path.write_text(json.dumps(decision_payload), encoding="utf-8")
    embedding_path.write_text(json.dumps(embedding_payload), encoding="utf-8")

    assert hasattr(module, "load_recorded_decision_adapter")
    assert hasattr(module, "load_recorded_embedding_adapter")
    decision = module.load_recorded_decision_adapter(decision_path)
    embedding = module.load_recorded_embedding_adapter(embedding_path)

    assert callable(decision.adjudicate)
    assert decision.authority_sha256 == RECORDED_DECISION_BUNDLE_SHA256
    assert embedding.model_id == "recorded-embedding-v1"
    assert embedding.dimension == 32
    assert embedding.authority_sha256 == RECORDED_EMBEDDING_BUNDLE_SHA256
    assert embedding.embed_batch(("same text",)) == embedding.embed_batch(
        ("same text",)
    )

    tampered = dict(embedding_payload)
    tampered["dimension"] = 64
    tampered.pop("content_sha256")
    tampered["content_sha256"] = _canonical_hash(tampered)
    embedding_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="authority|bundle"):
        module.load_recorded_embedding_adapter(embedding_path)


def test_release_embedding_loader_batches_real_provider_without_persisting_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    payload: dict[str, Any] = {
        "schema_version": "canonical-v2-openai-compatible-embedding-bundle-v1",
        "provider": "openai-compatible",
        "model_id": "Qwen/Qwen3-Embedding-8B",
        "dimension": 4096,
        "base_url": "http://100.64.0.27:18005/v1",
        "api_key_source": "local_api_key",
        "batch_size": 32,
        "max_workers": 32,
        "timeout_seconds": 180,
    }
    payload["content_sha256"] = _canonical_hash(payload)
    path = tmp_path / "release-embeddings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    class _FakeEmbeddingClient:
        def __init__(self, *, base_url: str, api_key: str, timeout: float) -> None:
            assert base_url == payload["base_url"]
            assert api_key == "runtime-secret"
            assert timeout == payload["timeout_seconds"]

        def embed_batch(
            self,
            texts: list[str],
            *,
            model: str,
        ) -> list[list[float]]:
            assert model == payload["model_id"]
            calls.append(tuple(texts))
            return [
                [float(int(text.removeprefix("text-")) + 1)]
                * payload["dimension"]
                for text in texts
            ]

    monkeypatch.setattr(module, "_OpenAIEmbeddingClient", _FakeEmbeddingClient)
    monkeypatch.setattr(module, "load_local_api_key", lambda: "runtime-secret")

    adapter = module.load_content_addressed_embedding_adapter(path)
    texts = tuple(f"text-{index}" for index in range(65))
    vectors = adapter.embed_batch(texts)

    assert payload["content_sha256"] == QWEN_EMBEDDING_BUNDLE_SHA256
    assert adapter.authority_sha256 == QWEN_EMBEDDING_BUNDLE_SHA256
    assert adapter.model_id == "Qwen/Qwen3-Embedding-8B"
    assert adapter.dimension == 4096
    assert sorted(len(call) for call in calls) == [1, 32, 32]
    assert tuple(vector[0] for vector in vectors) == tuple(
        float(i + 1) for i in range(65)
    )
    cached = adapter.embed_batch(("text-0", "text-65", "text-0"))
    assert calls.count(("text-65",)) == 1
    assert len(calls) == 4
    assert cached[0] == vectors[0]
    assert cached[0] == cached[2]
    assert adapter.embed_batch(("text-65", "text-0")) == (cached[1], cached[0])
    assert len(calls) == 4
    assert "runtime-secret" not in path.read_text(encoding="utf-8")

    tampered = dict(payload)
    tampered["max_workers"] = 31
    tampered.pop("content_sha256")
    tampered["content_sha256"] = _canonical_hash(tampered)
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="authority|bundle"):
        module.load_content_addressed_embedding_adapter(path)


def test_isolated_index_point_readback_is_bounded_and_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_module = import_module(
        "src.data_agents.canonical_v2.index_projection_isolated"
    )
    point_ids = tuple(f"point-{index:04d}" for index in range(1_025))

    class _BoundedClient:
        calls: list[tuple[str, ...]] = []

        def has_collection(self, _: str) -> bool:
            return True

        def get(self, *, ids: list[str], **_: Any) -> list[dict[str, str]]:
            values = tuple(ids)
            self.calls.append(values)
            assert len(values) <= 128
            return [{"point_id": point_id} for point_id in values]

    monkeypatch.setattr(
        index_module,
        "_validate_physical_point_rows",
        lambda rows, **_: tuple(row["point_id"] for row in rows),
    )
    client = _BoundedClient()

    result = index_module._read_points_with_client(
        client,
        collection_name="candidate_points",
        point_ids=point_ids,
    )

    assert result == point_ids
    assert len(client.calls) == 9
    assert tuple(point_id for batch in client.calls for point_id in batch) == point_ids


def test_isolated_index_vector_readback_embeds_all_points_in_one_adapter_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_module = import_module(
        "src.data_agents.canonical_v2.index_projection_isolated"
    )
    fake_points = tuple(
        SimpleNamespace(
            point_id=f"point-{index:04d}",
            release_id="candidate-batched-readback",
            projection_id=f"projection-{index:04d}",
            canonical_object_id=f"object-{index:04d}",
            embedded_content_sha256=f"embedded-{index:04d}",
            embedded_content=f"content-{index:04d}",
        )
        for index in range(257)
    )
    points_by_json = {point.point_id: point for point in fake_points}

    class _FakePointModel:
        @staticmethod
        def model_validate_json(value: str) -> Any:
            return points_by_json[value]

    class _BatchEmbeddingAdapter:
        dimension = 2
        calls: list[tuple[str, ...]] = []

        def embed_batch(
            self, texts: tuple[str, ...]
        ) -> tuple[tuple[float, ...], ...]:
            self.calls.append(texts)
            return tuple((float(index), 1.0) for index, _ in enumerate(texts))

    rows = [
        {
            "point_id": point.point_id,
            "release_id": point.release_id,
            "projection_id": point.projection_id,
            "canonical_object_id": point.canonical_object_id,
            "embedded_content_sha256": point.embedded_content_sha256,
            "point_json": point.point_id,
            "vector": [float(index) + (0.001 if index == 0 else 0.0), 1.0],
        }
        for index, point in enumerate(fake_points)
    ]
    monkeypatch.setattr(index_module, "IndexProjectionPoint", _FakePointModel)
    adapter = _BatchEmbeddingAdapter()

    result = index_module._validate_physical_point_rows(
        rows,
        expected_point_ids=tuple(point.point_id for point in fake_points),
        embedding_adapter=adapter,
    )

    assert result == fake_points
    assert adapter.calls == [tuple(point.embedded_content for point in fake_points)]

    rows[0]["vector"] = [0.0, -1.0]
    with pytest.raises(
        index_module.IndexProjectionIntegrityError,
        match="vector differs",
    ):
        index_module._validate_physical_point_rows(
            rows,
            expected_point_ids=tuple(point.point_id for point in fake_points),
            embedding_adapter=adapter,
        )


def test_isolated_index_write_is_bounded_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_module = import_module(
        "src.data_agents.canonical_v2.index_projection_isolated"
    )
    points = tuple(
        SimpleNamespace(
            point_id=f"point-{index:04d}",
            release_id="candidate-batched-write",
            projection_id=f"projection-{index:04d}",
            canonical_object_id=f"object-{index:04d}",
            embedded_content_sha256=f"embedded-{index:04d}",
            embedded_content=f"content-{index:04d}",
            model_dump_json=lambda index=index: f'{{"index":{index}}}',
        )
        for index in range(1_025)
    )

    class _BatchEmbeddingAdapter:
        model_id = "batched-embedding"
        dimension = 2

        def embed_batch(
            self, texts: tuple[str, ...]
        ) -> tuple[tuple[float, ...], ...]:
            assert texts == tuple(point.embedded_content for point in points)
            return tuple((float(index), 1.0) for index, _ in enumerate(texts))

    class _BoundedClient:
        batches: list[list[dict[str, Any]]] = []
        flushed: list[str] = []

        def has_collection(self, _: str) -> bool:
            return False

        def create_collection(self, **_: Any) -> None:
            return None

        def upsert(
            self, *, collection_name: str, data: list[dict[str, Any]]
        ) -> None:
            assert collection_name == "candidate_points"
            assert len(data) <= 128
            self.batches.append(data)

        def flush(self, *, collection_name: str) -> None:
            self.flushed.append(collection_name)

    client = _BoundedClient()
    index_module._write_milvus_projection(
        client,
        collection_name="candidate_points",
        points=points,
        embedding_adapter=_BatchEmbeddingAdapter(),
    )

    assert len(client.batches) == 9
    assert [row["point_id"] for batch in client.batches for row in batch] == [
        point.point_id for point in points
    ]
    assert client.flushed == ["candidate_points"]


_SOURCE_IDS_BY_DISPOSITION: dict[str, tuple[str, ...]] = {
    "requirements_only": (
        "inventory:531d3cb88f7c5605d5c3fe2d8c4e6564106c71cf3d278f23b3eea6daad08d145",
        "inventory:5b0c06ada31be18bfb8ce8704c3e1a7cf04346f243756b451e5d37b414328d2f",
        "inventory:5b17380f2b046730ccda68910ee8dec2af10319093d7b86734780f6a19f4c847",
        "inventory:619924e69182f9fffe9bef24455d50ebee787fabe9fb92b74e413a5e7a46544c",
        "inventory:7bbd1e8e41e98162add1fbb385443061ac91b8a8fd7e0da3fa9a2a6a5dac47ee",
        "inventory:bfd2f9771e12452101507f8e0d10b2243f7f1807e96905ed35c327c430f349b6",
        "inventory:c037008730833b28b5e9fb200a4ed9078d8571382b1250d36795d6ca18456e6b",
    ),
    "acceptance_only": (
        "inventory:03cdece09485247f5a036871021e770a9b3b35c25a515fb0314655589f5d9c44",
        "inventory:43c44a4cb584803b79fcd4760461af7dcd68304ac163d961a83643067e5227d8",
        "inventory:55c969432f588015934396a66874ea6b533d431aa3b521a61f5681c4f2f886a2",
        "inventory:9d70d6f276e39cd177079766739fbce58723ef79435cf502eedd798207f5c720",
        "inventory:c72421b11813abe836836545eb8925076e5e3c09b975a9a11387b7fef6e8bde4",
        "inventory:d26dd2f6d1e9a24699d642b68760c03df65b13e07edc5335868d5923eab43189",
        "inventory:e425f399185195b5e1c187db87869032e000e9c7e17b29353b61bce1b6ce025f",
    ),
    "evidence_input": (RELEASED_OBJECTS_SOURCE_ID,),
    "protection_only": (
        "forensic_recovery_tree",
        "inventory:1a873f91cf59065877e3b21a5b5a046c3c7705b128d9ae8c9db31c23588e439f",
        "inventory:5880891dd3b3c04f1f8e9b29c308dd9be12b233a3165338bf992c17f3aa848a8",
        "inventory:65c4a289550957659155a00799158dd615be14005eb8f35afc778cfa3943accd",
        "original_postgresql_volume",
    ),
    "registered_unprojected": (
        "inventory:11c9847d8bb362984a35e54c25d6f3f01f74b6209245d359e40f7dbd98738829",
        "inventory:1a987406c94c0f1e7b69e0272d8f06582f7f1fe2668f3cfbdd0e48780eed3026",
        "inventory:20be9e411f58e2d8a13f82ff094c5424074ba95bf6668177f64edc2396463d07",
        "inventory:27e2129243e993646d1e976814f26fd42590dd6c02639577c1ce6cdf36329ce7",
        "inventory:2d237edecb0f22c141c270f0c9147e3c5a18824025d155f607bb58ef79acc1bb",
        "inventory:306888219094fdee6713d1d21bf2716d8fd1326efaf5a7a4875c08ce3cbc58f5",
        "inventory:3371136d61fe041eb7e7ba087d9ddc37843330b4d39187b355310ba50599d1d2",
        "inventory:3bf673d8c10db3fc95558037794443a0b8f4a3994d5ae36ac7c85191440f1cd6",
        "inventory:4384044cb138f62be89edc0f9457065d00f08ce44d8dd9d06e0caefc555c3eef",
        "inventory:573305265d755bf3d85fb60e5e3d33e588838f7d71075d663f5f1b6836bf3ff7",
        "inventory:5e1ba9daab456914060f8df8b826a57006cb6ae8486ac816f7b1721186c17c73",
        "inventory:5eed796459843f74ecaebf4f0f8b20fd4570d2a343a442f9ddcbe0f26362d6ab",
        "inventory:603b9b33d7e8f3581d670659002768778ec06914a1f1586a0742619024038083",
        "inventory:6533126e9f7b14a478e8fc098541258d9b075ce70de16288b43dcf9abed59cc1",
        "inventory:6cf786f09478810a09cffe194d96e046a4d3e28a465c4418d8be2a13a126e5f7",
        "inventory:7a323115d06360192111c84e2a4da324146948d18c3189751885f6b95ac6d255",
        "inventory:82e601426705c3ab7ea24b9b9736975fc8f22128e077aa279075e19558309ee3",
        "inventory:8c3084c6d7364e43089903d8bd60c182534aa199eb7c04e6721291ad0b358e99",
        "inventory:909ada3e637a0220acc7d7a6335d3743045762e5c720e6120141c79ae5b0d8f8",
        "inventory:98a87f5fea987e586f33ead0914b848d4acd9e03a3312eaa5a8eb01f7c8765f5",
        "inventory:aa84883ccf6e8034b9ebe6d03fa91d6b265f4abd1f096ceb13d219d38a1a6435",
        "inventory:b2fd4e9bcf4238424785571f65e94161f07f9631a5b589ace749397527ac35ad",
        "inventory:b84a6eac6bc59c9b9431b94ae8735bcda813b3186c28455719ac3bd6718d41ae",
        "inventory:b9a8975b2d147348ef47cbd08ad12c6e550c6012ecc29e2979a4db76e3b3c4a0",
        "inventory:bdb272f5232f7d7bdb9df3e6341f8be4235c57bcc7f11917cb628b216a7367b5",
        "inventory:c2199ac16504af74d0e8a0a00c7e9fea5cf79c65c9de9631ceaa81a3ad0347d2",
        "inventory:d0306b9ab385b64379e437978a971e1d4a8abecee0de0863e0cdb53163b1028d",
        "inventory:dc465266f3a71f9c820cba8cf83f860feb053f6da5bfef79ec02283e9f5ee673",
        "inventory:eb4faa13a8f4c00f703b2fb014ecc5eb671cb29b3dd20e0836afb9b1024bf8a0",
        "inventory:f8fea06321bd45af4c88c9654497a8c504defbf56c5eaee1d758e26248ea2bae",
    ),
    "unrecoverable": (),
}


def _evidence_member(
    *, parent_source_id: str = RELEASED_OBJECTS_SOURCE_ID
) -> dict[str, Any]:
    return {
        "member_id": "accepted-restore:workspace/logs/data_agents/released_objects.db",
        "source_batch_id": SOURCE_BATCH_ID,
        "source_kind": "released_objects_sqlite",
        "content_path": "/accepted/restore/workspace/logs/data_agents/released_objects.db",
        "restore_member_path": RELEASED_OBJECTS_RESTORE_MEMBER_PATH,
        "backup_member_manifest_path": (RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_PATH),
        "backup_member_manifest_sha256": (
            RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_SHA256
        ),
        "source_member_manifest_sha256": (
            RELEASED_OBJECTS_SOURCE_MEMBER_MANIFEST_SHA256
        ),
        "byte_size": 20_267_008,
        "content_sha256": RELEASED_OBJECTS_SHA256,
        "parser": {
            "parser_name": "released_objects_sqlite",
            "parser_version": "canonical-v2-s12a-full-table-v1",
            "schema_version": "released-objects-v1",
            "options": {
                "table": "released_objects",
                "order": "primary_key",
                "limit": None,
            },
        },
        "observed_at": "2026-07-22T12:00:00Z",
        "parent_source_id": parent_source_id,
    }


def _manifest_payload(*, recollection: bool = False) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for disposition, source_ids in _SOURCE_IDS_BY_DISPOSITION.items():
        for source_id in source_ids:
            entries.append(
                {
                    "source_id": source_id,
                    "disposition": disposition,
                    "source_family": "accepted-s2b-source",
                    "members": (
                        [_evidence_member()]
                        if source_id == RELEASED_OBJECTS_SOURCE_ID
                        else []
                    ),
                    "approval_reference": None,
                    "gap_id": None,
                    "rationale": f"S12A exact {disposition} disposition.",
                }
            )
    payload: dict[str, Any] = {
        "schema_version": "canonical-v2-source-build-manifest-v1",
        "source_inventory_sha256": SOURCE_INVENTORY_SHA256,
        "backup_manifest_sha256": BACKUP_MANIFEST_SHA256,
        "restore_verification_sha256": RESTORE_VERIFICATION_SHA256,
        "acceptance_record_sha256": ACCEPTANCE_RECORD_SHA256,
        "released_objects_mapper_policy_version": (
            "canonical-v2-released-objects-mapper-v2"
        ),
        "released_objects_mapper_policy_sha256": (
            RELEASED_OBJECTS_MAPPER_POLICY_SHA256
        ),
        "released_objects_expected_row_counts": (RELEASED_OBJECTS_EXPECTED_ROW_COUNTS),
        "restore_root": "/accepted/restore",
        "approved_recollection_root": (
            "/approved/recollection" if recollection else None
        ),
        "inventory_entries": sorted(entries, key=lambda item: item["source_id"]),
        "targeted_recollection_entries": [],
    }
    if recollection:
        member = _evidence_member(parent_source_id="recollection:quarantined-row")
        member.update(
            {
                "member_id": "approved-recollection:quarantined-row.db",
                "source_batch_id": RECOLLECTION_BATCH_ID,
                "content_path": "/approved/recollection/quarantined-row.db",
                "byte_size": 4096,
                "content_sha256": "d" * 64,
                "restore_member_path": None,
                "backup_member_manifest_path": None,
                "backup_member_manifest_sha256": None,
                "source_member_manifest_sha256": None,
            }
        )
        payload["targeted_recollection_entries"] = [
            {
                "source_id": "recollection:quarantined-row",
                "disposition": "evidence_input",
                "source_family": "approved-targeted-recollection",
                "members": [member],
                "approval_reference": "user-approval:s12a-test-recollection",
                "gap_id": None,
                "rationale": "Approved malformed-row preservation fixture.",
            }
        ]
    payload["content_sha256"] = _canonical_hash(payload)
    return payload


def _rehash_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    changed = json.loads(json.dumps(payload))
    changed.pop("content_sha256", None)
    changed["content_sha256"] = _canonical_hash(changed)
    return changed


def _released_object_payload(domain: str, index: int) -> dict[str, Any]:
    object_id = f"{domain}:{index:05d}"
    display_name = f"{domain.title()} {index:05d}"
    core_facts: dict[str, Any] = {"name": display_name}
    summary_fields: dict[str, Any] = {
        "profile_summary": f"Evidence-bound {domain} {index}."
    }
    if domain == "company":
        core_facts.update(
            {
                "key_personnel": [],
                "normalized_name": display_name.casefold(),
            }
        )
        summary_fields["technology_route_summary"] = "Evidence-bound route summary."
    if domain == "professor":
        core_facts.update(
            {
                "canonical_name_zh": display_name,
                "company_roles": [],
                "department": {
                    "reference_id": "department:s12a",
                    "name": "S12A Department",
                },
                "email": f"professor-{index}@example.edu.cn",
                "homepage": f"https://example.edu.cn/professor/{index}",
                "institution": "SUSTech",
                "paper_summary": "Evidence-bound paper summary.",
                "patent_ids": [],
                "patent_summary": "Evidence-bound patent summary.",
                "research_directions": [],
                "title": "Professor",
            }
        )
    if domain == "paper":
        core_facts.update(
            {
                "authors": [],
                "title": f"Paper {index:05d}",
                "venue": {
                    "reference_id": "venue:s12a-test",
                    "name": "S12A Test Journal",
                },
                "year": 2026,
            }
        )
    if domain == "patent":
        core_facts.update(
            {
                "applicants": [],
                "inventors": [],
                "patent_number": f"CN{index:09d}A",
                "summary_text": "Evidence-bound patent summary.",
                "title": f"Patent {index:05d}",
            }
        )
    return {
        "id": object_id,
        "object_type": domain,
        "display_name": core_facts.get("title", core_facts["name"]),
        "core_facts": core_facts,
        "summary_fields": summary_fields,
        "evidence": [
            {
                "source_type": "xlsx_import",
                "source_url": f"https://evidence.invalid/{domain}/{index}",
                "fetched_at": "2026-07-21T00:00:00Z",
            }
        ],
        "last_updated": "2026-07-21T00:00:00Z",
        "quality_status": "ready",
    }


def _restored_shape_payloads(
    *, professor_company_role: bool = False
) -> tuple[dict[str, Any], ...]:
    company = _released_object_payload("company", 70)
    company["core_facts"].pop("key_personnel")

    professor = _released_object_payload("professor", 70)
    professor["core_facts"].pop("canonical_name_zh")
    professor["core_facts"].pop("paper_summary")
    professor["core_facts"].pop("patent_summary")
    professor["core_facts"].update(
        {
            "company_roles": (
                [
                    {
                        "company_name": company["core_facts"]["name"],
                        "role": "发起人",
                    }
                ]
                if professor_company_role
                else []
            ),
            "department": "机器人研究院",
            "paper_count": 12,
            "research_directions": ["机器人控制", "智能感知"],
        }
    )

    paper = _released_object_payload("paper", 70)
    paper["core_facts"].update(
        {
            "authors": ["Wenbo Ding", "Example Author"],
            "venue": "IEEE Robotics and Automation Letters",
            "professor_ids": [professor["id"]],
        }
    )
    paper["summary_fields"] = {
        "summary_text": "Source-grounded paper summary."
    }

    patent = _released_object_payload("patent", 70)
    patent["core_facts"].pop("summary_text")
    patent["core_facts"].update(
        {
            "applicants": [company["core_facts"]["name"]],
            "company_ids": [company["id"]],
            "inventors": [],
        }
    )
    patent["summary_fields"] = {
        "summary_text": "Source-grounded patent summary."
    }

    link = {
        "id": "professor-paper-link:four-domain",
        "object_type": "professor_paper_link",
        "display_name": "Four-domain professor-paper link",
        "core_facts": {
            "professor_id": professor["id"],
            "paper_id": paper["id"],
        },
        "summary_fields": {},
        "evidence": [
            {
                "source_type": "xlsx_import",
                "source_url": "https://evidence.invalid/link/four-domain",
                "fetched_at": "2026-07-21T00:00:00Z",
            }
        ],
        "last_updated": "2026-07-21T00:00:00Z",
        "quality_status": "ready",
    }
    return company, professor, paper, patent, link


def _professor_paper_link_payload(
    professor: dict[str, Any], paper: dict[str, Any], slug: str
) -> dict[str, Any]:
    return {
        "id": f"professor-paper-link:{slug}",
        "object_type": "professor_paper_link",
        "display_name": f"Professor-paper link {slug}",
        "core_facts": {
            "professor_id": professor["id"],
            "paper_id": paper["id"],
        },
        "summary_fields": {},
        "evidence": [
            {
                "source_type": "xlsx_import",
                "source_url": f"https://evidence.invalid/link/{slug}",
                "fetched_at": "2026-07-21T00:00:00Z",
            }
        ],
        "last_updated": "2026-07-21T00:00:00Z",
        "quality_status": "ready",
    }


def _parsed_released_objects(
    module: Any, payloads: tuple[dict[str, Any], ...]
) -> tuple[Any, ...]:
    member = module.SourceBuildMember.model_validate(_evidence_member())
    parsed: list[Any] = []
    for payload in payloads:
        row = {
            "id": payload["id"],
            "object_type": payload["object_type"],
            "display_name": payload["display_name"],
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        }
        record = module._source_record(
            row=row,
            source_batch_id=SOURCE_BATCH_ID,
            member=member,
            parsed_at=NOW,
        )
        parsed.append(
            module._ParsedReleasedObject(
                source_id=RELEASED_OBJECTS_SOURCE_ID,
                source_batch_id=SOURCE_BATCH_ID,
                record=record,
                artifact=module.EvidenceArtifact(
                    artifact_id=record.artifact_id,
                    source_kind=member.source_kind,
                    source_locator=str(member.content_path),
                    content_sha256=member.content_sha256,
                    byte_size=member.byte_size,
                    acquired_at=NOW,
                    run_id=RUN_ID,
                ),
                payload=payload,
            )
        )
    return tuple(parsed)


def _released_rows(
    *, malformed_recollection: bool = False
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    counts = {"company": 1037, "paper": 574, "patent": 1931, "professor": 1439}
    for domain, count in counts.items():
        for index in range(count):
            payload = _released_object_payload(domain, index)
            if domain == "paper":
                payload["core_facts"].update(
                    {
                        "abstract": "Historical paper abstract.",
                        "authors": [{"name": f"Historical Author {index}"}],
                        "venue": "Historical venue string",
                    }
                )
                payload["summary_fields"] = {
                    "summary_text": "Historical paper summary."
                }
            elif domain == "patent":
                payload["core_facts"].update(
                    {
                        "applicants": [{"name": f"Historical Applicant {index}"}],
                        "inventors": [{"name": f"Historical Inventor {index}"}],
                    }
                )
                payload["core_facts"].pop("summary_text")
                payload["summary_fields"] = {
                    "summary_text": "Historical patent summary."
                }
            elif domain == "professor":
                payload["core_facts"]["research_directions"] = [
                    "historical unmapped direction"
                ]
            rows.append(
                {
                    "id": payload["id"],
                    "object_type": domain,
                    "display_name": payload["display_name"],
                    "payload_json": json.dumps(
                        payload, ensure_ascii=False, sort_keys=True
                    ),
                }
            )
    for index in range(580):
        payload = {
            "id": f"professor-paper-link:{index:05d}",
            "object_type": "professor_paper_link",
            "display_name": f"Professor-paper link {index:05d}",
            "core_facts": {
                "professor_id": f"professor:{index:05d}",
                "paper_id": f"paper:{index % 574:05d}",
                "professor_name": f"Professor {index:05d}",
                "paper_title": f"Paper {index % 574:05d}",
                "link_status": "verified",
                "evidence_source": "accepted restored released_objects",
                "evidence_url": f"https://evidence.invalid/link/{index}",
                "verified_by": "canonical-v2-s12a-fixture",
            },
            "summary_fields": {
                "match_reason": "Explicit accepted professor and paper endpoints."
            },
            "evidence": [
                {
                    "source_type": "xlsx_import",
                    "source_url": f"https://evidence.invalid/link/{index}",
                    "fetched_at": "2026-07-21T00:00:00Z",
                }
            ],
            "last_updated": "2026-07-21T00:00:00Z",
            "quality_status": "ready",
        }
        rows.append(
            {
                "id": payload["id"],
                "object_type": "professor_paper_link",
                "display_name": payload["display_name"],
                "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            }
        )
    assert len(rows) == 5561
    assert Counter(row["object_type"] for row in rows) == {
        "company": 1037,
        "paper": 574,
        "patent": 1931,
        "professor": 1439,
        "professor_paper_link": 580,
    }
    ordered = sorted(rows, key=lambda item: item["id"])
    if malformed_recollection:
        ordered[0] = {
            **ordered[0],
            "display_name": "Readable quarantined row",
            "payload_json": "{malformed-json",
        }
    return tuple(ordered)


@dataclass(frozen=True)
class _StagedMember:
    source_id: str
    member_id: str
    source_batch_id: str
    content_sha256: str
    byte_size: int
    records: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class _AcceptedGateSnapshot:
    source_inventory_sha256: str
    backup_manifest_sha256: str
    restore_verification_sha256: str
    acceptance_record_sha256: str
    accepted_original_milvus_sha256: str


@dataclass(frozen=True)
class _CandidateRegistryReadback:
    candidate: Any
    manifest: Any
    sections: tuple[Any, ...]


@dataclass(frozen=True)
class _PhysicalAuditSnapshot:
    points: tuple[Any, ...]
    lookup_documents: tuple[Any, ...]
    index_projections: tuple[Any, ...]
    lookup_projections: tuple[Any, ...]
    content_sha256: str


def _physical_snapshot_payload(
    *,
    points: tuple[Any, ...],
    lookup_documents: tuple[Any, ...],
    index_projections: tuple[Any, ...],
    lookup_projections: tuple[Any, ...],
) -> dict[str, Any]:
    return {
        "points": [item.model_dump(mode="json") for item in points],
        "lookup_documents": [item.model_dump(mode="json") for item in lookup_documents],
        "index_projections": [
            item.model_dump(mode="json") for item in index_projections
        ],
        "lookup_projections": [
            item.model_dump(mode="json") for item in lookup_projections
        ],
    }


def _typed_copy(value: Any) -> Any:
    return value.__class__.model_validate(value.model_dump(mode="json"))


def _typed_json(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_typed_json(item) for item in value]
    return value.model_dump(mode="json")


@dataclass
class _RecordingDecisionAdapter:
    authority_sha256: str = RECORDED_DECISION_BUNDLE_SHA256
    calls: list[Any] = field(default_factory=list)

    def adjudicate(self, request: Any, /) -> Any:
        self.calls.append(request)
        recorded = getattr(request, "recorded_default", None)
        if recorded is None:
            raise _BoundaryFailure("no recorded decision for ambiguous fixture input")
        return recorded


@dataclass
class _RecordingEmbeddingAdapter:
    model_id: str = "recorded-embedding-v1"
    dimension: int = 32
    authority_sha256: str = RECORDED_EMBEDDING_BUNDLE_SHA256
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.calls.append(texts)
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            for index, value in enumerate(digest):
                vector[index % self.dimension] += float(value + 1)
            norm = math.sqrt(sum(value * value for value in vector))
            vectors.append(tuple(value / norm for value in vector))
        return tuple(vectors)


@dataclass
class _RecordingBoundary:
    """Raw IO/store/index primitives; never constructs a logical success artifact."""

    module: Any
    rows_by_source: dict[str, tuple[dict[str, Any], ...]]
    fail_at: str | None = None
    conflict_store: str | None = None
    drift_physical: bool = False
    drift_registry_readback: bool = False
    staged_source_ids: list[str] = field(default_factory=list)
    landing_records: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    typed_store: dict[tuple[str, str], Any] = field(default_factory=dict)
    persist_attempts: list[tuple[str, str, Any]] = field(default_factory=list)
    replay_readbacks: list[tuple[str, str, Any]] = field(default_factory=list)
    candidate_registry: dict[str, _CandidateRegistryReadback] = field(
        default_factory=dict
    )
    installed_relationship_types: tuple[Any, ...] = ()
    physical_points: tuple[Any, ...] = ()
    physical_documents: tuple[Any, ...] = ()
    physical_index_manifests: tuple[Any, ...] = ()
    physical_lookup_manifests: tuple[Any, ...] = ()
    claimed_index_manifests: tuple[Any, ...] = ()
    claimed_lookup_manifests: tuple[Any, ...] = ()
    last_index_request: Any | None = None
    last_audit: _PhysicalAuditSnapshot | None = None
    external_effects: list[str] = field(default_factory=list)
    store_table_observations: list[tuple[str, str]] = field(default_factory=list)
    active_release: dict[str, str] | None = None
    schema_tables_before: frozenset[str] = frozenset(
        {
            "release",
            "build_manifest",
            "manifest_section",
            "canonical_decision",
            "canonical_identity",
            "domain_projection_run",
            "evidence_artifact",
            "ingest_run",
            "relationship_projection_run",
            "knowledge_gap",
            "source_record",
        }
    )
    observed_schema_tables: set[str] = field(init=False)

    def __post_init__(self) -> None:
        self.observed_schema_tables = set(self.schema_tables_before)

    @property
    def schema_tables_after(self) -> frozenset[str]:
        return frozenset(self.observed_schema_tables)

    def _observe_store_table(self, *, store_name: str, table_name: str) -> None:
        self.store_table_observations.append((store_name, table_name))
        if table_name not in self.schema_tables_before:
            self.observed_schema_tables.add(f"invented_store:{store_name}:{table_name}")
            raise _BoundaryFailure(f"store {store_name} requires an unknown table")

    def resolve_accepted_original_milvus_path(
        self, *, gate_root: Path, expected_sha256: str
    ) -> Path:
        assert gate_root == Path("/accepted/gate")
        assert expected_sha256 == ORIGINAL_MILVUS_SHA256
        return Path("/protected/original/milvus.db")

    def verify_accepted_control_files_safe(self, *, gate_root: Path) -> None:
        assert gate_root == Path("/accepted/gate")

    def resolve_accepted_immutable_paths(
        self, *, gate_root: Path, expected_sha256: str
    ) -> Any:
        assert gate_root == Path("/accepted/gate")
        assert expected_sha256 == ORIGINAL_MILVUS_SHA256
        return self.module._AcceptedImmutablePaths(
            backup_root=Path("/accepted/backup"),
            restore_root=Path("/accepted/restore"),
            evidence_root=Path("/protected/evidence"),
            original_milvus_path=Path("/protected/original/milvus.db"),
        )

    def verify_accepted_gate(self, *, gate_root: Path) -> _AcceptedGateSnapshot:
        assert gate_root == Path("/accepted/gate")
        return _AcceptedGateSnapshot(
            source_inventory_sha256=SOURCE_INVENTORY_SHA256,
            backup_manifest_sha256=BACKUP_MANIFEST_SHA256,
            restore_verification_sha256=RESTORE_VERIFICATION_SHA256,
            acceptance_record_sha256=ACCEPTANCE_RECORD_SHA256,
            accepted_original_milvus_sha256=ORIGINAL_MILVUS_SHA256,
        )

    def validate_fresh_targets(self, *, target_config: Any) -> None:
        roots = {
            target_config.index.root.resolve(strict=False),
            target_config.staging.root.resolve(strict=False),
        }
        if len(roots) != 2:
            raise _BoundaryFailure("index and staging targets are cross-wired")
        if not self.module._prepared_index_root_is_fresh(target_config.index):
            raise _BoundaryFailure("index target is not fresh marker-only state")
        staging = target_config.staging.root
        if staging.is_symlink() or staging.exists():
            raise _BoundaryFailure("staging target is not fresh and non-symlink")

    def prepare_fresh_targets(self, *, target_config: Any) -> None:
        self.validate_fresh_targets(target_config=target_config)

    def stage_verified_member(
        self,
        *,
        entry: Any,
        member: Any,
        destination: Path,
    ) -> _StagedMember:
        del destination
        if entry.disposition.value != "evidence_input":
            raise _BoundaryFailure("non-evidence disposition reached staging")
        records = self.rows_by_source[entry.source_id]
        self.staged_source_ids.append(entry.source_id)
        self.external_effects.append(f"stage:{entry.source_id}")
        return _StagedMember(
            source_id=entry.source_id,
            member_id=member.member_id,
            source_batch_id=member.source_batch_id,
            content_sha256=member.content_sha256,
            byte_size=member.byte_size,
            records=records,
        )

    def land_released_objects(
        self,
        *,
        entry: Any,
        member: Any,
        staged_member: _StagedMember,
        run_id: str,
        observed_at: datetime,
    ) -> Any:
        del entry
        records = tuple(
            self.module._source_record(
                row=row,
                source_batch_id=member.source_batch_id,
                member=member,
                parsed_at=observed_at,
            )
            for row in staged_member.records
        )
        source_batch_id = member.source_batch_id
        for table_name in ("ingest_run", "evidence_artifact", "source_record"):
            self._observe_store_table(store_name="landing", table_name=table_name)
        self.external_effects.append(f"landing:{source_batch_id}")
        retained = tuple(records)
        existing = self.landing_records.get(source_batch_id)
        if existing is not None and existing != retained:
            raise _BoundaryConflict("landing replay content differs")
        self.landing_records[source_batch_id] = retained
        artifact_id = retained[0].artifact_id
        receipt = import_module(
            "src.data_agents.canonical_v2.evidence_landing"
        ).LandingReceipt(
            run_id=run_id,
            source_batch_id=source_batch_id,
            artifact_id=artifact_id,
            content_sha256=member.content_sha256,
            bytes_written=member.byte_size,
            status=(
                "accepted"
                if all(item.parse_status.value == "parsed" for item in retained)
                else "partial"
            ),
            parse_run_id=f"parse:{run_id}",
            record_count=len(retained),
            active_release_id=None,
        )
        artifact = self.module.EvidenceArtifact(
            artifact_id=artifact_id,
            source_kind=member.source_kind,
            source_locator=f"recorded://{member.member_id}",
            content_sha256=member.content_sha256,
            byte_size=member.byte_size,
            acquired_at=observed_at,
            run_id=run_id,
        )
        return self.module._LandingReadback(
            receipt=receipt,
            records=retained,
            artifact=artifact,
        )

    def _persist_exact(
        self,
        *,
        store_name: str,
        content_identity: str,
        value: Any,
    ) -> Any:
        table_by_store = {
            "identity": "canonical_identity",
            "decision": "canonical_decision",
            "domain": "domain_projection_run",
            "relationship": "relationship_projection_run",
            "gap": "knowledge_gap",
        }
        table_name = table_by_store.get(store_name)
        if table_name is None:
            self.observed_schema_tables.add(f"invented_store:{store_name}")
            raise _BoundaryFailure(f"unsupported or invented typed store: {store_name}")
        self._observe_store_table(store_name=store_name, table_name=table_name)
        key = (store_name, content_identity)
        if self.conflict_store == store_name and key not in self.typed_store:
            self.typed_store[key] = _ConflictingStoredValue(
                store_name=store_name,
                content_identity=content_identity,
            )
        self.persist_attempts.append((store_name, content_identity, value))
        existing = self.typed_store.get(key)
        if existing is not None and existing != value:
            raise _BoundaryConflict(f"append-only {store_name} replay differs")
        self.typed_store[key] = value
        readback = self.typed_store[key]
        self.replay_readbacks.append((store_name, content_identity, readback))
        self.external_effects.append(f"store:{store_name}")
        return readback

    def persist_identity_resolution(self, *, request: Any, result: Any) -> Any:
        assert isinstance(request, self.module.IdentityResolutionRequest)
        assert isinstance(result, self.module.IdentityResolutionResult)
        return self._persist_exact(
            store_name="identity",
            content_identity=result.content_sha256,
            value=(request, result),
        )[1]

    def persist_decision_batch(self, *, result: Any) -> Any:
        assert isinstance(result, self.module.DecisionBatchResult)
        return self._persist_exact(
            store_name="decision",
            content_identity=result.content_sha256,
            value=result,
        )

    def persist_domain_projection(self, *, result: Any) -> Any:
        return self._persist_exact(
            store_name="domain",
            content_identity=result.content_sha256,
            value=result,
        )

    def persist_relationship_projection(self, *, request: Any, result: Any) -> Any:
        value = (request, result)
        return self._persist_exact(
            store_name="relationship",
            content_identity=result.content_sha256,
            value=value,
        )[1]

    def persist_gap(self, *, signal: Any, expected: Any) -> Any:
        value = (signal, expected)
        return self._persist_exact(
            store_name="gap",
            content_identity=_canonical_hash(expected.model_dump(mode="json")),
            value=value,
        )[1]

    def persist_candidate_registry_and_identity_policy(
        self,
        *,
        candidate: Any,
        manifest: Any,
        sections: tuple[Any, ...],
        policies: tuple[Any, ...],
        relationship_types: tuple[Any, ...],
    ) -> Any:
        installed = tuple(
            sorted(
                relationship_types,
                key=lambda item: (item.relationship_type_id, item.version),
            )
        )
        if (
            self.installed_relationship_types
            and self.installed_relationship_types != installed
        ):
            raise _BoundaryConflict("relationship type catalog replay differs")
        self.installed_relationship_types = installed
        self.external_effects.append("relationship-types")
        for table_name in ("release", "build_manifest", "manifest_section"):
            self._observe_store_table(
                store_name="candidate_registry",
                table_name=table_name,
            )
        release_id = candidate.release_id
        value = _CandidateRegistryReadback(candidate, manifest, tuple(sections))
        existing = self.candidate_registry.get(release_id)
        if existing is not None and existing != value:
            raise _BoundaryConflict("candidate registry replay differs")
        self.candidate_registry[release_id] = value
        self.external_effects.append("registry")
        return self.module._candidate_registry_snapshot(
            candidate=candidate,
            manifest=manifest,
            sections=sections,
            policies=policies,
        )

    def read_candidate_registry(
        self,
        *,
        release_id: str,
        policies: tuple[Any, ...],
    ) -> Any:
        retained = self.candidate_registry[release_id]
        snapshot = self.module._candidate_registry_snapshot(
            candidate=retained.candidate,
            manifest=retained.manifest,
            sections=retained.sections,
            policies=policies,
        )
        if self.drift_registry_readback:
            return snapshot.model_copy(update={"content_sha256": "b" * 64})
        return snapshot

    def materialize_index(
        self,
        *,
        request: Any,
        points: tuple[Any, ...],
        lookup_documents: tuple[Any, ...],
        expected_index_projections: tuple[Any, ...],
        expected_lookup_projections: tuple[Any, ...],
    ) -> Any:
        if self.fail_at == "physical_index":
            raise _BoundaryFailure("recorded physical index failure")
        index_module = import_module("src.data_agents.canonical_v2.index_projection")
        typed_request = _typed_copy(request)
        self.last_index_request = typed_request
        self.claimed_index_manifests = tuple(expected_index_projections)
        self.claimed_lookup_manifests = tuple(expected_lookup_projections)
        selected_points = points[1:] if self.drift_physical else points
        selected_documents = (
            lookup_documents[1:] if self.drift_physical else lookup_documents
        )
        self.physical_points = tuple(_typed_copy(item) for item in selected_points)
        self.physical_documents = tuple(
            _typed_copy(item) for item in selected_documents
        )
        self.physical_index_manifests = index_module.build_index_projection_manifests(
            request=typed_request,
            points=self.physical_points,
            full_rebuild=typed_request.build_mode == "full",
        )
        self.physical_lookup_manifests = index_module.build_lookup_projection_manifests(
            request=typed_request,
            documents=self.physical_documents,
            full_rebuild=typed_request.build_mode == "full",
        )
        self.external_effects.append("physical-index")
        return self.module.IndexProjectionActualState(
            index_projections=self.physical_index_manifests,
            lookup_projections=self.physical_lookup_manifests,
        )

    def audit_index(self, *, target: Any) -> _PhysicalAuditSnapshot:
        del target
        if self.last_index_request is None:
            raise _BoundaryFailure("physical audit has no materialized request")
        index_module = import_module("src.data_agents.canonical_v2.index_projection")
        audited_request = _typed_copy(self.last_index_request)
        audited_points = tuple(_typed_copy(item) for item in self.physical_points)
        audited_documents = tuple(_typed_copy(item) for item in self.physical_documents)
        audited_index_manifests = index_module.build_index_projection_manifests(
            request=audited_request,
            points=audited_points,
            full_rebuild=audited_request.build_mode == "full",
        )
        audited_lookup_manifests = index_module.build_lookup_projection_manifests(
            request=audited_request,
            documents=audited_documents,
            full_rebuild=audited_request.build_mode == "full",
        )
        payload = _physical_snapshot_payload(
            points=audited_points,
            lookup_documents=audited_documents,
            index_projections=audited_index_manifests,
            lookup_projections=audited_lookup_manifests,
        )
        snapshot = _PhysicalAuditSnapshot(
            points=audited_points,
            lookup_documents=audited_documents,
            index_projections=audited_index_manifests,
            lookup_projections=audited_lookup_manifests,
            content_sha256=_canonical_hash(payload),
        )
        self.external_effects.append("physical-audit")
        self.last_audit = snapshot
        return snapshot

    def read_active_release(self) -> dict[str, str] | None:
        return None if self.active_release is None else dict(self.active_release)


@dataclass
class _AtomicEnvelopeSink:
    module: Any
    destination: Path
    writes: list[Any] = field(default_factory=list)
    phases: list[str] = field(default_factory=list)
    last_readback: Any | None = None

    def validate_fresh(
        self,
        *,
        required_destination: Path,
        protected_paths: tuple[Path, ...],
    ) -> None:
        assert required_destination == Path(
            "/accepted/gate/s12a/complete-candidate-build-envelope.json"
        )
        if self.destination.exists() or self.destination.is_symlink():
            raise _BoundaryFailure("test envelope destination is not fresh")
        if any(
            self.module._paths_overlap(self.destination, path)
            for path in protected_paths
        ):
            raise _BoundaryFailure("test envelope destination overlaps protected path")

    def write_and_readback(self, envelope: Any) -> Any:
        if not isinstance(envelope, self.module.CompleteCandidateBuildEnvelope):
            raise AssertionError("sink accepts only the typed complete envelope")
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        raw = envelope.model_dump_json(indent=2).encode("utf-8") + b"\n"
        temporary = self.destination.with_name(self.destination.name + ".tmp")
        self.phases.append("temp")
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        self.phases.append("fsync")
        os.replace(temporary, self.destination)
        self.phases.append("replace")
        readback = self.module.CompleteCandidateBuildEnvelope.model_validate_json(
            self.destination.read_bytes()
        )
        self.phases.append("same-file-readback")
        self.writes.append(envelope)
        self.last_readback = readback
        return readback


@dataclass
class _ProtectedOpenGuard:
    protected_path: Path
    attempts: list[str] = field(default_factory=list)
    monkeypatch: pytest.MonkeyPatch = field(default_factory=pytest.MonkeyPatch)

    def _matches(self, candidate: object) -> bool:
        if isinstance(candidate, int):
            return False
        try:
            raw = os.fsdecode(os.fspath(candidate))  # type: ignore[arg-type]
        except TypeError:
            return False
        if raw.startswith("file:"):
            raw = raw.removeprefix("file:").split("?", maxsplit=1)[0]
        return os.path.abspath(raw) == os.path.abspath(self.protected_path)

    def _reject(self, operation: str, candidate: object) -> None:
        if not self._matches(candidate):
            return
        self.attempts.append(operation)
        raise AssertionError(f"protected original open attempted through {operation}")

    def install(self) -> None:
        builtins_module = import_module("builtins")
        io_module = import_module("io")
        sqlite_module = import_module("sqlite3")
        original_builtin_open = builtins_module.open
        original_io_open = io_module.open
        original_path_open = Path.open
        original_os_open = os.open
        original_sqlite_connect = sqlite_module.connect

        def guarded_builtin_open(file: object, *args: Any, **kwargs: Any) -> Any:
            self._reject("builtins.open", file)
            return original_builtin_open(file, *args, **kwargs)

        def guarded_io_open(file: object, *args: Any, **kwargs: Any) -> Any:
            self._reject("io.open", file)
            return original_io_open(file, *args, **kwargs)

        def guarded_path_open(path: Path, *args: Any, **kwargs: Any) -> Any:
            self._reject("Path.open", path)
            return original_path_open(path, *args, **kwargs)

        def guarded_os_open(
            path: Any,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            self._reject("os.open", path)
            return original_os_open(path, flags, mode, dir_fd=dir_fd)

        def guarded_sqlite_connect(database: object, *args: Any, **kwargs: Any) -> Any:
            self._reject("sqlite3.connect", database)
            return original_sqlite_connect(database, *args, **kwargs)

        self.monkeypatch.setattr(builtins_module, "open", guarded_builtin_open)
        self.monkeypatch.setattr(io_module, "open", guarded_io_open)
        self.monkeypatch.setattr(Path, "open", guarded_path_open)
        self.monkeypatch.setattr(os, "open", guarded_os_open)
        self.monkeypatch.setattr(sqlite_module, "connect", guarded_sqlite_connect)

    def close(self) -> None:
        self.monkeypatch.undo()


def _target_config(
    module: Any,
    *,
    root: Path,
    source_manifest_sha256: str,
    release_id: str,
    run_id: str = RUN_ID,
    crosswired: bool = False,
    staging_root: Path | None = None,
    index_root: Path | None = None,
    forbidden_milvus_path: Path = Path("/protected/original/milvus.db"),
) -> Any:
    selected_index_root = (index_root or root / "index").resolve(strict=False)
    database_name = f"miroflow_{release_id.replace('-', '_')}"
    selected_staging_root = (
        selected_index_root
        if crosswired
        else (staging_root or root / "staging").resolve(strict=False)
    )
    return module.CompleteCandidateTargetConfig(
        database=module.DestructiveDatabaseTarget(
            url=f"postgresql+psycopg://miroflow@127.0.0.1:5432/{database_name}",
            expected_database=database_name,
            target_kind="disposable",
        ),
        index=module.IsolatedIndexTarget(
            root=selected_index_root,
            target_id=f"index:{release_id}",
            release_id=release_id,
            forbidden_milvus_paths=(forbidden_milvus_path,),
            marker_sha256="a" * 64,
        ),
        staging=module.CandidateStagingTarget(
            root=selected_staging_root,
            marker=module.CandidateStagingMarker(
                schema_version="canonical-v2-candidate-staging-marker-v1",
                run_id=run_id,
                candidate_release_id=release_id,
                source_manifest_sha256=source_manifest_sha256,
            ),
        ),
    )


def _request(
    module: Any,
    *,
    release_id: str = RELEASE_ID,
    run_id: str = RUN_ID,
    source_batch_ids: tuple[str, ...] = (SOURCE_BATCH_ID,),
) -> Any:
    return module.BuildCandidateRequest(
        run_id=run_id,
        candidate_release_id=release_id,
        source_batch_ids=source_batch_ids,
        parser_versions={"released_objects_sqlite": "canonical-v2-s12a-full-table-v1"},
        policy_versions={
            "released_objects_mapper": "canonical-v2-released-objects-mapper-v2",
            "path_eligibility": "path-eligibility-v1",
        },
        model_versions={"embedding": "recorded-embedding-v1"},
    )


def _build_fixture(
    module: Any,
    *,
    root: Path,
    manifest_payload: dict[str, Any],
    boundary: _RecordingBoundary,
    sink: _AtomicEnvelopeSink,
    release_id: str = RELEASE_ID,
    run_id: str = RUN_ID,
    crosswired: bool = False,
    staging_root: Path | None = None,
    index_root: Path | None = None,
    forbidden_milvus_path: Path = Path("/protected/original/milvus.db"),
) -> tuple[Any, _RecordingDecisionAdapter, _RecordingEmbeddingAdapter]:
    manifest_path = root / "source-build-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    decision = _RecordingDecisionAdapter()
    embedding = _RecordingEmbeddingAdapter()
    builder = module.create_isolated_knowledge_build(
        target_config=_target_config(
            module,
            root=root,
            source_manifest_sha256=manifest_payload["content_sha256"],
            release_id=release_id,
            run_id=run_id,
            crosswired=crosswired,
            staging_root=staging_root,
            index_root=index_root,
            forbidden_milvus_path=forbidden_milvus_path,
        ),
        accepted_backup_gate_root=Path("/accepted/gate"),
        source_manifest_path=manifest_path,
        accepted_original_milvus_sha256=ORIGINAL_MILVUS_SHA256,
        accepted_original_milvus_record_sha256=_canonical_hash(
            {
                "record_kind": "accepted-original-milvus-identity",
                "content_sha256": ORIGINAL_MILVUS_SHA256,
            }
        ),
        decision_adapter=decision,
        embedding_adapter=embedding,
        boundary=boundary,
        envelope_sink=sink,
        clock=lambda: NOW,
    )
    assert isinstance(builder, module.KnowledgeBuild)
    return builder, decision, embedding


def _success_fixture(
    module: Any,
    *,
    root: Path,
    release_id: str = RELEASE_ID,
    run_id: str = RUN_ID,
    malformed_recollection: bool = False,
    fail_at: str | None = None,
    conflict_store: str | None = None,
    drift_physical: bool = False,
    drift_registry_readback: bool = False,
) -> tuple[Any, _RecordingBoundary, _AtomicEnvelopeSink, tuple[str, ...]]:
    payload = _manifest_payload()
    rows_by_source = {
        RELEASED_OBJECTS_SOURCE_ID: _released_rows(
            malformed_recollection=malformed_recollection
        )
    }
    batches = (SOURCE_BATCH_ID,)
    boundary = _RecordingBoundary(
        module=module,
        rows_by_source=rows_by_source,
        fail_at=fail_at,
        conflict_store=conflict_store,
        drift_physical=drift_physical,
        drift_registry_readback=drift_registry_readback,
    )
    sink = _AtomicEnvelopeSink(module, root / "complete-candidate-envelope.json")
    builder, _, _ = _build_fixture(
        module,
        root=root,
        manifest_payload=payload,
        boundary=boundary,
        sink=sink,
        release_id=release_id,
        run_id=run_id,
    )
    return builder, boundary, sink, batches


def _assert_hostile_cases_fail_before_effect(
    module: Any,
    cases: tuple[tuple[str, dict[str, Any], bool, bool], ...],
) -> None:
    accepted_rows = _released_rows()
    quarantined_rows = _released_rows(malformed_recollection=True)
    for label, payload, crosswired, symlinked in cases:
        with tempfile.TemporaryDirectory(prefix=f"s12a-{label}-red-") as raw_root:
            root = Path(raw_root)
            staging_override: Path | None = None
            if symlinked:
                real_staging = root / "real-staging"
                real_staging.mkdir()
                staging_override = root / "staging-link"
                staging_override.symlink_to(real_staging, target_is_directory=True)
            boundary = _RecordingBoundary(
                module=module,
                rows_by_source={
                    RELEASED_OBJECTS_SOURCE_ID: accepted_rows,
                    "recollection:quarantined-row": quarantined_rows,
                },
            )
            sink = _AtomicEnvelopeSink(module, root / "envelope.json")
            builder, decision, embedding = _build_fixture(
                module,
                root=root,
                manifest_payload=payload,
                boundary=boundary,
                sink=sink,
                crosswired=crosswired,
                staging_root=staging_override,
            )
            with pytest.raises(
                (
                    module.SourceBuildManifestError,
                    module.IsolatedKnowledgeBuildSafetyError,
                )
            ):
                builder.build(
                    _request(
                        module,
                        source_batch_ids=(SOURCE_BATCH_ID, RECOLLECTION_BATCH_ID),
                    )
                )
            assert boundary.external_effects == []
            assert boundary.staged_source_ids == []
            assert decision.calls == []
            assert embedding.calls == []
            assert sink.writes == []


@_S12A_MISSING_TARGET
@pytest.mark.parametrize(
    ("field_name", "extra_key"),
    (
        ("parser_versions", "unused_parser"),
        ("policy_versions", "unused_policy"),
        ("model_versions", "unused_model"),
    ),
)
def test_preflight_rejects_unadmitted_version_keys_before_effect(
    tmp_path: Path,
    field_name: str,
    extra_key: str,
) -> None:
    module = _module()
    root = tmp_path / field_name
    boundary = _RecordingBoundary(
        module=module,
        rows_by_source={RELEASED_OBJECTS_SOURCE_ID: _released_rows()},
    )
    sink = _AtomicEnvelopeSink(module, root / "envelope.json")
    builder, decision, embedding = _build_fixture(
        module,
        root=root,
        manifest_payload=_manifest_payload(),
        boundary=boundary,
        sink=sink,
    )
    request = _request(module)
    supplied = dict(getattr(request, field_name))
    supplied[extra_key] = "unadmitted-v1"

    with pytest.raises(
        module.SourceBuildManifestError,
        match="versions differ from the exact admitted build authority",
    ):
        builder.build(request.model_copy(update={field_name: supplied}))

    assert boundary.external_effects == []
    assert boundary.staged_source_ids == []
    assert decision.calls == []
    assert embedding.calls == []
    assert sink.writes == []


@_S12A_MISSING_TARGET
def test_source_manifest_accounts_for_every_accepted_source_without_using_requirements_as_facts() -> (
    None
):
    module = _module()
    valid = _manifest_payload()
    manifest = module.SourceBuildManifest.model_validate(valid)
    assert manifest.released_objects_mapper_policy_sha256 == (
        RELEASED_OBJECTS_MAPPER_POLICY_SHA256
    )
    accepted_member = next(
        entry
        for entry in manifest.inventory_entries
        if entry.source_id == RELEASED_OBJECTS_SOURCE_ID
    ).members[0]
    assert accepted_member.restore_member_path == Path(
        RELEASED_OBJECTS_RESTORE_MEMBER_PATH
    )
    assert accepted_member.backup_member_manifest_sha256 == (
        RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_SHA256
    )
    assert accepted_member.source_member_manifest_sha256 == (
        RELEASED_OBJECTS_SOURCE_MEMBER_MANIFEST_SHA256
    )
    counts = Counter(entry["disposition"] for entry in valid["inventory_entries"])
    assert len(valid["inventory_entries"]) == 50
    assert counts == {
        "requirements_only": 7,
        "acceptance_only": 7,
        "evidence_input": 1,
        "protection_only": 5,
        "registered_unprojected": 30,
    }

    missing = json.loads(json.dumps(valid))
    missing["inventory_entries"].pop()
    missing = _rehash_manifest(missing)
    requirements_as_fact = json.loads(json.dumps(valid))
    requirement = next(
        entry
        for entry in requirements_as_fact["inventory_entries"]
        if entry["disposition"] == "requirements_only"
    )
    requirement["members"] = [
        _evidence_member(parent_source_id=requirement["source_id"])
    ]
    requirements_as_fact = _rehash_manifest(requirements_as_fact)

    for index, payload in enumerate((missing, requirements_as_fact)):
        with tempfile.TemporaryDirectory(
            prefix=f"s12a-source-red-{index}-"
        ) as raw_root:
            root = Path(raw_root)
            boundary = _RecordingBoundary(
                module=module,
                rows_by_source={RELEASED_OBJECTS_SOURCE_ID: _released_rows()},
            )
            sink = _AtomicEnvelopeSink(module, root / "envelope.json")
            builder, decision, embedding = _build_fixture(
                module,
                root=root,
                manifest_payload=payload,
                boundary=boundary,
                sink=sink,
            )
            with pytest.raises(module.SourceBuildManifestError):
                builder.build(_request(module))
            assert boundary.external_effects == []
            assert boundary.staged_source_ids == []
            assert decision.calls == []
            assert embedding.calls == []
            assert sink.writes == []


@_S12A_MISSING_TARGET
def test_complete_build_uses_verified_copies_landing_authority_projections_registry_index_and_verify() -> (
    None
):
    module = _module()
    publication_module = import_module(
        "src.data_agents.canonical_v2.release_publication"
    )
    publication_probe = publication_module.create_ephemeral_release_publication(
        candidate_manifests={},
        actual_index_projections={},
        expected_index_points={},
        actual_index_points={},
        active_release_state={
            "canonical_release_id": "accepted-bootstrap",
            "published_projection_release_id": "accepted-bootstrap",
            "index_release_id": "accepted-bootstrap",
        },
        verification_store={},
        discrepancy_store={},
        publication_history=[],
        clock=lambda: NOW,
    )
    publication_class = type(publication_probe)
    real_verify = publication_class.verify
    verify_calls: list[str] = []

    def observed_verify(publication: Any, candidate_release_id: str) -> Any:
        verify_calls.append(candidate_release_id)
        return real_verify(publication, candidate_release_id)

    with tempfile.TemporaryDirectory(prefix="s12a-complete-red-") as raw_root:
        root = Path(raw_root)
        builder, boundary, sink, batches = _success_fixture(module, root=root)
        verify_patch = pytest.MonkeyPatch()
        verify_patch.setattr(publication_class, "verify", observed_verify)
        try:
            candidate = builder.build(_request(module, source_batch_ids=batches))
        finally:
            verify_patch.undo()

        assert isinstance(candidate, module.CandidateRelease)
        assert verify_calls
        assert set(verify_calls) == {RELEASE_ID}
        assert candidate.release_id == RELEASE_ID
        assert candidate.run_id == RUN_ID
        assert candidate.active_release_changed is False
        assert boundary.staged_source_ids == [RELEASED_OBJECTS_SOURCE_ID]
        assert len(boundary.landing_records[SOURCE_BATCH_ID]) == 5561
        assert candidate.object_counts == {
            "company": 1037,
            "paper": 574,
            "patent": 1931,
            "professor": 1439,
        }
        assert candidate.relationship_count == 580
        assert RELEASE_ID in boundary.candidate_registry
        registry = boundary.candidate_registry[RELEASE_ID]
        assert registry.candidate == candidate
        assert registry.manifest.manifest_sha256 == candidate.manifest_sha256
        assert registry.sections
        assert {
            (item.relationship_type_id, item.version)
            for item in boundary.installed_relationship_types
        } >= {
            ("patent_has_applicant", "canonical-v2-relationship-v1"),
            ("professor_attributed_to_paper", "canonical-v2-relationship-v1"),
            ("professor_company_role", "canonical-v2-relationship-v1"),
        }
        assert boundary.external_effects.index("relationship-types") < (
            boundary.external_effects.index("store:decision")
        )

        envelope = sink.last_readback
        assert envelope is not None
        assert isinstance(envelope, module.CompleteCandidateBuildEnvelope)
        handoff = envelope.consumer_handoff
        # 1037 company payloads lost their only gap when core_facts.key_personnel
        # became an allowed (projected) field path; paper/patent/link gaps are
        # unchanged because the fixture lacks the newly allowed fields.
        assert len(envelope.receipt.gap_hashes) == 3085
        assert len(set(envelope.receipt.gap_hashes)) == 3085
        assert (
            envelope.receipt.recorded_decision_bundle_sha256
            == RECORDED_DECISION_BUNDLE_SHA256
        )
        assert (
            envelope.receipt.recorded_embedding_bundle_sha256
            == RECORDED_EMBEDDING_BUNDLE_SHA256
        )
        assert envelope.receipt.recorded_embedding_dimension == 32
        receipt_mutations = {
            "active": lambda value: value.update(
                {"active_release_after_sha256": "1" * 64}
            ),
            "gate": lambda value: value["gate_hashes"].update(
                {"acceptance_record": "2" * 64}
            ),
            "original": lambda value: value.update(
                {"accepted_original_milvus_sha256": "3" * 64}
            ),
            "decision_bundle": lambda value: value.update(
                {"recorded_decision_bundle_sha256": "4" * 64}
            ),
            "embedding_bundle": lambda value: value.update(
                {"recorded_embedding_bundle_sha256": "5" * 64}
            ),
            "embedding_dimension": lambda value: value.update(
                {"recorded_embedding_dimension": 64}
            ),
        }
        for mutate in receipt_mutations.values():
            mutated_receipt = envelope.receipt.model_dump(
                mode="json", exclude={"content_sha256"}
            )
            mutate(mutated_receipt)
            mutated_receipt["content_sha256"] = _canonical_hash(mutated_receipt)
            with pytest.raises(ValueError, match="receipt|authority|gate|active"):
                module.CompleteCandidateBuildReceipt.model_validate(
                    mutated_receipt,
                    context={"external_content_addressed": True},
                )
        crosswired_candidate_handoff = handoff.model_dump(
            mode="python", exclude={"content_sha256"}
        )
        crosswired_candidate_handoff["candidate"] = handoff.candidate.model_copy(
            update={"run_id": "same-release-crosswired-run"}
        )
        with pytest.raises(ValueError, match="candidate|manifest|build"):
            module.CompleteCandidateConsumerHandoff.model_validate(
                crosswired_candidate_handoff
            )
        crosswired_state_handoff = handoff.model_dump(
            mode="python", exclude={"content_sha256"}
        )
        crosswired_state_handoff["candidate"] = handoff.candidate.model_copy(
            update={"state": module.ReleaseState.verified}
        )
        with pytest.raises(ValueError, match="candidate|manifest|build"):
            module.CompleteCandidateConsumerHandoff.model_validate(
                crosswired_state_handoff
            )
        index_request = handoff.index_projection_request
        crosswired_index_request = module.IndexProjectionRequest.model_validate(
            {
                **index_request.model_dump(mode="python"),
                "embedding_model": "same-release-crosswired-embedding-v1",
            }
        )
        crosswired_handoff = handoff.model_dump(
            mode="python", exclude={"content_sha256"}
        )
        crosswired_handoff["index_projection_request"] = crosswired_index_request
        with pytest.raises(ValueError, match="index|cross-wired|replay"):
            module.CompleteCandidateConsumerHandoff.model_validate(crosswired_handoff)
        candidate_result = index_request.candidate_projection_result
        assert {
            item.entity_type for item in candidate_result.public_domain_projections
        } == {"company", "paper", "patent", "professor"}
        assert handoff.release_bundle.relationship_projection_request is not None
        relationship_result = handoff.release_bundle.relationship_projection_result
        assert relationship_result is not None
        assert len(relationship_result.current_relationships) == 580
        assert candidate_result.person_projections == ()
        assert candidate_result.technology_concept_projections == ()
        assert candidate_result.technology_route_projections == ()
        internal_manifests = tuple(
            manifest
            for manifest in candidate_result.published_projections
            if manifest.projection_scope.value == "internal_auxiliary"
        )
        assert {manifest.reference_type for manifest in internal_manifests} == {
            "person",
            "technology_concept",
            "technology_route",
        }
        assert all(manifest.record_count == 0 for manifest in internal_manifests)
        assert boundary.physical_points == handoff.release_bundle.index_result.points
        assert (
            boundary.physical_documents
            == handoff.release_bundle.index_result.lookup_documents
        )
        index_result = handoff.release_bundle.index_result
        assert boundary.physical_points
        assert boundary.physical_documents
        assert len({point.point_id for point in boundary.physical_points}) == len(
            boundary.physical_points
        )
        assert len(
            {document.document_id for document in boundary.physical_documents}
        ) == len(boundary.physical_documents)
        assert boundary.physical_index_manifests == (
            index_result.actual_index_projections
        )
        assert boundary.physical_lookup_manifests == (
            index_result.actual_lookup_projections
        )
        assert boundary.claimed_index_manifests == (
            index_result.expected_index_projections
        )
        assert boundary.claimed_lookup_manifests == (
            index_result.expected_lookup_projections
        )
        assert index_result.expected_index_projections == (
            index_result.actual_index_projections
        )
        assert index_result.expected_lookup_projections == (
            index_result.actual_lookup_projections
        )
        assert sum(
            manifest.point_count for manifest in index_result.actual_index_projections
        ) == len(boundary.physical_points)
        assert sum(
            manifest.document_count
            for manifest in index_result.actual_lookup_projections
        ) == len(boundary.physical_documents)
        assert boundary.external_effects.count("physical-index") == 1
        assert boundary.external_effects.count("physical-audit") == 1
        assert boundary.last_audit is not None
        audited = boundary.last_audit
        assert audited.points == boundary.physical_points
        assert audited.lookup_documents == boundary.physical_documents
        assert audited.points is not boundary.physical_points
        assert audited.lookup_documents is not boundary.physical_documents
        assert audited.points[0] is not boundary.physical_points[0]
        assert audited.lookup_documents[0] is not boundary.physical_documents[0]
        assert audited.index_projections == boundary.physical_index_manifests
        assert audited.lookup_projections == boundary.physical_lookup_manifests
        assert audited.content_sha256 == _canonical_hash(
            _physical_snapshot_payload(
                points=audited.points,
                lookup_documents=audited.lookup_documents,
                index_projections=audited.index_projections,
                lookup_projections=audited.lookup_projections,
            )
        )
        assert envelope.receipt.physical_index_snapshot_sha256 == audited.content_sha256
        internal_index_manifests = tuple(
            manifest
            for manifest in index_result.actual_index_projections
            if manifest.projection_scope.value == "internal_auxiliary"
        )
        internal_lookup_manifests = tuple(
            manifest
            for manifest in index_result.actual_lookup_projections
            if manifest.projection_scope.value == "internal_auxiliary"
        )
        assert len(internal_index_manifests) == 3
        assert len(internal_lookup_manifests) == 3
        assert all(manifest.point_count == 0 for manifest in internal_index_manifests)
        assert all(
            manifest.document_count == 0 for manifest in internal_lookup_manifests
        )
        verification = handoff.release_verification
        assert verification.accepted is True
        assert verification.canonical_index_parity is True
        assert (
            verification.missing_points,
            verification.extra_points,
            verification.stale_points,
            verification.cross_release_points,
        ) == (0, 0, 0, 0)
        assert len(verification.evidence_ids) == 1
        assert verification.evidence_ids[0].startswith("release-parity:sha256:")
        assert boundary.read_active_release() is None

        drift_release_id = "candidate-s12a-test-physical-drift"
        drift_builder, drift_boundary, drift_sink, drift_batches = _success_fixture(
            module,
            root=root / "physical-drift",
            release_id=drift_release_id,
            run_id="s12a-test-build-run-physical-drift",
            drift_physical=True,
        )
        with pytest.raises(
            module.IsolatedKnowledgeBuildError,
            match="index|parity|drift|physical",
        ):
            drift_builder.build(
                _request(
                    module,
                    release_id=drift_release_id,
                    run_id="s12a-test-build-run-physical-drift",
                    source_batch_ids=drift_batches,
                )
            )
        assert drift_boundary.physical_index_manifests != (
            drift_boundary.claimed_index_manifests
        )
        assert drift_boundary.physical_lookup_manifests != (
            drift_boundary.claimed_lookup_manifests
        )
        assert drift_sink.writes == []

        registry_release_id = "candidate-s12a-test-registry-drift"
        registry_builder, _, registry_sink, registry_batches = _success_fixture(
            module,
            root=root / "registry-drift",
            release_id=registry_release_id,
            run_id="s12a-test-build-run-registry-drift",
            drift_registry_readback=True,
        )
        with pytest.raises(
            module.IsolatedKnowledgeBuildError,
            match="registry|durable|readback",
        ):
            registry_builder.build(
                _request(
                    module,
                    release_id=registry_release_id,
                    run_id="s12a-test-build-run-registry-drift",
                    source_batch_ids=registry_batches,
                )
            )
        assert registry_sink.writes == []


@_S12A_MISSING_TARGET
def test_unrecoverable_or_quarantined_input_records_typed_gap_without_placeholder_fact() -> (
    None
):
    module = _module()
    with tempfile.TemporaryDirectory(prefix="s12a-gap-red-") as raw_root:
        root = Path(raw_root)
        builder, boundary, sink, batches = _success_fixture(
            module,
            root=root,
            malformed_recollection=True,
        )
        candidate = builder.build(_request(module, source_batch_ids=batches))

        assert candidate.release_id == RELEASE_ID
        assert len(boundary.landing_records[SOURCE_BATCH_ID]) == 5561
        quarantined = next(
            item
            for item in boundary.landing_records[SOURCE_BATCH_ID]
            if item.parse_status.value == "quarantined"
        )
        quarantined_id = quarantined.payload["id"]
        assert isinstance(quarantined_id, str)
        assert "Readable quarantined row" in repr(quarantined)
        assert quarantined_id in repr(quarantined)
        gap_values = [
            value
            for (store_name, _), value in boundary.typed_store.items()
            if store_name == "gap"
        ]
        assert gap_values
        serialized_gaps = json.dumps(
            [_typed_json(value) for value in gap_values],
            ensure_ascii=False,
            sort_keys=True,
        )
        assert quarantined_id in serialized_gaps
        assert "malformed" in serialized_gaps.casefold()
        success_envelope = sink.last_readback
        assert success_envelope is not None
        success_json = success_envelope.model_dump_json().casefold()
        assert "placeholder" not in success_json
        assert quarantined_id.casefold() not in success_json
        owner_values = [
            value
            for (store_name, _), value in boundary.typed_store.items()
            if store_name in {"identity", "decision", "domain", "relationship"}
        ]
        serialized_owners = json.dumps(
            [_typed_json(value) for value in owner_values],
            ensure_ascii=False,
            sort_keys=True,
        )
        assert quarantined_id not in serialized_owners
        registry = boundary.candidate_registry[RELEASE_ID]
        serialized_registry_sections = json.dumps(
            [section.model_dump(mode="json") for section in registry.sections],
            ensure_ascii=False,
            sort_keys=True,
        )
        assert quarantined_id not in serialized_registry_sections
        assert quarantined_id not in {
            point.canonical_object_id for point in boundary.physical_points
        }


@_S12A_MISSING_TARGET
def test_tampered_unapproved_original_symlink_and_crosswired_targets_fail_before_next_effect() -> (
    None
):
    module = _module()
    base = _manifest_payload()
    cases: list[tuple[str, dict[str, Any], bool, bool]] = []

    tampered = json.loads(json.dumps(base))
    evidence = next(
        entry
        for entry in tampered["inventory_entries"]
        if entry["source_id"] == RELEASED_OBJECTS_SOURCE_ID
    )
    evidence["members"][0]["content_sha256"] = "0" * 64
    cases.append(("tampered", _rehash_manifest(tampered), False, False))

    cases.append(("unapproved", _manifest_payload(recollection=True), False, False))

    original = json.loads(json.dumps(base))
    original_evidence = next(
        entry
        for entry in original["inventory_entries"]
        if entry["source_id"] == RELEASED_OBJECTS_SOURCE_ID
    )
    original_evidence["members"][0]["content_path"] = (
        "/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db"
    )
    cases.append(("original", _rehash_manifest(original), False, False))
    cases.append(("crosswired", base, True, False))
    cases.append(("symlink", base, False, True))

    protected_guard = _ProtectedOpenGuard(PROTECTED_ORIGINAL_MILVUS_PATH)
    protected_guard.install()
    try:
        _assert_hostile_cases_fail_before_effect(module, tuple(cases))
        assert protected_guard.attempts == []
    finally:
        protected_guard.close()


@_S12A_MISSING_TARGET
def test_failed_candidate_is_inspectable_retryable_and_never_changes_active_release() -> (
    None
):
    module = _module()
    with tempfile.TemporaryDirectory(prefix="s12a-failure-red-") as raw_root:
        root = Path(raw_root)
        failed_builder, failed_boundary, failed_sink, batches = _success_fixture(
            module,
            root=root / "failed",
            fail_at="physical_index",
        )
        active_before = failed_boundary.read_active_release()
        with pytest.raises(module.IsolatedKnowledgeBuildError, match="physical index"):
            failed_builder.build(_request(module, source_batch_ids=batches))

        assert RELEASE_ID in failed_boundary.candidate_registry
        failed_candidate = failed_boundary.candidate_registry[RELEASE_ID].candidate
        assert failed_candidate.release_id == RELEASE_ID
        assert failed_sink.writes == []
        assert not failed_sink.destination.exists()
        assert failed_boundary.read_active_release() == active_before
        assert "physical-index" not in failed_boundary.external_effects

        retry_release_id = "candidate-s12a-test-retry"
        retry_run_id = "s12a-test-build-run-retry"
        retry_builder, retry_boundary, retry_sink, retry_batches = _success_fixture(
            module,
            root=root / "retry",
            release_id=retry_release_id,
            run_id=retry_run_id,
        )
        retried = retry_builder.build(
            _request(
                module,
                release_id=retry_release_id,
                run_id=retry_run_id,
                source_batch_ids=retry_batches,
            )
        )
        assert retried.release_id == retry_release_id
        assert retried.run_id == retry_run_id
        retry_envelope = retry_sink.last_readback
        assert retry_envelope is not None
        assert retry_envelope.consumer_handoff.candidate == retried
        assert retry_boundary.read_active_release() == active_before
        assert RELEASE_ID not in retry_boundary.candidate_registry


@_S12A_MISSING_TARGET
def test_store_replay_and_single_envelope_readback_are_exact_and_conflicts_fail() -> (
    None
):
    module = _module()
    with tempfile.TemporaryDirectory(prefix="s12a-envelope-red-") as raw_root:
        root = Path(raw_root)
        builder, boundary, sink, batches = _success_fixture(module, root=root / "ok")
        candidate = builder.build(_request(module, source_batch_ids=batches))

        assert len(sink.writes) == 1
        assert sink.phases == ["temp", "fsync", "replace", "same-file-readback"]
        assert sink.destination.is_file()
        assert not sink.destination.with_name(sink.destination.name + ".tmp").exists()
        envelope = sink.last_readback
        assert envelope is not None
        assert isinstance(envelope, module.CompleteCandidateBuildEnvelope)
        assert (
            module.CompleteCandidateBuildEnvelope.model_validate_json(
                sink.destination.read_bytes()
            )
            == envelope
        )
        receipt = envelope.receipt
        handoff = envelope.consumer_handoff
        assert handoff.content_sha256 == _model_content_hash(handoff)
        assert receipt.content_sha256 == _model_content_hash(receipt)
        assert envelope.content_sha256 == _model_content_hash(envelope)
        assert handoff.candidate == candidate
        assert receipt.candidate == candidate
        assert receipt.consumer_handoff_sha256 == handoff.content_sha256
        assert handoff.release_bundle.release_id == candidate.release_id
        assert handoff.release_verification.candidate_release_id == candidate.release_id

        index_request = handoff.index_projection_request
        internal_result = index_request.candidate_projection_request.internal_reference_projection_result
        path_results = index_request.public_path_eligibility_results
        assert internal_result.content_sha256 == (
            index_request.candidate_projection_result.internal_reference_projection_result_content_sha256
        )
        section_hashes = {
            section.content_sha256
            for section in (
                handoff.release_bundle.manifest.decision_set,
                *handoff.release_bundle.manifest.object_sets,
                handoff.release_bundle.manifest.relationship_set,
                *handoff.release_bundle.manifest.eligibility_sets,
            )
        }
        assert internal_result.content_sha256 in section_hashes
        assert {result.content_sha256 for result in path_results} <= section_hashes
        stored_names = {store_name for store_name, _ in boundary.typed_store}
        assert {"identity", "decision", "domain", "relationship"} <= stored_names
        assert not {"internal_reference", "path_eligibility"} & stored_names
        assert boundary.schema_tables_after == boundary.schema_tables_before
        assert boundary.store_table_observations
        assert not any(
            table.startswith("invented_store:")
            for table in boundary.schema_tables_after
        )
        attempts_by_key: dict[tuple[str, str], list[Any]] = {}
        for store_name, content_identity, value in boundary.persist_attempts:
            attempts_by_key.setdefault((store_name, content_identity), []).append(value)
        replayed_keys = {
            key: values
            for key, values in attempts_by_key.items()
            if key[0] in {"identity", "decision", "domain", "relationship"}
            and len(values) >= 2
        }
        assert replayed_keys
        for key, values in replayed_keys.items():
            assert all(value == values[0] for value in values)
            assert boundary.typed_store[key] == values[0]
            matching_readbacks = [
                value
                for store_name, content_identity, value in boundary.replay_readbacks
                if (store_name, content_identity) == key
            ]
            assert len(matching_readbacks) == len(values)
            assert all(value == values[0] for value in matching_readbacks)

        conflict_release_id = "candidate-s12a-test-conflict"
        conflict_run_id = "s12a-test-build-run-conflict"
        conflict_builder, conflict_boundary, conflict_sink, conflict_batches = (
            _success_fixture(
                module,
                root=root / "conflict",
                release_id=conflict_release_id,
                run_id=conflict_run_id,
                conflict_store="identity",
            )
        )
        with pytest.raises(module.IsolatedKnowledgeBuildError, match="conflict"):
            conflict_builder.build(
                _request(
                    module,
                    release_id=conflict_release_id,
                    run_id=conflict_run_id,
                    source_batch_ids=conflict_batches,
                )
            )
        assert conflict_release_id in conflict_boundary.candidate_registry
        conflict_candidate = conflict_boundary.candidate_registry[
            conflict_release_id
        ].candidate
        assert conflict_candidate.release_id == conflict_release_id
        assert conflict_candidate.run_id == conflict_run_id
        identity_attempts = [
            (content_identity, value)
            for store_name, content_identity, value in conflict_boundary.persist_attempts
            if store_name == "identity"
        ]
        assert len(identity_attempts) == 1
        conflict_identity, attempted_identity_value = identity_attempts[0]
        preexisting = conflict_boundary.typed_store[("identity", conflict_identity)]
        assert isinstance(preexisting, _ConflictingStoredValue)
        assert preexisting != attempted_identity_value
        assert conflict_boundary.read_active_release() is None
        assert "physical-index" not in conflict_boundary.external_effects
        assert conflict_sink.writes == []


def test_patent_applicant_links_seed_from_exact_company_names() -> None:
    module = _module()
    company = _released_object_payload("company", 70)
    patent = _released_object_payload("patent", 71)
    patent["core_facts"].update(
        {
            "applicants": [company["core_facts"]["name"]],
            "company_ids": [],
            "inventors": [],
        }
    )
    rows = _parsed_released_objects(module, (company, patent))

    seeds = module._typed_relationship_seeds(
        source_rows=rows,
        canonical_by_source={
            f"source-released-object:{company['id']}": "company-c-pudu",
            f"source-released-object:{patent['id']}": "patent-c-alpha",
        },
        canonical_domains={
            "company-c-pudu": "company",
            "patent-c-alpha": "patent",
        },
    )

    applicant_seeds = [
        seed for seed in seeds if seed.relationship_type_id == "patent_has_applicant"
    ]
    assert len(applicant_seeds) == 1
    seed = applicant_seeds[0]
    assert seed.target_object_id == company["id"]
    assert seed.target_domain == "company"
    assert seed.role_id == "applicant"
    assert seed.evidence_metadata["source_field"] == "core_facts.applicants[0]"
    assert seed.evidence_metadata["match_kind"] == "exact"


def test_patent_applicant_links_abstain_on_ambiguous_names() -> None:
    module = _module()
    company_a = _released_object_payload("company", 70)
    company_b = _released_object_payload("company", 71)
    company_b["core_facts"]["name"] = company_a["core_facts"]["name"]
    company_b["core_facts"]["normalized_name"] = company_a["core_facts"][
        "normalized_name"
    ]
    patent = _released_object_payload("patent", 72)
    patent["core_facts"].update(
        {
            "applicants": [company_a["core_facts"]["name"]],
            "company_ids": [],
            "inventors": [],
        }
    )
    rows = _parsed_released_objects(module, (company_a, company_b, patent))

    seeds = module._typed_relationship_seeds(
        source_rows=rows,
        canonical_by_source={
            f"source-released-object:{company_a['id']}": "company-c-a",
            f"source-released-object:{company_b['id']}": "company-c-b",
            f"source-released-object:{patent['id']}": "patent-c-beta",
        },
        canonical_domains={
            "company-c-a": "company",
            "company-c-b": "company",
            "patent-c-beta": "patent",
        },
    )

    assert not any(
        seed.relationship_type_id == "patent_has_applicant" for seed in seeds
    )
