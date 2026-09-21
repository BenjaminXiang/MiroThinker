# Tasks: switch-embedding-model-to-qwen37-flash

Change id: `switch-embedding-model-to-qwen37-flash`.
Evidence dir: `.agents/runs/switch-embedding-model-to-qwen37-flash/` (this change)
and `.agents/runs/embedding-model-switch-v2/` (the lane's shared run dir:
runbook + precheck).
Owner branches: `docs/switch-embedding-model-change` (these artifacts) on top of
`v2/embedding-model-switch`.

Legend: `[x]` done in this preparation slice · `[ ]` open, ticked as the rebuild
proceeds. Every open task names its own verify step (`verify:`).

## T0 — change gate and evidence skeleton

- [x] T0.1 Write the verification contract
      (`.agents/runs/switch-embedding-model-to-qwen37-flash/verification-contract.md`):
      name the RED/GREEN artifacts — the identity refusals (unit, already green) as
      the deterministic layer, the recall gate as the scenario layer, the merge
      interactions as the new REDs.
- [x] T0.2 Register the change in `openspec/change-ledger.md`.
      verify: `openspec validate switch-embedding-model-to-qwen37-flash --strict` exits 0 with no errors.

## T1 — the candidate identity is frozen (inert, nothing selects it)

- [x] T1.1 Slice 1: DashScope-native client, batching adapter refactor, native
      bundle (`cdddcdfd…`, 1024), `_QWEN_FLASH_*` constants, fail-closed pair
      guards, 31 tests. Commits `d99ad726`, `11a29984`, `7ea495a8`.
- [x] T1.2 Slice 2: OpenAI-compatible candidate bundle (`45e45855…`),
      `_GatewayOpenAICompatibleEmbeddingAdapter`, accepted-authority table
      (per-bundle credential slot). Commit `17404d7a`.
      verify: `pytest tests/canonical_v2/test_embedding_model_switch_v2.py` green; the live bundle still loads to the local-slot adapter.
- [x] T1.3 Authenticated probe of the compatible route (2026-09-21):
      **HTTP 200, 1024 dims, 0.311 s, usage 20 prompt tokens** for
      `qwen3.7-text-embedding-flash` on
      `POST /compatible-mode/v1/embeddings`. The open question from slice 1 is
      answered: the model *is* served on the compatible route.
      verify: the probe script in `.agents/runs/embedding-model-switch-v2/precheck.sh` reproduces status 200 + dims 1024 (one call; never prints the key).

## T2 — the switch line (one merged tree for build and serving)

- [ ] T2.1 Create the switch worktree and merge, in this order:
      the serving line (`codex/canonical-v2-s12a-ready`, which contains
      `delivery-v1` + the s12g launcher), `v2/embedding-model-switch` (T1),
      `fix/embedding-lane-f1f2` (F1/F2), and the build line
      (`data/p4-serving-pack-rebuild`: runner + p4 manifest + gate root).
      verify: no conflict; `just lint` shows no new findings on the touched paths;
      the three suites below are green.
- [ ] T2.2 The build tree loads the candidate bundle:
      `load_content_addressed_embedding_adapter(<candidate bundle>)` returns an
      adapter with `model_id == qwen3.7-text-embedding-flash`, `dimension == 1024`,
      and the credential read from the gateway slot.
      verify: a one-off python check from the build tree; no HTTP call.
- [ ] T2.3 Record the serving tree's reader digest and the interpreter
      (`python 3.12.12` + `pydantic 2.12.5`) that the pack will be sealed with.
      verify: `reader_contract_digest()` printed by the sealer invocation matches
      the digest the cutover boot computes (mount receipt `verification: receipt`).
- [ ] T2.4 F1 interaction: a gateway transport failure (compatible route) and a
      native-client transport failure surface as builtin
      `TimeoutError`/`ConnectionError` to the lane's fail-open hook — not as an
      integrity error that kills the turn.
      verify: extend/adapt `tests/canonical_v2/test_embedding_lane_fail_open.py` +
      `test_embedding_transport_classification.py` to run against the two new
      adapters; both RED before the fix.
