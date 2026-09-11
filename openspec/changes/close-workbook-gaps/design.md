# Design: close-workbook-gaps

> Standard change. Design decisions are recorded per slice; slices B2–B6 /
> C1–C5 get their detailed section when their slice starts. B1 is designed
> in full because it starts immediately.

## Guiding constraints

1. **Simple path first** (user directive 2026-09-10): the current stack is
   over-engineered — audit/proof layers are frozen, traceability degrades
   to "point at the source when possible". New code takes the shortest
   correct path inside the existing serving architecture; no new proof
   scaffolding.
2. **Thin-load / direct-scan over assembly-contract repair** (risk R1):
   the run14 pack fails 42 cascading loader validations. We do NOT repair
   the assembly contract chain in this change; data reaches serving through
   direct reads of the pack lookup SQLite / Milvus Lite.
3. **No regression without evidence**: every serving-line slice re-runs the
   replay gate (7/7) and the focused workbook turns.

## B1 — company→patent direct scan (full design)

**Facts (measured 2026-09-09/10).** The s12f serving pack's relationship
tables hold 121 `patent_has_applicant` rows covering 48 companies — 优必选
not among them. The same pack's lookup SQLite carries 1,704 field-level
patent→applicant bindings (58 for 优必选; run14: 7,650 total, 459 for
优必选). Data exists; the read path does not.

**Chosen approach.** Port `_company_to_patent_relationship_candidates`
(the "G3-simple" block, ~60 lines, data-line commit `790f4d1`, file
`knowledge_read_isolated.py` in `.worktrees/data-rebuild`) into the
deployment line
`.worktrees/canonical-v2-s11-consolidation/apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`.

- The deployment-line function of the same name sits at ~`:3194`; the new
  scan block inserts before the final
  `return tuple(candidates[: request.max_candidates])` (~`:3801`).
- `EvidenceItem`, `RecallCandidate`, `PatentProjection` are already
  imported in the deployment line — the port must not add new imports or
  new dependencies.
- Scan semantics: from the pack lookup SQLite, select patent rows whose
  applicant binding matches the requested company_id (exact id match, not
  name fuzzy match); project each to the existing patent candidate shape;
  order deterministically (e.g. by publication date desc when available);
  cap by `request.max_candidates`; merge with relationship-table
  candidates, de-duplicated by patent id.
- Citations: candidates produced by this scan carry local evidence items so
  the answer renderer can emit local citations (GAP-07 alignment).

**Rejected alternatives.** ① Repairing the assembly contract so
`patent_has_applicant` fills completely — contract chain is the R1 swamp,
deferred to the data line. ② Name-based fuzzy matching against patent
applicant strings — ungrounded; id-based bindings already exist.

**RED → GREEN.** RED: hardened runner g17-t1 assertion (≥3 `CN\d{9,}` ids
AND citations_local ≥1) fails today (baseline: 1 CN id, citations_local=0,
answer sourced from web/Tianyancha). GREEN: same assertion passes on the
live 18188 endpoint after restart; replay gate stays 7/7.

## B1 revision (2026-09-10, after first implementation round)

The literal port landed (commit `b20161d`) but is **unreachable on the s12f
pack** — evidence in
`.agents/runs/close-workbook-gaps/verification-b1.md`. Two upstream gates
must open for g17-t1, plus the citation floor. Design corrections:

**Gate A — planner never binds 优必选 (knowledge_read_isolated.py:414–490).**
`_NAMED_COMPANY_PATENT_PATTERN` only matches "X的[相关]专利" ("有哪些专利"
and "的专利有哪些" shapes miss), and the verbatim channel needs a literal
alias/normalized_name hit while the pack's aliases lack the bare short name
"优必选". Fix:
1. Extend the pattern to the "X有哪些专利" / "X的专利有哪些" shapes.
2. Add a derived short-name channel: strip legal prefix/suffix
   (深圳市…股份有限公司/有限公司 etc.) from each company projection's name
   (reuse an existing company-name normalizer if one exists; otherwise a
   minimal fixed-suffix stripper), match when the short name (len ≥ 2)
   appears in the query. The existing `len(matched) != 1 → None` uniqueness
   guard already prevents ambiguous binds; the resolver only fires on
   patent-intent queries, bounding the blast radius. Systemic alias
   completion stays with C1; this is the serving-side minimum.

**Gate B — read-side dispatch bypasses the scan (:5409–5439).** s12f has 0
relationship-scoped eligibility rows, so company→patent always routes to
`_source_bound_relationship_candidates` (:4965), which scans only the
relationship table (121 rows / 48 companies, 优必选 absent). Fix: extract
the ported field-binding scan into a shared helper
(`_direct_patent_applicant_scan`) and call it from
`_source_bound_relationship_candidates` for the company→patent path
(`_COMPANY_TO_PATENT_QUERY_PATH`), unioned with relationship-table
candidates and deduplicated by patent id. Do NOT re-route the dispatch to
`_company_to_patent_relationship_candidates` — on packs without per-edge
eligibility its relationship-trace section yields 0 and would regress the
positive control (普渡 = 17 table rows). The ported block in
`_company_to_patent_relationship_candidates` stays (correct on packs with
per-edge eligibility) and now shares the helper.

