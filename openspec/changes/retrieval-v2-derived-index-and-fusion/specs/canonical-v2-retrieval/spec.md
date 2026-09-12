# Spec delta: canonical-v2-retrieval (retrieval-v2-derived-index-and-fusion)

## ADDED Requirements

### Requirement: Indexed lexical recall with word segmentation

The serving read path SHALL retrieve lexical candidates from a persisted
inverted index (SQLite FTS5) built from the release's lookup documents, with
documents and queries segmented by one shared Chinese word-segmentation
function (jieba with the derived entity-name-form user dictionary). The
lexical lane SHALL rank candidates with field-tiered BM25 (display names
above tags above body text) and SHALL treat a multi-term query as a ranked
sample (token OR), never as an AND filter. Candidate evidence items,
claim bindings, lineage hashes and citation shapes SHALL be produced by the
existing binding path; the index SHALL NOT change record lineage.

#### Scenario: question-style entity query hits the indexed lane

- **WHEN** the user asks 「大疆创新主要做什么」 and the release lookup carries
  the entity's documents
- **THEN** the lexical lane returns the entity's documents from the FTS5
  index within the lane budget (P95 < 150 ms)
- **AND** the resulting evidence items carry the same lineage fields as the
  substring lane produced before this change

#### Scenario: index artifact is bound to the release

- **WHEN** the serving process loads a derived lexical artifact whose pack
  sha256, release id or schema version differs from the active release bundle
- **THEN** the loader refuses the artifact and the read path falls back to
  the previous lexical behaviour
- **AND** the fallback is logged (the lane result contract has no limitation
  channel; the serving lane trace still records the lane it ran)

#### Scenario: derived artifact never mutates the sealed pack

- **WHEN** the index build runs against a sealed serving pack
- **THEN** the artifact and its manifest are written outside the pack root
- **AND** the pack's files and manifest hashes are byte-identical before and
  after the build

### Requirement: Structured facet filters

The serving read path SHALL expose the release's typed fields (domain,
industry, tech tags, geography, founded year, quality tier) as facet
predicates consumable by structured constraints, and SHALL derive the
geography facet from the entity's registered place rather than from its
display name.

#### Scenario: city-scoped narrowing uses the typed field

- **WHEN** a narrowing turn asks 「上述企业有哪些是深圳的企业」 and a
  recalled company's registered address is in 深圳 while its display name
  carries no city word
- **THEN** the company satisfies the geography constraint through the facet
  derived from its registered address
- **AND** companies whose registered address is elsewhere still fail it

### Requirement: Rank fusion across retrieval channels

The serving read path SHALL combine per-channel candidate lists with
reciprocal-rank fusion (k = 60) instead of positional interleaving, SHALL
record the per-channel ranks used in the fusion receipt, and SHALL break
score ties deterministically by canonical identity.

#### Scenario: channel quality influences order

- **WHEN** two candidates are produced by different channels and their
  per-channel ranks differ
- **THEN** their fused order follows the reciprocal-rank sum
- **AND** repeating the same turn reproduces the same order

### Requirement: Retrieval freshness and page-cache signals

The serving read path SHALL cache fetched web page text by URL with a
same-day TTL and SHALL expose a data as-of signal derived from the release
snapshot and the web evidence timestamps.

#### Scenario: cached page avoids a refetch

- **WHEN** the same URL is fetched again within the cache day
- **THEN** the fetch is served from the cache and the web lane trace records
  the hit
