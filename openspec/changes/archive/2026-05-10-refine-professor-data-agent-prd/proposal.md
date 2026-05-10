# Proposal: 完善 Professor Data Agent PRD — 引入 Agent 驱动的迭代采集架构

## 背景

当前 `docs/Professor-Data-Agent-PRD.md` 的 Phase 1 采集流程本质上仍是传统爬虫思路：预定义每个字段的固定来源（官网、Scholar、企查查等），按顺序依次爬取。但实际需求是构建一个**离线版 DeepResearch 流程**——每位教授启动一个独立的 agent 循环，LLM 自主判断信息完整度并迭代补充，整个技术路线参考 MiroThinker 的 Orchestrator 模式。

## 核心决策记录

以下是通过探索对话确认的关键决策：

| 决策项 | 结论 | 理由 |
|--------|------|------|
| 迭代粒度 | Per-Professor | 每位教授独立 agent 循环，教授间可并行 |
| Orchestrator | 新写定制 ProfessorOrchestrator | 借鉴 MiroThinker 模式但针对教授采集场景定制 |
| 完整度判断 | LLM 自主判断 | 纯 agent 模式，system prompt 含目标 schema，LLM 决定何时停止 |
| 字段来源 | 不预设固定来源 | agent 在迭代中从任何可用数据源动态发现并填充字段 |
| 采集 vs 清洗 | 分离 | agent 循环只管采集原始信息，清洗作为独立后处理阶段 |
| 同名消歧 | agent 内实时消歧 | LLM 在采集过程中通过交叉验证（机构+方向+合作者）判断信息归属 |
| Phase 分期 | 保持 4 Phase | Phase1 基础采集 → Phase2 独立论文采集(独立Agent/库) → Phase3 合并反哺 → Phase4 验证 |
| Phase 4 执行 | 本地部署 MiroThinker | 不依赖在线服务，本地跑 MiroThinker 做批量验证补采 |

## 变更范围

### 修改文件

`docs/Professor-Data-Agent-PRD.md`

### 具体修改章节

**1. 第四章 4.1 字段定义表**
- 删除固定"来源"列
- 替换为"采集策略"列，描述该字段的动态填充机制
- 说明 agent 在迭代中从官网、web search、Scholar 等任何可用源发现并填充

**2. 第五章 5.1 整体流程**
- 更新 Phase 1 描述为 agent 驱动的迭代采集 + 独立清洗
- 更新 Phase 4 为本地 MiroThinker 部署模式

**3. 第五章 5.2 Phase 1 详细流程 — 重写**
- 引入 BatchScheduler + ProfessorOrchestrator 两层架构
- 描述 ProfessorOrchestrator 的 agent 循环：
  - System prompt 设计（目标 schema + 已知初始信息 + 消歧指令）
  - 多轮迭代机制（爬取 → LLM 解析 → 判断是否补充 → 继续/停止）
  - LLM 自主完整度判断的终止条件
  - 实时消歧策略
  - max_turns 兜底 + 重复 URL 检测 + 工具失败回滚（借鉴 MiroThinker）
- 描述 DataCleaner 后处理阶段

**4. 新增：技术架构章节**
- ProfessorOrchestrator 与 MiroThinker Orchestrator 的关系
- MCP 工具集定义（playwright_scraper, web_search, scholar_scraper 等）
- Hydra 配置方案
- 并发模型与资源管理

**5. 第五章 5.4 Phase 4**
- 改为"本地 MiroThinker 服务做批量验证补采"

## 不做的事

- 不修改 Paper-Data-Agent-PRD.md（Phase 2 是独立 Agent 的 PRD）
- 不涉及代码实现
- 不改变数据模型的字段本身（只改来源描述方式）
- 不改变验收标准（第八章）

## 架构参考

```
BatchScheduler
├─ 爬取高校教师列表 → 发现教授 URL
├─ 并发控制 (per-site rate limit)
└─ 分发 Per-Professor 任务
    │
    ▼
ProfessorOrchestrator (借鉴 MiroThinker)
├─ System Prompt: schema + 初始信息 + 消歧规则
├─ 多轮循环 (max_turns 兜底):
│   ├─ 工具调用 (MCP: scraper/search/scholar)
│   ├─ LLM 解析结果 → 更新已知字段
│   ├─ LLM 判断: 需要补充? → 继续迭代
│   ├─ 实时消歧: 交叉验证信息归属
│   └─ LLM 判断: 足够完整 → 输出 raw_data
├─ 机制: 重复URL检测 / 工具失败回滚 / 上下文管理
└─ 输出: raw professor data
    │
    ▼
DataCleaner (独立后处理)
├─ 字段标准化 (职称/机构映射)
├─ completeness_score 计算
└─ 写入 professors.jsonl
```

## 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| LLM 自主判断可能过早停止或过度迭代 | 数据质量不一致 | max_turns 硬性兜底 + Phase 4 验证补采 |
| Per-Professor 并发量大时 LLM API 成本高 | 预算超支 | 5000+ 教授 × 平均 8 轮 × API cost 需预估 |
| 实时消歧在 agent 内增加复杂度 | 开发周期 | 消歧作为 system prompt 指令，不需要额外代码逻辑 |
