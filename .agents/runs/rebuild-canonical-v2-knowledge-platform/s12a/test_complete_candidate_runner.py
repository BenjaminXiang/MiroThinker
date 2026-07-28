"""Executable S12A owner for the complete-candidate command adapter."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


TARGET_PATH = Path(__file__).with_name("complete_candidate_runner.py")
RELEASE_ID = "candidate-s12a-runner"
RUN_ID = "s12a-runner-build"
SECRET = "runner-database-password"
SHA256_A = "a" * 64
SHA256_B = "b" * 64
SHA256_C = "c" * 64


class _MissingCompleteCandidateRunner(AssertionError):
    """Exact import-first RED sentinel for the S12A runner."""


def _runner() -> ModuleType:
    if not TARGET_PATH.is_file():
        raise _MissingCompleteCandidateRunner(
            f"exact target module is absent: {TARGET_PATH}"
        )
    spec = importlib.util.spec_from_file_location(
        "s12a_complete_candidate_runner", TARGET_PATH
    )
    if spec is None or spec.loader is None:
        raise _MissingCompleteCandidateRunner(
            f"exact target module cannot be loaded: {TARGET_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_S12A_MISSING_TARGET = pytest.mark.xfail(
    not TARGET_PATH.is_file(),
    strict=True,
    raises=_MissingCompleteCandidateRunner,
    reason="S12A RED: complete candidate runner is absent",
)


@dataclass(frozen=True)
class _Candidate:
    release_id: str = RELEASE_ID


@dataclass(frozen=True)
class _Handoff:
    candidate: Any
    release_bundle: Any
    index_projection_request: Any
    institution_catalog: Any
    release_verification: Any
    content_sha256: str = SHA256_B


@dataclass(frozen=True)
class _Receipt:
    candidate: Any
    consumer_handoff_sha256: str = SHA256_B
    source_manifest_sha256: str = SHA256_A
    accepted_original_milvus_sha256: str = SHA256_C
    accepted_original_milvus_record_sha256: str = SHA256_A
    content_sha256: str = SHA256_A


@dataclass(frozen=True)
class _Verification:
    evidence_ids: tuple[str, ...] = ("verification:s12a-runner",)


@dataclass(frozen=True)
class _Envelope:
    receipt: Any
    consumer_handoff: Any
    content_sha256: str = SHA256_C


class _Builder:
    def __init__(self, *, candidate: Any, events: list[Any]) -> None:
        self.candidate = candidate
        self.events = events

    def build(self, request: Any) -> Any:
        self.events.append(("build", request))
        return self.candidate


def _artifacts() -> tuple[Any, Any]:
    candidate = _Candidate()
    handoff = _Handoff(
        candidate=candidate,
        release_bundle=object(),
        index_projection_request=object(),
        institution_catalog=object(),
        release_verification=_Verification(),
    )
    return candidate, _Envelope(
        receipt=_Receipt(candidate=candidate),
        consumer_handoff=handoff,
    )


def _arguments(root: Path, *, serve: bool = False) -> list[str]:
    (root / "accepted-gate" / "s12a").mkdir(parents=True, exist_ok=True)
    values = [
        "--database-url",
        f"postgresql+psycopg://runner:{SECRET}@127.0.0.1:5432/miroflow_candidate_s12a_runner",
        "--expected-database",
        "miroflow_candidate_s12a_runner",
        "--database-target-kind",
        "disposable",
        "--accepted-backup-gate-root",
        str(root / "accepted-gate"),
        "--source-manifest",
        str(root / "source-manifest.json"),
        "--source-manifest-sha256",
        SHA256_A,
        "--candidate-staging-root",
        str(root / "staging"),
        "--index-root",
        str(root / "index"),
        "--index-marker-sha256",
        SHA256_B,
        "--candidate-release-id",
        RELEASE_ID,
        "--run-id",
        RUN_ID,
        "--source-batch-id",
        "s12a-released-objects-full-v1",
        "--parser-version",
        "released_objects_sqlite=canonical-v2-s12a-full-table-v1",
        "--policy-version",
        "released_objects_mapper=canonical-v2-released-objects-mapper-v2",
        "--policy-version",
        "path_eligibility=path-eligibility-v1",
        "--model-version",
        "embedding=recorded-embedding-v1",
        "--recorded-decision-bundle",
        str(root / "recorded-decisions.json"),
        "--recorded-embedding-bundle",
        str(root / "recorded-embeddings.json"),
        "--envelope-output",
        str(root / "accepted-gate" / "s12a" / "complete-candidate-build-envelope.json"),
        "--accepted-original-milvus-path",
        str(root / "protected-original" / "milvus.db"),
        "--accepted-original-milvus-sha256",
        SHA256_C,
        "--accepted-original-milvus-record-sha256",
        SHA256_A,
    ]
    if serve:
        values.extend(
            [
                "--recorded-serving-bundle",
                str(root / "recorded-serving.json"),
                "--recorded-serving-bundle-sha256",
                SHA256_A,
                "--serve",
                "--host",
                "0.0.0.0",
                "--port",
                "18188",
            ]
        )
    return values


def _dependencies(
    module: ModuleType,
    *,
    envelope: Any,
    candidate: Any,
    events: list[Any],
) -> Any:
    builder = _Builder(candidate=candidate, events=events)

    def create_builder(config: Any) -> Any:
        events.append(("create_builder", config))
        return builder

    def read_envelope(path: Path) -> Any:
        events.append(("read_envelope", path))
        return envelope

    def validate_envelope(value: Any) -> Any:
        events.append(("validate_envelope", value))
        return value

    return module.RunnerDependencies(
        create_builder=create_builder,
        read_envelope=read_envelope,
        validate_envelope=validate_envelope,
    )


@pytest.mark.parametrize("hazard", ("preexisting", "protected_child"))
def test_runner_rejects_unsafe_envelope_before_builder_call(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    hazard: str,
) -> None:
    module = _runner()
    candidate, envelope = _artifacts()
    events: list[Any] = []
    dependencies = _dependencies(
        module,
        envelope=envelope,
        candidate=candidate,
        events=events,
    )
    arguments = _arguments(tmp_path)
    output_index = arguments.index("--envelope-output") + 1
    if hazard == "preexisting":
        Path(arguments[output_index]).write_text(
            "independent owner\n", encoding="utf-8"
        )
    else:
        protected_parent = tmp_path / "accepted-gate" / "s2"
        protected_parent.mkdir(parents=True)
        arguments[output_index] = str(
            protected_parent / "complete-candidate-build-envelope.json"
        )

    assert module.main(arguments, dependencies=dependencies) == 2
    assert events == []
    output = capsys.readouterr()
    assert "RunnerConfigurationError" in output.err
    assert SECRET not in output.err


def test_production_builder_receives_exact_original_milvus_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner()
    config = module._parse_args(_arguments(tmp_path))
    captured: dict[str, Any] = {}

    class Value:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.__dict__.update(kwargs)

    def create_isolated(
        *,
        target_config: Any,
        accepted_backup_gate_root: Path,
        source_manifest_path: Path,
        accepted_original_milvus_sha256: str,
        accepted_original_milvus_record_sha256: str,
        decision_adapter: Any,
        embedding_adapter: Any,
        envelope_sink: Any,
        clock: Any,
        boundary: Any = None,
    ) -> object:
        captured.update(locals())
        return object()

    fake_build_module = SimpleNamespace(
        create_isolated_knowledge_build=create_isolated,
        FileCompleteCandidateEnvelopeSink=Value,
        load_recorded_decision_adapter=lambda path: ("decision", path),
        load_recorded_embedding_adapter=lambda path: ("embedding", path),
        CompleteCandidateTargetConfig=Value,
        DestructiveDatabaseTarget=Value,
        IsolatedIndexTarget=Value,
        CandidateStagingTarget=Value,
        CandidateStagingMarker=Value,
        CompleteCandidateBuildEnvelope=SimpleNamespace(
            model_validate_json=lambda value, **kwargs: value,
            model_validate=lambda value: value,
        ),
    )
    monkeypatch.setattr(module, "import_module", lambda name: fake_build_module)

    dependencies = module._production_dependencies(config)
    dependencies.create_builder(config)

    assert captured["accepted_original_milvus_sha256"] == SHA256_C
    assert captured["accepted_original_milvus_record_sha256"] == SHA256_A


def test_production_serve_fails_before_builder_without_task_12_2_serving_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner()
    config = module._parse_args(_arguments(tmp_path, serve=True))
    imported: list[str] = []

    def create_isolated(*, boundary: Any = None, **kwargs: Any) -> object:
        raise AssertionError("production builder must not be created")

    fake_build_module = SimpleNamespace(
        create_isolated_knowledge_build=create_isolated,
        FileCompleteCandidateEnvelopeSink=object,
        load_recorded_decision_adapter=lambda path: path,
        load_recorded_embedding_adapter=lambda path: path,
    )

    def import_probe(name: str) -> Any:
        imported.append(name)
        if name == "src.data_agents.canonical_v2.knowledge_build_isolated":
            return fake_build_module
        raise AssertionError(f"unexpected Task 12.2 import: {name}")

    monkeypatch.setattr(module, "import_module", import_probe)

    with pytest.raises(module.RunnerConfigurationError, match="Task 12.2|serving"):
        module._production_dependencies(config)

    assert imported == ["src.data_agents.canonical_v2.knowledge_build_isolated"]


@_S12A_MISSING_TARGET
def test_runner_calls_build_once_and_consumes_exact_sink_handoff_without_private_stage_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _runner()
    candidate, envelope = _artifacts()
    events: list[Any] = []
    dependencies = _dependencies(
        module,
        envelope=envelope,
        candidate=candidate,
        events=events,
    )
    monkeypatch.setenv("DATABASE_URL", f"postgresql://generic:{SECRET}@forbidden/db")
    monkeypatch.setenv("MILVUS_URI", str(tmp_path / "forbidden-milvus.db"))

    result = module.main(_arguments(tmp_path), dependencies=dependencies)

    assert result == 0
    assert [event[0] for event in events] == [
        "create_builder",
        "build",
        "read_envelope",
        "validate_envelope",
    ]
    config = events[0][1]
    request = events[1][1]
    assert config.database_url.endswith("/miroflow_candidate_s12a_runner")
    assert config.expected_database == "miroflow_candidate_s12a_runner"
    assert config.database_target_kind == "disposable"
    assert config.accepted_backup_gate_root == tmp_path / "accepted-gate"
    assert config.source_manifest_path == tmp_path / "source-manifest.json"
    assert config.candidate_staging_root == tmp_path / "staging"
    assert config.index_root == tmp_path / "index"
    assert config.recorded_decision_bundle == tmp_path / "recorded-decisions.json"
    assert config.recorded_embedding_bundle == tmp_path / "recorded-embeddings.json"
    expected_envelope = (
        tmp_path / "accepted-gate" / "s12a" / "complete-candidate-build-envelope.json"
    )
    assert config.envelope_output == expected_envelope
    assert config.accepted_original_milvus_path == (
        tmp_path / "protected-original" / "milvus.db"
    )
    assert config.accepted_original_milvus_sha256 == SHA256_C
    assert config.accepted_original_milvus_record_sha256 == SHA256_A
    assert request.run_id == RUN_ID
    assert request.candidate_release_id == RELEASE_ID
    assert request.source_batch_ids == ("s12a-released-objects-full-v1",)
    assert request.parser_versions == {
        "released_objects_sqlite": "canonical-v2-s12a-full-table-v1"
    }
    assert request.policy_versions == {
        "path_eligibility": "path-eligibility-v1",
        "released_objects_mapper": "canonical-v2-released-objects-mapper-v2",
    }
    assert request.model_versions == {"embedding": "recorded-embedding-v1"}
    assert events[2][1] == expected_envelope
    assert events[3][1] is envelope
    output = capsys.readouterr()
    assert output.err == ""
    assert SECRET not in output.out
    assert "candidate_release_id=candidate-s12a-runner" in output.out
    assert f"receipt_sha256={SHA256_A}" in output.out
    assert f"handoff_sha256={SHA256_B}" in output.out
    assert f"envelope_sha256={SHA256_C}" in output.out
    assert not any(
        forbidden in event[0]
        for event in events
        for forbidden in (
            "landing",
            "projection",
            "materialize",
            "verify",
            "promote",
            "rollback",
            "pointer",
            "cleanup",
        )
    )


@_S12A_MISSING_TARGET
def test_runner_serves_app_object_on_fixed_host_port_without_promotion_pointer_reload_or_second_build(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _runner()
    candidate, envelope = _artifacts()
    events: list[Any] = []
    dependencies = _dependencies(
        module,
        envelope=envelope,
        candidate=candidate,
        events=events,
    )
    recorded = SimpleNamespace(
        planning_policy=object(),
        proposal_provider=object(),
        ambiguity_policy=object(),
        universal_web_policy=object(),
        web_search=object(),
        web_snapshot_policy=object(),
        embedding_adapter=object(),
        identity_fuser=object(),
        reranker=object(),
        sufficiency_decider=object(),
        supplemental_search=object(),
        web_handle_resolver=object(),
        accepted_identity_lookup=object(),
        answer_factory=object(),
        answer_session_fork=object(),
        gap_operations=object(),
        supplemental_budget=object(),
        idle_keepwarm_cycle=object(),
    )
    published = object()
    planner = object()
    knowledge_read = object()
    runtime = object()
    app = object()

    def load_serving_inputs(config: Any) -> Any:
        events.append(("load_recorded_serving_inputs", config))
        return recorded

    def create_published_release(**kwargs: Any) -> Any:
        events.append(("create_published_release", kwargs))
        return published

    def create_planner(**kwargs: Any) -> Any:
        events.append(("create_planner", kwargs))
        return planner

    def create_read(**kwargs: Any) -> Any:
        events.append(("create_read", kwargs))
        return knowledge_read

    def compose_runtime(**kwargs: Any) -> Any:
        events.append(("compose_runtime", kwargs))
        return runtime

    def create_app(**kwargs: Any) -> Any:
        events.append(("create_app", kwargs))
        return app

    def uvicorn_run(app_value: Any, **kwargs: Any) -> None:
        events.append(("uvicorn_run", app_value, kwargs))

    dependencies = module.RunnerDependencies(
        create_builder=dependencies.create_builder,
        read_envelope=dependencies.read_envelope,
        validate_envelope=dependencies.validate_envelope,
        load_recorded_serving_inputs=load_serving_inputs,
        create_published_release=create_published_release,
        create_query_planner=create_planner,
        create_knowledge_read=create_read,
        compose_consumer_runtime=compose_runtime,
        create_candidate_app=create_app,
        uvicorn_run=uvicorn_run,
    )

    result = module.main(_arguments(tmp_path, serve=True), dependencies=dependencies)

    assert result == 0
    event_names = [event[0] for event in events]
    assert event_names == [
        "create_builder",
        "build",
        "read_envelope",
        "validate_envelope",
        "load_recorded_serving_inputs",
        "create_published_release",
        "create_planner",
        "create_read",
        "compose_runtime",
        "create_app",
        "uvicorn_run",
    ]
    assert event_names.count("build") == 1
    handoff = envelope.consumer_handoff
    assert events[9][1]["idle_keepwarm_cycle"] is recorded.idle_keepwarm_cycle
    publication_kwargs = events[5][1]
    assert publication_kwargs == {
        "release_id": RELEASE_ID,
        "previous_release_id": None,
        "canonical_release_id": RELEASE_ID,
        "published_projection_release_id": RELEASE_ID,
        "index_release_id": RELEASE_ID,
        "state": "active",
        "changed_at": module.RUN_LOCAL_PUBLICATION_TIME,
        "verification_evidence_ids": handoff.release_verification.evidence_ids,
    }
    planner_kwargs = events[6][1]
    assert planner_kwargs["release_bundle"] is handoff.release_bundle
    assert planner_kwargs["published_release"] is published
    assert (
        planner_kwargs["index_projection_request"] is handoff.index_projection_request
    )
    assert planner_kwargs["release_institution_catalog"] is handoff.institution_catalog
    assert planner_kwargs["proposal_provider"] is recorded.proposal_provider
    read_kwargs = events[7][1]
    assert read_kwargs["release_bundle"] is handoff.release_bundle
    assert read_kwargs["published_release"] is published
    assert read_kwargs["index_projection_request"] is handoff.index_projection_request
    assert read_kwargs["release_institution_catalog"] is handoff.institution_catalog
    assert read_kwargs["web_search"] is recorded.web_search
    assert read_kwargs["reuse_audited_vector_snapshot"] is True
    assert read_kwargs["vectorized_recall"] is True
    assert read_kwargs["sufficiency_decider"] is recorded.sufficiency_decider
    assert read_kwargs["supplemental_search"] is recorded.supplemental_search
    runtime_kwargs = events[8][1]
    assert runtime_kwargs["published_release"] is published
    assert runtime_kwargs["release_verification"] is handoff.release_verification
    assert runtime_kwargs["release_bundle"] is handoff.release_bundle
    assert (
        runtime_kwargs["index_projection_request"] is handoff.index_projection_request
    )
    assert runtime_kwargs["planner"] is planner
    assert runtime_kwargs["knowledge_read"] is knowledge_read
    assert events[9][1] == {
        "runtime": runtime,
        "idle_keepwarm_cycle": recorded.idle_keepwarm_cycle,
    }
    assert events[10] == (
        "uvicorn_run",
        app,
        {"host": "0.0.0.0", "port": 18188, "workers": 1, "reload": False},
    )
    assert not isinstance(events[10][1], str)
    assert not any(
        forbidden in name
        for name in event_names
        for forbidden in (
            "promote",
            "rollback",
            "pointer",
            "cleanup",
            "startup",
        )
    )
    output = capsys.readouterr()
    assert output.err == ""
    assert SECRET not in output.out


@_S12A_MISSING_TARGET
def test_runner_can_serve_existing_envelope_without_invoking_builder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner()
    candidate, envelope = _artifacts()
    arguments = [*_arguments(tmp_path, serve=True), "--serve-existing"]
    envelope_path = (
        tmp_path
        / "accepted-gate"
        / "s12a"
        / "complete-candidate-build-envelope.json"
    )
    envelope_path.write_text("existing-envelope", encoding="utf-8")
    events: list[str] = []

    def forbidden_builder(_: Any) -> Any:
        events.append("create_builder")
        raise AssertionError("serve-existing must not invoke the builder")

    dependencies = module.RunnerDependencies(
        create_builder=forbidden_builder,
        read_envelope=lambda _: events.append("read_envelope") or envelope,
        validate_envelope=lambda value: events.append("validate_envelope") or value,
    )

    def serve(*, config: Any, handoff: Any, dependencies: Any) -> None:
        assert config.serve_existing is True
        assert handoff is envelope.consumer_handoff
        events.append("serve")

    monkeypatch.setattr(module, "_serve", serve)

    result = module.main(arguments, dependencies=dependencies)

    assert result == 0
    assert events == ["read_envelope", "validate_envelope", "serve"]
    assert envelope.receipt.candidate == candidate
