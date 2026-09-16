"""Multi-value enrichment (G2b/G5): design notes for the supplementary_values change.

## Problem
Multiple valid assertions for the same field ("互联网"/"人工智能"/"科技企业")
are all correct at different granularities. The current pipeline picks one
(decision) and the rest vanish from the search surface (vector + lexical),
narrowing recall.

## Design (3 changes, no Pydantic model modifications)

### Change 1: compute supplementary values (new function in knowledge_build_isolated.py)

```python
def _supplementary_field_values(
    *,
    identity_result: IdentityResolutionResult,
    decision_result: DecisionBatchResult,
) -> dict[str, dict[str, list[str]]]:
    # canonical_id -> {field_path -> [non-selected values]}
    canonical_by_source = {
        a.source_identity_id: a.canonical_identity_id
        for a in identity_result.source_identity_assignments
    }
    selected: dict[tuple[str, str], str] = {}
    for cf in decision_result.current_fields:
        if isinstance(cf.value, str) and cf.value.strip():
            selected[(cf.canonical_identity_id, cf.field_path)] = cf.value.strip()

    supp: dict[str, dict[str, list[str]]] = {}
    for assertion in decision_result.field_assertions:
        canonical_id = canonical_by_source.get(assertion.source_identity_id)
        if canonical_id is None:
            continue
        value = assertion.value
        if not isinstance(value, str) or not value.strip():
            continue
        key = (canonical_id, assertion.field_path)
        if key in selected and value.strip() != selected[key]:
            supp.setdefault(canonical_id, {}).setdefault(
                assertion.field_path, []
            )
            if value.strip() not in supp[canonical_id][assertion.field_path]:
                supp[canonical_id][assertion.field_path].append(value.strip())
    return supp
```

### Change 2: enrich embedded_content (index_projection.py)

In `_vector_points()`, after calling `_public_embedded_content(projection, view)`:

```python
content_json = json.loads(content)
supp = supplementary.get(projection.canonical_identity_id)
if supp:
    content_json["_supplementary"] = supp
    content = json.dumps(content_json, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
```

This adds the supplementary values to the vector text without changing the
projection model. The `_supplementary` key is read by the vector lane as
plain text (JSON is embedded as text), so "互联网" appears in the vector.

### Change 3: enrich lookup_content for lexical matching (index_projection.py)

In `_lookup_documents()`, similarly inject `_supplementary` into the
lookup_content JSON before hashing:

```python
content_dict = json.loads(content)
supp = supplementary.get(projection.canonical_identity_id)
if supp:
    content_dict["_supplementary"] = supp
    content = json.dumps(content_dict, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
```

The serving-side `_projection_terms()` in knowledge_read_isolated.py reads
`lookup_content` and extracts `content_terms` — the `_supplementary` values
will automatically appear as searchable terms for the lexical lane because
`_projection_terms` recursively visits all string values in the lookup dict.

## Verification plan
1. Conservation replay with enrichment: check supplementary values appear
   in embedded_content and lookup_content for the sample
2. Golden set: "互联网公司" type queries should now recall ByteDance via
   vector lane
3. No regression: existing golden set queries unchanged

## Data flow (unchanged parts in ✅)
```
Assertions (all) ✅ → Decision (select one) ✅ → Current fields ✅
                                                   ↓
Supplementary (NEW): non-selected values ──→ embedded_content (vector)
                                              → lookup_content (lexical)
```
"""
