#!/usr/bin/env python3
"""Offline per-stage latency decomposition of the canonical-v2 retrieval path.

Question: the live serving entry (18188) answers ``大疆创新主要做什么`` in
72-84s with TTFT = retrieval + ~1.2s, and the retrieval segment alone is
73.1s. Component measurements already excluded the obvious suspects (all 8 web
searches cache-hit, top pages 0.3-1.6s, embedding 0.04s, gap judge 1.8s
timeout) — the time is somewhere else. This harness re-runs the SAME six turns
offline through the production composite (pack authority + production
planner/read/reranker/selector) with production-config components and records
a wall/CPU time for every step worth naming.

What is timed (per turn):

  planner
    plan.total            QueryPlanningRequest -> RetrievalPlan
    plan.proposal         the recorded proposal provider (view assembly)
    plan.rewrite.live     the real LLM query rewriter (2.0s hard timeout)
  read  (the "retrieval segment": chat.py retrieval_done - plan_done)
    read.outer            iso._ReleaseBoundKnowledgeRead.execute
    read.delegate         the inner KnowledgeRead.execute (lanes + assembly)
    read.outer_overhead   the isolated wrapper's own validation work
    iso.validate.*        the named pre/post validators (vector/internal/rel.)
    read.lane.<name>      every lane (web runs concurrently with local lanes)
    read.rerank           _serving_reranker (deterministic)
    read.sufficiency      the serving sufficiency decider
    read.supplemental     the supplemental probe+fetch+judge pipeline
  web lane internals (both the main lane adapter and the supplemental probe one)
    web.views             _merged_results_for_views (per call: views + wall)
    web.merged            _merged_results (single-view call)
    web.provider.search   _provider_search (per provider x view, cache hit?)
    web.enrich            _enrich_with_page_text (per call: depth + wall)
    web.fetch.page        one page fetch (tier-0 vs tier-1 split, text size)
    web.fetch.warm        the headless-Chromium warm-up
    web.judge.batch       every LLM judgment batch (kind + fail-open outcome)
  post-retrieval (synthesis boundary, for completeness)
    answer.selector       the answer selector
    answer.total          selector + claim grounding + payload assembly + prose
                          call (the prose LLM itself is stubbed -> excluded)
  embedding
    embed.batch / embed.http   the real Qwen endpoint adapter (proxy + HTTP call)

Every stage row also carries a monotonic start/end offset (relative to the read
start) so the report can show which steps overlap. A stack sampler thread runs
at 50ms throughout and records the sampled Python stacks per turn: that is the
evidence for whatever the explicit timers do not name.

Fidelity / deviations (also emitted into the JSON under ``harness.deviations``):

  * query views: production takes them from the LLM rewriter. Default mode
    ``auto`` calls the real rewriter (CHAT_LLM_PROFILE=deepseekv4flash, the
    deployed profile) and falls back to the views recorded in
    var/turn-trace/2026-09-12.jsonl when it returns nothing. ``--rewriter
    replay`` skips the LLM entirely.
  * the turn trace records search *completion* order, not plan order; replay
    extras are the first 3 recorded non-base views in that order.
  * prose LLM: stubbed, so generation time is out (measured live: 1.1-6.8s).
  * the contextual interpreter (3s timeout) runs before planning in chat.py and
    is not part of this harness (live planning ≈ 2s includes it).
  * milvus and the web-lane cache are opened from private copies; the pack,
    index root and release identity checks still run against the real paths.
  * the worktree is imported read-only (sys.dont_write_bytecode = True).

Usage (must run with the worktree venv; the pack load takes ~13 minutes):

  /home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation/.venv/bin/python3 \
      .agents/runs/close-workbook-gaps/latency/latency_harness.py \
      --out-dir .agents/runs/close-workbook-gaps/latency [--only dji-t1] [--smoke]
"""

from __future__ import annotations

import argparse
import contextlib
import faulthandler
import json
import os
import sqlite3
import sys
import threading
import time
import warnings
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

# --------------------------------------------------------------------------
# Paths and interpreter bootstrap (before any worktree import)
# --------------------------------------------------------------------------
HARNESS_PATH = Path(__file__).resolve()
MAIN_ROOT = HARNESS_PATH.parents[4]
WORKTREE = Path(
    os.getenv(
        "LATENCY_WORKTREE",
        str(MAIN_ROOT / ".worktrees" / "canonical-v2-s11-consolidation"),
    )
)
APP_ROOT = WORKTREE / "apps" / "miroflow-agent"
RUN_ROOT = WORKTREE / ".agents" / "runs" / "rebuild-canonical-v2-knowledge-platform"

PACK_DIR = Path("/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed")
INDEX_ROOT = Path("/var/tmp/mirothinker-data-v2/index-v1")
RELEASE_ID = "candidate-v2-20260819-r1"
BUNDLE_PATH = RUN_ROOT / "s12g" / "serving-bundle-run14.json"
BUNDLE_SHA = "846d3a580554376d3c4e22fcc705ec1518303d70943a9b746d7d9ae16d27299c"
EMBEDDING_BUNDLE = RUN_ROOT / "s12c" / "qwen-embedding-bundle-v1.json"
INDEX_MARKER_SHA = "8848197caaa665fa093f054aa6c7c241b90376f311ec62e089ddb479a6e97c8b"
ENVELOPE_PATH = RUN_ROOT / "s12a" / "complete-candidate-build-envelope.json"
FORBIDDEN_MILVUS = MAIN_ROOT / "apps" / "miroflow-agent" / "milvus.db"
TRACE_JOURNAL = WORKTREE / "var" / "turn-trace" / "2026-09-12.jsonl"
WEB_LANE_DB = WORKTREE / "var" / "turn-trace" / "web_lane.sqlite3"

DEFAULT_OUT_DIR = HARNESS_PATH.parent
SCRATCH = Path(os.getenv("LATENCY_SCRATCH", "/var/tmp/latency-harness"))
MILVUS_SCRATCH = SCRATCH / "index-copy"
TURN_TRACE_SCRATCH = SCRATCH / "turn-trace"

sys.dont_write_bytecode = True  # never leave .pyc files in the worktree
sys.path.insert(0, str(APP_ROOT))

os.environ.setdefault("TURN_TRACE_DIR", str(TURN_TRACE_SCRATCH))
# The deployed entry runs with this profile (deploy/README.md; live 18188 env);
# both the query rewriter and the LLM judge read it.
os.environ.setdefault("CHAT_LLM_PROFILE", os.getenv("CHAT_LLM_PROFILE", "deepseekv4flash"))

