# Data-Enhancement Iteration Report (2026-07-02)

> Goal (user-confirmed): enhance ALREADY-COLLECTED data (no new collection) — promote+embed the
> not-ready paper/professor subset that the eval's gap cases need. Scope A (promote+embed only,
> no profile enrichment). Range A (prioritize the eval-gap subset, not the full ~34k).
> First-principles frame: data is "retrieval-ready" when (1) quality_status=ready, (2) embedded
> in Milvus, (3) profile specific, (4) cross-domain linked. The gap was (1)+(2): ~70-75% of
> papers/professors not-ready → gated out + not embedded → not retrievable (柯文德's papers).

## 1. The chain (proven end-to-end)

Data-enhancement = 4 steps, all with EXISTING machinery (reused, not reinvented):
1. **abstract backfill** — fetch `abstract_clean` from external sources (the upstream gap; many
   needs_enrichment papers have NULL abstract → can't be summarized). Providers exist
   (`providers/crossref.py`, `providers/openalex.py`).
2. **summary_zh** — LLM-summarize from abstract (script `summarize_papers_zh.py`, commit e292c1a;
   claude-haiku-4-5 via the zenmux anthropic proxy).
3. **promote** — `quality_status` → `ready` (abstract+summary done).
4. **embed** — `run_milvus_backfill.py --domain paper --paper-id` (ready → Milvus paper_chunks).

**Proven on 5 embodied papers**: abstract fetched (Crossref title-search) → summary_zh generated
→ promoted to ready → **embedded (8 chunks, 0 errors)** → rescue-reachable. The milvus
single-writer concern (memory `milvus-single-writer-real-index`) did NOT materialize —
`run_milvus_backfill` embedded fine with the backend up (milvus-lite allowed the concurrent
write; the memory's "fail while backend is up" was over-cautious for this case).

## 2. "不可再修" — the environmental blocker

**24/25 embodied papers have `abstract_clean IS NULL`** (the real upstream gap — not "needs
summary_zh" but "needs abstract"). Abstract-backfill salvaged only **4/24**:
- **Crossref title-search WORKED** (salvaged the 4, with a 0.6 title-match threshold that
  caught + reverted 3 wrong-paper false positives — Crossref `query.title` is fuzzy).
- **OpenAlex 503 (sustained, Retry-After: 60)** + **arXiv 429** + **Semantic Scholar 429** —
  this host is throttled by those APIs. NOT a code defect; environmental.
- 柯文德's papers (old robotics: "Study of similar motion imitation" etc.) aren't in Crossref
  with abstracts + need arxiv/openalex (throttled) or professor-page re-harvest.

So qid27's GT 4 (柯文德/任尔夫/王强/刘桂良) stay RED — their papers are among the 20 throttled
NULL-abstract → can't promote → can't embed → rescue can't reach them. The chain works; the
data-source throttling blocks the specific GT 4.

## 3. Reusable artifacts (committed)

- `apps/miroflow-agent/scripts/summarize_papers_zh.py` (e292c1a) — idempotent LLM-summary;
  `--topic-regex`, `--statuses`, `--dry-run`, `--overwrite`. Re-runs pick up newly-eligible
  papers (NULL summary_zh + has abstract).
- `apps/miroflow-agent/scripts/backfill_embodied_abstracts.py` (2c6aa19) — idempotent
  abstract-fetch via crossref/openalex/arxiv by DOI/id/title; 0.6 title-match threshold; re-runs
  only touch NULL-abstract papers. **Re-run when OpenAlex/arXiv stop throttling this host** to
  complete the remaining 20.

## 4. Data-layer reality (the bigger picture)

- paper: 101440 total, **25066 ready (~25%)** — 33429 needs_enrichment + 8531 partial + 34109
  rejected. The ~75% not-ready is the big recall ceiling.
- professor: 3395 total, **1057 ready (~31%)** — 1668 needs_review + 644 needs_enrichment.
- company (6514) + patent (11408): all ready (no gap).
- The 25-paper embodied subset was the eval-gap probe; the same chain scales to the full ~34k
  needs_enrichment papers (range C, deferred — LLM/abstract-fetch cost).

## 5. What I'd do next (out of this round's scope)

1. **Re-run `backfill_embodied_abstracts.py` when the host's OpenAlex/arXiv throttling lifts**
   (the script is idempotent; it'll complete the 20 + unblock 柯文德's papers → qid27 GT 4
   GREEN). The throttling is environmental — wait it out or rotate IP/mailto.
2. **Scale the chain to the full ~34k needs_enrichment papers** (range C) — abstract-backfill +
   summarize + promote + embed, batched. This is the big recall-ceiling raiser; needs the
   throttling resolved + batched LLM cost management.
3. **Professor promote+embed** (~2338 not-ready professors) — same chain, professor domain
   (`run_milvus_backfill --domain professor`). The rescue + professor-topic recall both benefit.
4. **For papers with no external id (prof_page_only shells)** — the `recover-paper-shells-via-
   realtime-resolution` pattern (title-based realtime resolution); needs the throttled sources.

## 6. Net

The data-enhancement chain is proven end-to-end (abstract → summary → promote → embed → rescue),
reusing existing machinery + 2 new idempotent scripts. 5 papers through the full pipeline,
embedded, rescue-reachable. The milvus single-writer concern was over-cautious (embed works with
backend up). The blocker for the eval's GT 4 (柯文德) is environmental: external-API throttling
(OpenAlex 503 / arXiv 429) on abstract-backfill for old robotics papers not in Crossref. That's
the "不可再修" line — the chain is ready; the data-source throttling + the scale are the next
workstream, not a code fix I can make autonomously.
