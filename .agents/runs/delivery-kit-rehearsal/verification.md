# Delivery kit rehearsal — verification evidence

Rehearsal date: 2026-09-21 (this session). This is the dress rehearsal for
`docs/plans/2026-09-21-customer-site-delivery-plan.md` §P0-4: ship the kit,
rebuild the venv somewhere else, rewrite the command file for that root, boot on
a scratch port with a scratch state directory, then probe.

Scope boundary: **the live service was never touched** — pid 519941 and the
`canonical-v2-backend` user unit kept running on 18188 throughout, and no
command in this rehearsal targeted 18188.

## 0. What was under test

| Item | Value |
|---|---|
| Kit | `/var/tmp/mirothinker-delivery-kit/` built by `deploy/build-delivery-kit.sh` |
| code.tar | 449 MB, 4677 entries; the digest of the delivered kit is recorded in the kit's own `kit-manifest.txt` (the builder re-mints `code.tar` whenever the tree changes, so quoting a digest here would go stale by construction) |
| Scratch site | `/var/tmp/mirothinker-delivery-rehearsal/site` (code.tar extracted there) |
| Scratch state | `/var/tmp/mirothinker-delivery-rehearsal/state` (fresh, empty) |
| Scratch gate root | `/var/tmp/mirothinker-delivery-rehearsal/gate` (with an empty `s12a/`) |
| Scratch port | 18299 |
| Data | the real pack + index root, read-only, in place (`/var/tmp/mirothinker-data-v2/...`) |
| Bundles | kit `bundles/` copies, with the serving bundle's `envelope_path` rewritten to the scratch gate root |

## 1. Timeline (raw numbers)

| Phase | Command | Wall clock | Notes |
|---|---|---|---|
| Kit build | `bash deploy/build-delivery-kit.sh` | 56 s first run, 15 s re-run | re-run reused the digest cache and skipped both bundles (unchanged) |
| Extract | `tar -C site -xf code.tar` | 0.46 s | 4674 files, 438 MB on disk |
| Rewrite command file | python token rewrite + bundle re-declare | < 1 s | only the frozen milvus path string is still from our trees |
| `uv sync --frozen` | in the scratch site | **1.30 s** (warm uv cache) | 247 packages from the local uv cache |
| `uv sync --frozen` | second tree, `UV_CACHE_DIR` forced empty | **7.85 s** | 247 packages, 1.6 GB into the fresh cache, hardlink-mode venv |
| Boot | `nohup bash serve-18299.sh` → `/chat` 200 | **291.0 s** | matches the documented 291 s; mount receipt was reused (`verification: "receipt"`) |
| Smoke question | `probe_question.py ... "优必选科技有哪些专利"` | TTFT **1.64 s**, total **30.51 s** | `answer_style=llm_synthesized`, 12 citations, all `local-source-*` (patents) |
| Admin surface | login + `/api/auth/me` + `/admin` | 200 / 200 / 200 | password read from the file into a pipe, never printed; `admin-auth.key` appeared right after this login |
| Replay gate | `cd apps/admin-console && uv run python scripts/replay_fix_round1.py --base-url http://127.0.0.1:18299 --out-dir /tmp/delivery-rehearsal` | **4 m 59 s**, 19 turns, avg 15.7 s/turn | **RESULT: ALL PASS** (G1–G7 all PASS, 0 failures) |
| preflight (running) | `bash deploy/preflight.sh --repo <site> --kit-dir <kit> ...` | ~90 s | 1 FAIL (port 18299 held by the instance under test), 3 WARN |
| preflight (stopped) | same, after stopping the scratch service | ~90 s | **exit 0, 53 PASS, 0 FAIL, 3 WARN, RESULT: READY** |
| preflight `--fast --no-network` | size-only + no probes | ~5 s | exit 0 |

Resource readings of the scratch process (the real serving pid, not the `uv`
wrapper):

| Moment | RSS |
|---|---|
| 4 m 50 s after launch (boot just completed) | 18,080,204 kB = **17.24 GiB** |
| after 19 replay turns | 18,182,548 kB = **17.34 GiB** |
| live instance for comparison (uptime 13 h 22 m) | 18,168,792 kB = 17.33 GiB |

Disk: 988–1000 GB free throughout. State dir after the rehearsal: 496 KB
(access-logs, corrections, admin-auth.sqlite3 + key, admin-initial-password.txt).

## 2. Probes (exact results)

```
/chat      200
/main      200
/admin     302 (redirects to the login page — expected without a session)
/logs      302
/browse    302
/api/canonical-v2/admin/status 401 (unauthenticated — expected)
POST /api/auth/login           200 (admin)   → then /api/auth/me 200, /admin 200
POST /api/chat/stream          200, events: stage,plan_done,retrieval_done,stage,
                               answer_chunk×N,answer,done  (no `event: error`)
```

