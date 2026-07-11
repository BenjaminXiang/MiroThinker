## 1. Safety, Verification Contract, and Slice Gates

- [x] 1.1 Create `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`, `verification.md`, and independently reviewable slice contracts before production-code edits.
- [x] 1.2 Record the frozen original Postgres/Milvus identities and hashes, isolated candidate targets, forbidden targets, and stop conditions in the verification contract.
- [x] 1.3 Add RED integration coverage proving destructive Alembic/test paths reject missing, ambiguous, or non-disposable target identity and never fall back to a generic real `DATABASE_URL`.
- [x] 1.4 Fix Alembic/test database target selection through an explicit validated target interface and verify upgrade/downgrade only against a disposable database.
- [x] 1.5 Obtain review/acceptance of the safety slice before any broad migration suite, candidate schema write, or recovery replay.

## 2. Read-only Recovery and Acceptance Baseline

- [x] 2.1 Complete the read-only source inventory for forensic salvage, historical SQLite/JSONL/XLSX/files, Milvus copy, and recollection-capable sources with counts and hashes.
- [x] 2.2 Build a reviewed source-to-PRD coverage matrix for Professor, Company, Paper, Patent, relationships, evidence fields, and known workbook/PRD scenario families.
- [x] 2.3 Establish the frozen regression corpus and versioned challenge corpus from workbook seeds, PRD families, reviewed badcases, and controlled variations.
- [x] 2.4 Run the isolated read-only baseline for coverage/reach, Recall@K, Precision@K, ranking, relation paths, answer support, Web provenance, latency, and provider cost.
- [x] 2.5 Freeze numeric thresholds not already fixed by PRD in `acceptance.md` without lowering existing PRD minima or hard invariants.
- [x] 2.6 Create and independently restore-verify content-addressed backups for original PostgreSQL, Milvus, WAL/FPI, salvage, and all inventoried historical SQLite/JSONL/XLSX/PDF/cache/raw-source families; review/accept this gate before task 3.2 or any Canonical V2/landing write.

## 3. Canonical V2 Interfaces and Database Baseline

- [x] 3.1 Add RED interface/contract tests for `EvidenceLanding`, `KnowledgeBuild`, `KnowledgeRead`, `KnowledgeAnswer`, and `ReleasePublication` using typed requests/results and observable outcomes.
- [x] 3.2 After task 2.6 is Accepted, create the clean Canonical V2 migration baseline in a new isolated database with landing, shared knowledge, typed domain, publish, and ops schemas.
- [x] 3.3 Implement shared typed contracts for artifacts, source records/assertions, canonical decisions, identities, relationship types/decisions, policies, gaps, releases, and manifests.
- [x] 3.4 Add schema and migration integration tests for foreign keys, uniqueness, append-only evidence, reversible decisions, release scoping, and rollback.
- [x] 3.5 Review/accept the database/interface foundation before source adapters or domain builders depend on it.

## 4. Immutable Evidence Landing

- [x] 4.1 Add RED replay/chain-of-custody tests for byte identity, parser versioning, partial/corrupt records, and no placeholder fact invention.
- [x] 4.2 Implement `EvidenceLanding` plus source adapters for WAL/FPI salvage, historical structured files/databases, Milvus copy records, and newly collected responses.
- [x] 4.3 Persist content-addressed artifact manifests, parser runs, record locators, errors, and parent/copy lineage without mutating prior evidence.
- [x] 4.4 Replay a bounded representative source matrix into the isolated landing schema and verify hashes/counts/errors against the source inventory.
- [x] 4.5 Review/accept the landing slice and checkpoint its database dump/manifest before canonical construction.

## 5. Assertions, Identity, Fusion, and Temporal Decisions

