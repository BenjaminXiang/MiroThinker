from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from importlib import import_module
import json
import os
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
import psycopg
from psycopg import sql
import pytest
from sqlalchemy.engine import make_url

from src.data_agents.canonical_v2.contracts import (
    CandidateRelease,
    ReleaseState,
    ReleaseVerification,
)
from src.data_agents.canonical_v2.knowledge_gap_feedback import (
    GapEffectVerification,
    GapRemediationRequest,
    GapSignal,
    GapTrigger,
    OfflineRemediationReceipt,
)
from src.data_agents.storage.database_target import set_alembic_database_url


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "canonical_v2_alembic.ini"
SCRIPT_LOCATION = APP_ROOT / "canonical_v2_alembic"
RELEASE_ID = "release:s10o:online"
LINKED_RELEASE_ID = "release:s10o:linked"
RESOLVING_RELEASE_ID = "release:s10o:resolved"
NOW = datetime(2026, 7, 20, 13, 30, tzinfo=UTC)
PROTECTED_TABLES = (
    "knowledge.source_assertion",
    "knowledge.relationship_assertion",
    "knowledge.canonical_decision",
    "knowledge.relationship_decision",
    "knowledge.release",
    "publish.build_manifest",
    "publish.active_release",
)


class _MissingS10OOnlineWriteBoundary(RuntimeError):
    """Exact S10O vertical RED sentinel."""


def _operations_module() -> Any:
    try:
        module = import_module("src.data_agents.canonical_v2.knowledge_gap_postgres")
    except ModuleNotFoundError as exc:
        if exc.name == "src.data_agents.canonical_v2.knowledge_gap_postgres":
            raise _MissingS10OOnlineWriteBoundary(
                "exact S10O durable operations seam is absent"
            ) from exc
        raise
    if not hasattr(module, "create_postgres_knowledge_gap_operations"):
        raise _MissingS10OOnlineWriteBoundary(
            "exact S10O durable operations factory is absent"
        )
    return module


@dataclass(frozen=True, slots=True)
class _Target:
    database_url: str
    expected_database: str
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
        pytest.skip("S10O online vertical requires all explicit target settings")
    return values  # type: ignore[return-value]


def _dsn(database_url: str) -> str:
    return (
        make_url(database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


def _sibling_url(database_url: str, database: str) -> str:
    return (
        make_url(database_url)
        .set(database=database)
        .render_as_string(hide_password=False)
    )


def _drop(connection: Any, database: str, marker: str) -> None:
    row = connection.execute(
        "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname=%s",
        (database,),
    ).fetchone()
    if row is None:
        return
    assert row == (marker,)
    connection.execute(
        sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
    )


@pytest.fixture
def online_target(request: pytest.FixtureRequest) -> Iterator[_Target]:
    database_url, expected_database, target_kind, backup_gate_root = (
        _explicit_environment()
    )
    assert target_kind == "disposable"
    database = (
        f"{expected_database[:38]}_s10ow_"
        f"{hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:8]}"
    )
    marker = f"miroflow:destructive-target:v1:disposable:{database}"
    base_marker = f"miroflow:destructive-target:v1:disposable:{expected_database}"
    with psycopg.connect(_dsn(database_url), autocommit=True) as admin:
        assert admin.execute(
            "SELECT current_database(), shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname=current_database()"
        ).fetchone() == (expected_database, base_marker)
        _drop(admin, database, marker)
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        admin.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(database), sql.Literal(marker)
            )
        )
    target_url = _sibling_url(database_url, database)
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(SCRIPT_LOCATION))
    set_alembic_database_url(config, target_url)
    config.set_main_option("miroflow.expected_database", database)
    config.set_main_option("miroflow.target_kind", "disposable")
    config.set_main_option("miroflow.backup_gate_root", backup_gate_root)
    target = _Target(
        database_url=target_url,
        expected_database=database,
        backup_gate_root=Path(backup_gate_root),
        config=config,
    )
    try:
        command.upgrade(config, "C2_0011")
        _seed_release(target)
        yield target
    finally:
        with psycopg.connect(_dsn(database_url), autocommit=True) as admin:
            _drop(admin, database, marker)


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


def _content_bound(model: type[Any], payload: dict[str, Any]) -> Any:
    normalized = model.model_construct(**payload, content_sha256="0" * 64).model_dump(
        mode="json", exclude={"content_sha256"}
    )
    return model(**payload, content_sha256=_canonical_sha256(normalized))


