# Verification — alias passthrough and local foothold (in progress)

Layered evidence. T7 (scratch E2E) and T8 (reseal + cutover) are still open;
this file records what is proven so far.

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

Not yet run for this slice — T7 pending: scratch boot + the 4-form
acceptance matrix + `replay_fix_round1.py` 7/7 + recall-gate `--diff`. The
in-suite baseline assertion (①) is the current RED-class evidence; live E2E
follows before any deploy.

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
