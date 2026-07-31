"""Read-only real-r8 probe: does an anchor-bound research follow-up reach his papers?

Replays the exact r8 serving composition (planner + release-bound read) without
HTTP, Postgres, Web providers, or LLM calls. The Web lane degrades harmlessly
because no provider keys are present in this shell.
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[4]
AGENT_ROOT = REPO / "apps/miroflow-agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

RUN_DIR = REPO / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
ENVELOPE_PATH = RUN_DIR / "s12c/complete-candidate-build-envelope.json"
SERVING_BUNDLE_PATH = RUN_DIR / "s12c/serving-bundle-r8.json"
EMBEDDING_BUNDLE_PATH = RUN_DIR / "s12c/qwen-embedding-bundle-v1.json"
SERVING_BUNDLE_SHA256 = (
    "d5f5e5d1dc4077556e7ce2fed077669414f85a3b3b28efe82ebf45ed7efbde76"
)
RELEASE_ID = "candidate-s12c-20260726-r8"
DATABASE = "miroflow_candidate_s12c_20260726_r8"
INDEX_ROOT = Path("/var/tmp/mirothinker-canonical-v2-s12c/r8/index")
PROFESSOR_ID = "professor-c-c5950c0fba38ddb3cc037643"
NOW = datetime(2026, 7, 29, 8, 0, tzinfo=timezone.utc)


def main() -> int:
    build_module = import_module(
        "src.data_agents.canonical_v2.knowledge_build_isolated"
    )
    serving_module = import_module(
        "src.data_agents.canonical_v2.knowledge_serving_isolated"
    )
    read_module = import_module("src.data_agents.canonical_v2.knowledge_read_isolated")
    contracts = import_module("src.data_agents.canonical_v2.contracts")
    read_models = import_module("src.data_agents.canonical_v2.knowledge_read")

    print("loading envelope ...", flush=True)
    envelope = build_module.CompleteCandidateBuildEnvelope.model_validate_json(
        ENVELOPE_PATH.read_bytes(),
        context={"external_content_addressed": True},
    )
    handoff = envelope.consumer_handoff
    candidate = envelope.receipt.candidate
    if candidate.release_id != RELEASE_ID:
        raise RuntimeError("probe envelope release mismatch")
    print("envelope loaded", flush=True)

    published = contracts.PublishedRelease(
        release_id=RELEASE_ID,
        previous_release_id=None,
        canonical_release_id=RELEASE_ID,
        published_projection_release_id=RELEASE_ID,
        index_release_id=RELEASE_ID,
        state="active",
        changed_at=datetime(2026, 7, 22, tzinfo=timezone.utc),
        verification_evidence_ids=tuple(handoff.release_verification.evidence_ids),
    )
    recorded = serving_module.load_recorded_serving_inputs(
        path=SERVING_BUNDLE_PATH,
        expected_content_sha256=SERVING_BUNDLE_SHA256,
        expected_release_id=RELEASE_ID,
        expected_database=DATABASE,
        expected_index_root=INDEX_ROOT,
        expected_envelope_path=ENVELOPE_PATH,
        embedding_adapter=build_module.load_content_addressed_embedding_adapter(
            EMBEDDING_BUNDLE_PATH
        ),
        prose_renderer=lambda result: "probe",
    )
    planner = read_module.create_isolated_release_query_planner(
        release_bundle=handoff.release_bundle,
        published_release=published,
        index_projection_request=handoff.index_projection_request,
        release_institution_catalog=handoff.institution_catalog,
        planning_policy=recorded.planning_policy,
        proposal_provider=recorded.proposal_provider,
        ambiguity_policy=recorded.ambiguity_policy,
    )
    knowledge_read = read_module.create_isolated_release_knowledge_read(
        release_bundle=handoff.release_bundle,
        published_release=published,
        universal_web_policy=recorded.universal_web_policy,
        web_search=recorded.web_search,
        web_snapshot_policy=recorded.web_snapshot_policy,
        embedding_adapter=recorded.embedding_adapter,
        reuse_audited_vector_snapshot=True,
        vectorized_recall=True,
        index_projection_request=handoff.index_projection_request,
        release_institution_catalog=handoff.institution_catalog,
        identity_fuser=recorded.identity_fuser,
        reranker=recorded.reranker,
        sufficiency_decider=recorded.sufficiency_decider,
        supplemental_search=recorded.supplemental_search,
        web_handle_resolver=recorded.web_handle_resolver,
        accepted_identity_lookup=recorded.accepted_identity_lookup,
    )
    print("planner + read composed", flush=True)

    query = sys.argv[1] if len(sys.argv) > 1 else "他有哪些代表性研究成果"
    displayed_ids = (
        (PROFESSOR_ID,) if len(sys.argv) <= 2 or sys.argv[2] == "anchor" else ()
    )
    displayed_names = ("丁文伯",) if displayed_ids else ()
    request = read_models.QueryPlanningRequest(
        request_id="query-request:probe-research-followup",
        release_id=RELEASE_ID,
        original_query=query,
        as_of=NOW,
        displayed_entity_ids=displayed_ids,
        displayed_entity_names=displayed_names,
    )
    plan = planner.plan(request)
    print("=== plan ===")
    print("lanes:", plan.lanes)
    print("relationship_paths:", [
        (p.relationship_type_id, p.direction, p.source_type, p.target_type)
        for p in plan.relationship_paths
    ])
    print("displayed_entity_ids:", plan.structured_constraints.displayed_entity_ids)
    for view in plan.query_views:
        print(f"query_view[{view.kind}]: {view.text!r}")

    import sys as _sys
    _sys.path.insert(0, str(REPO / "apps/admin-console"))
    chat_service = __import__("backend.services.canonical_v2_chat", fromlist=["CanonicalV2ChatAdapter"])
    adapter = chat_service.CanonicalV2ChatAdapter(
        release_id=RELEASE_ID,
        planner=planner,
        knowledge_read=knowledge_read,
        answer_factory=recorded.answer_factory,
        answer_session_fork=__import__("copy").deepcopy,
    )
    response = adapter.answer(
        query=query,
        session_id="session:probe-adapter",
        option_id=None,
        as_of=NOW,
    )
    admin_services = __import__("backend.services.canonical_v2_admin", fromlist=["compose_canonical_v2_consumer_runtime"])
    contracts_module = __import__("src.data_agents.canonical_v2.contracts", fromlist=["PublishedRelease"])
    composed = admin_services.compose_canonical_v2_consumer_runtime(
        published_release=published,
        release_verification=handoff.release_verification,
        release_bundle=handoff.release_bundle,
        index_projection_request=handoff.index_projection_request,
        planner=planner,
        knowledge_read=knowledge_read,
        answer_factory=recorded.answer_factory,
        answer_session_fork=recorded.answer_session_fork,
        gap_operations=recorded.gap_operations,
        supplemental_budget=recorded.supplemental_budget,
    )
    composed_response = composed.chat_adapter.answer(
        query=query,
        session_id="session:probe-composed",
        option_id=None,
        as_of=NOW,
    )
    print("=== composed runtime (server path) ===")
    print("query_type:", composed_response.query_type)
    print("answer:", (composed_response.answer_text or "")[:240])
    print("clarification:", composed_response.clarification)
    print("=== adapter (live path) ===")
    print("query_type:", response.query_type)
    print("answer:", (response.answer_text or "")[:240])
    print("clarification:", response.clarification)
    print("=== plan/read (probe path) ===")
    print("executing read ...", flush=True)
    evidence_set = knowledge_read.execute(plan)
    decision = evidence_set.ambiguity_decision
    if decision is not None:
        print("decision outcome:", decision.outcome, "| mode:", decision.mode)
        print("decision candidates:", [
            (c.handle_id, c.discriminator, c.viable) for c in decision.candidates
        ])
        print("viable handles:", decision.viable_alternative_handle_ids)
        print("trace count:", len(decision.candidate_traces))
    answer = recorded.answer_factory().answer(
        __import__("src.data_agents.canonical_v2.knowledge_answer", fromlist=["TurnRequest"]).TurnRequest(
            session_id="session:probe",
            turn_id="turn:probe:1",
            query=query,
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
        )
    )
    print("answer mode:", answer.response_mode)
    print("answer text:", (answer.answer_text or "")[:200])
    print("offer:", None if answer.continuation_offer is None else [
        (o.option_id, o.operation, o.target_handle_ids, o.discriminator)
        for o in answer.continuation_offer.options
    ])
    print("=== evidence ===")
    lanes: dict[str, int] = {}
    for item in evidence_set.items:
        lanes[item.lane] = lanes.get(item.lane, 0) + 1
    print("items per lane:", lanes)
    print("limitations:", [item.code for item in evidence_set.limitations])
    handles = tuple(evidence_set.entity_handles)
    print(f"entity_handles: {len(handles)}")
    for handle in handles:
        kind = getattr(handle, "kind", "?")
        domain = getattr(handle, "domain", "?")
        name = getattr(handle, "display_name", "?")
        canonical = getattr(handle, "canonical_id", getattr(handle, "handle_id", "?"))
        print(f"  handle[{kind}/{domain}] {name} ({canonical})")
    relationship_items = [
        item for item in evidence_set.items if item.lane == "relationship"
    ]
    print(f"relationship items: {len(relationship_items)}")
    for item in relationship_items:
        snippet = (item.snippet or "")[:160].replace("\n", " ")
        print(f"  [{item.domain}] {item.object_id} :: {snippet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
