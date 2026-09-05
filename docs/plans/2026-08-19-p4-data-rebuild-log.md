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

---

## 2026-08-19 R4：4.3 构建 gate 卡点修复（build-v2.sh 幂等重置 + 重启构建）

**做了什么**：

1. **定位报错**：`IsolatedKnowledgeBuildSafetyError: isolated target or
   accepted backup gate validation failed`（`knowledge_build_isolated.py:8882`）
   只是 `_preflight` 的统一包裹（:8878-8884 同时包住
   `validate_fresh_targets` 与 `verify_accepted_gate` 两类失败）。本次
   traceback 的真实失败点是 `_assert_fresh_database`："candidate database
   is not fresh"（9 表非空）。
2. **根因（不在 gate，在 build 脚本的 DB 状态假设）**：`build-v2.sh` 的
   DB 准备逻辑把「库存在」当「已准备好」——上一轮构建中途因 psycopg2
   `executemany` 崩溃（commit 5178a79 已修）留下
   landing/knowledge/publish 残留数据，重跑脚本不清理 → fresh 校验拒绝；
   之后手工 DROP/CREATE 重建的库虽空但丢失
   `miroflow:destructive-target:v1:disposable:<db>` marker（脚本只在
   「新建」分支打 marker）→ 直接重跑会死在库身份校验
   （`verify_database_identity` 要求 marker 精确相等，alembic 环境同样
   校验，当前实测库 marker=None）。
3. **核对用户怀疑的 `verify_accepted_gate`(:7824)/`_gate_root` 路径绑定：
   无问题**——boundary 组合时 `resolve(strict=False)` 存储（:7782）、每次
   调用再 resolve 比较，两侧同源一致；gate 四文档
   （s2/source-inventory、s2b/backup-manifest、restore-verification、
   acceptance-record）实测 sha256 与 `rebuild_write_gate.py` 钉死常量
   逐一相等；manifest `content_sha256`（a6e82fcd…）与 build/serve 脚本
   pin 一致（整文件 sha acc62c33… 不同是预期——校验用内部内容哈希，
   非误报修复项）；alembic head `C2_0013` = `_EXPECTED_ALEMBIC_REVISION`；
   milvus.db sha256 与 pin 一致；envelope/staging/index 均 fresh。
4. **修复 `build-v2.sh`**：DB 准备改为**幂等重置**——仅当库带本脚本
   disposable marker（上次半途运行遗留，可安全丢弃）或**完全无表且无
   marker**（手工重建的空壳）时 `DROP DATABASE … WITH (FORCE)` 后重建并
   统一打 marker；带异 marker 且有表的库一律拒绝（防误删他人库）。
   PG 16.13 支持 FORCE。归档失败日志为 `*.failed-20260819-pre-fix`，
   重启 build-v2.sh（nohup，pid 209583）。

**发现**：

- 残留的 9 张表（knowledge.policy/relationship_type/release、
  landing.evidence_artifact/ingest_run/parser_run/source_record、
  publish.build_manifest/manifest_section）正是上次崩溃前构建最先写入
  的表，与 executemany 崩溃时间线吻合。
- 「库已重建为空」与「脚本能继续跑」之间隔着 marker 这道身份防线：
  手工重建绕过脚本即绕过 marker，属于安全设计按预期拦人。

**怎么验证的**：

- 重置逻辑对当前真实状态（无标记空库）实跑："unmarked but empty target
  dropped" → 重建后 psycopg 回读断言 marker 精确等于
  `miroflow:destructive-target:v1:disposable:miroflow_candidate_v2_20260819_r1`。
- 重启后：alembic 无错迁至 C2_0013 head；runner 进程存活（CPU ~88%）；
  库内 `landing.ingest_run`=15、`landing.source_record` 73,907 且持续
  增长——原 8882 卡点（preflight gate）已实际通过，构建进入数据写入
  阶段。构建最终结果（envelope 产出/对账/18200 冒烟）见后续条目。

**影响哪些问题**：解锁 Phase 4 全列重建本体（P5 专利关系、P8 企业
全集与富字段、论文覆盖 24,101、教授↔论文 18,655 链接）。

---

## 2026-08-19 R5：4.3 二度卡点——fingerprint 回归修复 + 脚本全面可重入

**做了什么**：

1. **R4 重启的构建跑了 1h20m 后再崩**（这次远超 preflight，landing
   73,907 条写完、合并/投影完成），死在 `_persist_owners` →
   `canonical_identity_postgres.py:628`：
   `AttributeError: 'SourceAssertion' object has no attribute
   'assertion_fingerprint_sha256'`。
2. **根因**：83faea0（批量 executemany 改写）把原助手调用
   `_assertion_fingerprint(assertion)` 误替换为不存在的模型属性
   `assertion.assertion_fingerprint_sha256`——fingerprint 是计算值
   （canonical JSON 的 sha256，:133），不是 `SourceAssertion` 契约字段。
   5178a79 只做了 `connection.executemany`→`connection.cursor()
   .executemany` 的机械路由，无表达式替换。
3. **同类位排查**（pattern 纪律，避免逐个再烧 1.5h）：逐行比对 83faea0
   两文件全部改写表达式——identity 文件**仅此一处**助手→属性替换，
   decision 文件全部忠实（`_legacy_instant`/`_temporal_json`/
   `_trace_json`/`_review_json` 均保留）；2270d86 为纯新增；全库 grep
   确认剩余 `assertion_fingerprint_sha256` 引用均为 SQL 列名或查询
   结果字典（合法）。
4. **修复 + 回归测试**（commit 9619b77）：恢复
   `_assertion_fingerprint(assertion)`；新增单测
   `test_insert_sources_and_assertions_batches_rows_with_computed_fingerprints`
   ——用记录型 stub connection 驱动真实
   `_insert_sources_and_assertions`，把 fingerprint 列钉死为
   canonical-json sha256 配方（修复前精确复现生产 AttributeError）。
5. **build-v2.sh 第二处可重入缺陷**：崩溃运行残留的
   `/var/tmp/mirothinker-data-v2/{staging,index}-v1` 触发脚本自己的
   "not fresh" 硬退出。改为**绑定校验后重置**：staging marker 必须精确
   绑定本构建身份（schema_version + run_id + release + manifest sha）
   才允许清除，否则拒绝。随后第三次重启构建。

**发现**：

- 既有测试为何没拦住：P4 的 9 个用例测 merge/authority，不触 persist
  路径；能覆盖真实 persist 的 4 个全持久化 e2e 用例在本环境挂起
  （等 127.0.0.1:5432 trust 库，基线同样挂），属已知环境门控缺口。
