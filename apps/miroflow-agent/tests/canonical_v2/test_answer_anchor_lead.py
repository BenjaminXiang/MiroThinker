"""G1 T3 form: single mid-text name-drop must trigger correction (RED)."""
from importlib import import_module
s = import_module("src.data_agents.canonical_v2.knowledge_serving_isolated")

ANCHOR = "国际先进技术应用推进中心（深圳）"

def test_mid_text_single_mention_fails():
    # Real G1 T3 shape: colon-terminated city-framed header, anchor once in body.
    answer = (
        "深圳在具身智能领域的布局与进展主要围绕政策规划、平台建设、产业生态"
        "及场景应用四个维度展开，具体进展如下：\n\n**1. 顶层规划与政策落地**\n"
        "深圳市科技创新局已印发行动计划，支持国际先进技术应用推进中心（深圳）"
        "建设具身智能技术试验场，并推动场景应用落地。"
    )
    assert not s._answer_mentions_anchor(answer, ANCHOR)

def test_leading_mention_passes():
    answer = "国际先进技术应用推进中心（深圳）依托粤港澳大湾区数字经济研究院建设，于2025年4月27日正式揭牌。"
    assert s._answer_mentions_anchor(answer, ANCHOR)

def test_recurring_mention_passes():
    answer = "深圳支持多个平台建设。国际先进技术应用推进中心（深圳）是其中之一，承担技术试验场职能；国际先进技术应用推进中心（深圳）还与高校合作。"
    assert s._answer_mentions_anchor(answer, ANCHOR)
