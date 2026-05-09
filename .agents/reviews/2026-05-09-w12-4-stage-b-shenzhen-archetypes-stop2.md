---
title: "Review — W12-4 Stage B (Codex stop #2, §5.1 dry-run Postgres handshake)"
date: 2026-05-09
spec: .agents/specs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md
handoff: .agents/handoffs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md
codex_agent_id: a9bf505427849c7e7
prior_review: .agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop1.md
decision: revise-and-resume
---

# Review — W12-4 Stage B Codex stop #2

## Outcome

Codex 第二次正确触发 spec §11 stop condition，未硬推、未伪造 fixture、未越界。Discipline check ✅✅。

## Codex 报告核心

- 现象：`psycopg.OperationalError: connection is bad: no error details available`
- Codex 误诊建议：「Postgres 没起来，docker start」
- 实际根因（claude 验证）：**代理拦截**，不是 Postgres 没起

## Claude 二次核实（独立验证）

```
$ env | grep -iE proxy
ALL_PROXY=socks5://100.64.0.14:10003
HTTP_PROXY=http://100.64.0.14:10003
HTTPS_PROXY=http://100.64.0.14:10003
NO_PROXY=localhost,127.0.0.1,::1   ← 我的 shell 有这个例外，所以我连 localhost 没事

$ nc -z localhost 15432
✓ port reachable

$ unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
$ uv run python -c "import psycopg; c=psycopg.connect('postgresql://miroflow:miroflow@localhost:15432/miroflow_real'); print('ok')"
ok                                  ← unset proxy 后秒连

$ uv run python scripts/run_homepage_paper_ingest.py --dry-run --limit 2
INFO httpx: HTTP Request: GET https://api.openalex.org/works ...
INFO httpx: HTTP Request: GET https://export.arxiv.org/api/query ...
（在跑、在调外网 API、在做 title 解析）
```

## 根因（用户提示直接命中）

用户在 Codex stop #2 的同一时间窗里告知：「claude code 与 codex 在当前环节中都需要走代理，但是代码验证的环境可以不走代理」。

机制：
1. 工作环境设了 `ALL_PROXY=socks5://...`
2. SOCKS5 与 HTTP_PROXY 不同，**会拦截所有 TCP 连接**包括 loopback
3. 我的交互 shell 同时设了 `NO_PROXY=localhost,127.0.0.1,::1` 让 loopback 例外
4. Codex 子代理的子 shell **不必然继承 `NO_PROXY`**，所以它握手 `localhost:15432` 时被 SOCKS5 劫持
5. psycopg 的 OperationalError "connection is bad: no error details available" 就是这种握手期失败的特征

CLAUDE.md §6 没记录这个 invariant——属于真正的项目隐式知识。已存到 project memory（`env_proxy_bypass.md`）。

## 决定：revise-and-resume

1. 修 spec §5.1 / §9 + handoff §3 / §8：所有 verification 命令前缀 `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy &&`
2. spec §13 加假设 A6（proxy 已 unset）
3. handoff §6 / §11 增加新 stop condition：「unset proxy 后 Postgres 仍连不上」
4. 派下一轮 Codex 时**在 prompt 里直接强调** proxy 例外
5. 项目记忆已落（`env_proxy_bypass.md`），未来所有 Codex 派发会自动带这个上下文

## 也发现的细节（不影响 Stage B）

- 实际 Postgres 表名：`professor / paper / company / patent` 系列，而不是 canonical schema 里的 `_profile` 后缀（我自己 dashboard 验证查询时一度用错）
- 这与本任务无关（Stage B 改 parser 不碰 SQL），但记一笔以防 Codex 在 §5.2 调研时被表名误导

## Spec/handoff 文档质量复盘

两轮 stop 共暴露 spec §13 假设的两处不完整：
- A2 「Postgres 起着」→ 应细化为「Postgres 起着 + DSN 是 libpq 形式（非 SQLAlchemy）+ proxy 已 unset」
- 这两次 stop 都暴露了**项目环境隐式 invariant**——属于应进 CLAUDE.md 或 docs/solutions/ 的知识。本 slice 不做这件事，记入 follow-up

## Follow-up（不做，仅记录）

- F4: CLAUDE.md §6 应补充 proxy 绕开 invariant（与 stop1 的 F1 一并）
- F5: docs/solutions/ 下应建一个「local verification env preflight」检查清单
- F6: 是否给 ingest 脚本加 `--no-proxy` 自动 unset 兜底（设计 question）

## Files touched (this round)

- `.agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop2.md`（新增）
- handoff（即将编辑）
- spec（即将编辑）
- project memory `env_proxy_bypass.md`（新增）

无产品代码变更。Codex 未 commit。
