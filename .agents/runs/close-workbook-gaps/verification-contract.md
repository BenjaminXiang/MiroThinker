# Verification Contract

## Change

- Change ID: close-workbook-gaps
- OpenSpec path: `openspec/changes/close-workbook-gaps/`
- Run workspace: `.agents/runs/close-workbook-gaps/`

## Change Type

- `agentic_rag_or_chat_behavior`

## Superpowers Mode

- `eval_first_required` (workbook scenario eval is the primary gate; unit
  tests alone are not sufficient GREEN evidence per
  `openspec/specs/development-methodology/spec.md`)

## RED Artifact

- Type: scenario eval (hardened workbook runner, live endpoint)
- Path: `.agents/runs/testset-baseline-20260909/run_testset.py`
  (three-layer judgment from `harden-serving-test-harness`), run against
  `http://127.0.0.1:18188`
- Expected failing reason: B1 — g17-t1 yields 1 CN id sourced from web with
  citations_local=0 (baseline `results-ds-flash-systemd.json`); the
  deployment-line read path never scans field-level patent→applicant
  bindings.
- Behavior class covered: company→patent traversal for any company with
  id-bound patents (7,078 bindings in s12f lookup), not only 优必选.

## Oracle Strength

- Observable behavior checked: answer text patent-id count (regex
  `CN\d{9,}[A-Z]?`), citations_local ≥1, and absence of web-sourced patent
  lists when local bindings exist.
- Why stronger: the oracle binds to local-data provenance (citation type),
  not just string presence — a web-sourced CN-id list cannot pass.
- LLM/agentic contract: full SSE scenario run on the live endpoint; replay
  gate guards the 7 reference sessions.

## Diagnosis / Anti-Overfit Check

- Root-cause hypothesis: the G3-simple direct scan exists only in the data
  line (commit `790f4d1`); the deployment line reads only relationship
  tables (121 rows / 48 companies, 优必选 absent).
- Sibling patterns searched: professor→company and paper→professor
  traversals (same direct-scan pattern, planned as C3/C4); simple_serve's
  prototype scan (defective: pronoun over-truncation, citation ordering) —
  not ported.
- Why not one-example: the scan keys on company_id bindings generically;
  g17-t1 is the workbook witness, but any bound company exercises it.
- Anti-hardcode: assertion requires citations_local ≥1 — hardcoding CN ids
  into the answer template cannot produce local citations.

## Context / Dependency Surface

- Source OpenSpec requirement(s): this change's spec delta
  (`canonical-v2-chat` company→patent traversal).
- Legacy/source-of-truth docs: evidence doc §九 GAP-01; data-line commit
  `790f4d1`.
- Affected modules:
  `.worktrees/canonical-v2-s11-consolidation/.../canonical_v2/knowledge_read_isolated.py`
  (serving line for 18188).
- Existing tests/evals likely affected: replay gate (must stay 7/7);
  canonical_v2 read-path tests.
- Regression surface: company→patent answers, citation assembly.
- External dependencies: live 18188 service; pack lookup SQLite (read-only).

## Mock Policy

- Mocks used: none in the scenario eval.
- Behavior not mocked away: end-to-end retrieval + rendering + citations.
- Complementary real check: direct SQLite probe of the pack lookup
  confirming the returned CN ids are the bound ones (no fabrication).

## GREEN Criteria

- g17-t1 assertion GREEN on the live endpoint (≥3 CN ids,
  citations_local ≥1, ids verified against lookup bindings).
- Replay gate 7/7 after restart.
- canonical_v2 focused tests pass; no pre-existing-passing test broken.
- Gap registry entry GAP-01 flipped with evidence archived.

## Forbidden Shortcuts

- No hardcoded 优必选 patent lists.
- No web-sourced patent list presented as local.
- No weakening of the runner assertion to force GREEN.

## Verification Plan

- RED command:
  `python .agents/runs/testset-baseline-20260909/run_testset.py --base-url http://127.0.0.1:18188 --only 17`
- Focused GREEN command: same, after B1 port + service restart.
- Regression command:
  `cd apps/admin-console && uv run python scripts/replay_fix_round1.py`
- Real interaction / contract command: SQLite probe comparing returned CN
  ids to `lookup` bindings for the 优必选 company_id.
- OpenSpec validation command: `openspec validate close-workbook-gaps`

## Notes

- Assumptions: 18188 runs from
  `.worktrees/canonical-v2-s11-consolidation` (branch
  `codex/canonical-v2-s12a-ready`); restart via the established
  systemd/wrapper flow.
- Out of scope: assembly-contract repair; simple_serve fixes (prototype,
  retired line); professor→company and paper→professor (C3/C4).
- Rollback note: revert the B1 commit and restart 18188; data untouched.

## B5 — guard-hit graceful degradation (slice contract, 2026-09-11)

