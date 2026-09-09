from __future__ import annotations

from pathlib import Path
import re
from unittest.mock import MagicMock, patch

from src.data_agents.paper import canonical_writer
from src.data_agents.paper.canonical_writer import upsert_paper
from src.data_agents.paper.quality_promotion import PromotionDecision


RUN_ID = "11111111-1111-1111-1111-111111111111"
READY_SUMMARY_ZH = (
    "该论文围绕多模态知识检索和科研数据治理展开研究，提出了面向复杂查询的结构化证据组织方法。"
    "论文结合语义表示、实体链接和可追溯引用机制，提升了跨来源数据融合后的检索准确性。"
    "实验部分覆盖真实科研场景中的作者、机构、论文和专利线索，展示了方法在开放环境下的稳定性。"
    "研究还讨论了质量门控、摘要生成和证据审计之间的关系，为科研信息服务提供了可复用实现路径。"
)


def _conn(existing_status: str | None = None) -> MagicMock:
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (
        None if existing_status is None else {"quality_status": existing_status}
    )
    return conn


def _upsert_ready_worthy(
    conn: MagicMock,
    *,
    quality_status: str = "needs_enrichment",
) -> tuple[str, tuple[object, ...]]:
    upsert_paper(
        conn,
        title_clean="Unified Quality Gates for Scientific Search",
        title_raw="Unified Quality Gates for Scientific Search",
        doi=None,
        arxiv_id=None,
        openalex_id="W123456",
        semantic_scholar_id=None,
        year=2026,
        venue="Journal of Data Quality",
        abstract_clean="A study of quality gates for scientific search systems.",
        authors_display="Ada Zhang, Bo Li",
        citation_count=3,
        canonical_source="openalex",
        run_id=RUN_ID,
        title_resolution_source="openalex",
        quality_status=quality_status,
        summary_zh=READY_SUMMARY_ZH,
    )
    insert_call = conn.execute.call_args_list[1]
    return insert_call.args[0], insert_call.args[1]


def _insert_param(sql: str, params: tuple[object, ...], column: str) -> object:
    match = re.search(r"INSERT INTO paper\s*\((?P<columns>.*?)\)\s*VALUES", sql, re.S)
    assert match is not None
    columns = [
        raw_column.strip()
        for raw_column in match.group("columns").split(",")
        if raw_column.strip()
    ]
    return params[columns.index(column)]


def test_upsert_paper_calls_promotion_state_machine_and_persists_return() -> None:
    conn = _conn(existing_status="needs_enrichment")

    with patch(
        "src.data_agents.paper.canonical_writer.evaluate_paper_promotion",
        return_value=PromotionDecision("ready", "all_required_fields_present"),
    ) as evaluate:
        sql, params = _upsert_ready_worthy(conn)

    evaluate.assert_called_once()
    assert evaluate.call_args.kwargs["current_status"] == "needs_enrichment"
    assert evaluate.call_args.kwargs["signals"].has_summary_zh is True
    assert _insert_param(sql, params, "quality_status") == "ready"


def test_ready_worthy_paper_promotes_to_ready_at_write_time() -> None:
    sql, params = _upsert_ready_worthy(_conn())

    assert _insert_param(sql, params, "quality_status") == "ready"


def test_rejected_paper_stays_rejected_at_write_time() -> None:
    sql, params = _upsert_ready_worthy(_conn(existing_status="rejected"))

    assert _insert_param(sql, params, "quality_status") == "rejected"


def test_paper_writer_has_no_quality_status_inline_case() -> None:
    source = Path(canonical_writer.__file__).read_text(encoding="utf-8")

    assert re.search(r"quality_status\s*=\s*CASE", source) is None
