## 1. Slice A — Frozen Oracle and True RED

- [x] 1.1 Create `.agents/runs/close-retrieval-generation-contract/verification-contract.md` and six slice contracts before production-code edits.
- [x] 1.2 Confirm Slice A is Ready and all later slices are Specified and blocked on predecessor acceptance.
- [x] 1.3 Define a versioned case-manifest schema for query, path, expected canonical IDs, predicates, required intents, forbidden claims, expected outcome, and scoring policy.
- [ ] 1.4 Freeze immutable priority on every case: all distinct minimum-floor, named true-RED, and known citation/synthesis-counterexample cases are P0 for applicable gates; only pre-output additive beyond-floor cases may be P1. Include `retrieval-active-v1` SQL/rule hash and all Type1-Type4/Q004/Q017/outcome/language/filter/state strata.
- [x] 1.5 Create immutable clone or before/after cryptographic DB/Milvus physical manifests, run a read-only two-level paper/chunk parity preflight, and stop for sequencing/substrate decision if the current index cannot support later Type4 evaluation. **STOP triggered:** snapshot `paper-snapshot-4afb567921be3dab` is stable but non-viable; sequencing/substrate decision pending.
- [x] 1.6 Write RED tests proving request echoes, prompts, debug fields, and configuration cannot satisfy retrieval scoring.
- [ ] 1.7 Freeze 6 visible dev plus an encrypted 12-topic holdout under independent/CI-secret custody; version only schema/strata/rubric/hash; test access log, signed one-shot rotation, two-reviewer kappa>=0.60, fresh holdout after unblinding, micro-P@5 slots, and no recall label.
- [ ] 1.8 Add deterministic gate aggregation and strengthen all 100 classifier rows to assert type/domain/normalized name-or-topic/endpoint so either defect exits nonzero rather than hiding in an average.
- [ ] 1.9 Replay parent and `c0f3db2` on the same snapshot with identical saved provider fixtures, then separately run the pinned live-provider stability protocol and publish raw corrected retrieval/citation/semantic evidence.
- [ ] 1.10 Demonstrate the known Type1/Type2/Q004/Q017/citation/synthesis cases as true RED without changing production behavior.
- [ ] 1.11 Run Slice A required checks, complete `verification.md`, obtain independent review, record an immutable diff/artifact hash (and an isolated commit only when explicitly authorized), and mark Slice A Accepted before Slice B starts.

## 2. Slice B — Canonical Grounded Answer Contract

