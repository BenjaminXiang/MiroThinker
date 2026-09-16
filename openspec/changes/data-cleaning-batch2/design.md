# Design: data-cleaning-batch2

Follows `data-cleaning-batch1` design: the cleaning point stays
`domain_projection._ProjectionContext.project_identity`, source assertions stay
verbatim, gates stay fail-closed, counts are reproduced offline.

## 1. Venue merging - why the map is computed, not pinned

The published label is the **most frequent variant of its group**, and "most
frequent" is a property of the whole pack, not of one paper.  Two options:

| option | verdict |
|---|---|
| pinned mapping table generated offline (the repo's recorded-decision pattern) | works, but the table goes stale between rebuilds and a new spelling silently escapes the merge |
| **computed per build** from the selections the projection already receives | chosen: same rule, always current, no new artifact, deterministic |

Key: `venue_group_key` casefolds, drops parentheticals and a trailing year,
normalises `&`, strips punctuation and the stopwords
`proceedings/proc/the/of/on/in/for/and`, then collapses whitespace - so
`Proceedings of the AAAI Conference on Artificial Intelligence` and
`AAAI Conference on Artificial Intelligence (AAAI)` are one group, and
`Journal of Geophysical Research: Solid Earth` matches its punctuation-free
twin.  Winner: most occurrences, ties broken by the lexicographically smallest
label (deterministic, order-independent).  Labels with no group-mate are still
rewritten to their own canonical spelling (parenthetical/year stripped) - a
no-op for the vast majority.

Boundary: a venue that is *not* a variant of another label is untouched.  The
replay reports 153 merged groups / 326 labels / 2,684 rows (the assessment's
weaker key found 121 / 244 / 1,979; the difference is the stopword and
`Proceedings of` handling plus post-canonicalisation grouping).

## 2. Edge de-duplication

One attribution link per (professor, paper) pair.  The retained historical link
wins because the smallest id sorts first (`PROF-PAPER-LINK-*` <
`derived-professor-paper-link:*` < `p4-professor-paper-link:*`), which keeps the
authority order: retained evidence beats synthesized salvage.  Endpoint lineage
was attached to the professor/paper identities *before* this point, so dropping
the duplicate link loses no source-record lineage.

Guard: `relationship_projection._assert_unique_relationship_edges` refuses to
publish two edges with the same (type, source, target).  The build-time rule
removes today's duplicates; the assertion keeps a future link family from
reintroducing them unnoticed.

Not in this slice: the count of dropped ids is not persisted into the build
report (the report runs at the index layer, downstream of the link assembly);
the offline counter reports it (31 pairs) and the assertion names any future
duplicate pair in its failure message.

## 3. Geography repair (extends batch-1 rule 3)

| shape | rule | run15 |
|---|---|---|
| leading/trailing `-`/`–` separator | strip it (`-开曼群岛` -> `开曼群岛`) | 1 |
| `省-城市` where the city lost its `市` | append `市` only for a city in the declared prefecture lexicon (`广东省-珠海` -> `广东省-珠海市`) | 1 |
| city-only label | recover the province from the company's own registered address by matching a provincial-level name (`苏州市` + `中国（江苏）…` -> `江苏省-苏州市`) | 1 |
| anything else | untouched, counted (`geography_unparsed`) | 2 |

The lexicon exists because guessing is worse than leaving a value alone:
`广东省-南沙` (a district) must not become `广东省-南沙市`, so only known
prefecture cities may be suffixed.

## 4. Applicant rows: the decision and its evidence

Measured on run15 (12,565 rows):

| shape | rows | decision |
|---|---|---|
| `canonical_company_id` set, `company_name` set, `name` set | 7,614 | unchanged; binding must stay inside the released company set (gate) |
| no id, no `company_name`, **`name` set** | 4,951 | **kept**: the name is real evidence and the null id is the unbound marker |
| no name at all | 0 | gate refuses to publish one |
| binding outside the released company set | 0 | gate refuses to publish one |

Why not "remove the empty rows": the rows are not empty.  The assessment's
`company_name = null` finding is about the *resolved company name* field; every
one of the 4,951 rows carries the applicant's own legal name, which is exactly
what D1's company binding consumes.  Removing them would delete 4,951 names to
tidy a count.

Why keeping is safe for the serving path: `_direct_patent_applicant_scan`
selects applicants by `canonical_company_id == displayed_company_id`, so unbound
rows are skipped by construction - the field that marks them unbound is the same
field the reader filters on.  The row's `name` is what
`knowledge_serving_isolated` renders (`申请人：…`), so unbound applicants stay
visible by name.

## 5. Dead declarations: decision table

Measured by the new build metric: a field is a *dead declaration* when it is
present on every document of its domain and empty on all of them.  run15: **49**
(company 10, professor 14, patent 8, paper 17).  The assessment's 46 did not
count `paper.enrichment_sources`, `paper.funders`, `paper.summaries`.

Retiring a declaration is **not** a cleaning rule: the domain catalog is
content-hash pinned twice (`CATALOG_CONTENT_SHA256`/`CATALOG_FILE_SHA256` in
`domain_catalog.py`, `BASE_DOMAIN_CATALOG_FILE_SHA256` in
`internal_reference_catalog.py`), the typed projection models forbid extra keys,
and `knowledge_read_isolated._read_public_projection` requires a published
document to be exactly `projection.model_dump_json()`.  A deletion must
therefore revise catalog + models + every reader together - a deliberate
release-identity change, escalated rather than done unilaterally.

| field | decision | fill path / reason |
|---|---|---|
| company `credit_code` | keep | join key; reader exists in `knowledge_read*`; needs an authoritative registry source (D1) |
| company `registered_capital` | retire-pending | no reader, no source batch |
| company `patent_count` | retire-pending | no reader; patent counts are computed by direct scan (G3) |
| company `products` | keep | read by `internal_reference_projection` + `knowledge_read_isolated`; product-capture lane |
| company `business_scenarios` | retire-pending | no reader, no source batch (subobject container) |
| company `capabilities` | retire-pending | no reader, no source batch (subobject container) |
| company `financing_events` | retire-pending | no reader, no source batch (subobject container) |
| company `latest_public_updates` | retire-pending | no reader, no source batch (subobject container) |
| company `personnel_education` | keep | reader + P4 workbook personnel lane |
| company `personnel_work_experience` | keep | reader + P4 workbook personnel lane |
| professor `phone` | retire-pending | no reader, no source batch |
| professor `office` | retire-pending | no reader, no source batch |
| professor `patent_ids` | keep | professor↔patent lane (D2) reads it in the build |
| professor `projects` | keep | read by the index embedded content (research view) |
| professor `awards` | retire-pending | no reader, no source batch (subobject container) |
| professor `company_roles` | keep | professor↔company lane (G6) |
| professor `education_history` | keep | reader + professor history lane |
| professor `work_history` | keep | reader + professor history lane |
| professor `affiliation_history` | keep | reader + professor history lane |
| professor `metric_snapshots` | retire-pending | no reader, no source batch (subobject container) |
| professor `contacts` | retire-pending | no reader, no source batch (subobject container) |
| professor `aliases` | keep | alias closure (C1/R15) is an active workstream; the field is the published side of it |
| professor `lifecycle_state` | retire-pending | no reader, no source batch |
| professor `manual_override` | retire-pending | no reader, no source batch |
| paper `title_zh` | keep | read by the reader/index; translation lane (17,894 `summary_zh` exist) |
| paper `reference_count` | retire-pending | no reader, no source batch |
| paper `professor_ids` | retire-pending | no reader; professor attribution travels as relationships |
| paper `fields_of_study` | keep | read by index embedded content; enrichment lane (D1) |
| paper `keywords` | keep | read by index embedded content; enrichment lane (D1) |
| paper `tldr` | keep | read by index embedded content; summary lane |
| paper `identifiers` | keep | read by `knowledge_read*` for identity display |
| paper `publications` | retire-pending | no reader, no source batch (subobject container) |
| paper `references` | keep | read by `internal_reference_projection`/index; full-text lane |
| paper `full_texts` | retire-pending | no reader, no source batch (subobject container) |
| paper `license` | retire-pending | no reader, no source batch |
| paper `oa_status` | retire-pending | no reader, no source batch |
| paper `pdf_path` | keep | written/read by the paper ingest lane |
| paper `publication_date` | keep | read by build + reader; the field is empty only because `year` carries the date today |
| paper `enrichment_sources` | retire-pending | provenance echo with no reader |
| paper `funders` | retire-pending | no reader, no source batch (subobject container) |
| paper `summaries` | retire-pending | no reader, no source batch (subobject container) |
| patent `title_en` | keep | read by build/reader/index |
| patent `inventors` | keep | inventor lane (data-blocked, D2) - the reader lists them |
| patent `company_ids` | keep | applicant binding lane writes it |
| patent `professor_ids` | retire-pending | no reader; patent↔professor travels as relationships |
| patent `ipc_codes` | keep | read by index embedded content; IPC extraction lane |
| patent `grant_date` | keep | read by the build's patent lane |
| patent `technical_summaries` | retire-pending | no reader, no source batch (subobject container) |
| patent `milestones` | retire-pending | no reader, no source batch (subobject container) |

Totals: **22 retire-pending, 27 keep** (49 measured).  The 22 are now *visible*:
every build reports them, so a new dead declaration cannot appear unnoticed even
before the catalog revision lands.

## 6. Build quality report

Written by `_IsolatedIndexMaterializer` after the readback verification (a
failed build leaves no report) at
`<index root>/publication-quality-report.json`:

```json
{"schema_version": "canonical-v2-publication-quality-report-v1",
 "release_id": "...",
 "publication_audit": {"documents": ..., "placeholder_hits": 0, ...,
                       "applicant": {...}, "declared_never_filled_fields": {...}},
 "quarantine_by_rule": {...}, "quarantine_records": [...]}
```

Why that location: the serving pack's manifest binds an *exact* file registry
(`serving_pack_loader` raises when `manifest.files` differs), so the report must
not enter the pack; the index root is the build's own output and is copied
selectively (index files + marker), so the report stays outside every content
hash and outside release verification.

Why it is safe to re-derive the quarantine: the report runs the same pure
functions over the same source selections the projection consumed, so the report
cannot disagree with the pack (the alternative - a new field on the projection
result contract - would churn a pinned contract for a reporting concern).

## 7. Gates added in this slice

| gate | threshold | run15 before |
|---|---|---|
| applicant rows published without any name | `== 0` | 0 |
| applicant bindings outside the released company set | `== 0` | 0 |
| duplicate (type, source, target) relationship edges | `== 0` | 31 |

The dead-declaration metric is reported, not gated: the 22 known declarations
are an accepted, documented state until the catalog revision.

## 8. Out of scope

* 1,595 companies with no geography at all, company-summary backfill, the 46/49
  declarations' actual population - collection work (D1).
* Retiring catalog declarations (needs the deliberate catalog revision above).
* Persisting the dropped duplicate-link ids into the build report.
