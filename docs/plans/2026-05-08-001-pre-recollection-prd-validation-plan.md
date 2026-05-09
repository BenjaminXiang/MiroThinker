---
title: "Pre-recollection PRD validation plan — 代码-vs-PRD 验收, 与数据清空-重采解耦"
type: plan
status: open
date: 2026-05-08
owner: Claude (designer/planner) → Codex (implementer)
origin:
  - docs/index.md  # §产品需求 / 架构（与实现对应） — 状态矩阵
  - docs/Data-Agent-Shared-Spec.md
  - docs/{Company,Professor,Paper,Patent}-Data-Agent-PRD.md
  - docs/Agentic-RAG-PRD.md
  - docs/Agentic-RAG-Operating-Guide.md
  - docs/Multi-turn-Context-Manager-Design.md
depends_on:
  - 2026-04-18-002-real-data-e2e-and-db-separation  # 双 DB 隔离基础
  - 2026-04-18-008-pipeline-run-id-trace            # run_id trace V007
sequencing:
  - 本计划是**重采前**的代码契约验收闸，输出物之一 (P2-data-wipe-and-recollect-runbook) 是后续重采计划的入口。
---

# 重采前 PRD 验收计划（与数据清空-重采解耦）

## 0. 起因 / Context

当前现状（`docs/index.md` 实现状态矩阵 2026-05-04 校准）：

- 四域采集与 Agentic RAG 代码路径已基本铺到位，但状态矩阵里 7 个 PRD 行**没有一行是 ✅**，全部 🟡。
- 关键缺口集中在：① classifier 真实基准未在 host 复跑；② paper `quality_status=ready` 仍 `0/7297`、`summary_zh` 未 rebackfill 到 Milvus；③ company Top-5 待人工标注；④ homepage selector 覆盖不足；⑤ 多轮上下文完整设计未落地。
- 现有 Postgres 数据是**多版本迭代的产物**（V001–V018 + 多次 backfill / promote），数据正确性已经无法支撑"代码是否满足 PRD"的判断。
- 用户决定：**清空当前采集数据 → 重跑全流程 → 拿干净数据做 PRD 验收**。

直接的问题：如果代码本身就漏实现了某条 PRD 要求，重采是浪费一次。所以**重采之前必须先做一轮 "code-vs-PRD" 验收**，确认代码路径在干净 fixtures / 小规模真实数据下能跑通契约。

## 1. Goal / Non-goal

**Goal**

- 在**不依赖现有混乱数据**的前提下，对状态矩阵 7 行（4 域 PRD + Agentic RAG PRD + Multi-turn + Paper-Multi-Source）逐行产出一份 **可执行的代码契约验收单**，每行落到 `docs/index.md` 验收模板的 4 要素：
  1. 测试集来源
  2. 样本量
  3. 评判标准
  4. 评审方式
- 区分两类 gate，避免互相绑架：
  - **G-code**: 用 fixtures / mock / ≤10 条手工 clean 数据可验的代码契约；**重采前必须全绿**。
  - **G-data**: 必须靠真实重采产出的数据规模才能验的指标（去重率、ready 率、Top-5 准确率等）；**重采后**单独跑。
- 输出**重采前-重采中-重采后**三阶段的 runbook 钩子（不在本 plan 内详写 runbook，只定义其 entry/exit）。

**Non-goal**

- 不在本计划内执行任何采集、清空、回填、benchmark。本计划只产出"如何验"。
- 不修改 PRD 本身，也不调整 PRD 的验收阈值。如发现 PRD 写法不可验，进 §10 风险表，由用户决定是否回到 PRD 修订。
- 不展开多 schema 物理迁移、不展开 admin auth/CORS 收敛（属另一条线，参见 plans/2026-04-18-006）。

## 2. 验收策略 — 把数据从代码里抽出去

PRD 里大量验收都写成"在线/真实数据集上的指标"，这种验收**天然依赖采集结果**。本计划把每条要求拆成两层：