warnings.filterwarnings("ignore")
faulthandler.dump_traceback_later(180, repeat=True)


def _mark(stage: str) -> None:
    print(f"[latency] {time.strftime('%H:%M:%S')} {stage}", flush=True)


# --------------------------------------------------------------------------
# Recorder
# --------------------------------------------------------------------------
class Recorder:
    """Wall/CPU/thread-time rows plus monotonic offsets for the current turn."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._origin = time.perf_counter()
        self.rows: list[dict] = []
        self.counters: Counter[str] = Counter()

    def reset(self) -> None:
        with self._lock:
            self._origin = time.perf_counter()
            self.rows = []
            self.counters = Counter()

    def record(
        self,
        name: str,
        wall: float,
        *,
        cpu: float | None = None,
        thread_cpu: float | None = None,
        started: float | None = None,
        **meta: object,
    ) -> None:
        row = {
            "name": name,
            "wall_s": round(wall, 4),
            "t_start_s": round((started if started is not None else time.perf_counter()) - self._origin, 3),
            "t_end_s": round(time.perf_counter() - self._origin, 3),
            "thread": threading.current_thread().name,
        }
        if cpu is not None:
            row["cpu_s"] = round(cpu, 4)
        if thread_cpu is not None:
            row["thread_cpu_s"] = round(thread_cpu, 4)
        clean = {key: value for key, value in meta.items() if value is not None}
        if clean:
            row["meta"] = clean
        with self._lock:
            self.rows.append(row)

    @contextlib.contextmanager
    def stage(self, name: str, **meta: object):
        wall0 = time.perf_counter()
        cpu0 = time.process_time()
        thread0 = time.thread_time()
        try:
            yield
        finally:
            self.record(
                name,
                time.perf_counter() - wall0,
                cpu=time.process_time() - cpu0,
                thread_cpu=time.thread_time() - thread0,
                started=wall0,
                **meta,
            )

    def count(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self.counters[key] += amount

    def bump(self, key: str, value: float) -> None:
        with self._lock:
            self.counters[key] += value

    def totals(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        with self._lock:
            for row in self.rows:
                totals[row["name"]] = round(
                    totals.get(row["name"], 0.0) + row["wall_s"], 4
                )
        return totals


RECORDER = Recorder()


class StackSampler(threading.Thread):
    """50ms Python-stack sampler: names whatever the explicit timers miss."""

    def __init__(self, interval: float = 0.05) -> None:
        super().__init__(daemon=True, name="latency-stack-sampler")
        self.interval = interval
        self._stop = threading.Event()
        self.phase = "boot"
        self.phase_samples: Counter[tuple[str, str, str]] = Counter()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.wait(self.interval):
            phase = self.phase
            try:
                frames = sys._current_frames()
            except Exception:  # noqa: BLE001
                continue
            names = {thread.ident: thread.name for thread in threading.enumerate()}
            for ident, frame in frames.items():
                label = names.get(ident, f"tid:{ident}")
                if label == self.name:
                    continue
                labels: list[str] = []
                current = frame
                while current is not None and len(labels) < 6:
                    labels.append(
                        f"{current.f_code.co_name}"
                        f"@{current.f_code.co_filename.rsplit('/', 1)[-1]}:{current.f_lineno}"
                    )
                    current = current.f_back
                self.phase_samples[(phase, label, " <- ".join(labels[:4]))] += 1

    def snapshot(self, phase: str, limit: int = 12) -> dict:
        rows = [
            {"thread": label, "stack": stack, "samples": count}
            for (phase_key, label, stack), count in self.phase_samples.most_common()
            if phase_key == phase
        ]
        thread_totals: Counter[str] = Counter()
        stack_totals: Counter[str] = Counter()
        for (phase_key, label, stack), count in self.phase_samples.items():
            if phase_key != phase:
                continue
            thread_totals[label] += count
            stack_totals[stack] += count
        return {
            "samples": sum(thread_totals.values()),
            "by_thread": dict(thread_totals.most_common()),
            "top_stacks": [
                {"stack": stack, "samples": count}
                for stack, count in stack_totals.most_common(limit)
            ],
            "raw_rows": rows[: limit * 2],
        }


SAMPLER = StackSampler()


# --------------------------------------------------------------------------
# Recorded turns (from the live turn-trace journal)
# --------------------------------------------------------------------------
# Recorded turns (from the live turn-trace journal). The journal is written by
# the running 18188 entry, so rows are looked up by (query, turn_ordinal) once
# at startup rather than by line index. PCB turn 2 is a continuation turn of
# the PCB session ("上述企业有哪些是深圳的企业", turn_ordinal 2).
TURNS: tuple[dict, ...] = (
    {"id": "dji-t1", "session": "lat-dji", "query": "大疆创新主要做什么", "turn_ordinal": 1},
    {
        "id": "professor-t1",
        "session": "lat-professor",
        "query": "深圳有哪些研究机器人的教授",
        "turn_ordinal": 1,
    },
    {
        "id": "lidar-t1",
        "session": "lat-lidar",
        "query": "深圳有哪些做激光雷达的公司",
        "turn_ordinal": 1,
    },
    {
        "id": "g2-t1",
        "session": "lat-g2",
        "query": "中国有哪些成熟的酒店送餐机器人供应商",
        "turn_ordinal": 1,
    },
    {
        "id": "pcb-t1",
        "session": "lat-pcb",
        "query": "我想找PCB打板， 有哪些推荐",
        "turn_ordinal": 1,
    },
    {
        "id": "pcb-t2",
        "session": "lat-pcb",
        "query": "上述企业有哪些是深圳的企业",
        "turn_ordinal": 2,
        "continuation": True,
    },
)

_ENUMERATION_MARKERS = ("哪些", "谁", "多少", "几个", "列出", "所有", "分别")


def _read_trace() -> list[dict]:
    if not TRACE_JOURNAL.is_file():
        return []
    return [
        json.loads(line)
        for line in TRACE_JOURNAL.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _recorded_turn(row: dict | None) -> dict:
    if not row:
        return {}
    started = datetime.fromisoformat(row["ts_start"])
    ended = datetime.fromisoformat(row["ts_end"])
    bocha_views = [
        outcome["view"]
        for outcome in row.get("web_outcomes", ())
        if outcome.get("provider") == "bocha-v1"
    ]
    distinct: list[str] = []
    for view in bocha_views:
        if view != row["query_raw"] and view not in distinct:
            distinct.append(view)
    return {
        "total_s": round((ended - started).total_seconds(), 2),
        "as_of": started,
        "lanes": row.get("lanes", {}),
        "degradation": row.get("degradation"),
        "views": tuple(distinct),
        "session_id": row.get("session_id"),
    }


def _index_trace(trace: list[dict]) -> dict[tuple[str, int], dict]:
    """First (earliest) journal row per (query, turn_ordinal), replay-ready."""

    indexed: dict[tuple[str, int], dict] = {}
    for row in trace:
        key = (str(row.get("query_raw", "")), int(row.get("turn_ordinal", 0) or 0))
        if key not in indexed:
            indexed[key] = _recorded_turn(row)
    return indexed


# --------------------------------------------------------------------------
# Offline hardening: private Milvus + web-lane cache copies
# --------------------------------------------------------------------------
def _prepare_web_lane_cache() -> dict:
    """Byte-copy the live web-lane cache (WAL-safe) into the scratch root."""

    TURN_TRACE_SCRATCH.mkdir(parents=True, exist_ok=True)
    target = TURN_TRACE_SCRATCH / "web_lane.sqlite3"
    info = {"source": str(WEB_LANE_DB), "copy": str(target), "rows": None}
    if WEB_LANE_DB.is_file():
        source = sqlite3.connect(f"file:{WEB_LANE_DB}?mode=ro", uri=True)
        dest = sqlite3.connect(target)
        with dest:
            source.backup(dest)
        source.close()
        dest.close()
    try:
        connection = sqlite3.connect(target)
        rows = connection.execute(
            "SELECT day, COUNT(*) FROM web_cache GROUP BY day"
        ).fetchall()
        info["rows_by_day"] = {str(day): int(count) for day, count in rows}
        connection.close()
    except sqlite3.Error as exc:  # pragma: no cover - diagnostics only
        info["error"] = str(exc)
    return info


def _install_milvus_copy_patch(index_projection_module) -> dict:
    """Redirect ONLY the Milvus file open to a private byte copy.

    The live 18188 server holds the exclusive Milvus Lite lock on the sealed
    index root; the marker/root/identity checks still run against the real
    root, so the copy is transparent to every integrity gate (same technique
    as .agents/runs/close-workbook-gaps/d0-probe/replay_f1b_downstream.py).
    """

    original = index_projection_module._open_milvus_client
    copies: dict[str, Path] = {}
    stats: dict[str, float] = {}

    def open_copy(path: Path) -> object:
        source_path = str(Path(path))
        if source_path not in copies:
            target_dir = MILVUS_SCRATCH / Path(path).parent.name
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / Path(path).name
            source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
            dest = sqlite3.connect(target)
            with dest:
                source.backup(dest)
            source.close()
            dest.close()
            copies[source_path] = target
        started = time.perf_counter()
        handle = original(copies[source_path])
        stats[source_path] = round(time.perf_counter() - started, 3)
        return handle

    index_projection_module._open_milvus_client = open_copy
    return {"copies": {key: str(value) for key, value in copies.items()}, "stats": stats, "_state": copies, "_stats_ref": stats}


# --------------------------------------------------------------------------
# Instrumented components
# --------------------------------------------------------------------------
class CaptureProse:
    """Prose renderer stand-in: records the payload, returns a fixed string."""

    def __init__(self) -> None:
        self.payloads: list[object] = []

    def __call__(self, result: object) -> str:
        self.payloads.append(result)
        return "LATENCY-HARNESS-PROSE-STUB"


class LiveRewriter:
    """Production _ServingQueryRewriter behind the harness's replay fallback."""

    def __init__(self, rewriter: object, mode: str, recorded: tuple[str, ...]) -> None:
        self._rewriter = rewriter
        self._mode = mode
        self._recorded = recorded
        self.last_source = "none"
        self.last_views: tuple[str, ...] = ()
        self.last_live_views: tuple[str, ...] = ()

    @property
    def producer_version(self) -> str:
        if self._rewriter is None:
            return "latency-harness-recorded-views-v1"
        return str(getattr(self._rewriter, "producer_version", "latency-harness-live"))

    def __call__(self, query: str) -> tuple[str, ...]:
        self.last_live_views = ()
        if self._mode != "replay" and self._rewriter is not None:
            with RECORDER.stage("plan.rewrite.live", query=query):
                live = tuple(self._rewriter(query))
            self.last_live_views = live
            RECORDER.count("plan.rewrite.live.calls")
            if live:
                self.last_source = "live"
                self.last_views = live
                return live
            RECORDER.count("plan.rewrite.live.empty")
        self.last_source = "replay"
        self.last_views = self._recorded[:3]
        RECORDER.count("plan.rewrite.replay")
        return self.last_views