def _remediation_request(
    gap: Any, *, release_id: str, state: str, ordinal: int
) -> tuple[GapRemediationRequest, datetime]:
    build_run_id = f"build:s10o:offline:{ordinal}"
    source_batch_ids = (f"batch:s10o:offline:{ordinal}",)
    manifest = f"{ordinal + 2:x}" * 64
    started_at = gap.updated_at + timedelta(minutes=10)
    completed_at = started_at + timedelta(minutes=10)
    receipt = _content_bound(
        OfflineRemediationReceipt,
        {
            "receipt_id": f"receipt:s10o:offline:{ordinal}",
            "gap_id": gap.gap_id,
            "remediation_kind": "relationship_repair",
            "execution_mode": "offline",
            "source_release_id": gap.release_id,
            "candidate_release_id": release_id,
            "affected_domains": gap.affected_domains,
            "affected_paths": gap.affected_paths,
            "offline_run_id": f"offline:s10o:{ordinal}",
            "source_batch_ids": source_batch_ids,
            "landing_artifact_ids": (f"artifact:s10o:{ordinal}",),
            "build_run_id": build_run_id,
            "review_state": "accepted",
            "review_evidence_ids": (f"review:s10o:{ordinal}",),
            "started_at": started_at,
            "completed_at": completed_at,
        },
    )
    candidate = CandidateRelease(
        release_id=release_id,
        run_id=build_run_id,
        state=ReleaseState(state),
        source_batch_ids=source_batch_ids,
        parser_versions={"offline-remediation": "parser-v1"},
        policy_versions={"gap-remediation": "gap-remediation-v1"},
        model_versions={},
        manifest_sha256=manifest,
        object_counts={"professor": 1, "paper": 1},
        relationship_count=1,
        active_release_changed=False,
    )
    release_verification = None
    effect_verification = None
    requested_at = completed_at + timedelta(minutes=30)
    if state == "accepted":
        verified_at = completed_at + timedelta(minutes=10)
        release_verification = ReleaseVerification(
            candidate_release_id=release_id,
            manifest_sha256=manifest,
            accepted=True,
            canonical_index_parity=True,
            missing_points=0,
            extra_points=0,
            stale_points=0,
            cross_release_points=0,
            evidence_ids=(f"verification:release:{ordinal}",),
            verified_at=verified_at,
        )
        effect_verification = _content_bound(
            GapEffectVerification,
            {
                "verification_id": f"verification:effect:{ordinal}",
                "gap_id": gap.gap_id,
                "release_id": release_id,
                "affected_domains": gap.affected_domains,
                "affected_paths": gap.affected_paths,
                "query_trace_id": gap.query_trace_id,
                "answer_trace_id": gap.answer_trace_id,
                "benchmark_case_id": gap.benchmark_case_id,
                "scenario_ids": ("scenario:s10o:online",),
                "accepted": True,
                "evidence_ids": (f"verification:effect:{ordinal}",),
                "verified_at": verified_at + timedelta(minutes=10),
            },
        )
    payload = {
        "request_id": f"request:s10o:offline:{ordinal}",
        "gap": gap,
        "remediation_receipt": receipt,
        "candidate_release": candidate,
        "release_verification": release_verification,
        "effect_verification": effect_verification,
        "requested_at": requested_at,
    }
    return (
        _content_bound(GapRemediationRequest, payload),
        requested_at + timedelta(minutes=1),
    )


def _seed_release(target: _Target) -> None:
    with psycopg.connect(_dsn(target.database_url)) as connection:
        for ordinal, (release_id, state) in enumerate(
            (
                (RELEASE_ID, "accepted"),
                (LINKED_RELEASE_ID, "candidate"),
                (RESOLVING_RELEASE_ID, "accepted"),
            ),
            start=1,
        ):
            build_run_id = f"build:s10o:offline:{ordinal}"
            manifest = f"{ordinal + 2:x}" * 64
            batches = [f"batch:s10o:offline:{ordinal}"]
            connection.execute(
                "INSERT INTO knowledge.release "
                "(release_id, build_run_id, state, manifest_sha256, created_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (release_id, build_run_id, state, manifest, NOW),
            )
            connection.execute(
                "INSERT INTO publish.build_manifest "
                "(release_id, manifest_version, build_run_id, source_batch_ids, "
                "source_batches_sha256, parser_versions, policy_versions, model_versions, "
                "manifest_sha256, created_at) VALUES "
                "(%s, 'canonical-v2-build-manifest-v2', %s, %s::jsonb, %s, "
                "%s::jsonb, %s::jsonb, '{}'::jsonb, %s, %s)",
                (
                    release_id,
                    build_run_id,
                    json.dumps(batches),
                    _canonical_sha256({"source_batch_ids": batches}),
                    json.dumps({"offline-remediation": "parser-v1"}),
                    json.dumps({"gap-remediation": "gap-remediation-v1"}),
                    manifest,
                    NOW,
                ),
            )
            for section_id, section_kind, count in (
                ("objects:professor", "object_set", 1),
                ("objects:paper", "object_set", 1),
                ("relationships", "relationship_set", 1),
            ):
                connection.execute(
                    "INSERT INTO publish.manifest_section "
                    "(release_id, section_id, section_kind, version, record_count, "
                    "content_sha256) VALUES (%s, %s, %s, 's10o-v1', %s, %s)",
                    (
                        release_id,
                        section_id,
                        section_kind,
                        count,
                        _canonical_sha256(
                            {"release_id": release_id, "section_id": section_id}
                        ),
                    ),
                )
        connection.commit()


