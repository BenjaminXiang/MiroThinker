# 重建成本分析：为什么一次 run15 级重建要 ~20 小时

> 定位：对"run14/run15 级完整重建到底要多久、为什么这么慢"的定量回答。
> change-id: `close-workbook-gaps`（C1.1-batch1b 上下文；§7 的性能修复待另立 change）。
> 状态：**一次成文的分析（write once）**，依据 2026-09-13 深夜–09-14 凌晨的只读取证。
> 一句话结论：**ETA 需要从"约 1 小时"校正为 ~20 小时**；主因是构建校验链里
> 两处"对断言集做二次全量扫描"（O(N×M)），不是配置错误、不是挂死、不是 Milvus。

---

## 1. 结论与影响

| 项 | 校正前 | 校正后（实测） |
|---|---|---|
| 一次完整重建时长 | 约 1 小时 | **≈ 20 小时**（run14 实测 20h04m） |
| run15 落信封时点 | 09-13 深夜 | 按同节奏 ≈ **09-14 19:30 前后** |
| "长时间无写出 + CPU 100%" | 疑似卡死/自旋 | **正常长 CPU 段**（校验链在算，见 §5） |

影响：

- **周期更新（收尾计划 W6/L3 月度一键发布）**：20 小时级构建无法作为月更流水线
  的常态，发布窗口、门禁、回滚演练都要按 20 小时重排；修 §5 的两处扫描是这个
  前置。
- **失败成本**：任何一次构建中断（如 09-13 23:24 那次会话中断）都意味着重跑
  20 小时，而不是 1 小时——这直接改变了"敢不敢动它"的判断。
- **与线上问答无关**：只影响构建期；TTFT/检索质量不受影响。
- 结论不改变 run15 的处置：**让它跑完**，不要因为"看起来卡住"杀掉。

---

## 2. 证据一：run14 分阶段实测时间线

run14 是最新一次成功构建（信封 `complete-candidate-build-envelope-run14.json`，
8,101,559,113 字节，mtime 2026-09-08 20:00）。它的候选库
`miroflow_candidate_v2_20260819_r1` 仍在本机 PG 上，各阶段落库时间戳可查：

| # | 阶段 | 时间（+0800） | 相对起点 | 落库依据 |
|---|---|---|---|---|
| 0 | landing（构建开始） | 09-07 23:56:13 | — | `landing.ingest_run.observed_at`、`landing.source_record.parsed_at`、`landing.parser_run.started_at` 同为该值 |
| 1 | 身份解析完成 | 09-08 02:50:43 | **+2h54m** | `knowledge.identity_resolution_run.created_at` |
| 2 | 四域 typed projection 落库 | 09-08 17:34:09 | **+14h43m** | `{company,paper,patent,professor}.current_projection.last_updated`、`company.key_personnel.created_at`、`paper.author.created_at`、`patent.applicant.created_at` |
| 3 | 关系投影完成 | 09-08 18:12:54 | +38m | `knowledge.relationship_projection_run.created_at` |
| 4 | 索引段（Milvus Lite 构建） | 09-08 18:52–19:10 | +40m~ | `build.log` 内 milvus-lite 的 GOAWAY 告警时间戳 |
| 5 | 信封落地 | 09-08 20:00 | +1h47m | 信封文件 mtime |

**端到端 ≈ 20 小时 04 分。** 注意 §2 第 2 行：**14 小时 43 分花在
"身份解析完成 → 四域 typed projection 落库"之间**，这一段是全流程的最大开销，
而它不写日志、不写进度，只在结束时落一次库——这正是"看起来卡住"的来源。

> "约 1 小时"的出处：另一执行会话的状态记录
> `.worktrees/data-rebuild/.agents/runs/full-column-serving-pack-rebuild/run15-status-20260913.md`
> 第 20 行。它是估计值，与 run14 自身的时间戳不符，本文件据此校正。

---

## 3. 证据二：py-spy 三份抓栈（同一执行点）

| dump 文件 | 时间 | 进程 | 栈顶 |
|---|---|---|---|
| `/tmp/watchdog-spin-231931.txt` | 09-13 23:19:31 | 3523141（A3） | 见下 |
| `/tmp/watchdog-spin-234432.txt` | 09-13 23:44:32 | 3623209（A4，现役） | 见下 |
| `/tmp/watchdog-spin-235432.txt` | 09-13 23:54:32 | 3623209 | 见下 |

三份栈完全一致（跨两次不同进程、跨越 35 分钟）：

