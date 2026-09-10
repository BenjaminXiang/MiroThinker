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
- [ ] B2.1 Layer D narrowing = displayed-id set ∩ condition; g2-t2/g5-t2
       coverage ≥80% of GT.
- [ ] B3.1 Enumeration key-entity self-check; g2-t1 five GT companies all
       present.
- [ ] B4.1 Local-citation floor at render; local answers carry ≥1 local
       citation.
- [ ] B4.2 Web-citation boilerplate filter (navigation/error templates).
- [ ] B5.1 LLM-guard hit degrades to template rendering; injected-fault
       test + trace token.
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
  - [ ] C2.1p Port `supplementary_field_values` to the serving line
         (inserted 2026-09-10 — third blocker; design.md §C2): verbatim
         model field (data-rebuild `index_projection.py:277`) + sealer
         conditional scalars passthrough + loader conditional
         reconstruction with `exclude_unset=True` (s12f rollback-compat
         lock). Contract test pins both sides; B1 focused suite +
         hermetic pack tests green.
  - [ ] C2.1r Seal the run14 pack with the OFFICIAL envelope sealer
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
  - [ ] C2.1b A/B boot on scratch port (localhost only, scratch
         access-log/corrections paths); measure boot wall-time and RSS —
         2.9G relationships replay is the resource gate; prohibitive →
         stop and report.
  - [ ] C2.1c Reconciliation report: per-domain counts vs s12f
         (5,659 → 47,071; papers 563 → 24,520), 优必选 bindings
         (58 → 459 expected), g2 GT-6 presence with addresses, 普渡
         control re-anchored to direct-scan bindings.
  - [ ] C2.1d Full 25-turn three-layer re-baseline on the scratch port.
         Hard gate: every turn green on the latest s12f baseline
         (results-after-s18.json: 21 PASS + g17-t1 GREEN via B1 = 22
         turns) still passes; regression → stop, no switch.
  - [ ] C2.1e Re-baseline gap-registry (GAP-15 closes; GAP-13 rows,
         GAP-02/04 ceilings re-measured); verification-c2.md landed.
  - [ ] C2.1f Switch 18188 (command file → run14, systemctl restart,
         replay 7/7); s12f pack + old command file kept for rollback.
         Production action — requires the user's go on the A/B evidence.
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
