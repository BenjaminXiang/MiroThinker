# Verification Contract — close-retrieval-generation-contract

> Behavior-affecting Agentic RAG Epic. OpenSpec owns expected behavior and RED/GREEN intent:
> `openspec/changes/close-retrieval-generation-contract/`. Unit tests alone are not acceptance for
> routing, retrieval, generation, citation, frontend, or index-parity behavior.

## Change and initial state

- **Change ID:** `close-retrieval-generation-contract`
- **Initial code checkpoint:** `c0f3db2` on `feat/professor-retrievability`
- **Epic state:** Ready for Slice A only.
- **Slice states:** A = Ready; B-F = Specified and dependency-blocked.
- **Predecessor state:** `fix-paper-topic-query-classification`,
  `wire-professor-paper-list-traversal`, and `fix-professor-ambiguity-intro-rule` are Candidate until
  their scenarios pass this contract.

## Verification principle

A case passes only through the full chain:

```text
expected canonical object/fact retrieved under predicate
  -> the same object/fact referenced by canonical evidence
    -> every required intent answered correctly and completely
```

The three stages are conjunctive. Text appearing in a request echo, debug structure, prompt,
uncited answer span, Web page, or wrong local object cannot satisfy a local retrieval/citation gate.

## Slice A RED contract

Slice A MUST create executable RED evidence before any production behavior edit. It is gate-only.

### Frozen inputs

The manifest records for every case:

- immutable case ID and query;
- immutable `priority: P0 | P1` and the rule/rationale that assigned it;
- expected route/path, normalized entity IDs/names, domain, and endpoint;
- expected local paper/professor/company IDs and relationship-edge IDs where applicable;
- predicate and pagination expectation;
- `retrieval-active-v1` company/professor/paper/edge state expectation and frozen SQL/rule hash;
- required answer intents and forbidden claims;
- expected typed outcome and allowed degradation;
- relevance rubric for Type4;
- deterministic and semantic scorer policy.

Each run records manifest hash, code SHA, database snapshot/version, eligibility-rule version,
Milvus collection/index version or alias target, embedding model/version, rerank/model/judge
configuration, timestamps, and raw responses. Parent and candidate comparison is invalid unless
manifest and data/index identity match.

Identity requires either an immutable read-only clone or cryptographic manifests: the full
query-visible DB projection for every planner (candidates, distractors, exclusions, relations), and
physical Milvus target/schema plus ordered chunk/paper/content and vector-byte/dimension hashes (or
trusted immutable segment checksum) and entity count. Gold-only hashes and alias/name are
insufficient. Capture
both fingerprints before and after each paired run; any drift invalidates it. Slice A also records a
read-only two-level paper/chunk parity preflight and stops for an explicit sequencing/substrate
decision if current index gaps make later Type4 evaluation non-viable.

### Required true-RED demonstrations

- A token present only in the echoed query fails retrieval.
- A title/name in prompt/debug/config but absent from canonical result IDs fails retrieval.
- A retrieved target absent from claim evidence references fails citation.
- A cited target with a wrong, incomplete, or unsupported answer fails semantics.
- The existing professor-paper payload/synthesis counterexamples fail their required-intent gate.
- Q004/Q017 fail when context is fused into the professor name or the wrong endpoint is used.
- The supported natural-title suffix case fails if it does not return the exact target ID.
- A Type3 positive fixture fails until a two-hop planner preserves its frozen edge IDs and tiers.
- Type4 uses frozen-topic Precision@5 and refuses an unsupported recall label.
- A classifier row fails when type is correct but expected domain, normalized name/topic, or planned
  endpoint is wrong.
- One hard-gate failure makes the command exit nonzero even if aggregate percentage is high.

Slice A GREEN means the evaluator reliably exposes these RED production cases and freezes the
oracle. It does **not** mean production retrieval or generation is fixed.

## Oracle isolation rules

- Scoring input is allowlisted to canonical result IDs, canonical evidence/claims/outcomes, and
  saved judge inputs/outputs.
- Request query, request metadata, prompt text, debug payloads, configuration, and serialized
  fixture expectations are excluded.
- Exact object checks use canonical IDs, never a substring proxy.
- Every 100-case classifier row asserts expected type, target domain, normalized name/topic, and
  planned endpoint wherever applicable; a type-only match cannot pass.
- Type2 completeness is evaluated against a frozen verified-link ID set and the requested page or
  full pagination traversal.
- Type1-Type3 expected sets apply exactly: company resolved; professor resolved plus lifecycle
  active; paper confirmed/unverified plus non-rejected quality (unverified disclosed); verified
  required edges; rejected/merged/inactive/candidate paths excluded.
