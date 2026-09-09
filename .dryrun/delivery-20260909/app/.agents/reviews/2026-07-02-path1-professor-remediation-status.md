# Path 1 (Professor Data-Quality Remediation) — Status (2026-07-02)

> Goal: bypass the external-throttling blocker (E) by fixing professors' LOCAL gate reasons →
> promote → embed → unblock qid27 (教授 vector recall + rescue). The professor ready gate does
> NOT require h_index (corrected); blockers are heterogeneous local data-quality issues.

## The loop — PROVEN end-to-end on 王强 (qid27 0/4 → 1/4 GREEN)

王强 (PROF-AE024E721DE1) was `needs_enrichment` (`profile_summary_too_short` +
`missing_research_overview_zh`). Fixed via:
1. **gate-fix**: LLM-regen profile_summary (31 → 276 chars, mentions 人形机器人/灵巧手/机器人)
   + INSERT a `professor_profile_section` (section_type='research_overview', language='zh',
   generation_method='llm_translation') — his raw_text already had the Chinese research
   direction, just needed the section row.
2. **re-evaluate**: `evaluate_professor_quality` → ready (no reasons).
3. **promote**: UPDATE professor SET quality_status='ready'.
4. **embed profile**: `run_milvus_backfill --collection professor_profiles --id ...` (the
   unified collection retrieve reads — NOT just `--domain professor`, which only writes the
   split identity/research collections).
5. **embed his 2 ready embodied papers**: `run_milvus_backfill --domain paper --paper-id ...`
   (the rescue finds professors via their PAPERS' authors — papers must be embedded too).
6. **eval-verify**: qid27 L1 0/4 → **1/4 (王强 HIT)**.

**Key insight**: a professor going GREEN requires embedding BOTH the profile (professor_profiles)
AND the ready papers (paper_chunks) — the rescue (FM4, in `_lookup_professors_by_topic`) finds
professors via their papers' authors, so the papers must be embedded. `--domain professor`
alone only writes the split collections (identity/research), NOT `professor_profiles` (the
unified one retrieve reads) — must use `--collection professor_profiles`.

## "不可再修" — the remaining 3 professors' heterogeneous blockers

| Professor | Blocker | Why not autonomous-fixable now |
|---|---|---|
| 柯文德 | `duplicate_verified_paper_links` (2 same-title paper pairs) | `run_paper_exact_title_dedup.py` is BROKEN (psycopg `%` placeholder bug at line 108 — `%'` rejected by the current psycopg version). Needs a code fix (escape `%` → `%%`) before the merge can run. Pre-existing bug. |
| 任尔夫 | `external_blocking_issue` + `field_contradiction` + `shallow_profile` | open pipeline_issue (release-blocking) + field contradiction — need the issue-tracker (resolve/close the issue) + contradiction resolver + profile regen. Per-professor investigative. |
| 刘桂良 | `external_blocking_issue` + `field_contradiction` | same as 任尔夫 — open issue + contradiction. |

These are NOT single-step autonomous fixes — they need: a code fix to the merge script
(柯文德), the pipeline_issue/contradiction machinery (任尔夫/刘桂良). That's the line.

## What this proves

- **Path 1 (professor) bypasses E (throttling)** — the blockers are LOCAL gate reasons
  (profile/research_overview/duplicate/issue/contradiction), not OpenAlex/h_index. The loop
  (gate-fix → promote → embed profile + papers → rescue) is the durable lever for the ~2338
  not-ready professors.
- **The loop is eval-measurable** — 王强 qid27 0→1/4 GREEN.
- **The remaining 3 + scale** need: (a) fix the merge-script `%` bug (柯文德 + the dedup
  workstream), (b) the pipeline_issue/contradiction resolver (任尔夫/刘桂良 + the
  professor-core-profile-paper-quality workstream), (c) batch the loop across the ~2338.

## Next (out of this round)

1. Fix `run_paper_exact_title_dedup.py` line-108 `%` placeholder bug → unblock 柯文德 dedup +
   the merge-paper workstream.
2. Resolve 任尔夫/刘桂良's open pipeline_issues + field contradictions (investigate + close).
3. Batch the Path 1 loop (gate-fix → promote → embed profile + papers) across the ~2338
   not-ready professors, by reason-class (profile-regen batch / research_overview batch /
   dedup batch / issue-resolution batch).
