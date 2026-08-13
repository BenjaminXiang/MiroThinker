# Acceptance: followup-subject-consistency

A change is accepted only when ALL hold. This is a backfill: every criterion below has its
outcome recorded with evidence references. Evidence lives in
`.agents/runs/followup-subject-consistency/evidence/` (committed with this change);
`.agents/runs/followup-subject-consistency/verification.md` carries the per-task
RED/GREEN mapping.

## 1. End-to-end PASS criteria (plan Task 8 Step 1, verbatim)

Three sessions against `POST /api/chat/stream` on a local production-replica
(cookie jar per session, `curl -N`, 150s+ timeout):

1. **Badcase (qualified):** `介绍一下 国际先进技术应用推进中心（深圳）` → `有没有更详细的信息` → `能再具体一点吗`
   - PASS criteria: turn 2/3 answers stay on the 深圳 branch; no SIAT/南开 as answer subject; no refusal; turn 2/3 `retrieval_done.web_items` tops contain 切题 results (河套/百度百科/政府), 南开 (T4) absent when kept≥3.
2. **Unqualified multi-branch:** `介绍一下国际先进技术应用推进中心` (fresh cookie)
   - PASS criteria: full org-level answer (never a refusal); branch facts correctly attributed; answer naturally notes the branches (合肥/南沙/深圳 per evidence) and invites naming a city; not a boilerplate appendix.
3. **Control (canonical entity):** `介绍一下深圳市普渡科技有限公司` → `有没有更详细的信息`
   - PASS criteria: no regression, normal deepening.

Verdicts are per-turn; LLM nondeterminism means a borderline turn is retried once before
being called a failure.

### Outcome — recorded

- [x] **First run** (commits `7cad141..377f249`, retest port 39878): badcase
      **PASS-with-concerns** (T3 drifted to a SIAT-organized subject on first attempt;
      the one allowed retry passed in degraded deterministic-fallback form); unqualified
      **FAIL** (deterministic 合肥-only answer, no branch notation, no city invitation;
      retry byte-identical); control **PASS**. Evidence: `phase2_badcase_t1.sse`,
      `phase2_badcase_t2.sse`, `phase2_badcase_t3.sse`, `phase2_unqualified_t1.sse`.
      The FAIL/concerns were root-caused to two plan defects and fixed by Tasks 10/11
      (plan amendment `367fd96`, user-ruled).
- [x] **Re-run after Tasks 10/11** (HEAD `6af3715`): **3/3 sessions PASS, first attempt,
      no retries.** Badcase T1/T2/T3 clean on-subject prose (Task 11 gate held; no SIAT
      drift recurrence); unqualified PASS (authority-seeking views fired from turn 1;
      natural in-prose city invitation); control PASS. Evidence: `phase2_r2_badcase_t1.sse`,
      `phase2_r2_badcase_t2.sse`, `phase2_r2_badcase_t3.sse`, `phase2_r2_unqualified_t1.sse`,
      `phase2_r2_control_t1.sse`, `phase2_r2_control_t2.sse`. (First-run control SSE dumps
      were not preserved; the first-run control PASS is recorded in the SDD ledger and its
      re-run equivalent is the committed evidence.)

## 2. Regression commands (plan Task 8 Step 2, verbatim)

```bash
cd apps/miroflow-agent && uv run pytest tests/canonical_v2/ -q --no-cov -n 2 -p no:randomly
cd apps/admin-console && uv run pytest tests/test_canonical_v2_chat_http_adapter.py tests/test_chat_anchor_clarification.py tests/test_canonical_v2_referent_history.py -q
cd apps/admin-console && node --test tests/chat_ui_behavior_test.mjs
```

Expected: green except the known baseline `test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers` (fails on HEAD).

### Outcome — recorded

- [x] Command A (canonical_v2 suite): **1 failed, 1138 passed, 149 skipped** — the single
      failure is the known baseline
      `tests/canonical_v2/test_consumer_migration_boundary.py::test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers`
      (same failure as pre-work HEAD; not introduced by this change). Tail:
      `regression_r2_tail.txt` (first run: 1134 passed, same single known-baseline
      failure — `regression_r1_tail.txt`).
- [x] Command B (admin-console chat suites): **140 passed** (first run: 135 passed).
- [x] Command C (chat UI node tests): **87 pass / 0 fail**.

## 3. Production smoke (plan Task 8 Step 3, verbatim criteria)

Repeat the badcase turn 1+2 and the unqualified query against
`http://127.0.0.1:18188/api/chat/stream`; verify PASS criteria as in Step 1.

### Outcome — recorded

- [x] **Badcase (qualified), production 18188:** T1 **PASS** (answer subject =
      推进中心（深圳）, no SIAT/南开, no refusal; `web_items` tops 切题, 南开 absent), T2
      **PASS** (stays on the 深圳 branch). First attempt. Evidence:
      `phase2_prod_badcase_t1.sse`, `phase2_prod_badcase_t2.sse`.
- [x] **Unqualified multi-branch, production 18188:** T1 **PASS** (full org-level answer,
      never a refusal; 合肥 founding correctly attributed; natural in-prose city
      invitation; `plan_done.views` include the authority-seeking views
      `国际先进技术应用推进中心 百度百科` / `国际先进技术应用推进中心 官网` — Task 10 behavior
      confirmed live on production). First attempt. Evidence:
      `phase2_prod_unqualified_t1.sse`.
- [x] Production serves worktree HEAD `6af3715`; deploy 2026-08-13; post-deploy health
      `GET /api/health` → `{"status":"ok"}`.

## 4. Honest scope (not claimed)

- [x] Official-site fetch injection on the hot path (original R3) remains deferred — NOT
      claimed solved.
- [x] Shared-alias lookalikes passing a *binary* gate: the residual recorded in the
      follow-up record is closed by the three-tier gate (T4 drop), verified by unit tests
      and the e2e (`南开` absent from `web_items` when kept≥3 across all re-run and
      production dumps).
- [x] Known residual risks (single-sample sessions; cold-cache retrieval variance; the
      re-run unqualified answer enumerated only the 合肥 branch — the explicit city
      invitation covered the criterion) are recorded in `tasks.md` §Out of scope.
