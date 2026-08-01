# S12e 关系数据审计（relationship-audit）

审计对象：candidate DB `miroflow_candidate_s12c_20260726_r8`（容器 canonical-v2-s12c-pg-20260726-r8），只读。
当前关系投影：`professor_attributed_to_paper` 262（shared 层）、`patent_has_applicant` 76、`professor_company_role` 1（typed 层）。所有决策状态均为 accepted，**无任何 rejected 记录**——所有流失都发生在候选生成之前，且未留痕。

## 1. professor_company_role 为何只有 1 条

结论：不是判定/投影拒绝，而是**源头数据只有 1 个可行 (教授,公司,角色) 三元组**。漏斗：

| 阶段 | 数量 | 说明 |
|---|---|---|
| 补充批次 s12c-r7-professor-company-roles-v1 | 2 条记录 | 两条都是 丁文伯→深圳无界智航科技有限公司（sohu 0.72 / idea.edu.cn 0.62） |
| 种子去重 | 2→1 | `_typed_relationship_seeds` 按 (类型, 教授canonical, 公司canonical, role) 去重，同一对只留 1 个种子 |
| 断言/判定/投影 | 1→1→1 | accepted，confidence=1，rationale="Explicit source relationship endpoints and supported role." |
| 内嵌路径 core_facts.company_roles | 40/1439 教授有数据，67 个条目 | 仅 3 条 role 命中词表（创始人/发起人/联合创始人），仅 1 条公司名可解析 |
| 内嵌路径产出 | 0 个新种子 | 唯一可解析的条目（PROF-8000C9F994C3 发起人@无界智航）与补充批次是同一三元组，被去重 |

拒绝原因分布：**不存在**。`typed_relationship_decision` / `relationship_projection_outcome` 中 professor_company_role 只有 1 条 admitted=t。种子生成处的 `continue`（role_id 为空、公司名解析不唯一）不落库、不记 reason code——观测缺口。

内嵌条目失败模式（67 条抽样全量）：role 为自由文本（首席科学家、高管、董事会成员、理事长、研究员…），词表 `_professor_company_role_id` 只认 founder/adviser/investor/employee/cooperator 五类精确匹配；company_name 多为大型科技公司（华为×6、Meta、京东、苹果、微软、腾讯、百度、富士康…）或非公司实体（行业协会、联合实验室、IACAI），不在 1037 家已发布公司内，仅 1/67 可解析。

## 2. patent_has_applicant 76/1931 漏斗

| 阶段 | 数量 |
|---|---|
| 专利源记录（全部有 applicants 名称） | 1931 |
| core_facts.company_ids 非空（上游已解析） | 76 (3.9%) |
| 断言→判定→投影 | 76→76→76 全通过 |

1855 条未解析专利的申请人构成（按申请人串分类）：公司但不在发布集 1717（迈瑞、拓邦、平安人寿等全量深圳企业，发布集只有 1037 家）、高校/学院 183、研究院/实验室 42、疑似个人 7、医院 1、其他 4。

抽样 10 例：PAT-7B8567B8E83C 深圳忆海原识科技有限公司；PAT-002EE94826BA 深圳拓邦股份有限公司；PAT-03662F62B10D 深圳迈瑞生物医疗电子股份有限公司；PAT-004331BCE56B/PAT-00B74391DD47 深圳市华成工业控制股份有限公司；PAT-004E9EA889BD 深圳赛动智造科技有限公司；PAT-00E375D1CDA9 深圳市欢创科技有限公司；PAT-014F5FB3824E 中国平安人寿保险股份有限公司；PAT-015D207EDA08 深圳市德泰兴自动化设备有限公司；PAT-01612B56AADD 广东美房智高机器人有限公司。全部为"公司不在发布集"，非解析逻辑错误。

**可回收**：45 条专利的申请人名精确命中已发布公司名但 company_ids 为空（上游解析漏配），例：PAT-23846675E4B8 深圳市普渡科技有限公司、PAT-20C329FC3DDE 奇勃(深圳)科技有限公司、PAT-2E22A0BE0D5A 盈合(深圳)机器人与自动化科技有限公司、PAT-19160FA3C466 交浦科技(深圳)有限公司（与哈工大(深圳)共同申请）。修复后可 76→121（+59%）。

## 3. professor_attributed_to_paper 归因证据质量

