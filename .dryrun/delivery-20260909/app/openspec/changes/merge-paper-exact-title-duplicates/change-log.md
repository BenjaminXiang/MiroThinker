# Change Log — merge-paper-exact-title-duplicates

- **2026-06-29** — User: from first principles, design how to close the
  paper-duplicate-merge gap. Grounded the post-Stage-A dedup state:
  - Tier 1 (identifier-anchored): **0 groups** (DB constraint + Phase-2
    ingest-dedup enforce identifier uniqueness) — empty, no active merge.
  - Tier 2 (exact-title + single author-list): **804 groups / 2,135 rows**;
    725/804 have an identifier-bearing member (canonical pick).
  - Tier 3 (exact-title + divergent authors): ~7,923 groups — ambiguous,
    review-gated (`duplicate-paper-review-workflow`).
- **2026-06-29** — First-principles strategy: tiered by confidence
  (deterministic → high-conf auto → review-gated); the non-negotiable invariant
  is attribution preservation (migrate links to canonical BEFORE rejecting old).
- **2026-06-29** — Created OpenSpec change `merge-paper-exact-title-duplicates`
  (Standard, behavior-affecting, new capability `paper-dedup`): Tier 2 auto-merge
  reusing the Stage-A merge pattern (`upsert_migrated_link` →
  `upsert_paper_merge_alias` → reject old links → mark merged); pilot-gated with
  an adversarial title-match false-merge guard.
- **Pending** — verification-contract (task 0.1), Codex script+helper+tests,
  Claude pilot → full apply → retrieval spot-check, ledger registration,
  `openspec validate --strict`.
