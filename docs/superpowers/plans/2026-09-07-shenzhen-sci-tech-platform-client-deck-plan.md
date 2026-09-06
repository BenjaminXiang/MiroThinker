# 深圳科创数据平台客户介绍 PPT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成一份两页、面向业务负责人和技术负责人的深圳科创数据平台客户介绍 PPT，并附真实系统截图与可预览 PDF。

**Architecture:** 用 Python `python-pptx` 生成 16:9 PPTX。第一页表达“自然语言问题如何变成带证据的答案”，第二页表达“四域数据底座 + Canonical-v2 服务层 + 运营闭环”。截图使用仓库已有真实界面，若本地服务可启动则再补 `/chat` 截图；所有文案以仓库文档为准，不添加未验证指标。

**Tech Stack:** Python 3.12+, `python-pptx`, Pillow, LibreOffice headless PDF export, existing PNG/JPG assets.

## Global Constraints

- 只交付两页 PPT；每页一条主线，适合 3–5 分钟客户介绍。
- 业务负责人能听懂，技术负责人认可；术语保留 Canonical-v2、PostgreSQL、Milvus、rerank、evidence 等必要名称并给中文解释。
- 至少使用两张真实系统截图；不伪造对话内容，不把 benchmark 分数当作平台交付指标。
- 不改变产品代码、配置、数据库或数据；新增文件仅限设计说明、计划、PPT 生成脚本、截图素材和导出文件。
- 交付前验证 PPTX 可打开、PDF 页数为 2、渲染图无明显溢出或遮挡。

---

### Task 1: 整理客户演示素材

**Files:**
- Read: `docs/Agentic-RAG-PRD.md`, `docs/Data-Agent-Shared-Spec.md`, `apps/admin-console/backend/static/chat.html`
- Copy/derive: `artifacts/screenshots/baseline-home.png`, `artifacts/screenshots/baseline-professors-list.png`
- Optional: `artifacts/screenshots/chat-live.png` only if a local `/chat` page can be started without changing runtime configuration

**Interfaces:**
- Produces: two authentic interface images with known pixel dimensions, ready for placement in the deck.

- [x] **Step 1: Verify source screenshots and crop targets**

Run:

```bash
identify baseline-home.png baseline-professors-list.png
```

Expected: both files are 1280x900 PNGs showing the admin console.

- [x] **Step 2: Create a presentation asset directory**

Create `artifacts/screenshots/` and copy the two source images there without modifying the originals. Use the exact filenames above so the deck build is reproducible.

- [x] **Step 3: Check whether `/chat` can be captured**

Inspect `apps/admin-console/backend/main.py` and existing launch scripts. A live `/chat` capture was not added because the local data runtime/model dependencies were not started; the two verified admin-console screenshots are used instead and the limitation is recorded in the final verification.

- [x] **Step 4: Verify image readability**

Open the copied images at high detail and ensure the dashboard cards, table headers, and filters remain legible after a 16:9 slide placement.

### Task 2: Implement the two-page deck generator

**Files:**
- Create: `artifacts/build_client_intro_deck.py`
- Read: `docs/superpowers/specs/2026-09-07-shenzhen-sci-tech-platform-client-deck-design.md`
- Inputs: `artifacts/screenshots/baseline-home.png`, `artifacts/screenshots/baseline-professors-list.png`, `国先 logo.jpg`
- Produces: `artifacts/shenzhen-sci-tech-platform-client-intro.pptx`

**Interfaces:**
- Script entry point: `python artifacts/build_client_intro_deck.py`
- Output: a two-slide 16:9 `Presentation` saved to the artifact path.

- [x] **Step 1: Add the slide theme and helper functions**

Define constants for 13.333x7.5 inch slides, navy/teal/amber/line colors, and helpers for title text, rounded panels, arrows, badges, image frames, and footer labels. Use Aptos/Arial-compatible fonts and keep text sizes at or above 11 pt except for small captions.

- [x] **Step 2: Build slide 1**

Place the title and one-sentence value statement at the top. Add a five-stage horizontal flow (`问题理解`, `意图路由`, `单域/跨域检索`, `召回融合 + rerank`, `结构化答案 + evidence`) in the left/middle area. Add a compact four-domain strip (`教授 / 企业 / 论文 / 专利`) and two authentic screenshots on the right/bottom with captions `运营总览` and `教授数据资产`.

- [x] **Step 3: Build slide 2**

Place the title at the top. Draw three bounded architecture bands: `交互与运营层`, `Canonical-v2 服务层`, `数据与检索层`. Show PostgreSQL, Milvus, Web Search, unified identity, projections, relationships, evidence, streaming session, and multi-turn context. Add a right-side evidence rail with five proof points and two small screenshot crops linked to `可运营` and `可追溯`.

- [x] **Step 4: Keep copy accurate and client-readable**

Use only capabilities supported by the PRD/shared spec: four domains, semantic routing, cross-domain aggregation, multi-turn context, PostgreSQL + Milvus, evidence traceability, quality gates, relationship projection, and replay validation. Do not mention unfinished readiness ratios, accuracy claims, or model benchmark scores.

- [x] **Step 5: Run the generator**

Run:

```bash
python artifacts/build_client_intro_deck.py
```

Expected: `artifacts/shenzhen-sci-tech-platform-client-intro.pptx` exists and contains exactly 2 slides.

### Task 3: Export and render for visual verification

**Files:**
- Input: `artifacts/shenzhen-sci-tech-platform-client-intro.pptx`
- Create: `artifacts/shenzhen-sci-tech-platform-client-intro.pdf`
- Create: `artifacts/rendered/slide-1.png`, `artifacts/rendered/slide-2.png`

**Interfaces:**
- Uses LibreOffice headless conversion and PDF rasterization available in the environment.
- Produces visual evidence for the final handoff.

- [x] **Step 1: Convert PPTX to PDF**

Run:

```bash
libreoffice --headless --convert-to pdf --outdir artifacts artifacts/shenzhen-sci-tech-platform-client-intro.pptx
```

Expected: a two-page PDF is created in `artifacts/`.

- [x] **Step 2: Render both pages to PNG**

Use `pdftoppm -png -r 144` or an equivalent installed renderer to create `artifacts/rendered/slide-1.png` and `slide-2.png`.

- [x] **Step 3: Inspect rendered pages**

Open both rendered PNGs and check: no text is clipped, the architecture arrows remain aligned, screenshots are not stretched, captions are readable, and the slide hierarchy is clear at 144 dpi.

### Task 4: Self-review and handoff evidence

**Files:**
- Modify: `docs/superpowers/plans/2026-09-07-shenzhen-sci-tech-platform-client-deck-plan.md`
- Optional: `docs/plans/index.md` only if a human-doc entry is explicitly desired; otherwise leave unchanged

- [x] **Step 1: Verify file list and slide count**

Run:

```bash
python - <<'PY'
from pptx import Presentation
from pathlib import Path
p = Path('artifacts/shenzhen-sci-tech-platform-client-intro.pptx')
prs = Presentation(p)
print('slides', len(prs.slides))
print('bytes', p.stat().st_size)
PY
pdfinfo artifacts/shenzhen-sci-tech-platform-client-intro.pdf | rg '^Pages:'
```

Expected: `slides 2`, a non-zero file size, and `Pages: 2`.

- [x] **Step 2: Report verification in layers**

Final response must distinguish: (1) new artifact checks and visual inspection, (2) pre-existing system screenshots reused, (3) live `/chat` capture status and any environment limitation.

- [x] **Step 3: Mark plan tasks complete**

Update checkboxes only after each command and visual check has actually run in this session.
