---
title: admin-console 架构 spec — 与 /browse 运营面板的边界与数据源
date: 2026-04-30
owner: claude
status: active
audience: codex（W10-6 实施 + admin-console 后续工作的设计契约）
related:
  - docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md  # W10-6 系列
  - docs/Data-Agent-Shared-Spec.md  # §6.1 物理分层
  - docs/Agentic-RAG-PRD.md  # 服务层契约
---

# admin-console 架构 spec

## 1. Goal

明确 **admin-console**（`apps/admin-console/`）这个项目内部并存的两套用户面：

- **React SPA**（Vite dev = `5180`，Prod build = `8088/<其他路径>`）
- **`/browse` 运营面板**（vanilla HTML，由后端 serve 在 `8088/browse`）

它们的**作用、读者、数据源、相互关系**，以及当前**数据源分裂**问题（plan W10-6）的修复路径。

让 Codex 在动 admin-console 任何代码前能够：

1. 知道每个 backend 模块（`/api/*` 路由）属于哪一面、读哪个数据库
2. 知道每个 React 页面 / `/browse` tab 调用哪些 endpoint、面向谁
3. 知道哪些不变量必须保留、哪些当前是 broken 状态需修复

## 2. Non-goals

- 本 spec 不重新设计 admin-console（不是 PRD），只规范当前与目标态边界
- 不决定是否 git rm 老的 SQLite store —— 那是 W10-6.5 的具体动作
- 不规范 chat.py 的内部行为（已在 Agentic-RAG-PRD 与 chat.py 中沉淀）
- 不规范 visualize-trace / gradio-demo（独立项目，与本 spec 无关）

## 3. 定义（避免再混淆）

| 术语 | 指什么 | 文件位置 |
|---|---|---|
| **admin-console** | 整个项目，FastAPI 后端 + React SPA + vanilla HTML 运营面板的总称 | `apps/admin-console/` |
| **admin-console backend** | FastAPI 进程，暴露所有 `/api/*` 路由 | `apps/admin-console/backend/` |
| **admin-console React SPA** | React/Vite 前端单页应用，含 4 个页面（Chat / Dashboard / DomainList / RecordDetail）| `apps/admin-console/frontend/` |
| **`/browse` 运营面板** | 由 backend serve 的 vanilla HTML 单页操作面板，**与 React SPA 平行**，不依赖前端构建 | `apps/admin-console/backend/static/browse.html` |
| **canonical Postgres** | 当前生产数据 = `miroflow_real` 上 V003–V011 alembic 表（professor / professor_affiliation / paper / company / patent / 关系表）| 数据库连接 |
| **SQLite released_objects store** | 早期 V2 时代的发布层快照，`SqliteReleasedObjectStore` 类承载 | `data_agents/storage/sqlite_store.py` |

后文严格区分这 6 个术语；不再用"dashboard"作为模糊词。当指 `Dashboard.tsx` 页面时写"Dashboard 页"，指 `/browse` 时写"`/browse` 运营面板"。

## 4. 当前各面的作用与读者

### 4.1 admin-console React SPA

**长期产品形态**。同一个 SPA 服务三类读者：

| 页面 | URL（dev / prod） | 读者 | 现状 |
|---|---|---|---|
| Chat | `/chat` | **最终用户** + 内部 dogfood | ✅ 走 Postgres（chat.py） |
| Dashboard | `/dashboard`（默认入口） | 数据团队 / 运营总览 | ✅ 走 Postgres（dashboard.py） |
| DomainList | `/domain/professor` 等 | 数据团队（按域筛选 / 翻页 / 看列表） | 🔴 **走 SQLite**（domains.py） |
| RecordDetail | `/domain/professor/PROF-xxx` 等 | 数据团队（看单对象 + 编辑） | 🔴 **走 SQLite**（domains.py） |

**关键代码入口**：
- `frontend/src/App.tsx` — 路由
- `frontend/src/api.ts` — 全部 fetch 封装
- `frontend/src/pages/{Chat,Dashboard,DomainList,RecordDetail}.tsx`
- Vite dev = `5180`；prod build 输出在 `frontend/dist/`，由 backend mount 为 `/assets/*` + `/<其他路径>` 的 SPA fallthrough

