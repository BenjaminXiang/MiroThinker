"""Convert one isolated index root from the v1 (Milvus) to the v2 storage form.

Thin CLI over ``index_projection_isolated.convert_isolated_index_to_v2``: reads
every index point out of the source ``milvus.db`` once, writes them into the
``index_point`` table of a fresh copy of the source ``lookup.sqlite3``, copies
``vector_matrix.npz``, writes the marker for the new root, and never writes a
``milvus.db``.

Read-only against ``--source-root``. Usage (from ``apps/miroflow-agent``)::

    uv run python ../../.agents/runs/drop-milvus-from-serving-pack/convert_index_to_v2.py \
        --source-root /var/tmp/slimpack-296/v1/index \
        --dest-root /var/tmp/slimpack-296/v2/index
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from importlib import import_module
from pathlib import Path


def _bootstrap_src() -> None:
    try:
        import_module("src.data_agents.canonical_v2.index_projection_isolated")
    except ModuleNotFoundError:
        agent_root = Path(__file__).resolve().parents[3] / "apps/miroflow-agent"
        if str(agent_root) not in sys.path:
            sys.path.insert(0, str(agent_root))


_bootstrap_src()

from src.data_agents.canonical_v2.index_projection_isolated import (  # noqa: E402
    convert_isolated_index_to_v2,
)


def _absolute(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("an explicit absolute path is required")
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert one isolated index root to the v2 (no-Milvus) form"
    )
    parser.add_argument("--source-root", required=True, type=_absolute)
    parser.add_argument("--dest-root", required=True, type=_absolute)
    return parser


def main(args: Sequence[str] | None = None) -> int:
    namespace = _parser().parse_args(args)
    try:
        report = convert_isolated_index_to_v2(
            source_root=namespace.source_root,
            dest_root=namespace.dest_root,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"index conversion failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    payload = {key: str(value) for key, value in asdict(report).items()}
    print("conversion_report=" + json.dumps(payload, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