```text
PRD requirement
  ├── G-code:   契约 / 字段 / 路由 / Pydantic / evidence shape / run_id  → fixtures / 单测 / 整型测试可验
  └── G-data:   规模性指标（ready 率、Top-K 准确率、覆盖率、误杀率）        → 仅在重采后真实数据上验
```

固定不变的纪律：

- **G-code 全绿是重采的前置 gate**。任一 G-code 失败 = 该域代码路径有缺口 = 不重采，先修代码。
- **G-data 失败不阻塞代码 freeze**，但要回写状态矩阵；多次 G-data 失败累积到一定程度则触发 PRD/算法层重新设计（不在本 plan 内）。
- **不允许在 G-code 里偷换标准**（例如把"Pydantic 校验通过"等同于"PRD 要求满足"）。每一行 G-code 必须能直接 trace 回 PRD 段落号或合同字段。

## 3. 适用代码路径与冻结范围

进入 G-code 验收前，对以下路径执行 **soft freeze**（只允许契约/测试修复，不允许新功能）：

```text
apps/miroflow-agent/src/data_agents/contracts.py
apps/miroflow-agent/src/data_agents/evidence.py
apps/miroflow-agent/src/data_agents/linking.py
apps/miroflow-agent/src/data_agents/normalization.py
apps/miroflow-agent/src/data_agents/publish.py
apps/miroflow-agent/src/data_agents/runtime.py
apps/miroflow-agent/src/data_agents/{company,professor,paper,patent}/**
apps/miroflow-agent/src/data_agents/canonical/**
apps/miroflow-agent/src/data_agents/quality/**
apps/miroflow-agent/src/data_agents/storage/milvus_collections.py
apps/miroflow-agent/src/data_agents/service/{retrieval,search_service}.py
apps/admin-console/backend/api/chat.py
apps/admin-console/backend/storage/chat_session.py
apps/miroflow-agent/alembic/versions/V001..V018
```

冻结期间允许的改动：

- 补/修单测、契约测试、fixture；
- 修缺失的 Pydantic 字段或字段约束（前提是属于"代码漏实现 PRD"范畴，并在本 plan §4–§9 里有 trace）；
- 修运维脚本里的 idempotency / dry-run 行为。

不允许的改动：

- 改 PRD 阈值；
- 引入新功能、新依赖；
- 修历史 Alembic 迁移；
- 改 evidence/run_id 序列化形式。

## 4. 状态矩阵 → 验收单（逐行展开）

每行格式：

```text
S-x.x  G-code 项                           证据来源 / 测试入口            判定
S-x.x  G-data 项                           需要的数据集                   推迟到重采后
```

### 4.1 Data-Agent-Shared-Spec（合同层）

PRD 段落对应：`docs/Data-Agent-Shared-Spec.md` 全文；逻辑契约 + evidence + run_id + 四域共享 schema。

