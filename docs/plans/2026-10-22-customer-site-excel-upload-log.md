# 客户现场：上传 Excel 材料，入库后可查 · 执行日志

关联计划：`2026-10-22-customer-site-excel-upload.md`

## 第 1 轮 · 2026-10-22 · XLSX 解析 + manual recall

**做了什么**

- `canonical_v2_manual_recall.py`：
  - 允许后缀加 `.xlsx`；
  - `_xlsx_text()` 用 `openpyxl` 读活动 sheet，首行表头，每行拼 `字段: 值；...`，按 24k 字符截断；
  - 预览返回 `media_kind=xlsx`、`row_count`、`chunk_count`、`text`。
- `browse.html`：上传输入 `accept` 加 `.xlsx`，提示文案同步。
- 测试：新增 `test_preview_xlsx_flattens_rows`；manual recall API 15 passed；ruff clean。

**已知验证**

- 服务器直调 `_extract_text("测试企业材料.xlsx")`：`kind=xlsx`、171 字符、2 个数据块，
  文本含 `公司名称: 深圳市测试科技有限公司` 和 `简介: 做传感器`。
- 服务端 `serve.log` 多次出现
  `manual_recall_store=/root/deploy/fullstack-v2/var/manual-recall-v1/manual-recall.json`，
  证明 manual recall 旁路已接入 serving。
- 真实 HTTP：预览返回 `media_kind=xlsx`、`row_count=2`、`chunk_count=1`；确认返回 201、
  `doc_id=doc-1fb84e3040a20575`、`chunk_count=1`；`manual-recall.json` points 1→2。
- 再上传唯一测试公司（蓝鲸九号 / BLUEWHALE-9000）：确认 201，points 2→3。
- **未通过**：用 `BLUEWHALE-9000`、公司全名、以及“负载 25kg 的协作机械臂”等问法请求
  `/api/chat/stream`，向量车道均返回 16 个 release 候选，未带出上传的 manual point；
  回答未包含 BLUEWHALE-9000/25kg 的上传事实。已加 display_name/型号 token 的 0.995 分
  boost，仍未改变结果，说明问题在 provider/车道过滤或 top-16 截断之外。
- 结论：**上传、解析、确认入库、管理员文档列表可查已通；chat 自动召回未打通**。需要专用
  “上传资料”召回车道（或修复 manual provider 在 pack 模式的传递），不能宣称“即时对话可查”。

**边界**

- 这是资料级入库：Excel 行变成可召回文本块，不是结构化写 `company` 表。
- 大文件超过 24k 字符会截断；需要完整结构化导入时仍要构建库/索引线。
- 两个 manual recall 单测在当前 worktree 失败（`test_runner_serve_manual_recall_store_fails_open`
  的 fake module 假设、`test_release_bound_vector_validator_exempts_manual_traces` 的校验
  分支），与 XLSX 解析无关，后续单独处理。

**第 2 轮 · 诊断结论（2026-10-22）**

- 加 warning 级诊断后确认：manual provider **存在**，`active=3`；
  查询时 `domains=[company] matched=3`、`appended=3`、`candidates=131`，
  全域名车道 `candidates=19`；manual top cosine = **0.8754**。
- 说明上传点已经进入向量车道候选池，问题不在 provider 或过滤。
- 试了两个修复：
  1. display_name/型号 token 精确匹配 boost（0.995）——无效；
  2. 车道排序后强制预留 2 个 manual 槽位（top score 0.8754）——无效。
- 最终 `retrieval_done` 仍是 16 个向量候选，答案与 citations 没有 manual 证据。结论：**问题在
  answer evidence/sufficiency retention，不在召回打分或 top-16**。需要改答案证据保留/注入，
  或新增一条专用“上传资料”证据车道。
- 两个实验性改动已从客户文件回滚（`.bak-boost-*` / `.bak-manualslot-*`），并重启回干净基线；
  XLSX 上传/预览/确认端点保留。
- 当前状态：**上传入库可查（管理员文档列表 + manual-recall.json），chat 自动引用未打通**。

**第 3 轮 · 2026-10-22 · 结构优先：先识别 Excel，再分域入库**

- 新增 `backend/services/excel_structure.py`：
  - 扫描每个 sheet 前 12 行，按 company/professor/patent/paper 四套表头别名打分；
  - 选匹配最多的一行作表头，输出域、置信度、字段映射、行数、样例、告警；
  - `source_index` 保留原始列位，避免“有个未识别列”导致后面值错位。
