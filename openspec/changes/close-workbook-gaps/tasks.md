# Tasks: close-workbook-gaps

> Sequencing (user decision 2026-09-10, design.md §sequencing): **C2 first**,
> then B2.1+B3.1 as one combined "enumeration & narrowing" slice on the
> run14 pack, then B4/B5. Rationale: GAP-02/04 acceptance assertions are
> data-capped on the s12f pack (human log entry 4).

## Stage B — core gap fixes

- [x] B1.1 Port `_company_to_patent_relationship_candidates` G3-simple scan
       into deployment-line `knowledge_read_isolated.py` (no new imports).
       (commit `b20161d`, +79 lines incl. path-eligibility guardrail the
       source block lacked)
- [x] B1.2 Restart 18188; RED→GREEN on g17-t1 assertion (≥3 CN ids,
       citations_local ≥1); replay gate 7/7.
       (GREEN 2026-09-10 round 3: g17-t1 three-layer PASS on live 18188 —
       16 CN ids + 16 local citations; replay-b1-r3 7/7, zero jitter
       signatures)
- [x] B1.3 Gate A: patent-intent patterns cover "有哪些专利/的专利有哪些";
       derived short-name channel with uniqueness guard binds 优必选.
       (round 2, tests `673edb7`: `_compact_company_alias` short-name
       channel binds company-c-64e631c0e0cd9e91d032d209; possessive-pattern
       extension deliberately skipped — the short-name channel covers it and
       the extension would mis-fire on "…的竞争对手有哪些专利")
- [x] B1.4 Gate B: shared `_direct_patent_applicant_scan` helper called
       from `_source_bound_relationship_candidates` for company→patent;
       positive control (普渡 17) not regressed.
       (round 2, snapshot `1860b8c`: 优必选 48 candidates = 58 bindings −
       10 path-eligibility exclusions; 普渡 17/16 CN/16 local cards held
       again in round 3)
- [x] B1.5 Relationship-lane local citations surface in the answer.
       (round 2: `local-source-<sha>` cards for URL-less local evidence in
       `_public_citations`; g17-t1 local_citations 0→16)
- [x] B1.6 Gate C: claim-binding witness branch in `_apply_constraints`
       (relationship lane only, trace branches keep precedence, binding
       value endpoint `canonical:<domain>:<displayed id>` with subject ==
       candidate); negative tests (cross-anchor / subject-side) +
       selector-equivalence contract test vs `_claim_binding_binds_anchor`;
       g17-t1 three-layer GREEN on live 18188.
       (commit `197b7f5`: knowledge_read.py +21; 3 new tests RED→GREEN —
       positive value-endpoint witness, 4 negatives, 5-fixture selector
       equivalence; focused suite 96 passed / 0 failed)
- [x] B3B2-D0 Diagnostic gate (DONE `1313c0f5` + D0.5
       `d05-findings.md`): per-entity drop-stage tables + production-
       function gate replay + lane construction facts; fix shape locked
       in design.md §B2+B3 "D0.5 locked phase-1 fix set".
- [x] B3B2-F3 Gate backfill fix (small): `kept<floor` keeps ALL
       full-name hits (T2/T3); only T4/T5 truncated to floor. Verify =
       re-run the D0.5 gate replay (g5-t2 3→12 expected; g2-t2
       unchanged at 7). (landed `7a65fb4a`, deployed)
- [x] B3B2-F2 Commit union: `_commit_prose_scope` commits selected ∪
       (displayed names appearing in the answer text) — kills the
       深南电路-style eviction (`answer:2488-2559`). (landed `0ec4b1a6`,
       deployed)
- [x] B3B2-F1 Category recall: deterministic category-term recall over
       `content_terms` (all scalar fields already in the lexicon,
       `knowledge_read_isolated.py:8147`); term extraction (stopword/
       city strip, ≥2 chars), bounded, enumeration window; offline
       GT-recall count over the sealed pack. Retrieval-critical —
       micro-design in implementation; STOP+report if it needs contract
       changes beyond matcher/planner level.
       (landed `aa67829f`; lane-level verified live: lexical 0→48)
- [x] B3B2-F4 Rerank stable-order fix (diagnostic f1b-downstream-trace.md):
       drop the `result_id` tie-break in the serving rerank bucket sort so
       equal-score candidates keep lane order (F1 ranking) —
       `knowledge_serving_isolated.py:2525-2526`. Verify: replay probe
       stage-table shows GT survival to payload; acceptance re-run
       (g2 5/5 → g2-t2 ≥5/6 → g5-t2 ≥9/12); replay gate zero new
       signatures; four-file regression unchanged.
       (landed `42ad58a2`: candidate_key → score-only; new anti-sorted
       equal-score test; replay after-table — g2 six GTs all reach
       payload at ordered 1/3/5/7/15/23; g5 顺易捷 revived 67→17;
       known exchange: 深南电路 back to true rank 81 (hex luck removed);
       rerank cluster 4/4, four-file suite 328 passed; deployed to 18188
       2026-09-11 18:0x for the acceptance re-run)
