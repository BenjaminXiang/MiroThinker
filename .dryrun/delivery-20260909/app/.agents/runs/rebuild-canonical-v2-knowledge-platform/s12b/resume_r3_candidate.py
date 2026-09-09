"""Resume the exact r3 Candidate after its committed identity checkpoint."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hashlib
from importlib import import_module, util
from pathlib import Path
import sys
from typing import Any

from psycopg import sql


BUILD_AT = datetime.fromisoformat("2026-07-26T07:54:19.872205+00:00")
EXPECTED_RELEASE_ID = "candidate-s12b-20260726-r3"
EXPECTED_RUN_ID = "s12b-build-20260726-r3"
EXPECTED_MANIFEST_SHA256 = (
    "f43e2d56cd2c4bc58a2fea9326854821e6d8cb197566396c034a0389410c7b89"
)
ORIGINAL_STAGING_ROOT = Path("/var/tmp/mirothinker-canonical-v2-s12b/r3/staging")
EXPECTED_COUNTS = {
    "landing.source_record": 5_561,
    "knowledge.identity_decision": 3_776,
    "knowledge.canonical_decision": 0,
    "knowledge.domain_projection_manifest": 0,
    "knowledge.relationship_projection_run": 0,
    "publish.active_release": 0,
}


def _load_runner() -> Any:
    runner_path = (
        Path(__file__).resolve().parents[1] / "s12a/complete_candidate_runner.py"
    )
    spec = util.spec_from_file_location("canonical_v2_s12b_runner", runner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("complete Candidate runner cannot be loaded")
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_resume_boundary(build_module: Any) -> type[Any]:
    class _R3IdentityCheckpointBoundary(build_module._RealBoundary):
        def _assert_fresh_database(self) -> None:
            with self._connect() as connection:
                revisions = connection.execute(
                    "SELECT version_num FROM public.canonical_v2_alembic_version "
                    "ORDER BY version_num"
                ).fetchall()
                if tuple(row["version_num"] for row in revisions) != ("C2_0011",):
                    raise ValueError("r3 checkpoint revision differs")

                relations = connection.execute(
                    "SELECT table_schema, table_name FROM information_schema.tables "
                    "WHERE table_type='BASE TABLE' AND table_schema = ANY(%s) "
                    "ORDER BY table_schema, table_name",
                    (list(build_module._OWNER_SCHEMAS),),
                ).fetchall()
                observed_tables = {
                    f"{row['table_schema']}.{row['table_name']}" for row in relations
                }
                if observed_tables != build_module._EXPECTED_OWNER_TABLES:
                    raise ValueError("r3 checkpoint schema inventory differs")
                if (
                    build_module._live_schema_catalog_sha256(connection)
                    != build_module._EXPECTED_LIVE_SCHEMA_CATALOG_SHA256
                ):
                    raise ValueError("r3 checkpoint schema fingerprint differs")

                release_rows = connection.execute(
                    "SELECT release_id, build_run_id, state, manifest_sha256, "
                    "created_at FROM knowledge.release"
                ).fetchall()
                if release_rows != [
                    {
                        "release_id": EXPECTED_RELEASE_ID,
                        "build_run_id": EXPECTED_RUN_ID,
                        "state": "candidate",
                        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
                        "created_at": BUILD_AT,
                    }
                ]:
                    raise ValueError("r3 Candidate registry checkpoint differs")

                identity_rows = connection.execute(
                    "SELECT release_id, decision_run_id, as_of "
                    "FROM knowledge.identity_resolution_run"
                ).fetchall()
                if identity_rows != [
                    {
                        "release_id": EXPECTED_RELEASE_ID,
                        "decision_run_id": EXPECTED_RUN_ID,
                        "as_of": BUILD_AT,
                    }
                ]:
                    raise ValueError("r3 identity checkpoint differs")

                for relation, expected in EXPECTED_COUNTS.items():
                    schema, table = relation.split(".")
                    row = connection.execute(
                        sql.SQL("SELECT count(*) AS count FROM {}.{}").format(
                            sql.Identifier(schema), sql.Identifier(table)
                        )
                    ).fetchone()
                    if row is None or row["count"] != expected:
                        raise ValueError(f"r3 checkpoint count differs for {relation}")

                release_tables = connection.execute(
                    "SELECT table_schema, table_name FROM information_schema.columns "
                    "WHERE column_name='release_id' AND table_schema = ANY(%s) "
                    "ORDER BY table_schema, table_name",
                    (list(build_module._OWNER_SCHEMAS),),
                ).fetchall()
                for table in release_tables:
                    release_ids = connection.execute(
                        sql.SQL("SELECT DISTINCT release_id FROM {}.{} ").format(
                            sql.Identifier(table["table_schema"]),
                            sql.Identifier(table["table_name"]),
                        )
                    ).fetchall()
                    if any(
                        row["release_id"] != EXPECTED_RELEASE_ID
                        for row in release_ids
                    ):
                        raise ValueError("r3 checkpoint contains another release")
                connection.rollback()
            print("resume_checkpoint_database=validated", flush=True)

        def stage_verified_member(
            self,
            *,
            entry: Any,
            member: Any,
            destination: Path,
        ) -> Any:
            staged = super().stage_verified_member(
                entry=entry,
                member=member,
                destination=destination,
            )
            original = ORIGINAL_STAGING_ROOT / (
                hashlib.sha256(member.member_id.encode("utf-8")).hexdigest()
                + ".source"
            )
            content = build_module._read_stable_unlinked_regular_file(original)
            if (
                len(content) != member.byte_size
                or hashlib.sha256(content).hexdigest() != member.content_sha256
            ):
                raise ValueError("original r3 staged member differs")
            return build_module._StagedSource(
                path=original,
                source_id=staged.source_id,
                member_id=staged.member_id,
                source_batch_id=staged.source_batch_id,
                content_sha256=staged.content_sha256,
                byte_size=staged.byte_size,
            )

    return _R3IdentityCheckpointBoundary


def main(args: list[str] | None = None) -> int:
    runner = _load_runner()
    raw_args = sys.argv[1:] if args is None else args
    config = runner._parse_args(raw_args)
    if (
        config.candidate_release_id != EXPECTED_RELEASE_ID
        or config.run_id != EXPECTED_RUN_ID
    ):
        raise RuntimeError("resume runner is restricted to the exact r3 checkpoint")

    dependencies = runner._production_dependencies(config)
    build_module = import_module(
        "src.data_agents.canonical_v2.knowledge_build_isolated"
    )
    boundary_type = _create_resume_boundary(build_module)

    def create_builder(value: Any) -> Any:
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
        resolved_targets = targets.model_copy(
            update={
                "database": build_module._resolve_explicit_database_target(
                    targets.database
                )
            }
        )
        print("resume_builder_target=resolved", flush=True)
        embedding = build_module.load_content_addressed_embedding_adapter(
            value.recorded_embedding_bundle
        )
        print("resume_builder_embedding=loaded", flush=True)
        boundary = boundary_type(
            targets=resolved_targets,
            backup_gate_root=value.accepted_backup_gate_root,
            embedding_adapter=embedding,
            clock=lambda: BUILD_AT,
        )
        print("resume_builder_boundary=composed", flush=True)
        builder = build_module.create_isolated_knowledge_build(
            target_config=targets,
            accepted_backup_gate_root=value.accepted_backup_gate_root,
            source_manifest_path=value.source_manifest_path,
            accepted_original_milvus_sha256=(
                value.accepted_original_milvus_sha256
            ),
            accepted_original_milvus_record_sha256=(
                value.accepted_original_milvus_record_sha256
            ),
            decision_adapter=build_module.load_recorded_decision_adapter(
                value.recorded_decision_bundle
            ),
            embedding_adapter=embedding,
            boundary=boundary,
            envelope_sink=build_module.FileCompleteCandidateEnvelopeSink(
                value.envelope_output
            ),
            clock=lambda: BUILD_AT,
        )
        print("resume_builder=created", flush=True)

        class _ObservedResumeBuilder:
            def build(self, request: Any) -> Any:
                try:
                    return builder.build(request)
                except Exception as exc:
                    chain: list[str] = []
                    current: BaseException | None = exc
                    while current is not None:
                        chain.append(f"{type(current).__name__}: {current}")
                        current = current.__cause__
                    print("resume_failure_chain=" + " <- ".join(chain), flush=True)
                    raise

        return _ObservedResumeBuilder()

    return runner.main(
        raw_args,
        dependencies=replace(dependencies, create_builder=create_builder),
    )


if __name__ == "__main__":
    raise SystemExit(main())
