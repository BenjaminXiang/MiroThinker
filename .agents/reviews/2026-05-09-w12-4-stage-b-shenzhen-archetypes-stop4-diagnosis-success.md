---
title: "Review — W12-4 Stage B Round 4 (Codex diagnostic stop, ACCEPTED)"
date: 2026-05-09
spec: .agents/specs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md
handoff: .agents/handoffs/2026-05-09-w12-4-stage-b-shenzhen-archetypes-path-a.md
codex_agent_id: a57a9ed0de80e9718
codex_job_id: latestFinished from codex-companion
prior_reviews:
  - .agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop1.md  # DSN
  - .agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop2.md  # proxy in subagent shell
  - .agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop3.md  # codex sandbox network
decision: accept-diagnosis-and-widen-spec-for-round-5
quality: high
---

# Review — W12-4 Stage B Round 4 (high-quality diagnostic stop, ACCEPTED)

## Outcome

**This is the first round Codex actually got to do real work**, and it produced an excellent diagnosis report (`logs/.../diagnosis.md`). The stop is **expected and well-handled** — Codex correctly identified that the spec §0 core assumption is wrong and stopped per spec §11 condition: "root cause is in `_find_publications_sections` or heading vocabulary".

This is the **best kind of stop** — it gathered ground truth and surfaced an architectural decision Claude must own.

## Codex's diagnostic quality (excellent)

- Probed all 10 FIX TARGET samples with rigor (sections + 5 strategies + manual DOM inspection)
- Found 9/10 fail at section detection, not content extraction
- Distinguished 3 distinct failure sub-modes:
  1. h3/h2 with non-vocab text (`学术成果`)
  2. `<p><strong>vocab-text</strong></p>` patterns (vocab match, non-h structure)
  3. `<div class="tit">vocab-text</div>` CMS templates
- Identified 2 samples (`PROF-0AD6B7854B29`, `PROF-056CEBB2980A`) as **genuinely unsalvageable** — saved HTML lacks publication data entirely
- Identified 1 sample (`PROF-0352087FC634`) as having only 4 papers in HTML
- Wrote per-sample table with exact DOM evidence

Discipline check ✅✅✅✅: didn't fabricate fixtures, didn't modify forbidden files, didn't re-run dry-run despite curiosity, didn't write code into a stop-condition area.

## Claude's verification

Spot-checked 2 samples myself:

```
PROF-02D420B17263 (SZTU sgim):
  text='代表性论文'
  parent: <span style='...font-family:宋体...'>
  grandparent: <strong>
  → confirmed: vocab match in <p><strong><span>, no h* tag

PROF-019A6958E272 (SIT csce):
  <h3 class="tit">学术成果</h3>      ← h3 but text not in vocab
  <p>近年发表的主要学术论文 (Selected Journal Papers)：</p>  ← list label below
  → confirmed: nested vocabulary mismatch
```

Codex's reading is accurate.

## Spec §0 / §1 假设破坏（重要）

原 spec §0：
> W9-5 dogfood 实测：M2.1 `homepage_publications` selector 在 10 教授真实主页中**全部**检测到 publications 区段但**0 篇**论文被提取。

**实测推翻**：

| Spec 假设 | 实测 |
|---|---|
| section detection ✓ across all 10 | section detection ✗ in 9/10 SIT/SZTU samples |
| extraction ✗ across all 10 | extraction never reached because sections=0 |
| Tsinghua SIGS broken | Tsinghua SIGS works (55, 6 papers extracted) |
| 4 archetype 全部需修 | 2 archetype（SIT、SZTU）需修；SYSU 大部分 OK；Tsinghua 已 OK |

W9-5 dogfood 数据可能是更早一代的 selector 状态；中间几次 commit (`d3708ba` M2.1 pure HTML→list extractor、`5519354` venue/author parser robustness) 已经修了不少。

## 真正的失败模式分类

