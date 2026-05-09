---
title: "W12-4 Stage B: 主页论文采集深圳高校 archetype 覆盖（重对齐当前架构）"
date: 2026-05-09
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review
wave: Wave 12 / Wave 13 sweep follow-up
supersedes: .agents/specs/2026-05-02-w12-4-m2-1-selector-expansion.md (Stage A 已落地)
related:
  - .agents/specs/2026-05-02-w12-4-m2-1-selector-expansion.md  # 原 W12-4 spec（设计意图来源；§6 dispatcher 设计已废）
  - .agents/reviews/2026-05-08-sweep-w12-4-escalated.md         # 5/8 sweep 升级原因（drift 已清场）
  - docs/Paper-Data-Agent-PRD.md                                # §模块三 R3
prd_anchor: docs/Paper-Data-Agent-PRD.md §M2.1 主页 publications selector / §模块三 R3
---

# W12-4 Stage B: 主页论文采集深圳高校 archetype 覆盖

## 0. Why this spec replaces the original §6

`apps/miroflow-agent/src/data_agents/professor/homepage_publications.py` 在 5/2 之后两次 commit
（`d3708ba` M2.1 pure HTML→list extractor、`5519354` venue/author parser robustness）演化为
**内容策略 dispatcher**，而非原 spec §6 设想的「institution-template archetype dispatcher」：

```
extract_publications_from_html(html, *, page_url, author_filter=None)
  → soup landmark-strip
  → sections = _find_publications_sections(soup)        # 用 _PUBLICATIONS_HEADING_KEYWORDS
  → for section in sections:
        _extract_section_publications(section, ...)
          → _extract_from_list             # <ul>/<ol>
          → _extract_from_paragraphs       # <p> 列表
          → _extract_from_table            # <table>
          → _extract_from_year_groups      # 按年份分块
          → _extract_from_definition_list  # <dl>
  → _dedupe_publications
  → cap _MAX_ITEMS_PER_PAGE
```

W9-5 dogfood 实测："Detected publications section on 10 professor pages but extracted 0 papers"
（spec 原文 §1）→ section detection 已经通过；**真正的失败在内容策略**对深圳高校 CMS DOM 的覆盖。

中文 heading 词典已经齐全（`学术论文 / 代表性论文 / 发表论文 / 论著 / 论文` 等都在
`homepage_publication_headings.py::_PUBLICATIONS_HEADING_KEYWORDS`）。本 spec **不动 heading 词典**。

## 1. Goal

让 `extract_publications_from_html` 在以下 4 类深圳高校真实主页 HTML 上各自提取 ≥ 5 篇论文：

| 学校 | 修复前 | 修复后目标 | 备注 |
|---|---:|---:|---|
| 清华大学深圳国际研究生院 (Tsinghua SIGS) | 0 | ≥ 5 | jdsigs.tsinghua.edu.cn / sigs.tsinghua.edu.cn |
| 中山大学（深圳） (SYSU Shenzhen) | 0 | ≥ 5 | 各院系 CMS（生医工、智能工等）|
| 深圳理工大学 (SIT) | 0 | ≥ 5 | sit.edu.cn 系教师页 |
| 深圳技术大学 (SZTU) | 0 | ≥ 5 | sztu.edu.cn 系教师页 |
| 港中深 / SUSTech / HIT-SZ | 0–N | best-effort，不破坏现状 | 如已能跑就保持 |

最终评估口径：`scripts/run_homepage_paper_ingest.py --dry-run --limit 10` 在上述 4 类样本上 ≥ 4
个教授拿到 papers > 0（保守门槛；理想 7/10）。

## 2. Non-goals

- ❌ 不重写 `extract_publications_from_html` 入口和 `_find_publications_sections`
- ❌ 不动 `_PUBLICATIONS_HEADING_KEYWORDS`（已覆盖中文）
- ❌ 不接 OpenAlex / Serper / arxiv 链路（M2.2/M2.3 已闭环）
- ❌ 不做 JS 渲染页面（Selenium / Playwright）
- ❌ 不做 PDF 解析增强
- ❌ 不重构现有 5 个 `_extract_from_*` 策略的命名/接口
- ❌ 不引入 LLM 调用（本 spec 是纯 BeautifulSoup 解析增强）

## 3. User-visible behavior

`scripts/run_homepage_paper_ingest.py --dry-run --limit 10` 后：

```text
                修复前                          修复后
prof A (Tsinghua SIGS):  0 papers      →   ≥ 5 papers
prof B (SYSU Shenzhen):  0 papers      →   ≥ 5 papers
prof C (SIT):            0 papers      →   ≥ 5 papers
prof D (SZTU):           0 papers      →   ≥ 5 papers
... 其它 6 教授：不退化
```

## 4. Affected paths

