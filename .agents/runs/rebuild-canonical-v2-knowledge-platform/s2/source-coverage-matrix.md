# S2 Source-to-PRD Coverage Matrix

## Evidence checkpoint

- Inventory: `source-inventory.json`
- Inventory SHA-256: `83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09`
- Git baseline: `a58184cee8d616cbcfc58c942f1b07790fc6ffdb`
- Captured: `2026-07-11T07:11:30Z`
- Recovery query proof: both checkpoint databases reported `transaction_read_only=on` in the same
  sessions used for counts.

Status means source-evidence availability, not Canonical V2 acceptance:

- **covered** — one or more readable source families contain the necessary raw facts at useful scale;
- **partial** — some facts/objects survive, but scope, fields, identity, provenance, or time is incomplete;
- **recollectable** — approved source adapters can reacquire the facts, but S2 made no provider call;
- **missing** — no inventoried local evidence or approved deterministic derivation currently supplies it.

## Substrate truth

The two recovery checkpoint databases are V042 containers with 42 public tables, but their public
Professor, Company, Paper, Patent, relationship, full-text, and lineage tables all contain zero
rows. They are not a usable legacy canonical database. Their only material rows are the `salvage`
schema: 99,437 distinct Papers, 101,158 distinct Professor-Paper links covering 2,826 Professor IDs
and 97,285 Paper IDs, plus 20,773 field errors and 10 recovery metadata rows.

The original Milvus file is 1,298,632,704 bytes with SHA-256
`43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`. No verified copy exists, so
S2 did not open a client or inspect collections. The 97 historical Milvus-like files are family-
hashed only; their canonical parent release and parity are unproven.

## Four PRD domains

| Domain | Inclusion anchor and required effect | Inventoried evidence | Status | Known ceiling / gap | Future owner |
|---|---|---|---|---|---|
| Professor | Approved roster/seed Professors; identity, institution/department/title, research profile, contact/metrics, source trace | 3,274-row legacy Professor JSONL; 825-row merged V3 JSONL; 11,604-file Professor fetch-cache family; 790 + 3,360 metric backfill rows; 351 legacy SQLite snapshots; raw release JSONL/PDF families | partial + recollectable | No recovered public Professor rows; overlapping generations need identity resolution; source pages/provenance vary; not every approved roster is proven present | S4 landing, S5 identity/fusion, S6 domain inclusion |
| Company | Approved skeleton batches and validated incremental Shenzhen Companies; identity, profile, technology/business, team, financing/products/scenarios, source trace | `docs/企业总表.xlsx` has 6,528 data rows; legacy published snapshot has 1,037 Companies; eight admin-upload workbooks; Company release JSONL; eight committed knowledge-field rows | covered raw, partial canonical | Duplicated uploads and historical projection policies; field-level evidence and conflict history not normalized; currentness requires Web/recollection | S4 landing, S5 fusion, S6 typed Company |
| Paper | Papers anchored to included Professors/approved sources; identifiers, title/authors/year/venue/abstract/summary/citations, existence separate from attribution | Salvage has 99,437 distinct Papers; 26,185 OpenAlex caches; Paper release families; one exact-identifier supplement; 2,657 raw PDFs; legacy snapshot has 574 Papers | covered identity/title at scale, partial content | 20,773 lost fields: 13,621 abstracts, 7,080 summaries, 37 venues, 33 author displays, 2 clean titles; salvage has no canonical decisions; full text/provenance is heterogeneous | S4 landing, S5 identity/fusion, S6 Paper inclusion, later enrichment |
| Patent | Approved export/import records; number/title/applicant/inventor/dates/type/IPC/abstract, source trace | Admin patent workbook contains 11,408 data rows with title/abstract/applicant/publication number/date/effect text; admin JSONL family; legacy published snapshot has 1,931 Patents; exact-ID supplement | covered core import, partial PRD fields | Primary 11,408-row workbook lacks Patent type and inventor/IPC columns; legacy and current-import populations differ; identity/provenance must be rebuilt | S4 landing, S5 identity/fusion, S6 Patent inclusion, targeted recollection |

## Typed sub-objects and business facts

