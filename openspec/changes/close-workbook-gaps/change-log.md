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

## 2026-09-10 — B5 full design landed (redact-and-continue) ahead of dispatch

- Live defect recap: drifted LLM echoes prose protocol markers; the
  decoder raises mid-stream → SSE abort → empty answer (production,
  both lines; GAP-09 class).
- Design (design.md §B5): marker-in-prose is echo noise → redact the
  marker, continue the answer, trace token
  `prose-private-marker-redacted` via the existing TurnTraceReporter;
  template fallback stays reserved for genuine synthesis failure.
  Implementation-start verifications listed (raise-site reachability /
  no fallback catcher / flag plumbing), RED→GREEN acceptance, evidence
  via same-day differential (marker-class empties disappear both sides).
- tasks.md: B5.1–B5.4 expanded. Dispatch waits for C2 closure.

## 2026-09-11 — C2 CLOSED: run14 sealed live on 18188; replay r2 zero new signatures

- Post-switch integration defect (MANUAL_RECALL_DIR release mismatch)
  fixed: repointed to the run14 store; 22:51 restart; smoke re-verified —
  0 errors / 0 release_mismatch, G5 two-turn flow completes.
- Replay r2: G5_expansion PASS; 6 failure items across 4 turns ALL in
  known classes — G1_t3 / G3_t2 / G7 = in-register historical jitter
  signatures (B1 doc), G2_t2 = env marker class (B5 target). ZERO new
  signatures; gate passed under the documented jitter policy.
- Differential verdict PASS (23/25; sole regression attributed to
  composition jitter); latency cost logged (p50 +6.7s / p95 +32.4s).
- GAP-15 flipped GREEN; GAP-12 thresholds decided (90/70/70).
- Acceptance evidence: .agents/runs/close-workbook-gaps/
  verification-c2.md §1–§7; worktree closure commit 45877e81.
- Process note: agent-4 stalled twice on unattended approval prompts —
  network verification and closure executed from the main context
  (loop-prompt rule updated).

## 2026-09-11 — B3+B2 full design landed (enumeration & narrowing) before dispatch

- Line-verified mechanism map (explore report): 3 independent enumeration
  detections; `required_member_ids` never set (required-member branch
  dead); `_commit_prose_scope` narrows the carried displayed set to
  LLM-selected entities; two canonical-only filters drop non-canonical
  members; web narrowing probes capped at ≤6 + prefix; coverage counts
  semantically wrong (retrieved ≠ displayed).
- Design: D0 diagnostic gate first (per-entity drop-stage table); fixes
  B2-a faithful manifest / B2-b full-set per-member verdicts / B2-c
  coverage statement + count semantics / B3-a completeness self-check +
  required_member_ids wiring; hook = chat layer (chat:1836-1868)
  preferred over read layer. Acceptance fixtures listed verbatim.
- tasks.md: B3B2-D0 + B2.1a-c + B3.1a-b expanded. Dispatch after B5
  completes (one writer).

## 2026-09-11 — B5.1–B5.3 landed (worktree 9e1e79d4); deploy + B5.4 evidence in flight

- Decoder redact-and-continue implemented; token
  `prose-private-marker-redacted` wired at both consumption points; the
  admin-console DegradationToken Literal + valid-token set extended
  (companion finding: unknown tokens raise there).
- Evidence layering: 31 new/rewritten tests RED 28→GREEN 31 (decoder
  unit matrix incl. cross-chunk splitting; SSE real-HTTP integration
  test proving answer+done and journal token); old raise-assertion test
  deliberately split into redact-continue tests + a framing boundary
  lock (documented in-test). Pre-existing failures (test_read_turn_trace
  3 failed at HEAD; ruff) confirmed not slice-introduced via stash
  comparison.
- Deploy: 18188 restart issued 2026-09-11 (B5 code live after boot);
  replay r3 + smokes running; B3B2-D0 diagnostic dispatched in parallel
  (offline instrumentation; network steps reserved to main context).

## 2026-09-11 — B5 ACCEPTED: marker-class empty answers cleared live (GAP-09 → GREEN)

- Deploy: 18188 restarted with B5 code (9e1e79d4); ready; smokes
  (丁文伯 / 具身智能枚举): 0 error events, done received on both.
