## ADDED Requirements

### Requirement: A-G remains the product behavior taxonomy

The system SHALL classify and evaluate exact lookup, semantic narrowing, conversational traversal,
panoramic aggregation, knowledge synthesis, refusal, and ambiguity under the existing A-G behavior
semantics. A-G SHALL guide interaction policy but SHALL NOT restrict execution to one hard-coded
retrieval handler.

#### Scenario: Cross-domain query needs several lanes
- **WHEN** an A-G-classified query requires structured local facts, a relationship traversal, and
  current Web evidence
- **THEN** the validated plan may execute all required lanes
- **AND** the response still satisfies the classified A-G interaction behavior

### Requirement: Local safety questions use a narrow safety-guidance policy

Recognized local safety/compliance reminder requests SHALL use a `safety_guidance` response policy
distinct from ordinary F refusal and from information retrieval. The default policy SHALL NOT run
general Web search or identify/speculate about illegal venues, districts, businesses, or venue
categories. It MAY provide brief lawful risk advice and official help/reporting direction. An
explicit request for current official contact/policy information MAY use a bounded official-source-
only lookup.

#### Scenario: User asks which local illegal venues to avoid
- **WHEN** the request has a legitimate local safety/compliance intent
- **THEN** the plan selects safety guidance rather than general Web retrieval or a venue list
- **AND** the answer does not provide allegations, discovery assistance, or enforcement-evasion detail

### Requirement: Entity ambiguity uses an evidence and margin gate

The system SHALL apply a versioned domain-aware evidence floor, confidence threshold, lead margin,
and protected-constraint checks to ambiguous entity candidates. Model self-confidence alone SHALL NOT
clear the gate. Exactly one dominant candidate MAY produce a non-blocking interpreted answer;
that answer SHALL disclose the selected interpretation and provide a bounded way to switch when a
viable alternative remains. Otherwise the turn SHALL be clarification-only.

#### Scenario: Two Professors share a name
- **WHEN** neither candidate clears the accepted evidence/lead-margin policy
- **THEN** the plan returns blocking ambiguity with evidenced candidate discriminators
- **AND** it does not produce a primary Professor answer before selection

#### Scenario: One candidate is clearly dominant
- **WHEN** exactly one candidate clears the accepted evidence, confidence, margin, and protected-
  constraint policy
- **THEN** the turn may answer for that candidate with an interpretation notice
- **AND** any viable alternative is exposed only as a bounded switch option rather than silently
  discarded

### Requirement: Explicit constraints are parsed and protected deterministically

The system SHALL deterministically extract exact identifiers, quoted or explicit names/titles,
dates/years, geography, negation, requested relationship direction, and other supported hard
constraints before LLM planning. No query rewrite or LLM plan SHALL silently alter or omit a
protected constraint.

#### Scenario: Patent number survives rewriting
- **WHEN** a user asks for details of patent `CN117873146A`
- **THEN** every applicable plan/rewrite preserves `CN117873146A` as an exact protected identifier
- **AND** semantic expansion cannot replace it with a merely similar patent

### Requirement: Query rewriting produces traceable lane-specific views

The system SHALL retain the original query and MAY produce validated views for conversational
resolution, canonical names/aliases, semantic expansion, domain retrieval, relationship traversal,
and current Web search. Each view SHALL identify the original query, rewrite kind, protected slots,
and producing model/policy version.

#### Scenario: Follow-up refers to a displayed Company set
- **WHEN** the user asks “which of the above Companies are in Shenzhen” after a displayed Company
  result set
- **THEN** the contextual rewrite binds “the above Companies” to the displayed IDs
- **AND** it preserves the Shenzhen filter and set membership constraint

### Requirement: LLM-assisted retrieval plans are structured and validated

The LLM planner SHALL emit a versioned typed plan containing behavior class, target domains, query
views, structured constraints, relationship paths, retrieval lanes, budgets, and expected material
answer parts. The server SHALL reject unsupported operations, malformed paths, lost protected slots,
or excessive budgets before execution.