- RED artifact (offline): decoder/renderer tests in
  `tests/canonical_v2/test_knowledge_serving_isolated.py` — prose carrying a
  full `<|canonical_v2_selection_v1|>` / `<|canonical_v2_answer_v1|>` marker
  raises `ValueError` today (decoder unit + both renderer modes + the
  rewritten marker-in-answer test); SSE integration test in admin-console
  `test_canonical_v2_chat_http_adapter.py` ends in an `error` event with no
  `done` today. Live-production RED already archived (design.md §B5:
  journalctl + replay failure set, both lines, 2026-09-10).
- GREEN criteria: marker redacted, surrounding prose byte-intact, redaction
  recorded on the decoder; both decode sites set the
  `prose-private-marker-redacted` degradation token via
  `current_turn_trace()`; SSE turn completes with answer+done, no error
  event, journal carries the token; token added to the admin-console
  allowlist (Literal + `_VALID_DEGRADATION_TOKENS`).
- Regression gate: hermetic pack (`test_serving_pack_loader.py` 22 passed),
  B1 focused (`-k "relationship or patent"` 96 passed / 26 skipped),
  fast_boot + index_projection_embedded (14 passed), full
  `test_knowledge_serving_isolated.py`, turn-trace suites — all unchanged
  vs the C2.1s baseline.
- Live evidence (B5.4, main context): same-day differential / replay
  re-run — marker-class empty answers disappear on both sides.
- Out of scope: template fallback for this class (rejected — stays reserved
  for genuine synthesis failure); prompt-side marker suppression.

## C1 batch 0 — placeholder scrub + anchoring declaration (slice contract, 2026-09-11)

- RED artifact (offline): fixtures per matcher family against
  `_validated_public_projection` scrub —
  (a) English sentence prefix, (b) Chinese whole-value (incl. single `无`),
  (c) glued `未找到` run inside a longer value (erasure keeps the real
  terms; e.g. `VE1未找到未找到B,VE3未找到AS等系列GPS/北斗定位器`),
  (d) structural `^-+$`; negative controls: the long `未知词识别` paper
  summary must survive, short legit values must survive, and value-level
  hits on `name`-class fields must NOT be scrubbed value-only (record-level
  rejection is build-side). Fixtures RED today (projection keeps the
  placeholders and they enter `content_terms` /
  `_projection_category_term_buckets`).
- RED artifact (declaration): loading an unknown-schema
  `anchoring-declaration-v1.json` must fail closed; F1 scoring must consume
  multipliers/tiers from the file (equivalence test = same outcomes as the
  current hardcoded constants on seeded values).
- RED artifact (packaging gate): dry-run on the run14 index emits
  `placeholder-scan-report.json` with counts matching the read-only census
  (professor 12,872 / company 3,099 / glued 189 / whole-value 1,817) while
  writing zero bytes to index or pack and leaving hashes untouched.
- GREEN criteria: all above pass; focus suites
  (`test_knowledge_read_isolated.py`, `test_knowledge_serving_isolated.py`
  F1 assertions) unchanged; scrub applied AFTER validation (lineage
  assertions at :8144-8151 stay green).
- Live evidence (main context, post-deploy): differential on the GT
  queries — lexical/category recall unchanged; replay gate zero new
  signatures; 18188 restart only after the F4 acceptance window closes.
- Out of scope: packaging-side actual cleaning (new packs), vector-corpus
  scrub, record-level rejection, threshold recalibration (batch 2+);
  answer-side confidence wording (answer-quality slice); `ChatCitation`
  contract untouched.
- Rollback note: revert the batch-0 commit(s) and restart 18188; the
  sealed pack and index are read-only for this slice.


## B1 revision 4 — local-evidence citation cards are lane-independent (slice contract, 2026-09-13)

- Reported case (workbook g17-t2, live 18188,
  `.agents/runs/close-workbook-gaps/green-g17-r4-20260913.json`): turn 2
  「专利 CN117873146A 的详细信息是什么」 answers correctly from the sealed
  pack (title / applicant / technical summary all match the local patent
  projection) yet arrives with `citations=[]`, so the harness provenance
  layer fails on `local_citations:0<1` while the answer itself is right.
- Root cause (measured, not inferred): the turn's own audit dump
  (`turn-debug-oiK7m73eHfvM-01.json`) reports `citations: 1`,
  `admitted_claims.total: 1` (`exact_identifier`),
  `committed_handle_ids: [patent-c-0aef2768e7b7e94fb51440e5]`, evidence
  `by_lane: {exact: 1, lexical: 1}`, `by_source_nature: {local: 2}` — the
  loss happens after claim admission, in the public-citation filter
  `canonical_v2_chat.py::_public_citations`. That filter drops any citation
  whose evidence has no valid official public URL unless
  `evidence.lane == "relationship"`; patent exact-lane evidence carries
  `snippet = document.lookup_content` (`knowledge_read_isolated.py:9296`),
  and the patent lookup projection has no URL field at all
  (`_OFFICIAL_URL_FIELDS["patent"] = ("official_url", "source_url", "url")`
  — verified absent in the sealed pack's
  `lookup_document.document_json` for `patent-c-0aef2768e7b7e94fb51440e5`).
  The lane check was written when relationship evidence was the only
  URL-less local lane; it is now the defect.
