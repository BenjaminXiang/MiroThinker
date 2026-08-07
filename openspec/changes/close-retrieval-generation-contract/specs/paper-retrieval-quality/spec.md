# paper-retrieval-quality Specification

## ADDED Requirements

### Requirement: Paper retrieval evaluation is ID-grounded and snapshot-fixed

The evaluator MUST score paper retrieval from canonical result and evidence object IDs under a
frozen case manifest and fixed database/index snapshot. It SHALL exclude echoed queries, prompts,
debug fields, configuration, and mutable substring-token oracles from retrieval scoring.

#### Scenario: Expected text exists only in the request echo

- **WHEN** an expected title token or professor name appears in the echoed query but no matching
  canonical paper ID is retrieved
- **THEN** the retrieval stage SHALL fail

#### Scenario: Parent and candidate are compared

- **WHEN** a change is evaluated against its parent
- **THEN** both runs SHALL use the same manifest, database snapshot/version, Milvus index version,
  and identical saved provider-boundary fixtures for a paired causal comparison
- **AND** both raw responses and code SHAs SHALL be retained

#### Scenario: Live-provider stability is reported separately

- **WHEN** acceptance exercises a live model, embedding, rerank, or Web provider
- **THEN** the provider/version/configuration SHALL be pinned and every P0 case SHALL run at least
  three independent times with all raw responses retained
- **AND** the report SHALL distinguish live stability evidence from deterministic fixture replay

#### Scenario: Type4 has no candidate universe

- **WHEN** a topic set defines judged relevance only for returned candidates rather than a complete
  corpus universe
- **THEN** topic queries, inclusion rules, rubric, and blind-labeling protocol SHALL be frozen before
  implementation with visible development and sealed acceptance sets
- **AND** the anonymized acceptance union SHALL receive independent saved labels/rationales from at
  least two blind reviewers, disagreement adjudication, raw agreement, and Cohen's kappa >=0.60
- **AND** labels SHALL be sealed before scores/run identities are revealed; any implementation change
  made after unblinding SHALL require a fresh versioned sealed holdout for re-certification
- **AND** only schema/strata/rubric/hash SHALL be committed; an independent reviewer or CI-secret
  custodian SHALL hold encrypted cases/labels with access logging and sign the one-shot result before
  disclosure/rotation to regression-only
- **AND** the report SHALL use the defined frozen-topic precision metric
- **AND** it SHALL NOT label the result as recall

#### Scenario: Classifier regression case is type-correct but entity-wrong

- **WHEN** a 100-case classifier row produces the expected query type but the target domain,
  normalized name/topic, or planned endpoint differs from the populated expectation
- **THEN** that row SHALL fail the regression gate

### Requirement: Frozen paper cases meet minimum coverage strata

The manifest SHALL meet the minimum case and stratum counts in the Epic verification contract
before Slice A is Accepted. Case strata MUST be selected from the frozen snapshot before candidate
implementation and MUST include positive, negative, ambiguity, degradation, language, rarity,
filter, pagination, and relationship-path coverage rather than only currently passing examples.
Every distinct case satisfying a minimum floor, every named true-RED demonstration, and every known
citation/synthesis counterexample MUST have immutable `priority=P0` for all applicable gates. P1 MAY
be used only for additive cases beyond all floors when assigned with rationale before output. A P0
case MUST NOT be demoted/replaced or made N/A after output; deterministic-only classifier rows MAY
mark semantic/live gates N/A only with a pre-output frozen reason.

#### Scenario: A proposed manifest omits a required stratum

- **WHEN** the manifest has too few cases for a required path/stratum or lacks its documented source,
  judgment method, and reviewer
- **THEN** Slice A SHALL remain unaccepted even if every included case passes

### Requirement: Retrieval-active-v1 maps path eligibility to concrete canonical states

Every Type1-Type3 expected set MUST use the same versioned `retrieval-active-v1` mapping on the
frozen snapshot. A company is active only when `company.identity_status='resolved'`. A professor is
active only when `professor.identity_status='resolved'` AND
`professor.lifecycle_state='active'`. A paper is nonterminal only when
`paper.identity_status IN ('confirmed','unverified')` AND
`coalesce(paper.quality_status,'needs_enrichment') <> 'rejected'`; `rejected` and `merged` paper
identities are excluded, with a merged input followed only to a survivor satisfying this mapping.
An `unverified` paper that matches the requested Type1-Type3 predicate/path SHALL remain in that
expected set, but only with a visible identity limitation and source-grounded facts; it cannot
silently become confirmed. Type4 dense/index admission applies the stricter versioned
`index_eligibility` rule in addition to this nonterminal mapping.

