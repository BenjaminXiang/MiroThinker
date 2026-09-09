## Context

The completed `professor-dataset-quality-closure` change provides bucketed
audits, dry-run evidence gates, write-mode batch orchestration, post-write
verification, and residual-risk filing. It intentionally does not fabricate
missing candidate fields. The current real database still has four blocker
classes that require generated or planned candidates before those existing
writers can repair data:

- short ready `profile_summary` values;
- missing durable Chinese `research_overview` profile sections;
- missing Professor `paper_summary` values despite verified Paper links;
- duplicate verified Professor-Paper title/year groups.

The candidate layer must sit between the bucket audit and the existing dry-run
evidence file consumed by write mode. It must be bounded, reproducible,
source-grounded, and safe to rerun.

## Goals / Non-Goals

**Goals:**

- Produce candidate values and merge plans for the four existing closure lanes.
- Keep every generated candidate tied to official Professor evidence, verified
  Professor-seeded Paper links, source text hashes, and deterministic selection
  hashes.
- Support bounded dry-run generation without mutating Professor, Paper,
  profile-section, merge-alias, vector, or quality-status rows.
- Assess candidate quality before write mode: Chinese profile-summary length,
  Chinese research overview, source-hash presence, paper-summary provenance, and
  duplicate-merge evidence become recorded quality signals. Usable weak
  candidates remain visible as `needs_review` candidates instead of broad
  validation failures.
- Record provider failures, validation failures, skipped rows, and residual-risk
  reasons in the dry-run report.
- Make the output directly consumable by the existing
  `run_dataset_closure_write_batch` path.

**Non-Goals:**

- Do not execute broad real write-mode remediation in this change without a
  separate operator step and matching dry-run evidence.
- Do not use external literature providers to create offline Professor paper
  lists from name-only searches.
- Do not infer hidden company/startup roles from news or Company data as part
  of Professor core readiness.
- Do not change Agentic RAG classification, multi-source recall, or runtime
  answer generation.
- Do not lower quality thresholds to make remaining blockers appear resolved.

## Decisions

### 1. Candidate generation is a dry-run enrichment step

Candidate generation should enrich bucket rows with `candidate_*` fields and
merge-plan evidence, then emit a dry-run report. Existing write mode remains
responsible for persistence and post-write verification.

Alternative considered: write candidates immediately as they are generated. That
would blur the dry-run/write boundary and make failed LLM output harder to
audit.

### 2. Use structured candidate models per lane

Each lane should use a typed candidate model:

- profile summary candidate: Chinese text, source ids, source hash, validation
  rules, generation method;
- research overview candidate: Chinese content, source language, source text
  hash, source span, generation method;
- paper summary candidate: Chinese summary, verified Paper ids used, duplicate
  exclusion evidence;
- duplicate merge candidate: canonical Paper id, old Paper ids, evidence type,
  confidence, rejection reason when unsafe.

Alternative considered: put arbitrary candidate fields into `row.evidence`.
That is flexible but makes validation and tests too weak.

### 3. LLM-first generation with deterministic evidence anchors

The generator should use the configured real LLM provider for bounded Chinese
summary synthesis, English-to-Chinese translation, and self-check evidence when
provider credentials are available in the development environment. Deterministic
official-text extraction and templated synthesis remain acceptable fallbacks,
but they must still emit the same candidate evidence fields.

Alternative considered: keep LLM generation disabled by default and only allow
deterministic candidates. The user rejected that posture for this development
phase because candidate generation needs to exercise real provider behavior.

### 4. Duplicate merge planning separates candidate reporting from auto-write

Automatic merge candidates should prefer exact DOI or arXiv matches. Title/year
similarity alone should not be enough for automatic writing unless
author/venue/source evidence raises the match above the configured safe
threshold. Ambiguous groups should still be emitted as reviewable candidates
with weak confidence and review-before-write recommendations so operators can
inspect the proposed canonical row and evidence chain.

Alternative considered: merge every title/year duplicate with an enriched row.
That can corrupt Professor-Paper links when common titles or same-year variants
refer to different works.

### 5. Keep Professor seed boundary explicit

For paper summaries and duplicate merge planning, the seed is the Professor's
official page and its verified Professor-Paper links. External provider metadata
may enrich those Paper records, but name-only provider discovery cannot create a
new Professor paper list.

Alternative considered: use OpenAlex/Crossref/Semantic Scholar author-name
searches to fill paper_summary gaps. The user explicitly rejected making that a
Professor core requirement because many public sources are incomplete or
ambiguous.

### 6. Parallel cleaning is bounded dry-run generation, not direct writes

Large existing dirty datasets should use bounded parallel candidate dry-run to
exercise DeepSeek-backed cleanup at useful throughput. Parallelism belongs in
candidate generation, not write mode. The output must remain the same evidence
JSON that serial generation produces, so the existing write-mode evidence gate
and post-write verification remain load-bearing.

Workers must not share the main `psycopg` connection. The safe implementation is
to keep bucket loading on the main connection, then process eligible bucket rows
with a worker connection factory. Each row task opens its own connection or uses
an isolated connection supplied by the factory, generates candidate/rejection
evidence, closes the connection, and returns a result tagged with the original
bucket row index. The aggregator then restores deterministic bucket order before
building lane summaries.

DeepSeek pressure should be controlled independently from row worker count. The
candidate CLI should expose worker concurrency and provider concurrency/interval
controls, and the provider client should reuse the existing file-lock based
provider limiter already used by company enrichment paths.

### 7. Review recommendations are write gates

