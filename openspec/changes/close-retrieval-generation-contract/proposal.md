# Proposal: close-retrieval-generation-contract

> **Behavior-affecting Epic:** YES — chat evidence assembly, answer generation, citation
> semantics, paper retrieval behavior, public response fields, and paper index lifecycle change.
> The behavior contracts are owned by the new capabilities `chat-grounded-answer-contract`,
> `paper-retrieval-quality`, and `paper-index-parity`. This proposal records the decisions from
> the 2026-07-10 retrieval/generation grilling session.

## Why

`c0f3db2` improved paper routing and candidate delivery, but the production and evaluation chain
is not closed: professor-paper candidates can enter `/api/chat` payloads without entering the LLM
evidence, answer markers can resolve to different sources in the API and UI, and the recall scorer
can pass from query echo while comparing different Type4 oracles. The three paper-retrievability
changes therefore return to **Candidate** until a fixed, ID-grounded retrieval → citation → answer
contract proves the behavior end to end.

## What Changes

- **Gate first:** freeze an ID-grounded manifest and data/index snapshot identity, archive the
  current RED cases, and prohibit scoring against the echoed request query or mutable substring
  tokens. No production behavior changes in Slice A.
- **Canonical grounded-answer contract:** introduce one ordered, atomic evidence list as the only
  source for prompts, validation, API citations, and UI numbering. LLM output becomes structured
  claims with typed evidence/result-set/lane supports; the service validates and renders the answer.
- **Explicit outcomes and compatibility:** distinguish `success`, `partial_result`, `no_result`,
  `retrieval_error`, and `synthesis_error`. Add canonical response fields while temporarily deriving
  legacy `answer_text` and `citations`; shadow-run behind a rollback flag before cutover.
- **Paper Type1/Type2 closure:** make natural exact-title variants resolve the same paper as the bare
  title; make professor-paper queries obey list, topic, time, and representative-work predicates,
  paginate the complete verified set, and preserve paper evidence through synthesis.
- **Paper Type4 quality:** parse topic/year/category constraints; fuse dense and local lexical/FTS
  candidates; aggregate by `paper_id` before rerank; admit `partial+rich` with a visible quality
  penalty; keep local and Web evidence in separate provenance lanes.
- **Paper Type3 traversal:** implement company → professor → paper as a two-hop, provenance-bearing
  plan. Verified professor-company roles are strong relations; resolved company-team professor
  links are labeled secondary relations; professor-paper links remain verified-only.
- **Index and data lifecycle:** keep canonical data plus the versioned predicate as sole eligibility
  authority; persist non-authoritative per-paper observations and exact chunk manifests with
  content/chunker/model/index/write versions, success, and failure. Backfill lanes operate only on
  active derived worklists; review is separate and rejected/merged records are excluded.
- **Path-specific acceptance:** Type1/Type2/Q004/Q017 use hard ID and citation gates; Type4 uses
  frozen-topic `Precision@5 >= 85%`; Type3 uses exact eligible path/tier and citation gates;
  generated claims have zero tolerance for unsupported facts; existing passing cases must not
  regress. Retrieval p95 remains <=6s and synthesis-on p95 <=15s.
- **Status correction:** the three existing changes
  `fix-paper-topic-query-classification`, `wire-professor-paper-list-traversal`, and
  `fix-professor-ambiguity-intro-rule` remain visible as historical implementation records but are
  linked to this Epic and marked Candidate until their end-to-end scenarios pass.
- **Behavior dependency:** retain `make-partial-papers-retrievable` as Accepted for its implemented
  pure partial-rich eligibility/snippet/admission rules. Its unmeasured D3 task is superseded by
  Slice F's full paper/chunk reconciliation and is not historical parity evidence.
- **Conflict dependency:** preserve `sigs-official-publications-to-paper-domain` as an in-verification
  ingest capability, but supersede its exact-title title-only exclusion and ready-first topic
  fallback; block normal archive until its pending task passes umbrella C0/D1.

Out of scope:

- New data domains or a rewrite of non-paper domain retrieval ranking.
- Streaming, retry policy, or long-form research-report generation.
- Treating Web results as local paper records or allowing Web evidence to satisfy local recall.
- Running bulk enrichment, migrations, index writes, or production cutover during the proposal
  phase.
- Removing legacy chat response fields before the additive migration and frontend cutover are
  accepted.

## Capabilities

### New Capabilities

- `chat-grounded-answer-contract`: canonical atomic evidence, structured claims, citation identity,
  typed outcomes, additive API migration, frontend rendering, shadow execution, and rollback for
  grounded chat answers across A-G routes.
- `paper-retrieval-quality`: end-to-end Type1/Type2/Type3/Type4 paper retrieval semantics,
  structured filters, paper-level hybrid ranking, partial-rich policy, local/Web provenance lanes,
  and path-specific quality gates.
- `paper-index-parity`: canonical-derived active worklists, non-authoritative per-paper audit ledger,
  exact chunk/version manifests, two-level Postgres-Milvus parity, resumable lanes, and terminal
  exclusion.

### Modified Capabilities

<!-- none — `agentic-rag-retrieval` exists only as in-flight change deltas, not as an archived
canonical spec. This Epic creates narrower canonical capabilities and links the in-flight changes
instead of pretending a missing base spec is already settled. -->

## Impact

- **Backend/API:** `apps/admin-console/backend/api/chat.py`, chat response models, synthesis and
  evidence assembly, error/degradation semantics, and compatibility/shadow flags.
- **Frontend/feedback:** React `Chat.tsx`, the deployed `backend/static/chat.html` route (or an
  explicit tested redirect/deprecation), API types/rendering, and integrity-checked minimized
  feedback/admin metadata; citation labels use canonical evidence order. No raw canonical response
  review surface is added without a separate auth change.
- **Retrieval:** `apps/miroflow-agent/src/data_agents/service/retrieval.py`, paper candidate
  aggregation, structured filters, local lexical fallback, and two-hop related-object orchestration.
- **Storage:** reversible IDs/sort-tuples-only chat result-set persistence in Slice B, normalized
  paper-subject/lexical-index substrate in Slice D, and embedding-ledger/chunk-manifest state in
  Slice F; no historical migration is rewritten and categories are not inferred from title text.
- **Evaluation:** frozen ID manifests, raw response artifacts, snapshot fingerprints, prompt/claim
  capture, independent-model semantic judging with human adjudication, browser/API checks, and
  path-bucketed latency.
- **Contracts/status:** new verification and slice contracts under
  `.agents/runs/close-retrieval-generation-contract/`; the three predecessor changes and
  `.agents/portfolio.md` are corrected to Candidate with explicit counter-evidence; the accepted
  eligibility dependency and its D3 disposition are linked separately.
- **Dependencies:** no new external service is required. Local lexical fallback uses approved
  PostgreSQL capabilities; existing embedding, rerank, LLM, and Web providers remain bounded
  system boundaries.
