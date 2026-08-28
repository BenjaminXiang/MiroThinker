"""Graded supplemental-budget degradation (fix-web-lane-timeout-and-utf8-truncation).

A receipt that exceeds ONLY max_wall_time_ms means the probes were slow, not
that the data is invalid: the web evidence already fetched stays served
(logged as late). Resource overruns (provider_calls / retries / cost /
attempts) still strip the web lane — those breach the quota contract.
"""

from __future__ import annotations

from src.data_agents.canonical_v2.knowledge_read import (
    SupplementalBudget,
    SupplementalBudgetReceipt,
)
from backend.services.canonical_v2_admin import _budget_receipt_overrun_kind


def _budget() -> SupplementalBudget:
    # Mirrors the serving bundle's supplemental budget (wall 10 s).
    return SupplementalBudget(
        max_wall_time_ms=10_000,
        max_provider_calls=2,
        max_retries=0,
        max_cost_units=16.0,
    )


def _receipt(
    *,
    elapsed_ms: int = 5_000,
    provider_calls: int = 1,
    retry_count: int = 0,
    cost_units: float = 3.5,
    attempt_count: int = 1,
) -> SupplementalBudgetReceipt:
    return SupplementalBudgetReceipt(
        exhausted=False,
        exhaustion_reason=None,
        exhausted_axis=None,
        limit_value=None,
        used_value=None,
        provider_calls=provider_calls,
        retry_count=retry_count,
        elapsed_ms=elapsed_ms,
        cost_units=cost_units,
        attempt_count=attempt_count,
    )


def test_within_budget_has_no_overrun():
    assert _budget_receipt_overrun_kind(_receipt(), _budget()) is None


def test_wall_time_only_overrun_is_time():
    # The production receipts observed 2026-08-28: elapsed 11.4–29.6 s with
    # provider_calls 1/2, retries 0/0, attempts 1 — slow but within quota.
    receipt = _receipt(elapsed_ms=29_611)
    assert _budget_receipt_overrun_kind(receipt, _budget()) == "wall_time"


def test_provider_calls_overrun_is_resource():
    receipt = _receipt(elapsed_ms=29_611, provider_calls=3)
    assert _budget_receipt_overrun_kind(receipt, _budget()) == "resource"


def test_cost_overrun_is_resource():
    receipt = _receipt(elapsed_ms=5_000, cost_units=17.0)
    assert _budget_receipt_overrun_kind(receipt, _budget()) == "resource"


def test_retry_overrun_is_resource():
    receipt = _receipt(elapsed_ms=5_000, retry_count=1)
    assert _budget_receipt_overrun_kind(receipt, _budget()) == "resource"
