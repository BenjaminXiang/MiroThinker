#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_agents.contracts import ProfessorRecord
from src.data_agents.paper.hybrid import (
    discover_professor_paper_candidates_from_hybrid_sources,
)
from src.data_agents.paper.openalex import (
    discover_professor_paper_candidates_from_openalex,
)
from src.data_agents.paper.pipeline import run_paper_pipeline
from src.data_agents.paper.release import publish_paper_release
from src.data_agents.paper.semantic_scholar import (
    discover_professor_paper_candidates,
)
from src.data_agents.publish import publish_jsonl


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _latest_professor_records_path() -> Path:
    release_dirs = sorted(
        (_repo_root() / "logs" / "debug").glob("professor_release_e2e_*/professor_records.jsonl")
    )
    if not release_dirs:
        raise FileNotFoundError(
            "No professor release output found under logs/debug/professor_release_e2e_*"
        )
    return release_dirs[-1]


def _default_output_paths() -> tuple[Path, Path, Path, Path]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = _repo_root() / "logs" / "debug" / f"paper_release_e2e_{timestamp}"
    return (
        output_dir / "paper_records.jsonl",
        output_dir / "released_objects.jsonl",
        output_dir / "professor_records_enriched.jsonl",
        output_dir / "report.json",
    )


def _load_professor_records(path: Path) -> list[ProfessorRecord]:
    records: list[ProfessorRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(ProfessorRecord.model_validate_json(line))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run professor-anchored paper discovery/release E2E and write "
            "PaperRecord + enriched ProfessorRecord JSONL outputs."
        )
    )
    parser.add_argument(
        "--professor-records",
        type=Path,
        default=None,
        help=(
            "Path to professor_records.jsonl. Defaults to the latest "
            "logs/debug/professor_release_e2e_*/professor_records.jsonl file."
        ),
    )
    parser.add_argument(
        "--source",
        choices=("hybrid", "openalex", "semantic_scholar"),
        default="hybrid",
        help=(
            "Paper discovery backend. Default: hybrid "
            "(OpenAlex first, Semantic Scholar fallback)."
        ),
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=16,
        help="Maximum professor-level concurrent external paper API requests.",
    )
    parser.add_argument(
        "--max-papers-per-professor",
        type=int,
        default=20,
        help="Semantic Scholar papers to fetch for each matched author.",
    )
    parser.add_argument("--paper-output", type=Path, default=None)
    parser.add_argument("--released-output", type=Path, default=None)
    parser.add_argument("--enriched-professor-output", type=Path, default=None)
    parser.add_argument(
        "--report-output",
        type=Path,
        default=None,
        help="Output path for JSON report. Use '-' to print report JSON to stdout.",
    )
    args = parser.parse_args()

    professor_records_path = args.professor_records or _latest_professor_records_path()
    paper_output, released_output, enriched_professor_output, report_output = (
        _default_output_paths()
    )
    if args.paper_output is not None:
        paper_output = args.paper_output
    if args.released_output is not None:
        released_output = args.released_output
    if args.enriched_professor_output is not None:
        enriched_professor_output = args.enriched_professor_output
    if args.report_output is not None:
        report_output = args.report_output

    professors = _load_professor_records(professor_records_path)
    discover_papers = {
        "hybrid": discover_professor_paper_candidates_from_hybrid_sources,
        "openalex": discover_professor_paper_candidates_from_openalex,
        "semantic_scholar": discover_professor_paper_candidates,
    }[args.source]
    pipeline_result = run_paper_pipeline(
        professors=professors,
        discover_papers=discover_papers,
        max_workers=args.max_workers,
        max_papers_per_professor=args.max_papers_per_professor,
        now=datetime.now(timezone.utc),
    )
    publish_paper_release(
        pipeline_result,
        paper_records_path=paper_output,
        released_objects_path=released_output,
    )
    publish_jsonl(enriched_professor_output, pipeline_result.updated_professors)

    report_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "professor_records_input": str(professor_records_path),
        "paper_summary": asdict(pipeline_result.report),
        "outputs": {
            "paper_records_jsonl": str(paper_output),
            "released_objects_jsonl": str(released_output),
            "professor_records_enriched_jsonl": str(enriched_professor_output),
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
