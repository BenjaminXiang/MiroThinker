# Acceptance: close-retrieval-generation-contract

This Epic is filled in two passes. The criteria are locked before implementation; exact commands,
run IDs, raw artifact links, metrics, adjudications, review decisions, immutable diff/artifact
hashes, and any explicitly authorized commit references are added during each slice. A checkbox is
not checked from code inspection or an earlier run.

## 1. Contract and artifact integrity

- [x] `proposal.md`, `design.md`, three capability specs, and `tasks.md` exist.
- [x] `.agents/runs/close-retrieval-generation-contract/verification-contract.md` exists before
  production-code implementation.
- [x] Slice A-F contracts exist; only Slice A is initially Ready.
- [x] `openspec validate close-retrieval-generation-contract --strict` exits 0 at proposal time.
- [ ] All OpenSpec and run artifacts remain internally linked and strict-valid at Epic acceptance.
- [ ] Every behavior-affecting implementation line is traceable to this change and one active slice.

## 2. Sequential slice discipline

- [ ] Slice A has independent RED evidence, review, immutable hash, and Accepted status before Slice B starts.
- [ ] Slice B has independent verification, review, immutable hash, and Accepted status before Slice C starts.
- [ ] Slice C has independent verification, review, immutable hash, and Accepted status before Slice D starts.
- [ ] Slice D has independent verification, review, immutable hash, and Accepted status before Slice E starts.
- [ ] Slice E has independent verification, review, immutable hash, and Accepted status before Slice F starts.
- [ ] Slice F has independent verification, review, immutable hash, and Accepted status before Epic cutover.
- [ ] A commit reference is required only when the user explicitly authorized that checkpoint's commit.
- [ ] Each slice stayed within its allowed scope or stopped for a contract update and re-review.

## 3. Slice A — frozen oracle and true RED

- [ ] The versioned manifest records query, path, expected local IDs, predicates, required intents,
  forbidden claims, expected outcome, and scorer policy for every frozen case.
- [ ] The manifest covers Type1, Type2, Type3, Type4, Q004, Q017, citation identity, typed outcome,
  and known professor-paper synthesis failures before production behavior work begins.
- [ ] Parent and candidate runs identify the same database snapshot/version, Milvus collection/index
  version, embedding version, identical saved provider-boundary fixtures, and manifest hash for
  paired causal comparison.
- [x] Snapshot identity is an immutable clone or before/after cryptographic DB and physical-Milvus
  manifest (relevant IDs/content/lifecycle/relations and chunk/paper/content/schema/entity state);
  alias/name alone and any observed drift invalidate the comparison.
- [x] Read-only Slice A two-level paper/chunk parity preflight either proves a viable Type4 substrate
  or stops for an explicit sequencing/substrate decision before later slices begin.
- [ ] Full raw request/response artifacts and code SHAs are retained for both sides.
- [ ] The manifest meets every minimum case/stratum count in `verification-contract.md`, with source,
  expected-ID grounding, judgment method, and reviewer; missing/cherry-picked strata block Slice A.
- [ ] Every minimum-floor, named true-RED, and known citation/synthesis-counterexample case is frozen
  P0 for every applicable gate; only pre-output additive beyond-floor cases are P1, and no P0 is
  demoted/replaced/made N/A after output.
- [x] Tests prove echoed query text, prompts, debug payloads, and configuration cannot satisfy
  retrieval, citation, or semantic scoring.
- [ ] Type4 freezes topic/rubric/blind-label protocol before implementation, labels the anonymized
  sealed-holdout parent/candidate union before scoring/unblinding, and emits no recall claim without
  a complete candidate universe.
- [ ] Type4 has 6 visible development plus 12 sealed acceptance topics; at least two independent
  blind reviewers save rationales, adjudicate disagreements, and achieve/report raw agreement and
  Cohen's kappa >=0.60 before labels are sealed.
- [ ] Any implementation change made after holdout judgments are unblinded retires that holdout to
  regression-only and requires a fresh versioned sealed holdout/union for certification.
- [ ] Repo contains only holdout schema/strata/rubric/hash; an independent reviewer/CI-secret
  custodian holds encrypted cases/labels with access log, signs one-shot results, then discloses and
  rotates the used holdout.
- [ ] Every 100-case classifier row asserts type, target domain, normalized name/topic, and planned
  endpoint where applicable; injected type-correct/entity-wrong rows fail.
