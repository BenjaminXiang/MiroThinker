# 检索增强优化 — 整轮综合总结 (2026-07-01 ~ 2026-07-02)

> 覆盖:eval 体系建立 → 检索逻辑修复 → 数据增强 → 根因梳理 → 教授数据质量修复 → merge 脚本修复。
> 所有产出已 commit;eval 是真值底座,每个修复 eval 可量。

## 一、Eval 体系建立(真值底座)

**为什么先建 eval**:没有可信测评,每个修复都是凭推断打补丁——而且已经踩过坑(eval env 缺 SERPER_API_KEY → 测出 58%/Serper-dead 假数字,实际 Serper 活的、recall 63%)。

**建成**:
- `parse_testset.py`:xlsx 42 行金标 → `test_cases.yaml`(25 case,多轮分组,短核心 required)。
- `eval_answer.py`:三层评估——L1 必需实体(deterministic)+ L2 禁出实体(deterministic)+ L3 六维 PRD judge(异模型 claude-sonnet-4-5,N/A-aware)。
- `eval_regression.py`:golden baseline + 退出码(L1/L2 回归或 L3 跌破 → 1)。
- `badcase_to_case.py`:web+LLM 生成 GT + 用户审 → 入集。
- `eval_env.sh`:从运行后端加载 SERPER_API_KEY + ANTHROPIC_* + unset 代理(env 真值,不再有假数字)。
- L1 标注 pass:LLM 起草 16 case required → 24/27 覆盖。
- L3 judge 校准:provenance/key_content 的 N/A 规则修正。

**关键纠正**:Serper 活的(key 有效,直连 200)——"Serper 死"是 eval env 缺 key 的假象;真实 recall 63%(带 web,达 acceptance),非 58%。eval env 真值是硬约束。

## 二、检索逻辑修复(4 个缺口,eval 验证)

| 缺口 | 根因 | 修复 | eval before→after |
|---|---|---|---|
| **FM5 法本** | 分类器无"X公司产品/团队"规则 + _extract_a_name 不剥后缀 + lookup_company exact/漏 registered_name | A-company 规则 + 剥 profile 后缀 + 切"这家公司" + _normalize_company_name + registered_name | unknown→A_company_profile, L3 0.00→0.70 |
| **qid11 pFedGPA** | 裸英文论文标题漏规则 → LLM 误拒 | 确定性 A_paper 规则(长 ASCII) | 路由 3/3 确定, L1 5/5 |
| **qid14 华力创** | 多从句查询 _extract_a_name 返回整串 | 切"这家公司"隔离公司名 | unknown→A_company_profile, L3 0.00→0.83 |
| **FM4 教授跨域** | professor 向量召回弱;paper→professor SQL 有但没在 topic 路径调 | _lookup_professors_by_topic 加 paper→professor rescue(按论文数排序) | 0 教授→召回教授, L3 0.00→0.10 |

## 三、数据增强(链路打通)

**第一性原理**:数据"检索就绪"= ready + 嵌入 Milvus。缺口:paper ~75%、professor ~69% 未就绪。

**链路 PROVEN**(abstract→summary→promote→embed,全用已有机制 + 2 新脚本):
- `backfill_embodied_abstracts.py`:abstract 回填(Crossref title-search,0.6 阈值拒误匹配)。4/24 done,20 卡 OpenAlex 503/arXiv 429(环境限流)。
- `summarize_papers_zh.py`:LLM summary_zh(claude-haiku via zenmux)。
- promote(UPDATE ready)+ embed(`run_milvus_backfill`)。5 篇走完全链路(嵌 8 chunks,0 错)。**milvus 单写约束没复现**(后端跑着也能嵌)。

## 四、根因梳理(7 主题 A-G)

| 根因 | 缺口 | 本本修复 |
|---|---|---|
| A. 分类器=脆弱 pattern-list + LLM 兜底 | FM5/qid11/qid14 | 归一化优先路由/训练分类器 |
| B. 召回=单域隔离,不遍历图谱 | FM4 | 图感知多跳召回 |
| C. 名匹配=刚性 | FM5(company) | 全类型归一化+模糊 |
| D. 数据未就绪(~70-75%) | 柯文德论文+教授 | 规模化 promote+embed |
| E. 外部限流(OpenAlex 503/arXiv 429) | D1 论文 abstract + D2 教授 metrics | 轮换 IP/polite-pool |
| F. 采集缺口 | FM1a(6 缺失) | ingest workstream |
| G. eval/harness 缺口 | 多轮 coref(单轮)+ L3 方差 | session harness + L3 平均 |

