"""Cron-ready wrapper around the professor projection refresh.

The refresh itself lives in `apps/miroflow-agent/scripts/refresh_professor_projection.py`
(projection → coherence → allowlist → metrics). This wrapper only resolves the
paths the customer site uses, runs it, and publishes `metrics.json` where the
console reads it (`CANONICAL_V2_PROFESSOR_PROJECTION_METRICS`).

Cron (Sunday 03:00, customer local time)::

    0 3 * * 0  cd /root/deploy/fullstack-v2/code/apps/admin-console && \
      /root/deploy/fullstack-v2/.venv/bin/python scripts/run_projection_refresh.py \
      >> /root/deploy/fullstack-v2/var/projection-refresh.log 2>&1

Environment (all optional; defaults match `run.sh`):

- ``CANONICAL_V2_SERVING_PACK``            pack directory
- ``CANONICAL_V2_PROFESSOR_PROJECTION_DIR`` output directory (allowlist lives here)
- ``CANONICAL_V2_PROFESSOR_PROJECTION_METRICS`` metrics file the console serves
- ``CANONICAL_V2_EMBEDDING_API_KEY``       embedding key (required)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

DEFAULT_PACK = "/var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth"
DEFAULT_OUT_DIR = "/root/deploy/fullstack-v2/var/professor-projection"
DEFAULT_METRICS = "/root/deploy/fullstack-v2/var/professor-projection-metrics.json"
DEFAULT_ALLOWLIST = "/root/deploy/fullstack-v2/var/professor-projection-allowlist.json"
REPO_ROOT = Path(__file__).resolve().parents[3]
REFRESH_SCRIPT = (
    REPO_ROOT
    / "apps"
    / "miroflow-agent"
    / "scripts"
    / "refresh_professor_projection.py"
)


def resolve_paths(environ: dict[str, str]) -> tuple[Path, Path, Path]:
    """Pack, output directory and published metrics path."""
    pack = Path(environ.get("CANONICAL_V2_SERVING_PACK") or DEFAULT_PACK)
    out_dir = Path(
        environ.get("CANONICAL_V2_PROFESSOR_PROJECTION_DIR") or DEFAULT_OUT_DIR
    )
    metrics = Path(
        environ.get("CANONICAL_V2_PROFESSOR_PROJECTION_METRICS") or DEFAULT_METRICS
    )
    return pack, out_dir, metrics


def bootstrap_managed_config(environ: dict[str, str]) -> None:
    """Project the managed settings/secrets into ``environ`` like the job runner does.

    The embedding key lives in the managed secrets file on the customer site, not
    in the process environment; without this the weekly job would fail on a
    healthy box.
    """

    agent_root = REPO_ROOT / "apps" / "miroflow-agent"
    if str(agent_root) not in sys.path:
        sys.path.insert(0, str(agent_root))
    try:
        from src.data_agents.canonical_v2.managed_runtime import (
            apply_managed_runtime_config,
        )
    except ImportError:
        return
    try:
        apply_managed_runtime_config(environ=environ)
    except Exception as error:  # noqa: BLE001 - a broken managed file must not hide the real error
        print(f"managed config unavailable: {error}", file=sys.stderr)


def publish_file(source: Path, target: Path) -> None:
    """Copy ``source`` over ``target`` atomically (readers never see a partial file)."""

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".tmp")
    shutil.copyfile(source, staging)
    os.replace(staging, target)


MIN_ALLOWLIST_RECORDS = 300
MAX_ALLOWLIST_SHRINK = 0.10


def allowlist_guard_reason(
    new_count: int,
    current_count: int | None,
    *,
    min_records: int = MIN_ALLOWLIST_RECORDS,
    max_shrink: float = MAX_ALLOWLIST_SHRINK,
) -> str | None:
    """Refuse a publish that would gut the allowlist.

    A weekly job may publish unattended, so two cheap invariants protect the live
    behaviour: never fewer than ``min_records`` records, and never a shrink of
    more than ``max_shrink`` against what is currently published.
    """

    if new_count < min_records:
        return f"too_small ({new_count} < {min_records})"
    if current_count and new_count < current_count * (1 - max_shrink):
        return f"shrink ({current_count} -> {new_count})"
    return None


def _record_count(path: Path) -> int | None:
    try:
        return len(json.loads(path.read_text()))
    except (OSError, json.JSONDecodeError):
        return None


def resolve_allowlist_target(environ: dict[str, str]) -> Path:
    return Path(environ.get("CANONICAL_V2_PROFESSOR_PROJECTION") or DEFAULT_ALLOWLIST)


def build_command(
    *, python: str, pack: Path, out_dir: Path, threshold: float, skip_coherence: bool
) -> list[str]:
    command = [
        python,
        str(REFRESH_SCRIPT),
        "--pack",
        str(pack),
        "--out",
        str(out_dir),
        "--threshold",
        str(threshold),
    ]
    if skip_coherence:
        command.append("--skip-coherence")
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=0.33)
    parser.add_argument(
        "--skip-coherence",
        action="store_true",
        help="reuse the previous coherence scores (no embedding calls)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the resolved command and exit"
    )
    parser.add_argument(
        "--publish-allowlist",
        action="store_true",
        help=(
            "also replace the live allowlist; the overlay reloads it on the next "
            "claim (no restart). Leave off until a refresh has been reviewed."
        ),
    )
    args = parser.parse_args(argv)

    environ = dict(os.environ)
    if not args.dry_run:
        bootstrap_managed_config(environ)
    pack, out_dir, metrics_path = resolve_paths(environ)
    if not pack.is_dir():
        print(f"serving pack missing: {pack}", file=sys.stderr)
        return 2
    if not environ.get("CANONICAL_V2_EMBEDDING_API_KEY") and not args.skip_coherence:
        print("CANONICAL_V2_EMBEDDING_API_KEY is required", file=sys.stderr)
        return 2

    command = build_command(
        python=sys.executable,
        pack=pack,
        out_dir=out_dir,
        threshold=args.threshold,
        skip_coherence=args.skip_coherence,
    )
    print(f"refresh: {' '.join(command)}")
    if args.dry_run:
        return 0

    child_env = dict(os.environ)
    child_env.update(environ)
    completed = subprocess.run(command, check=False, env=child_env)
    if completed.returncode != 0:
        print(f"refresh failed with {completed.returncode}", file=sys.stderr)
        return completed.returncode

    produced = out_dir / "metrics.json"
    if not produced.is_file():
        print(f"refresh produced no metrics at {produced}", file=sys.stderr)
        return 3
    publish_file(produced, metrics_path)
    print(f"published metrics: {metrics_path}")

    if args.publish_allowlist:
        allowlist_source = out_dir / "professor-projection-allowlist.json"
        if not allowlist_source.is_file():
            print(f"no allowlist to publish at {allowlist_source}", file=sys.stderr)
            return 3
        target = resolve_allowlist_target(environ)
        new_count = len(json.loads(allowlist_source.read_text()))
        reason = allowlist_guard_reason(new_count, _record_count(target))
        if reason:
            print(f"refusing to publish allowlist: {reason}", file=sys.stderr)
            return 4
        if target.is_file():
            # Keep one generation for rollback: the overlay hot-reloads, so a bad
            # publish takes effect on the next claim.
            publish_file(target, target.with_name(target.name + ".prev"))
        publish_file(allowlist_source, target)
        print(f"published allowlist: {target} ({new_count} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