**B1c — citation floor for relationship candidates.** Positive control
shows 17 local relationship candidates still produce citations=0. For the
spec-delta scenario (citations_local ≥1), the answer renderer must surface
local citations from relationship-lane candidates' evidence items. Scope
to the relationship lane here; the general citation floor + web hygiene is
B4.

**Source-block defect (follow-up, data line).** The verbatim port
re-admitted path-eligibility-excluded endpoints; the deployment-line port
added a guardrail. The same defect exists in the data line (`790f4d1`) —
back-port the guardrail there (recorded in change-log; data line is not
the serving line, not blocking).

**Replay-gate jitter (interim policy).** Three replay runs on b20161d gave
7/7, 6/7, 6/7 with mutually different failure subsets; every failing
signature also appears in historical logs on unmodified code
(`testset-baseline-20260909/regression/replay-*.log`) and the ported code
is unreachable on this pack (no causal path). Interim acceptance: a replay
run whose only failures match the documented pre-existing jitter signature
set, with the jitter table attached. Jitter quantification/fix is added to
`harden-serving-test-harness` as task A3.4.

## B1 revision 2 (2026-09-10, after round 2) — Gate C: constraint-layer witness for trace-less scan candidates

Round 2 landed Gate A (bare-short-name binding via the
`_compact_company_alias` channel), Gate B (shared
`_direct_patent_applicant_scan` unioned into
`_source_bound_relationship_candidates`; 优必选 yields 48 candidates =
58 bindings − 10 path-eligibility exclusions), and B1c (`local-source-<sha>`
citation cards for URL-less relationship evidence). The 普渡 positive
control is end-to-end green (17 candidates → 16 CN numbers + 16 local
cards). g17-t1 still failed RED at a third gate (evidence:
`verification-b1.md` round 2; minimal repro
`.agents/runs/close-workbook-gaps/repro_constraint_gate_scan_items.py`).

**Gate C — the displayed_entity_set constraint has no witness source for
trace-less scan candidates.** Scan `EvidenceItem`s carry a typed claim
binding (`subject=canonical:patent:<candidate>`,
`predicate=patent_has_applicant`,
`value=canonical:company:<displayed anchor>`, `status=accepted`) and, by
design, no `local_projection_trace` (scan edges have no per-edge
relationship authority). `_apply_constraints` (knowledge_read.py:6174)
derives `displayed_entity_witness_ids` only from the five relationship
trace branches (:6207/:6245/:6288/:6319/:6360), so scan candidates get an
empty witness tuple; their identity ids are patent ids, which never
intersect the company anchor in `slot.entity_ids`; every candidate is
rejected (:6542–6555) and the answer degrades to "未能建立关联".

**Fix — a claim-binding witness branch in `_apply_constraints`**, mirroring
the answer selector's `_claim_binding_binds_anchor`
(knowledge_serving_isolated.py:5678, call site :5777) — the selector already
admits exactly these candidates; the constraint layer must not be stricter
than the downstream selector:

1. Fires only for relationship-lane candidates
   (`candidate.origin_lane == "relationship"`), and only when no trace
   branch derived a witness (trace branches keep precedence; same-turn
   traces and scan bindings bind the same anchor, so precedence is
   behaviorally neutral today).
2. Witness = the terminal id of each claim-binding **value** of the shape
   `canonical:<domain>:<id>`, restricted to bindings whose subject is the
   candidate itself (`canonical:<candidate.domain>:<candidate.canonical_id>`).
   Value endpoint only, never subject — trace-bound traversal claims use
   the opposite orientation, so accepting the subject side would re-admit
   cross-anchor candidates (selector docstring rationale applies verbatim).
3. Consumption stays single-point: the `displayed_entity_set` branch
   intersects `identity_ids ∪ witness_ids` with `slot.entity_ids`. A
   binding pointing at a non-displayed company never intersects → still
   rejected (negative direction locked by test). Geography and
   exact-identifier slots consume claim-subject / identity paths, never
   witnesses — verified unaffected.

**Consistency is structural.** `_apply_constraints` has exactly two
callers — the main read flow (knowledge_read.py:7961) and the release-bound
relationship validator (knowledge_read_isolated.py:6118), which recomputes
expected selections with the same function. One edit keeps read flow and
validator in agreement; after the fix the validator *requires* the scan
items it previously excluded, and the read flow supplies them.

**Equivalence lock.** A contract test asserts the read-layer branch and the
serving selector's `_claim_binding_binds_anchor` agree over a fixture
matrix (anchor in/out of the displayed set, subject-side vs value-side
orientation, non-canonical values), so the two gates cannot drift apart.

**Rejected alternatives.** ① Attaching a synthetic
`LocalSourceRelationshipTrace` to scan items — fabricates per-edge
authority the scan never executed (trace fields bind the release hash chain
and path-eligibility evidence); the claim binding is the truthful
provenance shape. ② Routing scan candidates through
`_apply_direct_item_constraints` — that path has no witness concept and
would need the same branch anyway, plus loses fused-candidate receipts.
③ Fixing in the selector — the selector sits downstream of constraints;
rejected candidates never reach it (claims=0 → "未能建立关联"), so the fix
belongs at the constraint layer.

