---
title: 教授数据采集当前发现与操作经验汇总
date: 2026-04-16
category: docs/solutions/workflow-issues
module: apps/miroflow-agent professor pipeline
problem_type: workflow_issue
component: professor_pipeline_operating_guidance
severity: high
applies_when:
  - 需要快速判断教授数据采集主线当前是否收口
  - 需要决定下一步优先修哪里，而不是继续盲目调 heuristics
  - 需要区分验收型 E2E、serving 刷新、workbook 覆盖验证三种不同运行目的
tags: [professor-pipeline, e2e, serving-store, workbook, adapter, official-chain]
---

# 教授数据采集当前发现与操作经验汇总

## 最新状态更新（2026-04-16 end-of-day）

- workbook 真实共享库审计已收口为 `16 pass + 1 out_of_scope`
- 最新报告：`logs/data_agents/workbook_coverage_final_post_review_20260416/workbook_coverage_report.json`
- 当前 shared store 规模：`company=1037 / paper=17707 / patent=1931 / professor=3274`
- 这轮 closing 通过的关键路径包括：`q1 professor-company backfill`、`q2/q5/q7 company supplement backfill`、`q11-q16 company knowledge fields`
- Wave 4 discovery hardening 已在最新真实 targeted E2E 上收口：`SUSTech root + SZU hub + CUHK teacher-search = 3/3 gate_passed`
- 代表性单 seed 真实验证也已通过：`seed036 (released=29, ready=23)`、`seed013 (released=3, ready=3)`
- direct-profile `姓名 + URL` seed institution 继承已收口：`李立浧 main.htm = 1/1 gate_passed`
- `SYSU materials faculty/staff` 误判 direct-profile 已收口：`陈文多 = 1/1 gate_passed`
- 更宽 host family 扩样里，`清华 / 南科大 / 北大深研院 / 深大 / 深理工 / 哈工深 = 6/6 gate_passed`
- Wave 5 第一阶段 adapter 目标批次也已 fresh 收口：`CUHK / SYSU / SZTU = 6/6 gate_passed`
- `school_adapters.py` 的最小 registry + roster dispatch 已落地：`CUHK teacher-search + SYSU faculty/staff` 已进入 first-match-wins phase 1
- 更宽的 `SYSU faculty family` round2 也已 fresh 通过：`saa / sa = 2/2 gate_passed`
- 本轮更宽 professor 回归最新是 `141 passed`


## 结论

到 2026-04-16 UTC，教授数据采集这条线已经形成了比较稳定的操作结论：

1. **真实数据 E2E 是唯一可信方向盘**
   - 采样 smoke test、单脚本单点通过、历史 debug artifact，都不能替代真实 `docs/教授 URL.md` E2E。
2. **seed URL 只是 discovery 入口，不是最终画像页**
   - 高校官网教师列表页的职责是发现老师；真正决定质量的是后续沿官方链递归到详情页、个人主页、课题组页、CV、ORCID、Scholar、publication 页面。
3. **验收型 E2E 和 serving 刷新必须拆开**
   - 抽样或 `limit-per-url` 受限的 E2E 产物，不能直接拿去刷新共享 professor serving store。
4. **当前主问题已经从“完全抓不到”转成“分阶段结构优化与跨域覆盖增强”**
   - direct-profile 身份误判、Gemma4 鉴权链这类主线 blocker 已经收住；
   - workbook 对象级覆盖也已经在真实 shared-store audit 上收口；
   - 剩余重点转到 Wave 5 school-adapter 扩样收尾，以及更深的教授与论文/企业/专利关联质量。

## 当前已确认的发现

### 1. direct-profile 主线已经收住

补充说明：到这一步，Wave 4 里与 discovery/fetch 直接相关的残余项也已经用真实 E2E 收口，而不再只是代码层自证。最新证据见 [wave4 targeted round3](../../../logs/data_agents/professor_url_md_e2e_wave4_discoveryfix_targeted_round3_20260416/url_e2e_summary.json)：`南方科技大学`、`深圳大学`、`香港中文大学（深圳）理工学院` 三条真实 URL 全部 `gate_passed=true`。


以下问题已经被真实 E2E 证明修掉：

