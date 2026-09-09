# Professor→Paper Gap-Closure Portfolio (Re-baselined)

> Date: 2026-06-22. Status: **planning only — no execution yet.**
> Author: Claude (design/planner). Codex handoff pending per CLAUDE.md §1.
> Re-baselines: supersedes the counts in `docs/plans/2026-06-16-dirty-data-gap-closure-portfolio.md` and the 2026-05-04 `docs/index.md` matrix. The 6/16 wave taxonomy (W0a–W5) is retained as the underlying change-IDs; this doc corrects priorities and sequencing against **real `miroflow_real` counts (2026-06-22)**.

## §0. Why this re-baseline was needed

The 6/15 planning docs and the `docs/index.md` matrix are stale relative to today's database. Several gaps they flag as large have already been largely closed, and the corpus has grown ~2×. Acting on the stale numbers would mis-prioritize (notably: an Epic for professor field-completion whose real residual is ~240 professors, and a "paper ready = 0" claim that is actually 23,183). This portfolio grounds every cluster in a fresh read-only scan and re-sequences the work.

### Real DB baseline (2026-06-22, read-only scan of `miroflow_real`)

| Metric | 6/15 doc claim | Real today | Verdict |
|---|---|---|---|
| Paper total | ~49,814 | **97,774** | corpus ~2× |
| Paper `ready` | "0" → "9,461" | **23,183** | ready grew 2.5× |
| Paper `unverified` identity | 7,297 | **53,165** (W0b-eligible **28,928**) | larger than expected |
| Professor `profile_summary` < 200 chars | 441 | **3** | effectively closed |
| Professor missing `research_overview_zh` | 2,510 | **839** (2,548 present) | largely closed |
| Professor missing `paper_summary` | 2,200 | **1,095** | halved |
| Professor missing `education` (active fact) | "6/10 schools 0%" | **239** (93% covered) | effectively closed |
| Professor missing `academic_position` | — | **34** (99% covered) | effectively closed |
| DOI pollution | 4 strict + `doi_quality.py` uncommitted | **0** | clean |
| `run_id` null (professor/paper/fact/link) | partial | **0** (all four tables full) | traceability complete |
| `canonical_name_en` missing | "41% polluted" | **3,314 missing (98%)** | *missing*, not polluted |

**Scan methodology**: read-only SQL against `miroflow_real` (proxy vars unset per project env). Counts are point-in-time; the per-phase acceptance contracts below require re-running the relevant count at phase start and exit.

---

## §1. Two axes — kept separate (per user directive 2026-06-22)

These are different problems with different fix strategies. Mixing them re-manufactures dirty data while closing gaps. Every phase below states which axis it serves.

- **Axis 2 — dirty already-collected data**: rows in the DB today with quality problems. Bounded, directly improves online retrieval. Treat first where cheap and safe.
- **Axis 1 — collection-code gaps**: source text/fields never acquired. Long-tail, per-seed. Treat after the collection bug that feeds Axis-2 duplicates is stopped, else gap-filling re-injects dirt.

---

## §2. Axis 2 — dirty clusters (real counts)

| ID | Cluster | Real count | Severity | Root cause |
|---|---|---|---|---|
| D1 | Unverified papers still in retrieval | 53,165 unverified; **28,928 W0b-eligible** | 🔴 high | identity gate never wired (W0b core code applied, change not closed) |
| D2 | Duplicate paper rows | 25,527 groups / 61,757 rows; biggest group **162** | 🔴 high | ingest inserts per-professor-row not per-paper; + crawl-loop bug (162/114/101× same title) |
| D3 | Open `pipeline_issue` (classified, not cleared) | 10,336 open (6,657 high) | 🟠 med-high | closure run only classified blockers, never wrote |
| D4 | `canonical_name_en` missing | 3,314 (98%) | 🟠 med | EN name never extracted |
| D5 | `patent_summary` missing | 3,387 (100%) | 🟡 low-med | never generated |
| D6 | Professors with 0 verified paper links | 1,043 | 🟠 med | link verification gap |
| D7 | `ready` + `unverified` (crossref/manual/dblp source) | 9,032 | 🟠 med | metadata enriched but prof-link unverified — **out of W0b scope** |

