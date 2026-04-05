#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.data_agents.professor.validator import (
    SeedDocumentValidationError,
    validate_roster_discovery_file,
)


def _default_seed_doc() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "docs" / "教授 URL.md"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate professor roster seed markdown and report URL counts/duplicates."
        )
    )
    parser.add_argument(
        "--seed-doc",
        type=Path,
        default=_default_seed_doc(),
        help="Path to the professor roster seed markdown document.",
    )
    args = parser.parse_args()

    try:
        report = validate_roster_discovery_file(args.seed_doc)
    except FileNotFoundError:
        print(f"ERROR: seed document not found: {args.seed_doc}", file=sys.stderr)
        return 1
    except SeedDocumentValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for line in report.to_text_lines():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