```text
validate_request            canonical_identity_resolution.py:427
  __init__                  pydantic/main.py:253
  _map_public_authority     knowledge_build_isolated.py:6038
  _logical_graph            knowledge_build_isolated.py:9395
  build                     knowledge_build_isolated.py:9832
  main                      complete_candidate_runner.py:1183
```

即：身份解析请求（`IdentityResolutionRequest`）的**模型校验**是当时唯一的执行点。
进程侧同步取证：`wchar` 停在 131,499,092 不动（20+ 分钟），但 `utime`、`minflt`
持续增长、CPU 100%、RSS 2.9GB 缓涨 —— 是"在算"，不是"在等"。

---

## 4. 证据三：模块级数据规模（run14 库 `knowledge` schema）

| 表 | 行数 | 说明 |
|---|---|---|
| `source_identity` | 47,075 | 参与身份解析的源身份数（N） |
| `source_assertion` | 620,798 | 断言全集（M） |
| `identity_decision` | 47,071 | 身份判定 |
| `canonical_decision` | 417,120 | 字段级决策 |
| `canonical_decision_assertion` | 834,240 | 决策-断言绑定 |
| `domain_inclusion_decision_assertion` | 418,067 | 入域判定-断言绑定 |
| `domain_projection_lineage` | 539,805 | 投影血缘 |

N×M 的最坏量级 ≈ 47,075 × 620,798 ≈ **2.9×10¹⁰** 次比较（实际断言子集更小，
但仍是 10⁹~10¹⁰ 级）。

---

## 5. 根因：两处"对断言集做二次全量扫描"

位置：`apps/miroflow-agent/src/data_agents/canonical_v2/canonical_identity_resolution.py`
（本批 batch1a 未改该文件——`git status` 确认本批只动
`knowledge_build_isolated.py` + 2 个测试；故这是**构建侧历史遗留**，非本批引入）。

**热点 1（本次抓到的栈顶）—— `:423-430`：**

```python
assertion_ids_by_source = {
    source_id: {
        assertion.assertion_id
        for assertion in self.identity_assertions     # 全量 M
        if assertion.source_identity_id == source_id  # :427
    }
    for source_id in source_by_id                      # 全量 N
}
```

对 47,075 个 source 各扫一遍全量断言 → O(N×M)。

**热点 2（同一校验器内，量级更大）—— `:1099-1106`：**

```python
for decision in self.identity_decisions:               # 47,071
    ...
    any(
        not _has_evidence_bound_internal_identifier(
            source=source_by_id[source_id],
            assertions=self.identity_assertions,       # 传全量
            ...
        )
        for source_id in decision.source_identity_ids
    )
```

而 `_has_evidence_bound_internal_identifier`（定义在 `:2414`）内部**每次调用都把
整个断言集线性扫一遍**：

```python
identifier_assertions = tuple(
    assertion
    for assertion in assertions                        # 全量 M，逐次调用重扫
    if assertion.source_identity_id == source.source_identity_id
    and assertion.field_path == field_path
)
```

调用点：`:1035`、`:1100`、`:3266`。同一形态在决策/入域校验段（41.7 万决策、
83.4 万决策-断言绑定）很可能还有同类，与 §2 表中"身份解析后 14h43m"的区间吻合；
本次只取了栈，未逐点定位。

**为什么 §2 的第 1→2 阶段缺口最大**：§3 的栈证明身份解析校验器是实际执行点，
而它之后还有决策批次、入域判定、内部引用投影、候选投影四段落库——每一段都在做
"逐实体重扫全量绑定"的同类校验。

---

## 6. 为什么会一直被误判成"卡死"

watchdog（`/tmp/build_watchdog.sh`）的判据是**每 5 分钟采样 `/proc/<pid>/io` 的
写出字节**：连续两轮不变即打印"自旋特征命中"。但本构建的重活是**纯 CPU 段**，
天然不写字节 —— 判据必然误报（它只抓栈、不杀进程；grep 确认无 kill 逻辑）。

正确的判活口径（本次采用）：

1. `utime` / `minflt` 是否递增（递增 = 在算）；
2. `py-spy dump` 栈是否落在"已知重活函数"（本次即 §3）；
3. 阶段落库点（`identity_resolution_run` / `*_projection.last_updated` /
   `relationship_projection_run` / 信封 mtime）是否按时推进。

---

## 7. 修法方向与验收线（供立项参考，本文件不定方案）

方向：**一次扫描预分组，把两处 O(N×M) 降为 O(N+M)**，语义完全不变
（同样的校验、同样的报错、fail-closed 不放宽）：