- [ ] 2.1 Confirm Slice A is Accepted; stop without editing Slice B production scope otherwise.
- [ ] 2.2 **B0:** Run and review the frozen per-domain/field shared-provenance coverage preflight; stop if a P0 intent cannot be grounded without out-of-scope schema/data/auth work.
- [ ] 2.3 **B0:** Freeze old/new-client JSON/OpenAPI fixtures and write RED model tests for every current ChatRequest/ChatResponse field, including bare `entity_id_hint`, canonical hint+token round-trip, clarification option supports, plus canonical-v1 values/enums/registries, result sets, claims, outcomes, and compatibility projections.
- [ ] 2.4 **B0:** Define public models and the additive chat-owned typed retrieval-status port; add reversible 30-minute IDs/sort-tuples-only result-set/item and minimized `chat_clarification_action` stores plus exact `result-manifest-v1`, `response-integrity-v1`, `cursor-v1`, and `clarification-token-v1` codecs without changing selection/ranking.
- [ ] 2.5 **B0:** Run model/OpenAPI, port compatibility, cross-process/language crypto golden vectors, result/action-store migration/TTL/cascade, atomic first-use/same-ID retry/different-ID conflict/concurrency, cursor/key-rotation/tamper, privacy, and rollback checks; record review plus immutable diff/artifact hash and mark B0 Accepted.
- [ ] 2.6 **B1:** Confirm B0 is Accepted before grounding implementation.
- [ ] 2.7 **B1:** Write RED integration fixtures reproducing professor evidence dropping joined paper evidence, citation-marker/source divergence, bare-list failure ambiguity, stale continuation, unsupported claims, and lossy legacy projection.
- [ ] 2.8 **B1:** Implement Python/TypeScript-golden-tested `evidence-id-v1` including exact uint32 prefix, WHATWG HTTP(S)/IDN/query, logical-file, six-digit UTC time, null/both locator, SHA-256/collision behavior, and one evidence composer extending shared source, lane, nullable quality, tier, and limitations.
- [ ] 2.9 **B1:** Replace early-return evidence assembly with required-intent/domain composition, deduplication, budgets, and explicit truncation reporting.
- [ ] 2.10 **B1:** Change synthesis to typed support refs and implement the bounded ClaimEntailmentVerifier port, frozen production adapter, deterministic fixture adapter, and fail-closed limits/timeouts.
- [ ] 2.11 **B1:** Implement typed evidence/result-set/lane supports, full-set comparative/rank/count/completeness checks, evidence-backed clarification option facts/omitted counts, fail-closed cited-span entailment for other derived claims, required-intent validation, and deterministic rendering.
- [ ] 2.12 **B1:** Implement truthful `success`, `partial_result`, `no_result`, `retrieval_error`, and `synthesis_error` classification, including clarification/unsupported/cursor reason codes and degradation notes.
- [ ] 2.13 **B1:** Complete canonical-v1 serialization/signature and lossless/lossy compatibility projection; run schema, grounding, support, outcome, API, semantic, and legacy-compatibility gates; record review plus immutable diff/artifact hash and mark B1 Accepted.
- [ ] 2.14 **B2:** Confirm B1 is Accepted before consumer or rollout edits.
- [ ] 2.15 **B2:** Implement `CHAT_GROUNDED_ANSWER_MODE=legacy|shadow|canonical`, external field-presence/renderer matrix, redacted failure-isolated shadow execution, and immediate mode rollback.
- [ ] 2.16 **B2:** Update React and deployed static `/chat` consumers (or explicitly redirect/deprecate the latter) to choose one contract version, render canonical evidence/result/quality/tier metadata, and round-trip `entity_id_hint` with the signed clarification token without auto-selecting `default_id`.
- [ ] 2.17 **B2:** Implement signed-echo canonical feedback with minimized redacted issue metadata and tamper/replay/key tests; prove no raw unauthenticated canonical-response store/read surface was added.
- [ ] 2.18 **B2:** Freeze the privacy-safe shadow sampling frame/window/seed/dedupe/hash before output, then run stratified shadow, actual-route browser, latency, existing-session, feedback, and rollback coverage.
- [ ] 2.19 **B2:** Complete B2 and Slice B verification, obtain independent review, record immutable diff/artifact hashes (and isolated commits only when explicitly authorized), and mark B2/Slice B Accepted before Slice C starts.

## 3. Slice C — Q004/Q017, Natural Type1, and Type2

- [ ] 3.1 Confirm Slice B is Accepted; stop without editing Slice C production scope otherwise.
- [ ] 3.2 **C0:** Write RED professor-profile route/name/domain/endpoint/professor-ID/citation tests for frozen Q004/Q017 and Type1 tests for natural titles, same-title clarification, merge survivor/terminal handling, empty-detail evidence, and local-miss Web-success/empty/failure outcomes/provenance.
- [ ] 3.3 **C0:** Normalize organization/location context separately from professor names and align classifier, query type, domain, and retrieval endpoint.
- [ ] 3.4 **C0:** Implement wrapper-safe exact-title parsing, canonical-ID resolution, and separately typed/provenanced Web fallback behind `CHAT_C0_IDENTITY_TYPE1_MODE` without fabricating local IDs.
- [ ] 3.5 **C0:** Run Q004/Q017 and Type1 local-hit/local-miss outcome/provenance, citation, semantic, latency, regression, Web-fallback rollback, and independent review gates; record immutable diff/artifact hash and mark C0 Accepted.
- [ ] 3.6 **C1:** Confirm C0 is Accepted before Type2 implementation.
- [ ] 3.7 **C1:** Write RED Type2 tests for exact active-state mapping, all/list pagination, year/range, recent, topic intersection, representative ranking, and paper-aware synthesis.
- [ ] 3.8 **C1:** Implement typed Type2 predicates and materialized-result-set pagination behind `CHAT_C1_TYPE2_PLANNER_MODE`, with default 20/max 50 and versioned SQL `paper-title-sort-v1` year/citation/title/ID order over all active verified links.
- [ ] 3.9 **C1:** Define PaperTopicSearch port/current-provider/test adapters, then implement null-year/recent/N-year semantics, canonical-ID intersection, and citation/year/title/ID representative ranking with default 10/max 20.
- [ ] 3.10 **C1:** Wire the Type2 paper page and pagination metadata through canonical evidence and paper-list synthesis; cover more-than-one-page authors and low-ranked target papers.
- [ ] 3.11 **C1:** Run Type2 predicate/pagination/topic-port, citation, semantic, zero-regression, latency, port fallback/rollback, and independent review gates; record immutable diff/artifact hash and mark C1 Accepted.
- [ ] 3.12 Complete Slice C verification, record checkpoint hashes (and isolated commits only when explicitly authorized), and mark Slice C Accepted before Slice D starts.