```
修改：
  apps/miroflow-agent/src/data_agents/professor/homepage_publications.py
    选项 A（首选）：在 _extract_section_publications 里新增第 6 个内容策略
                    （e.g. _extract_from_shenzhen_cms_blocks）专门处理深圳高校
                    常见 DOM 模式（基于 dry-run 收集到的真实样本）
    选项 B（次选）：在现有 _extract_from_list / _extract_from_paragraphs /
                    _extract_from_table 里加 institution-aware 容忍度（更窄改动）
    实施前 codex 必须先做 §5 调研 决定走 A 还是 B 并在 PR/handoff 报告里说明

  （以下文件按需，最多动一处）：
  apps/miroflow-agent/src/data_agents/professor/homepage_publication_headings.py
    仅当调研发现某个 archetype 的 heading 不在现有词典内才追加；否则不动

新增：
  apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py
    fixture: 4 个真实 HTML 样本（清华 SIGS / 深圳理工 / 中大深圳 / 深圳技术）
    每个 archetype 至少 1 个 fixture + 1 个 ≥ 5 papers extracted assertion
    fixture 来源：dry-run 重新生成或手工抓的 minimal HTML 切片（可只保留 publications 段落）

logs/data_agents/paper/homepage_ingest_runs/2026-05-09/
  在线 dry-run 运行归档（HTML 样本、提取结果、对照表）
```

## 5. Investigation 方法（codex 必读，必须先跑）

### 5.1 重生成真实样本

样本未保留（spec §0 引用的 `2026-04-30/` 目录为空）。codex 第一步：

```bash
# ⚠️ 必须先 unset proxy（项目环境约束 — 见 §13 A6）
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy

cd apps/miroflow-agent

# DSN 用 libpq 形式（不是 SQLAlchemy 的 postgresql+psycopg://，2026-05-09 stop #1 验证）
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_homepage_paper_ingest.py --dry-run --limit 10 \
  2>&1 | tee /tmp/w12-4-stage-b-dryrun-before.log
```

> **DSN note**：`run_homepage_paper_ingest.py` 用 raw `psycopg.connect(dsn)`，**不走 SQLAlchemy**；
> CLAUDE.md §6 文档化的 `postgresql+psycopg://...` 是 admin-console 后端的 SQLAlchemy 形式，
> 不能用在这个脚本（2026-05-09 Codex stop #1 已验证）。
>
> **Proxy note**：项目 shell 默认 `ALL_PROXY=socks5://...`，SOCKS5 会拦截 loopback TCP 握手；
> codex 子代理的子 shell 不必然有 `NO_PROXY=localhost` 例外（2026-05-09 Codex stop #2 验证）；
> 所以**所有**本地 verification 命令必须先 `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy`。

如果 Web Search / 主页抓取受限，**这一步 codex 必须停下来报告**（不要硬编 fixture）。

### 5.2 分析每个 Shenzhen 样本的失败模式

对每个样本 HTML：

1. 跑 `_find_publications_sections(BeautifulSoup(html, "lxml"))` 看它返回了什么 section
2. 对每个 section，逐个调用 5 个现有 `_extract_from_*` 策略，看每个返回 0 还是非 0
3. 如果都是 0：DOM 结构是哪种？纯 `<div>` 嵌套？年份-标题倒序但没用 `<h2>` 分块？带项目编号 `[1]`？
4. 记录到 `logs/data_agents/paper/homepage_ingest_runs/2026-05-09/diagnosis.md`

### 5.3 决定 A 还是 B

- 如果 4 个 archetype 共享一个统一新 DOM 模式 → **选项 A（新策略）**
- 如果各 archetype 失败原因互不相同（清华 vs 中大 vs SIT vs SZTU 各踩各的坑）→ **选项 B（patch 现有策略）**
- 如果调研发现 root cause 在 `_find_publications_sections` 而不在内容策略 → 暂停，回报 claude（与 spec 假设矛盾）

## 6. Interface contracts

`extract_publications_from_html(html, *, page_url, author_filter=None) -> list[HomepagePublication]`
**完全不变**。`HomepagePublication` 数据类不变。`_PUBLICATIONS_HEADING_KEYWORDS` 不变（除 §4 例外）。

如选 A：新增的 `_extract_from_shenzhen_cms_blocks` 必须遵循与现有 `_extract_from_*` 一致的签名
（接受 BeautifulSoup `Tag`，返回 `list[HomepagePublication]` 或迭代候选），并在
`_extract_section_publications` 的策略链里以 fallback 顺序加入（在现有 5 策略**之后**，避免抢夺）。

## 7. Invariants

- 不破坏 `extract_publications_from_html` / `HomepagePublication` 公共接口
- 现有 `tests/data_agents/professor/test_homepage_publications.py` 里 32+ scenarios 全过
  （注：该文件当前有 277 行 working-tree drift 是另一拨 venue/author parser robustness 工作；
  本 spec 不接触该文件，新测试写到独立的 `_shenzhen_cms.py` 文件以避免 boundary 重叠）
- 现有 5 archetype（5 个内容策略）行为不退化
- 不引入 LLM、network、selenium 调用
- 不修改 Alembic / DB schema / 公共 API 序列化形态
- 不动 `_VALID_DOMAINS` / 路由 / classifier
- 解析必须是纯函数（同一 HTML → 同一输出）