- [ ] B3B2-ACC Acceptance (main context, multi-run): g2-t1 5/5;
       g2-t2 ≥5/6; g5-t2 ≥9/12 (data ceiling: 8 in-pack + Guangzhou
       exception); replay zero new signatures; differential
       non-regression.
- [ ] B3B2-DEFERRED (phase 2, trigger-based): B2-a manifest fidelity /
       B2-b per-member verdict probes / B2-c coverage statement /
       F-bind web-name binding / probe-path visibility.
- [ ] B4.1 Local-citation floor at render; local answers carry ≥1 local
       citation. Design locked (design.md §B4, adjudications 1–3):
       (a) D0-style per-segment card-loss probe first — 9 anchored turns,
       answer-layer citations vs adapter cards vs emitted SSE cards;
       (b) then Hook A — relax `canonical_v2_chat.py:2272` to any local
       evidence (`source_nature ∉ {current_web, supplemental_web}`) on a
       `_PUBLIC_DOMAINS` handle → URL-less `local-source-` card;
       (c) harness local-count by id prefix (`local-source-` /
       `official-source-`) instead of `type != "web"`.
- [ ] B4.2 Web-citation boilerplate filter (navigation/error templates).
       Adjudicated surface (design.md §B4 adj. 1): assertion runs over ALL
       citation url/label/locator fields + answer text; production filter
       extends `_DETERMINISTIC_RAW_DUMP_MARKERS` (+ 404/JS/navigation
       templates) and closes the `_enrich_with_page_text` fetch-side gap.
       No `ChatCitation` contract change. Acceptance: fired on constructed
       dirty fixture, silent on archived clean corpus, no 404-as-number
       false positives.
- [x] B5.1 `_ProseWireDecoder._filter_private_markers` redact-and-continue:
       on complete marker match drop the buffered candidate + record
       redaction instead of raising (design.md §B5; live GAP-09 defect —
       stream-path raise → empty answer). Unit tests RED→GREEN (marker
       removed, surrounding text byte-intact, redaction recorded).
       (worktree `9e1e79d4`: `_redactions` list + property; finish
       behavior unchanged; raise-site reachability verified — legit
       selection header never routes through the filter)
- [x] B5.2 Callers wire the degradation token: `_parse_response` +
       `stream()` call `current_turn_trace().set_degradation(
       "prose-private-marker-redacted")` when redaction happened; stream
       integration test (injected marker → done event, no error event,
       token present). Verify at start: raise-site reachability, no
       fallback catcher, flag plumbing (ProseSynthesisResult vs trace).
       (done: helper `_report_prose_marker_redactions`; token added to
       admin-console `DegradationToken` Literal + `_VALID_DEGRADATION_
       TOKENS` (canonical_v2_turn_trace.py); SSE real-HTTP integration
       test RED→GREEN; flag stays on trace reporter only)
- [x] B5.3 Regression: hermetic pack + B1 focused + fast_boot unchanged;
       worktree commit.
       (green, baseline-identical: hermetic 22 + fast_boot 14; B1 96/26;
       serving 265; admin 147; 31 new/rewritten tests RED 28→GREEN 31)
- [x] B5.4 Evidence: same-day differential / replay re-run — marker-class
       empty answers disappear on both sides; C2.1f replay signatures
       re-classified (marker-class rows clear).
       (DONE 2026-09-11: replay r3 post-deploy — failures 6→2; G1_t3 and
       the G2_t2 marker-class SSE error CLEARED; remaining G3_t2 + G7 are
       in-register historical jitter signatures (G7 = B3/D0 target).
       Smokes (丁文伯 / 具身智能枚举): 0 error events, done received.
       B5 accepted; GAP-09 → GREEN.)
- [ ] B6.1 Education × region × industry combined person retrieval;
       g7-t1 ≥2 gold entities. (depends C1)

## Stage C — data groundwork

- [x] G1 Retrieval-critical field contract draft: 4-domain field
       coverage inventory (measured) + per-field thresholds + category-
       anchoring input + gate-at-import sketch. (DONE:
       `g-series/g1-field-contract-draft.md` — placeholder pollution in
       content_terms quantified (professor 100% / company 30.3% docs);
       stable structured anchors only company.tech_tags/industry,
       patent.title, professor.research_directions)
