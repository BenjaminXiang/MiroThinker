"""Minimal reseal: copy the pack and rebind only the code-identity fields.

Proven increment (migration-log round 14): a data-identical pack differs
between two seals only in ``manifest.json``'s ``generated_at``,
``generator_run_id`` and ``reader_contract_sha256``. This script performs
exactly that minimal update for a code-identity change (new code -> new
reader contract) and audits itself:

- every non-manifest entry in the new pack is a hardlink of the source
  (same inode, zero bytes copied),
- the manifest differs in exactly those three fields,
- the written reader contract equals ``reader_contract_digest()`` computed by
  the code that the boot will run.

Acceptance is a separate dogfood boot against the new pack (the boot rewrites
the mount receipt and proves the loader accepts it). The official sealer
(``s12c/build_serving_pack.py``, ~42 min full re-proof) remains the fallback
if the dogfood refuses.

Usage (interpreter must be the line's serving interpreter):

    PYTHONPATH=<line>/apps/miroflow-agent <line-venv>/bin/python \
        reseal_manifest.py --source-pack <dir> --pack-dir <new dir> \
        --generator-run-id <id>
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path


def _bootstrap_src() -> None:
    try:
        import_module("src.data_agents.canonical_v2.serving_pack_loader")
    except ModuleNotFoundError:
        agent_root = Path(__file__).resolve().parents[4] / "apps/miroflow-agent"
        if str(agent_root) not in sys.path:
            sys.path.insert(0, str(agent_root))


_bootstrap_src()

from src.data_agents.canonical_v2 import serving_pack_loader as pack_loader  # noqa: E402

_REBOUND_FIELDS = ("generated_at", "generator_run_id", "reader_contract_sha256")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pack", required=True, type=Path)
    parser.add_argument("--pack-dir", required=True, type=Path)
    parser.add_argument("--generator-run-id", required=True)
    args = parser.parse_args()

    source = args.source_pack.resolve()
    target = args.pack_dir.resolve()
    if not source.is_dir():
        raise SystemExit(f"source pack missing: {source}")
    if target == source or source == target.parent:
        raise SystemExit("source and target must be distinct directories")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    entries = sorted(source.iterdir())
    for entry in entries:
        if entry.name == "manifest.json":
            continue
        if entry.is_dir():
            raise SystemExit(f"unexpected directory inside pack: {entry}")
        os.link(entry, target / entry.name)

    manifest = json.loads((source / "manifest.json").read_text())
    before = dict(manifest)
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["generator_run_id"] = args.generator_run_id
    manifest["reader_contract_sha256"] = pack_loader.reader_contract_digest()
    changed = sorted(
        key
        for key in set(before) | set(manifest)
        if before.get(key) != manifest.get(key)
    )
    if changed != sorted(_REBOUND_FIELDS):
        raise SystemExit(f"manifest drift beyond the proven increment: {changed}")

    with tempfile.NamedTemporaryFile(
        "w",
        dir=target,
        prefix=".manifest-",
        suffix=".json.tmp",
        delete=False,
    ) as handle:
        json.dump(manifest, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
        tmp_path = Path(handle.name)
    final = target / "manifest.json"
    tmp_path.replace(final)

    digest = pack_loader.reader_contract_digest()
    for entry in entries:
        if entry.name == "manifest.json":
            continue
        if not os.path.samefile(entry, target / entry.name):
            raise SystemExit(f"hardlink audit failed: {entry.name}")
    written = json.loads(final.read_text())
    if written["reader_contract_sha256"] != digest:
        raise SystemExit("written reader contract differs from the running code")
    if sorted(written) != sorted(before):
        raise SystemExit("manifest key set changed")
    print(f"resealed: {target}")
    print(f"  rebound fields: {changed}")
    print(f"  reader_contract_sha256: {digest}")
    print(f"  hardlinked entries: {len(entries) - 1} (zero bytes copied)")
    print(f"  manifest bytes: {final.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
