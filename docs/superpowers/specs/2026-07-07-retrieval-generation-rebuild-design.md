# Retrieval-Generation Rebuild — Design (doc-as-contract)

> End-to-end rebuild of the retrieve→context→fuse→synthesize pipeline.
> Status: design — grilling-validated 2026-07-07. Contract: doc-as-contract
> (`openspec/` absent on this branch).
> Predecessor: `docs/superpowers/specs/2026-07-07-synthesis-depth-fixes-design.md`
> (its Fix 1/3 kept; Fix 2 reverted — superseded by this rebuild).

## Goal

End-to-end correct retrieval-generation: answers that are **right, complete, and
context-coherent** across single-turn list/profile/knowledge and multi-turn follow-ups,
measured toward population-level 90%+. Not demo-scoped.

## First principle

End-to-end accuracy is a **product**, not an average:

```
accuracy ≈ knowledge-availability × retrieval-precision × context-coherence × synthesis-fidelity
```

Any factor at 0 → answer wrong. The three failing examples each zero a different factor:
- 普渡 (delivery robots): synthesis-fidelity=0 (DB has 普渡, buried under web junk).
- PCB makers: retrieval-precision=0 (equipment suppliers matched as makers) + knowledge-availability=0 (top-10 makers 3/15 in DB).
- 视触觉 professors: retrieval-precision=0 (semantic neighbors + paper-rescue admit off-topic) + context-coherence=0 (follow-up loses prior entity set).

Patching one flow lifts one factor; reaching 90% needs **all factors strong** → rebuild as layers, not patches.

## Architecture — Route C (hybrid), forced by invariants

CLAUDE.md §5: *"Evidence must remain structured, traceable, source-grounded, auditable."*
→ **Retrieval must be deterministic and auditable** (purely agentic — LLM writing queries
on the fly — is rejected: non-replayable, hallucinates query intent).
But "dump / no relevance / lost context" are **reasoning failures** — exactly what LLMs do
well; currently the LLM is only a formatter (rule-2 forces it to dump all).

**Principle:** deterministic retrieval + fusion (auditable, holds the invariant) → LLM reasons
on that grounded evidence (relevance judgment / synthesis / coreference). The LLM never selects
retrieval itself, so reasoning stays traceable and the retrieval stays auditable.

## Layer map — 8 failures → 5 layers + probe (root causes code-verified)

| Failure | Root cause (verified) | Layer | Fix |
|---|---|---|---|
| S1 dump | `_CHAT_SYNTHESIS_PROMPT_LIST` rule-2 "must list every entity, omit none" (chat.py:102) | **A** | two-step reasoning synth |
| S2 no clean refusal | same rule, no "no-relevant → refuse" branch | **A** | sufficiency gate → clean refuse |
| S3 retrieval precision | company: `%term%` ILIKE over a concat blob, no score/field-filter (chat.py:975-1103); professor: vector fuses narrative, paper-rescue admits tangential, no score gate (retrieval.py:329-461, chat.py:1906-1940) | **C** | field-tiered match + score gate |
| S4 shallow payload | matched entities lack research_topics/etc. | **C** (depth) | surface/require matching fields |
| S5 coverage | DB is Shenzhen-local; PCB top-10 only 3/15 | **E** | data backfill pipeline |
| S6 lost context | only single-entity pronoun→name (chat.py:1609); no set-level coref; `_handle_d_narrowing` locks same-domain (chat.py:4427) | **D** | set coref + cross-domain intent |
| S7 dirty/redundant web | web appended raw (no dedup, no marketplace filter) | **B** | marketplace blacklist + entity-name dedup |
| S8 no source-aware fusion | DB+web flattened, no weighting | **B** | source-aware render (DB curated / web supplemental) |

## Layer designs

### Probe (measurement — built first, drives everything)
Gold-entity set (~10-15 representative queries; gold sourced from **authoritative rankings
/ domain knowledge, not the DB** to avoid circular bias). For each query: get
`matched_objects`/`matched_professors`, check gold entities found (retrieval recall) and in
DB (coverage). **Distinguishes C from E**: in-DB-but-not-retrieved = precision (C);
not-in-DB = coverage (E). Settles the A-vs-C ordering question with data, not opinion.

