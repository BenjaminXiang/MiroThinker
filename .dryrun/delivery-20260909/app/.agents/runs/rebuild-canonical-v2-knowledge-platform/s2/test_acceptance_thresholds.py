from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

import build_acceptance_thresholds as threshold_builder


THRESHOLDS = Path(__file__).with_name("acceptance-thresholds.json")
APPROVED_CANDIDATE_SHA256 = (
    "15a99c284861854b98a4bbfb0653700103f7b3b26e58079296f2c24e4c6c81d0"
)
APPROVAL_STATEMENT = (
    "批准 Task 2.5 阈值候选、corpus ground-truth policy，并接受 S2 tasks 2.1–2.5"
)


class AcceptanceThresholdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not THRESHOLDS.exists():
            raise AssertionError("acceptance-thresholds.json is not implemented")
        cls.document = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
        cls.metrics = {item["id"]: item for item in cls.document["metrics"]}

    def test_prd_minima_are_present_and_not_lowered(self) -> None:
        expected = {
            "intent_accuracy": ("gte", 0.90),
            "professor_top5_relevance": ("gte", 0.85),
            "company_top5_relevance": ("gte", 0.85),
            "paper_top5_relevance": ("gte", 0.85),
            "patent_top5_relevance": ("gte", 0.85),
            "paper_human_summary_quality": ("gte", 4.0),
            "patent_human_summary_quality": ("gte", 4.0),
            "company_semantic_latency_seconds": ("lte", 5.0),
            "context_resolution_seconds": ("lt", 0.5),
            "session_ttl_seconds": ("eq", 1800),
            "company_import_coverage": ("gte", 0.95),
            "company_required_field_completeness": ("eq", 1.0),
            "company_team_structured_availability": ("gte", 0.80),
            "company_dedup_accuracy": ("gte", 0.95),
            "paper_summary_zh_completeness": ("gte", 0.90),
            "paper_summary_text_completeness": ("gte", 0.90),
            "paper_attribution_accuracy": ("gte", 0.90),
            "paper_dedup_accuracy": ("gte", 0.95),
            "patent_import_coverage": ("gte", 0.95),
            "patent_summary_text_completeness": ("gte", 0.90),
            "patent_company_relation_accuracy": ("gte", 0.90),
            "patent_professor_relation_accuracy": ("gte", 0.85),
            "patent_dedup_accuracy": ("gte", 0.95),
        }
        for metric_id, (operator, threshold) in expected.items():
            metric = self.metrics[metric_id]
            self.assertEqual(metric["source_kind"], "prd_minimum")
            self.assertEqual(metric["operator"], operator)
            self.assertEqual(metric["threshold"], threshold)
            self.assertEqual(metric["approval"], "prd_fixed")

        ttft = self.metrics["route_ttft_seconds"]
        self.assertEqual(ttft["target_band"], [5.0, 25.0])
        self.assertEqual(ttft["hard_ceiling"], 25.0)
        self.assertTrue(ttft["below_band_passes"])

    def test_hard_invariants_are_zero_or_complete(self) -> None:
        zero_ids = {
            "original_source_write_attempts",
            "destructive_target_ambiguity_writes",
            "wrong_identity_decisions",
            "invented_recovery_facts",
            "unsupported_material_claims",
            "unsourced_material_web_claims",
            "broken_relationship_references",
            "mixed_release_references",
            "index_parity_deviations",
            "online_direct_canonical_writes",
            "prebackup_rebuild_writes",
            "query_identity_mutations",
            "protected_slot_losses",
            "undisplayed_set_references",
            "unsupported_followup_claims",
        }
        for metric_id in zero_ids:
            metric = self.metrics[metric_id]
            self.assertEqual(metric["source_kind"], "hard_invariant")
            self.assertEqual(metric["operator"], "eq")
            self.assertEqual(metric["threshold"], 0)

        for metric_id in (
            "backup_family_coverage",
            "independent_restore_coverage",
            "material_claim_evidence_coverage",
            "evaluation_trace_completeness",
            "information_request_web_invocation",
        ):
            self.assertEqual(self.metrics[metric_id]["threshold"], 1.0)

    def test_calibrated_metrics_are_path_specific_and_user_approved(self) -> None:
        calibrated = [
            metric
            for metric in self.document["metrics"]
            if metric["source_kind"] == "calibrated"
        ]
        self.assertTrue(calibrated)
        self.assertTrue(
            all(metric["approval"] == "user_approved" for metric in calibrated)
        )
        for domain in ("professor", "company", "paper", "patent"):
            self.assertEqual(self.metrics[f"{domain}_exact_recall_at_5"]["threshold"], 0.95)
            self.assertEqual(self.metrics[f"{domain}_semantic_recall_at_10"]["threshold"], 0.80)
            self.assertEqual(self.metrics[f"{domain}_exact_precision_at_1"]["threshold"], 0.95)
            self.assertEqual(self.metrics[f"{domain}_semantic_ndcg_at_10"]["threshold"], 0.80)

        self.assertEqual(self.metrics["relationship_recall_at_10"]["threshold"], 0.80)
        self.assertEqual(self.metrics["workbook_key_point_coverage"]["threshold"], 0.80)
        self.assertEqual(self.metrics["llm_judge_human_agreement"]["threshold"], 0.80)
        self.assertEqual(self.metrics["intent_per_class_accuracy"]["threshold"], 0.80)
        self.assertEqual(
            self.metrics["intent_per_class_accuracy"]["population"],
            "each A-G class independently",
        )
        self.assertEqual(self.metrics["ordinary_provider_attempts"]["threshold"], 12)
        self.assertEqual(self.metrics["complex_provider_attempts"]["threshold"], 20)
        self.assertEqual(self.metrics["provider_cost_regression_ratio"]["threshold"], 1.20)
        self.assertEqual(
            self.metrics["provider_cost_regression_ratio"]["applicability"],
            "post_initial_accepted_real_provider_baseline",
        )
        self.assertEqual(
            self.metrics["required_relationship_family_scenario_coverage"]["threshold"],
            1.0,
        )
        self.assertEqual(
            self.metrics["required_relationship_family_scenario_coverage"]["operator"],
            "eq",
        )

    def test_prd_sources_resolve_to_precise_existing_lines(self) -> None:
        repo_root = THRESHOLDS.parents[4]
        for metric in self.document["metrics"]:
            if metric["source_kind"] != "prd_minimum":
                continue
            match = re.fullmatch(r"(.+\.md):(\d+)", metric["source"])
            self.assertIsNotNone(match, metric["id"])
            assert match is not None
            source_path = repo_root / match.group(1)
            self.assertTrue(source_path.is_file(), metric["id"])
            line_number = int(match.group(2))
            lines = source_path.read_text(encoding="utf-8").splitlines()
            self.assertLessEqual(line_number, len(lines), metric["id"])
            self.assertTrue(lines[line_number - 1].strip(), metric["id"])

        self.assertNotIn("sample_min", self.metrics["professor_top5_relevance"])
        self.assertEqual(
            self.metrics["intent_accuracy"]["sample_source"],
            "docs/Agentic-RAG-PRD.md:237",
        )

    def test_progress_and_retry_gates_do_not_overrestrict_parallel_lanes(self) -> None:
        progress = self.metrics["complex_progress_signal_coverage"]
        self.assertEqual(progress["source_kind"], "hard_invariant")
        self.assertEqual(progress["operator"], "eq")
        self.assertEqual(progress["threshold"], 1.0)
        retry = self.metrics["supplemental_retrieval_attempts"]
        self.assertEqual(retry["unit"], "supplemental_wave")
        self.assertTrue(retry["multiple_parallel_lanes_allowed"])
        self.assertEqual(
            self.metrics["information_request_web_invocation"]["unit"], "case_rate"
        )

    def test_metric_contract_is_complete_and_does_not_reuse_legacy_values(self) -> None:
        self.assertEqual(self.document["approval_state"], "accepted")
        self.assertEqual(
            self.document["approved_candidate_sha256"], APPROVED_CANDIDATE_SHA256
        )
        approval = self.document["approval_record"]
        self.assertEqual(approval["kind"], "explicit_user_approval")
        self.assertEqual(approval["approved_on"], "2026-07-11")
        self.assertEqual(approval["statement"], APPROVAL_STATEMENT)
        self.assertEqual(
            approval["review_path"],
            ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2/review.md",
        )
        self.assertEqual(
            self.document["corpus_manifest_sha256"],
            "dc7cc10ba08db341a38cc08da1edd2449594120a3861735edfd514b29be46088",
        )
        self.assertFalse(self.document["policy"]["aggregate_score_can_mask_dimension_failure"])
        self.assertFalse(self.document["policy"]["ordinary_incompleteness_is_global_exclusion"])
        self.assertFalse(self.document["policy"]["legacy_values_are_threshold_sources"])
        self.assertTrue(self.document["policy"]["llm_judging_requires_human_calibration"])
        self.assertTrue(self.document["policy"]["unavailable_measurement_blocks_acceptance"])
        self.assertEqual(
            self.document["policy"]["unavailable_scope"],
            "applicable_required_metrics_only",
        )
        for metric in self.document["metrics"]:
            for field in (
                "id",
                "effect",
                "dimension",
                "population",
                "operator",
                "threshold",
                "source_kind",
                "source",
                "rationale",
                "measurement",
                "approval",
            ):
                self.assertIn(field, metric, (metric.get("id"), field))
            self.assertNotEqual(metric["source_kind"], "legacy")

    def test_approval_rejects_threshold_content_not_in_reviewed_candidate(self) -> None:
        accept_candidate = getattr(
            threshold_builder, "accept_threshold_candidate", None
        )
        self.assertIsNotNone(
            accept_candidate,
            "candidate-hash approval binding is not implemented",
        )
        build_pending = getattr(threshold_builder, "build_pending_thresholds", None)
        self.assertIsNotNone(build_pending)
        assert accept_candidate is not None
        assert build_pending is not None

        changed_candidate = build_pending()
        changed_candidate["metrics"][0]["threshold"] = 0.0
        with self.assertRaisesRegex(ValueError, "reviewed candidate SHA-256"):
            accept_candidate(
                changed_candidate,
                approved_candidate_sha256=APPROVED_CANDIDATE_SHA256,
                approval_record={
                    "kind": "explicit_user_approval",
                    "approved_on": "2026-07-11",
                    "statement": APPROVAL_STATEMENT,
                    "review_path": (
                        ".agents/runs/rebuild-canonical-v2-knowledge-platform/s2/review.md"
                    ),
                },
            )

    def test_population_contract_is_honest_about_unmaterialized_samples(self) -> None:
        populations = self.document["population_contract"]
        self.assertEqual(populations["frozen_seed_cases"], 52)
        self.assertFalse(populations["all_required_samples_materialized"])
        self.assertTrue(populations["materialization_required_before_metric_acceptance"])
        self.assertEqual(
            populations["current_domain_case_counts"],
            {"company": 30, "paper": 7, "patent": 11, "professor": 12},
        )
        self.assertEqual(populations["domain_relevance_query_minimum_per_domain"], 50)
        policy = populations["future_population_policy"]
        self.assertTrue(policy["versioned_and_hashed"])
        self.assertTrue(policy["selected_without_candidate_output_knowledge"])
        self.assertTrue(policy["human_review_required"])
        self.assertTrue(policy["missing_population_blocks_owning_metric"])


if __name__ == "__main__":
    unittest.main()
