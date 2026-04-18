# Codex + Claude Code 交叉验证工作流 — 使用说明

> 最后更新：2026-04-15

## 一、概览

这套工作流用于在 **`codex cli` 主控开发** 的前提下，引入本机已安装并已登录的 **`claude` CLI** 做独立审查，从而形成闭环交叉验证。

核心目标：

- 让 `Codex` 负责主任务、代码修改、上下文整理和最终交付
- 让本机 `Claude Code CLI` 负责独立的 plan review、code review 或 review comment 生成
- 让 `Claude` 的 review 结果回流给 `Codex`
- 让 `Codex` 基于 findings 继续修复、优化、复核，而不是只转述评论

这不是双开两个独立会话，而是一个**以 Codex 为编排中心**的本地交叉验证工作流。

---

## 二、角色分工

### Codex

- 负责接收你的自然语言任务
- 负责写代码、改代码、整理 review 范围
- 负责补充必要上下文，例如 plan、spec、额外参考文件
- 负责调用本地 `claude` CLI
- 负责消费 review 结果并继续修复或优化
- 负责最终对你回复

### Claude Code CLI

- 通过本机 `claude` 命令参与工作
- 可以作为独立 reviewer，也可以在 review 类任务中作为主执行方
- 输出 review findings、plan review 结论或 review comments
- 不直接接管 `codex cli` 会话

### 访问约束

- 只允许使用本机 `claude` 命令
- 不使用 web search、browser automation、直连 Anthropic API、第三方 Claude 封装或其他替代访问路径

---

## 三、默认闭环

### 1. 实现类任务

默认路径：

`Codex -> Claude -> Codex`

含义：

- `Codex` 先实现
- `Claude` 再对原始改动做独立 review
- findings 回流给 `Codex`
- `Codex` 继续 fix、tighten、optimize

### 2. review 类任务

包括：

- `plan review`
- `code review`
- `review comment` 生成

默认路径：

`Claude -> Codex`

含义：

- `Codex` 调起本地 `Claude`
- `Claude` 产出主 review artifact
- `Codex` 验证结论是否基于原始 plan/diff/files
- `Codex` 决定修复、采纳、驳回或向用户汇报

### 3. 需求不明确时

如果以下信息不明确，`Codex` 应先问你，再调用 `Claude`：

- review 当前工作区、staged，还是某个 base ref 的分支 diff
- 是否只审查特定文件或目录
- 是否需要附带 plan/spec

---

## 四、在 Codex CLI 中怎么说

正常情况下，你**不需要手动跑脚本**，直接在 `codex cli` 里说需求即可。

常见说法：

```text
让 Claude 审查当前改动
```

```text
让 Claude 只审查 scripts/claude_review.py 和 AGENTS.md
```

```text
让 Claude review 当前 staged 改动
```

```text
让 Claude 对这个 plan 做 review：docs/plans/2026-04-06-003-feat-professor-pipeline-v3-implementation-plan.md
```

```text
让 Claude 主做 code review，然后把结果回给 Codex 继续修
```

```text
这个改动比较高风险，先让 Claude 做交叉验证再结束
```

### 高风险改动的自动触发

根目录 [AGENTS.md](../AGENTS.md) 已定义自动触发规则。以下类型的改动，在完成前应自动跑一次 Claude cross review：

- auth
- permissions
- persistence
- data mutations
- external APIs
- background jobs
- deletion/update flows

---

## 五、如何给足 Claude 必要上下文

为了让 `Claude Code` 的 review 更可靠，重点不是“多说几句总结”，而是**给原始 artifact 和必要约束**。

推荐做法：

- 用 `--plan` 传入实现计划或规格文档
- 用 `--context` 传入补充规则、共享 spec 或关键设计文档
- 保持 `--repo-instructions` 开启，让根目录 `AGENTS.md` / `CLAUDE.md` 一起进入上下文
- 用 `--path` 缩小 review 范围，避免脏工作区里的无关改动污染判断
- 让脚本直接收集 diff 和文件快照，不要只给 Codex 手写摘要

典型上下文组合：

- 实现 review：`diff + changed file snapshots + AGENTS.md`
- plan-driven implementation review：`diff + changed files + plan + shared spec`
- 纯 plan review：`plan + 相关 spec + AGENTS.md`

---

## 六、直接调用脚本

底层脚本是：

```bash
python3 scripts/claude_review.py
```

### 1. 审查当前未提交改动

```bash
python3 scripts/claude_review.py
```

### 2. 只审查 staged 改动

```bash
python3 scripts/claude_review.py --staged
```

### 3. 审查相对某个基线分支的 diff

```bash
python3 scripts/claude_review.py --base-ref origin/main
```

### 4. 只审查指定文件或目录

```bash
python3 scripts/claude_review.py \
  --path scripts/claude_review.py \
  --path AGENTS.md \
  --path local-skills/claude-cross-review
```

### 5. 对 plan 做 review

