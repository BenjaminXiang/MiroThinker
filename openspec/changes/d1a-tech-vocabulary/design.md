# Design: d1a-tech-vocabulary

## 1. Where the mapping happens

D0-a established the seam: cleaning runs once inside
`domain_projection._ProjectionContext.project_identity`, where decision-selected
source values become typed domain projections. Lookup documents, the vector
embedded content and the Postgres projection all read that one result, while
source assertions stay verbatim. D1-a hooks the same seam, after cleaning:

```text
source assertions (verbatim)
  -> canonical decisions (current selections)
  -> project_identity(): typed projection values
       -> clean_projected_values()      (D0-a)
       -> apply_vocabulary()            (D1-a)   <-- new
  -> lookup document / vector content / postgres projection
```

Nothing else changes: the tag fields keep their names and their
`{reference_id, name}` shape, so no catalog revision, no migration and no reader
change are needed. Rewriting the *value* is what makes the category retrievable;
introducing a *new field* would have required a release-identity change and is
rejected for this slice (D0-b reached the same conclusion for dead declarations).

## 2. The artifact pair: recorded bundle vs packaged vocabulary

| artifact | content | role |
|---|---|---|
| `recorded-vocabulary-decision-bundle.json` | every provider transcript (raw bytes + sha256), provider, model, prompt version, the exact batch composition of each call, the prompt templates' sha256 | audit trail; the only place the LLM is called |
| `catalogs/technical-vocabulary-v1.json` | the controlled concepts and the `value -> concepts` map | build input; loaded by the projection |

The packaged artifact is **the bundle's replay output**, and a test asserts they
are equal: `replay_vocabulary_from_bundle(bundle) == packaged vocabulary`. So the
build never needs the provider, and the artifact can be inspected, diffed and
reviewed as plain JSON.

Staleness policy (the trade-off D0-b documented for venue labels, decided the
other way here): a controlled vocabulary cannot be derived by rule, so it is a
deliberate, content-hash pinned revision - `VOCABULARY_ARTIFACT_CONTENT_SHA256`
in `tech_vocabulary.py` - and a vocabulary change is therefore a code change.
A value that later batches introduce is not guessed: it stays published verbatim,
is counted as `unmapped`, and lowers the reported coverage, which the gate turns
into a visible signal instead of silent drift.

## 3. What a concept is

```text
VocabularyConcept
  concept_id              stable slug, e.g. "robotics.delivery-robot"
  canonical_name          published label, e.g. "配送机器人"
  definition              one sentence, the induction intent
  acceptable_evidence_forms  short strings, e.g. "自述研发/生产该产品",
                             "主营产品描述中为该产品类别"
  kind                    "technology" (from tech_tags) | "industry" (from industry)
```

Concepts are **coarse by construction**: the mapping target is a category a user
would query, not a paraphrase of the marketing phrase. Two sources of
consistency:

1. the induction call fixes the concept list once for the whole value space;
2. every mapping call sees the *same* frozen list as its only allowed target, so
   a value can only map into the vocabulary or into `unmapped`.

## 4. Recorded-decision replay contract

`canonical-v2-recorded-vocabulary-decision-bundle-v1`:

```json
{
  "schema_version": "...",
  "provider": "deepseek",
  "model": "deepseek-v4-pro",
  "prompt_version": "d1a-tech-vocabulary-prompts-v1",
  "output_schema_version": "d1a-tech-vocabulary-output-v1",
  "prompts": {"<call kind>": {"sha256": "...", "text": "..."}},
  "induction_chunks": [["<value>", "..."]],
  "calls": [
    {
      "call_id": "map:tech_tags:0007",
      "kind": "value_mapping",
      "input_value_ids": ["tech_tags:PCBA设计生产商", "..."],
      "input_sha256": "...",
      "raw_output": "<exact provider text>",
      "output_sha256": "..."
    }
  ],
  "call_count": 63,
  "content_sha256": "..."
}
```

### Induction is chunked, and why

One call over the whole sample invites an unbounded taxonomy: the model answered
**500** and then **1,337** concepts - both truncated mid-line, both rejected by the
parser - although the prompt stated a cap of 240 and later of 100 per call.  The
recorded run therefore splits the deterministic sample (600 values) into **12
chunks of 50** (`induction_batches`), each asking for at most 100 concepts; the
transcripts stay bounded and all 12 recorded on the first attempt of the chunked
run.  The measured line count is 465 across chunks.

The union is merged by a deterministic rule (`merge_induced_concepts`):

| shape | rule | measured |
|---|---|---|
| same canonical name in several chunks | one concept, smallest id wins | 11 names |
| same id, different names | the id keeps the name that sorts first; the count is published as `induction_id_collisions` | 4 ids (智能硬件/智能硬件物联网方案, 智能家居/智能家居硬件, 炒菜机器人/烹饪机器人, 智慧零售方案/智能零售系统) |

The four colliding ids are all near-synonyms and the number is an audit field, not
a hidden correction: a reviewer sees 447 concepts, 11 name merges and 4 id
collisions in the artifact.

