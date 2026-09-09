"""Resume the exact r6 Candidate from its committed PostgreSQL checkpoint."""

from __future__ import annotations

from datetime import datetime
from importlib import util
from pathlib import Path
import sys
from typing import Any


def _load_resume_module() -> Any:
    path = Path(__file__).resolve().parents[1] / "s12b/resume_r3_candidate.py"
    spec = util.spec_from_file_location("canonical_v2_s12c_checkpoint_resume", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("checkpoint resume module cannot be loaded")
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(args: list[str] | None = None) -> int:
    resume = _load_resume_module()
    resume.BUILD_AT = datetime.fromisoformat("2026-07-26T12:48:21.433643+00:00")
    resume.EXPECTED_RELEASE_ID = "candidate-s12c-20260726-r6"
    resume.EXPECTED_RUN_ID = "s12c-build-20260726-r6"
    resume.EXPECTED_MANIFEST_SHA256 = (
        "008ba4bc40b62f5a5fdeff59edb26d276269601e31103f08ec29ed5e75dcd6fb"
    )
    resume.ORIGINAL_STAGING_ROOT = Path(
        "/var/tmp/mirothinker-canonical-v2-s12c/r6/staging"
    )
    resume.EXPECTED_COUNTS = {
        "landing.source_record": 5_561,
        "knowledge.identity_decision": 3_776,
        "knowledge.canonical_decision": 21_993,
        "knowledge.domain_projection_manifest": 1,
        "knowledge.relationship_projection_run": 1,
        "publish.active_release": 0,
    }

    base_boundary_factory = resume._create_resume_boundary

    def create_r6_checkpoint_boundary(build_module: Any) -> type[Any]:
        base_boundary = base_boundary_factory(build_module)

        class _R6CompletePostgresCheckpointBoundary(base_boundary):
            def persist_identity_resolution(
                self, *, request: Any, result: Any
            ) -> Any:
                return result

            def persist_decision_batch(self, *, result: Any) -> Any:
                return result

            def persist_domain_projection(self, *, result: Any) -> Any:
                return result

            def persist_relationship_projection(
                self, *, request: Any, result: Any
            ) -> Any:
                return result

            def persist_gap(self, *, signal: Any, expected: Any) -> Any:
                if (
                    expected.created_at != signal.observed_at
                    or expected.updated_at != signal.observed_at
                ):
                    raise ValueError("r6 checkpoint gap time differs")
                return expected

        return _R6CompletePostgresCheckpointBoundary

    resume._create_resume_boundary = create_r6_checkpoint_boundary
    return resume.main(sys.argv[1:] if args is None else args)


if __name__ == "__main__":
    raise SystemExit(main())
