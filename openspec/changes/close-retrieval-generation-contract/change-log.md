# Change Log: close-retrieval-generation-contract

## 2026-07-13 — Frozen / superseded-by-V2

- The user confirmed that the active refactor moves the implementation mainline to
  `rebuild-canonical-v2-knowledge-platform`.
- Froze this Epic at 5/92 tasks and superseded it as an implementation authority. Slice A remains
  stopped at its recorded non-viable substrate gate; Slices B-F remain unstarted.
- Preserve its contracts, evaluators, immutable manifests, RED evidence, and reusable requirements
  as Canonical V2 mapping inputs. No further production implementation or archive is authorized
  until the mapping is complete and reviewed.

## 2026-07-10 — Proposed / Slice A Ready

- Created the behavior-affecting Epic after the retrieval/generation gap audit and grilling session.
- Locked the canonical atomic evidence, structured-claim, typed-outcome, additive migration,
  Type1-Type4, two-hop provenance, embedding-ledger, fixed-oracle, semantic-gate, latency, and
  rollback decisions.
- Split execution into sequential slices A-F; only gate-only Slice A is Ready.
- Added independently gated B0/B1/B2, C0/C1, and D0/D1 internal checkpoints with separate scope,
  required evidence, hashes, review, and rollback.
- Locked every retained legacy `ChatResponse` field plus byte-stable versioned result-manifest,
  response-integrity, and cursor algorithms.
- Corrected the three predecessor retrieval changes to Candidate pending canonical end-to-end
  evidence.
- Preserved `make-partial-papers-retrievable` as an Accepted behavior dependency and moved its
  explicitly unmeasured D3 parity responsibility to Slice F's full reconciler.
- Amended the active SIGS publication change so its unique ingest capability remains normally
  archivable but its conflicting exact-title/title-only and ready-first topic rules are blocked on
  C0/D1 compatibility.
- No production code, data, index, rollout, or external repository state changed.

## 2026-07-10 — Slice A In Progress / substrate stop

- Added evaluator-only `paper-retrieval-case-manifest-v1`, allowlisted canonical observation
  scoring, conjunctive hard-gate aggregation, Type4 five-slot micro-P@5, classifier field scoring,
  and sealed-holdout receipt/kappa validation with test-first coverage.
- Added a read-only DB/Milvus snapshot and two-level paper/chunk parity preflight with full
  query-visible DB, ordered chunk/paper/content, schema, and physical Milvus Lite target hashes
  captured before and after inspection.
- Captured stable snapshot `paper-snapshot-4afb567921be3dab`; the index is non-viable for the frozen
  Type4 evaluation substrate: 16,777 expected papers missing, 13,438 unexpected, 36,835 expected
  chunks missing, 17,648 unexpected, 3,012 content-stale, and every 46,035 actual chunk lacks a
  verifiable model/chunker/index/write tuple.
- Triggered the Slice A Task 1.5 stop condition. Slice A remains In Progress, B-F remain blocked,
  and an explicit sequencing/substrate decision is required before further implementation.
- No production retrieval/generation/API/UI/schema behavior, canonical data, or Milvus content was
  changed; no commit or push was performed.
