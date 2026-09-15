# Design: data-cleaning-batch1

## 1. Layer choice (why the projection, not ingest and not the index)

Three candidate layers were considered; the choice is load-bearing, so it is
argued rather than assumed.

| Layer | Why not (or why yes) |
|---|---|
| **Evidence landing / assertions** | The assertions *are* the evidence record (O1: collected once, kept verbatim). Rewriting ingested values would destroy the source-of-truth and break the decision lineage that references them. Rejected. |
| **Index projection (lookup/vector content)** | This is where the pack is written, and it already carried one local patch (`_PROFESSOR_MISSING_FIELD_FALLBACK` compared before embedding). Cleaning here would have to be repeated for the lookup document, the vector content and the Postgres projection - three places, three chances to drift. Rejected as the primary layer. |
| **Domain projection (chosen)** | `domain_projection._ProjectionContext.project_identity` is the single point where decision-selected source values become typed per-domain projections, and everything downstream (lookup documents, vector embedded content, Postgres projection store, answer composition) derives from those objects. Cleaning once here is the "prove/clean once, earliest layer" rule the repo already applies to proofs. |

Consequence: the previously local index-layer guard for the professor fallback is
deleted (it became unreachable), and the vector embedded content simply omits
fields that are now `None`.

## 2. Placeholder semantics

* A placeholder is **absent**, never a rewritten value: `未找到`, lone `-`,
  `N/A`, `暂无/无/未知/待补充`, and the build's own English fallbacks
  ("Not supplied by the historical source.", "No dedicated summary was supplied
  by the ... source.") all become `None`.
* Values that merely *contain* the token are split by intent, not by convenience:
  * **damage** - the token replaced characters inside an identifier or version
    string (adjacent to `[0-9A-Za-z.]`): the original characters are
    unrecoverable. The value is **withheld** from publication and listed in the
    quarantine side report with its verbatim text. Nothing is guessed: neither a
    repaired identifier nor a partial deletion is published.
  * **legitimate prose** - the token is an ordinary word in a sentence
    (`...或未找到最终目标节点的过程内...`): kept unchanged, counted.
  * **no-information sentence** - the whole value is one short sentence saying
    the information was not found (`根据现有信息，未找到该公司产品的具体应用场景信息。`):
    absent. The shape guard (single sentence, nothing else) keeps informative
    sentences that merely mention the token.
* Required-field consequences: nine projection-model fields that only ever held
  placeholders become optional. The **domain catalog is deliberately not
  changed** - it is content-hash pinned in two places
  (`CATALOG_FILE_SHA256`, `BASE_DOMAIN_CATALOG_FILE_SHA256`) and its
  `requiredness` only feeds `quality_status`, which is computed from the raw
  selections and therefore unchanged.

## 3. Geography derivation

* Rule: only a **province-only** geography (`^…省$`) is derived, and only from
  `registered_address`; the city is the first `…市` token after a leading
  province/autonomous-region prefix is removed.  Anything else - already
  city-level, absent, or unparseable - is untouched (never invented).
* The derived value is a `NamedReference`; its `reference_id` is recomputed with
  the build's own deterministic scheme (`source-reference:{sha256(casefold(name))}`),
  so no dangling province reference is left behind.
* Out of scope: the 1,595 companies with no geography, and the three dirty
  labels (`广东省-珠海`, `苏州市`, `-开曼群岛`) - D0-b.

## 4. Research-direction quarantine

Junk is *withheld from the published projection* and recorded in the side report
(`rule`, `value`, `reference_id` of the source reference) so D1/LLM can review it
and the underlying source reference still resolves. Rules, checked in order:

| Rule | Meaning | run15 count |
|---|---|---|
| `layout_block` | contains a page/table label (`主讲本科课程`, `教育背景`, `工作经历`, `上一篇`, ...) | 154 |
| `too_short` | fewer than 3 characters (`1`) | 126 |
| `dated_dump` | contains a 4-digit year (CV/publication dump) | 65 |
| `sentence_fragment` | contains `。`/`，`/`；` (a sentence, not a noun phrase) | 333 |
| `truncated_tail` | ends with `等`/`等）`/`等)` | 118 |

Order matters: layout first (a layout block is often also long), then the cheap
structural signals. A bare length limit was **rejected during verification**: it
would have quarantined legitimate bilingual directions
(`基于图神经网络的电路表示学习 (GNN-based Circuit Representation Learning)`).

## 5. Gates (anti-recurrence)

`assert_publication_quality(audit_lookup_documents(documents))` runs in
`IndexProjectionBuilder.build`, the last build stage before the pack exists:

| Gate | Threshold | run15 before |
|---|---|---|
| published placeholder values | `== 0` | 15,976 |
| published glue-damaged values | `== 0` | 177 |
| published research-direction junk | `== 0` | 796 |
| company geography city-level ratio | `>= 0.90` | 0.109 |

Fail-closed: `PublicationQualityError` -> `IndexProjectionIntegrityError`, i.e. a
rebuild that would republish this junk cannot produce a pack at all.

## 6. Known gaps / debt

* `debt:` the build does not yet persist the quarantine side report next to the
  release quality report; it is reproduced offline by
  `.agents/runs/data-cleaning-batch1/count_cleaning_batch1.py` from the same pure
  rules (upgrade path: D0-b/D1 wiring, where the release quality report lands).
* No-information sentences that also carry content (`根据现有信息，该公司业务与
  智能家居领域相关，但未找到…`) are kept; tightening that is a policy decision
  for D1.
* Placeholder-aware completeness metrics (`quality_status`) are not changed here.
