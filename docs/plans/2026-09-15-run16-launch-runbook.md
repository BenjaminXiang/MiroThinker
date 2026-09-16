# run16 发射 Runbook（数据线重建 → 封印 → 切包）

状态：**待发射**（唯一未达门槛：D1-a 合流）。命令都在对应 worktree 内执行；
本文件是操作清单，不是证据文件（证据在 `.agents/runs/`）。

## 0. 本次要解决什么

run15 包已在线（18188，2026-09-15 00:40 切换）。run16 把数据线三片——D0-a/D0-b
清洗、C1 关系重投影、F3 触发器修复——灌进一次全新重建并切包：

- **查得准**：关系层 122 → 7,611 边（C1）；占位族 15,976 → 0（D0-a）。
- **构建时间**：单次重建 ~20h → ~8h（F3 消掉 12h40m 的触发器全量扫描）。

## 1. 发射门槛（全绿才发射）

| # | 门槛 | 状态 | 证据 |
|---|---|---|---|
| 1 | F3 触发器修复合入 + 头版本常量 C2_0014 | ✅ | merge `148bc03f` + `10b646ac` |
| 2 | D0-a 清洗第一批 | ✅ | merge `4b546cee`（分支 `cfa41ec5`） |
| 3 | D0-b 清洗第二批 | ✅ | 同前 |
| 4 | C1 关系重投影 | ✅ | merge `b5af35a9`（分支 `8f737c02`） |
| 5 | 合并集成定向测试 + C1 重放复跑 | ✅ | 6 文件 168 passed；revision 文件 8 passed；C1 重放与记录**逐字一致**（7,611 边 / 0 缺失；仅抽样列表顺序不同） |
| 6 | **D1-a 受控技术词表** | 🔧 最后门槛 | agent-44 续跑中；合入见 §2 |
| 7 | P1 瘦包（服务线） | ✅ 代码就绪 | `fix/slim-serving-pack` `c5c8f58c`；封印时启用 v2 |
| 8 | 服务线模型同步（D0-a 9 字段必填→可空） | 🔧 隔离分支 `feat/serving-model-sync` 实施中 | 已核实会 boot 拒载，见 §2.1 |

已知既有红（不阻塞，并入 P12）：`test_knowledge_build_isolated` 12 红（测试侧 mock
pin 在 C2_0012）、`test_canonical_scope_founder_red` 1 红、`knowledge_build_isolated.py`
F402 lint（`5078678b` 起既有）。

## 2. 合流（`.worktrees/data-rebuild`，分支 `data/p4-serving-pack-rebuild`）

已完成：D0-a `4b546cee` → C1 `b5af35a9` → F3 `148bc03f` → 头常量修复 `10b646ac`。

- 解析记录：`knowledge_build_isolated.py` 冲突取 C1 侧（`supplemental_rows`；该函数
  签名已换成 `object_rows_by_id` + `supplemental_rows`，HEAD 侧只是把 if 折成单行）；
  `openspec/change-ledger.md` 冲突 = 保留双方行。
- **合流中发现并修复**：F3 加了迁移 C2_0014 但没动 `_EXPECTED_ALEMBIC_REVISION`
  （仍是 C2_0013）。发射脚本第 2 步 `alembic upgrade head` 会把候选库升到 C2_0014，
  而 `validate_fresh_targets → _assert_fresh_database` 断言**精确相等**，构建会当场
  `ValueError` 终止。修复 = 常量升 C2_0014（`10b646ac`）+ 新守卫测试钉住
  "常量 == 迁移 head"（`tests/canonical_v2/test_canonical_revision.py`）。
- **合并树语义复验**：复跑 C1 重放（只读 run15 包 + 暂存库）——post-fix 7,611 边 /
  960 公司 / 0 未解释缺失、pre-fix 仍被拒；除抽样列表顺序外与 `replay-run15.json`
  逐字一致 → `.agents/runs/c1-relationship-reprojection/replay-run15-merged-tree.json`。

最后一步（D1-a）：

```bash
cd /home/longxiang/MiroThinker/.worktrees/data-rebuild
git merge --no-edit feat/d1a-tech-vocabulary
# 冲突处理：OpenSpec / ledger / index → 保留双方行；代码按语义合并
cd apps/miroflow-agent
uv run pytest tests/canonical_v2/ -k "tech_vocabulary or publication_cleaning" -q
```

### 2.1 跨线契约：服务线必须先拿到的模型改动（切包前闸）