- Replay r3 (replay-b5-post-deploy): failures 6→2 — G1_t3 cleared,
  G2_t2 marker-class SSE error CLEARED (the B5 target class); remaining
  G3_t2 + G7 both in-register historical jitter signatures (G7 is the
  B3/D0 target). Zero new signatures.
- GAP-09 → GREEN (mechanism: redact-and-continue per approved design).

## 2026-09-11 — B5.5 landed via auto-snapshot (04e15966); commit-discipline hardened

- B5.5 (marker-family redaction: `canonical_v2` namespace regex + DSML
  half/full-width variants, 96-char candidate cap, byte-preserving
  flush) implemented and suite-green; its clean commit never ran — an
  approval stall on `git commit -m "$(cat <<EOF …)"` (command
  substitution) hung the task to its 2h timeout; the 03:07 auto-snapshot
  swept the changes into `04e15966`. Main-context review of the diff:
  approach accepted.
- Hard rule dispatched to subagents: git messages via `-F file` (Write
  tool) only; single simple bash commands; no `$(…)`, no heredocs, no
  network from subagents (3rd approval-stall of this class today).
- D0.5 (selection-admission rules / subject-gate per-item drops /
  structured-lane facts) resumed after the re-verify.

## 2026-09-11 — D0.5 done; B3+B2 phase-1 fix set LOCKED (F1/F2/F3)

- D0.5 findings (d0-probe/d05-findings.md): gate replay uses production
  functions against real captured provider bodies (6/6 anchors). Root
  causes confirmed: no deterministic category recall anywhere (fields
  exist in content_terms: industry 91.9%/tech_tags 77.4%/summaries
  100%); web→canonical binding impossible on first-turn category
  queries; `_commit_prose_scope` commits only selected handles (mention
  ≠ commit, 深南电路 evicted); gate backfill truncates full-name hits
  (g5-t2 9 B+ items cut; g2-t2 gate itself mostly correct — its real
  loss was probe-path invisibility of 普渡 HQ evidence at views 5–6).
- Locked phase-1: F3 gate backfill (kept<floor keeps all T2/T3) → F2
  commit union (selected ∪ mentioned) → F1 category recall over
  content_terms (micro-design in implementation; stop+report if beyond
  matcher/planner level). Deferred phase-2 (B2-a/b/c, F-bind, probe
  visibility) with trigger = multi-run acceptance shortfall.
- Acceptance: multi-run (carried sets vary day to day); g2-t1 5/5 /
  g2-t2 ≥5/6 / g5-t2 ≥9/12 (data ceiling noted); replay zero new
  signatures; differential non-regression.
- B5.5 re-verify (task A): 289 passed serving+trace (265+24 new);
  hermetic 36; B1 96/26; admin 147+3 pre-existing — all baseline-
  identical.

## 2026-09-11 — G1 delivered: retrieval-critical field contract draft (4 domains)

