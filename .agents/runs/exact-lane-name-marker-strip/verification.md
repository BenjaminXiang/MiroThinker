# Verification evidence: exact-lane-name-marker-strip (Stage0-G2a)

## ① New tests (3, in `test_exact_lane_marker_strip.py`)

- `test_exact_name_query_with_lane_marker_matches` — RED before fix
  (reproduces: query_text carrying the planner's `[lane=exact]` marker can
  never equal a display term), GREEN after.
- `test_markerless_exact_name_query_still_matches` — control (proves the
  marker is the sole breakage).
- `test_containment_with_marker_keeps_g6_behavior` — G6 containment
  insensitive to the marker (regression guard).

## ② Pre-existing suites

- `test_exact_title_containment.py` — all PASS.
- exact/lexical/lookup-focused sweep (`-k "exact or lexical or lookup"`):
  84 passed, 1 failed — `test_s8l3_release_scoped_lexical_phrase_recall…`
  **pre-existing** (stash-revert control: fails identically without this
  change).

## ③ E2E (18188 restarted on fixed code, warmup 564s)

Golden set rerun (same seed, 34 queries):

| metric | baseline | G1 | G1+G2a |
|---|---|---|---|
| exact-lane hits (named) | 3/24 | 3/24 | **16/24** |
| 点名 in-pack | 12/19 | 16/19 | **18/19 (95%)** |
| — company | 2/7 | 4/7 | **6/7** |
| — professor / patent / paper | 5/5, 3/3, 2/4 | 5/5, 3/3, 4/4 | 5/5, 3/3, 4/4 |
| 语义 / 关系 | 2/4, 3/6 | 3/4, 3/6 | 3/4, 3/6 (unchanged, as scoped) |

Residuals (honest):
- 字节跳动 → LOCAL_DROPPED: alias absent from pack (company alias fields
  4.8% filled) — owned by G2b alias closure (data work item).
- 池外论文 0/5 — G4 (pack scope).
- ByteDance Ltd. PASS via correct subject + exact hit; its citation card is
  still web-heavy (no local claim card for this row) — rides with G2b.

## Root cause recap (one line)

Planner stamps lane queries `f"{pure_topic} [lane={lane}]"`;
lexical/vector/web lanes strip their own marker; the exact lane never did —
so name equality was structurally impossible and only the
`exact_identifier` protected-slot path (patent numbers) survived.
