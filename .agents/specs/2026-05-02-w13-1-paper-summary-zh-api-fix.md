---
title: "W13-1: paper summary_zh API 暴露修正（P0-1）"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex（实施）；claude review
wave: Wave 13
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w12-3-paper-v011-fields-exposure.md
  - .agents/specs/2026-05-02-w12-6-paper-summary-zh.md
prd_anchor: docs/Paper-Data-Agent-PRD.md §4.1（summary_zh 必填）
shared_spec_anchor: docs/Data-Agent-Shared-Spec.md §4.3（论文 summary_zh 四段式）
---

# W13-1: paper summary_zh API 暴露修正（P0-1）

## 1. Goal

W12-6（V018）已在 `paper` 主表加入 `summary_zh TEXT` 列、abstract_translator 已具备 Gemma-4 翻译能力。但 `apps/admin-console/backend/api/domains.py` 的对外接口存在两个一致性 bug，使得"V018 列加了 = 用户看到中文摘要"这件事完全不成立：

1. **PAPER_SELECT_SQL 漏列**：`apps/admin-console/backend/api/domains.py:219-243` `PAPER_SELECT_SQL` 没有 SELECT `p.summary_zh`，row dict 里根本没有这个 key。
2. **DTO 接口欺骗**：`apps/admin-console/backend/api/domains.py:743` 把 `row.get("abstract_clean")` 直接赋给 `summary_zh` 字段返回前端，变成"英文 abstract 冒充中文 summary"。

本 spec 修复两点。

## 2. Non-goals

- **不**触发 summary_zh 真实回填（W13-V1 单独跑 dogfood）
- **不**改 `abstract_translator.py` 翻译逻辑或四段式结构（W13 之外另议）
- **不**改 chat.py 路径（chat 走 retrieval，本 spec 不动 retrieval._PAPER_OUTPUT_FIELDS；如有缺失另起 spec）
- **不**改 V018 schema

## 3. User-visible behavior

| 场景 | 之前 | 之后 |
|---|---|---|
| `GET /api/domains/papers/{paper_id}` 返回值的 `summary_zh` 字段 | 永远是英文 abstract_clean | DB 里 `p.summary_zh IS NOT NULL` 时返回真实中文摘要；为 NULL 时字段为 `null`（前端可降级展示 abstract_clean） |
| `GET /api/domains/papers` 列表 | 同上 | 同上 |
| 现已 backfill 完成的 paper（W13-V1 之后） | 看到 abstract_clean | 看到中文摘要 |

接口契约：`summary_zh: str | None`（PRD §4.1 标"必填"，但 backfill 是渐进的，过渡期允许 None）。

## 4. Affected paths

```
修改：
  apps/admin-console/backend/api/domains.py
    PAPER_SELECT_SQL（:219-243）→ 加 p.summary_zh
    paper DTO（:743 附近 _build_paper_dto / list 路径）→ 真读 summary_zh，不再用 abstract_clean 冒充

新增：
  apps/admin-console/tests/test_data_api_paper_v011.py
    （已存在；新增 ≥ 2 个用例：summary_zh 非空 / summary_zh 为 None 时的字段值）
```

## 5. Interface contract

DTO（PaperDetail）：

```python
class PaperDetail(BaseModel):
    paper_id: str
    title_clean: str | None
    abstract_clean: str | None        # 英文，原始
    summary_zh: str | None             # ← 真实从 p.summary_zh 列读出
    pdf_url: str | None                # W12-3 已暴露
    # ...其余字段保持不变
```

SQL：`PAPER_SELECT_SQL` 列表加入 `p.summary_zh`。

## 6. Invariants

- `summary_zh` 为 None 时不抛错，前端可继续渲染 abstract_clean
- `abstract_clean` 不再被复用为 summary_zh 占位
- 现有其它字段（pdf_url / authors_display / publication_year）行为不变
- 已合 V018（已存在）；本 spec 不改 schema

## 7. Edge cases

| 场景 | 处理 |
|---|---|
| paper 行无 V018 列（DB 旧） | 不会发生；CI 跑 alembic upgrade head 后所有库都有 V018 |
| summary_zh 是空字符串 `""` | 视为有值返回（不要在 API 层 coerce 成 None；下游可见原始） |
| summary_zh 含极长文本（4 段式 JSON 拼一起） | 不截断，前端自行处理 |

## 8. Validation

```bash
cd apps/admin-console
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
  uv run pytest tests/test_data_api_paper_v011.py -n0 --no-cov -v

# 既有 paper / domain 测试不退化
uv run pytest tests/ -k "paper or domain" -n0 --no-cov
```

## 9. Done criteria

1. ✅ `PAPER_SELECT_SQL` 含 `p.summary_zh`
2. ✅ DTO 真实读 `row["summary_zh"]`，不再回退到 abstract_clean
3. ✅ 新增 ≥ 2 单测覆盖 summary_zh 有值/无值
4. ✅ 既有 paper-relevant tests 全过
5. ✅ ruff 通过

## 10. Open questions（建议默认决策）

| 问题 | 默认决策 | 备注 |
|---|---|---|
| 前端是否需要 `summary_zh_status` 字段（标"中文摘要待生成"） | 不加 | 前端按 None 展示"暂无中文摘要"即可 |
| 是否同时把 `abstract_translation_status` 暴露 | 不暴露 | 内部字段，只对 backfill 脚本有意义 |
| 4 段式 JSON 还是单段 string | 与 W12-6 一致：单段 string；4 段式由后续 spec 推进 | 见整体差距报告 P2 |
