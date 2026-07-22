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
- [x] 2.7 Add the versioned claim-level case-contract schema and migrate applicable workbook/PRD/challenge turns to required/forbidden claims/entities, allowed variants, source snapshots, as-of, enumeration policy, and observable stage oracles; retain reference prose as non-normative review context.
- [ ] 2.8 Validate hard per-case outcomes, snapshot/version integrity, evidence-bounded LLM judging, and human review; independently review/accept S2C before S8 or S9 uses the corpus as an acceptance oracle.

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
- [x] 5.2 Implement append-only field/relationship assertions and reproducible canonical decisions with evidence, policy/model version, confidence, rationale, and conflict state.
- [x] 5.3 Add RED identity scenarios for strong-identifier merge, cross-format LLM decision, same-name separation, mistaken-merge split, and recovery lineage.
- [x] 5.4 Implement reversible offline canonical identity resolution and source-identity mapping without pre-launch ID compatibility constraints; query/answer paths remain read-only and may only emit identity-review gaps.
- [x] 5.5 Implement proportional temporal semantics for observation/publication/event time and naturally changing validity intervals.
- [x] 5.6 Verify deterministic/recorded-fake LLM decisions, review queues, reversal, and current/history projections; review/accept the slice.
- [x] 5.7 Introduce one precision-preserving temporal value contract for date-only and instant validity across assertions, current selections, typed sub-objects, hashes, PostgreSQL, and restart reconstruction; implement `explicit-calendar-v1` so cross-precision comparison requires caller-supplied calendar/timezone context and otherwise returns `indeterminate`; rerun the affected S5 contract/persistence matrix and accept S5G before Task 6.3 resumes.

## 6. Typed Domains, Relationships, Inclusion, and Eligibility

- [x] 6.1 Derive and freeze the typed Professor, Company, Paper, Patent field/sub-object and relationship catalog from authoritative PRDs in the verification evidence.
- [x] 6.2 Add RED domain inclusion scenarios for approved Professor seeds, roster-anchored Papers, approved Patent exports, Company skeleton batches, and validated incremental Shenzhen Companies.
- [x] 6.3 After Task 5.7 is Accepted, implement typed domain current projections and inclusion-policy adapters over retained assertions/identities without coercing date-only validity to an instant.
- [x] 6.4 Add RED relationship scenarios across identity/lifecycle, organization/role, scholarly output, intellectual property, Company business/product/event, taxonomy/topic/geography, and evidence/lineage families.
- [x] 6.5 Implement the extensible typed relationship catalog, assertions, decisions, direction/role/time/state semantics, and cross-domain integrity.
- [x] 6.6 Add RED path-eligibility scenarios proving partial exact/traversal reach, soft quality signals, and named hard exclusions for every published path.
- [x] 6.7 Implement versioned inclusion and path-eligibility policies with limitations/gap output rather than one global `ready` gate.
- [x] 6.8 Verify per-domain/relationship coverage and sibling invariants on the bounded candidate; review/accept the slice.
- [x] 6.9 Add RED catalog/interface scenarios for internal role-neutral Person identities/projections, unresolved person references that create no Person identity, internal Technology concepts/routes with non-adoption discussion-or-mention/claimed-adoption/demonstrated-use distinctions, exact relationship-type versioning, public-domain versus internal-auxiliary manifest scope, and the invariant that Professor, Company, Paper, and Patent remain the only public inclusion domains; Product capability remains answer-scoped.
- [x] 6.10 Implement the S6R catalog/shared-identity/internal-reference-projection and manifest-scope reconciliation behind a separate deep module for Person and Technology reference knowledge; keep four-domain `DomainProjection`/inclusion unchanged, require accepted four-domain evidence anchors, and add no canonical Product-capability relation or S7 publication/index persistence.
- [x] 6.11 Re-run the complete S6 catalog/domain/relationship/identity/path matrix, source-hash binding, migration/write-safety checks if persistence changes, and independently review/accept S6R before S7 builds publication/index projections.