- `assertions_by_source: dict[str, tuple[SourceAssertion, ...]]`（一次遍历建索引）；
- `(source_id, field_path) → tuple[...]`，供 `_has_evidence_bound_internal_identifier`
  改为查索引；
- 同类形态在决策/入域校验段做**模式修复**（sibling 搜索），不要只修被点到的那一处。

验收线（建议）：

- 同一输入产出**逐字节可比的 envelope**（或至少 projection/身份结果摘要一致）；
- 身份解析段与"§2 第 1→2 阶段"耗时从小时级降到分钟级；
- `apps/miroflow-agent` canonical_v2 相关测试全绿 + 一次完整重建通过；
- 补一个中间进度可观测点（现在只有 merge ledger 与两处 run 落库，中段无信号）。

边界：**不做**"为缩短时间而放宽校验"；构建仍在跑期间不动这份代码。

---

## 8. 复核方法（任何人可重跑）

```bash
# ① run14 分阶段时间线（无需 psql，用 venv 里的 psycopg）
cd /home/longxiang/MiroThinker/.worktrees/data-rebuild/apps/miroflow-agent
.venv/bin/python - <<'PY'
import psycopg
url="postgresql://miroflow@127.0.0.1:55458/miroflow_candidate_v2_20260819_r1"
q=[("landing.ingest_run","observed_at"),("knowledge.identity_resolution_run","created_at"),
   ("knowledge.relationship_projection_run","created_at"),("company.current_projection","last_updated")]
with psycopg.connect(url, autocommit=True) as c:
    for t,col in q:
        s,tb=t.split(".")
        print(t, c.execute(f'SELECT min("{col}"), max("{col}") FROM "{s}"."{tb}"').fetchone())
PY

# ② 抓栈（需 sudo，watchdog 已用同法）
sudo -n env "PATH=$PATH" uvx py-spy dump --pid <runner_pid> > /tmp/rebuild-stack.txt

# ③ 判活（不依赖写出字节）
grep -E 'utime|minflt' /proc/<pid>/stat        # 定时采样看是否递增
ls -t /tmp/watchdog-spin-*.txt | head -3       # 最近的栈
```

---

## 9. run15 现况（截至 2026-09-14 00:00 前后）

- 进程：真身 PID 3623209（uv 包装 3623205，独立会话 SID 3622815），23:31:33 发射；
- 已过配置门：landing 73,907 条（23:31:39）、`P4_MERGE_LEDGER`（23:33:50，
  `company_full.fields_filled=4632`，较 run14 的 3726 **+906**＝别名填充生效）；
- 当前处于 §3 的身份解析校验段（长 CPU 段）；
- `staging-v2` 107MB 已落，`index-v2` 仅有 marker，信封未生成；
- 按 §2 节奏外推，信封预计 **09-14 19:30 前后**落地；
- 线上 18188 全程未受影响（仍跑 run14 sealed 包，health 200）。

---

## 10. 现场更新（2026-09-14 约 03:20）：第三个同类热点在 PG 层

**阶段已切换**：约 02:37 起，§3 的内存 CPU 段结束，进程进入
`persist_identity_resolution`（`knowledge_build_isolated.py:8761`）；抓栈落在

```text
wait                              psycopg/connection.py:484      ← 客户端在等结果
execute                           psycopg/cursor.py:113
_validate_release_and_restore_triggers   canonical_identity_postgres.py:449
persist                           canonical_identity_postgres.py:1517
persist_identity_resolution       knowledge_build_isolated.py:8761
_persist_owners / build / main    knowledge_build_isolated.py:9592 / :9855 / :1183
```

服务端取证（`docker top canonical-v2-s12c-pg-20260726-r8` + `pg_stat_activity`）：

| 观测 | 值 | 判定 |
|---|---|---|
| 语句 | `SET CONSTRAINTS ALL IMMEDIATE` | 延迟触发器强制此刻校验 |
| 后端 | `state=active`、`wait_event` 空、`stat=Rs` | 在 CPU 上跑，不是等锁 |
| CPU | **87.7%**，累计 CPU 时间 00:42:38 → 00:43:08（30s 内 +30s） | 真在算 |
| 时长 | 语句 38m25s→40m25s 递增；事务年龄 49m | 长耗时、非卡死 |
| **结局（约 04:05 观测）** | 语句已结束，后端转 `idle in transaction` / `ClientRead`；**该语句共耗服务端 CPU ≈ 85 分钟**（后端累计 CPU TIME 00:42:38 → **01:25:02**） | 单条复验语句 ≈ 1.4 小时 CPU |
| 之后 | 客户端读回 `SELECT chunk_index, chunk_b64, chunk_sha256 FROM knowledge.i…`（identity_resolution_run 分块） | 进入落库/回读环节 |
| 锁 | `pg_locks` 无未授予项 | 非死锁 |
| 库体积 | 45s 内 +0 字节（都在同一未提交事务里） | 复验阶段本就不写 |