| Family | PRD effect | Evidence | Status / limitation |
|---|---|---|---|
| Professor affiliation/education/work history | Show current and historical organization/role with time/evidence | V3/legacy Professor JSONL includes institution, department, title, education, positions, work experience; fetch caches preserve pages | partial — current vs historical role and validity intervals need decisions |
| Professor research/projects/awards/metrics | Search and assess expertise with sourced support | V3 JSONL, metric backfills, profile caches, release JSONL | partial — source freshness and per-field assertions are inconsistent |
| Company team/financing/business/product/scenario | Filter and compare Company capability/business maturity | Company workbook/admin uploads, release JSONL, committed knowledge fields | covered raw / partial semantics — typed events, evidence anchors, and conflict retention absent |
| Paper identifiers/authors/content/metrics | Exact lookup, semantic recall, authorship and evidence-based summary | Salvage, OpenAlex caches, raw PDFs, release JSONL, exact-ID supplement | partial — lost TOAST fields and mixed source generations set a real enrichment ceiling |
| Patent applicant/inventor/classification/content | Exact/filter/semantic lookup and IP relationship traversal | 11,408-row workbook and release JSONL | partial — applicant/core content strong; type/inventor/IPC gaps prevent complete structured filtering |
| Temporal/source/quality state | Explain when, from where, conflicts, and usable retrieval paths | Recovery xmin/ctid metadata, V3 `field_provenance`/URLs, artifact hashes, historical statuses | partial — no unified assertion/decision/policy version or accepted current projection |

## Relationship families

The relationship goal is an extensible typed catalog. Counts below describe surviving evidence, not
accepted canonical edges.

| Relationship family | Representative typed relations | Evidence | Status | Gap / risk |
|---|---|---|---|---|
| Identity and lifecycle | source-record→entity, alias-of, merged-into, split-from, supersedes | historical IDs, round-7-17 decisions (763 rows), released-object snapshots, Paper merge artifacts in legacy family | partial | No unified reversible identity graph; old decisions may embody incorrect merges |
| Organization and role | Professor→institution/department, Professor→Company role, person→Company team role | Professor JSONL/profile pages; two explicit Professor-Company role rows; Company workbook/team data | weak partial | Professor-Company evidence is tiny; time/role direction and entity matching need rebuild |
| Scholarly output | Professor→Paper authorship/listing, Paper→author, Paper→venue/topic/reference | 101,158 salvaged Professor-Paper links, 97,285 linked Papers, Paper author/content caches | strong partial | 2,826 Professor source IDs are not canonical Professor identities; authorship state/evidence conflicts remain |
| Intellectual property | Professor→Patent inventor/claim, Company→Patent applicant/owner, Patent→inventor/applicant | Patent applicants in 11,408-row workbook; Professor JSONL `patent_ids`; historical release JSONL | partial | Recovered public link tables are empty; inventor and Professor-Patent evidence is sparse; applicant-name joins are not canonical proof |
| Company business/product/event | Company→product/scenario/financing/news/team/capability | Company source workbook, eight upload workbooks, release JSONL, knowledge-field supplement | covered raw | Typed event time, product evidence, and duplicate Company resolution must be reconstructed |
| Taxonomy/topic/geography | entity→research topic, industry, IPC, geography, institution | research directions, fields of study, Company tags/workbook fields, addresses | partial | Patent IPC/type missing in primary source; taxonomy versions and cross-domain normalization absent |
| Evidence and lineage | assertion→artifact/page/record, decision→assertion/run/policy | forensic hashes, source URLs/provenance in V3, recovery xmin/ctid, release artifacts | partial | Legacy artifacts lack one common field-level lineage contract; source priority/conflicts not reproducible yet |
| Derived release-scoped | similarity, ranking, trend, representative result | historical Milvus-like files and evaluation artifacts | unavailable as accepted relation | No verified parent release/parity; never promote these as source-grounded canonical facts |
| Conversation/session | displayed set, referent, selected next relation | committed multi-turn fixtures and PRD | scenario-covered only | Not canonical knowledge; runtime session behavior is rebuilt in S9 |

## Retrieval and answer path reach

