"""Resume the exact r5 Candidate after its committed domain checkpoint."""

from __future__ import annotations

from datetime import datetime
from importlib import util
from pathlib import Path
import sys
from typing import Any


def _load_resume_module() -> Any:
    path = Path(__file__).with_name("resume_r3_candidate.py")
    spec = util.spec_from_file_location("canonical_v2_s12b_checkpoint_resume", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("checkpoint resume module cannot be loaded")
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(args: list[str] | None = None) -> int:
    resume = _load_resume_module()
    resume.BUILD_AT = datetime.fromisoformat("2026-07-26T10:36:20.560395+00:00")
    resume.EXPECTED_RELEASE_ID = "candidate-s12b-20260726-r5"
    resume.EXPECTED_RUN_ID = "s12b-build-20260726-r5"
    resume.EXPECTED_MANIFEST_SHA256 = (
        "18c0e8835e71f3317979c316355437e76ac5dbb6cc1c77b491b9de515c2f78ec"
    )
    resume.ORIGINAL_STAGING_ROOT = Path(
        "/var/tmp/mirothinker-canonical-v2-s12b/r5/staging"
    )
    resume.EXPECTED_COUNTS = {
        "landing.source_record": 5_561,
        "knowledge.identity_decision": 3_776,
        "knowledge.canonical_decision": 21_993,
        "knowledge.domain_projection_manifest": 1,
        "knowledge.relationship_projection_run": 0,
        "publish.active_release": 0,
    }
    return resume.main(sys.argv[1:] if args is None else args)


if __name__ == "__main__":
    raise SystemExit(main())
