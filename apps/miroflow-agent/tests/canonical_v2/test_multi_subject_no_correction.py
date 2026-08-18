"""G7 final fault: multi-subject (enumeration) answers are never single-subject corrected."""
from importlib import import_module
s = import_module("src.data_agents.canonical_v2.knowledge_serving_isolated")


class _Receipt:
    soft_context_subject = "深圳国创具身智能机器人有限公司"


class _Result:
    response_mode = "answer"
    enumeration_coverage = None
    context_receipt = _Receipt()
    claims = None


class _Claim:
    def __init__(self, subject_id: str) -> None:
        self.subject_id = subject_id


def test_multi_subject_answer_not_corrected():
    result = _Result()
    result.claims = tuple(_Claim(sid) for sid in ("c1", "c2", "c3", "c4"))
    assert s._anchor_correction_name(result, active_anchor=None) is None


def test_single_subject_answer_still_correctable():
    result = _Result()
    result.claims = (_Claim("c1"), _Claim("c1"))
    assert (
        s._anchor_correction_name(result, active_anchor=None)
        == "深圳国创具身智能机器人有限公司"
    )