- Type4 topic queries, eligibility criteria, relevance rubric, and blind-labeling protocol are
  frozen before implementation with visible development and sealed acceptance sets. After parent/
  candidate holdout outputs, their local-ID union is anonymized/randomized; at least two independent
  reviewers save labels/rationales, adjudicate disagreement, report raw agreement and Cohen's kappa
  >=0.60, and seal labels before scoring/unblinding. Any post-unblinding implementation change makes
  that holdout regression-only and requires a fresh versioned sealed holdout/union. Candidates are
  deduplicated by paper ID before Precision@5.
- The committed repo contains only sealed-holdout schema/strata/rubric/hash. Encrypted cases/labels
  are held by an independent reviewer or CI-secret custodian with access log; one-shot output is
  signed to the hash, then the used holdout is disclosed/rotated to regression-only.
- No paper recall claim is allowed without a declared candidate universe and relevance labels for
  that universe.
- Raw artifacts are append-only per run ID; a new snapshot creates a new baseline.

## Minimum frozen coverage

These are floors, not targets to optimize against. A case may satisfy multiple stated strata, but
the minimum distinct case counts still apply.

| Area | Minimum frozen coverage before Slice A Accepted |
|---|---|
| Type1 local positives | 12 distinct paper IDs; at least 4 English titles, 4 Chinese/mixed titles, 4 conversational/quoted wrappers; include same-title ambiguity, merged/terminal target, and empty-grounding-snippet negatives |
| Type1 local misses | 3 explicit titles covering Web success, successful local+Web empty, and Web failure |
| Type2 | 12 cases across at least 6 professors; all/list, year, range, bare recent, explicit N-year, topic, representative, zero-paper, missing-year, multi-page, and below-prior-limit/rank strata |
| Type3 | strong, secondary, unresolved, unverified/terminal paper edge, multi-path dedupe, and zero-live-coverage cases (at least 6) |
| Type4 positive topics | 6 visible development topics plus 12 sealed acceptance topics, each with >=5 relevant local papers; sealed set has >=4 Chinese, 4 English, 4 mixed-language, 4 common, 4 long-tail, 2 year/range, 2 category, 2 recency, and 3 partial-rich strata |
| Type4 negative/degraded | at least 4 covering genuine local no-result, dense failure, lexical failure, and Web-only supplement |
| Outcomes | at least 2 fixtures each for `partial_result`, `no_result`, `retrieval_error`, and `synthesis_error`; success is covered by every positive path |
| Classifier regression | all 100 existing rows with populated type/domain/name-or-topic expectations and endpoint expectations where applicable |

Each stratum records source (snapshot query or synthetic boundary fixture), expected-ID grounding,
judgment method, and reviewer. Missing counts or undocumented cherry-picking block Slice A.

Every distinct case used to satisfy any minimum count in this table is P0 for every applicable gate,
as are all named true-RED demonstrations and known synthesis/citation counterexamples. The 100
classifier rows are P0 for their deterministic fields; live-provider/semantic gates are N/A only
when that row exercises no such boundary, with the N/A reason frozen. P1 is permitted only for
additional cases beyond all floors, assigned with rationale before parent/candidate output. A P0
case cannot be demoted, replaced, or declared N/A after output; new hard cases discovered later are
added as P0 in a versioned manifest.

## Deterministic hard gates

| Bucket | Gate |
|---|---|
| Type1 | exact expected paper ID retrieved 100%; the same ID cited 100% |
| Type2 | expected predicate/page ID set complete 100%; every returned paper item cited 100% |
| Q004/Q017 | professor-profile classifier/type, normalized name, domain, endpoint, professor ID, citation 100% each |
| Type4 | frozen-topic micro-Precision@5 >=85% over exactly 5 local slots/topic; every returned paper item cited 100% |
| Type3 | eligible two-hop IDs/tiers/edges exact; excluded paths absent; returned items cited 100% |
| Outcomes | absence and retrieval/synthesis failures typed correctly 100% for P0 fixtures |
| Claims | unknown evidence IDs and unsupported material claims = 0 accepted |
| Regression | previously passing frozen cases lost = 0 |

The verifier exits nonzero when any hard gate fails. It prints aggregate metrics only as additional
diagnostics, never as a replacement for bucket gates.

For N Type4 topics, micro-Precision@5 is `relevant unique local top-five slots / (5 * N)`.
Missing slots, repeated paper IDs, Web/non-local items, and irrelevant papers contribute zero.
Per-topic P@5 is always reported but is diagnostic; the 85% hard gate applies to the micro aggregate.

## Semantic gate

- Deterministic checks first validate response schema, IDs, predicates, pages, evidence references,
  citation coverage, outcome, and forbidden structural states.