- Artifacts in `.agents/runs/close-workbook-gaps/g-series/` (g1 doc + 3
  reproducible probes). Headline findings: placeholder pollution in
  content_terms (professor 100% / company 30.3% of docs; 12,872 + 3,099
  occurrences; matcher must be prefix/pattern-based; "placeholders out of
  content_terms" is an ingestion-side rule recommendation); category
  anchoring — stable structured anchors only company.tech_tags/industry,
  patent.title, professor.research_directions; company category words
  8/14 >80% summary-only (储能 96.6%, PCB 91.8%); paper 13/14 summary-only.
- Thresholds (single-pack calibrated): only industry (91.9%<92) and
  patent summary (83.2%<85) warn on run14; target-state list of 9 items.
- G2 (identity) / G3 (category anchoring) sibling streams still running;
  combined C1-contract consolidation after all three land.

## 2026-09-11 — G2 delivered: identity audit — FOUR-DOMAIN ID CHURN 100% across releases

- Headline: s12f→run14 four domains changed ALL ids (company 1,733/1,733,
  professor 1,391, paper DOI 494, patent 1,931; natural-key hit 98.7-100%);
  575/1,733 companies (33%) had 16-field snapshots IDENTICAL yet got new ids
  — pure re-forging loss. Mechanism: the identity minting hash includes
  release_id (`canonical_identity_resolution.py:2219-2237`), no persistent
  identity state between generations.
- Fragmentation: company T2-core 12 entities/24 docs; T3-stem 72/146 (upper
  bound, brand collisions); professor 18 clusters/37 (9 sameness dup + 9
  homonyms); paper 6 clusters/12 (preprint vs journal, ALL DOIs different —
  dedup cannot rely on DOI equality); patent 0. Conflicts: 30/72 clusters
  have address+legal-rep mutually exclusive (42%) — brand-name auto-merge
  would merge different legal entities; only 42 clusters soft-mergeable.
  普渡 full sample: 3 identities, conflicting industry, bindings split
  128/0/27. credit_code/registered_capital fully empty; quality_status
  always "partial".
- §4 proposal = direct ADR input: primary-record rule (source family
  p4>legacy>backfill + completeness + deterministic tie-break); field
  merge rules; **stable_uid protocol** (ledger-allocated once, never
  re-minted; canonical id kept as version id; merge/split/rename event log;
  reference surfaces write stable_uid only) + interim option (drop
  release_id from the mint hash; max benefit 33%) with cost list and
  acceptance KPIs.
- Impact: every periodic update (C6) currently churns ALL ids — manual
  recalls, uploads, session/binding references break each cycle (the
  earlier manual-recall release_mismatch is a symptom of this class).
  The ADR (two-line contract home) now has its core input.

## 2026-09-11 — G3 delivered: category anchoring reality (tech_tags is the single point)

- Category corpus thin (914 turns / 76 distinct queries; category
  questions 361 → 190 clean → only 15 distinct; one query ×115).
  9 traffic words + 21 in-pack words = top 30; `g3_verify.py` 27/27.
- Anchoring: industry/industry_tags are coarse (2/30 hit); **tech_tags
  is the ONLY structured anchor for fine categories** (26/30 hit but
  ≈1 tag/company: 机器人 414/7089=5.8%, 具身智能 11 companies); patent
  ipc_codes / paper keywords = 0. Structured coverage spans 85.9%
  (人工智能) → 14.5% (具身智能) → 7.7% (PCB) → 0% (送餐机器人/视触觉).
- Gaps by traffic: 具身智能 summary-only; 酒店送餐机器人 / PCB打板
  ZERO hits in 47,071 docs (combination-granularity / action-word
  classes) — contract needs an unanchored branch (web supplement +
  honest wording), no summary fallback pretense. 17 high-volume
  text-only words listed (储能 3.0%, 机械臂 6.7%, 半导体 17.0%…).
- G-stream COMPLETE (G1/G2/G3). Next: consolidate into C1-contract v1 +
  two-line ADR draft for user review.

## 2026-09-11 — F1-B diagnostic: reranker hex-id tie-break destroys lane ranking; fix F4 approved

- Live acceptance (post-F1) failed 0/5 although the lane fired (lexical
  in=48). Production-function replay diagnostic (agent-4): all local
  candidates carry raw_score=1.0 (`knowledge_read_isolated.py:8741`), so
  the rerank bucket sort `(-raw_score, result_id)`
  (`knowledge_serving_isolated.py:2525-2526`) degenerates to random-hex
  canonical-id string order; the 48-cut then keeps hex-lucky candidates.
  g2's 普渡/开普勒/擎朗/九号/艾唯尔 all die at the 48-cut; 云迹 survives
  as local #18 and dies at the local-16 selector window; g5 only
  深南电路 (hex-lucky) reaches the answer. The prose LLM never saw the
  GTs. The hypothesized direct_object_ids cut was NOT triggered.
- Fix F4 approved: drop the `result_id` tie-break (stable sort preserves
  fusion/lane order). Predicted: g2 six GTs into payload; g5 顺易捷
  revives. Out of scope: g5 out-of-window six (F1 recall gap), local-16
  semantics (separate decision). Evidence: d0-probe/f1b-downstream-trace.md.

## 2026-09-11 — B4 scoped (read-only); three adjudications required before dispatch

- Scope report: `.agents/runs/close-workbook-gaps/b4-scoping.md` (from
  explore agent-11 read-only pass over the serving worktree).
- Minimal citation-floor hook = Hook A: relax `canonical_v2_chat.py:2272`
  `lane != "relationship"` to "any local evidence (source_nature ∉
  {current_web, supplemental_web}) with public-domain handle" → URL-less
  `local-source-` card. Closes g17-t2. No retrieval/prompt changes;
  retained-membership check still bounds it (no fabricated citations).