### Layer C — retrieval precision (the content factor)
- **Company**: field-tiered match. `product_category`/`industry` field hit = tier1 (true target);
  narrative/scenario hit = tier2 (adjacent). Score + threshold; tier1 ranked first. Replaces
  the bare `%term%` blob ILIKE (chat.py:975-1103).
- **Professor**: rerank → **absolute score gate** (drop low-score, not just top-k); paper-rescue
  requires `research_topic` real match (not one tangential paper); weight `research_directions`
  in the embedding narrative.
- Thresholds tuned by the probe, not guessed.

### Layer A — reasoning synthesis (the fidelity factor) — two-step
- **Step 1 — relevance/sufficiency** (structured output): per entity `relevant`/`adjacent`/`irrelevant`
  + `sufficient` (can we answer? what's missing?). Audit-logged (holds §5 traceability).
- **Step 2 — synthesize/refuse**: feed only relevant set → dedup, rank, cite [N]; `sufficient=false`
  → clean refuse + state the gap (points to E/web, **not** agentic re-retrieval).
- **Relevance criteria = structured field-hit + LLM fallback** (company: product_category/industry;
  professor: research_topic) — **same field semantics as Layer C**, so A and C don't fight.
- Kills rule-2's dump mandate. Local LLM (deepseek-v4-pro for accuracy; qwen3.6 available).
- Accuracy > latency >> cost → two-step accepted.

### Layer B — source-aware fusion + web quality
- Marketplace domain blacklist (alibaba/1688/taobao/11467顺企网/huangye88/made-in-china).
- Dedup web by extracted entity name (PCB top-10 ×3 listicles → 1).
- Source-aware render: `## 数据库已知` (curated, primary) + `## 网络补充`, cross-source by name.

### Layer D — multi-turn set coreference + cross-domain
- Resolve `上述/这些/他们` → prior `last_result_set` ID set (not single-entity pronoun).
- Cross-domain intent detection: when follow-up jumps domain with a prior set → batch
  `get_related_objects` over the set (new path; `_build_c_type_response` only does single entity).
- `looks_like_narrowing_query` must distinguish same-domain-narrow from cross-domain-jump.

### Layer E — coverage / data population (long-running)
- Backfill notable companies by category (PCB top-10, delivery-robot leaders, etc.) via
  the company pipeline. Probe's coverage gap directs the priority.

## Sequence (dependency-driven, not demo-driven)

```
Probe (measure C/E) → C (precise retrieval) → A (reasoning synth) → D (context)
                         ↑ kill-dump + B (fusion) as parallel quick-wins
   E (coverage)  ── probe-directed, parallel/long-running
   measurement   ── throughout (eval-harden for the judge side already shipped)
```

Rationale: C is upstream (content); A is downstream (presentation). A can't answer what C
didn't retrieve. But kill-dump + B are cheap and decoupled → parallel quick-wins so C's
gains are visible end-to-end. The probe settles C-vs-E priority with data.

## Invariants preserved (CLAUDE.md §5)
- Evidence traceable/source-grounded: retrieval deterministic + Step-1 audit log.
- A-G classification semantics: unchanged (D-route gains set-coref, not new query classes).
- `_VALID_DOMAINS`, evidence shape, `run_id`: unchanged.
- No agentic retrieval (LLM never writes queries) → auditable.

## Non-goals (this rebuild)
- New domains beyond professor/company/paper/patent.
- Migration / schema change (Layer C/E may add a `product_category` filter index, but no
  data-contract change without its own slice).
- Pure-agentic RAG (rejected by the invariant above).

## Files (anticipated)
- Probe: `apps/admin-console/scripts/probe_retrieval_precision.py` + gold set.
- Layer C: `chat.py` (`_lookup_companies_by_topic`, `_lookup_professors_by_topic`), `retrieval.py`.
- Layer A: `chat.py` (`_CHAT_SYNTHESIS_PROMPT_*`, `_call_gemma_synthesis` → two-step).
- Layer B: `chat.py` (`_build_evidence_blocks` web section, fusion).
- Layer D: `chat.py` (`_handle_d_narrowing`, `_build_c_type_response`), `services/chat_context.py`.
- Layer E: company backfill scripts (separate).
