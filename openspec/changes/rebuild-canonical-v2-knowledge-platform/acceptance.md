# Acceptance: rebuild-canonical-v2-knowledge-platform

This Epic is accepted only through independently accepted slices. OpenSpec artifact completeness is
not implementation acceptance. The original `pgtest` and original Milvus are forbidden write
targets throughout this change.

## 0. Stage gates

- [x] The proposal, design, delta specs, tasks, acceptance, and verification contract pass strict
      validation and user review.
- [x] The ADR-013-ADR-022 reconciliation across proposal/design/specs/tasks/acceptance/verification
      passes strict validation, two independent review rounds with zero open Critical/Important
      findings, and explicit user review through the recorded per-decision selections plus the
      instruction to continue before S2C or S6R becomes Ready.
- [x] Slice S1 (database target safety) is Accepted before any broad migration suite or candidate
      schema/replay write.
- [x] Slice S2 (read-only baseline) freezes `acceptance-thresholds.json` and corpus manifests before
      feature/data implementation slices become Ready.
- [x] Slice S2B/task 2.6 independently restore-verifies complete source backups and is Accepted
      before task 3.2 or any Canonical V2 schema, landing, canonical, publication, or index write.
- [ ] Slice S2C/tasks 2.7-2.8 migrates applicable cases to machine-readable claim-level contracts and
      is Accepted before S8/S9 uses the corpus as an acceptance oracle.
- [x] Slice S6R/tasks 6.9-6.11 reconciles internal Person/Technology catalog, identity, projection,
      release, and no-fifth-public-domain boundaries and is Accepted before S7 starts.
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
- [ ] Before S8/S9 acceptance execution, S2C supersedes prose/key-point pass/fail semantics with
      accepted claim-level contracts while retaining the historical S2 material as review context.
- [x] The challenge corpus is separately versioned and includes reviewed badcases and controlled
      alias/constraint/relation/context variations.
- [x] Every gold expectation is human-reviewed; unreviewed same-model generation/judging cannot
      establish gold truth.
- [ ] Every applicable accepted turn has a versioned machine-readable contract for required/forbidden
      claims/entities, allowed variants, source snapshots, as-of, enumeration policy, and observable
      stage outcomes; reference prose/free-text key points are non-normative.
- [ ] Required/forbidden identity, unsupported material claim, false exhaustiveness, protected-slot,
      and session-transition requirements fail per case and cannot be averaged away.
- [ ] Dynamic-fact/source snapshots and contract versions are content-addressed, human-reviewed, and
      replayable; evidence-bounded LLM-judge decisions identify their contract/snapshot inputs.

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

- [x] Professor, Company, Paper, and Patent projections satisfy their authoritative PRD field,
      inclusion, and typed-subobject contracts.
- [x] Every material current field/relationship traces to retained source assertion(s) and a
      canonical decision; selecting a value does not delete competing assertions.
- [ ] Reviewed identity gold has zero wrong-identity merges/splits and zero cross-domain references
      to the wrong real-world object.
- [x] Strong identifier, same-name separation, cross-format LLM decision, reversible merge/split,
      source conflict, and temporal-history scenarios pass.
- [x] Date-only and instant validity preserve their source precision through assertions, current
      selections, typed projections, hashes, PostgreSQL, and restart; no date is fabricated as UTC
      midnight. `explicit-calendar-v1` uses only caller-supplied calendar/timezone context, returns
      `indeterminate` without it, and never treats an overlapping instant as exact date equality.
- [ ] Normalization, candidate identity recall, deterministic rules, structured LLM adjudication,
      human review, and merge/split publication run only in versioned offline builds; query/answer
      paths create zero canonical identity/source-mapping mutations.
- [x] Every registered relationship type defines direction, roles, evidence, state, and time
      semantics; all relation endpoints exist and match allowed types.
- [x] Derived and session relations are not asserted as source-grounded canonical facts.
- [x] Inclusion/path eligibility scenarios prove partial exact/traversal reach and independent
      semantic/recommendation/ranking admission.
- [x] Ordinary incomplete enrichment is never a hard-exclusion reason; every hard exclusion cites a
      named invariant and decision evidence.
- [x] Professor-attribution rejection does not reject Paper existence without an independent Paper
      identity decision.
