# Change Log: close-workbook-gaps

## 2026-09-10 — Change opened

- Opened under the system-completion plan approved 2026-09-10
  (P1 functional completeness first, P2 delivery second).
- Scope: 16-item workbook gap list (evidence doc
  `docs/plans/2026-09-09-testset-baseline-and-repair-plan.md` §九),
  stages B (serving-line fixes) and C (data groundwork).
- B1 designed in full (design.md); B2–C5 recorded as stubs to be filled at
  slice start.
- User directives baked in: simple path first; audit/proof layers frozen;
  thin-load/direct-scan instead of assembly-contract repair (risk R1).

## 2026-09-10 — B1 round 1: port landed, design revised (two upstream gates)

- Port of the G3-simple scan landed as commit `b20161d` (+79 lines) with an
  added path-eligibility guardrail (source block `790f4d1` re-admitted
  excluded endpoints — same defect confirmed present in the data line;
  **follow-up: back-port the guardrail to the data line**).
- g17-t1 stayed RED: the ported function is unreachable on the s12f pack.
  Evidence in `.agents/runs/close-workbook-gaps/verification-b1.md`:
  Gate A (planner binding: patterns miss "有哪些专利" shape + pack aliases
  lack the bare short name) and Gate B (dispatch routes company→patent to
  `_source_bound_relationship_candidates` because s12f has 0
  relationship-scoped eligibility rows; positive control 普渡 = 17
  candidates proves the lane machinery works).
- design.md §B1 revised: Gate A fix (patterns + derived short-name channel
  with uniqueness guard), Gate B fix (shared `_direct_patent_applicant_scan`
  helper called from the source-bound path — dispatch re-routing rejected
  because it would regress 普渡), B1c (relationship-lane citations).
- Replay jitter documented (7/7, 6/7, 6/7 across identical code; failing
  signatures all pre-existing in historical logs; ported code unreachable
  on this pack). Interim acceptance policy recorded in design.md; jitter
  fix queued as `harden-serving-test-harness` A3.4.
- Tasks B1.3–B1.5 added; B1.1 marked done.

## 2026-09-10 — B1 round 2: Gates A/B + citation floor landed; Gate C found

- Round 2 landed on `codex/canonical-v2-s12a-ready` (source in auto
  snapshot `1860b8c`, tests `673edb7`): Gate A binds the bare short name
  ("优必选有哪些专利" → `company-c-64e631c0e0cd9e91d032d209`) through the
  `_compact_company_alias` channel — the originally sketched possessive
  pattern extension was correctly skipped (the short-name channel covers
  it, and the extension would mis-fire on "…的竞争对手有哪些专利");
  Gate B unions `_direct_patent_applicant_scan` into
  `_source_bound_relationship_candidates` (优必选: 48 candidates = 58
  bindings − 10 path-eligibility exclusions); B1c emits
  `local-source-<sha>` citation cards for URL-less relationship evidence.
  Positive control 普渡 end-to-end green: 17 candidates → 16 CN numbers +
  16 local cards (archive `pudu-answer-r2.json`).
- g17-t1 stayed RED at a third, deeper gate: `_apply_constraints`
  (knowledge_read.py:6174) derives `displayed_entity_witness_ids` only from
  relationship projection traces; scan items carry a typed claim binding
  and no trace (by design), so the `displayed_entity_set` slot rejects all
  48. Minimal repro:
  `.agents/runs/close-workbook-gaps/repro_constraint_gate_scan_items.py`.
- Mechanism verified line-by-line before designing the fix: witness ids are
  consumed solely by the `displayed_entity_set` branch (geography /
  exact-identifier slots use claim-subject / identity paths); the answer
  selector already admits these candidates via `_claim_binding_binds_anchor`
  (knowledge_serving_isolated.py:5678); `_apply_constraints` is shared by
  the main read flow (:7961) and the release-bound relationship validator
  (knowledge_read_isolated.py:6118), so one edit keeps both consistent.
