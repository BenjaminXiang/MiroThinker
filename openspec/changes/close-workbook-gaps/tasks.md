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
- [ ] B3B2-D0 Diagnostic gate: per-entity drop-stage table for g2-t1 /
       g2-t2 / g5-t2 on the live run14 line (retrieval / displayed /
       answer / naming); final fix shape locked by this table
       (design.md §B2+B3).
- [ ] B2.1a Faithful carried manifest: session carries all displayed
       members (kind,id,name); canonical-only filtering kept only for
       identity-binding consumers (chat:2047, chat:714 sites).
- [ ] B2.1b Per-member narrowing verdicts for the full carried set
       (local claim → name heuristic → web probe); budget-capped
       remainder stated honestly.
- [ ] B2.1c Coverage statement (共 N / 确认 M / 排除 K / 未决 J) from
       actual outcomes; fix representative count semantics
       (read:6925-6933).
- [ ] B3.1a Enumeration completeness self-check pre-render: reconcile
       retrieved vs selected; one supplemental probe on shortfall;
       `required_member_ids` wired from the retrieved strong set (chat
       hook chat:1836-1868 preferred).
- [ ] B3.1b Acceptance: g2-t1 5/5 entities + ratio ≥0.8; g2-t2 ≥5/6;
       g5-t2 ≥9/12; replay zero new signatures; differential
       non-regression.
- [ ] B4.1 Local-citation floor at render; local answers carry ≥1 local
       citation.
- [ ] B4.2 Web-citation boilerplate filter (navigation/error templates).
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
- [ ] B5.4 Evidence: same-day differential / replay re-run — marker-class
       empty answers disappear on both sides; C2.1f replay signatures
       re-classified (marker-class rows clear).
- [ ] B6.1 Education × region × industry combined person retrieval;
       g7-t1 ≥2 gold entities. (depends C1)

## Stage C — data groundwork

- [ ] C1.1 Field-quality contract + cleanup (professor boilerplate /
       placeholders; company placeholders; alias closure; key_personnel
       education).
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

## Spec deltas

- [x] S-delta B1: `canonical-v2-chat` — company→patent local traversal
       requirement (added with B1; both scenarios now satisfied live —
       g17-t1 GREEN round 3, honest-fallback wording unchanged).
- [ ] S-deltas for B2–B5 added with their slices.
