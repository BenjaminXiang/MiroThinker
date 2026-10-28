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

---

## 8. S0 结果（2026-10-28 实跑）

### 一个改变设计的发现

原以为"库 → 导出 → 构建"就够了。实测发现**采集库比原始源包薄得多**：

| 字段 | 原始源包 | 采集库 | 当前 pack |
|---|---|---|---|
| `research_directions` | 37% | 0%（决策 3 丢弃） | 47% |
| `education_structured` | 19% | 0% | **0%** |
| `work_experience` | 20% | 0% | **0%** |
| `academic_positions` | 17% | 0% | **0%** |
| `awards` | 13% | 0% | **0%** |
| `top_papers` | 17% | 0% | **0%** |

也就是说：**只从库导出会让重建比现在更薄**。而 pack 本身也不是全量（上表第三列）。

### 修正后的设计：三方合并，优先级明确

```text
每个字段的取值优先级：采集库 > 原始源包 > 当前 pack
```

- **采集库**：新写入的事实（补全简介、修正、计数）；
- **原始源包**：字段最全（education/awards/top_papers 只有它有）；
- **当前 pack**：兜底（含最新构建的规范化结果）。

**id 映射**：源包用 `PROF-…`、pack 用 `professor-c-…`，两者靠 pack 文档里
`evidence[].assertion_id` 携带的 `PROF-…` 对上——这是 S0 打通的关键。

### 交付的两个脚本

| 脚本 | 作用 |
|---|---|
| `export_collection_sources.py` | pack + 源包 + 库 → 确定性 JSONL（按 id 排序、canonical JSON、`<sha256>.source`） |
| `validate_export_sources.py` | 形状校验 + **字段覆盖率对比**（对照原始源包），逐字段报出"导出比源包少了多少" |

### 首轮结果（教授，3,958 行）

```text
{"rows": 3958, "source_rows": 3652, "sha256": "5282674b…"}
shape_errors: 2（两行缺 profile_summary）
覆盖率：多数字段达到源包的 ~75%；四个字段 0%——未映射，S1 补齐：
  research_directions_source / publication_evidence_urls /
  official_paper_count / scholarly_profile_urls
```

### S1 待办

1. 补四个未映射字段；
2. 提高源包匹配率（3,652/3,735，差 83 条）；
3. 处理 2 行缺简介的记录（是数据问题还是映射问题）；
4. 之后用**真实 mapper** 做最终校验（S0 的覆盖率校验是形状级，不是语义级）。

---

## 9. S1 结果：教授导出达到源包同等覆盖（2026-10-28）

### 三处改进

1. **补齐 5 个未映射字段**：`research_directions_source`、`publication_evidence_urls`、
   `official_paper_count`、`scholarly_profile_urls`、`official_anchor_profile`；
2. **名称兜底匹配**：有些 pack 文档带的 `PROF-…` 不在源文件里，但教授本人在——
   按规范化姓名再匹配一次，覆盖率从 **~75% 提升到 ~98%**；
3. **剔除 2 条垃圾记录**：pack 里有两条 `name` 是网页标题（"本科生"、"团学风采"），
   没有任何简介——构建的发布门本来也会拒，导出时直接丢弃并计数。

### 结果

```text
{"rows": 3956, "pack": 3958, "source_rows": 7303, "dropped_without_summary": 2,
 "sha256": "849ba8f5……"}
shape_errors: 0
coverage_regressions: {}      # 所有源包字段导出量 ≥ 源包 95%
ok: true
```

**确定性验证**：连续两次导出，sha256 完全一致（`849ba8f5…`）。

**字段绝对量对照**（导出 / 源包）：

| 字段 | 导出 | 源包 | 比例 |
|---|---|---|---|
| `research_directions_source` | 3,665 | 3,735 | 98% |
| `education_structured` | 703 | 713 | 99% |
| `work_experience` | 729 | 740 | 99% |
| `awards` | 487 | 497 | 98% |
| `top_papers` | 639 | 651 | 98% |

剩余 ~1.5% 差异是"源包有、pack 没有"的教授——他们在源包里，但不在当前 pack 里，
导出可选地纳入（见下）。

### 一个待定项

源包里有 **164 位教授不在 pack 里**。是纳入导出（重建后 pack 会多出他们），
还是排除（保持与当前 pack 一致）？倾向**纳入**——他们是真实数据，重建后应该可检索。

### S2 待办

论文导出（24,558 篇）：同样三方合并（库 > 源包 > pack），源包字段对照见
`staging-v4` 的 paper 源；论文没有 `PROF-…` 式的 id 映射问题（源/库用同名 `paper_id` 家族？需确认）。