### 4.2 `/browse` 运营面板（vanilla HTML）

**早期诊断面板**，用于不依赖 React 构建直接审查 canonical 数据。`backend/main.py:49-55` 注释自述 "primary operator surface"。

特点：
- 单文件 `backend/static/browse.html`（约 1500 行手写 JS + Ant-Design like 控件）
- 不依赖前端构建，只需 backend 起来就能用
- 全部走 `/api/data/*` Postgres canonical 路由（data.py）
- 实现了 4 域查询 + provenance / coverage / review 三 tab + pipeline issue 浏览
- 适合数据团队快速排查，不适合最终用户使用

**关键代码入口**：
- `backend/static/browse.html`（唯一文件）
- `backend/main.py:62-73` 路由定义（`/`, `/browse`, `/chat`）

### 4.3 用户面 vs 运营面

| 面 | 谁用 | 当前承载 |
|---|---|---|
| 用户面 | 最终用户、产品演示 | React SPA `/chat`（chat.py）|
| 运营面 | 数据团队、采集与质量审查 | React SPA `/dashboard` + `/domain/*`（**目前读 SQLite，错位**）+ `/browse` 运营面板（读 canonical Postgres） |

**当前 broken**：运营面有两条路径并存，数据源不一致。详见 §6。

## 5. Architecture / Data flow

### 5.1 进程拓扑

```
┌─────────────────────────────────────────────────────────────────┐
│ admin-console FastAPI 进程（uvicorn, port 8088）                 │
│   ├─ 12 个 backend/api/*.py 路由文件                              │
│   ├─ 后端 mount /static、/assets、catch-all SPA fallthrough       │
│   └─ DB 连接：DATABASE_URL=postgresql+psycopg://.../miroflow_real│
│                                                                   │
│   serve:                                                          │
│     /api/* (12 模块路由)                                           │
│     /browse → backend/static/browse.html                          │
│     /chat   → backend/static/chat.html (legacy, 与 React 重复)    │
│     /, /<其他路径> → frontend/dist/index.html (React SPA)         │
└─────────────────────────────────────────────────────────────────┘
                          ▲ proxy /api
                          │
┌─────────────────────────────────────────────────────────────────┐
│ Vite dev server（dev only, port 5180）                           │
│   ├─ 读 frontend/src/ 实时编译，HMR                               │
│   └─ 所有 /api/* 代理到 8088                                      │
│   serve:                                                          │
│     / → frontend/src/main.tsx 入口的 React SPA                    │
└─────────────────────────────────────────────────────────────────┘

数据库:
  ├─ Postgres miroflow_real（生产，端口 15432）
  └─ SQLite ADMIN_DB_PATH 指向（V2 时代发布层快照，目前还在被 React 读）
```

### 5.2 端点 → 存储后端 inventory

12 个 backend/api 模块的存储后端归属：

| 模块 | 路由前缀 | 存储 | 读者 |
|---|---|---|---|
| `chat.py` | `/api/chat` | **Postgres** | React Chat.tsx |
| `dashboard.py` | `/api/dashboard` | **Postgres** | React Dashboard.tsx |
| `data.py` | `/api/data/*`（11 routes：companies / professors / papers / patents / facets / search 等）| **Postgres** | `/browse` |
| `review.py` | `/api/review/*`（4 routes） | **Postgres** | `/browse` |
| `pipeline.py` | `/api/pipeline/*`（2 routes：coverage-by-institution / source-breakdown）| **Postgres** | `/browse` |
| `pipeline_issues.py` | `/api/pipeline-issues/*`（2 routes：guard-runs / 列表） | **Postgres** | `/browse` |
| **`domains.py`** | `/api/{domain}` 通配（6 routes：list / detail / related / filters / patch / delete） | **SQLite** ❌ | **React DomainList / RecordDetail / 编辑 / 删除** |
| **`batch.py`** | `/api/batch/*`（delete / quality） | **SQLite** ❌ | **React 批量操作** |
| **`export.py`** | `/api/export/*` | **SQLite** ❌ | **React 导出** |
| **`upload.py`** | `/api/upload/*` | **SQLite** ❌ | **React 上传** |

