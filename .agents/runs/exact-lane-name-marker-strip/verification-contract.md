# Verification contract: exact-lane-name-marker-strip (Stage0-G2a)

Written BEFORE production edits.

## Behavior under test

B1: a LaneRequest whose `query_text` carries the planner's trailing
`[lane=exact]` marker MUST still match (equality) a document whose
display_terms contain the normalized query phrase.

B2: marker-less query_text (original_query fallback path) keeps matching
(no double-strip breakage).

B3: non-regression — G6 long-title containment (with trailing ask and
marker), identifier protected-slot path, and explicit_name slot path all
behave as before; quoted-name queries strip quotes symmetrically with the
lexical lane.

## Test levels

L1 unit: extend the house pattern of `test_exact_title_containment.py` —
`_matches("深圳市飞象工业科技有限公司 [lane=exact]", "company", {normalized
name})` → True (RED now); plus marker-less control and G6 containment with
marker appended.

L2 neighbors: `test_exact_title_containment.py` full file; exact/lexical
adapter suites.

L3 e2e: restart 18188 (fixed code, warmup first query); rerun
`stage0_golden_attribution.py`. Expected:
- exact-lane candidates > 0 for in-pack named queries (baseline 3/24, all
  patents) — company/professor/paper named queries gain exact hits;
- residual English-name misanchor rows (ByteDance Ltd., Future Mobility)
  flip to correctly-anchored PASS if the exact hit anchors fusion;
- 字节跳动 (alias, no alias data) may remain unresolved — honest residual
  owned by G2b (alias closure, data).

## Fix surface

`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`
— `_matches_exact_request` (+ new `_exact_query_phrase` helper).

## Rollback

Single-commit revert; matcher returns to marker-poisoned equality (baseline
3/24 exact hits).