语义（代码注释原文）：让唯一启用的延迟触发器
`trg_validate_identity_resolution_release` 在恢复其余触发器之前**校验整个 release 图**。
与 §5 同一类"写完再全量复验"的成本模型，只是发生在**数据库层**——所以

- §7 的性能修复不能只盯 Python 侧两处扫描；PG 侧的整图复验同样是小时级开销，
  两者**并列**为 C6 前置的候选；
- 该处的修法方向不同（触发器/约束策略、分批提交、把整图复验改增量或索引化），
  需在立项时单独设计，且**不得放宽 fail-closed 语义**。

复核命令：

```bash
docker top canonical-v2-s12c-pg-20260726-r8 -eo pid,etime,time,pcpu,stat,args \
  | grep candidate_v2_20260913            # 看后端 CPU TIME 是否在涨
# 再看语句与等待：pg_stat_activity 的 state / wait_event / xact_start / query_start
```

---

## 11. 现场更新（2026-09-14 约 08:20）：决策批次 COMMIT 的确切根因已定位

**现象**：约 05:35 起进入 `persist_decision_batch`（`knowledge_build_isolated.py:8771`），
客户端卡在 `commit`（`canonical_decision_postgres.py:1349`）。至 08:20 该 `COMMIT` 已跑
**2h42m 墙钟 / 后端 CPU 2h25m**，仍 `state=active`、`wait_event` 在
`IPC/BgWorkerShutdown` 与空之间切换、**无未授予锁**、`state=R`、~89% CPU；
并行 worker 每 30 秒换一批 PID（反复派生/回收），`canonical_decision` 行数仍 0
（全部在未提交事务里）。

**确切根因**（代码 + 库内实测）：

- 触发器 `trg_validate_field_human_review_assertion_binding` 是
  **`CREATE CONSTRAINT TRIGGER … DEFERRABLE INITIALLY DEFERRED FOR EACH ROW`**
  （`canonical_v2_alembic/versions/C2_0007_bind_human_review_provenance.py:1464`），
  即**逐行**触发、**延迟到 COMMIT** 才执行；
- 其函数体第一段（同文件 `:1170-1185`）对**每一行** `canonical_decision_assertion`
  执行一次

  ```sql
  IF TG_TABLE_NAME = 'canonical_decision_assertion'
     AND EXISTS (SELECT 1 FROM knowledge.canonical_decision AS human_decision
                 WHERE human_decision.method = 'human_review'
                   AND human_decision.human_review_resolution->'review_case'->>'release_id' = NEW.release_id
                   AND human_decision.human_review_resolution->'review_case'->>'originating_record_id' = NEW.decision_id)
  ```

- 而 `knowledge.canonical_decision` 上**没有任何针对 `method` 或该 JSONB 路径的索引**
  （实测索引清单：仅 6 个唯一/主键约束索引，无表达式索引）→ 每次触发都是
  **417,120 行表上的无索引扫描 + JSONB 取值**；
- 代价模型：`canonical_decision_assertion` **834,240 行** × 每次扫描 417,120 行
  ⇒ 10¹¹ 量级比较，且发生在 COMMIT 里（不可中断、不可分批）。

**修法方向（三选一或组合，立项时定；不得放宽 fail-closed）**：

1. 给该 `EXISTS` 加**表达式/部分索引**（如
   `ON knowledge.canonical_decision (release_id, (human_review_resolution->'review_case'->>'originating_record_id')) WHERE method = 'human_review'`）；
2. 把逐行触发器改为**语句级**（`AFTER INSERT … FOR EACH STATEMENT` + transition table），
   或先做一次廉价的"本 release 是否存在 human_review 决策"守卫，无则整段跳过；
3. 分批提交（把一次巨型 COMMIT 拆成多个受控批次），避免单事务把所有延迟触发堆到最后一刻。

**验证方式**：同输入产出逐字节可比信封（或至少决策/断言行数与内容摘要一致）
＋ `COMMIT` 从小时级降到分钟级；回归＝canonical_v2 测试全绿 + 一次完整重建。

