---
title: "Codex handoff (Path A) — W12-4 Stage B: 主页论文 SIT/SZTU CMS 覆盖"
date: 2026-05-09
spec: .agents/specs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md
prior_handoff: .agents/handoffs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md
prior_reviews:
  - .agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop1.md  # DSN
  - .agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop2.md  # proxy in subagent shell
  - .agents/reviews/2026-05-09-w12-4-stage-b-shenzhen-archetypes-stop3.md  # codex sandbox network
mode: claude-prepares-data → codex-implements-parser → claude-validates
estimated_effort: 0.3–0.5 day (codex side)
---

# Codex handoff v2 (Path A) — W12-4 Stage B

> **Why this handoff exists**: previous 3 attempts hit env constraints (Codex CLI sandbox blocks localhost network, even after proxy unset). Path A splits work by sandbox capability:
> - **Claude (no sandbox)** has done all network/DB work: queried DB, fetched 17 Shenzhen prof homepage HTMLs, ran current parser baseline. All artifacts in `logs/data_agents/paper/homepage_ingest_runs/2026-05-09/`.
> - **You (Codex, sandbox-friendly)** only need to: read those HTMLs, modify parser, write pytest, commit.
> - **Claude** will run end-to-end dry-run after-state to validate.

## 1. 任务简述（修订自 baseline 实测）

让 `extract_publications_from_html` 处理 SIT (suat-sz.edu.cn) + SZTU (sztu.edu.cn) 这两个 CMS 模板，把它们从 0 papers/prof 拉到 ≥ 5 papers/prof。**Tsinghua SIGS 已经能跑（55/6 papers），不用动。** SYSU 大部分子域也能跑，eco 的一个 prof 是边缘 case，nice-to-have。

baseline 实测细节看 `logs/data_agents/paper/homepage_ingest_runs/2026-05-09/baseline.md`。

## 2. 必读源文档（按顺序）

1. `logs/data_agents/paper/homepage_ingest_runs/2026-05-09/baseline.md` — 17 个真实样本 + 当前 parser 表现 + 修订过的 acceptance 阈值（**这是权威 goal**）
2. `.agents/specs/2026-05-09-w12-4-stage-b-shenzhen-archetypes.md` — 设计契约（§4 affected paths、§6 interface contracts、§7 invariants 仍有效；§1 目标表已被 baseline.md 替换）
3. `apps/miroflow-agent/src/data_agents/professor/homepage_publications.py` — 当前 983-line parser（5 个策略 dispatcher）
4. `apps/miroflow-agent/src/data_agents/professor/homepage_publication_headings.py` — heading vocab（不要动除非确认缺词）
5. `apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications.py` — **不要动**（277 行别人的 drift）

## 3. 实施流程（强制顺序）