def _make_page_fetcher(recorder: Recorder):
    from src.data_agents.providers import page_fetch

    direct_times: dict[str, float] = {}
    lock = threading.Lock()

    def direct(url: str) -> str | None:
        started = time.perf_counter()
        text = page_fetch.fetch_page_text(url)
        with lock:
            direct_times[url] = time.perf_counter() - started
        return text

    tiered = page_fetch.create_tiered_page_fetcher(direct_fetcher=direct)

    def fetch(url: str) -> str | None:
        started = time.perf_counter()
        text = tiered(url)
        wall = time.perf_counter() - started
        with lock:
            direct_s = direct_times.pop(url, None)
        recorder.record(
            "web.fetch.page",
            wall,
            started=started,
            url=url[:120],
            text_chars=len(text or ""),
            direct_s=None if direct_s is None else round(direct_s, 4),
            tier1_s=None if direct_s is None else round(wall - direct_s, 4),
        )
        return text

    def warm(timeout: float = 10.0) -> bool:
        with recorder.stage("web.fetch.warm"):
            return bool(tiered.warm(timeout))

    fetch.warm = warm  # type: ignore[attr-defined]
    return fetch


def _wrap_lane_callables(delegate: object, recorder: Recorder) -> None:
    """Time every lane the read delegate runs (each on its own thread)."""

    def wrap(name: str, fn):
        def wrapped(request):
            with recorder.stage(f"read.lane.{name}", query_view=getattr(request, "query_view", None)):
                result = fn(request)
            recorder.count(f"read.lane.{name}.calls")
            try:
                recorder.bump(f"read.lane.{name}.candidates", len(result.candidates))
                recorder.bump(f"read.lane.{name}.items", len(result.items))
            except Exception:  # noqa: BLE001
                pass
            return result

        return wrapped

    for lane_name, lane_fn in list(delegate._lane_adapters.items()):
        delegate._lane_adapters[lane_name] = wrap(lane_name, lane_fn)
    delegate._web_search = wrap("web", delegate._web_search)