Professor-paper edges MUST have `link_status='verified'`. Type3 strong company-professor edges MUST
have `link_status='verified'`; secondary membership MUST satisfy the separately specified matched-
resolution/latest-snapshot rule. Candidate/rejected edges never become active through node state.
Slice A MUST freeze the exact SQL/rule hash and expected IDs under this mapping; implementations may
not substitute generic “active” or “nonterminal” checks.

#### Scenario: Resolved but archived professor is traversed

- **WHEN** a professor has `identity_status='resolved'` but `lifecycle_state='archived'`
- **THEN** Type2 and Type3 SHALL exclude that professor and its paths under `retrieval-active-v1`

#### Scenario: Verified link points to an unverified paper

- **WHEN** a verified professor-paper link points to a paper whose identity is `unverified` and whose
  quality is not rejected
- **THEN** Type2 and Type3 SHALL include/return it when it otherwise matches the frozen predicate/path,
  but SHALL expose only source-grounded facts with a visible identity limitation
- **AND** Type4 dense retrieval SHALL still require separate `index_eligibility=true`

#### Scenario: Company or paper is terminal

- **WHEN** a company is `needs_review`, `merged_into`, or `inactive`, or a paper is `rejected` or
  `merged`
- **THEN** the node and every path through it SHALL be absent from local eligible sets

### Requirement: Type1 resolves natural exact-title requests by canonical ID

Type1 SHALL normalize conversational title wrappers without corrupting the paper title and MUST
resolve bare, quoted, and supported natural exact-title variants to the same canonical paper ID.

#### Scenario: Natural detail suffix

- **WHEN** a known exact title is followed by a wrapper such as “这篇论文的详细信息”
- **THEN** Type1 SHALL retrieve and cite the same canonical paper ID as the bare title

#### Scenario: Similar title is not the target

- **WHEN** lexical text resembles the requested title but resolves to a different canonical paper
  ID
- **THEN** the target-ID gate SHALL fail even if shared title tokens are present

#### Scenario: Exact title is absent from the local snapshot

- **WHEN** an explicit-title lookup completes successfully with no matching canonical local paper
- **THEN** the system SHALL invoke the separately typed Web fallback when it is available
- **AND** any Web result SHALL be cited as Web evidence and SHALL NOT fabricate or satisfy a local
  paper ID gate
- **AND** the response SHALL use `partial_result` with a local-snapshot limitation when useful Web
  evidence exists, `no_result` only when both planned lanes succeed empty, or `retrieval_error` when
  a required fallback fails without a usable result

#### Scenario: Exact title resolves to multiple active papers

- **WHEN** more than one distinct active canonical paper has the same exact normalized title
- **THEN** Type1 SHALL return `partial_result` with a cited disambiguation payload
- **AND** it SHALL NOT choose an arbitrary paper by rank

#### Scenario: Exact title matches a merged or terminal paper

- **WHEN** the matched ID is merged into an active canonical survivor
- **THEN** Type1 SHALL follow and cite the survivor plus merge trace
- **AND** when only rejected/terminal matches exist it SHALL treat local lookup as no active match
  and apply the separately provenanced Web fallback policy

#### Scenario: Exact identity has no supportable detail

- **WHEN** a canonical paper identity is resolved but requested details have no shared-contract source
  evidence/snippet
- **THEN** the response SHALL be a disclosed `partial_result` limited to supported identity facts
- **AND** it SHALL NOT invent detail to turn the response into success

### Requirement: Professor anchors are normalized before routing

The system SHALL align the classifier, query type, normalized professor name, domain, and retrieval
endpoint for professor-paper queries. Organization or location context SHALL NOT be retained as
part of the person name when it is not part of that name.

#### Scenario: Q004 organization-qualified professor query

- **WHEN** the frozen Q004 query supplies an organization plus professor name and asks who the
  professor is
- **THEN** the system SHALL classify professor-profile intent, normalize the expected person name,
  resolve the expected professor ID, call the professor endpoint, and cite that professor ID in the
  profile answer
- **AND** the case SHALL NOT require or invent a paper predicate

#### Scenario: Q017 location-qualified professor query

- **WHEN** the frozen Q017 query supplies location context plus professor name and asks who the
  professor is
