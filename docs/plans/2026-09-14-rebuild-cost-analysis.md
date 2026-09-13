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
