---
title: "W11-6: 多域 entity stack（共享 SessionEntity LRU 5）"
date: 2026-05-02
owner: claude
status: ready-for-codex
audience: codex；claude review
wave: Wave 11
plan: docs/plans/2026-04-28-portfolio-update-wave-9-to-13.md
related_specs:
  - .agents/specs/2026-05-02-w11-5-chat-session-postgres.md
prd_anchor: docs/Multi-turn-Context-Manager-Design.md
---

# W11-6: 多域 entity stack

## 1. Goal

W11-5 SessionContext.entities 已支持 SessionEntity（kind=professor / paper / company / patent），但当前 chat.py 只在 A 类型 prof query 时 push entity。其他域（paper / company / patent）单实体 query 完成后未推入 stack → C 类型跨域跳转（"这家公司的专利"）找不到 latest company。

**本 spec**：A 类型 4 域 handler 都 push entity；pronoun 解析支持 4 域。

## 2. Non-goals

- **不**改 entity stack 大小（保留 5）
- **不**改 entity LRU 算法
- **不**做 click-only push（user 锁定 query 命中即 push）
- **不**改 W11-5 schema

## 3. User-visible behavior

| query | entity stack 变化 |
|---|---|
| "丁文伯" | push (professor, PROF-XXX, "丁文伯") |
| "无界智航" | push (company, COMP-XXX, "无界智航") |
| "他的论文"（C followup） | 用 latest professor entity |
| "这家公司的专利"（C followup） | 用 latest company entity |
| "Robot Force Control" 论文 | push (paper, PAPER-XXX, "Robot...") |
| "CN12345 专利" | push (patent, PAT-XXX, "CN12345") |

## 4. Affected paths

```
修改：
  apps/admin-console/backend/api/chat.py
    所有 A 类型 handler （professor / paper / company / patent profile）
      → 在返 response 前 session.push_entity(SessionEntity(kind, id, label))
    _SESSION_PRONOUNS_RE 加 "这家公司" / "这本论文" / "这件专利" / "该专利" pattern
    SessionContext.latest_for(domain) 方法：返 stack 中最新的指定域 entity
    _rewrite_query_with_context 改：根据 pronoun 类型选 latest_for(domain)

CREATE / MODIFY:
  apps/admin-console/tests/test_chat_multi_domain_entity_stack.py
    test_company_query_pushes_entity
    test_patent_query_pushes_entity  
    test_paper_query_pushes_entity
    test_pronoun_这家公司_resolves_to_latest_company
    test_pronoun_他_resolves_to_latest_professor
    test_stack_lru_5_eviction_across_domains
```

## 5. Pronoun → domain mapping

```python
_PRONOUN_DOMAIN_MAP = {
    "他": "professor", "她": "professor",
    "这位教授": "professor", "该教授": "professor",
    "上面那位": "professor",
    "这家公司": "company", "该公司": "company",
    "这件专利": "patent", "该专利": "patent",
    "这篇论文": "paper", "这本论文": "paper", "该论文": "paper",
}
```

## 6. Invariants

- entities deque maxlen 5（W11-5 已锁）
- push_entity 去重（同 kind+id 不重复）
- LRU 跨域共享：5 = 总 entities (混合 domain)
- pronoun 解析未命中 → query 不改写（保留原行为）

## 7. Edge cases

| 场景 | 处理 |
|---|---|
| 无 prior entity 的某域 + 该域 pronoun | 不改写；handler 报 "未识别引用，请提供具体名称" |
| 同名教授多个 push | last push 胜（按时间） |
| 跨域 LRU 挤压 | 5 个 hot entities，按时间淘汰最旧 |
| 同名同 domain（同一 prof 反复查） | push_entity 已去重，仅更新位置 |

## 8. Validation

```bash
uv run pytest apps/admin-console/tests/test_chat_multi_domain_entity_stack.py \
              apps/admin-console/tests/test_chat_v1.py \
              apps/admin-console/tests/test_chat_session_persistence.py \
              -v
```

## 9. Done criteria

1. ✅ 4 域 A handler push entity
2. ✅ 4 域 pronoun 解析覆盖
3. ✅ 单测覆盖 push / lru / pronoun 解析
4. ✅ 既有 chat tests 不退化

## 10. Open questions（已锁）

| 问题 | 决策 |
|---|---|
| Stack 模型 | 4 域共享 SessionEntity stack (LRU 5) |
| Promote 规则 | query 命中即 push（无需 click） |
| 跨域 LRU | 5 总（共享）|
