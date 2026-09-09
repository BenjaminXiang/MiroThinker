# Data-gap first-principles analysis (2026-07-03)

> Reusable technical lesson. Corrects and extends `2026-07-02-retrieval-gaps-root-cause-map.md`
> with code- and DB-grounded evidence gathered this session. Model-facing artifacts in English
> per [[language_preference]].

## 1. What the benchmarks said (quantified)

| Oracle | File | Result | Reading |
|---|---|---|---|
| Recall (post-fix) | `retrieval-generation-alignment/post-fix-recall.json` | 12/24 = 50% | single-entity cases all 1/1; misses cluster at qid19(0/2), qid50(0/4), qid51(0/1), qid4(1/5), qid13(2/3) |
| Latency | `retrieval-generation-alignment/latency-baseline.json` | SLO FAIL | overall p95 9.61s; only FAIL is qid26 `D_cross_domain_topic` p95 9.6s |
| Precision | `retrieval-generation-alignment/precision-baseline.json` | dirty candidates | candidate_names carry web article titles (知乎/21经济网/澎湃) and each name repeats 3×; dedup is by paper_id, not surface name |

The `diagnosis-baseline.md` conclusion — "retrieval logic is sound, the gap is DATA" — is
directionally right but under-structured: it treats "data gap" as one block and so hides the
mechanism that actually decides retrievability.

## 2. The structural root the existing map misses

> **Retrievability is coupled to completeness. `is_indexable ≡ quality_status == "ready"`, and
> `ready` treats *derived* fields (summary_zh) as a precondition for *reachability*. The data a
> query matches against (title/abstract) and the data the gate demands (summary_zh) are different
> things — but the gate makes the second gate the first.**

Evidence chain (all verified this session):

- `src/data_agents/quality/gating_contract.py:60-69` — `is_indexable` returns
  `normalize_quality_status(quality_status) == "ready"`. Pure status, no row.
- `src/data_agents/paper/milvus_backfill.py:181` — `_is_indexable_paper` is
  `identity not in {rejected,merged} AND quality_status == "ready"`. The backfill SQL
  (`:50-56`) **fetches partial/needs_enrichment rows then deletes their chunks** at `:86-97`.
- `src/data_agents/paper/chunker.py` — `chunk_paper` always emits a `title` chunk, plus
  optional `abstract`/`intro` chunks. So a paper with a title is *chunkable* regardless of
  summary_zh; the gate, not the chunker, blocks it.

The 2026-07-02 map lists root **D (data not retrieval-ready)** and **E (external throttling)** as
peers and claims "E blocks D1 (paper abstracts) AND D2 (professor metrics)." Code refutes the D2
half:

- `professor/quality_gate.py` — `PROFESSOR_READY_REQUIRED_RULES` and
  `_needs_enrichment_reasons` reference **no** `h_index`/`citation_count`. The `h_index` column
  exists but the ready gate never consults it. So **professor readiness has zero external-source
  dependency** — the "E blocks professor" claim is false.

That collapses the map's D2 branch and makes the professor path fully E-bypassable (consistent
with `2026-07-02-next-step-gap-fill-plan.md`'s correction, now code-confirmed).

## 3. The retrievability ceiling, by domain (DB-grounded)

Professor (`identity_status <> 'merged_into'`; 3409 total):

| status | count | gate reason stage (open quality-gate issues) | local-fixable? |
|---|---|---|---|
| ready | 794 | — | — |
| needs_review | 1889 | paper_attribution 867, data_quality_flag 683, coverage 478, research_directions 333, name 26, affiliation 22, identity 2 | **100% local** (dedup, contradiction, shallow/short profile, missing research_overview_zh, open pipeline_issue) |
| needs_enrichment | 700 | (same rule families) | **100% local** (LLM regen from profile_raw_text + papers) |
| low_confidence | 26 | missing_official_source / non_person_name | mostly local |

