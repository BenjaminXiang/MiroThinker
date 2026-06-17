# 高校教师→论文 脏数据缺口补齐 · 总体规划 (Portfolio)

> **For agentic workers:** This is a **portfolio / master plan**, not a single-feature TDD plan. It decomposes the professor→paper dirty-data gap into multiple independent OpenSpec changes (per CLAUDE.md §14). Each change card below is a spec stub; the bite-sized TDD task plan for a change is written when that change is opened (`.agents/runs/<change-id>/` + `openspec/changes/<change-id>/tasks.md`) during refinement. Sequencing and dependencies are normative; per-change code steps are deferred.
>
> **Scope-check note (writing-plans §Scope):** this covers multiple independent subsystems (provider integration, parser/extractor, identity/quality gate, closure loop, cross-domain contract). It is intentionally a portfolio decomposition; each change ships working, testable software on its own.

**Goal:** Close the structural dirty-data gap on the professor→paper collection route so that canonical rows stop accruing dirty data at ingestion, existing dirty rows are remediated (not merely filed), and the known code↔requirement contract drifts are reconciled.

**Architecture (approach):** Five waves sequenced by leverage — (W0) stop the bleeding at ingestion, (W1) decontaminate provenance so dirty data stops "looking clean", (W2) remediate historical gaps, (W3) make the close-don't-file loop real, (W4–W5) reconcile contract drift and doc debt. One cross-cutting rule: every remediation change must resolve the `pipeline_issue` rows it fixes (addresses root cause A1 incrementally).

**Tech Stack:** Python 3.12 (uv), Pydantic v2, SQLAlchemy/Alembic (V001–V042 history is immutable), Postgres + Milvus, FastAPI, pytest+xdist, OpenSpec change workflow.

**Evidence base:** Root-cause investigation 2026-06-16 (4 investigation lanes, evidence-backed; see `.agents/runs/` and the per-change cards). This plan is the synthesis of that investigation plus the OpenSpec `debt-register.md` open items.

---

## 0. Background — what the investigation established

### 0.1 Quantified dirty data (prof→paper route; counts from saved artifacts)

| Dirty-data class | Count (artifact) | Producing stage | Disposition |
|---|---|---|---|
| Paper missing `summary_zh` | ~29,030 still missing (39,433/49,814) | summary generation | open |
| Paper missing `abstract_clean` | ~37,400 missing | homepage / source-gap | open (largest source-acq gap) |
| `prof_page_only` dead-ends (no usable text/identifier) | 10,264 (baseline 11,603) | parser + title-resolve failure | open/unverified |
| Identifier-only, no source text | 4,590–5,122 | enrichment providers not returning abstract | open |
| Duplicate paper groups unresolved | 5,186 groups / 821 profs | dedup/merge | ~100% open (45-iter write loop failed) |
| Professor missing `paper_summary` | 2,200 | paper-summary generation | open (blocked upstream by dup lane) |
| Professor missing `research_overview_zh` | 2,510 | research-overview extract/translate | open |
| Title pollution (malformed `title_clean`) | 1,597/49,814 | homepage title extraction | **not applied** (cleanup ran read-only) |
| `profile_summary` short (<200) | 441 ready / 1,435 broad | summary fallback | open |
| DOI pollution | 4 strict residual | enrichment backfill | partial (`doi_quality.py` **uncommitted**) |
| Unverified paper identity | historical 7,297 `unverified` | identity gate | structurally unwired |

> **Correction to `docs/index.md:62`:** "paper ready 仍 0" is a **stale assertion**. Current artifacts show linked paper `ready=9,461`. W3b governance change recompute fixes this.

### 0.2 Root-cause IDs (referenced by change cards)