- A judge that is independent from synthesis evaluates only the saved query, required intents,
  canonical answer, atomic evidence, sanitized result-set manifest/assertions, and immutable lane
  assertions. All inputs/support hashes plus model ID, prompt hash, temperature, and full output are
  pinned and retained.
- The judge evaluates semantic correctness, required-intent completeness, evidence support, and
  unsupported material claims per case.
- P0 cases require 100% pass; remaining frozen cases require at least 90%; unsupported material
  claims have zero tolerance.
- Paired causal GREEN uses identical saved provider-boundary fixtures. Live-provider confirmation is
  a separate stability report with pinned versions/configuration and at least three independent runs
  per P0 case that exercises a live provider; every applicable live P0 observation must pass
  deterministic and semantic hard gates. Live
  variance cannot substitute for deterministic GREEN.
- Scores on the declared boundary or judge/parser disagreement require saved human adjudication.
  Answer/order/run/SHA identity is anonymized and randomized; the adjudicator sees only query,
  intents, answer, and typed supports, then seals decision/rationale before unblinding. Human review
  can resolve semantic ambiguity only and MUST NOT override deterministic schema, expected ID/
  predicate/page, support-reference, citation, outcome, or regression failures. Adjudication cannot
  change the manifest after output is known; manifest defects create a versioned replacement baseline.

## Performance gate

- Retrieval-on p95 <=6 seconds.
- Synthesis-on end-to-end p95 <=15 seconds.
- Slice A freezes hardware, provider versions, concurrency, warmup/cache policy, request boundaries,
  deadlines, and the required Type1-Type4/local-only/local-plus-Web bucket matrix.
- Every required bucket has at least 5 unscored warmups and 100 measured observations. A bucket may
  be marked not applicable only in the frozen protocol before candidate implementation, with review.
- Report nearest-rank p95 and p99 separately per bucket. Retrieval p99 must be <=12 seconds and
  synthesis-on end-to-end p99 <=30 seconds; timeouts count at their configured deadline and as
  failures. Timeout/error rate must be 0 for P0 observations and <=1% otherwise.
- A fast bucket or synthesis-off run cannot hide a slow required bucket.
- Dense/lexical provider failures and timeouts remain visible in typed outcomes and traces.

## Verification surfaces by slice

### Slice A

- Evaluator schema/unit tests for allowlisted scorer input and nonzero failure exit.
- Frozen manifest review and snapshot fingerprint.
- Same-snapshot parent/candidate raw replay.
- Diff proof of no production behavior changes.

### Slice B

- B0 foundation, B1 grounding, and B2 consumers/rollout are separately reviewed and hash-locked;
  each checkpoint's required checks/stop/rollback contract in the Slice B file passes before the
  next becomes Ready.
- Migration upgrade/downgrade and retention/TTL/cascade compatibility for the IDs/sort-tuples-only
  chat result store; signed-echo feedback integrity/minimization/tamper tests and proof that no raw
  unauthenticated canonical response/evidence store or read surface was added.
- Model/unit tests for evidence identity, claim validation, outcomes, derived compatibility, and
  deterministic rendering.
- Golden old/new client fixtures cover every retained current `ChatRequest`/`ChatResponse` field,
  including bare and clarification-bound `entity_id_hint`; cross-process/language vectors lock
  `result-manifest-v1`, `response-integrity-v1`, `cursor-v1`, and `clarification-token-v1`.
- `/api/chat` integration fixtures through real evidence composition and response serialization.
- Saved model/provider fixtures for valid, malformed, unsupported, timeout, and partial synthesis.
- Runtime support fixtures for typed fact/relation/set claims, unsupported derived claims, and an
  unavailable entailment verifier that must fail closed.
- Frontend type/build/test plus browser walkthrough for marker-to-source identity and quality labels.
- Legacy/shadow/canonical comparison and immediate rollback evidence.

### Slice C

- C0 identity/Type1 is independently reviewed, hash-locked, and rollback-tested before C1 Type2
  becomes Ready; C1 has a separate topic-port/planner rollback.
- Parser/routing unit tests plus public retrieval/API integration for Q004/Q017 and natural titles.
- Test-database Type2 set/predicate/pagination coverage using professors with more than one page and
  a target beyond prior LIMIT/rank boundaries.
- Live or snapshot replay through chat with synthesis on; paper titles and page metadata must reach
  canonical claims/evidence.

### Slice D

- D0 substrate is independently reviewed, hash-locked, migration/data/index rollback-tested, and
  Accepted before D1 retrieval becomes Ready; D1 has a separate planner rollback.
- Migration upgrade/downgrade and model/provenance tests for normalized paper subjects plus
  PostgreSQL FTS/trigram extension/index/query-plan/rollback evidence.