def _instrument_web_lane_class(serving_module, recorder: Recorder) -> dict:
    """Patch _DualWebLaneAdapter (main lane + supplemental probe adapter)."""

    from src.data_agents.canonical_v2 import web_lane_resilience as resilience

    adapter_class = serving_module._DualWebLaneAdapter
    roles: dict[int, str] = {}
    state = {"main_adapter_id": None}

    def role_for(adapter: object) -> str:
        if id(adapter) == state["main_adapter_id"]:
            return "main"
        return roles.setdefault(id(adapter), "probe")

    original_provider_search = adapter_class._provider_search
    original_merged_results = adapter_class._merged_results
    original_merged_for_views = adapter_class._merged_results_for_views
    original_enrich = adapter_class._enrich_with_page_text

    def provider_search(self, provider, query, provider_version=None, reporter=None, error_flags=None):
        cached: bool | None = None
        if provider_version is not None:
            try:
                day = resilience._utc_day(self._clock)
                cached = (
                    self._resilience_store.cache_get(
                        provider_version, resilience.view_cache_key(query), day
                    )
                    is not None
                )
            except Exception:  # noqa: BLE001 - diagnostics only
                cached = None
        started = time.perf_counter()
        results = original_provider_search(
            self, provider, query, provider_version, reporter, error_flags
        )
        recorder.record(
            "web.provider.search",
            time.perf_counter() - started,
            started=started,
            role=role_for(self),
            provider=provider_version or "unversioned",
            view=query[:90],
            cache_hit=None if cached is None else int(cached),
            results=len(results),
        )
        return results

    def merged_results(self, query):
        started = time.perf_counter()
        merged = original_merged_results(self, query)
        recorder.record(
            "web.merged",
            time.perf_counter() - started,
            started=started,
            role=role_for(self),
            view=str(query)[:90],
            merged=len(merged),
        )
        return merged

    def merged_for_views(self, queries):
        started = time.perf_counter()
        merged = original_merged_for_views(self, queries)
        recorder.record(
            "web.views",
            time.perf_counter() - started,
            started=started,
            role=role_for(self),
            query_count=len(queries),
            views=" | ".join(str(item)[:60] for item in queries),
            merged=len(merged),
        )
        return merged

    def enrich(self, results, depth: int = 2):
        started = time.perf_counter()
        enriched = original_enrich(self, results, depth=depth)
        recorder.record(
            "web.enrich",
            time.perf_counter() - started,
            started=started,
            role=role_for(self),
            depth=depth,
            candidates=len(results),
        )
        return enriched

    adapter_class._provider_search = provider_search
    adapter_class._merged_results = merged_results
    adapter_class._merged_results_for_views = merged_for_views
    adapter_class._enrich_with_page_text = enrich
    state["roles"] = roles
    return state


def _instrument_judge_class(recorder: Recorder) -> None:
    from src.data_agents.canonical_v2 import llm_judgments

    original = llm_judgments._LlmJudge.judge_batch

    def judge_batch(self, kind, question, items, context=""):
        started = time.perf_counter()
        results = original(self, kind, question, items, context)
        recorder.record(
            "web.judge.batch",
            time.perf_counter() - started,
            started=started,
            kind=str(kind),
            item_count=len(items) if hasattr(items, "__len__") else None,
            outcome=str(getattr(self, "last_outcome", "")),
            results=len(results) if hasattr(results, "__len__") else None,
        )
        return results

    llm_judgments._LlmJudge.judge_batch = judge_batch


class InstrumentedEmbedding:
    """Attribute-preserving proxy: the production adapter is a slots dataclass.

    The vector lane validates model_id/dimension/embed_batch through
    _ValidatingEmbeddingAdapter, so a delegating proxy is transparent; the HTTP
    call itself is timed by patching EmbeddingClient.embed_batch.
    """

    def __init__(self, inner: object, recorder: Recorder) -> None:
        self._inner = inner
        self._recorder = recorder
        self.model_id = getattr(inner, "model_id")
        self.dimension = getattr(inner, "dimension")
        self.authority_sha256 = getattr(inner, "authority_sha256", None)
        self.base_url = getattr(inner, "base_url", None)

    def embed_batch(self, texts):
        started = time.perf_counter()
        vectors = self._inner.embed_batch(texts)
        wall = time.perf_counter() - started
        self._recorder.record(
            "embed.batch",
            wall,
            started=started,
            texts=len(texts),
            chars=sum(len(str(text)) for text in texts),
            cache_served=bool(wall < 0.001 and texts),
        )
        return vectors


def _instrument_embedding_adapter(adapter: object, recorder: Recorder) -> object:
    from src.data_agents.company import vectorizer as embedding_client_module

    proxy = InstrumentedEmbedding(adapter, recorder)
    client_class = embedding_client_module.EmbeddingClient
    if not getattr(client_class, "_latency_harness_patched", False):
        original = client_class.embed_batch

        def embed_batch(self, texts, *, model: str = ""):
            started = time.perf_counter()
            vectors = (
                original(self, texts, model=model)
                if model
                else original(self, texts)
            )
            recorder.record(
                "embed.http",
                time.perf_counter() - started,
                started=started,
                texts=len(texts),
                base_url=str(getattr(self, "base_url", ""))[:60],
            )
            return vectors

        client_class.embed_batch = embed_batch
        client_class._latency_harness_patched = True  # type: ignore[attr-defined]
    return proxy


def _instrument_isolated_validators(iso_module, recorder: Recorder) -> None:
    for name in (
        "_validate_release_bound_vector_evidence",
        "_validate_release_bound_internal_reference_evidence",
        "_validate_release_bound_relationship_evidence",
        "_validate_internal_reference_request",
        "_validate_relationship_request",
        "_build_relationship_result",
    ):
        original = getattr(iso_module, name, None)
        if original is None:
            continue

        def make(original_fn, label):
            def wrapper(*args, **kwargs):
                with recorder.stage(f"iso.{label}"):
                    return original_fn(*args, **kwargs)

            return wrapper

        setattr(iso_module, name, make(original, name.removeprefix("_")))


