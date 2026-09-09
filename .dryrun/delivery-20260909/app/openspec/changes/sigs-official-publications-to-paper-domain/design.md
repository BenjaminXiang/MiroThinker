## Context

SIGS professor pages use a shared template where publication content appears under tab-like sections such as "Representative Publications" / `代表性论文`. The content is official and source-grounded, but current behavior has two gaps:

- The homepage publication parser can split author-prefixed citations incorrectly, producing author lists as `clean_title` and moving the true title into venue-like fields.
- The professor seed recollection path writes professor profile data without synchronously running the paper-domain bridge, while the existing `paper.homepage_ingest.run_homepage_paper_ingest` path already knows how to resolve titles, upsert canonical papers, create professor-paper links, preserve evidence tier, and fetch professor-page PDFs.

The change must bridge official SIGS page publications into the paper domain without turning the professor seed loop into a long-running OpenAlex/arXiv batch.

## Goals / Non-Goals

**Goals:**

- Use Ahmed Elazab's SIGS page as the first RED regression for author-prefixed citation parsing.
- Parse all official SIGS publication entries without a business-level per-professor paper cap.
- Preserve the source section label as provenance only; do not assert that listed papers are representative works.
- Reuse `run_homepage_paper_ingest` as the post-collection bridge into `paper` and `professor_paper_link`.
- Write verified professor-paper links with `is_officially_listed=true` and page-tier evidence.
- Attempt metadata, abstract, summary, full-text, and Milvus refresh through paper-domain follow-up jobs.
- Produce Ahmed, random SIGS sample, cross-institution publication-parser audit evidence, and full SIGS rollout statistics.

**Non-Goals:**

- Do not run OpenAlex/arXiv title resolution synchronously inside the professor seed recollection main loop.
- Do not fabricate `abstract_clean` for page-only papers that have no resolver or full-text abstract.
- Do not add a database migration unless an implementation check proves the existing schema cannot represent the required data.
- Do not redefine professor `top_papers` semantics in this slice; the paper-domain bridge treats page publications as officially listed papers.
- Do not claim full SIGS completion until real run evidence exists.

## Decisions

1. Fix parser behavior before bridge execution.
   - Rationale: bad parsed titles cause title resolution to query external providers with author strings, which is slow and produces incorrect canonical paper rows.
   - Alternative considered: add only an ingest-side skip guard. That would prevent some damage but leave the official data unusable.

2. Use LLM-assisted extraction as the fallback for variable official professor-page citation formats.
   - Rationale: SIGS pages exposed the issue first, but cross-institution audit also found suspicious author-string titles and low-recall publication sections on SUSTech and Shenzhen University pages. Continuing to add citation-specific regex rules is brittle and hard to audit.
   - Implementation direction: deterministic rules locate publication sections and parse easy cases. When a complex page is explicitly run with LLM extraction, the model receives only the publication-section text and returns strict JSON with `title`, `authors_text`, `venue_text`, `year`, `source_span`, and confidence. A validator accepts only source-grounded items.
   - Trigger policy: with an LLM extractor configured, fallback is not tied to a single hostname. It triggers when rule parsing yields suspicious publication titles, or when the detected publication section contains citation signals but rules extract fewer than three items.
   - Safety boundary: the LLM does not create abstracts and does not write storage rows. Invalid items are dropped or left for review; accepted items still pass through paper-domain title resolution, canonical paper upsert, and verified professor-paper linking.
   - Alternative considered: fully rule-based parsing for every citation style. Rejected because the current random sample already shows multiple independent author/title boundary conventions.

3. Use `run_homepage_paper_ingest` as the SIGS paper bridge.
   - Rationale: it already performs `resolve_paper_by_title`, `upsert_paper`, `_upsert_professor_paper_link`, page-only fallback, PDF full-text fetch, tier evidence, run tracking, and resume checkpoints.
   - Alternative considered: call paper resolution directly from professor seed recollection. Rejected because recollecting 250 SIGS professors would be coupled to external provider latency and rate limits.

4. Treat publication section labels as provenance, not ranking.
   - Rationale: the system is not qualified to infer which publications are representative for every field. All official page-listed publications are eligible for paper-domain ingestion.
   - Alternative considered: map `代表性论文` to top/representative paper semantics. Rejected because it introduces a domain judgment and can hide non-listed papers from the bridge.

5. Remove business-level caps from official publication extraction and ingest.
   - Rationale: the requirement is to ingest every official listed page publication. Operational controls may still exist at the run level, such as professor `limit`, checkpoint resume, provider backoff, and PDF fetch caps.
   - Alternative considered: fixed top-N per professor. Rejected by user requirement and because it loses official source data.

6. Keep abstract/summary quality honest.
   - Rationale: resolver or full-text extraction may provide an abstract. When none is available, `abstract_clean` remains empty and the paper stays in an enrichment/review state with diagnostic issues.
   - Alternative considered: synthesize an abstract from title/venue. Rejected because it would pollute the paper domain with invented source content.

## Risks / Trade-offs

- Parser overfitting to Ahmed's citation style -> Mitigation: add focused unit tests for author-prefixed numbered SIGS citations and keep existing homepage publication tests running.
- Very large publication sections can create long external-resolution runs -> Mitigation: no per-professor publication cap, but execute as a post-collection job with `--prof-id`, `--limit`, and resume checkpoint controls.
- Resolver misses for recent or obscure papers -> Mitigation: keep page-only canonical rows and verified links, mark quality as enrichment/review needed, and record pipeline issues when all titles are unresolved.
- Full SIGS rollout may hit provider or DB runtime limits -> Mitigation: stage Ahmed first, then random 10 SIGS professors, then full SIGS with checkpoint resume.
- Existing dirty worktree may contain unrelated changes -> Mitigation: keep this slice to OpenSpec, parser, ingest bridge tests, and validation artifacts only.

## Migration Plan

1. Create RED tests for Ahmed-style SIGS citation parsing and no official-list truncation.
2. Fix `homepage_publications.py` author-prefixed citation splitting and remove official publication extraction truncation.
3. Add LLM-assisted extraction tests and validation so variable SIGS citation formats can be structured without regex overfitting.
4. Add ingest guard/tests so malformed author-list titles do not enter resolver/upsert silently.
5. Wire `run_homepage_paper_ingest` to optionally use the validated LLM extraction fallback outside professor seed recollection.
6. Run Ahmed dry-run to collect parse count, title correctness, resolver hit rate, page-only count, and issue count.
7. Run Ahmed real bridge, summary backfill, and targeted paper Milvus refresh when local services and credentials are available.
8. Run a random SIGS sample of 10 professors and record statistics.
9. Run cross-institution audit samples and confirm non-SIGS suspicious/low-recall cases use the same source-grounded fallback.
10. Run full SIGS with a resume checkpoint after sample acceptance.

Rollback is straightforward for code: revert the parser/ingest changes and stop the post-collection job. Data rollback, if needed after a real run, must delete only rows linked to the recorded pipeline run and should be planned separately before destructive actions.

## Open Questions

- Whether SIGS official profile pages should be classified as `prof_homepage_tier2` or `prof_homepage_tier3` depends on the stored `source_page.page_role`. The bridge must use the strongest tier derived from existing page-role data and file a diagnostic issue when no tier is derivable.
- Page-only low-confidence `summary_zh` from title/venue fallback is allowed only if implemented with explicit low-confidence quality status and diagnostic evidence. This slice prioritizes resolver/full-text summaries and must not fabricate `abstract_clean`.
