---
title: 数据质量护栏 + LLM 身份对齐 Gate（Rounds 7.6 → 7.14）
date: 2026-04-18
status: active
owner: claude
extends:
  - docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
  - docs/plans/2026-04-18-002-real-data-e2e-and-db-separation.md
  - docs/plans/2026-04-18-004-admin-console-professor-and-ui.md
---

# 数据质量护栏 + LLM 身份对齐 Gate

## 0. 背景 / 触发

`miroflow_real` 跑通 admin-console 后（Round 8a，计划 004），发现数据质量远低于预期：

- **教授维度**：`教研团队` / `教研序列` / `About Us` / `Central Saint Martins` 被作为 canonical_name 入库；823 行中 ~30 行是页面导航文字；`canonical_name_en` 列充斥 `Energy Mater` / `Highly Cited Chinese Researchers` / `Cover Image` 这类期刊名/图注名。
- **论文维度**：OpenAlex 返回的 87 行"论文"实际是 CV 片段（`Ph.D. in Physics, ...`、`Fellow, AIMBE`、`Associate Editor, IEEE TBME`、`Workshop Co-Chair`）；1400 行 `official_page` 源抓取的论文 `authors_display` 全空；有 1460 行因 `run_real_e2e_paper_staging_backfill.py` 的 fallback 逻辑错误地被标成 `canonical_source='openalex'`（实际来自 `official_site` 抓取）。
- **教授 → 论文连接**：8287 条 `professor_paper_link`（6794 candidate + 1493 verified-by-rule_auto）几乎全部 `topic_consistency_score IS NULL`；抽样发现 40%+ 属于 **同名异人**、**作者根本不在 byline**、**非论文条目**（Technical Committee on ... / Principles and Applications of X 教材 / 引用串）。
- **研究主题维度**：`professor_fact(research_topic)` 中 259 行是整段句子碎片（`不同取食策略生物的耐热性，仍缺乏系统验证`）、残破引用（`《国家科学评论》（National Science Re`）或 `等）`结尾的分割错误，跟 dashboard 的 top-topics facet 一起暴露给用户。

核心结论：**规则过滤的增量永远跟不上 scraper 的新污染形态**。Gemma-4 在学校内网基本零成本，应该转成 **LLM-first / rule-as-prefilter** 架构。

## 1. 目标

1. 在 `miroflow_real` 把**已存在**的脏数据清干净，量化每类污染的规模。
2. 在 pipeline 的**写入层**加护栏，使重跑 backfill 不会再次引入相同形态污染。
3. 在 pipeline 的**收集层**（`paper_collector` / `openalex.py`）用 LLM 拦截同名异人和作者缺失，不再依赖下游过滤。
4. 产出 `topic_consistency_score` 让 dashboard / 未来 RAG 对每条链都有连续的质量信号。

非目标：不重跑完整 v3 采集流水线；不新增 schema 迁移（沿用现有列）。

## 2. 数据污染分类与当前量化（miroflow_real）

| 类别 | 量 | 代码来源 | 缓解 |
|---|---|---|---|
| 教授 canonical_name 是页面标题（教研团队 / About Us 等） | 31 行 DELETE | `name_selection.is_obvious_non_person_name` 旧版漏 | Round 7.8 扩展 denylist + 正则 |
| 教授 canonical_name_en 是期刊/图注/委员会（Energy Mater / Cover Image / Highly Cited Chinese Researchers） | 133 行 NULL | 同上，英文分支 | Round 7.8 `JUNK_NAME_TITLES_CASEFOLD` + `_looks_like_journal_or_topic_name` |
| 研究方向事实是句子碎片（`...仍缺乏系统验证` / `等）` / `《国家科学评论》（National Science Re`） | 259 行 deprecated | v3 抽取没校验主题形状 | Round 7.9 `professor/topic_quality.is_plausible_research_topic` |
| Paper 标题是 CV 片段（Ph.D., Fellow,, Associate Editor, Workshop, Research Area 开头或 `YYYY -` 前缀） | 87 行 DELETE（cascade 97 链） | `paper_staging` 抓到主页后没甄别 | Round 7.9 `paper/title_quality.is_plausible_paper_title` |
| Paper canonical_source='openalex' 但实际 source='official_site' | 1460 行 remap → `official_page` | `run_real_e2e_paper_staging_backfill.py` 有 fallback→openalex bug | Round 7.9 `_OFFICIAL_SOURCE_ALIASES` 映射表 |
| 教授→论文链是 OpenAlex 同名异人 | ~27% 被 gate 拒（~2300 行） | `paper_collector` 仅规则挑 author_id | Round 7.6 batch identity gate + Round 7.10' LLM author-id picker |
| 教授→论文链是作者不在 byline | ~17% 被 gate 拒（~1500 行） | 同上 | Round 7.6 identity gate |
| 教授→论文链是非论文记录（委员会 / 教材 / 引用片段） | ~12% 被 gate 拒（~1000 行） | 标题护栏没覆盖所有形态 | Round 7.6 gate + 未来 Round 7.12' |
| `professor_paper_link.topic_consistency_score` 全 NULL | 8287 行 | 从未计算过 | Round 7.14 gate prompt 顺手输出 |
| paper_collector `official_page` 源 paper.authors_display 空 | 1400 行 | scraper 没解析 author 段 | 未来 Round 7.15 |

