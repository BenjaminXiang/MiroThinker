# 教授本地数据缺口台账（2026-10-26）

> 目标：把 q27/教授画像/论文反哺/创业角色能落地的本地数据补齐；不能核实的明确标记，
> 不编造。数据分三层：serving pack、collection PG、manual recall overlay。

## 1. q27 期望的 4 位教授

| 姓名 | pack | collection PG | manual overlay | 状态 |
|---|---|---|---|---|
| 柯文德 | 存在，模板 summary、无 directions | 不存在 | 已补：南科大、机器人/仿人机器人、邮箱 | 可用（实测“柯文德教授的研究方向”带本地 citation） |
| 刘桂良 | 不存在 | 不存在 | 已补：港中大深圳、具身智能/强化学习/机器人操作 | 数据已补；需名称命中 boost 才稳定召回 |
| 任尔夫 | 不存在 | 不存在 | 未补 | 公开搜索无稳定对应，**不编造** |
| 王强 | 存在，但方向是 HPC/AI 系统 | 不存在 | 未补 | 与“灵巧手”不同域，可能是同名；**不冒认** |

结论：4 人里 2 人可补（柯文德/刘桂良），2 人不可核实（任尔夫/王强）。
标准集 exact 4/4 不能靠编造达成；产品口径应按“有姓名+高校+方向+引用”验收。

## 2. 56 位主题教授

- pack 里有 56 位教授的 directions/summary 含“具身智能/灵巧手”；
- q27 修复后本地 professor 车道召回 147 条证据（exact 1 / lexical 62 /
  vector 21 / web 63），答案列 13 位教授 + 12 条 professor citation；
- 不需要把这 56 位全部复制到 manual overlay，pack 已可用；
- 缺口是 selector 的 claim window（21 条）没有覆盖全部 56 位，不是数据缺失。

## 3. 创业/公司角色

- collection PG `professor_company_role`：1 行；
- pack professor `company_roles`：0 位；
- manual overlay：丁文伯已补
  `company_roles=[{company_name: 深圳无界智航科技有限公司, role: 联合创始人、首席科学家}]`；
- 实测 `丁文伯还在哪些公司任职` → 答出无界智航 + company citation；
- 其余教授的公司角色未补；`pipeline_v3` 有 web search + company linking，
  但没有定时任务，也没有物化到 pack。

## 4. 论文链接与画像

| 层 | 数据 | 缺口 |
|---|---|---|
| collection PG | 200 professor / 555 paper / 55 link / 5 位教授 | 链接覆盖 2.5%；模板 summary 105/200（52.5%）；5 位链接教授 paper_count 全空 |
| serving pack | 3,958 professor / 24,520 paper / 10,742 links / 1,019 位教授 | paper 文档 `professor_ids` = 0；professor 文档无 `paper_ids/top_papers`；paper_count 235/3,958 |
| 关系图 | `professor_attributed_to_paper` 10,742 | 只可用于具名教授→论文，不用于主题检索/画像写回 |

## 5. 已做的数据修复

1. manual recall professor serializer 增加
   `email/homepage/paper_count/patent_count/education_history/work_history/awards/company_roles`；
2. 新增/更新教授记录：柯文德、刘桂良、弋力、丁文伯（含 company_roles）；
3. manual recall 名称命中 boost：查询包含记录 display_name 时给 1.0 分，
   避免短 query/长 profile 的向量分数低于阈值；
4. q27 主题教授守卫：不再把“有哪些…教授”误绑到公司，恢复本地 professor 车道；
5. 缓存命中 q27 0.06s，12 条 professor citations。

## 6. 仍需补的本地数据

1. **pack 物化**：把 `professor_paper_link` / `professor_company_role` 投影进
   professor 文档（`paper_ids/top_papers/company_roles`）和关系图；需要 pack 重建或 overlay。
2. **论文链接**：补英文名/ORCID/OpenAlex author ID；把 10,742 条关系变成
   `paper.professor_ids` 和 professor 的 `paper_count/top_papers`。
3. **画像写回**：论文主题→`research_directions`；web 创业角色→`company_roles`
   和 `profile_summary`；带 provenance 和质量门。
4. **模板清理**：105/200 PG professor 模板 summary；pack 54% 模板。模板不得作为
   检索证据，标 `needs_enrichment`。
5. **调度**：教授论文采集、创业角色 web search、画像更新、pack 重建，目前都没有
   客户定时任务。
6. **任尔夫/王强**：公开来源无法稳定确认，保持 unresolved，不写入假数据。

## 7. 验收

- 柯文德/刘桂良：按名查询可答，带本地 citation；
- 丁文伯：创业角色可答，带 company citation；
- q27：≥10 位教授、≥10 条 professor citations、答案含高校/方向；
- 56 位主题教授：selector 覆盖或明确“展示代表”；
- 模板 summary 占比下降（需要重建/overlay）；
- 链接覆盖率、paper 反查率、company_role 覆盖率按分析文档 P0–P3 验收。

## 8. 通用人名脏记录（2026-10-26 补充）

pack 里有 4 条 professor 记录的 canonical_name 是通用称谓：

- 教授 ×1、院士 ×1、讲师 ×1、副教授 ×1。

其中 canonical_name=`教授` 的记录（中山大学深圳，方向混有法学/流体力学）
会在查询“刘桂良教授的研究方向”时被 exact-name resolver 当作“教授”命中，
写进 protected slot，导致真正的刘桂良 manual 记录不被使用。

修复：`_entity_name_forms` 增加通用人名 blocklist
（教授/副教授/讲师/老师/教师/博士/研究员/院士），不再参与实体链接。
这是**通用称谓屏蔽**，不是按业务词表穷举。

重启后应验证：

- `刘桂良教授的研究方向` 不再绑定 `professor-c-256f...`（name=教授）；
- manual 刘桂良 记录通过名称命中 boost 进入答案。

## 9. 验证结果（2026-10-26 15:40）

- `刘桂良教授的研究方向` → 正确答出具身智能决策/强化学习、
  港中大（深圳）数据科学学院、EmbodiedChain，并带
  `professor 刘桂良` 本地 citation + 2 条 web citation；
  还主动提示同名人士，避免误认。
- `柯文德教授的研究方向` → 正确答出南科大、机器人控制/仿人机器人，
  带本地 professor citation。
- `有哪些做具身智能和灵巧手的教授` → 列出 18+ 位教授，含弋力、高庆、
  庞智博、罗健文、楼云江、黄锐、彭卫文、战强、徐刚、张世武、王宇、
  李秀、刘厚德、丁文伯、乔宇、陈华、胡靓、熊小刚、苗嘉旭等，
  12 条 professor citation，缓存命中 0.5s。
- `丁文伯还在哪些公司任职` → 答出深圳无界智航，带 company citation。
- 通用人名脏记录 `canonical_name=教授` 已通过 blocklist 屏蔽，
  不再劫持“刘桂良教授”类查询。

仍未补：

- 任尔夫：公开来源无稳定对应，保持 unresolved；
- 王强：pack 里是哈工大深圳 HPC 方向，与“灵巧手”不同域，不冒认；
- 张世武/徐刚等公司角色、论文链接、pack 物化、定时任务仍未做。
