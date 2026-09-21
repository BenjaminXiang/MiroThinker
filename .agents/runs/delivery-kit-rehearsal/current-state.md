# Delivery kit rehearsal — current state (facts this slice is built on)

Slice: ship the canonical-v2 serving stack as a delivery kit + prove the
target-machine procedure by rehearsing it on this host **without touching the
live service**. Agent-side evidence lives beside this file
(`verification.md`); the human plan is
`docs/plans/2026-09-21-customer-site-delivery-plan.md`.

All statements below were read from the code/artifacts on 2026-09-21 (this
session) unless marked otherwise.

## 1. The line being shipped

| Fact | Value |
|---|---|
| Live code root | `/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation` @ `36df47b8` (`codex/canonical-v2-s12a-ready`) |
| Service unit | `canonical-v2-backend` (systemd --user) → `deploy/start-canonical-v2.sh` → `exec env $(cat s12g/serve-18188-command.sh)` |
| Live pid / port | 519941 on `0.0.0.0:18188`, RSS ≈ 17.3 GB, uptime 12 h 59 m at recon time |
| Command file | `<live>/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serve-18188-command.sh`, 3462 bytes, 93 shell tokens (89 argv + 4 env assignments) |
| Extra service-unit env | `DATABASE_URL` (console PG; explicit drop-in), `CANONICAL_V2_LEXICAL_INDEX=0`, `CANONICAL_V2_TURN_DEBUG_DIR` — none of these are in the command file, and none are required by the serving path |

## 2. What the command file's 89 argv tokens actually do

`--serve --serve-existing --serving-pack <dir>` selects the pack path in
`complete_candidate_runner.py:1154`: the runner builds its handoff from the
pack authority and **never reads the build envelope, source manifest, decision
bundle or staging root**. Everything below was verified in
`apps/miroflow-agent/src/data_agents/canonical_v2/serving_pack_loader.py:705-930`
and `.../s12a/complete_candidate_runner.py:219-391, 989-1060, 1144-1175`.

| Argument | Serving-time role | Kind |
|---|---|---|
| `--serving-pack` | real: manifest + relationships + catalog + lookup + index marker, all hash-checked | dir |
| `--index-root` | real: marker read; **compared character-for-character** with pack manifest `index_root`, index marker `root`, serving bundle `index_root` | dir (frozen) |
| `--index-marker-sha256` | real: compared with pack manifest field and with the marker file's sha256 | frozen string |
| `--recorded-serving-bundle` (+`-sha256`) | real: read at boot; its `content_sha256`, `release_id`, `database_name`, `index_root`, `envelope_path` are all compared with CLI values | file |
| `--recorded-embedding-bundle` | real: `load_embeddings()` reads it; supplies the embedding base_url/model/dimension | file |
| `--envelope-output` | **never opened** in pack mode; its *string* must equal `<gate-root>/s12a/complete-candidate-build-envelope.json` and equal the bundle's `envelope_path`; its parent dir must exist | parentdir |
| `--accepted-backup-gate-root` | `<it>/s12a/` must exist (strings only) | dir (empty ok) |
| `--source-manifest`, `--candidate-staging-root`, `--recorded-decision-bundle` | parse-time only: must exist as *distinct* path strings, never opened | string |
| `--accepted-original-milvus-path` | compared with the pack manifest's `index_forbidden_milvus_paths[0]`; the file need not exist | frozen string |
| `--database-url`, `--expected-database` | `expected_database` must equal `miroflow_<candidate_release_id with - → _>`; the DSN is not dialled by the pack path | string |
| `--port` | the s12e wrapper monkeypatches the parsed port; `_parse_args` hard-rejects anything but 18188 unless patched (this is how a scratch port is possible) | — |
| `CANONICAL_V2_ACCESS_LOG_DB`, `CANONICAL_V2_CORRECTIONS_DB`, `CANONICAL_V2_MANUAL_RECALL_DIR` | env: ledgers; siblings (admin auth DB/key, chat gaps, jobs, uploads) resolve from the access-log DB's parent | dir/file |

State directory contract (`apps/admin-console/backend/services/admin_auth.py:31-45`,
`backend/storage/chat_gaps.py:30-70`): the admin credential store is
`<state>/admin-auth.sqlite3` + `<state>/admin-auth.key` (0600), seeded on first
boot with `admin-initial-password.txt`. When no path is configured the code
falls back to the hard-coded `DEFAULT_STATE_DIR = /var/tmp/mirothinker-canonical-v2-s12f`
in two modules — a missing directory therefore produces a service that boots
and answers `/chat` while the whole admin surface is silently absent.

Mount receipt: `open_serving_pack_authority` writes `<pack>.mount-receipt.json`
**into the pack's parent directory** on the first verified mount and reuses it
later (marker hash + file sizes + first/last-block fingerprints) instead of
re-hashing 1.7 GB of index artifacts on the user path. That is why the data
root must stay writable, and why the rehearsal snapshots the receipt.