- **THEN** the system SHALL not treat the location token as part of the professor name
- **AND** its professor-profile route/name/domain/endpoint/professor-ID/citation gates SHALL pass

### Requirement: Type2 list intent exposes the complete verified set through pagination

After resolving a professor, a Type2 all/list request SHALL operate over all active, verified
professor-paper links under the snapshot. It MUST provide stable pagination metadata and MUST NOT
claim completeness for an implementation-limited top-N subset. Default page size SHALL be 20,
explicit page size SHALL be capped at 50, and stable order SHALL be year descending null-last,
citation count descending null-last, `paper-title-sort-v1` ascending, then paper ID ascending. The cursor
MUST bind the full sort tuple, predicate/order version, page size, and materialized result set.
`paper-title-sort-v1` MUST be the two ascending database keys
`CASE WHEN btrim(regexp_replace(coalesce(title_clean, ''), E'\\s+', ' ', 'g')) = '' THEN 1 ELSE 0 END`
and `btrim(regexp_replace(coalesce(title_clean, ''), E'\\s+', ' ', 'g')) COLLATE "C"`. The first is
a computed expression, not a schema field, and puts empty/whitespace-only titles last; no
application-local title normalizer MAY define cursor order.

#### Scenario: Professor has more papers than one page

- **WHEN** a professor's verified paper set exceeds the configured page size
- **THEN** the first response SHALL contain a correctly cited page plus total and continuation
  metadata
- **AND** traversing all pages SHALL yield the complete set exactly once under the snapshot

#### Scenario: Synthesis receives a paper page

- **WHEN** Type2 retrieval returns professor identity, paper results, and pagination metadata
- **THEN** synthesis SHALL answer the paper-list intent from those paper results
- **AND** it SHALL NOT fall back to a professor-profile answer or state that papers cannot be listed

### Requirement: Type2 applies typed time, topic, and representative predicates

Type2 SHALL distinguish all/list, publication year or range, recent, topic intersection, and
representative-work predicates. The response MUST disclose the effective predicate and whether the
result is complete, filtered, or ranked. Canonical publication time SHALL be `paper.year`: null years
remain at the end of all/list but are excluded by exact year/range predicates. Bare recent/latest
SHALL mean recency-ranked first page without an implicit time cutoff; explicit N-year queries SHALL
use the inclusive range ending at the Asia/Shanghai reference year captured in the first request.
Representative work SHALL default to 10, cap an explicit limit at 20, and order by citation count
descending null-last, year descending null-last, `paper-title-sort-v1`, then paper ID.

#### Scenario: Exact publication year

- **WHEN** a professor-paper query specifies a publication year
- **THEN** every returned local paper SHALL be linked to the professor and satisfy that year under
  the canonical publication date rule

#### Scenario: Topic intersection

- **WHEN** a professor-paper query specifies a topic
- **THEN** the system SHALL call the shared paper-topic search interface on the same snapshot and
  intersect its canonical paper IDs with the professor's complete verified set
- **AND** it SHALL label the output ranked unless a frozen exhaustive predicate set exists
- **AND** Slice D's deeper topic provider SHALL rerun this same Type2 contract rather than introduce
  a second matcher

#### Scenario: Recent works

- **WHEN** the user asks only for recent/latest papers
- **THEN** verified papers SHALL use the stable recency ordering and first-page limit without an
  implicit year cutoff
- **AND** the result SHALL be labeled ranked

#### Scenario: Explicit N-year works

- **WHEN** the user asks for papers from the last N years
- **THEN** the inclusive year range SHALL end at the cursor-bound Asia/Shanghai reference year
- **AND** papers with null year SHALL be excluded and the effective range SHALL be disclosed

#### Scenario: Representative works

- **WHEN** the user asks for representative papers
- **THEN** results SHALL use citation count then year then `paper-title-sort-v1` then paper ID, with
  the specified default/capped limit
- **AND** the answer SHALL label them as ranked selections rather than the complete publication set

### Requirement: Type3 uses verified two-hop traversal with relationship tiers

Company-to-paper queries SHALL traverse a resolved company-to-professor edge followed by an active,
verified professor-to-paper edge. `professor_company_role` SHALL be the strong tier;
`company_team_member.resolved_professor_id` SHALL be a secondary tier when its eligibility rules
match, MUST be disclosed, and MUST NOT be represented as a verified role. Strong edges MUST have
`link_status=verified`. Secondary
edges MUST come from the latest company snapshot, have `resolution_status=matched`, and have a
non-null resolved professor ID. Candidate/unresolved/rejected relations and terminal company,
professor, paper, or professor-paper nodes/edges MUST be excluded.

