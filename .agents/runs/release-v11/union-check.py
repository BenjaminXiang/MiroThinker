#!/usr/bin/env python3
"""Prove the merged release tree is exactly the union of the three branches.

For every path that differs between the base (delivery-v1 = 36df47b8) and the
merge (release/v1.1):
  * it must be changed by at least one of the three branches (no path may have
    been touched by the merge itself), and
  * its merged blob must equal the blob of at least one branch that changed it,
  * and its change status must agree with that branch's status.

Also asserts the reverse direction: every path changed by a branch is present in
the merge (union subset), i.e. nothing was dropped by a merge resolution.

Usage: python3 union-check.py [base] [merge] [branch ...]
"""

from __future__ import annotations

import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.run(
        ("git", *args), capture_output=True, text=True, check=True
    ).stdout


def name_status(base: str, ref: str) -> dict[str, str]:
    out = git("diff", "--name-status", base, ref)
    return {line.split("\t")[-1]: line.split("\t")[0] for line in out.strip().splitlines()}


def blob(ref: str, path: str) -> str | None:
    result = subprocess.run(
        ("git", "rev-parse", f"{ref}:{path}"), capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else None


def main() -> int:
    base, merge, *branches = sys.argv[1:] or [
        "36df47b8",
        "HEAD",
        "fix/embedding-lane-f1f2",
        "delivery/docker",
        "feat/recall-regression",
    ]
    per_branch = {branch: name_status(base, branch) for branch in branches}
    merged = name_status(base, merge)

    overlap = {}
    for path in merged:
        owners = [b for b, s in per_branch.items() if path in s]
        if owners:
            overlap[path] = owners

    untouched = sorted(p for p in merged if p not in overlap)
    mismatched = sorted(
        p
        for p, owners in overlap.items()
        if blob(merge, p) not in {blob(b, p) for b in owners}
    )
    dropped = sorted(
        p for b, s in per_branch.items() for p in s if p not in merged
    )
    status_conflicts = sorted(
        (p, merged[p], [per_branch[b][p] for b in owners])
        for p, owners in overlap.items()
        if merged[p] not in {per_branch[b][p] for b in owners}
        and not (
            merged[p] == "M" and any(per_branch[b][p] == "M" for b in owners)
        )
    )

    print(f"base={base} merge={merge}")
    for branch, s in per_branch.items():
        print(f"  branch {branch}: {len(s)} changed paths")
    print(f"merged changed paths: {len(merged)}")
    print(f"paths changed by the merge that no branch changed: {untouched}")
    print(f"paths whose merged blob differs from every owning branch: {mismatched}")
    print(f"paths changed by a branch but missing from the merge: {dropped}")
    print(f"status conflicts: {status_conflicts}")
    ok = not (untouched or mismatched or dropped or status_conflicts)
    print("VERDICT:", "union holds" if ok else "UNION MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
