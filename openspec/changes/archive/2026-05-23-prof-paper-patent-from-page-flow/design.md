# Design: prof-paper-patent-from-page-flow

This document captures the architectural decisions behind the spec
deltas in `specs/paper-patent-from-prof-page/spec.md` and explicitly
maps each decision back to its origin in the Reviews / PRDs / Audit.

## 1. Decision: Spec codifies existing `homepage_ingest.py` as canonical discovery path

**Source**: Theme 7.1 (Professor Review) + Paper Review §3.2 C1.

**Decision**: `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py`
already implements the prof-page → paper canonical path (498 lines).
Theme 7.1's user decision **promotes this path** to be the canonical
discovery source. No new discovery code is greenfielded; this spec
formalizes the existing path's contract.

**Alternative rejected**: rewrite discovery from scratch using a new
"discovery_from_prof_page.py" module. Adds churn and risks regressing
existing tested behavior.

## 2. Decision: hybrid.py refactor is mandatory, not optional

**Source**: Theme 7.1 + Paper Review §3.1 P7 + audit
`paper-prd-source-list-stale-001`.

**Decision**: `hybrid.py` currently supports `discover_*_from_openalex
/ from_crossref / from_semantic_scholar` returning paper candidates
keyed by author. This is incompatible with the locked stance. Refactor
mandates renaming + signature change to `enrich_paper_with_*` taking a
paper canonical row and returning enrichment fields.

**Why mandatory (not allow-both-modes-via-flag)**: leaving discovery
mode active risks regression; a future caller could accidentally use
discovery semantics. Flag-gating doubles the test surface and obscures
the contract.

**Cost**: any current caller of `discover_*_from_hybrid_sources`
breaks. Survey (during this spec's drafting) showed `pipeline.py`
calls `discover_professor_paper_candidates` from
`semantic_scholar.py` directly (not via hybrid wrapper), so the only
caller of `hybrid.py:discover_*` is itself. Refactor is contained.

## 3. Decision: Patents extraction is heuristic-based, not per-school adapter

**Source**: Paper Review §3.1 (no specific number; bridges P9 +
patents discussion).

**Decision**: Use a conservative section-header heuristic (matching
`专利 / Patents / Patent Applications / 发明专利 / 实用新型 / 外观`)
across all schools. Do NOT introduce a new per-school adapter
framework for Patents.

**Why heuristic over adapters**:
- Most prof pages do NOT list patents. Adapter overhead high, value low.
- Patents-section layout is more uniform than Publications (single list,
  no complex citation formatting).
- Per-school adapters can be added incrementally if a specific school's
  patent layout breaks the heuristic.

**Implementation hint**: a new helper
`apps/miroflow-agent/src/data_agents/professor/homepage_patents.py`
parallel to existing `homepage_publications.py` (without the per-school
adapter dispatch).

## 4. Decision: Identity gate verifies same-person, not content

**Source**: Paper Review §1 (meta-principle) + Paper Review §3.1 P9.

**Decision**: Gate's job is to disambiguate "this paper claimed by Prof
A is by Prof A vs by another John Smith". Gate does NOT verify "this
paper is real / contains truthful claims / actually got accepted".

**Why**: the system's product framing is "科创检索 system" — admin /
end-user infer real-world truth from the source URL chain
(`evidence.source_url`); the system's job is to faithfully reproduce
what the source said.

**Implementation hint**: `paper/identity_gate.py` already implements
this; this spec just constrains the Requirement's scope so future
contributors don't accidentally extend it to truth-checking.

## 5. Decision: Page-only attribution → confidence 1.0 unconditional acceptance

**Source**: Paper Review §3.1 P9.

**Decision**: When a paper or patent is sourced solely from the prof's
own page (no enrichment available yet), the identity gate accepts
unconditionally. The page declaration alone is sufficient.

**Why**: the prof maintains their own page; their declaration is
authoritative within the system's "trust pages" framing. Skepticism
toward their own claim would be incoherent with the meta-principle.

**When does the gate become discriminating?** Only when external
enrichment (e.g. OpenAlex) returns multiple candidate authors with
the same name and the page-side claim becomes ambiguous. Then the
gate uses institution + ORCID + co-authors as tiebreakers.

## 6. Decision: Async fire-and-forget enrichment

**Source**: Paper Review §3.1 P10 + design pragmatics.

**Decision**: Enrichment runs asynchronously after discovery /
canonical upsert. The seed-run's `last_run_status` (per
`prof-seed-admin-console` spec) flips to `success` once discovery +
upsert + cross-domain link writes complete, regardless of enrichment
status.

