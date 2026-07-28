# Canonical V2 Dual Web and Idle Keep-Warm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Combine Bocha and Serper for every normal Canonical V2 information request and keep all external provider paths responsive after long idle periods without delaying real requests or writing business data.

**Architecture:** Replace the serving-only Serper lane with one bounded dual-provider adapter that owns independent Bocha and Serper clients, launches both calls concurrently, normalizes and deduplicates results, and emits content-addressed snapshots with exact provider provenance. Add one small admin-console lifecycle coordinator that owns idle timing and runs an injected provider-only warm callable in a daemon thread; the chat route only marks activity before invoking the existing adapter.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, `concurrent.futures`, `threading`, pytest, Ruff, Pyright, OpenSpec.

---

## File Map

- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py` for dual-provider normalization, URL deduplication, provider-bound snapshots, and a provider-only warm callable.
- Create `apps/admin-console/backend/services/canonical_v2_keepwarm.py` for lifecycle-owned idle/activity/non-overlap coordination.
- Modify `apps/admin-console/backend/main.py` and `apps/admin-console/backend/api/canonical_v2_chat.py` for app lifecycle and real-request activity marking.
- Modify `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py` to pass the warm callable to the app factory.
- Modify `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/serving-bundle-r8.json` to bind the approved dual-provider policy and recompute only its own content hash.
- Modify focused tests beside each owner; do not add production persistence, public response fields, or generic scheduling infrastructure.

### Task 1: Dual-provider Web Lane

**Files:**
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/serving-bundle-r8.json`

- [ ] **Step 1: Add injected fake-provider tests**

Construct the serving Web adapter with independent fake Bocha and Serper providers. Assert both are
called once, normalized duplicate URLs consume one position, Bocha `summary` is preferred, snapshot
JSON retains `primary_provider_version` plus both `corroborating_provider_versions`, and provider-
unique results retain their actual `RecallCandidate.provider_version`. Add one-provider and both-
provider failure cases.

- [ ] **Step 2: Run the RED tests**

```bash
cd apps/miroflow-agent
uv run pytest -q -n0 tests/canonical_v2/test_knowledge_serving_isolated.py -k 'dual_web or web_provider_provenance'
```

Expected: FAIL because the serving adapter still accepts only Serper and cannot retain corroborating
provider versions.

- [ ] **Step 3: Implement normalized dual-provider results**

Add these serving-private shapes:

```python
@dataclass(frozen=True, slots=True)
class _NormalizedWebResult:
    title: str
    url: str
    snippet: str
    summary: str
    primary_provider_version: str
    corroborating_provider_versions: tuple[str, ...]

def _normalized_web_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))
```

Replace `_SerperLaneAdapter` with `_DualWebLaneAdapter`. Give it independent injected
`BochaSearchProvider` and `WebSearchProvider` instances plus a persistent two-worker executor. Submit
one call per provider, normalize usable HTTP(S) results, merge Bocha first, union provider versions
on duplicate normalized URLs, and apply `request.max_candidates` only after deduplication. Snapshot
JSON contains title, link, snippet, summary, primary provider, and corroborating providers; its
existing SHA-256 continues to bind the exact bytes. The selected result's primary provider remains
in `RecallCandidate.provider_version`.

- [ ] **Step 4: Update bounded policy and secret-free bundle configuration**

Change the serving bundle provider declaration to the exact dual-provider policy and expose only
`BOCHA_API_KEY` and `SERPER_API_KEY` environment/key-file names. Set planning, Web, and supplemental
provider-call caps to two without changing the existing outer wall-time or result cap. Never
serialize credential values.

Update only `serving-bundle-r8.json` from `serper-v1`/`SERPER_API_KEY` to the dual-provider policy
and its two environment-key names, then recompute the bundle's `content_sha256` with the existing
canonical serializer. Use the new hash in the restart command. Do not alter the Candidate envelope,
release ID, database name, index root, or any historical serving bundle.

- [ ] **Step 5: Run focused GREEN checks**

