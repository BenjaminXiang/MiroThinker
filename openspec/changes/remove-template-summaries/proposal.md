# Proposal: remove-template-summaries

Human doc: `docs/plans/2026-10-26-systematic-completion-gates.md` §3.6.

## Why

**2,149 of 3,958 professor summaries (54.3%) contain a padding sentence** that
was never evidence: `该教授在深圳科创领域有持续贡献。` (and the companion
`研究成果具有重要学术价值。`). It exists because
`pipeline_v2._build_fallback_summary` padded short summaries to 200 characters
by appending the same sentence in a loop. The text then entered the research
vector and every claim, crowding out real fields.

None of the affected records is *only* filler — every summary keeps at least a
factual clause — so removing the padding never empties a claim.

## What Changes

1. The fallback summariser stops padding; a short factual summary stays short
   (the 200-character contract remains a validator for LLM output, not a target
   for fallbacks).
2. Claim rendering drops the known padding sentences from a professor summary
   before the repetition collapse, so existing pack data stops showing them
   immediately, without a rebuild.

## Impact

- Claim text changes for 2,149 professors (shorter, factual); retrieval vectors
  are unchanged until the next pack rebuild.
- No schema, API or pack change.

## Out of scope

- Rebuilding the pack so the vectors also lose the filler (20 h; separate
  decision).
- Rewriting the affected summaries at the source.