- 崩溃时间线本身证明新代码路径其余部分健康：source_identity 与
  source_identity_record 两条 `cursor().executemany` 已成功执行，
  psycopg3 路由与 `source.*` 全部属性有效。
- 一次机械重构（循环→批量）引入的缺陷只在 1.5h 深的运行时暴露——
  可重入的构建脚本（DB/staging 自动重置）把重试成本从"人工清场"
  降为"直接重跑"。

**怎么验证的**：

- 回归测试 RED→GREEN：修复前失败于生产同款 AttributeError，修复后
  4 passed（identity 文件 35 skipped 均为既有环境门控）；
- P4 套件 9/9 PASS；ruff 全过；`test_knowledge_build_isolated.py`
  因 4 个基线挂起用例中断收集（非本切片回归，与 R3 记录一致）；
- 重启实战验证两条重置路径：staging/index 按 marker 绑定清除 +
  脏库按 marker 归属 DROP 重建（两次日志原句
  "stale staging/index roots from a failed run of this build removed" /
  "stale disposable target dropped (owned by a previous run)"），
  alembic 至 C2_0013，runner 进入构建。
- 构建最终结果（envelope/对账/18200 冒烟）待构建完成，见下一条目。

**影响哪些问题**：同 R4；另沉淀可重入构建脚本体（DB + staging/index
marker 绑定重置），后续任何中途崩溃可直接重跑。

---

## 2026-08-20 R6：4.3 三度卡点——容器 shm 64MB 瓶颈（非代码问题）

**做了什么**：

1. **R5 重启的构建（第三次尝试）跑了 ~13h 后在决策持久化阶段再崩**。
   顶层异常是泛化包装（"canonical-decision verification or transaction
   failed"），完整日志里的底层原因是：
   `psycopg.errors.DiskFull: could not resize shared memory segment
   "/PostgreSQL.838765374" to 80337184 bytes: No space left on device`。
2. **根因**：候选库长到 1.8GB 后，决策阶段的大查询触发 PostgreSQL
   **并行查询**，并行 worker 需要把共享内存段扩到 ~80MB，而构建容器
   `canonical-v2-s12c-pg-20260726-r8` 的 `/dev/shm` 是 Docker 默认
   **64MB**。宿主机资源充足（内存 503G/磁盘 1.3T 空闲），瓶颈只在
   容器 shm 上限——非代码缺陷，非数据问题。
3. **重要里程碑（顺带验证）**：本次运行已把上次的崩溃点完整走完——
   `knowledge.source_assertion` 提交了 **132,358 行**，R5 的 fingerprint
   修复经实战充分验证；这次死在更深一层（决策持久化）。
4. **修复**：按原配置重建容器（同镜像 pgvector/pgvector:pg16、同端口
   127.0.0.1:55458、同数据卷、同环境变量），唯一变化
   `--shm-size 64M → 1g`。重建后核验：/dev/shm=1.0G，**全部 9 个库
   完好**（s12c/s12e/s12f 历史库、候选库、测试库均在）。第四次重启
   build-v2.sh（自动重置脏 DB + staging，全部日志原句见 nohup）。

**发现**：

- 三次崩溃三种性质：R4 安全防线按设计拦人（脚本假设错误）→ R5 代码
  笔误（机械重构引入）→ R6 基础设施容量（数据规模长大后必然触发）。
  每次都比上一次深一层：preflight(分钟级) → identity persist(1h20m)
  → decision persist(13h)。
- 64MB shm 对 s12 时代的小库够用，P4 全列库（GB 级）必然不够——
  这是数据规模跨量级后第一次暴露的容量假设。

**怎么验证的**：

- docker inspect 实测 ShmSize=67108864（64MB）+ 容器内 df 确认
  /dev/shm 64M；错误信息本身（resize to ~80MB 失败）与 64MB 上限
  吻合；
- 重建后 /dev/shm=1.0G、9 库齐全、构建第四次启动通过全部守卫并进入
  landing（7.3 万源记录重灌中）；
- 构建最终结果（envelope/对账/18200 冒烟）待完成，见下一条目。

**影响哪些问题**：同 R4/R5；基础设施容量假设修复后，全列构建的
最后一层已知风险清除。

---

## 2026-08-20 R7：容量前置放大（用户决策）——shm 8GB + 维护内存 1GB

**做了什么**：

1. **用户裁定**：与其带着 1GB shm 跑 13 小时赌决策段够用，不如立即
   放大容量、放弃当时跑了 ~45min 的第四次尝试、从头重跑——机器
   503GB 内存，容量成本为零，重试成本（13h+）远高于重启成本（<1h）。
2. **容器再重建**（同镜像/端口/卷/环境变量）：
   `--shm-size 1g → 8g`（实测崩溃需求 ~80MB/段，1GB≈12 段并发余量，
   8GB 给未探明的投影/建索引段留足空间）。
3. **`ALTER SYSTEM SET maintenance_work_mem = '1GB'`**（写入数据卷内
   postgresql.auto.conf，随卷在容器重建间持久；新会话实测生效）——
   为后续 CREATE INDEX/ANALYZE 阶段预置，避免磁盘排序拖慢索引段。
4. 第五次启动 build-v2.sh（自动重置 DB + staging，监控在位）。

**发现（过程坑，记录备查）**：`pkill -f "build-v2.sh"` 会匹配到执行
它的 shell 自身命令串而自杀，导致 runner 成孤儿进程——按 pid 精确
kill 收尾。容器重建后 `SHOW` 旧会话仍显示旧值（会话级 GUC 初始化
早于 reload），须用新会话验证。

**怎么验证的**：`df /dev/shm`=8.0G；新会话 `SHOW maintenance_work_mem`
=1GB；9 个库全部完好（含 s12f 历史库与候选库）；第五次构建通过
全部守卫并完成 alembic C2_0013 迁移。

**影响哪些问题**：同 R6——把"13 小时处撞墙"的残余风险与建索引段
的容量风险一次性清除；构建时长预期不变（>13h 到决策段，全流程
一天以上）。

---

## 2026-08-21 R8：4.3 四度卡点——域投影持久化哈希校验失败（诊断中）

**做了什么**：

1. **第五次尝试跑了 ~29h 后在域投影持久化再崩**（比上次又深一层：
   身份 ✓ 132,358 + 决策 ✓ 10,773 均已提交，域投影写入中途）：
   `DomainProjectionPersistenceError: durable inclusion decision
   envelope/hash is inconsistent`（domain_projection_postgres.py:876，
   整个事务回滚，现场无数据可查）。
