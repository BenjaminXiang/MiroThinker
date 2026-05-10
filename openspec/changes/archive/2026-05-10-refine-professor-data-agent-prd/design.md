# Design: Professor Data Agent PRD 完善

## 设计决策

### 1. 字段定义表重构

将 4.1 的固定"来源"列替换为"采集策略"列。每个字段不再绑定单一数据源，而是描述 agent 在迭代中如何动态发现和填充。

### 2. Phase 1 架构：两层分离

- **BatchScheduler**：负责高校列表遍历、教授 URL 发现、并发任务调度
- **ProfessorOrchestrator**：Per-Professor 的 agent 循环，LLM 自主判断完整度

采集与清洗分离——Orchestrator 输出原始数据，DataCleaner 做后处理标准化。

### 3. 技术路线参考

借鉴 MiroThinker 的核心机制：
- 多轮工具调用循环
- 重复检测与回滚
- max_turns 兜底
- MCP 工具标准化

但不直接复用 MiroThinker Orchestrator 代码，新写定制版本。

### 4. Phase 4 改为本地部署

Phase 4 验证补采使用本地部署的 MiroThinker 服务，不依赖在线 API。