- [x] G2 Identity governance audit: fragmentation counts + cross-
       identity conflict inventory + cross-release id stability +
       merge-rules proposal (input to the two-line contract ADR).
       (DONE: `g-series/g2-identity-audit.md` — four-domain id churn
       100% across releases, 33% pure loss; 42% merge traps; stable_uid
       protocol proposal)
- [x] G3 Category lexicon & field anchoring: from real category
       queries; anchoring rules + offline verification table + gap list
       (feeds G1/C1). (DONE: `g-series/g3-category-anchoring.md` —
       tech_tags is the only fine-category structured anchor (26/30
       words hit but ~1 tag/company); structured coverage spans 85.9%
       (人工智能) → 14.5% (具身智能) → 7.7% (PCB) → 0% (送餐机器人);
       zero-signal classes (酒店送餐机器人/PCB打板) need an unanchored
       branch)
- [ ] C1.1 Ingestion quality gate implementation (G-series contracts →
       gate-at-import: field thresholds + anchoring + identity merge;
       folded into the C6 update pipeline). (depends G1-G3; next:
       consolidation into C1-contract v1 + ADR draft for user review)
  - [x] C1.1-batch0 Read-side placeholder scrub + anchoring declaration
         + packaging scan gate. (commit `ad401302` in the s11 worktree,
         9 files +2067/−18: `placeholder_scrub.py` 4-family matcher,
         `_projection_terms`/`_projection_category_term_buckets` scrub
         post-validation, `anchoring_declaration.py` +
         `catalogs/anchoring-declaration-v1.json` (110 terms, F1 block
         8/4/2/2/2 migrated from hardcoded), `s12c/build_serving_pack.py`
         warn-only scan gate with sidecar report. Verified: 12 new tests
         (main context re-ran scrub suite 10/10), four-file 340 passed
         (baseline 328), gate dry-run counts match the census
         (12,872/3,099/189/1,817) with byte-identical hashes, no deploy
         in the slice. Live differential + replay gate by main context;
         remaining: answer-side wording (consumer b), write-side cleaning
         (batch 2+).)