### D1 blast-radius (decisive for W0b safety)

The 28,928 W0b-eligible rows (unverified + `prof_page_only` + no verified link) break down by `quality_status`: **28,927 `needs_enrichment` + 1 `rejected` + 0 `ready`**.

→ W0b rejection touches **zero `ready` papers**; it only evicts empty-shell `prof_page_only` papers from Milvus. Blast radius is safe; dry-run→apply can proceed once the plausible-title guard lands. 28,926 of these have only `candidate` links (never verified) — exactly the wrong-attribution population W0b targets.

**Growth warning (2026-06-22 re-baseline)**: the eligible set was **1,519 on 6/16** and is **28,928 today** — a 19× increase dominated by fresh UPC/crawl output (new `prof_page_only`/`unverified`/candidate-only rows), not corpus growth alone (papers only ~2×). Implications for Phase 1: (a) the dry-run is a heavy LLM operation (28,928 gate calls) — batch + rate-limit + monitor; (b) many eligible rows are in-flight (still being enriched) — the apply should target stable subsets; (c) the 6/16 "92% garbage title" finding may not hold for the fresh batch — the dry-run reveals the true split. See `.agents/runs/wire-paper-identity-gate-rejection/eligibility-baseline.json`.

> Note: the SQL proxy for title pollution (~312 obviously bad) is a *lower bound*. The real guard `is_plausible_paper_title` (~40 regexes) is stricter, so the true reject rate is knowable only by running the W0b dry-run. This is the first acceptance gate of Phase 1.

### D2 structure (partly an Axis-1 collection bug)

Top groups: `简单氧化物mgo:cr可调自恢复应力发光特性研究` ×162, `全光逻辑处理单元实现光子智能计算` ×114, `fets: a feature-aware framework...` ×101, `以课程成果转化为导向培养创新人才` ×67 (teaching article, not a paper), `《马王堆汉墓出土香囊》` ×53 (museum exhibit). Two classes: (a) genuine co-authored papers collected as N rows (should be 1 paper + N links); (b) single-page crawl-loop bug collecting the same title 162×. 17,936 groups have a DOI (programmatic dedup); 7,591 have no DOI (heuristic/LLM review). **Class (b) is an Axis-1 collection bug.**

---

## §3. Axis 1 — collection-code gaps (real counts)

| ID | Gap | Real count | Severity | Code-level root cause |
|---|---|---|---|---|
| G1 | Title-only shell papers (no abstract/summary/full-text) | **66,401 true dead-ends** (68% of papers) | 🔴 high | homepage paper extractor returns title only, source text never fetched |
| G2 | `full_text_fetcher` `no_arxiv_id` failures | 25,860 | 🔴 high | fetcher is **arxiv-first**; 66,731 `prof_page_only` papers have no arxiv_id → skipped |
| G3 | Missing `summary_zh` + `abstract_clean` (both) | 66,536 | 🔴 high | downstream of G1/G2 |
| G4 | full-text fetch failure rate | 26,558 / 43,762 = **61%** | 🟠 med | weak PDF strategy; errors dominated by 25,860 `no_arxiv_id` |
| G5 | 0-paper professors (homepage present, 0 links) | 531 (**15.7%**); worst 深圳信息 57%, 电子科大(深圳) 49%, 哈工大(深圳) 24% | 🟠 med | per-seed homepage citation template not adapted |
| G6 | Collection-time duplicate generation | 162/114/101× same title | 🟠 med | ingest INSERTs a new paper row without checking the dedup anchor; builds `professor_paper_link` instead |
| G7 | `source_page.http_status` mostly blank | 5,125 blank vs 15 with `200` | 🟡 low | fetch metadata not persisted |