2. **静态排查（全部排除）**：该错误由五项比对触发（4 项信封列 +
   1 项"存储哈希 vs 重建对象重算哈希"）。逐一核查：
   - `path` 字段不对称（读回不恢复 path）：排除——域纳入引擎全部
     决策 path=None（模型校验器强制 inclusion 决策不得带 path）；
   - `supporting_assertion_ids` 顺序（写入原序/读回 SQL 排序）：
     排除——InclusionCandidate 校验器强制排序；
   - 双重持久化同 release 撞行：排除——_insert_row 是裸 INSERT，
     会先撞唯一键而非哈希错；
   - C2_0013 迁移动过 manifest 表：排除——只动了 identity/relationship
     两张 run 表；
   - policy 表跨 lane 内容冲突：排除——有前置守卫（:457）且未触发。
3. **尝试本地快速复现（未成）**：test_domain_projection_postgres.py
   有全套真库回环测试但被 4 个 CANONICAL_V2_TEST_* 环境变量门控；
   搭好带 marker 的基座库 + 真 gate root 后实跑：10 失败全部因
   **fixture 钉的目录证据是 C2_0009 时代、与现行 C2_0013 pin 不符**
   （"projection request does not bind the installed catalog"）——
   测试基建老化，与本次崩溃无关，属另一待修项。
4. **落地方案（commit 6c517b1）**：把该五项校验改为**自诊断式**——
   报错附带具体差异字段与两侧值（含 content_sha256 行值/重建值、
   score/limitations/assertion_ids/evaluated_at/policy 的原始行值与
   重建值）。第六次启动构建（预计 ~20h 再抵此处），届时要么通过、
   要么报出精确根因。

**发现**：

- 四次崩溃四种性质逐层深入：安全防线 → 代码笔误 → 基础设施容量 →
  **数据/序列化一致性**（当前）。前三类的修复在本轮全部经受住考验
  （本次运行完整通过了全部三个旧崩溃点）。
- 域投影 e2e 测试套件（C2_0009 时代 fixture）已与现行 schema pin
  脱节——构建管道演进时未同步维护这批门控测试，是需要单独排期的
  测试债。

**怎么验证的**：

- 自诊断报错改造后：ruff 过、模块导入过、文件内非门控单测过；
- 第六次构建启动日志确认 DB/staging 自动重置正常、alembic 至
  C2_0013、runner 存活。

**影响哪些问题**：同前；本次为构建可观测性投资——下一轮运行必出
精确根因（或直接通过），不再有猜谜成本。

---

## 2026-08-21 备忘：候选项目「构建检查点续跑」（用户裁定暂缓）

**背景**：四轮重跑累计代价 ~60h，用户提出"已完成段能否持久化、
下次续跑"。结论（详见当日对话）：

- **现状**：各阶段成果崩溃后本就留在库里（identity/decision 已
  验证跨崩溃存活），store 层支持同内容重放——技术基础存在；
- **障碍**：preflight 强制全新空库 + 单次构建生命周期 + envelope
  全链路哈希绑定，"从半成品续跑"被安全设计**有意禁止**（与
  2026-08-19 首次崩溃的 fresh 校验是同一设计）；
- **量级**：需动 preflight/构建器/凭证绑定，属独立工程项目，
  非局部补丁；
- **裁定**：本轮先不做（自诊断运行要么成功要么分钟级修复），
  **触发条件**=全列重建成为常态需求（如月度重灌）或再发生
  ≥2 次深水区崩溃。届时按 OpenSpec 标准流程立项。

**再评估时点**：本轮构建出结果后。

---

## 2026-08-21 需求备忘（用户裁定）：联系方式缺失时的回答规则（P10）

**规则**：用户查询公司联系方式时，若电话/邮箱为占位符或缺失——

1. 直接说明"通过公开渠道无法获得联系方式"，不展示占位符；
2. 转而简要介绍该公司（业务/行业等核心信息）；
3. 若邮箱存在则附上邮箱。

**归属**：服务线（答案合成层）行为，非数据线。落地窗口：P4
数据切换后的下一轮服务线修改（需按 OpenSpec 门禁立项）。**P4
冒烟验收时先人工核对该场景**（18200 上问公司联系方式，看是否
出现"电话：-"式回答——出现即记缺陷）。

**背景**：企业源里电话/邮箱大量为 "-" 占位（爬取时确实无此
信息，占位合理）；风险仅在答案层把占位符当真值展示。

---

## 2026-08-21 产品定位澄清（用户裁定）：出处能力 =「尽量能指出处」

**裁定**：产品定位从「每个答案都能指出处」修正为**「尽量能指出处」**。
理由：库内数据本身是爬取所得，爬取过程中原始出处（URL）已大量丢失；
只指向"内部库"意义不大。

**实测事实**（当日核查源 payload）：

- 爬取 URL 几乎全丢：论文批次无任何 url 字段（5,000 条抽查 0 命中）；
  链接批次只有来源**类型**标签（"个人主页"），无主页地址；
- **但持久标识符大量存活**：论文带 doi / arxiv_id / openalex_id；
  专利带公开号；企业带法人名——这些都能**复原出真实可核查的公开
  出处链接**（doi.org/…、arxiv.org/abs/…、专利公示页）。

**影响三处**：

1. **答案层引用策略**：优先用存活标识符生成公开出处链接（论文/
   专利基本全覆盖）；无法复原的诚实说明"内部整理数据"，不硬凑；
   禁止把"内部库记录 id"包装成出处。
2. **重量账本重算**：深度内部血缘（记录→断言→决策链）的用户价值
   降级，主要剩工程价值（构建完整性/排错）。后续轻量路线评估时
   不再以"答案可深链溯源"作为保留重架构的理由。
3. **根因修复方向**：新采集工具必须记录来源 URL + 采集时间，
   让"尽量"随数据迭代逐次变强。

**P4 验收口径调整**：出处能力按"可复原公开链接覆盖率"报告
（论文 DOI/arXiv 覆盖率、专利公开号覆盖率 100%），不再按内部
血缘深度报告。

---

## 2026-08-21 R9：轻量检索线落地（用户裁定"等不起反复折腾"后与重线并行）

**背景**：用户明确时间约束反转——重线第六次构建仍需 ~7h 到观测
点且不保证通关，不能再单点押注。裁定：**轻量线立即启动，与重线
并行**（重线不杀，跑成是增量收益）。

**做了什么**（`light_lane/`，独立库 `miroflow_light_lane_r1` 带
disposable marker，零接触重线/线上）：