## 8. Edge cases / failure modes

- 某 archetype 站点对 user agent 敏感 → 调研阶段 dry-run 拿不到样本 → 报告，不硬编
- 样本里大量「会议讲座」混入 publications section（中文页常见）→ 容忍度提升不应导致 false positive
- 样本里有 `[1]/[2]/...` 编号前缀、`、，` 全角分隔 → 利用现有 `_strip_item_prefix*` 工具，不要自己写
- 标题里出现引号嵌套或 LaTeX 表达式 → 用现有 `_extract_quoted_title_segment` 行为，不另起一套

## 9. Validation

```bash
cd apps/miroflow-agent

# 1) 新单测（必须 PASS）
uv run pytest tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py -n0 --no-cov -v

# 2) 既有单测（必须不退化）
uv run pytest tests/data_agents/professor/ -k "publication" -n0 --no-cov

# 3) 端到端 dry-run（必须有显著改善；归档到 logs/data_agents/paper/homepage_ingest_runs/2026-05-09/）
#    必须 unset proxy（§5.1 Proxy note）；DSN libpq 形式（§5.1 DSN note）
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy && \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_homepage_paper_ingest.py --dry-run --limit 10 \
  2>&1 | tee logs/data_agents/paper/homepage_ingest_runs/2026-05-09/after.log
```

期望 §3 表里 ≥ 4 个深圳教授拿到 papers > 0。

## 10. Done criteria

1. ✅ §5.1 dry-run before 日志归档（即使受限）
2. ✅ §5.2 diagnosis.md 写到 logs 目录，说明每个 archetype 的失败模式
3. ✅ A/B 选择有书面理由
4. ✅ 4 个 archetype fixture 单测 ≥ 5 papers/prof PASS
5. ✅ 既有 publications 单测无退化
6. ✅ 端到端 dry-run before/after 对照在 PR/handoff 回报里
7. ✅ Stage B 报告里附 R3 重新评估的一句结论（≥ 5 papers/prof × 4/10 → R3 是否仍 fail）

## 11. Stop conditions（codex 必须遇到就停下报告）

- §5.1 dry-run 起不来（DATABASE_URL/Postgres/Web Search 任一项缺）→ 停，报告，**不要伪造 fixture**
- §5.2 调研发现根因在 `_find_publications_sections` 或 heading 词典缺失 → 停，回报 claude（与本 spec §0 假设矛盾）
- 新策略与现有 5 策略冲突且无法用 fallback 顺序解决 → 停，回报
- 实测发现 4 个 archetype 都需要 JS 渲染（lxml 解析的 HTML 是壳子）→ 停，本 spec 范围之外

## 12. Migration / rollback

无 schema/数据迁移。代码层 rollback：`git revert` 单 commit 即可；不会污染 Postgres、Milvus、benchmark
报告或公共 API。

## 13. Assumptions（如不成立必须停下报告）

- A1: 5/8 之后 `homepage_publications.py` 无 working-tree drift（已验证 ✅，2026-05-09）
- A2: Postgres `miroflow_real` 起着，含教授数据（claude 已验证 unset proxy 后可连，DB 有 29 张表，含 `professor` 系列）
- A3: Web Search / OpenAlex / arxiv 未关停（claude 已验证 dry-run 期间 `api.openalex.org` 与 `export.arxiv.org` 都返 200）
- A4: 教授主页 URL 在 DB 里有
- A5: Shenzhen 4 archetype 真的是「section ✓ extraction ✗」而非 JS 渲染问题
- A6: **proxy 已被 unset**（项目环境 `ALL_PROXY=socks5://...` 会拦截 loopback TCP；§5.1 Proxy note；Codex stop #2 验证）
- A7: DSN 形式是 libpq `postgresql://...`（非 SQLAlchemy `postgresql+psycopg://`；§5.1 DSN note；Codex stop #1 验证）

## 14. Open questions

| 问题 | 处理 |
|---|---|
| 选 A（新策略）还是选 B（patch 现策略）？ | codex 调研 §5 后决定，并在 review 里说明理由 |
| Fixture 用真实抓页 HTML 还是手工 minimal HTML？ | codex 自决，建议保留真实抓页（更不易 over-fit） |
| 是否同时 backfill 已收录但 papers=0 的教授？ | 本 spec **不**做。Stage C 任务，归 W13-10 之后 |

## 15. Self-review / boundary check

- 不接触 `_PUBLICATIONS_HEADING_KEYWORDS`（除 §4 例外，调研后才能启用）
- 不接触现有 `test_homepage_publications.py`（277 行 drift 是别人在做的 parser robustness 工作）
- 新测试独立文件 → boundary 干净
- 不动 admin-console、retrieval、classifier、chat 任何代码
- 不动 docs/ 之外只补 `logs/data_agents/paper/homepage_ingest_runs/2026-05-09/`
