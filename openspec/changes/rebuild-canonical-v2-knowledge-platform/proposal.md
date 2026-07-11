## Why

The pre-launch V042 data and retrieval architecture cannot express the confirmed product outcomes
without carrying fragmented provenance, identity, relationship, eligibility, indexing, and chat
orchestration behavior across many physical tables and callers. The destructive test incident also
demonstrated that rebuilding the knowledge base must be isolated, reproducible, release-versioned,
and verifiable from evidence rather than treated as an in-place restoration of the old database.

This is a behavior-affecting change. It establishes the owning contracts for the Canonical V2
knowledge platform, evidence-first query orchestration, grounded progressive answers, and safe
release/index publication before any production-code or recovery-candidate write begins.

## What Changes

- **BREAKING** Replace the V042-centered canonical storage contract with a clean, typed Canonical V2
  knowledge platform. Pre-launch table shapes, internal IDs, migrations, handlers, and payloads are
  not compatibility requirements; all in-repository consumers migrate together.
- Introduce an immutable recovery/source evidence landing contract for forensic salvage, historical
  artifacts, and new collection responses.
- Introduce retained source assertions, reversible canonical identity resolution, field/relation
  fusion, minimal temporal semantics, an extensible typed relationship catalog, and domain-specific
  inclusion policies.
- Separate canonical inclusion from path-specific eligibility. Ordinary incompleteness is a soft
  quality signal; only named hard invariants exclude an object from a path.
- Introduce candidate releases that keep canonical data, published projections, and vector indexes
  on one accepted version with deterministic parity and rollback evidence.
- Replace fixed-handler chat routing with validated LLM-assisted retrieval plans, protected-slot
  multi-view query rewrites, recall-oriented multi-lane retrieval, universal Web augmentation for
  all information-retrieval requests, late evidence-aware reranking, and bounded sufficiency retry.
- Introduce claim-to-evidence grounded answers, evidence-based assessments, progressive multi-turn
  relationship exploration, and validated next-hop suggestions.
- Introduce a query/acceptance feedback loop that turns no-result, insufficient-evidence,
  Web-dependent, relation, user-feedback, and benchmark failures into traceable knowledge gaps.
- Rebuild Milvus from the accepted Canonical V2 release into versioned indexes; allow later
  versioned incremental refresh while retaining scheduled/full reconciliation.
- Supersede overlapping pre-launch implementation assumptions in active retrieval/Web changes;
  those changes must be reconciled with this Epic before their behavior is used as a dependency.

## Capabilities

### New Capabilities

- `recovery-evidence-landing`: Immutable, content-addressed, replayable evidence inputs and chain of
  custody for forensic recovery, historical sources, and recollection.
- `canonical-v2-knowledge`: Typed domain objects, retained source assertions, reversible identity,
  canonical value selection, temporal semantics, relationships, inclusion, and path eligibility.
- `canonical-v2-release`: Candidate construction, acceptance, publication, canonical/index parity,
  rollback, and release-scoped Milvus projection behavior.
- `evidence-first-query-orchestration`: A-G behavior semantics, protected query rewriting, validated
  LLM planning, structured/lexical/vector/relation/Web recall, fusion, rerank, and bounded retry.
- `grounded-progressive-answer`: Claim-evidence mapping, source-lane disclosure, evidence-based
  assessment, structured LLM contracts, progressive relationship exploration, and safe degradation.
- `knowledge-gap-feedback`: Structured query/acceptance gaps that drive reviewed recollection,
  enrichment, relationship repair, and retrieval improvement without online direct-to-canonical
  writes.

### Modified Capabilities

- `paper-identity-status`: Replace old-table/global-status retrieval effects with reversible
  identity decisions and path-specific eligibility; terminal wrong identities remain excluded.
- `professor-retrieval-index-split`: Preserve intent-separated Professor retrieval semantics while
  replacing fixed collection-name/payload compatibility with release-versioned index projections
  and traceable alias promotion.

## Impact

- New isolated Postgres database and schema baseline for Canonical V2; V042 remains a recovery input,
  not the target schema.
- New deep modules and interfaces for evidence landing, candidate building, knowledge read/query,
  answer orchestration, and release publication.
- Replacement or broad refactor of current canonical writers, retrieval, chat/session orchestration,
  admin data access, Milvus builders, migrations, and their implementation-coupled tests.
- External adapters for LLM, Web search, embeddings, reranking, Postgres, Milvus, and source files;
  deterministic/local test adapters at each real seam.
- New reviewed acceptance corpus and multidimensional gates. Existing PRD minima remain lower bounds;
  missing numeric thresholds are frozen after the authorized read-only baseline.
- Original `pgtest` and original Milvus remain frozen. This change does not authorize production-like
  cutover or writes outside the isolated recovery candidate environment.