run16 包会携带 D0-a 的"占位值 → 置空"。以下 9 个字段在数据线已改为可空，
服务线（`codex/canonical-v2-s12a-ready`）仍是必填：

- CompanyProjection：`profile_summary`、`technology_route_summary`
- ProfessorProjection：`department`、`email`、`homepage`、`paper_summary`、
  `patent_summary`、`profile_summary`、`title`

机制（已核实）：`serving_pack_loader.py` 在 boot 时解析 pack 的
`relationships.json → candidate_projection_result`，对每条投影按模型校验且
**fail-closed**（`ServingPackIntegrityError`）→ 含 null 的 run16 包会被**拒载**。
字段注解逐条对比（`model_fields[...].is_required()`）已做：服务线 9/9 required，
数据线 9/9 optional。

处置：**已完成**（隔离 worktree `feat/serving-model-sync`，基于服务线 `codex/canonical-v2-s12a-ready`）：
`e9f2e974` 模型对齐（`domain_projection_models.py` 与数据线逐字节一致）+ `eff2a793` 回归测试
（RED 4 failed/2 passed → GREEN 6 passed；13 文件回归 208 passed/2 skipped，失败集差异仅新 RED）
+ `57877ebc` 证据。**run15 包仍可装载**：两次 scratch 装载 OK（336.1s/333.5s），全包哈希重算
= run15 manifest 值 `6ad4c090…`（逐字节一致）。

**新增已核实事实（影响封印）**：sealer 解析 `CompleteCandidateBuildEnvelope` 时同样把
`index_projection_request.candidate_projection_result` 按 `CandidateProjectionResult` 校验
（`index_projection.py:263-265`）——**封印也会撞这 9 个字段**。所以切包窗口里服务线树必须先
同时合入 **P1（v2 sealer）与 `feat/serving-model-sync`**，然后才能封印/装载 run16 包。
已知遗留（证据在案）：`index_projection.py:754` 的 `projection.department.name` 对 None 不安全，
仅索引物化/信封 replay 路径可达（数据线副本已有守卫，pack 的 boot/查询路径不经过）——
若服务线将来用 run16 形态投影做索引物化，再修。

## 3. 发射重建（脱离会话）

模板：`.agents/runs/full-column-serving-pack-rebuild/build-run15.sh` → 参数副本
`build-run16.sh`（**已就绪**：run16 参数 + 两道 fail-closed 闸——① `feat/d1a-tech-vocabulary`
未并入 HEAD 则拒绝（已实测 exit 2）；② 信封路径被占用时提示先归档 run15 信封；其它参数一律不改）。
注意 `--source-manifest-sha256` 是 manifest 的**内部 `content_sha256` 字段**（内容寻址），
不是文件字节 sha（文件字节现为 `acc62c33…`，属正常）。

| 参数 | run15 | run16 |
|---|---|---|
| `TARGET_DB` | `miroflow_candidate_v2_20260913_r1` | `miroflow_candidate_v2_20260916_r1` |
| `RUN_ID` | `p4-build-20260913-v1` | `p4-build-20260916-v1` |
| `STAGING` | `staging-v2` | `staging-v3`（fresh） |
| `INDEX` | `index-v2` | `index-v3`（fresh） |
| `ENVELOPE` | `s12a/complete-candidate-build-envelope.json` | **同一固定路径**（runner 强制；见下）——发射前必须先把 run15 信封归档为 `s12a/complete-candidate-build-envelope-run15.json`（8.1GB，同盘 `mv`，秒级） |
| release id | `candidate-v2-20260913-r1` | `candidate-v2-20260916-r1` |

> runner 强制：`--envelope-output` 必须等于 `<gate-root>/s12a/complete-candidate-build-envelope.json`
> 且必须"全新"（不存在/非符号链接/单链接；`complete_candidate_runner.py` 的配置段检查）。
> 所以 run16 复用固定路径，run15 信封先归档保留（回滚不需要 reseal——直接切回 run15
> sealed 包即可；归档文件仅作证据）。

发射（禁止前台；run15 的 A3 死因就是前台被中断杀进程组）：

```bash
cd /home/longxiang/MiroThinker/.worktrees/data-rebuild
setsid nohup bash .agents/runs/full-column-serving-pack-rebuild/build-run16.sh \
  > .agents/runs/full-column-serving-pack-rebuild/build-run16-detached-nohup.log 2>&1 &
```

监控与里程碑（`watchdog-run16.log`（`watchdog-run16.sh`，5 分钟一行：pid/state/cpu/wchar/envelope）+ `build-run16.log`）：

