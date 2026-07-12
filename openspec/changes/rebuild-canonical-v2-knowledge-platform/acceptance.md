# Acceptance: rebuild-canonical-v2-knowledge-platform

This Epic is accepted only through independently accepted slices. OpenSpec artifact completeness is
not implementation acceptance. The original `pgtest` and original Milvus are forbidden write
targets throughout this change.

## 0. Stage gates

- [x] The proposal, design, delta specs, tasks, acceptance, and verification contract pass strict
      validation and user review.
- [x] Slice S1 (database target safety) is Accepted before any broad migration suite or candidate
      schema/replay write.
- [x] Slice S2 (read-only baseline) freezes `acceptance-thresholds.json` and corpus manifests before
      feature/data implementation slices become Ready.
- [x] Slice S2B/task 2.6 independently restore-verifies complete source backups and is Accepted
      before task 3.2 or any Canonical V2 schema, landing, canonical, publication, or index write.
- [ ] Every later slice has an independently testable/reviewable contract, immutable evidence, and
      Accepted predecessor; no Specified/Candidate slice is used as an accepted dependency.
- [ ] Production-like cutover remains a separate explicit user authorization after final isolated
      candidate acceptance.

## 1. Safety and recovery-source invariants

- [x] Original Postgres and Milvus identities/hashes are recorded; pre/post read-only inventory
      checks match and the original Postgres remains paused.
- [x] Every destructive migration/test/rebuild command uses an explicit target and proves disposable
      or isolated-candidate identity before writes.
- [x] A generic real `DATABASE_URL` cannot override an explicit test/recovery DSN; missing or
      ambiguous target identity fails closed before Alembic or application writes.
- [x] No accepted verification command connects or writes to the original `pgtest` or original
      Milvus file.
- [x] Forensic/historical evidence chain-of-custody hashes remain intact.
- [x] A reviewed backup manifest covers original PostgreSQL, Milvus, WAL/FPI, salvage, and every
      inventoried historical SQLite/JSONL/XLSX/PDF/cache/raw-source family with source/copy identity,
      size, SHA-256, copy run/time, and no hard-link dependence on original bytes.
- [x] Every required backup passes an independent restore/materialization drill in a target distinct
      from source and backup: PostgreSQL identity/revision/schema/count probes, Milvus copy
      schema/collection/count probes, and file/recovery-family hash plus readability/replay probes.
- [x] Any missing family, mismatch, failed recovery probe, or unreviewed backup state rejects task
      3.2 and all later rebuild writes before their first write.

## 2. Threshold and corpus freeze

- [x] `acceptance-thresholds.json` records each metric, population/corpus version, threshold,
      rationale, source (PRD or calibrated), and approval; implementation does not lower it.
- [x] Existing PRD minima remain lower bounds, including intent accuracy `>= 0.90`, applicable
      Top-5 relevance `>= 0.85`, applicable human summary quality `>= 4.0/5.0`, and applicable
      latency/import constraints.
- [x] The frozen regression corpus contains workbook seed scenarios plus PRD-derived exact,
      semantic, structured-filter, relationship, A-G, multi-turn, Web, and assessment families.
- [x] User-confirmed workbook answers and key points are case-specific reference ground truth with
      row-level provenance; they are not generalized into a product-wide answer template or treated
      as the sole acceptance source.
- [x] The challenge corpus is separately versioned and includes reviewed badcases and controlled
      alias/constraint/relation/context variations.
- [x] Every gold expectation is human-reviewed; unreviewed same-model generation/judging cannot
      establish gold truth.

## 3. Evidence landing acceptance

- [x] Every registered artifact has source/copy identity, content hash, size, acquisition time,
      run, and parent lineage where applicable.
- [x] Parser outputs identify artifact, record locator, parser/schema version, parse run, and error;
      a new parser run does not mutate prior outputs.
- [x] A bounded representative matrix covers WAL/FPI partial rows, SQLite, JSONL, XLSX, Milvus copy,
      and recollected response inputs.
- [x] Readable partial fields survive; missing/corrupt fields are quarantined without invented
      placeholders, parents, facts, or evidence.
- [x] Replay count/hash/error summaries match the accepted landing checkpoint.

## 4. Canonical knowledge acceptance

- [ ] Professor, Company, Paper, and Patent projections satisfy their authoritative PRD field,
      inclusion, and typed-subobject contracts.
- [ ] Every material current field/relationship traces to retained source assertion(s) and a
      canonical decision; selecting a value does not delete competing assertions.
- [ ] Reviewed identity gold has zero wrong-identity merges/splits and zero cross-domain references
      to the wrong real-world object.
- [ ] Strong identifier, same-name separation, cross-format LLM decision, reversible merge/split,
      source conflict, and temporal-history scenarios pass.
- [ ] Normalization, candidate identity recall, deterministic rules, structured LLM adjudication,
      human review, and merge/split publication run only in versioned offline builds; query/answer
      paths create zero canonical identity/source-mapping mutations.
- [ ] Every registered relationship type defines direction, roles, evidence, state, and time
      semantics; all relation endpoints exist and match allowed types.
- [ ] Derived and session relations are not asserted as source-grounded canonical facts.
- [ ] Inclusion/path eligibility scenarios prove partial exact/traversal reach and independent
      semantic/recommendation/ranking admission.
- [ ] Ordinary incomplete enrichment is never a hard-exclusion reason; every hard exclusion cites a
      named invariant and decision evidence.
- [ ] Professor-attribution rejection does not reject Paper existence without an independent Paper
      identity decision.

## 5. Release and Milvus acceptance