- [x] A hard-gate failure makes the evaluator exit nonzero even if its aggregate score passes.
- [ ] The corrected RED report records the known failures and explains why the earlier 30/41 result
  is not an end-to-end acceptance result.
- [x] `git diff` for Slice A contains no production retrieval, generation, API, UI, schema, or data
  behavior change.

## 4. Slice B — canonical grounded answer

- [ ] B0 foundation is independently verified/reviewed/Accepted before B1; B1 grounding is Accepted
  before B2 consumers/rollout; each has immutable diff/artifact hash and rollback evidence.
- [ ] One ordered atomic `evidence_items` list feeds the prompt, validation, API, derived legacy
  citations, and frontend numbering.
- [ ] Evidence items extend Data-Agent-Shared-Spec §4.5 source type/URL-or-file/fetched-at/confidence,
  add local/Web lane separately, and keep record quality separate from relationship tier.
- [ ] `record-quality-v1` is exactly ready/needs_review/low_confidence/needs_enrichment/partial/
  rejected/null; partial remains visible, rejected is audit/exclusion-only, legacy values normalize,
  and null (plus material limitation) covers Web/relation/no-quality without being treated ready.
- [ ] A read-only per-domain/per-field provenance coverage report records joinable source type,
  URL/file, fetched-at, and snippet; no DOI/ID URL, row timestamp, or table locator is fabricated.
- [ ] Missing source evidence yields omission/partial disclosure, and Slice B stops if a P0 intent
  needs out-of-scope canonical data/schema/auth work to become grounded.
- [ ] Stable evidence IDs are content/source/object/field based and remain distinct from display
  ordinals.
- [ ] Evidence assembly composes all required domains and cannot discard a joined paper list through
  an earlier professor branch.
- [ ] Synthesis emits typed structured sections/items/claims with subject/predicate/value where
  applicable and typed evidence/result-set/lane support refs; the server validates and renders them.
- [ ] Identity/field/relation/membership/count/completeness/absence claims pass deterministic typed
  support checks, while other material claims pass a cited-span-only runtime entailment verifier.
- [ ] Source facts use evidence support; count/rank/completeness/set claims use full result-set
  support; empty/error/degradation claims use lane-trace support; no material claim has empty support.
- [ ] Comparative/top/representative wording cannot be approved from one span or entailment and is
  rendered only when the registered full-set order proves it.
- [ ] A verifier failure fails closed to `partial_result` or `synthesis_error`; offline semantic
  judging is not used as a substitute for runtime support validation.
- [ ] The ClaimEntailmentVerifier production model/prompt/version/config is frozen before B Ready;
  max 20 claims/12,000 cited characters/5 seconds and deterministic fixture adapter tests pass.
- [ ] Unknown evidence IDs, unsupported material claims, missing required-intent coverage, and silent
  domain truncation cannot produce `success`.
- [ ] Every response has one truthful outcome among `success`, `partial_result`, `no_result`,
  `retrieval_error`, and `synthesis_error`, plus reason/degradation details.
- [ ] An additive chat-owned retrieval port returns candidates plus per-lane status/error/timing/
  snapshot/trace while the shared legacy list-returning method and candidate ranking remain
  compatible; chat never infers successful empty retrieval from a bare list after provider failure.
- [ ] Clarification and unsupported-scope responses use `partial_result` with explicit reason/action
  and no unsupported factual claims.
- [ ] `no_result` is used only after successful qualifying retrieval, never as a provider-failure
  alias.
- [ ] Canonical API models add contract version and result-set predicate/order/completeness/total/
  cursor/snapshot metadata plus a tested generic cursor codec; Slice C owns real Type2 stable-page
  continuation and stale/mismatched behavior.
- [ ] Golden JSON/OpenAPI fixtures lock LegacyChatResponse versus CanonicalChatResponse required,
  null, absent, discriminated value, enum/registry, object-ID, compatibility, and response-ID fields.
- [ ] Golden old/new consumer fixtures cover every retained public field: `answer_text`, `citations`,
  legacy `evidence`, `clarification`, `structured_payload`, `answer_style`, `citation_map`, and
  `suggested_followups`; legacy/shadow preserve the current schema and canonical mode uses only the
  documented projections/action semantics.
- [ ] Canonical `clarification_required` includes a signed bounded canonical-ID action payload;
  legacy `default_id` never auto-selects ambiguity, and server-derived followups introduce no
  unsupported factual claim.
