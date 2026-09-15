#!/usr/bin/env python3
"""Replay the recorded bundle into the packaged vocabulary artifact.

This is the only step that turns LLM transcripts into the build input.  It runs
twice and refuses to write unless both replays are byte-identical, so the artifact
is provably the bundle's replay output - the property the build depends on.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
APP_ROOT = REPO_ROOT / "apps" / "miroflow-agent"
sys.path.insert(0, str(APP_ROOT))

from src.data_agents.canonical_v2.tech_vocabulary import (  # noqa: E402
    VOCABULARY_ARTIFACT_FILENAME,
    VocabularyIntegrityError,
    artifact_document,
    load_recorded_vocabulary_bundle,
    replay_vocabulary_from_bundle,
)

DEFAULT_OUT = REPO_ROOT / ".agents/runs/d1a-tech-vocabulary/out"
ARTIFACT_DIR = APP_ROOT / "src/data_agents/canonical_v2/catalogs"


def render(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        type=Path,
        default=DEFAULT_OUT / "recorded-vocabulary-decision-bundle.json",
    )
    parser.add_argument(
        "--artifact", type=Path, default=ARTIFACT_DIR / VOCABULARY_ARTIFACT_FILENAME
    )
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    bundle = load_recorded_vocabulary_bundle(args.bundle)
    first = render(artifact_document(replay_vocabulary_from_bundle(bundle)))
    second = render(artifact_document(replay_vocabulary_from_bundle(bundle)))
    if first != second:
        raise VocabularyIntegrityError("two replays of one bundle differ")

    if args.check_only:
        if not args.artifact.is_file():
            raise SystemExit(f"artifact missing: {args.artifact}")
        if args.artifact.read_text(encoding="utf-8") != first:
            raise SystemExit("packaged artifact differs from the bundle replay")
        print(
            json.dumps(
                {"artifact": str(args.artifact), "matches_bundle": True}, indent=2
            )
        )
        return

    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(first, encoding="utf-8")
    document = json.loads(first)
    print(
        json.dumps(
            {
                "artifact": str(args.artifact),
                "content_sha256": document["content_sha256"],
                "bundle_content_sha256": document["bundle_content_sha256"],
                "concepts": len(document["concepts"]),
                "mappings": len(document["mappings"]),
                "unmapped": len(document["unmapped"]),
                "llm_calls": document["llm_call_count"],
                "provider": document["provider"],
                "model": document["model"],
                "prompt_version": document["prompt_version"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