- `gemma4` 的 `http -> https` 与 stale `API_KEY` 覆盖问题
- `工作履历 / Teaching / Presentation / 专任教师` 被当成教授姓名的问题
- L1 失败对象仍落成 `ready` 的质量门漏洞
- official publication fallback 吃 footer/copyright 噪声的问题

主证据：

- [教授 Pipeline 当前已收住与剩余旁路问题清单](./professor-pipeline-current-closed-vs-open-issues-2026-04-16.md)
- [direct-profile round4](../../../logs/data_agents/professor_url_md_e2e_direct_identityfix_round4_20260416/url_e2e_summary.json)
- [URL.md sample 20-22 round2](../../../logs/data_agents/professor_url_md_e2e_urlmd_sample20_22_round2_20260416/url_e2e_summary.json)

### 2. seed URL 不是终点，官方链递归才是主链

这轮排查确认了一个必须固定下来的原则：

- `docs/教授 URL.md` 里的 URL 主要用于发现学校/院系有哪些老师
- 采集不能停在 seed 页或教师列表页
- 必须沿官方教师详情页继续递归到：
  - 官方个人主页
  - 官方课题组主页
  - 官方挂出的 `CV / ORCID / Scholar / publication` 页面

原因很直接：

- 老师自己维护的主页或课题组页，通常有更完整的个人介绍
- 最新论文列表、代表作、CV 往往不在学校列表页，而在个人页或组页
- 外部第二证据源只有在“官方链挂出”时，才足够安全进入主链

相关文档：

- [教授数据采集在深圳有限 seed 场景下优先采用学校级 Adapter](../best-practices/professor-school-adapter-architecture-for-limited-shenzhen-seeds-2026-04-16.md)

### 3. serving 刷新不能直接吃 sample-limited E2E 产物

这是这轮新增的关键流程结论。

之前 workbook 反查发现：

- 历史 artifact 里存在的教授
- 当前共享 `released_objects.db` 里却不存在

进一步核对后确认，至少有一部分缺口并不是“发布逻辑把人丢了”，而是：

- 当前 serving refresh 输入本身来自受 `limit-per-url` 约束的 clean E2E 产物
- 老师在进入 publish 之前就已经被截断

这条结论已经单独沉淀：

- [教授 Serving 刷新不能直接使用 sample-limited E2E 产物](./professor-serving-refresh-must-use-full-harvest-not-sampled-e2e-2026-04-16.md)

配套脚本层改动也已经落地：

- [run_professor_url_md_e2e.py](../../../apps/miroflow-agent/scripts/run_professor_url_md_e2e.py) 支持 `--limit-per-url 0`
- E2E 默认写隔离 store，不再默认污染共享 `released_objects.db`

### 4. workbook 现在是 closure regression gate，不再是“当前缺口列表”

这轮已经把 workbook 检查从手工核查变成了可复跑基线：

- [实现测试集答案 Workbook 覆盖度验证](./testset-answer-workbook-coverage-validation-2026-04-16.md)
- [Workbook Coverage Gap Remediation Plan](../../plans/2026-04-16-005-workbook-coverage-gap-remediation-plan.md)
- [Professor Workbook Closure Sequencing Plan](../../plans/2026-04-16-006-professor-workbook-closure-sequencing-plan.md)

需要明确区分两层语义：

- `testset-answer-workbook-coverage-validation-2026-04-16.md` 记录的是 **修复前 baseline 缺口**
- 当前真实 shared-store audit 的 closure 结果已经收口为 **`16 pass + 1 out_of_scope`**

这意味着 workbook 现在的用途已经从“告诉我们缺什么”转成“回归验证是否又把这些能力弄丢了”。

### 5. 当前速度已经可用，但不该以牺牲正确性换吞吐

最近一次真实 `URL.md` 扩样批次显示：

- `12` 个真实 URL
- `11` 个 gate 通过
- `elapsed_seconds = 1041.6`
- 约 `86.8 秒 / URL`
- 约 `32.6 秒 / 老师`

这说明当前系统已经不是“完全跑不动”，但长尾 host 仍会明显拉长耗时。  
更重要的是，这个批次也证明了：**真实 E2E 不只给性能结论，还会直接暴露 correctness 问题**。因此速度优化不能脱离真实 E2E 做。