1. `load_light_lane.py`：六个已抽取 JSONL 直接灌库——热字段建列 +
   全量 raw JSONB 保留；pg_trgm 关键词索引；pgvector 扩展。
   计数：company 6,514 / patent 11,408 / paper 24,101 /
   professor 3,652（源 3,735 行含 75 个完全重复编号，首写保留，
   零信息损失）/ link 18,655 / applicant 2,373。
2. `embed_light_lane.py`：4.5 万对象经学校 Qwen3 端点全量嵌入
   （16/批 × 24 并发，断点续传，内容哈希键控幂等）——
   **45,675 条向量，9.5 分钟，零失败**。
3. 三路检索实测全通：
   - SQL：`applicants @> '["深圳市欧拉智造科技有限公司"]'` → 3 条
     真实专利；
   - 关键词（trigram）：论文标题模糊匹配连 en-dash 变体可容错；
   - 语义：四连测全中——「做电池研究的教授」→ 李宝华（真实电池
     领域教授）/「机器人路径规划的专利」→ 3 条对题专利 /「深圳
     做机器人的公司」→ 3 家深圳机器人企业。

**发现**：

- 轻量线从决定到全功能落地 **~1.5 小时**（含嵌入），与重线形成
  数量级的工期对照——代价是无裁决档案/无锚定门/教授不去重变体
  （仅首写去重完全重复行）；论文 24,101 全量可搜（重线按锚定门
  会移除一部分）。
- 嵌入端点吞吐实测 ~80 条/秒，全量 4.5 万 <10 分钟——若将来重建，
  轻量线全程可压缩到 2 小时内。

**怎么验证的**：装载后逐表 count 对账（与 batch-inventory 一致）；
三路检索各≥1 个真实目标命中；嵌入 ok=45,671 fail=0（+4 条冒烟）。

**影响哪些问题**：P5/P8 的"能查到"维度即刻可用（语义/关键词/SQL
三路 + 关系表）；答案生成与出处策略待接服务层。重线结果出来后
两线对照，再定服务线最终用哪条（或重线为主、轻量为检索加速层）。

---

## 2026-08-23 R10：轻量线查询服务交付（12h 交付线，对齐旧 session 三场景）

**背景**：用户裁定时间优先（"等不起反复折腾"），并澄清任务谱系
——本任务由旧 session（sess_0270a6c2）扩展而来，其 Phase 4 验收
画面是三个具体产品场景（优必选专利/具身智能清单/公司详情）。
12 小时交付线据此定义。

**做了什么**（`light_lane/`）：

1. `api.py`（FastAPI，127.0.0.1:18201，admin-console venv）：
   - `/api/search` 语义/关键词/混合（RRF 融合）三模式 + 四域过滤；
   - `/api/company|professor|patent|paper/{id}` 详情端点：公司带
     别名/网页出处/专利列表（按别名扩展匹配）；教授带论文列表
     （附 DOI 公开链接）；专利带申请人解析；论文带公开标识链接；
   - `/api/inventory` 对账数字；占位符（"-"）不出现在详情字段
     （P10 规则落地）。
2. `test_light_lane_api.py`：**11 用例全绿**——三场景 + 语义/关键词
   检索 + 详情/出处/404/占位符过滤 + 计数对账。
3. `reconcile_light_lane.py` + `reconcile-report.md`（P8 口径）：
   四域计数全达标；企业↔专利 **7,668 对**（基线≈0）；教授↔论文
   存活 **12,238** 条（旧包 580）；DOI 覆盖 **98.0%**；专利公开号
   100%；绑定网页出处 684 条；缺口四项如实列出（1,239 未解析
   申请人、6,417 悬空链接、别名覆盖不全、论文无锚定门口径说明）。

**过程坑（记录备查）**：① 重灌表时 DDL 误 DROP embedding 表清空
4.5 万向量——已改为 IF NOT EXISTS 永不重置派生数据，向量重灌
零失败；② 关键词检索最初误绑 embedding JOIN（向量清空期连带
失效）——改为直查实体表；③ `pkill -f` 对含同串的自身命令
反复自杀（第三次）——kill 与 start 严格分调用、awk 匹配过滤
自身；④ payload 键名核对（product_summary 而非
product_description，绑定表 resolved_company/aliases/evidence_urls）。

**怎么验证的**：pytest 11/11（含崩溃后重灌再跑）；对账脚本实测
数字如上；三场景 curl 实测（优必选 448 专利含别名 UBTECH 与
百科/天眼查出处；深圳机器人公司 top5 全对）。

**影响哪些问题**：P5 数据根因闭环（7,668 对企业↔专利 + 448 条
优必选专利可查）；P8 清单完整（6,514 全企业 + 语义/行业过滤）；
P4/P10 规则落地（占位符过滤）。服务端切换仍待终局决策
（轻量线 API vs 重线 serving pack，重线 run 6 仍在跑）。

---

## 2026-08-23 R11：轻量线问答入口交付（"从可查到可问"）

**做了什么**（用户授权自主推进）：

1. `api.py` 扩展：`/api/ask` 有据问答端点 + `/` 极简对话页：
   - 检索组装：问句 n-gram 实体优先（简称→全称，如"优必选"→
     深圳市优必选科技股份有限公司）+ 混合检索补充，最多 6 个
     资料块（企业带别名/专利清单/网页出处；教授带论文+DOI 链接）；
   - 生成：DeepSeek（项目默认 LLM，key 从批准的 .env 文件读取，
     不落代码），系统提示词固化产品规则——只依据资料、联系方式
     缺失按 P10 话术、占位符不展示、样例注明"部分列举"、出处
     必附；LLM 不可用时降级返回检索结果并注明。
2. 实测三类问题全通：优必选专利（准确 448 + 样例 + 出处）/
   深圳机器人公司清单（6 家带业务简介）/ 优必选联系方式
   （数据中实存电话/邮箱/官网，如实展示——P10 仅在缺失时触发）。
3. 测试：`test_light_lane_api.py` 增至 **14/14 绿**（新增 3 个 QA
   用例：计数准确引用/清单结构/联系方式-or-P10 话术+占位符禁现）。

**过程坑（记录备查）**：① 追加在 `uvicorn.run()` 阻塞块之后的
代码永不执行——入口块必须置文件末尾；② DeepSeek 为推理型模型，
max_tokens=800 被思考吃光致正文为空——提至 4000 + 空答案按失败
降级；③ n-gram LIKE 忘加 `%` 通配符成精确匹配；④ 电话号码中的
合法连字符 vs 占位符"-"需按"字段值为 -"形态区分。