- design.md §B1 revision 2 adds the Gate C fix (claim-binding witness
  branch mirroring the selector's value-endpoint semantics) with rejected
  alternatives and the round-3 test matrix; task B1.6 added.

## 2026-09-10 — Sequencing change: C2 first; C2 design landed + contract verified

- User decision (evidence: human log entry 4): GAP-02/04 acceptance
  assertions are data-capped on the s12f pack (g2 GT-6 3/6 in pack,
  geography 0/1,737; g5 GT-11 3/11) and only reachable on run14 (GT-6 6/6
  with Shenzhen addresses, GT-11 8/11, geography 91.9%). New order:
  **C2 → combined B2.1+B3.1 "enumeration & narrowing" slice → B4/B5**.
- design.md §C2 written in full: boot the run14 serving pack
  (`/var/tmp/mirothinker-data-v2/serving-pack-run14/`, 47,071 docs /
  7,089 companies / relationships.json 2.9G) through the existing
  pack-mode fast path (`--serve --serve-existing --serving-pack`),
  scratch-port A/B with boot-time/RSS measurement gate, reconciliation
  report, 25-turn re-baseline hard gate (s12f's 9 PASS + g17-t1 must not
  regress), then the 18188 switch (production action, user go required).
- Boot contract verified line-by-line in main context before dispatch:
  `open_serving_pack_authority` binds release_id + index_marker_sha256 +
  forbidden milvus path + per-file hashes + deep request/result hash
  reproduction; run14 manifest values extracted
  (`candidate-v2-20260819-r1`, marker `8848197c…`, index_root
  `/var/tmp/mirothinker-data-v2/index-v1` — live marker hash matches);
  all five pack file hashes pre-verified ALL-OK; thin mode never reads
  the envelope and never connects to Postgres (disposable db name is an
  agreement string); `load_recorded_serving_inputs` still binds the
  serving bundle (release/database/index_root/envelope_path/content
  hash) — exact six-arg command delta + one minted bundle file recorded
  in design.md §C2 step 2.
- tasks.md: C2.1 expanded into C2.1a–f; sequencing note added at top.

## 2026-09-10 — C2.1a landed; first scratch boot failed closed (half-sealed pack); reseal step inserted

- C2.1a done (worktree `9cfdabe`): run14 RecordedServingBundle minted and
  externally re-validated; `serve-18189-command.sh` cloned with a
  token-level assert that the diff is exactly the designed six args + port
  + two scratch env overrides.
- C2.1b first boot on 18189: RSS peaked ~14G, exited after ~2min at
  `serving_pack_loader.py:672` — "serving pack index result does not
  reproduce its recorded hash". Root cause (agent evidence doc
  `c2-scratch-boot-failure.md`, re-verified in main context): the run14
  pack is half-sealed — index files are the 2026-09-08 run14
  materialization (live-index receipt built_at 2026-09-08T11:07:10Z,
  51,029 pts / 47,071 docs) while the manifest keeps the p4 (2026-08-26)
  index-side bindings (`index_result_content_sha256 738219cf…`, policy
  snapshot, rebuild decisions). No run14 build envelope exists; the only
  sealer seals from an envelope. Loader is correct; pack is the defect.
- design.md §C2 amended: setback subsection + new task C2.1r —
  deterministic `reseal_serving_pack.py` recomputes every loader-bound
  manifest field from the artifacts into a fresh pack dir
  (`serving-pack-run14-resealed`), dogfoods through
  `open_serving_pack_authority`; provenance fields carried, reseal records
  itself via `generator_run_id c2-reseal-20260910-v1`. Rejected: in-place
  hash patch, full envelope build, loader loosening.
- tasks.md: C2.1a marked done, C2.1r inserted before C2.1b.

## 2026-09-10 — C2.1r revised: genuine run14 envelope found; seal with the official envelope sealer

