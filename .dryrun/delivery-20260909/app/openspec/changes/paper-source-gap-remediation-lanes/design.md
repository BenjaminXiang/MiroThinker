## Context

The previous `professor-dataset-candidate-generation` change completed the
candidate-generation and Paper cleanup pass needed to make existing Professor
and Paper data more usable. It also proved that the remaining Paper gaps have a
different shape: after live title resolution and DeepSeek summary backfill,
there are still 19,800 active Paper rows missing `summary_zh` and 19,884
missing `abstract_clean`.

The key observation is that broad mixed backfills are inefficient and hard to
reason about. Mixed DOI/PDF/summary workers wrote useful summaries, but they
also spent most runtime on PDF/full-text fetch failures and skipped rows with
no usable abstract. The remaining work must therefore be split into lanes with
separate evidence, checkpoints, and acceptance criteria.

## Goals / Non-Goals

**Goals:**

- Classify remaining active Paper gaps into explicit remediation lanes.
- Run existing-source-text summary generation as a fast LLM-backed lane.
- Run DOI/OpenAlex/Crossref/arXiv metadata enrichment separately from summary
  generation.
- Run PDF/full-text acquisition as a bounded, resumable slow lane with failure
  accounting.
- Keep `prof_page_only` rows on conservative parser/title/source repair until
  usable source text exists.
- Record residual buckets so unresolved rows remain visible and explainable.
- Preserve the professor-page seed boundary and avoid author-name paper-list
  discovery.

**Non-Goals:**

- Do not fabricate abstracts or summaries for rows without usable source text.
- Do not merge this work into the completed
  `professor-dataset-candidate-generation` change.
- Do not change Agentic RAG answer routing or frontend display behavior in this
  change.
- Do not require every remaining Paper row to be closed in one run; this change
  defines lane contracts and safe execution flow.

## Decisions

### 1. Audit-first lane classification

Every run starts with a read-only source-gap audit that assigns each active
Paper row to one primary next-action lane. This makes acceptance measurable:
the system should show how many rows can be summarized now, how many need
identifier metadata, how many need full-text acquisition, and how many remain
unsafe or source-gapped.

Alternative considered: continue running one broad script over all missing
summary rows. That hides source-quality problems behind skipped rows, slow PDF
fetches, and partial pipeline runs.

### 2. Existing abstracts are a fast path

Rows with `abstract_clean`, `paper_full_text.abstract`, or
`paper_full_text.intro` already have source-grounded inputs. They should go
directly to LLM summary generation and self-check, without DOI enrichment or
PDF fetching.

Alternative considered: always enrich metadata before summarizing. That wastes
provider time on rows whose source text is already sufficient.

### 3. Source acquisition is separated from summary writes

DOI metadata enrichment and PDF/full-text fetching should update source fields
and full-text evidence first. Summary generation should consume those fields in
a later fast-path run. This separation makes slow source failures visible and
keeps LLM generation throughput high.

Alternative considered: fetch PDF/full-text inside the summary loop. The latest
run showed this causes long-running workers, timeout-heavy logs, and poor
operator visibility.

### 4. Prof-page-only rows stay conservative

`prof_page_only` rows are only page-declared seeds. They need source repair
through title resolver evidence, parser cleanup, official links, or full-text
evidence before summaries are written. The system should not make those rows
look complete by asking an LLM to invent content from a title alone.

Alternative considered: summarize from title and venue alone. That would make
the UI look less empty but would undermine trust and evidence traceability.

### 5. Partial runs are first-class evidence

Operators may stop slow workers when a better lane is identified. The run must
be closed as `partial` with checkpoint counts and interruption reason. This is
important because stale `running` pipeline rows otherwise make later audits
ambiguous.

Alternative considered: leave terminated workers as operational noise. That
makes data provenance and cleanup status harder to reconstruct.

## Risks / Trade-offs

- [Residual gap remains large] Splitting lanes will not immediately clear all
  19,800 missing summaries. Mitigation: lane reports show exactly which rows
  need source acquisition or manual review.
- [More artifacts] Separate lanes produce more evidence files. Mitigation:
  aggregate worker summaries and source-gap audits provide compact rollups.
- [Provider limits] DOI/full-text sources can return 403, timeout, or content
  type failures. Mitigation: slow lane caps, retries, and reason buckets.
- [LLM variance] Summary generation may reject or produce weak output.
  Mitigation: keep rejection counts, self-check evidence, and no direct writes
  without source text.

## Migration Plan

1. Add the verification contract and baseline source-gap audit.
2. Implement or extend a Paper source-gap audit report.
3. Harden the summary fast path and report shape for existing-source-text rows.
4. Split identifier metadata enrichment and full-text acquisition into
   resumable source-acquisition lanes.
5. Re-run summary fast path on newly acquired source text.
6. Re-audit residual buckets and record source-specific next actions.

Rollback is operational: each lane writes with its own run id and evidence.
Stopping a lane should mark its pipeline run as `partial`; already written
source fields and summaries remain traceable by run id.

## Open Questions

- Should the first implementation slice prioritize the `262` remaining
  existing-source-text rows or the larger `prof_page_only` parser/title bucket?
- What per-provider concurrency and timeout caps should be used for the next
  full-text slow lane?
