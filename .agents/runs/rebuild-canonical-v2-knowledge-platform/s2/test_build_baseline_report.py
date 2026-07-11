from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from typing import Any
import unittest


ROOT = Path(__file__).parent


def _load(name: str) -> Any:
    path = ROOT / name
    if not path.exists():
        raise AssertionError(f"{name} is not implemented")
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


class OfflineIntentMeasurementTests(unittest.TestCase):
    def test_measurement_scores_actual_classifier_and_hashes_fixture(self) -> None:
        measure = _load("measure_offline_intent.py")
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "intent.jsonl"
            fixture.write_text(
                '\n'.join(
                    [
                        json.dumps({"id": "Q001", "query": "exact", "expected_type": "A"}),
                        json.dumps({"id": "Q002", "query": "topic", "expected_type": "B"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = measure.measure_intent(
                fixture,
                lambda query: {"type": {"exact": "A", "topic": "G"}[query]},
                git_commit="abc123",
                measured_at="2026-07-11T12:00:00Z",
                command="offline-test",
            )

            self.assertEqual(result["cases"], 2)
            self.assertEqual(result["correct"], 1)
            self.assertEqual(result["accuracy"], 0.5)
            self.assertEqual(result["mismatches"][0]["id"], "Q002")
            self.assertEqual(
                result["fixture_sha256"], hashlib.sha256(fixture.read_bytes()).hexdigest()
            )
            self.assertEqual(result["status"], "measured_current")


class BaselineReportBuilderTests(unittest.TestCase):
    def test_report_keeps_current_legacy_and_unavailable_metrics_separate(self) -> None:
        builder = _load("build_baseline_report.py")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory = root / "source-inventory.json"
            corpus = root / "corpus-manifest.json"
            intent = root / "offline-intent.json"
            _write_json(
                inventory,
                {
                    "captured_at": "2026-07-11T07:11:30Z",
                    "sources": [{"kind": "milvus_lite_original", "bytes": 10}],
                    "recovery_database_snapshot": {
                        "databases": [
                            {
                                "name": "recovery",
                                "public_core_counts": {
                                    "professor": 0,
                                    "company": 0,
                                    "paper": 0,
                                    "patent": 0,
                                    "professor_paper_link": 0,
                                },
                            }
                        ],
                        "salvage": {
                            "paper": {"distinct_ids": 99437},
                            "professor_paper_link": {
                                "distinct_ids": 101158,
                                "distinct_professor_ids": 2826,
                                "distinct_paper_ids": 97285,
                            },
                            "field_errors": {"total": 20773},
                        },
                    },
                },
            )
            _write_json(
                corpus,
                {
                    "schema_version": "corpus-v1",
                    "approval_state": "pending_user_acceptance",
                },
            )
            _write_json(
                intent,
                {
                    "status": "measured_current",
                    "cases": 100,
                    "correct": 100,
                    "accuracy": 1.0,
                    "fixture_sha256": "fixture-hash",
                    "git_commit": "abc123",
                },
            )
            legacy_values = {
                "recall": {"total_hit": 30, "total_req": 41, "pct": 73.1707, "rows": []},
                "precision": {"rows": [], "total_unsourced_web": 0},
                "precision_labels": {
                    "_status": "SCAFFOLD",
                    "cases": [{"qid": "4", "true_positives": []}],
                },
                "latency": {"rows": [], "overall_p95": 5.7088, "slo_verdict": "PASS"},
                "answer": {"head_cases": 19, "true_accuracy": "10/19 (53%)", "results": []},
                "multi_turn": {
                    "summary": {
                        "scored_cases": 18,
                        "passed_cases": 1,
                        "required_recall": "6/37 (16%)",
                    },
                    "rows": [],
                },
                "golden_answer": {"rows": []},
                "full_testset": {"head_cases": 19, "rows": []},
            }
            legacy_paths: dict[str, Path] = {}
            for name, value in legacy_values.items():
                path = root / f"{name}.json"
                _write_json(path, value)
                legacy_paths[name] = path

            report = builder.build_report(
                inventory,
                corpus,
                intent,
                legacy_paths,
                git_commit="abc123",
            )

            self.assertEqual(report["dimensions"]["intent"]["current"]["status"], "measured_current")
            self.assertEqual(report["dimensions"]["recall_at_k"]["current"]["status"], "unavailable")
            self.assertEqual(report["dimensions"]["recall_at_k"]["legacy"][0]["status"], "legacy")
            self.assertEqual(report["dimensions"]["recall_at_k"]["legacy"][0]["hit"], 30)
            self.assertEqual(report["dimensions"]["latency"]["legacy"][0]["p95_seconds"], 5.7088)
            self.assertEqual(
                report["dimensions"]["precision_at_k_and_rank"]["legacy"][0][
                    "label_status"
                ],
                "SCAFFOLD",
            )
            self.assertEqual(
                report["dimensions"]["answer_support_and_citation"]["legacy"][2][
                    "required_recall"
                ],
                None,
            )
            self.assertEqual(
                report["dimensions"]["provider_calls_and_cost"]["current"]["status"],
                "unavailable",
            )
            self.assertFalse(report["comparison_policy"]["cross_population_comparison_allowed"])

    def test_report_contains_every_required_dimension_and_input_hash(self) -> None:
        builder = _load("build_baseline_report.py")
        self.assertEqual(
            builder.REQUIRED_DIMENSIONS,
            {
                "coverage_and_reach",
                "recall_at_k",
                "precision_at_k_and_rank",
                "intent",
                "answer_support_and_citation",
                "universal_web",
                "multi_turn",
                "latency",
                "provider_calls_and_cost",
            },
        )


if __name__ == "__main__":
    unittest.main()