- `P4_MERGE_LEDGER` 打印：与 run15 的 `fields_filled` 对账（清洗会改数字，看量级）；
- **决策批次 COMMIT 应 ≈4 分钟**；若仍是小时级 → F3 未生效，停下查 C2_0014 是否应用；
- identity 阶段 = F1/F2 插桩数据采集点；信封落地即完成（打印 `envelope_sha256=`）。
- 长 CPU 段 + 无写出是已知正常（身份解析/信封哈希），判活用 utime/py-spy 栈。

预计 ~8h（run15 实测 ~21h13m − F3 的 12h40m）。

**发射历史**：attempt 1/2 死于环境（进程组被回收 / 信封路径处置）；attempt 3（09-15 22:53）
跑到 09-16 00:32 被 D0-a 发布门拦下（`placeholder values published: 5`，根因＝补充通道未过
清洗，见 data-cleaning-batch1 日志轮次追加）；修复 `3a9f9149` 后 attempt 4（09-16 11:01）发射；attempt 4 又被同一道门拦下但**门已点名**（`paper.venue.name: 未提供期刊出处` —— venue 引用型字段漏在清洗清单外），修复 `fee2fc85` 后 **attempt 5（09-16 14:45）**发射。**失败巡检机制**：watchdog 落 `run16-failure-report-<ts>.md` ＋10 分钟 cron 四态巡检（运行中/成功/失败/CPU 冻结）。attempt 5（09-16 14:45）过了占位门、倒在类型化投影（`PaperProjection.venue` 必填 vs 清洗置空），修复 `41a8d96e`（模型可空）＋服务线 `c1c17ad5` 后 attempt 6（09-16 16:13）发射——attempt 6 **首次走到落库**，死在 DB 侧 NOT NULL（模型可空的第 10 个字段没有同步到 schema），迁移 `C2_0015` 修复（`ca50ae68`）后 attempt 7（09-16 19:06）发射——attempt 7 落库到 paper 投影时又撞上形状约束 `ck_paper_current_projection_venue_shape`（NOT NULL 之后的同一耦合下半层），迁移 `C2_0016` 修复（`84100331`，含同类穷举 15/15）后 **attempt 8（09-16 22:06）**发射。

### 3.1 发射前干跑（2026-09-16 教训，新增）

发射重建前必须按序跑（全绿才发射）：

1. **风险扫描 gate**（约 2 分钟，扫全量输入）：
   `uv run python .agents/runs/full-column-serving-pack-rebuild/sweep_publication_risks.py`
   —— 用**生产分类器**（占位族/粘连/研究方向垃圾）加"兜底触发字段为空"扫全部 P4 批次，
   把每个风险字段映射到发布字段并断言清洗表已覆盖；出现 `UNCOVERED` 即 exit 1。
   （venue 缺口正是这一类；修正映射后当前全绿。）
2. **修复类 RED/GREEN 单测** + D0-a/D1-a 定向套件，并跑**模型⇄schema 空值门**
   （`apps/miroflow-agent/scripts/run_canonical_v2_pg_regression.sh`，秒级）：它断言"默认为 None
   的模型字段都有可空列、且四个 current_projection 表上没有拒 NULL 的 CHECK"。已用
   C2_0014 对照证明能逐项点名 attempt 5/6/7 的违规项（company 2 列 / paper venue+约束 /
   professor 7 列+约束），head 上通过。
3. **端到端 mini 重演**（`build-mini.sh`，可选）：整链重演（同一 runner，独立 DB/staging/index/信封）。
   注意：按 run16 的输入构成它已不再"小"——要覆盖风险路径就得纳入全部六批 P4，体积与 full 逐条
   相同（111MB、同一集合）；因此它用于**结构变更时的整链重演**，不是常规快检。

## 4. 封印（pack v2）

**脚本已就绪**：`build_run16_serving_pack.sh`（参数副本 + 三道 fail-closed 闸：pack 目录
必须全新；index 根/marker 必须存在且 sha 与 `EXPECTED_MARKER_SHA256`（来自
`build-run16.sh` 打印的 `index marker sha256=`）一致；sealer 必须支持
`--pack-schema-version`——当前 index-v3 未建故直接 exit 2，已实测）。**前置（已核实）**：
运行封印的服务线树必须先同时合入 **P1（`fix/slim-serving-pack`，提供 v2 sealer）** 与
**`feat/serving-model-sync`（sealer 的信封解析也会校验那 9 个可空字段，见 §2.1）**。
差异：

