"""Unit tests for parse_testset (no live xlsx needed; uses a synthetic seed)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from parse_testset import parse_workbook, _derive_required, _derive_forbidden


def test_derive_required_strips_marker_and_normalizes_to_short_core():
    kp = "深圳市普渡科技股份有限公司；上海开普勒机器人有限公司；云迹科技 需要在回答结果"
    req = _derive_required(kp)
    assert "普渡" in req  # normalized short core, not the long form
    assert "云迹" in req
    assert "需要在回答结果" not in req
    assert not any("股份有限公司" in r for r in req)  # suffix stripped


def test_derive_forbidden_extracts_after_marker():
    kp = "不应该出现深圳智航无人机有限公司"
    forb = _derive_forbidden(kp)
    assert "深圳智航无人机有限公司" in forb


def test_parse_skips_header_rows_and_groups_multi_turn(tmp_path):
    # build a tiny synthetic xlsx mirroring the real structure
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["问题1", "答案", "关键点"])
    ws.append(["介绍清华的丁文伯", "丁文伯教授信息...", "获取知识库中的信息"])
    ws.append(["他是否有参与哪些企业的创立", "丁文伯参与创立...", "需要识别这里的他指的是丁文伯"])
    ws.append(["问题2", "答案", "关键点"])
    ws.append(["中国有哪些成熟的酒店送餐机器人供应商", "普渡;云迹...", "普渡；云迹 需要在回答结果"])
    p = tmp_path / "seed.xlsx"
    wb.save(p)
    cases = parse_workbook(p)
    assert len(cases) == 3  # 2 from 问题1 + 1 from 问题2
    assert cases[0]["query"] == "介绍清华的丁文伯"
    assert cases[0]["turn_group"] == "问题1"
    assert cases[0]["is_head_turn"] is True
    assert cases[1]["is_head_turn"] is False
    assert cases[1]["coref_needs_label"] is True  # "他" followup
    assert cases[2]["required_entities"]  # non-empty after derive
