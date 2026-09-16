"""The supplementary publication channel obeys the D0-a cleaning rules.

`_supplementary_field_values` feeds non-selected assertion values into the
published vector content and lookup documents.  Those raw values never pass the
projection cleaning seam, so the publication gate (which audits the built pack)
trips on any placeholder-family value that enters through this channel - e.g.
the build's own fallback sentences
("No dedicated summary was supplied by the full-column workbook source.").

The channel must apply the same single rule set as the projection seam.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[4]
APP_ROOT = REPO_ROOT / "apps/miroflow-agent"
sys.path.insert(0, str(APP_ROOT))

from src.data_agents.canonical_v2.knowledge_build_isolated import (  # noqa: E402
    _supplementary_field_values,
)

PLACEHOLDER_SENTENCE = (
    "No dedicated summary was supplied by the full-column workbook source."
)
GLUE_DAMAGED = (
    "多参数监护仪（如DM-7未找到未找到C,DM-8未找到未找到C系列）、智能自控手术室、"
    "手术吊塔、无影灯、一次性手术包"
)
LEGIT_VALUE = "专注协作机器人与具身智能本体研发"


def _build_results():
    identity_result = SimpleNamespace(
        source_identity_assignments=(
            SimpleNamespace(
                source_identity_id="src-1", canonical_identity_id="company-c-1"
            ),
        )
    )
    decision_result = SimpleNamespace(
        current_fields=(
            SimpleNamespace(
                canonical_identity_id="company-c-1",
                field_path="profile_summary",
                value="选中的简介",
            ),
        ),
        # Supplementary values are alternatives to a selected value for the same
        # field, so every assertion below shares the selected field path.
        field_assertions=(
            SimpleNamespace(
                source_identity_id="src-1",
                field_path="profile_summary",
                value=PLACEHOLDER_SENTENCE,
            ),
            SimpleNamespace(
                source_identity_id="src-1",
                field_path="profile_summary",
                value=GLUE_DAMAGED,
            ),
            SimpleNamespace(
                source_identity_id="src-1",
                field_path="profile_summary",
                value=LEGIT_VALUE,
            ),
        ),
    )
    return identity_result, decision_result


def _supplementary() -> dict[str, dict[str, list[str]]]:
    identity_result, decision_result = _build_results()
    return _supplementary_field_values(
        identity_result=identity_result, decision_result=decision_result
    )


def test_supplementary_channel_drops_unpublishable_values() -> None:
    supplementary = _supplementary()

    values = [
        value
        for field_values in supplementary.get("company-c-1", {}).values()
        for value in field_values
    ]
    assert PLACEHOLDER_SENTENCE not in values
    assert GLUE_DAMAGED not in values
    assert LEGIT_VALUE in values


def test_supplementary_channel_keeps_the_selected_value_out() -> None:
    supplementary = _supplementary()

    assert "选中的简介" not in [
        value
        for field_values in supplementary.get("company-c-1", {}).values()
        for value in field_values
    ]
