# Proposal: fix-paper-topic-query-classification

> Behavior-affecting. Amends `agentic-rag-retrieval` (query-classification routing into paper
> topic retrieval). Grounded in the paper-retrievability baseline (2026-07-09,
> `.agents/runs/paper-retrievability-baseline/baseline-summary.md`): Type4 (topic→paper) recall
> was **0/4** because paper-topic queries were mis-routed to `unknown`.

## Why

The paper-retrievability baseline measured Type4 (topic→paper) e2e recall at **0/4**: queries
like "关于perovskite钙钛矿材料的论文有哪些" and "关于联邦学习federated learning的最新论文"
classified as **`unknown`** and triggered **no retrieval** — even though 284 perovskite and 145
federated-learning `ready` papers exist and ARE vector-retrievable.

Root cause (code-confirmed via direct `_classify_query_by_rules` diagnosis): the rule classifier
in `backend/api/chat.py` over-fired its **exact-paper deterministic rule** on these queries.
- The B paper-topic rule (`chat.py:637`) required the query to **end in 论文/文章/paper**
  (`$`-anchored), so "…论文有哪些" / "…的最新论文" did not match.
- The exact-paper rule (`chat.py:658`) fires on `("论文" in q) AND (an 8+ char ASCII run in q)`.
  Topic queries with an English term (perovskite / federated learning) matched → classified as
  type **A** with `name`=the whole query → the A branch exact-title-looked-up a non-existent
  paper → fell through to `unknown`.

Contrast: "钙钛矿太阳能电池方向的论文" (ends in 论文) correctly classified B/paper. So the B
rule's ending-anchor was the gap, and the exact-paper rule filled it wrongly.

This is a query-classification A-G defect (CLAUDE.md §5 invariant): a topic-search intent was
routed to neither B (topic search) nor a valid A (exact entity), but to `unknown`.

## What Changes

1. **MODIFY** the B paper-topic deterministic rule (`chat.py:637`) to also match topic-search
   intent that does NOT end in 论文: a query mentioning 论文/文章/paper AND a search/topic marker
   (关于/有关/哪些/有哪些/有什么/有没有/找/查找/搜索/检索/推荐/最新/最近/相关), **guarded** by:
   - NOT a bare English title (`^[A-Za-z][A-Za-z0-9\s:,\-./]{15,}$` — left to the english-title
     rule at `chat.py:647`), and
   - NOT entity-anchored (no 教授/研究员/创始人/企业家/公司/企业 — left to the professor/company
     rules).
   Such a query SHALL classify as type **B**, `target_domain="paper"` → routes to
   `B_paper_topic_search` → `_lookup_domain_by_topic(domain="paper", …)`.
2. The exact-paper rule (`chat.py:658`) is unchanged; it no longer over-fires on these queries
   because the broadened B rule precedes it and matches first.

### Non-goals
- **Topic-recall measurement quality**: the baseline's Type4 `required` tokens (specific notable
  paper titles) remain an imperfect topic-recall instrument (substring topic-recall is weak +
  the system returns top-vector-similar, not top-cited). The classification **gate** is fixed
  here; refining the topic-recall measure is a separate follow-up.
- **Type2 (professor→paper)** and **Type3 (company→paper, structurally dead)**: separate gaps,
  untouched.

## Capabilities

### Modified
- `agentic-rag-retrieval`: a paper-topic-search query SHALL route to paper topic retrieval
  (`B_paper_topic_search`), not be over-classified as exact-paper (A) or fall to `unknown`.
  (Capability in-flight via `fix-chat-retrieval-recall-gaps`; this change amends its routing
  requirements.)

## Impact

- **Retrieval**: qid109/110 `unknown` → `B_paper_topic_search`, each returning 8 relevant papers
  (perovskite / federated-learning) where previously zero. Verified by direct classifier call +
  live `/api/chat` curl.
- **Code**: `backend/api/chat.py:637` — one rule broadened (added topic-search intent clause +
  two guards). No other rule, no schema, no migration, no persisted column.
- **Regression**: zero. The 21 other oracle cases (professor/company/paper-profile/patent +
  Type1 title-self + Type2 professor→paper) classify identically before/after (deterministic
  test + e2e `eval_recall_chat.py` 21/43 unchanged).
- **Invariant**: A-G classification semantics preserved — the fix RESTORES intended B-topic
  routing that the exact-paper rule was violating; it does not add a new type or change any
  existing route's destination for non-topic queries.