def _snapshot_tables(target: _Target) -> dict[str, tuple[str, ...]]:
    snapshots: dict[str, tuple[str, ...]] = {}
    with psycopg.connect(_dsn(target.database_url)) as connection:
        for table in PROTECTED_TABLES:
            rows = connection.execute(
                sql.SQL("SELECT to_jsonb(row_value)::text FROM {} AS row_value").format(
                    sql.SQL(table)
                )
            ).fetchall()
            snapshots[table] = tuple(sorted(row[0] for row in rows))
    return snapshots


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _RecordedIndexAdapter:
    def __init__(self, read_module: Any) -> None:
        self._read_module = read_module
        self.query_calls: list[str] = []
        self.mutation_calls: list[Any] = []
        self.state = {
            "release_id": RELEASE_ID,
            "projection_ids": ("company:exact",),
            "point_content_sha256": _canonical_sha256([]),
        }

    def search(self, request: Any) -> Any:
        self.query_calls.append(request.lane)
        return self._read_module.RetrievalLaneResult()


class _RecordedWebAdapter:
    def __init__(self, read_module: Any, item: Any) -> None:
        self._read_module = read_module
        self._item = item
        self.calls: list[str] = []

    def search(self, request: Any) -> Any:
        self.calls.append(request.lane)
        return self._read_module.RetrievalLaneResult(items=(self._item,))