| Path/effect | Local evidence potential | Current measurable state | S2 conclusion |
|---|---|---|---|
| Exact identifiers/names/titles | Strong for Paper IDs/titles, Patent publication numbers, Company names, Professor names | Current recovery public DB has zero objects; current service cannot be replayed from it | Data exists for rebuild; current reach is unavailable, not zero product capability |
| Structured filters | Company and Professor fields are broad; Patent type/IPC and temporal normalization incomplete | No current canonical projection | Partial source support; thresholds must be domain/path-specific |
| Semantic recall | Large text/cache/PDF families exist | Original Milvus cannot be opened and no verified copy exists | Index baseline unavailable; full versioned rebuild required |
| Relationship traversal | Professor-Paper evidence is substantial; other cross-domain relations are sparse | Recovered public link tables are empty | Professor-Paper is recoverable; Professor-Company, Professor-Patent, Company-Patent require fusion/recollection |
| Cross-domain composition | Some endpoints/facts survive across source families | No accepted canonical identity joins | Cannot truthfully benchmark until S5/S6; wrong-identity joins remain hard invariant zero |
| Universal Web augmentation | Source adapters/config exist; S2 makes no live call | No current accepted invocation/provenance baseline | Freeze 100% invocation requirement for information requests; measure in S8 real-provider acceptance |
| Grounded answer/citation | User-confirmed workbook answers/key points provide case-specific reference ground truth; other legacy outputs also exist | No stable current evidence/claim trace over recovered substrate | Workbook reference gold cannot be generalized into a template; unreviewed legacy prose is not gold; S9 must build and evaluate claim-evidence mapping |
| Multi-turn exploration | PRD and committed scenario fixtures exist | Current runtime baseline may be replayed deterministically only where no data/provider is needed | Freeze scenario behavior now; data-grounded multi-turn acceptance waits for accepted release |

## Source priority for later build

1. Forensic manifests/dump and original artifact hashes establish lineage, never canonical truth by
   themselves.
2. Approved roster/export/workbook sources establish domain inclusion candidates.
3. Official pages, academic identifiers/APIs, and primary Company/Patent sources provide assertions.
4. Historical projections/caches supply recoverable assertions but never override stronger sources
   without a recorded decision.
5. Live Web and recollection are freshness/coverage inputs routed through landing and fusion; online
   search never writes directly to active canonical or indexes.

## Binding gaps before Canonical V2 acceptance

- Professor, Company, and Patent have no forensic row-level salvage; their reconstruction depends on
  historical artifacts plus approved recollection.
- Paper salvage is broad but has 20,773 known field failures and cannot restore lost values.
- Only Professor-Paper has large-scale surviving relationship evidence; other cross-domain relation
  families need identity-aware fusion and targeted collection.
- No verified Milvus copy or active release manifest exists. Index content/parity is unavailable and
  must be rebuilt, not inferred from file presence.
- Current retrieval/answer/Web/latency/cost behavior cannot be rerun end-to-end on the recovered
  substrate. S2 must label stored metrics legacy and missing dimensions unavailable.

## Six north-star requirement effects

| Confirmed effect | What available evidence supports | What remains required |
|---|---|---|
| Knowledge coverage | All four domain families have local evidence; Professor-Paper is strongly represented; Company/Patent source exports are substantial | Reconstruct inclusion-qualified objects and the broader typed relationship catalog; recollect missing Professor/Company/Patent relations and lost Paper content |
| Trusted data | Artifact/recovery hashes, source URLs, field provenance fragments, recovery row locators, and competing historical generations survive | Build append-only assertions, reversible identity, source priority, conflict retention, observation/publication time, and quality/decision state |
| Retrievability | Exact identifiers, structured fields, text caches/PDFs, and Professor-Paper edges exist as rebuild inputs | Publish accepted exact/lexical/vector/filter/relation projections; rebuild Milvus and measure every domain/path without treating incomplete enrichment as a blanket gate |
| Generation fidelity | Workbook answers/key points are user-confirmed case-specific reference ground truth; source-bearing historical fields can seed additional scenarios | Build claim-evidence mapping, distinguish local/Web/model judgment, disclose conflict/limitations, and prohibit unsupported material claims |
| Continuous operations | Historical runs, caches, uploads, recovery metadata, and source families show recollection/replay inputs | Implement versioned landing, incremental collection, enrichment/review, release publication, full reconciliation, rollback, and gap closure |
| Scenario acceptance | Workbook, PRDs, committed classifier/retrieval/multi-turn fixtures, and reviewed badcases are available | Freeze separate regression/challenge corpora and multidimensional thresholds; workbook contributes 25 seed queries with case-specific reference gold, not a general answer template |