- [ ] C2.1 run14 thin-load online (47,071 docs) + reconciliation report;
       workbook score not regressed. Sub-steps (design.md §C2, contract
       verified line-by-line 2026-09-10):
  - [x] C2.1a Mint run14 `RecordedServingBundle` json (release_id
         `candidate-v2-20260819-r1`, index_root `/var/tmp/mirothinker-
         data-v2/index-v1`, disposable db name, policy knobs carried from
         s12f bundle) + clone the s12g command file with the six-arg delta.
         (worktree `9cfdabe`: `s12g/serving-bundle-run14.json` +
         `s12g/serve-18189-command.sh`; token-level diff asserted to be
         exactly the designed six args + port + 2 scratch env vars)
  - [x] C2.1p Port `supplementary_field_values` to the serving line
         (inserted 2026-09-10 — third blocker; design.md §C2): verbatim
         model field (data-rebuild `index_projection.py:277`) + sealer
         conditional scalars passthrough + loader conditional
         reconstruction with `exclude_unset=True` (s12f rollback-compat
         lock). Contract test pins both sides; B1 focused suite +
         hermetic pack tests green.
         (worktree `3734f30`: 2 pin tests; hermetic 21 + B1 focused 96/26
         + fast_boot 14 identical to pre-port baseline; reconstruction
         trees verified 10/10, 6/6, 13/13, 13/13 explicit)
  - [x] C2.1q Port the remaining 4 build-path hunks (47 lines) of
         `index_projection.py` verbatim — two-line file reaches
         byte-identical zero drift (inserted 2026-09-10 — the sealer's
         envelope validator embeds a full deterministic index replay and
         demands build-level parity; envelope is self-consistent, serving
         build path is the divergent side). Same regression gate, then
         re-run the official seal.
         (worktree `174f141`; seal re-run then COMPLETED 14:34 — sealed
         pack verified in main context)
  - [x] C2.1r Seal the run14 pack with the OFFICIAL envelope sealer
         (revised 2026-09-10: run14's genuine envelope found in
         data-rebuild s12a — 8.1G, Sep 8, same build run; design.md §C2):
         serving-worktree `s12c/build_serving_pack.py --envelope <run14
         envelope, read-only> --index-root /var/tmp/mirothinker-data-v2/
         index-v1 --pack-dir /var/tmp/mirothinker-data-v2/serving-pack-
         run14-sealed --expected-release-id candidate-v2-20260819-r1
         --generator-run-id c2-seal-20260910-v1`; sealer dogfoods through
         the real loader and proves envelope-equality; then point the
         18189 command at the sealed pack. (First-iteration resealer
         `9a99ca2` stays committed as tooling — superseded, not the C2
         path; transcode rejected: genuine artifacts exist.)
         (DONE 14:34: sealed pack `serving-pack-run14-sealed`, manifest
         verified: release candidate-v2-20260819-r1, marker 8848197c…,
         relationships 3.36G with eligibility sections)
  - [x] C2.1s Port the 14-line `_supplementary`/`_quality_tier` strip
         block verbatim into serving `_validated_public_projection`
         (inserted 2026-09-10 — blocker ④: the read-side half of the
         multi-value enrichment; 903 public lookup docs carry the baked
         key; data line `knowledge_read_isolated.py:7954-7967`). Pin test
         (constructed doc with `_supplementary` → RED before, GREEN
         after); same regression gate; then restart C2.1b.
         (worktree `43fa1340`: pin test with lineage-tamper negative
         assertion; hermetic pack 22 + B1 focused 96/26 + fast_boot 14;
         function head diff vs data line = zero)
  - [x] C2.1b A/B boot on scratch port (localhost only, scratch
         access-log/corrections paths); measure boot wall-time and RSS.
         (boot4: wall 696s ≤900 gate; RSS peak 28.7G ≤32G gate, 16.9G at
         ready; responsive — 优必选 query full SSE with 17 grouped
         patents; log c2-scratch-boot4.log)
  - [x] C2.1c Reconciliation report: per-domain counts vs s12f
         (5,659 → 47,071), 优必选 bindings, GT-6 presence, 普渡 control.
         (closed: lookup counts match design; relationship side —
         current_relationships 10,897, patent_has_applicant 123
         materialized records across 49 companies; the 450/128 numbers
         ride the lookup_content `applicants` field consumed by the
         read-side `_direct_patent_applicant_scan` — the pipeline
         materializes ~123 of ~7,078 by design; both sides consistent)
  - [x] C2.1d Full 25-turn three-layer re-baseline — METHODOLOGY
         AMENDED 2026-09-10: archived 9/9 baseline unreproducible (LLM
         backend drift; live 18188 s12f fails identically today, journal
         evidence). Effective gate = SAME-DAY DOUBLE RUN: 25 rounds on
         18188 (s12f) + 25 on 18189 (run14); pass = run14 not worse than
         same-day s12f per turn, with per-turn attribution for any
         s12f-pass/run14-fail.
         (DONE 2026-09-10: 23/25 per-turn identical, both sides 7/25
         under env drift; sole s12fP→run14F turn 5-1 attributed to
         composition jitter with three-way re-composition evidence;
         reverse improvement 10-1; verdict PASS. Latency evidence: p50
         13.7→20.4s, p95 42.5→74.9s — logged as the C2 speed-axis cost.)
  - [x] C2.1e Re-baseline gap-registry (GAP-15 closes; GAP-13 rows,
         GAP-02/04 ceilings re-measured); verification-c2.md landed; the
         differential tables are the C2 acceptance evidence.
         (DONE: GAP-15 flipped GREEN; GAP-12 thresholds decided
         90/70/70; verification-c2.md §1–§7 complete)
  - [x] C2.1f Switch 18188 (command file → run14 sealed, restart, replay
         7/7); s12f pack + old command file kept for rollback. Routine
         per user policy (2026-09-10).
         (DONE 2026-09-10 19:32; post-switch integration defect
         MANUAL_RECALL_DIR release mismatch found → fixed by repointing
         to the run14 store 22:51 (worktree 45877e81); replay r2: ZERO
         new signatures — G5 PASS, remaining 4 failing turns all in
         known classes (3 historical jitter + 1 env marker). 18188 live
         on run14 sealed for user E2E.)
- [ ] C3.1 Company→patent full relations + professor→company coverage (90
       candidates); 10-sample manual check.
- [ ] C4.1 Paper↔professor canonical id links; paper detail lists involved
       professors.
- [ ] C5.1 Delete taxonomy dead path after zero-reference sweep.
- [ ] C6.0 Data-acquisition backlog (from the g5 GT check, 2026-09-12):
       companies verified ABSENT from every local store — 华秋PCB (深圳华秋
       电子有限公司), 中信华, 领智电路（深圳）, 鼎纪电子 (广州) — plus the
       thin-profile GT pair (深圳嘉立创科技集团股份有限公司 /
       深南电路股份有限公司: content-tier-only matches, no tags). Queue
       for the next refresh cycle (C1 batch 2 / C6 pipeline) so the local
       pack can eventually carry them; until then the web-completion track
       covers them in answers (user-approved 2026-09-12).