**复核命令**：

```bash
# 触发器挂载方式与函数体
grep -n 'CREATE CONSTRAINT TRIGGER' -A2 canonical_v2_alembic/versions/C2_0007_bind_human_review_provenance.py | head
sed -n '1170,1185p' canonical_v2_alembic/versions/C2_0007_bind_human_review_provenance.py
# 库内确认索引缺失与触发器清单
#   SELECT indexname FROM pg_indexes WHERE schemaname='knowledge' AND tablename='canonical_decision';
#   SELECT tgname, tgtype FROM pg_trigger WHERE tgrelid='knowledge.canonical_decision_assertion'::regclass AND NOT tgisinternal;
```

### 11.1 代价实测（09-14 09:15，只读、带 10s 超时）

在 run14 库（同 schema、数据完整）上对触发器里那条 `EXISTS` 做 `EXPLAIN (ANALYZE)`：

| 观测 | 值 |
|---|---|
| 计划 | `Gather → Parallel Seq Scan on canonical_decision`（**无索引可用**，2 个并行 worker） |
| **单次执行** | **42.8 ms**（`shared read=26042`，冷缓冲） |
| `human_review` 决策数 | **0** |
| 决策总数 | 417,120 |
| 断言总数 | 834,240 |
| 索引清单 | 6 个主键/唯一索引，**无 `method` 或 JSONB 路径的表达式索引** |

⇒ 该触发器在本 release 的实际作用是"**每次确认一遍：本库没有人工评审决策**"，
而代价是 **834,240 × 43 ms ≈ 10 小时**（缓存热时也在数小时量级）。
这解释了 run15 的 `COMMIT` 为何 3h42m 仍未结束（同时段 runner 完全空转）。

**性价比最高的修法是加守卫而不是加索引**：`human_review` 计数为 0 时整段跳过
（或按 release 缓存一次"本 release 是否有 human_review 决策"），
语义完全不变（有评审决策时仍逐行校验），却把这一步从数小时压到毫秒级。
表达式索引（见 §11 修法 1）可作为第二步，用于真正存在评审决策的场景。



---

## 12. 设计评审：这一步算不算"过度设计"（2026-09-14，只读评审）

> 结论先行：**规则没问题，机制过度**。规则是"人审过的字段，机器重建不得悄悄换掉其证据"，
> 这是真实业务规则（`/review` 评审台是真实路径），**不该删**；但它的实现方式有四条可检验的
> 过度设计特征，且第 4 条直接堵死月更重建的路线。

### 12.1 规则本身（正当）

触发器的三部分职责（`apps/miroflow-agent/canonical_v2_alembic/versions/C2_0007_bind_human_review_provenance.py`）：

| 部分 | 位置 | 做了什么 |
|---|---|---|
| ① 不可变守卫 | `:1170-1185` | 新断言若挂到"已被人审过的字段决策"上即拒绝，`RAISE EXCEPTION 'reviewed field origin evidence is immutable'`（ERRCODE 23514） |
| ② 评审来源必须是祖先 release | `:1197-1216` | 对 `knowledge.release` 递归 ancestry，禁止自引用；否则报 `'field human review binding requires an immutable ancestor case'` |
| ③ 评审 case 与原决策逐项对齐 | `:1218-1265+` | 先 `FOR UPDATE` 锁原行，再逐项比对 `subject_id`/`field_path`/`supersedes_decision_id`/`policy_*`/`method`/`method_version`/`confidence`/`rationale`/`decided_at`/`llm_trace.*`/decision_id 前缀 |

对**普通（非人工评审）决策**只有 ① 会执行（②③ 在 `:1191` 的 `IF NOT FOUND OR reviewed.method <> 'human_review' THEN RETURN NEW` 处提前返回），
所以 §11.1 实测的那 42.8 ms × 834,240 次**全部花在 ①**。

### 12.2 四条可检验的过度设计特征（四条全中）

1. **同一不变量多层重复实现。** Python 侧 `canonical_identity_resolution.py:431-451` 已在校验
   `human_review_resolutions` 的绑定（`'identity human review must bind one prior exact component'`），
   DB 侧又用 PL/pgSQL 重写：本文件 `:1156` 一份 field 版、`:1486` 一份 relationship 版，
   `C2_0009_typed_domain_projections.py:1140` 还有一份 domain_inclusion 版。
   **一个规则 ≥5 份实现**，每份独立维护、独立踩性能坑——属"没有威胁模型的纵深防御"。
