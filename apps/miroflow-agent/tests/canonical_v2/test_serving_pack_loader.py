"""Hermetic tests for the Serving Pack loader, generator, and runner wiring.

A tiny but complete release graph (one Company, one Patent, one
``patent_has_applicant`` relationship, plus the resolved-person internal
reference graph) is built once with the real deterministic builders, its index
is materialized with the real on-disk writers (mirroring
``test_fast_boot.py``), and a serving pack is generated from the in-memory
authority. The tests then prove:

- the pack boots and answers planner/relationship/exact/structured/lexical/
  vector queries with plans and evidence sets *identical* to the envelope
  path (same release binding hashes, same evidence identities);
- tampered manifests, tampered pack files, semantic tampering, missing files,
  and wrong expected identities all refuse to boot (fail closed);
- the runner's default envelope path is unchanged and the opt-in
  ``--serving-pack`` / ``CANONICAL_V2_SERVING_PACK`` path uses the pack
  handoff instead of reading the envelope;
- the pack consumer-runtime composition mirrors the admin graph checks.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from src.data_agents.canonical_v2 import (
    index_projection_isolated as isolated_index,
)
from src.data_agents.canonical_v2 import (
    knowledge_read_isolated as isolated_read,
)
from src.data_agents.canonical_v2 import (
    serving_pack_loader as pack_loader,
)
from src.data_agents.canonical_v2.contracts import ReleaseVerification
from src.data_agents.canonical_v2.index_projection import (
    IndexProjectionMaterializationReceipt,
)
from src.data_agents.canonical_v2.index_projection_isolated import (
    RecordedEmbeddingAdapter,
)
from src.data_agents.canonical_v2.knowledge_read import (
    LaneRequest,
    RetrievalLaneResult,
    StructuredConstraints,
    SupplementalBudget,
    WebSearchPolicy,
    WebSnapshotPolicy,
)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
RELEASE_ID = "candidate-serving-pack-test"

_CONTRACT_FIXTURE_PATH = Path(__file__).with_name(
    "test_internal_reference_projection_contract.py"
)
_RUNS_ROOT = (
    Path(__file__).resolve().parents[4]
    / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
)
_GENERATOR_PATH = _RUNS_ROOT / "s12c/build_serving_pack.py"
_RUNNER_PATH = _RUNS_ROOT / "s12a/complete_candidate_runner.py"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _bound_hash(model_type: Any, values: dict[str, Any], hash_field: str) -> str:
    provisional = model_type.model_construct(**values, **{hash_field: "0" * 64})
    payload = provisional.model_dump(mode="json", exclude={hash_field})
    return _canonical_sha256(payload)


def _receipt(index_result: Any) -> Any:
    values: dict[str, Any] = {
        "release_id": RELEASE_ID,
        "target_id": f"index:{RELEASE_ID}",
        "target_kind": "isolated-candidate",
        "vector_backend": "milvus-lite",
        "lookup_backend": "sqlite",
        "point_ids": tuple(sorted(point.point_id for point in index_result.points)),
        "lookup_document_ids": tuple(
            sorted(document.document_id for document in index_result.lookup_documents)
        ),
        "index_projections": index_result.expected_index_projections,
        "lookup_projections": index_result.expected_lookup_projections,
        "source_inventory_sha256": "1" * 64,
        "backup_manifest_sha256": "2" * 64,
        "restore_verification_sha256": "3" * 64,
        "acceptance_record_sha256": "4" * 64,
        "built_at": NOW,
    }
    return IndexProjectionMaterializationReceipt(
        **values,
        content_sha256=_bound_hash(
            IndexProjectionMaterializationReceipt, values, "content_sha256"
        ),
    )


class _PackFixture(SimpleNamespace):
    root: Path
    index_root: Path
    pack_dir: Path
    target: Any
    bundle: Any
    published: Any
    catalog: Any
    verification: Any
    index_request: Any
    adapter: Any
    contract: Any
    generator: Any


def _build_fixture_once(tmp: Path) -> _PackFixture:
    contract = _load_module(
        "canonical_v2_pack_contract_fixture", _CONTRACT_FIXTURE_PATH
    )
    generator = _load_module("canonical_v2_pack_generator", _GENERATOR_PATH)
    release_module = contract._isolated_release_publication_module()
    index_module = contract._index_projection_module()
    contracts_module = import_module("src.data_agents.canonical_v2.contracts")
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")

    authority = contract._company_patent_relationship_authority(release_id=RELEASE_ID)
    index_request = contract._s8r2_index_projection_request(index_module, authority)
    _, index_result, manifest = contract._task7_7_release_values(
        release_module,
        release_id=RELEASE_ID,
        candidate_bundle_factory=lambda: authority[:2],
        relationship_projection_pair=authority[2:],
        exact_index_projection_request=index_request,
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            isolated_index,
            "require_accepted_backup_gate",
            lambda _root: None,
        )
        target = isolated_index.prepare_isolated_index_target(
            root=tmp / "index",
            target_id=f"index:{RELEASE_ID}",
            release_id=RELEASE_ID,
            backup_gate_root=tmp / "gate",
            forbidden_milvus_paths=((tmp / "original-milvus.db").resolve(),),
        )
    adapter = RecordedEmbeddingAdapter(
        model_id=index_result.policy_snapshot.embedding_model,
        dimension=32,
    )
    lookup_path = target.root / "lookup.sqlite3"
    isolated_index._write_lookup_projection(
        lookup_path,
        release_id=RELEASE_ID,
        documents=index_result.lookup_documents,
        manifests=index_result.expected_lookup_projections,
    )
    collection_name = isolated_index._collection_name(target, index_request)
    client = isolated_index._open_milvus_client(target.root / "milvus.db")
    try:
        isolated_index._write_milvus_projection(
            client,
            collection_name=collection_name,
            points=index_result.points,
            embedding_adapter=adapter,
        )
    finally:
        client.close()
    isolated_index._write_build_metadata(lookup_path, collection_name=collection_name)
    isolated_index._write_receipt(lookup_path, _receipt(index_result))
    bundle = release_module.IsolatedReleaseBundle(
        manifest=manifest,
        index_result=index_result,
        index_target=target,
        relationship_projection_request=authority[2],
        relationship_projection_result=authority[3],
    )
    published = contract._s8p1_published_release(
        contracts_module,
        release_id=RELEASE_ID,
    )
    catalog = contract._s8r2_institution_catalog(read_module, release_id=RELEASE_ID)
    verification = ReleaseVerification(
        candidate_release_id=RELEASE_ID,
        manifest_sha256=manifest.manifest_sha256,
        accepted=True,
        canonical_index_parity=True,
        missing_points=0,
        extra_points=0,
        stale_points=0,
        cross_release_points=0,
        evidence_ids=published.verification_evidence_ids,
        verified_at=NOW,
    )
    pack_dir = tmp / "serving-pack"
    generator.build_serving_pack_from_authority(
        release_bundle=bundle,
        index_projection_request=index_request,
        institution_catalog=catalog,
        release_verification=verification,
        index_root=target.root,
        pack_dir=pack_dir,
        expected_release_id=RELEASE_ID,
        generator_run_id="serving-pack-test-run",
    )
    return _PackFixture(
        root=tmp,
        index_root=target.root,
        pack_dir=pack_dir,
        target=target,
        bundle=bundle,
        published=published,
        catalog=catalog,
        verification=verification,
        index_request=index_request,
        adapter=adapter,
        contract=contract,
        generator=generator,
    )


@pytest.fixture(scope="module")
def serving_fixture(tmp_path_factory: pytest.TempPathFactory) -> _PackFixture:
    return _build_fixture_once(tmp_path_factory.mktemp("serving-pack"))


@pytest.fixture()
def pack_copy(serving_fixture: _PackFixture, tmp_path: Path) -> Path:
    destination = tmp_path / "serving-pack"
    shutil.copytree(serving_fixture.pack_dir, destination)
    return destination


def _open_authority(fixture: _PackFixture, pack_dir: Path) -> Any:
    return pack_loader.open_serving_pack_authority(
        pack_dir=pack_dir,
        expected_release_id=RELEASE_ID,
        expected_index_marker_sha256=fixture.target.marker_sha256,
        expected_forbidden_milvus_path=fixture.target.forbidden_milvus_paths[0],
        embedding_adapter=fixture.adapter,
    )


def _lane_request(
    *,
    lane: str,
    query_text: str,
    displayed_ids: tuple[str, ...] = (),
) -> Any:
    return LaneRequest(
        lane=lane,
        release_id=RELEASE_ID,
        query_view="view:original",
        original_query=query_text,
        behavior_class="A",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(mode="disabled"),
        query_text=query_text,
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(
            displayed_entity_ids=displayed_ids
        ),
        max_candidates=8,
    )


def _web_policies() -> tuple[WebSearchPolicy, WebSnapshotPolicy]:
    return (
        WebSearchPolicy(
            mode="universal",
            max_provider_calls=2,
            timeout_ms=1_000,
            max_results=5,
        ),
        WebSnapshotPolicy(
            policy_id="web-snapshot:pack-test",
            policy_version="web-snapshot-v1",
            max_bytes=4096,
        ),
    )


def test_pack_boot_matches_envelope_path(serving_fixture: _PackFixture) -> None:
    fixture = serving_fixture
    contract = fixture.contract
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read")
    authority = _open_authority(fixture, fixture.pack_dir)

    planning_policy = contract._s8r2_planning_policy(read_module)

    def proposal_provider(value: Any) -> Any:
        return contract._s8r2_proposal(read_module, value)

    envelope_planner = isolated_read.create_isolated_release_query_planner(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
        index_projection_request=fixture.index_request,
        release_institution_catalog=fixture.catalog,
        planning_policy=planning_policy,
        proposal_provider=proposal_provider,
    )
    pack_planner = pack_loader.create_serving_pack_query_planner(
        authority=authority,
        published_release=fixture.published,
        planning_policy=planning_policy,
        proposal_provider=proposal_provider,
    )
    request = contract._s8r2_planning_request(read_module, release_id=RELEASE_ID)
    envelope_plan = envelope_planner.plan(request)
    pack_plan = pack_planner.plan(request)
    assert envelope_plan == pack_plan
    assert envelope_plan.release_binding is not None
    assert (
        envelope_plan.release_binding.index_projection_request_sha256
        == authority.manifest.index_projection_request_sha256
    )

    web_policy, snapshot_policy = _web_policies()

    def web_search(_request: Any) -> Any:
        return RetrievalLaneResult()

    envelope_read = isolated_read.create_isolated_release_knowledge_read(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
        universal_web_policy=web_policy,
        web_search=web_search,
        web_snapshot_policy=snapshot_policy,
        embedding_adapter=fixture.adapter,
        reuse_audited_vector_snapshot=True,
        vectorized_recall=True,
        fast_boot=True,
        index_projection_request=fixture.index_request,
        release_institution_catalog=fixture.catalog,
    )
    pack_read = pack_loader.create_serving_pack_knowledge_read(
        authority=authority,
        published_release=fixture.published,
        universal_web_policy=web_policy,
        web_search=web_search,
        web_snapshot_policy=snapshot_policy,
        embedding_adapter=fixture.adapter,
    )
    envelope_evidence = envelope_read.execute(envelope_plan)
    pack_evidence = pack_read.execute(pack_plan)
    assert envelope_evidence == pack_evidence
    assert envelope_evidence.items


def test_pack_lane_adapters_match_upstream(serving_fixture: _PackFixture) -> None:
    fixture = serving_fixture
    authority = _open_authority(fixture, fixture.pack_dir)
    bundle = authority.release_bundle
    candidate_result = authority.index_projection_request.candidate_projection_result
    company = next(
        projection
        for projection in candidate_result.public_domain_projections
        if projection.entity_type == "company"
    )
    company_name = company.name
    company_id = company.canonical_identity_id
    lookup_view = isolated_read._create_audited_lookup_view(bundle)

    cases: list[tuple[str, Any, Any]] = []
    upstream_exact = isolated_read.create_isolated_exact_lookup_adapter(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
    )
    pack_exact = pack_loader._create_pack_exact_lookup_adapter(
        bundle=bundle,
        publication=fixture.published,
        lookup_view=lookup_view,
    )
    cases.append(("exact", upstream_exact, pack_exact))

    upstream_structured = isolated_read.create_isolated_structured_lookup_adapter(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
    )
    pack_structured = pack_loader._create_pack_structured_lookup_adapter(
        bundle=bundle,
        publication=fixture.published,
        lookup_view=lookup_view,
    )
    cases.append(("structured", upstream_structured, pack_structured))

    upstream_lexical = isolated_read.create_isolated_lexical_lookup_adapter(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
    )
    pack_lexical = pack_loader._create_pack_lexical_lookup_adapter(
        bundle=bundle,
        publication=fixture.published,
        lookup_view=lookup_view,
    )
    cases.append(("lexical", upstream_lexical, pack_lexical))

    upstream_vector = isolated_read.create_isolated_vector_recall_adapter(
        release_bundle=fixture.bundle,
        published_release=fixture.published,
        embedding_adapter=fixture.adapter,
        reuse_audited_snapshot=True,
        vectorized_scoring=True,
        fast_boot=True,
    )
    pack_vector = pack_loader._create_pack_vector_recall_adapter(
        bundle=bundle,
        publication=fixture.published,
        embedding_adapter=fixture.adapter,
        vectorized_scoring=True,
        preopened_snapshot=authority.index_snapshot,
    )
    cases.append(("vector", upstream_vector, pack_vector))

    requests = {
        "exact": _lane_request(lane="exact", query_text=company_name),
        "structured": _lane_request(
            lane="structured",
            query_text=company_name,
            displayed_ids=(company_id,),
        ),
        "lexical": _lane_request(lane="lexical", query_text=company_name),
        "vector": _lane_request(
            lane="vector",
            query_text=f"{company_name} [lane=vector]",
        ),
    }
    for lane, upstream_adapter, pack_adapter in cases:
        upstream_result = upstream_adapter(requests[lane])
        pack_result = pack_adapter(requests[lane])
        assert upstream_result == pack_result, lane
        assert upstream_result.candidates, lane


def test_generator_round_trip_reloads_exact_authority(
    serving_fixture: _PackFixture,
) -> None:
    fixture = serving_fixture
    authority = _open_authority(fixture, fixture.pack_dir)
    assert authority.release_bundle.index_result == fixture.bundle.index_result
    assert (
        authority.release_bundle.relationship_projection_result
        == fixture.bundle.relationship_projection_result
    )
    assert (
        authority.index_projection_request.candidate_projection_result
        == fixture.index_request.candidate_projection_result
    )
    assert authority.institution_catalog == fixture.catalog
    assert authority.release_verification == fixture.verification
    assert authority.release_bundle.manifest == fixture.bundle.manifest
    observed = pack_loader._canonical_sha256(
        authority.release_bundle.relationship_projection_request.model_dump(mode="json")
    )
    assert observed == authority.manifest.relationship_request_sha256


def test_missing_pack_directory_refuses(tmp_path: Path) -> None:
    with pytest.raises(
        pack_loader.ServingPackIntegrityError,
        match="missing or unsafe|must be absolute",
    ):
        pack_loader.open_serving_pack_authority(
            pack_dir=(tmp_path / "absent").resolve(),
            expected_release_id=RELEASE_ID,
            expected_index_marker_sha256="0" * 64,
            expected_forbidden_milvus_path=(tmp_path / "original.db").resolve(),
        )


def test_missing_relationships_file_refuses(
    serving_fixture: _PackFixture,
    pack_copy: Path,
) -> None:
    (pack_copy / pack_loader.PACK_RELATIONSHIPS_FILENAME).unlink()
    with pytest.raises(pack_loader.ServingPackIntegrityError, match="missing"):
        _open_authority(serving_fixture, pack_copy)


def test_missing_index_copy_refuses(
    serving_fixture: _PackFixture,
    pack_copy: Path,
) -> None:
    (pack_copy / "milvus.db").unlink()
    with pytest.raises(pack_loader.ServingPackIntegrityError, match="missing"):
        _open_authority(serving_fixture, pack_copy)


def test_tampered_relationships_file_refuses(
    serving_fixture: _PackFixture,
    pack_copy: Path,
) -> None:
    path = pack_copy / pack_loader.PACK_RELATIONSHIPS_FILENAME
    content = path.read_bytes()
    path.write_bytes(content[:100] + b" " + content[101:])
    with pytest.raises(pack_loader.ServingPackIntegrityError, match="hash differs"):
        _open_authority(serving_fixture, pack_copy)


def test_tampered_manifest_identity_refuses(
    serving_fixture: _PackFixture,
    pack_copy: Path,
) -> None:
    path = pack_copy / pack_loader.PACK_MANIFEST_FILENAME
    manifest = json.loads(path.read_bytes())
    manifest["release_id"] = "candidate-serving-pack-tampered"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(pack_loader.ServingPackIntegrityError, match="release differs"):
        _open_authority(serving_fixture, pack_copy)


def test_tampered_manifest_model_hash_refuses(
    serving_fixture: _PackFixture,
    pack_copy: Path,
) -> None:
    path = pack_copy / pack_loader.PACK_MANIFEST_FILENAME
    manifest = json.loads(path.read_bytes())
    manifest["relationship_request_sha256"] = "0" * 64
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(
        pack_loader.ServingPackIntegrityError,
        match="does not reproduce its recorded hash",
    ):
        _open_authority(serving_fixture, pack_copy)


def test_semantic_tamper_with_updated_file_hash_refuses(
    serving_fixture: _PackFixture,
    pack_copy: Path,
) -> None:
    relationships_path = pack_copy / pack_loader.PACK_RELATIONSHIPS_FILENAME
    document = json.loads(relationships_path.read_bytes())
    current = document["relationship_projection_result"]["current_relationships"]
    assert current
    document["relationship_projection_result"]["current_relationships"] = current[1:]
    relationships_path.write_bytes(
        (json.dumps(document, ensure_ascii=False) + "\n").encode("utf-8")
    )
    manifest_path = pack_copy / pack_loader.PACK_MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"][pack_loader.PACK_RELATIONSHIPS_FILENAME] = hashlib.sha256(
        relationships_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(pack_loader.ServingPackIntegrityError):
        _open_authority(serving_fixture, pack_copy)


def test_wrong_expected_release_refuses(serving_fixture: _PackFixture) -> None:
    with pytest.raises(pack_loader.ServingPackIntegrityError, match="release differs"):
        pack_loader.open_serving_pack_authority(
            pack_dir=serving_fixture.pack_dir,
            expected_release_id="candidate-serving-pack-other",
            expected_index_marker_sha256=serving_fixture.target.marker_sha256,
            expected_forbidden_milvus_path=(
                serving_fixture.target.forbidden_milvus_paths[0]
            ),
            embedding_adapter=serving_fixture.adapter,
        )


def test_wrong_embedding_adapter_refuses(serving_fixture: _PackFixture) -> None:
    wrong = RecordedEmbeddingAdapter(model_id="recorded-embedding-other", dimension=32)
    with pytest.raises(
        pack_loader.ServingPackIntegrityError,
        match="embedding model differs",
    ):
        pack_loader.open_serving_pack_authority(
            pack_dir=serving_fixture.pack_dir,
            expected_release_id=RELEASE_ID,
            expected_index_marker_sha256=serving_fixture.target.marker_sha256,
            expected_forbidden_milvus_path=(
                serving_fixture.target.forbidden_milvus_paths[0]
            ),
            embedding_adapter=wrong,
        )


# ---------------------------------------------------------------------------
# Runner wiring: opt-in pack path, default path unchanged.
# ---------------------------------------------------------------------------


def _runner(tmp_path: Path) -> tuple[Any, list[str], Path]:
    runner = _load_module("canonical_v2_pack_runner", _RUNNER_PATH)
    gate_root = tmp_path / "gate"
    envelope_output = gate_root / "s12a/complete-candidate-build-envelope.json"
    envelope_output.parent.mkdir(parents=True, exist_ok=True)
    envelope_output.write_bytes(b"{}")
    argv = [
        "--database-url",
        "postgresql+psycopg://example.invalid:5432/miroflow_pack",
        "--expected-database",
        "miroflow_candidate_serving_pack_test",
        "--database-target-kind",
        "disposable",
        "--accepted-backup-gate-root",
        str(gate_root),
        "--source-manifest",
        str(tmp_path / "source-manifest.json"),
        "--source-manifest-sha256",
        "0" * 64,
        "--candidate-staging-root",
        str(tmp_path / "staging"),
        "--index-root",
        str(tmp_path / "index"),
        "--index-marker-sha256",
        "1" * 64,
        "--candidate-release-id",
        RELEASE_ID,
        "--run-id",
        "serving-pack-test-run",
        "--source-batch-id",
        "accepted-s2b-source-batch",
        "--parser-version",
        "historical=parser-v1",
        "--policy-version",
        "eligibility=path-eligibility-v1",
        "--model-version",
        "embedding=recorded-embedding-v1",
        "--recorded-decision-bundle",
        str(tmp_path / "decisions.json"),
        "--recorded-embedding-bundle",
        str(tmp_path / "embeddings.json"),
        "--recorded-serving-bundle",
        str(tmp_path / "serving.json"),
        "--recorded-serving-bundle-sha256",
        "2" * 64,
        "--envelope-output",
        str(envelope_output),
        "--accepted-original-milvus-path",
        str(tmp_path / "original-milvus.db"),
        "--accepted-original-milvus-sha256",
        "3" * 64,
        "--accepted-original-milvus-record-sha256",
        "4" * 64,
        "--serve",
        "--serve-existing",
    ]
    return runner, argv, envelope_output


def test_parse_args_default_has_no_serving_pack(tmp_path: Path) -> None:
    runner, argv, _ = _runner(tmp_path)
    config = runner._parse_args(argv)
    assert config.serving_pack is None


def test_parse_args_serving_pack_opt_in(tmp_path: Path) -> None:
    runner, argv, _ = _runner(tmp_path)
    pack_dir = (tmp_path / "serving-pack").resolve()
    config = runner._parse_args([*argv, "--serving-pack", str(pack_dir)])
    assert config.serving_pack == pack_dir


def test_parse_args_serving_pack_env_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, argv, _ = _runner(tmp_path)
    pack_dir = (tmp_path / "serving-pack").resolve()
    monkeypatch.setenv("CANONICAL_V2_SERVING_PACK", str(pack_dir))
    config = runner._parse_args(argv)
    assert config.serving_pack == pack_dir


def test_parse_args_serving_pack_requires_serve_existing(tmp_path: Path) -> None:
    runner, argv, _ = _runner(tmp_path)
    pack_dir = (tmp_path / "serving-pack").resolve()
    without_serve_existing = [value for value in argv if value != "--serve-existing"]
    with pytest.raises(
        runner.RunnerConfigurationError,
        match="requires --serve --serve-existing",
    ):
        runner._parse_args([*without_serve_existing, "--serving-pack", str(pack_dir)])


def test_parse_args_serving_pack_skips_envelope_ownership(tmp_path: Path) -> None:
    runner, argv, envelope_output = _runner(tmp_path)
    envelope_output.unlink()
    pack_dir = (tmp_path / "serving-pack").resolve()
    # The envelope file does not exist; pack mode must not require it...
    config = runner._parse_args([*argv, "--serving-pack", str(pack_dir)])
    assert config.serving_pack == pack_dir
    # ...while the default serve-existing path still refuses its absence.
    with pytest.raises(
        runner.RunnerConfigurationError,
        match="owned regular envelope",
    ):
        runner._parse_args(argv)


def _mocked_serving_dependencies(
    runner: Any,
    *,
    recorded: Any,
    serve_calls: list[Any],
) -> Any:
    return runner.RunnerDependencies(
        create_builder=lambda _config: object(),
        read_envelope=lambda _path: serve_calls.append("read_envelope"),
        validate_envelope=lambda value: value,
        load_recorded_serving_inputs=lambda _config: recorded,
        create_published_release=lambda **kwargs: SimpleNamespace(**kwargs),
        create_query_planner=lambda **kwargs: object(),
        create_knowledge_read=lambda **kwargs: object(),
        compose_consumer_runtime=lambda **kwargs: object(),
        create_candidate_app=lambda **kwargs: object(),
        uvicorn_run=lambda _app, **kwargs: None,
        create_serving_pack_handoff=lambda _config: recorded,
    )


def test_main_pack_mode_uses_pack_handoff_not_envelope(tmp_path: Path) -> None:
    runner, argv, _ = _runner(tmp_path)
    pack_dir = (tmp_path / "serving-pack").resolve()
    recorded = SimpleNamespace(
        release_bundle=object(),
        index_projection_request=object(),
        institution_catalog=object(),
        release_verification=SimpleNamespace(
            evidence_ids=("release-verification:pack-test",)
        ),
        relationship_request_sha256="a" * 64,
        index_projection_request_sha256="b" * 64,
    )
    served: list[Any] = []

    def fake_serve(*, config: Any, handoff: Any, dependencies: Any) -> None:
        served.append(handoff)

    runner._serve = fake_serve
    serve_calls: list[Any] = []
    dependencies = _mocked_serving_dependencies(
        runner,
        recorded=recorded,
        serve_calls=serve_calls,
    )
    result = runner.main(
        [*argv, "--serving-pack", str(pack_dir)],
        dependencies=dependencies,
    )
    assert result == 0
    assert served == [recorded]
    assert serve_calls == []


def test_pack_consumer_runtime_composition(
    serving_fixture: _PackFixture,
) -> None:
    runner = _load_module("canonical_v2_pack_runner_compose", _RUNNER_PATH)
    fixture = serving_fixture
    authority = _open_authority(fixture, fixture.pack_dir)
    captured: dict[str, Any] = {}

    def capture(name: str):
        def factory(**kwargs: Any) -> Any:
            captured[name] = kwargs
            return SimpleNamespace(kind=name, **kwargs)

        return factory

    fake_admin = SimpleNamespace(
        _ServerOwnedPlanner=capture("planner"),
        _ValidatedKnowledgeRead=capture("read"),
        CanonicalV2ChatAdapter=capture("chat"),
        CanonicalV2AdminRuntime=capture("admin_runtime"),
        CanonicalV2ConsumerRuntime=capture("runtime"),
        require_canonical_v2_consumer_runtime=lambda runtime: runtime,
    )
    budget = SupplementalBudget(
        max_wall_time_ms=1_000,
        max_provider_calls=2,
        max_retries=0,
        max_cost_units=3.5,
    )
    runtime = runner._compose_pack_consumer_runtime(
        authority=authority,
        admin_module=fake_admin,
        published_release=fixture.published,
        release_verification=fixture.verification,
        planner=object(),
        knowledge_read=object(),
        answer_factory=lambda: object(),
        answer_session_fork=lambda answer: answer,
        gap_operations=object(),
        supplemental_budget=budget,
    )
    assert runtime.kind == "runtime"
    binding = captured["planner"]["expected_binding"]
    assert binding.release_id == RELEASE_ID
    assert (
        binding.index_projection_request_sha256
        == authority.manifest.index_projection_request_sha256
    )
    assert binding.manifest_sha256 == fixture.bundle.manifest.manifest_sha256
    assert captured["admin_runtime"]["candidate_projection"] == (
        fixture.index_request.candidate_projection_result
    )

    tampered_verification = fixture.verification.model_copy(
        update={"manifest_sha256": "0" * 64}
    )
    with pytest.raises(runner.RunnerIntegrityError, match="verification"):
        runner._compose_pack_consumer_runtime(
            authority=authority,
            admin_module=fake_admin,
            published_release=fixture.published,
            release_verification=tampered_verification,
            planner=object(),
            knowledge_read=object(),
            answer_factory=lambda: object(),
            answer_session_fork=lambda answer: answer,
            gap_operations=object(),
            supplemental_budget=budget,
        )
