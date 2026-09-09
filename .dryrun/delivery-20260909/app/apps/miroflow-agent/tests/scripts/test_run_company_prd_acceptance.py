from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path
from typing import Any

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "run_company_prd_acceptance.py"
)


def _import_cli():
    spec = importlib.util.spec_from_file_location("run_company_prd_acceptance", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _SequencedConn:
    def __init__(self, result_sets: list[list[dict[str, Any]]]):
        self._result_sets = list(result_sets)
        self.calls: list[tuple[str, Any]] = []

    def execute(self, query: str, params: Any = None) -> _FakeResult:
        self.calls.append((" ".join(query.split()), params))
        if not self._result_sets:
            raise AssertionError("Unexpected execute call")
        return _FakeResult(self._result_sets.pop(0))


def test_build_summary_candidate_uses_xlsx_material_without_fabricating() -> None:
    cli = _import_cli()
    candidate = cli.build_summary_candidate(
        {
            "canonical_name": "深圳示例科技",
            "hq_city": "深圳市",
            "industry": "人工智能",
            "sub_industry": "医疗AI",
            "business": "心电诊断平台研发商",
            "description": "公司专注 AI 心电智能筛查和远程诊断服务。",
            "products_json": [{"name": "CareLink"}],
            "scenarios_json": [{"name": "远程心电诊断"}],
            "reported_patent_count": 3,
        }
    )

    assert candidate.blocker is None
    assert candidate.profile_summary
    assert "深圳示例科技" in candidate.profile_summary
    assert "CareLink" in candidate.profile_summary
    assert candidate.technology_route_summary
    assert "远程心电诊断" in candidate.technology_route_summary


def test_build_summary_candidate_blocks_sparse_material() -> None:
    cli = _import_cli()
    candidate = cli.build_summary_candidate(
        {
            "canonical_name": "深圳示例科技",
            "products_json": [],
            "scenarios_json": [],
        }
    )

    assert candidate.blocker == "insufficient_trusted_material"
    assert candidate.profile_summary is None
    assert candidate.technology_route_summary is None


def test_run_audit_reports_shape_and_missing_summary_candidates() -> None:
    cli = _import_cli()
    conn = _SequencedConn(
        [
            [
                {
                    "resolved_companies": 1,
                    "missing_profile_summary": 1,
                    "missing_technology_route_summary": 1,
                    "ready_companies": 1,
                    "needs_review_companies": 0,
                }
            ],
            [
                {
                    "product_rows": 1,
                    "companies_with_products": 1,
                    "scenario_rows": 1,
                    "companies_with_scenarios": 1,
                    "signal_rows": 0,
                    "companies_with_signals": 0,
                    "news_rows": 0,
                    "companies_with_news": 0,
                }
            ],
            [{"table_name": "product", "status": "ready", "row_count": 1}],
            [
                {
                    "products_without_evidence": 0,
                    "scenarios_without_evidence": 0,
                    "signal_events_without_source": 0,
                }
            ],
            [
                {
                    "company_id": "COMP-1",
                    "canonical_name": "深圳示例科技",
                    "hq_city": "深圳",
                    "industry": "人工智能",
                    "sub_industry": "医疗AI",
                    "business": "心电诊断平台研发商",
                    "description": "公司专注 AI 心电智能筛查。",
                    "products_json": [{"name": "CareLink"}],
                    "scenarios_json": [{"name": "远程心电诊断"}],
                    "reported_patent_count": 3,
                }
            ],
        ]
    )

    payload = cli.run_audit(conn, sample_limit=5)

    assert payload["summary_counts"]["missing_profile_summary"] == 1
    assert payload["business_counts"]["companies_with_products"] == 1
    assert payload["review_counts"][0]["table_name"] == "product"
    sample = payload["missing_summary_samples"][0]
    assert sample["company_id"] == "COMP-1"
    assert sample["candidate"]["blocker"] is None
    assert "CareLink" in sample["candidate"]["profile_summary"]


def test_score_top5_uses_query_level_hit_rate(tmp_path: Path) -> None:
    cli = _import_cli()
    label_csv = tmp_path / "top5.csv"
    rows = [
        {"query_id": "q1", "query": "做手术机器人", "rank": "1", "human_label": "miss"},
        {"query_id": "q1", "query": "做手术机器人", "rank": "2", "human_label": "hit"},
        {"query_id": "q2", "query": "做储能", "rank": "1", "human_label": "partial"},
        {"query_id": "q2", "query": "做储能", "rank": "2", "human_label": "miss"},
    ]
    with label_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    payload = cli.score_top5(label_csv)

    assert payload["query_count"] == 2
    assert payload["hit_queries"] == 1
    assert payload["top5_hit_rate"] == 0.5
    assert payload["top1_hits"] == 0
    assert payload["partial_results"] == 1
    assert payload["top5_prd_pass"] is False


def test_candidate_pool_query_set_is_ten_query_pilot() -> None:
    cli = _import_cli()

    assert len(cli.COMPANY_CANDIDATE_POOL_QUERIES) == 10
    assert cli.COMPANY_CANDIDATE_POOL_QUERIES[0]["query"] == "深圳做手术机器人的公司"
    assert "手术机器人" in cli.COMPANY_CANDIDATE_POOL_QUERIES[0]["terms"]


def test_rank_lexical_candidates_uses_products_and_scenarios() -> None:
    cli = _import_cli()
    rows = [
        {
            "company_id": "COMP-1",
            "canonical_name": "深圳示例科技",
            "products_json": [{"name": "AI心电诊断平台"}],
            "scenarios_json": [{"name": "远程心电诊断"}],
        },
        {
            "company_id": "COMP-2",
            "canonical_name": "深圳无关科技",
            "description": "工业软件服务商",
            "products_json": [],
            "scenarios_json": [],
        },
    ]

    ranked = cli._rank_lexical_candidates(rows, ["心电诊断", "远程心电"], limit=5)

    assert ranked == [
        {
            "company_id": "COMP-1",
            "lexical_score": 2,
            "matched_terms": ["心电诊断", "远程心电"],
        }
    ]


def test_score_candidate_pool_separates_corpus_gap_from_retrieval_failure(
    tmp_path: Path,
) -> None:
    cli = _import_cli()
    label_csv = tmp_path / "candidate_pool.csv"
    rows = [
        {
            "query_id": "q1",
            "query": "深圳做心电 AI 诊断的公司",
            "retrieval_rank": "1",
            "in_retrieval_top5": "yes",
            "human_relevance_label": "hit",
            "query_answerability": "answerable",
        },
        {
            "query_id": "q2",
            "query": "深圳做量子通信的公司",
            "retrieval_rank": "1",
            "in_retrieval_top5": "yes",
            "human_relevance_label": "miss",
            "query_answerability": "corpus_gap",
        },
        {
            "query_id": "q3",
            "query": "深圳做平面超透镜的公司",
            "retrieval_rank": "8",
            "in_retrieval_top5": "no",
            "human_relevance_label": "hit",
            "query_answerability": "answerable",
        },
    ]
    with label_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    payload = cli.score_candidate_pool(label_csv)

    assert payload["query_count"] == 3
    assert payload["answerable_queries"] == 2
    assert payload["corpus_gap_queries"] == 1
    assert payload["top5_hit_queries_on_answerable"] == 1
    assert payload["top5_hit_rate_on_answerable"] == 0.5
    assert payload["candidate_pool_hit_queries"] == 2
    assert payload["retrieval_missed_answerable_queries"][0]["query_id"] == "q3"


def test_score_duplicate_pairs_excludes_uncertain(tmp_path: Path) -> None:
    cli = _import_cli()
    label_csv = tmp_path / "dedup.csv"
    rows = [
        {"system_prediction": "duplicate", "human_label": "duplicate"},
        {"system_prediction": "duplicate", "human_label": "not_duplicate"},
        {"system_prediction": "not_duplicate", "human_label": "not_duplicate"},
        {"system_prediction": "not_duplicate", "human_label": "uncertain"},
    ]
    with label_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    payload = cli.score_duplicate_pairs(label_csv)

    assert payload["labeled_rows"] == 3
    assert payload["uncertain_or_unlabeled_rows"] == 1
    assert payload["true_positive"] == 1
    assert payload["false_positive"] == 1
    assert payload["true_negative"] == 1
    assert payload["false_negative"] == 0
    assert payload["accuracy"] == 2 / 3


def test_review_policy_publishes_high_trust_needs_review_only() -> None:
    cli = _import_cli()

    assert cli.source_fact_is_default_visible(
        quality_status="needs_review",
        confidence=0.72,
        source_tiers=["xlsx"],
    )
    assert cli.source_fact_is_default_visible(
        quality_status="ready",
        confidence=None,
        source_tiers=[],
    )
    assert not cli.source_fact_is_default_visible(
        quality_status="needs_review",
        confidence=0.95,
        source_tiers=["generic_web"],
    )
    assert not cli.source_fact_is_default_visible(
        quality_status="rejected",
        confidence=1,
        source_tiers=["official_site"],
    )


def test_refresh_dry_run_selects_explicit_ids_without_writes() -> None:
    cli = _import_cli()
    conn = _SequencedConn(
        [
            [
                {
                    "company_id": "COMP-1",
                    "canonical_name": "深圳示例科技",
                    "last_refreshed_at": None,
                    "missing_profile_summary": False,
                    "missing_technology_route_summary": False,
                }
            ]
        ]
    )

    payload = cli.run_refresh_dry_run(
        conn,
        explicit_ids=["COMP-1"],
        stale_days=30,
        limit=10,
    )

    assert payload["dry_run"] is True
    assert payload["selection_reasons"] == ["explicit_company_ids"]
    assert payload["selected_company_ids"] == ["COMP-1"]
    assert payload["writes"] == {"business_fact_tables": 0, "vectors": 0}
    assert "c.company_id = ANY" in conn.calls[0][0]


def test_duplicate_candidate_export_shape() -> None:
    cli = _import_cli()
    rows: list[dict[str, Any]] = [
        {
            "company_id": "COMP-1",
            "canonical_name": "深圳示例科技有限公司",
            "industry": "AI",
            "website": "https://example.com",
        },
        {
            "company_id": "COMP-2",
            "canonical_name": "深圳示例科技",
            "industry": "AI",
            "website": "https://example.com",
        },
        {
            "company_id": "COMP-3",
            "canonical_name": "深圳无关制造有限公司",
            "industry": "制造",
            "website": "https://other.example.com",
        },
    ]

    pairs = cli._build_duplicate_candidates(rows, limit=2)

    assert pairs
    assert set(pairs[0]) >= {
        "left_company_id",
        "right_company_id",
        "system_similarity",
        "system_prediction",
        "human_label",
    }