❌ 标记 = 与 canonical 数据脱钩，是 W10-6 修复目标。

### 5.3 React SPA → 端点路由映射

| React 调用 | 实际命中 | 期望（W10-6 后） |
|---|---|---|
| `fetchDashboard()` → `/api/dashboard` | `dashboard.py`（Postgres）✅ | 不变 |
| `fetchDomainList(domain, ...)` → `/api/{domain}` | `domains.py`（SQLite）❌ | `domains.py` 内部切 Postgres（方案 B）或前端改走 `/api/data/{domain}s`（方案 A）|
| `fetchDomainObject(domain, id)` → `/api/{domain}/{id}` | `domains.py`（SQLite）❌ | 同上 |
| `updateRecord(domain, id, body)` → PATCH `/api/{domain}/{id}` | `domains.py`（SQLite）❌ | 必须切 Postgres |
| `deleteRecord(...)` → DELETE | `domains.py`（SQLite）❌ | 必须切 Postgres |
| `fetchRelated(domain, id)` → `/api/{domain}/{id}/related` | `domains.py`（SQLite）❌ | 必须切 Postgres |
| `fetchFilterOptions(domain, field)` → `/api/{domain}/filters/{field}` | `domains.py`（SQLite）❌ | 必须切 Postgres |
| 批量 → `/api/batch/{action}` | `batch.py`（SQLite）❌ | 必须切 Postgres |
| 导出 → `/api/export/{domain}` | `export.py`（SQLite）❌ | 必须切 Postgres |
| 上传 → `/api/upload/{domain}` | `upload.py`（SQLite）❌ | 切 canonical 主线（具体方式见 W10-6.4） |
| `/api/chat` POST | `chat.py`（Postgres）✅ | 不变 |

### 5.4 `/browse` → 端点路由映射

`/browse` HTML 直接通过 `fetch()` 调用：

- `/api/data/{domain}` — 4 域列表（companies / professors / papers / patents），data.py
- `/api/data/{domain}/{id}` — 单对象详情
- `/api/data/facets/{kind}` — 过滤选项（institution / industries 等）
- `/api/pipeline/coverage-by-institution`、`/api/pipeline/source-breakdown` — pipeline tab
- `/api/review/sample`、`/api/review/issues`、`POST /api/review/issues` — review tab
- `/api/pipeline-issues/guard-runs`、`/api/pipeline-issues?...` — pipeline-issues tab

**全部走 Postgres canonical**。

## 6. 当前已知偏差

### 6.1 实测偏差

同一台机器、同一 backend 进程（PID 1537803）、同一 institution `清华大学深圳国际研究生院`：

- React DomainList → `/api/professor` → `domains.py` → SQLite → **total = 4**（首条：PROF-8000C9F994C3 丁文伯）
- `/browse` 教授 tab → `/api/data/professors?institution=...` → `data.py` → Postgres → **total = 249**（首条：PROF-C5B04779FA56 杜尚波）

差 245 条。SQLite 是 V2 时代或更早的少量发布快照，**从未与 canonical 主线同步过**。

### 6.2 写入面 silent failure

React 上的所有 PATCH / DELETE / 批量 quality 标记动作只写 SQLite。canonical Postgres 不感知。具体后果：

- 运营在 React 标了 quality_status='ready' → SQLite 标了，Postgres 没标 → chat / retrieval / `/browse` 均看不到这次标记
- 运营在 React 删了一行 → SQLite 删，Postgres 还在 → 数据"死灰复燃"
- 运营在 React 上传 xlsx → SQLite 长一行，pipeline 不会跑，canonical 不更新

### 6.3 字段集差异

`domains.py` 输出 schema = `ReleasedObject`：`id` / `display_name` / `core_facts` / `summary_fields` / `evidence` / `last_updated` / `quality_status`。

`data.py /api/data/professors` 输出 schema = `ProfessorListItem`：`professor_id` / `canonical_name` / `canonical_name_en` / `institution` / `title` / `discipline_family` / `aliases` / `research_topic_count` / `verified_paper_count` / `last_refreshed_at`。

切换时需要适配（见 §8.1 候选方案）。