- [ ] Candidate manifest identifies all source, parser, policy, model, decision, object,
      relationship, eligibility, publication, and expected-index versions/counts/hashes.
- [ ] Candidate failure cannot alter active canonical/published/index pointers.
- [ ] Initial Canonical V2 indexes are built fully in new versioned projections.
- [ ] Professor identity/research projections preserve intent-specific content without fixed legacy
      collection-name/payload obligations.
- [ ] Expected vs actual eligible entity/chunk IDs, counts, content hashes, projection versions,
      embedding model, and release IDs have exact parity; unexplained missing/extra/stale/cross-
      release points are zero.
- [ ] Promotion is impossible without accepted verification and explicit authorization.
- [ ] Isolated promotion/rollback rehearsal restores one internally consistent prior release without
      mutating landing evidence.

## 6. Query orchestration acceptance

- [ ] A-G behavior scenarios pass while validated plans may combine supported retrieval lanes.
- [ ] Exact identifiers, names/titles, dates, geography, negation, set membership, and relation
      direction survive all rewrites/plans with zero protected-slot loss in the frozen corpus.
- [ ] Institution-bearing queries resolve canonical full names and aliases into typed, release-
      scoped institution slots before topic rewriting; query filters and alias rewrites consume one
      accepted, versioned institution catalog.
- [ ] Parameterized institution trace replay covers several institutions by canonical full name and
      alias, ambiguous aliases where applicable, unknown institutions, queries without an
      institution, and institution/topic word overlap, with zero protected-slot loss, false
      canonicalization, or topical-term loss.
- [ ] Every evaluated institution rewrite records the matched source span, resolution state,
      canonical candidate identity or retained unresolved text, catalog/release version, pure
      topic, and resulting lane query/filter.
- [ ] Query orchestration contains no institution-name or alias enumeration in generic topic
      stopwords and no independent alias-to-canonical source consumed by planning or retrieval.
- [ ] Query, rewrite, lane, attempt, provider/model, candidate decision, release, and evidence traces
      are complete for every evaluated answer.
- [ ] Exact/structured, lexical, vector, relationship, and Web lanes meet their per-domain/path
      thresholds in the frozen `acceptance-thresholds.json`.
- [ ] Recall and precision independently pass; no aggregate score masks a failed required dimension.
- [ ] Identity-aware fusion produces one result per real-world identity while preserving local/Web
      evidence contributions.
- [ ] Universal Web invocation is `100%` for evaluated A/B/C/D/E/G information-retrieval requests
      and `0%` for evaluated refusal, clarification-only, and UI-control inputs.
- [ ] Every accepted Web candidate/claim has auditable source URL, source nature, and retrieval time;
      unsourced material Web claims are zero.
- [ ] Web/provider/LLM failure scenarios return supported local/partial results with correct
      limitations and no silent evidence loss.
- [ ] Sufficiency detects material unsupported sub-questions; supplemental retrieval obeys frozen
      time/call/cost budgets and never loops indefinitely.

## 7. Answer and session acceptance

- [ ] Unsupported material identity, relationship, capability, role, date, and numeric claims are
      zero in deterministic checks and reviewed acceptance samples.
- [ ] Every material claim has an internal evidence mapping; Web, conflict, and model-only inference
      disclosure scenarios pass.
- [ ] Evidence-based assessment scenarios expose dimensions, sourced support, conditional synthesis,
      and uncertainty; categorical unsupported verdicts are zero.
- [ ] Prose-LLM failure can render a deterministic grounded answer from validated claims/evidence.
- [ ] Multi-turn anchor, displayed-set, narrowing, traversal, coverage, ambiguity, and topic-switch
      scenarios meet frozen context thresholds with zero use of retrieved-but-undisplayed members as
      displayed-set referents.
- [ ] Suggested followups are drawn only from actual eligible relation availability and introduce
      zero unsupported factual claims.
- [ ] Ordinary and complex latency/progress plus provider-call/cost results meet PRD and frozen route
      budgets.

## 8. Feedback and continuous-operation acceptance

- [ ] No-result, insufficient-evidence, repeated-Web, missing-relation, user-feedback, benchmark,
      and index-parity gaps are typed and traceable to query/answer/release evidence.
- [ ] Gap classification distinguishes coverage, identity, freshness/conflict, relationship/reach,
      retrieval precision, context, synthesis, index, and provider ownership.
- [ ] Current-Web/LLM evidence never writes directly into active canonical or Milvus.
- [ ] A canonical gap closes only through an accepted release and scenario evidence demonstrating
      the intended user/operational effect.
- [ ] Operators can prioritize gaps by demand, PRD impact, severity, source availability, and owning
      lane without treating every incomplete field equally.

## 9. Consumer replacement and final candidate

- [ ] Chat HTTP, admin data access, domain writers, retrieval callers, and operational scripts use
      the new deep module interfaces; accepted behavior contains no direct dependency on V042 tables,
      old collection names, fixed handlers, or global readiness.
- [ ] Interface/scenario/trace/Postgres/index tests replace implementation-coupled tests while valid
      PRD fixtures and reviewed gold expectations remain.
- [ ] Complete isolated rebuild reports source coverage, unresolved gaps, identity/relationship
      decisions, eligibility, release/index parity, rollback, benchmark, latency, and cost.
- [ ] All required targeted and broad checks pass against explicit disposable/candidate targets, or
      remaining failures are documented and prevent acceptance when required by the contract.
- [ ] `openspec validate rebuild-canonical-v2-knowledge-platform --strict` exits `0`.
- [ ] Independent review and user acceptance approve the isolated candidate; original sources remain
      frozen pending separate cutover direction.
