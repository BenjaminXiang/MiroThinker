# Verification — alias passthrough and local foothold (complete)

Layered evidence. T7 (scratch E2E) recorded in ④; T8 (reseal + dual-line
cutover) recorded in ⑤.

## ① New tests written this slice (9, all green)

`apps/miroflow-agent/tests/canonical_v2/test_alias_foothold.py` — fixture
source: round-47 live turns (verbatim asks) + the read side's own
`_entity_name_forms` / `_entity_link_entry_indexes` (production language, no
hand-built vocabulary).

| cluster | locks |
|---|---|
| form coverage | both failing asks contain a generated form (国先中心 / 国际先进技术应用推进中心 via city-prefix strip) |
| negative controls ×4 | concept/general asks never link (世界上最美丽的女人是谁 / JEPA有哪些变体 / 介绍一下 / 深圳有哪些做机器人的公司) |
| foothold decision | without linker → False (pre-fix decision); with linker → True for both asks |
| kill switch | `CANONICAL_V2_ALIAS_FOOTHOLD=0` → False; lexical positives untouched |
| determinism | repeated calls stable |

## ② Pre-existing regression suites (green, one proven pre-existing red)

| suite | result |
|---|---|
| `test_llm_query_rewrite.py` (37) | 36 passed; `test_rewriter_timeout_falls_back_to_deterministic_view` tripped under full-suite load and **passes in isolation** (timing-sensitive, rerun) |
| `test_followup_domain_carryover.py` | passed |
| `test_serving_pack_loader.py` + `test_manual_recall_points.py` + `test_fast_boot.py` | 51 passed; `test_release_bound_vector_validator_exempts_manual_traces` fails on the baseline too（改动暂存后复跑同样失败 → 预存/环境性，Milvus mvccTs warning class，属既有红） |
| `s12a/test_complete_candidate_runner.py` | 7 passed |
| `test_alias_foothold.py` | 9 passed |

## ③ Replay / fault-injection (RAG/chat-level claim)

Ran three times: scratch 18299 (④), dev line 18188 after the pack cutover,
and the customer site 100.64.0.96 after its on-site reseal (⑤) — all three
`ALL PASS 7/7`. The recall-gate `--diff` belongs to the scratch run (④).

## Changed files

- `knowledge_serving_isolated.py` — foothold way (d) + kill switch +
  `_proposal_provider` / `load_recorded_serving_inputs` threading
- `serving_pack_loader.py` — `create_local_name_linker` (lazy, memoized)
- `managed_config.py` — `serving.alias_foothold` row
- `s12a/complete_candidate_runner.py` — `_compose_local_name_linker` +
  `_serve` wiring + serving-input wrapper kwarg
- tests: new `test_alias_foothold.py`; fakes updated in three suites +
  `s12a/test_complete_candidate_runner.py`

## ④ T7 live E2E — scratch instance (port 18299, fembed pack, new code)

Scratch = a detached copy of the live 18188 stack (same argv, port swapped,
state stores rebased to `/var/tmp/scratch-t7`). Live lines untouched. Boot
~8 min: the v1 pack's reader contract predates the new code, so the boot took
the full reconstruction path and **succeeded** — a reader-contract mismatch
costs time, it never refuses the boot.

### Acceptance matrix (fresh session per ask)

| ask | lanes | result |
|---|---|---|
| 国先中心（深圳）的详细信息 | exact 2 · vector 16 · web | official points；旧线同题 = web-only/0 条 → 「暂未找到」 |
| 国际先进技术应用推进中心（深圳）的详细信息 | exact 2 · vector 16 · web | official points + 河套揭牌 web 补充（旧线 web-only） |
| 国先中心的详细信息 | exact 2 · vector 16 · web | official points；随后给出 合肥/大湾区 消歧段（正确区分不同机构） |
| 国先中心（深圳）是什么公司（对照） | exact 2 · vector 16 · web | official points |
| 世界上最美丽的女人是谁（负控） | **web only** | 纯 web 回答，未拉本地清单——第 41 轮纪律完好 |
| 优必选有哪些专利（回归） | relationship 128 · web 75 | 12 条本地专利引用 + CN 号清单 |

### Timing (cold vs warm; same query live-vs-scratch, same hour)

| measurement | new code (scratch) | old code (live 18188) |
|---|---|---|
| 国先中心（深圳）的详细信息 | 120.9 s **first-ever ask (cold)** → **4.9 s warm** | 7.9 s（错答「暂未找到」） |
| 优必选有哪些专利 | 30.0 s（web 正常，75 候选） | 56.7 s（web 道 unavailable——已知 dev 线时段性抖动） |

Cold 拆分说明：首个提问付一次性进程预热（含惰性 linker 构建）；warm 稳态比旧线同题更快（4.9 vs 7.9），因为本地回答无需 web 取数。

### Replay gate

`replay_fix_round1.py --base-url http://127.0.0.1:18299` → **ALL PASS（7/7）**，
19 轮；单轮 1.0–33.6 s，全部在旧线包络内。

### Recall gate

