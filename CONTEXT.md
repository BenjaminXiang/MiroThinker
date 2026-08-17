# 深圳科创数据平台 — Chat / Retrieval Context

Conversational sci-tech retrieval over professor / company / paper / patent domains.
This glossary pins the ubiquitous language for multi-turn chat context (Layer D) and
its neighbors. Glossary only — no implementation details.

## Language

### Multi-turn context

**Referent (指代对象)**:
What a follow-up query points at. Four kinds: single entity (R1), result set (R2),
constraint frame (R3), answer text (R4).
_Avoid_: pronoun target, anaphor (use only for the surface word)

**Operation (操作)**:
What the follow-up does to the referent: profile (O1), filter (O2), cross-domain
traversal (O3), attribute aggregation (O4), constraint re-query (O5).

**Result set (结果集)**:
The per-domain list of entity IDs a prior turn's answer *displayed to the user*
(answer list + citations). The thing set-referents (上述/这些/他们) resolve to.
Retrieved-but-not-displayed evidence is NOT part of the result set — set coreference
must match the user's mental model, not retrieval internals.
_Avoid_: candidates, matches (those are retrieval-internal, pre-display)

**Set coreference (集合指代)**:
Resolving a set-referent expression (上述教授/这些公司/他们) to a prior result set,
as opposed to single-entity pronoun rewriting (他/这家公司).

**Anchor (锚点)**:
A single entity the user has individually focused on (profile answer, disambiguation
pick, explicit naming). Singular pronouns (他/这家公司) resolve to anchors only.
List answers do NOT create anchors — a singular pronoun after a bare list is a true
ambiguity and must trigger clarification, not a silent guess.
_Avoid_: session entity (ambiguous — the stack holds anchors, not everything shown)

**Narrowing (收窄)**:
Same-domain filter over a prior result set (其中做大模型的). Output ⊆ input set.
Three mechanisms by predicate type: chip predicate, open predicate, topic narrowing.
_Avoid_: refinement, drill-down

**Chip predicate (谓词快路径)**:
A closed-table structured predicate (region/institution, year/recency, grant status,
applicant type) evaluated deterministically per member. Never sent to semantic retrieval.

**Open predicate (开放谓词)**:
A free-form member condition (引用量超1000 / 能自主按电梯) judged by the LLM per member
on deterministically fetched rows, emitting an audited structured verdict.
_Avoid_: fuzzy filter

**Topic narrowing (话题收窄)**:
Semantic-similarity filter (retrieve(topic) ∩ set) — the right mechanism for research
topics, and the degradation path for open predicates when synthesis is off.

**Cross-domain traversal (跨域遍历)**:
From a result set in one domain to its linked entities in another domain
(上述教授参与的企业). Distinct from narrowing: output domain ≠ input domain.
_Avoid_: cross-domain jump, domain switch

**Member-target mapping (成员-目标映射)**:
The bipartite result of a set traversal: each source member ↔ its linked target
entities, with link semantics (role_type) and evidence strength (link_status).
Two projections: target-centric (default; dedup by target, back-links kept) and
member-centric (per-member listing, when the query says 分别).

**Coverage statement (覆盖声明)**:
The mandatory answer line stating how many set members had linked records and how
many had none — distinguishes "no data" from "not searched".

**Constraint re-query (换约束重查)**:
Re-running the prior query frame with one constraint swapped (深圳的→那广东的呢).
Out of Layer D scope; needs constraint-frame memory (R3).

### Layer D boundary

**Layer D owns**: set-coreference resolution + set operations (filter, traversal,
member attribute retrieval) — the *context* factor.

**Layer A owns**: aggregation/comparison *expression* over retrieved member data —
the *synthesis* factor. D resolves and fetches; A reasons and phrases.

### Retrieval gap taxonomy (single-turn accuracy factors)

Accuracy factors as `knowledge-availability × retrieval-precision × reach × context-coherence × synthesis-fidelity`.
Each gap maps to one factor:

**Coverage (覆盖)**:
An entity is NOT in the DB. The hard ceiling on accuracy — can't retrieve or cite what
isn't ingested. Owned by Layer E (data backfill pipeline). Slow, data-pipeline cost.
_Avoid_: "data quality" (overloaded)

**Reach (可达性)**:
An entity IS in the DB but UNREACHABLE via a query path (e.g. professor→their papers,
topic→papers, paper→professor, company-name alias). Distinct from coverage (data present)
and precision (data retrieved-but-wrong). High value: unlocks existing data without ingest.
Measured path-dependent: self-retrieval 100%, professor→paper 11%, topic→paper 0%.

**Precision (精度)**:
The right data is reachable but buried under wrong/adjacent results (retrieved-but-not-gold).
Owned by Layer C. Diminishing returns once the main signals are fused.

**Synthesis fidelity (生成保真)**:
The retrieved evidence is correct but the answer is a shallow dump, misses the point, or
hallucinates. Owned by Layer A (two-step relevance/sufficiency + cite) and the intent-aware
prompts.

**Web quality / fusion (网络质量/融合)**:
Web evidence is raw, marketplace-polluted, un-deduped, or not source-aware (DB curated vs
web supplemental). Owned by Layer B.

### Canonical knowledge

**Canonical V2**:
The identity-resolved, evidence-backed, quality-governed knowledge representation for the
four PRD domains and their business-required relationships. It is independent of recovery
source formats and serving indexes.
_Avoid_: recovered database copy, Milvus snapshot, answer-key database

**Canonical relation (规范事实关系)**:
A source-grounded relationship between canonical entities, carrying its own semantics,
evidence, confidence, and validity state.
_Avoid_: inferred similarity, conversational association

**Derived relation (派生关系)**:
A reproducible relationship computed from canonical facts, such as similarity, ranking,
trend, or representative-result selection. It is not asserted as source-grounded truth.
_Avoid_: canonical fact

**Relationship exploration (关系探索)**:
A progressive multi-turn interaction in which each answer follows a bounded relation path
and helps the user choose the next traversal. It is not an exhaustive one-query graph dump.
_Avoid_: one-shot graph answer

**Web augmentation (网络增强)**:
Parallel Web evidence acquisition for every information-retrieval request, used for freshness,
corroboration, and coverage. It excludes out-of-scope refusal, clarification-only, and interface
control inputs; searching does not by itself make a Web claim accepted evidence.
_Avoid_: Web fallback, Web rescue

**Inclusion policy (收录规则)**:
The domain-specific rule that decides whether an identity-resolved object belongs in Canonical
V2. Evidence may remain in recovery landing or the live-Web lane without qualifying for inclusion.
_Avoid_: one global Shenzhen filter, automatic promotion of every Web hit

**Path eligibility (路径资格)**:
The query-path-specific decision that a canonical object has enough identity, evidence, and
content quality for exact lookup, relation traversal, semantic recall, recommendation, or ranking.
Canonical inclusion alone does not grant eligibility for every path.
_Avoid_: one global ready flag, canonical means universally retrievable

**Hard exclusion (硬排除)**:
Removal from a retrieval path only when an object is known to be the wrong identity, terminally
merged/rejected, unsafe to expose, or devoid of usable facts. Missing enrichment alone is not a
hard-exclusion reason.
_Avoid_: treating every quality signal as a gate

**Quality signal (质量信号)**:
Evidence about completeness, confidence, freshness, or provenance used for ranking, disclosure,
review, and enrichment. A quality signal is soft unless a named hard-exclusion invariant applies.
_Avoid_: quality gate (when no exclusion is intended)

**Material claim (重要事实断言)**:
A user-visible assertion about a concrete entity, relationship, capability, role, date, or number
whose correctness could materially change the answer. It requires local or current-Web evidence.
_Avoid_: treating model confidence as evidence

**LLM judgment (模型判断)**:
Use of model reasoning and world knowledge to interpret a query, assess plausibility and relevance,
resolve ambiguity, rerank evidence, or synthesize an answer. It does not itself establish a material
claim as a sourced fact.
_Avoid_: LLM as source

