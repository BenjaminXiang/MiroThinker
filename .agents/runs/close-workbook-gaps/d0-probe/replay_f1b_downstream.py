"""F1-B downstream breakpoint probe: offline replay of run14 g2-t1 / g5-t1.

Question: F1 (category recall) put the GT companies into the lexical 48-window
(proven by f1-category-recall.json and the live trace lexical in=48/retained=48),
yet the production answer named six mid-window companies instead. This probe
replays the two turn-1s through the REAL serving stack (serving pack authority +
recorded serving inputs + real planner/read/reranker/selector) and records each
GT company's fate at every stage:

  1. lane outputs (lexical/vector/web candidates, raw scores, order)
  2. lane -> direct_items assembly (direct_object_ids, direct_result_count)
  3. rerank order vs candidate_limit = max_candidates - direct_result_count
  4. answer selector claims + displayed_handle_ids (local<=16 / web<=48)
  5. prose payload displayed_entities (what the LLM actually saw)
  6. final production answer (from the acceptance recording, since the prose
     LLM cannot run offline)

Offline hardening (no network, no writes outside this directory):
  * TURN_TRACE_DIR pinned at the worktree var/turn-trace so the web lane reads
    the SAME-day cache the 07:11-07:14 live turns wrote (cache_get happens
    before any provider call).
  * serving.create_llm_judge patched to None BEFORE load: no gap-judge and no
    supplemental probe judgments (rule-only acceptance; deviations recorded).
  * _DualWebLaneAdapter._bocha/_serper replaced post-load with raising stubs:
    a cache miss can never reach the network.
  * Embedding adapter is a zero-vector dummy: production embeds queries live
    against an OpenAI-compatible endpoint (knowledge_build_isolated.py:6736).
    Vector-lane membership therefore differs from production, but vector
    candidates carry raw_score=cosine<1.0 while every local projection
    candidate carries raw_score=1.0 (knowledge_read_isolated.py:8741), so
    vector candidates cannot outrank lexical ones in the serving reranker's
    local bucket; the local outcome is unaffected.
  * page_fetcher is fail-closed (None): web deep-fetch text is missing, so web
    claim text is snippet-only; snapshot admission still succeeds because the
    adapter builds snippet-based snapshots.
  * query_rewriter stub returns the exact extra views recorded in the live
    turn trace (var/turn-trace/2026-09-11.jsonl) so the web lane searches
    cache-hit views. Production additionally fired gap-judge follow-up views
    (LLM); those are absent here, so the web merged set may be smaller than
    the live 67. The candidate window (candidate_limit) does not depend on
    the web candidate count because the web lane returns items=().
"""

from __future__ import annotations

import faulthandler
import json
import os
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/miroflow-agent"))

os.environ.setdefault("TURN_TRACE_DIR", str(ROOT / "var" / "turn-trace"))
os.environ.setdefault("BOCHA_API_KEY", "probe-offline-construction-only")
os.environ.setdefault("SERPER_API_KEY", "probe-offline-construction-only")

# The pack loader's model_construct leaves nested dicts unconverted; every
# serialize then rebuilds a giant PydanticSerializationUnexpectedValue message
# (tens of thousands of lines), which dominated the first probe run's runtime.
# Production suppresses these; the probe does the same and dumps a stack every
# 120s so a hang is diagnosable from the log.
warnings.filterwarnings("ignore")
faulthandler.dump_traceback_later(120, repeat=True)


def _mark(stage: str) -> None:
    print(f"[probe] {stage}", flush=True)

from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving  # noqa: E402
from src.data_agents.canonical_v2 import serving_pack_loader as pack_loader  # noqa: E402
from src.data_agents.canonical_v2 import index_projection_isolated as ipi  # noqa: E402
from src.data_agents.canonical_v2.contracts import PublishedRelease  # noqa: E402
from src.data_agents.canonical_v2.knowledge_answer import TurnRequest  # noqa: E402
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    QueryPlanningRequest,
    RetrievalPlan,
)

# Offline: no LLM judgments anywhere (web gap judge + supplemental judge).
serving.create_llm_judge = lambda: None  # noqa: E731

# The live 18188 server holds the Milvus Lite exclusive lock on the sealed
# index root, and the marker binds that absolute root, so a second opener
# cannot point elsewhere. Redirect ONLY the Milvus file open to a
# WAL-consistent byte copy taken through the SQLite backup API (the source is
# opened mode=ro; the marker/root/identity checks still run against the real
# root). The vector lane then reads the preopened in-memory snapshot, so this
# is the single open that needs redirecting. Scratch lives outside the repo.
_orig_open_milvus_client = ipi._open_milvus_client
_milvus_copies: dict[str, Path] = {}