## 3. Rounds 分解

### Round 7.8 — 教授姓名护栏（已完成）

**交付**：
- `src/data_agents/professor/name_selection.py`：
  - `JUNK_NAME_TITLES` 增 17 条（`教学平台` / `本科生` / `团学风采` / `行政人员` …）。
  - `JUNK_NAME_TITLES_CASEFOLD` 增 8 条（`About Us` / `View More` / `Central Saint Martins` / `Highly Cited Chinese Researchers` …）。
  - 新增 `_looks_like_journal_or_topic_name` 正则：`\b(journal|advances|mater|sciences|academia|society|transportation|...)\b` 的两词以上字符串拒掉。
- `tests/data_agents/professor/test_name_selection.py`：+22 条 parametrize cases，含反面断言（Connie Chang-Hasnain / Jianwei Huang 等真名不误杀）。
- `scripts/run_real_e2e_professor_backfill.py`：加 `is_obvious_non_person_name` 守卫 + `skipped_junk_name` / `nulled_junk_name_en` 统计；剥离 name 前导 `\u200b`。

**清理量（miroflow_real）**：809 → 778 教授（DELETE 31 行，FK CASCADE 到 affiliation / fact / paper_link / company_team_member）；NULL 133 条 `canonical_name_en`。

### Round 7.9 — 论文标题 + 研究主题护栏（已完成）

**交付**：
- `src/data_agents/paper/title_quality.py` — `is_plausible_paper_title`；~50 条 prefix 黑名单 + `^(19|20)YY\s*[-–—]` 年份前缀检测 + ASCII 短字符串 ≥3 token 要求。
- `src/data_agents/professor/topic_quality.py` — `is_plausible_research_topic`；80 字符上限 / 尾部标点拒 / `等` 结尾拒 / 不平衡括号拒 / meta 短语拒（`主要研究方向` / `仍缺乏` / `以及`）。
- 两个模块各 28-31 条 pytest（含负面断言：常见期刊中英文双语主题 `图像退化恢复 (Image Restoration)` 通过）。
- `scripts/run_real_e2e_paper_staging_backfill.py`：
  - 加 `is_plausible_paper_title` 过滤 + `skipped_implausible_title` 统计。
  - 新 `_OFFICIAL_SOURCE_ALIASES = {official_site, official_linked_orcid, official_linked_google_scholar}` → `canonical_source='official_page'`，替换原 fallback-to-openalex 逻辑。

**清理量**：87 paper DELETE（97 link cascade）、1460 paper canonical_source 重映射、259 research_topic `status='deprecated'`。

### Round 7.6 — 批量 LLM 身份 Gate（已完成代码，回填进行中）

**交付**：
- `src/data_agents/professor/paper_identity_gate.py` — 新模块：`ProfessorContext`（复用 `identity_verifier`）、`PaperIdentityCandidate`、`PaperIdentityDecision`、`batch_verify_paper_identity`。
  - Batch size 15 候选/次 prompt；保序输出；失败 fail-safe reject；空列表短路。
  - confidence < 0.8 拒（精确优先）。
- `src/data_agents/professor/paper_collector.py` — `enrich_from_papers` 加 `identity_gate_enabled` / `identity_gate_llm_client` / `identity_gate_llm_model` 参数；`_apply_identity_gate` 在 `official_site` 以外的源上过滤 `collection_papers`；gate 全错时保守保留不删。
- `scripts/run_identity_verify_candidate_links.py` — DB-driven backfill：
  - 按 professor_id 分组；`_load_context` 拉 affiliation.institution + top-12 research_topic；`_load_candidates` 拉 title/authors_display/year/venue/abstract_clean。
  - 接受 → `link_status='verified', verified_by='llm_auto'`，拒 → `link_status='rejected', rejected_reason=...`，保序，批提交。
  - 安全守卫：`miroflow_test_mock` 需 `ALLOW_MOCK_BACKFILL=1`；`--dry-run` / `--limit` / `--professor-id` / `--commit-every`。
  - LLM：默认本地 Gemma 4；`--use-online` 切 DashScope；自动清代理 env。