**Source assertion (来源断言)**:
One source's time-bound statement about an entity, field, or relationship. Assertions are retained
even when another value is selected for canonical use.
_Avoid_: canonical truth, overwrite candidate

**Canonical value (规范值)**:
The currently selected representation of a field or relationship, chosen from retained source
assertions under deterministic constraints plus LLM-assisted semantic adjudication.
_Avoid_: destructive overwrite, permanent truth

**Canonical identity (规范身份)**:
The stable entity that survives resolution of source records, identifiers, names, and aliases.
Resolution is reversible and preserves every source identity plus the evidence for merge or split.
_Avoid_: source row ID, display name as identity

**Identity continuity (身份连续性)**:
The product property that the same real-world object remains stable across future accepted releases
while duplicates and mistaken identity decisions can still be corrected and audited. Pre-launch
internal IDs are lineage inputs, not compatibility obligations.
_Avoid_: preserve a pre-launch internal ID at any cost

**Current projection (当前投影)**:
The present user-facing selection from retained time-bound assertions. It does not erase earlier
assertions or imply that every fact needs a full bitemporal model.
_Avoid_: latest row wins, history overwrite

**Retrieval plan (检索计划)**:
A validated, typed description of domains, exact constraints, semantic intents, relationship paths,
and retrieval lanes needed for one turn. LLM reasoning may propose it; deterministic parsing and
server validation preserve exact constraints and execution bounds.
_Avoid_: free-form tool improvisation, regex route only

**Query rewrite (查询改写)**:
One or more retrieval-lane-specific formulations derived from the original query and session
context. Rewrites preserve the original query and protected exact constraints while making
referents, aliases, semantics, and relation intent explicit.
_Avoid_: replacing the user's query, pronoun substitution only

**Evidence sufficiency (证据充分性)**:
Whether the retrieved evidence supports the material parts of the user's current question, not
merely whether a candidate count threshold was reached. Missing material support may trigger a
bounded targeted retrieval attempt or an explicit limitation.
_Avoid_: non-empty retrieval means sufficient

**Claim-evidence map (断言-证据映射)**:
The internal mapping from each material answer claim to the local or current-Web evidence that
supports it. User-visible citation presentation may be grouped, but the mapping remains explicit.
_Avoid_: unstructured source list

**Evidence-based assessment (证据化评价)**:
An LLM-synthesized judgment over explicit evaluation dimensions and sourced facts, with conditions
and uncertainty stated. The judgment is not stored or presented as an objective canonical fact.
_Avoid_: subjective label as field, unsupported verdict

**Candidate release (候选版本)**:
A run-scoped, internally consistent Canonical/serving/index version awaiting acceptance. It can be
verified without changing the active version and can be promoted or discarded atomically.
_Avoid_: partially updated live data

**Index projection (索引投影)**:
A versioned, reproducible retrieval representation built from a named canonical release and
path-eligibility policy. It accelerates retrieval but is never an independent source of truth.
_Avoid_: vector database as canonical store

**Knowledge gap (知识缺口)**:
A structured, evidence-bearing record that a user or acceptance need lacked an entity, fact,
relationship, freshness, or retrieval path. It can drive recollection or enrichment without making
the online query write directly to canonical data.
_Avoid_: generic error, immediate Web-to-canonical write

**Typed relationship (类型化关系)**:
A directed, role-specific relationship with registered semantics, source assertions, time, and
state. The catalog is extensible, but unsupported LLM inference is not a canonical relationship.
_Avoid_: untyped edge, relationship hidden only in summary text

**Recovery landing (恢复落地区)**:
The immutable, content-addressed evidence layer for forensic copies, historical artifacts, and new
collection responses. Downstream representations are reproducible; landing evidence is not edited
or treated as canonical merely because it was recovered.
_Avoid_: staging table that gets overwritten, direct recovery-to-canonical write