- Fix: the URL-less local card rule follows the evidence's nature, not its
  lane — a local (non-`current_web`) admitted item that backs the answer
  surfaces a non-clickable card (hashed `local-source-<sha256[:16]>` id,
  label = public handle display name, `url=None`) even when no validated
  official public URL exists; web evidence keeps requiring a validated
  public official URL. Internal ids and locators stay out of the payload.
- RED artifact (offline): admin-console
  `tests/test_canonical_v2_chat_http_adapter.py` — a patent `exact`-lane
  local evidence with no URL-bearing snippet must appear in
  `_public_citations`; RED today (dropped), and the same test pins that a
  `current_web` item with a non-official locator stays dropped.
- RED artifact (live): `.agents/runs/close-workbook-gaps/green-g17-r4-20260913.json`
  g17-t2 `citations_local=0`, provenance fail.
- GREEN criteria: new + rewritten adapter tests pass; `_public_citations`
  never emits internal ids/locators; live g17 rerun reaches 2/2 turns with
  g17-t2 `citations_local ≥ 1`; replay gate unchanged; answer payload for
  web-only turns unchanged (no new cards without local evidence).
- Out of scope: fabricating official URLs for patents (no CNIPA locator is
  validated in the pack); web-evidence URL relaxation; `ChatCitation`
  contract change.
- Rollback: revert the `_public_citations` hunk and restart 18188; no data
  or pack writes are involved.
- GREEN evidence (2026-09-13, live, re-run this session after the round-4
  restart; worktree `codex/canonical-v2-s12a-ready`):
  - `green-g17-r5-20260913.json` — g17 2/2 turns; g17-t2 `citations_local=1`
    (g17-t1 unchanged at 32 local citations).
  - Raw public payload captured from the same endpoint
    (`g17t2-citation-payload-r5.json`): `{"type": "patent", "id":
    "local-source-9170b0c44a9b8470", "label": "一种机器人的落地控制方法、
    机器人及终端设备", "url": null}`. sha derivation re-computed:
    sha256("local:patent-c-0aef2768e7b7e94fb51440e5")[:16] =
    9170b0c44a9b8470. No internal id, locator, or release metadata in the
    payload.
  - Adapter suite `tests/test_canonical_v2_chat_http_adapter.py` 131 passed
    (18.12s, re-run after the trailing blank-line cleanup); `ruff check`
    clean on both touched files; `git diff --check` clean.
  - Replay gate (`replay-b1r4`): 5/7 sessions (3 failing turns). Failing signatures: G3-T2
    `neither clarification nor person-scoped answer` (deterministic P4
    defect registered in human log entry 34) and G7 #2/#3 `required
    substring missing: 优必选` (intermittent 缺龙头; #1 passed in-run).
    Attribution: identical signatures on the same worktree at 01:32–02:09
    today, i.e. before the rev-3 edit (`knowledge_answer.py` mtime 08:49)
    and the rev-4 edit (`canonical_v2_chat.py` mtime 09:04); both
    signatures also on the August record (verification-b1.md round 1).
    rev-4's diff is post-answer-text (public citation mapping) and cannot
    change answer-text assertions; the rev-3 code path's own session (G4
    `该公司的专利有哪些`) passes.

## C1.1-batch1a — Alias closure (build-side projection), 2026-09-13

Executed in the data-rebuild worktree (`data/p4-serving-pack-rebuild`) —
the worktree that actually built run14; the serving worktree only carries
the acceptance probes later.

### RED definitions

- `test_p4_company_field_merge.py`: alias union writes new aliases with a
  `p4fill:aliases` assertion; casefold dedupe; self-name/short-form
  exclusion; non-list fill ignored.
- `test_knowledge_build_p4_full_column.py`: `_p4_company_record` carries
  `project_name` in core_facts + selected; same-name/absent project_name
  emits nothing; an overlapping p4 row unions the alias into the retained
  company through `_p4_company_field_merge`.

Pre-fix RED: 3 failing (union missing, record alias missing, overlap merge
missing); the two absence-behavior tests pass as guardrails.

### GREEN criteria

- Focused: both files 20/20 green post-fix.
- Dry run over the full batch (`alias_dry_run.py`, real build functions +
  current pack aliases read-only): every p4 company lands as 6,504 alias
  emissions; pack coverage 342 → 6,846 (4.8% → 96.6%); collisions 9 forms
  (each 2 companies) ≤ serving `_ENTITY_LINK_MAX_FORM_FANOUT = 4` → kept,
  reported; backfill identity side effect measured 0 records.
- Acceptance still owed (batch1b): rebuild → probes → replay gate.

### Scope notes

- Pre-existing lint: `F402` (`for field in` shadows import) at HEAD —
  not introduced; left alone.
- Env-class red encountered while running a wider slice
  (`test_real_boundary_rejects_nonfresh_database_before_source_read
  [company.current_projection]`): DB migration revision mismatch message,
  orthogonal to this change (fails before any source read).