```bash
python3 scripts/claude_review.py \
  --review-type plan \
  --plan docs/plans/2026-04-06-003-feat-professor-pipeline-v3-implementation-plan.md
```

### 6. 给 plan review 附带额外上下文

```bash
python3 scripts/claude_review.py \
  --review-type plan \
  --plan docs/plans/2026-04-06-003-feat-professor-pipeline-v3-implementation-plan.md \
  --context docs/Data-Agent-Shared-Spec.md \
  --context docs/Professor-Data-Agent-PRD.md
```

### 7. 给 code review 附带 plan/spec

```bash
python3 scripts/claude_review.py \
  --path scripts/claude_review.py \
  --plan docs/plans/2026-04-06-003-feat-professor-pipeline-v3-implementation-plan.md \
  --context docs/Data-Agent-Shared-Spec.md
```

### 8. 只验证 prompt 和 scope，不实际调用 Claude

```bash
python3 scripts/claude_review.py --dry-run
```

### 9. 保存 review 报告

```bash
python3 scripts/claude_review.py \
  --path scripts/claude_review.py \
  --markdown-out /tmp/claude_cross_code_review.md \
  --json-out /tmp/claude_cross_code_review.json
```

### 10. 常用可调参数

```bash
python3 scripts/claude_review.py \
  --model sonnet \
  --effort low \
  --max-files 8 \
  --max-file-bytes 6000 \
  --claude-timeout-seconds 300
```

---

## 七、输出与退出码

### 输出文件

可选输出：

- `--markdown-out`：保存可读版 review 报告
- `--json-out`：保存结构化 review 数据，便于后续消费

### 退出码

- `0`：review clean，没有 findings
- `1`：Claude 发现了问题
- `2`：执行失败，例如本地 `claude` 调用失败、鉴权失败或输入不合法

注意：

- `1` 不表示脚本报错，只表示**有 review findings**
- 这些 findings 必须回流给 `Codex`

---

## 八、推荐工作流

### 场景 A：Codex 写代码，Claude 复核

1. 你在 `codex cli` 里提出实现需求
2. `Codex` 写代码并缩小 review 范围
3. `Codex` 调用本地 `claude` CLI 做独立 review
4. `Claude` 返回 findings
5. `Codex` 逐条处理：
   - fix
   - justified waive
   - 明确汇报给用户
6. 如果修复较大，`Codex` 再跑一轮 review
7. 闭环完成后再交付

### 场景 B：Claude 主做 review，Codex 校验和收口

1. 你在 `codex cli` 里要求 `plan review` 或 `code review`
2. `Codex` 收集 plan/diff/raw files
3. `Codex` 调起本地 `Claude`
4. `Claude` 产出主 review artifact
5. `Codex` 校验 findings 是否站得住脚
6. `Codex` 修复问题、过滤弱结论或向你汇报最终结论

---

## 九、常见问题

### 1. 为什么不用 web 或 MCP 直连 Claude

本工作流的设计目标是：

- 主控制权留在 `codex cli`
- review 后端固定为本机 `claude` CLI
- 减少额外 transport 层和多份逻辑

如果后续需要给更多客户端复用，再考虑把同一个 runner 包成薄 MCP 工具。

### 2. 为什么 Claude 的 findings 不能直接当最终结论

因为这套机制强调的是**交叉验证**，不是把责任转交给另一个模型。  
`Claude` 给出 findings 后，`Codex` 仍然要做验证、修复、优化和收口。

### 3. review 结果不准怎么办

先检查三件事：

- scope 是否过大，混入了无关改动
- 是否缺少 plan/spec/context
- 是否只给了手写总结，没有给原始 diff 和文件快照

### 4. 提示 prompt 太大怎么办

优先缩小上下文：

- 用 `--path` 限定范围
- 降低 `--max-files`
- 降低 `--max-file-bytes`
- 只保留必要的 `--plan` 和 `--context`

### 5. 没有检测到改动怎么办

先确认你想审查的是：

- 当前 worktree
- staged changes
- 还是相对 `origin/main` 的分支 diff

如果工作区很脏，优先使用：

```bash
python3 scripts/claude_review.py --staged
```

或：

```bash
python3 scripts/claude_review.py --path path/to/file
```

### 6. 本地 `claude` 无法调用怎么办

先检查：

```bash
claude auth status
```

如果是在受限沙箱里运行 `codex cli`，还需要允许本地 `claude` 相关命令执行。

---

## 十、相关文件

- [AGENTS.md](../AGENTS.md)
- [local-skills/claude-cross-review/SKILL.md](../local-skills/claude-cross-review/SKILL.md)
- [scripts/claude_review.py](../scripts/claude_review.py)
- [tests/test_claude_review.py](../tests/test_claude_review.py)

这四个文件共同组成当前的本地 Claude cross-review 能力：

- `AGENTS.md` 定义触发和路由规则
- `SKILL.md` 定义工作流约束
- `claude_review.py` 负责收集原始 artifact 并调用本机 `claude`
- 测试文件保证 runner 行为可回归验证