- [x] Internal Person identity/projection shares only resolved Professor, Company-personnel, author,
      and inventor evidence; unresolved names are not forced together and no fifth public Person
      inclusion domain exists.
- [x] Internal Technology concept/route identities preserve aliases, definitions, hierarchy,
      source/time, and typed mention/adoption/use distinctions; Industry Briefs remain derived output.
- [x] Company capability and Product remain separate canonical surfaces; no canonical Product-
      capability relation is introduced and Company capability never entails a Product claim.

## 5. Release and Milvus acceptance

- [x] Candidate manifest identifies all source, parser, policy, model, decision, object,
      relationship, eligibility, publication, and expected-index versions/counts/hashes.
- [x] Candidate failure cannot alter active canonical/published/index pointers.
- [x] Initial Canonical V2 indexes are built fully in new versioned projections.
- [x] Professor identity/research projections preserve intent-specific content without fixed legacy
      collection-name/payload obligations.
- [x] Internal Person/Technology lookup/vector projections are release-scoped, content-bound
      auxiliaries anchored to public-domain evidence and never become independently promoted public
      domain populations.
- [x] Expected vs actual eligible entity/chunk IDs, counts, content hashes, projection versions,
      embedding model, and release IDs have exact parity; unexplained missing/extra/stale/cross-
      release points are zero.
- [x] Promotion is impossible without accepted verification and explicit authorization.
- [x] Isolated promotion/rollback rehearsal restores one internally consistent prior release without
      mutating landing evidence.

## 6. Query orchestration acceptance

S8C accepted the release-bound runtime implementation for Tasks 8.3, 8.5, and 8.7 at `59/80`.
The checkboxes below remain aggregate Task 8.8 gates and are intentionally not inferred from this
runtime-only acceptance; S2C-reviewed calibration is still required.

- [ ] A-G behavior scenarios pass while validated plans may combine supported retrieval lanes.
- [ ] List plans declare `exhaustive_bounded`, `required_members`, or `representative` with scope,
      as-of, universe/required members, budgets, and continuation; Top-K never implies exhaustive.
- [ ] Confidence-gated ambiguity has zero protected-constraint auto-selections, reports policy/
      evidence/margin state, uses a reviewed/calibrated versioned policy, answers one dominant
      candidate with an interpretation notice and bounded switch when applicable, and otherwise
      clarifies.
- [ ] Local safety/compliance questions use bounded safety guidance with zero venue allegations,
      discovery/evasion assistance, or accidental general-Web invocation; explicit official lookup is
      official-source-only and snapshot-grounded.
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
- [ ] Internal Person retrieval passes accepted education/Company-role/geography cases through
      resolved evidence-backed projections, keeps unresolved same-name references separate, and
      creates no public Person inclusion population.
- [ ] Technology alias/route retrieval preserves definition, hierarchy, scope/as-of, and distinct
      non-adoption discussion-or-mention/claimed-adoption/demonstrated-use semantics across
      representative Company/Product/Paper/Patent cases.
- [ ] Every displayed Web-only entity uses a typed session-scoped handle bound to bounded content-
      addressed evidence snapshots and trace/resolution state; URL-as-domain-ID occurrences are zero.
- [ ] Web-handle replay covers later read-only resolution, unresolved traversal, snapshot tampering,
      provider content change, expiry, and URL collision without snapshot replacement, entity merge,
      or online canonical mutation.
- [ ] Universal Web invocation is `100%` for evaluated A/B/C/D/E/G information-retrieval requests
      and `0%` for evaluated refusal, clarification-only, and UI-control inputs.
- [ ] Every accepted Web candidate/claim has auditable source URL, source nature, retrieval time,
      bounded snapshot/content identity, and provider/attempt trace; unsourced material Web claims are
      zero.
- [ ] Web/provider/LLM failure scenarios return supported local/partial results with correct
      limitations and no silent evidence loss.
- [ ] Sufficiency detects material unsupported sub-questions; supplemental retrieval obeys frozen
      time/call/cost budgets and never loops indefinitely.

## 7. Answer and session acceptance

S9I accepted the deterministic answer, assessment, and typed-session implementation for Tasks 9.2,
9.4, and 9.6 at `62/80`. The checkboxes below remain aggregate Task 9.8 gates and are intentionally
not inferred from this implementation-only acceptance; reviewed claim-level/provider/latency
evidence is still required.