#### Scenario: Strong relationship path

- **WHEN** a company has a verified professor-company role whose professor has verified paper links
- **THEN** the result SHALL preserve and cite company ID, strong edge identity, professor ID,
  professor-paper edge identity, and paper ID
- **AND** general related-paper intent SHALL disclose current/former/unknown role time while an
  explicit current-role intent SHALL require `is_current=true`

#### Scenario: Secondary resolved-team path

- **WHEN** only a resolved company-team-member edge connects the company to a professor
- **THEN** every otherwise eligible paper SHALL be returned with `relation_tier=secondary` and an
  explicit limitation
- **AND** their canonical record quality SHALL remain separate from relationship tier
- **AND** the answer SHALL disclose that relationship tier

#### Scenario: Unresolved or unverified edge

- **WHEN** a company team name has no resolved professor ID or the professor-paper link is not
  verified and active
- **THEN** that path SHALL NOT produce a local company-to-paper result

#### Scenario: Multiple paths reach one paper

- **WHEN** more than one eligible professor/path reaches the same paper
- **THEN** the final paper MAY be deduplicated for display
- **AND** its provenance SHALL retain every supporting path through stable path continuation rather
  than erase alternate edges

#### Scenario: Large Type3 result and path sets

- **WHEN** unique papers or supporting paths exceed one response page
- **THEN** paper pages SHALL default to 20/max 50 with the stable year/citation/title/ID order
- **AND** each paper SHALL expose total path count, up to 10 strong-first paths, and an opaque cursor
  that traverses every remaining path under the same snapshot

#### Scenario: Production relationships are empty or sparse

- **WHEN** read-only production inspection finds no or insufficient eligible strong/secondary paths
- **THEN** Slice E MAY accept its mechanism against frozen fixtures only with an explicit production
  coverage-pending status, counts, causes, and linked data-remediation owner/worklist
- **AND** the Epic SHALL NOT claim production Type3 coverage closure

### Requirement: Type4 parses structured topic constraints

Type4 SHALL separate topic text from supported year/range, category, and recency constraints and
apply those constraints at canonical paper level. It MUST reuse `paper.year` and the shared
Asia/Shanghai reference-year/null rules. Exact/range/N-year/category filters SHALL apply before
fusion/rerank. Bare latest SHALL add no implicit cutoff and, after relevance qualification and
paper-level deduplication, order by year descending null-last, fused relevance descending, then
paper ID. The parsed predicate/order SHALL be present in trace and evaluation artifacts.

#### Scenario: Topic plus year

- **WHEN** a topic query includes a publication year
- **THEN** final local candidates SHALL satisfy both frozen-topic relevance and the canonical year
  predicate

#### Scenario: Topic plus bare latest

- **WHEN** a topic query asks for latest/recent without an explicit range
- **THEN** no hidden year window SHALL be applied
- **AND** relevant deduplicated local papers SHALL use year-descending null-last, fused-relevance,
  paper-ID order with the effective order disclosed

#### Scenario: Latest external request

- **WHEN** the user asks for information newer than the known local snapshot
- **THEN** the planner MAY invoke the separate Web lane
- **AND** the answer SHALL disclose local snapshot limits and Web source times

### Requirement: Category and lexical retrieval use an approved canonical substrate

The system SHALL store paper categories in a normalized paper-subject relation with taxonomy,
subject identity/label, normalized label, shared source evidence, confidence, run ID, and lifecycle
timestamps. Category filtering MUST use those rows and a versioned alias map; it MUST NOT infer a
category from title text. Local mixed-language lexical search MUST use a reviewed reversible
PostgreSQL FTS/trigram index rather than an unbounded unindexed scan.

#### Scenario: Category has authoritative retained evidence

- **WHEN** a parsed category resolves unambiguously through the versioned alias map
- **THEN** paper-level filtering SHALL use active subject rows with traceable shared evidence

#### Scenario: Category is ambiguous or coverage is missing

- **WHEN** a category maps to multiple subjects or qualifying papers lack authoritative category
  data
- **THEN** the system SHALL ask for clarification or return a disclosed partial result
- **AND** it SHALL NOT silently ignore the category or infer one from title tokens

#### Scenario: Lexical index prerequisite is unavailable

