"""Multi-value enrichment (G2b/G5): non-selected assertion values widen the
search surface (vector + lexical). All valid values for a field — not just
the decision-selected one — go into embedded_content and lookup_content.
"""

from __future__ import annotations

from importlib import import_module

build = import_module("src.data_agents.canonical_v2.knowledge_build_isolated")


class _FakeAssignment:
    def __init__(self, source: str, canonical: str):
        self.source_identity_id = source
        self.canonical_identity_id = canonical


class _FakeCurrentField:
    def __init__(self, canonical: str, field: str, value: str):
        self.canonical_identity_id = canonical
        self.field_path = field
        self.value = value


class _FakeAssertion:
    def __init__(self, source: str, field: str, value: str):
        self.source_identity_id = source
        self.field_path = field
        self.value = value


class _FakeIdentityResult:
    def __init__(self, assignments):
        self.source_identity_assignments = assignments


class _FakeDecisionResult:
    def __init__(self, current_fields, field_assertions):
        self.current_fields = current_fields
        self.field_assertions = field_assertions


def test_supplementary_values_collected():
    """Three valid industry values → one selected + two supplementary."""
    identity_result = _FakeIdentityResult([
        _FakeAssignment("src-a", "company-1"),
        _FakeAssignment("src-b", "company-1"),
        _FakeAssignment("src-c", "company-1"),
    ])
    decision_result = _FakeDecisionResult(
        current_fields=[
            _FakeCurrentField("company-1", "industry", "人工智能"),
        ],
        field_assertions=[
            _FakeAssertion("src-a", "industry", "人工智能"),    # selected
            _FakeAssertion("src-b", "industry", "互联网"),      # supplementary
            _FakeAssertion("src-c", "industry", "科技企业"),    # supplementary
        ],
    )
    supp = build._supplementary_field_values(
        identity_result=identity_result,
        decision_result=decision_result,
    )
    assert supp == {
        "company-1": {
            "industry": ["互联网", "科技企业"],
        }
    }


def test_supplementary_values_empty_when_single_source():
    """Single-source field → no supplementary (only one value exists)."""
    identity_result = _FakeIdentityResult([
        _FakeAssignment("src-a", "company-1"),
    ])
    decision_result = _FakeDecisionResult(
        current_fields=[
            _FakeCurrentField("company-1", "name", "字节跳动"),
        ],
        field_assertions=[
            _FakeAssertion("src-a", "name", "字节跳动"),
        ],
    )
    supp = build._supplementary_field_values(
        identity_result=identity_result,
        decision_result=decision_result,
    )
    assert supp == {}


def test_supplementary_values_skip_non_string():
    """Non-string values (numbers, objects) are skipped."""
    identity_result = _FakeIdentityResult([
        _FakeAssignment("src-a", "company-1"),
        _FakeAssignment("src-b", "company-1"),
    ])
    decision_result = _FakeDecisionResult(
        current_fields=[],
        field_assertions=[
            _FakeAssertion("src-a", "founded_at", 2012),        # non-string
            _FakeAssertion("src-b", "metadata", {"k": "v"}),     # non-string
        ],
    )
    supp = build._supplementary_field_values(
        identity_result=identity_result,
        decision_result=decision_result,
    )
    assert supp == {}


def test_supplementary_values_dedup():
    """Duplicate values across sources are deduplicated."""
    identity_result = _FakeIdentityResult([
        _FakeAssignment("src-a", "company-1"),
        _FakeAssignment("src-b", "company-1"),
        _FakeAssignment("src-c", "company-1"),
    ])
    decision_result = _FakeDecisionResult(
        current_fields=[
            _FakeCurrentField("company-1", "industry", "AI"),
        ],
        field_assertions=[
            _FakeAssertion("src-a", "industry", "AI"),
            _FakeAssertion("src-b", "industry", "互联网"),
            _FakeAssertion("src-c", "industry", "互联网"),  # duplicate
        ],
    )
    supp = build._supplementary_field_values(
        identity_result=identity_result,
        decision_result=decision_result,
    )
    assert supp == {"company-1": {"industry": ["互联网"]}}