Candidate evidence may include useful but weak candidates. Those rows should
remain visible to operators, but write mode must not treat them as approved
data. Duplicate Paper merge write mode should persist only candidates whose
candidate evidence says `candidate_status=ready` and
`write_recommendation=auto_write_candidate`. Review-only merge candidates
should become unresolved write issues without inserting `paper_merge_alias`
rows.

Alternative considered: let write mode attempt every automatically eligible
bucket row and rely on dry-run operators to filter the evidence file. That is
too fragile for full-dataset cleanup because a single unfiltered evidence file
can contain thousands of safe candidates plus hundreds of review-only rows.

### 8. Live scholarly resolver provider configuration is explicit

The live title resolver path should proceed with OpenAlex as the primary
metadata source and Crossref as the contactable fallback, while Semantic Scholar
approval remains pending. Crossref must use configurable contact metadata
(`CROSSREF_MAILTO` and optional `CROSSREF_USER_AGENT`) instead of the previous
placeholder email. Semantic Scholar title search should be independently
disableable for large OpenAlex/Crossref-primary backfills, but the Semantic
Scholar request helpers should still send `SEMANTIC_SCHOLAR_API_KEY` or
`S2_API_KEY` when those credentials become available.

Alternative considered: keep Semantic Scholar in every live title resolver run
and rely on temporary circuits for rate limits. That wastes quota and retries on
large batches when the user has already chosen OpenAlex as the current primary
source while Semantic Scholar approval is pending.

### 9. DOI quality is a resolver admission gate

The cleaning layer should treat DOI strings as candidate identifiers, not as
trusted routing input. Obvious DOI pollution, such as nested DOI prefixes,
separator-joined DOI and URL tails, should be classified before external
provider calls. Bad DOI-only rows become residual source-quality evidence; rows
with a bad DOI plus a stronger arXiv or OpenAlex id may still use the stronger
identifier for metadata enrichment.

The same admission gate applies to title-enrichment shortcuts that build a
resolved Paper from existing row identifiers. A polluted DOI must not be
promoted as a high-confidence `doi_lookup` result before the title resolver has
a chance to use the cleaned title and stronger enabled providers.

Alternative considered: send all DOI-like strings to OpenAlex/Crossref and rely
on provider misses. That wastes external resolver quota and hides source
pollution as generic provider failure instead of a repairable data-quality
bucket.

### 10. Research overview source text is noisy by default

Official Professor profile text may contain a research-overview label followed
by a mixture of research directions, teaching assignments, recruitment notes,
contact details, publication headings, links, awards, or page navigation. The
candidate layer should not treat a Chinese source span as automatically clean
merely because it is Chinese. When source text shows page-noise patterns, the
research-overview LLM provider should act as a source-grounded cleaner: extract
only research directions, compress them into concise Chinese, and preserve the
original source span and source hash in evidence.

Automatic writing remains gated by the candidate quality evidence. If LLM
cleaning still returns URLs, contact details, teaching, recruitment, publication
headings, awards, or navigation text, the candidate must stay
`needs_review` or be rejected. This avoids turning the cleaner into a
fabrication or publication bypass.

Alternative considered: keep deterministic Chinese extraction and rely on
post-write cleanup. The full-run sample showed this lets low-quality sections
enter storage before being removed later, so the cleaner belongs before the
write gate.

## Risks / Trade-offs

- [LLM variance] Generated summaries or translations may be shallow or
  inconsistent. Mitigation: emit candidate status, quality flags, self-check
  evidence, source confidence, bounded batches, and provider-failure reporting.
- [Hallucinated profile summaries] LLM output may add unsupported facts.
  Mitigation: prompt only with official facts/source text and reject candidates
  that introduce unsupported names, institutions, or topics when guards can
  detect them.
- [False duplicate merges] Over-aggressive merge candidates can corrupt Paper
  identity. Mitigation: require DOI/arXiv or stronger author/venue/source
  evidence for auto-write, and downgrade ambiguous fuzzy groups to
  review-before-write candidates.
- [Cost and runtime] Thousands of blockers can make generation expensive.
  Mitigation: lane filters, bucket limits, batch sizes, checkpointable evidence,
  provider failure counts, provider rate limits, bounded worker concurrency,
  and rerunnable selection hashes.
- [Stale residual-risk issues] Existing residual-risk rows may remain after
  successful remediation. Mitigation: final post-write verification and later
  issue-resolution tooling should close or supersede resolved residual risks.

## Migration Plan

1. Add verification contract and RED tests for candidate-generation report
   shape, validation failures, provider failures, and boundary preservation.
2. Add lane-specific candidate models and pure validation helpers.
3. Add relaxed-gate metadata fields to every candidate and report sample.
4. Implement deterministic official-source extraction/synthesis where useful.
5. Add LLM-backed bounded generation for profile summaries and English research
   overview translation behind injectable provider interfaces, with real
   provider usage enabled when configured.
6. Add Professor paper-summary generation from deduplicated verified links.
7. Add duplicate Paper canonical merge candidate planning and manual-review
   weak candidates.
8. Extend the closure CLI to emit candidate-enriched dry-run evidence and write
   it to an operator-provided path.
9. Run bounded real dry-runs against `miroflow_real`, record evidence, then run
   write mode only when the operator accepts the candidate evidence.
10. Add bounded parallel candidate dry-run for the same evidence shape, using
    independent worker connections and provider rate limits before scaling
    DeepSeek cleaning beyond small samples.
11. Enforce candidate review recommendations in write mode before running any
    real duplicate Paper merge batch from full candidate evidence.

Rollback is operational: candidate-generation dry-run files can be discarded;
write-mode remediation remains guarded by the existing run id, dry-run evidence,
rollback evidence, and post-write verification paths.

## Open Questions

- What batch size should operators use for the first real write-mode run after
  candidate generation: 20, 50, or 100?