**Why fire-and-forget**:
- Enrichment can take seconds to minutes per paper (rate-limited
  external APIs); blocking discovery completion on enrichment makes
  seed runs unreliable.
- If enrichment fails for an individual paper, that paper stays in
  `needs_enrichment` and gets retried on the next cron pass.

**Cost**: a successful seed run may leave many papers in
`needs_enrichment`. Admin sees seed status `success` but underlying
data quality is partial. This is acceptable per Paper Review §3.1 P15
which retains `partial` and `needs_enrichment` as first-class states.

**Implementation hint**: Phase A uses FastAPI `BackgroundTasks` (same
choice as `prof-seed-admin-console` design.md §3) for enrichment.
Phase B may move to APScheduler / Celery if reliability becomes
issue.

## 7. Decision: Enrichment is field-level fallback, not source-level priority

**Source**: Paper Review §3.1 P10.

**Decision**: Each metadata field (`abstract`, `citation_count`,
`venue`, `authors`, `doi`, `arxiv_id`) has its own source priority:

```
abstract:        OpenAlex → Crossref → S2 → arXiv (first wins)
citation_count:  OpenAlex only (canonical)
venue / year:    OpenAlex (publication_date)
authors:         OpenAlex (ORCID-bearing entries preferred)
doi / arxiv_id:  cross-checked across all sources; mismatch → pipeline_issue
```

**Alternative rejected**: source-level priority where OpenAlex wins
all fields it provides, Crossref fills gaps, etc. Loses precision on
fields where one source is canonical (e.g. citation_count is only
meaningful from OpenAlex).

## 8. Decision: Patent has no external enrichment; only xlsx-merge can enrich

**Source**: Paper Review §3.3 C6 (patent has 2 sources: prof page +
xlsx; no external API).

**Decision**: Patent canonical rows from prof-page discovery do NOT
trigger external enrichment. They stay in `needs_enrichment` until:
(a) the same patent appears in a future xlsx import bringing
authoritative metadata (matched by patent_id), OR (b) a future
prof-page sighting brings additional fields.

**Implication**: `patent_id`-less patents from prof pages may stay
incomplete indefinitely. This is acceptable: the patent is still
discoverable via title in chat / browse interfaces; admin can manually
upgrade to `ready` if confident in the bare title alone.

## 9. Decision: summary_zh is paragraph form, not JSON

**Source**: Paper Review §3.1 P2.

**Decision**: `paper.summary_zh` is a Chinese paragraph 200-400
characters, optionally containing internal four-段 markers. The
Postgres column type stays `text` (no jsonb migration).

**Why paragraph over JSON**:
- Existing `abstract_translator.py` already produces this form.
- Embedding (Milvus) requires text input; paragraph is directly
  consumable.
- JSON form requires post-extraction concatenation for embedding,
  which adds complexity without value.
- The four-段 mental model can be expressed via text markers (e.g.
  paragraph break + `【方法】` prefix).

## 10. Decision: summary_text equals summary_zh; no separate column

**Source**: Paper Review §3.1 P3 + audit
`paper-summary-text-contract-drift-001`.

**Decision**: `summary_text` (the field name in `PaperRecord` Pydantic
contract + Shared-Spec §4.2.1) equals `summary_zh` content. No
separate `paper.summary_text` Postgres column. The admin API alias
fix lives in a separate change `paper-summary-text-contract-fix`.

**Why no column**:
- DRY: same data, two storage locations creates write-time drift risk.
- Embedding consumes `summary_text` from the in-memory `PaperRecord`
  (already wired via `release.py`).

## 11. Decision: Boilerplate detection via LLM judge, not regex