- `tests/data_agents/professor/test_paper_identity_gate.py` — 9 条 mocked-LLM 测试（accept / reject-threshold / explicit-no / parse-err / exception / batching / order-preservation / missing-decision / empty）。

**执行**：pg_dump-替代备份 `backups/professor_paper_link.pre-gate.20260418-070901.csv.gz`（8287 行），然后对 `miroflow_real` 全量跑。当前中期报告（480/622 教授，77%）：
- 3160 verified by llm_auto · 2867 新 rejected · 418 unchanged · 533 旧 `rule_auto` 被降级为 rejected（这部分是真正被 gate 抓住的老规则污染）。
- 拒绝率 ~47%，与干跑估计 31% 相比更高——说明规则 tiebreaker 选 h-index 高的候选在同名场景反而偏离目标。

### Round 7.10' — LLM author-id picker（已完成）

**动机**：`paper_collector` 走 hybrid sources 时，OpenAlex/SS/Scholar 的 author_id 解析目前是纯规则：`name_match * 3 + institution_match + h_index + citations + works_count` 的加权排序。规则在 **name_disambiguation_conflict** 场景只靠 h-index 打破平局——当同名学者中有一位更有名但不在目标机构时，规则选错、下游全错。LLM 在候选列表上做领域 + 机构 + topic 综合判断天然更准。

**交付**：
- `src/data_agents/paper/author_id_picker.py` — `AuthorCandidate` / `PickerDecision` / `pick_author_id()`。
  - 输入：target 姓名 / 机构 / 研究方向 + 候选列表（display_name, alt, institutions, topics 前 6 项, works_count, cited_by_count, h_index）。
  - 输出：`accepted_author_id` or `None`；confidence < 0.75 一律返回 None。
  - Fast-path：单候选且机构字符串重叠 → 免 LLM 直接采用。
- `src/data_agents/paper/openalex.py`：
  - `discover_professor_paper_candidates_from_openalex` 接收 `author_picker` + `target_research_directions` 参数。
  - 当 `candidate_count >= 2` 无条件调 picker（**不**再依赖 `name_disambiguation_conflict` 标志，因为规则的 h-index tiebreaker 会掩盖真正的冲突）。
  - picker 返回的 author_id 覆盖规则选择；picker 返回 None → 直接放弃 author_id（`/works` 都不调）。
- `src/data_agents/paper/hybrid.py` + `src/data_agents/professor/paper_collector.py`：参数向上透传。`paper_collector` 用 `official_directions` 作为 `target_research_directions`。
- `src/data_agents/professor/pipeline_v3.py`：闭包 `author_picker` 绑定 `resilient_client` + `local_llm_model`，一次性接入 v3 流水线。
- 12 条测试：
  - `tests/data_agents/paper/test_author_id_picker.py`（9 单元测试）
  - `tests/data_agents/paper/test_openalex_picker_integration.py`（3 集成测试验证规则路径被覆盖、picker-None 导致空结果、单候选跳过 picker）。

### Round 7.14 — topic_consistency_score 打分（已完成代码，二次 backfill 待跑）

**动机**：`professor_paper_link.topic_consistency_score` 列在 schema 中存在但全 NULL。既然 gate 每条论文都在跟教授研究方向比，顺手让 LLM 输出 0-1 连续分（`1.0` 完全吻合 / `0.7` 子方向不同 / `0.3` 仅领域交集 / `0.0` 无关）就行。

**交付**：
- `src/data_agents/professor/paper_identity_gate.py` — prompt 新增第 6 条规则 + 输出 schema 增 `topic_consistency` 字段；`_PaperDecision` / `PaperIdentityDecision` 加 `topic_consistency: float | None = None`（向后兼容，LLM 漏字段时 None）。
- `scripts/run_identity_verify_candidate_links.py`：
  - `_apply_decision` 三个分支（promoted / rejected / unchanged）都 `UPDATE professor_paper_link.topic_consistency_score`。
  - 新 `--backfill-topic-scores` 模式：只对 `link_status='verified' AND topic_consistency_score IS NULL` 的 prof 再跑一遍 gate，把分数补上，决定本身不变。
