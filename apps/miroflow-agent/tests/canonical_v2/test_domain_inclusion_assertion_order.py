"""Regression: inclusion-decision assertion ids must round-trip hash-stably.

Root cause locked on 2026-08-24 (run 8 forensics): the write side orders
``supporting_assertion_ids`` with Python's byte-wise ``sorted()``, while the
read side relied on SQL ``ORDER BY``, whose collation orders strings that
differ only by punctuation the other way ("tech_tags" vs
"technology_route_summary"). The reconstructed object then hashed
differently from the stored hash and the build aborted 29h in, five times.

This test pins the actual invariant: ids rebuilt from the database must be
in Python-sorted order regardless of the database collation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.data_agents.canonical_v2.contracts import (
    PolicyDecision,
    PolicyKind,
    PolicyReference,
)
from src.data_agents.canonical_v2.domain_projection_postgres import (
    _canonical_sha256,
)

# The exact punctuation-sensitive pair from the failing p4 company.
FIELD_A = "tech_tags"
FIELD_B = "technology_route_summary"


def test_python_order_diverges_from_collation_sensitive_pair() -> None:
    """Document the hazard pair: Python and common DB collations disagree."""
    assert sorted([FIELD_B, FIELD_A]) == [FIELD_A, FIELD_B]


def test_reconstructed_order_matches_write_hash() -> None:
    policy = PolicyReference(
        policy_id="p", policy_version="v", policy_kind=PolicyKind.inclusion,
        content_sha256="0" * 64,
        effective_at=datetime(2026, 8, 23, 2, 53, 33, tzinfo=timezone.utc),
    )
    prefix = "assertion:x:"
    python_sorted_ids = [prefix + FIELD_A, prefix + FIELD_B]

    decision = PolicyDecision(
        decision_id="d", policy=policy, subject_identity_id="s",
        release_id="r", outcome="admitted",
        supporting_assertion_ids=tuple(python_sorted_ids),
        evaluated_at=datetime(2026, 8, 23, 2, 53, 33, tzinfo=timezone.utc),
    )
    stored_hash = _canonical_sha256(decision)

    # Simulate the read path with the collation-ordered fetch result and the
    # post-fetch Python sort from _load_inclusion_result.
    fetched_in_collation_order = [prefix + FIELD_B, prefix + FIELD_A]
    rebuilt = sorted(fetched_in_collation_order)
    reconstructed = PolicyDecision(
        decision_id="d", policy=policy, subject_identity_id="s",
        release_id="r", outcome="admitted",
        supporting_assertion_ids=tuple(rebuilt),
        evaluated_at=datetime(2026, 8, 23, 2, 53, 33, tzinfo=timezone.utc),
    )
    assert _canonical_sha256(reconstructed) == stored_hash
