# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_gate_script():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_professor_phase_a_gate.py"
    return _load_module("run_professor_phase_a_gate", script_path)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_phase_a_gate_blocks_when_manual_metrics_are_missing(tmp_path, monkeypatch) -> None:
    module = _load_gate_script()
    summary_path = _write_json(
        tmp_path / "url_e2e_summary.json",
        {
            "sampled_urls": 2,
            "gate_passed_urls": 2,
            "identity_passed_urls": 2,
            "paper_backed_urls": 2,
            "required_fields_passed_urls": 2,
            "quality_ready_urls": 2,
            "degraded_ratio": 0.0,
            "degradation_alerts": {},
            "results": [],
        },
    )
    output_dir = tmp_path / "gate"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--url-summary",
            str(summary_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    code = module.main()
    assert code == 1

    report = json.loads((output_dir / "phase_a_gate_report.json").read_text(encoding="utf-8"))
    assert report["go_for_phase_b"] is False
    assert "manual_identity_metrics_missing" in report["blocking_reasons"]
    assert "manual_paper_link_metrics_missing" in report["blocking_reasons"]
    assert "retrieval_eval_missing" in report["blocking_reasons"]


def test_phase_a_gate_passes_when_all_thresholds_are_met(tmp_path, monkeypatch) -> None:
    module = _load_gate_script()
    summary_path = _write_json(
        tmp_path / "url_e2e_summary.json",
        {
            "sampled_urls": 2,
            "gate_passed_urls": 2,
            "identity_passed_urls": 2,
            "paper_backed_urls": 2,
            "required_fields_passed_urls": 2,
            "quality_ready_urls": 2,
            "degraded_ratio": 0.5,
            "degradation_alerts": {"TimeoutError": 1},
            "results": [],
        },
    )
    manual_audit_path = _write_json(
        tmp_path / "manual_audit.json",
        {
            "items": [
                {
                    "manual": {
                        "identity_correct": True,
                        "paper_matches_judged": 5,
                        "paper_matches_correct": 5,
                        "notes": "",
                    }
                },
                {
                    "manual": {
                        "identity_correct": True,
                        "paper_matches_judged": 5,
                        "paper_matches_correct": 5,
                        "notes": "",
                    }
                },
            ]
        },
    )
    retrieval_eval_path = _write_json(
        tmp_path / "retrieval_eval.json",
        {
            "query_count": 4,
            "top5_relevant_query_count": 4,
        },
    )
    output_dir = tmp_path / "gate"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--url-summary",
            str(summary_path),
            "--manual-audit-json",
            str(manual_audit_path),
            "--retrieval-eval-json",
            str(retrieval_eval_path),
            "--output-dir",
            str(output_dir),
            "--min-identity-samples",
            "2",
            "--min-paper-link-samples",
            "10",
            "--min-retrieval-query-samples",
            "4",
        ],
    )

    code = module.main()
    assert code == 0

    report = json.loads((output_dir / "phase_a_gate_report.json").read_text(encoding="utf-8"))
    assert report["go_for_phase_b"] is True
    assert report["blocking_reasons"] == []
    assert "degradation_alert:TimeoutError=1" in report["warnings"]
    assert report["metrics"]["manual_identity_accuracy"] == 1.0
    assert report["metrics"]["manual_paper_link_accuracy"] == 1.0
    assert report["metrics"]["retrieval_top5_rate"] == 1.0


def test_phase_a_gate_accepts_result_level_retrieval_metrics(tmp_path, monkeypatch) -> None:
    module = _load_gate_script()
    summary_path = _write_json(
        tmp_path / "url_e2e_summary.json",
        {
            "sampled_urls": 2,
            "gate_passed_urls": 2,
            "identity_passed_urls": 2,
            "paper_backed_urls": 2,
            "required_fields_passed_urls": 2,
            "quality_ready_urls": 2,
            "degraded_ratio": 0.0,
            "degradation_alerts": {},
            "results": [],
        },
    )
    manual_audit_path = _write_json(
        tmp_path / "manual_audit.json",
        {
            "items": [
                {
                    "manual": {
                        "identity_correct": True,
                        "paper_matches_judged": 5,
                        "paper_matches_correct": 5,
                        "notes": "",
                    }
                },
                {
                    "manual": {
                        "identity_correct": True,
                        "paper_matches_judged": 5,
                        "paper_matches_correct": 5,
                        "notes": "",
                    }
                },
            ]
        },
    )
    retrieval_eval_path = _write_json(
        tmp_path / "retrieval_eval.json",
        {
            "query_count": 4,
            "judged_result_count": 20,
            "relevant_result_count": 18,
        },
    )
    output_dir = tmp_path / "gate"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--url-summary",
            str(summary_path),
            "--manual-audit-json",
            str(manual_audit_path),
            "--retrieval-eval-json",
            str(retrieval_eval_path),
            "--output-dir",
            str(output_dir),
            "--min-identity-samples",
            "2",
            "--min-paper-link-samples",
            "10",
            "--min-retrieval-query-samples",
            "4",
        ],
    )

    code = module.main()
    assert code == 0

    report = json.loads((output_dir / "phase_a_gate_report.json").read_text(encoding="utf-8"))
    assert report["go_for_phase_b"] is True
    assert report["metrics"]["retrieval_top5_rate"] == 0.9