```bash
cd apps/miroflow-agent
uv run pytest -q -n0 tests/canonical_v2/test_knowledge_serving_isolated.py
```

Expected: PASS, including existing local-only degradation and snapshot-integrity tests.

- [ ] **Step 6: Commit the provider slice**

```bash
git add apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py
git commit -m "feat(canonical-v2): combine Bocha and Serper retrieval"
```

### Task 2: Adaptive Idle Coordinator

**Files:**
- Create: `apps/admin-console/backend/services/canonical_v2_keepwarm.py`
- Create: `apps/admin-console/tests/test_canonical_v2_keepwarm.py`

- [ ] **Step 1: Write deterministic lifecycle tests**

Use an injected monotonic clock and recorded callable:

```python
coordinator = AdaptiveIdleKeepwarm(
    cycle=recorded_cycle,
    idle_seconds=300.0,
    monotonic=fake_clock,
)
coordinator.mark_activity()
assert coordinator.run_scheduled_cycle() is False
fake_clock.advance(300.0)
assert coordinator.run_scheduled_cycle() is True
assert calls == ["cycle"]
```

Add cases proving a second overlapping cycle is skipped, `start()` owns at most one daemon worker,
and `stop()` signals and joins without waiting for the full interval.

- [ ] **Step 2: Run the RED test**

```bash
cd apps/admin-console
uv run pytest -q -n0 tests/test_canonical_v2_keepwarm.py
```

Expected: FAIL because `AdaptiveIdleKeepwarm` does not exist.

- [ ] **Step 3: Implement the focused coordinator**

Create only this public surface:

```python
class AdaptiveIdleKeepwarm:
    def mark_activity(self) -> None: ...
    def run_scheduled_cycle(self) -> bool: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

Protect `last_activity`, `cycle_running`, and worker identity with one lock. The daemon worker waits
on a stop event for `idle_seconds`, then invokes `run_scheduled_cycle`. Recheck idle time and set the
non-overlap flag under the lock; clear the flag in `finally`. Catch and log cycle exceptions so the
lifecycle thread survives. Do not queue missed work or add persistence, retries, distributed
coordination, metrics storage, or a scheduler dependency.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd apps/admin-console
uv run pytest -q -n0 tests/test_canonical_v2_keepwarm.py
git add backend/services/canonical_v2_keepwarm.py tests/test_canonical_v2_keepwarm.py
git commit -m "feat(canonical-v2): add adaptive idle keepwarm"
```

Expected: PASS.

### Task 3: Provider-only Cycle and App Lifecycle

**Files:**
- Modify: `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`
- Modify: `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`
- Modify: `apps/admin-console/backend/main.py`
- Modify: `apps/admin-console/backend/api/canonical_v2_chat.py`
- Modify: `apps/admin-console/tests/test_canonical_v2_review_http.py`
- Modify: `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py`

- [ ] **Step 1: Add RED tests for provider-only work and app wiring**

Assert `RecordedServingInputs.idle_keepwarm_cycle` launches Bocha, Serper, embedding, and LLM warm
calls concurrently and does not invoke chat, answer selection, session, evidence snapshot, gap,
database, or index code. Assert the Candidate app starts/stops an injected coordinator and
`/api/chat` calls `mark_activity()` before `adapter.answer()`. Update the runner test to assert it
passes `recorded.idle_keepwarm_cycle` to the app factory.

- [ ] **Step 2: Run RED tests**

```bash
cd apps/miroflow-agent
uv run pytest -q -n0 tests/canonical_v2/test_knowledge_serving_isolated.py -k keepwarm
cd ../../apps/admin-console
uv run pytest -q -n0 tests/test_canonical_v2_chat_http_adapter.py tests/test_canonical_v2_review_http.py -k 'keepwarm or activity or candidate_app'
uv run pytest -q -n0 ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py -k serve
```

Expected: FAIL because no cycle or lifecycle dependency exists.

- [ ] **Step 3: Implement the provider-only cycle**