## 3. Delivery artifacts (as they exist on this host)

| Artifact | Path | Size | Notes |
|---|---|---|---|
| Serving pack | `/var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound` | 4.4 GB | manifest 11 MB, relationships 3.47 GB, lookup 896 MB, institution catalog 381 B, index-target marker 316 B |
| Index root | `/var/tmp/mirothinker-data-v2/index-v3-v2` | 2.6 GB | lookup 896 MB, vector_matrix.npz 1.68 GB, marker 316 B; no milvus.db |
| State dir | `/var/tmp/mirothinker-canonical-v2-s12f` | — | admin auth DB+key+initial password, access logs, corrections, chat gaps, jobs, uploads, manual recall |
| Gate root (build tree) | `.worktrees/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform` | — | read-only for this slice; never modified |
| Serving / embedding bundle | `s12g/serving-bundle-run16.json` (1013 B), `s12c/qwen-embedding-bundle-v1.json` (410 B) | — | identical copies exist in both trees (verified by md5) |

## 4. Findings that shape the kit

1. **The shipped serving bundle hard-codes our envelope path.** Its
   `envelope_path` is
   `/home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-envelope.json`
   and `load_recorded_serving_inputs` compares it with `--envelope-output`
   (`knowledge_serving_isolated.py:6592`). Options for the site: (a) create that
   literal directory tree (`mkdir -p …/s12a`, the file itself is never opened),
   or (b) edit the bundle copy and pass the new declared hash, or (c) reseal —
   no tool exists for (c): `s12g/reseal_serving_pack.py` seals *packs*, not
   bundles.
2. **The bundle hash is declared, not recomputed.** `RecordedServingBundle`
   validates with `external_content_addressed=True`
   (`knowledge_serving_isolated.py:229-231`): the file's `content_sha256` is
   trusted as long as it is non-zero and equals the CLI value. Integrity of that
   file at the site therefore rests on `checksums.sha256` in the kit, not on the
   loader. The rehearsal exercised option (b) end-to-end.
3. **The chat profile is decided at boot by the managed settings file.**
   `config/managed/settings.json` sets `serving.chat_llm_profile =
   deepseekv4flash` (mapped to `CHAT_LLM_PROFILE` by
   `managed_config.py:80`, applied once in
   `serving_pack_loader.py:733-735`), which is why the live command file carries
   no `CHAT_LLM_PROFILE`. The endpoint/credential therefore follow
   `professor/llm_profiles.py` (deepseek → `https://api.deepseek.com` +
   `.deepseek_api_key`). `extraction_endpoints.embedding_base_url` is a
   read-only page field with **no runtime reader** — the frozen embedding
   address cannot be changed from the console today (F2 not landed).
4. **Key files are resolved by walking ancestors** of the source tree
   (`providers/local_api_key.py`, `professor/llm_profiles.py:23-42`): the live
   worktree therefore borrows `/home/longxiang/MiroThinker/.sglang_api_key` from
   the main checkout. A site code root with no such ancestor gets *no*
   credential — `preflight.sh` reports the key path it resolved, or warns.
5. **Rebuilding the venv is mandatory** (the `.venv` in the tree carries
   absolute editable pointers); `uv sync --frozen` from `uv.lock` is the
   documented path (`docs/plans/2026-09-21-customer-site-delivery-plan.md` §P1).

## 5. Kit shape produced from these facts

`deploy/build-delivery-kit.sh` writes `/var/tmp/mirothinker-delivery-kit/`:

- `code.tar` (449 MB, 4674 files) + `code.tar.sha256` — the live tree minus
  `.venv`, `node_modules`, `htmlcov`, `report.html`, `.tmp-*`, caches,
  `.worktrees`, top-level `logs/` and `var/`, `.coverage`, and the
  `complete-candidate-build-envelope*.json` blobs (3.4 GB of build evidence that
  the pack path never reads). `config/managed/*` **is** included (gitignored in
  the repo), as are the `s12a`/`s12e`/`s12g` entry points and bundles.
- `bundles/` — the two release bundles, copied only when their digest changes.
- `checksums.sha256` + `sizes.tsv` — data artifacts by frozen absolute path,
  bundles by kit-relative path; digest cache keyed on path+size+mtime so a
  re-run never re-reads 7 GB.
- `site-paths.txt` — 17 rows derived by parsing the command file, each with
  kind (`dir`/`file`/`parentdir`/`string`), flag, our reference value, a check
  and a one-line purpose; site-specific rows are marked `[现场改写]`.
- `kit-manifest.txt` — sizes + digests of the kit and the artifact inventory.

`deploy/preflight.sh` consumes the same command file on the target (not the
reference paths) and cross-checks the three-way frozen strings; it is
read-only.