- **A1** — "File residual-risk instead of repair": `pipeline_issue` rows filed `resolved=false`; no code closes them; write-lanes only touch summaries/merges, not real paper gaps. `dataset_quality_closure.py:492-522,788-852,70`; closer is a different reporter `quality_gate.py:702-711`.
- **B1** — Provider silent-failure swallowing: `openalex.py:210-251`, `arxiv.py:34-35`, `title_resolver.py:510-520`; circuit `providers/openalex.py:18-68`. Empirical: identifier lane 5,069 rows → 460 errors + 229 rate-limits → 11 persisted, "did not reduce gap".
- **C1** — CMS template coverage incomplete (only SIGS repaired): `homepage_ingest.py:1964-1984`.
- **C2/C3** — Parser splitting arms-race + LLM extractor containment-only guards: `homepage_publications.py:1142-1451,3564-3683,2149,2371-2390`.
- **D1** — Paper title-resolver web_search contamination (NEVER addressed; prof-title-contamination only fixed professor affiliation.title): `title_resolver.py:337-356,62-77,951-991,1319-1401`; persist `run_paper_title_enrichment_backfill.py:702-732`.
- **D2** — DOI gate format-only + uncommitted: `doi_quality.py:22-68`; component/supplement not zeroed `title_resolver.py:648-655`.
- **E1** — Identity gate defined but never wired: `quality_promotion.py:212-238 apply_identity_gate_reevaluation` (tests-only); `identity_verifier.py:27,179`.
- **E2** — COALESCE upsert stickiness: `canonical_writer.py:968-1004`.
- **E3** — `paper_summary` not in default ingest: `output_summaries.py:67-108,311-397`; `canonical_writer.py:990`.
- **E4** — `research_overview_zh` extractor too narrow (13 labels, structure-dependent; bucket regex superset): `profile_sections.py:32-46,161-197`; `dataset_quality_closure.py:1108-1118`.
- **F1** — Governance amplifier: `change-ledger.md` (no June rows; 5 active + ~15 archived unregistered), `docs/index.md` (matrix stopped 2026-05-04).

### 0.3 OpenAlex role (decides W2a design)

OpenAlex is **not the unique source for any of the six `ready` fields** (title/year/venue/authors/abstract/summary_zh); every field is backstopped by Crossref/S2/arXiv (`enrichment.py:19-31` cascade, gap-filling). OpenAlex **is** unique for **professor metrics** (h_index/works_count/citation_count, `professor/openalex_metrics.py:39`, V012). Therefore an abstract gap = the **whole four-provider cascade came back empty** (B1), not "OpenAlex alone empty". `discover_professor_paper_candidates_from_openalex` (`openalex.py:43`) is **dead code** (zero callers).

---

## 1. Guiding principles

1. **Stop-bleeding → decontaminate → remediate.** W0 before W2: new data must stop turning dirty before we backfill, else filled gaps re-pile.
2. **A1 is cross-cutting, not a standalone-only fix.** Every remediation change (W2) resolves the `pipeline_issue` rows it repairs; W3 adds the loop + visibility.
3. **Hard dependency:** the abstract fallback (W2a) reuses the D1 web surface → **W1a attribution gate must land before W2a**, else the fallback re-manufactures D1 contamination.
4. **Behavior → OpenSpec.** Each change is behavior-affecting (§14.2) → its own OpenSpec change (Standard weight by default; contract-drift doc-only items may be Lite).
5. **Preserve invariants** (CLAUDE.md §7): evidence shape, `run_id` traceability, A–G semantics, `_VALID_DOMAINS`, V001–V042 history. No fix weakens a validation/provenance check to pass.

---

## 2. The portfolio

### Wave 0 — Stop the bleeding (ingestion-time; highest leverage; do first)

#### W0a · `provider-failure-taxonomy-and-retry` — fixes B1 (upstream)
- **Root cause:** every provider client swallows HTTP errors into `[]`/`None`; transient rate-limit/5xx becomes a permanent `prof_page_only` dirty row.
- **Behavior:** providers classify outcomes — `provider_unavailable` (rate-limit/5xx → retriable, marks `quality_status`, does NOT permanently demote the row) vs `no_data` (4xx/true-empty, normal). Circuit state propagates to a quality signal.
- **Affected files:** `src/data_agents/providers/openalex.py`, `paper/openalex.py`, `paper/arxiv.py`, `paper/crossref.py`, `paper/semantic_scholar.py`, `paper/title_resolver.py`, `paper/enrichment.py`; new shared outcome enum in `providers/`.
- **Level / Risk:** L3–L4 / medium.
- **Dependencies:** none.
- **Acceptance:** (a) a simulated 429 leaves the row in a retriable state, not `prof_page_only`; (b) `provider_unavailable` counts surface in run reports; (c) regression tests for each provider's error branch.
- **Open Q (refine):** where to persist the "retriable" state — a column on paper, or the existing `pipeline_issue` with a `provider_unavailable` stage?