---

## §4. Phase plan (Phase 1 = first change-id to execute)

Each phase: **goal · change-id · axis · scope · exit criteria (acceptance contract) · dependencies · evidence**. Phases 2–6 are registered as `proposed` placeholders; only Phase 1 is opened for execution now.

### Phase 0 — Governance reconcile (doc-only, no OpenSpec)
- **Goal**: make ledgers/index match reality so no one is misled by stale counts.
- **Change-id**: W3b `governance-ledger-index-reconcile` (debt-register, doc-only).
- **Axis**: meta.
- **Scope**: register 7 active + ~15 archived changes in `change-ledger.md`; refresh `docs/index.md` to 2026-06-22 with the §0 baseline table; re-route "unverified promotion" notes.
- **Exit criteria**: (1) every dir under `openspec/changes/` has a ledger row (active or archived); (2) `docs/index.md` matrix carries the 2026-06-22 scan date and the corrected counts; (3) no ledger row claims a status contradicted by its `openspec/changes/<id>/tasks.md` checkbox state.
- **Dependencies**: none. **Cheapest, do first.**

### Phase 1 — Close W0b identity-gate rejection (Axis-2, D1) ← FIRST CHANGE TO EXECUTE
- **Goal**: promote LLM same-person-gate rejections to `paper.identity_status='rejected'` so wrong-attribution `prof_page_only` papers drop out of Milvus retrieval; reversible, dry-run-first, flag-gated.
- **Change-id**: `wire-paper-identity-gate-rejection` (already open; 12/24 tasks done, core code applied). Capability `paper-identity-status`.
- **Axis**: Axis-2 (dirty existing data).
- **Scope (remaining tasks)**: 2.4/2.5 plausible-title guard; 5.6 guard tests; 6.1 real dry-run on 28,928 eligible; 6.2 bounded `--apply`; 6.3 Milvus re-backfill; 7.1–7.4 acceptance/validate/ledger.
- **Exit criteria (acceptance contract)**:
  - AC1: `decide_identity_status_rejection` rejects only when (no verified link) AND (`canonical_source='prof_page_only'`) AND (`is_plausible_paper_title(title_clean)` True). Guarded by unit tests incl. `test_decide_no_change_for_garbage_title`. **RED = the 5.6 tests; GREEN = they pass without weakening the gate.**
  - AC2: dry-run on `miroflow_real` reports `examined / rejected / unchanged` counts; saved to `.agents/runs/wire-paper-identity-gate-rejection/`; reject count compared to the 28,928 baseline (1.2). Real reject rate recorded (expected < 28,928 due to the guard).
  - AC3: bounded `--apply` transitions only qualifying rows to `identity_status='rejected'`; each carries a stage-`identity_gate` `pipeline_issue` with `run_id`; **0 `ready` papers touched** (verified by a post-apply `quality_status` audit on the rejected set).
  - AC4: Milvus re-backfill excludes the rejected set; a spot-checked rejected paper no longer returns in retrieval.
  - AC5: reversibility — `restore_identity_status` re-establishes a prior status when a `verified` link appears; `quality_status` never mutated by the rejection path.
  - AC6: `openspec validate wire-paper-identity-gate-rejection --strict` exits 0; ledger status → `tasks-complete-not-archived`.
- **Dependencies**: none. **Safe to start immediately** (0 `ready` in eligible set).
- **Evidence**: `.agents/runs/wire-paper-identity-gate-rejection/{verification-contract.md, implementation-plan.md, eligibility-baseline.json, dry-run-*.jsonl, apply-summary.json, milvus-rebackfill-log}`.
- **Out of scope**: the ~24,237 non-`prof_page_only` unverified rows (crossref/manual/dblp/s2) → D7/Phase 6; dead `apply_identity_gate_reevaluation` cleanup (Gap A); gate threshold changes.

