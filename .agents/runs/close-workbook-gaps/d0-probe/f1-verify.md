# F1 verification — deterministic category recall in the lexical lane (close-workbook-gaps B1)

Locked shape (D0.5 phase-1 fix set / main-context instruction): for
enumeration-marker category queries, extract content words from the query
(stopword-stripped, >=2 chars), match them against `content_terms`, stay
inside the 48 enumeration window, apply a precision guardrail, and let hits
flow through the existing rerank/selection chain. Live path is pack mode —
both lane adapters (`knowledge_read_isolated.create_isolated_lexical_lookup_adapter`
and `serving_pack_loader._create_pack_lexical_lookup_adapter`) are wired to
the same shared helper; the new adapter-level test
(`test_pack_lexical_category_fallback_matches_upstream`) locks the lockstep.

## Micro-design (no contract change — no new lane kind, no LaneRequest/plan field)

- **Placement**: the category fallback lives entirely inside the lexical
  lane. `knowledge_read_isolated.py` gains `_category_query_terms` /
  `_category_recall_entries` / `_projection_category_term_buckets`;
  `_PublicLookupEntry` gains three short-field buckets computed once at view
  build. Both lexical adapters call `_category_recall_entries` **only when
  their primary whole-phrase pass produced zero candidates** — strictly
  additive recall; every query that returns anything today is byte-identical
  (locked by the markerless-query assertions in the adapter test and the
  unit matrix).
- **Trigger gate**: the normalized query must contain an enumeration marker.
  `_CATEGORY_RECALL_TRIGGER_MARKERS` mirrors serving's
  `_ENUMERATION_QUERY_MARKERS` (read cannot import serving; comment
  cross-references the source tuple).