```
Step 1  调研（读 HTML 文件，纯 file IO，sandbox 友好）
        └─ 1a) cd /home/longxiang/MiroThinker（base 路径）
        └─ 1b) 读 logs/.../baseline.md 看 acceptance 阈值
        └─ 1c) 对每个 FIX TARGET 样本（SIT × 5 + SZTU × 5 = 10 个），运行下列 probe：

           import bs4
           from src.data_agents.professor.homepage_publications import (
               extract_publications_from_html,
               _find_publications_sections,
               _extract_from_list, _extract_from_paragraphs, _extract_from_table,
               _extract_from_year_groups, _extract_from_definition_list,
               _extract_section_publications,
           )
           html = open("logs/.../<prof_id>.html").read()
           soup = bs4.BeautifulSoup(html, "lxml")
           # strip landmarks if needed (per parser convention)
           sections = _find_publications_sections(soup)
           print(f"sections found: {len(sections)}")
           for sec in sections:
               for strategy in [_extract_from_list, _extract_from_paragraphs,
                                _extract_from_table, _extract_from_year_groups,
                                _extract_from_definition_list]:
                   # invoke each independently; signature compatibility per existing helpers
                   ...

        └─ 1d) 写 logs/data_agents/paper/homepage_ingest_runs/2026-05-09/diagnosis.md：
              - 每个 FIX TARGET 样本：sections 数、5 策略各自命中数、DOM 结构片段（找出公共 pattern）
              - SIT 与 SZTU 的 DOM pattern 是否相同？
              - 与 Tsinghua SIGS / SYSU bme 等 working 样本的差异在哪？
              - 提出 fix proposal（A 还是 B，理由）

Step 2  实现（src/data_agents/professor/homepage_publications.py）
        └─ 选项 A：新增第 6 个内容策略（_extract_from_<name>），加在现有 5 策略 fallback 链之后
        └─ 选项 B：patch 现有策略（最小改动，常见情况是放宽某 selector 的 tag 集）
        └─ 不要重命名/删除现有 5 策略；不要改 extract_publications_from_html 入口

Step 3  测试
        └─ 新建 tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py
        └─ 每个 FIX TARGET archetype 至少 1 fixture（minimal HTML 切片，~50–200 行）+ ≥ 5 papers assertion
        └─ 加 regression-guard 测试：3 个 working sample（Tsinghua SIGS × 1, SYSU bme × 1, SYSU eco-working × 1）必须 papers > 0
        └─ Fixture 可以从 logs/.../<prof_id>.html 直接 inline，或用 pathlib 读

Step 4  Sandbox-friendly 验证（codex 自跑）
        └─ unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy（习惯性 unset，pytest 不用网但保险）
        └─ uv run pytest tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py -n0 --no-cov -v
        └─ uv run pytest tests/data_agents/professor/ -k "publication" -n0 --no-cov（既有不退化）
        └─ 跑 17 个真实样本（用 baseline.md 里的 prof_id 列表），打印 before/after 对比
              注：此步是 file IO + 解析，不需要网络

Step 5  Commit (NO push)
        └─ git add 仅 §4 列出的文件
        └─ commit message 模板：
            feat(homepage_publications): SIT/SZTU CMS archetype coverage (W12-4 Stage B)

            - 17 real Shenzhen samples (claude-prefetched in logs/.../2026-05-09/)
            - SIT (suat-sz.edu.cn) + SZTU (sztu.edu.cn) brought from 0 → ≥5 papers/prof
            - Tsinghua SIGS / SYSU regression-guarded
            - Decision: A or B (write reason in commit body)
            - PRD §M2.1 R3 progress: x/17 samples ≥1 paper

Step 6  回报（按本 handoff §6 结构）
```

## 4. 修改文件清单

```
修改:
  apps/miroflow-agent/src/data_agents/professor/homepage_publications.py

新增:
  apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py
  logs/data_agents/paper/homepage_ingest_runs/2026-05-09/diagnosis.md  # 你写

按需（仅当 §1c probe 明确发现缺词，并且 claude 同意）:
  apps/miroflow-agent/src/data_agents/professor/homepage_publication_headings.py

不要碰:
  apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications.py（277 行 drift）
  其它 51 个 drift 文件
```

## 5. Do-not（强制约束）

- ❌ 不要做任何 localhost 网络访问（Postgres/Milvus）——Path A 已把这部分挪给 Claude 做。如果发现自己在写 `psycopg.connect` 或 `localhost:` 之类，停下回报。
- ❌ 不要 fetch 任何 homepage URL（Claude 已经全 fetch 完，HTML 在 logs 目录）
- ❌ 不要改 `extract_publications_from_html` 入口、`HomepagePublication` dataclass、`_find_publications_sections` 函数主体
- ❌ 不要重写或重命名现有 5 个 `_extract_from_*` 策略
- ❌ 不要碰 `test_homepage_publications.py`（drift）
- ❌ 不要引入 LLM / Selenium / Playwright / network-fetching 代码
- ❌ 不要动 Alembic / DB schema / classifier / chat / retrieval / admin-console
- ❌ 不要 amend 已发布的 commit；只新增 commit
- ❌ 不要使用 `--no-verify`
- ❌ 不要 push 到 remote