### Phase 2 — Stop collection-time duplicate generation (Axis-1, G6 → feeds D2)
- **Goal**: ingest checks the dedup anchor before INSERT; on hit, builds `professor_paper_link` instead of a new `paper` row. Stops D2 growth.
- **Change-id**: **NEW** `ingest-dedup-anchor-before-insert` (proposed).
- **Axis**: Axis-1 (collection-code gap).
- **Scope**: `paper/homepage_ingest.py` (and SIGS bridge path); dedup anchor = DOI > arxiv_id > `lower(title_clean)+year+first-author-token`; INSERT→link-attach on hit.
- **Exit criteria**: (1) a regression test asserts N professors' pages listing the same DOI produce 1 `paper` row + N links (not N rows); (2) re-ingesting the 162×/114×/101× seed samples produces 0 new duplicate rows; (3) no public API/serialized-format change.
- **Dependencies**: none. **Must precede Phase 4** (else dedup clears while ingest re-grows).

### Phase 3 — full_text_fetcher non-arxiv path + W1a attribution gate (Axis-1, G1/G2/G3)
- **Goal**: acquire source text for `prof_page_only` shells via prof-page PDF/landing-page fetch + Jina reader fallback, **gated by the W1a web-attribution gate** so D1/D2 contamination is not re-manufactured.
- **Change-id**: `W1a title-resolver-web-attribution-gate` (proposed) + `W2a abstract-web-reader-fallback` (proposed, hard-depends on W1a).
- **Axis**: Axis-1.
- **Scope**: W1a — web tier of `title_resolver` requires DOI/arxiv-id match OR (title_match≥0.85 AND author-token Jaccard≥0.3); W2a — four-providers-empty → Jina fetches the row's own `pdf_url`/landing_page → writes to `paper_full_text` (NOT `abstract_clean`); not auto-`ready`.
- **Exit criteria**: (1) W1a unit/contract tests assert contaminated titles are not written; web-sourced rows carry a lower-confidence tag; (2) W2a fallback writes only to `paper_full_text`, never `abstract_clean`; (3) matching `pipeline_issue` resolved on success; (4) `no_arxiv_id` failures drop by an order of magnitude on a pilot slice.
- **Dependencies**: **W1a must land before W2a.** This is the hard blocker of the whole gap-filling chain.

### Phase 4 — Dedup existing duplicates (Axis-2, D2)
- **Goal**: merge the 25,527 duplicate groups after Phase 2 stops growth.
- **Change-id**: `W2e duplicate-paper-review-workflow` (proposed).
- **Axis**: Axis-2.
- **Scope**: 17,936 DOI-groups → programmatic merge + `paper_merge_alias`; 7,591 no-DOI groups → human/LLM review workflow; distinguish class (a) genuine co-authorship (1 paper + N links) from class (b) crawl-loop residue.
- **Exit criteria**: (1) `paper_merge_alias` covers all DOI-confirmed groups; (2) biggest group drops to single digits; (3) no auto-merge without a confirmed anchor (review-gated); (4) retrieval de-dups via the existing `merged` exclusion.
- **Dependencies**: Phase 2 (no regrowth).

### Phase 5 — Per-seed homepage paper extraction (Axis-1, G5)
- **Goal**: raise 0-paper rate via per-seed citation-template fixes.
- **Change-id**: `W2c homepage-cms-selector-coverage` (proposed) + per-seed work units from `docs/plans/2026-06-16-professor-paper-cleanup-seed-checklist.md`.
- **Axis**: Axis-1.
- **Scope**: attack P0 seeds first (深圳信息 57%, 电子科大(深圳) 49%, 哈工大(深圳) 24%); per-seed: sample 5–10 0-paper profs → identify citation template → fix extractor → dry-run re-extract → verify 0-paper rate drops + `is_plausible_paper_title` filter → ingest via `run_homepage_paper_ingest.py`.
- **Exit criteria**: (1) 0-paper professors drop from 531 to <100 (each school <10%); (2) each seed has a dry-run→ingest artifact; (3) no new D2 rows (Phase 2 guard holds).
- **Dependencies**: Phase 3 (stable source text); per-seed incremental.

