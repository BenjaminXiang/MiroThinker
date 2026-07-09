# chat-multi-turn-context — Delta Spec

> Terminology per root `CONTEXT.md` (result set = displayed entities; anchor; narrowing;
> cross-domain traversal; member-target mapping; coverage statement; chip/open/topic
> predicates). Decisions per ADR-011.

## ADDED Requirements

### Requirement: Result set captures displayed entities only
The session result set (`last_result_set`, per-domain) SHALL contain exactly the entity IDs
the prior turn's answer displayed to the user (answer list entries + citations). Retrieved
but undisplayed evidence MUST NOT enter the result set.

#### Scenario: Displayed subset recorded
- **WHEN** a list answer displays 10 professors while retrieval produced 30 candidates
- **THEN** `last_result_set["professor"]` contains exactly the 10 displayed IDs

#### Scenario: Set operations never surface unseen entities
- **WHEN** a follow-up filters or traverses 上述 results
- **THEN** every source member in the answer is one the user saw in the prior turn

### Requirement: Set coreference resolves to the prior result set
Set-referent expressions SHALL resolve deterministically: a domain-worded set referent
(上述教授/这些公司) resolves to that domain's result set; a bare set referent
(他们/这些/上述) resolves to the most recent non-empty domain's result set. Resolution MUST
NOT fall back to a different domain or to a global re-search when the referenced domain's
set is empty.

#### Scenario: Domain-worded set referent
- **WHEN** the prior turn displayed a professor list and the user asks 上述教授参与的企业
- **THEN** the referent is the displayed professor ID set

#### Scenario: Bare set referent
- **WHEN** the prior turn displayed a company list and the user asks 他们有哪些专利
- **THEN** the referent is the displayed company ID set

#### Scenario: Empty-domain clarification, no silent fallback
- **WHEN** the prior turn displayed companies only and the user asks 上述教授参与的企业
- **THEN** the system returns a clarification stating no professor list is in context, and
  does NOT run a global search or substitute the company set

### Requirement: List answers do not create single-entity anchors
Only individually-focused entities SHALL be pushed onto the anchor stack only for profile
answers, disambiguation picks, or explicit naming. List answers SHALL NOT push their members as
anchors. A singular pronoun with no anchor but a live same-domain result set SHALL trigger
a deterministic clarification listing the set members, never a silent guess.

#### Scenario: Singular pronoun after a bare list clarifies
- **WHEN** the prior turn displayed a 10-professor list (no profile since) and the user
  asks 他的论文
- **THEN** the system asks which member is meant, listing the members, and does not answer
  with an arbitrary member's papers

#### Scenario: Singular pronoun after a profile still resolves
- **WHEN** the prior turn was a single professor profile and the user asks 他的论文
- **THEN** the pronoun resolves to that professor (existing anchor behavior preserved)

### Requirement: Follow-up routing is hybrid with A-G semantics unchanged
A deterministic rule layer SHALL route every suggested-followup chip text and every query
whose set-referent word is explicit. The LLM classifier SHALL emit an orthogonal
`referent: set|entity` field to route paraphrases. No new top-level A-G query class is
introduced. Precedence MUST be deterministic: explicit set-word → set path; singular
pronoun → entity path; neither → classifier referent; classifier unavailable or silent →
existing single-entity behavior.

#### Scenario: Every chip text routes correctly
- **WHEN** any suggested-followup chip string emitted by the backend is sent as a query
  (e.g. 看看这些教授的论文, 上述哪些在深圳, 这些公司有哪些专利, 上述哪些已授权)
- **THEN** the rule layer routes it to the correct set operation without requiring the
  classifier

#### Scenario: Paraphrase routes via classifier referent
- **WHEN** the user asks 他们都开了哪些公司 after a professor list
- **THEN** the classifier's `referent=set` routes it to set traversal targeting companies

#### Scenario: A-G classes unchanged
- **WHEN** the classifier processes any query
- **THEN** its top-level type remains within the existing A-G/UNKNOWN classes

### Requirement: Set cross-domain traversal produces a member-target mapping answer
A set-referent follow-up targeting another domain SHALL traverse per member via the
deterministic relation lookup (retrieval-service `get_related_objects`), assembling a
member-target bipartite mapping stored whole in `structured_payload`. The rendered answer
SHALL default to target-centric projection (dedup by target, back-links to members kept);
when the query contains 分别 it SHALL use member-centric projection. Every traversal answer
MUST include a coverage statement (how many members had linked records, how many had none),
surface link semantics (`role_type`), and label candidate-status links distinctly from
verified.

#### Scenario: Target-centric traversal (default)
- **WHEN** the user asks 上述教授参与的企业 after a professor list where 4 of 10 members
  have company links
