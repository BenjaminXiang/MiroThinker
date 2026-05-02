---
title: "W12-4: M2.1 selector 扩展深圳高校 CMS 模板"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review
wave: Wave 12
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_solutions:
  - docs/solutions/integration-issues/homepage-paper-ingest-dogfood-2026-05-02.md  # W9-5 R3 partial-fail 根因
prd_anchor: docs/Paper-Data-Agent-PRD.md §M2.1 主页 publications selector
---

# W12-4: M2.1 selector 扩展深圳高校 CMS 模板

## 1. Goal

W9-5 dogfood 实测：M2.1 `homepage_publications` selector 在 10 教授真实主页中**全部**检测到 publications 区段但**0 篇**论文被提取。根因：现有 5 个合成 archetype 不覆盖深圳高校 CMS 模板（清华 SIGS、深圳理工、深圳技术大学、中大深圳）。

PRD §模块三 R3：主页论文采集 ≥ 15 papers/prof × 10 profs。当前 0 篇 → R3 fail。

**本 spec**：基于 W9-5 收集的 10 教授真实 HTML 样本，扩展 selector + 模板规则，目标 ≥ 5 篇/prof 平均（保守门槛）。

## 2. Non-goals

- **不**做 OpenAlex / arxiv / Serper 链路（M2.2 / M2.3 已完成）
- **不**做 JS-rendered 页面抓（独立 follow-up）
- **不**做 PDF 解析增强
- **不**做单 selector 完美覆盖；目标是覆盖深圳 lane 1 的 7 所学校

## 3. User-visible behavior

| 学校 | 修复前 | 修复后目标 |
|---|---:|---:|
| 清华大学深圳国际研究生院 | 0 papers/prof | ≥ 5 |
| 中山大学（深圳） | 0 | ≥ 5 |
| 深圳技术大学 | 0 | ≥ 5 |
| 深圳理工大学 | 0 | ≥ 5 |
| 港中深 / SUSTech / HIT-SZ | 0-N | best-effort |

## 4. Affected paths

```
修改：
  apps/miroflow-agent/src/data_agents/professor/homepage_publications.py
    + 添加 4 个深圳高校 archetype（CSS selector + JSONLD pattern）
    + 段落识别加 "近期论文 / 学术成果 / 期刊论文 / SCI 论文 / Selected Publications" 标题模式
  apps/miroflow-agent/src/data_agents/professor/homepage_publication_headings.py
    + 标题词扩展（中英文混合）

新增：
  apps/miroflow-agent/tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py
    fixture 5 个真实 HTML 样本（清华 SIGS / 深圳理工 / 中大深圳 / 深圳技术 / 港中深）
    每个 ≥ 5 papers extracted assertion
```

## 5. Investigation 方法（codex 必读）

1. claude 已收集 10 教授样本 HTML 在 `logs/data_agents/paper/homepage_ingest_runs/2026-04-30/<prof_id>.html`（如不存在，跑 `scripts/run_homepage_paper_ingest.py --dry-run --limit 10` 重生成）
2. 对每个学校样本，分析现有 selector 错过的 pattern：
   - 清华 SIGS: 通常 `<div class="news-list">` 或 `<ul class="paper-list">`
   - 深圳理工: SUSTech 集团模板，类似 academic.sit.edu.cn
   - 中大深圳: SYSU CMS，`<div class="ml-publications">`
   - 深圳技术: SZTU 自建模板
3. 不写正则；用 BeautifulSoup 选择器组合

## 6. Interface contracts

`extract_papers_from_homepage(html: str, base_url: str) -> list[ExtractedPaper]` 不变。新增 archetype 内部分发：

```python
_SHENZHEN_CMS_ARCHETYPES = [
    ("tsinghua-sigs", _matches_tsinghua_sigs, _extract_tsinghua_sigs),
    ("sit-shenzhen", _matches_sit, _extract_sit),
    ("sysu-shenzhen", _matches_sysu_shenzhen, _extract_sysu_shenzhen),
    ("sztu", _matches_sztu, _extract_sztu),
]

def extract_papers_from_homepage(html, base_url):
    # 现有 archetype loop
    for name, matcher, extractor in (_EXISTING_ARCHETYPES + _SHENZHEN_CMS_ARCHETYPES):
        if matcher(html, base_url):
            return extractor(html, base_url)
    # 现有兜底
```

## 7. Invariants

- 不破坏现有 5 archetype 行为
- ExtractedPaper schema 不变
- 现有 test 全过
- 无 LLM 调用（纯 HTML parser）

## 8. Validation

```bash
cd apps/miroflow-agent

uv run pytest tests/data_agents/professor/test_homepage_publications_shenzhen_cms.py -n0 --no-cov -v

# 既有
uv run pytest tests/data_agents/professor/ -k "publication" -n0 --no-cov

# 端到端 dry-run（claude 操作）
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_homepage_paper_ingest.py --dry-run --limit 10
# 期望：10 个教授中 ≥ 7 个 papers > 0
```

## 9. Done criteria

1. ✅ 4 学校 archetype + 单测 ≥ 5 papers/prof
2. ✅ 既有 publications 单测无退化
3. ✅ 端到端 dry-run 显著改善（Y/N 两段对比）
4. ✅ R3 重新评估（claude 跑后归档）

## 10. Stop conditions

- HTML 样本从未生成（claude 没存）→ codex 跑 dry-run 重新生成
- 4 学校 selector 互相冲突 → 加分发顺序优先级；不优化即可

## 11. Open questions

| 问题 | 决策 |
|---|---|
| HTML 样本路径？ | claude 后续提供（dogfood 已存）|
| Selector 维护成本？ | 每年 1-2 次更新（CMS 升级）|
| JS-rendered 页面？ | 独立 follow-up，本 spec 不处理 |