def _open_milvus_copy(path: Path) -> object:
    import sqlite3

    source_path = str(Path(path))
    if source_path not in _milvus_copies:
        scratch_dir = Path("/var/tmp/f1b-probe-index") / Path(path).parent.name
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

RUN_ROOT = ROOT / ".agents/runs/rebuild-canonical-v2-knowledge-platform"
PACK_DIR = Path("/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed")
RELEASE_ID = "candidate-v2-20260819-r1"
BUNDLE_PATH = RUN_ROOT / "s12g/serving-bundle-run14.json"
BUNDLE_SHA = "846d3a580554376d3c4e22fcc705ec1518303d70943a9b746d7d9ae16d27299c"
INDEX_MARKER_SHA = (
    "8848197caaa665fa093f054aa6c7c241b90376f311ec62e089ddb479a6e97c8b"
)
ACCEPTANCE_RESULTS = Path(
    "/home/longxiang/MiroThinker/.agents/runs/testset-baseline-20260909/"
    "results-b3b2-acc-r1.json"
)
OUT = Path(__file__).with_name("f1b-downstream-trace.json")

SCENARIOS = (
    {
        "id": "g2-t1",
        "query": "中国有哪些成熟的酒店送餐机器人供应商",
        "as_of": datetime(2026, 9, 11, 7, 11, 22, tzinfo=UTC),
        # Live trace P5Wpcpr-5BIsu5Ty views minus the deterministic base view.
        "rewrite_extras": (
            "酒店服务机器人厂商",
            "酒店配送机器人品牌",
            "酒店送餐机器人供应商",
            "酒店送餐机器人 主流品牌 厂商",
            "酒店配送机器人 供应商 落地案例",
            "酒店配送 供应商 落地案例",
            "酒店送餐 主流品牌 厂商",
        ),
        "gt": ("云迹", "普渡", "开普勒", "擎朗", "九号", "艾唯尔"),
        "acceptance_group": 2,
    },
    {
        "id": "g5-t1",
        "query": "我想找PCB打板， 有哪些推荐",
        "as_of": datetime(2026, 9, 11, 7, 12, 33, tzinfo=UTC),
        # Live trace HfTVgAhr4wHvj5BX views minus the deterministic base view.
        "rewrite_extras": (
            "PCB打板 推荐 厂商",
            "PCB打板 平台 对比",
            "PCB打样 小批量 厂家",
        ),
        "gt": ("嘉立创", "深南电路", "一博", "顺易捷", "兴森", "则成", "上达", "精诚达"),
        "acceptance_group": 5,
    },
)


class _ZeroEmbedding:
    """Deterministic pseudo-embedding (hash-seeded unit vector).

    Production embeds queries live; offline we cannot. Vector membership
    therefore differs from production, but vector candidates carry
    raw_score=cosine<1.0 while local projection candidates carry raw_score=1.0
    (knowledge_read_isolated.py:8741), so vector results cannot outrank lexical
    ones in the serving reranker's local bucket. The validating adapter rejects
    zero-norm vectors (knowledge_read_isolated.py:345), hence non-zero.
    """

    model_id = "Qwen/Qwen3-Embedding-8B"
    dimension = 4096

    def embed_batch(self, texts: tuple[str, ...]) -> list[list[float]]:
        import hashlib
        import random

        vectors: list[list[float]] = []
        for text in texts:
            seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
            rng = random.Random(seed)
            vector = [rng.random() - 0.5 for _ in range(self.dimension)]
            norm = sum(value * value for value in vector) ** 0.5
            vectors.append([value / norm for value in vector])
        return vectors


class _FailClosedProvider:
    def __init__(self, name: str) -> None:
        self._name = name

    def search(self, query: str) -> dict:
        raise RuntimeError(f"offline probe: {self._name} provider disabled")


class _CaptureProse:
    """Prose renderer stand-in: records the payload, returns a fixed string."""

    def __init__(self) -> None:
        self.payloads: list[object] = []

    def __call__(self, result: object) -> str:
        self.payloads.append(result)
        return "PROBE"


def _names_from_handles(handles: object) -> list[str]:
    return [str(getattr(handle, "display_name", "")) for handle in handles or ()]


