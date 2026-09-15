# Acceptance: d1a-tech-vocabulary

Every criterion is checked by a command recorded in
`.agents/runs/d1a-tech-vocabulary/verification.md`. Counts marked "(measured)" are
filled from `out/vocabulary-replay-counts.json`; the launch gate (#5 of
`docs/plans/2026-09-15-requirements-gap-plan.md` §11) is satisfied when AC1-AC6 pass.

## AC1 - controlled vocabulary exists and is a real reduction

- Distinct `tech_tags` values 4,945 map into a controlled vocabulary of `N` concepts
  with `N <= 400` (a 12x or better reduction), one concept per queried category.
- Each concept carries a canonical name, a definition and at least one acceptable
  evidence form (schema-validated; a concept missing any field cannot load).

## AC2 - coverage and honesty

- `tech_tags` mapped-value coverage `>= 0.90`; `industry` coverage `>= 0.90`.
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

- Category-probe support in the tag fields improves for the GT-flavoured probes
  (`送餐`, `配送机器人`, `餐饮机器人`, `具身智能`, `灵巧手`, `协作机器人`, `PCB`,
  `激光雷达`) - reported per probe, before and after, no probe may regress.
- Concept-level support is reported for the same probes, so the gain attributable to
  the vocabulary (raw strings -> concept) is visible separately from the substring
  effect.
- Tags per company after mapping `>=` before (union, never fewer).

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
