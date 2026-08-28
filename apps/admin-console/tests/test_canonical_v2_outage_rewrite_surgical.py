"""Outage-rewrite surgical guard (fix-outage-rewrite-surgical).

G12/问题14 regression (2026-08-28): all 4 web-view searches timed out on a
transient stall; the LLM's grounded enumeration (48 local + 3 supplemental
candidates) contained a negative fragment and the wholesale outage rewrite
replaced the entire answer with a 79-char system-state message. The guard:
only SHORT essentially-negative answers get rewritten.
"""

from __future__ import annotations

from importlib import import_module

service = import_module("backend.services.canonical_v2_chat")


def test_short_negative_claim_still_rewritten() -> None:
    claim = "未找到该机构的相关信息。"
    rewritten = service._rewrite_lane_outage_answer_text(
        claim, anchor_name="国际先进技术应用推进中心（深圳）"
    )
    assert "网络检索暂不可用" in rewritten
    assert "未找到" not in rewritten


def test_substantive_enumeration_survives_negative_fragment() -> None:
    answer = (
        "深圳具身智能、灵巧手厂商及数据路线如下：自变量机器人采用真机遥操作与"
        "大模型驱动；戴盟机器人以多维触觉数据与外骨骼遥操作采集为核心；跨维智能"
        "构建 Sim2Real 仿真合成数据闭环；源升智能依靠电子皮肤触觉数据与 0.1N "
        "力控积累精细操作数据。以上企业的公开资料中未找到统一的行业数据路线分类，"
        "但各自路线已如上所述。此外，忆海原识采用类脑计算与多传感器融合路线，宇数科技以 UnifoLM 大模型自我学习迭代构建数据闭环，赛博格机器人则依靠穿戴式外骨骼遥操作回传与力位混合算法积累交互数据，各家路线互有侧重。"
    )
    assert (
        service._rewrite_lane_outage_answer_text(
            answer, anchor_name="源升智能机器人（深圳）有限公司"
        )
        == answer
    )


def test_boundary_length_untouched() -> None:
    # Just over the cap with a negative marker: survives.
    long_answer = "深圳具身智能厂商众多，涵盖本体研发、核心零部件、数据服务与平台生态多个环节，" * 6 + "未找到统一分类。"
    assert len(long_answer) > service._OUTAGE_REWRITE_MAX_CHARS
    assert (
        service._rewrite_lane_outage_answer_text(long_answer, anchor_name=None)
        == long_answer
    )
