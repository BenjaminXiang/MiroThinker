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