`eval_recall_canonical_v2.py`（warmup pass 丢弃，判定 pass），随后双 diff
（protocol §3，exit 0 PASS / 1 FAIL / 2 REVIEW）：

| diff | verdict |
|---|---|
| vs `baseline.json` | **REVIEW — 0 fail 级、2 review 级**（q11t1 / q15t1，概念题措辞行；harness 自注 "wording, not an entity"；q15t1 带基线自身的 web-timeout 注记） |
| vs `control.json` | **REVIEW — 0 fail 级、1 review 级**（q11t1 同一概念措辞行；对照对同样翻转 → 属 run-to-run 噪声，非本片引入） |

逐案例 vs control：候选层命中 29→32（+3）、答案层 31→32（+1）、向量中位数
在共享切片上全部为 0 变化（all/testset/probes）、引用 local 228→223 / web
128→144（web 道比基线的 17 次超时状态更健康）。wall 489.8 s → 558.3 s。

**T7 判定：通过**——replay 7/7 ALL PASS、召回门 0 fail 级、验收矩阵 6/6、
负控与回归问法无退化。（REVIEW 行为概念措辞噪声，按噪声校准口径解读。）

## ⑤ T8 — reseal + dual-line cutover (dev 18188 + site 100.64.0.96)

### T8a reseal (local, manifest-only minimal)

- Tool `.agents/runs/alias-passthrough-and-foothold/reseal_manifest.py`
  (proven increment, migration-log round 14): hardlink-copies the four data
  entries (zero bytes copied) and rebinds exactly `generated_at`,
  `generator_run_id`, `reader_contract_sha256`; self-audits (samefile on every
  entry, drift == those three fields, written contract == running code's
  digest). The official sealer (s12c, ~42 min full re-proof) stays the fallback.
- Result: `/var/tmp/mirothinker-data-v2/serving-pack-fembed-v2-aliasfoothold`
  (manifest 11,116,293 B, 4 hardlinks, data file digests unchanged vs v1).
- Interpreter caveat (verified twice this slice): the digest binds python +
  pydantic + every `canonical_v2/*.py` byte. Root venv (pydantic 2.12.5) →
  `ebba1bce…`; site venv (3.12.14 / pydantic 2.13.4) → `ff5ed0fc…`. The site's
  manifest therefore has to be resealed **on the site, with the site
  interpreter**.
- Dogfood before touching the line: bypass instance on 18300 mounted the v2
  pack — full verification 409 s, receipt written, smoke answer carried the
  official points; that receipt is what lets the real cutover take the fast
  path.

### T8b dev line (18188, systemd)

- The line is a systemd **user** unit (`canonical-v2-backend.service`,
  `ExecStart=…/deploy/start-canonical-v2.sh` → the s12g command file), so the
  cutover edited the command file's pack path and `systemctl --user restart`ed
  it; rollback = restore the command file (backup kept next to it) + restart.
- Boot: mount **193.2 s** (`verification: "receipt"` fast path), Uvicorn ready
  16:39:02, `/chat` 200, zero integrity errors, recorded hashes reproduced
  verbatim (`relationship_request_sha256=b3746c26…`,
  `index_projection_request_sha256=bba1d16b…`).
- Acceptance matrix **6/6**: the three 国先 phrasings + the control phrasing
  answer with the official points (exact 2 · vector 16 · web); the negative
  control stays **web-only**; 优必选 patents = relationship 128 · web 68 →
  **12 local patent citations**.
- Replay gate **ALL PASS 7/7** (19 turns, 0 failures, 1.0–36.4 s per turn).
- Timing: 123.5 s cold (the lazy linker's first build) → 6.4–15.5 s warm.

### T8c customer site (100.64.0.96)

- Delta to the site was exactly the three modules (+ the runner); the rest of
  the site's `canonical_v2` package was byte-identical to the worktree.
- On-site reseal (**no service impact**): a hardlink farm of the live agent
  package with the three new modules overlaid served as `PYTHONPATH`, so the
  site interpreter sealed the site's own contract
  (`reader_contract_sha256 = ff5ed0fc…`, exactly three rebound fields, four
  hardlinks, zero bytes copied).
- Cutover (single window, ~13 min): back up four files → install the new code
  **fail-closed** (byte `cmp` per file, then the site interpreter recomputing
  the live tree's contract must equal the sealed value → MATCH) → point
  `run.sh` at the v2 pack → `systemctl restart`.
- Boot: first mount **391.2 s** (`verification: "full"`, receipt written);
  `/chat` `/main` `/api/health` all 200; the boot reproduced the same frozen
  hashes as the dev line.
- Acceptance matrix **6/6** (77.5 s cold, then 7.7–16.7 s); 优必选 = 12 local
  patent citations; the negative control stayed web-only.
- Replay gate **ALL PASS 7/7** (19 turns, 0 failures, 0.9–19.8 s per turn).
- Rollback asset: `staging-slice2/site/site-rollback.sh` (restores the three
  modules + `run.sh` and restarts; the v1 pack and its receipt stay untouched).