## 4. Slice D — Type4 Hybrid Paper Retrieval

- [ ] 4.1 Confirm Slice C is Accepted; stop without editing Slice D production scope otherwise.
- [ ] 4.2 **D0:** Write RED migration/model/category-alias tests; freeze benchmark-independent category cohort SQL/source snapshot/ID hash/denominator; and preflight retained evidence plus PostgreSQL FTS/trigram plans.
- [ ] 4.3 **D0:** Add the reversible normalized paper-subject migration/model, process the full frozen source-backed cohort or report residuals, version aliases, and add reversible mixed-language lexical indexes.
- [ ] 4.4 **D0:** Freeze the post-substrate derivative snapshot; run migration upgrade/downgrade, source/provenance, query-plan/index rollback, cohort/residual, manifest-drift, and independent review gates; record immutable diff/artifact hash and mark D0 Accepted.
- [ ] 4.5 **D1:** Confirm D0 is Accepted before retrieval implementation.
- [ ] 4.6 **D1:** Write RED parser tests for topic plus year/range, category, and recency constraints, including ambiguous/missing-category degradation.
- [ ] 4.7 **D1:** Write RED retrieval tests for independent dense and local lexical lanes, embedding failure, lexical failure, and truthful degraded outcomes.
- [ ] 4.8 **D1:** Write RED ranking tests proving chunk matches aggregate by canonical `paper_id` before fusion/rerank.
- [ ] 4.9 **D1:** Write RED tests proving active partial-rich candidates are penalized/disclosed but not globally suppressed by ready candidates.
- [ ] 4.10 **D1:** Implement the typed Type4 predicate/trace and candidate planner behind `PAPER_D1_TOPIC_RETRIEVAL_MODE` for all supported structured constraints.
- [ ] 4.11 **D1:** Implement bounded indexed local lexical/FTS candidate retrieval and run it concurrently with dense retrieval where safe.
- [ ] 4.12 **D1:** Normalize candidates, aggregate chunk features/evidence by paper ID, fuse lanes, apply paper-level filters, and rerank once per paper.
- [ ] 4.13 **D1:** Add documented partial-rich quality penalties and title-only eligibility/degradation handling.
- [ ] 4.14 **D1:** Keep local and Web candidates/evidence in separate typed lanes; prevent Web results from satisfying local ID gates.
- [ ] 4.15 **D1:** Add provider/storage boundary fixtures for dense, lexical, rerank, and Web success/failure without mocking retrieval orchestration internals.
- [ ] 4.16 **D1:** Run paired derivative-snapshot outputs, collect two-reviewer/adjudicated sealed-union labels and agreement, then run holdout micro-P@5, citation, semantic, regression, local/Web, p95, p99, and retrieval rollback gates.
- [ ] 4.17 **D1:** Complete D1 and Slice D verification, obtain independent review, record immutable diff/artifact hashes (and isolated commits only when explicitly authorized), and mark D1/Slice D Accepted before Slice E starts.

## 5. Slice E — Company-to-Paper Traversal

- [ ] 5.1 Confirm Slice D is Accepted; stop without editing Slice E production scope otherwise.
- [ ] 5.2 Materialize the Slice A-frozen `retrieval-active-v1` node-state, strong, secondary, unresolved, unverified-paper-edge, and multi-path Type3 fixtures without changing their expected IDs or edge tiers.
- [ ] 5.3 Write RED retrieval and synthesis tests for two-hop company-to-professor-to-paper provenance.
- [ ] 5.4 Implement strong traversal behind `COMPANY_PAPER_TRAVERSAL_MODE` through `link_status=verified` roles with current/former/unknown time disclosure and explicit-current filtering.
- [ ] 5.5 Implement secondary traversal only through the latest company snapshot's `resolution_status=matched` non-null professor IDs and preserve the secondary label.
- [ ] 5.6 Apply the exact `retrieval-active-v1` company/professor/paper mapping and verified second-hop edge; exclude candidate/unresolved/rejected/merged/inactive paths.
- [ ] 5.7 Implement default-20/max-50 stable unique-paper pagination and strong-first per-paper path totals/first-10/path continuation while preserving every edge identity in canonical evidence.
- [ ] 5.8 Add API/generation tests proving the answer discloses secondary relationships and never upgrades them to verified roles.
- [ ] 5.9 Produce the read-only production relationship coverage report and explicitly label mechanism-only versus production-covered status with remediation owner/worklist.
- [ ] 5.10 Run Type3 retrieval, pagination/path-provenance, citation, semantic, zero-regression, and retrieval p95/p99 gates.
- [ ] 5.11 Complete Slice E verification, obtain independent review, record an immutable diff/artifact hash (and an isolated commit only when explicitly authorized), and mark it Accepted before Slice F starts.