## 当前最重要的操作经验

### 1. 先用真实 E2E 定位问题，再改代码

正确顺序是：

1. 跑真实 `docs/教授 URL.md` E2E
2. 看失败 URL 与失败原因
3. 只对真实暴露的问题动刀
4. 修完后再回到真实 E2E 复验

不要反过来先堆 heuristics，再找样本证明自己是对的。

### 2. 验收型 E2E 与 serving 型 full harvest 必须分流

- **验收型 E2E**
  - 允许抽样
  - 允许 `limit-per-url`
  - 目标是判断主链是否收口
- **serving 型 full harvest**
  - 不能裁掉单 URL 内的教授
  - 目标是尽可能完整地产出可发布对象

两者可以共用同一条主 pipeline，但不能复用同一份受采样限制的产物。

### 3. 结构上应从“通用 heuristics”过渡到“统一主链 + 学校级 Adapter”

当前深圳高校 seed 集合有限且稳定，继续在通用 `discovery / roster / profile` 里堆 host-specific if/else 的收益已经在下降。

更合适的结构是：

- 通用主链负责 orchestration、fallback、quality gate
- 学校级 adapter 负责：
  - roster 发现
  - detail page 识别
  - 官方主页 / publication 提取

这比“每个院系一个脚本”更稳，也比继续堆散落 heuristics 更可维护。

### 4. 第二证据源必须走官方链，不接受裸搜索反客为主

ORCID / CV / Scholar / DBLP 这类页面只有在以下条件下才应进入教授主链：

- 从官方教师页
- 或官方个人主页 / 官方课题组页
- 沿页面链接直接递归发现

外部搜索直接找到的同类页面，可以当辅助线索，但不应覆盖官方身份锚点。

## 当前仍在推进但尚未完全写成 closing 的事项

当前已经切到 `Wave 5 / Professor School Adapter Phase 1`，而且不再只是计划状态：

- pre-wave snapshot 已生成：`logs/data_agents/wave_snapshots/wave4_20260416/`
- `school_adapters.py` registry、旁路开关和 `roster.py` 顶层 dispatch 已落地
- direct-profile guardrail 仍保持通过：`logs/data_agents/professor_url_md_e2e_wave4_guardrail_round3_20260416/url_e2e_summary.json`
- 第一阶段真实 E2E 已 fresh 收口：`wave5 matrix B round2 = 6/6 gate_passed`
- 当前这一阶段已经做完的是：更宽 SYSU faculty family（`saa / sa`）也已补进 phase 1 的真实验证集，并 fresh 通过
- 当前真正剩下的，是决定 `SZTU / SUAT-SZ` 是否单独开 phase 2，或者把优先级切回更深的论文/企业/专利关联增强

也就是说，这份文档当前的作用是提供已经被真实 E2E 证明的稳定操作结论，并说明 Wave 5 phase 1 现在已经完成，不需要再把 `sa/saa` 当成未验证缺口。

## 推荐阅读顺序

如果要接手这条线，推荐按这个顺序读：

1. [教授 Pipeline 当前已收住与剩余旁路问题清单](./professor-pipeline-current-closed-vs-open-issues-2026-04-16.md)
2. [教授 Serving 刷新不能直接使用 sample-limited E2E 产物](./professor-serving-refresh-must-use-full-harvest-not-sampled-e2e-2026-04-16.md)
3. [实现测试集答案 Workbook 覆盖度验证](./testset-answer-workbook-coverage-validation-2026-04-16.md)
4. [教授数据采集在深圳有限 seed 场景下优先采用学校级 Adapter](../best-practices/professor-school-adapter-architecture-for-limited-shenzhen-seeds-2026-04-16.md)
5. [Workbook Coverage Gap Remediation Plan](../../plans/2026-04-16-005-workbook-coverage-gap-remediation-plan.md)

## One-Line Rule

**教授域当前最重要的经验不是“某个 heuristics 怎么调”，而是：只用真实 E2E 定方向，把 seed 当 discovery 入口，把官方链递归当主链，把 full harvest 和 sample-limited 验收彻底分开。**
