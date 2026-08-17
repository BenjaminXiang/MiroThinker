# Serving-pack 覆盖审计（链路审计第一块）

Date: 2026-08-17. Mode: read-only audit of `/var/tmp/mirothinker-canonical-v2-s12f/
serving-pack/`（生产 18188 正在服务的索引）。Trigger: 用户问"四个本地库在检索
生成中有没有被检索、表结构是否支持检索"。

## 结论速览

1. **每轮都在查本地库**（exact/structured/lexical → lookup.sqlite3；vector →
   Milvus Lite 每域一 collection；关系遍历 → relationships.json）——工序 3
   的机器在转。
2. **但被查的"本地库"只是四个域库的一小部分、且是旧快照**——服务索引
   2026-08-01 从 `logs/data_agents/released_objects.db`（旧发布快照）一次性
   构建后从未刷新；用户所说的当前四域库（Postgres）数据从未流入。

## 覆盖对照（服务索引 vs 当前本地四域库）

| 域 | 服务索引内 | 本地库（Postgres） | 占比 | 备注 |
|---|---|---|---|---|
| 企业 | 1,737 | 6,514 | 27% | |
| 教授 | 1,428 | 3,387 | 42% | |
| 专利 | 1,931 | 11,408 | 17% | **是旧 ready 集**；类型推断后的 11,408 未进入 |
| 论文 | **563** | 97,774 | **0.6%** | 论文域在服务索引里几乎不存在 |

另：person / technology_concept / technology_route 投影为 0 行；向量库
point_count 与 lookup 一致（company 1737 / paper 563 / patent 1931 /
professor 1428×2）。

## 关系图覆盖

- professor_attributed_to_paper: 3,421
- patent_has_applicant: **727**（全部公司↔专利链路）
- professor_company_role: **7**
- 其余关系类型各 1–2 条（注册表样本级）

## 直接定案

- **P5（优必选专利外甩）归因关闭：数据缺失。** 优必选（company-c-64e631c0…
  在 lookup 中存在）在关系图中的专利链路 = **0 条**；服务索引专利域只有旧
  1,931 条且仅 727 条公司关联。"该公司的专利有哪些"在当前服务索引上无数据
  可答——检索/合成层无罪，兜底话术（外甩）仍单列为缺陷。
- **P8（具身智能清单缺龙头）部分归因**：本地企业域仅覆盖 27%，本地通道贡献
  弱，答案被 web 榜单主导；词汇错位（人形机器人 vs 具身智能）为次因（待审）。
- 论文域 0.6% 覆盖 ⇒ "X 教授的论文"类查询本地基本无米下锅。

## 对"应该怎么来"（管线设计）的含义

- 工序 3 之前需要一道**数据供给/新鲜度工序**：本地 Postgres 四域 → canonical
  restore → serving pack rebuild 的管道必须可定期执行（当前是一次性 08-01
  快照）。这是我此前判断"legacy 数据侧修复只有新 accepted restore + rebuild
  才能进 V2"的实证。
- 结构（投影信封/eligibility/血统哈希/每域 collection）可保留——瓶颈是内容
  与关系覆盖，不是表结构设计。
- 补数优先级建议：① 论文域（0.6%）；② company↔patent 关系链（727，legacy
  11,408 条专利均有申请人可回填）；③ 企业全集（27%）；④ 教授（42%）。
