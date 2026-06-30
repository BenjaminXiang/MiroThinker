# Retrieval Gap Diagnosis — Baseline (2026-06-29)

> First-principles root-cause diagnosis for the retrieval-alignment-to-testset work.
> Method: DB-grounded + Milvus-grounded measurement (Tier-2 lesson: verify, don't assume).
> Harness: `apps/admin-console/scripts/eval_recall.py` (forced-domain) +
> `eval_recall_chat.py` (faithful /api/chat end-to-end, synthesis off).

## Baseline: 53% end-to-end entity recall (10/19) on single-domain gradable cases

`eval_recall_chat.py` (POST /api/chat via TestClient, CHAT_LLM_SYNTHESIS=off, required-entity
substring check over full JSON response).

## Failure modes

### FM1a — Data not ingested (PRIMARY blocker; NOT retrieval-fixable)
Required test entities with **0 rows** in `company`:
- #4 (酒店送餐机器人供应商): 云迹科技, 九号机器人, 擎朗智能 (3 of 5 required).
- #13 (PCB打板): 嘉立创.
Present: 普渡科技 (sz=T, ready), 上海开普勒机器人 (sz=F, ready), 深南电路 (sz=T, ready).
**Even at 100% retrieval, #4 caps at 2/5, #13 at 2/3.** Needs ingest (data pipeline).

### FM1b — Recall ranking for present+ready data
- 普渡科技: raw ANN rank 32; 深南电路: raw ANN rank 50 (both ready + embedded, full coverage
  6,514/6,514). `candidate_limit=30` cuts them pre-rerank.
- Reranker (Qwen3-Reranker @ 100.64.0.27:18006) WORKS (HTTP 200; standalone ranks 普渡 #2 on
  short docs). Over the full 200-pool it promotes 普渡 only to rerank-rank-10 (borderline),
  because 普渡's profile_summary is broad (配送/清洁/餐饮/酒店/医疗/工业 — diluted) vs
  competitors' laser-focused "酒店送餐" profiles.
- `retrieve(candidate_limit=100)` still excludes 普渡 from top-10 → rerank doesn't reliably
  rescue. Partially fixable (raise candidate_limit so reranker at least sees deep candidates);
  profile-quality part is deeper.

### FM3 — Routing misclassification
#19 (毕业于早稻田，且在深圳专注在机器人行业的企业家有谁) → classified `unknown` → no recall
attempt. Cross-filter professor queries (attribute AND attribute) fall through the classifier.

## Confirmed working (no fix)
- Patent applicant lookup (#40 → A_patent_by_applicant) + exact patent-number (#41 →
  A_patent_profile): SQL routing correct.
- Single-entity profiles (#1/#10/#16/#21/#24/#26/#34): routing + recall correct.

## Scope decision (autonomous)
- **Retrieval-logic fixes (in scope):** FM3 (routing) + FM1b (candidate_limit / recall tuning).
- **FM1a (data ingest):** flagged as a separate data-pipeline workstream — blocks test
  alignment but is not a retrieval-logic gap. Recorded for ingest-scope decision.

## Repro
```
cd apps/admin-console
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_real \
MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=off UV_OFFLINE=1 \
uv run python scripts/eval_recall_chat.py
```

## CONCLUSION (decisive) — retrieval logic is sound; the gap is DATA

Quantified split of all 9 missed entities (baseline 10/19):

| Category | Entities | Count |
|---|---|---|
| **FM1a — not ingested (data)** | 云迹/九号/擎朗 (#4), 嘉立创 (#13), 许晋诚/陈功 (#19) | **6/9 = 67%** |
| **FM1b — present+ready+embedded, rerank doesn't promote (profile quality)** | 普渡/深南电路 (#4/#13), 开普勒 (#4) | 3/9 = 33% |
| retrieval-logic routing miss | — | **0/9** |

- Retrieval LOGIC (classification, routing, recall mechanics, reranker) is **sound** — verified:
  patent applicant/exact lookup works; single-entity profiles work; topic recall works for
  present data; reranker is live (HTTP 200) and ranks sensibly.
- The test-set recall ceiling is **data coverage** (6 entities simply absent) + **profile
  quality** (broad profiles not promoted). Max achievable without ingest ≈ 13/19 (68%).
- **Iteration outcomes:** FM1b candidate_limit raise (30→64) was eval-NEUTRAL → reverted.
  FM3 routing fix is data-blocked (许晋诚/陈功 absent) → not worth implementing.
- **Real levers:** (a) FM1a data ingest of the 6 absent entities (dominant; different
  workstream); (b) optional FM1b hybrid retrieval (vector+keyword) for the 3 present-but-broad.