## 6. 必报项（回 claude review）

```markdown
# Codex Stage B Path A 回报

## A. 选项决策
A 或 B？基于 §1c diagnosis 的具体 DOM 证据。

## B. 修改文件清单 + LOC

## C. before/after 对照（17 个真实样本，跑 §3 Step 4 第 3 子步）

| prof_id | archetype | before | after |
|---|---|---:|---:|
| ... | tsinghua-sigs | 55 | should remain ≥55 |
| ... | sit-csce | 0 | should be ≥5 |
| ... | sztu-sgim | 0 | should be ≥5 |
| ...

## D. 测试结果
- 新单测 PASS / FAIL count
- 既有 publications 单测 PASS / FAIL count
- 命令 + 输出片段（每段 < 30 行）

## E. 风险 / 假设破坏
- §1c probe 是否揭示了 spec §13 假设破坏？
- 选 A 是否影响 working sample（false positive）？

## F. R3 重新评估
- 当前 papers > 0 的 ratio：x/17（baseline 6/17 = 35%）
- 是否达成 baseline.md acceptance（≥ 4/5 SIT、≥ 4/5 SZTU、5/5 regression-guard）

## G. 不在 spec 范围但发现的 follow-up
（可选；只列举，不要顺手做）

## H. Sandbox / 环境状态
- localhost 调用次数：应为 0
- 是否触碰 §5 do-not 列表里任意条？停下了吗？

## 提交信息
- staged files: [list]
- commit SHA: [sha]
```

## 7. Done criteria

- [ ] §1d diagnosis.md 已写
- [ ] §2 选项 A/B 决定有书面理由
- [ ] §3 4 个 archetype（实际是 SIT + SZTU 两类，但每类多个子域）单测 PASS，每个 archetype ≥ 5 papers
- [ ] §3 regression-guard：5 working samples 仍 papers > 0
- [ ] §4 step 4 第 3 子步在 17 真实样本上跑，输出 before/after table
- [ ] §6 回报全部填齐

## 8. Verification commands（一行串）

```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy && \
  cd /home/longxiang/MiroThinker/apps/miroflow-agent && \
  uv run pytest tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py -n0 --no-cov -v && \
  uv run pytest tests/data_agents/professor/ -k "publication" -n0 --no-cov && \
  echo "--- 17-sample sweep ---" && \
  uv run python <<'PY'
from pathlib import Path
from src.data_agents.professor.homepage_publications import extract_publications_from_html
LOGS = Path("/home/longxiang/MiroThinker/logs/data_agents/paper/homepage_ingest_runs/2026-05-09")
samples = sorted(LOGS.glob("PROF-*.html"))
for h in samples:
    html = h.read_text(encoding="utf-8")
    pubs = extract_publications_from_html(html, page_url=f"file://{h}")
    print(f"{h.stem}: {len(pubs)} papers")
PY
```

## 9. 工作树状态

- branch: `main`
- `homepage_publications.py`: 无 drift（已验证 2026-05-09）
- `test_homepage_publications.py`: **+277 lines drift（不要碰）**
- 其它 professor src/test 文件多处 drift：与本任务无关
- 51 个 drift 文件分布广泛 — 严格只动 §4 列出的文件

## 10. Sandbox 注意

本任务**不需要**任何 localhost 网络访问。所有需要网络的部分（DB query、homepage fetch）已由 Claude 完成。你只需要：
- 文件读（`logs/.../*.html`）
- 文件写（修改 parser、新建 test file、写 diagnosis.md、写 commit）
- pytest（不用网）
- git commit（不用网）

如果你的实施过程中发现需要网络，**那是 spec 边界外的工作**，停下回报。

## 11. 完工后

1. 不要 push
2. 把回报粘回，由 claude 写最终 review (`stage-b-final.md`) 决定 accept/revise/reject
3. claude 之后会跑 17-sample sweep 做最终验证