2. **把全局事实放到行级事件上重推。** "本 release 是否存在 human_review 决策"是 release 级一个
   bit 的事实，却被设计为**每插一行断言就全表查一次**。本次重建 **834,240 次触发，有效拦截 0 次**
   （run14 库 `method='human_review'` 计数 = 0）——语义上是空操作，代价是约 10 小时（§11.1）。
3. **执行查询没有可用索引。** ① 的谓词是 `method` 等值 + 两次 JSONB 路径取值；而
   `knowledge.canonical_decision` 上现有 6 个索引**全是 btree**
   （`(release_id, decision_id)`、`(decision_id)`、`(decision_id, canonical_identity_id, field_path)`、
   `(supersedes_decision_id)`、`(canonical_identity_id, field_path) WHERE supersedes_decision_id IS NULL`、
   `(release_id, decision_id, canonical_identity_id, field_path)`），**一个都用不上** →
   每次触发只能顺序扫 417,120 行并对每行做 JSONB 取值。设计时若考虑过代价，这里就该有表达式/部分索引。
4. **代价随语料规模超线性增长。** 总代价 ≈ 断言数 × 决策数（本次 834,240 × 417,120），
   即 O(N²)。月更重建 + 四域数据持续增长的前提下，这一步**不是"现在慢一点"，而是路线走不通**。

### 12.3 判定"过度设计"的四条口径（建议纳入后续同类评审）

1. 同一规则在几层各实现了几遍？
2. 是**行级**执行，还是可以**集合级**一次算完？
3. 执行它的查询**有没有索引**？（没有＝设计时没考虑代价）
4. 代价随数据规模是**线性**还是**超线性**？

### 12.4 最小设计（语义完全不变，不删规则）

1. **守卫优先**：release 级预计算一次"是否存在 human_review 决策"（小表或标记），为 0 则整段跳过——本次重建的约 10 小时直接归零；
2. **补索引**：`CREATE INDEX … ON knowledge.canonical_decision (release_id, (human_review_resolution->'review_case'->>'originating_record_id')) WHERE method = 'human_review'`，把全表扫变成索引查找（真正存在评审决策时也快）；
3. **改粒度**：触发器从 `FOR EACH ROW` 改 `FOR EACH STATEMENT` + transition table（或按批校验），834,240 次变 1 次集合查询；
4. **合并同型**：四份 provenance 校验合并为一份共享不变量（与 §5 的 Python 两处一起做，属 pattern-repair 范畴）。

### 12.5 验收线（与 §7 一致，不削弱 fail-closed）

- 同一输入产出**逐字节可比的信封**（或至少决策/断言行数与内容摘要一致）；
- 该 `COMMIT` 由**小时级降到秒/分钟级**；
- **补一条回归测试**：往已评审字段插入断言必须被拒（ERRCODE `23514`）——用它证明规则没被削掉；
- 回归：`apps/miroflow-agent` canonical_v2 相关测试全绿 + 一次完整重建通过。

### 12.6 复核命令

```bash
cd /home/longxiang/MiroThinker/.worktrees/data-rebuild/apps/miroflow-agent

# 触发器挂载方式（DEFERRABLE INITIALLY DEFERRED FOR EACH ROW）与函数体
grep -n 'CREATE CONSTRAINT TRIGGER' -A2 canonical_v2_alembic/versions/C2_0007_bind_human_review_provenance.py | head
sed -n '1170,1185p' canonical_v2_alembic/versions/C2_0007_bind_human_review_provenance.py

# 库内：索引清单（确认无表达式/部分索引可用）与触发器清单
#   SELECT indexdef FROM pg_indexes WHERE schemaname='knowledge' AND tablename='canonical_decision';
#   SELECT tgname, tgtype FROM pg_trigger WHERE tgrelid='knowledge.canonical_decision_assertion'::regclass AND NOT tgisinternal;

# 单次代价（只读，带超时；run14 库）
#   SET statement_timeout='10s';
#   EXPLAIN (ANALYZE, TIMING OFF, BUFFERS)
#     SELECT 1 FROM knowledge.canonical_decision h
#     WHERE h.method='human_review'
#       AND h.human_review_resolution->'review_case'->>'release_id'='never-matches'
#       AND h.human_review_resolution->'review_case'->>'originating_record_id'='never-matches';
#   实测：Gather → Parallel Seq Scan，2 workers，Execution Time ≈ 42.8 ms
```

> 出处：本节为 2026-09-14 只读评审结论，数字与栈证据见 §11、§11.1 与 §3；
> 修法与验收线与 §7 同源，合并立项时以 §12.4/§12.5 为准。

