from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import os
from typing import Any, cast

import pytest
from pydantic import ValidationError

from src.data_agents.canonical_v2.canonical_decision_engine import (
    CurrentFieldSelection,
    canonical_adjudication_input_sha256,
)
from src.data_agents.canonical_v2.contracts import (
    SourceAssertion,
    TemporalComparisonContext,
    TemporalDateValue,
    TemporalInstantValue,
    TemporalRelation,
    compare_temporal_values,
)


NOW = datetime(2026, 7, 13, 10, 30, tzinfo=timezone.utc)


def _assertion(
    *,
    assertion_id: str = "assertion:temporal",
    valid_from: date | datetime | TemporalDateValue | TemporalInstantValue | None,
) -> SourceAssertion:
    return SourceAssertion(
        assertion_id=assertion_id,
        source_record_id="record:temporal",
        source_identity_id="source:temporal",
        subject_entity_type="professor",
        field_path="affiliations.history",
        value={"institution": "Example University"},
        observed_at=NOW,
        valid_from=cast(Any, valid_from),
        assertion_run_id="assertion-run:temporal",
    )


def test_date_only_validity_round_trips_with_an_explicit_precision_discriminator() -> (
    None
):
    assertion = _assertion(valid_from=date(2024, 9, 1))

    assert assertion.valid_from == TemporalDateValue(
        precision="date", value=date(2024, 9, 1)
    )
    assert assertion.model_dump(mode="json")["valid_from"] == {
        "precision": "date",
        "value": "2024-09-01",
    }
    assert SourceAssertion.model_validate_json(assertion.model_dump_json()) == assertion


def test_instant_validity_canonicalizes_offsets_without_changing_precision() -> None:
    shanghai = _assertion(
        valid_from=datetime(
            2024,
            9,
            1,
            8,
            30,
            tzinfo=timezone(timedelta(hours=8)),
        )
    )
    utc = _assertion(valid_from=datetime(2024, 9, 1, 0, 30, tzinfo=timezone.utc))

    assert shanghai.valid_from == utc.valid_from
    assert shanghai.model_dump(mode="json")["valid_from"] == {
        "precision": "instant",
        "value": "2024-09-01T00:30:00Z",
    }


def test_same_lexical_day_with_different_precision_is_not_exact_temporal_equality() -> (
    None
):
    date_value = TemporalDateValue(precision="date", value=date(2024, 9, 1))
    instant_value = TemporalInstantValue(
        precision="instant",
        value=datetime(2024, 9, 1, 0, 0, tzinfo=timezone.utc),
    )

    assert date_value != instant_value
    assert (
        compare_temporal_values(date_value, instant_value)
        is TemporalRelation.indeterminate
    )


def test_cross_precision_comparison_never_reads_an_ambient_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    date_value = TemporalDateValue(precision="date", value=date(2024, 9, 1))
    instant_value = TemporalInstantValue(
        precision="instant",
        value=datetime(2024, 8, 31, 16, 30, tzinfo=timezone.utc),
    )

    original_tz = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    first = compare_temporal_values(date_value, instant_value)
    monkeypatch.setenv("TZ", "UTC")
    second = compare_temporal_values(date_value, instant_value)
    if original_tz is None:
        monkeypatch.delenv("TZ", raising=False)
    else:
        monkeypatch.setenv("TZ", original_tz)

    assert first is TemporalRelation.indeterminate
    assert second is TemporalRelation.indeterminate


def test_explicit_calendar_v1_uses_the_named_half_open_civil_day_for_comparison() -> (
    None
):
    date_value = TemporalDateValue(precision="date", value=date(2024, 9, 1))
    instant_value = TemporalInstantValue(
        precision="instant",
        value=datetime(2024, 8, 31, 16, 30, tzinfo=timezone.utc),
    )
    shanghai = TemporalComparisonContext(
        policy_version="explicit-calendar-v1",
        calendar="gregorian",
        timezone="Asia/Shanghai",
    )
    utc = TemporalComparisonContext(
        policy_version="explicit-calendar-v1",
        calendar="gregorian",
        timezone="UTC",
    )

    assert (
        compare_temporal_values(date_value, instant_value, context=shanghai)
        is TemporalRelation.overlap
    )
    assert (
        compare_temporal_values(date_value, instant_value, context=utc)
        is TemporalRelation.after
    )
    assert date_value.value == date(2024, 9, 1)


def test_precision_participates_in_assertion_identity_and_invalid_tampering_fails() -> (
    None
):
    date_assertion = _assertion(valid_from=date(2024, 9, 1))
    instant_assertion = _assertion(
        valid_from=datetime(2024, 9, 1, 0, 0, tzinfo=timezone.utc)
    )

    date_hash = canonical_adjudication_input_sha256(
        decision_kind="field",
        subject_id="professor:temporal",
        path="affiliations.history",
        assertions=(date_assertion,),
    )
    instant_hash = canonical_adjudication_input_sha256(
        decision_kind="field",
        subject_id="professor:temporal",
        path="affiliations.history",
        assertions=(instant_assertion,),
    )
    assert date_hash != instant_hash

    tampered = date_assertion.model_dump(mode="json")
    tampered["valid_from"]["precision"] = "instant"  # type: ignore[index]
    with pytest.raises(ValidationError, match="valid_from|datetime|timezone"):
        SourceAssertion.model_validate(tampered)


def test_assertions_and_current_selections_share_the_precision_bearing_value() -> None:
    assertion = _assertion(valid_from=date(2024, 9, 1))
    current = CurrentFieldSelection(
        release_id="candidate-s5g-r1",
        canonical_identity_id="professor:temporal",
        field_path=assertion.field_path,
        value=assertion.value,
        decision_id="decision:temporal",
        supporting_assertion_ids=(assertion.assertion_id,),
        valid_from=assertion.valid_from,
    )

    assert isinstance(current.valid_from, TemporalDateValue)
    assert current.valid_from == assertion.valid_from


def test_temporal_contract_rejects_unknown_timezone_and_naive_instants() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        TemporalComparisonContext(
            policy_version="explicit-calendar-v1",
            calendar="gregorian",
            timezone="Not/A-Timezone",
        )
    with pytest.raises(ValidationError, match="timezone"):
        TemporalInstantValue(
            precision="instant",
            value=datetime(2024, 9, 1, 0, 0),
        )