# --------------------------------------------------------------------------
# Report helpers
# --------------------------------------------------------------------------
def _stage_table(rows: list[dict], names: list[str] | None = None) -> list[dict]:
    totals: dict[str, float] = {}
    counts: Counter[str] = Counter()
    cpu: dict[str, float] = {}
    for row in rows:
        totals[row["name"]] = totals.get(row["name"], 0.0) + row["wall_s"]
        cpu[row["name"]] = cpu.get(row["name"], 0.0) + row.get("cpu_s", 0.0)
        counts[row["name"]] += 1
    table = [
        {
            "stage": name,
            "calls": counts[name],
            "wall_s": round(wall, 3),
            "cpu_s": round(cpu.get(name, 0.0), 3),
        }
        for name, wall in totals.items()
    ]
    table.sort(key=lambda item: item["wall_s"], reverse=True)
    if names is not None:
        order = {name: index for index, name in enumerate(names)}
        table.sort(key=lambda item: (order.get(item["stage"], 10_000), -item["wall_s"]))
    return table


def _sum(rows: list[dict], name: str) -> float:
    return round(sum(row["wall_s"] for row in rows if row["name"] == name), 3)


def _rows(rows: list[dict], name: str) -> list[dict]:
    return [row for row in rows if row["name"] == name]


