# LEGACY (Round 7.5): v2 pipeline runner. Canonical professor data should now
# come from pipeline_v3 + canonical_writer + run_real_e2e_professor_backfill.py.
# Kept for reference; do not use for new data collection.
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sys

# Ensure imports work when running this script directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.professor.pipeline import run_professor_pipeline
from src.data_agents.professor.release import (
    build_professor_release,
    publish_professor_release,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_seed_doc() -> Path:
    return _repo_root() / "docs" / "教授 URL.md"


def _default_output_paths() -> tuple[Path, Path, Path]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = _repo_root() / "logs" / "debug" / f"professor_release_e2e_{timestamp}"
    return (
        output_dir / "professor_records.jsonl",
        output_dir / "released_objects.jsonl",
        output_dir / "report.json",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run professor crawler+release e2e from seed markdown and publish "
            "ProfessorRecord / ReleasedObject JSONL outputs."
        )
    )
    parser.add_argument(
        "--seed-doc",
        type=Path,
        default=_default_seed_doc(),
        help="Path to markdown document containing roster seed URLs.",
    )
    parser.add_argument(
        "--professor-output",
        type=Path,
        default=None,
        help="Output path for ProfessorRecord JSONL.",
    )
    parser.add_argument(
        "--released-output",
        type=Path,
        default=None,
        help="Output path for ReleasedObject JSONL.",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=None,
        help="Output path for JSON report. Use '-' to print report JSON to stdout.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP request timeout in seconds.",
    )
    parser.add_argument(
        "--official-domain-suffix",
        action="append",
        default=["sustech.edu.cn"],
        help=(
            "Allowed official domain suffix. "
            "Can be provided multiple times. Default: sustech.edu.cn."
        ),
    )
    parser.add_argument(
        "--include-external-profiles",
        action="store_true",
        help="Fetch external profile URLs too. Default behavior skips external domains.",
    )
    parser.add_argument(
        "--skip-profile-fetch",
        action="store_true",
        help="Build release objects from roster discovery only, without fetching profile pages.",
    )
    args = parser.parse_args()

    professor_output, released_output, report_output = _default_output_paths()
    if args.professor_output is not None:
        professor_output = args.professor_output
    if args.released_output is not None:
        released_output = args.released_output
    if args.report_output is not None:
        report_output = args.report_output

    if not args.seed_doc.exists():
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "seed_document": str(args.seed_doc),
            "error": f"seed document not found: {args.seed_doc}",
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 1

    suffixes = tuple(
        sorted(
            {
                suffix.lower().strip().lstrip(".")
                for suffix in args.official_domain_suffix
                if suffix and suffix.strip()
            }
        )
    )
    pipeline_result = run_professor_pipeline(
        seed_doc=args.seed_doc,
        timeout=args.timeout,
        official_domain_suffixes=suffixes,
        include_external_profiles=args.include_external_profiles,
        skip_profile_fetch=args.skip_profile_fetch,
    )
    release_result = build_professor_release(
        profiles=pipeline_result.profiles,
        official_domain_suffixes=suffixes,
    )
    publish_professor_release(
        release_result,
        professor_records_path=professor_output,
        released_objects_path=released_output,
    )

    report_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed_document": str(args.seed_doc),
        "pipeline_summary": asdict(pipeline_result.report),
        "release_summary": asdict(release_result.report),
        "outputs": {
            "professor_records_jsonl": str(professor_output),
            "released_objects_jsonl": str(released_output),
        },
    }

    if str(report_output) == "-":
        print(json.dumps(report_payload, ensure_ascii=False, indent=2))
        return 0

    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(report_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