- **WHEN** the approved PostgreSQL extension/index/query plan cannot be installed or proven within
  the latency and rollback contract
- **THEN** Slice D SHALL stop before claiming local lexical/FTS support

### Requirement: Type4 combines dense and local lexical candidates

Type4 SHALL execute dense retrieval and local lexical/FTS retrieval as independent bounded lanes
when both are available, normalize their candidates, and fuse them only after grouping all matches
by canonical `paper_id`.

#### Scenario: Repeated chunks match one paper

- **WHEN** several chunks from one paper match the query
- **THEN** they SHALL contribute features/evidence to one paper candidate
- **AND** they SHALL NOT occupy multiple final paper positions

#### Scenario: Embedding lane fails

- **WHEN** dense retrieval is unavailable but local lexical retrieval succeeds
- **THEN** Type4 SHALL return the valid lexical candidates with a disclosed degradation
- **AND** it SHALL NOT report a successful empty local search merely because embeddings failed

#### Scenario: Lexical lane fails

- **WHEN** local lexical retrieval fails but dense retrieval succeeds
- **THEN** Type4 MAY return validated dense candidates as `partial_result`
- **AND** the failed lane SHALL be visible in outcome and trace artifacts

### Requirement: Active partial-rich papers remain eligible with quality disclosure

Active partial papers with sufficient rich text SHALL participate in the Type4 candidate pool with
a documented rank penalty and visible quality metadata. They MUST NOT be suppressed solely because
one or more ready papers were retrieved.

#### Scenario: Partial-rich paper outranks irrelevant ready paper

- **WHEN** a partial-rich paper remains relevant after the documented quality penalty and a ready
  paper is less relevant
- **THEN** the partial-rich paper MAY appear in the final results with a quality disclosure

#### Scenario: Title-only partial record

- **WHEN** an active partial paper lacks content required by the dense eligibility rule
- **THEN** it SHALL NOT be represented as a successfully embedded rich paper
- **AND** any exact or lexical exposure SHALL disclose its title-only limitation

### Requirement: Local and Web paper lanes do not substitute for each other

Local paper recall and identity gates MUST use canonical local paper IDs. Web results SHALL carry
Web provenance and SHALL NOT be cast to local paper citations or counted toward local retrieval
success.

#### Scenario: Web result has the expected title

- **WHEN** a Web page mentions the expected paper but the local target paper ID was not retrieved
- **THEN** the local retrieval gate SHALL fail
- **AND** the Web source MAY appear only as separately labeled supplemental evidence

### Requirement: Paper paths have independent quality and latency gates

Verification SHALL enforce Type1 target-ID retrieval/citation at 100%, Type2 predicate/page
completeness and returned-item citation at 100%, Type3 eligible path/tier and returned-item citation
at 100%, Type4 frozen-topic micro-`Precision@5 >= 85%` and returned-item citation at 100%, and
Q004/Q017 professor-profile route/name/domain/endpoint/professor-ID/citation at 100%. For N Type4
topics the precision denominator MUST be `5 * N`; missing, duplicate, non-local/Web, and irrelevant
slots count as incorrect. Per-topic P@5 SHALL be diagnostic, not a separate 85% hard gate.
Previously passing frozen cases MUST have zero regression. Retrieval p95 MUST remain at most six
seconds in each required path bucket.

#### Scenario: Aggregate score hides a failed path

- **WHEN** the overall average passes but any Type1, Type2, Type3, Q004/Q017, citation, or
  regression hard gate fails
- **THEN** the paper retrieval verification SHALL fail and exit nonzero

#### Scenario: Type4 precision is measured

- **WHEN** Type4 returns up to five results for each frozen topic
- **THEN** relevance SHALL be judged through the blinded-union protocol after paper deduplication
- **AND** micro-`Precision@5` across exactly five local slots per frozen topic SHALL be at least 85%
- **AND** each per-topic P@5 and missing/duplicate/Web slot SHALL be reported for diagnosis

#### Scenario: Retrieval latency is reported

- **WHEN** the frozen benchmark completes
- **THEN** every Slice-A-required Type1, Type2, Type3, Type4, local-only, and local-plus-Web bucket
  SHALL have 5 warmups and at least 100 measured observations under the frozen protocol
- **AND** nearest-rank retrieval p95/p99 SHALL be at most 6/12 seconds, timeouts SHALL count at
  deadline and as failures, and required error-rate gates SHALL pass
- **AND** no bucket SHALL be omitted after implementation or hidden by a faster aggregate