- [ ] Unsupported material identity, relationship, capability, role, date, and numeric claims are
      zero in deterministic checks and reviewed acceptance samples.
- [ ] Every material claim has an internal evidence mapping; Web, conflict, and model-only inference
      disclosure scenarios pass.
- [ ] Product capability claims bind direct named-Product evidence; Company-capability propagation,
      inferred status/maturity, and canonical Product-capability relationships are zero.
- [ ] Every list answer reports mode/scope/as-of and checked/eligible/retrieved/displayed, omission,
      unknown, and continuation accounting; false exhaustive claims are zero.
- [ ] Evidence-based assessment scenarios preserve user criteria or expose reasonable LLM-selected
      per-turn dimensions, sourced support, insufficiency/conflict, conditional synthesis, and
      uncertainty; no policy registry or exact dimension list is required unless the case requests it.
- [ ] Industry Brief scenarios expose route definitions/semantics, scope, as-of, local/Web evidence,
      enumeration coverage, conflicts, and limitations; brief text/conclusions create zero canonical
      facts and imply zero unsupported Product capability.
- [ ] Prose-LLM failure can render a deterministic grounded answer from validated claims/evidence.
- [ ] Multi-turn anchor, displayed-set, narrowing, traversal, coverage, ambiguity, and topic-switch
      scenarios meet frozen context thresholds with zero use of retrieved-but-undisplayed members as
      displayed-set referents.
- [ ] Session state distinguishes Canonical IDs from Web entity handles, preserves displayed evidence/
      order/resolution, and blocks unresolved canonical traversal or structured filters.
- [x] Conditional `ContinuationOffer` appears only for accepted triggers, contains at most three
      executable bound options, introduces zero unsupported claims, and selected options transition
      correctly; simple complete answers omit it.
- [ ] Ordinary and complex latency/progress plus provider-call/cost results meet PRD and frozen route
      budgets.

## 8. Feedback and continuous-operation acceptance

S10O accepted the durable operations implementation for Tasks 10.3, 10.4, and 10.5 at `65/80`.
The checkboxes below remain broader final-candidate/operational acceptance evidence and are not
inferred beyond the exact durable lifecycle, admin read model, and online no-write owners accepted
by this slice.

- [ ] No-result, insufficient-evidence, repeated-Web, recurring Product-capability, missing-relation,
      user-feedback, benchmark, and index-parity gaps are typed and traceable to query/answer/release
      evidence.
- [ ] Gap classification distinguishes coverage, identity, freshness/conflict, relationship/reach,
      retrieval precision, context, synthesis, index, and provider ownership.
- [ ] Current-Web/LLM evidence never writes directly into active canonical or Milvus.
- [ ] A canonical gap closes only through an accepted release and scenario evidence demonstrating
      the intended user/operational effect.
- [ ] Operators can prioritize gaps by demand, PRD impact, severity, source availability, and owning
      lane without treating every incomplete field equally.

## 9. Consumer replacement and final candidate

S11C accepted the complete consumer-migration boundary at `70/80`. The first, second, and explicit-
target broad-check items below are closed by exact S11A/S11B reruns, interface/scenario/trace/real-
PostgreSQL/index owners, immutable legacy disposition, and complete failure-ledger reconciliation.
The isolated rebuild, final strict aggregate, and user-acceptance items remain S12-owned.

- [x] Chat HTTP, admin data access, domain writers, retrieval callers, and operational scripts use
      the new deep module interfaces; accepted behavior contains no direct dependency on V042 tables,
      old collection names, fixed handlers, or global readiness.
- [x] Interface/scenario/trace/Postgres/index tests replace implementation-coupled tests while valid
      PRD scenarios and accepted claim-level case contracts remain.
- [ ] Complete isolated rebuild reports source coverage, unresolved gaps, identity/relationship
      decisions, eligibility, release/index parity, rollback, benchmark, latency, and cost.
- [x] All required targeted and broad checks pass against explicit disposable/candidate targets, or
      remaining failures are documented and prevent acceptance when required by the contract.
- [ ] `openspec validate rebuild-canonical-v2-knowledge-platform --strict` exits `0`.
- [ ] Independent review and user acceptance approve the isolated candidate; original sources remain
      frozen pending separate cutover direction.
