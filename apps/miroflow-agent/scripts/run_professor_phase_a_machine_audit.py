#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Build a machine-assisted Phase A audit from real URL E2E outputs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.paper.models import ProfessorPaperDiscoveryResult
from src.data_agents.professor.paper_collector import _discover_best_hybrid_result


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_profiles(output_dir: Path) -> list[dict[str, Any]]:
    enriched_path = output_dir / "enriched_v3.jsonl"
    if not enriched_path.exists():
        return []
    return [
        json.loads(line)
        for line in enriched_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _select_best_profile(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        profiles,
        key=lambda item: (
            len(item.get("top_papers", [])),
            item.get("paper_count") or 0,
            item.get("h_index") or 0,
            item.get("citation_count") or 0,
            len(str(item.get("profile_summary") or "")),
        ),
        default={},
    )


def _profile_matches_selector(
    profile: dict[str, Any],
    selector: dict[str, Any],
) -> bool:
    expected_name = str(selector.get("name") or "").strip()
    expected_institution = str(selector.get("institution") or "").strip()
    expected_profile_url = str(selector.get("profile_url") or "").strip()

    actual_name = str(profile.get("name") or "").strip()
    actual_institution = str(profile.get("institution") or "").strip()
    actual_profile_url = str(
        profile.get("profile_url") or profile.get("homepage") or ""
    ).strip()

    if expected_name and actual_name != expected_name:
        return False
    if expected_institution and actual_institution != expected_institution:
        return False
    if expected_profile_url and actual_profile_url != expected_profile_url:
        return False
    return True


def _select_target_profile(
    *,
    profiles: list[dict[str, Any]],
    item: dict[str, Any],
) -> dict[str, Any]:
    selector = item.get("profile_selector")
    if isinstance(selector, dict) and selector:
        for profile in profiles:
            if _profile_matches_selector(profile, selector):
                return profile
    return _select_best_profile(profiles)


def _paper_judged_count(item: dict[str, Any], profile: dict[str, Any]) -> int:
    machine = item.get("machine") or {}
    machine_count = int(machine.get("top_papers_len") or 0)
    profile_count = len(profile.get("top_papers") or [])
    return min(max(machine_count, profile_count), 5)


def _paper_verification(
    *,
    item: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    name = str((profile.get("name") or item.get("machine", {}).get("name") or "")).strip()
    institution = str(
        (
            profile.get("institution")
            or item.get("machine", {}).get("resolved_institution")
            or item.get("institution")
            or ""
        )
    ).strip()
    homepage_url = str(
        (profile.get("profile_url") or profile.get("homepage") or item.get("url") or "")
    ).strip() or None
    judged = _paper_judged_count(item, profile)
    if not name or not institution or judged <= 0:
        return {
            "accepted": False,
            "judged": judged,
            "correct": 0,
            "reason": "missing_identity_or_papers",
            "source": None,
            "school_matched": False,
            "fallback_used": False,
            "name_disambiguation_conflict": False,
        }

    result = _discover_best_hybrid_result(
        name=name,
        name_en=str(profile.get("name_en") or "").strip() or None,
        institution=institution,
        institution_en=None,
        professor_id=str(item.get("audit_id") or name),
        homepage_url=homepage_url,
    )
    if result is None:
        return {
            "accepted": False,
            "judged": judged,
            "correct": 0,
            "reason": "no_verified_paper_match",
            "source": None,
            "school_matched": False,
            "fallback_used": False,
            "name_disambiguation_conflict": False,
        }

    # Mirror production discovery semantics: a returned hybrid result has already
    # passed the weak-result filter, so strong non-school-matched OpenAlex hits
    # remain acceptable as long as they are not fallback/conflict cases.
    accepted = bool(
        result.source == "openalex"
        and not result.fallback_used
        and not result.name_disambiguation_conflict
    )
    return {
        "accepted": accepted,
        "judged": judged,
        "correct": judged if accepted else 0,
        "reason": "accepted" if accepted else "weak_or_fallback_paper_match",
        "source": result.source,
        "school_matched": result.school_matched,
        "fallback_used": result.fallback_used,
        "name_disambiguation_conflict": result.name_disambiguation_conflict,
        "author_id": result.author_id,
        "paper_count": result.paper_count,
    }


def _audit_item(item: dict[str, Any]) -> dict[str, Any]:
    output_dir_value = item.get("output_dir")
    profiles = _load_profiles(Path(output_dir_value)) if output_dir_value else []
    profile = _select_target_profile(profiles=profiles, item=item)
    machine = item.get("machine") or {}
    identity_correct = bool(machine.get("identity_passed"))
    verification = _paper_verification(item=item, profile=profile)

    updated = dict(item)
    updated["manual"] = {
        "identity_correct": identity_correct,
        "paper_matches_judged": verification["judged"],
        "paper_matches_correct": verification["correct"],
        "notes": (
            f"machine_audit:{verification['reason']};"
            f"source={verification.get('source')};"
            f"school_matched={verification.get('school_matched')};"
            f"fallback_used={verification.get('fallback_used')};"
            f"name_conflict={verification.get('name_disambiguation_conflict')}"
        ),
    }
    updated["machine_audit"] = {
        "identity_correct": identity_correct,
        "paper_verification": verification,
        "profile_name": profile.get("name"),
        "profile_institution": profile.get("institution"),
    }
    return updated


def _build_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Professor Phase A Machine Audit",
        "",
        f"- Audit manifest: `{payload['audit_manifest_json']}`",
        f"- Item count: `{payload['item_count']}`",
        "",
        "## Items",
    ]
    for item in payload["items"]:
        manual = item["manual"]
        verification = item["machine_audit"]["paper_verification"]
        lines.extend(
            [
                "",
                f"### {item['audit_id']}",
                f"- Institution: `{item['institution']}`",
                f"- Machine name: `{item.get('machine', {}).get('name')}`",
                f"- Identity correct: `{manual['identity_correct']}`",
                f"- Paper matches judged: `{manual['paper_matches_judged']}`",
                f"- Paper matches correct: `{manual['paper_matches_correct']}`",
                f"- Paper verification accepted: `{verification['accepted']}`",
                f"- Paper verification source: `{verification.get('source')}`",
                f"- Notes: `{manual['notes']}`",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a machine-assisted Phase A audit from real URL E2E outputs."
    )
    parser.add_argument("--audit-manifest-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if not args.audit_manifest_json.exists():
        print(json.dumps({"error": f"audit manifest not found: {args.audit_manifest_json}"}, ensure_ascii=False))
        return 1

    payload = _load_json(args.audit_manifest_json)
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        print(json.dumps({"error": "audit manifest must contain a non-empty items list"}, ensure_ascii=False))
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    audited_items = [_audit_item(item) for item in items]
    report = {
        "audit_manifest_json": str(args.audit_manifest_json),
        "output_dir": str(args.output_dir),
        "item_count": len(audited_items),
        "items": audited_items,
    }

    json_path = args.output_dir / "phase_a_machine_audit.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = args.output_dir / "phase_a_machine_audit.md"
    markdown_path.write_text(_build_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nMachine audit saved to: {json_path}")
    print(f"Markdown machine audit saved to: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
