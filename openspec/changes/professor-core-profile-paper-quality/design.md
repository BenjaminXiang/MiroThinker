## Context

The Professor domain currently has the ingredients for the intended pipeline,
but they are not coordinated by one release contract. Admin seed triggering can
write Professor rows, homepage paper ingest can create verified
`professor_paper_link` rows, paper title enrichment can migrate page-only papers
to richer canonical rows, paper summary enrichment can promote paper quality,
and Professor output summaries can write `paper_summary`. These steps are
implemented as separate paths, so real data can stop between stages while still
being visible to users.

The current data snapshot shows the impact:

- 3,387 Professor rows exist and 1,407 are marked `ready`.
- 928 Professor rows have `profile_summary` shorter than 150 characters; 230
  of those are still `ready`.
- 2,202 professors have verified papers, but none have `paper_summary`.
- 6,563 verified title/year duplicate groups exist across Professor paper
  links, affecting 994 professors; 6,315 groups already have an enriched row.
- Known cases include Ahmed Elazab's duplicated Alzheimer paper, Ding Wenbo's
  short/repetitive summary and missing paper summary, and the pFedGPA paper
  lacking arXiv/PDF enrichment.

This change is behavior-affecting. The behavior contract belongs to the new
`professor-core-profile-paper-quality` capability.

## Goals / Non-Goals

**Goals:**

- Make the university roster -> official Professor profile -> homepage paper
  chain explicit and testable.
- Persist Chinese user-facing profile sections instead of extracting them only
  at API read time.
- Make Professor `ready` depend on user-facing quality, not only minimal
  identity presence.
- Deduplicate homepage-derived papers against enriched canonical paper rows and
  preserve merge traceability.
- Chain post-seed follow-up stages so full seed runs can produce publishable
  Professor/Paper data or visible blockers.
- Align admin UI and chat paper links on `/paper/<paper_id>`.
- Use `docs/测试集答案.xlsx` rows for Ding Wenbo and pFedGPA as acceptance
  samples for this change.

**Non-Goals:**

- Do not require hidden company/startup roles to be collected by the Professor
  crawler. Company/news evidence remains a downstream cross-domain retrieval
  concern.
- Do not use external literature databases to discover papers by professor
  name. External sources enrich papers already found from official Professor
  pages.
- Do not rewrite all historical Professor or Paper pipeline architecture in one
  slice. The implementation should add a coordinated quality closure path over
  existing modules.
- Do not change Agentic RAG A-G classification semantics.

## Decisions

### 1. Add durable profile-section storage for Chinese research overview

Use an additive `professor_profile_section` table, or an equivalent additive
storage surface, for user-facing long profile sections. The minimum section for
this change is `research_overview_zh`; future sections may include research
progress, education narrative, work narrative, honors narrative, and student or
academic-service narrative.

Each section row should include `professor_id`, `section_type`, `language`,
`content`, `source_page_id`, `source_span` or source text hash,
`generation_method`, `source_language`, `run_id`, and timestamps. If the
official profile only provides English research text, the pipeline may call an
LLM translation step and must preserve the English source text or hash. The
admin API should expose the Chinese overview from this durable storage first
and fall back to raw extraction only for diagnostics.

Alternative considered: add only `professor.research_overview_zh`. This is
smaller but repeats the current pattern of stuffing user-facing sections into
one canonical row and makes later section-level provenance harder.

### 2. Treat paper merge traceability as part of canonical quality

The Paper canonical path must merge Professor homepage papers through DOI,
arXiv id, then title/year/author similarity. When a page-only row is migrated to
an enriched canonical row, the old paper id must retain a durable target through
`paper.merged_into_id`, a `paper_merge_alias` table, or an equivalent queryable
mapping. Encoding the target only in `professor_paper_link.rejected_reason` is
not sufficient for API, summary, or index maintenance.

Alternative considered: keep the current repair script as an offline cleanup
only. That leaves normal seed runs able to recreate duplicate user-visible
links, so it does not enforce the invariant.

