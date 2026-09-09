# Tasks: paper-homepage-enrichment-completion

## 1. Tier evidence

- [x] T1.1: Trace professor source-page tier classification into
  `paper/homepage_ingest.py`.
- [x] T1.2: Emit `prof_homepage_tier2` or `prof_homepage_tier3` for
  page-declared paper evidence.
- [x] T1.3: File a `pipeline_issue` when tier classification is absent
  and cannot be derived.
- [x] T1.4: Add unit tests for Tier 2, Tier 3, and missing-tier cases.

## 2. Enrichment fallback

- [x] T2.1: Add or wire arXiv enrichment lookup for DOI/arXiv-aware
  paper rows.
- [x] T2.2: Extend `PaperMetadataEnrichment` with author metadata if
  the existing model lacks it.
- [x] T2.3: Merge authors by source priority while preserving ORCID
  evidence when present.
- [x] T2.4: Keep `citation_count` OpenAlex-only.
- [x] T2.5: Add tests for OpenAlex, Crossref, Semantic Scholar, and
  arXiv fallback ordering.

## 3. Identifier contradictions

- [x] T3.1: Detect DOI mismatch across enrichment sources.
- [x] T3.2: Detect arXiv id mismatch across enrichment sources.
- [x] T3.3: Write `pipeline_issue` rows with an existing stage value
  for identifier contradictions.
- [x] T3.4: Prevent auto-promotion to `ready` while an unresolved
  identifier contradiction exists.
- [x] T3.5: Add tests for contradiction and non-contradiction cases.

## 4. Summary-to-Milvus refresh

- [x] T4.1: Choose and document the refresh signal contract.
- [x] T4.2: Update the summary backfill or enrichment write path to
  emit that signal when `summary_zh` changes.
- [x] T4.3: Add `run_milvus_backfill.py` support for targeted paper
  refresh by paper id, changed-since, or pending marker.
- [x] T4.4: Add tests proving a changed `summary_zh` row is selected
  for re-embedding.

## 5. Rebuild runbook and verification

- [x] T5.1: Add a short rebuild order note to this change's
  `acceptance.md` or run artifact.
- [x] T5.2: Run focused paper enrichment tests.
- [x] T5.3: Run paper summary backfill tests touched by the refresh
  signal.
- [x] T5.4: Run Milvus backfill tests touched by targeted refresh.
- [x] T5.5: Record a bounded end-to-end sample from summary write to
  paper chunk refresh.
