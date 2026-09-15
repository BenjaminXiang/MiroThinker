# Proposal: data-cleaning-batch2 (D0-b: venue merge, edge dedup, dirty geography, dead declarations, quality report)

> Second D0 slice of `docs/plans/2026-09-15-requirements-gap-plan.md` §8 (R21).
> Continues `data-cleaning-batch1` (`openspec/changes/data-cleaning-batch1/`),
> which landed the projection-layer cleaning point, the publication gate and the
> offline counter.  This slice adds the remaining rule-based items of the
> assessment's D0 backlog that fit that architecture, and it closes batch 1's
> `debt:` note by writing a quality report from the build.

## Why

1. **Venue labels are not reusable.** 5,204 distinct `venue` labels for 24,520
   papers; 153 groups are the same venue under different spellings
   (`arXiv (Cornell University)` 418 vs `arXiv` 242; `PLoS ONE` vs `PLOS ONE`;
   `… (2018)` suffixes; `Proceedings of the …` prefix family).  Category recall
   and any "papers from venue X" answer depend on the label being one label.
2. **The relationship layer publishes duplicate edges.** 10,773
   `professor_attributed_to_paper` edges cover 10,742 distinct (professor,
   paper) pairs: 31 pairs came through two link families (retained
   `PROF-PAPER-LINK-*` and the P4 salvage `p4-professor-paper-link:*`), so one
   attribution is counted twice.
3. **Three geography values defeat the city rule** introduced in batch 1:
   `广东省-珠海` (city lost its `市`), `苏州市` (province missing) and
   `-开曼群岛` (stray separator).
4. **Applicant rows need a decision, not an assumption.** 4,951 of 12,565
   applicant rows carry no `canonical_company_id`; measured, they are *not*
   empty rows: every one of them carries the applicant's name
   (`深圳先进技术研究院`), 0 rows are nameless and 0 bindings point outside the
   released company set.
5. **46 declared fields are never filled** (measured here as 49, see the
   reconciliation note) - a declaration without data makes a consumer believe
   the field is obtainable (R9's "no reader, no weight").
6. **The build produced no data-quality artifact.** R21 requires every rebuild
   to emit a quality report; batch 1 could only produce one offline.

## What Changes

1. **Venue merging** at the projection's cleaning point: a grouping key
   (case/punctuation/`&`/stopword/`Proceedings of the [the]`/parenthetical/year
   agnostic) plus a deterministic winner (most frequent canonical spelling,
   ties by label).  The map is computed once per build from the same selections
   the projections consume - no pinned table, no stale mapping.
2. **Edge de-duplication** in the build's link assembly: one attribution link
   per (professor, paper) pair, smallest link id wins so the retained historical
   link beats the synthesized families; plus a fail-closed uniqueness assertion
   in the relationship projection that refuses to publish two edges for the same
   (type, source, target).
3. **Geography repair** for the three dirty shapes, inside the existing rule:
   separator stripping, prefecture-city `市` restoration from a declared
   lexicon, and province recovery from the company's own registered address.
4. **Applicant decision (keep + explicit marker).**  The rows are kept: they
   carry the applicant names that D1's company binding needs, and the unbound
   state is already machine-readable as `canonical_company_id: null` - the exact
   filter `_direct_patent_applicant_scan` uses, so its semantics are preserved.
   Two new fail-closed gates protect the shape: a published applicant row must
   carry a name, and a binding must point at a company the release contains.
5. **Dead-declaration measurement.**  Every build now reports, per domain, the
   fields that are declared on every document and filled on none (49 on run15;
   the assessment counted 46).  Retiring a declaration is a catalog revision
   (content-hash pinned) plus a projection-contract change, i.e. a deliberate
   release-identity change: the decision table in `design.md` records
   keep-with-fill-path vs retire-pending-catalog-revision for all 49 and this
   change does **not** unilaterally rewrite the pinned catalog.
6. **Build quality report**: `publication-quality-report.json` is written next
   to the index artifacts (not in the pack; the pack loader binds an exact file
   registry and the sealer copies only the index files), containing the
   publication audit (placeholders, glue, research directions, geography,
   applicants, dead declarations) and the quarantine records re-derived from the
   build's own source selections with the same pure rules.
