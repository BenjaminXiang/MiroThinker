"""Build one explicit isolated Canonical V2 candidate and optionally serve it."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import Any

RUN_LOCAL_PUBLICATION_TIME = datetime(2026, 7, 22, 0, 0, tzinfo=timezone.utc)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CompleteCandidateRunnerError(RuntimeError):
    """The explicit candidate-run configuration or result is unsafe."""


class RunnerConfigurationError(CompleteCandidateRunnerError):
    """The production composition boundary is incomplete or invalid."""


class RunnerIntegrityError(CompleteCandidateRunnerError):
    """The returned candidate and sink envelope are not the same graph."""


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    database_url: str = field(repr=False)
    expected_database: str
    database_target_kind: str
    accepted_backup_gate_root: Path
    source_manifest_path: Path
    source_manifest_sha256: str
    candidate_staging_root: Path
    index_root: Path
    index_marker_sha256: str
    candidate_release_id: str
    run_id: str
    source_batch_ids: tuple[str, ...]
    parser_versions: dict[str, str]
    policy_versions: dict[str, str]
    model_versions: dict[str, str]
    recorded_decision_bundle: Path
    recorded_embedding_bundle: Path
    recorded_serving_bundle: Path | None
    recorded_serving_bundle_sha256: str | None
    envelope_output: Path
    accepted_original_milvus_path: Path
    accepted_original_milvus_sha256: str
    accepted_original_milvus_record_sha256: str
    serve: bool
    serve_existing: bool
    host: str
    port: int
    serving_pack: Path | None = None


@dataclass(frozen=True, slots=True)
class RunnerDependencies:
    """Narrow recording seam; production binds it to existing accepted factories."""

    create_builder: Callable[[RunnerConfig], Any]
    read_envelope: Callable[[Path], Any]
    validate_envelope: Callable[[Any], Any]
    load_recorded_serving_inputs: Callable[[RunnerConfig], Any] | None = None
    create_published_release: Callable[..., Any] | None = None
    create_query_planner: Callable[..., Any] | None = None
    create_knowledge_read: Callable[..., Any] | None = None
    compose_consumer_runtime: Callable[..., Any] | None = None
    create_candidate_app: Callable[..., Any] | None = None
    uvicorn_run: Callable[..., Any] | None = None
    create_serving_pack_handoff: Callable[[RunnerConfig], Any] | None = None


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _required_absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("an explicit absolute path is required")
    return path


def _required_sha256(value: str) -> str:
    if _SHA256.fullmatch(value) is None:
        raise argparse.ArgumentTypeError("an exact lowercase SHA-256 is required")
    return value


def _normalized_absolute_path(path: Path) -> Path:
    if not path.is_absolute():
        raise RunnerConfigurationError("safety-sensitive paths must be absolute")
    return Path(os.path.abspath(os.fspath(path)))


def _paths_overlap(left: Path, right: Path) -> bool:
    normalized_left = _normalized_absolute_path(left)
    normalized_right = _normalized_absolute_path(right)
    return (
        normalized_left == normalized_right
        or normalized_left.is_relative_to(normalized_right)
        or normalized_right.is_relative_to(normalized_left)
    )


def _require_no_symlink_ancestors(path: Path) -> None:
    normalized = _normalized_absolute_path(path)
    for ancestor in (normalized, *normalized.parents):
        if ancestor.is_symlink():
            raise RunnerConfigurationError(
                "complete candidate envelope ancestry contains a symlink"
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build one isolated Canonical V2 candidate without promotion"
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument(
        "--database-target-kind", required=True, choices=("disposable",)
    )
    parser.add_argument(
        "--accepted-backup-gate-root", required=True, type=_required_absolute_path
    )
    parser.add_argument(
        "--source-manifest", required=True, type=_required_absolute_path
    )
    parser.add_argument(
        "--source-manifest-sha256", required=True, type=_required_sha256
    )
    parser.add_argument(
        "--candidate-staging-root", required=True, type=_required_absolute_path
    )
    parser.add_argument("--index-root", required=True, type=_required_absolute_path)
    parser.add_argument("--index-marker-sha256", required=True, type=_required_sha256)
    parser.add_argument("--candidate-release-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-batch-id", required=True, action="append")
    parser.add_argument("--parser-version", required=True, action="append")
    parser.add_argument("--policy-version", required=True, action="append")
    parser.add_argument("--model-version", required=True, action="append")
    parser.add_argument(
        "--recorded-decision-bundle", required=True, type=_required_absolute_path
    )
    parser.add_argument(
        "--recorded-embedding-bundle", required=True, type=_required_absolute_path
    )
    parser.add_argument("--recorded-serving-bundle", type=_required_absolute_path)
    parser.add_argument(
        "--recorded-serving-bundle-sha256", type=_required_sha256
    )
    parser.add_argument(
        "--envelope-output", required=True, type=_required_absolute_path
    )
    parser.add_argument(
        "--accepted-original-milvus-path",
        required=True,
        type=_required_absolute_path,
    )
    parser.add_argument(
        "--accepted-original-milvus-sha256", required=True, type=_required_sha256
    )
    parser.add_argument(
        "--accepted-original-milvus-record-sha256",
        required=True,
        type=_required_sha256,
    )
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--serve-existing", action="store_true")
    parser.add_argument(
        "--serving-pack",
        type=_required_absolute_path,
        help=(
            "optional prebuilt serving pack directory; when set (or when the "
            "CANONICAL_V2_SERVING_PACK environment variable names one) and "
            "--serve --serve-existing are given, serving boots from the pack "
            "instead of parsing the build envelope"
        ),
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18188)
    return parser


def _version_map(values: Sequence[str], *, label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        key, separator, version = value.partition("=")
        if not separator or not key or not version or key in result:
            raise RunnerConfigurationError(
                f"{label} entries must be unique non-empty KEY=VALUE pairs"
            )
        result[key] = version
    return dict(sorted(result.items()))


def _parse_args(args: Sequence[str] | None) -> RunnerConfig:
    namespace = _parser().parse_args(args)
    if not namespace.database_url:
        raise RunnerConfigurationError("database URL must be explicit")
    if (
        not namespace.expected_database
        or not namespace.candidate_release_id
        or not namespace.run_id
    ):
        raise RunnerConfigurationError(
            "database, release, and run identities are required"
        )
    if len(set(namespace.source_batch_id)) != len(namespace.source_batch_id):
        raise RunnerConfigurationError("source batch IDs must be unique")
    if namespace.host != "0.0.0.0" or namespace.port != 18188:
        raise RunnerConfigurationError(
            "the isolated candidate server is fixed to 0.0.0.0:18188"
        )
    serving_pack = namespace.serving_pack
    if serving_pack is None:
        environment_pack = os.environ.get("CANONICAL_V2_SERVING_PACK", "").strip()
        if environment_pack:
            environment_path = Path(environment_pack)
            if not environment_path.is_absolute():
                raise RunnerConfigurationError(
                    "CANONICAL_V2_SERVING_PACK must be an absolute path"
                )
            serving_pack = environment_path
    if serving_pack is not None and not (namespace.serve and namespace.serve_existing):
        raise RunnerConfigurationError(
            "a serving pack requires --serve --serve-existing"
        )
    if namespace.serve and (
        namespace.recorded_serving_bundle is None
        or namespace.recorded_serving_bundle_sha256 is None
    ):
        raise RunnerConfigurationError(
            "production serving requires an explicit content-addressed serving bundle"
        )
    if namespace.serve_existing and not namespace.serve:
        raise RunnerConfigurationError("serve-existing requires --serve")
    if (namespace.recorded_serving_bundle is None) != (
        namespace.recorded_serving_bundle_sha256 is None
    ):
        raise RunnerConfigurationError(
            "serving bundle path and SHA-256 must be supplied together"
        )
    roots = (
        namespace.candidate_staging_root.resolve(strict=False),
        namespace.index_root.resolve(strict=False),
    )
    if roots[0] == roots[1]:
        raise RunnerConfigurationError("staging and index roots must be distinct")
    explicit_paths = (
        namespace.accepted_backup_gate_root,
        namespace.source_manifest,
        namespace.candidate_staging_root,
        namespace.index_root,
        namespace.recorded_decision_bundle,
        namespace.recorded_embedding_bundle,
        namespace.envelope_output,
        namespace.accepted_original_milvus_path,
        *(
            (namespace.recorded_serving_bundle,)
            if namespace.recorded_serving_bundle is not None
            else ()
        ),
    )
    if len({path.resolve(strict=False) for path in explicit_paths}) != len(
        explicit_paths
    ):
        raise RunnerConfigurationError(
            "explicit control, target, and output paths must differ"
        )
    if namespace.candidate_release_id.startswith("candidate-s12c-"):
        evidence_slice = "s12c"
    elif namespace.candidate_release_id.startswith("candidate-s12b-"):
        evidence_slice = "s12b"
    else:
        evidence_slice = "s12a"
    expected_envelope = namespace.accepted_backup_gate_root / (
        f"{evidence_slice}/complete-candidate-build-envelope.json"
    )
    if _normalized_absolute_path(namespace.envelope_output) != (
        _normalized_absolute_path(expected_envelope)
    ):
        raise RunnerConfigurationError(
            "envelope output must use the fixed candidate evidence path"
        )
    _require_no_symlink_ancestors(
        namespace.envelope_output
        if namespace.serve_existing
        else namespace.envelope_output.parent
    )
    if not namespace.envelope_output.parent.is_dir():
        raise RunnerConfigurationError("envelope output parent must already exist")
    if (
        namespace.serve_existing
        and serving_pack is None
        and (
            not namespace.envelope_output.is_file()
            or namespace.envelope_output.is_symlink()
            or namespace.envelope_output.stat().st_nlink != 1
        )
    ):
        raise RunnerConfigurationError(
            "serve-existing requires one owned regular envelope"
        )
    if not namespace.serve_existing and (
        namespace.envelope_output.exists() or namespace.envelope_output.is_symlink()
    ):
        raise RunnerConfigurationError("envelope output must have fresh ownership")
    immutable_or_target_paths = (
        namespace.accepted_backup_gate_root / "s2",
        namespace.accepted_backup_gate_root / "s2b",
        namespace.source_manifest,
        namespace.candidate_staging_root,
        namespace.index_root,
        namespace.recorded_decision_bundle,
        namespace.recorded_embedding_bundle,
        namespace.accepted_original_milvus_path,
        *(
            (namespace.recorded_serving_bundle,)
            if namespace.recorded_serving_bundle is not None
            else ()
        ),
    )
    if any(
        _paths_overlap(namespace.envelope_output, path)
        for path in immutable_or_target_paths
    ):
        raise RunnerConfigurationError(
            "envelope output overlaps an immutable input or target"
        )
    expected_name = "miroflow_" + namespace.candidate_release_id.replace("-", "_")
    if namespace.expected_database != expected_name:
        raise RunnerConfigurationError(
            "expected database must bind the explicit candidate release"
        )
    return RunnerConfig(
        database_url=namespace.database_url,
        expected_database=namespace.expected_database,
        database_target_kind=namespace.database_target_kind,
        accepted_backup_gate_root=namespace.accepted_backup_gate_root,
        source_manifest_path=namespace.source_manifest,
        source_manifest_sha256=namespace.source_manifest_sha256,
        candidate_staging_root=namespace.candidate_staging_root,
        index_root=namespace.index_root,
        index_marker_sha256=namespace.index_marker_sha256,
        candidate_release_id=namespace.candidate_release_id,
        run_id=namespace.run_id,
        source_batch_ids=tuple(sorted(namespace.source_batch_id)),
        parser_versions=_version_map(namespace.parser_version, label="parser version"),
        policy_versions=_version_map(namespace.policy_version, label="policy version"),
        model_versions=_version_map(namespace.model_version, label="model version"),
        recorded_decision_bundle=namespace.recorded_decision_bundle,
        recorded_embedding_bundle=namespace.recorded_embedding_bundle,
        recorded_serving_bundle=namespace.recorded_serving_bundle,
        recorded_serving_bundle_sha256=(
            namespace.recorded_serving_bundle_sha256
        ),
        envelope_output=namespace.envelope_output,
        accepted_original_milvus_path=namespace.accepted_original_milvus_path,
        accepted_original_milvus_sha256=namespace.accepted_original_milvus_sha256,
        accepted_original_milvus_record_sha256=(
            namespace.accepted_original_milvus_record_sha256
        ),
        serve=namespace.serve,
        serve_existing=namespace.serve_existing,
        host=namespace.host,
        port=namespace.port,
        serving_pack=serving_pack,
    )


def _build_request(config: RunnerConfig) -> Any:
    request_type = import_module(
        "src.data_agents.canonical_v2.knowledge_build"
    ).BuildCandidateRequest
    return request_type(
        run_id=config.run_id,
        candidate_release_id=config.candidate_release_id,
        source_batch_ids=config.source_batch_ids,
        parser_versions=config.parser_versions,
        policy_versions=config.policy_versions,
        model_versions=config.model_versions,
    )


def _require_attribute(value: Any, name: str, *, owner: str) -> Any:
    try:
        return getattr(value, name)
    except AttributeError as exc:
        raise RunnerIntegrityError(f"{owner} is missing required field {name}") from exc


def _validate_result_graph(
    *, candidate: Any, envelope: Any, config: RunnerConfig
) -> Any:
    receipt = _require_attribute(envelope, "receipt", owner="envelope")
    handoff = _require_attribute(envelope, "consumer_handoff", owner="envelope")
    receipt_candidate = _require_attribute(receipt, "candidate", owner="receipt")
    handoff_candidate = _require_attribute(handoff, "candidate", owner="handoff")
    if candidate != receipt_candidate or candidate != handoff_candidate:
        raise RunnerIntegrityError("builder, receipt, and handoff candidates differ")
    if (
        _require_attribute(candidate, "release_id", owner="candidate")
        != config.candidate_release_id
    ):
        raise RunnerIntegrityError(
            "candidate release differs from the explicit request"
        )
    handoff_hash = _require_attribute(handoff, "content_sha256", owner="handoff")
    if (
        _require_attribute(receipt, "consumer_handoff_sha256", owner="receipt")
        != handoff_hash
    ):
        raise RunnerIntegrityError("receipt does not bind the exact sink handoff")
    receipt_bindings = (
        ("source_manifest_sha256", config.source_manifest_sha256),
        (
            "accepted_original_milvus_sha256",
            config.accepted_original_milvus_sha256,
        ),
        (
            "accepted_original_milvus_record_sha256",
            config.accepted_original_milvus_record_sha256,
        ),
    )
    for name, expected in receipt_bindings:
        if _require_attribute(receipt, name, owner="receipt") != expected:
            raise RunnerIntegrityError(
                f"receipt {name} differs from explicit authority"
            )
    for name in (
        "release_bundle",
        "index_projection_request",
        "institution_catalog",
        "release_verification",
    ):
        _require_attribute(handoff, name, owner="handoff")
    return handoff


def _required_serving_dependency(
    value: Callable[..., Any] | None, *, name: str
) -> Callable[..., Any]:
    if value is None:
        raise RunnerConfigurationError(f"recorded serving dependency is absent: {name}")
    return value


def _serve(
    *,
    config: RunnerConfig,
    handoff: Any,
    dependencies: RunnerDependencies,
) -> None:
    load_inputs = _required_serving_dependency(
        dependencies.load_recorded_serving_inputs,
        name="load_recorded_serving_inputs",
    )
    create_published = _required_serving_dependency(
        dependencies.create_published_release, name="create_published_release"
    )
    create_planner = _required_serving_dependency(
        dependencies.create_query_planner, name="create_isolated_release_query_planner"
    )
    create_read = _required_serving_dependency(
        dependencies.create_knowledge_read,
        name="create_isolated_release_knowledge_read",
    )
    compose_runtime = _required_serving_dependency(
        dependencies.compose_consumer_runtime,
        name="compose_canonical_v2_consumer_runtime",
    )
    create_app = _required_serving_dependency(
        dependencies.create_candidate_app, name="create_canonical_v2_candidate_app"
    )
    run_uvicorn = _required_serving_dependency(
        dependencies.uvicorn_run, name="uvicorn.run"
    )
    recorded = load_inputs(config)
    verification = handoff.release_verification
    evidence_ids = tuple(
        _require_attribute(verification, "evidence_ids", owner="release verification")
    )
    fast_boot = os.environ.get("CANONICAL_V2_FAST_BOOT", "").strip() == "1"
    print(f"fast_boot={'1' if fast_boot else '0'}")
    published = create_published(
        release_id=config.candidate_release_id,
        previous_release_id=None,
        canonical_release_id=config.candidate_release_id,
        published_projection_release_id=config.candidate_release_id,
        index_release_id=config.candidate_release_id,
        state="active",
        changed_at=RUN_LOCAL_PUBLICATION_TIME,
        verification_evidence_ids=evidence_ids,
    )
    planner = create_planner(
        release_bundle=handoff.release_bundle,
        published_release=published,
        index_projection_request=handoff.index_projection_request,
        release_institution_catalog=handoff.institution_catalog,
        planning_policy=recorded.planning_policy,
        proposal_provider=recorded.proposal_provider,
        ambiguity_policy=recorded.ambiguity_policy,
    )
    knowledge_read = create_read(
        release_bundle=handoff.release_bundle,
        published_release=published,
        universal_web_policy=recorded.universal_web_policy,
        web_search=recorded.web_search,
        web_snapshot_policy=recorded.web_snapshot_policy,
        embedding_adapter=recorded.embedding_adapter,
        reuse_audited_vector_snapshot=True,
        vectorized_recall=True,
        fast_boot=fast_boot,
        index_projection_request=handoff.index_projection_request,
        release_institution_catalog=handoff.institution_catalog,
        identity_fuser=recorded.identity_fuser,
        reranker=recorded.reranker,
        sufficiency_decider=recorded.sufficiency_decider,
        supplemental_search=recorded.supplemental_search,
        web_handle_resolver=recorded.web_handle_resolver,
        accepted_identity_lookup=recorded.accepted_identity_lookup,
    )
    runtime = compose_runtime(
        published_release=published,
        release_verification=verification,
        release_bundle=handoff.release_bundle,
        index_projection_request=handoff.index_projection_request,
        # The pack composition binds its inputs to the pack authority by
        # identity, which requires the catalog; the envelope composer does
        # not consume it.
        **(
            {"release_institution_catalog": handoff.institution_catalog}
            if config.serving_pack is not None
            else {}
        ),
        planner=planner,
        knowledge_read=knowledge_read,
        answer_factory=recorded.answer_factory,
        answer_session_fork=recorded.answer_session_fork,
        gap_operations=recorded.gap_operations,
        supplemental_budget=recorded.supplemental_budget,
    )
    app = create_app(
        runtime=runtime,
        idle_keepwarm_cycle=recorded.idle_keepwarm_cycle,
    )
    run_uvicorn(
        app,
        host=config.host,
        port=config.port,
        workers=1,
        reload=False,
    )


def _compose_pack_consumer_runtime(
    *,
    authority: Any,
    admin_module: Any,
    published_release: Any,
    release_verification: Any,
    planner: Any,
    knowledge_read: Any,
    answer_factory: Any,
    answer_session_fork: Any,
    gap_operations: Any,
    supplemental_budget: Any,
) -> Any:
    """Mirror ``compose_canonical_v2_consumer_runtime`` over a serving pack.

    The pack loader already proved the release graph exact (marker- and
    hash-bound snapshot, byte-exact reconstructed authority), so the
    deterministic candidate/index replays and the giant-model re-validation
    are not repeated here; every remaining identity, parity, and hash check
    still runs and any mismatch refuses the composition.
    """

    contracts = import_module("src.data_agents.canonical_v2.contracts")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    isolated_read = import_module(
        "src.data_agents.canonical_v2.knowledge_read_isolated"
    )
    bundle = authority.release_bundle
    index_request = authority.index_projection_request
    published = contracts.PublishedRelease.model_validate(
        published_release.model_dump(mode="json")
    )
    verification = contracts.ReleaseVerification.model_validate(
        release_verification.model_dump(mode="json")
    )
    release_id = bundle.release_id
    if (
        published.release_id != release_id
        or published.canonical_release_id != release_id
        or published.published_projection_release_id != release_id
        or published.index_release_id != release_id
        or verification.candidate_release_id != release_id
        or index_request.candidate_projection_request.release_id != release_id
        or index_request.candidate_projection_result.release_id != release_id
    ):
        raise RunnerIntegrityError("consumer artifacts do not identify one release")
    if published.state not in {
        contracts.ReleaseState.active,
        contracts.ReleaseState.rolled_back,
    }:
        raise RunnerIntegrityError("published release is not serviceable")
    if (
        not verification.accepted
        or not verification.canonical_index_parity
        or any(
            value != 0
            for value in (
                verification.missing_points,
                verification.extra_points,
                verification.stale_points,
                verification.cross_release_points,
            )
        )
        or verification.manifest_sha256 != bundle.manifest.manifest_sha256
        or tuple(sorted(verification.evidence_ids))
        != tuple(sorted(published.verification_evidence_ids))
    ):
        raise RunnerIntegrityError(
            "release verification differs from publication authority"
        )
    if bundle.manifest.manifest_sha256 != _canonical_sha256(
        bundle.manifest.model_dump(mode="json", exclude={"manifest_sha256"})
    ):
        raise RunnerIntegrityError(
            "manifest_sha256 does not bind the complete manifest"
        )
    relationship_request = bundle.relationship_projection_request
    relationship_result = bundle.relationship_projection_result
    if relationship_request is None or relationship_result is None:
        raise RunnerIntegrityError(
            "candidate requires relationship publication authority"
        )
    candidate_internal_request = (
        index_request.candidate_projection_request.internal_reference_projection_request
    )
    candidate_internal_result = (
        index_request.candidate_projection_request.internal_reference_projection_result
    )
    if (
        relationship_request.internal_reference_projection_request
        != candidate_internal_request
        or relationship_request.internal_reference_projection_result
        != candidate_internal_result
        or relationship_result.release_id != release_id
    ):
        raise RunnerIntegrityError(
            "relationship authority is not bound to the candidate graph"
        )
    candidate = index_request.candidate_projection_result
    candidate_manifests = {
        item.projection_id: item for item in candidate.published_projections
    }
    release_manifests = {
        item.projection_id: item for item in bundle.manifest.published_projections
    }
    if (
        len(candidate_manifests) != 7
        or len(release_manifests) != 7
        or candidate_manifests != release_manifests
    ):
        raise RunnerIntegrityError(
            "published projections differ from the release manifest"
        )
    public_domains = tuple(
        sorted(
            {
                projection.entity_type
                for projection in candidate.public_domain_projections
            }
        )
    )
    if public_domains != tuple(sorted(isolated_read._PUBLIC_DOMAINS)):
        raise RunnerIntegrityError("candidate must retain exactly four public domains")
    publication_state = (
        "active" if published.state is contracts.ReleaseState.active else "rolled_back"
    )
    binding = read_module.PlanningReleaseBinding(
        release_id=release_id,
        publication_state=publication_state,
        published_release_sha256=_canonical_sha256(published.model_dump(mode="json")),
        publication_verification_evidence_ids=tuple(
            sorted(published.verification_evidence_ids)
        ),
        manifest_sha256=bundle.manifest.manifest_sha256,
        index_projection_request_sha256=_canonical_sha256(
            index_request.model_dump(mode="json")
        ),
        index_projection_result_sha256=bundle.index_result.content_sha256,
        candidate_projection_result_sha256=candidate.content_sha256,
        internal_reference_projection_result_sha256=(
            candidate_internal_result.content_sha256
        ),
        # These two values are owned by the accepted release-bound planner and
        # are additionally closed by RetrievalPlan validation. They are not
        # independently supplied consumer inputs.
        institution_catalog_sha256="0" * 64,
        planning_policy_sha256="0" * 64,
    )
    exact_budget = read_module.SupplementalBudget.model_validate(
        supplemental_budget.model_dump(mode="json")
    )
    controlled_planner = admin_module._ServerOwnedPlanner(
        delegate=planner,
        expected_binding=binding,
        supplemental_budget=exact_budget,
    )
    validated_read = admin_module._ValidatedKnowledgeRead(delegate=knowledge_read)
    newly_created_answer: list[Any | None] = [None]

    def per_turn_answer_factory() -> Any:
        answer = answer_factory()
        newly_created_answer[0] = answer
        return answer

    def per_turn_answer_fork(answer: Any) -> Any:
        if answer is newly_created_answer[0]:
            newly_created_answer[0] = None
        else:
            # Revalidate the configured factory on every later turn while the
            # committed session is forked copy-on-write from its prior state.
            fresh = answer_factory()
            answer_session_fork(fresh)
        return answer_session_fork(answer)

    chat_adapter = admin_module.CanonicalV2ChatAdapter(
        release_id=bundle.release_id,
        planner=controlled_planner,
        knowledge_read=validated_read,
        answer_factory=per_turn_answer_factory,
        answer_session_fork=per_turn_answer_fork,
    )
    admin_runtime = admin_module.CanonicalV2AdminRuntime(
        release_id=bundle.release_id,
        manifest=bundle.manifest,
        candidate_projection=candidate,
        relationship_authority=relationship_result,
        planner=controlled_planner,
        knowledge_read=validated_read,
        chat_adapter=chat_adapter,
        gap_operations=gap_operations,
    )
    runtime = admin_module.CanonicalV2ConsumerRuntime(
        release_id=bundle.release_id,
        admin_runtime=admin_runtime,
        chat_adapter=chat_adapter,
        gap_operations=gap_operations,
    )
    return admin_module.require_canonical_v2_consumer_runtime(runtime)


def _production_dependencies(config: RunnerConfig) -> RunnerDependencies:
    build_module = import_module(
        "src.data_agents.canonical_v2.knowledge_build_isolated"
    )
    create_isolated = build_module.create_isolated_knowledge_build
    parameters = inspect.signature(create_isolated).parameters
    boundary = parameters.get("boundary")
    file_sink_type = getattr(build_module, "FileCompleteCandidateEnvelopeSink", None)
    load_decisions = getattr(build_module, "load_recorded_decision_adapter", None)
    load_embeddings = getattr(
        build_module,
        "load_content_addressed_embedding_adapter",
        getattr(build_module, "load_recorded_embedding_adapter", None),
    )
    if (
        boundary is None
        or boundary.default is inspect.Parameter.empty
        or file_sink_type is None
        or load_decisions is None
        or load_embeddings is None
    ):
        raise RunnerConfigurationError(
            "isolated build module has no exported real boundary, file envelope sink, "
            "or recorded adapter loaders"
        )
    load_serving = getattr(build_module, "load_recorded_serving_inputs", None)
    if config.serve and load_serving is None:
        raise RunnerConfigurationError(
            "production serving requires a separate content-addressed S11 serving bundle; "
            "that Task 12.2 input is not available"
        )

    def create_builder(value: RunnerConfig) -> Any:
        targets = build_module.CompleteCandidateTargetConfig(
            database=build_module.DestructiveDatabaseTarget(
                url=value.database_url,
                expected_database=value.expected_database,
                target_kind=value.database_target_kind,
            ),
            index=build_module.IsolatedIndexTarget(
                root=value.index_root,
                target_id=f"index:{value.candidate_release_id}",
                release_id=value.candidate_release_id,
                forbidden_milvus_paths=(value.accepted_original_milvus_path,),
                marker_sha256=value.index_marker_sha256,
            ),
            staging=build_module.CandidateStagingTarget(
                root=value.candidate_staging_root,
                marker=build_module.CandidateStagingMarker(
                    schema_version="canonical-v2-candidate-staging-marker-v1",
                    run_id=value.run_id,
                    candidate_release_id=value.candidate_release_id,
                    source_manifest_sha256=value.source_manifest_sha256,
                ),
            ),
        )
        return create_isolated(
            target_config=targets,
            accepted_backup_gate_root=value.accepted_backup_gate_root,
            source_manifest_path=value.source_manifest_path,
            accepted_original_milvus_sha256=(value.accepted_original_milvus_sha256),
            accepted_original_milvus_record_sha256=(
                value.accepted_original_milvus_record_sha256
            ),
            decision_adapter=load_decisions(value.recorded_decision_bundle),
            embedding_adapter=load_embeddings(value.recorded_embedding_bundle),
            envelope_sink=file_sink_type(value.envelope_output),
            clock=lambda: datetime.now(timezone.utc),
        )

    def read_envelope(path: Path) -> Any:
        return build_module.CompleteCandidateBuildEnvelope.model_validate_json(
            path.read_bytes(),
            context={"external_content_addressed": True},
        )

    read_module = None
    contracts_module = None
    admin_module = None
    app_module = None
    uvicorn_module = None
    if config.serve:
        read_module = import_module(
            "src.data_agents.canonical_v2.knowledge_read_isolated"
        )
        contracts_module = import_module("src.data_agents.canonical_v2.contracts")
        try:
            admin_module = import_module("backend.services.canonical_v2_admin")
            app_module = import_module("backend.main")
            uvicorn_module = import_module("uvicorn")
        except ModuleNotFoundError:
            admin_root = Path(__file__).resolve().parents[4] / "apps/admin-console"
            if str(admin_root) not in sys.path:
                sys.path.insert(0, str(admin_root))
            admin_module = import_module("backend.services.canonical_v2_admin")
            app_module = import_module("backend.main")
            uvicorn_module = import_module("uvicorn")

    def load_recorded_serving_inputs(value: RunnerConfig) -> Any:
        if load_serving is None:
            raise RunnerConfigurationError(
                "isolated build module has no exported recorded S11 serving-input loader"
            )
        if (
            value.recorded_serving_bundle is None
            or value.recorded_serving_bundle_sha256 is None
        ):
            raise RunnerConfigurationError(
                "production serving requires an explicit serving bundle"
            )
        page_fetch_module = import_module("src.data_agents.providers.page_fetch")
        return load_serving(
            path=value.recorded_serving_bundle,
            expected_content_sha256=value.recorded_serving_bundle_sha256,
            expected_release_id=value.candidate_release_id,
            expected_database=value.expected_database,
            expected_index_root=value.index_root,
            expected_envelope_path=value.envelope_output,
            embedding_adapter=load_embeddings(value.recorded_embedding_bundle),
            page_fetcher=page_fetch_module.create_tiered_page_fetcher(),
        )

    pack_loader_module = None
    if config.serve and config.serving_pack is not None:
        pack_loader_module = import_module(
            "src.data_agents.canonical_v2.serving_pack_loader"
        )
    pack_authority_cache: dict[str, Any] = {}

    def pack_authority() -> Any:
        if pack_loader_module is None:
            raise RunnerConfigurationError(
                "serving pack loader is unavailable without --serving-pack"
            )
        if "authority" not in pack_authority_cache:
            pack_authority_cache["authority"] = (
                pack_loader_module.open_serving_pack_authority(
                    pack_dir=config.serving_pack,
                    expected_release_id=config.candidate_release_id,
                    expected_index_marker_sha256=config.index_marker_sha256,
                    expected_forbidden_milvus_path=(
                        config.accepted_original_milvus_path
                    ),
                )
            )
        return pack_authority_cache["authority"]

    def create_serving_pack_handoff(value: RunnerConfig) -> Any:
        del value
        authority = pack_authority()
        return SimpleNamespace(
            release_bundle=authority.release_bundle,
            index_projection_request=authority.index_projection_request,
            institution_catalog=authority.institution_catalog,
            release_verification=authority.release_verification,
            relationship_request_sha256=(
                authority.manifest.relationship_request_sha256
            ),
            index_projection_request_sha256=(
                authority.manifest.index_projection_request_sha256
            ),
        )

    def _require_pack_composition_inputs(
        kwargs: dict[str, Any],
        authority: Any,
    ) -> None:
        if (
            kwargs.get("release_bundle") is not authority.release_bundle
            or kwargs.get("index_projection_request")
            is not authority.index_projection_request
            or kwargs.get("release_institution_catalog")
            is not authority.institution_catalog
        ):
            raise RunnerIntegrityError(
                "serving pack composition inputs differ from the pack authority"
            )

    def create_pack_query_planner(**kwargs: Any) -> Any:
        authority = pack_authority()
        _require_pack_composition_inputs(kwargs, authority)
        return pack_loader_module.create_serving_pack_query_planner(
            authority=authority,
            published_release=kwargs["published_release"],
            planning_policy=kwargs["planning_policy"],
            proposal_provider=kwargs["proposal_provider"],
            ambiguity_policy=kwargs["ambiguity_policy"],
        )

    def create_pack_knowledge_read(**kwargs: Any) -> Any:
        authority = pack_authority()
        _require_pack_composition_inputs(kwargs, authority)
        return pack_loader_module.create_serving_pack_knowledge_read(
            authority=authority,
            published_release=kwargs["published_release"],
            universal_web_policy=kwargs["universal_web_policy"],
            web_search=kwargs["web_search"],
            web_snapshot_policy=kwargs["web_snapshot_policy"],
            embedding_adapter=kwargs["embedding_adapter"],
            vectorized_recall=kwargs["vectorized_recall"],
            identity_fuser=kwargs["identity_fuser"],
            reranker=kwargs["reranker"],
            sufficiency_decider=kwargs["sufficiency_decider"],
            supplemental_search=kwargs["supplemental_search"],
            web_handle_resolver=kwargs["web_handle_resolver"],
            accepted_identity_lookup=kwargs["accepted_identity_lookup"],
        )

    def compose_pack_consumer_runtime(**kwargs: Any) -> Any:
        authority = pack_authority()
        _require_pack_composition_inputs(kwargs, authority)
        if admin_module is None:
            raise RunnerConfigurationError(
                "serving pack requires the admin console module"
            )
        return _compose_pack_consumer_runtime(
            authority=authority,
            admin_module=admin_module,
            published_release=kwargs["published_release"],
            release_verification=kwargs["release_verification"],
            planner=kwargs["planner"],
            knowledge_read=kwargs["knowledge_read"],
            answer_factory=kwargs["answer_factory"],
            answer_session_fork=kwargs["answer_session_fork"],
            gap_operations=kwargs["gap_operations"],
            supplemental_budget=kwargs["supplemental_budget"],
        )

    pack_mode = pack_loader_module is not None
    return RunnerDependencies(
        create_builder=create_builder,
        read_envelope=read_envelope,
        validate_envelope=build_module.CompleteCandidateBuildEnvelope.model_validate,
        load_recorded_serving_inputs=load_recorded_serving_inputs,
        create_published_release=(
            contracts_module.PublishedRelease if contracts_module is not None else None
        ),
        create_query_planner=(
            create_pack_query_planner
            if pack_mode
            else (
                read_module.create_isolated_release_query_planner
                if read_module is not None
                else None
            )
        ),
        create_knowledge_read=(
            create_pack_knowledge_read
            if pack_mode
            else (
                read_module.create_isolated_release_knowledge_read
                if read_module is not None
                else None
            )
        ),
        compose_consumer_runtime=(
            compose_pack_consumer_runtime
            if pack_mode
            else (
                admin_module.compose_canonical_v2_consumer_runtime
                if admin_module is not None
                else None
            )
        ),
        create_candidate_app=(
            app_module.create_canonical_v2_candidate_app
            if app_module is not None
            else None
        ),
        uvicorn_run=uvicorn_module.run if uvicorn_module is not None else None,
        create_serving_pack_handoff=(
            create_serving_pack_handoff if pack_mode else None
        ),
    )


def main(
    args: Sequence[str] | None = None,
    *,
    dependencies: RunnerDependencies | None = None,
) -> int:
    """Execute one build and optionally serve its exact sink-readback handoff."""

    try:
        config = _parse_args(args)
        selected_dependencies = dependencies or _production_dependencies(config)
        if config.serve_existing and config.serving_pack is not None:
            create_pack_handoff = _required_serving_dependency(
                selected_dependencies.create_serving_pack_handoff,
                name="create_serving_pack_handoff",
            )
            handoff = create_pack_handoff(config)
            print(f"candidate_release_id={config.candidate_release_id}")
            print(f"serving_pack={config.serving_pack}")
            print(
                "relationship_request_sha256=" f"{handoff.relationship_request_sha256}"
            )
            print(
                "index_projection_request_sha256="
                f"{handoff.index_projection_request_sha256}"
            )
            if config.serve:
                _serve(
                    config=config,
                    handoff=handoff,
                    dependencies=selected_dependencies,
                )
            return 0
        if config.serve_existing:
            raw_envelope = selected_dependencies.read_envelope(config.envelope_output)
            envelope = selected_dependencies.validate_envelope(raw_envelope)
            candidate = _require_attribute(
                _require_attribute(envelope, "receipt", owner="envelope"),
                "candidate",
                owner="receipt",
            )
        else:
            builder = selected_dependencies.create_builder(config)
            candidate = builder.build(_build_request(config))
            raw_envelope = selected_dependencies.read_envelope(config.envelope_output)
            envelope = selected_dependencies.validate_envelope(raw_envelope)
        handoff = _validate_result_graph(
            candidate=candidate,
            envelope=envelope,
            config=config,
        )
        receipt = envelope.receipt
        print(f"candidate_release_id={candidate.release_id}")
        print(f"receipt_sha256={receipt.content_sha256}")
        print(f"handoff_sha256={handoff.content_sha256}")
        print(f"envelope_sha256={envelope.content_sha256}")
        if config.serve:
            _serve(
                config=config,
                handoff=handoff,
                dependencies=selected_dependencies,
            )
        return 0
    except CompleteCandidateRunnerError as exc:
        print(
            f"complete candidate runner failed: {type(exc).__name__}", file=sys.stderr
        )
        return 2
    except Exception as exc:
        print(
            f"complete candidate runner failed: {type(exc).__name__}", file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CompleteCandidateRunnerError",
    "RUN_LOCAL_PUBLICATION_TIME",
    "RunnerConfig",
    "RunnerConfigurationError",
    "RunnerDependencies",
    "RunnerIntegrityError",
    "main",
]
