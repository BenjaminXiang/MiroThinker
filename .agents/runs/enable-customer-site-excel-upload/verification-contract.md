# Verification contract — uploaded workbook recall in chat answers

Slice: `enable-customer-site-excel-upload`, task 1.9
("Verify a chat query can recall uploaded content").

## Behaviour under test

An operator-uploaded workbook is written to the manual-recall sidecar and its
embedding is appended to the vector lane. The answer selector must treat that
operator-attested evidence as first-class local evidence: when the uploaded
document matches the query, the answer's claim set and citations must include
it even when

1. the query is a focused entity lookup (company name alone), where the current
   selector keeps only `current_web` + relationship items; and
2. the query has lexical/preferred local objects, where the current selector
   keeps only items whose `object_id` is in `preferred_objects`.

A weak manual match must not be promoted: the manual item is only eligible for
a claim when its similarity score is at or above the sidecar floor.

## RED artifacts (must fail before the production edit)

`apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`

- `test_selector_keeps_manual_upload_claim_on_focused_company_lookup`
- `test_selector_keeps_manual_upload_claim_when_lexical_objects_preferred`
- `test_selector_does_not_promote_low_score_manual_upload`

The first two fail on the current selector because manual items are filtered
out; the third locks the relevance floor.

## GREEN evidence required

1. The three tests above pass.
2. Pre-existing selector/serving suites stay green:
   `uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py -q`
   and `uv run pytest tests/canonical_v2/test_manual_recall_points.py -q`.
3. Live customer-site end-to-end:
   - upload a unique company workbook through
     `POST /api/canonical-v2/admin/company-documents/structured`;
   - ask all three query shapes (product + attribute, product alone, company
     name alone);
   - each answer must contain the unique product token and carry a citation
     whose id equals `local-source-<sha256("local:manual-upload:<doc_id>")[..16]>`;
   - revert the document and confirm the token no longer appears.

## Out of scope

- Lane scoring, truncation, or rerank changes.
- Release-index evidence and web-lane behaviour.
- Admin UI changes.
