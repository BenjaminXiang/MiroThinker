# Proposal: local-citation-floor (Stage0-G1)

> Grounded in `docs/plans/2026-09-03-stage0-hit-rate-baseline.md` (G1: 14/34
> golden-set queries recalled the target locally but cited only web sources).
> Amends the serving answer-selection and citation-mapping behavior.

## Why

The goal function (user-ruled 2026-09-03) is 可达 × 诚实分级: a query that
names a real in-pack entity must cite it locally. Today it does not:

1. **Answer layer** — `_answer_selector.select`
   (`knowledge_serving_isolated.py`) only promotes a local evidence item to a
   claim when `item.claim_binding is not None`. Local lookup/lexical items of
   a named entity frequently carry no field binding, so the claim set degrades
   to web-only (verified end-to-end: 飞象 turn — lexical retained=1,
   answer_subject = the local company, citation_count=1 web patent page).
   The attributed fallback (`knowledge_answer.py` `_attributed` filter) is
   web-only by construction (`source_nature in {"current_web","supplemental_web"}`).
2. **Mapping layer** — `CanonicalV2ChatAdapter._public_citations`
   (`canonical_v2_chat.py`) drops a handle-bound local citation card entirely
   when `_official_evidence_url` finds no whitelisted field (company
   `website`, professor `homepage`, paper `doi`...). Entities without those
   profile fields can never surface a local card even when their claims exist.

## What Changes

1. **Selector floor** (`knowledge_serving_isolated.py::_answer_selector`):
   for each object in `exact_named_objects` (query names the entity) that has
   NO local claim after the main loop, synthesize exactly one floor claim
   from its best local item (text = `_semantic_text`, subject = the canonical
   handle, predicate = `entity_profile`, value = display name, evidence =
   that item). Floor claims stay inside `local_claim_limit`.
2. **Mapping floor** (`canonical_v2_chat.py::_public_citations`): a
   handle-bound citation whose evidence is local and yields no official URL
   still emits a card (`type = handle.domain`, `label = display_name`,
   `url = None`), deduped per handle, before web-only cards. `ChatCitation.url`
   is already `str | None`; `chat.html` already renders url-less cards as
   non-link rows.

## Impact

- 点名命中 citation leg: golden-set company/paper LOCAL_DROPPED rows flip to
  PASS (local card present). Web citations still supplement; local cards
  order first.
- No retrieval/planner change; no pack change; no schema change.
- Non-goal: fixing G2 (exact-lane name matching), G3 (relationship type
  break), aliases, or multi-turn anchoring.
- Risk: floor claims for entities whose local profile is thin — the card
  asserts existence + archive provenance, not field completeness (honest
  tiering is preserved by the claim's semantic text).
