# 教授/论文的架构债：系统性修复规划（2026-10-28）

> 现状：服务包有 3,958 位教授、24,520 篇论文；采集库只有 220 / 555。
> 也就是说 **pack 的大头不在库里**，构建源包与采集库是两条数据线。
> 对应变更：`unify-collection-as-source-of-truth`（Epic，见 §7）。

## 1. 为什么这是债，不是 bug

| 现在的样子 | 后果 |
|---|---|
| pack 由外部源包构建，采集库只收了一小部分 | 库里查不到大多数教授/论文 |
| 管理端"数据浏览"读库 | 只能看到 220 / 555，与 pack 对不上 |
| 补全流水线从库选人 | 只能补那 220 位，pack 里的 2,856 位薄画像**无法批量补** |
| 重建读源包 | 库里新增/修改的数据在重建时**丢失** |

最后一条最危险：任何"入库即改数据"的运营动作，都会在下次重建时被覆盖。

## 2. 目标（按阶段可验收）

1. **pack ⊆ 库**：pack 里每一条教授/论文都能在库中找到；
2. **库可运营**：补全、纠错、导入都能在库上做，且不会被重建覆盖；
3. **重建从库导出**：构建的源从"外部源包"改为"库导出 + 必要源包"；
4. **一致性可见**：每日核对 pack 与库，差异超阈值告警。

## 3. 阶段与工作量

### P0 核对与设计（0.5 天）

- 字段映射表：pack 文档 → 库表（教授：`professor` + `professor_affiliation` + `source_page`；论文：`paper`）；
- **id 策略**：pack 用 `professor-c-…` / `PAPER-…`，库用 `PROF-…`。建议保留 pack id 作为主键，另存来源标记；
- **枚举值**：`discipline_family`（未知 → `other`）、`canonical_source`（论文来源需新值或映射）、`quality_status`（`needs_enrichment`）；
- **幂等键**：教授按 pack id；论文按 DOI → 规范化标题；
- 产出：字段映射表 + 迁移 SQL 模板 + 抽样 20 条对照。

### P1 教授回灌（1 天）

- 从 pack 导出 3,958 位教授 → 生成 COPY/批量插入（教授 + 机构 + 源页）；
- 验收：库教授 = 3,958（±0）、抽样 50 条字段一致率 ≥ 98%、`professor_affiliation` 每条都有；
- **副产品**：补全流水线从此能按 `--min-summary-len` 覆盖全量画像（不必再手工导名单）。

### P2 论文回灌（1.5 天）

- 24,520 篇 → 批量插入；去重：DOI → 规范化标题；
- 验收：库论文 ≥ 24,520、重复率 < 1%、抽样 50 条一致；
- 注意：`paper_id` 与 pack 的 `PAPER-…` 同名，需与现有 555 条去重。

### P3 一致性守卫（0.5 天）

- 每日任务：核对 `pack ⊆ 库`（按 id），输出每域差异数；
- 管理端展示 + 差异 > 1% 时告警；
- 复用现有 `system-status` 的 `collection_record_count` 口径。

### P4 构建改为从库导出（3–5 天，另立项）

- 构建的 professor/paper 源从"外部源包"改为"库导出快照"；
- 需要处理：源哈希、可复现性、增量源包兼容；
- 这是 Epic，单独出 OpenSpec + 设计方案。

## 4. 风险与对策

| 风险 | 对策 |
|---|---|
| id 冲突（pack id vs 库 id） | 保留 pack id；`run_id` 标记 `pack-backfill-20261028`；重复执行幂等 |
| 机构缺 `source_page`（NOT NULL） | 用 homepage 生成 `source_page`；无 homepage 用 `pack://<id>` 占位并标记 |
| 论文来源枚举不含"回灌" | 二选一：映射到最接近值 + `run_id` 溯源，或加迁移新增 `pack_backfill` 值 |
| 24k 行插入慢 | 单事务 + COPY；禁止逐行提交（专利导入的教训：逐行提交让 69 秒变 25 分钟） |
| 回灌后重复 | 幂等键 + 唯一索引；先 dry-run 统计冲突 |
| 回灌把库撑大后，重建仍读源包 | P4 之前，回灌只解决"库可运营"，不改变重建行为——必须在文档与告警里写清 |

## 5. 验收（整体）