Feasibility of local professor repair: only 5/1889 needs_review and 16/700 needs_enrichment lack
`profile_raw_text`; **1592 not-ready professors already have a verified paper link**. Zero
external deps to raise the professor recall ceiling from ~794 → ~3000.

Paper (`identity_status NOT IN ('rejected','merged')`; ~49.9k):

| status | count | abstract_clean NULL | summary_zh NULL | retrievable today? |
|---|---|---|---|---|
| ready | 25990 | 1 | 0 | yes |
| needs_enrichment | 14343 | 14343 | 14343 | no — and **0 have full-text abstract/intro** (genuinely data-poor) |
| partial | 9300 | 9279 | 7279 | no — but **1366 have `paper_full_text.abstract`, 644 have `intro`** (data IS collected locally) |

So `partial` conflates two populations:
- **partial-with-rich-text (~2010)** — full text already ingested locally; blocked from retrieval
  only because `summary_zh` (a *derived* field) is null. Pure structural waste.
- **partial-title-only (~7212)** — only a title chunk; indexing these is a real precision risk.

Company: 6514/6514 ready (full coverage — not a data-gap domain).

## 4. A second structural finding: embedding-source ⊋ snippet-source

`retrieval.py:1071` builds the generation snippet from `("summary_zh", "abstract_clean")` only.
`milvus_backfill.py:174` builds the *embedding* from `summary_zh or abstract_clean or abstract
(paper_full_text)`. So a paper can be embedded off `paper_full_text.abstract` yet produce an
**empty snippet** for generation — recalled but invisible to the answer, hence invisible to the
recall oracle. Any "make partial retrievable" change that does not also extend the snippet chain
yields recall-logic GREEN but eval RED. This asymmetry is itself a first-principles defect worth
its own line in the map (it is not in the 2026-07-02 map).

## 5. A reachable path the gate does not control: the entity graph

`get_related_objects(paper→professor)` (`_paper_profects_sql`, `retrieval.py:597-646`) filters on
`link_status='verified'` and `identity_status='resolved'` — **not** on professor
`quality_status`. So the 1592 not-ready-but-verified-linked professors are reachable *today* via a
graph rescue wired onto the topic path, independent of any gate/promote/embed work. The rescue
**IS shipped** (FM4): `_lookup_professors_by_topic` (chat.py:1787) recalls papers on the topic
and rescues their authors via `get_related_objects(paper→professor)` when professor vector
recall is thin; it is reached by the `ctype=="B"` branch (chat.py:4447 →
`_lookup_domain_by_topic(professor)`), so `B_semantic_topic_search` already uses it (qid50's
王强 came through it). The remaining gap is therefore **rescue effectiveness + professor
readiness**, not wiring.

## 6. The four levers, ordered by leverage × E-bypass

| # | Lever | Unlock | E-bypass? | Capability touched | Risk |
|---|---|---|---|---|---|
| **0** | Decouple retrievability from completeness: make `partial`-with-collected-full-text retrieval-ready (+ extend snippet chain so they are presentable) | ~2010 papers into the vector pool; pure local-data win | yes | `data-quality-gating` + `agentic-rag-retrieval` | low (rich chunks; title-only excluded) |
| **1** | Professor reason-class batch repair → promote → embed | professor recall ceiling ~794 → ~3000; qid27/qid50 | yes | professor pipeline + `data-quality-gating` | medium (LLM regen quality) |
| **2** | ~~Wire graph rescue (Move C) onto topic/B path~~ **Already shipped (FM4)** — rescue is wired into `_lookup_professors_by_topic`, active for `B_semantic`/Pattern-B professor-topic. Real gap = rescue **effectiveness** (the `len(rows)<limit` gate; N+1 calls) + professor readiness (Lever 1) | qid50 only 1/4 because most profs aren't in the vector index (Lever 1) | n/a | `agentic-rag-retrieval` | low |
| **3** | Paper abstract: local PDF/intro route + E mitigation (Crossref retry, polite-pool, IP rotation) | needs_enrichment 14343 ceiling | partial (PDF route yes) | paper pipeline | medium (E-gated) |
| **4** | Candidate hygiene: surface-name dedup + drop web-article titles | precision oracle | yes | `agentic-rag-retrieval` | low |

