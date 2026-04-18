#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Build a fixed + weighted-random manual audit manifest for professor Phase A."""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_SAMPLE_SEED = 20260414

_SHENZHEN_INSTITUTION_KEYWORDS = (
    "清华大学深圳国际研究生院",
    "南方科技大学",
    "SUSTech",
    "深圳大学",
    "北京大学深圳研究生院",
    "PKUSZ",
    "深圳理工大学",
    "深圳技术大学",
    "SZTU",
    "哈尔滨工业大学（深圳）",
    "HIT Shenzhen",
    "香港中文大学（深圳）",
    "CUHK-Shenzhen",
    "中山大学（深圳）",
)


class SeedEntry(TypedDict):
    index: int
    label: str
    url: str
    institution: str


class ProfileEntry(TypedDict):
    index: int
    institution: str
    name: str
    profile_url: str
    output_dir: str
    rerun_id: str
    profile: dict[str, Any]


def _default_seed_doc() -> Path:
    return _REPO_ROOT / "docs" / "教授 URL.md"


def _default_output_dir() -> Path:
    return _REPO_ROOT / "logs" / "data_agents" / "professor_phase_a_audit"


def _infer_institution(label: str, url: str) -> str:
    for keyword in _SHENZHEN_INSTITUTION_KEYWORDS:
        if keyword in label:
            return keyword

    host = (urlparse(url).hostname or "").lower()
    host_hints = {
        "sigs.tsinghua.edu.cn": "清华大学深圳国际研究生院",
        "pkusz.edu.cn": "北京大学深圳研究生院",
        "sustech.edu.cn": "南方科技大学",
        "szu.edu.cn": "深圳大学",
        "suat-sz.edu.cn": "深圳理工大学",
        "sztu.edu.cn": "深圳技术大学",
        "hit.edu.cn": "哈尔滨工业大学（深圳）",
        "cuhk.edu.cn": "香港中文大学（深圳）",
        "sysu.edu.cn": "中山大学（深圳）",
    }
    for suffix, institution in host_hints.items():
        if suffix in host:
            return institution
    return "unknown_institution"


def _parse_seed_lines(path: Path) -> list[SeedEntry]:
    entries: list[SeedEntry] = []
    for index, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        url = parts[-1]
        label = " ".join(parts[:-1]) or url
        institution = _infer_institution(label, url)
        entries.append(
            SeedEntry(
                index=index,
                label=label,
                url=url,
                institution=institution,
            )
        )
    return entries


def _school_counts(entries: list[SeedEntry]) -> dict[str, int]:
    return dict(Counter(entry["institution"] for entry in entries))


def _school_counts_from_profile_entries(entries: list[ProfileEntry]) -> dict[str, int]:
    return dict(Counter(entry["institution"] for entry in entries))


def _entry_key(entry: SeedEntry) -> tuple[int, str]:
    return (entry["index"], entry["url"])


def _weighted_school_sample(
    entries: list[SeedEntry],
    sample_size: int,
    *,
    random_seed: int = DEFAULT_SAMPLE_SEED,
    enable_weighting: bool = True,
) -> list[SeedEntry]:
    if sample_size <= 0:
        return []
    if sample_size >= len(entries):
        rng = random.Random(random_seed)
        sampled = entries.copy()
        rng.shuffle(sampled)
        return sampled

    rng = random.Random(random_seed)
    candidates = entries.copy()
    selected: list[SeedEntry] = []

    if not enable_weighting:
        for _ in range(sample_size):
            if not candidates:
                break
            selected.append(candidates.pop(rng.randrange(len(candidates))))
        return selected

    school_buckets: dict[str, list[SeedEntry]] = {}
    for entry in candidates:
        school_buckets.setdefault(entry["institution"], []).append(entry)

    for _ in range(sample_size):
        if not school_buckets:
            break
        school_counts = {
            school: len(items)
            for school, items in school_buckets.items()
            if items
        }
        total_weight = sum(school_counts.values())
        if total_weight <= 0:
            break
        threshold = rng.uniform(0, total_weight)
        cumulative = 0.0
        chosen_school = ""
        for school, weight in school_counts.items():
            cumulative += weight
            if threshold <= cumulative:
                chosen_school = school
                break
        if chosen_school == "":
            chosen_school = next(iter(school_counts))
        bucket = school_buckets[chosen_school]
        selected.append(bucket.pop(rng.randrange(len(bucket))))
        if not bucket:
            school_buckets.pop(chosen_school, None)
    return selected