**Source**: Paper Review §3.1 P15 (rejected state) +
Professor Review §3.1 Theme 9.1 (boilerplate detection).

**Decision**: After `summary_zh` generation, an LLM judge evaluates
whether the output is generic / unhelpful boilerplate vs. actually
informative. Failing summaries set `summary_zh=NULL` and
`quality_status=rejected`.

**Why LLM over regex**: boilerplate phrases vary by topic ("本文研究
了 X，提出了 Y，实验证明 Z" patterns); regex catalog would be brittle.
LLM judge can adapt.

**Cost**: extra LLM call per generated summary. Acceptable since
summary generation is itself an LLM call; one more is marginal.

## 12. Decision: Quality status is forward-monotonic from `ready`

**Source**: design pragmatics; not explicitly in Reviews.

**Decision**: Once a paper reaches `quality_status=ready`, it does not
auto-degrade if a later enrichment fails. Only admin (manual override)
or detected contradiction (e.g. duplicate detected) can take it back
to `needs_review`.

**Why forward-monotonic**: chat / browse should not flip status of
already-shown papers based on background enrichment hiccups. Once
`ready`, the paper is exposed to retrieval; stability matters more
than freshness for status.

**Implementation hint**: enrichment failures write `pipeline_issue`
with `stage="paper_attribution"` for admin review, but the paper row
stays `ready`.

## 13. Decision: Cross-domain link writers are idempotent via composite key

**Source**: design pragmatics + Audit `professor_paper_link` table
existing.

**Decision**: `professor_paper_link` and `professor_patent_link`
upserts use composite keys `(paper_id, professor_id)` /
`(patent_id, professor_id)` for idempotency. Re-crawling the same prof
page does not duplicate links.

**Why composite-key**: existing tables already have these as natural
keys (V005a/V005b). Application-level idempotency check before
INSERT, plus DB-level UNIQUE constraint where the schema supports it.

## 14. Decision: Deprecation, not removal, for S2 discovery path

**Source**: design pragmatics (existing tests + scripts depend on it).

**Decision**: `paper.pipeline.run_paper_pipeline` (S2-based discovery)
is marked deprecated with a `DeprecationWarning`, not removed. Removal
deferred to a follow-up `paper-pipeline-cleanup` change after callers
migrate.

**Why deprecate-don't-remove**:
- Existing scripts (`scripts/run_paper_release_e2e.py` etc.) still
  call this path; removing would break testing.
- Removal in a follow-up change creates a clear two-step migration
  history.

## 15. Source traceability matrix

Every Requirement in `spec.md` has a source citation.

| Requirement | Paper Review ref | Professor Review ref | PRD / MSD ref | Audit ref |
|---|---|---|---|---|
| Publications-section extraction | §3.1 P4 / P9 | Theme 7.1 | PRD §3.1 / §5.1 / §5.2 (post-rewrite) | — |
| Patents-section extraction | §3.3 C5 | (Patent decisions in Prof Review §3.1 Theme 5.3) | Patent PRD §4-§5 | — |
| Paper canonical upsert (3-level dedup) | §3.1 P11 | — | PRD §6 | — |
| Patent canonical upsert (patent_id hard) | §3.3 C5 | — | Patent PRD §4 | — |
| Identity gate semantics | §1 + §3.1 P9 | Theme 4 / Theme 5.3 | — | — |
| Async enrichment workflow | §3.1 P10 + §3.2 C2 | Theme 7.1 | MSD §2 | paper-prd-source-list-stale-001 |
| summary_zh generation | §3.1 P2 | — | PRD §4.2 (post-rewrite) | paper-prd-summary-zh-schema-shape-001 |
| Quality status promotion | §3.1 P15 | Theme 9.1 | — | — |
| Cross-domain link writers | (carry-over) | Theme 5.1 / 5.2 / 5.3 | — | — |
| Deprecation of S2 discovery | §3.1 P7 | Theme 7.1 | — | paper-prd-source-list-stale-001 |
| Refactor hybrid.py | §3.1 P7 + §3.1 P10 | Theme 7.1 | MSD §2 | paper-prd-source-list-stale-001 |
