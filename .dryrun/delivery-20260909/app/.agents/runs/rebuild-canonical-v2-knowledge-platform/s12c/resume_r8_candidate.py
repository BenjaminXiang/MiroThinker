"""Resume the exact r8 Candidate after its committed identity checkpoint."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from importlib import util
from pathlib import Path
import sys
from typing import Any


def _load_resume_module() -> Any:
    path = Path(__file__).resolve().parents[1] / "s12b/resume_r3_candidate.py"
    spec = util.spec_from_file_location("canonical_v2_s12c_r8_resume", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("checkpoint resume module cannot be loaded")
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(args: list[str] | None = None) -> int:
    resume = _load_resume_module()
    resume.BUILD_AT = datetime.fromisoformat("2026-07-26T17:27:05.166020+00:00")
    resume.EXPECTED_RELEASE_ID = "candidate-s12c-20260726-r8"
    resume.EXPECTED_RUN_ID = "s12c-build-20260726-r8"
    resume.EXPECTED_MANIFEST_SHA256 = (
        "26162728337231cf2f233954efe75903f869b450ac324f75dd44c6e2192d1c99"
    )
    resume.ORIGINAL_STAGING_ROOT = Path(
        "/var/tmp/mirothinker-canonical-v2-s12c/r8/staging"
    )
    resume.EXPECTED_COUNTS = {
        "landing.source_record": 5_586,
        "knowledge.identity_decision": 3_784,
        "knowledge.canonical_decision": 0,
        "knowledge.domain_projection_manifest": 0,
        "knowledge.relationship_projection_run": 0,
        "publish.active_release": 0,
    }

    base_boundary_factory = resume._create_resume_boundary

    def create_r8_checkpoint_boundary(build_module: Any) -> type[Any]:
        base_boundary = base_boundary_factory(build_module)

        class _R8IdentityCheckpointBoundary(base_boundary):
            def persist_identity_resolution(
                self, *, request: Any, result: Any
            ) -> Any:
                return result

            def persist_decision_batch(self, *, result: Any) -> Any:
                relationship_ids = tuple(
                    assertion.assertion_id
                    for assertion in result.relationship_assertions
                )
                relationship_id_set = set(relationship_ids)
                fingerprints = tuple(
                    build_module._canonical_sha256(
                        assertion.model_dump(mode="json")
                    )
                    for assertion in result.relationship_assertions
                )
                outcome_counts = Counter(
                    outcome.assertion_id
                    for outcome in result.constraint_outcomes
                    if outcome.assertion_id in relationship_id_set
                )
                with self._connect() as connection:
                    source_identity_ids = {
                        row["source_identity_id"]
                        for row in connection.execute(
                            "SELECT source_identity_id FROM knowledge.source_identity"
                        ).fetchall()
                    }
                    memberships = {
                        (row["source_identity_id"], row["record_id"])
                        for row in connection.execute(
                            "SELECT source_identity_id, record_id FROM "
                            "knowledge.source_identity_record"
                        ).fetchall()
                    }
                    connection.rollback()
                missing_endpoints = sorted(
                    {
                        endpoint.identity_id
                        for assertion in result.relationship_assertions
                        for endpoint in (
                            assertion.source_endpoint,
                            assertion.target_endpoint,
                        )
                        if endpoint.identity_id not in source_identity_ids
                    }
                )
                missing_memberships = sorted(
                    {
                        (endpoint.identity_id, assertion.source_record_id)
                        for assertion in result.relationship_assertions
                        for endpoint in (
                            assertion.source_endpoint,
                            assertion.target_endpoint,
                        )
                        if (endpoint.identity_id, assertion.source_record_id)
                        not in memberships
                    }
                )
                print(
                    "resume_decision_diagnostic="
                    + repr(
                        {
                            "relationship_assertions": len(relationship_ids),
                            "duplicate_assertion_ids": sorted(
                                key
                                for key, count in Counter(relationship_ids).items()
                                if count > 1
                            ),
                            "duplicate_fingerprints": sum(
                                count - 1
                                for count in Counter(fingerprints).values()
                                if count > 1
                            ),
                            "multi_outcome_assertion_ids": sorted(
                                key
                                for key, count in outcome_counts.items()
                                if count > 1
                            ),
                            "missing_endpoints": missing_endpoints,
                            "missing_memberships": missing_memberships,
                        }
                    ),
                    flush=True,
                )
                return super().persist_decision_batch(result=result)

        return _R8IdentityCheckpointBoundary

    resume._create_resume_boundary = create_r8_checkpoint_boundary
    return resume.main(sys.argv[1:] if args is None else args)


if __name__ == "__main__":
    raise SystemExit(main())
