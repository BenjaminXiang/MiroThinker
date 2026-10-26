# Proposal: materialize-professor-paper-projection

Human doc: `docs/plans/2026-10-26-systematic-completion-gates.md` §3.3.

## Why

Gate 3.1 proved the pack already holds 10,742 professor→paper edges, but the
lookup documents carry none of them: `paper.professor_ids` is empty and 86% of
the linked professors have no `paper_count`. Gate 3.3 then showed the edges
cannot be materialised wholesale — 10,742 of them claim `confidence=1.0`, and
hand review found same-name merges among the top nodes (王强: HPC professor with
remote-sensing and catalysis papers). Identity services cannot fix it: ORCID
returns empty records for this population, OpenAlex and Semantic Scholar are
rate-limited, homepages are not publication lists.

What we do have: a semantic coherence score between each professor's declared
directions and their linked papers, calibrated on 30 hand labels, which separates
matches (top-3 ≥ 0.33) from merges (≤ 0.28). On that basis an allowlist of 536
professors / 6,112 papers was produced offline.

## What Changes

1. A **sidecar overlay** the serving runtime may load from
   `CANONICAL_V2_PROFESSOR_PROJECTION` (unset = off, today's behaviour).
2. When active and the professor is on the allowlist, the claim builder adds
   `论文数` and up to three `代表作` to the professor claim.
3. Precision rules: pack values are never overwritten; records flagged
   `duplicate_name` are ignored; a missing or malformed file disables the overlay
   and logs a warning instead of failing the request.
4. Nothing is written into the serving pack — it stays byte-identical, so the
   boot-time hash check is unaffected.

## Impact

- Behaviour change only when the environment variable is set. With it unset,
  claims are byte-identical to today.
- 533 allowlist records survive the `duplicate_name` filter (3 dropped).
- Deployment is a separate step: enable on the customer site, run the 27-turn
  eval gate, and turn it off by unsetting the variable if the gate regresses.

## Out of scope

- Fixing template summaries (they still dominate some claims; separate slice).
- Rebuilding the pack with the projection baked in.
- Professors without directions (272) and the review bucket (200): they keep no
  paper count.
