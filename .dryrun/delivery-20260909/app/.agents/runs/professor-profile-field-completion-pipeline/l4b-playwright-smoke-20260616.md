# L4(b) Playwright Smoke — HIT(Shenzhen) (2026-06-16)

## Result: ✅ Playwright rendering works; rendered DOM contains all target fields

Probe: `sync_playwright` → chromium headless → `homepage.hit.edu.cn/hedaojing` → `wait_until=networkidle` + 4s. **No proxy needed** (direct fetch works in this env). Rendered text length ~1.7 KB+ (full profile).

## Rendered content + field map

| Rendered section (label) | Maps to professor field | Notes |
|---|---|---|
| 何道敬 | canonical_name | header |
| 长聘教授、博导；副院长… | academic_position / title | "目前就职" block |
| 信息学部/计算机科学与技术学院（深圳） | department / institution | |
| 研究方向 | research_directions | section label present |
| 个人简介 (long paragraph) | profile_summary + research_topic facts | rich: 人工智能/网络空间安全/机器人/大模型/具身智能/医疗大健康; "83篇IEEE论文, 185专利" |
| 教育及工作经历 | education + work_experience | section present |
| 部分项目及论文列表 | **papers (Part 2.1) + projects** | section present — papers recoverable for HIT-SZ too |
| 成果 / 专利 / 荣誉 / 邮箱 / @ | awards / patents / honors / contact | present |

Field-hit counts in rendered DOM: 研究方向×1, 个人简介×2, 工作经历×1, 教授×1, 邮箱×1, @×2, 论文×4, 成果×3, 专利×1, 项目×6, 荣誉×1.

## Conclusion
- **L4(b) approach = Playwright render → parse rendered DOM sections → map to professor_fact/papers with provenance.** The browser executes the page's AES-crypto `.do` calls; we do NOT need to replicate the `{k,v,d}` API.
- Papers are in the rendered page → this adapter also closes HIT-SZ's Part 2.1 (0-paper) gap, not just profile fields.
- The page structure (labeled sections: 个人简介 / 教育及工作经历 / 部分项目及论文列表) is parseable from the rendered DOM.

## Status
- L4(a) redirect-follow fix: DONE + verified (1 redirect test pass; 249 fetch-path tests no regression).
- L4(b) smoke: DONE (this artifact) — approach locked.
- L4(b) adapter (render + parse + map + provenance + tests + ingest integration): pending — re-dispatch to Codex.
