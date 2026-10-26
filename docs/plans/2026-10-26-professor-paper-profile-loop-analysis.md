# 教授画像 × 论文反哺：实现审计与差距分析（2026-10-26）

> 对应需求：`docs/Agentic-RAG-PRD.md:317-327`、`docs/Data-Agent-Shared-Spec.md:503-507`
> 结论：**代码骨架存在，但闭环没有接通；离“论文持续更新教授画像”还有明显距离。**

## 1. PRD 要求

PRD 写得很明确：

- 论文模块不仅是独立检索，也是**教授画像更新的重要来源**；
- 周期性论文采集以**深圳教授 roster** 为起点；
- 论文作者如果是已收录教授，**必须建立关联**；
- 论文结果需要**反向补充**教授 `research_directions` 和 `profile_summary`。

## 2. 代码实现地图（已有什么）

| 环节 | 代码 | 实际作用 |
|---|---|---|
| 论文发现 | `professor/paper_collector.py` | OpenAlex / ORCID / Google Scholar / CV / hybrid 多源发现，身份门，LLM 聚类出 `research_directions`、`top_papers`、staging records |
| 论文→画像 | `professor/batch_reprocess.py` Stage 2b | 调 `enrich_from_papers`，更新内存中的 `research_directions`、h_index、citation_count、paper_count、top_papers |
| 画像落盘 | `batch_reprocess._update_store_with_enriched` | 写 enriched JSONL + **SQLite released-object store**，不是 PG，也不是 serving pack |
| 论文关联写库 | `professor/canonical_writer.py` | 可以从 `paper_staging` 写 `professor_paper_link` |
| pack 关系 | `canonical_v2/knowledge_build_isolated.py` | 从 author alias 派生 `professor_attributed_to_paper`，并合并 P4 显式 links |
| 服务消费 | `knowledge_read_isolated.py` | 只有**具名教授→论文**的 `professor_authored_paper` 路径 |

## 3. 数据实测

### 3.1 客户 collection DB（`miroflow_collection_v1`）

| 指标 | 数值 |
|---|---|
| professor | 200 |
| paper | 555 |
| professor_paper_link | **55** |
| 有论文链接的教授 | **5** |
| link 证据来源 | 全部 `prof_homepage_tier2` |
| 模板 summary | **105 / 200（52.5%）** |
| 有 `paper_count` 的教授 | 11 |
| 5 位有链接教授的 `paper_count` | 全部 NULL |
| professor_patent_link | 0 |

5 位有链接的教授里，4 位的 summary 仍是模板或与论文无关；有 19 条链接的彭珏、16 条的杨世和、15 条的仉晶晶，`paper_count` 仍为空。

### 3.2 客户 serving pack

| 指标 | 数值 |
|---|---|
| professor | 3,958 |
| paper | 24,520 |
| `professor_attributed_to_paper` | 10,742 条 / 1,019 位教授（25.7%） |
| professor 有 `paper_count` | 235 / 3,958（5.9%） |
| paper 有 `professor_ids` | **0 / 24,520** |
| professor 有 `paper_ids` / `top_papers` | 0 |
| 研究方向含“具身智能/灵巧手”的教授 | 56 |
| 抽样 30 位有论文链接的教授 | 30/30 有 directions + 非模板 summary |

结论：**有关系图，没有投影**。10,742 条链接只存在于 `relationships.json`，没有进入 paper/professor 的 lookup 文档，所以主题检索和画像更新都用不上。

## 4. 断点分析

1. **流水线不接服务**
   `batch_reprocess` 写 SQLite released-object store/JSONL，不写 PG collection DB；没有定时任务；pack 构建用的是另一份 P4 快照。论文反哺的结果到不了客户服务包。

2. **链接不物化**
   `professor_paper_link` 只有 55 条 / 5 位教授；pack 有 10,742 条关系，但 paper 文档没有 `professor_ids`，professor 文档没有 `paper_ids`/`top_papers`。链接只能用于“具名教授→论文”，不能用于“按主题找教授”或画像更新。