## 7. Invariants（不变量，任何 PR 不得破坏）

1. **唯一 backend 进程**：admin-console FastAPI 在 8088。**绝不重新拉一个独立进程读不同 DB**（之前 8000 的老进程已 kill）。
2. **数据库唯一权威 = `miroflow_real`**：所有 admin-console 上的"实时数据"必须最终来自 Postgres canonical。SQLite 是历史，逐步退役。
3. **5180 与 8088 数据一致性**：5180 vite 代理 → 8088 backend。同一查询返回必须相同。当前因 §6.1 broken；W10-6 完成后必须满足。
4. **/browse 与 React SPA 数据一致性**：同 institution、同 filter 下，`/browse` 与 React DomainList 的 `total` 必须相同。当前因 §6.1 broken；W10-6 完成后必须满足。
5. **写入 = 读出**：在任一面（React 或 `/browse`）上做的编辑，在另一面立即可见（无缓存延迟超过 1 秒）。当前因 §6.2 broken。
6. **字段契约（与 Shared-Spec 对齐）**：admin-console 暴露的 professor / company / paper / patent 字段必须是 Shared-Spec §4.2 / §4.3 的子集；不得自创字段。
7. **环境变量唯一**：DATABASE_URL 是 admin-console backend 启动的唯一 DB 配置入口。不允许 module-level 默认值或硬编码 fallback。
8. **/browse 不直接连 DB**：`browse.html` 永远只通过 `fetch('/api/...')` 间接访问；不引入独立 DB 客户端。

## 8. Migration plan（与 W10-6 衔接）

### 8.1 候选方案（已决定 — 2026-05-01）

✅ **方案 B 选定**：改后端 `domains.py` 内部切 Postgres，前端 URL 不变。6 个 handler 重写为 Postgres 查询，输出 schema 保持现有 `ReleasedObject`（`id` / `display_name` / `core_facts` / `summary_fields` / `evidence` / `last_updated` / `quality_status`）；写入面（PATCH/DELETE/batch）对 canonical 表生效；前端零改动。

未选用：

- A 改前端走 `/api/data/*`：会强迫 React 4 页重写字段映射（display_name → canonical_name 等），短期摩擦较大
- C SQLite + Postgres 双写：过渡兼容；复杂度高、易不一致
- D 直接 git rm SQLite store：完整切换前 React 整段 break，风险高

### 8.2 执行序（基于方案 B）

1. ~~W10-6.0：用户决策~~ ✅ 已决定 B（2026-05-01）
2. **W10-6.1**：`domains.py` GET 路径切 Postgres（list / detail / filters / related）
3. **W10-6.2 / 6.3**：`batch.py` / `export.py` 切 Postgres
4. **W10-6.4**：`upload.py` 决策（写 source_page raw 触发 pipeline，还是 canonical upsert）
5. **W10-6.6**：跑回归（`/api/professor` ↔ `/api/data/professors` 一致性）
6. **W10-6.5**：`SqliteReleasedObjectStore` git rm；`backend/deps.py` 中 `get_store` 移除；环境变量 `ADMIN_DB_PATH` 退役

### 8.3 `/browse` 长期退役（2026-05-01 已决定）

✅ **决定退役**。理由：与 React SPA 职责重叠 + 数据源分裂（实测 4 vs 249 教授），双面并存制造持续认知混淆。

执行节奏（拆两个 wave）：

- **Wave 10（数据统一）**：W10-6.1–6.6 把 `domains.py` / `batch.py` / `export.py` / `upload.py` 切 Postgres，使 React 与 `/browse` 数据一致；本阶段 `/browse` 仍可访问
- **Wave 13（端口迁移 + 退役）**：W13-7 在 React 建 `Provenance.tsx` / `Coverage.tsx` / `Review.tsx` / `PipelineIssues.tsx` 4 页消费 `/api/pipeline/*` / `/api/review/*` / `/api/pipeline-issues/*`；W13-8 git rm `backend/static/browse.html` + `chat.html`；W13-9 git rm `SqliteReleasedObjectStore`

**退役完成态**：admin-console 单面 = React SPA；唯一存储 = Postgres `miroflow_real`；端口 5180/8088 数据完全一致。