**系统洞察**:FM4 是 A+B+D 交汇;E 一个环境因堵 D1+D2 两条;A/B/C 症状层补了,根还在;D 是最大召回天花板。

## 五、Path 1 教授数据质量修复(绕过 E)

**关键纠正**:教授 ready gate **不查 h_index**(红鲱鱼)。GT-4 卡在**异质本地问题**:
- 柯文德:`duplicate_verified_paper_links`
- 任尔夫:`external_blocking_issue` + `field_contradiction` + `shallow_profile`
- 王强:`profile_summary_too_short` + `missing_research_overview_zh`
- 刘桂良:`external_blocking_issue` + `field_contradiction`

**王强闭环 PROVEN**(qid27 0/4 → 1/4 GREEN):
1. gate-fix:LLM regen profile(31→276字,含具身/灵巧手)+ INSERT research_overview section。
2. promote + embed profile(`--collection professor_profiles`——关键!`--domain professor` 只写 split,不写 retrieve 读的 unified)。
3. embed 他的 2 篇 ready 论文(rescue 靠论文找作者)。
4. qid27 王强 HIT(2 次稳定)。

**核心洞察**:教授 GREEN 需嵌 **profile + 论文**两者;embed 要用 `--collection professor_profiles`(unified)。

## 六、merge 脚本修复(解柯文德 dedup)

**深层根因**:`run_paper_exact_title_dedup.py` line 108 的 `LIKE '10.48550/arxiv.%'` 在 **psycopg3** 下炸——psycopg3 **只在传 params 时扫 `%` 占位符**(空 tuple 也触发),LIKE 字面量的 `%'` 被当非法占位符。psycopg2 容忍此;psycopg3 严格。这是 psycopg2→3 迁移的隐式行为变化。

**修复**:LIKE 通配符 `%` → `%%`(标准 psycopg 转义)。dry-run 27 组 / 0 false-merge;apply 27 merges + 27 aliases。

**柯文德结果**:dedup 解了 → gate 清 → ready → profile 嵌入。但 **qid27 柯文德仍未浮出**——他的具身论文全 needs_enrichment(E 限流未嵌)→ rescue 够不到;profile 即使加了"具身智能"关键词也排不进 top-10(有更直接的教授竞争)。**柯文德 GREEN 需论文嵌入(E-blocked)**。

## 七、commit 清单

| commit | 内容 |
|---|---|
| eval 体系(6 任务 TDD)| parse_testset/eval_answer(L1L2L3)/eval_regression/badcase_to_case/eval_env + baseline |
| `f052646` | FM5 法本 名变体路由+lookup |
| `0f09256` | qid11 英文论文标题规则 |
| `4dd21d1` | FM4 跨域 paper→professor rescue |
| `4416fed` | qid14 多从句名提取 |
| `9195f83`+`b14ffda` | parse_testset(短核心 required + 去 marker) |
| `13492c0` | L3 judge(六维 + N/A-aware) |
| `968b71e` | eval_regression gate |
| `e292c1a`/`2c6aa19` | summarize_papers_zh / backfill_embodied_abstracts |
| `9c2df14` | final baseline(逻辑修复后) |
| `8d7265f`/`9523b4b` | 根因图谱 + next-step plan |
| `62f7cc2` | Path 1 教授修复状态(王强 GREEN) |
| `842f71d` | merge 脚本 `%`→`%%` psycopg3 修复 |

## 八、诚实剩余缺口(不可再修线)

1. **柯文德/任尔夫/刘桂良**:柯文德需论文嵌入(E-blocked);任尔夫/刘桂良需 pipeline_issue + field_contradiction resolver。
2. **~33k needs_enrichment paper + ~2.3k professor**:规模化 promote+embed(E 解后)。
3. **多轮 coref(qid2/4/10/12)**:eval harness 不带 session_id。
4. **L3 方差**:qid11/17/20 跨 run 波动(需多次平均/更强 judge)。
5. **架构根 A/B/C**:pattern-list 分类器/单跳召回/刚性匹配——症状补了,根还在。
6. **FM1a(6 缺失实体)**:未采集,ingest workstream。

## 九、持久价值

**eval 体系是真值底座**——env 真值 + 三层 + 27 case + 回归门,让每个未来修复可量红绿、卡回归。**逻辑修复**(FM5/qid11/FM4/qid14)+ **数据增强链路**(abstract→summary→promote→embed proven)+ **教授修复闭环**(王强 GREEN)+ **merge 脚本深修**(psycopg3 占位符)都是可量、可复用的产出。剩余是数据(E 限流 + 规模化)、harness(多轮)、架构(A/B/C)——都是别的 workstream,不是单点可自主修的检索逻辑。