**怎么验证的**：pytest 14/14；三类问题 curl 实测原文见日志；
出处链接（DOI/专利号/百科/天眼查）随答案返回。

**影响哪些问题**：P4 数据价值闭环至"自然语言可问"；P5/P8 场景
端到端打通（问→检索→有据回答→出处）。

---

## 2026-08-23 R12：迁移包交付（用户要求 24h 内迁至另一台服务器上线）

**做了什么**（commit 5530a00）：

1. **api.py 全面参数化**：数据库 DSN/监听地址端口/嵌入端点与密钥/
   LLM 密钥文件全部环境变量化（附 `.env.example`）；**嵌入端点不可达
   时优雅降级**——语义检索自动切关键词（响应带 `semantic_available`
   标记），问答照常，不报错。
2. **迁移工件（已彩排验证）**：`light.dump`（pg_dump -Fc，642MB，
   sha256 前 16 位 ed036b10594ef0bc）——**实测恢复 36 秒**；恢复到
   全新空库后起独立实例（18202）跑全套验收 **15/15 绿**——工件
   完整性有证明，不是"应该能行"。
3. **MIGRATION.md 迁移手册**：工件清单（含密钥单独通道警示）、
   目标机前置条件、三种网络情形对应功能档位（校内网全功能/
   仅互联网关键词+问答/离线仅检索）、路径 A 恢复快照（推荐，
   全命令）、路径 B 源数据重灌、验收清单、回退说明。
4. `requirements.txt` + `start.sh`（.env 自动加载、venv 探测）。

**待用户提供（迁移执行的前置）**：目标服务器访问方式、所属网络
情形（能否达 100.64.0.27 校内接口）、密钥安全通道安置。三者齐备
后目标机执行约 30 分钟（手册步骤化）。

**影响哪些问题**：轻量线从"本机可用"升级为"可迁移可上线"；
P4 交付物具备脱离当前服务器独立运行的能力。

---

## 2026-08-23 R13：run 6 观测点结果——诊断命中，差异收窄到最后三个未打印字段；run 7 已启动

**做了什么**：

1. **run 6 在域投影校验点按预测崩溃，自诊断报错带回完整现场**
   （commit 6c517b1 的投资兑现）。逐字段比对（真实数据）：
   - evaluated_at **精确到微秒一致**（UTC）；policy JOIN 重建的
     content_sha256/effective_at 一致；空字段 `[]`/`()` 等价；
     断言 ID 12 条且已排序——**时区/顺序/空值/策略 JOIN 四大
     理论在真实数据上全部排除**；
   - 失败实体锁定：company-p4 批次（aa6494bc…），decision_id
     `domain-inclusion:sha256:6f0c3fd7…`，两哈希
     388858…（写） vs fba6d05…（读）。
2. **残留盲区**：报错未打印 outcome/subject_identity_id/
   release_id 三字段——差异必在其一或写侧对象本身。
3. **commit a656657**：插桩补全（三字段 + 完整重建对象 dump +
    **报错前落盘** `/tmp/domain-inclusion-failure-dump.json`
   防日志截断）。**run 7 已启动**（预计 ~25h 抵达同一点）。

**止损门状态**：这是**同一缺陷类的诊断深化**（非新类别），
按门条款允许本轮修复+一跑；run 7 结果出来若仍不能定位，
则触发止损——服务线轻量线收尾，重线转后台。

**影响哪些问题**：同前；轻量线交付不受影响（20/20 测试、
管理界面、迁移包均已就绪）。

---

## 2026-08-23 R14：本地哈希考古——READ 侧完全复现，写入侧成唯一盲区；改写入侧取证（run 8）

**做了什么**：

1. **本地哈希考古**（利用 run 7 已提交的身份数据查得失败实体
   canonical id：`company-c-0016f96baf79206afb8ff6b1` 深圳市
   尚锐科技）：
   - **READ 哈希 fba6d05… 本地精确复现**（12 条排序断言 +
     outcome=admitted + 全部已知字段）——读回重建对象被 100%
   验证，subject/release/outcome 三字段疑云就此解决；
   - 写入侧哈希 388858… 在"同一断言集合"（断言表行=写入元组，
   同一循环写入，铁证）前提下，穷举五种构造顺序 × 两 outcome ×
   ±1 字段全部未命中——写入对象的真实形态无法从任何读侧
   证据推出。
2. **纠正一个计划失误**：run 7 的插桩只增强读侧，而读侧已无
   新信息——跑完 25h 不会有新产出。果断终止（仅沉没 3h）。
3. **commit 585c37f：写入侧取证**——`_insert_inclusion_decisions`
   把每条决策的完整 model_dump + 计算哈希落盘
   `/tmp/domain-inclusion-write-dump.jsonl`；崩溃时与读侧转储
   **直接逐字段 diff**——写入对象在产生哈希的那一刻被拍下，
   根因必现。**run 8 已启动**。

**止损门状态**：同一缺陷类第三次诊断深化（机制无新类别），
run 8 的取证设计保证终结此案：写入侧与读侧的完整对象都将在
案，差异无处可藏。

**影响哪些问题**：同前；轻量线（20/20+管理界面+迁移包）不受
任何影响。

---

## 2026-08-24 R16：五案告破——排序规则不一致（commit d17deff）；run 9 启动

**根因（双面取证 + 哈希考古闭环）**：

- 写入侧 `supporting_assertion_ids` 按 **Python 字节序** sorted()
  排序（`tech_tags` < `technology_route_summary`，下划线参与比较）；
- 读回侧信任 **SQL ORDER BY**，数据库本地化 collation **忽略下划线**
  （`technologysummary` < `techtags` → 顺序相反）；
- 同一组值、两种排法 → 重建对象哈希必异 → 构建在 29h 处中止。
  **存读一致从未被违反**——用户 8-23 的直觉完全正确：是校验自身
  管道误报。R13 手抄字段时无意用了数据库顺序复现出读侧哈希，
  与 run 8 写入侧转储对照后瞬间归位。

**证据链**（全部可复现）：
1. run 8 写入哈希 == 行哈希（转储忠实）；
2. 写入对象换 run 6 时间戳 → 精确等于 run 6 写入哈希 388858…；
3. PG 实测 `'technology_route_summary' < 'tech_tags'` 为真、Python 相反。

**过程自责**：585c37f 取证插桩缩进错位导致断言插入掉出循环，
run 8 的崩溃是医源性的（写入侧转储本身干净有效）——已在
d17deff 一并还原。