3. **作者身份对不上**
   professor 文档只有中文名/别名；paper 作者是英文名。丁文伯/王学谦/柯文德/王强的中文名在 paper authors 里 0 命中；没有 ORCID/OpenAlex author ID 作为桥。10,742 条链接更可能来自 P4 显式锚定，而不是实时 alias 派生。

4. **画像写回不完整**
   `batch_reprocess` 更新 `research_directions`，但**不更新 `profile_summary`**；PRD 要求两者都反哺。pack 的 summary 主要来自官网，不是论文。

5. **质量门缺失**
   52.5% 的 summary 是模板重复；模板仍被当作 profile 文本索引。柯文德就是典型：记录存在、方向为空、summary 模板，所以主题检索永远命中不了。

6. **论文采集路径过窄**
   客户 DB 的 55 条链接全部是 `prof_homepage_tier2`，说明多源论文发现（OpenAlex/ORCID/Scholar/CV）没有在客户数据上真正落地；目前只覆盖了官网列出的论文。

7. **没有主题检索车道**
   pack 里有 56 位带“具身智能/灵巧手”文本的教授，但 q27 的本地 professor 车道没有把他们变成候选；只有具名教授→论文路径，没有“按论文主题找教授”。

## 5. 离目标还有多远

| 目标 | 当前 | 差距 |
|---|---|---|
| 教授有论文链接 | pack 25.7%；collection 2.5% | 覆盖不足 |
| paper 可反查教授 | 0% | 投影缺失 |
| professor 有 paper_count | 5.9% | 画像指标缺失 |
| 论文反哺 research_directions | 代码有，客户数据不可见 | 未闭环 |
| 论文反哺 profile_summary | 无 | 未实现 |
| 模板 summary 清理 | 52.5% 仍是模板 | 质量门缺失 |
| 按主题找教授 | 56 位有文本但未召回 | 检索车道缺失 |

**判断：** 不是“算法没写”，而是“身份、链接、投影、写回、调度”五段没有接成一条链。离目标不是一步，而是一个数据闭环切片。

## 6. 目标架构（闭环）

```text
教授 roster + 中英文名/ORCID/OpenAlex/邮箱
        ↓ 身份归一
paper authors → author identity（ID，不靠字符串）
        ↓ 证据化链接
professor_paper_link（homepage/OpenAlex/ORCID/Scholar/CV，confidence/status）
        ↓ 双向物化
paper.professor_ids  +  professor.paper_ids/top_papers/paper_count
        ↓ 主题信号
paper title/abstract/keywords → research_directions（paper_driven/merged）
        ↓ 质量门
模板检测 / 证据要求 / needs_enrichment
        ↓ serving 投影
professor research vector 包含论文主题；topic retrieval 可用论文证据
        ↓ 定时任务
周/月 roster 增量采集 → 链接校验 → 画像更新 → pack 重建/overlay
```

## 7. 修复顺序

**P0：链接与身份**
- professor 补英文名/别名/ORCID/OpenAlex author ID；
- paper authors 归一为 author ID；
- `professor_paper_link` 双向物化；
- 链接覆盖率、证据来源、置信度可观测。

**P1：画像写回与质量门**
- 从链接论文抽主题词，更新 `research_directions`，按 `paper_driven/merged` 记录 provenance；
- 生成/更新 `profile_summary`，但不得覆盖官方事实；
- 模板 summary 检测，标 `needs_enrichment`，不进入检索证据；
- 重建 professor research 向量。

**P2：主题检索与答案**
- “有哪些做 X 的教授”走 professor research vector + lexical + paper topic；
- 本地候选优先，web 补充；
- 答案列“姓名+高校+方向+论文证据”。

**P3：调度与验收**
- 定时任务：roster 增量论文采集、链接校验、画像更新、pack 重建；
- 指标：链接覆盖率、纸→教授反查率、画像更新率、模板率、topic recall@20、q27 答案质量。

## 8. 验收指标（建议）

- `professor_paper_link` 覆盖 ≥ 60% 的活跃教授；
- `paper.professor_ids` 反查覆盖 ≥ 60% 的已链接论文；
- 模板 summary 占比 < 10%；
- 有论文链接的教授 `paper_count` 覆盖率 ≥ 90%；
- q27 本地 professor 候选 recall@20 ≥ 0.6（以 56 位主题教授为参考集）；
- 答案列出 ≥3 位教授，含姓名、高校/院系、方向、citation。