- `INDEX_ROOT=index-v3`、`PACK_DIR=/var/tmp/mirothinker-data-v2/serving-pack-run16-sealed`、
  `ENVELOPE=` 固定路径（run16 信封，见 §3）、`RELEASE_ID=candidate-v2-20260916-r1`、
  `GENERATOR_RUN_ID=p4-pack-20260916-v1`；
- **sealer 用 P1 版且运行树 = 将服务该包的服务线树**（脚本默认
  `SERVING_WORKTREE=.worktrees/canonical-v2-s11-consolidation`，即 P1 + 模型同步合入后的
  服务线；可用环境变量覆盖）；产出 v2 契约包；
- 产出 v2 pack + mount receipt；随后 `smoke_test.py` 冒烟（scratch 端口，不占 18188）。

## 5. 切包窗口（18188）

活线结构（已核对）：user systemd `canonical-v2-backend` → ExecStart
`.worktrees/canonical-v2-s11-consolidation/deploy/start-canonical-v2.sh` → 读取
`s12g/serve-18188-command.sh`（单一事实来源）。当前指向 run15 包 +
`miroflow_candidate_v2_20260913_r1` + index-v2。

0. **服务线预合（已完成于隔离树）**：`.worktrees/serving-run16-ready` @
   `codex/canonical-v2-run16-ready` = `codex/canonical-v2-s12a-ready` + P1 + 模型同步
   （两处 doc 冲突已按"保留双方行"解析），关键子集 **77 passed**（loader/可选字段/
   投影合同/fast boot）。切包时：**封印从这棵树跑**，随后把活线
   `.worktrees/canonical-v2-s11-consolidation`（当前 5afdb6f6）**fast-forward 到
   同一提交 d8294d37**，再重启——两棵树同码，包与装载器一致。

1. 回滚资产确认（已存在，不动）：`s12g/serve-18188-command-run15.sh`、
   `s12g/serving-bundle-run15.json`、`serving-pack-run15-sealed`、index-v2 / staging-v2。
2. 生成 `s12g/serving-bundle-run16.json`：`generate_run16_serving_bundle.py`（**已就绪**：
   以 `serving-bundle-run15.json` 为源，只换 release/DB/index/envelope/bundle id；要求
   `EXPECTED_MARKER_SHA256` 环境变量并从包 marker 现算复核、要求包 manifest 为 **v2 契约**
   且身份四项（release/index_root/marker/generator_run）匹配；运行树由 `SERVING_WORKTREE`
   指定——应为合入 P1 + 模型同步后的服务线）。
3. 生成 `s12g/serve-18188-command-run16.sh`：`prepare_serve_command_run16.py`（**已就绪**：从活
   命令做 10 处身份替换，逐项校验出现次数、替换后防残留；bundle sha 取 run16 bundle 的
   `content_sha256`；已用假 bundle 干跑，token 级差异恰好 10 处）。产物先落数据线 run 目录，
   切包时拷入服务线 `s12g/`。
4. 切换：`cp serve-18188-command-run16.sh serve-18188-command.sh && systemctl --user restart canonical-v2-backend`。
5. 验收（全在 18188 上跑）：replay 门 7/7；两个逐字探针（「字节跳动」→ ByteDance Ltd.；
   「优必选有哪些专利」→ 32 个本地 CN）；国先案例；g17 双轮；TTFT 记录。
6. **回滚演练**：切回 `serve-18188-command-run15.sh` → restart → 跑探针 → 记录耗时；
   演练后切回 run16。

## 6. 回滚

- 触发条件：boot 拒载 / replay < 7/7 / 探针失败 / 崩溃循环 / TTFT 明显回退。
- 命令：§5.6；资产不删（run15 pack、run15 DB、index-v2/staging-v2、bundle-run15）。
- 根因未定位前不得二次切包。

## 7. 切包后

- 从 run16 信封记录 per-phase 计时（F3 acceptance A1/A2 与 F1/F2 follow-up 的判定输入）。
- 根仓 `AGENTS.md` §2 的 serving-pack 描述（Milvus Lite）随 v2 生效更新（受保护文件，单独确认）。
- 既有红灯（isolated 12 / scope 1 / F402）并入 P12 卫生；另记：`test_knowledge_build_isolated.py`
  全文件跑在并发负载下需 20+ 分钟（mock 重 + in-process 构建），**不是挂死**，P12 时拆分/标记
  慢用例；D0-a 死字段退役（22 个）单独切片；light-lane 残留库清理待拍板。
