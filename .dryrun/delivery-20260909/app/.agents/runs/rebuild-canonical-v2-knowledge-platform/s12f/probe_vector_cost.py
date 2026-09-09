"""测向量 lane 耗时（服务同构：preopened snapshot + vectorized scoring）。"""
from __future__ import annotations

import sys, time
from datetime import UTC, datetime
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(AGENT_ROOT))

from src.data_agents.canonical_v2 import serving_pack_loader as spl  # noqa: E402
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    LaneRequest, StructuredConstraints, WebSearchPolicy,
)

PACK = Path("/var/tmp/mirothinker-canonical-v2-s12f/serving-pack")


class _Embedding:
    model_id = "Qwen/Qwen3-Embedding-8B"
    def embed_batch(self, texts):
        import sys as _s
        _s.path.insert(0, "/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation")
        from src.data_agents.canonical_v2.knowledge_serving_isolated import load_embeddings
        return load_embeddings(None)  # placeholder — 不可用


def main() -> None:
    # 直接复用服务的 embedding bundle 加载方式
    import json
    bundle = json.load(open(PACK / "manifest.json"))
    print("manifest keys:", list(bundle.keys())[:10])


if __name__ == "__main__":
    raise SystemExit(main())
