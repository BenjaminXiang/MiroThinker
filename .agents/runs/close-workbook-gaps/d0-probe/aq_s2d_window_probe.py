"""AQ-S2d window probe — fused local positions of g5 GTs at candidate windows.

Question (user decision 2026-09-12, track 1): does widening the enumeration
candidate window 64 -> 128 (or 160/192) pull 嘉立创 / 深南电路 into the fused
local half, i.e. into the AQ-S2c disclosure pool (`entity_handles` filtered to
canonical company handles)? Lane ranks (S5 table: 嘉立创 56 / 深南电路 37) are
NOT fused positions — this probe measures the real fused order by replaying
g5-t1 through the REAL serving stack (planner -> lanes -> fusion ->
_serving_reranker -> ordered[:max_candidates] -> entity_handles), once per
candidate window, and reports per-GT positions in three orders:

  * fused_abs: position in the reranker `ordered` list (the window cut
    `ordered[:candidate_limit]` applies here);
  * handle: position in `evidence_set.entity_handles` (post-cut, post
    handleability filter);
  * disclosure: position in the canonical-company subsequence of
    entity_handles — the AQ-S2c sentence's member pool and cap coordinate.

Offline hardening identical to replay_f1b_downstream.py: same-day web cache
only (providers fail-closed), zero-vector embedding (vector membership
differs from production but cannot outrank local projection candidates —
all locals carry raw_score=1.0, vector carries cosine<1.0), LLM judges off,
Milvus Lite opened on a WAL-consistent byte copy (18188 holds the live lock).
The candidate window is patched per run via the module constant, exactly the
knob the production proposal provider reads (knowledge_serving_isolated.py
:737-752); the planning-policy ceiling is loaded once at the max window.

No network, no writes outside this directory's JSON output (+ /var/tmp
scratch for the index copy).
"""

from __future__ import annotations

import faulthandler
import json
import os
import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/miroflow-agent"))

os.environ.setdefault("TURN_TRACE_DIR", str(ROOT / "var" / "turn-trace"))
os.environ.setdefault("BOCHA_API_KEY", "probe-offline-construction-only")
os.environ.setdefault("SERPER_API_KEY", "probe-offline-construction-only")

warnings.filterwarnings("ignore")
faulthandler.dump_traceback_later(120, repeat=True)


def _mark(stage: str) -> None:
    print(f"[probe] {stage}", flush=True)


WINDOWS = (64, 128, 160, 192)
MAX_WINDOW = max(WINDOWS)

import src.data_agents.canonical_v2.knowledge_serving_isolated as serving  # noqa: E402

# Patch the ceiling BEFORE load: planning_policy.max_candidates is computed at
# load time (knowledge_serving_isolated.py:6085). The proposal provider reads
# the constant per plan call, so per-window runs only re-plan, never reload.
serving._ENUMERATION_CANDIDATE_WINDOW = MAX_WINDOW

from src.data_agents.canonical_v2 import serving_pack_loader as pack_loader  # noqa: E402
from src.data_agents.canonical_v2 import index_projection_isolated as ipi  # noqa: E402
from src.data_agents.canonical_v2.contracts import PublishedRelease  # noqa: E402
from src.data_agents.canonical_v2.knowledge_read import (  # noqa: E402
    CanonicalEntityHandle,
    QueryPlanningRequest,
    RetrievalPlan,
)

# Offline: no LLM judgments anywhere (web gap judge + supplemental judge).
serving.create_llm_judge = lambda: None  # noqa: E731

_orig_open_milvus_client = ipi._open_milvus_client
_milvus_copies: dict[str, Path] = {}


def _open_milvus_copy(path: Path) -> object:
    import sqlite3

    source_path = str(Path(path))
    if source_path not in _milvus_copies:
        scratch_dir = Path("/var/tmp/s2d-probe-index") / Path(path).parent.name
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
OUT = Path(__file__).with_name("aq-s2d-window-probe.json")

SCENARIOS = (
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
    },
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
        "gt": ("普渡", "开普勒", "云迹", "九号", "擎朗", "艾唯尔", "安赛步", "锐曼"),
    },
)


class _ZeroEmbedding:
    """Deterministic pseudo-embedding (see replay_f1b_downstream.py)."""

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


_rerank_capture: dict[str, object] = {"request": None, "proposal": None}


