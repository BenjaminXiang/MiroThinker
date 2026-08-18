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