#### Scenario: Planner invents an unsupported relationship
- **WHEN** an LLM plan requests an unregistered relationship type or invalid source/target direction
- **THEN** the plan is rejected or repaired within the bounded planning retry
- **AND** the unsupported traversal is not executed

### Requirement: List plans declare an enumeration policy

Every list plan SHALL declare `exhaustive_bounded`, `required_members`, or `representative`, plus the
applicable scope, as-of, finite universe source or required members, and budgets/continuation state.
Open-world lists without a finite universe or accepted required-member contract SHALL default to
`representative`. Top-K or a non-empty candidate set SHALL NOT imply exhaustive coverage.

#### Scenario: User asks for all patents of a Company
- **WHEN** the accepted release and explicit query scope provide a finite applicant-to-Patent universe
- **THEN** the plan may select `exhaustive_bounded` and account for every eligible member
- **AND** otherwise it selects `representative` or clarifies scope rather than claiming all Patents

### Requirement: Recall combines exact, structured, lexical, vector, relationship, and Web lanes

For an information-retrieval request, the system SHALL execute all validated independent lanes
concurrently where possible. Each lane SHALL return a bounded recall-oriented candidate set with
query-view, lane, attempt, release, source, and score traceability.

#### Scenario: Topic query has lexical and semantic signals
- **WHEN** a topic query contains a rare exact technical phrase and broader semantic intent
- **THEN** the plan may combine lexical and vector candidates
- **AND** exact lexical coverage is not discarded merely because its vector rank is lower

### Requirement: Internal Person reference knowledge supports bounded person-oriented retrieval

The system SHALL use accepted release-scoped internal Person projections for person-oriented
retrieval across resolved Professor, Company-personnel, Paper-author, and Patent-inventor evidence.
Plans MAY filter those projections by supported typed facts such as education, Company role, and
geography, but SHALL retain the originating public-domain evidence and SHALL NOT treat Person as a
fifth public inclusion domain. Unresolved Person references SHALL remain separately traceable and
SHALL NOT satisfy identity-dependent filters or traversals.

#### Scenario: Find entrepreneurs by education and Company role
- **WHEN** a user asks for people with a named education background and a founder role in Shenzhen
  Companies
- **THEN** the plan may query the internal Person projection and its typed evidence-backed relations
- **AND** returned people identify the originating Company/Professor/Paper/Patent evidence without
  entering a public Person population

### Requirement: Technology aliases and routes resolve through internal versioned knowledge

The system SHALL resolve accepted Technology concept and route aliases against the current release
before comparing routes or retrieving related Companies, Products, Papers, and Patents. Retrieval
SHALL preserve the distinction between non-adoption discussion/mention, claimed adoption, and
demonstrated use, plus scope, as-of, source evidence, and enumeration policy. Discussion and lexical
mention share one non-adoption relationship state in this change; neither entails adoption or
capability. An unresolved term MAY remain a search view or gap but SHALL NOT silently become an
accepted Technology identity.

#### Scenario: Compare two technical routes and representative adopters
- **WHEN** a user names two route aliases and asks for their differences and representative Companies
- **THEN** the plan binds accepted aliases, retrieves definition/relationship evidence for each
  route, and uses `representative` enumeration unless a finite universe is available
- **AND** a mere topic mention is not reported as demonstrated Company or Product use

### Requirement: Normal information retrieval always uses bounded current Web search

Every normal information-retrieval request SHALL invoke bounded current Web search alongside the
applicable local exact, structured, lexical, vector, relationship, or internal-reference lanes.
Local and current-Web evidence SHALL remain distinguishable and SHALL both be available to final
evidence selection and answer synthesis. Out-of-scope refusal, clarification-only input, safety
guidance, and interface control input SHALL NOT invoke general Web search.

#### Scenario: Exact local object has adequate evidence
- **WHEN** an information-retrieval request exactly resolves a high-confidence local object and its
  local evidence adequately supports the requested material parts
