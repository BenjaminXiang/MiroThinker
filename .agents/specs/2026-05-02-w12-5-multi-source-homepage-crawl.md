---
title: "W12-5: 多源主页抓（Group Website + CV PDF + 2 hop）"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex；claude review + 操作 re-scrape
wave: Wave 12
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w11-7-summary-generator-raw-text.md
prd_anchor: docs/Professor-Data-Agent-PRD.md §模块一 raw_text 完整度
---

# W12-5: 多源主页抓

## 1. Goal

W11-7 backfill 后 787 教授中 91% 有 raw_text，但 raw_text 来源仍是单页 anchor 抓取。丁文伯例可见末尾常含 `Group Website: http://ssr-group.net/...` / CV PDF 链接 → 这些链接信息未抓 → summary 信号不全。

PRD §模块一 R3：profile_summary 应反映完整研究画像（方向 + 团队 + 履历）。CV PDF 与课题组主页是关键补充。

**本 spec**：homepage_crawler 加 2-hop 抓取，follow Group Website / Lab / CV PDF 链接，concatenate 到 profile_raw_text。

## 2. Non-goals

- **不**改 V3 pipeline 主流程（仅扩 homepage_crawler 模块）
- **不**做 JS-rendered 页面（独立 follow-up，需 Playwright）
- **不**改 quality_gate / summary_generator
- **不**抓 paper PDF（噪音多）
- **不**触碰 robots.txt 黑名单站点（保守抓）

## 3. User-visible behavior

| 教授 | 修复前 raw_text | 修复后 raw_text |
|---|---|---|
| 丁文伯（清华 SIGS） | 4735 chars 单页 | + Group Website 内容 ~3000 + CV PDF ~5000 = 12000+ chars |
| 95% 教授有 Group/Lab link | 单页 | 2-3 倍 raw_text |
| 60% 教授有 CV PDF | 仅 link | 加全文 |

W11-7 reinforcement 读 raw_text → 更长 / 更结构化 summary。

## 4. Affected paths

```
新增：
  apps/miroflow-agent/src/data_agents/professor/multi_source_crawler.py
    follow_supplementary_links(html, base_url, max_hops=2) -> list[str] (拼接 raw_text 段)
    _is_group_website_anchor / _is_cv_pdf_anchor / _is_lab_anchor (anchor text + URL pattern matcher)
    _fetch_html_with_timeout / _fetch_pdf_to_text
  apps/miroflow-agent/scripts/run_professor_raw_text_re_scrape.py
    遍历 787 教授；调 multi_source_crawler；UPDATE professor.profile_raw_text
    open/close pipeline_run('backfill_real')
    --resume / --limit / --dry-run

修改：
  apps/miroflow-agent/src/data_agents/professor/homepage_crawler.py
    新 V3 pipeline 调用时也走 multi_source_crawler（V3 后续 STEM 重跑生效）

新增 tests:
  apps/miroflow-agent/tests/data_agents/professor/test_multi_source_crawler.py
    test_follows_group_website_anchor (HTML fixture)
    test_follows_cv_pdf_link (PDF fixture)
    test_respects_2_hop_depth_limit
    test_skips_external_unrelated_domains
    test_handles_pdf_parse_error_gracefully
  apps/miroflow-agent/tests/scripts/test_run_professor_raw_text_re_scrape.py
```

## 5. Anchor matching rules

```python
_GROUP_PATTERNS = [
    r"Group Website", r"实验室", r"课题组", r"Lab\b", r"Group\b",
    r"研究组", r"团队主页",
]
_CV_PATTERNS = [
    r"CV\b", r"个人简历", r"履历", r"resume\.pdf", r"-cv\.pdf",
]
_PDF_URL_PATTERNS = [
    r"\.pdf(\?|$)",
]

def _is_group_website_anchor(text: str, href: str) -> bool:
    text_lc = text.lower()
    return any(re.search(p, text_lc, re.I) for p in _GROUP_PATTERNS)

def _is_cv_pdf_anchor(text: str, href: str) -> bool:
    if any(re.search(p, href, re.I) for p in _PDF_URL_PATTERNS):
        return any(re.search(p, text.lower() + " " + href.lower(), re.I) for p in _CV_PATTERNS)
    return False
```

## 6. Crawl algorithm

```
Hop 1 (already done by V3): primary teacher page → bio_text + links
Hop 2 (new):
  for link in primary_page_links:
    if _is_group_website_anchor(link.text, link.href):
      try: html = fetch(link.href); raw += extract_main_text(html)
    elif _is_cv_pdf_anchor(link.text, link.href):
      try: text = fetch_pdf(link.href); raw += text
    # else skip
    
    For Group page (if visited):
      for sub_link in group_page_links:
        if _is_personal_section(sub_link, prof.name):
          try: html2 = fetch(sub_link.href); raw += extract_main_text(html2)

return raw[:30000]  # cap
```

## 7. Invariants

- 2 hop max（防爬深）
- 单页 fetch timeout 10 sec
- PDF parse timeout 30 sec
- 失败的 fetch / parse → log + skip（不 raise）
- 同 domain 的 sub link 限 5 个（防 link farm）
- robots.txt 不强制检（学校官网通常允许）但实现 User-Agent
- raw_text 拼接结果 cap 30000 chars（防 LLM context overflow；W11-7 prompt 截 4000）

## 8. Edge cases

| 场景 | 处理 |
|---|---|
| Group Website 死链 | skip + log |
| CV PDF 加密 / 扫描件 | pdfminer fail → log skip |
| 同主页 link 出现多次 | dedupe by URL hash |
| 跨域 link（非学校域） | skip（保守） |
| 主页本身 200 但内容 0 字 | skip |
| 需登录的子页 | 401/403 → skip |

## 9. Validation

```bash
cd apps/miroflow-agent

# 单测（HTML/PDF fixture mock）
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/data_agents/professor/test_multi_source_crawler.py \
                tests/scripts/test_run_professor_raw_text_re_scrape.py \
                -n0 --no-cov -v

# 既有不退化
uv run pytest tests/data_agents/professor/ -k crawl -n0 --no-cov

# 操作 re-scrape（claude）：
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_professor_raw_text_re_scrape.py \
    --limit 5 --dry-run > /tmp/rescrape_smoke.json

# 全量
uv run python scripts/run_professor_raw_text_re_scrape.py
```

## 10. Done criteria

1. ✅ multi_source_crawler 单测过；fixture-based PDF + HTML
2. ✅ 既有 crawler 不退化
3. ✅ claude 操作 5 prof smoke 验证 raw_text 显著增长
4. ✅ 全量 re-scrape 后 ≥ 60% 教授 raw_text 长度增长
5. ✅ W11-7 reinforcement 重跑：summary 平均长度 +20%

## 11. Stop conditions

- pdfminer 在 sandbox 不可用 → 用 pdfplumber fallback；都不行 → CV PDF skip
- 抓取速度过慢（< 0.5 prof/sec） → 减少 sub_link 限到 3
- 大量学校域返 4xx → 重检 User-Agent；可能需 robots.txt 遵循

## 12. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| Link follow 范围 | Group Website + Lab + CV PDF |
| 深度 | 2 hop |
| robots.txt | 不强制（保守 throttle 即可）|
| 同域 sub_link 上限 | 5 |
