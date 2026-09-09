# 语义差异评审任务说明（Excel 25 轮 vs 参考答案）

## 输入
- 回放 JSON：`/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation/.agents/runs/rebuild-canonical-v2-knowledge-platform/s12f/acceptance-<TS>/workbook-replay-independent.json`
- 每个 conversation 有 turns，每 turn 含：query、reference_answer（参考答案）、key_points（备注硬要求）、response.answer_text。

## 任务
对 25 个 turn 逐一做差异评审，输出结构化分类报告（Markdown），每轮按以下类别标注：

1. **查准错误（precision）**：答案中的事实性错误、与参考答案冲突的断言、张冠李戴。
2. **查全缺失（recall）**：参考答案/备注中明确要求、但答案缺失的实体或要点。
3. **呈现问题（presentation）**：措辞别扭、元叙述（"根据材料"等）、结构问题、噪声条目（如"PCB厂商之一"类低质量条目）。
4. **覆盖备注（key coverage）**：key_points 硬要求的实体是否出现。
5. **指代/多轮问题**：跨轮指代绑定错误、话题切换失败。
6. **误报澄清**：本应可答却触发澄清的情况。

每轮输出：轮号、查询、类别标签、差异描述（引用答案与参考答案的具体片段）、严重度（高/中/低）。

最后给总体结论：
- 查准/查全/呈现三轴的整体评分印象
- 修复优先级列表（哪些差异最值得下一轮处理）
- 与上一轮（2026-08-02 05:45 回放）相比可观察的变化（如果方便对比的话）

## 约束
- 只读任务：不修改任何文件、不调用服务。
- 输出写到 stdout（或 /tmp/ 下的评审报告文件），长度控制在 4000 字以内，聚焦高价值差异。
- 以参考答案为准绳，但也要判断参考答案本身可能过时/过细的地方（如某实体在备注中未出现）。