**Round-3 tests.** Positive: a fused scan-only candidate bound to the
displayed anchor passes `displayed_entity_set`. Negatives: binding value
pointing at a non-displayed company still rejected; subject-side-only
canonical binding (traversal orientation) yields no witness and is still
rejected. Equivalence: read branch ≡ `_claim_binding_binds_anchor` over
the matrix. End-to-end: g17-t1 three-layer GREEN on the live 18188
endpoint (优必选 + ≥3 CN ids + local_citations ≥1), CN ids cross-checked
against the pack SQLite; 普渡 positive control not regressed; replay gate
per the interim jitter policy.

## B2–B6, C1–C5 — design stubs (filled at slice start)

> Sequencing change (user decision 2026-09-10, evidence in human log entry 4):
> **C2 runs first**, then B3+B2 as one combined "enumeration & narrowing"
> slice on the run14 pack. Rationale: the GAP-02/04 acceptance assertions are
> data-capped on s12f (g2 GT-6: 3/6 in pack, geography fields 0/1,737; g5
> GT-11: 3/11) and only become reachable on run14 (GT-6: 6/6 with Shenzhen
> addresses, GT-11: 8/11, geography filled 91.9%, all five g2-t1 GT companies
> present). B4/B5 stay code-only and queue after the combined slice.

## C2 — run14 thin-load online (full design, 2026-09-10)