## 9. 证据

- collection DB 查询：200 professor / 555 paper / 55 link / 5 distinct professor / 105 template summary。
- pack 查询：3,958 professor / 24,520 paper / 10,742 links / 0 paper.professor_ids / 235 paper_count / 56 topical professors。
- 关系文件抽样：`professor_attributed_to_paper` 存在，source/target 为 canonical professor/paper；首条即丁文伯→论文。
- 代码路径：`paper_collector.py`、`batch_reprocess.py`、`canonical_writer.py`、`knowledge_build_isolated.py`、`knowledge_read_isolated.py`。

## 10. 教授创业/公司角色补全（web search）

用户要求：收集教授信息时要充分 web search 补全创业/公司角色，并更新画像。
代码里有这条链，但没有进入客户定时任务，也没有物化到 serving pack。

### 10.1 代码地图

| 环节 | 代码 | 作用 |
|---|---|---|
| 全量流水线 | `professor/pipeline_v3.py` Stage 7–8 | Web Search + Identity Verification → Company Linking → 双向写库 |
| 搜索补全 | `professor/web_search_enrichment.py` | 搜索教授信息、抓页面、身份校验、抽 `CompanyMention` |
| 角色校验 | `professor/company_linker.py` | LLM 校验“教授—公司—角色”，输出 `CompanyLink` |
| 双向写库 | `professor/cross_domain_linker.py` + `link_backfill.py` | 写 `professor_company_role`，回填 company |
| 手动入口 | `admin-console/backend/api/upload.py` | `/upload` 教授导入调用 `pipeline_v3` |

### 10.2 数据现实

- collection DB `professor_company_role`：**1 行**；
- serving pack professor 文档 `company_roles`：**0 位教授**有值；
- pack 关系图 `professor_company_role`：仅 1 条；
- 定时任务只有：
  - `professor-homepage-rescrape`（每月 1 日，主页 bio）；
  - `professor-homepage-paper-ingest`（每月 1 日，主页论文/专利）。
- **没有**“教授创业/公司角色 web search”定时任务；`pipeline_v3` 只被 `/upload` 手动导入调用，不是 roster 刷新。

### 10.3 断点

1. **未调度**：web search + company linking 只在 pipeline_v3 里，客户机没有对应 cron/admin job。
2. **未物化**：即使写了 `professor_company_role`，pack professor 文档 `company_roles` 仍为空；关系图只有 1 条，服务端答案拿不到“联合创始人/首席科学家”等角色。
3. **画像不更新**：`company_roles` 没有进入 `profile_summary`，也没有“创业经历”字段；摘要生成不保证覆盖。
4. **证据/质量门缺失**：没有角色证据 URL、置信度、人工复核状态；同名教授（王强）容易把别的公司角色挂错。
5. **成本/配额未控制**：全量 roster web search 需要搜索配额和 LLM 校验预算；当前没有分批/低信号优先策略。

### 10.4 修复建议

- 新增 `professor-entrepreneurship-enrich` 定时任务：
  - 优先级：低学术信号、无公司角色、近期主页有创业关键词的教授；
  - 查询模板：“姓名 + 创业/创始人/联合创始人/首席科学家/公司”；
  - 身份校验 + LLM 角色校验 + 证据 URL；
  - 写 `professor_company_role`，同时更新 professor 文档 `company_roles` 和 `profile_summary`（带 provenance）；
  - 分批限额、失败重试、人工复核队列。
- pack 构建把 `professor_company_role` 投影到 professor `company_roles` 与关系图；
- 答案 claim 渲染所有角色（已支持非 founder 角色），并带公司 citation；
- 验收：company_role 覆盖率、抽样正确率、pack 可见角色数、`丁文伯创办的公司`/`他还在哪些公司任职` 类问题。

## 11. 2026-10-26 数据桥实测

为了先让画像数据可见，做了两件事：

1. `canonical_v2_manual_recall.py` 的 professor serializer 增加
   `email/homepage/paper_count/patent_count/education_history/work_history/awards/company_roles`；
