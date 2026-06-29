## ADDED Requirements

### Requirement: prof_page_only shells are realtime-resolved against academic APIs

The system SHALL recover `prof_page_only` title-only shells (no abstract) by
running realtime title resolution against OpenAlex / Crossref / Semantic Scholar
/ arXiv / DBLP with the linked professor's name as `author_hint`. A shell that
resolves to a real paper SHALL be enriched with its DOI / abstract / identifiers
and merged into the canonical paper via `paper_merge_alias`; its
`professor_paper_link`s SHALL be re-pointed to the canonical paper. Realtime
resolution SHALL be retried/continued across runs via the
`paper_title_resolution_cache` (idempotent).

#### Scenario: A resolvable shell is recovered
- **GIVEN** a `prof_page_only` shell with a title but no abstract, linked to a
  professor
- **WHEN** realtime resolution runs with `author_hint=<professor name>`
- **AND** the paper is found in OpenAlex/Crossref/S2/arXiv
- **THEN** the shell is enriched with DOI/abstract/identifiers and merged into
  the canonical paper; the professor link is re-pointed to the canonical

#### Scenario: An unresolvable shell stays a bounded residual
- **GIVEN** a shell whose paper is not in any academic API
- **WHEN** realtime resolution runs
- **THEN** it remains `prof_page_only` / not-`ready` (excluded from retrieval);
  no `summary_zh` is fabricated for it

### Requirement: Ingest defaults to realtime resolution

`run_homepage_paper_ingest` SHALL resolve extracted publications in realtime by
default. The `--external-resolution-max-per-professor` cap SHALL be a **safety
valve** (a high limit for bulk fast-mode reruns), NOT the default behavior. When
the cap is `None` (the default), ingest SHALL NOT fall through to `cache_only`
for un-cached titles — it SHALL resolve them in realtime. This prevents the
silent creation of `prof_page_only` shells that are never realtime-resolved.

#### Scenario: Default ingest resolves a new publication
- **GIVEN** `run_homepage_paper_ingest` invoked with the default
  `--external-resolution-max-per-professor` (None)
- **WHEN** it extracts a publication title not already in the resolution cache
- **THEN** it resolves the title in realtime (not `cache_only`); it does not
  synthesize a `prof_page_only` shell merely because the title was un-cached

#### Scenario: Explicit cap still honored for bulk fast-mode
- **GIVEN** `--external-resolution-max-per-professor=5` (bulk fast-mode rerun)
- **WHEN** a professor's 6th publication is reached
- **THEN** that publication MAY be resolved `cache_only` (the cap is a deliberate
  safety valve for bulk reruns)

### Requirement: Recovered papers proceed to ready and become retrievable

A shell recovered to a real paper (with abstract) SHALL proceed through the
unified quality gate to `ready` once it has title + year + venue + authors +
abstract + non-boilerplate `summary_zh`, and SHALL be indexed into Milvus
`paper_chunks` so it is retrievable via the retrieval service.

#### Scenario: A recovered shell becomes retrievable
- **GIVEN** a shell resolved to a real paper with abstract + generated
  `summary_zh`
- **WHEN** the quality gate evaluates it and a Milvus rebackfill runs
- **THEN** its `quality_status` is `ready` and it is retrievable via
  `paper_chunks` (was not retrievable as a shell)

### Requirement: Each recovery stage is gated with a dry-run and yield assertion

Each stage (re-resolution, `summary_zh`, ready+index) SHALL run a read-only
dry-run first that reports the expected yield (rows affected, by-source for
resolution), and SHALL apply only after the dry-run yield is recorded and
reviewed. A pilot (bounded sample) SHALL precede any full-scale stage to confirm
yield and tune rate-limits.

#### Scenario: Re-resolution runs a pilot before the full backfill
- **GIVEN** the 66,578-shell candidate set
- **WHEN** Stage A begins
- **THEN** a bounded pilot (e.g. 500 shells) runs first; its yield (resolved /
  unresolved, by source) is recorded; the full run proceeds only after the pilot
  yield is reviewed
