#!/usr/bin/env python3
"""Fail when a deployed tree diverges from a git ref.

The customer runtime is not a git checkout, so behaviour can drift onto the host
and disappear on the next re-seal. This check makes the drift visible: compare
the deployed ``apps/`` tree against a git ref by file hash and exit non-zero on
any difference.

Usage::

    # compare the local checkout's ref against a remote host
    python scripts/check_runtime_drift.py --ref hotfix/customer-20261026 \
        --remote root@100.64.0.96:/root/deploy/fullstack-v2/code

    # compare against a local copy (e.g. a tarball you already unpacked)
    python scripts/check_runtime_drift.py --ref HEAD --local /tmp/prod-sync

    # restrict the scope
    python scripts/check_runtime_drift.py --ref HEAD --path apps/admin-console

Exit codes: 0 = no drift, 1 = drift, 2 = transport/usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import subprocess
import sys
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

_IGNORED_DIRS = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".agents",
        "node_modules",
        "dist",
        "logs",
        "htmlcov",
        "var",
    }
)
_IGNORED_SUFFIXES = (".pyc", ".pyo", ".swp", ".DS_Store")
_RESIDUE_MARKERS = (".bak", ".pre", ".orig", ".rej")
# Repo-side tooling that deliberately never ships to a host.
_REPO_ONLY = frozenset({"apps/admin-console/scripts/check_runtime_drift.py"})
# Runtime state that legitimately lives inside the deployed tree and is not
# source: secrets, SQLite databases, build reports. Reported, never failed.
_RUNTIME_NAMES = frozenset({".env", "report.html"})
_RUNTIME_SUFFIXES = (".db", ".sqlite3", ".log")


def is_runtime_artifact(relative: str) -> bool:
    name = relative.rsplit("/", 1)[-1]
    if name in _RUNTIME_NAMES or name.startswith(".env."):
        return True
    return name.endswith(_RUNTIME_SUFFIXES)


def is_ignored(relative: str) -> bool:
    if relative in _REPO_ONLY:
        return True
    parts = relative.split("/")
    if any(part in _IGNORED_DIRS for part in parts):
        return True
    name = parts[-1]
    if name.endswith(_IGNORED_SUFFIXES):
        return True
    if is_runtime_artifact(name):
        return True
    # Hot-patch residue written next to the source on the deployed host.
    return any(marker in name for marker in _RESIDUE_MARKERS)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def scan_local(
    root: Path, path: str = "apps", runtime: list[str] | None = None
) -> dict[str, str]:
    """Map ``<path>/<rel>`` -> sha256 for every regular file under ``root/path``."""
    base = (root / path).resolve()
    if not base.is_dir():
        raise FileNotFoundError(f"not a directory: {base}")
    tree: dict[str, str] = {}
    for candidate in sorted(base.rglob("*")):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root.resolve()).as_posix()
        if is_runtime_artifact(relative):
            if runtime is not None:
                runtime.append(relative)
            continue
        if is_ignored(relative):
            continue
        tree[relative] = sha256_bytes(candidate.read_bytes())
    return tree


def scan_git(root: Path, ref: str, path: str = "apps") -> dict[str, str]:
    """Map the same keys for a git ref, read through one ``git archive``."""
    blob = subprocess.run(
        ["git", "-C", str(root), "archive", "--format=tar", ref, path],
        check=True,
        capture_output=True,
    ).stdout
    tree: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            if is_ignored(member.name):
                continue
            handle = archive.extractfile(member)
            tree[member.name] = sha256_bytes(handle.read() if handle else b"")
    return tree


def scan_remote(
    target: str, path: str = "apps", runtime: list[str] | None = None
) -> dict[str, str]:
    """Map the same keys for ``user@host:/absolute/path`` over ssh."""
    if ":" not in target:
        raise ValueError("remote target must look like user@host:/absolute/path")
    host, remote_path = target.split(":", 1)
    command = f"cd {remote_path} && find {path} -type f -print0 | xargs -0 sha256sum"
    completed = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", host, command],
        check=True,
        capture_output=True,
        text=True,
    )
    tree: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        digest, _, relative = line.partition("  ")
        if not relative:
            continue
        if is_runtime_artifact(relative):
            if runtime is not None:
                runtime.append(relative)
            continue
        if is_ignored(relative):
            continue
        tree[relative] = digest
    return tree


@dataclass
class Drift:
    changed: list[tuple[str, str, str]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # in ref, not deployed
    untracked: list[str] = field(default_factory=list)  # deployed only, not in ref

    @property
    def total(self) -> int:
        return len(self.changed) + len(self.missing) + len(self.untracked)


def compare(reference: dict[str, str], deployed: dict[str, str]) -> Drift:
    drift = Drift()
    for relative in sorted(reference.keys() | deployed.keys()):
        left = reference.get(relative)
        right = deployed.get(relative)
        if left is None:
            drift.untracked.append(relative)
        elif right is None:
            drift.missing.append(relative)
        elif left != right:
            drift.changed.append((relative, left, right))
    return drift


def format_report(drift: Drift, *, limit: int = 20) -> str:
    if drift.total == 0:
        return "no drift: deployed tree matches the git ref"
    lines = [
        f"drift: {len(drift.changed)} changed, {len(drift.missing)} only-in-ref, "
        f"{len(drift.untracked)} only-deployed"
    ]
    for relative, left, right in drift.changed[:limit]:
        lines.append(f"  CHANGED  {relative}  ref={left[:12]} deployed={right[:12]}")
    for relative in drift.missing[:limit]:
        lines.append(f"  MISSING  {relative}  (in ref, absent on host)")
    for relative in drift.untracked[:limit]:
        lines.append(f"  UNTRACKED {relative}  (host only, not in ref)")
    hidden = drift.total - min(drift.total, limit * 3)
    if hidden > 0:
        lines.append(f"  … {hidden} more")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="git checkout to read the ref from")
    parser.add_argument("--ref", required=True, help="git ref to compare against")
    parser.add_argument(
        "--path",
        action="append",
        default=None,
        help=(
            "subtree to compare; repeatable. Default: apps/admin-console and "
            "apps/miroflow-agent (the deployed scope — apps/ also holds historical "
            "apps that are never shipped)"
        ),
    )
    parser.add_argument("--limit", type=int, default=40, help="max lines per category")
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help=(
            "also compare tests/. Off by default: the deployed bundle ships a "
            "trimmed test tree, and tests are not runtime behaviour"
        ),
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--remote", help="user@host:/absolute/path of the deployed tree"
    )
    target.add_argument("--local", help="local copy of the deployed tree")
    args = parser.parse_args(argv)

    repo = Path(args.repo)
    paths = args.path or ["apps/admin-console", "apps/miroflow-agent"]
    runtime: list[str] = []
    try:
        reference: dict[str, str] = {}
        deployed: dict[str, str] = {}
        for path in paths:
            reference.update(scan_git(repo, args.ref, path))
            if args.remote:
                deployed.update(scan_remote(args.remote, path, runtime))
            else:
                deployed.update(scan_local(Path(args.local), path, runtime))
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as error:
        print(f"drift check failed: {error}", file=sys.stderr)
        return 2

    if not args.include_tests:
        reference = {k: v for k, v in reference.items() if "/tests/" not in k}
        deployed = {k: v for k, v in deployed.items() if "/tests/" not in k}

    drift = compare(reference, deployed)
    print(format_report(drift, limit=args.limit))
    if runtime:
        sample = ", ".join(sorted(runtime)[:4])
        print(f"runtime files ignored ({len(runtime)}): {sample}")
    print(f"compared {len(reference)} ref files against {len(deployed)} deployed files")
    return 0 if drift.total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
