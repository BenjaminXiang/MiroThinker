"""Generate the run16 serve-18188 command file from the live run15 command.

The live `serve-18188-command.sh` is the single source of truth for the serving
line (systemd -> start-canonical-v2.sh -> this file).  For run16 only the
release-bound identity values change; this script substitutes exactly those and
refuses when any value is not found the expected number of times, so a drifted
or half-edited live command cannot silently produce a wrong run16 file.

The `--recorded-serving-bundle-sha256` token is taken from the run16 bundle's
own `content_sha256` field (the same convention the live command uses).

Usage:
    python prepare_serve_command_run16.py [--source PATH] [--bundle PATH]
        [--output PATH] [--marker-sha SHA]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

S12G = Path(
    "/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation"
    "/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g"
)
DEFAULT_SOURCE = S12G / "serve-18188-command.sh"
DEFAULT_BUNDLE = S12G / "serving-bundle-run16.json"
DEFAULT_OUTPUT = Path(
    "/home/longxiang/MiroThinker/.worktrees/data-rebuild"
    "/.agents/runs/full-column-serving-pack-rebuild/serve-18188-command-run16.sh"
)
# Printed by build-run16.sh ("index marker sha256=") for the run16 target.
DEFAULT_MARKER_SHA = "36305daf720c2745411653169c14935ea70c87665bc7deee85bf357fdd477256"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _bundled_sha256(bundle: Path) -> str:
    value = json.loads(bundle.read_text(encoding="utf-8")).get("content_sha256")
    if not isinstance(value, str) or not _SHA_RE.match(value):
        raise SystemExit(f"bundle {bundle} has no valid content_sha256")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--marker-sha", default=DEFAULT_MARKER_SHA)
    args = parser.parse_args()

    if not args.source.is_file() or args.source.is_symlink():
        raise SystemExit(f"live command file is missing: {args.source}")
    if args.output.exists() or args.output.is_symlink():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    if not args.bundle.is_file():
        raise SystemExit(f"run16 serving bundle is missing: {args.bundle}")
    bundle_sha = _bundled_sha256(args.bundle)
    if not _SHA_RE.match(args.marker_sha):
        raise SystemExit("marker sha must be 64 hex characters")

    text = args.source.read_text(encoding="utf-8")
    if text.count("\n") > 1:
        raise SystemExit("live command file is not the expected single line")

    substitutions = (
        ("miroflow_candidate_v2_20260913_r1", "miroflow_candidate_v2_20260916_r1", 2),
        ("/var/tmp/mirothinker-data-v2/staging-v2", "/var/tmp/mirothinker-data-v2/staging-v3", 1),
        ("/var/tmp/mirothinker-data-v2/index-v2", "/var/tmp/mirothinker-data-v2/index-v3", 1),
        (
            "071b858627559d87be09eb01363e951b1275d513aa7a8cddbd45f423b9bac1e9",
            args.marker_sha,
            1,
        ),
        ("candidate-v2-20260913-r1", "candidate-v2-20260916-r1", 1),
        ("p4-build-20260913-v1", "p4-build-20260916-v1", 1),
        ("serving-bundle-run15.json", "serving-bundle-run16.json", 1),
        (
            "4a8038950147e310799dea93cc11638fbb08d97fc311b4eafb7da4d93cf45cb0",
            bundle_sha,
            1,
        ),
        ("serving-pack-run15-sealed", "serving-pack-run16-sealed", 1),
    )

    updated = text
    for old, new, expected in substitutions:
        count = updated.count(old)
        if count != expected:
            raise SystemExit(
                f"token {old!r} appears {count} times, expected {expected}"
            )
        updated = updated.replace(old, new)

    for leftover in ("20260913", "run15", "index-v2", "staging-v2"):
        if leftover in updated:
            raise SystemExit(f"leftover run15 identity token after substitution: {leftover}")

    args.output.write_text(updated, encoding="utf-8")
    print(f"wrote {args.output}")
    print("substitutions:")
    for old, new, expected in substitutions:
        shown_old = old if len(old) < 40 else old[:16] + "…"
        shown_new = new if len(new) < 40 else new[:16] + "…"
        print(f"  [{expected}x] {shown_old} -> {shown_new}")


if __name__ == "__main__":
    main()
