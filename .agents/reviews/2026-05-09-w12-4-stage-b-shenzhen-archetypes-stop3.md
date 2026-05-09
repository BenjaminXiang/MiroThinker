---
title: "Review — W12-4 Stage B (Codex stop #3, sandbox network restriction + wrapper-agent false-running report)"
date: 2026-05-09
spec: .agents/specs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md
handoff: .agents/handoffs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md
codex_agent_id: a0d90599ae4700860
codex_job_id: task-moxrgpui-htpdce
prior_reviews:
  - .agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop1.md
  - .agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop2.md
decision: revise-workflow-not-just-handoff
---

# Review — W12-4 Stage B Codex stop #3

## Outcome

Codex 第三次正确触发 spec §11 stop condition。这次 unset proxy ✓、libpq DSN ✓ 都做到了，但 **Codex CLI 默认 sandbox 阻断 localhost 网络**——结构性问题，不是 prompt 能解决的。

并且发现一个**工作流自身的真问题**：codex:codex-rescue 包装层 agent 的「Codex 在后台运行」是**虚假报告**。

## Codex 行为（Discipline ✅✅✅）

- 第三次还是 stop 在该 stop 的地方
- Sandbox 阻断时主动调试：`UV_CACHE_DIR=/tmp` 绕过文件系统 sandbox（合理范围内的工程判断）
- 排除了 proxy / DSN 假设，定位到端口不通才停下
- 没有伪造 fixture、没有越界、没有触碰 protected files

## 真正的根因（claude 二次核实）

```
Codex CLI sandbox modes (codex --help):
  -s read-only            ← 默认或 codex-companion 缺省
  -s workspace-write
  -s danger-full-access   ← 这个才允许 localhost 网络
  --dangerously-bypass-approvals-and-sandbox
```

codex-companion `task` 子命令的 flag 列表：

```
task [--background] [--write] [--resume-last|...] [--model] [--effort] [prompt]
```

**没有 `--sandbox` 或 `--no-sandbox` flag**——所以包装层把 Codex 钉在默认 sandbox 模式上，无论 prompt 怎么写都解不开 loopback 网络限制。

`~/.codex/config.toml` 里 `[projects."/home/longxiang/MiroThinker"]
trust_level = "trusted"` 已经设了，但 sandbox 是另一层，trust 不蕴含 sandbox 解除。

## Workflow-level 问题（codex:codex-rescue 包装层）

我（claude）派发 codex:codex-rescue 子代理，它返回：

> "The Codex task has been dispatched in the background (job ID: b2jbmn6x6).
>  Codex will: 1. Unset all 6 proxy vars... 2. Read the revised handoff..."

**事实上**：
- 包装 agent 自己只跑了 42s，它把 prompt 投递给 codex broker，broker 立刻起 Codex 进程
- Codex 03:04 起，03:07 完工——**当包装 agent 返回时 Codex 早就 stop 了**
- 我以「Codex 在跑」为前提等了大约 25 分钟，其实早结束

如果不是用户问「codex 反馈结果了吗」加上「持续监控」的指令，我会一直等到下次 wakeup 才发现。

## 决定：revise workflow，不只是 handoff

光修 spec/handoff 没用——sandbox 是结构问题，要换路径。

### 路径选择

| 路径 | 说明 | 风险 / 代价 |
|---|---|---|
| **A: 分工调整（推荐）** | claude（无 sandbox）做需要网络/DB 的部分（dry-run before、收集 HTML 样本归档到 logs）；codex（sandbox 内）只做 parser 改造 + pytest（不需要网络）；claude 再做 dry-run after 验证 | 工作流稍复杂，但完美对齐两个 agent 的能力边界 |
| B: 用 Bash 直接调 codex CLI 加 `--dangerously-bypass-approvals-and-sandbox` | 绕开 codex-companion 包装 | 失去 codex-companion 的 review-gate / 状态查询 / 资源管理；安全模型变弱 |
| C: claude 全程实现 | 跳过 codex 这一环 | demo 「Claude 设计 → Codex 实现」工作流断裂；但现实可行 |

**首选 A**：保留 demo 的核心命题（Claude 设计 + 验证；Codex 实现），只是把 sandbox-incompatible 的 IO 挪给 Claude 做。也是最贴合 CLAUDE.md §1 的实际分工——Claude 是 reviewer/data validator，Codex 是 implementer。

## Monitoring follow-up（用户 2026-05-09 指令）

未来所有 Codex 派发必须：
1. 不依赖 codex:codex-rescue 包装 agent 的「running」状态——它会撒谎
2. 派发后立刻设 Monitor，定期 poll `codex-companion status <job-id> --json`
3. 任何 `phase: "done"` / `status: "completed"` 立刻拉 result 看 stop 原因
4. 不要相信「task launched in background」的字面意思

## Files touched (this round)

- `.agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop3.md`（新增）
- 即将：`memory/codex_sandbox_constraints.md`（新增）
- 即将：spec / handoff §13 assumption 列表加 A8 "no sandbox network access for Codex"
- 即将：考虑增加 path A 的 split workflow handoff（取决于用户决策）

无产品代码变更。

## Spec/handoff 假设破坏统计（迄今）

| 假设 | round | 是否成立 |
|---|---|---|
| A1 file no drift | all | ✅ |
| A2 Postgres reachable | round 3 | ❌（sandbox 阻断 loopback；不是 Postgres 真挂）|
| A3 Web Search up | not tested | — |
| A4 prof URLs in DB | not tested | — |
| A5 section ✓ extraction ✗ | not tested | — |
| A6 proxy unset | round 2/3 | round 2 ❌; round 3 ✅ |
| A7 libpq DSN | round 1 | round 1 ❌; round 2/3 ✅ |
| **A8 sandbox network** | **round 3** | **❌** |

每一轮都暴露了一个结构性 invariant 进入 spec/memory。三轮 stop 的工程价值：
- 隐式 invariant 显式化：DSN 形式、proxy 绕开、sandbox 边界
- 包装层 agent 不可信的「running」语义被发现
- 落地到项目记忆，后续派 Codex 任何任务都自动避开

## Follow-up（不做，仅记录）

- F7: codex-companion `task` 暂无暴露 sandbox flag——可向上游提；本地可考虑直调 codex CLI
- F8: claude 派 codex 之后**强制**立刻 Monitor poll，写成 skill / 工作流模板
- F9: codex:codex-rescue 包装 agent 的「running」语义文档化为「已派发，未必在跑」