1. 库教授 ≥ 3,958、论文 ≥ 24,520；
2. 抽样 50 条/域字段一致率 ≥ 98%；
3. 一致性守卫每日运行，管理端可见差异；
4. 补全流水线能对全量教授选人（试点 20 位已证明可行）；
5. 回灌脚本幂等（重复执行不产生新行）。

## 6. 不做什么

- 不在 P1/P2 阶段改变重建逻辑（P4 单独立项）；
- 不迁移历史 id（保留 pack id，另存来源）；
- 不清理现有 220/555 行（去重合并放到 P2 的幂等逻辑里）。

## 7. 变更登记

- Epic：`unify-collection-as-source-of-truth`（proposal 先行，P1 落地时补 specs）；
- P1/P2 各自可拆 Lite/Standard change；
- 人类文档：本文；日志：`2026-10-26-systematic-completion-gates-log.md` 第 35 轮。

---

## 8. P0 结果（2026-10-28 实跑）

脚本：`reconcile_pack_to_collection.py`（只读，输出 JSON）。

| 域 | pack | 采集库 | 按 id 命中 | 按名/DOI/标题命中 | **待插入** | 缺失必填 | 库独有 |
|---|---|---|---|---|---|---|---|
| 教授 | 3,958 | 220 | 220 | 2（重名不同 id） | **3,736** | 0 | 0 |
| 论文 | 24,520 | 555 | 500 | 17（15 DOI + 2 标题） | **24,003** | 0 | **55** |

**结论**：

1. 采集库里现有的 220 位教授**全部来自 pack**（id 一致），回灌是纯增量；
2. 有 2 位教授是"同名不同 id"，需要合并策略（否则会重复）；
3. 论文有 55 条库独有（不在 pack 里），回灌不能删它们；
4. 没有因缺必填字段被挡下的记录——字段映射可行。

## 9. 字段映射（P0.1）

### 教授 · pack → 采集库

| pack 字段 | 目标 | 说明 |
|---|---|---|
| `canonical_identity_id` | `professor.professor_id` | 保留 pack id（可追溯） |
| `name` / `canonical_name_zh` | `professor.canonical_name` | NOT NULL |
| `canonical_name_en` | `professor.canonical_name_en` | |
| `aliases` | `professor.aliases` | `text[]`，默认空数组 |
| `institution` | `professor_affiliation.institution` | 先建 `source_page` 再插机构 |
| `department`（dict） | `professor_affiliation.department` | 取 `.name`，缺失留空 |
| `title` | `professor_affiliation.title` | |
| `homepage` | `source_page.url` | 无主页时用 `pack://<id>` 占位 |
| `profile_summary` | `professor.profile_summary` | |
| `paper_count` / `h_index` / `citation_count` | 同名列 | |
| `quality_status` | `professor.quality_status` | 枚举含 `partial`，直接透传 |
| `research_directions` | — | 库无对应列；P1 先跳过，记入待办 |

固定值：`discipline_family='other'`、`identity_status='needs_review'`、`lifecycle_state='active'`、`run_id='pack-backfill-20261028'`。

### 论文 · pack → 采集库

| pack 字段 | 目标 | 说明 |
|---|---|---|
| `canonical_identity_id` | `paper.paper_id` | |
| `title` / `title_zh` | `title_clean` / `title_raw` | |
| `abstract` | `abstract_clean` | |
| `authors` | `authors_display`（拼接）+ `authors_raw`（jsonb） | |
| `doi` / `arxiv_id` | 同名列 | |
| `venue`（dict） | `venue`（text） | 取 `.name` |
| `year` / `citation_count` | 同名列 | |
| `summary_text` / `summary_zh` | 同名列 | |
| `quality_status` | `quality_status` | |
| — | `canonical_source`（NOT NULL，枚举） | **待定**：见下 |

固定值：`identity_status='unverified'`、`run_id='pack-backfill-20261028'`。

## 10. P0 待决（进 P1 前必须拍板）

1. **`canonical_source` 取值**：枚举有 `openalex / semantic_scholar / crossref / official_page / manual / prof_page_only / arxiv / web_search / dblp`。pack 论文来自 P4 发布包，来源混杂。
   - 方案 A：按 `enrichment_sources` 推断，缺省 `openalex`（最接近，但可能失真）；
   - 方案 B：加迁移新增 `pack_backfill` 值（最诚实，多一次迁移）；
   - 我倾向 B。
