"""Write the scratch serving bundle for one 18296 run (index root rebound).

The recorded serving bundle pins the index root, and the runner refuses a
bundle whose content hash or index root differs. This script takes the 18295
scratch bundle (run15 release, same DB/envelope authority), rebinds
``index_root`` to the scratch root under test, and re-hashes it through the
real ``RecordedServingBundle`` model.

Usage (from ``apps/miroflow-agent``)::

    uv run python ../../.agents/runs/drop-milvus-from-serving-pack/make_scratch_bundle.py \
        --source /var/tmp/webfloor-295/serving-bundle-run15-18295.json \
        --index-root /var/tmp/slimpack-296/v2/index \
        --output /var/tmp/slimpack-296/serving-bundle-v2.json
"""

from __future__ import annotations

import argparse
import json
from importlib import import_module
import sys
from pathlib import Path


def _bootstrap_src() -> None:
    try:
        import_module("src.data_agents.canonical_v2.knowledge_serving_isolated")
    except ModuleNotFoundError:
        agent_root = Path(__file__).resolve().parents[3] / "apps/miroflow-agent"
        if str(agent_root) not in sys.path:
            sys.path.insert(0, str(agent_root))


_bootstrap_src()

from src.data_agents.canonical_v2.knowledge_serving_isolated import (  # noqa: E402
    RecordedServingBundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Write one scratch serving bundle")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--index-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    namespace = parser.parse_args()
    if namespace.output.exists():
        raise SystemExit(f"refusing to overwrite existing bundle: {namespace.output}")
    payload = json.loads(namespace.source.read_text(encoding="utf-8"))
    payload.pop("content_sha256", None)
    payload["index_root"] = str(namespace.index_root)
    bundle = RecordedServingBundle.model_validate(payload)
    rendered = (
        json.dumps(
            bundle.model_dump(mode="json"),
            ensure_ascii=False,
            indent=1,
            sort_keys=False,
            allow_nan=False,
        )
        + "\n"
    )
    namespace.output.write_text(rendered, encoding="utf-8")
    readback = RecordedServingBundle.model_validate_json(
        namespace.output.read_bytes(),
        context={"external_content_addressed": True},
    )
    if readback != bundle:
        raise SystemExit("scratch serving bundle readback differs")
    print(f"{namespace.output} {bundle.content_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