## 6. Slice F — Embedding Ledger, Data Lanes, and Parity

- [ ] 6.1 Confirm Slice E is Accepted; stop without editing Slice F production scope otherwise.
- [ ] 6.2 Freeze the sole `index_eligibility` readiness predicate plus separate non-admitting `enrichment_lane_membership` rule versions and snapshot worklists for active needs-enrichment, partial title-only, partial-rich/ready parity, needs-review audit, and terminal exclusions.
- [ ] 6.3 Write RED tests for stale non-authoritative eligibility observations, content/chunker/model/index drift, partial chunk writes, terminal transitions, equal-paper-count/different-chunk parity, unverifiable vector tuples, and resume.
- [ ] 6.4 Add a reversible migration and validated models for per-paper audit ledger, both rule-version observations, exact chunk manifests/version metadata, and attempt history without creating a second readiness authority.
- [ ] 6.5 Implement recomputed rule-versioned eligibility observations, source/chunk manifest hashes, chunker/schema/model/index tuples, full-manifest confirmed success, and retryable failure recording.
- [ ] 6.6 Implement two-level desired paper/chunk computation and actual Milvus/linked-sidecar inspection with missing, unexpected, stale, conflicting, unverifiable, and failed reports.
- [ ] 6.7 Implement checkpointed, idempotent, resumable lane execution that skips current tuples and never auto-promotes needs-review records.
- [ ] 6.8 Implement dry-run plans, bounded mutation batches, confirmed-write checkpoints, terminal cleanup/quarantine policy, and recorded index-alias rollback.
- [ ] 6.9 Run migration upgrade/downgrade, storage integration, no-provider-call idempotency, interrupted replay, and dry-run safety tests.
- [ ] 6.10 Execute an approved non-production bounded rehearsal and prove distinct-paper plus exact chunk-manifest/version parity or retain a machine-readable failure worklist.
- [ ] 6.11 Produce a read-only active-production paper/chunk parity and residual-lane report; label production parity/backfill/promotion pending unless an explicitly authorized production run proves them.
- [ ] 6.12 Re-run frozen paper retrieval, citation, semantic, zero-regression, p95/p99, and index rollback gates on the candidate index.
- [ ] 6.13 Complete Slice F verification, obtain independent review, record an immutable diff/artifact hash (and an isolated commit only when explicitly authorized), and mark it Accepted before any production promotion.

## 7. Epic Acceptance and Cutover

- [ ] 7.1 Confirm all six slices are Accepted and their immutable diff/artifact hashes, any explicitly authorized commits, raw artifacts, review decisions, and rollback checkpoints are linked from the Epic verification evidence.
- [ ] 7.2 Run the full frozen manifest and all 100 classifier rows with type/domain/normalized name-or-topic/endpoint gates, independent semantic judging, repeated live P0 stability, and saved adjudications.
- [ ] 7.3 Demonstrate Type1/Type2/Q004/Q017 100% hard gates, Type3 exact path/tier and citation gates, Type4 Precision@5 at least 85%, P0 semantics 100%, remaining semantics at least 90%, zero unsupported material claims, and zero frozen-case regression.
- [ ] 7.4 Under the Slice A-frozen protocol and at least 100 measured observations per required bucket, demonstrate retrieval p95/p99 at most 6/12 seconds, synthesis-on p95/p99 at most 15/30 seconds, and the required timeout/error rates.
- [ ] 7.5 Review shadow diffs and operational evidence, run the atomic reverse-dependency rollback matrix and invalidation injection, approve canonical cutover explicitly, and retain every planner/index/legacy control for the full observation window.
- [ ] 7.6 After their linked canonical gates pass, accept each predecessor only as superseded historical evidence and archive it with `openspec archive --skip-specs`; never migrate its broad/overlapping delta into the main specs.
- [ ] 7.7 Verify `make-partial-papers-retrievable` as the Accepted eligibility/snippet dependency, record its D3 task as superseded by Slice F rather than measured, and normally archive it with spec migration when those accepted deltas are canonically represented.
- [ ] 7.8 Keep `sigs-official-publications-to-paper-domain` normal archive blocked until Task 5.20 plus C0/D1 align exact-title identity partials and ready+active-partial-rich topic competition; do not use `--skip-specs` for its unique ingest capability.
- [ ] 7.9 Update Epic acceptance, verification, change log, portfolio, ledger, and source/agent links; obtain final review before archive consideration.