- GAP-08 web-pollution assertion is near-noop TODAY: `CITATION_FORBIDDEN_PATTERNS`
  (`anchors.py:205-217`) is consumed only by the test harness; the card
  contract has no title/snippet and the canonical path never emits a
  `type=="web"` card; all archived runs have citations_web==0. Needs an
  adjudication (extend ChatCitation contract vs re-point assertion at
  answer text / evidence payload) before B4 code lands.
- Latent drift found: the B1 `local-source-` card branch exists only in
  the worktree (`chat:2272-2285`, 24-line diff); main-repo HEAD lacks it.
  Recorded into the S3 contract-convergence scope; do not hand-port
  ad hoc.
- Harness local-judgement to change to `local-source-` prefix (currently
  counts every non-web card as local, including official-source).
- First step after adjudication: D0-style 9-round card-loss
  probe (answer-layer vs adapter-layer loss) before Hook A lands.
  g1-t1 / g17-t2 need a post-B5 re-run for coverage.

## 2026-09-11 — F4 deployed; acceptance r3/r4 (live) red 0/5 — attribution map

- Deploy: 18188 restarted on the F4 worktree state; lane-level evidence
  (trace `var/turn-trace/2026-09-11.jsonl`) shows lexical in=48 on the
  enumeration turns; answers switched from hex-lucky companies to the
  lane-ranked canonical set (r3 g2-t1 names 云迹/普渡/擎朗/艾唯尔/中科世界/
  小村; g5-t1 names 嘉立创/顺易捷/深南电路) — F4's effect is live.
- Acceptance double-run (r3/r4, `results-b3b2-acc-r3/r4.json`): both 0/5.
  Signatures are stable across runs (开普勒/九号 and 一博 missing in
  every post-F4 run; g2-t2 pool 1–2<5; g5-t2 coverage 1/12).
- Attribution (evidence: replay after-F4 stage tables + trace + in-pack
  records):
  1. **g2-t1** — payload has the five must-entities (开普勒 local#3,
     九号 local#8, both inside the 16-window); 安赛步/锐曼 are OUTSIDE
     the local-16 window. The prose answer names 云迹/普渡/擎朗 but skips
     开普勒/九号: their in-pack records are thin/generic (九号:
     `product_description=null`, boilerplate profile; 开普勒: product
     names only, hotel mention sits in `technology_route_summary`), so no
     claim supports naming them as hotel-delivery suppliers. GT expects
     them because of outside knowledge → needs web-supplement binding or
     data (D9).
  2. **g2-t2** (narrowing) — pool companies ARE 深圳 by name/address,
     but the follow-up answer only confirms 普渡: address/geography
     evidence does not reach the narrow-turn claims (models refuses to
     infer HQ from a name prefix). entity pool stuck at 1–2/6 in all
     four runs.
  3. **g2-t3** (stance) — GT: 普渡 can 自主按电梯; in-pack has no such
     claim → post-F4 answers say "无法确认" (forbidden pattern). Pre-F4
     runs failed the entity layer instead (普渡 not mentioned at all).
  4. **g5-t1/g5-t2** — the four PCB names beyond F1 recall
     (一博 pool 98 / 兴森 70 / 则成 62 / 上达+精诚达 no score) never enter
     the candidate set; 一博 missing in all runs. 深南电路/嘉立创 appear
     in r3 but not r4 (answer-layer selection variance). g5-t2 breadth
     stays 1/12 because t1's committed set is 4–5 entities (session
     snapshot `displayed_id_count`), far below the GT 9/12.
- Verdict: B3B2-ACC NOT met; F1–F4 delivered their retrieval-level
  effect; the remaining gaps are answer-content class (display/claim
  breadth, narrowing attribution, stance data) + F1 recall windows —
  i.e. the answer-quality slice, not another rerank fix. Run-to-run
  variance is large (pre-F4 r1 2/10 vs r2 6/10 key points on g2-t1);
  only the double-run-stable misses count as findings.