def test_accepted_read_answer_to_durable_gap_changes_only_ops_rows(
    online_target: _Target,
) -> None:
    operations_module = _operations_module()
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    answer_module = import_module("src.data_agents.canonical_v2.knowledge_answer")
    original_milvus = Path("/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db")
    milvus_before = _file_sha256(original_milvus)
    protected_before = _snapshot_tables(online_target)

    snapshot_payload = b"Recorded bounded S10O current-Web evidence"
    snapshot_hash = hashlib.sha256(snapshot_payload).hexdigest()
    web_item = read_module.EvidenceItem(
        evidence_id="evidence:s10o:online-web",
        object_id="company:s10o:online",
        domain="company",
        lane="web",
        source_nature="current_web",
        source_authority="other",
        source_locator="https://current.example/s10o/online",
        snippet="A bounded current source reports an operational fact.",
        score=1.0,
        observed_at=NOW,
        claim_binding=read_module.EvidenceClaimBinding(
            subject_id="company:s10o:online",
            predicate="operational_stage",
            value="reported",
            status="reported",
        ),
        web_snapshot=read_module.WebEvidenceSnapshot(
            snapshot_id=f"web-snapshot:s10o:sha256:{snapshot_hash}",
            content_sha256=snapshot_hash,
            retrieved_at=NOW,
            byte_length=len(snapshot_payload),
        ),
    )
    index = _RecordedIndexAdapter(read_module)
    index_state_before = _canonical_sha256(index.state)
    web = _RecordedWebAdapter(read_module, web_item)
    plan = read_module.RetrievalPlan(
        plan_version="retrieval-plan-v1",
        original_query="核实当前线上信息并标记本地证据缺口",
        behavior_class="A",
        interaction_mode="information_retrieval",
        release_id=RELEASE_ID,
        domains=("company",),
        protected_slots=(),
        lanes=("exact", "web"),
        max_candidates=10,
        web_required=True,
        web_policy=read_module.WebSearchPolicy(
            mode="universal", max_provider_calls=1, timeout_ms=1500, max_results=3
        ),
        freshness_material=True,
    )
    evidence_set = read_module.create_ephemeral_knowledge_read(
        universal_web_policy=plan.web_policy,
        local_search=index.search,
        web_search=web.search,
        clock=lambda: NOW,
    ).execute(plan)
    turn_request = answer_module.TurnRequest(
        session_id="session:s10o:online",
        turn_id="turn:s10o:online",
        query=evidence_set.original_query,
        release_id=evidence_set.release_id,
        evidence_set=evidence_set,
    )
    claim = answer_module.MaterialClaimProposal(
        claim_id="claim:s10o:online",
        text="A bounded current source reports an operational fact.",
        subject_id="company:s10o:online",
        predicate="operational_stage",
        value="reported",
        subject_handle_ids=("company:s10o:online",),
        evidence_ids=(web_item.evidence_id,),
        status="reported",
    )

    def answer_selector(request: Any) -> Any:
        return answer_module.AnswerSelectionProposal(
            selection_input_sha256=request.content_sha256,
            schema_version="answer-selection-v1",
            decision_id="answer-selection:s10o:online",
            model_id="recorded-s10o-selector",
            prompt_version="recorded-s10o-v1",
            decision_run_id="answer-selection-run:s10o:online",
            answer_text="NON_AUTHORITATIVE_DRAFT",
            claims=(claim,),
        )

    turn_result = answer_module.create_ephemeral_knowledge_answer(
        answer_selector=answer_selector
    ).answer(turn_request)
    evidence_hash = _canonical_sha256(evidence_set.model_dump(mode="json"))
    answer_hash = _canonical_sha256(turn_result.model_dump(mode="json"))
    online_operations = operations_module.create_postgres_knowledge_gap_operations(
        database_url=online_target.database_url,
        expected_database=online_target.expected_database,
        target_kind="disposable",
        backup_gate_root=online_target.backup_gate_root,
        clock=lambda: NOW,
    )
    gap = online_operations.record(
        GapSignal(
            signal_id="signal:s10o:online-web-gap",
            trigger=GapTrigger.insufficient_evidence,
            release_id=evidence_set.release_id,
            affected_domains=tuple(
                sorted({item.domain for item in evidence_set.items})
            ),
            affected_paths=tuple(
                sorted({f"{item.domain}:{item.lane}" for item in evidence_set.items})
            ),
            query_trace_id=f"evidence-set:sha256:{evidence_hash}",
            answer_trace_id=f"turn-result:sha256:{answer_hash}",
            benchmark_case_id=None,
            telemetry_key=None,
            observed_symptom="Current-Web evidence is not durable canonical evidence.",
            evidence_ids=tuple(item.evidence_id for item in evidence_set.items),
            demand_observation_ids=("demand:s10o:online",),
            observed_at=NOW,
        )
    )

    assert gap.release_id == evidence_set.release_id == turn_result.release_id
    assert gap.query_trace_id == f"evidence-set:sha256:{evidence_hash}"
    assert gap.answer_trace_id == f"turn-result:sha256:{answer_hash}"
    assert protected_before == _snapshot_tables(online_target)
    with psycopg.connect(_dsn(online_target.database_url)) as connection:
        assert connection.execute(
            "SELECT count(*) FROM ops.knowledge_gap"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM ops.gap_remediation_transition"
        ).fetchone() == (0,)
    assert index.query_calls == ["exact"]
    assert index.mutation_calls == []
    assert _canonical_sha256(index.state) == index_state_before
    assert web.calls == ["web"]
    assert _file_sha256(original_milvus) == milvus_before

    linked_request, linked_clock = _remediation_request(
        gap, release_id=LINKED_RELEASE_ID, state="candidate", ordinal=2
    )
    linked = operations_module.create_postgres_knowledge_gap_operations(
        database_url=online_target.database_url,
        expected_database=online_target.expected_database,
        target_kind="disposable",
        backup_gate_root=online_target.backup_gate_root,
        clock=lambda: linked_clock,
    ).apply_remediation(linked_request)
    assert linked.transition_state == "linked"
    assert linked.gap.status.value == "planned"
    assert protected_before == _snapshot_tables(online_target)

    resolved_request, resolved_clock = _remediation_request(
        linked.gap,
        release_id=RESOLVING_RELEASE_ID,
        state="accepted",
        ordinal=3,
    )
    resolved_operations = operations_module.create_postgres_knowledge_gap_operations(
        database_url=online_target.database_url,
        expected_database=online_target.expected_database,
        target_kind="disposable",
        backup_gate_root=online_target.backup_gate_root,
        clock=lambda: resolved_clock,
    )
    resolved = resolved_operations.apply_remediation(resolved_request)
    assert resolved.transition_state == "resolved"
    assert resolved.gap.resolved_release_id == RESOLVING_RELEASE_ID
    detail = resolved_operations.get_for_admin(gap.gap_id)
    assert detail is not None
    assert detail.transitions == (linked, resolved)
    assert protected_before == _snapshot_tables(online_target)
    with psycopg.connect(_dsn(online_target.database_url)) as connection:
        assert connection.execute(
            "SELECT count(*) FROM ops.knowledge_gap"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM ops.gap_remediation_transition"
        ).fetchone() == (2,)
    assert _canonical_sha256(index.state) == index_state_before
    assert index.mutation_calls == []
    assert _file_sha256(original_milvus) == milvus_before