def test_phase_a_gate_accepts_exact_target_retrieval_metrics(tmp_path, monkeypatch) -> None:
    module = _load_gate_script()
    summary_path = _write_json(
        tmp_path / "url_e2e_summary.json",
        {
            "sampled_urls": 2,
            "gate_passed_urls": 2,
            "identity_passed_urls": 2,
            "paper_backed_urls": 2,
            "required_fields_passed_urls": 2,
            "quality_ready_urls": 2,
            "degraded_ratio": 0.0,
            "degradation_alerts": {},
            "results": [],
        },
    )
    manual_audit_path = _write_json(
        tmp_path / "manual_audit.json",
        {
            "items": [
                {
                    "manual": {
                        "identity_correct": True,
                        "paper_matches_judged": 5,
                        "paper_matches_correct": 5,
                        "notes": "",
                    }
                },
                {
                    "manual": {
                        "identity_correct": True,
                        "paper_matches_judged": 5,
                        "paper_matches_correct": 5,
                        "notes": "",
                    }
                },
            ]
        },
    )
    retrieval_eval_path = _write_json(
        tmp_path / "retrieval_eval.json",
        {
            "query_count": 4,
            "top5_exact_target_query_count": 4,
            "top5_exact_target_rate": 1.0,
        },
    )
    output_dir = tmp_path / "gate"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--url-summary",
            str(summary_path),
            "--manual-audit-json",
            str(manual_audit_path),
            "--retrieval-eval-json",
            str(retrieval_eval_path),
            "--output-dir",
            str(output_dir),
            "--min-identity-samples",
            "2",
            "--min-paper-link-samples",
            "10",
            "--min-retrieval-query-samples",
            "4",
        ],
    )

    code = module.main()
    assert code == 0

    report = json.loads((output_dir / "phase_a_gate_report.json").read_text(encoding="utf-8"))
    assert report["go_for_phase_b"] is True
    assert report["metrics"]["retrieval_top5_rate"] == 1.0


def test_phase_a_gate_warns_on_duplicate_target_retrieval_queries(tmp_path, monkeypatch) -> None:
    module = _load_gate_script()
    summary_path = _write_json(
        tmp_path / "url_e2e_summary.json",
        {
            "sampled_urls": 2,
            "gate_passed_urls": 2,
            "identity_passed_urls": 2,
            "paper_backed_urls": 2,
            "required_fields_passed_urls": 2,
            "quality_ready_urls": 2,
            "degraded_ratio": 0.0,
            "degradation_alerts": {},
            "results": [],
        },
    )
    manual_audit_path = _write_json(
        tmp_path / "manual_audit.json",
        {
            "items": [
                {
                    "manual": {
                        "identity_correct": True,
                        "paper_matches_judged": 5,
                        "paper_matches_correct": 5,
                        "notes": "",
                    }
                },
                {
                    "manual": {
                        "identity_correct": True,
                        "paper_matches_judged": 5,
                        "paper_matches_correct": 5,
                        "notes": "",
                    }
                },
            ]
        },
    )
    retrieval_eval_path = _write_json(
        tmp_path / "retrieval_eval.json",
        {
            "query_count": 4,
            "top5_exact_target_query_count": 4,
            "top5_exact_target_rate": 1.0,
            "top5_duplicate_target_query_count": 2,
            "top5_duplicate_target_rate": 0.5,
        },
    )
    output_dir = tmp_path / "gate"

    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "script",
            "--url-summary",
            str(summary_path),
            "--manual-audit-json",
            str(manual_audit_path),
            "--retrieval-eval-json",
            str(retrieval_eval_path),
            "--output-dir",
            str(output_dir),
            "--min-identity-samples",
            "2",
            "--min-paper-link-samples",
            "10",
            "--min-retrieval-query-samples",
            "4",
        ],
    )

    code = module.main()
    assert code == 0

    report = json.loads((output_dir / "phase_a_gate_report.json").read_text(encoding="utf-8"))
    assert report["go_for_phase_b"] is True
    assert report["metrics"]["retrieval_duplicate_target_queries"] == 2
    assert "retrieval_duplicate_targets=2" in report["warnings"]
