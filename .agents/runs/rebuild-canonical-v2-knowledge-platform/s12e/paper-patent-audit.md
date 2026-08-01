# 论文+专利域数据质量审计（s12e track）

- Release: `candidate-s12c-20260726-r8`（DB `miroflow_candidate_s12c_20260726_r8`，容器 `canonical-v2-s12c-pg-20260726-r8`，只读 SELECT）
- 索引：`/var/tmp/mirothinker-canonical-v2-s12c/r8/index/lookup.sqlite3`（只读）
- 参考代码：worktree `canonical-v2-s11-consolidation`
- 规模基线：paper 262 / patent 1931；关系：professor_attributed_to_paper 262、patent_has_applicant 76

## 1. 论文标识符覆盖（arxiv_id / doi / pdf）

- **投影层 262/262（100%）arxiv_id、doi、pdf_path 全空**；`paper.identifier` 子对象表 0 行。pFedGPA 不是孤例，是全量缺陷。
- Landing 层（574 条 `released_objects:PAPER-*`）：doi 500/574（87.1%）、arxiv_id 1/574、pdf_path 0/574（后两者源侧本就稀缺）。
- 断言层：`identity.doi` 断言存在 230/262（87.8%）；arxiv_id / pdf_path 无任何断言。
- **根因**：`knowledge_build_isolated.py` `_selected_fields` paper 分支（L2335-2357）只提取 `authors/summary_text/title/venue/year`；doi 仅作身份键进入 `identity.doi` 断言，从未映射到投影标量 `doi`（catalog 声明 field_path `doi`，domain-catalog-v1.json:761）。
- pFedGPA 实证（`paper-c-00ef8d8cf801c66284170d1f` ← `PAPER-B907001E299D`）：landing core_facts 含 `doi=10.1609/aaai.v39i17.33980`、`arxiv_id=2409.05701`；断言有 `identity.doi`；投影与 r8 索引 lookup_content 全部 NULL。
- 同机制丢弃的其他字段（landing→projection，262 篇全空）：keywords（源 573/574）、citation_count（461/574）、abstract（358/574）、enrichment_sources（574/574）、professor_ids（573/574）、title_zh、funders、reference_count。
- r8 索引核验：262 个 paper lookup 文档 doi/arxiv/keywords/pdf 全部为 0——索引忠实反映了被截断的投影。
- 连带效应：262 篇 quality_status 全为 `partial`（可选字段全缺所致）。

## 2. 论文作者→教授归因覆盖

- Release 内：262 条关系覆盖 **262/262 篇论文（每篇恰好 1 条，全量）**，但仅落在 **23 位教授**上。分布：丁文伯 21、徐扬生/Tinghuan Chen/郑庆彬/潘毅/甘培润/吴亚北各 20、孙海鹏 19、谢洪途 18、李锦辉/颜骏各 17、李海文/湛家铭各 15，其余 10 位 ≤4。
- Landing 视角：574 篇中 573 篇带 professor_ids，仅 262 篇（45.6%）准入，**312 篇被弃**：
  - 307/312 是教授未进 release 的级联丢失。例：王学谦 `PROF-132D3CC74120`（gate-rejected，无 source_identity）名下 20 篇中 17 篇被弃；其余 3 篇按作者名重锚到王晓浩等在库教授。
  - **5/312 为真缺口**（教授在 release 且 active，论文在 landing 且指向该教授，但论文未准入）：唐金陵 `PROF-422015824431` ×3（NHS reorganisation / Clinical guidelines in China / Research priorities in TCM——主题离群，可能是有意过滤，需人工确认）、孙海鹏 `PROF-3C905BF6749A` ×1（Nonlinear transport theory at the order of quantum metric）、李海文 `PROF-728A33A31D60` ×1（A Simple and Efficient Preparation of High-Purity…）。
- 作者名解析质量（`paper.author` 1006 行 / 262 篇，均值 3.84、最大 14）：空名 0、"et al" 0、含数字 0、含逗号 0、含机构词 0；pFedGPA 9 位作者及顺序与 landing 完全一致。**解析质量良好，无需修复**。
- 注意：论文投影 `professor_ids` 列 262/262 全空——归因只存在于关系投影，未回写域投影。

## 3. 专利号可查性