First slice = **Lever 0**: it is the only change that strikes the structural root
(completeness↔retrievability coupling), it is E-bypass, and its scope is provably bounded by the
partial-with-rich-text population. Title-only indexing (the ~7212 + 14343) is deliberately a
separate, precision-gated change.

## 7. Honest gap — not verified this session

D3 (ready-but-not-embedded): Postgres has no embedding ledger column, so the count of
ready-but-unindexed entities is unmeasured here. Milvus (`apps/miroflow-agent/milvus.db`,
single-writer, held by the running backend — see [[milvus-single-writer-real-index]]) is the only
source. If non-zero, "embed already-ready entities" is a zero-data-work lever that precedes Lever 0.
**First action of any implementation slice: measure D3.**

## 8. Correction summary vs the 2026-07-02 map

- **D2 (professor metrics E-blocked): FALSE.** No gate rule reads h_index/citation_count.
  Professor readiness is 100% local. Removes the professor half of root E's reach.
- **New structural root: completeness↔retrievability coupling** (`is_indexable ≡ ready`, ready
  demands derived summary_zh). This is the actual mechanism behind "partial papers not
  retrievable" and is absent from the A–G map.
- **New defect: embedding-source ⊋ snippet-source** — recalled-without-snippet makes eval-RED
  even when recall-logic is GREEN.
- **Root B's fix is gate-independent** — graph rescue reaches not-ready professors via
  link_status/identity_status, not quality_status.
- Lever 0 selected as first slice (structural, E-bypass, bounded). Title-only indexing deferred.

## 9. Status (2026-07-05) — Lever 0 Accepted; the real ceiling is Lever 1/2

Lever 0 (`make-partial-papers-retrievable`) is implemented and **Accepted
(structural-correctness)**. Outcome:
- 4 seams shipped; contract suite 42 + regression 1037 green; `openspec validate
  --strict` clean; rebackfill embedded **1952 partial+rich-text papers** (6845 chunks).
- Recall eval: **+1 reproducible** (王强 on qid50 — topical partials → graph rescue).
  The other qid50 professors are **out-of-scope for Lever 0** (not-ingested /
  no-partial-rich / rescue issues), so +2 was unachievable on this oracle.

**The "search returns limited results" symptom (user-confirmed on the frontend) is
NOT materially moved by Lever 0.** It is dominated by the bigger ceilings this
analysis identified — in priority order:
1. **Lever 1** — 77% of professors (2615/3409) are not `ready` (gate-blocked from the
   professor vector index). Every professor-topic/professor-profile query is capped by
   this. Highest single lever for frontend search breadth.
2. **Lever 2** — graph rescue IS already wired (`_lookup_professors_by_topic`,
   active for B_semantic/Pattern-B). The remaining gap is rescue **effectiveness**
   (the `len(rows)<limit` gate suppresses it when ≥20 profs recall, even tangentially;
   N+1 `get_related_objects` calls) and, dominantly, professor readiness (Lever 1).
3. **Lever 3** — 48% of papers (14343 needs_enrichment + ~7212 title-only partial)
   lack abstracts → not retrievable. The big paper-search ceiling; E-gated (OpenAlex)
   with a local PDF/full-text bypass.
4. **FM1a** — entities simply not ingested (e.g. 任尔夫). Separate ingest workstream.

Lever 0 was a necessary structural fix (it removed the completeness↔retrievability
coupling so future promotions flow into retrieval), but it is not the lever that
widens frontend search breadth on its own. **Next slice: Lever 1 or Lever 2.**

D3 (ready-but-not-embedded) remains **unmeasured** (disjoint from Lever 0; open).