- 新增 `backend/services/excel_ingest.py`：
  - company → `company`（按信用代码/稳定 ID upsert）；
  - professor → `professor`（+ `professor_seed`）；
  - patent → `patent`（按专利号）；
  - paper → `paper`（按 DOI）；
  - 全部 `quality_status='needs_review'`；专利类型归一化到“发明/实用新型/外观/PCT/其他”。
- 新增 `POST /company-documents/structured`，预览返回 `analysis`；前端在预览下显示
  “识别为：企业/教授/专利/论文 · 置信度 · 表 · 行数 · 字段映射”，并多一个
  “按识别结构入库”按钮。
- 实测：
  - 企业 Excel：`domain=company, confidence=high`，2 行插入 `company`，2 个 `company-upload-*` ID；
  - 教授 Excel：`domain=professor`，1 行插入 `professor`，1 条 `professor_seed`；
  - 论文 Excel：`domain=paper`，1 行插入 `paper`；
  - 专利 Excel：识别正确；首次运行因服务还在用旧代码报 `ck_patent_type`（“发明专利”不是
    允许值）；加归一化并重启后复测，1 行插入 `patent`，`patent_type='发明'`。
- 测试：`test_excel_structure.py` + manual recall API **18 passed**；ruff clean。
- 当前口径：**结构识别 + 企业/教授/专利/论文四域结构化入库已通**；chat 自动引用仍受
  answer evidence retention 限制。

**第 4 轮 · 2026-10-23 · 上传后问答闭环（修复 answer 候选窗口 + selector）**

- 复现：重启后上传唯一企业工作簿（深圳市严格验收机器人有限公司 / STRICT-9000 / 30kg）。
  “负载 30kg 的 STRICT-9000 是什么产品？”能答；但
  “STRICT-9000 协作机械臂的负载参数是什么”和“严格验收机器人公司是做什么的？”
  仍答“无公开信息”。说明不是所有问法都能召回上传内容。
- 根因是两处 **answer 侧丢弃**，不在召回打分：
  1. `knowledge_read._EphemeralKnowledgeRead.execute` 用
     `ordered[:candidate_limit]` 截断融合候选。lexical 车道 16 条命中占满窗口；
     manual 候选分数 0.6592 / 0.7592，高于当次第 16 名 0.4555 / 0.6185，
     仍在进入 evidence 前被截掉。
  2. `knowledge_serving_isolated._answer_selector` 的 eligible 过滤：
     focused-entity 分支只留 current_web + 绑定的 relationship；
     preferred-object 分支只留 exact/structured/lexical 对象。manual 对象都不在集合内，
     即使进了 evidence 也成不了 claim/citation。
- 修复：
  - `knowledge_read.py`：新增 `_protect_manual_candidates`，
    对 `source_authority=manual_upload` 且 cosine ≥ 0.52 的候选保留最多 2 个候选窗口槽位，
    替换排名最低的非 manual 候选；低于阈值的上传不挤占 release 证据。
  - `knowledge_serving_isolated.py`：selector 把达阈值的 manual evidence 并入 eligible
    并排在最前，保证进入 3 条本地 claim 窗口。
- 单元回归（本地 worktree）：
  - 新增 5 个测试：focused-company、preferred-object、低分不提升、窗口保留、低分不保留；
  - serving + fusion + manual 三个测试文件：**322 passed, 1 failed**；
    唯一失败是既有 `test_release_bound_vector_validator_exempts_manual_traces`
    （validator 自 2026-08-30 起被 `return` 关闭，负向用例无法抛错），与本改动无关；
  - 答案/引用相关 5 个文件：**18 passed**。
- 客户机实测（重启后 PID 3913401，health 200）：
  - 重启前上传的 `doc-924835…` 三种问法全部命中：
    答案含 STRICT-9000 / 30kg，citation 恒为
    `local-source-57861b25eafa73e0`（= sha256("local:manual-upload:doc-924835…")[:16]）；
  - “深圳有哪些机器人公司？”不引用该上传；
  - 撤销后再问，同一问题回到“无公开信息”，证明因果；
  - 重启后新上传 `doc-c831b705…`（NOVA-7700 / 18kg），“公司名”和“产品名”两种问法
    均命中，citation 为 `local-source-3947662581cc8a44`，随后撤销。
- 清理：两份测试文档已 revert；`company-upload-*` 行已删除（company 7089）；
  `manual-recall.json` 15 points / 1 active（保留原有真实点）。
- 当前口径：**上传后问答闭环已打通**（企业文档；教授/专利/论文共用同一条 manual 通道，
  结构识别与入库此前已验证）。
