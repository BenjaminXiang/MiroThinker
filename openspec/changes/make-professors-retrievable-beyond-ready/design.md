## Context

Professor data is 94.5% official-sourced (4,819 official vs 279 non-official source pages) and
all 3,409 professors are already embedded in Milvus (`professor_identity_profiles` +
`professor_research_profiles`). Yet 65% (2,221) are NOT `ready`, and the vector-recall filter
(`_filter_ready_only`) drops them → invisible to search. The "limited search" symptom is
dominated by this.

First-principles (2026-07-05): `quality_status` is a publication-completeness contract; using it
as the retrievability gate conflates two concerns. The strict conjunction gate also over-flags
legitimate multi-value data (83% of `field_contradiction` is same-domain dept+personal emails —
not a real contradiction). The data is high-quality; the gate's strictness is the mismatch.

## Goals / Non-Goals

**Goals:** admit real identified professors (resolved, named, institutioned) to vector recall
regardless of publication-completeness; preserve `low_confidence` exclusion + the `ready`
publication contract + ranking.

**Non-Goals:** change professor embedding (already all embedded); change the `quality_status`
enum or `ready` criteria; address the contact-multi-value `field_contradiction` (separate
canonicalization follow-up); fix the classifier phrasing brittleness (root A, separate).

## Decisions

### D1: Filter-only change (not embedding)
All professors are already embedded; the gate is the retrieval filter. So the fix is one
conditional in `_filter_ready_only` (professor branch) — not an embedding/contract change like
Lever 0. Smallest possible blast radius for the biggest recall gain (+2,176 retrievable).

### D2: Exclude only `low_confidence`
`low_confidence` = non-person-name / profile-blob / reader-artifact / missing-official-source
(these are genuinely unreliable entities). `needs_review`/`needs_enrichment` are real entities
with minor/derived-field gaps → admitted. This keeps the worst data out while unblocking the bulk.

### D3: `quality_status` as ranking signal, not gate
With more candidates admitted, ranking matters. `ready` profiles (better embeddings, full
summaries) rerank naturally higher; no explicit boost needed for v1 (verify via breadth probe +
precision). If precision regresses, add a `quality_status` rank boost as a follow-up.

## Risks / Trade-offs

- **[Precision regression from less-polished profiles]** → mitigated by excluding only
  `low_confidence`; rerank; precision-oracle guard (to be labeled per the benchmark-completion-spec).
  Acceptance = breadth up (topic queries return more relevant professors) WITHOUT precision regression.
- **[Ranking dilution]** → more candidates may push the best `ready` prof lower if a `needs_review`
  prof matches the query strongly; rerank is the guardrail. Watch via the breadth probe.
- **[Multi-value contact `field_contradiction` still blocks `ready`]** → orthogonal; those profs
  are now still RETRIEVABLE (needs_review admitted) even if not `ready`, so retrievability no
  longer waits on the contact canonicalization. The canonicalization becomes a display-quality
  concern, not a recall blocker.

## Migration Plan

No migration. Deploy: code change (filter) + tests; restart backend (loads new filter); the
already-embedded professors become retrievable immediately. Rollback: revert the filter branch
(restores ready-only admission exactly).
