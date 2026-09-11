"""F4 before/after stage-table comparison (canonical-only view).

The probe's gt_table matches aliases by substring over display names, which
web page titles can false-positive (e.g. 「普渡机器人携手亚朵集团…」). This
script recomputes the stage-3/4/5 columns with canonical-only semantics:
a hit is an eligible candidate whose canonical_id is non-null and whose exact
display_name matches, mapped into the ordered / displayed / payload sequences
by exact name equality.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BEFORE = HERE / "f1b-downstream-trace.json"
AFTER = HERE / "f1b-downstream-trace.after-f4.json"

GT = {
    "g2-t1": ("云迹", "普渡", "开普勒", "擎朗", "九号", "艾唯尔"),
    "g5-t1": ("嘉立创", "深南电路", "一博", "顺易捷", "兴森", "则成", "上达", "精诚达"),
}


def canonical_view(scenario: dict, alias: str) -> dict:
    window = scenario["stage3_window"]
    eligible = window["eligible"]
    ordered_names = window["ordered_names"]
    candidate_limit = window["candidate_limit"]
    # canonical eligible entries whose display_name contains the alias
    canon = [
        (index + 1, entry)
        for index, entry in enumerate(eligible)
        if entry.get("canonical_id") and alias in entry["display_name"]
    ]
    row = {
        "eligible_rank": None,
        "ordered_rank": None,
        "local_seq": None,
        "within_limit": False,
        "displayed_rank": None,
        "payload_rank": None,
    }
    if not canon:
        return row
    eligible_rank, entry = canon[0]
    row["eligible_rank"] = eligible_rank
    name = entry["display_name"]
    positions = [
        index + 1 for index, value in enumerate(ordered_names) if value == name
    ]
    if len(positions) > 1:
        row["ordered_rank"] = f"AMBIGUOUS:{positions}"
        return row
    if not positions:
        return row
    ordered_rank = positions[0]
    row["ordered_rank"] = ordered_rank
    row["within_limit"] = ordered_rank <= candidate_limit
    # local-sequence position: canonical-local candidates up to ordered_rank
    canonical_names = {
        item["display_name"] for item in eligible if item.get("canonical_id")
    }
    row["local_seq"] = sum(
        1 for value in ordered_names[:ordered_rank] if value in canonical_names
    )
    displayed = scenario["stage4_selector"]["displayed_names"]
    payload = scenario["stage5_payload"]["displayed_names"]
    row["displayed_rank"] = next(
        (i + 1 for i, v in enumerate(displayed) if v == name), None
    )
    row["payload_rank"] = next((i + 1 for i, v in enumerate(payload) if v == name), None)
    return row


def lexical_rank(scenario: dict, alias: str) -> int | None:
    names = (
        scenario["stage1_lanes"].get("lexical", {}).get("candidate_names") or []
    )
    return next(
        (i + 1 for i, v in enumerate(names) if alias in v), None
    )


def main() -> None:
    before = {s["id"]: s for s in json.loads(BEFORE.read_text())["scenarios"]}
    after = {s["id"]: s for s in json.loads(AFTER.read_text())["scenarios"]}
    for scenario_id, aliases in GT.items():
        print(f"=== {scenario_id}")
        print(
            f"{'GT':<6} | {'lex':>4} | "
            f"{'bef: elig/ord/loc/disp/pay':>26} | {'aft: elig/ord/loc/disp/pay':>26}"
        )
        for alias in aliases:
            lex = lexical_rank(after[scenario_id], alias)
            b = canonical_view(before[scenario_id], alias)
            a = canonical_view(after[scenario_id], alias)

            def fmt(row: dict) -> str:
                return (
                    f"{row['eligible_rank']}/{row['ordered_rank']}/"
                    f"{row['local_seq']}/{row['displayed_rank']}/"
                    f'{row["payload_rank"]}'
                )

            print(f"{alias:<6} | {str(lex):>4} | {fmt(b):>26} | {fmt(a):>26}")


if __name__ == "__main__":
    main()
