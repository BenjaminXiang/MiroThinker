# Design: alias passthrough and local foothold

## Where the decision lives today

`_has_local_scope_foothold(query)` (`knowledge_serving_isolated.py:451`) is
purely lexical: domain inference / topic markers / three name-shape
extractors. Its call site decides `lanes = (exact, structured, lexical,
vector, web)` vs `("web",)` and also gates the enumeration window widening.

## The reuse point (the data-driven name-shape decision)

The read side already owns exactly the needed matcher:

- `knowledge_read_isolated._create_audited_lookup_view(bundle)` builds the
  audited lookup view: public entries plus a `name_index` over
  `_entity_name_forms(domain, display_terms)` — display name + aliases +
  derived forms (legal-suffix strip, industry-word strip, city-prefix strip),
  so `深圳国先中心 → 国先中心` and `深圳国际先进技术应用推进中心 →
  国际先进技术应用推进中心`.
- `_entity_link_entry_indexes(index, query_text)` links entry positions whose
  name form appears in the normalized query — the SAME matcher the exact lane
  already runs (`_entity_link_indexes_for_view`). Round 47 proves the linkage:
  `国先中心（深圳）是什么公司` reached exact 2 + vector 16 once the lanes ran.

Against the three round-47 asks, both failing forms contain a generated form;
the missing piece is only that planning never consults this index.

## Wiring

1. `serving_pack_loader.create_local_name_linker(release_bundle)` — a lazy,
   memoized `query -> bool` closure over `_create_audited_lookup_view` +
   `_entity_link_indexes_for_view`. Built on first use only, so a query whose
   lexical checks already pass never pays it; any failure degrades to `False`
   (old routing) and never fails a turn.
2. Runner (`s12a/complete_candidate_runner.py`): `_serve()` composes the
   linker from `handoff.release_bundle` and passes it into
   `load_inputs(config, name_linker=...)`; when no linker can be composed the
   call keeps its old single-argument shape (old call sites unchanged).
3. `knowledge_serving_isolated.load_recorded_serving_inputs(..., name_linker=None)`
   → `_proposal_provider(..., name_linker=...)` → `_has_local_scope_foothold(
   query, name_linker=...)`: the linker check runs LAST (after domain /
   markers / extractors) and only while `CANONICAL_V2_ALIAS_FOOTHOLD` is not
   switched off.
4. `managed_config`: `serving.alias_foothold → CANONICAL_V2_ALIAS_FOOTHOLD`.

## Why not layers ②/③ from the proposal (for now)

With the foothold given, the local lanes run and — per round 47 — exact and
vector already reach the entity from the raw query form, so alias→canonical
rewriting is only added if the E2E shows a form the lanes miss (decide at T7
from evidence). The web-0 local fallback is likewise subsumed: "web 0 results
and pack-known name" can only occur with no foothold, and pack-known names now
always hold one.

## Debt / notes

- One extra `_create_audited_lookup_view` per process, lazily paid on the
  first name-shaped query. The read side builds its own view at boot; sharing
  one instance is a possible later micro-optimisation, not v1.
- Boot cost: zero added (lazy). First affected query: one-time view build
  (documents come from the process-wide bound-document cache), then memoized.
- The runner file lives outside the sealed `canonical_v2` package; the three
  module edits are sealed → T8 reseal applies to them plus the runner file
  being copied to the served tree as usual.