- `apps/admin-console/backend/api/data.py`：
  - `PaperSummary` + `LinkedProfessorSummary` 加 `topic_consistency_score: float | None = None`。
  - `PROFESSOR_TOP_PAPERS_SQL` + `PAPER_LINKED_PROFESSORS_SQL`：`ORDER BY topic_consistency_score DESC NULLS LAST, ...`；教授详情页自动按主题贴合度排论文。
- 12 条 gate 测试里加 3 条新断言（分数 parse / 默认 None / 拒绝时保留分数）。

**执行状态**：当前运行的 gate 是在 prompt 改前启动的，不会产生分数；等它收尾后立即 `--backfill-topic-scores` 二次跑。

## 4. 沉淀的工程决定（不再反复）

1. **LLM-first 架构**：本地 Gemma 免费后，pipeline 的身份 / 标题 / 主题判断从"规则优先+LLM兜底"翻转为"LLM 主判+规则预过滤"。参见 `memory/feedback_data_quality_guards.md`。
2. **Gate 必须无条件上场**：规则层 `name_disambiguation_conflict` flag 依赖 h-index tiebreaker，会掩盖真冲突。任何 `candidate_count >= 2` 都交给 LLM。
3. **Fail-safe = reject**：LLM 调用失败、JSON 解析失败、无决定 → 都拒绝。同 `identity_verifier` 策略，precision > recall。
4. **single-candidate fast-path**：`pick_author_id` / `paper_identity_gate` 都有「单候选且机构命中」的免 LLM 路径。既省调用也避免 LLM 给零分歧场景画蛇添足。
5. **安全守卫**：backfill 脚本默认拒写 `miroflow_test_mock`，需 `ALLOW_MOCK_BACKFILL=1`（pytest fixture 已设）；写 `miroflow_real` 之前必须先 CSV 备份（`backups/professor_paper_link.pre-gate.*.csv.gz`）。
6. **sourced 源别名**：`paper_staging.source` 的 `official_site` / `official_linked_orcid` / `official_linked_google_scholar` 全部映射到 `canonical_source='official_page'`，不再误落 openalex。

## 5. 当前状态检查清单

- [x] Round 7.8 name guard 代码 + 测试 + miroflow_real 清理
- [x] Round 7.9 title / topic guard 代码 + 测试 + miroflow_real 清理 + 源别名修正
- [x] Round 7.6 gate 模块 + 测试 + backfill 脚本 + paper_collector 注入
- [x] Round 7.6 backfill 对 miroflow_real 启动并已过 ~77%
- [x] Round 7.10' author-id picker 模块 + 测试 + openalex/hybrid/paper_collector/pipeline_v3 注入
- [x] Round 7.14 gate prompt 扩展 topic_consistency + script `--backfill-topic-scores` 模式 + admin-console API 暴露
- [ ] Round 7.6 backfill 完成（剩 ~142 教授，ETA ~15 分钟）
- [ ] Round 7.14 `--backfill-topic-scores` 对 verified 链二次跑（ETA ~40 分钟）
- [ ] Backend restart（已做）+ `/browse` 前端页加 topic_consistency 列展示（可后续）

## 6. 非本轮事项（列入后续）

- **Round 7.12'**：LLM title 分类器兜底，处理当前护栏漏掉的委员会/教材/引用串。
- **Round 7.15**：1400 行 `official_page` 源 `authors_display` 空的论文，用 LLM 从原始抓取片段重新解析 author 列表，填回字段并再跑 gate。
- **Round 7.13**：等 7.10'/7.14/7.15 验证稳定后，把 `identity_gate_enabled=True` 从 opt-in 改默认开。
- **Same-name dedup**：`Jianwei Huang` / `黄建伟` 在 `miroflow_real` 有两条 professor 行，应在 `professor` 主键策略里加基于 (canonical_name, institution, email) 的人工复核流程，不在本计划内。

## 7. 参考

- `memory/feedback_data_quality_guards.md`（工作流模板）
- `memory/feedback_web_search_identity.md`（0.8 confidence 阈值来源）
- `memory/feedback_proxy_llm.md`（Gemma / 代理环境）
- `docs/plans/2026-04-17-003-professor-official-anchor-first-paper-disambiguation-plan.md`（规则路径的原始设计，本计划中被 7.10' 覆盖）
