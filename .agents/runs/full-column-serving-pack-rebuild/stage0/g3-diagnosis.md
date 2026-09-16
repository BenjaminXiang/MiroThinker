# G3 diagnosis correction (2026-09-04): data gap, not code break

Corrects the Stage0 report's G3 root cause. The earlier claim — "规划路径
`company_has_patent` 在包内注册表无此类型 → 类型断链" — was **wrong in
mechanism**: a translation layer exists (`_SOURCE_BOUND_RELATIONSHIP_PATHS`,
knowledge_read_isolated.py:163-170) mapping the planner path to the stored
type `patent_has_applicant` (inverse direction), and the pack registry DOES
install that type.

## Verified chain (all evidence reproducible)

1. **Anchor resolution works**: turn traces for the three failing golden
   queries show `inferred_domains=['patent']` + relationship lane planned —
   `_ReleaseBoundQueryPlanner.plan` bound the named company via
   `_resolve_named_company_patent_source` (first-turn name anchoring exists).
2. **Traversal works when data exists**: `深圳市普渡科技有限公司有哪些专利`
   → `relationship:17 candidates` (top bound company, 85 bindings).
3. **The gap is data**: streaming scan of the pack's 2.4GB relationships.json
   — `patent_has_applicant` instances target only **48 companies (~290
   instances)**; the pool (miroflow_light_lane_r1) holds **950 companies /
   7,668 resolved bindings**. All three golden companies (智赛/陶世/威洛博,
   top-patent-count in the pool) are absent: their canonical ids appear in
   the file only in non-endpoint contexts (assertions/decisions), never as
   `target_endpoint`.
4. **Missing batch**: `p4-applicant-binding-full-v1` — exactly the batch the
   killed runs 9/10 were rebuilding when the decision-persist layer froze.

## Fix routing

- Serving code: **no fix needed** (verified working).
- Data: deliver the binding batch into a rebuilt pack — the 阶段2 thin
  pipeline slice (decision-persist 修形 per R15 推论一) is the prerequisite;
  a binding-only incremental pack is the minimal data slice.
- Optional honest-disclosure slice (answer layer): when the relationship
  lane returns 0 for a named in-pack company, say 本地未收录该关联 instead
  of silently web-falling-back (34-44 web results observed). Behavior-
  affecting; needs its own OpenSpec change if pursued.

## Reproduce

- Bound-company probe: POST /api/chat/stream 普渡 query (above), expect
  relationship candidates > 0.
- Binding census: stream-scan script pattern in this file's history
  (`pat` regex over relationships.json, 8MB chunks, 1.2KB overlap).
