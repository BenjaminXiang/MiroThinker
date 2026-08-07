# Verification Contract: fix-paper-topic-query-classification

## Status

Candidate historical implementation; not end-to-end Accepted.

## Local invariant

Paper noun plus topic/search intent routes B/paper without stealing bare English exact titles or
professor/company-anchored routes. Local deterministic tests may prove only this routing seam.

## Promotion gate

The controlling RED/GREEN contract is `close-retrieval-generation-contract`: Slice A fixes the
oracle, Slice B proves canonical grounding/citation, and Slice D proves Type4 paper-level quality,
semantics, regression, and latency. No response-wide token or unblinded candidate inspection can
promote this change.

## Archive

After linked acceptance, archive only with `--skip-specs`; the umbrella owns canonical behavior.