#### W0b · `wire-paper-identity-gate-rejection` — fixes E1 (Gap B; **opened 2026-06-16**)
- **Premise correction (refinement):** the original E1 framing conflated three mechanisms. The LLM same-person gate (`batch_verify_paper_identity`) writes only `professor_paper_link.link_status`, never `paper.identity_status` → wrong-attribution papers stay in Milvus. (`apply_identity_gate_reevaluation` is a separate dead `quality_status` path = Gap A, out of scope; the ~7,297 `unverified` rows lack a resolved identifier → re-routed to **W0a/W2a** source-gap, not this change.)
- **Behavior (Gap B):** when the gate rejects the **last surviving `verified`** `professor_paper_link` for a paper whose `canonical_source='prof_page_only'`, set `paper.identity_status='rejected'` → excluded from Milvus via the existing `_is_indexable_paper`. Reversible (re-scan after a verified link returns), flag-gated (`PAPER_IDENTITY_GATE_ENABLED`, independent), dry-run-first via a new `run_paper_identity_scan.py` mirroring `run_name_identity_scan.py`.
- **Affected files:** new `paper/identity_status_writer.py` + `scripts/run_paper_identity_scan.py`; reuse `professor/paper_identity_gate.py` + `run_identity_verify_candidate_links.py` unchanged; `milvus_backfill.py:178-181` unchanged.
- **Level / Risk:** L4 / medium.
- **Dependencies:** none (benefits from W0a/W2a so rejections aren't masking missing data).
- **Acceptance:** see `openspec/changes/wire-paper-identity-gate-rejection/acceptance.md` (spec scenarios + dry-run/apply evidence).
- **Resolved open Q:** flag-gated + dry-run first (professor precedent); reject → reversible, non-terminal. Default conservative until dry-run counts reviewed.

#### W0c · `professor-summary-overwrite-on-recrawl` — fixes E2
- **Root cause:** `COALESCE(EXCLUDED.x, professor.x)` never overwrites a short/empty `profile_summary`/`paper_summary`.
- **Behavior:** recrawl overwrites when the new value is strictly better (passes the 200–300 / non-boilerplate contract) or the old is below threshold.
- **Affected files:** `professor/canonical_writer.py:968-1004`.
- **Level / Risk:** L2–L3 / low.
- **Dependencies:** none.
- **Acceptance:** re-crawl of a short-summary professor replaces the value; no regression on already-good summaries.

#### W0d · `commit-and-harden-doi-gate` — fixes D2
- **Root cause:** `doi_quality.py` is format-only and uncommitted; component/supplement DOIs pass.
- **Behavior:** commit `doi_quality.py`; component/supplement DOIs zeroed (`title_resolver.py:648-655` extended to OpenAlex/S2); gate wired in both `enrichment.py:446` and `run_paper_title_enrichment_backfill.py:742-755`.
- **Affected files:** `paper/doi_quality.py`, `paper/enrichment.py`, `paper/title_resolver.py`, `scripts/run_paper_title_enrichment_backfill.py`.
- **Level / Risk:** L3 / low.
- **Dependencies:** none.
- **Acceptance:** the 4 known residual DOIs are rejected; new backfill writes no malformed/component DOI.

### Wave 1 — Decontaminate provenance (L6 write-through; "dirty data looks clean")

#### W1a · `title-resolver-web-attribution-gate` — fixes D1
- **Root cause:** web_search tier passes a different paper's title at Jaccard ≥0.85 and writes it with `match_source="web_search"` as if source-grounded; this paper-side path was never touched by `prof-title-contamination-repair`.
- **Behavior:** web tier requires attribution — DOI/arXiv-id match to canonical OR (`title_match_score ≥ 85` AND `author_token_jaccard ≥ 0.3`) reusing `doi_verifier.py` logic; contaminated titles are NOT written to canonical; web-sourced rows tagged lower-confidence.
- **Affected files:** `paper/title_resolver.py:337-356,62-77,951-991,1319-1401`, `paper/doi_verifier.py` (extend `VerificationSource` beyond `cache/openalex/arxiv`), `scripts/run_paper_title_enrichment_backfill.py:702-732`.
- **Level / Risk:** L4 / medium.
- **Dependencies:** none (but **blocks W2a**).
- **Acceptance:** a curated set of known-mismatched titles no longer gets overwritten; web-sourced titles carry a distinct, lower-confidence provenance tag.

#### W1b · `homepage-parser-boundary-guards` — fixes C2/C3
- **Root cause:** splitter is a ~25-heuristic cascade that still mis-segments; LLM extractor guards verify containment, not boundaries → author-list-as-title contamination.
- **Behavior:** reject author-list-as-title at write time; upgrade LLM extractor guards from containment to boundary correctness; malformed-title gate strengthened.
- **Affected files:** `professor/homepage_publications.py:1142-1451,3564-3683,2149,2371-2390`, `paper/llm_publication_extractor.py`.
- **Level / Risk:** L3–L4 / medium.
- **Dependencies:** none.
- **Acceptance:** the 1,597 malformed-title population stops growing; LLM-extractor test suite covers boundary-mis-segmentation cases.

### Wave 2 — Remediate historical gaps (new data now clean, provenance trusted)

#### W2a · `abstract-web-reader-fallback` — fixes B1 (downstream; user-proposed)
- **Root cause / trigger:** four-provider cascade all empty → abstract gap. (OpenAlex alone empty is NOT the trigger — it is backstopped.)
- **Behavior:** four-providers-empty → Jina reader fetches the **row's own** `pdf_url`/landing_page; result writes to `paper_full_text` / a web-provenance sidecar (**not `abstract_clean`**); reuses W1a attribution gate; lower confidence; does NOT auto-promote to `ready`; on success resolves the matching `pipeline_issue`.
- **Affected files:** `paper/enrichment.py:63-210,291`, `paper/full_text_fetcher.py:132-170` (add reader path mirroring `professor/discovery.py:540-599`), `scripts/run_paper_summary_zh_backfill.py:~1053`, `config/settings.py:29-30` (`JINA_API_KEY`/`JINA_BASE_URL`).
- **Level / Risk:** L4 / medium.
- **Dependencies:** **W1a** (attribution gate), W0a (so fallback isn't masking silent failures), Jina key from env.
- **Acceptance:** a bounded dry-run fills abstracts for a sample with attribution evidence; no abstract written into `abstract_clean` without a matching identifier; filled rows not auto-`ready`.
- **Open Q (refine):** Serper-snippet vs Jina-fetch-known-URL — recommendation is **Jina-fetch-known-URL** (lower contamination); confirm field = sidecar vs `paper_full_text`.

#### W2b · `research-overview-extractor-broadening` — fixes E4
- **Behavior:** broaden `_RESEARCH_SECTION_LABELS`; handle table/`<dl>` structures; wire translator for English pages; align bucket regex with extractor capability (stop over-counting).
- **Affected files:** `professor/profile_sections.py:32-46,161-197`, `professor/dataset_quality_closure.py:1108-1118`.
- **Level / Risk:** L3 / low.
- **Acceptance:** the 2,510 bucket shrinks by extractor gains; over-count gap between bucket-regex and extractor closes.

#### W2c · `homepage-cms-selector-coverage` — fixes C1
- **Behavior:** selector-repair loop for non-SIGS Shenzhen-institution CMS templates (SZTU etc.); a `publication_source_sparse_count_only` issue triggers a re-run with a fixed selector rather than silent 0-extract.
- **Affected files:** `professor/homepage_ingest.py:1964-1984`, per-institution selectors in `professor/`.
- **Level / Risk:** L3 / medium.
- **Acceptance:** 0-extract professors on covered CMS templates yield publications after selector fix; re-run is recorded.

#### W2d · `paper-summary-into-default-ingest` — fixes E3
- **Behavior:** wire `output_summaries` generation into the default ingest path (`canonical_writer`), not only the separate `run_output_summary_backfill` script.
- **Affected files:** `professor/output_summaries.py:67-108,311-397`, `professor/canonical_writer.py:990`.
- **Level / Risk:** L3 / low.
- **Acceptance:** new professors get `paper_summary` at ingest without a manual backfill run.

#### W2e · `duplicate-paper-review-workflow` — fixes the 5,186 unresolved groups
- **Root cause:** title+year-only groups are **correctly** precision-gated to `needs_review` (no DOI/arXiv anchor) → they need review, not auto-merge.
- **Behavior:** a human/LLM-assisted review workflow for title+year-only duplicate groups; writes `paper_merge_alias` only on confirmed merges; records rejected merges.
- **Affected files:** `professor/dataset_candidate_generation.py:903-960,1510-1521`, `storage/postgres/paper_merge_alias.py`, new review endpoint/UI hook.
- **Level / Risk:** L3 / medium.
- **Acceptance:** bounded sample reviewed with precision metric; confirmed merges traced; the 45-iteration failed-write loop replaced.

### Wave 3 — Structural closure (A1 + visibility)

#### W3a · `pipeline-issue-closure-loop` — fixes A1
- **Behavior:** (a) every remediation success resolves its `pipeline_issue`; (b) wire `source_gap_audit.py:13-19` paper-side lanes into `pipeline_issue` filing (currently invisible to the closure report); (c) add an "unresolved residual" report that cannot be silently filed off.
- **Affected files:** `professor/dataset_quality_closure.py:492-522,788-852,70`, `paper/source_gap_audit.py`, `alembic/versions/V006_init_pipeline_issue.py` / `V023` stage enum (extend if needed), `professor/quality_gate.py:702-711` (unify closers).
- **Level / Risk:** L4–L5 / medium.
- **Dependencies:** best after W0–W2 so there are real resolutions to close.
- **Acceptance:** `residual_risk`-reported issues reach `resolved=true` when data is fixed; paper-side gaps appear in the coverage report with `unclassified_count` semantics.

#### W3b · `governance-ledger-index-reconcile` — fixes F1 (doc-only)
- **Behavior:** register the 5 active + ~15 archived changes in `change-ledger.md`; refresh `docs/index.md` matrix to 2026-06 state (including the `ready=9,461` correction and per-Wave status as they ship).
- **Affected files:** `openspec/change-ledger.md`, `openspec/debt-register.md`, `docs/index.md`.
- **Level / Risk:** L0 (doc) / low.
- **Acceptance:** ledger active+archived tables match the `openspec/changes/` directory; index matrix counts match latest artifacts.

### Wave 4 — Contract drift reconciliation (debt-register; code↔requirement)

#### W4a · `release-dto-run-id` — debt `shared-spec-run-id-on-released-dto-001` (medium, cross-domain)
- **Behavior:** add `run_id: str` to the four `*Record` + `ReleasedObject`, OR amend Shared-Spec §4.2 to scope `run_id` to the Postgres canonical layer. Cross-domain.
- **Affected files:** `src/data_agents/contracts.py`, `docs/Data-Agent-Shared-Spec.md §4.2`.
- **Level / Risk:** L4 / medium.
- **Open Q (refine):** extend DTOs vs narrow the spec — recommendation depends on whether downstream consumers need `run_id` on released JSONL.

#### W4b · `company-publish-field-contract` — debts `company-prd-industry-required-drift-001` + `company-prd-min-publish-fields-drift-001` + `company-prd-recommended-config-aspirational-001`
- **Behavior:** reconcile `industry` required-vs-optional; align min publish fields (`credit_code`/`legal_representative`/`registered_capital`/`patent_count`); annotate §八 Hydra config as not-yet-realized.
- **Affected files:** `contracts.py:236,232-243`, `company/release.py:40-43`, `docs/Company-Data-Agent-PRD.md`.
- **Level / Risk:** L3–L4 / low.

#### W4c · `company-key-personnel-structure` — debt `company-prd-key-personnel-schema-drift-001` (medium)
- **Behavior:** extend `CompanyKeyPerson` (`contracts.py:154-156`) to PRD schema (name/role/education_structured/work_experience/description), promoting already-captured `raw_intro`. Cascades to R3/R17/R27/R34 structured filters → separate change.
- **Affected files:** `contracts.py:154-156`, `company/team_parser.py:55-89`, `company/enrichment.py:27-47`, `docs/Company-Data-Agent-PRD.md §二.2.2/§四.4.3`.
- **Level / Risk:** L4 / medium.

#### W4d · `patent-prd-patent-type-vocabulary` — debt `patent-patent-type-vocabulary-001` (doc-only)
- **Behavior:** align PRD §四.4.1 `patent_type` vocabulary with the V004 enum (`发明/实用新型/外观/PCT/其他`).
- **Affected files:** `docs/Patent-Data-Agent-PRD.md`.
- **Level / Risk:** L1 / low.

### Wave 5 — Doc / governance debt (non-behavior; schedule by capacity)

- `multi-turn-design-current-state` — debt `multi-turn-design-partial-001`: rewrite the design doc to reflect implemented vs deferred.
- `agentic-rag-prd-guide-relationship` — debt `agentic-rag-prd-vs-guide-001`: declare PRD canonical, Operating-Guide supplement.
- `paper-companion-design-relationship` — debt `paper-companion-design-relationship-001`: declare MSD a phasing-attachment of the PRD.
- `agents-specs-touch-triage` — debt `agents-specs-frozen-but-uncategorized-001`: per-file `migration_status` frontmatter pass.
- `cleanup-copilot-openspec-artifacts` — debt `copilot-openspec-artifacts-001`: decide keep/remove `.github/` Copilot OpenSpec artifacts.

All L0 (doc), low risk, no code behavior.

---

## 3. Dependency graph & sequencing

```
W0a (B1 stop-bleed) ─┐
W0b (E1 identity)   ─┼─► (new data stops turning dirty)
W0c (E2 overwrite)  ─┤
W0d (D2 DOI gate)   ─┘

W1a (D1 web attribution) ──┐
W1b (parser boundaries)  ──┘  (provenance trustworthy)

        W1a ──HARD──► W2a (abstract fallback reuses web surface)
W0a ─────────────────► W2a (don't mask silent failures)

W2a–W2e (remediate) ──► each resolves its own pipeline_issue (A1 incremental)

W3a (closure loop + visibility) — best after W0–W2; parallelizable
W3b (governance docs) — anytime
W4a–W4d, W5 — independent; schedule by capacity
```

**Recommended first three to open as OpenSpec changes (highest leverage + W2a prerequisites):**
1. `wire-paper-identity-gate` (W0b) — most independent, direct unblock of `ready`.
2. `provider-failure-taxonomy-and-retry` (W0a) — stops the bleeding that re-piles gaps.
3. `title-resolver-web-attribution-gate` (W1a) — decontaminates + is the hard prerequisite for W2a.

The user's `abstract-web-reader-fallback` (W2a) is 4th, gated on #3.

---

## 4. Non-goals (explicit)

- Not migrating `docs/` wholesale into OpenSpec (CLAUDE.md §14.3 — capability-by-capability, touch-to-promote).
- Not rewriting V001–V042 alembic history.
- Not weakening any evidence/provenance/quality check to make a backfill pass.
- Not auto-merging title+year-only duplicate groups (they are correctly review-gated).
- Not treating "residual-risk filing" as closure (the whole point of W3a).

---

## 5. Open questions for refinement discussion

1. **W2a field boundary:** abstract sidecar vs `paper_full_text` web-provenance — and is Serper-snippet ever acceptable, or Jina-fetch-known-URL only?
2. **W0a retriable state:** new column vs `pipeline_issue` stage — schema impact.
3. **W0b gate blast-radius:** default-on vs flag-gated (professor name-identity caution).
4. **W4a run_id:** extend the four DTOs vs narrow Shared-Spec §4.2.
5. **W4c key_personnel:** full PRD schema vs documented deferral (cascade cost on R3/R17/R27/R34).
6. **Capacity / parallelism:** how many changes in flight at once (one active writer per slice per CLAUDE.md §11).

---

## 6. Tracking

Each change card maps 1:1 to `openspec/changes/<change-id>/` (proposal/specs/design/tasks/acceptance + source-links/agent-links) and `openspec/change-ledger.md` row, with execution under `.agents/runs/<change-id>/`. W3b ensures the ledger is reconciled as part of this portfolio.