| 编号 | 类型 | 验收项 | 入口 / 测试集 | 样本量 | 评判标准 | 评审方式 |
|---|---|---|---|---|---|---|
| S-1.1 | G-code | 四域 ingest → publish 任一对象产出 row 必带 `evidence`（结构合规）+ `run_id`（V007 schema） | `apps/miroflow-agent/tests/data_agents/test_publish.py` + 新增契约测试 `test_evidence_shape_contract.py` | ≥ 1 row/域，共 4 row | `evidence` 字段在线 schema 与 §术语表 evidence 结构一致；`run_id` 非空且能匹配 `pipeline_run` | 自动化（pytest） |
| S-1.2 | G-code | `quality_status` 取值仅在 `{ready, needs_review, low_confidence, needs_enrichment}` | `data_agents/contracts.py` `quality_status` enum + `tests/data_agents/test_contracts_status.py` | 全代码静态扫描 + 单测 | 任何域 publish 不允许写入 enum 之外的值 | 自动化（pytest + mypy/pyright） |
| S-1.3 | G-code | `service/retrieval.py::_VALID_DOMAINS == {professor, paper, company, patent}` 且 `get_object`/`get_related_objects` 4 域均不抛异常 | `tests/data_agents/service/test_retrieval_domain_coverage.py`（新增） | 4 域 × 1 已知 id × 2 接口 = 8 case | 接口 200 返回；object_type 与请求一致 | 自动化（pytest，使用 fixtures 模拟 4 域 1 row） |
| S-1.4 | G-code | 跨域 link 走 normalization + 公开 evidence；不存在硬编码姓名/公司名映射 | `rg -n "if.*name.*==" src/data_agents/{linking,*/*linking*}.py` + `tests/data_agents/test_linking_normalization.py` | 静态扫描 + 1 单测 | 不允许文字硬编码；linking 必须经 `normalization.py` | 人工复核 + 自动化 |
| S-1.5 | G-data | 跨域 link 准确率 ≥ 95%（PRD §术语表 验收模板示例） | 标注集 ≥ 100 对（重采后人工抽样） | ≥ 100 对 | 人工判定是否同实体 | 人工抽检 |

### 4.2 Company-Data-Agent-PRD

| 编号 | 类型 | 验收项 | 入口 | 样本量 | 评判标准 | 评审方式 |
|---|---|---|---|---|---|---|
| S-2.1 | G-code | XLSX import → canonical company row 全字段（name / credit_code / 法人 / 别名 / 关系）按 PRD §字段 落入 Pydantic 模型且 evidence 指回 source_file | `tests/data_agents/company/test_import_xlsx.py` + 新增 `test_import_xlsx_pdr_field_coverage.py` | 1 条最小测试 XLSX，覆盖 PRD 全字段 | 100% 字段非空（or 注明可选）；evidence.source_type=`xlsx_import` | 自动化 |
| S-2.2 | G-code | Top-5 retrieval 路径：`service/retrieval.py` company 分支可对 5 条 fixture 公司返回 ≤5 条结果且 source 可 trace | `tests/data_agents/service/test_retrieval_company.py` | 5 条 fixture × 3 query | 命中率 100%（fixture 内 ≥1 命中） + 每条结果带 evidence | 自动化 |
| S-2.3 | G-code | narrative + Top-5 字段（`profile_summary`、`technology_route_summary`）由 `company_narrative_backfill` 写入，且能被 chat D 路由读取 | `tests/data_agents/company/test_narrative.py` + `apps/admin-console/tests/test_chat_*` 中 company D-case | 5 条 fixture | 字段存在 + chat D handler 在 fixture 上返回非空答案 | 自动化 |
| S-2.4 | G-data | Top-5 ≥ 85% accuracy（PRD §验收）；needs_review 比例 < 5% | 50 条标注集 + 全量 ready 率 | 50 条 | 人工抽检 + 自动统计 | 人工 + 自动化 |

### 4.3 Professor-Data-Agent-PRD

| 编号 | 类型 | 验收项 | 入口 | 样本量 | 评判标准 | 评审方式 |
|---|---|---|---|---|---|---|
| S-3.1 | G-code | V3 crawler → publish 链路在 fixture 学校（≤2 教授）上跑通；`research_directions`、`profile_summary`、metrics 字段均落库 | `tests/professor/test_pipeline_v3_e2e.py` + fixture school adapter | 1 fixture school × 2 教授 | 全字段非空 + name-identity gate 通过 | 自动化 |
| S-3.2 | G-code | name-identity gate（Round 7.17）拒绝合成 negative case（`canonical_name` ↔ `canonical_name_en` 不一致） | `tests/data_agents/professor/test_name_identity_gate.py` | 5 positive + 5 negative | 5 negative 全部进入 `pipeline_issue` | 自动化 |
| S-3.3 | G-code | 教授 ↔ 论文 link 走 ORCID / paper id 匹配，不依赖姓名相似度作单一信号 | `tests/data_agents/professor/test_paper_link.py` | 3 教授 × 3 paper fixture | 至少一条 link 由 ORCID 触发；纯姓名相似度命中需 ≥2 共同作者 | 自动化 + 人工复核 |
| S-3.4 | G-data | STEM/HSS 抽检 ready 率 ≥ PRD 要求；真实 web fallback 触发率与精度 | 重采后产出全量 + 抽样标注 | 抽样 ≥ 50 教授 | 人工判定 | 人工抽检 |