- [x] 5.1 Add RED contract/scenario coverage for retained competing assertions, deterministic constraints, structured LLM adjudication, unresolved conflicts, and current projections.
- [ ] 5.2 Implement append-only field/relationship assertions and reproducible canonical decisions with evidence, policy/model version, confidence, rationale, and conflict state.
- [ ] 5.3 Add RED identity scenarios for strong-identifier merge, cross-format LLM decision, same-name separation, mistaken-merge split, and recovery lineage.
- [ ] 5.4 Implement reversible offline canonical identity resolution and source-identity mapping without pre-launch ID compatibility constraints; query/answer paths remain read-only and may only emit identity-review gaps.
- [ ] 5.5 Implement proportional temporal semantics for observation/publication/event time and naturally changing validity intervals.
- [ ] 5.6 Verify deterministic/recorded-fake LLM decisions, review queues, reversal, and current/history projections; review/accept the slice.

## 6. Typed Domains, Relationships, Inclusion, and Eligibility

- [ ] 6.1 Derive and freeze the typed Professor, Company, Paper, Patent field/sub-object and relationship catalog from authoritative PRDs in the verification evidence.
- [ ] 6.2 Add RED domain inclusion scenarios for approved Professor seeds, roster-anchored Papers, approved Patent exports, Company skeleton batches, and validated incremental Shenzhen Companies.
- [ ] 6.3 Implement typed domain current projections and inclusion-policy adapters over retained assertions/identities.
- [ ] 6.4 Add RED relationship scenarios across identity/lifecycle, organization/role, scholarly output, intellectual property, Company business/product/event, taxonomy/topic/geography, and evidence/lineage families.
- [ ] 6.5 Implement the extensible typed relationship catalog, assertions, decisions, direction/role/time/state semantics, and cross-domain integrity.
- [ ] 6.6 Add RED path-eligibility scenarios proving partial exact/traversal reach, soft quality signals, and named hard exclusions for every published path.
- [ ] 6.7 Implement versioned inclusion and path-eligibility policies with limitations/gap output rather than one global `ready` gate.
- [ ] 6.8 Verify per-domain/relationship coverage and sibling invariants on the bounded candidate; review/accept the slice.

## 7. Candidate Releases and Versioned Milvus Publication

- [ ] 7.1 Add RED release tests for isolated candidate failure, immutable manifests, deterministic projection hashes, parity mismatch, atomic promotion, and rollback.
- [ ] 7.2 Implement `KnowledgeBuild` candidate construction and release manifests over named evidence, policy, parser, model, and decision versions.
- [ ] 7.3 Implement typed published projections from one candidate release without changing active pointers.
- [ ] 7.4 Add RED index tests for release/object/content/version metadata, full-rebuild admission, missing/extra/stale/cross-release points, and Professor identity/research split semantics.
- [ ] 7.5 Implement versioned Milvus projection builders and perform the first full isolated Canonical V2 index rebuild.
- [ ] 7.6 Implement deterministic canonical/published/index reconciliation and `ReleasePublication.verify/promote/rollback` with explicit authorization.
- [ ] 7.7 Verify rollback and DB/index parity on an isolated candidate; review/accept the release/index slice without promoting any production-like target.

## 8. Evidence-first Query Orchestration

- [ ] 8.1 Add RED trace-replay scenarios for A-G behavior semantics, deterministic protected slots, contextual/alias/domain/Web rewrites, and invalid-plan rejection.
- [ ] 8.2 Implement typed query understanding, protected-slot extraction, multi-view rewriting, and schema-validated LLM retrieval planning.
- [ ] 8.3 Implement `KnowledgeRead.execute` with concurrent exact/structured, lexical, vector, relationship, and current-Web adapters and full candidate traceability.
- [ ] 8.4 Add RED scenarios proving Universal Web runs for all information-retrieval requests, skips refusal/clarification/control input, and degrades safely on provider failure.
- [ ] 8.5 Implement identity-aware fusion, evidence aggregation, deterministic constraints, and structured LLM late reranking without blanket early quality exclusion.
- [ ] 8.6 Add RED sufficiency/retry scenarios for supported, conflicting, and missing material question parts plus time/call/cost exhaustion.
- [ ] 8.7 Implement structured evidence-sufficiency decisions and targeted bounded supplemental retrieval.
- [ ] 8.8 Verify route/domain recall, precision, rank, trace replay, Web provenance, latency, and cost against frozen gates; review/accept the query slice.

