# P4 数据线执行日志：serving pack 全列重建（full-column-serving-pack-rebuild）

> 工作目录 `.worktrees/data-rebuild`（分支 `data/p4-serving-pack-rebuild`）。
> 本日志只追加；每条 = 做了什么 → 发现 → 怎么验证 → 影响哪些问题。
> 关联：总计划 `docs/plans/2026-08-17-systematic-fix-round-1.md` §一 P5/P8；
> 基线审计 `.agents/runs/2026-08-17-serving-pack-coverage-audit.md`；
> OpenSpec change `full-column-serving-pack-rebuild`。

---

## 2026-08-19 R1：4.1 源勘察（完成）

**做了什么**：按 tasks 4.1 定位全列 legacy 源、核对数量级、定位关系源。

**发现（关键结论）**：

1. **"全列 legacy Postgres" 的真相：原库已空，幸存源是文件家族。**
   - 历史 DSN `postgresql://miroflow@localhost:15432/miroflow_real` 对应容器
     `pgtest`（已停，本次勘察临时启动）。`miroflow_real` 四域公共表全为 **0 行**。
   - 灾难恢复程序（S2B）早已定案：original Postgres volume 恢复物化后
     `core_counts = company/professor/paper/patent 全 0`
     （`s2/source-coverage-matrix.md` "Substrate truth"；restore 记录
     `postgres-restore-record.json`）。审计对照表里的 6,514/3,387/11,408/97,774
     是灾前实测（docs/index.md 2026-06-22 re-baseline），非活库。
   - ⇒ 重建源 = 幸存文件家族 + recovery lab 的 salvage schema，全部已逐一核实存在。

2. **四域全列源（可达、量级对上 ~45k）**：

   | 域 | 源（restore root `/var/tmp/mirothinker-restores/canonical-v2-s2b-20260711T152222Z/workspace/`） | 行数 | 全列情况 |
   |---|---|---|---|
   | 企业 | `docs/企业总表.xlsx`（Sheet1） | 6,528 | 16 列：名称/项目/行业/省份地区/业务/成立时间/法人/团队/企业类型/注册地址/网址/邮箱/电话/产品简介/产品特点/应用场景 |
   | 专利 | `data/admin_uploads/patent/0dab.../11月专利完整版-patent-release/released_objects.jsonl`（灾前专利域已处理成 released 形态，PAT-xxx id） | 11,408 | 标题/摘要/申请人/公开号/日期/技术功效；`patent_type` 全"未知类型" → 用 `.agents/runs/infer-patent-type-from-patent-number/backfill-apply-2026-06-26.jsonl`（11,408 行全覆盖，确定性号码推断）补 |
   | 论文 | recovery lab 容器 `pgtest-recovery-lab-01` 的 `miroflow_recovery_candidate.salvage.paper` | `quality_status='ready'` **24,101**（总 99,437；有摘要 13,664；summary_zh 20,842） | title/doi/arxiv/openalex/年份/venue/摘要/作者/引用 |
   | 教授 | `logs/legacy_v2/enriched_v2_2026-04-05.jsonl`（3,274）+ `logs/data_agents/professor/enriched_v3_merged.jsonl`（825） | 并集 (name,institution) 去重 **3,736** | 全字段（title/institution/department/research_directions/education_structured/…） |

   内容承载对象合计 ≈ 6,528+11,408+24,101+3,736 = **45,773 ≈ 45k** ✓。

3. **关系源**：
   - 教授↔论文：`salvage.professor_paper_link` 共 101,158（verified 55,063 /
     rejected 46,095）。verified 链接引用 2,611 个 PROF 源 id；其中 **907 个**可
     通过"271 个 released_objects 快照并集（4,320 ids）+ 662 个 paper_staging
     文件（anchoring_professor_id→name 706 个）"映射到教授姓名 ⇒
     **18,655 条 verified 链接（18,061 篇论文）可直接锚定**，较当前包 580 条
     professor_paper_link 提升 ~32×。其余 ~1.7k PROF id 无名映射（源侧缺失，
     记为 typed gap，不用启发式凑）。
   - 企业↔专利：11,408 条专利 100% 带申请人名；企业侧 6,528 全名录 +
     s12f `applicant_name_resolution.jsonl`（700 已解析，含机构分类）⇒ 按
     归一化名称 + 别名连接（沿用 s12f applicant-binding 既定模式扩展到全集）。