### 4.4 Paper-Data-Agent-PRD

| 编号 | 类型 | 验收项 | 入口 | 样本量 | 评判标准 | 评审方式 |
|---|---|---|---|---|---|---|
| S-4.1 | G-code | `run_homepage_paper_ingest.py` dry-run 在 1 条 fixture 教授主页上能产出 ≥1 paper candidate（不要求真实抓取通过，验路径） | `tests/scripts/test_run_homepage_paper_ingest.py` | 1 fixture HTML | 不抛异常 + 输出包含 paper_id 占位 | 自动化（fixture HTML） |
| S-4.2 | G-code | OpenAlex / S2 / ORCID 三通路在 mock provider 下可独立工作并合并 | `tests/data_agents/paper/test_multi_source.py` | 1 paper × 3 source mock | 合并后 evidence 同时含 3 source 标记 | 自动化 |
| S-4.3 | G-code | `paper_doi_verify` 在已知 DOI fixture 上正确匹配；OpenAlex 弃用字段 (`host_venue`) 已替换（参见提交 e55b1a8） | `tests/data_agents/paper/test_doi_verify.py` | 5 known + 5 unknown DOI | 已知 verified=true；未知 verified=false | 自动化 |
| S-4.4 | G-code | `summary_zh` 字段写入 paper 行；`paper_chunks` Milvus collection schema 包含 summary chunk_type | `tests/data_agents/paper/test_summary_zh.py` + `tests/data_agents/storage/test_milvus_collections.py` | 1 paper fixture | 字段写入 + Milvus schema 校验 | 自动化 |
| S-4.5 | G-data | `quality_status=ready` 比例（PRD 阈值待定）；`summary_zh` Milvus rebackfill 完整覆盖 | 重采后全量 | 全量 | 自动统计 | 自动化（重采后） |
| S-4.6 | G-data | DOI verify 已知样本 unverified 率（W13-14 Q-10/Q-11 根因已修，需重测） | 100 paper 标注集 | 100 | unverified ≤ PRD 阈值 | 自动化（重采后） |

### 4.5 Patent-Data-Agent-PRD

| 编号 | 类型 | 验收项 | 入口 | 样本量 | 评判标准 | 评审方式 |
|---|---|---|---|---|---|---|
| S-5.1 | G-code | XLSX import → canonical patent + summary_text；`patent_profiles` Milvus collection schema 校验 | `tests/data_agents/patent/test_import_xlsx.py` + `test_release.py` + `test_exact_backfill.py` + Milvus schema test | 5 条 fixture 专利 | 全字段写入 + Milvus collection 创建成功 | 自动化 |
| S-5.2 | G-code | 申请人 normalize（公司名 → canonical_name）pipeline 行为可测 | `tests/data_agents/patent/test_applicant_normalize.py` | 5 multi-applicant fixtures | 多申请人全部进入 link 候选 | 自动化 |
| S-5.3 | G-code | chat 专利 applicant 查询路径（`chat.py` 专利分支）在 fixture 上返回 200 + evidence | `apps/admin-console/tests/test_chat_patent.py`（已有 / 补） | 3 query fixtures | 200 + evidence 非空 | 自动化 |
| S-5.4 | G-data | 多申请人召回率与 link 准确率 | 重采后人工抽样 | ≥ 100 条 | 人工抽检 | 人工 |