- First resealer iteration (worktree `9a99ca2`) exposed layer 2: run14
  relationships.json candidate section is an old-generation container (20
  pydantic errors vs the current typed-split contract) and four
  loader-required sections are missing (request scalars ×2, eligibility
  requests/results — data-level, one per entity). Evidence doc
  `.agents/runs/close-workbook-gaps/c2-reseal-blocked.md`.
- Main-context verification: all 47,071 candidate elements parse clean
  into the current PublicDomainProjection union (uniform release/as_of/
  version, sorted, no dups) — transcode would have been mechanical; p4
  pack carries 32,941 per-entity eligibility pairs, so synthesizing the
  missing sections meant computing pipeline artifacts.
- Decisive discovery: the data line DID run the full pipeline for run14 —
  genuine envelope at data-rebuild
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-
  candidate-build-envelope.json` (8.1G, mtime 2026-09-08 20:00, one hour
  after the run14 index materialized; release `candidate-v2-20260819-r1`,
  run `p4-build-20260819-v1`, receipt with all hash bindings). The
  half-sealed pack was a hand-assembly that bypassed the envelope sealer.
- C2.1r revised: seal with the official `s12c/build_serving_pack.py`
  (serving-worktree copy) into fresh
  `/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed/`
  (generator `c2-seal-20260910-v1`); sealer dogfoods through the real
  loader and proves envelope-equality. Resealer/transcode path rejected
  (synthesizing sections when genuine artifacts exist = inventing data);
  resealer stays committed as tooling. Sealed relationships.json will be
  larger than 2.9G (eligibility sections) — A/B boot measurement gate
  applies as designed.

## 2026-09-10 — Third blocker: envelope/serving contract delta; C2.1p ports supplementary_field_values

- Official sealer failed closed at envelope validation on exactly one
  pydantic error: `index_projection_request.supplementary_field_values` —
  the data line's 2026-09-07 multi-value enrichment field (`a226bd8`),
  which widens run14's vector/lexical search surfaces at build time.
  Structural: sealer hashes the full request but writes 6 scalars; loader
  reconstructs from scalars — all three sites must learn the field.
- Option (a) chosen (agent analysis, main-context verification of the
  three edit sites): verbatim port — model field + sealer conditional
  scalars passthrough + loader conditional reconstruction with
  `exclude_unset=True`. The exclude_unset semantics keep s12f's
  canonical dump byte-identical (rollback path boots with the same new
  code) while run14 includes the field and reproduces the envelope hash.
  No serving query-code change: the enrichment is baked into the index
  content; serving needs contract-level understanding only.
- Rejected: (b) strip the field (provenance lie), (c) re-run run14 with
  serving-contract code (heaviest, discards the enrichment).
- tasks.md: C2.1p inserted before C2.1r; C2.1d hard gate corrected to
  the latest baseline (21 PASS + g17-t1 = 22 turns must not regress;
  agent evidence: results-after-s18.json).

## 2026-09-10 — C2.1p landed (3734f30); second seal refusal: replay-level build-path delta; C2.1q approved

- C2.1p verified: 2 pin tests + hermetic pack 21 + B1 focused 96/26 +
  fast_boot 14, all identical to the pre-port baseline; reconstruction
  trees verified fully explicit (exclude_unset provably inert for s12f).
- Re-run seal passed field validation, then refused deeper: "consumer
  handoff index request is cross-wired from its release bundle" — the
  envelope validator (`knowledge_build_isolated.py:1824-1835`) embeds a
  full deterministic index replay; the serving build path lacks the data
  line's 47 enrichment-consumption lines (4 hunks, same
  `index_projection.py`). Envelope self-consistent (data-line validator
  verbatim, no bypass). Discovery: the data line carries a private
  `SERVING_PACK_SKIP_HASH_VERIFY=1` backdoor (18 lines) — that is how the
  half-sealed pack ever booted; the serving line correctly lacks it.
- Option (a) approved: port the remaining 4 hunks verbatim → two-line
  `index_projection.py` byte-identical (zero-drift end state;
  `domain_projection_models.py` confirmed no-diff; side benefit:
  `knowledge_read_isolated.py:818/1866` replays become bit-consistent).
  Rejected: (b) data-line sealing (their sealer lacks C2.1p scalars
  passthrough), (c) validator bypass (forbidden).
- C2.1c lookup-side reconciliation landed (agent, pre-computed):
  5,659→47,071 per domain; 优必选 450 id bindings (s12f 58; entity
  re-normalized `company-c-b2aac54891e3fce8c98612d8`; by-name sightings
  459 = 450 + 9 unbound); total bindings 7,650 as designed; 普渡 128;
  GT-6 all in pack, addresses filled 3/6 （越疆/优必选/速腾聚创 yes;
  普渡/优地/云迹 null — B3+B2 narrowing must keep the name-heuristic/
  web fallback path for null-address members).
- tasks.md: C2.1p done, C2.1q inserted.

## 2026-09-10 — Blocker ④: read-side enrichment strip block; C2.1s inserted; drift inventory classified

- After C2.1q, the sealed pack passed `open_serving_pack_authority` IN
  FULL on the first boot attempt (authority chain proven live; supplies
  the dogfood phase the seal log did not echo). Boot then failed in the
  knowledge-read composition: 903 public lookup docs carry a baked
  `_supplementary` key (company 899/7,089, professor 4/3,958) that
  serving's strict projection validation rejects. This is the READ half
  of the multi-value enrichment; C2.1q's "one file = zero drift"
  assumption was incomplete.
- Option A chosen: port the data line's 14-line strip block
  (`knowledge_read_isolated.py:7954-7967` — strip `_supplementary`/
  `_quality_tier` from a copy, then validate; lineage/round-trip checks
  unchanged) verbatim + pin test; then restart the boot. Rejected:
  relax the model extra (weakens validation, fails round-trip), rebuild
  run14 without the key (discards the enrichment).
- Full two-line drift inventory of `knowledge_read_isolated.py` (16
  hunks/338 lines) classified in `c2-boot-blocked-supplementary.md`;
  only the strip block is ported. Named follow-ups: ① vector-trace
  tolerance hunks — query-time fail-closed risk, C2.1d trips it → STOP
  and fix as its own verified port; ② exact-phrase/identifier-fallback/
  G6-containment hunks — genuine retrieval improvements, dedicated
  convergence slice after B3+B2 (must not be smuggled into a boot-fix).
- tasks.md: C2.1q/C2.1r marked done; C2.1s inserted; C2.1f reframed per
  user policy (18188 switch routine + milestone live for user E2E).

## 2026-09-10 — C2.1s/b/c done; C2.1d gate amended to same-day double-run (LLM env drift)

- C2.1s landed (43fa1340): strip block ported verbatim, function head
  diff vs data line = zero; pin test (RED→GREEN, lineage-tamper negative)
  + hermetic pack 22 + B1 96/26 + fast_boot 14.
- C2.1b on the sealed pack: wall 696s (≤900), RSS peak 28.7G (≤32G;
  16.9G at ready), responsive (优必选 query: full SSE, 17 grouped
  patents). C2.1c closed: relationships 10,897 / patent_has_applicant
  123 materialized (49 companies) — 450/128 ride lookup applicants +
  read-side direct scan by design ("~123 of ~7,078", numbers match).
- C2.1d aborted turn 6: empty_answer = `_filter_private_markers` raising
  on echoed protocol markers; SAME failure on live 18188 (s12f,
  untouched) today — LLM backend (deepseekv4flash) drifted post-9/9;
  archived baseline unreproducible. Gate amended: same-day double run
  (18188 s12f vs 18189 run14, 25×2; run14 not worse per turn; 2-1/2-3
  普渡 differences attributed by the differential).
- Queue note: the guard hard-fail → empty answer is GAP-09 live; B5
  priority recommendation (before B3+B2) recorded, pending user nod.
- tasks.md: C2.1s/b/c marked done; C2.1d rewritten; C2.1f wording keeps
  differential gate.