| 类型 | 触发条件 | 修复路径 | 样本数 |
|---|---|---|---|
| **V1 vocab gap** | h*tag with text not in `_PUBLICATIONS_HEADING_KEYWORDS` | 加 vocab：`学术成果`、`代表性文章`、`代表文章` | 1 (csce 019A) |
| **V2 non-h heading via `<p><strong>vocab</strong>`** | vocab 命中但容器是 p/strong/span 而非 h* | 扩展 `_find_publications_sections` 识别 styled paragraph headings | 4 (csce 0210, sgim 02D4, cep 02DD, sgim 0AD6 partial) |
| **V3 non-h heading via `<div class="tit">vocab`** | 来自 CMS 模板的 div title block | 扩展 `_find_publications_sections` 识别 CMS title divs | 3 (lhs 00FD, synbio 162E, hsee 0352 partial) |
| **V4 trailing punctuation** | `代表性论文：` 末尾全角冒号 | 容忍末尾标点 | 多个 |
| **V5 unsalvageable** | HTML 中根本没列出版物 | 排除 | 2 (sgim 0AD6 only prose, bs 056C only profile) |
| **V6 only 4 papers** | HTML 列了 4 篇但 < 5 阈值 | 接受 ≥4，或排除 | 1 (hsee 0352) |

## 决定：authorize 上游 fix，widen spec for Round 5

### 1. 修订 spec §0 / §1 / §2 / §11 / §13

**新允许**：
- ✅ 修改 `_find_publications_sections` 识别非 h* 容器（仅在容器内文本命中 vocab 且容器具有 styled paragraph / CMS title block 特征时）
- ✅ 扩展 `_PUBLICATIONS_HEADING_KEYWORDS`：`学术成果`、`代表性文章`、`代表文章`
- ✅ 容忍 vocab 末尾全角冒号 `：` / 半角 `:`

**仍禁止**：
- ❌ 重写 `extract_publications_from_html` 入口
- ❌ 重命名/删除现有 5 策略
- ❌ 改 `HomepagePublication` dataclass

### 2. 修订 acceptance threshold

```
原 baseline.md: ≥4/5 SIT、≥4/5 SZTU、5/5 regression-guard

修订后（去掉真无 publication 数据的 2 个 + 接受 1 个 ≥4）:
- 2 个 SIT csce 样本：≥5 papers
- 1 个 SIT lhs 样本（00FD）：≥5 papers
- 1 个 SIT synbio 样本（162E）：≥5 papers
- 1 个 SIT swyxgcxy 样本（2E2F）：保持 5 papers（regression-guard，已 working）
- 1 个 SZTU sgim 样本（02D4）：≥5 papers
- 1 个 SZTU cep 样本（02DD）：≥5 papers
- 1 个 SZTU hsee 样本（0352）：≥4 papers（HTML 只有 4 篇）
- 排除 2 个 unsalvageable：PROF-0AD6B7854B29 (sgim 仅 prose), PROF-056CEBB2980A (bs 仅 profile)
- 5 个 regression-guard 不退化（Tsinghua × 2、SYSU bme × 1、SYSU ise × 1、SYSU eco-working × 1）

总 ≥ 12/15 真实可修样本（17 - 2 unsalvageable）有 papers > 0
其中 ≥ 7 个达到 ≥ 5 papers
```

### 3. Round 5 handoff（即将写）

新 handoff: `2026-05-09-w12-4-stage-b-shenzhen-archetypes-round-5.md`

要点：
- 明确授权扩展 `_find_publications_sections` + 加 vocab 词
- 给 Codex 具体的 V1/V2/V3/V4 修复路径
- 明确 unsalvageable 2 个样本不在 acceptance 内
- 保持 sandbox-friendly（path A 模式：纯文件 IO + pytest）
- 给出 regression-guard 测试要求

## Files touched (this round)

- `.agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop4-diagnosis-success.md`（this）
- 即将：spec §0 / §1 / §2 / §11 / §13 修订
- 即将：handoff round-5 编写
- `logs/data_agents/paper/homepage_ingest_runs/2026-05-09/diagnosis.md`（Codex 写的，保留）

无产品代码变更。

## Spec/handoff/memory 工程价值（迄今）

四轮 stop 把项目里的隐式 invariant 全显式化了：

| Round | Stop 类型 | 学到的项目知识 |
|---|---|---|
| 1 | DSN format | CLAUDE.md §6 是 admin-console 形式；ingest 脚本要 libpq |
| 2 | Subagent shell missing NO_PROXY | proxy unset 模板 → memory `env_proxy_bypass.md` |
| 3 | Codex CLI sandbox blocks loopback | sandbox 边界 → memory `codex_sandbox_constraints.md` |
| 4 | Spec §0 假设错（diagnostic） | 真实失败模式 V1–V6（本 review） → 改 spec |

每一轮的产出都让下一次（或下一个不同任务）的派发**永久避开**这一类问题。这就是 spec/review/memory 这套 artifact 的工程复利。
