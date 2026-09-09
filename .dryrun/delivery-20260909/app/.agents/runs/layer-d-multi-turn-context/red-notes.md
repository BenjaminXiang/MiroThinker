# RED baseline notes — layer-d-multi-turn-context (2026-07-09)

- Artifact: `red-baseline-2026-07-09.json` (16 groups / 34 turns / 18 scored follow-ups).
- Backend: booted for this run — `uv run --no-sync uvicorn backend.main:app --port 18188`,
  env from `apps/miroflow-agent/.env` + `DATABASE_URL=…15432/miroflow_real`,
  `MILVUS_USE_REAL_CLIENT=1 CHAT_LLM_SYNTHESIS=on CHAT_QUERY_CLASSIFIER=on
  CHAT_USE_RETRIEVAL_SERVICE=on ADMIN_PROFESSOR_SEED_CRON_ENABLED=0`, proxies unset.
  Log `/tmp/layerd-backend.log`. Left running after the run.

## Headline

| Metric | RED |
|---|---|
| Accept-line 14 (8 yaml + S1–S5) | **0/14** |
| Chip matrix (S6 ×4) | **1/4** (only S6D 上述哪些已授权) |
| set_derived assertions | 1/8 |
| query_type assertions | 3/10 |
| forbidden violations | 0 |

## Failure modes → layer mapping

**M1 — 集合跨域遍历被同域收窄劫持 (S1-F, S5-F1, S5-F2, S6C-F).** 上述/这些 prefix
matches `looks_like_narrowing_query` → `_handle_d_narrowing` locks the source domain and
runs `retrieve("教授参与的企业") ∩ set` → garbage or empty; synthesis then free-associates
over whatever evidence exists (S5-F2 answered with 四维图新 — never displayed). → tasks
group 3 (routing: narrow vs traverse) + group 4 (traversal).

**M2 — 谓词收窄机制错配 (qid4, qid10, S6B-F).** 在深圳/总部在深圳 sent to semantic
retrieval as a "topic": S6B returns 0 members (`未筛选到与'哪些在深圳'相关的条目`); qid4/10
end up listing 万科/华侨城/腾讯/招商银行 — entities NEVER in the prior set (set discipline
broken end-to-end once narrowing yields nothing usable). → group 5 chip predicates; also
evidence for group 2 (displayed-set capture + no-silent-fallback).

**M3 — 裸集合代词无解析 (S2-F).** 他们发表了哪些论文 → classifier C/paper → single-entity
path → no anchor → generic clarification (doesn't list members). → groups 2+3.

**M4 — chip 文案完全脱靶 (S6A-F).** 看看这些教授的论文 → `unknown` ("我还没判断清楚要查
哪类科创信息") — the UI-promise gap, verbatim. → group 3 rule layer.

**M5 — 域不匹配未澄清 (S4-F).** Company-only context + 上述教授参与的企业 → D_narrowing
runs anyway instead of clarifying. → group 2 (empty-set/domain-mismatch guard).

**M6 — 列表后单数代词 (S3-F).** Routes to C-clarification (acceptable class, qtype check
passed) but does NOT list the set members, so a user can't resolve it in one turn.
Half-correct today; needs the member-listing clarification. → group 6.

**M7 — 开放谓词无通路 (qid5).** 机械臂自主按电梯 filter → `unknown` refusal. → group 5
open-predicate LLM lane.

**M8 — out-of-D-scope failures (candidates for the 2-case tolerance):**
- qid2: routing CORRECT (C_cross_domain_related via profile anchor); answer honest
  (暂未收录丁文伯关联的企业数据) — `professor_company_role` lacks the 无界智航 link.
  **Data gap (Layer E-ish), not Layer D.**
- qid25: routing CORRECT (A_patent_profile); CN117873146A not in evidence — data/coverage.
- qid15: knowledge expansion tied to prior company context — R3-flavored (constraint
  frame), explicitly deferred by ADR-011.
- qid8: alias flip 智航无界/无界智航 not matched — G-route name-matching, sibling of FM5
  (company-name fuzzy), not Layer D.
- qid12: 这论文 (without 篇) missing from `_PRONOUN_DOMAIN_MAP`, falls into C-route
  clarification. One-line fix candidate in group 2/6 (add the variant), then the case
  needs paper-attribute answering (link) — partially data-dependent.

Note: 14-case accept line needs ≥12; M8 contains ~4 cases whose fixes are outside D's
scope (qid2, qid25, qid15, qid8). Realistic D-scope ceiling on the 14 ≈ 10-12 — tight
against the line. If groups 2-6 land and these 4 remain red, options: fix the cheap ones
(qid12 pronoun variant; qid8 alias normalization is FM5 work), or renegotiate the line
with the user. Recorded now so acceptance isn't a surprise.

## Corrections applied during the run (reviewer, measurement-side only)

- `_collect_source_like_ids`: entity-ID-prefix filter (PROF/COMP/PAPER/PAT) + skip `*url*`
  keys — was false-failing on `source_url`/`source_label`.
- S3-F/S4-F `expected_query_type` widened to accept `C_cross_domain_clarification`.