- **THEN** the answer lists the deduplicated companies each with its linked professor(s),
  role_type, and link-status label, and states 10 位中 4 位有企业关联记录、6 位暂无

#### Scenario: Member-centric projection on 分别
- **WHEN** the user asks 他们分别参与了哪些企业
- **THEN** the answer lists per professor their companies (members with none marked 暂无收录)

#### Scenario: No global re-search on traversal
- **WHEN** a set traversal runs
- **THEN** every target entity in the answer is reachable via a relation link from a set
  member (verifiable in `structured_payload`), not from a fresh global topic search

### Requirement: Narrowing selects its mechanism by predicate type
Set narrowing SHALL support three mechanisms: (1) chip predicates — a closed table
(region/institution, year/recency, grant status, applicant type) evaluated
deterministically per member on rows fetched by ID; (2) open predicates — free-form member
conditions judged by the LLM per member on deterministically fetched rows, each emitting an
audited structured verdict `{member_id, verdict, evidence_field, quote}` recorded in
`structured_payload`; (3) topic narrowing — the existing semantic
retrieve(topic) ∩ set. Chip predicates MUST NOT be sent to semantic retrieval. Narrowing
answers MUST include a coverage statement and MUST distinguish unknown (missing field) from
unsatisfied.

#### Scenario: Chip predicate is deterministic
- **WHEN** the user asks 上述哪些在深圳 over a company set
- **THEN** each member is judged from its stored region/institution fields, the answer
  explains per-member basis, and no semantic retrieval runs

#### Scenario: Open predicate judged per member with audit
- **WHEN** the user asks 上述企业的产品有哪些可以实现机械臂自主按电梯
- **THEN** the LLM judges each member on its fetched product/scenario fields and the
  per-member verdicts (with quoted evidence) appear in `structured_payload`

#### Scenario: Unknown distinguished from unsatisfied
- **WHEN** a chip predicate evaluates a member whose relevant field is empty
- **THEN** the member is reported as 信息缺失, not counted as failing the predicate

#### Scenario: Topic narrowing preserved
- **WHEN** the user asks 其中做大模型的 over a professor set
- **THEN** the existing topic-intersection narrowing runs against the set

### Requirement: Set operations chain
Traversal and narrowing answers SHALL update the result set with the displayed output
entities (in the output domain), enabling chained follow-ups across turns.

#### Scenario: Three-turn chain
- **WHEN** the user runs 教授列表 → 上述教授参与的企业 → 这些公司有哪些专利
- **THEN** turn 3 traverses the companies displayed in turn 2 (not the professors, not a
  global search)

### Requirement: Deterministic base survives LLM kill-switches
With `CHAT_QUERY_CLASSIFIER=off`, chip texts and explicit set-word queries SHALL still
route and execute correctly; paraphrases fall through to existing new-query handling. With
`CHAT_LLM_SYNTHESIS=off`, traversal, chip-predicate narrowing, clarification, and
deterministic rendering SHALL remain fully functional; open-predicate narrowing SHALL
degrade to topic-intersection with the answer labeled 按语义相关性筛选.

#### Scenario: Chips work with classifier off
- **WHEN** `CHAT_QUERY_CLASSIFIER=off` and the user clicks 上述哪些在深圳
- **THEN** the chip-predicate narrowing executes normally

#### Scenario: Open predicate degrades with synthesis off
- **WHEN** `CHAT_LLM_SYNTHESIS=off` and the user asks an open-predicate narrowing
- **THEN** the system runs topic-intersection over the set and labels the answer as
  semantic-similarity filtering

### Requirement: Multi-turn behavior is eval-verified
Multi-turn behavior SHALL be verified by a session-sticky eval runner replaying
`turn_group`-linked golden conversations over HTTP against the live backend. The golden
set comprises the 8 existing follow-up cases in `test_cases.yaml` plus ~6 synthesized
dialogs covering set traversal, bare 他们, list-then-singular clarification,
empty-set/domain-mismatch clarification, a 3-turn chain, and the chip routing matrix. A RED
baseline MUST be archived before implementation. Acceptance: ≥12/14 multi-turn cases pass
AND zero regression on the single-turn 19-case set AND the chip routing matrix fully green.

#### Scenario: RED baseline before implementation
- **WHEN** the eval runner exists and implementation has not started
- **THEN** a baseline run over the golden conversations is archived under
  `.agents/runs/layer-d-multi-turn-context/`

#### Scenario: Acceptance gate
- **WHEN** the slice is proposed for acceptance
- **THEN** the same runner shows ≥12/14 multi-turn pass, zero single-turn regression, and
  all chip strings routing correctly