Add `idle_keepwarm_cycle: Callable[[], None]` to `RecordedServingInputs`. Build it from the configured
dual Web adapter, embedding adapter, and an environment LLM warm callable. One invocation uses a
four-worker executor for one Bocha query, one Serper query, one minimal timestamp-bucket embedding
input (to bypass the normal embedding cache), and one-token non-thinking LLM completion. Bound each
operation with existing provider timeouts, log failures without raising, and return no value. Do not
construct a `LaneRequest`, `TurnRequest`, answer, snapshot, session, citation, or gap.

- [ ] **Step 4: Wire activity and app lifecycle**

Extend `create_canonical_v2_candidate_app` with optional `idle_keepwarm_cycle`. When supplied,
construct `AdaptiveIdleKeepwarm(idle_seconds=300.0)`, store it only on `app.state`, and register
`start`/`stop` as startup/shutdown handlers. In `/api/chat`, call `mark_activity()` after query
validation and before `adapter.answer()`. The runner passes the recorded callable. Do not change any
response model, cookie, citation, or feedback checkpoint.

- [ ] **Step 5: Run GREEN and commit**

Run the three commands from Step 2; expect PASS. Then:

```bash
git add apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py apps/admin-console/backend/services/canonical_v2_keepwarm.py apps/admin-console/backend/main.py apps/admin-console/backend/api/canonical_v2_chat.py apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py apps/admin-console/tests/test_canonical_v2_review_http.py .agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete_candidate_runner.py .agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py
git commit -m "feat(canonical-v2): wire full-path idle keepwarm"
```

### Task 4: Regression, Timing, and Evidence

**Files:**
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/acceptance.md`
- Modify: `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- Modify: `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s12d-universal-web-llm-public-evidence.md`

- [ ] **Step 1: Run changed-surface regression tests**

```bash
cd apps/miroflow-agent
uv run pytest -q -n0 tests/canonical_v2/test_knowledge_serving_isolated.py
cd ../../apps/admin-console
uv run pytest -q -n0 tests/test_canonical_v2_keepwarm.py tests/test_canonical_v2_chat_http_adapter.py tests/test_canonical_v2_real_preview_ui.py tests/test_canonical_v2_review_http.py
uv run pytest -q -n0 ../../.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/test_complete_candidate_runner.py -k serve
```

Expected: PASS with no public-envelope or official-citation regression.

- [ ] **Step 2: Run static and contract checks**

Run focused Ruff and Pyright on changed Python files, then:

```bash
openspec validate rebuild-canonical-v2-knowledge-platform --strict
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 3: Restart the isolated Candidate**

Stop only the existing Candidate process owned by this worktree, then start the unchanged recorded
r8 Candidate runner on `0.0.0.0:18188` with existing environment/key files. Do not rebuild, promote,
write active pointers, or touch original PostgreSQL/Milvus.

- [ ] **Step 4: Record real timing and behavior evidence**

Run direct Bocha/Serper/embedding/LLM timing probes, repeated warm four-domain requests, and one
post-idle request after at least one 300-second interval. Record HTTP status, total time, provider
availability/tails, answer text, official citations, and absence of `/browse`, internal trace,
release ID, or synthetic warm input. Replay the Ding Wenbo founder follow-up and confirm it still
states that Ding Wenbo participated in founding Shenzhen Wujie Zhihang.

- [ ] **Step 5: Update evidence and mark only demonstrated items complete**

Check Tasks 12.5d-12.5f and new acceptance items only after exact evidence passes. Return S12D to
`Candidate`; leave Task 12.5 unchecked for direct user acceptance and Task 12.6 unchecked for
separate Cutover authorization.

- [ ] **Step 6: Commit the verified checkpoint**

```bash
git add openspec/changes/rebuild-canonical-v2-knowledge-platform .agents/runs/rebuild-canonical-v2-knowledge-platform docs/superpowers/plans/2026-07-28-canonical-v2-dual-web-idle-keepwarm.md
git commit -m "chore(canonical-v2): verify dual web idle keepwarm"
```