- 580 个源 link 对象 → 两端均已发布 251；流失 329：教授未发布+论文未发布 313、仅教授未发布 11、仅论文未发布 5（与 885 教授/312 论文被 gate 一致，非关系层问题）。
- 262 条已接受 = 251 条 link 对象断言 + 11 条 derived 断言（来自 SIGS 官方出版物论文记录显式教授端点，attribution_basis=explicit_accepted_*_endpoint）。
- 证据质量（251 条 link 来源）：evidence_source = openalex 140 / official_linked_orcid 91 / official_linked_cv 20；link_status = verified 247、**candidate（未核验）4 条仍被接受**——全部属于 张雅鸥(PROF-13FC926273C1)：PAPER-2066B11D20FE / 8A1F29F4301C / 646E092FFB59 / 31BC69152B14。
- 判定全部走 deterministic 策略，rationale 统一为 "The sole surviving relationship assertion satisfies all constraints."，confidence 未做区分。
- **集中度风险**：262 条关系覆盖 262 篇论文（每篇恰好 1 位教授）但仅覆盖 **23/554 位教授（4.2%）**；top-4（丁文伯 21、徐扬生 20、吴亚北 20、郑庆彬 20）占 81 条（31%），top-12 占 ~76%。531 位已发布教授无论文归因。

## 4. 可挖关系类型评估

| 关系 | 数据可得性 | 估计产量 | 优先级 |
|---|---|---|---|
| 专利→公司（修复漏配） | 45 条申请人名精确命中已发布公司 | +45（76→121） | **P0**：纯重跑解析，零新数据 |
| 教授-专利（inventor） | **0/1931** 专利填了 inventors / professor_ids（上游未抽取发明人） | 潜在大（1931 专利） | **P1**：需先在落地/解析层补 inventor 抽取，再按 姓名+单位 消歧 |
| 教授-公司任职 | 内嵌 67 条仅 1 可解析（公司多为华为等大厂，不在发布集）；公司 key_personnel 1293 条中 35 个 (公司,教授) 姓名精确命中（张芳/李佳/刘伟 等常见名，误报风险高）；补充 websearch 批次仅 2 条 | 高置信 ~10-35 | **P2**：先扩 company 别名解析+补充批次扩量；key_personnel 需角色类型过滤+佐证消歧 |
| 公司-论文 | papers.funders 0/574；authors 有值（574/574）但仅姓名无单位 | ≈0（直接路径） | P3：只能经教授桥接（公司→任职教授→论文），依赖教授-公司先做厚 |

## 5. 优先建议

1. **P0 专利申请人回填**：对 1855 条 company_ids 为空的专利，用 `_source_name_key` 同款归一化对 applicants×(company.name, normalized_name) 做精确匹配重跑解析，预期 +45 条 patent_has_applicant；同时在种子生成处为解析失败落 reason code（当前静默 continue）。
2. **P1 专利发明人上游补抽**：1931 专利 inventors/professor_ids 全空，professor-patent 关系数据基础为零；在落地批次补 inventor 抽取后按姓名+单位消歧建 `professor_attributed_to_patent`。
3. **P2 教授-公司任职扩源**：(a) 补充批次目前仅 2 条记录，按 554 已发布教授系统性 websearch 扩量；(b) 放宽 role 词表（首席科学家/高管/董事→executive/adviser）前先解决公司解析——67 条内嵌条目仅 1 条公司可解析，词表不是当前瓶颈；(c) key_personnel 35 个姓名命中需消歧后才可用。
4. **P2 证据完整性**：4 条 link_status=candidate 的归因（张雅鸥）被 deterministic 策略直接接受，建议核验或降级；domain_inclusion_decision 只存 admitted 行、关系种子流失不留痕，补 rejected/跳过原因记录。

## 附：审计方法

- 数据：landing.source_record（s12a-released-objects-full-v1 5561 条 + 5 个 s12c-r7 补充批次）、knowledge.typed_relationship_assertion / typed_relationship_decision / relationship_assertion / relationship_decision / current_relationship_projection / relationship_projection_outcome / domain_inclusion_decision / current_source_identity_assignment。
- 名称归一化与种子逻辑对照 `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_build_isolated.py:4021-4228`（`_professor_company_role_id`、`_typed_relationship_seeds`）。
- 全部查询为 SELECT；姓名匹配在 /tmp 下用 Python 复算（company 1037 名称键、patent 1855 未解析、key_personnel 1293 条）。
