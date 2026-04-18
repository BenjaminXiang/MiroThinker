---
title: 教授 URL.md 收口必须逐 URL 验证 `ready` + 论文数据
date: 2026-04-08
category: docs/solutions/workflow-issues
module: apps/miroflow-agent professor pipeline v3
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - 收口 `docs/教授 URL.md` 的教授站点接入工作
  - 修改教授 roster 发现、姓名清洗或 synthetic profile 逻辑
  - 用抽样 E2E 判断教授域是否真的达到可发布状态
tags: [professor-pipeline, url-md, e2e, ready-gate, paper-backed, roster-discovery, synthetic-profile]
---

# 教授 URL.md 收口必须逐 URL 验证 `ready` + 论文数据

## Context

2026-04-07 的教授域修复已经解决了两类上游问题：一类是“无论文也能 `ready`”的质量语义错误，另一类是若干学校会被质量门误拦截。但在真正对 [`docs/教授 URL.md`](../../教授%20URL.md) 做全量收口时，仍然暴露出最后一层真实问题：聚合统计看起来接近通过，单个 URL 却依然可能产出“假教授”或“假完成”。

这轮全量验证里，典型失败样例包括：

- PKUSZ 根页把 `学术交流` 这类栏目名当成老师，导致 `released=1` 但 `ready=0`
- 部分 SYSU 页面把院校名或导航项当成老师名，例如 `中山大学`
- SZTU 多个学院页面没有详情页链接，只能从 heading 文本里识别老师
- synthetic `#prof-...` 锚点页在 enrichment 阶段又被页面标题覆盖成 `教研团队`

结论是：教授 URL 收口不能只看“有没有 release”，也不能只看“有没有 paper_count”。必须同时验证“老师实体是否正确”。

## Guidance

把教授 URL 收口标准固定成逐 URL 的三段式门槛：

1. `released > 0`：这个 URL 至少真的放出了教授对象。
2. `ready > 0`：至少有一个对象通过当前质量门，不是纯占位或待复核。
3. `paper_count > 0`：至少有一个 `ready` 教授带论文相关数据，证明教授-论文链路真的接通。

只要其中任一条件不满足，就不要把该 URL 视为完成。聚合通过率不能替代逐 URL 验收。

为满足这个门槛，本轮修复采用了四个关键决策：

- **发现逻辑先识别学校模板，再走通用递归。** 对高方差学校页面，站点特化分支必须优先于 generic extractor。此次补充了 CUHK `teacher-search` 分页发现、SYSU `sa.sysu.edu.cn -> ab.sysu.edu.cn` fallback，以及 ISE `/teachers` hub 页特殊处理。
- **对无详情链接的 faculty 页面，允许 heading 直接生成 synthetic profile。** 在 [`apps/miroflow-agent/src/data_agents/professor/roster.py`](../../../apps/miroflow-agent/src/data_agents/professor/roster.py) 中，heading-based extraction 现在会优先于导航链接抽取，并为 `杜鹤民`、`Franz Raps` 这类页面生成 `#prof-<name>` 锚点资料页。
- **synthetic profile 的姓名以 roster 为准。** [`apps/miroflow-agent/src/data_agents/professor/enrichment.py`](../../../apps/miroflow-agent/src/data_agents/professor/enrichment.py) 发现 `#prof-...` 片段时，不再让页面标题覆盖名单页老师名，避免 `杜鹤民 -> 教研团队` 这类回退。
- **把“名字安全”当成一等规则。** [`apps/miroflow-agent/src/data_agents/professor/roster.py`](../../../apps/miroflow-agent/src/data_agents/professor/roster.py) 和 [`apps/miroflow-agent/src/data_agents/professor/name_selection.py`](../../../apps/miroflow-agent/src/data_agents/professor/name_selection.py) 扩充了非人名关键词、路径黑名单、机构/角色后缀过滤和中文职称后缀裁剪，专门拦 `学术交流`、`教研团队`、`中山大学`、`荣誉教授` 这类污染源。

执行上不要全量重跑到最后再看结果。正确做法是：

- 先跑基础批次，定位失败索引
- 对失败 URL 做定点 rerun，保留独立 summary 产物
- 最后把基础批次和定点修复批次合并成最终覆盖报告

这样既能维持大批量 E2E 的吞吐，也能保留每个问题 URL 的可追溯证据。

环境侧也有三条必须记录的规则：

