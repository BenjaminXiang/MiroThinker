"""P4 company field-level supplemental merge (fix-p4-company-field-merge).

The whole 6514-record P4 company batch used to be silently skipped
(skip-on-overlap): every rich workbook record shared a name with a thin
retained s12 object, so application_scenarios / team bios / products never
entered the pack. Now overlapping records field-merge: fill empty fields,
replace only recognizable generated route boilerplate, never touch real
values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module

build = import_module(
    "src.data_agents.canonical_v2.knowledge_build_isolated"
)

NOW = datetime(2026, 8, 29, 0, 0, tzinfo=timezone.utc)

BOILERPLATE_ROUTE = (
    "上海开普勒机器人有限公司的技术路线围绕机器人展开。当前重点落在人形机器人。"
    "业务场景集中在通用人形机器人研发与应用。专注于通用人形机器人研发、生产及应用生态。"
)
REAL_SCENARIOS = (
    "智能制造流水线搬运、冲压收料、质量检测，仓储物流快速分拣存储，"
    "安保巡逻、高危作业，酒店餐厅商场服务，科研教育展示与实验"
)
TEAM = "杨华，创始人，1976年生，2000年毕业于内蒙古大学。胡德波，联合创始人&CEO。"
PRODUCT = "先行者K2、K1、S1、D1"


def _merge(existing: dict, fill: dict) -> tuple[dict, int, list]:
    assertions: list = []
    filled = build._p4_company_field_merge(
        existing=existing,
        fill=fill,
        object_id="company-c-test",
        source_record_id="record:test",
        run_id="run:test",
        observed_at=NOW,
        assertions=assertions,
    )
    return existing, filled, assertions


def test_fills_empty_fields_and_replaces_boilerplate_route() -> None:
    existing = {"technology_route_summary": BOILERPLATE_ROUTE}
    _, filled, assertions = _merge(
        existing,
        {
            "technology_route_summary": REAL_SCENARIOS,
            "team_description": TEAM,
            "product_description": PRODUCT,
            "website": "https://www.gotokepler.com",
        },
    )
    assert filled == 4
    assert existing["team_description"] == TEAM
    assert existing["product_description"] == PRODUCT
    assert existing["technology_route_summary"] == REAL_SCENARIOS
    assert len(assertions) == 4
    assert all(a.assertion_id.startswith("assertion:company-c-test:p4fill:") for a in assertions)


def test_never_overwrites_real_values() -> None:
    existing = {
        "technology_route_summary": "自研光基六维力传感器，纳米级形变感知。",
        "team_description": "刘宏斌，董事长，中科院百人计划学者。",
        "website": "https://www.haptron-scientific.com/",
    }
    _, filled, _ = _merge(
        existing,
        {
            "technology_route_summary": REAL_SCENARIOS,
            "team_description": TEAM,
            "website": "https://example.com",
        },
    )
    assert filled == 0
    assert existing["technology_route_summary"].startswith("自研光基")
    assert existing["team_description"].startswith("刘宏斌")


def test_p4_fallback_route_not_written() -> None:
    existing = {"technology_route_summary": BOILERPLATE_ROUTE}
    _, filled, _ = _merge(
        existing, {"technology_route_summary": build._P4_COMPANY_ROUTE_FALLBACK}
    )
    assert filled == 0


def test_generated_route_detector() -> None:
    assert build._p4_company_route_is_generated(BOILERPLATE_ROUTE)
    assert build._p4_company_route_is_generated(None)
    assert build._p4_company_route_is_generated("")
    assert not build._p4_company_route_is_generated(REAL_SCENARIOS)