**Facts (measured 2026-09-10).** The data line already built a run14 serving
pack at `/var/tmp/mirothinker-data-v2/serving-pack-run14/` with exactly the
live pack's file contract (compare `/var/tmp/mirothinker-canonical-v2-s12f/
serving-pack/`): `.canonical-v2-isolated-index-target.json`,
`institution_catalog.json`, `lookup.sqlite3` (635M; 47,071 docs / 7,089
companies), `manifest.json` (8.7M), `milvus.db` (1.1G), `relationships.json`
(2.9G vs live 321M). The serving line's boot already has a frozen-validation
fast path: `--serve --serve-existing --serving-pack <dir>` in
`complete_candidate_runner.py:1151-1172` skips the envelope build and
`_validate_result_graph`, loading only the pack authority
(`serving_pack_loader.open_serving_pack_authority`, keyed by
`candidate_release_id` + `index_marker_sha256`).

**Chosen approach.** Boot the run14 pack through the existing pack-mode fast
path — no assembly-contract repair, no new serving code:

1. **Pack authority probe** (done 2026-09-10, main-context verification):
   run14 `manifest.json` → `release_id = candidate-v2-20260819-r1`,
   `index_marker_sha256 = 8848197caaa665fa093f054aa6c7c241b90376f311ec62e
   089ddb479a6e97c8b`, `index_root = /var/tmp/mirothinker-data-v2/index-v1`
   (live index the snapshot opens; its marker file sha256 matches the
   manifest value byte-for-byte), `index_forbidden_milvus_paths` identical
   to the s12f command's `--accepted-original-milvus-path`, embedding model
   identical (`Qwen/Qwen3-Embedding-8B`). All five pack file hashes
   pre-verified against `manifest.files` (ALL-OK). Thin-mode facts: the
   runner's pack path never reads the envelope and never connects to
   Postgres (`database_url` is only consumed by `create_builder`;
   `gap_operations` is ephemeral), so `--database-url`/`--expected-database`
   are agreement strings only. `load_recorded_serving_inputs`
   (`knowledge_serving_isolated.py:5916`) still runs in thin mode and binds
   the serving bundle to release_id / database_name / index_root /
   envelope_path / content hash.
2. **run14 serve command**: clone the s12g command contract. Exact delta —
   six args plus one new file: ① `--serving-pack /var/tmp/mirothinker-
   data-v2/serving-pack-run14`; ② `--candidate-release-id
   candidate-v2-20260819-r1`; ③ `--index-marker-sha256 8848197c…`;
   ④ `--index-root /var/tmp/mirothinker-data-v2/index-v1`;
   ⑤ `--expected-database` / `--database-url` → a fresh disposable name
   (`miroflow_candidate_v2_20260819_r1`, never connected); ⑥
   `--recorded-serving-bundle{,-sha256}` → a new minted
   `RecordedServingBundle` json (schema `canonical-v2-serving-bundle-v1`;
   policy knobs `max_candidates`/`max_web_results`/`web_timeout_ms`/
   `web_snapshot_max_bytes` carried from the s12f bundle; `envelope_path`
   equal to the unchanged CLI `--envelope-output`; `content_sha256` =
   canonical sha256 of the dump minus the field, per the model validator).
   Everything else stays byte-identical (forbidden-milvus triple, recorded
   decision/embedding bundles, envelope-output, run-id, source batches,
   parser/policy versions). New command file next to the s12g one; the
   live 18188 command file is NOT touched until the A/B gate passes.
   Scratch runs additionally override `CANONICAL_V2_ACCESS_LOG_DB` /
   `CANONICAL_V2_CORRECTIONS_DB` to scratch paths so A/B traffic never
   pollutes the production stores.
3. **A/B boot on a scratch port** (localhost only): boot run14 on a scratch
   port with the same worktree code; measure boot wall-time and RSS — the
   2.9G `relationships.json` is 9× the live one and the in-memory
   relationship authority replay is the main resource risk (measurement
   gate: boot succeeds and stays responsive; if RSS/replay is prohibitive,
   stop and report before any switch).
4. **Reconciliation report**: per-domain document counts vs s12f
   (5,659 → 47,071; papers 563 → 24,520), relationship counts, and spot
   checks — 优必选 patent bindings (58 → 459 expected), g2 GT-6 presence
   with addresses, 普渡 positive control (17 relationship-table candidates
   may differ on run14; the B1 direct scan supersedes it as long as
   bindings exist).
5. **Full re-baseline**: three-layer runner, all 25 turns against the
   scratch port. Hard gate: every turn that passed on s12f (9 PASS + g17-t1
   GREEN) still passes on run14 — a regression stops the switch. Record
   the new honest baseline; update gap-registry statuses that the data
   change closes (GAP-15 closes: serving == 47,071) or re-measures
   (GAP-13 rows, GAP-02/04 ceilings).
6. **Switch 18188**: point the command file at run14, restart
   `canonical-v2-backend.service`, re-run the 7-session replay gate (7/7 or
   documented jitter), keep the s12f pack + old command file for rollback.

**Setback 2026-09-10 (first scratch boot) and the reseal step.** C2.1a
landed (run14 bundle + 18189 command, worktree `9cfdabe`), but the first
scratch boot failed closed at `serving_pack_loader.py:672` ("serving pack
index result does not reproduce its recorded hash"). Root cause (agent
evidence in `.agents/runs/close-workbook-gaps/c2-scratch-boot-failure.md`,
independently re-verified in main context against the live-index
`build_receipt`): the run14 pack is **half-sealed** — its index files are
the 2026-09-08 run14 materialization (receipt built_at 2026-09-08T11:07:10Z,
51,029 pts / 47,071 docs) but the manifest still carries the p4
(2026-08-26) index-side bindings: `index_result_content_sha256`
(`738219cf…`), `index_policy_snapshot`, `index_rebuild_decisions`, and
suspected-stale `index_projection_request_sha256` /
`build_manifest.published_projections`. The data line never ran the
envelope pipeline for run14 (no run14 envelope exists anywhere), and the
repo's only sealer (`s12c/build_serving_pack.py`) seals **from an
envelope**, so there is no honest way to mint these bindings except
recomputing them from the artifacts. The loader is correct; the pack is
the defect.

**Repair (revised 2026-09-10, second iteration): seal with the OFFICIAL
envelope sealer.** The resealer was built (worktree `9a99ca2`,
`s12g/reseal_serving_pack.py`) and its first run exposed a deeper layer:
run14's `relationships.json` candidate section is an OLD-generation
container (single `projections` array + `inclusion_decisions`, 20 pydantic
errors vs the current typed-split contract), and four loader-required
sections are missing entirely (`candidate_projection_request_scalars`,
`index_projection_scalars`, `public_path_eligibility_requests/results` —
the latter data-level, one per entity: 32,941 pairs in the p4 pack).
Element-level transcode was verified mechanical (0/47,071 parse failures,
uniform release/as_of/version, sorted, no dups) — **but then the genuine
run14 build envelope was found**: `.worktrees/data-rebuild/.agents/runs/
rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-
envelope.json` (8.1G, mtime 2026-09-08 20:00 — one hour after the run14
index materialized; release `candidate-v2-20260819-r1`, run
`p4-build-20260819-v1`, receipt with all hash bindings, top-level
consumer_handoff). The data line DID run the full current-contract
pipeline for run14; the half-sealed pack was a hand-assembly that
bypassed the envelope sealer. So C2.1r is: run the official
`s12c/build_serving_pack.py` (serving-worktree copy, so loader semantics
== production) with `--envelope` (read-only, the run14 envelope above)
`--index-root /var/tmp/mirothinker-data-v2/index-v1`
`--pack-dir /var/tmp/mirothinker-data-v2/serving-pack-run14-sealed`
(fresh) `--expected-release-id candidate-v2-20260819-r1`
`--generator-run-id c2-seal-20260910-v1`. The sealer recomputes every
binding from envelope + index, dogfoods the pack through the real loader,
and refuses to ship unless the reconstructed authority equals the
envelope in every compared field — the strongest provenance available.
**Rejected**: ① the resealer/transcode path — synthesizing contract
sections (typed splits, 47,071 eligibility pairs) when the genuine
artifacts exist is inventing data; the resealer stays committed as
tooling but is not the C2 path. ② In-place hash patch of the half-sealed
pack — destroys evidence, repeats the Sep-9 partial surgery. ③ Loosening
the loader — never. After sealing, C2.1b–f run against the sealed pack
(the 18189 command's `--serving-pack` path is updated; nothing else
changes). Note the sealed relationships.json will be larger than 2.9G
(it gains the eligibility sections) — the A/B boot measurement gate
applies as designed.

**Third blocker and the contract port (task C2.1p, inserted before the
seal).** The official sealer's envelope validation failed closed on
exactly one pydantic error: the run14 envelope's
`index_projection_request.supplementary_field_values` — a field the data
line added 2026-09-07 (`a226bd8`, multi-value enrichment: non-selected
assertion values per canonical identity, baked into embedded/lookup
content to widen the vector and lexical search surfaces — one of the
run14 improvements C2 exists to bring online). The serving line has zero
knowledge of it, and the gap is structural: sealer hashes the full
request dump but writes only 6 named scalars; the loader reconstructs
the request from scalars — so all THREE sites must learn the field or
hash reproduction fails at boot. **Chosen fix (option a): port the field
to the serving line, verbatim**, three small edits —
① model (`index_projection.py`, after `prior_accepted_snapshot`):
`supplementary_field_values: dict[str, dict[str, list[str]]] = {}`
verbatim from data-rebuild `index_projection.py:277`; ② sealer
(`s12c/build_serving_pack.py`): conditional passthrough into
`index_projection_scalars` (only when the envelope dump carries the
field); ③ loader (`serving_pack_loader.py` request reconstruction):
pass the field only when present in scalars, and dump the request hash
with `exclude_unset=True`. The ③ semantics are the rollback-compat
lock: for s12f scalars (no field) the reconstructed dump is
byte-identical to the pre-port canonical form (s12f pack keeps booting
with the same new code — rollback path intact); for run14 scalars the
field is included and reproduces the envelope hash. All other
reconstruction fields are passed explicitly, so `exclude_unset` changes
nothing else. Rejected: (b) strip the field from the envelope — the
request would declare no supplementary values while the index contains
them (provenance lie); (c) re-run the whole run14 pipeline with
serving-contract code — heaviest, and throws away the multi-value
enrichment. No serving query-code change is needed: the enrichment is
baked into run14's index content at build time; serving only needs
contract-level understanding (parse + hash-bind). Tests: a contract
test pinning both sides (s12f-style scalars without the field →
canonical dump unchanged; run14-style with the field → passthrough and
hash reproduction), the B1 focused suite, and the hermetic pack tests.

**Sealer replay-level convergence (task C2.1q, inserted 2026-09-10).**
C2.1p landed clean (worktree `3734f30`: 2 pin tests, hermetic pack 21,
B1 focused 96/26, fast_boot 14 — all identical to the pre-port baseline;
reconstruction trees verified 10/10, 6/6, 13/13, 13/13 explicit so
`exclude_unset` is provably inert for s12f). The re-run seal passed the
field validation but refused deeper:
`consumer handoff index request is cross-wired from its release bundle`
— the envelope validator (`knowledge_build_isolated.py:1824-1835`)
embeds a full deterministic index replay
(`create_ephemeral_index_projection_builder().build(request)`) and
demands field-equal reproduction of `release_bundle.index_result`. The
serving line's build path lacks the data line's 47 lines of enrichment
consumption (4 hunks in the same `index_projection.py`: `build()` call
sites, `_public_embedded_content` supplementary/team_description/
`_quality_tier`, `_vector_points`/`_lookup_documents` merge) — the code
that shaped run14's index content. The envelope is self-consistent (the
data line's validator is verbatim-identical, no bypass; separately, the
data line carries a private `SERVING_PACK_SKIP_HASH_VERIFY=1` hash
backdoor the serving line correctly lacks — that backdoor is how the
half-sealed pack ever booted). So: C2.1p's "contract-level suffices"
holds for the pack loader (thin serve never replays), but the OFFICIAL
sealer requires build-level parity. **Chosen fix (option a): port the
remaining 4 hunks verbatim — two-line `index_projection.py` reaches
byte-identical zero drift** (dependencies verified self-contained:
`domain_projection_models.py` has no two-line diff; side benefit:
`knowledge_read_isolated.py:818/1866` full-validation replays become
bit-consistent too). Rejected: (b) seal with data-line code — their
sealer lacks C2.1p's scalars passthrough, the pack would still fail the
serving loader; (c) any validator bypass — forbidden. Same regression
gate as C2.1p, then the seal re-runs.

**Read-side half of the enrichment (task C2.1s, inserted 2026-09-10 —
blocker ④).** After C2.1q, the official sealed pack passed
`open_serving_pack_authority` IN FULL on the first boot attempt — the
authority chain (manifest, marker, per-file hashes, request/result
reproductions) is now proven in a live boot context (this also supplies
the dogfood phase the seal log did not echo). The boot then failed in
the knowledge-read composition: `_validated_public_projection` strictly
validates each lookup document's embedded projection and 903 public
docs carry a baked `_supplementary` key (`dict[str, list[str]]`; company
899/7,089, professor 4/3,958, paper/patent 0) — the READ half of the
multi-value enrichment. The data line's same function opens with a
14-line strip block (`knowledge_read_isolated.py:7954-7967`: copy the
document, drop `_supplementary`/`_quality_tier`, then validate — comment:
"for wider lexical search; strip before validation (extra=forbid)";
lineage and round-trip checks still run on the stripped copy, validation
is not weakened). C2.1q's "one file = zero drift" assumption was
therefore incomplete: the enrichment spans build (C2.1p/q) AND read
(C2.1s). Chosen: port the 14 lines verbatim + a pin test (constructed
lookup document carrying `_supplementary` → RED before, GREEN after).
Rejected: (B) relaxing model extra — weakens validation and fails the
round-trip check; (C) rebuilding run14 without `_supplementary` —
discards the enrichment, disproportionate. Companion finding: the FULL
two-line drift inventory of `knowledge_read_isolated.py` (16 hunks/338
lines) is now classified in `.agents/runs/close-workbook-gaps/
c2-boot-blocked-supplementary.md`; only the strip block is ported in
C2.1s. Two named follow-ups, NOT silently ported: ① hunks 9–11 (vector
trace tolerance: data line `rel_tol=1e-6`+warn+return vs serving
`1e-12`+raise) — a query-time fail-closed risk; if the C2.1d baseline
trips it, STOP and report, fix as its own verified port; ② hunks 13–16
(exact-phrase `[lane=exact]` strip, identifier fallback, G6 long-title
containment — genuine retrieval-behavior improvements) — a dedicated
two-line convergence slice queued after B3+B2, with its own behavior
evidence (the 22-turn gate baseline was measured on current serving
code; behavior ports must not be smuggled into a boot-fix slice).

**C2.1d methodology amendment (2026-09-10 evening).** The first
differential-free run of the 22-round gate aborted at turn 6: four
in-gate turns FAILed, and the failure signature was an EMPTY ANSWER
caused by the serving guard `_filter_private_markers` raising on a
repeated protocol marker (`<|canonical_v2_selection_v1|>`) inside the
LLM prose (prose fully streamed, then the turn aborts without the answer
event). Decisive control: the SAME queries against the LIVE 18188 (s12f
pack, untouched since 9/9) fail identically today (g1-t1 3/3 on scratch
+ 1/1 on live; journalctl shows the same production error) — the LLM
backend (deepseekv4flash) drifted after the 9/9 baseline, and the
archived baseline is no longer reproducible in today's environment.
Gate amendment: the effective acceptance for C2 is a SAME-DAY DOUBLE
RUN — 25 rounds on 18188 (s12f) and 25 on 18189 (run14); pass = run14
not worse than same-day s12f per turn (any turn where s12f passes and
run14 fails must be attributed; turns 2-1/2-3 普渡 content differences
are attributed by this differential). This isolates the pack swap from
environment drift. Companion finding for the queue: the guard hard-fail
producing empty answers is exactly GAP-09 / slice B5 (守卫命中降级模板
渲染，不空答), now observed live in production traffic — B5 priority
recommendation: run it before B3+B2 (pending user nod) so subsequent
baselines measure retrieval, not guard noise.

**Rejected alternatives (overall approach).** ① Repairing the assembly
contract so run14 passes `_validate_result_graph` — the R1 swamp,
unchanged. ② Building a new minimal serve entry — the pack-mode fast path
already IS the thin-load entry; new code would duplicate it. ③ In-place
data surgery on s12f — run14 is the reconciled superset; piecemeal
backfill re-creates the reconciliation problem C2 solves once.

**RED → GREEN.** RED: GAP-15 assertion (serving doc count == 47,071) fails
today (5,659). GREEN: serving boots run14, reconciliation report lands,
25-turn re-baseline shows no regression on previously-green turns, replay
7/7 after the switch, gap-registry re-baselined.

## B2+B3 — combined "enumeration & narrowing" full design (2026-09-11, starts after B5)

**Live evidence (run14 line, 2026-09-10 differential).** g2-t1 misses
开普勒/九号; g2-t2 answers "上述十家企业…总部都在深圳" while only 3/6 GT
pool entities appear; g5-t2 answers "上述四家企业均为深圳企业" (2/12 key
points). All three fixtures have their GT entities IN the pack (C2
reconciliation: g2 GT-6 present with addresses 3/6; g5 GT-11 8 in pack) —
so the live losses are pipeline-side, not data-side.

**Mechanism map (line-verified 2026-09-11, `.agents` explore report).**
- Enumeration is detected THREE times independently (planning
  `serving:616`+markers `serving:2766-2778`; chat `_enumeration_context`
  `chat:561-571`; answer selector `serving:5700-5718`) with no unified
  classifier. `_ENUMERATION_CANDIDATE_WINDOW=48` expands the planner
  window; live bundle max_candidates=8/max_web=8.
- **`required_member_ids` is NEVER set by the chat layer** →
  `read:4285-4295` required-member outcomes are dead code → representative
  mode only; per-member completeness outcomes never produced.
- Answer entities come from the LLM's selection over `displayed_entities`
  (`serving:4954-4966`, prompt `serving:5131-5138`) and
  `_commit_prose_scope` (`answer:2488-2559`) then **narrows the carried
  displayed set to the LLM-selected entities** — next turn sees the
  truncated set.
- Two canonical-only filters drop non-canonical displayed members:
  `_displayed_ids` (`chat:2047`) and `_next_referent_history` (`chat:714`).
- Narrowing per-member evaluation exists but is partial: deterministic
  geography constraints (`read:6440-6553`, incl. name heuristic
  `:6535-6546`) apply to local candidates; web probes
  (`serving:2919-2968`) run only for ≤6 members with
  `company:`/`company-`/`web-handle:` prefixes, probing `"{name} 总部"`
  (`serving:3965`) and binding geography unconditionally on hit
  (`serving:3846-3852`). Final per-member verdicts de-facto reste with the
  prose LLM (prompt rule `serving:5102-5103`).
- Coverage statements exist (deterministic `answer:1272-1290`; prose
  payload `serving:4999-5030`, prompt `serving:5144-5146`) but the
  representative-mode counts are semantically wrong: `displayed_ids/count`
  = retrieved = available (`read:6925-6933`), NOT what the answer actually
  showed.

**D0 diagnostic gate (RED artifact — no fix lands before it).** Replay
g2-t1 / g2-t2 / g5-t2 on the live run14 line and build a per-entity
drop-stage table: ① not retrieved (window/lane); ② retrieved but not in
displayed set (selection); ③ in displayed set but absent from answer
(prose selection); ④ in answer but substring-mismatch (naming/alias).
Method: endpoint queries (main context runs network) + turn artifacts;
target queries read from `run_testset.py`'s query table.

**Chosen fixes (final shape locked by D0; intent by stage).**
- **B2-a faithful carried manifest**: the committed session carries ALL
  displayed members as (kind, id, name) — canonical-only filtering stays
  ONLY where identity binding requires canonical ids (relationship
  binding, plan display set). Fixes the two filter sites.
- **B2-b per-member narrowing for the full carried set**: extend the
  existing probe path so every carried member gets a verdict (canonical
  local claim → name heuristic → web probe); if budget caps the probes,
  the answer must state the uncapped remainder honestly instead of
  claiming "均为深圳企业".
- **B2-c coverage statement** for narrowing: 共 N 家 / 确认 M / 排除 K /
  未决 J, rendered from actual per-member outcomes; fix the
  representative-mode count semantics so displayed counts reflect the
  displayed set, not the retrieved set.
- **B3-a enumeration completeness self-check before rendering**:
  reconcile the retrieved candidate set (claims/handles) against the
  answer's selected entities; on shortfall of strong local candidates,
  trigger ONE supplemental probe (existing `SupplementalBudget`) and/or
  set `required_member_ids` from the retrieved strong set so
  `read:4285-4295` per-member outcomes finally run; then honest wording.
  Hook: chat-layer `chat:1836-1868` (holds coverage + handles + displayed
  set + planner/reader) preferred over read-layer `read:8147-8172`
  (cannot see which key entities are missing without a pass-through).

### D0.5 evidence and the LOCKED phase-1 fix set (2026-09-11)

D0.5 (`.agents/runs/close-workbook-gaps/d0-probe/d05-findings.md`, gate
replay uses production functions against real captured provider bodies):
confirmed root causes — ① category queries have NO deterministic recall
path (exact=name equality, structured=displayed-id re-query + empty
short-circuit, lexical=whole-phrase substring; all scalar fields already
sit in `content_terms` via `_normalized_scalar_values`,
`knowledge_read_isolated.py:8147`, industry 91.9% / tech_tags 77.4% /
summaries 100% filled in the run14 pack); ② web→canonical binding is
structurally impossible on first-turn category queries (binding set
empty → `_matched_bound_entity` always None, `serving:2497`); ③
`_commit_prose_scope` commits ONLY `selected_handle_ids` — entities
mentioned in prose but unselected are evicted (深南电路 case,
`answer:2488-2559`); ④ the subject-consistency gate's `kept<floor`
backfill truncates to exactly 3, discarding ALL full-name member hits
(g5-t2: 9 B+ items cut; g2-t2 gate itself judged mostly correctly — the
real g2 loss was probe-path invisibility, below); ⑤ supplemental probe
results bypass the gate and lane counting (`_merged_results`) and their
probe→candidate death is unpersisted (普渡 HQ evidence in views 5–6).

**Locked phase-1 fixes (critical path only):**
- **F1 category recall** — deterministic category-term recall over
  `content_terms` for category queries ("做X的公司"): term extraction
  (strip stopwords/city/metadata; terms ≥2 chars), bounded matching in
  the lane layer, enumeration window applies. Offline-verifiable: count
  GT recall over the sealed pack for the g2/g5 query terms. Retrieval-
  critical: if the shape needs contract changes beyond
  matcher/planner level, STOP and return a micro-design.
- **F2 commit union** — `_commit_prose_scope` commits
  `selected ∪ (displayed entities whose names appear in the answer)` so
  mentioned members stay reachable next turn (kills the 深南电路
  eviction).
- **F3 gate backfill** — `kept<floor` keeps ALL full-name hits (T2/T3;
  the same signal the kept≥3 branch trusts); only T4/T5 backfill is
  truncated to floor. Verify by re-running the D0.5 gate replay
  (g5-t2 expected 3→12). The anchor-qualifier/kept-count semantics
  change is NOT taken now (neutralized by F3 for the failing cases).

**Deferred (phase 2, trigger-based — per D0.5 evidence not on the
critical path):** B2-a carried-manifest fidelity (canonical-only filters
`chat:2047/:714` — canonical GT entities flow fine once F1/F2 land),
B2-b per-member verdict probes, B2-c coverage statement + count
semantics, F-bind web-name binding, probe-path visibility/qualification.
Revisit if multi-run acceptance shows residual shortfall.

**Acceptance (multi-run; single replay insufficient — carried sets vary
day to day):** g2-t1 entities 5/5; g2-t2 pool ≥5/6; g5-t2 ≥9/12
key_points (data ceiling noted: 8 in-pack + the Guangzhou exception —
all eight must hit); replay zero new signatures; differential
non-regression.

**Rejected.** ① Blanket window/lane enlargement — cost without precision.
② Prompt-only fixes — no retrieval reconciliation, incompleteness
persists. ③ Read-layer-only hook — cannot see the missing-key-entity
signal without new pass-through plumbing (larger blast radius than the
chat hook).

## B5 — guard-hit graceful degradation: redact-and-continue (full design, 2026-09-10)

**Problem (live, production).** The drifted LLM backend (deepseekv4flash)
sometimes echoes the prose protocol markers
(`<|canonical_v2_selection_v1|>` / `<|canonical_v2_answer_v1|>`) inside the
answer prose. `_ProseWireDecoder._filter_private_markers`
(`knowledge_serving_isolated.py:4296`) treats any full marker match in the
prose region as fatal: it raises `ValueError("LLM prose response contains a
private marker")` (:4311). In the STREAM path (`stream()`, :5387) that raise
happens after chunks were already published → the SSE turn aborts without
the answer/done events → user-visible EMPTY ANSWER (prose partially or fully
streamed, then error). Production evidence 2026-09-10: reproducible on the
untouched s12f line (journalctl + replay 9-failure set), environment-class,
and exactly the GAP-09 defect class (workbook baseline §9.2: 守卫命中降级，
不空答).

**Design.** A marker in the prose region is echo noise, not a safety leak —
the marker text must never reach the user, and redaction guarantees that as
strongly as aborting, without destroying the answer:

1. `_ProseWireDecoder._filter_private_markers`: on a complete marker match,
   drop the buffered candidate characters instead of raising, and record a
   redaction (count + which marker). The partial-candidate behavior at
   `finish` stays as-is.
2. Callers (`_parse_response` sync path :5236; `stream()` :5387): after
   decode, when any redaction happened, call
   `current_turn_trace().set_degradation("prose-private-marker-redacted")`
   (same `TurnTraceReporter` mechanism as `web-lane-unavailable` at :1249).
   The answer continues normally — no template fallback for this class; the
   deterministic fallback stays reserved for genuine synthesis failures.
3. Selection integrity: verify at implementation start (line-level) that the
   raise site is reachable only from prose-publishing states and that a
   legitimate selection header never routes through
   `_filter_private_markers` — redaction must be provably incapable of
   corrupting a valid header. Also verify: (a) no caller catches this
   ValueError for a fallback branch; (b) whether the flag should ride
   `ProseSynthesisResult` or only the trace reporter.

**Acceptance (RED→GREEN).** ① decoder unit: prose containing a full marker →
RED today (raises); GREEN: marker removed, surrounding text byte-intact,
redaction recorded; ② stream-path integration: injected-marker completion →
stream completes with the done event, no error event, trace carries the
degradation token; ③ regression: hermetic pack + B1 focused suites + fast_boot
unchanged; ④ evidence: same-day differential / replay re-run — marker-class
empty answers disappear from BOTH sides (fail open into complete answers).

**Rejected.** ① Keep aborting — it is the live GAP-09 defect (user-visible
empty answers). ② Template-fallback for this class — discards fully streamed
good prose; template rendering stays as the last-resort path for genuine
synthesis failure. ③ Prompt-side marker suppression alone — provider drift is
outside our control; the guard must be robust regardless.

## B4–B6, C1, C3–C5 — design stubs (filled at slice start)

- **B2**: narrowing = previous displayed-id set ∩ filter; the displayed-id
  manifest already exists from the Layer D work.
- **B3**: enumeration completeness self-check against the retrieval set
  before rendering; shortfall triggers one supplemental probe, then honest
  wording (not fabricated completeness).
- **B4**: citation floor enforced at render; web boilerplate filtered by a
  template blocklist at citation-assembly time.
- **B5**: full design above (redact-and-continue + trace token, 2026-09-10).
- **B6**: combine structured education/region/industry constraints; blocked
  on C1 field quality for `key_personnel.education_structured`.
- **C1**: field-quality contract thresholds — professor profile_summary
  boilerplate <10%, paper_summary placeholder 0%, title placeholder <5%,
  email placeholder 0%, aliases coverage ≥30% for companies with known
  aliases.
- **C2**: thin-load run14 (47,071 docs) into the serving pack format
  without the assembly contract; reconciliation report (counts per domain,
  relationship counts, spot checks).
- **C3/C4**: relationship backfills as data-line jobs; serving reads them
  through the same direct-scan pattern as B1.
- **C5**: delete the taxonomy dead path (curated vocabulary + dedicated
  fields) after a serving-wide reference sweep shows zero reads.