- **不要手抄或二次转述 E2E 所需密钥。** 这轮定点重跑里，最初的 `401` 不是业务逻辑回退，而是 shell 里使用了错误的 API key 值。对教授 E2E，这类值应以仓库脚本为准，例如 [`apps/miroflow-agent/scripts/run_full_e2e_parallel.sh`](../../../apps/miroflow-agent/scripts/run_full_e2e_parallel.sh)。
- **在 `zsh` 里导出包含 `!` 的密钥前先关闭 history expansion。** 否则 shell 会在命令执行前改写字符串，导致看起来“已经 export”，实际发出的值是错的。安全做法是先执行 `set +H`，再用单引号导出环境变量。
- **定点 URL 修复验证要尽量裁掉非核心依赖。** 这轮最终收口只关注“是否能放出带论文数据的教授对象”，因此 rerun 时使用了 `--skip-web-search --skip-vectorize`，避免把搜索增强和向量化侧噪声混进教授 URL 验收。

## Why This Matters

教授域最容易出现一种“看起来全都通了”的假象：release 有了，paper 也有了，但老师其实是栏目名、院校名或者页面标题。这样的对象一旦进入共享库，会把搜索、推荐和后续 paper 反哺全部污染掉。

逐 URL 验证 `released + ready + paper-backed` 的组合门槛，实际是在同时检查三件事：

- crawler 真的找到了人
- quality gate 认可这条人是可用的
- professor-to-paper 关联不是空链路

这比“总共放出了多少对象”更接近最终用户真正依赖的数据质量。

## When to Apply

- 新接入一个学校或学院站点时
- roster 页面以标题块、卡片块、JS 内联数据或 hub 页跳转为主时
- 页面存在 synthetic profile、锚点页或无详情页老师列表时
- 教授域 E2E 已经接近通过，但仍有少量 URL 卡在 `ready=0` 或名字污染时

## Examples

本轮最典型的两个 before/after：

- PKUSZ 基础批次里，`003` 一开始产出的是 `学术交流`，表现为 `released=1`、`ready=0`。补上根页跳过噪声入口与递归后，最终修正为 `陈少川`，并达到 `ready=1`、`paper_count=1`。
- SZTU 创意设计学院和城市交通与物流学院页面没有老师详情链接。加入 heading-based extraction 和 synthetic-name 保真后，页面能够稳定产出 `杜鹤民`、`李立全`、`Franz Raps`，不再被 `机构设置`、`本科生`、`教研团队` 覆盖。

本轮收口时实际保留的验证命令和结果：

```bash
set +H
cd apps/miroflow-agent
.venv/bin/python -m pytest -o addopts='' \
  tests/data_agents/professor/test_profile_record_merge.py \
  tests/data_agents/professor/test_roster_validation.py -q
```

结果为 `75 passed in 1.95s`。

定点 E2E 重跑时，环境准备也应固定成“先 shell，再密钥，再最小化开关”的顺序：

```bash
set +H
cd apps/miroflow-agent
export API_KEY='...'
export DASHSCOPE_API_KEY='...'
export SERPER_API_KEY='...'
.venv/bin/python scripts/run_professor_url_md_e2e.py \
  --seed-doc ../../docs/教授\ URL.md \
  --start-index <idx> \
  --end-index <idx> \
  --limit-per-url 3 \
  --skip-web-search \
  --skip-vectorize
```

这里的关键不是具体密钥内容，而是：

- 密钥来源要以仓库脚本为准，不要依赖历史终端回显
- `set +H` 要先于密钥导出
- professor URL 收口时，先验证 release/ready/paper 主链路，再决定是否回开 web search 和向量化

最终合并基础批次与定点修复批次后，[`logs/data_agents/professor_url_md_final_verification_2026-04-07.md`](../../../logs/data_agents/professor_url_md_final_verification_2026-04-07.md) 记录的收口结果是：

- `41/41` URL 有 released professor
- `41/41` URL 至少有一个 `ready` professor
- `41/41` URL 至少有一个带论文数据的教授
- `0` 个执行错误

残余现实也要保留：在当前 `limit_per_url=3` 抽样下，仍有部分 URL 出现 `ready < released`。这代表“每个 URL 已有至少一个可交付样本”，不代表“每个采样到的教授都已完全达标”。

## Related

- [教授论文缺口审查与修复计划](../data-quality/professor-paper-gap-root-cause-and-remediation-plan-2026-04-07.md) — 定义了为什么 `ready` 必须和论文数据绑定
- [Professor Pipeline V3: Quality Gate False Blocks](../logic-errors/professor-pipeline-v3-quality-gate-false-blocks-2026-04-07.md) — 记录了质量门从“错误拦截”到 L1/L2 分层的修复
- [CUHK SSL crawler markdown fallback](../integration-issues/cuhk-ssl-crawler-markdown-fallback-2026-04-07.md) — 记录了 CUHK `teacher-search` 的上一层接入问题
- [数据代理 E2E 门控](./data-agent-real-e2e-gates-2026-04-02.md) — 更早的通用 real-source E2E 原则；教授域的验收标准现在应以“逐 URL `ready` + 论文数据”作为更严格补充
- [Professor URL.md Final Verification](../../../logs/data_agents/professor_url_md_final_verification_2026-04-07.md) — 本轮最终验证报告