**修复**（d17deff）：`_load_inclusion_result` 取回后用 Python
sorted() 重排；撤销写入侧转储（保留失败侧诊断）；回归测试
`test_domain_inclusion_assertion_order.py` 钉死标点敏感对。
**run 9 已启动**——前 29h 的全部路径（含四个已修根因）均将
带修复重走，其后进入未探明段（关系投影已预猎无同类雷）。

**影响哪些问题**：P4 数据线的最终通关条件就位；两系统一致性
迁移（R15 修正案：全栈迁移+数据升级）依赖本跑产出包。

---

## 2026-08-23 设计契约备忘（用户裁定）：可解释性契约

> **任何硬门禁在触发时，必须保留或输出足以解释"为什么触发"
> 的证据。能检测而不能自解释的门禁，是半成品设计。**
> ——"不能解释，就完全不知道自己在做什么。"

完整工程含义为三条配套，缺一不可：

1. **确定性**：出问题可复现（重线已具备——三次运行断言逐条
   一致）；
2. **证据保全**：触发即现场在案（重线域投影校验缺的正是这条
   ——写入对象算完哈希即丢、事务回滚连证据一起抹掉，导致五次
   触发五次不可解释；run 8 的写入侧转储是补课）；
3. **可测试性**：不用等 25 小时才见到失败（域持久化阶段应可
   独立重放，见"检查点续跑"备忘——优先级因本次教训上调）。

**适用范围**：今后任何带硬校验/门禁的设计（重线复活、采集
工具、服务线）在方案评审时按此三条逐项过——没有证据保全
设计的门禁不予通过。

**推论一：混装校验必须拆分（2026-08-23 用户质询"这些强校验
是否真在保证存读一致"引出）**。现行域投影校验一次比对三段路
（对象拆列 / 存储往返 / 列重拼对象），任何一段出问题都响但
分不清是哪段。正确形态是两道独立检查：①**列值哈希**——写入
时对实际发送的列值元组算哈希、读回时对实际读到的列值算哈希
比对（这才是"存读一致"的直接验证，失败=存储问题，永远可解
释）；②**重建等价**——对象往返验证（重线投影可重建的独特
价值），单独报错。当日证据（读回哈希已从列值本地复现 + 列值
与写入哈希同表达式同源）支持首优假设：**真正的存读一致至今
未被证明违反，触发极可能是校验自身管道的不对称**——待
run 8 双面取证定论。

---

## 2026-08-23 R15：架构终局定案（用户裁定）——服务线=轻量线；重线取证后归档

**裁定**：经过需求-设计对照（用户十日内的全部产品规则 vs 重线
设计分层），确认**错配**：五次崩溃 100% 发生在超出当前需求的
审计/校验层，零次发生在数据质量层；用户真正需要的部分轻量线
已交付。

1. **服务线定案：轻量线**（18201，20/20 测试、有据问答、管理
   界面、迁移包）。
2. **重线**：run 8 后台跑完取写入侧取证（可解释性契约欠账 +
   数据质量层有无真缺陷的最后证据），随后**正式归档**：
   - 取证若证实校验管道自身问题（首优假设）→ 归档，数据质量
     层结论"无已知缺陷"；
   - 取证若发现数据质量层真缺陷 → 只修该层，审计层按弱化后的
     出处需求直接裁撤。
3. **重线复活条件**（明确写下，防止无意识重启）：产品将来
   真需要审计级出处（如面向机构客户）或常态化重建时，按契约
   三前置**重建**而非复活旧设计——证据保全、列值哈希与重建
   等价拆分、阶段级可测（快照+独立重放）。
4. **流程教训入册**：产品定位变更（8-21 出处弱化）必须触发
   依赖设计的复审——本次错配的根源是需求变了、设计冻结。

**影响哪些问题**：P4/P5/P8 的交付路径就此收敛到轻量线
（已交付）；P8 总验收按轻量线对账报告执行；重线止损门由
"条件触发"转为"定时归档"（run 8 取证后）。

---

## 2026-09-03 阶段0传感器交付：三命中率基线 + ROI 缺口清单（G1–G6）

**背景**：用户裁定目标函数（可达 × 诚实分级；点名/语义/关系三命中率），
并裁定"先调查清楚如何把本地数据补齐增强"。阶段0 = 建传感器，不动任何
serving 行为。

**做了什么**：两个只读传感器（`.agents/runs/full-column-serving-pack-rebuild/stage0/`）：
①`stage0_entity_inventory.py` 全量盘点（包↔池差异/别名/分层/绑定/字段）；
②`stage0_golden_attribution.py` golden set 34 查询（seed=42）打 18188
stream 接口，逐车道归因。完整报告见
[2026-09-03-stage0-hit-rate-baseline.md](./2026-09-03-stage0-hit-rate-baseline.md)。

**发现**（基线 + 六缺口，按 ROI 排序）：
- 三命中率基线：点名 12/29≈41%（exact 车道仅专利号 3/24 命中，名称类全零）；
  语义 2/4；关系 3/6（教授→论文通、企业→专利 0/3）。
- **G1 引用层 web 挤出本地**（14/34，最高频）：本地 lexical/vector 有召回、
  引用全 web。纯代码线（融合/引用选择），建议最先切。
- **G2 exact 名称匹配零命中 + 别名面缺失**（企业别名仅 4.8% 有值；
  规范名全等查询 exact 也为 0——`_matches_exact_request` 对名称 display
  terms 是否生效存疑，切片先读代码）。
- **G3 企业↔专利关系类型断链**：规划路径 `company_has_patent`，包内关系
  注册表**无此类型**（绑定以 `patent_has_applicant` 入库）——2.4GB 关系
  文件内 957 条 resolved 绑定不可达。一次类型映射修复可通。
- **G4 论文范围缺口**：包 10,390 / 池 24,058（41%），其余三域池覆盖≈100%
  ——范围问题已收敛到论文单域。池外论文点名 0/5 全灭（端到端确认）。
- **G5 教授画像字段薄**：research_directions 37% 非空、name_en 7%、别名 0、
  论文链接覆盖 24.8% ——教授属性查询本地召回但答案只用 web。
- **G6 诚实分层未启用**：包内 32,941 条全 admitted、0 limited（披露债，归
  阶段1准入矩阵）。
- 好消息：教授点名 5/5、专利号点名 3/3、教授→论文 3/3、企业属性 2/2 通。

**怎么验证**：报告§一有复现命令；golden set 与归因明细落
`stage0-golden-set.json` / `stage0-attribution.json`；归因分类器两处误标
（池外论文 false-PASS、RELATION_NOT_PLANNED 实为 EMPTY）已在报告§二修正说明。

