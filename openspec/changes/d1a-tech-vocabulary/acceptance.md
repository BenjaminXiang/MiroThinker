# Acceptance: d1a-tech-vocabulary

Every criterion is checked by a command recorded in
`.agents/runs/d1a-tech-vocabulary/verification.md`. Counts marked "(measured)" are
filled from `out/vocabulary-replay-counts.json`; the launch gate (#5 of
`docs/plans/2026-09-15-requirements-gap-plan.md` §11) is satisfied when AC1-AC6 pass.

## AC1 - controlled vocabulary exists and is a real reduction

- Distinct `tech_tags` values 4,945 map into a controlled vocabulary of `N = 447`
  concepts (**11x reduction**), one concept per queried category.  The bound is
  stated as a reduction factor (>= 10x) rather than a fixed count: the chunked
  induction is measured, and 447 is what 12 chunks x 100 concepts produced.
- Each concept carries a canonical name, a definition and at least one acceptable
  evidence form (schema-validated; a concept missing any field cannot load).

## AC2 - coverage and honesty

- `tech_tags` mapped-value coverage `>= 0.90` (measured 0.9531: 4,713 of 4,945).
- `industry` coverage is **reported, not gated** (measured 0.7561: 31 of 41): the
  ten undecided labels are `-`, 企业服务, 体育健身, 开采, 批发零售, 旅游户外,
  服装纺织, 消费升级, 生活服务, 餐饮业 - the induction refused to invent concepts
  for non-technical labels, which is the required no-guess behaviour.  They publish
  verbatim and are listed in the artifact and the report.
- Every undecided value is present in the `unmapped` list **and** still published
  verbatim; the published set of tag values equals (concept names) plus (unmapped
  raw values) with no third case, and no value is silently dropped.

## AC3 - reproducibility (R21 guard #2)

- The build path calls no provider: the projection reads the recorded bundle /
  packaged artifact only (`grep` proof plus the replay tests).
- Replaying the recorded bundle twice yields byte-identical vocabulary JSON.
- The packaged artifact equals `replay_vocabulary_from_bundle(bundle)`.
- A tampered transcript, a missing call, a wrong batch composition, an unknown
  concept id, a malformed line, a drifted prompt hash and an edited bundle each fail
  closed with a distinct error - no LLM fallback exists.

## AC4 - retrievability before/after (run15 copy, read-only)

- Every probe is reported before/after with three numbers: literal tag-field hits,
  concept-level hits, and **companies that lose the literal string**.  No probe may
  lose a company: for every probe with a source hit, all of its companies stay
  published with tags (measured below).
- Where a probe's literal string disappears (`灵巧手` 5, `激光雷达` 7, `协作机器人` 3,
  `配送机器人` 1, `餐饮机器人` 1), the report lists the concepts those companies now
  carry, so the substitution is visible and reviewable rather than hidden - the raw
  value that produced each concept is recoverable from the artifact's mapping table.
- Probes that gain: `工业机器人` 43 -> 128, `传感器` 121 -> 173,
  `机器人` 414 -> 423, `具身智能` 11 -> 14 (concept-level, measured).
- Tags per company after mapping `>=` before (union, never fewer): 0.774 -> 0.865.

## AC5 - gate and report wiring

- `publication-quality-report.json` carries a `vocabulary` section with unique-value
  counts, concept counts, coverage, unmapped count/examples, tags-per-company and
  call count (`attach_vocabulary_section` on a report fixture; idempotent).
- The gate fails the build on coverage below the floor, on a published concept
  reference outside the artifact, and on a published tag value that is neither a
  concept nor a recorded unmapped value.
- The collection gap (one tag per company / companies with no tags) is reported and
  never blocks.

## AC6 - production safety and scope

- Zero writes under `/var/tmp/mirothinker-data-v2/`; the whole slice works from the
  `/tmp/d1a-scratch/` copy; 18188 is untouched and not restarted.
- No rebuild is triggered; the change is documented as effective from run16.
- No secret is printed or written: the provider key is read through the repository's
  existing local credential chain (`providers/local_api_key.py` / `.deepseek_api_key`)
  and never enters an artifact (bundle records provider/model/prompt only).
- Re-tagging candidates (LLM-inferred tags from local free text) are **not** part of
  this slice and no inferred tag reaches the retrieval surface.