### 4.6 Agentic-RAG-PRD（在线服务层）

| 编号 | 类型 | 验收项 | 入口 | 样本量 | 评判标准 | 评审方式 |
|---|---|---|---|---|---|---|
| S-6.1 | G-code | 分类器 7 类 (A/B/C/D/E/F/G) + UNKNOWN 路由代码全在；deterministic fallback 在内部 LLM 不可达时仍返回稳定 7 类标签 | `apps/admin-console/tests/test_classifier_benchmark.py`（fallback coverage 子集） | ≥1 case/类 = 7 case | label ∈ {A..G}，UNKNOWN 永远不上线 | 自动化 |
| S-6.2 | G-code | B/C/D/E/G handler 在 fixture 数据上各自不抛异常并返回带 evidence 的回答 | `apps/admin-console/tests/test_chat_*.py` 全套 | 每 handler ≥1 fixture | 200 + answer 非空 + evidence trace 存在 | 自动化 |
| S-6.3 | G-code | retrieval `_VALID_DOMAINS` 4 域，rerank 不可用时 fallback 到 ANN 顺序（M0.1 R8） | `tests/data_agents/service/test_retrieval_rerank_fallback.py` | rerank 注入失败 mock | 不抛异常 + 日志 warning + 返回非空 | 自动化 |
| S-6.4 | G-code | Serper web fallback 路径可走且在 stub provider 下不调用真实网络 | `tests/admin-console/test_chat_e_handler.py` + provider stub | 1 query | 调用 stub，非真实网络 | 自动化 |
| S-6.5 | G-data | 100-case classifier real-LLM benchmark overall ≥ ADR-008 阈值；B/G 单独达阈 | host 真实 LLM + 100 case 集 | 100 | overall + 子类 | 自动化（重采后或独立 host run） |
| S-6.6 | G-data | 四域 chat E2E：B/C/D/E 各 ≥10 query，answer 命中率 + source 可点击 | 真实重采后数据 | ≥40 | 人工 + 自动化 | 人工 + 自动化 |

### 4.7 Multi-turn-Context-Manager（部分落地）

| 编号 | 类型 | 验收项 | 入口 | 样本量 | 评判标准 | 评审方式 |
|---|---|---|---|---|---|---|
| S-7.1 | G-code | Postgres `chat_session` 表 (V015) + `last_result_set` 列 (V016) 可写入并跨进程恢复 | `apps/admin-console/tests/test_chat_session_persistence.py` | 1 session × 2 process | 第二进程读取到第一进程写入的 entities/last_result_set | 自动化 |
| S-7.2 | G-code | C 路由（跨域跳转）在 fixture 上能消费 `last_result_set` 并切换 domain | `apps/admin-console/tests/test_chat_c_handler.py` | 3 multi-turn fixture | domain 切换正确 + entities 正确 transfer | 自动化 |
| S-7.3 | G-code | D 路由（多轮收窄）在 fixture 上能从已有结果集做 filter | `apps/admin-console/tests/test_chat_d_narrowing.py` | 3 narrowing fixture | 第二轮命中数 < 第一轮 | 自动化 |
| S-7.4 | G-data | `ResultRef` 完整语义、topic switch 策略、跨进程多轮真实脚本验收 | 重采后真实多轮脚本 | ≥ 20 多轮脚本 | 人工 | 人工 |

### 4.8 Paper-Collection-Multi-Source-Design（Phase A）

| 编号 | 类型 | 验收项 | 入口 | 样本量 | 评判标准 | 评审方式 |
|---|---|---|---|---|---|---|
| S-8.1 | G-code | Phase A provider 优先级编排 / fallback 逻辑覆盖单测 | `tests/data_agents/paper/providers/test_priority.py` | mock 4 provider | 优先级序列与 plan 005 一致 | 自动化 |
| S-8.2 | G-data | Phase A 真实 dogfood 报告（Phase B 不在重采前范围） | 重采后 | — | 报告归档于 `docs/source_backfills/` | 人工 |