## Answer-quality slice (2026-09-11, design locked in design.md; runs after C1 batch 0)

- [x] AQ-S0 Reframed to live sampling (offline injected-payload harness
       dropped — payload assembly is not reproducible offline). Executed
       as N=5 g2 samples after AQ-S1/S2 deploy: chain CONFIRMED (t2 names
       pool members with 注册地在深圳 wording; passes when t1 coverage
       7/10), stability insufficient (2/5) → AQ-S2b added.
- [x] AQ-S1 C-1 address claims: `_semantic_text` company branch gains
       注册地址/注册地 lines behind a narrow/geography-turn switch
       (`serving:5901` call site); off-switch output byte-identical.
       (landed `5900bd98`, deployed 19:35; live: address wording present
       in narrowing answers, 91.78% address availability)
- [x] AQ-S2 A-1 enumeration windows: local 32 / web 32 / cut 48→64 for
       enumeration-class queries; `web_claim_limit` decoupled; selector
       unit RED (#17–32 locals -> claims), plan unit (max_candidates 64);
       offline pack probe (嘉立创/则成 enter the window); TTFT recorded.
       (landed `5900bd98`; probe: 嘉立创54/则成62 in at 64, 锐曼26 in
       with local 32; payload net −1.3K chars; elapsed 21–39s per turn
       in sampling)
- [ ] AQ-S2b Deterministic coverage layer for enumeration turns
       (design.md §AQ-S2b): append displayed-but-unmentioned local
       members as a coverage sentence (displayed order, cap ~16, honest
       wording); only displayed members (truncated stay count-only);
       must feed F2 commit-union; non-enumeration byte-identical.
       Verify: determinism/order/cap tests + live N≥5 g2 sampling
       (t2 ≥5/6 in ≥4/5 samples).
- [ ] AQ-S3 B-probe member category probes + probe visibility fixes
       (subject-consistency gate, lane counters, claims inclusion;
       `chat:1813-1836` integration point); RED = enumeration turn sends
       no probe today.
- [ ] AQ-S3b Protocol-JSON leak fixture (selection JSON in answer text;
       r2/r3 occurrences) fixed with the wire decoder or visibility fix.
- [ ] AQ-S4 D-1 capability-evidence binding for the relation frame
       (`serving:2943-2947`); RED replay on the sealed pack shows
       "普渡+机械臂+按电梯" absent from claims today; D-2 manual sidecar
       (single PuDu record) only if S4 evidence says the window eats it.
- [ ] AQ-S5 A-2 declaration vocabulary extension (PCB synonym family) with
       F1 matcher consumer; offline table must show the 8 in-pack GT
       entering the window; anti-false-positive matrix.
- [ ] AQ-S6 Acceptance double-run + replay gate + differential for
       prompt touches; targets: g2-t1 5/5 + ≥8/10; g2-t2 ≥5/6; g2-t3
       stance clean; g5-t1 3/3; g5-t2 ≥9/12.

## Spec deltas

- [x] S-delta B1: `canonical-v2-chat` — company→patent local traversal
       requirement (added with B1; both scenarios now satisfied live —
       g17-t1 GREEN round 3, honest-fallback wording unchanged).
- [ ] S-deltas for B2–B5 added with their slices.

## Latency + commit-scope slices (2026-09-12 evening)

- [x] LAT-1 Professor vector display authority indexing: build the
       canonical_id → document index once, resolve each point in O(1)
       (landed `e3d7d0b2`, deployed 15:23). Live r3: 大疆 79.3→24.2s,
       教授 60.1→15.5s TTFT.
- [x] LAT-2 Env-gated turn audit probe (CANONICAL_V2_TURN_DEBUG_DIR):
       planned/committed ids, recalled handles, lane wall times; off by
       default (landed `9e0c6a00`, deployed 17:28).
- [x] AQ-S8 Geography slots witness a company's registered address, not
       only its name (landed `7241bfdc`, deployed 17:46). g5-t2 深南电路
       root cause; unit RED→GREEN; live t2 recalled 63→64 with 深南 in the
       answer ×2 samples.
- [ ] LAT-3 Web-phase budget / page cache: live lidar TTFT is
       web-fetch-bound (lane probe: web 10.3s vs local 6.6s; cold batches
       seen at 44-48s). Bound the enumeration fetch phase (per-page timeout
       already 2s floor — check the effective value) and/or add a page-level
       cache with TTL; keep snippets as the degrade path.