- [ ] T2.5 F2 interaction: `resolve_embedding_base_url` + the `base_url`-only
      exclusion apply to **both** new authorities, and `api_key_source` stays
      part of the frozen comparison (an operator must not be able to point a
      gateway bundle at the local slot).
      verify: `tests/canonical_v2/test_embedding_endpoint_resolution.py` extended
      with a case per new authority; the `api_key_source` mutation is refused.
- [ ] T2.6 Conditional, only if T4.1's batch probe fails: re-freeze the
      compatible-route bundle with `batch_size` ≤ the route's cap, recompute
      `content_sha256`, update `_QWEN_FLASH_OPENAI_COMPAT_EMBEDDING_BUNDLE_SHA256`.
      verify: bundle self-hash == constant; the probe passes at the new batch size.

## T3 — credential delivery and compliance

- [ ] T3.1 Deliver the gateway key as `CANONICAL_V2_EMBEDDING_API_KEY` for both the
      rebuild shell and the serving process (key file `0600` outside the repo, or a
      managed-secret entry); nothing in the repo carries the value.
      verify: precheck prints `SET` for the slot and `absent` for any literal key
      in the run artifacts (`grep` over `.agents/runs/**` finds no key material).
- [ ] T3.2 Rotate the credential(s) that have appeared in cleartext (plan §3 step 5);
      confirm the old value is not referenced by any command file.
      verify: operator record + the cutover command file names the slot, not a value.
- [ ] T3.3 Operator records the third-party gateway's data-retention/stability
      acceptance (plan §3 step 5) — product decision, not an engineering gate.

## T4 — pre-rebuild precheck (before the window opens)

- [ ] T4.1 `bash .agents/runs/embedding-model-switch-v2/precheck.sh` → all checks
      `OK` (rollback anchor hashes, fresh target paths, Postgres, interpreter,
      disk, endpoint reachability + the one authenticated call, the recall
      artifacts and the frozen bundle hashes).
- [ ] T4.2 Archive the run16 envelope so the runner's fixed envelope path is free:
      `mv complete-candidate-build-envelope.json complete-candidate-build-envelope-run16.json`
      (record: file-bytes sha256 `43735faa…`, content sha256 `a8440bdf…`, size
      `8,303,007,285`).
      verify: the precheck reports the archive present and the fixed path free.
- [ ] T4.3 Confirm the disposable Postgres container is up, the new target
      database is absent (or marker-owned), and the alembic head is the expected one.
      verify: `precheck.sh` D-cluster + `alembic heads`.

## T5 — rebuild (the long window; no checkpoint inside the embedding pass)

- [ ] T5.1 Prepare the fresh index marker for the new release; record the printed
      marker sha256.
      verify: the marker exists, the index root contains nothing else.
- [ ] T5.2 Create and mark the disposable target database; run alembic upgrade head.
      verify: the target DB's `shobj_description` marker is the disposable marker
      for this DB name.
- [ ] T5.3 Run the official runner with the candidate embedding bundle and
      `--model-version embedding=qwen3.7-text-embedding-flash`, `nohup` + `tee` +
      watchdog. Record: envelope content sha256, file sha256, wall clock, the
      embedding pass's TPM behaviour.
      verify: exit 0; `candidate_release_id` / `receipt_sha256` / `handoff_sha256`
      lines present in the log.
- [ ] T5.4 Verify the new vector matrix: `dimension=1024`,
      `point_count == 51026`, `embedding_model_id == qwen3.7-text-embedding-flash`,
      file ≈ 420 MB, every norm finite and non-zero. Compare the point count with
      the pre-switch matrix.
      verify: read the npz meta (`meta`, `matrix.shape`) — the same check T4.1
      runs against the pre-switch matrix, with the candidate values.
- [ ] T5.5 Convert the v1 (Milvus) index root to the v2 serving form; record the
      `conversion_report` (dest lookup bytes/sha, dest marker sha, removed Milvus
      bytes).
      verify: the destination root has no `milvus.db`, `index_point` has
      `point_count` rows, and the source root is unmodified.

## T6 — pack seal, identity and fast path

