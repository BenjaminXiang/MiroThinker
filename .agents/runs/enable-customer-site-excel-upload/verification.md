# Verification: enable-customer-site-excel-upload

Date: 2026-10-22 (Asia/Shanghai)
Customer host: `100.64.0.96` / `/root/deploy/fullstack-v2`

## 1. Code

- `backend/api/canonical_v2_manual_recall.py`: `.xlsx` allowed; `_xlsx_text()` flattens the active
  sheet (`header: value` per row, 24k cap); preview returns `row_count`.
- `backend/static/browse.html`: file input accepts `.xlsx`.
- Test `test_preview_xlsx_flattens_rows` passes; manual recall API suite 15 passed.
- Experimental exact-match boost and forced manual-slot reservation were **reverted** after they
  did not change the answer; the customer files were restored from `.bak-boost-*` /
  `.bak-manualslot-*`.

## 2. Live upload

- Preview `星尘机器人材料.xlsx`: HTTP 200, `media_kind=xlsx`, `row_count=2`, `chunk_count=1`,
  227 chars.
- Confirm: HTTP 201, `doc_id=doc-1fb84e3040a20575`, `chunk_count=1`.
- Second unique workbook (蓝鲸九号 / BLUEWHALE-9000): HTTP 201,
  `doc_id=doc-a3bf8efa0e58e8cb`, `chunk_count=1`.
- `manual-recall.json` points: 1 → 2 → 3, all 1024-dim active company points.

## 3. Chat recall diagnosis

- Query `负载 25kg 的 BLUEWHALE-9000 协作机械臂型号是什么？`
  - Diagnostic logs show `manual_recall_filter active=3 domains=[company] matched=3`;
    `manual_recall_append provider=yes eligible=3 appended=3 candidates=131`;
    all-domain lane `candidates=19`.
  - Manual top cosine score `0.8754`; with a forced 2-slot reservation the lane still returns 16
    candidates, but the final `retrieval_done` and answer do not cite any manual evidence.
  - The answer says `BLUEWHALE-9000` has no public record; citations are release company + web only.
- Conclusion: the upload reaches the manual recall store and the vector lane appends it, but the
  **answer evidence/sufficiency retention** drops manual evidence. This needs a dedicated
  upload-evidence lane or an answer-context injection; it is not a score/threshold problem.

## 4. Service

- `systemctl is-active = active`, `/api/health` 200 after the final restart.
- Experimental lane changes are reverted; the final running process is the clean baseline plus the
  XLSX upload endpoint.

## 5. Structure-first ingest (2026-10-22)

- `excel_structure.analyze_workbook` detects company/professor/patent/paper headers; unit tests
  cover all four and unmatched-column alignment.
- `POST /company-documents/structured` live results:
  - company workbook: `domain=company`, `confidence=high`, 2 rows inserted into `company`
    (`company-upload-*`, `needs_review`, unique credit codes);
  - professor workbook: 1 row inserted into `professor`, 1 `professor_seed` row;
  - paper workbook: 1 row inserted into `paper`;
  - patent workbook: 1 row inserted into `patent`, `patent_type='发明'` after normalization.
- All test rows and test recall documents were cleaned up (`company_test=0`, `professor_test=0`,
  `patent_test=0`, `paper_test=0`; 8 test docs reverted; `manual-recall.json` 9 points / 1 active).
- `test_excel_structure.py` + manual recall API: 18 passed; ruff clean.

## 6. Known test failures (unrelated)

- `test_runner_serve_manual_recall_store_fails_open` assumes the admin backend module is not
  importable; in this worktree it is importable.
- `test_release_bound_vector_validator_exempts_manual_traces` fails in the existing validator
  fixture; not touched by the XLSX upload change.

## 7. Recall fix and end-to-end closure (2026-10-23)

### Root cause (two answer-side drops, not scoring)

1. `knowledge_read._EphemeralKnowledgeRead.execute` trimmed the fused candidate list with
   `ordered[:candidate_limit]`. A lexical lane with 16 hits filled the window; the manual
   candidate scored **0.6592 / 0.7592** against a 16th-place release score of **0.4555 / 0.6185**,
   so it was still trimmed before evidence existed.
2. `knowledge_serving_isolated._answer_selector` filtered eligible items: the focused-entity
   branch kept only `current_web` + bound relationship evidence, and the preferred-object branch
   kept only exact/structured/lexical object ids. Manual items were in neither set, so even a
   manual item that reached `EvidenceSet.items` could not become a claim or citation.

### Fix

- `knowledge_read.py`: `MANUAL_RECALL_MIN_SIMILARITY = 0.52`;
  `_protect_manual_candidates` reserves up to two candidate-window slots for
  `source_authority="manual_upload"` candidates at or above the floor, replacing the
  lowest-ranked non-manual entry. Weak uploads never displace release evidence.
- `knowledge_serving_isolated.py`: eligible-item construction merges floor-passing manual items
  at the front, so they survive the focused-entity and preferred-object filters and land inside
  the three-local-claim window.

### Tests (local worktree, `apps/miroflow-agent`)

New (5):

- `test_selector_keeps_manual_upload_claim_on_focused_company_lookup`
- `test_selector_keeps_manual_upload_claim_when_lexical_objects_preferred`
- `test_selector_does_not_promote_low_score_manual_upload`
- `test_answer_candidate_window_reserves_manual_upload_slot`
- `test_answer_candidate_window_keeps_weak_manual_upload_out`

Results:

- `test_knowledge_serving_isolated.py` + `test_knowledge_read_retrieval_fusion_contract.py` +
  `test_manual_recall_points.py`: **322 passed, 1 failed**. The failure is the pre-existing
  `test_release_bound_vector_validator_exempts_manual_traces`: the validator starts with an
  unconditional `return` (disabled 2026-08-30), so its negative control cannot raise. Unrelated
  to this change; left untouched.
- Answer/citation suites (`test_local_citation_floor.py`, `test_knowledge_answer_atomic_green_contract.py`,
  `test_knowledge_answer_grounding_contract.py`, `test_knowledge_read_atomic_green_contract.py`,
  `test_knowledge_read_interface.py`): **18 passed**.

### Live end-to-end (customer site, PID 3913401, `/api/health` 200)

Documents were uploaded through `POST /api/canonical-v2/admin/company-documents/structured`
and cited via `local-source-<sha256("local:manual-upload:<doc_id>")[:16]>`.

1. Pre-restart document `doc-924835eccf8aa044` (STRICT-9000 / 30kg), after the fix:
   - product+attribute → token present, citation `local-source-57861b25eafa73e0`;
   - product-only → “额定负载为 30kg”, same citation;
   - company-name → profile from the workbook, same citation;
   - unrelated (“深圳有哪些机器人公司？”) → no upload citation;
   - after revert → “no public information”, upload citation gone (causality).
2. Post-restart fresh document `doc-c831b705898d0e27` (NOVA-7700 / 18kg):
   - company-name and product-only both answer with the token and cite
     `local-source-3947662581cc8a44`;
   - reverted after the check.
3. Cleanup: both test documents reverted; `company-upload-*` rows deleted
   (`company` back to **7089**); `manual-recall.json` **15 points / 1 active**
   (the pre-existing real point).

### Service

- `systemctl is-active = active`, `/api/health` 200 after loading the fix.
- Rollback: restore the `.bak-manualquery-20261023-0032` copies of the two modules and restart.
