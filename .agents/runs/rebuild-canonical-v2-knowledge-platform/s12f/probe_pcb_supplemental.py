"""Trace theme probes for the PCB enumeration turn end to end.

Runs the web lane, then the sufficiency decider + supplemental search and
prints whether 深南/一博 appear as probe specs and as findings.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(AGENT_ROOT))

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving  # noqa: E402
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    EvidenceSet,
    LaneRequest,
    QueryPlanningRequest,
    StructuredConstraints,
    SufficiencyDecisionRequest,
    SupplementalRequest,
    WebSearchPolicy,
)

RUN_ROOT = AGENT_ROOT / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
RELEASE_ID = "candidate-s12f-20260801-v1"
QUERY = "我想找PCB打板， 有哪些推荐"


class _Embedding:
    model_id = "Qwen/Qwen3-Embedding-8B"


def main() -> None:
    inputs = serving.load_recorded_serving_inputs(
        path=RUN_ROOT / "s12f/serving-bundle-s12f.json",
        expected_content_sha256="93fb456012f5e9799414cd90fa2ea27bb7d58acd5d41c13ac3b9dea601aed9c0",
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_s12f_20260801_v1",
        expected_index_root=Path("/var/tmp/mirothinker-canonical-v2-s12f/index-v1"),
        expected_envelope_path=RUN_ROOT / "s12a/complete-candidate-build-envelope.json",
        embedding_adapter=_Embedding(),
    )
    proposal = inputs.proposal_provider(
        QueryPlanningRequest(
            request_id="query-request:probe-pcb-supp",
            release_id=RELEASE_ID,
            original_query=QUERY,
            as_of=datetime.now(UTC),
        )
    )
    request = LaneRequest(
        lane="web",
        release_id=RELEASE_ID,
        query_view="view:original",
        original_query=QUERY,
        behavior_class="D",
        interaction_mode="information_retrieval",
        web_policy=WebSearchPolicy(
            mode="universal", max_provider_calls=2, timeout_ms=15_000, max_results=48
        ),
        query_text=QUERY,
        domains=("company",),
        protected_slots=(),
        structured_constraints=StructuredConstraints(displayed_entity_ids=()),
        max_candidates=proposal.max_candidates,
    )
    web_result = inputs.web_search(request)
    web_items = [
        item
        for candidate in web_result.candidates
        for item in candidate.evidence
    ]
    print(f"web items: {len(web_items)}")
    for item in web_items:
        if "深南" in (item.snippet or "") or "一博" in (item.snippet or ""):
            print("  HIT:", (item.snippet or "")[:100].replace("\n", " "))

    theme_part = serving._theme_material_part(QUERY)
    print("theme part core:", theme_part.requested_value if theme_part else None)
    plan_id = "plan:probe-pcb-supp"
    decider = inputs.sufficiency_decider
    decider(
        SufficiencyDecisionRequest(
            plan_id=plan_id,
            release_id=RELEASE_ID,
            original_query=QUERY,
            material_parts=(theme_part,),
            evidence=tuple(web_items),
        )
    )
    result = inputs.supplemental_search(
        SupplementalRequest(
            plan_id=plan_id,
            release_id=RELEASE_ID,
            material_part_ids=(theme_part.part_id,),
            query_view=QUERY,
        )
    )
    print(
        f"supplemental items: {len(result.items)} cost={result.cost_units} "
        f"elapsed={result.elapsed_ms}"
    )
    for item in result.items:
        name = ""
        try:
            payload = __import__("json").loads(item.snippet)
            name = payload.get("name", "")
        except Exception:  # noqa: BLE001
            pass
        print("  finding:", name, "|", (item.snippet or "")[:80].replace("\n", " "))

    # Also dump the theme probes recorded in the context store for inspection.
    store = serving._SupplementalContextStore()
    decider2 = serving._serving_sufficiency_decider(context_store=store)
    decider2(
        SufficiencyDecisionRequest(
            plan_id="plan:probe-pcb-probes",
            release_id=RELEASE_ID,
            original_query=QUERY,
            material_parts=(theme_part,),
            evidence=tuple(web_items),
        )
    )
    context = store.pop("plan:probe-pcb-probes")
    if context is not None:
        print(f"\ntheme probes: {len(context.theme_probes)}")
        for probe in context.theme_probes[:20]:
            marker = " <== 深南" if "深南" in probe.entity_name else ""
            print("  probe:", probe.entity_name, marker)


if __name__ == "__main__":
    raise SystemExit(main())