## 9. Grounded Progressive Answers and Sessions

- [ ] 9.1 Add RED scenario coverage for material claim-evidence mapping, local/Web disclosure, conflict display, model-only inference labels, and deterministic fallback.
- [ ] 9.2 Implement structured claim selection/citation and `KnowledgeAnswer.answer` over validated evidence sets.
- [ ] 9.3 Add RED evidence-based-assessment scenarios for technical strength, competitiveness, maturity, and expert-standing questions.
- [ ] 9.4 Implement evidence-based assessment with explicit dimensions, conditional conclusions, and uncertainty.
- [ ] 9.5 Add RED multi-turn scenarios for anchors, displayed result sets, protected constraints, typed traversals, coverage statements, and topic switches.
- [ ] 9.6 Implement release-aware session state and user-directed progressive relationship exploration.
- [ ] 9.7 Implement followup suggestions only from actual eligible relation availability and validate that suggestions introduce no unsupported factual claims.
- [ ] 9.8 Verify claim support/completeness, context correctness, progressive behavior, LLM degradation, TTFT/progress, and response contracts; review/accept the answer slice.

## 10. Knowledge-gap Feedback and Operations

- [ ] 10.1 Add RED gap scenarios for no-result, insufficient evidence, repeated Web dependence, missing relationship, user feedback, benchmark failure, and index parity.
- [ ] 10.2 Implement typed knowledge-gap creation, LLM-assisted classification with confidence/review state, demand/PRD impact, and owner/remediation proposal.
- [ ] 10.3 Implement gap-to-offline recollection/enrichment/build linkage and require accepted release evidence before canonical gaps close.
- [ ] 10.4 Migrate admin review and data-quality operations to Canonical V2 gaps, assertions, decisions, releases, and provenance.
- [ ] 10.5 Verify that online Web/LLM evidence never writes directly to active canonical/Milvus; review/accept the operations slice.

## 11. Consumer Migration and Legacy Removal

- [ ] 11.1 Migrate chat HTTP, admin APIs/UI data access, domain writers, retrieval callers, and scripts to the new deep module interfaces.
- [ ] 11.2 Replace implementation-coupled legacy tests with interface, scenario, trace-replay, real Postgres, and index-adapter tests while retaining valid PRD fixtures/gold evidence.
- [ ] 11.3 Remove or quarantine obsolete V042-only writers, direct chat SQL, fixed-handler routing, legacy global readiness, old collection-name assumptions, and direct active-index mutation paths.
- [ ] 11.4 Run targeted and broad repository checks only against explicit disposable/candidate targets; record unrelated or intentionally retired failures separately.
- [ ] 11.5 Review/accept the consumer migration slice and confirm no accepted behavior depends on a removed pre-launch implementation detail.

## 12. Final Candidate Acceptance and Handoff

- [ ] 12.1 Build the complete isolated Canonical V2 candidate from inventoried recovery/historical sources plus approved targeted recollection.
- [ ] 12.2 Run all hard invariants and multidimensional domain/path/query/answer/Web/parity/latency/cost gates against frozen regression and challenge versions.
- [ ] 12.3 Produce recovery coverage, unresolved gap, source lineage, decision, release, index, rollback, and benchmark evidence in `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- [ ] 12.4 Run `openspec validate rebuild-canonical-v2-knowledge-platform --strict` and repository contract/lint/type/test checks required by the verification contract.
- [ ] 12.5 Obtain independent review and user acceptance of the isolated candidate.
- [ ] 12.6 Keep original sources frozen and request separate explicit authorization for any production-like cutover, archive, or destructive cleanup.
