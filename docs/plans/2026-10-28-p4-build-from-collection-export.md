# P4：构建从采集库导出（设计 + 排期）

> 目标：让**重建以采集库为源**，而不是外部源包。这样 P1/P2 回灌进库的数据不会在重建时丢失，
> 重建也能吸收日常导入/补全的结果。
> 对应变更：`build-from-collection-export`（Standard）。

## 1. 现在构建吃什么

```text
run.sh / complete_candidate_runner
  └─ --source-manifest  canonical-v2-source-build-manifest-v2.json
       └─ inventory_entries[]  → members[]
            member: member_id / source_batch_id / source_kind / content_path /
                    byte_size / content_sha256 / parser / observed_at
  └─ 构建把每个 member 复制成 staging/<sha256(member_id)>.source
  └─ land_released_objects：按 released_objects_mapper 解析成 SourceRecord/EvidenceArtifact/payload
  └─ 投影 → 索引 → 封印（pack + manifest + index marker）
```

**关键点**：源是"清单 + 带哈希的成员文件"。只要我们能产出**同格式的成员文件**并写进清单，
构建端**一行不用改**。

## 2. 设计：DB → 导出 → 源包 → 构建（构建端零改动）

```text
采集库（Postgres，现在是 pack 的超集）
   └─ export_collection_sources.py --domain X --snapshot <id>
        ├─ 读表 → 映射成 released-object 记录（JSONL，确定性排序）
        ├─ 写 <sha256>.source（内容寻址）
        ├─ 记录 pipeline_run（run_kind='build_source_export'）
        └─ 产出 manifest 片段（members：batch/kind/sha256/size/parser）
   └─ 组装 source-build-manifest-v2（DB 导出成员 + 仍需保留的外部源）
   └─ 构建（不变）
```

**为什么走"导出"而不是"让构建直连库"**：保留可复现性（同一导出可重放）、保留哈希校验、
避免构建端引入数据库依赖；出问题时可以回退到旧源包重建。

## 3. 风险与对策

| 风险 | 说明 | 对策 |
|---|---|---|
| **schema 不匹配** | 构建的 `released_objects_mapper` 对字段形状很严格（run16 曾连续 8 次失败） | **先做校验器**：把导出样本喂给真实 mapper，秒级反馈，不跑全量构建 |
| 字段缺失 | 采集库有些字段 pack 有、库没有（如 `research_directions`） | 导出时置空并在报告里计数；由 P1 记录为已知损失 |
| 幂等/可重放 | 同一快照必须导出相同字节 | 确定性排序 + 规范化 JSON（`sort_keys`、无浮点误差） |
| 与外部源共存 | 专利/企业还有别的来源 | 清单支持混合：DB 导出成员 + 原有成员 |
| 全量重建 20 小时 | 一次做错代价大 | 先"只 ingest 不投影"的干跑（分钟级），再全量 |

## 4. 切片（每片可独立验收）

| 片 | 内容 | 验收 | 工期 |
|---|---|---|---|
| **S0** | 导出器骨架 + **校验器**（样本 → 真实 mapper） | 100 条样本全部通过 mapper，无异常 | 1 天 |
| **S1** | 教授导出（3,956 位） | 校验器全通过；行数对账；与 pack 字段抽样一致 | 1 天 |
| **S2** | 论文导出（24,558 篇） | 同上；DOI/标题去重率 < 1% | 1 天 |
| **S3** | 专利（17,963）+ 企业（7,089）导出 | 同上；专利号唯一 | 1 天 |
| **S4** | 清单组装 + **ingest 干跑**（只跑装载与落库，不跑投影） | 干跑通过、行数一致、哈希自证 | 1 天 |
| **S5** | 全量重建（约 20 小时）→ 封印 → 切包 | 评测门 ≥ 80/120；replay 7/7；回滚资产就绪 | 1–2 天 |

**总工期**：5–7 天（不含 20 小时构建窗口）。

## 5. 开始 S0 的命令

```bash
# 1. 取样本（每域 100 条）
python scripts/export_collection_sources.py --domain professor --limit 100 --out /tmp/export-prof

# 2. 校验（真实 mapper）
python scripts/validate_export_sources.py --export /tmp/export-prof --domain professor

# 3. 看报告
cat /tmp/export-prof/validation.json
```

## 6. 前置条件

- P1/P2 已完成（库是 pack 超集）——✅；
- 构建窗口与切包窗口需与使用方约定（20 小时构建 + 约 10 分钟切换）；
- 回滚资产：旧 pack、旧 index、旧 manifest 全部保留。

## 7. 验收（整体）

1. 导出的源包能通过构建的 ingest 干跑；
2. 全量重建产物：四域计数与采集库一致（差值 ≤ 已知基线）；
3. 评测门 ≥ 80/120，replay 7/7；
4. 旧包可一键回滚；
5. 重建后，采集库里 P1/P2 回灌的数据**仍在**（不再被覆盖）。