- [ ] A reversible session-owned result-set/item store materializes only ordered IDs/sort tuples/
  hashes/manifest for 30 minutes; signed cursors, cleanup, cross-session rejection, privacy/size
  guards, and source-row drift yielding a disclosed partial page are tested.
- [ ] `result-manifest-v1`, `response-integrity-v1`, and `cursor-v1` match their exact canonical JSON,
  SHA-256/HMAC-SHA256, key/expiry/session binding, Merkle proof, and token formats across independent
  process/language golden vectors; tamper, noncanonical encoding, and key rotation fail closed.
- [ ] Existing bare `entity_id_hint` behavior remains golden-tested as an explicit selector whose
  target still requires evidence; canonical clarification selection sends the hint with
  `clarification-token-v1` and rejects out-of-set, stale, tampered, cross-session, query/domain-
  mismatched, and conflicting-ID choices.
- [ ] The privacy-safe 30-minute clarification-action store atomically records first use, accepts
  concurrent/later same-ID retries idempotently, rejects different-ID reuse, expires/cleans state,
  stores no raw interaction content, and downgrades only after TTL drain.
- [ ] Canonical clarification prompts are neutral templates; factual option labels/hints have atomic
  evidence support, omitted/candidate counts have result-set support, unsupported fields are
  omitted, and the compatibility `default_id` is never auto-selected or presented as recommended.
- [ ] In canonical mode legacy `answer_text`/`citations` are projections of canonical output;
  unrepresentable Web/relation evidence is marked lossy and never cast as a false local entity type.
- [ ] `legacy`, `shadow`, and `canonical` modes work; shadow is externally legacy and records a
  canonical diff; returning to legacy is tested as immediate rollback.
- [ ] Legacy/shadow remain byte/schema-compatible and omit `contract_version`; field absence selects
  the legacy renderer, while canonical mode selects only the canonical renderer and never merges
  citation arrays.
- [ ] Shadow execution is bounded, off the response-critical path, failure-isolated, adds no more
  than 50 ms p95/100 ms p99 legacy latency, and never exposes/persists sensitive canonical payloads.
- [ ] The shadow selection frame/time window/seed/dedupe/inclusion/exclusion counts and corpus hash
  are frozen before candidate output; cases are not hand-selected for clean diffs.
- [ ] Cutover shadow evidence includes the frozen suite and at least 10 privacy-approved redacted
  cases per supported A-G route plus outcome/failure/local-Web strata, with zero canonical hard
  failures, zero frozen semantic regression, external legacy identity, SLO compliance, and no
  persisted secrets/cookies/authorization.
- [ ] The frontend resolves markers to the same canonical evidence and exposes material Web,
  record-quality, and separate secondary-relation tier/limitation metadata.
- [ ] Both React `Chat.tsx` and the actually served `backend/static/chat.html` consumer are migrated
  and browser-tested, or the static route is explicitly deprecated/redirected and that route is
  tested; the deployed `/chat` cannot remain legacy-only silently.
- [ ] Canonical feedback echoes the signed canonical response; the backend verifies integrity and
  stores/renders only minimized IDs/lanes/tiers/assertion hashes/outcome/run metadata. It rejects
  tampering and persists/exposes no raw query/text/snippet/URL/provider/credential payload without a
  separately approved authenticated review change.
- [ ] Public API integration, saved synthesis fixtures, provider failures, and browser citation
  rendering pass; unit tests alone are not used as GREEN.

## 5. Slice C — Q004/Q017, natural Type1, and Type2

- [ ] C0 identity/Type1 is independently verified/reviewed/Accepted with its own rollback before C1
  Type2 starts; C as a whole waits for both checkpoints.
- [ ] Independent C0 and C1 rollout flags restore their prior accepted paths and remain through the
  observation window.
- [ ] `retrieval-active-v1` is frozen with SQL/rule hash and exact state fixtures: company resolved;
  professor resolved+active; paper confirmed/unverified and quality non-rejected with unverified
  limitation; rejected/merged nodes and candidate/rejected edges excluded; verified links required.
- [ ] Q004 and Q017 each pass professor-profile classifier/type, normalized name, professor domain,
  professor endpoint, target professor ID, and citation checks without requiring a paper predicate.
- [ ] Organization/location context is not retained as part of the professor name.
- [ ] Bare, quoted, and supported natural detail variants of an exact title retrieve and cite the
  same canonical paper ID.