def _weighted_profile_sample(
    entries: list[ProfileEntry],
    sample_size: int,
    *,
    random_seed: int = DEFAULT_SAMPLE_SEED,
    enable_weighting: bool = True,
) -> list[ProfileEntry]:
    if sample_size <= 0:
        return []
    if sample_size >= len(entries):
        rng = random.Random(random_seed)
        sampled = entries.copy()
        rng.shuffle(sampled)
        return sampled

    rng = random.Random(random_seed)
    candidates = entries.copy()
    selected: list[ProfileEntry] = []

    if not enable_weighting:
        for _ in range(sample_size):
            if not candidates:
                break
            selected.append(candidates.pop(rng.randrange(len(candidates))))
        return selected

    school_buckets: dict[str, list[ProfileEntry]] = {}
    for entry in candidates:
        school_buckets.setdefault(entry["institution"], []).append(entry)

    for _ in range(sample_size):
        if not school_buckets:
            break
        school_counts = {
            school: len(items)
            for school, items in school_buckets.items()
            if items
        }
        total_weight = sum(school_counts.values())
        if total_weight <= 0:
            break
        threshold = rng.uniform(0, total_weight)
        cumulative = 0.0
        chosen_school = ""
        for school, weight in school_counts.items():
            cumulative += weight
            if threshold <= cumulative:
                chosen_school = school
                break
        if chosen_school == "":
            chosen_school = next(iter(school_counts))
        bucket = school_buckets[chosen_school]
        selected.append(bucket.pop(rng.randrange(len(bucket))))
        if not bucket:
            school_buckets.pop(chosen_school, None)
    return selected


def _select_fixed_entries(entries: list[SeedEntry], fixed_per_school: int) -> list[SeedEntry]:
    if fixed_per_school <= 0:
        return []
    selected: list[SeedEntry] = []
    counts: Counter[str] = Counter()
    for entry in entries:
        if counts[entry["institution"]] >= fixed_per_school:
            continue
        selected.append(entry)
        counts[entry["institution"]] += 1
    return selected


def _select_fixed_profile_entries(
    entries: list[ProfileEntry],
    fixed_per_school: int,
) -> list[ProfileEntry]:
    if fixed_per_school <= 0:
        return []
    selected: list[ProfileEntry] = []
    counts: Counter[str] = Counter()
    for entry in entries:
        if counts[entry["institution"]] >= fixed_per_school:
            continue
        selected.append(entry)
        counts[entry["institution"]] += 1
    return selected


def _parse_output_dir_index(output_dir: Path) -> int:
    prefix = output_dir.name.split("_", 1)[0]
    try:
        return int(prefix)
    except ValueError:
        return 0


def _load_profile_entries(
    enriched_dir: Path,
    *,
    start_index: int,
    end_index: int | None,
) -> list[ProfileEntry]:
    entries: list[ProfileEntry] = []
    for enriched_path in sorted(enriched_dir.rglob("enriched_v3.jsonl")):
        output_dir = enriched_path.parent
        index = _parse_output_dir_index(output_dir)
        if index <= 0:
            continue
        if index < start_index:
            continue
        if end_index is not None and index > end_index:
            continue
        rerun_id = output_dir.name
        for line in enriched_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            profile = json.loads(line)
            name = str(profile.get("name") or "").strip()
            institution = str(profile.get("institution") or "").strip()
            if not name or not institution:
                continue
            profile_url = str(
                profile.get("profile_url")
                or profile.get("homepage")
                or profile.get("roster_source")
                or ""
            ).strip()
            entries.append(
                ProfileEntry(
                    index=index,
                    institution=institution,
                    name=name,
                    profile_url=profile_url,
                    output_dir=str(output_dir),
                    rerun_id=rerun_id,
                    profile=profile,
                )
            )
    return entries