### 3. Introduce a seed-scoped quality closure runner

Full admin seed runs should schedule a seed-scoped closure flow after Professor
rows are written:

```text
roster seed full run
  -> homepage paper ingest
  -> title enrichment / canonical merge
  -> paper abstract + summary_zh + PDF enrichment where available
  -> paper quality promotion
  -> Professor output summary generation
  -> Professor quality re-evaluation
  -> retrieval/vector refresh selection
```

The flow should be idempotent and issue-producing: failed stages must create
pipeline issues or run evidence rather than silently leaving records marked
ready. Sample or limited seed runs may preview data but must not promote final
Professor readiness.

Alternative considered: keep separate manual scripts and document an operator
runbook. That is useful for backfill, but it does not prevent future full seed
runs from producing partial ready data.

### 4. Strengthen Professor ready eligibility

`ready` should require at least:

- a current official identity and current affiliation;
- a 200-300 Chinese `profile_summary` with concrete research terms and no
  obvious term-list repetition;
- a durable Chinese `research_overview_zh` when the official profile contains a
  research overview in any supported language;
- a deduplicated verified paper set when papers are listed on the official
  profile;
- `paper_summary` when the professor has eligible verified papers;
- no active duplicate verified paper links for the same normalized title/year;
- no open critical pipeline issues for the Professor core profile or paper
  chain.

This does not require every linked paper to be fully `ready`; page-only
preprints remain valid paper records. It does require that page-only records are
not duplicated against richer canonical rows and that detail/citation routes
work for every displayed paper.

### 5. Align API, frontend, and chat routes

The Admin Professor detail API should return deduplicated paper rows with
`paper_id`, title, year, quality, canonical source, and available external
links. The React Professor workbench should render paper titles as links to
`/paper/<paper_id>`. Chat answer citations should use the same route, including
hosted URLs such as `http://100.64.0.4:5180/paper/PAPER-...` when the deployment
base URL is configured.

## Risks / Trade-offs

- [Migration scope] Adding section and merge mapping storage touches schema,
  writers, APIs, and tests. Mitigation: use additive migrations and keep the old
  fields/read paths until backfill is verified.
- [LLM translation variance] Translated research overview text can drift.
  Mitigation: use source-hash-based idempotency, preserve source text/hash, and
  validate Chinese output length and non-empty meaning before promotion.
- [External paper provider latency/rate limits] arXiv/OpenAlex/Crossref lookups
  can time out or rate limit. Mitigation: cache title resolution, allow
  page-only records, and file issues without failing the whole seed closure.
- [Over-strict ready gate] Requiring every linked paper to be ready would block
  legitimate preprints. Mitigation: gate deduplication and displayability, while
  keeping paper-level readiness separate.
- [Existing dirty data] Backfill may change many quality statuses. Mitigation:
  require dry-run reports, case-specific acceptance rows, and before/after
  distributions before write mode.

## Migration Plan

1. Add migrations for profile-section storage and paper merge traceability.
2. Backfill Chinese research overview sections from official raw text, using
   LLM translation only when the source overview is non-Chinese.
3. Run a plan-only duplicate paper audit and title-enrichment migration for
   official Professor paper links.
4. Backfill paper summaries/PDF links where providers can resolve them.
5. Generate Professor output summaries from deduplicated eligible links.
6. Re-evaluate Professor quality statuses with before/after distribution
   evidence.
7. Refresh retrieval/vector indexes for changed Professor and Paper records.

Rollback is additive: disable the closure runner, keep old API fallbacks, and
read through the previous `professor` columns while investigating. Merge
mappings should not be physically deleted; rollback should restore link status
only from a recorded dry-run/write report if necessary.

## Open Questions

- Which deployment config should provide the public base URL for chat citations:
  a new admin-console setting, an existing frontend origin, or an environment
  variable?
- Should the first implementation add the general `professor_profile_section`
  table immediately, or temporarily add only the minimum research-overview
  columns and migrate to sections in a later slice?
- What maximum runtime budget should the full seed closure runner enforce per
  professor and per seed?