## 7. Candidate Releases and Versioned Milvus Publication

- [x] 7.1 After S6R is Accepted, add RED release tests for isolated candidate failure, immutable manifests, deterministic public/auxiliary projection hashes, parity mismatch, atomic promotion, and rollback.
- [x] 7.2 Implement `KnowledgeBuild` candidate construction and release manifests over named evidence, policy, parser, model, and decision versions.
- [x] 7.3 After S6R is Accepted, implement typed public-domain projections plus internal release-scoped Person/Technology auxiliary projections from one candidate release without changing active pointers.
- [x] 7.4 Add RED index tests for release/object/content/version metadata, full-rebuild admission, missing/extra/stale/cross-release points, Professor identity/research split semantics, and the no-fifth-public-domain boundary for internal Person/Technology indexes.
- [x] 7.5 Implement versioned Milvus/public lookup projection builders, including internal Person/Technology auxiliaries, and perform the first full isolated Canonical V2 index rebuild.
- [x] 7.6 Implement deterministic canonical/published/index reconciliation and `ReleasePublication.verify/promote/rollback` with explicit authorization.
- [x] 7.7 Verify rollback and DB/index parity on an isolated candidate; review/accept the release/index slice without promoting any production-like target.

## 8. Evidence-first Query Orchestration

- [ ] 8.1 After S2C/S6R are Accepted, add fixture-only RED trace-replay scenarios for A-G behavior, safety guidance, confidence-gated ambiguity, enumeration policy, Person typed-filter retrieval, Technology alias/route comparison, deterministic protected slots, contextual/alias/domain/Web rewrites, invalid-plan rejection, and the parameterized institution-slot matrix; calibrate and freeze the versioned ambiguity evidence/confidence/margin policy against reviewed claim-level cases before GREEN.
- [x] 8.2 After S7 is Accepted, implement typed query understanding, protected-slot/institution and internal Person/Technology resolution, enumeration policy, confidence-gated ambiguity, safety response policy, assessment intent/user-criteria capture, multi-view rewriting, and schema-validated LLM retrieval planning; do not build the evidence-dependent AssessmentFrame here and do not use institution topic-stopword enumeration.
- [x] 8.3 After S7 is Accepted, implement `KnowledgeRead.execute` with concurrent exact/structured, lexical, vector, relationship, internal Person/Technology auxiliary, and current-Web adapters, content-addressed bounded Web evidence snapshots, typed Web entity handles, and full candidate traceability.
- [x] 8.4 Add RED scenarios proving Universal Web runs for all information-retrieval requests, skips refusal/blocking-clarification/control/safety-guidance input by default, permits only explicit bounded official-source safety lookup, and degrades safely on provider failure.
- [x] 8.5 Implement identity-aware fusion, Web-handle snapshot/tamper/expiry/resolution lineage, evidence aggregation, deterministic constraints, confidence/margin ambiguity decisions, and structured LLM late reranking without blanket early quality exclusion.
- [x] 8.6 Add RED sufficiency/retry scenarios for supported, conflicting, and missing material question parts, answer-scoped Product capability, all three enumeration modes, false exhaustiveness, and time/call/cost exhaustion.
- [x] 8.7 Implement structured evidence-sufficiency decisions, enumeration accounting, typed continuation metadata, and targeted bounded supplemental retrieval.
- [ ] 8.8 Verify route/domain/internal-reference recall, precision, rank, Person filter and Technology route semantics, institution-slot/pure-topic invariants, calibrated ambiguity/safety/enumeration/Web-handle lifecycle trace replay, Web provenance/snapshots, latency, and cost against frozen claim-level gates; review/accept the query slice.

## 9. Grounded Progressive Answers and Sessions

