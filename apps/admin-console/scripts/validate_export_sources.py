"""P4 S0: validate an exported source bundle against the build's source shape.

Two checks that need no build:

1. **shape** — every row parses, has the required keys, and is JSON-clean;
2. **coverage** — compare per-field non-empty coverage against a reference source
   file from the last build, so fields the export cannot reproduce are named
   explicitly instead of being discovered after a 20-hour rebuild.

Usage::

    python scripts/validate_export_sources.py \
        --export /tmp/export-prof \
        --reference /var/tmp/mirothinker-data-v2/staging-v4/<sha>.source \
        --domain professor --out /tmp/export-prof/validation.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED = {
    "professor": ("professor_id", "name", "institution", "profile_summary"),
    "paper": ("paper_id", "title"),
}


def _rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for key, value in row.items():
            if value not in (None, "", [], {}):
                counts[key] = counts.get(key, 0) + 1
    return counts


def coverage(rows: list[dict]) -> dict[str, float]:
    if not rows:
        return {}
    counts: dict[str, int] = {}
    for row in rows:
        for key, value in row.items():
            if value not in (None, "", [], {}):
                counts[key] = counts.get(key, 0) + 1
    return {key: round(count / len(rows), 4) for key, count in sorted(counts.items())}


def validate(export_rows: list[dict], reference_rows: list[dict], domain: str) -> dict[str, Any]:
    required = REQUIRED.get(domain, ())
    shape_errors: list[dict] = []
    for index, row in enumerate(export_rows):
        missing = [field for field in required if not row.get(field)]
        if missing:
            shape_errors.append({"row": index, "missing": missing})
            continue
        try:
            json.dumps(row, ensure_ascii=False, allow_nan=False)
        except ValueError as exc:
            shape_errors.append({"row": index, "error": str(exc)})

    export_counts = _counts(export_rows)
    reference_counts = _counts(reference_rows)
    # Compare absolute counts, not percentages: the export legitimately contains
    # records the source never had (pack-only professors), which would depress a
    # percentage comparison without meaning anything.
    regressions = {
        key: {"export": export_counts.get(key, 0), "reference": count}
        for key, count in reference_counts.items()
        if count >= 10 and export_counts.get(key, 0) < count * 0.95
    }
    return {
        "domain": domain,
        "export_rows": len(export_rows),
        "reference_rows": len(reference_rows),
        "shape_errors": len(shape_errors),
        "shape_error_samples": shape_errors[:5],
        "coverage_regressions": regressions,
        "ok": not shape_errors and not regressions,
    }


def find_export_file(export_dir: Path) -> Path:
    candidates = sorted(export_dir.glob("*.source"))
    if not candidates:
        raise SystemExit(f"no .source file in {export_dir}")
    return candidates[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", required=True)
    parser.add_argument("--reference", default=None)
    parser.add_argument("--domain", required=True, choices=("professor", "paper"))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    export_rows = _rows(find_export_file(Path(args.export)))
    reference_rows = _rows(Path(args.reference)) if args.reference else []
    report = validate(export_rows, reference_rows, args.domain)
    print(json.dumps({k: v for k, v in report.items() if k != "shape_error_samples"}, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
