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
  provider failure counts, and rerunnable selection hashes.
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

Rollback is operational: candidate-generation dry-run files can be discarded;
write-mode remediation remains guarded by the existing run id, dry-run evidence,
rollback evidence, and post-write verification paths.

## Open Questions

- What batch size should operators use for the first real write-mode run after
  candidate generation: 20, 50, or 100?