## 5. 跨切面 G-code（无法挂在单一 PRD 行）

| 编号 | 验收项 | 入口 | 评判 |
|---|---|---|---|
| X-1 | Alembic V001–V018 全部在干净 Postgres 上 `upgrade head` 成功；`downgrade -1` 在最近 5 个版本上可逆 | `tests/alembic/test_migrations_clean.py`（新增） | 全 OK |
| X-2 | Milvus 4 个 collection 的 `ensure_*_collection()` 幂等 | `tests/data_agents/storage/test_milvus_collections.py` | 重复调用不报错 + schema 一致 |
| X-3 | `.agents/handoffs/` + `docs/index.md` 状态矩阵自动可校验：每个 ✅ 必带代码证据 + 测试证据 link | `scripts/lint_status_matrix.py`（新增小工具） | CI 报错 |
| X-4 | secret / API key 静态扫描全 repo 无 hit | `rg -n "secret\|token\|api_key\|cookie\|credential\|Authorization" . --glob '!**/.venv/**'` | 0 hit（白名单除外） |
| X-5 | `run_id` trace V007 phase 1：所有 publish 写入路径都 attach run_id；phase 2 writer wiring 残余项归档 | `tests/data_agents/test_run_id_trace.py` + 检查 plans/2026-04-18-008 §3.2 | 测试通过 + 缺口入风险表 |

## 6. 与"清空+重采"流程的对齐

本 plan 不写 runbook，只定义 entry/exit 钩子，供后续重采计划直接复用：

```text
Phase 0 — 重采前 G-code 验收（本 plan 主体）
  ├── 入口: soft freeze §3 路径
  ├── 出口: §4–§5 全部 G-code 标记 PASS
  └── 产物: docs/source_backfills/2026-05-08-pre-recollection-gcode-report.md

Phase 1 — 数据快照 + 清空 + 重采（独立 plan）
  ├── 入口:
  │   1. Phase 0 全绿
  │   2. 现有 Postgres / Milvus 数据快照已归档（可回退）
  │   3. 重采参数（school 列表、source 列表、run_id 命名）已锁定
  └── 出口:
      1. 新 run_id 标记的全量数据落 Postgres + Milvus
      2. publish layer 上每个对象都带 evidence + run_id
      3. 旧 run_id 行不在线上读路径出现

Phase 2 — 重采后 G-data 验收（独立 plan）
  ├── 输入: §4 中所有 G-data 行
  ├── 出口: §4 G-data 中至少完成 PRD 阈值检查 + docs/index.md 状态矩阵刷新
  └── 失败处理: 多次 G-data 失败累积 → 触发 PRD/算法层重新设计（本 plan 不展开）
```

**关键纪律**：Phase 1 永远不向前跨越 Phase 0 的 G-code 红灯。代码漏实现 PRD 不能通过"再采一次"解决。

## 7. 工时与并行

| 块 | 估算（Codex 实施工时） | 可并行 |
|---|---|---|
| §4.1 Shared-Spec 5 项 | 0.5 d | — |
| §4.2 Company 4 项 | 1 d | 可与 §4.3 / §4.4 / §4.5 并行 |
| §4.3 Professor 4 项 | 1 d | ↑ |
| §4.4 Paper 6 项 | 1.5 d | ↑ |
| §4.5 Patent 4 项 | 0.5 d | ↑ |
| §4.6 Agentic-RAG 6 项 | 1 d | 依赖 §4.1–§4.5 fixture |
| §4.7 Multi-turn 4 项 | 0.5 d | 依赖 §4.6 |
| §4.8 Paper-Multi-Source 2 项 | 0.5 d | 与 §4.4 并行 |
| §5 跨切面 5 项 | 0.5 d | 全程并行 |