def _dump_handles(
    *,
    out_dir: Path,
    spec: dict,
    evidence_set: object,
    selection: object | None,
    answer_result: object | None,
) -> None:
    """Mention audit for one turn: which recalled handles the answer named.

    The coverage sentence (knowledge_answer._enumeration_member_coverage_sentence)
    lists unmentioned company handles; when a GT member goes missing from an
    enumeration answer this dump shows whether the handle was never recalled
    or the mention filter wrongly folded it in.
    """
    from src.data_agents.canonical_v2.knowledge_answer import (
        _prose_mention_name_forms,
    )
    from src.data_agents.canonical_v2.knowledge_read import CanonicalEntityHandle

    handles = list(getattr(evidence_set, "entity_handles", ()))
    final_text = (
        None
        if answer_result is None
        else str(getattr(answer_result, "answer_text", "") or "")
    )
    folded = "" if final_text is None else final_text.casefold()

    def mentioned(name: str) -> bool:
        return any(form in folded for form in _prose_mention_name_forms(name))

    dump = {
        "turn": spec["id"],
        "query": spec["query"],
        "handle_count": len(handles),
        "handles": [
            {
                "display_name": str(getattr(handle, "display_name", "")),
                "domain": str(getattr(handle, "domain", "")),
                "kind": str(getattr(handle, "kind", "canonical")),
                "public_id": (
                    getattr(handle, "canonical_id", None)
                    if getattr(handle, "kind", "canonical") == "canonical"
                    else getattr(handle, "handle_id", None)
                ),
            }
            for handle in handles
        ],
        "company_handles": [
            str(getattr(handle, "display_name", ""))
            for handle in handles
            if isinstance(handle, CanonicalEntityHandle)
            and getattr(handle, "domain", None) == "company"
        ],
        "mention_forms_by_company": {
            str(getattr(handle, "display_name", "")): list(
                _prose_mention_name_forms(str(getattr(handle, "display_name", "")))
            )
            for handle in handles
            if isinstance(handle, CanonicalEntityHandle)
            and getattr(handle, "domain", None) == "company"
        },
        "mentioned_in_final_answer": [
            str(getattr(handle, "display_name", ""))
            for handle in handles
            if isinstance(handle, CanonicalEntityHandle)
            and getattr(handle, "domain", None) == "company"
            and mentioned(str(getattr(handle, "display_name", "")))
        ],
        "unmentioned_companies": [
            str(getattr(handle, "display_name", ""))
            for handle in handles
            if isinstance(handle, CanonicalEntityHandle)
            and getattr(handle, "domain", None) == "company"
            and not mentioned(str(getattr(handle, "display_name", "")))
        ],
        "selection_displayed_handle_ids": (
            [] if selection is None else [str(value) for value in selection.displayed_handle_ids]
        ),
        "fused_candidate_count": len(getattr(evidence_set, "fused_candidates", ())),
        "evidence_item_count": len(getattr(evidence_set, "items", ())),
        "final_answer_text": final_text,
    }
    path = out_dir / f"handles-{spec['id']}.json"
    path.write_text(
        json.dumps(dump, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    _mark(f"wrote {path}")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--only", default="")
    parser.add_argument("--rewriter", choices=("auto", "live", "replay"), default="auto")
    parser.add_argument("--smoke", action="store_true", help="only the 大疆 turn")
    parser.add_argument("--no-answer", action="store_true", help="skip selector/answer")
    parser.add_argument("--json-name", default="latency-breakdown.json")
    parser.add_argument("--md-name", default="latency-breakdown.md")
    parser.add_argument(
        "--dump-handles",
        action="store_true",
        help="write handles-<turn>.json: entity handles + mention audit per turn",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    only = {item.strip() for item in args.only.split(",") if item.strip()}
    if args.smoke:
        only = {"dji-t1"}

    profile = os.getenv("CHAT_LLM_PROFILE", "")
    _mark(f"bootstrap: worktree={WORKTREE} chat_llm_profile={profile}")
    cache_info = _prepare_web_lane_cache()
    _mark(f"web-lane cache copied: {cache_info}")

    import_started = time.perf_counter()
    from src.data_agents.canonical_v2 import knowledge_answer as answer_module
    from src.data_agents.canonical_v2 import knowledge_build_isolated as build_iso
    from src.data_agents.canonical_v2 import knowledge_read as read_module
    from src.data_agents.canonical_v2 import knowledge_read_isolated as iso
    from src.data_agents.canonical_v2 import knowledge_serving_isolated as serving
    from src.data_agents.canonical_v2 import serving_pack_loader as pack_loader
    from src.data_agents.canonical_v2 import index_projection_isolated as ipi
    from src.data_agents.canonical_v2.contracts import PublishedRelease
    from src.data_agents.canonical_v2.knowledge_answer import TurnRequest
    from src.data_agents.canonical_v2.knowledge_read import (
        EnumerationPlanningContext,
        QueryPlanningRequest,
        RetrievalPlan,
    )

    import_s = time.perf_counter() - import_started
    _mark(f"worktree modules imported in {import_s:.1f}s")

    milvus_patch = _install_milvus_copy_patch(ipi)
    _instrument_judge_class(RECORDER)
    _instrument_isolated_validators(iso, RECORDER)

    trace_rows = _read_trace()
    recorded_turns = _index_trace(trace_rows)
    turns = [spec for spec in TURNS if not only or spec["id"] in only]
    _mark(f"turn set: {[spec['id'] for spec in turns]}")

    recorder = RECORDER
    prose = CaptureProse()
    page_fetcher = _make_page_fetcher(recorder)

    # --- composition (production config) --------------------------------
    _mark("loading recorded serving inputs (embedding adapter + real components)")
    embedding_adapter = build_iso.load_content_addressed_embedding_adapter(EMBEDDING_BUNDLE)
    embedding_adapter = _instrument_embedding_adapter(embedding_adapter, recorder)

    proposal_holder: dict[str, object] = {}

    def proposal_provider(request):
        with recorder.stage("plan.proposal"):
            return proposal_holder["inner"](request)

    recorded = None
    rewriter_holder: dict[str, LiveRewriter] = {}

    def query_rewriter(query: str) -> tuple[str, ...]:
        spec = next((item for item in turns if item["query"] == query), None)
        recorded_views = (
            recorded_turns.get((query, spec["turn_ordinal"]), {}).get("views", ())
            if spec is not None
            else ()
        )
        rewriter = LiveRewriter(
            serving._ServingQueryRewriter() if args.rewriter != "replay" else None,
            args.rewriter,
            tuple(recorded_views),
        )
        rewriter_holder["current"] = rewriter
        return rewriter(query)

    # Cache day is pinned per turn through this holder so the replay hits the
    # same UTC-day cache rows the live 09-12 turns wrote. The same clock object
    # is handed to the loader so the web lane and the supplemental probe
    # adapter both read it.
    clock_holder = {"now": datetime.now(UTC)}

    def served_clock() -> datetime:
        return clock_holder["now"]

    load_started = time.perf_counter()
    recorded = serving.load_recorded_serving_inputs(
        path=BUNDLE_PATH,
        expected_content_sha256=BUNDLE_SHA,
        expected_release_id=RELEASE_ID,
        expected_database="miroflow_candidate_v2_20260819_r1",
        expected_index_root=INDEX_ROOT,
        expected_envelope_path=ENVELOPE_PATH,
        embedding_adapter=embedding_adapter,
        prose_renderer=prose,
        page_fetcher=page_fetcher,
        query_rewriter=query_rewriter,
        clock=served_clock,
    )
    load_inputs_s = time.perf_counter() - load_started
    _mark(f"recorded inputs loaded in {load_inputs_s:.1f}s")

    web_lane_state = _instrument_web_lane_class(serving, recorder)
    web_lane_state["main_adapter_id"] = id(recorded.web_search)

    _mark("opening serving pack authority (this is the ~13 minute step)")
    pack_started = time.perf_counter()
    authority = pack_loader.open_serving_pack_authority(
        pack_dir=PACK_DIR,
        expected_release_id=RELEASE_ID,
        expected_index_marker_sha256=INDEX_MARKER_SHA,
        expected_forbidden_milvus_path=FORBIDDEN_MILVUS,
    )
    pack_open_s = time.perf_counter() - pack_started
    _mark(f"authority opened in {pack_open_s:.1f}s")

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

    proposal_holder["inner"] = recorded.proposal_provider

    planner_started = time.perf_counter()
    planner = pack_loader.create_serving_pack_query_planner(
        authority=authority,
        published_release=published,
        planning_policy=recorded.planning_policy,
        proposal_provider=proposal_provider,
        ambiguity_policy=recorded.ambiguity_policy,
    )
    planner_compose_s = time.perf_counter() - planner_started

    def timing_reranker(request):
        with recorder.stage("read.rerank", eligible=len(request.eligible_candidates)):
            return recorded.reranker(request)

    def timing_sufficiency(request):
        with recorder.stage("read.sufficiency"):
            return recorded.sufficiency_decider(request)

    def timing_supplemental(request):
        with recorder.stage("read.supplemental"):
            return recorded.supplemental_search(request)

    read_started = time.perf_counter()
    read = pack_loader.create_serving_pack_knowledge_read(
        authority=authority,
        published_release=published,
        universal_web_policy=recorded.universal_web_policy,
        web_search=recorded.web_search,
        web_snapshot_policy=recorded.web_snapshot_policy,
        embedding_adapter=recorded.embedding_adapter,
        identity_fuser=recorded.identity_fuser,
        reranker=timing_reranker,
        sufficiency_decider=timing_sufficiency,
        supplemental_search=timing_supplemental,
        web_handle_resolver=recorded.web_handle_resolver,
        accepted_identity_lookup=recorded.accepted_identity_lookup,
    )
    read_compose_s = time.perf_counter() - read_started
    _wrap_lane_callables(read._delegate, recorder)

    bundle = serving._read_bundle(BUNDLE_PATH)
    raw_selector = serving._answer_selector(bundle=bundle)

    def timing_selector(request):
        with recorder.stage("answer.selector"):
            return raw_selector(request)

    outer_execute = read.execute
    delegate_execute = read._delegate.execute

    def timing_delegate_execute(plan):
        with recorder.stage("read.delegate"):
            return delegate_execute(plan)

    read._delegate.execute = timing_delegate_execute

    def timing_outer_execute(plan):
        with recorder.stage("read.outer"):
            return outer_execute(plan)

    read.execute = timing_outer_execute  # type: ignore[method-assign]

    SAMPLER.start()
    _mark("composed; starting turns")

    session_state: dict[str, dict] = {}
    turn_reports: list[dict] = []
    for spec in turns:
        recorded_turn = recorded_turns.get((spec["query"], spec["turn_ordinal"]), {})
        as_of = recorded_turn.get("as_of", datetime.now(UTC))
        clock_holder["now"] = as_of
        recorder.reset()
        SAMPLER.phase = spec["id"]
        _mark(f"turn {spec['id']}: {spec['query']} (recorded {recorded_turn.get('total_s')}s)")

        session = session_state.setdefault(spec["session"], {"displayed": (), "names": (), "answer": None})
        displayed_ids = session["displayed"] if spec.get("continuation") else ()
        displayed_names = session["names"] if spec.get("continuation") else ()
        enumeration_context = (
            EnumerationPlanningContext(
                requested=True,
                scope=spec["query"],
                as_of=as_of,
                finite_universe=None,
            )
            if displayed_ids and any(marker in spec["query"] for marker in _ENUMERATION_MARKERS)
            else None
        )

        request = QueryPlanningRequest(
            request_id=f"latency:{spec['id']}",
            release_id=RELEASE_ID,
            original_query=spec["query"],
            as_of=as_of,
            displayed_entity_ids=tuple(displayed_ids),
            displayed_entity_names=tuple(displayed_names),
            enumeration_context=enumeration_context,
            soft_context_subject=None,
        )

        plan_started = time.perf_counter()
        raw_plan = planner.plan(request)
        plan_wall = time.perf_counter() - plan_started
        recorder.record("plan.total", plan_wall, started=plan_started)

        session_id = f"session:latency-harness:{spec['session']}"
        bind_started = time.perf_counter()
        plan = RetrievalPlan.model_validate(
            {**raw_plan.model_dump(mode="json", exclude={"content_sha256"}), "session_id": session_id}
        )
        recorder.record("plan.session_bind", time.perf_counter() - bind_started, started=bind_started)

        read_wall_started = time.perf_counter()
        evidence_set = read.execute(plan)
        read_wall = time.perf_counter() - read_wall_started

        turn_request = TurnRequest(
            session_id=session_id,
            turn_id=f"turn:latency:{spec['id']}:1",
            query=spec["query"],
            release_id=RELEASE_ID,
            evidence_set=evidence_set,
            assessment_intent=plan.assessment_intent,
        )

        selector_wall = None
        selection = None
        answer_result = None
        if not args.no_answer:
            selector_started = time.perf_counter()
            selection = timing_selector(turn_request)
            selector_wall = time.perf_counter() - selector_started
            recorder.record("answer.selector.external", selector_wall, started=selector_started)

            base_answer = recorded.answer_factory() if session["answer"] is None else session["answer"]
            candidate_answer = recorded.answer_session_fork(base_answer)
            answer_started = time.perf_counter()
            answer_error = None
            answer_result = None
            try:
                answer_result = candidate_answer.answer(turn_request)
            except Exception as exc:  # noqa: BLE001 - payload captured before any raise
                answer_error = f"{type(exc).__name__}: {exc}"
            recorder.record(
                "answer.total",
                time.perf_counter() - answer_started,
                started=answer_started,
                error=answer_error,
            )
            if answer_error is None:
                session["answer"] = candidate_answer

        # session carry for continuation turns
        handles = list(evidence_set.entity_handles)
        handle_by_id = {}
        for handle in handles:
            public_id = (
                handle.canonical_id
                if getattr(handle, "kind", "canonical") == "canonical"
                else handle.handle_id
            )
            handle_by_id[public_id] = handle
        if selection is not None:
            session["displayed"] = tuple(selection.displayed_handle_ids)
            session["names"] = tuple(
                str(getattr(handle_by_id.get(handle_id), "display_name", ""))
                for handle_id in selection.displayed_handle_ids
            )

        payload_displayed: list[str] = []
        if prose.payloads:
            payload = prose.payloads[-1]
            context = getattr(payload, "context_receipt", None)
            displayed_set = getattr(context, "displayed_result_set", None)
            payload_displayed = [
                str(getattr(handle, "display_name", ""))
                for handle in getattr(displayed_set, "handles", ())
            ]
        prose.payloads.clear()

        rewriter = rewriter_holder.pop("current", None)
        rows = list(recorder.rows)
        lane_rows = [row for row in rows if row["name"].startswith("read.lane.")]

        turn_report = {
            "id": spec["id"],
            "session": spec["session"],
            "query": spec["query"],
            "as_of": as_of.isoformat(),
            "continuation": bool(spec.get("continuation")),
            "recorded": {
                "trace_day": TRACE_JOURNAL.name,
                "turn_ordinal": spec["turn_ordinal"],
                "total_s": recorded_turn.get("total_s"),
                "lanes": recorded_turn.get("lanes"),
                "degradation": recorded_turn.get("degradation"),
                "replay_views": list(recorded_turn.get("views", ())),
            },
            "rewriter": {
                "mode": args.rewriter,
                "source": None if rewriter is None else rewriter.last_source,
                "live_views": [] if rewriter is None else list(rewriter.last_live_views),
                "used_views": [] if rewriter is None else list(rewriter.last_views),
                "wall_s": _sum(rows, "plan.rewrite.live"),
            },
            "plan": {
                "wall_s": round(plan_wall, 3),
                "proposal_s": _sum(rows, "plan.proposal"),
                "lanes": list(plan.lanes),
                "domains": list(plan.domains),
                "max_candidates": plan.max_candidates,
                "web_max_results": plan.web_policy.max_results,
                "views": [str(getattr(view, "text", "")) for view in plan.query_views],
                "view_kinds": [str(getattr(view, "producer_kind", "")) for view in plan.query_views],
                "supplemental_budget_ms": (
                    None
                    if plan.supplemental_budget is None
                    else plan.supplemental_budget.max_wall_time_ms
                ),
            },
            "read": {
                "wall_s": round(read_wall, 3),
                "outer_s": _sum(rows, "read.outer"),
                "delegate_s": _sum(rows, "read.delegate"),
                "outer_overhead_s": round(_sum(rows, "read.outer") - _sum(rows, "read.delegate"), 3),
                "lanes": {
                    row["name"].removeprefix("read.lane."): row["wall_s"] for row in lane_rows
                },
                "rerank_s": _sum(rows, "read.rerank"),
                "sufficiency_s": _sum(rows, "read.sufficiency"),
                "supplemental_s": _sum(rows, "read.supplemental"),
                "evidence_items": len(evidence_set.items),
                "candidates": len(evidence_set.fused_candidates),
                "handles": len(handles),
                "limitations": sorted(
                    {str(getattr(item, "code", item)) for item in evidence_set.limitations}
                ),
            },
            "web": {
                "views_calls": _rows(rows, "web.views"),
                "merged_calls": _rows(rows, "web.merged"),
                "provider_calls": _rows(rows, "web.provider.search"),
                "fetch_calls": _rows(rows, "web.fetch.page"),
                "judge_calls": _rows(rows, "web.judge.batch"),
                "enrich_calls": _rows(rows, "web.enrich"),
                "totals": {
                    name: _sum(rows, name)
                    for name in (
                        "web.views",
                        "web.merged",
                        "web.provider.search",
                        "web.fetch.page",
                        "web.judge.batch",
                        "web.enrich",
                        "web.fetch.warm",
                    )
                },
                "cache_hits": sum(
                    1
                    for row in _rows(rows, "web.provider.search")
                    if (row.get("meta", {}).get("cache_hit") or 0) == 1
                ),
                "provider_calls_total": len(_rows(rows, "web.provider.search")),
            },
            "embedding": {
                name: {"calls": len(_rows(rows, name)), "wall_s": _sum(rows, name)}
                for name in ("embed.batch", "embed.http")
            },
            "answer": {
                "selector_s": selector_wall,
                "total_s": _sum(rows, "answer.total"),
                "displayed_handles": 0 if selection is None else len(selection.displayed_handle_ids),
                "payload_displayed": payload_displayed[:40],
                "claims": 0 if selection is None else len(selection.claims),
            },
            "stages": _stage_table(rows),
            "sampler": SAMPLER.snapshot(spec["id"], limit=15),
            "counters": dict(recorder.counters),
        }
        turn_reports.append(turn_report)
        if args.dump_handles:
            _dump_handles(
                out_dir=out_dir,
                spec=spec,
                evidence_set=evidence_set,
                selection=selection,
                answer_result=answer_result,
            )
        _mark(
            f"turn {spec['id']} done: plan={plan_wall:.1f}s read={read_wall:.1f}s "
            f"lanes={turn_report['read']['lanes']} web.search={turn_report['web']['totals']['web.provider.search']:.1f}s "
            f"(cache {turn_report['web']['cache_hits']}/{turn_report['web']['provider_calls_total']}) "
            f"fetch={turn_report['web']['totals']['web.fetch.page']:.1f}s"
        )
        print("    top stages:", json.dumps(turn_report["stages"][:8], ensure_ascii=False))

    SAMPLER.stop()

    report = {
        "harness": {
            "generated_at": datetime.now(UTC).isoformat(),
            "harness_path": str(HARNESS_PATH),
            "worktree": str(WORKTREE),
            "pack_dir": str(PACK_DIR),
            "release_id": RELEASE_ID,
            "chat_llm_profile": profile,
            "rewriter_mode": args.rewriter,
            "bootstrap": {
                "import_s": round(import_s, 2),
                "load_recorded_inputs_s": round(load_inputs_s, 2),
                "pack_open_s": round(pack_open_s, 2),
                "planner_compose_s": round(planner_compose_s, 2),
                "read_compose_s": round(read_compose_s, 2),
            },
            "web_lane_cache": cache_info,
            "milvus_copy": {
                "copies": {
                    key: str(value) for key, value in milvus_patch["_state"].items()
                },
                "open_stats_s": milvus_patch["_stats_ref"],
            },
            "components": {
                "page_fetcher": "providers.page_fetch.create_tiered_page_fetcher (real httpx+BS4 tier0, real headless Chromium tier1)",
                "planner/read/reranker/selector": "serving_pack_loader production composite over the sealed run14 pack",
                "gap_judge/supplemental_judge": "llm_judgments.create_llm_judge (real LLM, 1.8s timeout, profile="
                + profile
                + ")",
                "embedding": "qwen-embedding-bundle-v1 via load_content_addressed_embedding_adapter "
                + str(EMBEDDING_BUNDLE),
                "web_providers": "bocha-v1 + serper-v1 behind the shared SQLite view cache (private copy)",
                "prose_renderer": "capture stub (generation excluded)",
            },
            "deviations": [
                "prose LLM stubbed: generation (live 1.1-6.8s) excluded from answer.total",
                "contextual interpreter (chat.py, 3s timeout, before planning) not replayed",
                "replay view order = turn-trace completion order, truncated to the first 3 non-base views",
                "milvus + web-lane cache are private byte copies; pack/index/marker identity checks still run against the real paths",
                "session carry for PCB turn 2 comes from this harness's own turn-1 selector output",
                "replayed turns reuse the live web-view cache when the view text matches (day pinned to the recorded as_of)",
            ],
        },
        "turns": turn_reports,
    }

    json_path = out_dir / args.json_name
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    _mark(f"wrote {json_path}")

    md_path = out_dir / args.md_name
    md_path.write_text(_render_brief(report), encoding="utf-8")
    _mark(f"wrote {md_path}")
    return 0


def _render_brief(report: dict) -> str:
    lines: list[str] = []
    lines.append("# 检索段时延分解（offline harness）")
    lines.append("")
    harness = report["harness"]
    lines.append(f"- 生成时间: {harness['generated_at']}")
    lines.append(f"- 运行来源: `{harness['harness_path']}`")
    lines.append(f"- 组件: worktree `{harness['worktree']}` + sealed pack `{harness['pack_dir']}`")
    lines.append(f"- 引导耗时: {json.dumps(harness['bootstrap'], ensure_ascii=False)}")
    lines.append("")
    lines.append("## 偏差声明 (deviations)")
    for item in harness["deviations"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## 逐轮分解")
    for turn in report["turns"]:
        lines.append("")
        lines.append(f"### {turn['id']} — {turn['query']}")
        lines.append("")
        lines.append(
            f"- 线上同轮: total {turn['recorded']['total_s']}s / lanes {json.dumps(turn['recorded']['lanes'], ensure_ascii=False)}"
        )
        lines.append(
            f"- 本机: plan {turn['plan']['wall_s']}s / read {turn['read']['wall_s']}s "
            f"(outer {turn['read']['outer_s']}s, delegate {turn['read']['delegate_s']}s, 外层校验 {turn['read']['outer_overhead_s']}s)"
        )
        lines.append(
            f"- lanes: {json.dumps(turn['read']['lanes'], ensure_ascii=False)}"
        )
        lines.append(
            f"- web: search {turn['web']['totals']['web.provider.search']}s "
            f"(cache {turn['web']['cache_hits']}/{turn['web']['provider_calls_total']}), "
            f"fetch {turn['web']['totals']['web.fetch.page']}s, "
            f"judge {turn['web']['totals']['web.judge.batch']}s, "
            f"views {turn['web']['totals']['web.views']}s"
        )
        lines.append(
            f"- rewriter: {turn['rewriter']['source']} ({turn['rewriter']['wall_s']}s) → {json.dumps(turn['rewriter']['used_views'], ensure_ascii=False)}"
        )
        lines.append("")
        lines.append("| stage | calls | wall_s | cpu_s |")
        lines.append("|---|---:|---:|---:|")
        for row in turn["stages"][:16]:
            lines.append(
                f"| {row['stage']} | {row['calls']} | {row['wall_s']} | {row['cpu_s']} |"
            )
        if turn["sampler"]["by_thread"]:
            lines.append("")
            lines.append(
                "thread samples: " + json.dumps(turn["sampler"]["by_thread"], ensure_ascii=False)
            )
            for row in turn["sampler"]["top_stacks"][:6]:
                lines.append(f"- {row['samples']}× {row['stack']}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