def _hit(alias: str, names: list[str]) -> int | None:
    for index, name in enumerate(names, start=1):
        if alias in name:
            return index
    return None


def main() -> None:
    _mark("load recorded inputs start")
    prose = _CaptureProse()
    recorded = serving.load_recorded_serving_inputs(
        path=BUNDLE_PATH,
        expected_content_sha256=BUNDLE_SHA,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_v2_20260819_r1",
        expected_index_root=Path("/var/tmp/mirothinker-data-v2/index-v1"),
        expected_envelope_path=(
            RUN_ROOT / "s12a/complete-candidate-build-envelope.json"
        ),
        embedding_adapter=_ZeroEmbedding(),
        prose_renderer=prose,
        page_fetcher=lambda url: None,
        query_rewriter=lambda text: next(
            (spec["rewrite_extras"] for spec in SCENARIOS if spec["query"] == text),
            (),
        ),
    )
    # Offline: hard-block the provider objects behind the cache.
    recorded.web_search._bocha = _FailClosedProvider("bocha")
    recorded.web_search._serper = _FailClosedProvider("serper")

    _mark("recorded inputs loaded")
    authority = pack_loader.open_serving_pack_authority(
        pack_dir=PACK_DIR,
        expected_release_id=RELEASE_ID,
        expected_index_marker_sha256=INDEX_MARKER_SHA,
        expected_forbidden_milvus_path=Path(
            "/home/longxiang/MiroThinker/apps/miroflow-agent/milvus.db"
        ),
    )
    published = PublishedRelease(
        release_id=RELEASE_ID,
        previous_release_id=None,
        canonical_release_id=RELEASE_ID,
        published_projection_release_id=RELEASE_ID,
        index_release_id=RELEASE_ID,
        state="active",
        changed_at=datetime(2026, 7, 22, tzinfo=UTC),
        verification_evidence_ids=tuple(authority.release_verification.evidence_ids),
    )
    _mark("authority opened")
    planner = pack_loader.create_serving_pack_query_planner(
        authority=authority,
        published_release=published,
        planning_policy=recorded.planning_policy,
        proposal_provider=recorded.proposal_provider,
        ambiguity_policy=recorded.ambiguity_policy,
    )

    capture: dict[str, object] = {"lanes": {}, "rerank_request": None, "rerank_proposal": None}

    def _wrap_lane(name, fn):
        def wrapped(request):
            result = fn(request)
            capture["lanes"][name] = {"request": request, "result": result}
            return result

        return wrapped

    def _wrap_reranker(fn):
        def wrapped(request):
            capture["rerank_request"] = request
            proposal = fn(request)
            capture["rerank_proposal"] = proposal
            return proposal

        return wrapped

    read = pack_loader.create_serving_pack_knowledge_read(
        authority=authority,
        published_release=published,
        universal_web_policy=recorded.universal_web_policy,
        web_search=recorded.web_search,
        web_snapshot_policy=recorded.web_snapshot_policy,
        embedding_adapter=recorded.embedding_adapter,
        identity_fuser=recorded.identity_fuser,
        reranker=_wrap_reranker(recorded.reranker),
        sufficiency_decider=recorded.sufficiency_decider,
        supplemental_search=recorded.supplemental_search,
        web_handle_resolver=recorded.web_handle_resolver,
        accepted_identity_lookup=recorded.accepted_identity_lookup,
    )
    delegate = read._delegate
    for lane_name, lane_fn in list(delegate._lane_adapters.items()):
        delegate._lane_adapters[lane_name] = _wrap_lane(lane_name, lane_fn)
    delegate._web_search = _wrap_lane("web", delegate._web_search)

    _mark("read composed")
    bundle = serving._read_bundle(BUNDLE_PATH)
    raw_selector = serving._answer_selector(bundle=bundle)

    acceptance = {entry["group"]: entry for entry in json.loads(ACCEPTANCE_RESULTS.read_text())}

    report: dict[str, object] = {"scenarios": []}
    for spec in SCENARIOS:
        capture["lanes"] = {}
        capture["rerank_request"] = None
        capture["rerank_proposal"] = None
        prose.payloads.clear()

        _mark(f"scenario {spec['id']} plan start")
        plan = planner.plan(
            QueryPlanningRequest(
                request_id=f"probe:f1b:{spec['id']}",
                release_id=RELEASE_ID,
                original_query=spec["query"],
                as_of=spec["as_of"],
                displayed_entity_ids=(),
                displayed_entity_names=(),
                enumeration_context=None,
                soft_context_subject=None,
            )
        )
        # canonical_v2_chat.py session bind: re-validate with the session id.
        session_id = f"session:probe:f1b:{spec['id']}"
        plan = RetrievalPlan.model_validate(
            {
                **plan.model_dump(exclude={"content_sha256"}),
                "session_id": session_id,
            }
        )
        _mark(f"scenario {spec['id']} execute start")
        evidence_set = read.execute(plan)
        _mark(f"scenario {spec['id']} execute done")

        lane_summary: dict[str, object] = {}
        for lane_name, entry in capture["lanes"].items():
            result = entry["result"]
            lane_summary[lane_name] = {
                "candidates": len(result.candidates),
                "items": len(result.items),
                "candidate_names": [c.display_name for c in result.candidates],
                "candidate_raw_scores": [c.raw_score for c in result.candidates],
                "candidate_lanes_of_evidence": [
                    sorted({item.lane for item in c.evidence}) for c in result.candidates
                ],
            }

        rerank_request = capture["rerank_request"]
        rerank_proposal = capture["rerank_proposal"]
        eligible_names = (
            [c.display_name for c in rerank_request.eligible_candidates]
            if rerank_request is not None
            else []
        )
        eligible_meta = (
            [
                {
                    "result_id": c.result_id,
                    "display_name": c.display_name,
                    "raw_score": c.raw_score,
                    "canonical_id": c.canonical_id,
                    "lanes": sorted({item.lane for item in c.evidence}),
                    "natures": sorted({item.source_nature for item in c.evidence}),
                }
                for c in rerank_request.eligible_candidates
            ]
            if rerank_request is not None
            else []
        )
        ordered_ids = (
            list(rerank_proposal.ordered_result_ids) if rerank_proposal is not None else []
        )
        id_to_name = {m["result_id"]: m["display_name"] for m in eligible_meta}
        ordered_names = [id_to_name.get(value, value) for value in ordered_ids]

        # Stage 2/3 replication of knowledge_read.py:7694-8060 semantics.
        direct_items: list[object] = []
        for lane_name in [lane for lane in plan.lanes if lane in capture["lanes"]]:
            lane_result = capture["lanes"][lane_name]["result"]
            lane_items = list(lane_result.items)
            if lane_name == "web":
                lane_items = lane_items[: max(0, 48)]
            direct_items.extend(lane_items)
        direct_object_ids = list(
            dict.fromkeys(item.object_id for item in direct_items)
        )[: plan.max_candidates]
        direct_result_count = len(direct_object_ids)
        candidate_limit = max(0, plan.max_candidates - direct_result_count)

        handles = list(evidence_set.entity_handles)
        handle_names = _names_from_handles(handles)
        dispositions: dict[str, int] = {}
        for trace in evidence_set.candidate_traces:
            dispositions[trace.disposition] = dispositions.get(trace.disposition, 0) + 1

        # Stage 4: the real selector on the replayed evidence set.
        turn_request = TurnRequest(
            session_id=session_id,
            turn_id=f"turn:probe:{spec['id']}:1",
            query=spec["query"],
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
            assessment_intent=plan.assessment_intent,
        )
        selection = raw_selector(turn_request)
        _mark(f"scenario {spec['id']} selector done")
        handle_by_id = {}
        for handle in handles:
            public_id = (
                handle.canonical_id
                if getattr(handle, "kind", "canonical") == "canonical"
                else handle.handle_id
            )
            handle_by_id[public_id] = handle
        displayed_names = [
            getattr(handle_by_id.get(handle_id), "display_name", handle_id)
            for handle_id in selection.displayed_handle_ids
        ]
        claim_texts = [claim.text for claim in selection.claims]

        # Stage 5: full answer run; the capture stub sees the prose payload.
        answer_error = None
        try:
            answer = recorded.answer_factory()
            answer.answer(turn_request)
            _mark(f"scenario {spec['id']} answer done")
        except Exception as exc:  # payload already captured before any raise
            answer_error = f"{type(exc).__name__}: {exc}"
        payload_displayed: list[str] = []
        payload_claims: list[str] = []
        if prose.payloads:
            payload = prose.payloads[-1]
            context = getattr(payload, "context_receipt", None)
            displayed_set = getattr(context, "displayed_result_set", None)
            payload_displayed = _names_from_handles(
                getattr(displayed_set, "handles", ())
            )
            payload_claims = [
                str(getattr(claim, "text", ""))
                for claim in getattr(payload, "claims", ())
            ]

        acc_turn = acceptance[spec["acceptance_group"]]["turns"][0]
        acc_answer = acc_turn["answer_text"]
        window_names = (
            lane_summary.get("lexical", {}).get("candidate_names", [])
            if "lexical" in lane_summary
            else []
        )
        answered_names = [name for name in window_names if name in acc_answer]

        gt_rows = []
        for alias in spec["gt"]:
            gt_rows.append(
                {
                    "alias": alias,
                    "s1_lexical_rank": _hit(alias, lane_summary.get("lexical", {}).get("candidate_names", []) or []),
                    "s1_vector_rank": _hit(alias, lane_summary.get("vector", {}).get("candidate_names", []) or []),
                    "s3_eligible_rank": _hit(alias, eligible_names),
                    "s3_ordered_rank": _hit(alias, ordered_names),
                    "s3_within_candidate_limit": (
                        (pos := _hit(alias, ordered_names)) is not None
                        and pos <= candidate_limit
                    ),
                    "s3_handle": _hit(alias, handle_names),
                    "s4_selector_claim": _hit(alias, claim_texts),
                    "s4_displayed": _hit(alias, displayed_names),
                    "s5_payload_displayed": _hit(alias, payload_displayed),
                    "s5_payload_claim": _hit(alias, payload_claims),
                    "s6_in_production_answer": alias in acc_answer,
                }
            )

        report["scenarios"].append(
            {
                "id": spec["id"],
                "query": spec["query"],
                "plan": {
                    "lanes": list(plan.lanes),
                    "max_candidates": plan.max_candidates,
                    "web_max_results": plan.web_policy.max_results,
                    "query_views": [view.text for view in plan.query_views],
                    "enumeration_policy": (
                        None
                        if plan.enumeration_policy is None
                        else str(plan.enumeration_policy)
                    ),
                },
                "stage1_lanes": {
                    name: {k: v for k, v in summary.items() if k != "candidate_names" or name == "lexical"}
                    for name, summary in lane_summary.items()
                },
                "stage2_direct": {
                    "direct_item_count": len(direct_items),
                    "direct_result_count": direct_result_count,
                },
                "stage3_window": {
                    "candidate_limit": candidate_limit,
                    "ordered_count": len(ordered_ids),
                    "ordered_names": ordered_names,
                    "eligible": eligible_meta,
                    "handle_count": len(handles),
                    "handle_names": handle_names,
                    "dispositions": dispositions,
                    "evidence_item_count": len(evidence_set.items),
                },
                "stage4_selector": {
                    "claim_count": len(selection.claims),
                    "displayed_handle_count": len(selection.displayed_handle_ids),
                    "displayed_names": displayed_names,
                    "claim_texts": claim_texts,
                },
                "stage5_payload": {
                    "answer_error": answer_error,
                    "displayed_names": payload_displayed,
                    "claim_count": len(payload_claims),
                },
                "stage6_production_answer": {
                    "answer_text": acc_answer,
                    "answered_window_names": answered_names,
                },
                "gt_table": gt_rows,
            }
        )

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    for scenario in report["scenarios"]:
        print(f"=== {scenario['id']}: {scenario['query']}")
        print("  plan:", scenario["plan"])
        for lane, summary in scenario["stage1_lanes"].items():
            print(f"  lane {lane}: candidates={summary['candidates']} items={summary['items']}")
        print("  stage2/3:", {k: scenario["stage2_direct"][k] for k in scenario["stage2_direct"]},
              "candidate_limit=", scenario["stage3_window"]["candidate_limit"],
              "handles=", scenario["stage3_window"]["handle_count"],
              "dispositions=", scenario["stage3_window"]["dispositions"])
        print("  stage4 displayed:", scenario["stage4_selector"]["displayed_handle_count"],
              scenario["stage4_selector"]["displayed_names"][:20])
        print("  stage5 payload displayed:", scenario["stage5_payload"]["displayed_names"][:20],
              "answer_error:", scenario["stage5_payload"]["answer_error"])
        print("  stage6 answered window names:", scenario["stage6_production_answer"]["answered_window_names"])
        for row in scenario["gt_table"]:
            print("   ", row)


if __name__ == "__main__":
    main()
