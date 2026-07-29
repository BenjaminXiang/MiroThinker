# Canonical V2 Recall-First Web Synthesis Implementation Plan

> **Execution:** Use `superpowers:executing-plans` task by task. Keep RED/GREEN evidence in the
> current session and do not add subagents or a new worktree; this branch is already isolated.

**Goal:** Ensure relevant bounded Web evidence reaches the existing final LLM for every normal
information request, especially displayed-set capability follow-ups, without adding a serial LLM
stage or weakening evidence/public-source constraints.

**Architecture:** Replace keyword-conditioned Web retention with a serving-private lane-balanced
ordering. Build a bounded mixed local/Web claim set for one final Qwen synthesis call. Validate a
current-Web public link only against explicit authority or the same canonical entity's retained
official hostname.

**Tech stack:** Python 3.12, Pydantic, FastAPI, pytest, Ruff, Pyright, OpenSpec, real Bocha/Serper and
OpenAI-compatible Qwen runtime for final E2E only.

## Task Contract

```text
Goal:
  Relevant Web evidence survives to final LLM synthesis across query wording and domains.

Expected invariant:
  Recall is lane-balanced; material claims remain evidence-bound; public citations remain official.

Context:
  S12D read-only Candidate, dual Web already active, one final prose LLM already active.

Constraints:
  No new LLM stage, no case-specific code, no canonical/index/source write, no public API change.

Done when:
  Focused tests and real three-turn replay pass, latency remains one-Web-plus-one-LLM critical path,
  OpenSpec evidence is updated, commits are clean, and `0.0.0.0:18188` is ready for user testing.

Out of scope:
  Full structured planner/reranker/sufficiency implementation, source recollection, cutover,
  authentication for `/browse`, streaming, and UI redesign.
```

## File Map

- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`:
  lane-balanced reranking, mixed claim selection, and prose-v3 input/prompt.
- Modify `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`:
  RED/GREEN regression and sibling matrix.
- Modify `apps/admin-console/backend/services/canonical_v2_chat.py`:
  same-entity official-host validation for current-Web citations.
- Modify `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`:
  public official-host and arbitrary-host regressions.
- Update existing OpenSpec, slice, change-log, and verification artifacts only.

### Task 1: Capture RED for lane starvation

**Files:**

- Modify `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`

- [ ] Add a reranker test with at least eight strong local candidates and several current-Web
  candidates. Use a capability follow-up that contains none of the retired Web-gap keywords.
- [ ] Assert the first `bundle.max_candidates` result IDs contain both source natures.
- [ ] Add a mixed-candidate case and assert it remains ahead of single-lane candidates.
- [ ] Run:

```bash
cd apps/miroflow-agent
uv run pytest -q -n0 tests/canonical_v2/test_knowledge_serving_isolated.py \
  -k 'recall_first or lane_balanced'
```

Expected RED: Web candidates are ordered behind all strong local candidates and disappear at the
configured candidate limit.

### Task 2: Capture RED for final-LLM evidence starvation

**Files:**

- Modify `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`

- [ ] Build an `EvidenceSet` with eight local Company facts followed by direct Web evidence naming a
  Product and its robotic-hand elevator-button capability.
- [ ] Use the exact shape of a displayed-set follow-up, but no production exact-query branch.
- [ ] Inject a prose renderer that records selected claims and assert it receives both lanes and the
  direct Product-capability snippet.
- [ ] Parameterize sibling wording for capability, current fact, role, geography, and link queries.
- [ ] Extend the renderer contract test to assert all bounded claims, source authority, locator, and
  prompt version `canonical-v2-prose-v3` reach the single completion request.
- [ ] Run the same focused command. Expected RED: Web evidence is absent or truncated.

### Task 3: Implement lane-balanced candidate retention

**Files:**

- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`

- [ ] Remove `_WEB_GAP_MARKERS` and `_requires_web_evidence` from admission/ranking decisions.
- [ ] Classify candidates by mixed, strong-local, Web, and other evidence.
- [ ] Sort within each class by descending raw score and stable result ID.
- [ ] Emit mixed candidates first, interleave local and Web candidates, then append other candidates.
- [ ] Keep the generic `KnowledgeRead` global cap and public contracts unchanged.
- [ ] Run Task 1 tests and the existing reranker/focused-entity regressions. Expected GREEN.

### Task 4: Implement bounded mixed claim selection and prose-v3

**Files:**

- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`
- Modify `apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`

- [ ] Select current-Web evidence for every normal information answer, independent of wording.
- [ ] Retain preferred local evidence for focused queries and the broader local set for enumeration.
- [ ] Round-robin source natures and deduplicate repeated local object/predicate facts.
- [ ] Bound total selected claims by `max_candidates + max_web_results`.
- [ ] Remove the renderer's unrelated first-12 truncation; trust the selector's explicit bound.
- [ ] Add `source_authority` and `source_locator` to the process-only LLM payload.
- [ ] Update the system prompt to judge relevance, integrate rather than copy, enforce direct Product
  binding, distinguish physical button operation from IoT integration, and qualify unsupported set
  members.
- [ ] Preserve founder-role postcondition and deterministic typed fallback.
- [ ] Run Task 2 tests plus the complete serving test file. Expected GREEN.

### Task 5: Validate official current-Web citations without hardcoding domains

**Files:**

- Modify `apps/admin-console/backend/services/canonical_v2_chat.py`
- Modify `apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`

- [ ] Add a RED test where one canonical Company handle contains local `website` evidence and a
  current-Web Product page on the same hostname. Assert the official page is public.
- [ ] Add sibling RED cases for a subdomain, unrelated news host, private address, credential-bearing
  URL, and a Web-only untrusted result. Assert only the first two official-host cases can appear.
- [ ] Derive trusted official hosts from admitted local evidence IDs bound to the same handle.
- [ ] Accept current-Web evidence only when already marked official or host-matched to that trusted
  set. Reuse `_public_url` for scheme/private-host validation.
- [ ] Do not change `ChatResponse`, the collapsed UI, or server-side trace retention.
- [ ] Run:

```bash
cd apps/admin-console
uv run pytest -q -n0 tests/test_canonical_v2_chat_http_adapter.py \
  -k 'official or citation or public'
```

Expected GREEN: same-entity official links display; arbitrary/internal links remain hidden.

### Task 6: Focused systemic verification

- [ ] Run complete serving and Admin HTTP tests:

```bash
cd apps/miroflow-agent
uv run pytest -q -n0 tests/canonical_v2/test_knowledge_serving_isolated.py
cd ../../apps/admin-console
uv run pytest -q -n0 tests/test_canonical_v2_chat_http_adapter.py
uv run pytest -q -n0 tests/test_canonical_v2_real_preview_ui.py
```

- [ ] Run changed-file Ruff and targeted Pyright using the repository's existing commands.
- [ ] Run `openspec validate rebuild-canonical-v2-knowledge-platform --strict`.
- [ ] Run `git diff --check` and inspect the complete diff for case-specific strings, weakened
  evidence validation, public trace leakage, and unrelated changes.
- [ ] Commit the implementation checkpoint only after these checks pass.

### Task 7: Restart and execute real three-turn E2E

- [ ] Stop only the existing Candidate process on `:18188`.
- [ ] Start the same recorded serving bundle and read-only Candidate on `0.0.0.0:18188` with the
  existing model profile `gemma4` (`qwen3.6-35b-a3b-fp8`) and provider credentials from environment
  files. Do not change database/index/release/source arguments.
- [ ] Wait for startup to finish; keep the PTY session managed.
- [ ] Replay one cookie-preserving conversation:

```text
中国有哪些成熟的酒店送餐机器人供应商
上述企业里总部在深圳的企业有哪些
酒店电梯需要送餐机器人能够使用机械臂自主按电梯，上述企业的产品有哪些可以实现
```

- [ ] Verify the third answer identifies only directly supported Products, includes PUDU FlashBot
  Arm when the provider returns its official evidence, distinguishes ordinary elevator IoT
  integration, and qualifies the remaining Companies.
- [ ] Verify `answer_style=llm_synthesized`, Web trace success, official-only citations, empty public
  raw evidence/trace fields, no `/browse`, and complete HTTP time.
- [ ] Run one unrelated sibling capability follow-up to prove the implementation is not query-bound.

### Task 8: Close the Candidate checkpoint

- [ ] Update Tasks 12.5g-12.5i and the three new acceptance checks only when their evidence exists.
- [ ] Append exact commands, counts, real response summary, timings, source-isolation status, and
  remaining risk to `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- [ ] Mark S12D `Candidate`; leave Task 12.5 user acceptance and Task 12.6 cutover open.
- [ ] Run final strict OpenSpec validation and `git diff --check`.
- [ ] Commit the evidence/artifact checkpoint and verify `git status --short --branch` is clean.
- [ ] Leave the Candidate listening on `0.0.0.0:18188` for direct user testing.

## Stop Conditions

- The fix requires weakening direct claim-evidence binding or treating model memory as evidence.
- An official public citation cannot be validated without adding a Company/query-specific registry.
- The real fix requires an additional serial provider/model call on the request path.
- Candidate restart would write source/canonical/index data or change active pointers.
- Focused tests reveal a public API/schema change or an unrelated cross-module behavior conflict.

## Rollback

Revert the implementation commit and restart the same Candidate. Documentation and regression tests
may remain as evidence of the rejected approach. No database or index rollback is needed.