- **THEN** the plan still invokes bounded current Web search for corroboration, freshness, or useful
  supplementation
- **AND** final synthesis may prefer the stronger local fact while retaining relevant Web evidence

#### Scenario: Local evidence is incomplete or stale
- **WHEN** a material requested fact is missing, stale, or conflicting in the local Candidate
- **THEN** the plan invokes bounded current Web search for that fact
- **AND** local and Web evidence remain distinguishable during fusion and answer generation

#### Scenario: Refusal request is out of scope
- **WHEN** a request is classified as an ordinary out-of-scope refusal
- **THEN** the system returns the refusal behavior without calling Web search

### Requirement: Web failure degrades without losing local evidence

Web provider failure, timeout, or invalid output SHALL NOT remove or invalidate usable local
evidence. The trace SHALL record the unavailable lane, and the answer SHALL disclose a freshness or
coverage limitation when material.

#### Scenario: Web times out after local retrieval succeeds
- **WHEN** current Web search exceeds its route budget and local evidence is usable
- **THEN** the system proceeds with the supported local evidence
- **AND** it does not present the result as current-Web-verified

### Requirement: Current Web retrieval combines bounded independent providers

Each normal information request SHALL run Bocha and Serper concurrently within the existing Web
lane wall-time budget, merge their normalized results, and deduplicate by normalized HTTP(S) URL
before applying the configured result cap. A retained Web snapshot SHALL record the provider that
supplied the selected content and any second provider that returned the same URL. Failure or empty
output from one provider SHALL preserve usable output from the other provider; failure of both
providers SHALL preserve the existing local-evidence degradation behavior. The route budget SHALL
permit at most one call to each configured provider per normal retrieval attempt.

#### Scenario: Both providers return the same official page
- **WHEN** Bocha and Serper return the same normalized official URL with different snippets
- **THEN** fusion retains one result position and prefers the richer Bocha content
- **AND** the content-addressed snapshot records both provider versions

#### Scenario: One provider is unavailable
- **WHEN** either Bocha or Serper fails or returns no usable results within the Web lane budget
- **THEN** the request continues with the other provider's usable results
- **AND** it does not wait beyond the existing outer Web lane budget

### Requirement: Long-idle provider paths are adaptively kept warm

The isolated Candidate SHALL run at most one background keep-warm cycle after each configured idle
interval when no real chat request has arrived during that interval. A cycle SHALL concurrently
touch the configured Bocha, Serper, embedding, and prose-LLM provider paths with bounded minimal
requests. A real request SHALL mark activity before answer execution, SHALL never wait for a
keep-warm cycle, and SHALL suppress the next idle cycle. Keep-warm work SHALL stop with application
shutdown and SHALL NOT call the chat adapter, create sessions or citations, write Canonical/index/
gap data, or expose its synthetic inputs to users.

#### Scenario: Candidate has been idle for one interval
- **WHEN** no real request arrives for the configured idle interval
- **THEN** one bounded keep-warm cycle concurrently touches all four external provider paths
- **AND** no business record, feedback checkpoint, session, evidence snapshot, or index mutation is
  created

#### Scenario: Real request arrives near a scheduled cycle
- **WHEN** a real chat request marks activity before its answer begins
- **THEN** the request proceeds without waiting for background keep-warm work
- **AND** the next scheduled cycle is skipped until another complete idle interval elapses

### Requirement: Candidate fusion is identity-aware and selection happens late

The system SHALL resolve/deduplicate candidate identities and aggregate their evidence before final
filtering/reranking. Ordinary quality gaps SHALL affect ranking or limitations rather than broad
early exclusion. Deterministic constraints and schema-validated LLM judgment SHALL perform final
evidence-aware selection.

#### Scenario: Local and Web candidates name the same Company
- **WHEN** local and current-Web lanes return the same real-world Company under different names
- **THEN** fusion presents one candidate identity with both evidence lanes
- **AND** it does not consume two result positions as unrelated Companies

