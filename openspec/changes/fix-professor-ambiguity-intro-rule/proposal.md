# Proposal: fix-professor-ambiguity-intro-rule

> **Status correction (2026-07-10): Candidate.** The local ambiguity guard remains implemented
> evidence, but Q004/Q017 still require normalized-name, domain, endpoint, target-ID, citation, and
> semantic proof. Re-acceptance requires Slices A-C of
> `openspec/changes/close-retrieval-generation-contract/`. A type-only 100-case classifier result is
> insufficient for acceptance; do not archive this change before the linked scenarios pass. After
> they pass, accept this record only as superseded history and archive with
> `openspec archive fix-professor-ambiguity-intro-rule --skip-specs`, recording
> `superseded_by=close-retrieval-generation-contract`; default spec migration is forbidden.
>
> Behavior-affecting. Amends `agentic-rag-retrieval` (the ambiguous-intro classification rule).
> Pre-existing bug surfaced by the 100-case classifier benchmark (Q004/Q017), found while running
> regression for the paper-retrievability Type4 fix.

## Why

The 100-case deterministic classifier benchmark had two pre-existing failures:
- Q004 "南方科技大学张巍教授是谁" — expected **A**, classified **G**.
- Q017 "港中大深圳吴佳教授是谁" — expected **A**, classified **G**.

Root cause: the ambiguous-intro deterministic rule (`chat.py`, `_classify_query_by_rules`)
`re.search(r"^(介绍)?\s*[一-鿿A-Za-z0-9]{2,12}\s*(是谁|的相关信息)$", q)` matched these
queries (the institution+name+title string is ≤12 chars and ends in 是谁) → type **G** (ambiguous,
asking for clarification). But a name carrying an academic title (教授/研究员/博导/院士) is a
**definite** person, not an ambiguity — it should route to type **A** (professor profile) via the
professor-name extraction rule. The G result also mis-set `target_domain` to company (len(name) > 3).

## What Changes

1. **MODIFY** the ambiguous-intro rule to add a guard: it SHALL NOT fire when the query contains
   an academic title (`教授|研究员|博导|院士`). Such queries fall through to the professor-name
   extraction rule → type A, `target_domain="professor"`.

### Non-goals
- The `的相关信息` variant and title-less "X是谁" queries keep their existing G behavior (genuinely
  ambiguous). Only title-bearing names are re-routed to A.

## Capabilities

### Modified
- `agentic-rag-retrieval`: the ambiguous-intro classification rule SHALL NOT fire for names
  carrying an academic title; those route to A (professor). (Capability in-flight via
  `fix-chat-retrieval-recall-gaps`.)

## Impact

- **Classification**: Q004/Q017 G → A/professor. The 100-case deterministic classifier benchmark
  goes from 2 pre-existing failures to **all 100 passing**.
- **Code**: `backend/api/chat.py` — one guard added to the ambiguous-intro rule condition. No
  other rule, schema, migration, or persisted column.
- **Regression**: zero. Title-less ambiguous queries ("张三是谁") and `的相关信息` queries keep G;
  verified by `tests/test_paper_retrievability.py` (untitled-name-still-G) + the full benchmark.
- **Invariant**: A-G classification semantics preserved — restores intended A routing that the
  ambiguous-intro rule was violating for titled names.

The 100-case result above is retained as a historical deterministic-classifier result, not an
end-to-end entity-resolution or answer-quality acceptance result.
