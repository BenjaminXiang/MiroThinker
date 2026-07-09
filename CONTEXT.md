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
