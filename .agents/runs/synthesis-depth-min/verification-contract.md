# Verification contract — synthesis-depth-min (slice ①min)

Written before production edits. RED artifacts: `red-case.md` (live transcript,
provider probe, merge-order read). Every RED item names the GREEN check that must
flip it.

| RED (measured today) | GREEN (must hold after) | How |
|---|---|---|
| Web-only list turn keeps `max_web_results=8`; 0/8 relevant material | window = `bundle.max_candidates + bundle.max_web_results` (16) for Web-only list turns; ≥3 relevant from the same views | unit (window-gate matrix) + live ask |
| Cross-check: local list turns unchanged (128), non-list Web turns unchanged (8) | same values as today | unit matrix |
| Kill switch absent | `CANONICAL_V2_WEB_WIDE_WINDOW=0` → 8-wide window, read per call | unit + in-process |
| Rewrite prompt yields Chinese-only views | one view may be the English/short-name form for abbreviation subjects | in-process rewriter probe (the class is directly callable) |
| 「目前有哪几种主流的JEPA变体？」 answers 719 chars / 0 citations / 6 flat items | ≥3 real citations, ≥4 categorised groups with per-item key points (AC1), no fabricated entities (AC2) | live ask dev + site, before/after transcripts |
| T7 first run: kept list = 10 items, all view-1 junk, 0 relevant while the lane held 45+ across 4 views | every view lands inside the window (`per_view_head = max(4, window//views)`); ≥3 relevant kept | unit (merge cap lock) + live ask kept-list audit |
| — | 片② matrix 6/6; negative control stays Web-only; 优必选 = 12 local patent citations | live ask ×6 |
| — | replay gate 7/7 | `replay_fix_round1.py` dev + site |
| — | recall gate 0 fail-level (baseline + control) | `eval_recall_canonical_v2.py --diff` |
| — | TTFT: JEPA warm ≤ round-43 envelope; 8-question probe not worse | live timing |
| — | reseal manifest-only, rollback pack byte-identical | reseal log + audit |
| — | targeted regression suites green (1 known pre-existing red exempt) | pytest |

Notes:

- The window change is plan-level: it must not alter `max_candidates`, the local
  enumeration window (128), the protected-slot invariants, or any lane's result
  ordering beyond how many Web results the read side keeps.
- The prompt clause must not weaken `_should_rewrite_serving_query`'s gate and must
  keep the failure contract (any rewrite error → deterministic view only).
- Site verification uses the same scripts as 片② (`staging-slice2/site/`), with a
  fresh reseal on the site interpreter (pydantic 2.13.4).