- **Term extraction** (`_category_query_terms`): `_normalize` the query,
  strip stop phrases longest-first (enumeration scaffolding, generic
  organization nouns, particles, geography — the pack is city-scoped so city
  words carry no discrimination), split on non-CJK/alnum. Latin/digit runs
  >=2 chars are self-delimiting words (weight 2); CJK runs of 2-3 chars stay
  whole (weight 2); longer CJK runs decompose into overlapping bigrams
  (weight 1) — token level chosen because the project has no segmenter
  dependency and bigrams are deterministic (per the lock's "子串/词元级自定
  并写明理由").
- **Matching**: a term hits a document when it is a substring of any
  normalized content term (field values are free text like tech_tags
  "室内外配送机器人研发商", so token equality would miss them). Score = sum
  of surviving term weights, each multiplied by the tier of the strongest
  field the term hits (tiers below). Justification, measured on the sealed
  pack: the long template summaries mention category words across hundreds
  of companies (机器 coverage 1467/7089), while only true category members
  carry them in the short fields (industry=机器人: 8 docs).
- **Field tiers** (`_projection_category_term_buckets`, CompanyProjection):
  `industry` (closed primary label) x8; `industry_tags` / `tech_tags`
  (curated free-text tags) x4; `name` / `normalized_name` /
  `product_description` (short identity / product line) x2; every other
  content term (the long template summaries) x1. A term hitting several
  tiers counts once, at the highest. Calibration evidence in the next
  section.
- **Precision guardrails**: (a) coverage filter — a weight-1 bigram must hit
  >=2 public documents (singleton bigrams are entity-name fragments owned by
  the exact lane); a weight-2 self-delimiting word survives even with one
  hit (FPC/打板 are vocabulary, not names); (b) score floor 2 — one stray
  bigram never recalls (机器视觉 stays out of a 机器人 query); (c)
  `excluded_terms` / non-empty `displayed_entity_ids` / request domains
  restrict exactly as `_matches_lexical_request` does.
- **Bounded**: sort by (-score, domain, canonical_object_id, document_id),
  truncate to `request.max_candidates` — 48 on the enumeration branch, so
  fusion sees the hits inside the existing window and the existing
  rerank/selection chain owns final ranking (per the lock).

## Field-tier calibration (measured on the sealed run14 pack)

The tier constants were set by measurement, not by guess; two flatter
schemes fail on the g2 query (`collect_f1_category_recall.py` /
`inspect_f1_g2_scores.py`):

- **Flat x2** (single short-field bucket, first F1 iteration): the whole
  short-field set boosts together, so 九号 (industry=机器人, no scenario
  text anywhere else) scored 4 and sat in a 320-company score-4 tie at pool
  rank 724 — the reported defect.
- **Flat x4 on industry+tags** : tech_tags are free text
  ("室内外配送机器人研发商"), so 机器/器人 tag hits cover hundreds of
  companies. Measured histogram: score 9 -> 45 companies, score 8 -> 374.
  The five industry=机器人 GTs land at 9 (云迹 22 / 普渡 30 / 开普勒 47 /
  擎朗 51) or 8 (九号 420) — the tag mass still outnumbers the window.
- **Final tiers x8/x4/x2/x1**: `industry` is a closed controlled label (8
  companies with industry=机器人 pack-wide) while tags are free text, so
  the label gets its own top tier. The strongest non-label profile measured
  on the pack scores 13 (two tag terms at x4 plus product/summary extras);
  two bigram label hits at x8 score 16, clearing it with margin. No
  company-specific rules anywhere — the split is field semantics only.

## Offline GT recall evidence (sealed run14 pack, real functions, read-only)

Script: `d0-probe/collect_f1_category_recall.py`; JSON:
`d0-probe/f1-category-recall.json`; per-GT field provenance:
`d0-probe/inspect_f1_gt_fields.py`. "before" = the production whole-phrase
matcher (what runs live today; production trace shows lexical=0 for these
turns); "after" = `_category_recall_entries` over the pack's 7,089 public
company documents. Probe queries verbatim from the 2026-09-10 turn-trace.

### g2-t1 中国有哪些成熟的酒店送餐机器人供应商 — before 0 → after 48 (pool 1390)

| GT | identities in pack | recalled (window rank) | full-pool rank |
|---|---|---|---|
| 云迹 | 1 | **1** (1) | 1 |
| 普渡 | 3 | **1** (2) | 2 / 54 / 438 |
| 开普勒 | 1 | **1** (3) | 3 |
| 擎朗 | 1 | **1** (4) | 4 |
| 九号 | 1 | **1** (8) | 8 |
| 艾唯尔 | 1 | **1** (12) | 12 |
| 安赛步 | 1 | 0 | 436 |

6/7 GT entities recalled, all six inside the top-16 answer-claim ceiling —
the five industry=机器人 GTs (云迹/普渡/开普勒/擎朗/九号) lead the window
(score 16-17), 艾唯尔 follows via its tech_tags + scenario hits (12). The
普渡 second identity (industry=物流运输, tech_tags 室内外配送机器人研发商)
rose 438→54 on the tag tier. **Residual gap**: 安赛步 (pool 436) —
industry=人工智能, empty tags, product line "AS09"; only its name carries
机器人 (product tier, 2+2) and its summary has no 酒店/送餐 text. Zero
scenario/category overlap beyond the name: deterministic term matching
cannot reach it (data thinness, the vector lane's job).

### g5-t1 我想找PCB打板， 有哪些推荐 — before 0 → after 48 (pool 150)

| GT | recalled (window rank) | full-pool rank | pcb text location (measured) |
|---|---|---|---|
| 顺易捷 | **1** (9) | 9 | tech_tags "印制PCB/线路板快速打样层板研发商" (tag tier) |
| 深南电路 | **1** (41) | 41 | long summary only (score-2 tie, id order) |
| 嘉立创 | 0 | 54 | tech_tags empty, product None → summary only (score-2 tie) |
| 则成 | 0 | 62 | tech_tags "FPC组件产品研发商" — no literal "pcb" |
| 兴森 | 0 | 70 | tech_tags "印制线路样板及小批量板研发商" — no literal "pcb" |
| 一博 | 0 | 98 | tech_tags empty, product "未找到" → summary only |
| 上达 | 0 | — | FPC/FPCA vocabulary only — zero term overlap |
| 精诚达 | 0 | — | FPC/柔性线路板 vocabulary only — zero term overlap |

2/8 in-window. **Residual gaps, all structural** (field provenance from
`inspect_f1_gt_fields.py`): 嘉立创/一博 carry pcb only in the long summary
and tie at score 2 with ~100 others, cut by canonical-id order just outside
the 48 window; 则成/兴森/上达/精诚达 speak FPC/线路板 vocabulary that shares
no term with {pcb, 打板} — a synonym/expansion problem (vector lane or
query-side vocabulary), not a ranking one. Per the lock, no company-specific
patches were added. The window top is now tag-verified PCB companies (36
docs carry pcb in name/industry/tags/product_description) instead of an
arbitrary id-ordered slice.

### pcb-list 深圳有哪些做PCB的公司 — before 0 → after 48 (pool 150)

Same shape as g5-t1: 顺易捷 9 / 深南电路 40 in; 嘉立创 53 / 则成 61 /
兴森 69 / 一博 97 just outside; 上达/精诚达 zero-overlap.

### embodied 深圳有哪些做具身智能的公司 — before 0 → after 48 (pool 3037)

No GT list recorded for this workbook question; the lane now returns 48
bounded candidates where production returned 0.

### Latency

Per category query against the full 47k-document pack (7,089 companies):
warm steady-state 120-210 ms (g2 208.8 / g5 179.1 / pcb-list 120.3 /
embodied 139.9) — same order as the existing lexical scan, far below the
web lanes' network time; the pack view is process-resident in serving. The
first call in a fresh process pays interpreter warm-up (measured cold:
600-800 ms). Phase profile (`inspect_f1_latency.py`, g2): content-term scan
175 ms, the three field-bucket scans 15 ms — the tier weighting costs ~7%
over the flat scan.

## Tests

- New `tests/canonical_v2/test_knowledge_read_isolated.py` (13 tests):
  extraction matrix (verbatim g2/g5/embodied queries), marker gate, empty /
  single-char residue, bigram coverage >=2 (singleton-bigram noise stays
  out), weight-2 singleton word survives (FPC case), score floor (机器视觉
  excluded), tag-field boost ordering, **field-tier ordering
  (industry > tags > product > summary for the same term, ids arranged to
  reverse under plain id order)**, **industry label outranks a multi-term
  summary tie (the run14 g2 failure shape, 16 vs 5 vs 3)**, **multi-tier
  term counts once at the highest tier (no stacking)**, domain/displayed/
  excluded filters, window truncation + deterministic order. Fixture source:
  constructed scenarios; extraction expectations taken from verbatim run14
  trace queries.
- `test_serving_pack_loader.py`: new
  `test_pack_lexical_category_fallback_matches_upstream` — both adapters
  fire the fallback identically on the hermetic pack (recalls exactly the
  fixture company), and a markerless query on the same text never falls
  back. RED side: before the wiring both adapters returned 0 candidates for
  category queries (production trace lexical=0; sealed-pack "before" column
  above).

## Regression

(pending — full tests/canonical_v2 run + suites; appended below)

## Regression (final, main-context closed out 2026-09-11)
- Four-file set: 327 passed / 0 failed (read_isolated 13 / serving_isolated 286 / trace_reporting 5 / pack_loader 23).
- Admin trace files: 16 passed.
- B1 focused (-k relationship-or-patent): 96 passed, 26 skipped, 1306 deselected, 2 warnings in 138.44s (0:02:18)