Answer sample (first 200 chars of the probe answer): a CN-numbered patent
enumeration for 优必选, source-grounded in `local-source-*` citations — i.e. the
answer came from the local knowledge base, not from the web lane.

## 3. preflight output (scratch site, service stopped)

Full outputs committed beside this file:
`rehearsal-preflight-stopped.txt` (service stopped → READY) and
`rehearsal-preflight-running.txt` (service up → the port FAIL below). The replay
gate's own report and log are committed as `rehearsal-replay-report.json` /
`rehearsal-replay.log`. Headline:

```
== summary ==
failures=0 warnings=3
RESULT: READY (warnings are non-blocking, review them anyway)
```

The three warnings are: rerank endpoint answered 401 (no rerank key configured —
the lane is fail-open), PostgreSQL not installed (`/seeds` `/upload` and three
maintenance jobs stay 503, `/chat` unaffected), and `admin-initial-password.txt`
still present (expected on a fresh instance, must be deleted after the first
password change).

Notable PASS lines (evidence for the checks that matter most):

```
[PASS] dir     --serving-pack -> /var/tmp/mirothinker-data-v2/serving-pack-run16-readerbound
[PASS] dir     --index-root -> /var/tmp/mirothinker-data-v2/index-v3-v2
[PASS] parentdir --envelope-output -> /var/tmp/mirothinker-delivery-rehearsal/gate/s12a
[PASS] pack parent dir is writable (mount receipt is written there): /var/tmp/mirothinker-data-v2
[PASS] state dir exists / is writable: /var/tmp/mirothinker-delivery-rehearsal/state
[PASS] admin credential store present (admin-auth.sqlite3 + admin-auth.key)
[PASS] no milvus.db inside the index root
[PASS] sha256 verified for 10 artifacts (checksums.sha256)
[PASS] cross-check: index_root agrees (pack manifest == --index-root)
[PASS] cross-check: index marker file sha256 == --index-marker-sha256
[PASS] cross-check: serving bundle envelope_path == --envelope-output
[PASS] cross-check: --envelope-output is the fixed evidence path (…/gate/s12a/complete-candidate-build-envelope.json)
[PASS] embedding endpoint reachable and dimension == 4096 (…, key source: key file …/site/.sglang_api_key (contents never printed))
[PASS] chat LLM endpoint reachable (http=200, profile=deepseekv4flash, https://api.deepseek.com)
```

The `--port 18299` run against the *running* scratch instance produced the
intended failure, with the holder named:

```
[FAIL] port 18299 is already in use: LISTEN …  users:(("python3",pid=3892629,fd=31)) …
[PASS] port 18188 is already serving (existing instance left untouched by this check)
```

## 4. Live instance protection (evidence)

1. No command in this rehearsal targeted 18188 except `curl /chat` (read-only).
2. `*.mount-receipt.json` was snapshotted before boot
   (`logs/receipt-pre-boot.sha256`, `receipt-before.json`). The scratch boot
   **did rewrite it** — a boot writes the receipt unconditionally
   (`serving_pack_loader.py:1150`) — with only `generated_at` and `mount_seconds`
   different; every binding field stayed identical. It was restored byte-for-byte
   (`sha256sum -c` → OK, original mtime preserved) after the rehearsal.
3. Live checks after the rehearsal: `curl http://127.0.0.1:18188/chat` → 200;
   pid 519941 still listening with RSS 18,168,792 kB and 13 h 22 m uptime.
4. The scratch instance used a different port, a different state directory, a
   different code root; the only shared inputs were the pack and the index root.

## 5. Traps this rehearsal confirmed (site engineer's list)

1. **The shipped serving bundle pins our envelope path.** `envelope_path` inside
   `serving-bundle-run16.json` must equal `--envelope-output` character-for-
   character or the boot fails closed with
   `ValueError: serving bundle envelope differs`. Three ways out: recreate that
   literal directory tree on the site (the file is never opened in pack mode),
   edit the bundle copy and pass the new declared hash (what this rehearsal did),
   or re-seal at build time (no tool exists today for bundles).
2. **Editing the bundle weakens its integrity proof.** The loader validates the
   bundle with `external_content_addressed=True`
   (`knowledge_serving_isolated.py:229`), so a hand-edited `content_sha256` is
   accepted as long as the CLI passes the same value. The kit's
   `checksums.sha256` is what protects those bytes — a site-side edit must
   refresh that line, otherwise `preflight` fails on the bundle.
3. **`--envelope-output` must be `<gate-root>/s12a/complete-candidate-build-envelope.json`.**
   The parent (`<gate-root>/s12a/`) must exist; an empty directory is enough.
   Creating this is easy to forget because the flag is never read at runtime.