def _load_summary_lookup(
    summary_path: Path | None,
) -> tuple[dict[tuple[int, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    if summary_path is None or not summary_path.exists():
        return {}, {}
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    lookup_by_key: dict[tuple[int, str], dict[str, Any]] = {}
    lookup_by_url: dict[str, dict[str, Any]] = {}
    for item in payload.get("results", []):
        try:
            index = int(item.get("index", 0))
        except (TypeError, ValueError):
            index = 0
        url = str(item.get("url") or "")
        if not url:
            continue
        lookup_by_url[url] = item
        if index > 0:
            lookup_by_key[(index, url)] = item
    return lookup_by_key, lookup_by_url


def _filter_entries_to_summary_results(
    entries: list[SeedEntry],
    *,
    summary_lookup_by_key: dict[tuple[int, str], dict[str, Any]],
    summary_lookup_by_url: dict[str, dict[str, Any]],
) -> list[SeedEntry]:
    if not summary_lookup_by_key and not summary_lookup_by_url:
        return entries
    return [
        entry
        for entry in entries
        if _entry_key(entry) in summary_lookup_by_key or entry["url"] in summary_lookup_by_url
    ]


def _build_item(
    entry: SeedEntry,
    *,
    selection_source: str,
    summary_lookup_by_key: dict[tuple[int, str], dict[str, Any]],
    summary_lookup_by_url: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    result = summary_lookup_by_key.get(_entry_key(entry)) or summary_lookup_by_url.get(
        entry["url"],
        {},
    )
    return {
        "audit_id": result.get("rerun_id") or f"audit_{entry['index']:03d}",
        "selection_source": selection_source,
        "index": entry["index"],
        "institution": entry["institution"],
        "label": entry["label"],
        "url": entry["url"],
        "rerun_id": result.get("rerun_id"),
        "output_dir": result.get("output_dir"),
        "machine": {
            "name": result.get("name"),
            "resolved_institution": result.get("resolved_institution"),
            "quality_status": result.get("quality_status"),
            "gate_passed": result.get("gate_passed"),
            "identity_passed": result.get("identity_passed"),
            "paper_backed_passed": result.get("paper_backed_passed"),
            "required_fields_passed": result.get("required_fields_passed"),
            "paper_count": result.get("paper_count"),
            "top_papers_len": result.get("top_papers_len"),
        },
        "manual": {
            "identity_correct": None,
            "paper_matches_judged": 0,
            "paper_matches_correct": 0,
            "notes": "",
        },
    }


def _build_markdown_manifest(manifest: dict[str, Any]) -> str:
    selection_unit = str(manifest.get("selection_unit") or "url")
    unit_label = "Profiles" if selection_unit == "profile" else "URLs"
    candidate_key = "candidate_profiles" if selection_unit == "profile" else "candidate_urls"
    selected_key = "selected_profiles" if selection_unit == "profile" else "selected_urls"
    fixed_key = "fixed_profiles" if selection_unit == "profile" else "fixed_urls"
    random_key = "random_profiles" if selection_unit == "profile" else "random_urls"
    lines = [
        "# Professor Phase A Audit Manifest",
        "",
        "## Batch",
        f"- Seed doc: `{manifest['seed_doc']}`",
        f"- Enriched dir: `{manifest.get('enriched_dir')}`",
        f"- Summary json: `{manifest['summary_json']}`",
        f"- Output dir: `{manifest['output_dir']}`",
        f"- Selection unit: `{selection_unit}`",
        f"- Candidate {unit_label}: `{manifest[candidate_key]}`",
        f"- Selected {unit_label}: `{manifest[selected_key]}`",
        f"- Fixed {unit_label}: `{manifest[fixed_key]}`",
        f"- Random {unit_label}: `{manifest[random_key]}`",
        f"- Sample seed: `{manifest['sample_seed']}`",
        f"- School weighted: `{manifest['school_weighted']}`",
        "",
        "## Items",
    ]
    for item in manifest["items"]:
        machine = item["machine"]
        lines.extend(
            [
                "",
                f"### {item['audit_id']}",
                f"- Selection source: `{item['selection_source']}`",
                f"- Institution: `{item['institution']}`",
                f"- Label: `{item['label']}`",
                f"- URL: `{item['url']}`",
                f"- Machine name: `{machine['name']}`",
                f"- Machine institution: `{machine['resolved_institution']}`",
                f"- Machine quality status: `{machine['quality_status']}`",
                f"- Machine gate passed: `{machine['gate_passed']}`",
                f"- Machine paper count: `{machine['paper_count']}`",
                f"- Machine top papers len: `{machine['top_papers_len']}`",
                f"- Profile selector: `{item.get('profile_selector')}`",
                "- Manual identity correct: [ ] yes  [ ] no",
                "- Manual paper matches judged: `____`",
                "- Manual paper matches correct: `____`",
                "- Notes:",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a fixed + weighted-random Phase A audit manifest."
    )
    parser.add_argument("--seed-doc", type=Path, default=_default_seed_doc())
    parser.add_argument("--summary-json", type=Path, default=None)
    parser.add_argument("--enriched-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=_default_output_dir())
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int, default=None)
    parser.add_argument("--fixed-per-school", type=int, default=1)
    parser.add_argument("--random-sample-size", type=int, default=20)
    parser.add_argument("--sample-seed", type=int, default=DEFAULT_SAMPLE_SEED)
    parser.add_argument("--disable-school-weighting", action="store_true")
    parser.add_argument(
        "--summary-results-only",
        action="store_true",
        help="Limit candidate URLs to entries that appear in the provided summary JSON.",
    )
    parser.add_argument(
        "--profile-level",
        action="store_true",
        help="Build the audit manifest from all profiles under --enriched-dir instead of one item per seed URL.",
    )
    args = parser.parse_args()

    if not args.seed_doc.exists():
        print(json.dumps({"error": f"seed doc not found: {args.seed_doc}"}, ensure_ascii=False))
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    seed_entries = _parse_seed_lines(args.seed_doc)
    if not seed_entries:
        print(json.dumps({"error": "No valid seed entries found"}, ensure_ascii=False))
        return 1

    summary_lookup_by_key, summary_lookup_by_url = _load_summary_lookup(args.summary_json)

    end_index = args.end_index or len(seed_entries)
    if args.profile_level:
        if args.enriched_dir is None or not args.enriched_dir.exists():
            print(
                json.dumps(
                    {"error": "--enriched-dir is required and must exist when --profile-level is set"},
                    ensure_ascii=False,
                )
            )
            return 1
        candidate_profiles = _load_profile_entries(
            args.enriched_dir,
            start_index=args.start_index,
            end_index=end_index,
        )
        if not candidate_profiles:
            print(json.dumps({"error": "No candidate profiles selected"}, ensure_ascii=False))
            return 1

        fixed_profiles = _select_fixed_profile_entries(candidate_profiles, args.fixed_per_school)
        fixed_keys = {
            (
                entry["output_dir"],
                entry["name"],
                entry["profile_url"],
            )
            for entry in fixed_profiles
        }
        remaining_profiles = [
            entry
            for entry in candidate_profiles
            if (
                entry["output_dir"],
                entry["name"],
                entry["profile_url"],
            ) not in fixed_keys
        ]
        random_profiles = _weighted_profile_sample(
            remaining_profiles,
            args.random_sample_size,
            random_seed=args.sample_seed,
            enable_weighting=not args.disable_school_weighting,
        )

        def build_profile_item(entry: ProfileEntry, selection_source: str) -> dict[str, Any]:
            profile = entry["profile"]
            top_papers = profile.get("top_papers") or []
            paper_count = int(profile.get("paper_count") or 0)
            quality_status = str(profile.get("quality_status") or "").strip() or None
            return {
                "audit_id": f"{entry['rerun_id']}__{entry['name']}",
                "selection_source": selection_source,
                "index": entry["index"],
                "institution": entry["institution"],
                "label": entry["name"],
                "url": entry["profile_url"],
                "rerun_id": entry["rerun_id"],
                "output_dir": entry["output_dir"],
                "profile_selector": {
                    "name": entry["name"],
                    "institution": entry["institution"],
                    "profile_url": entry["profile_url"],
                },
                "machine": {
                    "name": entry["name"],
                    "resolved_institution": entry["institution"],
                    "quality_status": quality_status,
                    "gate_passed": quality_status == "ready",
                    "identity_passed": True,
                    "paper_backed_passed": paper_count > 0 or len(top_papers) > 0,
                    "required_fields_passed": bool(str(profile.get("profile_summary") or "").strip()),
                    "paper_count": paper_count,
                    "top_papers_len": len(top_papers),
                },
                "manual": {
                    "identity_correct": None,
                    "paper_matches_judged": 0,
                    "paper_matches_correct": 0,
                    "notes": "",
                },
            }

        items = [build_profile_item(entry, "fixed") for entry in fixed_profiles]
        items.extend(build_profile_item(entry, "random") for entry in random_profiles)

        manifest = {
            "seed_doc": str(args.seed_doc),
            "enriched_dir": str(args.enriched_dir),
            "summary_json": str(args.summary_json) if args.summary_json else None,
            "output_dir": str(args.output_dir),
            "selection_unit": "profile",
            "start_index": args.start_index,
            "end_index": end_index,
            "fixed_per_school": args.fixed_per_school,
            "random_sample_size": args.random_sample_size,
            "sample_seed": args.sample_seed,
            "school_weighted": not args.disable_school_weighting,
            "candidate_profiles": len(candidate_profiles),
            "selected_profiles": len(items),
            "fixed_profiles": len(fixed_profiles),
            "random_profiles": len(random_profiles),
            "candidate_school_counts": _school_counts_from_profile_entries(candidate_profiles),
            "selected_school_counts": _school_counts_from_profile_entries(
                fixed_profiles + random_profiles
            ),
            "items": items,
        }
    else:
        candidate_entries = [
            entry
            for entry in seed_entries
            if args.start_index <= entry["index"] <= end_index
        ]
        if not candidate_entries:
            print(json.dumps({"error": "No candidate seed entries selected"}, ensure_ascii=False))
            return 1

        if args.summary_results_only:
            candidate_entries = _filter_entries_to_summary_results(
                candidate_entries,
                summary_lookup_by_key=summary_lookup_by_key,
                summary_lookup_by_url=summary_lookup_by_url,
            )
            if not candidate_entries:
                print(
                    json.dumps(
                        {"error": "No candidate seed entries matched summary results"},
                        ensure_ascii=False,
                    )
                )
                return 1

        fixed_entries = _select_fixed_entries(candidate_entries, args.fixed_per_school)
        fixed_keys = {_entry_key(entry) for entry in fixed_entries}
        remaining_entries = [
            entry for entry in candidate_entries if _entry_key(entry) not in fixed_keys
        ]
        random_entries = _weighted_school_sample(
            remaining_entries,
            args.random_sample_size,
            random_seed=args.sample_seed,
            enable_weighting=not args.disable_school_weighting,
        )

        items = [
            _build_item(
                entry,
                selection_source="fixed",
                summary_lookup_by_key=summary_lookup_by_key,
                summary_lookup_by_url=summary_lookup_by_url,
            )
            for entry in fixed_entries
        ]
        items.extend(
            _build_item(
                entry,
                selection_source="random",
                summary_lookup_by_key=summary_lookup_by_key,
                summary_lookup_by_url=summary_lookup_by_url,
            )
            for entry in random_entries
        )

        manifest = {
            "seed_doc": str(args.seed_doc),
            "enriched_dir": str(args.enriched_dir) if args.enriched_dir else None,
            "summary_json": str(args.summary_json) if args.summary_json else None,
            "output_dir": str(args.output_dir),
            "selection_unit": "url",
            "start_index": args.start_index,
            "end_index": end_index,
            "fixed_per_school": args.fixed_per_school,
            "random_sample_size": args.random_sample_size,
            "sample_seed": args.sample_seed,
            "school_weighted": not args.disable_school_weighting,
            "candidate_urls": len(candidate_entries),
            "selected_urls": len(items),
            "fixed_urls": len(fixed_entries),
            "random_urls": len(random_entries),
            "candidate_school_counts": _school_counts(candidate_entries),
            "selected_school_counts": _school_counts(
                fixed_entries + random_entries
            ),
            "items": items,
        }

    manifest_path = args.output_dir / "phase_a_audit_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path = args.output_dir / "phase_a_audit_manifest.md"
    markdown_path.write_text(_build_markdown_manifest(manifest), encoding="utf-8")

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"\nManifest saved to: {manifest_path}")
    print(f"Markdown manifest saved to: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