**影响哪些问题**：P5 数据根因细化为 G3（类型断链，非"绑定不存在"）；
P8 质量提升路径明确（G1 引用层先行）；阶段1切片顺序更新为
G1→G3→G2→G4→G5；阶段2（决策持久层修形）仍为 G4 前置。

---

## 2026-09-04 G1 切片交付：本地引用下限（local-citation-floor）——点名 in-pack 12/19→16/19

**背景**：阶段0基线把 G1（引用层 web 挤出本地）列为最高 ROI。本切片按
OpenSpec change `local-citation-floor` 交付。

**做了什么**：两道 floor——
1. **选择层**（`knowledge_serving_isolated.py::_answer_selector`）：点名查询
   （display_name==检索视图）在主循环没绑出本地 claim 时，为每个被点名
   实体合成一条 entity_profile floor claim（本地证据 + 语义文本，计入
   local_claim_limit）。根因：整档案 lookup 证据不带字段 claim_binding，
   主循环按 binding 过滤导致本地全灭（飞象实锤：lexical retained=1、
   answer_subject 正确、citation_count=1 全 web）。
2. **映射层**（`canonical_v2_chat.py::_public_citations`）：handle 绑定的
   本地引用在无官网/主页/DOI 白名单 URL 时不再整卡丢弃，改为发出
   url=None 的档案卡（id=handle id，每 handle 一张，排在 web 卡之前）。
   chat.html 本就支持无 URL 卡渲染。

**发现**：
- 残差 3 例（ByteDance Ltd./字节跳动/Future Mobility）trace 显示
  answer_subject=深圳市安络科技——**英文名主体解析锚错实体**，归 G2
  （别名+实体解析），非本切片回归。
- 运维新知：冷实例首查 ~9-10 分钟（全量 lookup 解析+校验后入缓存）；
  快速重启会撞 Milvus Lite 文件锁崩溃（须等端口释放）；二分证实首查
  挂起与本次改动无关。

**怎么验证**：分层证据见
`.agents/runs/local-citation-floor/verification.md`——①新测试 6 个
（2 RED→GREEN + 4 对照）②回归 adapter 132/132、serving 套件 15/15
（closure 套件 3 失败为预存，stash 对照排除）③E2E golden set 复跑：
点名 in-pack **12/19→16/19**（企业 2/7→4/7、论文 2/4→4/4、教授/专利
保持）、语义 2/4→3/4、关系 3/6 不变（G3 范围）、池外论文 0/5 诚实保持。
飞象答案正文改为本地档案内容+本地引用卡。

**影响哪些问题**：G1 关闭；G2 获得新证据（英文名锚错实体）；
P5（G3）与 G4（论文范围）不变；目标函数"可达"腿的引用环节达标。

---

## 2026-09-04 G3 诊断修正：关系遍历代码无辜，缺口在绑定数据（48 家 vs 950 家）

**背景**：阶段0报告初判 G3 为"关系类型断链"。本切片准备修代码前先做
根因深化，结果推翻初判。

**做了什么**：证据链三步——①trace 证实 golden 三条失败查询的锚定与
路径规划都成功（domains=['patent']、relationship 车道已规划）；
②读遍历实现发现类型翻译层本就存在（company_has_patent→
patent_has_applicant inverse）；③流式扫描 2.4GB relationships.json +
阳性对照探针。

**发现**：
- **serving 遍历代码正常**：普渡科技（包内绑定 Top1，85 条）查询返回
  relationship:17 候选——阳性对照通过。
- **真实缺口是数据**：包内仅 **48 家企业**有申请人绑定（~290 实例），
  池内 950 家/7,668 对；golden 三家全不在包内绑定集（其 canonical id
  在文件里只出现在断言/决策上下文，从不在 target_endpoint）。
- 缺失批次 = `p4-applicant-binding-full-v1`——正是被杀的 run 9/10
  在重建的东西。

**怎么验证**：`.agents/runs/full-column-serving-pack-rebuild/stage0/
g3-diagnosis.md`（含复现命令）；阶段0报告 G3 节已按此修正。

**影响哪些问题**：G3 从"代码修复"改道"数据交付"——绑定批次入包
依赖阶段2瘦管线修形（决策持久层），优先级与 G4（论文批次）合并；
下一刀改为 G2（别名/主体解析，纯代码线，有 G1 残差 3 例新证据）。
P5 数据根因口径同步修正。

---

## 2026-09-04 G2a 切片交付：exact 车道剥 `[lane=exact]` 标记——exact 命中 3/24→16/24，点名 in-pack 18/19

**根因**（一行）：planner 给每条车道查询盖章
`f"{pure_topic} [lane={lane}]"`，lexical/vector/web 车道都会剥自己的
标记再匹配，**exact 车道从不剥**——名称等值匹配结构性不可能，只有
专利号走 `exact_identifier` 保护槽（值干净）幸存。G6 长标题 containment
对尾部标记不敏感，所以这个 bug 藏在 G6 后面。

**做了什么**：`_matches_exact_request` 改用 `_exact_query_phrase`
（仿 `_lexical_query_phrase`：剥标记+剥引号），等值与 containment 两处。

**怎么验证**（`.agents/runs/exact-lane-name-marker-strip/verification.md`）：
①新测试 3 个（1 RED→GREEN + 2 对照，对照证明标记是唯一破坏点）；
②exact/lexical 扫描 84 过 1 挂（挂的为预存，stash 对照排除）；
③E2E 重启复跑 golden set：**exact 命中 3/24→16/24；点名 in-pack
16/19→18/19（95%）**；ByteDance Ltd. 与 Future Mobility 从"主体锚错"
翻转为正确锚定 PASS。残差：字节跳动（别名不在包内，归 G2b 数据项）、
池外论文 0/5（归 G4）。

**影响哪些问题**：G2 的代码侧闭环；G1 残差 3 例中 2 例消除；
目标函数"可达"腿的确定性锚定（exact）恢复。剩余 G2b（别名闭包，
数据工件）与 G3/G4 同为数据线队列。

---

## 2026-09-04 阶段2交付：thin-decision-persist（R15 推论一落地）——run 9/10 冻结点的修形

**背景**：run 9/10 在决策持久层冻结 13h（55/88 抓栈），无完成路径。
R15 已裁定正确形态（推论一：列值检查与重建等价拆分），本切片落地。