def _wrap_reranker(fn):
    def wrapped(request):
        _rerank_capture["request"] = request
        proposal = fn(request)
        _rerank_capture["proposal"] = proposal
        return proposal

    return wrapped


def _position(alias: str, names: list[str]) -> int | None:
    for index, name in enumerate(names, start=1):
        if alias in name:
            return index
    return None


def main() -> None:
    _mark("load recorded inputs start")
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
        prose_renderer=lambda result: "PROBE",
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
    _mark("read composed")

    report: dict[str, object] = {"windows": list(WINDOWS), "scenarios": []}
    for spec in SCENARIOS:
        per_window: dict[str, object] = {}
        for window in WINDOWS:
            serving._ENUMERATION_CANDIDATE_WINDOW = window
            session_id = f"session:probe:s2d:{spec['id']}:{window}"
            plan = planner.plan(
                QueryPlanningRequest(
                    request_id=f"probe:s2d:{spec['id']}:{window}",
                    release_id=RELEASE_ID,
                    original_query=spec["query"],
                    as_of=spec["as_of"],
                    displayed_entity_ids=(),
                    displayed_entity_names=(),
                    enumeration_context=None,
                    soft_context_subject=None,
                )
            )
            plan = RetrievalPlan.model_validate(
                {
                    **plan.model_dump(exclude={"content_sha256"}),
                    "session_id": session_id,
                }
            )
            started = time.monotonic()
            evidence_set = read.execute(plan)
            execute_s = round(time.monotonic() - started, 3)

            rerank_request = _rerank_capture["request"]
            rerank_proposal = _rerank_capture["proposal"]
            name_by_result_id = {
                candidate.result_id: candidate.display_name
                for candidate in rerank_request.eligible_candidates
            }
            # The window-cut coordinate: the reranker's fused order; the read
            # layer then applies ordered[:candidate_limit].
            fused_names = [
                name_by_result_id.get(result_id, result_id)
                for result_id in rerank_proposal.ordered_result_ids
            ]
            handle_names = [
                str(getattr(handle, "display_name", ""))
                for handle in evidence_set.entity_handles
            ]
            disclosure_names = [
                handle.display_name
                for handle in evidence_set.entity_handles
                if isinstance(handle, CanonicalEntityHandle)
                and handle.domain == "company"
            ]
            gt_rows = []
            for alias in spec["gt"]:
                gt_rows.append(
                    {
                        "alias": alias,
                        "fused_abs": _position(alias, fused_names),
                        "handle": _position(alias, handle_names),
                        "disclosure": _position(alias, disclosure_names),
                        "in_window": _position(alias, handle_names) is not None,
                    }
                )
            listing = "、".join(disclosure_names)
            per_window[str(window)] = {
                "plan_max_candidates": plan.max_candidates,
                "plan_web_max_results": plan.web_policy.max_results,
                "execute_seconds": execute_s,
                "eligible_count": len(fused_names),
                "handle_count": len(handle_names),
                "disclosure_pool": len(disclosure_names),
                "evidence_item_count": len(evidence_set.items),
                "sentence_chars_if_all_unmentioned": len(
                    f"此外，本次检索还召回以下相关本地企业：{listing}。"
                ),
                "gt": gt_rows,
                "disclosure_names": disclosure_names,
            }
            _mark(f"{spec['id']} window={window} done ({execute_s}s)")
        report["scenarios"].append(
            {"id": spec["id"], "query": spec["query"], "windows": per_window}
        )

    serving._ENUMERATION_CANDIDATE_WINDOW = 64
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    for scenario in report["scenarios"]:
        print(f"=== {scenario['id']}: {scenario['query']}")
        for window, data in scenario["windows"].items():
            covered = sum(1 for row in data["gt"] if row["in_window"])
            print(
                f"  window={window} plan_max={data['plan_max_candidates']} "
                f"web_max={data['plan_web_max_results']} "
                f"eligible={data['eligible_count']} "
                f"handles={data['handle_count']} "
                f"pool={data['disclosure_pool']} "
                f"items={data['evidence_item_count']} "
                f"exec={data['execute_seconds']}s "
                f"sentence_chars={data['sentence_chars_if_all_unmentioned']} "
                f"gt_in_window={covered}/{len(data['gt'])}"
            )
            for row in data["gt"]:
                print("   ", row)


if __name__ == "__main__":
    main()