## 9. Validation commands

W10-6 任意子项落地后须通过：

```bash
# 一致性回归（必须 pass）
diff <(curl -s "http://localhost:8088/api/professor?filters=%7B%22institution%22%3A%22清华大学深圳国际研究生院%22%7D&page_size=1000" | jq '.total') \
     <(curl -s "http://localhost:8088/api/data/professors?institution=清华大学深圳国际研究生院&page_size=1000" | jq '.total')

# Patch 后两面立即可见（必须 pass）
curl -X PATCH "http://localhost:8088/api/professor/PROF-XXX" \
  -H "Content-Type: application/json" \
  -d '{"quality_status":"ready"}'
curl -s "http://localhost:8088/api/data/professors/PROF-XXX" | jq '.quality_status'
# → "ready"

# pytest
cd apps/admin-console && uv run pytest tests/ -k "domains or batch or upload or export" -n0
```

## 10. Open questions

- [ ] **W10-6.0 架构决策**（A/B/C/D），见 §8.1 — 用户尚未拍板
- [x] ~~`/browse` 长期去留~~ → **2026-05-01 已决定退役**（plan W13-7/8）。详见 §8.3
- [x] ~~React 是否承载 `/browse` 三 tab~~ → **是**。Wave 13 起 4 个 React 页：Provenance / Coverage / Review / PipelineIssues
- [x] ~~`chat.html` 退役~~ → **是**。Wave 13 一并 git rm
- [ ] `upload.py` 切 canonical 时的语义：是触发 pipeline 还是直接 upsert canonical？取决于 W10-6.4 设计
- [ ] 是否需要 admin-console 对外的简单 README（onboarding 用），与本 spec 区分

## 11. Assumptions

- admin-console backend 与 frontend 始终同源部署，不拆分（Vite dev 例外，仅本地开发）
- `miroflow_real` 是当前与可预见未来唯一的生产 Postgres
- React SPA 与 `/browse` 的并存仅是 W10-6 完成前的过渡态，不视为长期目标
- 用户所说的"前端"在大多数对话上下文中指 admin-console React SPA + `/browse` 两套 UI 之一或两者，不指 visualize-trace / gradio-demo / lobehub-compatibility 等独立项目

## 12. 附录：关键文件清单

```
apps/admin-console/
├── backend/
│   ├── main.py                ← FastAPI app + 路由 mount
│   ├── deps.py                ← DATABASE_URL 解析、SQLite store factory（待退役）
│   ├── api/
│   │   ├── chat.py            (Postgres) ✅
│   │   ├── dashboard.py       (Postgres) ✅
│   │   ├── data.py            (Postgres) ✅ — /browse 主依赖
│   │   ├── review.py          (Postgres) ✅
│   │   ├── pipeline.py        (Postgres) ✅
│   │   ├── pipeline_issues.py (Postgres) ✅
│   │   ├── domains.py         (SQLite) ❌ — W10-6.1 切 Postgres
│   │   ├── batch.py           (SQLite) ❌ — W10-6.2 切 Postgres
│   │   ├── export.py          (SQLite) ❌ — W10-6.3 切 Postgres
│   │   └── upload.py          (SQLite) ❌ — W10-6.4 切 canonical
│   └── static/
│       ├── browse.html        ← /browse 运营面板（vanilla HTML，Postgres 直读）
│       └── chat.html          ← legacy chat 页（已被 React Chat.tsx 覆盖，待退役）
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api.ts             ← fetchJSON 封装、URL 拼装
│   │   └── pages/
│   │       ├── Chat.tsx        (Postgres ✅，via /api/chat)
│   │       ├── Dashboard.tsx   (Postgres ✅，via /api/dashboard)
│   │       ├── DomainList.tsx  (SQLite ❌，via /api/{domain})
│   │       └── RecordDetail.tsx(SQLite ❌，via /api/{domain}/{id})
│   ├── dist/                   ← 上次 npm run build 输出（Apr 17，stale）
│   └── vite.config.ts          ← server.port=5180, proxy /api → :8088
└── tests/                      ← pytest（含 test_chat_v1 / test_chat_retrieval / test_professor_api 等）
```