4. **嵌入端点**：学校接口 `http://100.64.0.27:18005/v1`
   （Qwen/Qwen3-Embedding-8B，dim 4096）实测存活（探针成功返回 4096 维）；
   key 走 `~/.sglang_api_key`（loader 父目录遍历可命中仓库根的 `.sglang_api_key`）。
   与裁定"优先学校接口分批"一致。

5. **构建管道约束（决定 4.2 方案）**：s12 主源 `released_objects.db` 被
   hash/lineage 硬校验（`knowledge_build_isolated.py` 中
   `_RELEASED_OBJECTS_SHA256` 等常量），**不能**替换为新 45k 行 SQLite。
   扩展方式 = s12e/s12f 同款：新增 `_SupplementalSourceAuthority`（hash 钉死
   的 jsonl/xlsx 批次）+ 专用 merge 函数合成 released 对象；这是构建管道代码，
   非 serving 行为代码（serving 不变）。

**怎么验证的**：
- `pgtest` 启动后 psycopg 实查 `miroflow_real` 四域表 count=0；
- 恢复记录 `postgres-restore-record.json` core_counts 全 0 与 S2 矩阵互证；
- 工作簿 openpyxl 实读行数/列头（企业 6,528×16；admin 专利 xlsx 11,408×6；
  docs 专利 1,931×13 与旧发布集一致）；
- recovery lab 容器 psql 实查 salvage 计数与 link_status 分布；
- 11,408 专利 jsonl 逐行统计（applicants 100%、patent_number 去重 11,408、
  type 全未知→backfill 全覆盖 11,408）；
- PROF-id 映射覆盖率用 271+662 个文件扫描实测（907/2,611；18,655 链接）；
- 嵌入端点用真实 key 探针（401 未带 key → 带 key 200/4096 维）。

**影响哪些问题**：P5（专利关系 0→可物化 11,408 申请人链路）、P8（企业 27%→
6,528 全集+富字段 16 列）、论文域覆盖 0.6%→24,101、教授↔论文 580→18,655+。
出口标准 ③（对账报告）的基线数字本条已固化。