4. **Port is not a free parameter.** `_parse_args` rejects anything but 18188;
   only the `s12e` wrapper's monkeypatch makes another port possible. A site that
   needs a different port must keep using that wrapper (or edit the runner).
5. **The chat profile comes from `config/managed/settings.json`, not the command
   file.** The shipped `settings.json` says `serving.chat_llm_profile =
   deepseekv4flash`; that decision is what makes the LLM probe go to
   `api.deepseek.com` with `.deepseek_api_key`. A site that changes the profile on
   the console changes the endpoint *and* the credential file name.
6. **Key files are found by walking ancestors of the code root.** Shipping the
   code to a root without `.sglang_api_key`/`.deepseek_api_key` beside it (or
   above it) leaves the embedding lane and the LLM keyless — the service still
   boots and answers, degraded. `preflight` prints which key file it resolved.
7. **`uv run` inside `apps/admin-console` creates a second venv.** The root
   `uv sync` builds the serving venv; running the replay gate from
   `apps/admin-console` builds that app's own venv (216 packages here). Budget
   for both, or run the gate with the root venv's python.
8. **Every boot rewrites the mount receipt in the pack's parent directory.** That
   directory must stay writable for the whole service life, and a backup product
   that "protects" the receipt file is pointless (it is regenerated).
9. **The first boot seeds the admin store but not the signing key.** The key
   appears at the first login (`admin_session.py:load_signing_key`); the
   rehearsal's own preflight rule had to be softened for this (fixed in
   `9d29d375`).
10. **A pydantic warning storm dominates the service log.** The scratch log
    accumulated 47,073 `PydanticSerializationUnexpectedValue` lines in ~8 minutes
    of light traffic (plus normal access lines). Pre-existing, unrelated to this
    slice, but it inflates log volume and looks alarming to a site engineer.

## 6. Decisions taken by the agent (reviewer checkpoints)

| Decision | Rationale |
|---|---|
| The kit does not copy the ~7 GB data; it ships `checksums.sha256` + `site-paths.txt` and the data travels as its own shipment | matches the delivery plan's "three shipments"; copying would need 7 GB of scratch disk per kit build |
| `code.tar` excludes `complete-candidate-build-envelope*.json` (3.4 GB), `logs/`, `var/`, `.venv`, `node_modules`, coverage output | none of it is read in pack mode; the artifacts stay in the repo, only the delivery copy drops them |
| `site-paths.txt` carries five columns (`KIND FLAG reference CHECK purpose`) and `preflight` reads values from the *target's* command file | a checklist with our absolute paths is unusable on a machine with a different root |
| The rehearsal edited the bundle copy instead of recreating our path tree | exercises the harder of the two site-side options and keeps the kit pristine; the other option is documented in §5.1 |
| The scratch state dir was left in place, the scratch site and the cold-cache tree were left for inspection | they are evidence; nothing under `/var/tmp/mirothinker-delivery-rehearsal/` is on the delivery path |
| The mount receipt was restored byte-for-byte rather than left rewritten | keeps "the live instance is untouched" literally true |

## 7. Not proven by this rehearsal

See the honesty list in the handoff: the rehearsal runs on our host, with our
network, our key files, our data root path, and a warm page cache; a fresh
customer machine will differ in OS, disk speed, network path, and the absence of
the frozen absolute paths (`/home/longxiang/...` for the forbidden Milvus path
and our gate tree).

## 8. Interpreter contract (follow-up, 2026-09-21)

### 8.1 The mechanism, and why the patch is a contract

`serving_pack_loader.reader_contract_digest()` hashes, in order:

```
"python=(3, 12, 12)\n"          # sys.version_info[:3] — patch version included
"pydantic=2.12.5\n"
for every *.py in the canonical_v2 package: path.name + file bytes
```

The pack manifest carries the digest of the reader that sealed it
(`reader_contract_sha256 = ebc22047cc9bef912201da5292809935c619705a2b8d8eb718cfec081b0da362`
for run16; the manifest has no python version string anywhere, only this digest).
`_reader_contract_matches()` decides between "the reconstruction is a replay"
and "run it": on a mismatch the boot **still succeeds** and silently pays the
reconstruction (~190 s measured elsewhere: 466 s vs 276 s). Verified by reading
`serving_pack_loader.py:213-309, 814`; the local digest was reproduced
independently in both the live tree and the extracted kit tree and matched the
manifest byte-for-byte (1.3 s per computation).

### 8.2 What the pin is (single place)

`.python-version` at the tree root, content `3.12.12`, written by
`uv python pin 3.12.12`. Chosen because it is the file **uv already reads** to
decide which interpreter `uv sync` / `uv run` uses — the command file runs
`uv run python …`, so this is the mechanism that actually controls the boot
interpreter. Evidence that it controls it, with two real interpreters:

```
pin=3.12.12 -> /home/longxiang/.local/share/uv/python/cpython-3.12.12-linux-x86_64-gnu/bin/python3.12
pin=3.11.14 -> warning: … resolved to Python 3.11.14, which is incompatible with the
               project's Python requirement: `==3.12.*` …
               /home/longxiang/.local/share/uv/python/cpython-3.11.14-linux-x86_64-gnu/bin/python3.11
```

`.python-version` was gitignored (`.gitignore:232`, matching the generic
pyenv/pipenv defaults); a negation `!/.python-version` with a comment now keeps
it committable so `code.tar` ships it, and `site-paths.txt` lists it as
`@python-pin` so the site checklist carries it too. The version number appears in
exactly one file in the tree; `preflight.sh` contains no version literal.

### 8.3 preflight behaviour (raw output)

Section printed by `deploy/preflight.sh` as `== interpreter contract ==`.

**Match** (scratch site, venv 3.12.12, exit 0):
`logs/preflight-interp-match.txt`, also committed as
`rehearsal-preflight-interp-match.txt`:

```
[PASS] interpreter pin (.python-version): 3.12.12
[PASS] boot interpreter matches the pin: CPython 3.12.12 (project venv — what 'uv run python' uses in this tree)
[PASS] reader-contract digest matches the pack (ebc22047cc9bef91…): this boot takes the fast path, no reconstruction replay
```

plus the checklist row `[PASS] file @python-pin -> …/site/.python-version (8 bytes)`.

**Patch mismatch** — a *real* interpreter, not an injected string: CPython
3.12.11, installed with `uv python install 3.12.11`, pointed at via the new
`--python` test flag (exit 1):
`logs/preflight-interp-mismatch.txt` / `rehearsal-preflight-interp-mismatch.txt`:

```
[PASS] interpreter pin (.python-version): 3.12.12
[FAIL] boot interpreter is CPython 3.12.11 but the pack was sealed with CPython 3.12.12 (--python override (test only): /home/longxiang/.local/share/uv/python/cpython-3.12.11-linux-x86_64-gnu/bin/python3.12) — the boot will not fail, it will silently replay the reconstruction: ≈190 s added to EVERY boot (measured 466 s vs 276 s on the same machine and data root). Fix: uv python pin 3.12.12 && uv sync --frozen (uv downloads the matching patch if it is missing), then re-run preflight
[SKIP] reader-contract digest: not computed while the interpreter differs from the pin
```

The `[SKIP]` is deliberate: with the wrong interpreter the digest is expected to
differ, and the version line already says why.

**Digest drift with the correct interpreter** — same site, one comment appended
to `canonical_v2/__init__.py`, then reverted (exit 1):
`logs/preflight-digest-drift.txt` / `rehearsal-preflight-digest-drift.txt`:

```
[PASS] boot interpreter matches the pin: CPython 3.12.12 (project venv — what 'uv run python' uses in this tree)
[FAIL] reader-contract digest differs from the pack (local d19f8d4ec7133c9a… vs pack ebc22047cc9bef91…) — the boot will silently replay the reconstruction (≈190 s per boot). The digest covers the python patch, the pydantic version and every canonical_v2/*.py byte: check the interpreter pin first, then that nothing edited the serving code
```

The file was restored byte-identically (`326ac3e8…`, 210 bytes) and the section
went back to three PASS lines — the check is not sticky.

### 8.4 Real mismatched-interpreter boot on this machine

The scratch site's venv was rebuilt with CPython 3.12.11 (`uv sync --frozen`
after setting the site pin to 3.12.11) and the service was booted on 18299 with
the same pack, index root, state dir and command file (`mismatch-boot.sh`,
output committed as `rehearsal-mismatch-boot.log`):

| Interpreter | Boot to `/chat` 200 | RSS at ready | Reader digest vs pack |
|---|---|---|---|
| CPython **3.12.12** (the pin, §1) | **291.0 s** | 17.24 GiB | matches → fast path |
| CPython **3.12.11** (one patch off) | **426.0 s** | 17.26 GiB | differs → reconstruction replay |

So the penalty is real and silent on this host too: **+135 s per boot** (the
container measured +190 s; the absolute numbers differ by host, the direction
does not). No error line appears in the service log — the log prefix is
identical to a fast boot. The receipt was snapshotted and restored around this
boot, the venv was re-synced back to 3.12.12 afterwards, and `uv run --no-sync
python -V` in the site tree then reported 3.12.12 again (see
`rehearsal-python-pin-probe.txt`). The live instance on 18188 was not involved at
any point (`/chat` 200, same pid, uptime unbroken).
