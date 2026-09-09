from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest


S12F = Path(__file__).resolve().parent
EXPECTED_BATCHES = sorted(
    [
        "s12a-released-objects-full-v1",
        "s12c-r7-company-knowledge-v1",
        "s12c-r7-company-workbook-supplement-v1",
        "s12c-r7-paper-identifiers-v1",
        "s12c-r7-patent-identifiers-v1",
        "s12c-r7-professor-company-roles-v1",
        "s12e-professor-backfill-v1",
    ]
)


def _load(name: str, filename: str) -> ModuleType:
    path = S12F / filename
    assert path.is_file(), f"missing requested s12f tool: {filename}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _passing_metrics() -> dict[str, Any]:
    object_counts = {
        "company": 1037,
        "paper": 563,
        "patent": 1931,
        "professor": 1428,
    }
    return {
        "database": {
            "database_name": "miroflow_candidate_s12f_20260801_v1",
            "database_marker": (
                "miroflow:destructive-target:v1:disposable:"
                "miroflow_candidate_s12f_20260801_v1"
            ),
            "transaction_read_only": True,
            "release": {
                "release_id": "candidate-s12f-20260801-v1",
                "build_run_id": "s12f-build-20260801-v1",
                "state": "candidate",
                "manifest_sha256": "a" * 64,
            },
            "object_counts": object_counts,
            "relationship_count": 692,
        },
        "envelope": {
            "release_id": "candidate-s12f-20260801-v1",
            "run_id": "s12f-build-20260801-v1",
            "manifest_sha256": "a" * 64,
            "source_manifest_sha256": (
                "7908db3925c8450bc93aa9543b9c94b7cf37a4bae8f796cf0cdd007ac77c0f97"
            ),
            "source_batch_ids": EXPECTED_BATCHES,
            "object_counts": object_counts,
            "relationship_count": 692,
            "release_verification": {
                "accepted": True,
                "canonical_index_parity": True,
                "missing_points": 0,
                "extra_points": 0,
                "stale_points": 0,
                "cross_release_points": 0,
            },
            "index_target": {
                "root": "/var/tmp/mirothinker-canonical-v2-s12f/index-v1",
                "target_id": "index:candidate-s12f-20260801-v1",
                "release_id": "candidate-s12f-20260801-v1",
                "marker_sha256": (
                    "e4314c15518980aaa75a0069dce14c3857df43b74705ce600c6741af74d49f51"
                ),
            },
            "patent_has_applicant": 121,
        },
        "index": {
            "root": "/var/tmp/mirothinker-canonical-v2-s12f/index-v1",
            "marker_sha256": (
                "e4314c15518980aaa75a0069dce14c3857df43b74705ce600c6741af74d49f51"
            ),
            "snapshot_matches_envelope": True,
        },
        "wang_xueqian": {
            "match_count": 1,
            "canonical_identity_id": "professor-c-6c27ec7bab291ecfc6a3d9f2",
            "institution": "清华大学深圳国际研究生院",
            "department": "数据与信息研究院",
            "title": "教授、博士生导师",
            "research_direction_count": 7,
        },
        "company": {
            "total": 1037,
            "industry_nonempty": 1037,
            "website_nonempty": 625,
            "key_personnel_nonempty": 851,
        },
        "pfedgpa": {
            "match_count": 1,
            "doi": "10.1609/aaai.v39i17.33980",
            "arxiv_id": "2409.05701",
        },
        "patent_dates": {
            "total": 1931,
            "filing_date_nonempty": 1931,
            "publication_date_nonempty": 1931,
        },
        "patent_has_applicant": {
            "count": 121,
            "decision_kinds": ["typed"],
            "relationship_type_versions": ["canonical-v2-relationship-v1"],
        },
        "pollution": {"count": 0, "rows": []},
        "reversed_emails": {"count": 0, "rows": []},
        "backfill_merge": {
            "stats": {
                "records_seen": 16,
                "records_merged": 16,
                "records_unmatched": 0,
                "fields_merged": 21,
                "fields_kept_existing": 0,
                "fields_unsupported": 31,
                "fields_invalid": 0,
            },
            "field_counts": {"department": 6, "email": 9, "title": 6},
            "selected_lineage_count": 21,
            "unselected_assertion_ids": [],
            "value_mismatches": [],
        },
    }