- [ ] An explicit title absent from the local snapshot invokes the separate Web fallback; useful Web
  evidence yields disclosed `partial_result`, dual successful empties yield `no_result`, and an
  unusable required fallback failure yields `retrieval_error`.
- [ ] A Web exact-title result retains Web provenance and never fabricates or satisfies a local paper
  ID gate.
- [ ] Same-title active matches clarify without arbitrary selection; merged matches follow/cite the
  survivor and merge trace; terminal-only matches are not local success.
- [ ] A paper identity without source-grounded requested details yields a supported limited partial
  response, never invented detail.
- [ ] Type2 all/list traverses the complete active verified set through stable pagination, with no
  duplicates or omissions under the snapshot.
- [ ] Type2 year/range and recent semantics use the documented publication-time rule and expose the
  effective predicate.
- [ ] Type2 topic results are the intersection of the resolved professor's verified papers and the
  parsed paper topic.
- [ ] Type2 representative results use documented significance features/ties and are labeled ranked,
  not complete.
- [ ] Professor-paper payloads generate a paper answer with cited paper titles and pagination
  metadata, not a profile-only answer or a false inability message.

## 6. Slice D — Type4 hybrid paper retrieval

- [ ] D0 subject/lexical substrate is independently verified/reviewed/Accepted with migration/data/
  index rollback before D1 planner/ranking starts; D as a whole waits for both.
- [ ] The D1 planner flag restores the pre-D1 topic path without removing D0 and remains through the
  observation window.
- [ ] A reversible normalized paper-subject migration/model and versioned alias map preserve shared
  source evidence; bounded source-backed backfill never infers category from title text.
- [ ] Category cohort SQL/source snapshot/denominator/ID hash is frozen before candidate output,
  independent of benchmark membership, and fully processed or accompanied by residual owner/worklist.
- [ ] D freezes a new immutable post-substrate derivative snapshot before outputs and runs parent and
  candidate on it identically while retaining the original A baseline and pre-output-reviewed
  category expectations.
- [ ] Reversible mixed-language PostgreSQL FTS/trigram indexes have upgrade/downgrade, query-plan,
  bounded-scan, and p95/p99 evidence.
- [ ] Ambiguous category asks for clarification and missing category coverage yields a disclosed
  partial result instead of silently dropping the filter.
- [ ] Topic, year/range, category, and recency constraints are parsed and preserved in trace output.
- [ ] Type4 reuses `paper.year`/Asia-Shanghai/null rules; exact/range/N-year/category filter before
  fusion, while bare latest has no hidden cutoff and orders qualified papers by year/relevance/ID.
- [ ] Dense and local lexical/FTS lanes are independently bounded and may degrade independently.
- [ ] Dense failure with successful lexical retrieval yields a disclosed degraded result, not a
  false empty search; the symmetric lexical failure is also truthful.
- [ ] All chunk candidates are aggregated by canonical `paper_id` before fusion, filters, rerank, and
  final top-five selection.
- [ ] Active partial-rich papers participate with a documented rank penalty and visible quality
  status; ready hits do not globally suppress them.
- [ ] Title-only partial records are not represented as successfully embedded rich records.
- [ ] Local and Web paper lanes remain separately typed; Web cannot satisfy a local paper ID gate.
- [ ] Frozen-topic micro-`Precision@5 >= 85%` passes after paper deduplication using exactly five
  local slots per topic; missing, duplicate, Web/non-local, and irrelevant slots count as incorrect,
  while per-topic P@5 is reported diagnostically.
- [ ] The returned-ID union is anonymized/blind-labeled under the frozen rubric and sealed before
  score calculation or parent/candidate unblinding with two-reviewer/adjudication/agreement evidence.

## 7. Slice E — Type3 company-to-paper traversal

- [ ] The Type3 traversal flag defaults to the accepted prior/off path, is independently reversible,
  and remains through the observation window.
- [ ] Strong paths use `link_status=verified` roles plus active verified professor-paper links;
  current/former/unknown time is disclosed, and explicit current intent requires `is_current=true`.
- [ ] Secondary paths use only `resolution_status=matched`, non-null resolved professor IDs from the
  latest company snapshot and remain labeled secondary; candidate/unresolved rows are excluded.