- Category alias ambiguity, missing coverage, and no-title-inference cases.
- Pre-output frozen category cohort SQL/source snapshot/ID hash/denominator, no benchmark-dependent
  selection, complete processing or residual worklist, and a new immutable derivative-snapshot
  manifest used identically by parent/candidate while preserving the original A baseline.
- Parser tests for structured filters.
- Retrieval-service integration with real test database and deterministic dense/lexical/rerank
  provider fixtures.
- Paper-level dedupe/fusion, partial-rich, dense-failure, lexical-failure, and Web-separation cases.
- Frozen topic benchmark plus citation, semantic, regression, and per-bucket latency gates.

### Slice E

- Test-database strong/secondary/unresolved/unverified/multi-path fixtures.
- Retrieval-service and `/api/chat` integration proving both edge identities and relationship tiers
  survive through evidence and generated disclosure.
- Type3 citation, semantic, exclusion, regression, and latency gates.
- Read-only production relationship coverage report (strong/secondary edges, eligible nodes/papers,
  zero-coverage causes) and explicit mechanism-only versus production-covered status with a
  separately owned remediation worklist.

### Slice F

- Migration upgrade/downgrade and storage integration.
- Ledger state-machine/property or matrix tests for recomputed non-authoritative eligibility,
  source/chunk manifest, content/chunker/model/index drift, partial failure, retry, and idempotence.
- Candidate-row/linked-sidecar proof of chunk/content/model/chunker/index/write identity.
- Two-level reconciler tests with distinct-paper coverage plus exact chunk manifests, including
  equal-paper-count/different-chunk, stale/unverifiable tuples, terminal extras, legitimate
  multi-chunk papers, and conflicting chunk identity.
- Dry-run, interrupted replay, bounded non-production rehearsal, distinct-paper plus exact
  chunk-manifest/version parity, frozen retrieval, latency, and index-alias rollback evidence.
- Read-only active-production paper/chunk parity and residual-lane coverage report; non-production
  mechanism acceptance cannot be labeled production parity.

## Mock boundaries

Mock only model/embedding/rerank/Web clients, Milvus adapter boundaries, clocks, and external
network. Do not mock away classifier-to-planner wiring, evidence composition, response validation,
pagination, candidate aggregation, relation traversal, ledger decisions, or API serialization in
acceptance tests. Saved provider fixtures must preserve real response schemas and representative
failure shapes.

## Artifact layout

Each execution run writes immutable machine-readable artifacts under:

```text
.agents/runs/close-retrieval-generation-contract/artifacts/
  <snapshot-id>/
    <code-sha>/
      manifest.json
      environment.json
      raw-responses.jsonl
      deterministic-results.json
      semantic-judge.jsonl
      adjudications.jsonl
      latency.json
      parity.json                 # Slice F when applicable
```

`verification.md` links the exact paths and hashes; it does not paste selected successes while
omitting failures. Secrets, authorization headers, cookies, and credential-bearing payloads are
redacted before persistence.

## Environment and safety invariants

- Use a named frozen test/read-only snapshot for evaluation; do not mutate production/business data.
- Milvus mutation is forbidden through Slices A-E. Slice F starts with a dry run and explicit
  non-production target/alias approval.
- Localhost commands unset proxy variables as required by the current harness; record the effective
  non-secret environment.
- Sequence any TestClient and live-backend steps that contend for the Milvus single writer.
- No threshold, rubric, expected ID, required intent, or judge prompt is tuned after candidate
  outputs are inspected without versioning and rerunning the parent baseline.
- No test, schema validator, evidence check, or benchmark definition is weakened to make GREEN.

## Promotion rule

A slice moves Ready -> In Progress -> Candidate only after implementation and all required evidence
exist. It moves Candidate -> Accepted only after independent review confirms scope, invariants,
oracle integrity, results, and rollback. An immutable diff/artifact hash is then recorded; an
isolated commit reference is added only when the user explicitly authorized it. The next slice may
become Ready only after that acceptance. Failure leaves the slice Candidate or Rejected and does
not broaden the next slice.

The Epic can become Candidate only after Slice F is Accepted and the integrated full-manifest,
100-case, semantic, latency, shadow, parity, and rollback evidence is linked. Archive requires a
separate acceptance decision.

A planned rollback drill must prove the design matrix without changing lifecycle. An operational or
injected threshold-failure rollback records one rollback run/hash, switches chat legacy first,
executes checkpoint controls in reverse dependency order, marks listed downstream Accepted states
Candidate with `invalidated_by`, blocks cutover/archive, and requires re-acceptance plus a fresh
observation window. All legacy/planner/index controls remain present until that window completes.