def test_post_build_acceptance_matrix_passes_and_rejects_department_regression() -> (
    None
):
    verifier = _load("s12f_post_build_verify_test", "post_build_verify.py")
    passing = _passing_metrics()

    checks = verifier.evaluate_metrics(passing)
    assert checks
    assert all(check.ok for check in checks)

    regressed = _passing_metrics()
    regressed["wang_xueqian"]["department"] = "Not supplied by the historical source."
    failed = [
        check.check_id for check in verifier.evaluate_metrics(regressed) if not check.ok
    ]
    assert failed == ["wang_xueqian.department"]


def test_post_build_rejects_database_run_drift() -> None:
    verifier = _load("s12f_post_build_verify_run_test", "post_build_verify.py")
    regressed = _passing_metrics()
    regressed["database"]["release"]["build_run_id"] = "different-run"

    failed = [
        check.check_id for check in verifier.evaluate_metrics(regressed) if not check.ok
    ]
    assert failed == ["database.release.build_run_id"]


def test_post_build_rejects_non_miroflow_dsn_before_connecting() -> None:
    verifier = _load("s12f_post_build_verify_dsn_test", "post_build_verify.py")
    verifier._require_exact_dsn(verifier.DEFAULT_DSN)

    with pytest.raises(verifier.PostBuildAuditError):
        verifier._require_exact_dsn(
            verifier.DEFAULT_DSN.replace("miroflow@", "postgres@")
        )


def test_post_build_rejects_colliding_report_paths(tmp_path: Path) -> None:
    verifier = _load("s12f_post_build_verify_output_test", "post_build_verify.py")
    output = tmp_path / "report"
    report = {
        "status": "pass",
        "summary": {"total": 0, "passed": 0, "failed": 0},
        "checks": [],
        "metrics": {},
    }

    with pytest.raises(verifier.PostBuildAuditError):
        verifier._write_reports(
            json_path=output,
            markdown_path=output,
            report=report,
        )


def test_serving_bundle_generator_rebinds_only_release_identities() -> None:
    generator = _load(
        "s12f_generate_serving_bundle_test", "generate_s12f_serving_bundle.py"
    )
    source = generator._load_source()
    rebound = generator._rebind_source(source, envelope_path=generator.ENVELOPE)

    assert rebound.release_id == generator.RELEASE_ID
    assert rebound.database_name == generator.DATABASE_NAME
    assert rebound.index_root == generator.INDEX_ROOT
    assert rebound.envelope_path == generator.ENVELOPE

    rebound_fields = {
        "bundle_id",
        "release_id",
        "database_name",
        "index_target_id",
        "index_root",
        "envelope_path",
        "content_sha256",
    }
    source_payload = source.model_dump(mode="json")
    output_payload = rebound.model_dump(mode="json")
    assert {
        key for key in source_payload if source_payload[key] != output_payload[key]
    } == rebound_fields


def test_serving_bundle_generator_rejects_tampered_source(
    tmp_path: Path, monkeypatch: Any
) -> None:
    generator = _load(
        "s12f_generate_serving_bundle_source_test", "generate_s12f_serving_bundle.py"
    )
    payload = json.loads(generator.SOURCE.read_text(encoding="utf-8"))
    payload["max_candidates"] += 1
    tampered = tmp_path / "tampered-serving-bundle.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(generator, "SOURCE", tampered)

    with pytest.raises((RuntimeError, ValueError)):
        generator._load_source()


def test_serving_bundle_generator_rejects_invalid_envelope(
    tmp_path: Path, monkeypatch: Any
) -> None:
    generator = _load(
        "s12f_generate_serving_bundle_envelope_test", "generate_s12f_serving_bundle.py"
    )
    envelope = tmp_path / "complete-candidate-build-envelope.json"
    envelope.write_text("{}\n", encoding="utf-8")
    pack_dir = tmp_path / "serving-pack"
    pack_dir.mkdir()
    output = tmp_path / "serving-bundle-s12f.json"
    monkeypatch.setattr(generator, "ENVELOPE", envelope)
    monkeypatch.setattr(generator, "PACK_DIR", pack_dir)
    monkeypatch.setattr(generator, "OUTPUT", output)

    with pytest.raises((RuntimeError, ValueError)):
        generator.main()
    assert not output.exists()


def test_pack_wrapper_runs_pinned_envelope_identity_preflight() -> None:
    wrapper = (S12F / "build_s12f_serving_pack.sh").read_text(encoding="utf-8")
    assert "--envelope-identity-only" in wrapper
