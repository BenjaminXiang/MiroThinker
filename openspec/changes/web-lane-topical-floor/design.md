# Design: web-lane topical floor

## Placement

`WebLane.__call__` (`knowledge_serving_isolated.py`), in this order:

```python
gated = _apply_web_subject_consistency(results=merged, request=request)
gated = _apply_web_topical_floor(results=gated, request=request)
if <enumeration refinement gate>:
    refined = self._merged_results_for_views((f"{query_text} 榜单", f"{query_text} 名单"))
    gated = _dedupe_normalized_results(
        (*gated, *_apply_web_topical_floor(results=refined, request=request))
    )
```

After the subject gate (its backfill pool is the very source of the noise) and
before the refinement merge (round-2 results bypass the subject gate entirely,
so they need the same floor). `record_lane_counts("web", …)` follows the whole
expression, unchanged.

## Admission rule

For each result, in order:

1. **Topical hit.** `searchable = _normalized_web_identity(title + " " + snippet)`
   contains any core query token ⇒ keep.
2. **Empty text.** `searchable == ""` ⇒ keep (fail-open; nothing to judge).
3. **Identity exemption.** Any name in `bound_entity_names ∪ {soft_context_subject}`
   matches the result — `_web_result_hits_bound_entity` name forms (full name,
   paren-stripped stem, legal-suffix shortenings, compact alias) or the pinyin
   brand domain (`_web_identity_domain_matches`) ⇒ keep. This is the same
   口径 the subject gate uses, so the floor can never undo an identity hit —
   English official pages and brand-domain pages survive with zero literal
   overlap.
4. Otherwise ⇒ drop.

Dropping is not compensated: the floor may empty the lane for a query whose
every web result was off-topic. That is intended (the alternative is keeping
noise) and it is the one behavior change that needs product sign-off if a
"never empty the lane" rule is wanted later.

## Core query tokens

```
text = original_query.casefold()
for phrase in _WEB_QUERY_SCAFFOLD_PHRASES (longest first): text = text.replace(phrase, " ")
for run in [0-9a-z㐀-鿿]+:
    CJK sub-runs      -> character bigrams            (国先中心 -> 国先, 先中, 中心)
    latin sub-runs    -> whole words, len >= 2
drop any token that is a substring of an _ANCHOR_LOCATION_LEXICON entry (深圳 -> gone)
```

- Scaffolding is stripped as *phrases*, not bigrams, so `详细介绍一下国先中心`
  cannot leak the cross-boundary bigram `绍一`/`下国`.
- Location qualifiers are **deleted rather than tokenized** (P3): a page that
  only mentions 深圳 is not topical evidence.
- No token survives (「介绍一下」) ⇒ `()` ⇒ fail-open with a warning log.

Rejected alternative: jieba segmentation. The serving read path does not
segmentation on the web lane, `jieba.Tokenizer()` costs ~0.4 s to load, and the
char-bigram rule already yields the exact token set the design specifies
(`{国先, 先中, 中心}`) with no dictionary or process-wide state. Kept in reserve
if the probe matrix ever shows bigram precision/recall losing to word tokens.

## Cost

No network, no model, no IO. Per-result work is one `_normalized_web_identity`
regex pass, a handful of substring tests, and one `urlparse`. Name forms and
the pinyin alias are computed once per lane call:
`_web_identity_domain_labels` (extracted from `_web_identity_domain_matches`,
semantics unchanged) + `_web_result_identity_hitter`.

Measured (this slice, 64 results, 200 repetitions):
median **0.875 ms**, p95 0.895 ms, max 0.979 ms — budget 5 ms.

## Fail-open

- no core token → keep everything, `_logger.warning`;
- empty title+snippet → keep that result;
- any unexpected exception → keep everything (whole body wrapped), warning with
  traceback. The floor can never fail a turn.

## Observability

`record_gate_drop("web_topical_floor", dropped)` only when `dropped > 0` —
mirrors `web_subject_consistency`. `record_lane_counts("web", in_/retained/filtered)`
stays where it is, after the floor and the refinement merge, so `filtered`
keeps meaning "dropped by any gate".

## Kill switch

`CANONICAL_V2_WEB_TOPICAL_FLOOR` read **per call** (not at import): a scratch or
hot-update line flips it by restarting the process with the variable set to
`0`, `false`, `off` or `no`; tests flip it in-process. Default: enabled.

## Deviation from the frozen design (for the main session to accept)

The frozen rule is "identity-exempt or topical match, else drop". Implemented
verbatim, it conflicts with an existing invariant of the same lane:
`WebLane.__call__` raises `ConnectionError("Bocha and Serper Web search are
unavailable")` when its result set is empty (line ~1692), and
`_WEB_SUBJECT_CONSISTENCY_FLOOR` exists precisely so that branch is not
reached. A query whose every web result is off-topic (translated query,
paraphrased question, English query against a Chinese page set) would
therefore turn into a *provider failure* instead of a filtered lane.

Resolution implemented here, conservative (under-drop beats over-drop): if the
floor would drop every result, it keeps the **first** result of the batch —
for the pipeline that is the subject gate's top-ranked survivor — and drops
the rest, logging a warning. The reported case still loses both junk pages.

If the product prefers a strictly-empty lane plus a UI message instead, drop
the guard block in `_apply_web_topical_floor` and change the lane's empty-set
handling; that is a larger, separate change.

## Design-vs-fact conflict found with real provider text (reported)

T1 was completed against the **real** snippets captured from the run15 pack:

```
sohu 减肥达人训练营: "深圳国贸营地简介 深圳国贸营地位于深圳传统商业中心区,…"
sz.gov.cn 平台综述 : "国际先进技术应用推进中心（深圳）依托粤港澳大湾区数字经济研究院建设,…"
```

Consequences the frozen design did not anticipate:

1. **The frozen token set cannot filter the reported page.** With core
   `{国先, 先中, 中心}`, the sohu page matches 中心 through its 商业中心区 address
   line, so P1 fails on real data. Generic nouns are therefore removed from the
   core set exactly the way location words are (`_WEB_QUERY_GENERIC_TOKENS`:
   中心/公司/企业/集团/平台/机构/项目/服务/产品/行业/领域/市场/信息/系统/情况/
   业务/单位/部门); the query then reduces to `{国先, 先中}`.
2. **A known false drop.** The sz.gov.cn page is topical (it names the entity,
   in the reordered form `国际先进技术应用推进中心（深圳）`), but that form is
   neither a query core token nor one of `_web_identity_forms` (which keeps the
   city prefix), so the floor drops it too. Fixing that means extending the
   identity forms with a city-stripped variant guarded by the existing
   branch-qualifier logic (`_evidence_branch_qualifiers`) so the 合肥 branch page
   stays out — a subject-gate change, deliberately **not** in this slice.
3. **Unanchored requests are out of scope.** With no bound entity and no soft
   subject there is no subject-consistency run at all (H1) and no backfill
   channel to compensate, and the professor fixtures show such queries
   legitimately return pages naming neither the query words nor a bound entity
   (`清华的王学谦` → `空间机器人团队`). The floor therefore only guards anchored
   requests; the H1 hole remains open by design decision, reported here.
4. **An empty filtered lane is not a provider outage.** The existing raise at
   the end of `WebLane.__call__` turns a zero-result lane into
   `status="unavailable"` plus a material `current_web_unavailable` limitation.
   The lane now raises only when the providers returned nothing at all
   (`merged` empty) and returns an empty lane result when the gates removed
   everything; `_report_web_degradation` already owns the outage signal.