- [ ] Unresolved team names and unverified/terminal professor-paper edges produce no local path.
- [ ] Every Type3 company, professor, paper, and edge applies the exact `retrieval-active-v1`
  physical-state mapping rather
  than a generic non-rejected check.
- [ ] Every result preserves company, professor, paper, both edge identities, relation tier, and
  atomic supporting evidence.
- [ ] Unique paper pages use default 20/max 50 and stable order; each paper returns path total, up to
  10 strong-first paths, and continuation that traverses every alternate path.
- [ ] Retrieval, API, citation, semantic, and latency checks cover strong, secondary, excluded, and
  multi-path cases.
- [ ] A read-only production coverage report records eligible strong/secondary edges, companies,
  professors, papers, zero-coverage causes, and remediation worklist/owner; fixture GREEN is labeled
  mechanism-only when production coverage remains sparse.

## 8. Slice F — embedding ledger, lanes, and parity

- [ ] A reversible additive migration and validated storage model implement the per-paper embedding
  audit ledger, per-chunk manifest/version state, and attempt history.
- [ ] Canonical data plus the versioned pure `index_eligibility` predicate remain the sole readiness
  authority; ledger eligibility is recomputed and never used alone for retrieval admission.
- [ ] Separate versioned `enrichment_lane_membership` rules derive active enrichment/audit worklists
  but never add a paper to desired index state; reports persist and distinguish both rule families.
- [ ] Every paper in the reconciliation snapshot has a row covering rule/snapshot, source-content
  hash, chunker/schema version, expected chunk count/manifest hash, embedding/index tuple,
  success/attempt/failure.
- [ ] Candidate Milvus rows or a cryptographically linked sidecar expose verifiable chunk ID,
  paper ID, chunk type/index, content hash, embedding model, chunker/schema, target index, and write
  identity; ledger self-report alone cannot pass.
- [ ] Active `needs_enrichment`, active partial title-only, active partial-rich/ready parity, and
  `needs_review` audit are separate snapshot worklists; rejected/merged records are excluded.
- [ ] Current full paper/chunk tuples are skipped without provider calls; content/chunking/model/index
  drift creates deterministic replay and obsolete-chunk cleanup.
- [ ] Failed or unconfirmed index writes never become successful ledger state.
- [ ] Lane execution is checkpointed, bounded, resumable, and idempotent across interruption.
- [ ] Parity compares both distinct paper coverage and exact expected/actual chunk manifests/version
  tuples; it reports missing/unexpected/stale/conflicting chunks and treats multiple valid chunks per
  paper as normal rather than duplicate papers.
- [ ] Dry run precedes mutation, needs-review records are not auto-promoted, and the prior index
  alias/version remains a tested rollback checkpoint.
- [ ] Migration upgrade/downgrade and a non-production bounded rehearsal have accepted evidence
  before any production data or index write.
- [ ] A read-only active-production report records paper coverage, exact chunk/version gaps, and
  residual enrichment/review lanes with owner/follow-up; non-production GREEN is labeled
  mechanism-only and cannot claim production parity or overall paper retrievability closure.

## 9. End-to-end hard gates

| Gate | Required result |
|---|---:|
| Type1 expected local paper ID retrieved | 100% |
| Type1 expected local paper ID correctly cited | 100% |
| Type2 requested predicate/current page complete | 100% |
| Type2 returned paper items correctly cited | 100% |
| Type3 eligible two-hop IDs/tiers/exclusions exact | 100% |
| Type3 returned paper items correctly cited | 100% |
| Q004/Q017 profile type, normalized name, professor domain/endpoint/ID/citation | 100% each |
| Type4 frozen-topic Precision@5 | at least 85% |
| Type4 returned paper items correctly cited | 100% |
| P0 required-intent semantic pass | 100% |
| Non-P0 required-intent semantic pass | at least 90% |
| Unsupported material claims | 0 |
| Previously passing frozen cases regressed | 0 |

- [ ] Every applicable case passes retrieval, correct citation, and semantic correctness/completeness;
  success in one stage cannot compensate for failure in another.
- [ ] Deterministic schema/ID/predicate/pagination/citation/outcome checks pass.
- [ ] The pinned independent judge passes with full inputs/outputs saved; all boundary results have
  a recorded blind/randomized pre-unblinding adjudication against atomic evidence plus immutable
  result/lane supports.
- [ ] Human adjudication resolves semantic ambiguity only and cannot override deterministic schema,
  expected-ID/predicate/page, support, citation, outcome, or regression hard failures.