### Phase 6 — Field/link residual completion (Axis-2, D4/D5/D6/D7)
- **Goal**: close the small remaining structured-field/link residuals.
- **Change-ids**: `W0c professor-summary-overwrite-on-recrawl` + `W2d paper-summary-into-ingest` + `W2b research-overview-extractor-broadening` + a D7 prof-link verification pass.
- **Axis**: Axis-2.
- **Scope**: D7 — verify the 9,032 `ready`+`unverified` crossref rows via `batch_verify_paper_identity`; D6 — 1,043 profs with 0 verified links; D4 — EN-name extraction backfill (3,314); D5 — `patent_summary` generation (3,387).
- **Exit criteria**: (1) `ready`+`unverified` → 0 (verified or re-classified); (2) `canonical_name_en` coverage >95%; (3) `patent_summary` non-null for profs with linked patents; (4) no regression to D1/D2.
- **Dependencies**: low; largely parallelizable.
- **Priority note**: `professor-profile-field-completion-pipeline` (the 0/24 Epic) — its original premise ("6/10 schools 0% education") is falsified by the scan (education missing only 239, position 34). **Downgrade**: narrow to a small L3 ORCID/OpenAlex backfill for the ~239 education residuals, not a 4-layer Epic.

---

## §5. Sequencing

```
Phase 0  Governance reconcile (doc-only, ~½ day)
   │
Phase 1  Close W0b (D1) — safe, 0 ready touched          ← execute first
   │
Phase 2  Stop collection-time dup (G6) — stop the bleed
   │
   ├─ Phase 3  full_text_fetcher + W1a (W1a must precede W2a)
   │       │
   │       └─ Phase 5  per-seed extraction (incremental)
   │
Phase 4  Dedup existing (D2) — after Phase 2 stops growth
   │
Phase 6  Field/link residuals (D4/D5/D6/D7) — parallelizable
```

**Downgraded**: `professor-profile-field-completion-pipeline` Epic → narrow L3 backfill (real residual ~240).
**Max single-point leverage**: Phase 1 (W0b) + Phase 3 (W1a→full_text). Former cleans online retrieval now; latter unlocks the 66,401 shell channel.

---

## §6. Mapping to the 6/16 W-wave taxonomy

| Phase | 6/16 wave(s) | Status |
|---|---|---|
| 0 | W3b | not-started (doc-only) |
| 1 | W0b `wire-paper-identity-gate-rejection` | open, 12/24, execute now |
| 2 | (new) `ingest-dedup-anchor-before-insert` | proposed |
| 3 | W1a + W2a | proposed (W1a blocks W2a) |
| 4 | W2e | proposed |
| 5 | W2c + per-seed checklist | proposed |
| 6 | W0c + W2d + W2b + D7 verify | proposed |

6/16 waves NOT carried forward as-is: W0a (provider-failure taxonomy) folded into Phase 3's fetcher work; W0c/W0d scope shrunk (real residuals small); the 4-layer field-completion Epic downgraded (§6 Phase 6 note).

---

## §7. Open questions (for next planning round, not blocking Phase 1)

1. Phase 3: one combined LLM call (fields+papers, UPC style) vs two — needs pilot comparison (UPC alignment doc).
2. Phase 4: store residual-risk no-DOI groups in `pipeline_issue` vs a new review table.
3. Phase 6 D7: is a `ready`+`unverified` crossref row a verification gap or a classification gap (should it be `confirmed` via identifier resolution, not prof-link)?
4. Where does the W1a stealth-fetch layer live — extend `paper/homepage_http.py` or new module (UPC alignment doc recommends extend).