**环境操作备注**：勘察期临时启动了两个已停容器 `pgtest`（15432）与
`pgtest-recovery-lab-01`（network=none，docker exec 只读查询）；活路径
（/var/tmp/mirothinker-canonical-v2-s12f/**、miroflow_candidate_s12f_20260801_v1、
18188）零写入。抽取完成后将停回原状。

---

## 2026-08-19 R2：4.2 构建方案（设计定案）

**做了什么**：读穿 s12 构建管道（knowledge_build_isolated.py 的源准入/merge/
投影/关系/索引流），校准 s12f 切片成本（单切片 ≈688 行管道代码+691 行测试），
定案 P4 全列重建方案。

**方案（六批一策略）**：

1. **六个新补充源批次**（s12e/s12f 同款准入模式：payload 落
   restore 树 `workspace/docs/source_backfills/p4-*.jsonl`（只增新文件，不动
   既有文件——s12f 先例），byte+sha256 钉死进 manifest）：
   - `p4-company-full-v1`：企业总表 6,528 → 全列 company（行业/省份地区/业务/
     成立时间/法人/团队/企业类型/注册地址/网址/产品简介/特点/应用场景）；
   - `p4-patent-full-v1`：11,408 全量专利（灾前已处理好的 released 形态）+
     类型推断 backfill（确定性号码规则，11,408 全覆盖）；
   - `p4-paper-salvage-v1`：salvage ready 24,101（authors 从 authors_display
     切分为 author dict 列表，供派生锚点机制使用）；
   - `p4-professor-full-v1`：v2+v3 并集 3,736（v3 覆盖同 (name,institution)；
     PROF-id 尽量取自恢复映射，取不到用 sha 稳定生成；污染名过滤）；
   - `p4-professor-paper-links-v1`：salvage verified 55,063 中 prof-id 可映射
     的 18,655 条（professor 端解析到 p4 教授 id，paper 端保留 PAPER-id）；
   - `p4-applicant-binding-full-v1`：全量申请人解析（s12f 819 条既有解析
     复用 + 对 6,528+700+1,037 企业名做归一化精确/别名连接；机构分类沿用
     s12f 判据；无匹配记 unresolved，不做启发式凑数）。
2. **mapper 政策升 v3**：`_ALLOWED_FIELD_PATHS_BY_OBJECT_TYPE` +
   `_selected_fields` 扩展全列可选字段（仅当 payload 携带才投影，缺失不产生
   gap）：company +geography/founded_at/legal_representative/registered_address/
   registered_capital/team_description/product_description/tech_tags/
   industry_tags；patent +patent_type/abstract/technology_effect/grant_date/
   ipc_codes/title_en；paper +abstract/summary_zh/citation_count/title_zh/
   publication_date/keywords；professor +name_en/h_index/citation_count/
   education/projects/awards/work_experience/office。政策版本
   `canonical-v2-released-objects-mapper-v3`（构建侧，serving 行为不变，
   lookup 文档内容=投影模型全量 dump，字段自然流入）。
3. **新 merge 函数**：company_full/patent_full/paper_salvage/professor_full
   照 company_backfill 模式合成 released 对象（已存在同名/同号/同 DOI 的跳过
   或并字段，绝不覆盖既有数据）；professor_paper_links 合成 link 对象进
   links 泳道（端点校验复用）；applicant_binding_full 复用 s12f 绑定语义。
4. **论文教授锚点门保持**：无锚点论文照旧被移除并记 typed gap——这是 PRD
   纳入契约（论文须锚定教授），不是可以绕过的薄回填。ready 24,101 中
   verified-锚定 7,805 为下界，构建时派生作者别名锚点会再加。
5. **构建参数**（全部新名，零写入活路径）：
   - gate root = 本 worktree 的 `.agents/runs/rebuild-canonical-v2-knowledge-platform`
     （四份 gate 文档实测 hash 与代码钉死值一致）；
   - DB `miroflow_candidate_v2_20260819_r1`（55458 集群新库，不碰
     miroflow_candidate_s12f_20260801_v1）；
   - staging/index 根 `/var/tmp/mirothinker-data-v2/{staging,index}-v1`；
   - run-id `p4-build-20260819-v1`，release `candidate-v2-20260819-r1`；
   - envelope 落本 worktree gate root 的 s12a 槽（fresh，已确认不存在）；
   - 嵌入沿用 qwen bundle（学校端点 100.64.0.27:18005 实测存活）；
   - 主源 s12a SQLite 及其 5,561 行校验不动（计数断言只对主源生效，已核实）。

**怎么验证的**：管道关键断言逐条读码核实（主源 hash 钉死不可替换⇒必须走
补充批次；5561 计数断言仅主源；supplemental 须完整 parse；论文锚点移除门；
lookup 文档=投影模型 dump）。gate 四文档 hash 与 rebuild_write_gate.py 常量
逐一比对相等。s12f serve 包装器（serve_s12e_port.py 端口 monkeypatch）确认
可用于 18200 冒烟。

**影响哪些问题**：同 R1（P5/P8/论文覆盖/关系规模），另解锁 G7 枚举抓手
（industry/geography/tech_tags 进入 lookup）。

---

## 2026-08-19 R3：4.2 构建方案落地（抽取+管道+脚本+测试）

**做了什么**：
1. **源抽取** `.agents/runs/full-column-serving-pack-rebuild/extract_p4_sources.py`
   （可重跑、确定性排序；payload 落 restore 树 source_backfills，只增不改）：
   - company 6,514（表内重名去重后，恰=审计基线 6,514）；
   - patent 11,408（admin release + 类型推断全覆盖）；
   - paper 24,101（salvage ready；authors 由 authors_display 切分）；
   - professor 3,735（v2+v3 并集，污染名过滤）；
   - 教授↔论文 verified 链接 18,655（prof 名字可锚定）；
   - 申请人解析 2,373（resolved 957 / institution 125 / individual 52 /
     unresolved 1,239 typed-gap）。
   首轮论文抽取踩坑：psql 行式导出被多行字段打断（26,261≠24,101）→ 改
   `\copy CSV` 后精确对上；六批 payload hash/字节数固化为
   `batch-inventory.json`。
2. **管道扩展** `knowledge_build_isolated.py`（s12e/s12f 同款准入）：
   - 6 个 `_SupplementalSourceAuthority`（byte+sha256 钉死）+ purposes +
     registered_unprojected 槽位；
   - `_merge_p4_created_rows`：四域创建型合并（重叠保守跳过：company 名/别名、
     patent 号、paper doi/题名、professor 名；绝不覆盖既有对象）；全列 selected
     塑形对齐投影模型（NamedReference/Date/named members）；
   - `_merge_p4_professor_paper_links`：端点完备才成链，缺端点记 typed gap；
     合成链接走主 lane 同款端点 lineage；
   - applicant binding 全量批复用 s12f 绑定语义（purpose 集合扩展）；
   - mapper 政策保持 v2——补充批次绕过主 lane `_selected_fields`，全列字段
     经合并函数直入 selected→投影（lookup 文档=投影模型全量 dump，字段自然
     流入服务侧）。
3. **manifest** `source-build-manifest-p4.json`：s12f 全量 + 6 个
   evidence_input 条目，`SourceBuildManifest` 真实校验器验证通过
   （content_sha256 `a6e82fcd…`，58 源）。
4. **构建脚本** `build-v2.sh`：DB `miroflow_candidate_v2_20260819_r1`（55458
   集群，与 s12f 库同集群不同库）、staging/index 根
   `/var/tmp/mirothinker-data-v2/`、envelope 落本 worktree gate root s12a 槽、
   run-id `p4-build-20260819-v1`、release `candidate-v2-20260819-r1`、
   16 个 batch id、嵌入学校端点 bundle。
5. **测试**：新增 `tests/canonical_v2/test_knowledge_build_p4_full_column.py`
   9 用例（authority 钉死/四域创建塑形/重叠跳过/链接端点门/绑定复用/payload
   hash 对账/manifest 校验）；更新既有两个测试文件的 disposition 镜像与
   batch 列表并补 6 条 side-effect-free 夹具行。

**发现**：
- 既有 `test_knowledge_build_isolated.py` 有 4 个全持久化 e2e 用例在**基线
  （stash 我的改动后）同样挂起**——需要 127.0.0.1:5432 上可用的 miroflow
  trust 一次性库（当前环境无）。**非本切片回归**（stash 对比复现）。其余
  137 用例全绿。
- 教授 `company_roles` 投影是 RelationshipProjectionReference（来自关系 lane），
  不能从 core_facts 直投——builder 已移出 selected（与 s12a 行为一致）。
- 申请人池 1,239 个企业名未入企业名录（unresolved）是**源侧真实缺口**（typed
  gap 记录在案），不做启发式凑数。

**怎么验证的**：`uv run pytest tests/canonical_v2/test_knowledge_build_p4_full_column.py`
9/9 PASS；`test_knowledge_build_isolated.py` 137 passed / 4 env-deselect（基线
同样挂起，stash 对比）；`test_knowledge_build_professor_backfill.py` 13/13；
ruff 全过；manifest 过真实 SourceBuildManifest 校验；嵌入端点探针 4096 维。

**影响哪些问题**：为 4.3 构建（P5/P8/论文覆盖/关系规模）铺平管道。