### 11.2 结局实测（09-14 18:14）：决策批次 `COMMIT` 共约 12h40m

| 观测 | 值 |
|---|---|
| 事务窗口 | 约 05:32 → 18:10（**≈12h40m 墙钟**），leader 累计 CPU ≈ **11h30m**（全程 ~91% 单核占用） |
| 期间客户端 | runner 完全空转（`utime` 每小时仅 +40~50 ticks） |
| 结束形态 | 事务提交后 `canonical_decision` = **423,493** 行、`canonical_decision_assertion` = **846,986** 行（较 run14 的 417,120 / 834,240 **+1.5%**，与别名富化一致） |
| 对照预测 | §11.1 预测 4.6–10h、09-14 15:14 重估为 14h 量级 ⇒ **实测 12h40m 落在重估区间内**（原 9.9h 模型因未计 worker 启停开销而偏低） |

**意义**：单是这一条"对 0 条人工评审决策反复确认"的延迟触发器，就吃掉了一次重建的一半以上时间。
按 §12.4 的最小设计（release 级守卫 + 表达式索引 + 语句级粒度），这一段应回到**秒级**。
剩余同型风险点：入域判定（`domain_inclusion_decision_assertion`，run14 口径约 41.8 万断言）
与关系投影（2.2 万断言），量级递减但同为 O(断言数 × 决策数)。

---

## 13. 发布契约评审：封印器在做什麼、8GB 信封算不算过度设计（2026-09-14，侧线只读评审）

> 结论先行：**规则正当，机制偏重**。封印器要证明的命题（"这个可秒级启动的包与发布信封完全等价"）
> 是必须的；但把发布权威装成**单个 8GB JSON**，使"解析 + 规范化 + 重算哈希"每一步都变成
> **小时级**，且同一事实被证了三遍。修法不是改封印器，而是改**契约形态**。
> 它**不是**当前最大成本（§11.2 的触发器单次 12h40m），优先级排在其后。

### 13.1 封印器在做什么（`s12c/build_serving_pack.py`）

| phase | 做什么 | 关键位置 | 代价性质 |
|---|---|---|---|
| `envelope_validate` | 读入 8.18GB 信封 → Pydantic 解析 → **重算 canonical 内容哈希**（`external_content_addressed=True`：整模型 dump 成规范 JSON 再 sha256） | `:175-179`；哈希绑定见 `knowledge_build_isolated.py:885 _model_sha256` / `:902 bind_content_sha256` | **小时级** |
| `index_snapshot_verify` | 打开 index 快照校验 marker/manifest，并确认与信封里的 release bundle 一致 | `:241-246` | 分钟级 |
| `placeholder_scan` | 全扫 `lookup.sqlite3`(669MB) 找占位符残留，写 side-car 报告 | `:255-279` | **仅 warn、不阻断**；几分钟 |
| `index_artifacts_copied` | 拷 `lookup.sqlite3`/`milvus.db`/marker，边拷边算 sha256 | `:281-304` | 3.2GB I/O，分钟级 |
| `authority_documents_written` / `manifest_written` | 写 `relationships.json`、`institution_catalog.json`、`manifest.json`（含各文件哈希与权威哈希） | `:306-417` | 秒级 |
| `dogfood_open` | **用真实 loader 打开刚做的包**，把重建出的权威与信封逐字段比对；不一致则拒绝出包 | `:424-444` | 分钟级 |

**存在理由充分**：线上启动只读 pack（秒级），不再碰信封；所以必须有一次性离线证明"pack ≡ 信封"，
否则改包就等于悄悄改数据。这一条**不该删**。

### 13.2 成本实测（run15, 2026-09-14）

- 信封体积 **8,184,481,154 字节**（run14 为 8,101,559,113）；
- 构建收尾 **runner 读回校验**：`read_envelope (complete_candidate_runner.py:935)` → `model_validate_json`
  → `validate_artifact_graph (knowledge_build_isolated.py:1970)` → `build (index_projection.py:457)`，
  20:44 开始、约 **1h45m**，期间 RSS 峰值约 **93GB**；
- 封印器（22:53 启动）**第一件事就是把这 8GB 再解析 + 再重算哈希一遍**，与上一步是同量级的重复开销：
  **`phase=envelope_validate seconds=2071.098`（≈34.5 分钟）**，占整包耗时（各 phase 合计约 **2663 秒 ≈ 44 分钟**）的约 **78%**；
  其余 phase：`index_snapshot_verify` 54.4s、`placeholder_scan` 10.1s（professor=12872 company=3097 glued=189）、
  `index_artifacts_copied` 3.7s、`authority_documents_written` 167.2s、`manifest_written` 5.3s、`dogfood_open` 351.1s；