总计串行关键路径 ≈ 4 d；理想并行 ≈ 2 d。

## 8. 输出物

- `docs/plans/2026-05-08-001-pre-recollection-prd-validation-plan.md`（本文件）
- `docs/source_backfills/2026-05-08-pre-recollection-gcode-report.md` — Phase 0 出口报告（每 §4 行的 PASS/FAIL + 测试 hash）
- `.agents/specs/2026-05-08-<slug>.md` — Codex 实施前的具体 spec（按 §4 分块下发，必要时拆多份）
- `.agents/handoffs/2026-05-08-<slug>.md` — Codex 实施 handoff
- 每行 G-code 对应的新增 / 加强测试文件（路径见 §4 入口列）
- `docs/index.md` 状态矩阵更新：把通过 G-code 的行从 🟡 退到 🟡* 标记 "code-契约已绿，待 G-data"，避免与"完整 ✅"混淆

## 9. Done criteria

本 plan 闭合的判定：

1. §4.1–§4.8 + §5 全部 G-code 项已在仓库内有可定位的测试或扫描入口（即使初次运行失败，入口必须已建立）；
2. 每条 G-code 失败均挂入 `pipeline_issue` 或 `.agents/reviews/` 任一处，留下 owner + 截止；
3. Phase 0 出口报告（§8 第二项）写入 `docs/source_backfills/`；
4. `docs/index.md` 状态矩阵被同步刷新；
5. 用户确认可进入 Phase 1（数据清空 + 重采）。

## 10. 风险与未决项

| 风险 | 等级 | 说明 / 处理 |
|---|---|---|
| PRD 阈值不可验 | 中 | 例如 paper `quality_status=ready` 阈值在 PRD 内未明确数值；需用户在 Phase 0 内决定阈值或转 G-data 推迟 |
| classifier 真实 LLM 不可达（ADR-008 历史 sandbox 全 UNKNOWN 教训） | 高 | §4.6 G-code 强制 deterministic fallback 路径；G-data 阶段单独安排 host run |
| Phase 0 揭露代码漏实现，但成本高于 Phase 1 重采 | 低 | 本 plan §6 已规定不可跨越；如出现，单独风险升级请用户决策 |
| 多 schema 物理迁移在重采时被一并触发 | 中 | Phase 1 入口锁定 V001–V018；任何新迁移必须独立计划，不在重采流程里夹带 |
| 重采过程中 evidence/run_id 写路径漏点（plans/2026-04-18-008 phase 2 残余） | 中 | §5 X-5 把 phase 2 残余作为风险登记，不在本 plan 修复 |
| `docs/index.md` 状态矩阵与代码 drift | 低 | §5 X-3 引入 lint 工具，CI 强校验 |

## 11. 不在本计划内（防止 scope 蔓延）

- 数据清空 / 备份 / 重采 / 回填运行（独立 plan）；
- admin-console auth / CORS / upload-pipeline 收敛（已有 plans/2026-04-18-006 跟踪）；
- Multi-turn 完整设计落地（独立 plan）；
- Paper-Multi-Source Phase B（独立 plan）；
- 性能 / 并发 / 缓存 / vector index 调优；
- 任何 PRD 文本本身的修订。

---

## Trace 表（status matrix → 本 plan）

| docs/index.md 行 | 本 plan 节 |
|---|---|
| Data-Agent-Shared-Spec | §4.1 |
| Company-Data-Agent-PRD | §4.2 |
| Professor-Data-Agent-PRD | §4.3 |
| Paper-Data-Agent-PRD | §4.4 |
| Patent-Data-Agent-PRD | §4.5 |
| Paper-Collection-Multi-Source-Design | §4.8 |
| Agentic-RAG-PRD | §4.6 |
| Multi-turn-Context-Manager-Design | §4.7 |
| 跨域 link、run_id trace、Alembic、Milvus、secrets | §5 |
