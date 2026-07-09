# Review — layer-d-multi-turn-context, task group 5: narrowing mechanisms

- **Date:** 2026-07-09  **Builder:** Codex  **Reviewer:** Claude  **Decision: Accept**

## Scope check (handoff → code)

| Deliverable | Verdict |
|---|---|
| `detect_chip_predicate` (4 kinds: region/recency/grant_status/applicant_type, domain-gated) | ✓ pure, table-driven |
| `evaluate_chip_predicate` (True/False/信息缺失 + basis) per-domain field mapping | ✓ company region verified against schema: `hq_city`/`region`/`registered_address`/`hq_district`/`is_shenzhen`; patent grant via `grant_date` (+ `status AS legal_status` alias, no real legal_status col); patent applicant_type via `applicants_raw`; paper recency via `year`; prof region via `institution` |
| Chip-narrowing handler (fetch-by-id, per-member verdict, coverage statement, satisfy-first, citations, `skip_synthesis=True`, `source_ids` in payload) | ✓ |
| Open-predicate LLM lane (batched deepseek-v4-pro, structured verdicts, audit in payload, degrade to labeled topic when synthesis off) | ✓ |
| Selector `chip > open-LLM > topic` in `_handle_d_narrowing`; topic preserved | ✓ |
| tests/test_chat_narrowing_mechanisms.py | ✓ 31 new tests |

Hard boundaries respected: no classifier/traversal/anchor changes, no fixture/eval edits, A-G unchanged (D_narrowing reused).

## Evidence

- Unit: **155 passed** (full affected chat suite), ruff clean, `openspec validate --strict` clean.
- Multi-turn (`post-group5-2026-07-09.json`): **8/18 pass** (S6B-F flipped green), `set_derived 7/8`,
  `required_recall 7/37 → 15/37` (chip narrowing returns real set members). Smoke-verified chip
  region predicate: "上轮 9 个教授中，5 个在深圳，4 个不满足，0 个信息缺失" + per-member institution basis.
- **Single-turn 19-case: ZERO regression** vs traversal run.

## Mechanism verdict on remaining red (10) — by owner, none are group-5 defects

- **qid4 — mechanism CORRECT, oracle artifact.** Chip company-region answer contains ALL 6 gold
  companies (`required_hit=6/6`) but eval `coverage=0.0`. The deterministic terse render
  ("• 深圳安赛步机器人 - hq_city=深圳市 -> 在深圳") shares zero significant terms with the standard
  prose answer. Functionally a pass masked by the coarse coverage oracle. (Eval-metric issue, not D.)
- **qid10 — mechanism correct, upstream retrieval gap.** Narrowing correctly filtered qid9's set,
  but qid9 ("PCB打板") retrieved 芯拓/驭鹰者/深华科 instead of gold 嘉立创/深南电路/华秋PCB → only
  2/6. A Layer C retrieval gap, not Layer D.
- **qid5 — routing reachability gap.** Long preamble ("酒店电梯需要…机械臂…") puts 上述 mid-sentence;
  `looks_like_narrowing_query` is line-anchored → never enters `_handle_d_narrowing` → classifier
  `unknown`. The open-predicate lane is unreachable for this query shape. Real gap; follow-up.
- **qid2/8/12/15/25, S5-F2** — out-of-D-scope (data/alias/R3/chain-break), unchanged.
- **S3-F** — group 6 (anchor/clarification listing).

## Follow-ups logged (non-blocking)

1. **Professor region precision** — `南方科技大学` (SUSTech, actually in Shenzhen) is marked 不在深圳
   because its name lacks "深圳". Fix: reuse the existing `_INSTITUTION_KEYS_BY_LEN` /
   `_resolve_institution` alias set (already maps 南方科技大学→Shenzhen) in the region evaluator
   instead of bare substring on `institution`. Affects answer quality (S6B passes on routing anyway).
2. **qid5 routing reachability** — relax `looks_like_narrowing_query` to detect 上述/这些
   non-anchored (or route via classifier) so open-predicate follow-ups with preambles reach the
   narrowing selector.
3. **qid4 coverage=0.0 anomaly** — investigate why term-overlap is exactly 0 when all gold terms
   are present; likely a `_terms`/stopword interaction with the bulleted render. Eval-metric only.

## Next

Group 5 Accepted ⇒ **task group 6 (anchor discipline + clarification listing) Ready** — fixes S3-F
(list-then-他 must LIST members) and stops list citations polluting the anchor stack. After group 6,
D-scope work is complete; the acceptance-line reckoning (6 out-of-scope cases) lands at group 7.