### Fail-closed axes

Replay is fail-closed on every axis that could silently change the mapping:

| failure | detection |
|---|---|
| a call is missing / extra for the recorded value set | the batch composition is recomputed from the source values and compared with `input_value_ids` per call id (mapping) and with `induction_chunks` (induction) |
| a transcript was edited | `output_sha256` recomputed |
| a concept in a response is not in the vocabulary | referential check, `VocabularyIntegrityError` |
| a response is malformed JSONL | parse error, no fallback (this is what caught the truncated taxonomies and the CSV header of the first attempt) |
| the bundle itself was edited | `content_sha256` recomputed over the canonical payload |
| prompt drifted from the recording | `prompts[kind].sha256` compared with the shipped template, re-rendered from a fixed probe input for both templates |

The output format is **JSON Lines, one record per input value**, not a JSON
array, so a truncated or partially-invalid response is detected per line instead
of silently dropping the tail. Parsing is total: a line whose value is not part
of the call's input set, a duplicate value, a concept id outside the vocabulary,
or a missing value all raise.

## 5. Mapping semantics

- A value maps to 0..n concepts. `[]` means *undecidable*, not *no category*: the
  value is recorded in the unmapped list **and stays published verbatim**.
- The published tag list is the union of the concepts of that company's tags,
  sorted, de-duplicated, so two marketing phrases that mean the same thing stop
  being two tags (the "PCB: 11 rows over 3 industry labels" problem).
- `industry_tags` is mapped through the same table as `industry`; because it is a
  pure duplicate axis with no reader (measured again on run15: 5,480 equal / 0
  differing), the mapping keeps it equal by construction. Retiring the
  declaration is a catalog revision and is escalated, not done here.
- Raw values stay traceable: the vocabulary artifact is the complete
  `raw value -> concepts` table, content-hash pinned, and it is the input the
  projection replayed, so any published concept resolves back to every raw value
  that produced it. Lineage to the decision that selected the original value is
  unchanged (`field_lineage`).

## 6. Gate and report

`build_vocabulary_quality_section` produces the section that is attached to the
build's `publication-quality-report.json` under the key `vocabulary`:

```json
"vocabulary": {
  "artifact_content_sha256": "...",
  "provider/model/prompt_version/bundle_content_sha256/llm_calls": "...",
  "source_values": {"tech_tags": 4945, "industry": 41},
  "concepts": {"technology": N, "industry": M},
  "mapped_values": {...}, "unmapped_values": {...},
  "coverage": {"tech_tags": 0.xx, "industry": 0.xx},
  "unmapped_examples": [...],
  "tags_per_company": {"before": 1.0, "after": x},
  "companies_without_concepts": n
}
```

`assert_vocabulary_quality` is fail-closed on the vocabulary's own contract:
coverage below `MINIMUM_MAPPED_VALUE_COVERAGE` (0.90), a published concept
reference that is not in the artifact, or a published tag value that is neither a
concept name nor a recorded unmapped value. It deliberately does **not** fail on
the collection gap (tags per company, companies with no tags) - that is a
collection defect reported to D1-b/D3.

`attach_vocabulary_section(payload, section)` merges the section into an existing
report payload, creating it when absent, and is idempotent. It is the integration
point with D0-b's `compose_publication_quality_report` (one call, both branches
touch the same function); the wiring is verified on a report fixture in this
slice because D0-b lives on `chore/data-cleaning-batch1` and is not in this
branch's lineage.

## 7. Cost and batching

The prompt `value_mapping` sends a fixed concept list plus up to N raw values per
call, and asks for one compact JSONL line per value:

```text
{"v":"<raw value verbatim>","c":["concept.id", ...]}
```

Induction is `len(induction_chunks)` calls (12 x 50 sampled values); mapping is
`ceil(distinct_values / batch)` calls per field (100 values per call). The call
count is reported verbatim in the bundle (`call_count`), in
`out/induction-telemetry.json` and in the quality section - it is an audit number,
not an estimate.

Measured for this recording: **63 recorded calls** (12 induction + 50 `tech_tags`
mapping + 1 `industry` mapping) plus **3 failed attempts** from the pre-fix
recording rounds that were re-asked and are *not* in the bundle; the telemetry
file accounts for both numbers, because a quota report that hides the retries
would not be honest.

## 8. Alternatives rejected

| option | verdict |
|---|---|
| deterministic suffix stripping ("研发商/服务商") as the vocabulary | rejected: it maps 4,945 values to ~3,000 still-uncontrolled phrases and answers no category query; kept only as an input feature |
| embed the raw tags and rely on the vector lane alone | rejected: the assessment shows the tag text is the lane that failed; a controlled label is also what makes the operator able to read and audit a category |
| add a new `tech_concepts` field | rejected for this slice: catalog + typed models + readers must change together (release-identity change); rewriting the existing field reaches the same retrieval surface |
| ask the LLM at build time | rejected by R21 guard #2 - a rebuild must replay, not re-ask |
| treat undecidable values as removable | rejected: the assessment's own rule is "do not guess"; unmapped values stay published and counted |
