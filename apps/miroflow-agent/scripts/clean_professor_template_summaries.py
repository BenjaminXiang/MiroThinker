"""Strip the padding sentences from professor summaries in a released-objects source.

The source family `professor` (one JSONL file under the staging root) carries
summaries where the old fallback summariser appended
`该教授在深圳科创领域有持续贡献。` in a loop to reach a character target. Those
sentences were embedded into the research vectors, so they dilute retrieval — the
serving-side filter only cleans what users read, not what the vector holds.

This tool rewrites the source *into a new file* (never in place): the staging
files are content-addressed, so the new file's name must be its new sha256 and the
launch must reference it. The original stays untouched for rollback.

Usage::

    python scripts/clean_professor_template_summaries.py \
        --source /var/tmp/mirothinker-data-v2/staging-v4/7ddf….source \
        --out /var/tmp/mirothinker-data-v2/cleaning/professor-cleaned.source \
        [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

PADDING_SENTENCES = (
    "该教授在深圳科创领域有持续贡献",
    "研究成果具有重要学术价值",
    "在深圳科创领域有持续贡献",
)
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？；])")


def strip_padding(summary: str) -> str:
    """Remove padding sentences, keeping everything else in order."""
    if not summary:
        return summary
    kept: list[str] = []
    for part in _SENTENCE_SPLIT.split(summary):
        if not part.strip():
            continue
        if any(padding in part for padding in PADDING_SENTENCES):
            continue
        kept.append(part)
    return "".join(kept)


def clean_record(record: dict) -> tuple[dict, bool]:
    """Return ``(record, changed)``; the summary is the only field touched."""
    summary = record.get("profile_summary")
    if not isinstance(summary, str) or not any(
        padding in summary for padding in PADDING_SENTENCES
    ):
        return record, False
    cleaned = strip_padding(summary)
    if cleaned == summary:
        return record, False
    updated = dict(record)
    updated["profile_summary"] = cleaned
    return updated, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    source = Path(args.source)
    output = Path(args.out)
    if not source.is_file():
        print(f"source not found: {source}", file=sys.stderr)
        return 2

    scanned = changed = removed_chars = 0
    samples: list[tuple[str, str, str]] = []
    rendered: list[str] = []
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            scanned += 1
            updated, was_changed = clean_record(record)
            if was_changed:
                changed += 1
                removed_chars += len(record["profile_summary"]) - len(
                    updated["profile_summary"]
                )
                if len(samples) < 3:
                    samples.append(
                        (
                            str(record.get("name") or record.get("canonical_name_zh")),
                            record["profile_summary"][:80],
                            updated["profile_summary"][:80],
                        )
                    )
            rendered.append(json.dumps(updated, ensure_ascii=False))

    print(f"rows scanned: {scanned}")
    print(f"rows changed: {changed}")
    print(f"characters removed: {removed_chars}")
    for name, before, after in samples:
        print(f"  {name}")
        print(f"    before: {before}")
        print(f"    after : {after}")

    if args.dry_run:
        print("dry run: nothing written")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(rendered) + "\n"
    output.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    print(f"written: {output} ({(len(payload) / 1024 / 1024):.1f} MB)")
    print(f"sha256: {digest}")
    print(f"content-addressed name: {digest}.source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
