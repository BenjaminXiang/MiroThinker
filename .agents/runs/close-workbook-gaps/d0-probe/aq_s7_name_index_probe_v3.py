"""AQ-S7 probe v3 — measure the PRODUCTION name index on the sealed pack.

v2 (aq-s7-name-index-probe-v2.json) validated the candidate design copied
into the probe: 6/6 anchors linked, 8/8 category/generic queries empty, but
the build cost 1.50s measured under tracemalloc. v3 times the shipped
`knowledge_read_isolated._build_entity_name_index` itself — CPU time without
tracemalloc, peak memory in a separate traced pass — and re-runs the anchor
and category matrices through the shipped matcher on the view-built index.
"""

from __future__ import annotations

import faulthandler
import json
import sys
import time
import tracemalloc
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/miroflow-agent"))

warnings.filterwarnings("ignore")
faulthandler.dump_traceback_later(300, repeat=True)


def _mark(stage: str) -> None:
    print(f"[probe] {stage}", flush=True)


from src.data_agents.canonical_v2 import index_projection_isolated as ipi  # noqa: E402
from src.data_agents.canonical_v2 import knowledge_read_isolated as iso  # noqa: E402
from src.data_agents.canonical_v2 import serving_pack_loader as pack_loader  # noqa: E402

_orig_open_milvus_client = ipi._open_milvus_client
_milvus_copies: dict[str, Path] = {}


def _open_milvus_copy(path: Path) -> object:
    import sqlite3

    source_path = str(Path(path))
    if source_path not in _milvus_copies:
        scratch_dir = Path("/var/tmp/s7-probe-index") / Path(path).parent.name
        scratch_dir.mkdir(parents=True, exist_ok=True)
        target = scratch_dir / Path(path).name
        source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
        dest = sqlite3.connect(target)
        with dest:
            source.backup(dest)
        source.close()
        dest.close()
        _milvus_copies[source_path] = target
    return _orig_open_milvus_client(_milvus_copies[source_path])


ipi._open_milvus_client = _open_milvus_copy

PACK_DIR = Path("/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed")
RELEASE_ID = "candidate-v2-20260819-r1"
INDEX_MARKER_SHA = (
    "8848197caaa665fa093f054aa6c7c241b90376f311ec62e089ddb479a6e97c8b"
)
OUT = Path(__file__).with_name("aq-s7-name-index-probe-v3.json")

ANCHORS = (
    "大疆创新主要做什么",
    "优必选科技怎么样",
    "深南电路的主要产品",
    "开普勒机器人 怎么样",
    "普渡科技有哪些产品",
    "普渡有哪些产品",
)
CATEGORY_QUERIES = (
    "深圳有哪些做激光雷达的公司",
    "我想找PCB打板， 有哪些推荐",
    "中国有哪些成熟的酒店送餐机器人供应商",
    "深圳有哪些机器人公司",
    "机器人的发展前景怎么样",
    "深圳的历史",
    "公司注册流程是什么",
    "送餐机器人哪个品牌好",
)


def main() -> None:
    _mark("open authority start")
    authority = pack_loader.open_serving_pack_authority(
        pack_dir=PACK_DIR,
        expected_release_id=RELEASE_ID,
        expected_index_marker_sha256=INDEX_MARKER_SHA,
        expected_forbidden_milvus_path=Path(
            "/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db"
        ),
    )
    _mark("authority open")
    started = time.monotonic()
    view = iso._create_audited_lookup_view(authority.release_bundle)
    view_build_s = time.monotonic() - started
    entries = view.public_entries
    _mark(
        f"view built (index included): {len(entries)} entries in {view_build_s:.2f}s; "
        f"index forms: {len(view.name_index.targets)}"
    )

    # Honest CPU timing: three untraced rebuilds, report each.
    rebuild_s: list[float] = []
    for _ in range(3):
        started = time.monotonic()
        rebuilt = iso._build_entity_name_index(entries)
        rebuild_s.append(round(time.monotonic() - started, 3))
    assert rebuilt.targets == view.name_index.targets

    tracemalloc.start()
    iso._build_entity_name_index(entries)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    _mark(f"rebuilds {rebuild_s}s, traced peak {peak/1e6:.1f}MB")

    def describe(query: str) -> dict[str, object]:
        started_q = time.monotonic()
        linked = iso._entity_link_entry_indexes(view.name_index, query)
        ms = (time.monotonic() - started_q) * 1000
        return {
            "query": query,
            "ms": round(ms, 2),
            "hits": [
                f"{entries[p].display_name}({entries[p].document.domain})"
                for p in linked
            ],
        }

    anchors = [describe(query) for query in ANCHORS]
    categories = [describe(query) for query in CATEGORY_QUERIES]

    report = {
        "view_entries": len(entries),
        "view_build_seconds_incl_index": round(view_build_s, 3),
        "index": {
            "forms": len(view.name_index.targets),
            "rebuild_seconds_untraced": rebuild_s,
            "tracemalloc_peak_mb": round(peak / 1e6, 1),
            "fanout_cap": iso._ENTITY_LINK_MAX_FORM_FANOUT,
            "max_entities": iso._ENTITY_LINK_MAX_ENTITIES,
            "blocklist_forms": len(iso._ENTITY_LINK_FORM_BLOCKLIST),
        },
        "anchors": anchors,
        "category_queries": categories,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    _mark(f"wrote {OUT.name}")
    print(json.dumps(report["index"], ensure_ascii=False, indent=1))
    for row in (*anchors, *categories):
        print("Q", row["query"], row["ms"], "ms ->", row["hits"])


if __name__ == "__main__":
    main()
