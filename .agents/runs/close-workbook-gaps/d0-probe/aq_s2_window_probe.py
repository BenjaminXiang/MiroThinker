"""AQ-S2 window probe — F1 category-recall ranks at window 48 vs 64.

Runs the REAL `_category_recall_entries` chain against the sealed run14 pack
(read-only), the same way `collect_f1_category_recall.py` does, and compares
the GT ranks under the pre-AQ-S2 window (48) and the AQ-S2 window (64). The
expected free benefit (design §1.A-1): 嘉立创 (pool 54) and 则成 (pool 62)
enter the window; 兴森 (70) / 一博 (98) stay out (A-2 territory).

Also records:
  * registered-place evidence availability for AQ-S1 — company entries whose
    `registered_address` / `geography.name` survive the C1 placeholder
    scrubber (the values `_semantic_text` can render as 注册地);
  * the claim-payload character cost of the window split change
    (local 16 -> 32, web 48 -> 32): real local claim lengths rendered by the
    production `_semantic_text` over the 64-window entries, versus the web
    claim cap (240 snippet chars + source suffix).

No network, no writes outside this directory's JSON output.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/miroflow-agent"))

from src.data_agents.canonical_v2 import (  # noqa: E402
    knowledge_read_isolated as iso,
)
from src.data_agents.canonical_v2 import (  # noqa: E402
    knowledge_serving_isolated as serving,
)
from src.data_agents.canonical_v2.index_projection import (  # noqa: E402
    LookupProjectionDocument,
)
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    EvidenceClaimBinding,
    EvidenceItem,
    LaneRequest,
    StructuredConstraints,
    WebSearchPolicy,
)
from src.data_agents.canonical_v2.placeholder_scrub import (  # noqa: E402
    scrub_placeholder_value,
)

PACK_LOOKUP_DB = Path("/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed/lookup.sqlite3")
OUT = Path(__file__).with_name("aq-s2-window-probe.json")

QUERIES = (
    {
        "id": "g2-t1",
        "query": "中国有哪些成熟的酒店送餐机器人供应商",
        "gt": ("普渡", "开普勒", "云迹", "九号", "擎朗", "艾唯尔", "安赛步", "锐曼"),
    },
    {
        "id": "g5-t1",
        "query": "我想找PCB打板， 有哪些推荐",
        "gt": ("嘉立创", "深南电路", "一博", "顺易捷", "兴森", "则成", "上达", "精诚达"),
    },
    {
        "id": "pcb-list",
        "query": "深圳有哪些做PCB的公司",
        "gt": ("嘉立创", "深南电路", "一博", "顺易捷", "兴森", "则成", "上达", "精诚达"),
    },
)
WINDOWS = (48, 64)
WEB_CLAIM_CAP = 240 + len("；来源：") + len("https://example.test/00")


def _claim_text(entry) -> str:
    item = EvidenceItem(
        evidence_id=f"evidence:probe:{entry.document.document_id}",
        object_id=entry.document.canonical_object_id,
        domain=entry.document.domain or "company",
        lane="lexical",
        source_nature="local",
        source_locator=f"canonical-v2-isolated:{entry.document.document_id}",
        snippet=entry.document.lookup_content,
        score=1.0,
        source_authority="canonical_release",
        claim_binding=EvidenceClaimBinding(
            subject_id=entry.document.canonical_object_id,
            predicate="canonical_projection",
            value="a" * 64,
            status="admitted",
        ),
    )
    return serving._semantic_text(item, entry.display_name)


def main() -> None:
    db = sqlite3.connect(f"file:{PACK_LOOKUP_DB}?mode=ro&immutable=1", uri=True)
    rows = db.execute("SELECT document_json FROM lookup_document").fetchall()
    documents = tuple(
        LookupProjectionDocument.model_validate(json.loads(row[0])) for row in rows
    )
    release_id = documents[0].release_id
    entries = iso._public_lookup_entries(documents)
    company_entries = tuple(
        entry for entry in entries if entry.document.domain == "company"
    )

    report: dict = {
        "pack": str(PACK_LOOKUP_DB),
        "release_id": release_id,
        "windows": list(WINDOWS),
        "queries": [],
    }
    for spec in QUERIES:
        per_window = {}
        for window in WINDOWS:
            request = LaneRequest(
                lane="lexical",
                release_id=release_id,
                query_view="view:original",
                original_query=spec["query"],
                behavior_class="A",
                interaction_mode="information_retrieval",
                web_policy=WebSearchPolicy(mode="disabled"),
                query_text=spec["query"],
                domains=("company",),
                protected_slots=(),
                structured_constraints=StructuredConstraints(),
                max_candidates=window,
            )
            recalled = iso._category_recall_entries(request=request, entries=entries)
            ranks = {}
            for alias in spec["gt"]:
                rank = next(
                    (
                        index + 1
                        for index, entry in enumerate(recalled)
                        if alias in entry.display_name
                    ),
                    None,
                )
                if rank is not None:
                    ranks[alias] = rank
            per_window[str(window)] = {
                "recalled": len(recalled),
                "gt_ranks": ranks,
            }
        report["queries"].append(
            {"id": spec["id"], "query": spec["query"], "windows": per_window}
        )

    # AQ-S1 evidence availability: registered-place values that survive the
    # C1 scrubber (exactly what the gated 注册地 line can render).
    addressable = 0
    geography_only = 0
    for entry in company_entries:
        payload = json.loads(entry.document.lookup_content)
        address = payload.get("registered_address")
        if isinstance(address, str) and scrub_placeholder_value(address.strip()):
            addressable += 1
            continue
        geography = payload.get("geography")
        if isinstance(geography, dict):
            name = geography.get("name")
            if isinstance(name, str) and scrub_placeholder_value(name.strip()):
                geography_only += 1
    report["registered_place_coverage"] = {
        "company_entries": len(company_entries),
        "registered_address_usable": addressable,
        "geography_name_fallback_only": geography_only,
        "registered_address_share": round(addressable / len(company_entries), 4),
        "any_registered_place_share": round(
            (addressable + geography_only) / len(company_entries), 4
        ),
    }

    # Claim-payload cost of the window split change: local 16 -> 32 claims
    # (+16 real local claim texts) versus web 48 -> 32 (-16 capped web claims).
    cost = {}
    for spec in QUERIES:
        request = LaneRequest(
            lane="lexical",
            release_id=release_id,
            query_view="view:original",
            original_query=spec["query"],
            behavior_class="A",
            interaction_mode="information_retrieval",
            web_policy=WebSearchPolicy(mode="disabled"),
            query_text=spec["query"],
            domains=("company",),
            protected_slots=(),
            structured_constraints=StructuredConstraints(),
            max_candidates=64,
        )
        recalled = iso._category_recall_entries(request=request, entries=entries)
        lengths = [len(_claim_text(entry)) for entry in recalled]
        if not lengths:
            continue
        cost[spec["id"]] = {
            "local_claims_in_64_window": len(lengths),
            "local_claim_chars_mean": round(statistics.mean(lengths), 1),
            "local_claim_chars_median": statistics.median(lengths),
            "local_claim_chars_max": max(lengths),
        }
    report["claim_payload_cost"] = {
        "per_query_local_claim_stats": cost,
        "web_claim_char_cap": WEB_CLAIM_CAP,
        "delta_estimate": (
            "local +16 x mean_local_claim_chars vs web -16 x "
            "<= web_claim_char_cap per enumeration turn"
        ),
    }

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    for query_report in report["queries"]:
        print(f"=== {query_report['id']}: {query_report['query']}")
        for window, data in query_report["windows"].items():
            print(f"  window={window} recalled={data['recalled']} gt={data['gt_ranks']}")
    print("registered-place coverage:", report["registered_place_coverage"])
    print("claim cost:", json.dumps(report["claim_payload_cost"], ensure_ascii=False))


if __name__ == "__main__":
    main()