#### Scenario: Local candidates fill the nominal result window
- **WHEN** a normal information request produces more eligible local candidates than the configured
  global candidate limit and also produces current-Web candidates
- **THEN** late selection retains a bounded share from both local and current-Web lanes
- **AND** local rank alone cannot remove all current-Web evidence before final synthesis

#### Scenario: Follow-up adds a new capability constraint
- **WHEN** a user asks which members of a displayed set support a newly introduced Product
  capability and local projections do not contain that capability
- **THEN** the current query, displayed entity names, and capability constraint reach bounded Web
  retrieval
- **AND** relevant direct Product-capability evidence remains available to final LLM synthesis

### Requirement: Displayed Web-only entities use evidence-bound session handles

The system SHALL preserve any displayed Web-only candidate as a typed session-scoped handle and retain
its evidence lineage in the query result contract. The handle SHALL bind claimed domain/display
identity, bounded content-addressed evidence snapshots, retrieval/provider trace, originating query/
lane/attempt, and resolution state. A URL SHALL remain evidence metadata and SHALL NOT be used as a
Professor, Company, Paper, or Patent ID. An unresolved handle SHALL NOT execute canonical traversal or
satisfy a canonical structured filter.

#### Scenario: Web finds a Company absent from the accepted release
- **WHEN** the Company is displayed as a relevant Web-only result
- **THEN** session state stores an evidence-bound Web entity handle rather than the source URL as ID
- **AND** a later canonical traversal first requires read-only resolution to an accepted identity

#### Scenario: Retained snapshot is tampered with or the live provider changes
- **WHEN** a later turn cannot reproduce the handle's recorded content hash, or a provider returns
  different live content for the same URL
- **THEN** the original handle remains bound only to its accepted snapshot and the mismatch is
  reported
- **AND** the changed content cannot replace the snapshot or establish canonical continuity

#### Scenario: Handle expires or two entities share a URL
- **WHEN** the session retention policy expires a handle, or one URL is evidence for two distinct
  displayed entities
- **THEN** an expired handle cannot be used as a live referent and each displayed entity retains a
  distinct handle identity
- **AND** URL equality does not merge the entities

#### Scenario: Later read-only resolution succeeds
- **WHEN** retained evidence and an accepted release later resolve a Web handle to one canonical
  identity
- **THEN** the session records the resolution while retaining the original handle and snapshot
  lineage
- **AND** no online identity or source-mapping mutation occurs

### Requirement: Evidence sufficiency is assessed against material question parts

After initial fusion, a structured LLM decision SHALL identify which material question parts are
supported, conflicting, or missing. A non-empty candidate list SHALL NOT by itself mean the evidence
is sufficient.

#### Scenario: Company exists but requested product capability is unsupported
- **WHEN** retrieval finds the requested Company but no evidence for the requested product capability
- **THEN** sufficiency marks that material part as missing
- **AND** the answer cannot infer the capability merely from the Company's general business

### Requirement: Supplemental retrieval is targeted and bounded

The system SHALL permit a material evidence gap to trigger targeted query views and one or more
supplemental lanes only within explicit wall-time, provider-call, retry, and cost budgets. Budget
exhaustion SHALL return the best supported result and unresolved limitations; execution SHALL NOT
loop indefinitely.

#### Scenario: Targeted Web query still cannot verify a claim
- **WHEN** supplemental retrieval exhausts its route budget without supporting the missing claim
- **THEN** the final evidence set marks the claim unsupported
- **AND** the answer omits it or states the limitation rather than inventing detail

### Requirement: Query execution remains traceable across attempts

The final evidence set SHALL retain the original query, session referents, protected constraints,
plan version, each rewrite, each lane/attempt, provider/model versions, candidate decisions, and
release IDs needed to reproduce or diagnose the answer.

#### Scenario: Benchmark case fails after a model change
- **WHEN** a previously accepted query fails after a planner or reranker model update
- **THEN** its trace identifies the changed model/version and affected decisions
- **AND** the failure can be classified without guessing which query path ran
