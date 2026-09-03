# Verification contract: local-citation-floor (Stage0-G1)

Written BEFORE production edits (task 1). RED evidence comes from this
contract + the OpenSpec proposal.

## Behavior under test

B1 (selector floor). A single-turn query whose normalized text names a
canonical entity (display_name == search view, or display_name ⊂ query with
len ≥ 8), with the entity's local evidence retained in the evidence set but
carrying NO `claim_binding`, MUST still produce at least one answer claim
whose `evidence_ids` reference that local item.

B2 (mapping floor). A handle-bound citation over local evidence that yields
no official URL MUST still appear as a public citation card with
`type = handle.domain`, `label = handle.display_name`, `url = None`.

B3 (non-regression). Queries that already cite local evidence keep their
cards (新濠天地-class: official URL card). Web-only enumeration answers keep
web cards. No claim is synthesized for entities the query does NOT name.

## Test levels (per development-methodology: RAG answer/citation work needs
more than unit GREEN)

L1 unit (agent): `test_local_citation_floor.py`
  - case a: named query + binding-less local item + binding-ful web item ⇒
    claims include a local-evidence claim (floor) — RED before fix.
  - case b: control — named query + binding-ful local item ⇒ unchanged
    behavior (claim from main loop, exactly one per object; floor adds none).
  - case c: non-named query (topic query) + binding-less local item ⇒ NO
    floor claim (floor does not fire).

L2 unit (admin): `test_canonical_v2_local_citation_cards.py`
  - case a: handle-bound local citation, snippet without website ⇒ card with
    url=None — RED before fix.
  - case b: same handle cited twice ⇒ one card (dedupe).
  - case c: official-URL local citation ⇒ card with that URL (unchanged).

L3 e2e (serving): restart 18188 on fixed code; rerun
`stage0_golden_attribution.py` (same seed, same golden set). Expected deltas:
  - 点名/company LOCAL_DROPPED (5) → PASS or EXACT_HIT (≥4 flip)
  - 点名/paper + 点名-池外/paper: in-pack rows gain local cards; pool-only
    rows stay web-only (honest — target absent from pack)
  - 属性/professor: unchanged unless mapping floor surfaces cards (may flip
    1-2 via existing professor citations)
  - Three-metric summary recorded in the log entry as the acceptance number.

L4 regression: focused pytest on answer-selector closure + chat http adapter
tests; the 7-session replay gate is NOT in this slice's scope (dev-line
serving only; customer-test hot update is a separate release step).

## Fix surface

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`
  (`_answer_selector.select` — floor claims)
- `apps/admin-console/backend/services/canonical_v2_chat.py`
  (`_public_citations` — url-less local cards)

## Rollback

Single-commit revert; serving restart with the prior code path restores
baseline (golden set re-run confirms 41% named-entity baseline).