- [x] 9.1 Add RED scenario coverage for material claim-evidence mapping, direct Product-capability binding, scoped/as-of Industry Brief route comparison, enumeration coverage reports, local/Web disclosure, conflict display, model-only inference labels, and deterministic fallback.
- [x] 9.2 Implement structured claim selection/citation and `KnowledgeAnswer.answer` over validated evidence sets.
- [x] 9.3 Add RED evidence-based-assessment scenarios for technical strength, competitiveness, maturity, and expert-standing questions with user-prescribed and LLM-selected per-turn dimensions.
- [x] 9.4 Implement the lightweight structured AssessmentFrame with per-dimension evidence, conclusion/insufficiency, uncertainty, and conditional answer-scoped synthesis; add no global policy registry or canonical score.
- [x] 9.5 Add RED multi-turn scenarios for canonical IDs and Web entity handles, anchors, displayed result sets, protected constraints, typed traversals, enumeration coverage, ambiguity/clarification selection, conditional ContinuationOffer, and topic switches.
- [x] 9.6 Implement release-aware typed-handle session state, user-directed progressive relationship exploration, confidence-gated interpretation/clarification rendering, and bounded safety-guidance rendering.
- [x] 9.7 Implement conditional structured ContinuationOffer with at most three validated executable options for the accepted trigger reasons; validate zero unsupported factual claims and correct next-turn binding.
- [ ] 9.8 Verify claim support/completeness, coverage honesty, Person-oriented and Technology/Industry-Brief user effects, Product-capability non-propagation, context/handle correctness, safety/ambiguity/continuation behavior, LLM degradation, TTFT/progress, and response contracts against claim-level gates; review/accept the answer slice.

## 10. Knowledge-gap Feedback and Operations

- [x] 10.1 Add RED gap scenarios for no-result, insufficient evidence, repeated Web dependence, recurring answer-scoped Product-capability demand, missing relationship, user feedback, benchmark failure, and index parity.
- [x] 10.2 Implement typed knowledge-gap creation, LLM-assisted classification with confidence/review state, demand/PRD impact, and owner/remediation proposal.
- [x] 10.3 Implement gap-to-offline recollection/enrichment/build linkage and require accepted release evidence before canonical gaps close.
- [x] 10.4 Migrate admin review and data-quality operations to Canonical V2 gaps, assertions, decisions, releases, and provenance.
- [x] 10.5 Verify that online Web/LLM evidence never writes directly to active canonical/Milvus; review/accept the operations slice.

## 11. Consumer Migration and Legacy Removal

- [x] 11.1 Migrate chat HTTP, admin APIs/UI data access, domain writers, retrieval callers, and scripts to the new deep module interfaces.
- [x] 11.2 Replace implementation-coupled legacy tests with interface, scenario, trace-replay, real Postgres, and index-adapter tests while retaining valid PRD scenario evidence through the accepted claim-level case contracts rather than prose gold.
- [x] 11.3 Remove or quarantine obsolete V042-only writers, direct chat SQL, fixed-handler routing, legacy global readiness, old collection-name assumptions, and direct active-index mutation paths.
- [x] 11.4 Run targeted and broad repository checks only against explicit disposable/candidate targets; record unrelated or intentionally retired failures separately.
- [x] 11.5 Review/accept the consumer migration slice and confirm no accepted behavior depends on a removed pre-launch implementation detail.

## 12. Final Candidate Acceptance and Handoff

- [ ] 12.1 Build the complete isolated Canonical V2 candidate from inventoried recovery/historical sources plus approved targeted recollection.
- [ ] 12.2 Run all hard per-case invariants and multidimensional domain/path/query/answer/Web/parity/latency/cost gates against the accepted claim-level regression and challenge versions.
- [ ] 12.3 Produce recovery coverage, unresolved gap, source lineage, decision, release, index, rollback, and benchmark evidence in `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- [ ] 12.4 Run `openspec validate rebuild-canonical-v2-knowledge-platform --strict` and repository contract/lint/type/test checks required by the verification contract.
- [ ] 12.5 Obtain independent review and user acceptance of the isolated candidate.
- [ ] 12.6 Keep original sources frozen and request separate explicit authorization for any production-like cutover, archive, or destructive cleanup.