- [ ] Paired causal GREEN uses identical saved provider fixtures; separately labeled live-provider
  stability runs pin configuration, execute every P0 case at least three times, and pass every P0
  deterministic/semantic gate on every observation.
- [ ] The gate command exits nonzero for every injected/replayed hard-gate failure.
- [ ] The full frozen manifest and 100-case regression benchmark pass all type/domain/normalized
  entity-or-topic/endpoint expectations without changing their oracle after candidate results.

## 10. Performance, observability, and rollback

- [ ] Retrieval-on p95 is at most 6 seconds in every required Type1-Type4 and source-lane bucket with
  at least 100 measured observations after 5 warmups.
- [ ] Synthesis-on end-to-end p95 is at most 15 seconds in every required path/source bucket with
  at least 100 measured observations after 5 warmups.
- [ ] The Slice A-frozen benchmark protocol records hardware, provider versions, concurrency,
  warmup/cache state, request boundaries, deadlines, nearest-rank percentile method, and any bucket
  declared not applicable before implementation.
- [ ] Retrieval p99 is at most 12 seconds, synthesis-on p99 at most 30 seconds, timeouts count at
  deadline and as failures, and timeout/error rate is 0 for P0 and at most 1% otherwise.
- [ ] Outcome, lane degradation, evidence truncation, unsupported-claim validation, and shadow diffs
  are observable without logging secrets or credential-bearing payloads.
- [ ] Canonical chat can return immediately to legacy mode.
- [ ] Candidate index can return to the recorded prior alias/version.
- [ ] Every checkpoint records code/schema/data/index/config predecessor hashes and all C0/C1/D1/E/F
  rollout controls remain operable through the full observation window.
- [ ] A reverse-order rollback drill covers chat-legacy safety switch, F alias, E, D1, D0, C1, C0,
  B2, B1, and TTL-drained B0; no migration/data removal precedes dependent disablement.
- [ ] An injected real checkpoint invalidation moves every matrix-listed downstream Accepted state to
  Candidate with `invalidated_by`, blocks cutover/predecessor/dependency archive, and requires a new
  observation window after re-acceptance; a planned successful drill does not change lifecycle.
- [ ] Legacy chat implementation removal and production bulk backfill remain outside this Epic's
  acceptance unless separately approved.

## 11. Predecessor status and archive gate

- [x] `fix-paper-topic-query-classification`, `wire-professor-paper-list-traversal`, and
  `fix-professor-ambiguity-intro-rule` are corrected to Candidate and linked to this Epic.
- [ ] `make-partial-papers-retrievable` remains an Accepted behavior dependency; its unmeasured D3
  task is explicitly superseded by Slice F's frozen full paper/chunk reconciliation, not called done.
- [ ] That dependency is normally archived with spec migration after its implemented eligibility and
  snippet/admission deltas are represented canonically and strict-valid.
- [ ] `sigs-official-publications-to-paper-domain` remains in verification with its unique ingest
  capability intact; normal archive is blocked until Task 5.20 plus C0/D1 align exact-title identity
  partials and remove historical ready-first suppression. It is not a `--skip-specs` dependency.
- [ ] No Candidate predecessor is re-accepted or archived until its linked canonical end-to-end
  scenarios pass; then it is accepted only as superseded history and archived with
  `openspec archive --skip-specs` plus `superseded_by=close-retrieval-generation-contract`.
- [ ] Default spec-migrating archive is forbidden for the three Candidate predecessors because their
  broad overlapping deltas are replaced by this Epic's narrower canonical capabilities.
- [ ] This Epic is not archived until all slices, acceptance evidence, review decisions, and rollback
  checkpoints are complete.

## Evidence

### Proposal-time evidence — 2026-07-10

- OpenSpec strict validation: `openspec validate close-retrieval-generation-contract --strict`
  exited 0.
- Audit counter-evidence, current baselines, and code seams are linked in `source-links.md` and the
  initial `.agents/runs/close-retrieval-generation-contract/verification.md`.
- No production implementation, live data mutation, index write, push, or commit was performed by
  this proposal step.

### Slice A

- Pending.

### Slice B

- Blocked on Slice A Accepted.

### Slice C

- Blocked on Slice B Accepted.

### Slice D

- Blocked on Slice C Accepted.

### Slice E

- Blocked on Slice D Accepted.

### Slice F / Epic

- Blocked on Slice E Accepted.
