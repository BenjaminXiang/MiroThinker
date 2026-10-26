# Serving pack 重建（2026-10-27 排期）

> 对应变更：`rebuild-serving-pack-with-links-and-clean-summaries`（待创建，Epic）。
> 目标：**一次 20 小时重建，同时解决「向量里的模板文本」和「paper_ids 物化」**。

## 0. 结论先说：重建本身搞不定 paper_ids

`paper.professor_ids` 在 pack 里 **24,520 篇全空**，不是数据没算，是**构建端从来没写过这个字段**：

```text
$ grep -rn "professor_ids=" --include=*.py apps/miroflow-agent/src/data_agents/canonical_v2/
（无输出）
```

`PaperProjection.professor_ids` 只是模型里的一个字段，构建时没有被赋值。
关系边（10,742 条 `professor_attributed_to_paper`）确实算出来了，但只写进
`relationships.json`，没有回填到 paper / professor 文档。

所以「一次解决两件事」的前提是先补一段构建端代码（P1），否则跑完 20 小时，
只有模板向量被清掉，`paper_ids` 仍然是 0。

## 1. 四个前置（全绿才发射）

| # | 前置 | 内容 | 预估 |
|---|---|---|---|
| P1 | 构建端投影 | 把关系边按 paper 聚合写进 `paper.professor_ids`，按 professor 聚合写进 `paper_ids / paper_count / top_papers`；单测 + 小样本构建验证 | ~1 天 |
| P2 | 源数据清理 | 清 `released_objects` 里 2,149 条模板 summary（备份 + 计数对账 + 可回滚） | ~2 小时 |
| P3 | 配额与磁盘 | embedding 调用预算；信封 ~8.3 GB、索引 ~1.7 GB、旧包保留（回滚资产） | 30 分钟 |
| P4 | 切包窗口 | 单节点站点，重启 10 分钟；需与使用方约定 | 协调 |

## 2. 排期

```text
D0 上午   P1 代码 + 单测（paper_ids 投影、professor 聚合）
D0 下午   P1 小样本构建（单个 domain 子集）验证字段非空、哈希链正常
D1 上午   P2 源数据清理 + 对账；P3 资源检查
D1 傍晚   发射 20h 构建（脱离会话，watchdog + 十分钟巡检）
D2 下午   出信封 → 封印 → 切包窗口 → replay 7/7 → 评测门
```

## 3. 发射（复用 run16 流程）

命令沿用 `docs/plans/2026-09-15-run16-launch-runbook.md` §3 的
`complete_candidate_runner` 调用，差异只有三处：

1. `--run-id` 换成新的（如 `linkproj-build-20261028-v1`）；
2. 信封输出路径归档旧的（`mv` 到 `*-run16.json`，同盘秒级）；
3. 代码来自 `feat/serving-pack-links`（P1 合流后的分支），不是旧 worktree。

**禁止前台运行**（run15 的 A3 死因就是前台被中断杀进程组）；必须
`nohup`/`setsid` + watchdog + 失败巡检（沿用 run16 的 `run16-failure-report-*.md` 机制）。

## 4. 验收

| 项 | 标准 |
|---|---|
| 构建 | 信封生成、哈希链自证通过 |
| 字段 | `paper.professor_ids` 非空覆盖率 ≥ 60% 已链接论文；professor `paper_count` 覆盖 ≥ 60% |
| 检索 | 27 轮评测门不劣于基线 77/120；q27 稳定 |
| 反查 | 「这篇论文的作者是谁」能答出并带 citation |
| 回滚 | 旧 pack + 旧 index 保留，一次切换即回退 |

## 5. 风险

1. **构建端改动进 20 小时流程**：任何字段类型/约束不一致都会让构建在落库阶段失败
   （run16 曾有 8 次 attempt，全部死在投影形状与 NOT NULL）。所以 P1 必须先在小样本上跑通。
2. **源数据清理不可逆**：只清 `profile_summary` 字段，先 `pg_dump` 目标表 + 计数对账。
3. **切包窗口**：单节点，10 分钟空窗；失败要能 3 分钟内回滚。
4. **时间**：run16 实测约 8 小时，run14 约 20 小时；排期按 20 小时兜底。

## 6. 现在就能定的三件事

1. P1 是否按上述范围做（paper_ids + professor 聚合 + top_papers）；
2. P2 清理是否包含「模板句在句中」的记录（当前逻辑是整句丢弃，句中拼接的需要单独判断）；
3. 切包窗口选哪天几点。