2. 新增/更新人工教授记录：刘桂良（港中大深圳，具身智能/机器人操作）、
   弋力（清华交叉信息院，通用灵巧操作）、柯文德（南科大，机器人/仿人机器人）、
   丁文伯（补 `company_roles=无界智航 联合创始人/首席科学家`）。

实测：

- `丁文伯还在哪些公司任职` → 答出深圳无界智航，带 company citation。
- q27 → web lane `in=77 / retained=77 / filtered=0`，但 trace 只有
  web+relationship，**没有本地 professor 车道**，所以 4 条人工教授记录
  没有被召回；`citation_count=0`，答案仍是“没有可确认名单”。

结论：数据桥和门层都已就绪，q27 的下一个阻塞是**检索计划没有 professor
topic 车道**（以及 web 未绑定证据的答案装配）。这不是再加几条教授记录能解决的。

## 12. q27 的真正上游：`_standalone_anchor` 把主题问法当成公司关系

打开 `CANONICAL_V2_TURN_DEBUG_DIR` 后，q27 的 turn-debug 显示：

- `planned_displayed_ids: []`
- `protected_slots: displayed_entity_set = ["company-c-ab6cedefcc559de20fce271a"]`
  —— 正是浙江灵巧智能科技有限公司；
- `requested_traversal: company_to_professor / professor_company_role`；
- `lane_timings: relationship + web`；
- `evidence_items.total = 0`，`citations = 0`。

根因在 chat 的 `_standalone_anchor`：

- 查询含“教授”，命中 `_COMPANY_PROFESSOR_MARKERS`，target 被设为 company；
- 调 exact-name resolver(`query, "company")`；
- resolver 的实体名索引从 alias `灵巧智能` 派生出 2 字形式 `灵巧`，
  在“灵巧手”里命中，返回浙江灵巧智能；
- 该 company 被写入 planning `displayed_entity_ids`/protected slot；
- planner 因此走 `company_to_professor` 关系路径，**不跑 professor topic 车道**；
- 关系路径没有该公司的 professor_company_role，evidence=0，答案只能编泛化话术。

这解释了为什么加教授记录、修 web gate 都没用：问题发生在 planning 之前。

修复（已部署）：

- `_standalone_anchor` 增加主题教授守卫：含“教授”+“哪些/谁/有哪些/列出”、
  且不含“公司/企业”时，不做 named-company anchor；
- 仍需 P1：实体名索引不再合成 2 字派生形式，防止其他主题词被同样劫持。

### 12.1 修复结果（2026-10-26 15:02）

`_standalone_anchor` 增加主题教授守卫后，q27 的 turn-debug：

- `planned_displayed_ids: []`，`protected_slots: []`，`requested_traversal: None`；
- evidence **147 条，全部 professor**：exact 1 / lexical 62 / vector 21 / web 63；
- 本地 84、web 63，**147/147 有 claim_binding**；
- admitted claims **21**（canonical_projection 11、current_web_result 8、semantic_recall 2）；
- lane timings：exact 0.26s / lexical 0.60s / vector 1.03s / web 3.57s。

答案：1114 字，列出弋力、高庆、庞智博、罗健文、楼云江、黄锐、彭卫文、战强、
徐刚、张世武、王宇、李秀、刘厚德等 13 位教授，含高校/方向；
public citations **12 条 professor**，无公司污染。缓存命中 0.06s。

仍有两个缺口：

1. **标准集 exact 0/4**：答案没有逐字命中柯文德/任尔夫/王强/刘桂良。
   柯文德/刘桂良是人工记录但未被选进答案；任尔夫/王强不在 pack 或同名错域。
2. **多轮“他们分别在哪所高校”** 仍答“没有可对应对象”。缓存 payload 有
   displayed_result_set + 15 个 displayed_ids，但 follow-up 的集合指代没有
   被答案装配使用；这是下一刀（set referent 绑定/答案）。

产品层 q27 已从“没有名单”变成“13 位教授 + 12 引用”的 80 分答案；
标准集层仍是 0/4，两个口径要分开看。