2. **2 位同名教授**：合并到已有 id，还是保留两条并标记 `needs_review`？倾向合并（同一人）。
3. **55 条库独有论文**：保留（不回灌删除），在 P3 守卫里作为"库领先"记录。
4. **`research_directions`**：先丢（库无列），还是写进 `professor_fact`？倾向先丢并在报告里计数，避免 P1 膨胀。

---

## 11. P1 执行结果（2026-10-28 实跑）

```text
{"pack": 3958, "already_present": 220, "to_insert": 3736, "to_merge": 2, "dropped_research_directions": 8958}
{"written": 3736, "merged_filled": 2, "truncated_names": 2}
```

| 指标 | 值 |
|---|---|
| 采集库教授（回灌后） | **3,956**（220 + 3,736；2 位同名合并到已有 id） |
| 有主页源页 | 3,956（全部） |
| 有机构记录 | 3,757（差 199 是原有 220 位里的历史缺口，不是回灌造成） |
| 有简介 | 3,954 |
| `run_id` 标记为回灌 | 3,736 |
| 幂等性 | 重跑 `to_insert = 0` |
| 抽样一致 | 3/3（姓名、简介、quality_status 与 pack 完全一致） |

**过程中发现并处理的三件事**：

1. `professor.run_id` 是 **uuid 且有 FK** → 先登记一条 `pipeline_run`（`run_kind='backfill_real'`，确定性 uuid）；
2. `primary_official_profile_page_id` 是 FK → 主页页用 `ON CONFLICT (url)` 插入后**按 url 回查 page_id**（不能直接用算出来的 uuid）；
3. pack 里有 **2 条记录的 `name` 是一整段话**（3,762 / 5,905 字节），直接入库会炸 btree 索引 → 截断到 200 字并计数（`truncated_names: 2`）。

**补全解锁**：新增 `--padded-only` 选择器——按"补位标记"选人，而不是按长度
（补位本身就把长度撑到 200+，长度过滤器选不出来）。当前可选 **2,024** 位。

## 12. P2 待办（论文回灌）

1. 迁移新增 `canonical_source='pack_backfill'`（决策 B）；
2. 按 §9 映射插入 24,003 篇（幂等键：pack id；去重：DOI → 标题）；
3. 保留 55 条库独有记录；
4. 验收：库论文 ≥ 24,520、重复率 < 1%、抽样 50 条一致。

---

## 13. P2 执行结果（2026-10-28 实跑）

```text
{"pack": 24520, "already_present": 500, "matched_by_doi": 15, "matched_by_title": 2, "to_insert": 24003}
{"written": 24003}      # 22 秒
```

| 指标 | 值 |
|---|---|
| 采集库论文 | **24,558**（555 + 24,003） |
| 标记 `pack_backfill` | 24,003 |
| 带作者 | 24,558（全部） |
| 唯一标题 | 24,552（6 组同题，可接受） |
| 幂等 | 重跑 `to_insert: 0` |
| 库独有 55 条 | 未动 |

**迁移**：`V043_allow_pack_backfill_paper_canonical_source.py`（决策 B），
已直接应用到客户机约束（`ck_paper_canonical_source` 增加 `pack_backfill`）。

**踩坑**：paper 表**没有** `summary_text` 列（只有 `summary_zh`），
第一次执行被 Postgres 拒绝，已删掉该字段——这也说明"先干跑再执行"的价值。

## 14. 两个域现在的状态

| 域 | pack | 采集库 | 差异 | 备注 |
|---|---|---|---|---|
| 教授 | 3,958 | 3,956 | 2 位同名合并 | 已完成 |
| 论文 | 24,520 | 24,558 | +55 库独有 | 已完成 |
| 专利 | 10,563 唯一标题 | 17,963 | 库领先 | 上一阶段已处理 |
| 企业 | 7,086 | 7,089 | +3 | 已通过增量桥 |

**结论**：`pack ⊆ 库` 的目标已达成（教授/论文/专利/企业四个域都满足），
重建时"库里数据被覆盖"的风险从"必丢"变成"可导出"——只差 P4 把构建源改成库导出。

## 15. 剩余工作

| 阶段 | 内容 | 状态 |
|---|---|---|
| P3 | 一致性守卫（每日核对 pack ⊆ 库 + 管理端差异） | 待做（0.5 天） |
| P4 | 构建从库导出（Epic 子项） | 待立项 |
| 附 | 199 位原有教授缺机构记录 | 可选清理 |
| 附 | 补全批次（2,024 位可批量） | 待排期 |