**做了什么**（canonical_decision_postgres.py）：
1. **事务内全量读回+整树比较 → 原始元组多重集验证**：`_written_batches`
   独立重建每张写入表的行（与插入器独立构造，漂移即失败），插入后按
   各自作用域读回原始元组比对（Jsonb/datetime 归一，无对象构造）。
   开发中该验证抓住了本切片自己的 3 个 bug（字段名/unnest 形式/
   dict_row 归一）——fail-closed 特性实证。
2. **幂等重放短路**：批次已存在 → 同款元组比对；相等直接返回输入
   （相等性已证）；冲突报 replay conflict（消息兼容）。重启不再重付
   全量重建代价——被杀运行无法前进的死结解除。
3. **超链检查集合化**：逐决策递归 CTE → 每族 2 条批量查询（unnest
   并行展开，20k/块），错误语义与消息保持。
4. **重建等价移到提交后金丝雀**：≤5,000 决策的批次提交后全量重建
   核对（检测保留、不再阻塞回滚）；大批次跳过（列值检查已证存储
   一致）；`CANONICAL_V2_DECISION_REBUILD_CHECK=always|off|auto`。

**发现**（诚实记录）：超链查询实测仅 0.19ms/决策（~190k 也只 ~1 分钟）
——**不是** 13h 冻结主犯；主犯确认为事务内 `_load_result` 重建
（冻结 wchar + R 态 CPU + psycopg 等待栈形完全吻合），该路径已不在
提交前运行。另：决策表带 append-only 触发器+FK+终态角色唯一约束——
存储层本身防篡改（设计测试时发现）。

**怎么验证**（`.agents/runs/thin-decision-persist/verification.md`）：
①新测试 3 个（replay 零重建、冲突检测零重建、金丝雀开关 0/1 计数）
②存量 46/46 + 合并 49/49 全过（错误契约/回滚/往返语义保持）
③性能：超链 A/B 11x；机制量级：每批次 2 次全图重建 → 0（提交前）。

**影响哪些问题**：run 10 重启的公共前置完成；G3（绑定批次）与 G4
（论文批次）的数据交付路径解锁。下一步：重启 run 10（带资源监控）。

---

## 2026-09-04 run 10 重启（瘦 persist 首航）

**发射检查**：envelope 无残留 ✅；watchdog（8-29 起）存活并已锁定新
runner ✅；磁盘 1.2T 余 ✅；候选库空净（上次冻结事务已随 kill 回滚，
无部分批次）✅；build-v2.sh 幂等标记校验通过（staging 重置）✅。

**发射**：12:20 经 build-v2.sh nohup 启动（16 源批次全量清单）。
5 分钟态：runner 96.7% CPU / 2GB RSS，早期 staging/迁移阶段正常。

**观察计划**：①身份解析段（上次 ~3h，CPU 密集、wchar 静止——
watchdog 会误报自旋，看 py-spy 栈是否在动=在推进）；②**关键观察点
≈3h 处的决策持久段**——上次在此冻结 13h；瘦 persist 下应分钟级穿过；
③完成后 envelope + 新包落 staging，走对账门→重放门→rsync 切换。

---

## 2026-09-05 run 10 完成 + 对账失败：管线通、数据批静默蒸发；批次台账交付

**run 10 机械层成功**：12:20→22:39（10h19m）完成，envelope 5.8GB +
三段 sha 回执。**决策持久段如预期穿过**（旧形态在此冻结 13h）——瘦
persist（f0528b1）首航验证通过。

**对账失败（三组硬数）**：
- 新包与旧包**完全同数**（32,941 docs；论文仍 10,390）——salvage
  24,101 行（全有 title、24,058 个不同标题、源文件 sha 验证在 staging）
  **零新增论文**；探针标题（Crop selection…，不与任何保留论文重叠）
  在断言层 0 命中——行未进合并或合并内蒸发。
- **申请人绑定回归为 0**：新构建 patent_has_applicant 决策=0，而 8-26
  旧包尚有 48 家/约 290 条——8-29 的 P4 合并改写疑似弄丢该路径。
- 教授-论文链接 18,655→10,773（与 10.4k 论文端点门控一致，合理）。

**已排除**：salvage 源损坏（否）、source_id 不匹配（否，cdce88c4 两边
一致）、建造器字段校验（24,071/24,101 过）、重叠跳过（14,205 行不重叠
本应新建）。**未定位到具体掉行**——关键障碍：两个合并函数的 stats
（records_seen/created/skipped…）**算完即丢**（`_p4_create_stats`/
`_applicant_binding_stats` 下划线丢弃）——元缺口④第三次现身。

**交付（批次台账，本轮）**：P4 合并尾部打印 `P4_MERGE_LEDGER`（逐
purpose in/out 计数入 build.log）+ 零贡献批次响亮 typed gap；申请人
合并打印 `APPLICANT_BINDING_LEDGER`。合并测试 13/13 过。**下一次重建
（或离线重放合并）将直接以数字点名掉行**，无需考古。

**决策**：新包**不切换**（严格劣于旧包：对象同数、绑定更少）；18188
继续服务旧包。下一刀：离线重放 salvage 行过 `_map_public_authority`
（带台账），定位掉行后修复，再重跑。

---

## 2026-09-05 run 11 发射（台账武装）+ 双台账即时读数：合并恢复正常

**离线重放结论**：合并函数孤立运行完美（探针行 created=1、7 断言、
台账打印）——静态链路（源→landing→过滤→合并）逐环验证全部无戉，
但 run 10 结果为零，无法静态定位。

**run 11 发射**（11:30，run 10 envelope 保留为 -run10.json，DB/staging
幂等重置）。台账 ~2 分钟即打出：

- P4_MERGE_LEDGER：**paper_salvage seen=24,101 / created=23,957**（104
  重复、30 无效、10 重叠跳过）；company_full created=5,491 + 字段补齐
  1,023（5078678 修复在工作）；patent_full created=9,573；
  professor_full created=2,530。
- APPLICANT_BINDING_LEDGER：**applicants_bound=7,650 / patents_bound=
  7,650**（resolved 1,662/3,192，未解析 1,530 如实计数）。

**判定**：run 10 的双异常（论文 0、绑定 0）在 run 11 **均未复现**——
同输入、合并代码仅差语义中性的台账打印。run 10 异常定性为环境性偶发
（疑似此前被杀运行留下的 staging/标记状态与幂等重置相互作用），
无法回顾性定论；台账现已守护该类问题（零贡献即响亮 gap）。

**进行中**：run 11 预计 ~21:30-22:30 完成；完成后走对账（预期论文
10,390→~34k、绑定 0→7,650）→ golden set → 切换评估。
