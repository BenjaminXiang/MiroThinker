# Proposal: anchor-standalone-professor-relations

Human doc: `docs/plans/2026-10-23-professor-standalone-answer-fix.md`.

## Why

A single-turn query that names a professor and asks for a relation
(`丁文伯创办的公司是哪家`, `丁文伯有哪些专利`) does not bind the named person
to the pack entity. The planner runs only the asked domain's free-text lanes
and the web lane; the relationship lane never executes because
`_relationship_path` requires `displayed_entity_ids` from a prior turn. The
answer then falls back to web lookalikes (`丁文波`, `广州文伯化工`,
`丁文博`, `丁文胜`) or a false "no records" conclusion. The same relation
answers correctly when the person was displayed in the previous turn
(`介绍清华的丁文伯` → `他参与创立了哪些企业`), which isolates the defect to
standalone anchoring.

## What Changes

1. Add a pack-backed entity resolver that maps a query's exact name form to one
   professor/company canonical id (longest name form; ambiguous multi-owner
   names return None).
2. Anchor the single-turn planning request in the chat layer: when a request has
   no displayed entity and the query carries a relation intent, resolve the
   named entity and pass it as the request's displayed anchor.
   - professor + 创办/创立/创业/公司/企业 → `professor_company_role`
   - professor + 论文/研究成果/… → `professor_authored_paper`
   - company + 教授/老师/学者/创始人/联合创始人 → `professor_company_role`
3. Add a deterministic local company→patent count path: the relationship lane
   caps candidates at the plan window, so a count query cannot read the total
   from the lane; the counter reads the full patent projection and the chat
   answers the count directly with the company's local citation card.
4. No change to retrieval scoring, answer synthesis, or web provider selection.
   The anchored name also feeds the existing web subject-consistency gate, so
   near-name web results are rejected instead of answered.

## Non-goals

- Professor→patent traversal (no such relationship type in the pack).
- Web provider quality (Bocha lookalike recall is tracked separately).
- Multi-owner ambiguous names: the resolver declines to anchor.