- 包产物 **4.8GB**：`lookup.sqlite3` 668,884,992 / `milvus.db` 1,078,276,096 / `relationships.json` 3,390,932,565 /
  `manifest.json` 11,116,209 / `.canonical-v2-isolated-index-target.json` 313 / `institution_catalog.json` 381 字节；dogfood 自举校验通过；
- **同一份发布权威在 24 小时内被完整重算/重载了三次**：① 构建收尾读回（8.18GB 信封，≈1h45m，RSS 峰值 93GB）
  ② 封印器 `envelope_validate`（同一 8.18GB，2071s）③ 封印器 dogfood 重载（包内 `relationships.json` 3.39GB，351s）
  —— 合计约 **2.5 小时**，全部是"同一事实再证一遍"，这正是 §13.4 要消掉的成本。

### 13.3 用 §12.3 的四条口径评审

1. **同一不变量多层重复实现 —— 中招。** "这就是那个信封"被证三遍：构建收尾 runner 读回一次 →
   封印器再解析 + 重算 canonical 哈希一次 → dogfood 再把权威重建一次。三层各自重算同一批事实
   （对比 §12.2 第 1 条：同一规则 ≥5 份实现）。
2. **行级 vs 集合级 —— 不适用**（一次性批任务，无逐行触发）。
3. **有没有索引 —— 基本不适用。** 唯一"非必需"成本是那 669MB 占位符扫描，而它**只 warn 不阻断**：
   花几分钟换一个不参与任何决策的报告（可 gate、可抽检、可移到离线巡检）。
4. **代价是否超线性 —— 不适用**（是 O(bytes)），但**常数极大且重复 3 次**：单体 8GB JSON
   让每一步都是小时级 + 峰值 ~93GB 内存。

**根因是契约形态，不是封印器写得差**：把"一次算完的全局事实"装进最贵的执行路径，
与 §12 的触发器同属一类病（只是没有 O(N²) 那么毒）。

### 13.4 最小设计（按性价比，语义不减弱）

1. **pack 为主、信封降级为"哈希收据"**：出包只读 pack 自身 manifest + 两个小文档，
   信封只校验**顶层哈希**、不重建全模型 ⇒ 封印从小时级到分钟级；
2. 或**信封分块内容寻址**——仓内已有先例：C2_0013 迁移"Chunk oversized run snapshots instead of
   one jsonb value"，`identity_resolution_run_content_chunk` 就是为这个存在的，信封没享受到；
3. 或至少**去重**：runner 读回已经算过哈希并打印 `envelope_sha256=`，封印器可直接信这张收据，
   不必"再证明一次我是我"。

**适用条件**：能接受"发布慢但极稳"时，2/3 可暂不做；但月更（C6/W7）要常态化，第 1 条迟早要做。

### 13.5 验收线（若立项，不削弱 fail-closed）

- 封印（含解析）从**小时级 → 分钟级**；构建收尾的读回同样受益；
- **dogfood 等价性证明保留**（包与信封一致的证据不能少）；
- 回归：一次完整重建 + 封印 + scratch 端口起服务 + replay 门 7/7；
- 明确**不**为了提速而跳过 marker/索引校验或放宽哈希绑定。

### 13.6 优先级与依赖

- 先修 **§12/§11.2 的延迟触发器**（单次 12h40m，是真正的成本大头）；
- 再做本节的契约重构（每次发布省 ~1h45m 读回 + ~1h+ 封印 + 峰值 93GB 内存）；
- 两者都属 C6（周期更新）前置，建议并入同一份性能 change，分两步验收。

### 13.7 复核命令

```bash
# 封印器 phase 与耗时
tail -f /home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/full-column-serving-pack-rebuild/build-run15-pack-seal.log
# 代码位置
sed -n '170,200p;236,300p;420,460p' \
  /home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12c/build_serving_pack.py
# 信封体积与 RSS（读回窗口）
ls -l /home/longxiang/MiroThinker/.worktrees/data-rebuild/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12a/complete-candidate-build-envelope.json
```

> 出处：本节为 2026-09-14 侧线只读评审结论；证据（phase 表、`model_validate_json` 栈、8.18GB 体积、
> 93GB RSS）与 §11.2 同源；与 §12 的四条判定口径一致，合并立项时以 §13.4/§13.5 为准。