- [ ] T6.1 Seal the pack with the official v2 sealer **from the switch line**, into
      a fresh pack directory; record the phase seconds (`envelope_validate`,
      `dogfood_open`) and the manifest sha256.
      verify: exit 0; "pack destination must be fresh" not triggered; the sealer
      refuses a v1 index root (so the conversion in T5.5 is proven necessary).
- [ ] T6.2 Boot the new pack on a scratch instance (spare port, own state dirs) and
      confirm the mount receipt: `verification: receipt`, `mount_seconds` in the
      fast-path class (~120 s, not ~285 s), `index_marker_sha256` and
      `pack_manifest_sha256` matching T5/T6.1.
      verify: `.agents/runs/release-v11/fastpath-check.py` (copied into the switch
      line) with `--verify-reconstruction no`, plus the receipt file.
- [ ] T6.3 Generate the new serving bundle (`embedding_model_id =
      qwen3.7-text-embedding-flash`, new release/database/index/envelope/bundle id);
      record its `content_sha256`.
      verify: the generator re-validates in external content-addressed mode and the
      pack's manifest identity matches the new release.
- [ ] T6.4 Object inventory comparison against the pre-switch release (R6): object
      counts, source hashes and the relationship graph match; only the embedding
      identity, the vector matrix and the identity documents differ.
      verify: the envelope's counts vs run16's envelope/count ledger; any other
      difference ⇒ stop, do not accept.

## T7 — recall non-regression gate (blocking)

- [ ] T7.1 Boot the scratch instance from the new pack **with**
      `CANONICAL_V2_TURN_DEBUG_DIR` and `TURN_TRACE_DIR` set (a capture without
      them is a coverage REVIEW, not a pass).
- [ ] T7.2 Warm-up pass: run the harness once against the switched instance,
      discard the output (fills the web cache).
- [ ] T7.3 Judged pass: run the harness again → `after.json`.
- [ ] T7.4 `--diff baseline.json after.json` → record the verdict, the per-case
      table and `[web timeouts=n]`; cold-cache answer-layer deltas are annotated,
      not silently accepted.
- [ ] T7.5 `--diff control.json after.json` → record the verdict (the same question
      with the web-lane noise removed).
- [ ] T7.6 Every REVIEW row decided and recorded (case, layer, reason, decision,
      decider). Probes' GT losses and lane-halving rows are re-checked by hand.
- [ ] T7.7 **FAIL ⇒ no cutover** (stop and report). PASS (with recorded REVIEW
      decisions) ⇒ T8.

## T8 — cutover and rollback drill

- [ ] T8.1 Write the new serve-command file: new `--serving-pack`,
      `--index-root` + `--index-marker-sha256`, `--recorded-embedding-bundle`
      (candidate), `--recorded-serving-bundle` + sha, `--candidate-release-id`,
      `--run-id`, `--database-url`/`--expected-database`,
      `--model-version embedding=qwen3.7-text-embedding-flash`, and the gateway key
      supplied from the key file. Keep the previous file as the rollback copy.
      verify: the precheck's command-file lint (no literal secret; all paths exist).
- [ ] T8.2 Cutover: restart 18188 with the new command file; `/api/health` 200;
      one smoke query returns an answer whose citations are local (a vector-lane
      question, not a name query).
- [ ] T8.3 Rollback drill (in the window, on the switched service): restore the
      previous command file, restart, confirm the pre-switch release/marker/model
      are served, then re-cut to the new one.
      verify: the receipt/health output names the expected identities in both
      directions; the new pack and both index roots remain byte-identical.
- [ ] T8.4 Record the observed per-query embedding latency on the switched line
      (expect ≈0.28–0.31 s remote) and the index/pack sizes.

## T9 — close-out

- [ ] T9.1 Human-side log + index entry (the orchestrator owns `docs/plans/`).
- [ ] T9.2 `acceptance.md` statuses updated; ledger row → `tasks-complete-not-archived`.
- [ ] T9.3 Record new debt (e.g. the managed-secret slot for the gateway key, the
      batch-size cap if T2.6 fired) in `openspec/debt-register.md`.