- `patent_number` 覆盖 **1931/1931（100%）**，全部 CN 前缀，无首尾空白、无重复（distinct 1931）。`display_name`=标题 100%，从无专利号。
- r8 索引：1931 个 patent lookup 文档 `lookup_content` 均含 patent_number；CN117873146A → `patent-c-b5e0a15fa7a329d1f49ffd23`《一种机器人的落地控制方法、机器人及终端设备》**在库且索引完备**。
- 读路径参考代码（`knowledge_read_isolated.py`）：`_projection_terms` 把 patent_number 纳入 identifier_terms（L7748）；`_matches_exact_request` 对 `exact_identifier` slot 做归一化精确比对（L7836-7839）；claim 绑定（`_projection_claim_binding`）与约束校验（knowledge_read.py L6413-6460）链路完整。
- **CN117873146A 案例残余解释**（按可能性）：(a) 案例观察自旧 release（r8 于 2026-07-26 重建，此前投影可能无 patent_number）；(b) 查询规划器未把裸号码查询路由到 exact lane 或 domains 未含 patent——需对 18188 live 服务回归验证（本审计只读未触碰）；(c) 即便命中，结果卡 display_name 为标题，用户看不到号码命中，产生"不可按号检索"的体感。
- 同 `_selected_fields` 机制丢弃的专利字段（landing→projection）：filing_date（源 1931→0，仅存 `identity.filing_date` 断言）、publication_date（1931→0）、patent_type（1931→空串，列 NOT NULL）、abstract（1931→0）、title_en（1921→0）、technology_effect（1908→0）。grant_date / ipc_codes / inventors 为源侧真空（landing 即空）。r8 索引 patent 文档 filing_date 0/1931。

## 4. 专利申请人→公司链接

- `patent_has_applicant` 76 条 ↔ landing 76 篇带 company_ids 的专利**一一对应**（76 专利 → 33 公司），已有链接 100% 忠实投影，无丢失。
- **覆盖低（76/1931 = 3.9%）的根因在源数据**：landing 1931 篇全部 ready，2088 条申请人记录 `canonical_company_id` 全空，仅 76 篇 core_facts.company_ids 非空。即 1855 篇（96.1%）的申请人只是名称字符串，历史上从未做申请人→公司归一化链接。
- `patent.applicant` 子对象 2088 行 `canonical_company_id` 100% NULL；专利投影 `company_ids` 列 1931/1931 全空（链接仅存于关系投影）。

## 5. 按影响排序的修复建议

1. **P0｜修复 `_selected_fields` 字段截断并重跑断言+投影**（影响全部 262 论文 + 1931 专利）。paper 增提取 doi/arxiv_id/abstract/keywords/citation_count/enrichment_sources/title_zh/professor_ids，并把 `identity.doi` 断言映射到投影 `doi`；patent 增提取 filing_date（映射 `identity.filing_date`）/publication_date/patent_type/abstract/title_en/technology_effect。纯白名单+映射改动，landing 数据已在库、无需重新抓取。验收：doi ≥230/262、filing_date 1931/1931、paper quality_status 大面积从 partial 转 complete。
2. **P1｜申请人→公司归一化链接**（影响 1855 篇专利）。用 `patent.applicant.name` 对 company normalized_name/aliases 做精确+归一化匹配（可复用 `_supplemental_match_indexes` 同类机制），把 patent_has_applicant 从 76 提升至理论上限 1931，并回写 `patent.applicant.canonical_company_id` 与投影 `company_ids`。
3. **P1｜论文归因补漏+级联丢失可观测**。补归 5 篇真缺口论文（先人工确认唐金陵 3 篇离群主题是否有意过滤）；把 312 篇被弃论文（含王学谦 17 篇）显式登记进 `ops.current_knowledge_gap`，使教授 gate 的级联效应可观测、可复查。
4. **P2｜按号检索端到端回归 + 展示层带号**。对 live 服务跑 CN117873146A 查询回归确认 exact-lane 路由；展示层把 patent_number 加入显示（display_name 副标题），消除"命中但看不到号"的体感不可查。
5. **P2｜域投影外键回写**。论文投影 `professor_ids`、专利投影 `company_ids` 当前 100% 空，随建议 1/2 一并回写，使域投影自洽，降低读路径对关系投影的隐式依赖。

---
审计方式声明：全部结论来自只读 SQL / 只读索引读取 / 参考代码静态阅读；未修改任何 DB、索引、仓库文件或运行中进程；未触碰 18188 服务。
