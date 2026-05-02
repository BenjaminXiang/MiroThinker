# W13 Batch A Codex Report

Date: 2026-05-02
Owner: Codex

## Summary

| Slice | Status | Summary |
|---|---|---|
| W13-5 | Done | Added professor `h_index`, `citation_count`, `paper_count` to retrieval output fields and asserted metadata propagation. |
| W13-1 | Done | `PAPER_SELECT_SQL` now selects `p.summary_zh`; paper domain DTO returns the DB value instead of `abstract_clean`. |
| W13-2 | BLOCKED | Stopped before code changes: locked schema does not match spec writer contract and handoff forbids schema edits. |
| W13-3 | BLOCKED | Stopped before code changes: locked patent/relation schema lacks required columns and handoff forbids schema edits. |
| W13-4 | Done | Added C-type cross-domain handler using `RetrievalService.get_related_objects`, session source entity selection, target push, clarification, and A fallback. |

## Changed Files

| File | Slice | +/- | Reason |
|---|---:|---:|---|
| `apps/miroflow-agent/src/data_agents/service/retrieval.py` | W13-5 | +3/-0 | Add professor metric fields to Milvus output fields. |
| `apps/miroflow-agent/tests/data_agents/service/test_retrieval.py` | W13-5 | +6/-0 | Add metric fields to professor ANN fixture and assert metadata. |
| `apps/admin-console/backend/api/domains.py` | W13-1 | +2/-1 | Select `p.summary_zh` and return it as `summary_fields.summary_zh`. |
| `apps/admin-console/tests/test_data_api_paper_v011.py` | W13-1 | +23/-2 | Cover non-null and null `summary_zh` on domain paper DTO. |
| `apps/admin-console/backend/api/chat.py` | W13-4 | +333/-0 | Add C handler helpers, session source selection, related-row normalization, patent evidence formatting, and dispatch branch. |
| `apps/admin-console/tests/test_chat_c_handler.py` | W13-4 | +244/-0 | New tests for prof->paper, prof->company, company->patent, empty/same-target stack clarification, and A fallback. |

Note: `uv.lock` and several untracked `.agents` / `docs` artifacts were already present or unrelated to this batch; they were left untouched.

## Key Design Choices

- W13-5 keeps the existing retrieval metadata path: `_row_to_evidence` already copies the Milvus entity dict, so adding output fields is sufficient.
- W13-1 intentionally returns `None` for missing `summary_zh` and does not coerce from `abstract_clean`.
- W13-4 uses `SessionContext.latest_entity_for_other_domains(target_domain)` so C queries never use a target-domain entity as their own source.
- W13-4 records the top target entity by placing the first target object in the existing top-level structured payload keys (`paper_id`, `company_id`, etc.); existing `_record_and_return` handles stack push and result-set history.
- W13-4 returns a clarification when there is no usable source entity; retrieval failures fall back to an A-style exact lookup path.

## BLOCKED Items

### W13-2 BLOCKED

Spec sections: W13-2 §5, §6, §7, §8.

Reason:
- W13-2 requires writing `professor_company_role` with `run_id`, `role`, and evidence enum values `official_site` / `public_web` / `manual_review`.
- Actual `V005b` creates `professor_company_role` with `role_id`, `role_type`, `evidence_url NOT NULL`, `match_reason NOT NULL`, and no `run_id` column (`V005b` lines 83-150).
- Actual evidence enum values are schema-specific (`company_official_site`, `professor_official_profile`, `trusted_media`, `xlsx_team_with_explicit_role`, `gov_registry`), not the W13-2 spec values.
- `V007` traced tables exclude relation tables (`professor_company_role`, `professor_patent_link`, `company_patent_link`), lines 25-33.
- Handoff Do-not forbids modifying V005b/V007 schema.

No W13-2 code was changed.

### W13-3 BLOCKED

Spec sections: W13-3 §5, §6, §7, §8.

Reason:
- W13-3 requires `patent.summary_text`, `summary_text_method`, and `quality_status`.
- Actual `V004` `patent` table has `abstract_clean`, `technology_effect`, `status`, and `run_id` later via V007, but no `summary_text`, `summary_text_method`, or `quality_status` columns (`V004` lines 100-146).
- W13-3 also requires `company_patent_link.run_id`; actual `V005b` `company_patent_link` has `link_id`, `link_role`, `evidence_source_type`, timestamps, and no `run_id` (`V005b` lines 278-333).
- Handoff Do-not forbids modifying V004/V005b/V007 schema.

No W13-3 code was changed.

## Verification

### W13-5

- `DATABASE_URL_TEST=... uv run pytest tests/data_agents/service/test_retrieval.py tests/data_agents/service/test_retrieval_get_object.py tests/data_agents/service/test_retrieval_get_related.py -n0 --no-cov -v`
  - First attempt failed before collection because `uv` cache under `/home/longxiang/.cache/uv` was read-only.
  - Rerun with workspace `UV_CACHE_DIR`: 36 passed.
- `DATABASE_URL_TEST=... uv run pytest tests/data_agents/service/ -n0 --no-cov -v`
  - 48 passed.
- Post-lint rerun: `DATABASE_URL_TEST=... uv run pytest tests/data_agents/service/test_retrieval.py -n0 --no-cov -v`
  - 16 passed.

### W13-1

- Handoff command with admin-console `-n0 --no-cov` failed before collection: admin-console pytest does not recognize those options.
- `DATABASE_URL_TEST=... uv run pytest tests/test_data_api_paper_v011.py -v`
  - 5 passed.
- `DATABASE_URL_TEST=... uv run pytest tests/ -k "paper or domain" -v`
  - 48 passed, 16 skipped, 160 deselected.
- Post-lint rerun: `DATABASE_URL_TEST=... uv run pytest tests/test_chat_c_handler.py tests/test_data_api_paper_v011.py -v`
  - 11 passed.

### W13-2

- `DATABASE_URL_TEST=... uv run pytest tests/data_agents/professor/test_link_backfill_postgres.py tests/data_agents/professor/test_link_backfill_pg_idempotency.py tests/data_agents/service/test_retrieval_get_related.py -n0 --no-cov -v`
  - Failed before collection: `tests/data_agents/professor/test_link_backfill_postgres.py` does not exist because W13-2 was blocked before adding tests.
- Retrieval relation coverage was still exercised in W13-5 service suite: included in 36 passed / 48 passed runs above.

### W13-3

- `DATABASE_URL_TEST=... uv run pytest tests/data_agents/patent/ tests/scripts/test_run_patent_release_e2e_pg.py -n0 --no-cov -v`
  - Failed before collection: `tests/scripts/test_run_patent_release_e2e_pg.py` does not exist because W13-3 was blocked before adding tests.
- Existing patent regression: `DATABASE_URL_TEST=... uv run pytest tests/data_agents/patent/ -n0 --no-cov -v`
  - 12 passed.
- Existing script path check: `tests/scripts/test_run_patent_release_e2e.py` is also absent in this checkout.
- Milvus dry-run: `uv run python scripts/run_milvus_backfill.py --domain=patent --limit=10 --dry-run`
  - Exit 0; reported `patent_profiles` collection missing and listed expected fields.

### W13-4

- First new-test run: `DATABASE_URL_TEST=... uv run pytest tests/test_chat_c_handler.py -v`
  - 5 passed, 1 failed; fixed patent answer formatting to include `patent_number`.
- Rerun: `DATABASE_URL_TEST=... uv run pytest tests/test_chat_c_handler.py -v`
  - 6 passed.
- `DATABASE_URL_TEST=... uv run pytest tests/test_chat_c_handler.py tests/test_chat_classifier_c_type.py tests/test_chat_v1.py tests/test_chat_retrieval.py -v`
  - 66 passed.
- Full chat regression: `DATABASE_URL_TEST=... uv run pytest tests/ -k "chat" -v`
  - 85 passed, 3 skipped, 142 deselected.
- Post-lint rerun with W13-1 changed test file:
  - 11 passed.

### Lint

- `just lint`
  - Failed: `just` command is not installed in the environment.
- Direct recipe attempt: `uv tool run ruff@0.8.0 check --fix .`
  - Failed with default uv tool dir: read-only `/home/longxiang/.local/share/uv/tools`.
  - Failed with workspace uv tool dir: network is blocked, so `ruff@0.8.0` could not be fetched.
- Available local Ruff: `/home/longxiang/.local/bin/ruff --version`
  - `ruff 0.15.10`.
- Repo-wide fallback: `/home/longxiang/.local/bin/ruff check --fix .`
  - Failed with 118 total issues; 43 auto-fixed, 75 remaining. Remaining failures are pre-existing unrelated files under `apps/miroflow-agent/scripts/`, professor pipeline modules, and professor tests. The unrelated auto-fix churn was reverted.
- Touched-file Ruff: `/home/longxiang/.local/bin/ruff check --fix <changed files>`
  - All checks passed.
- `git diff --check` on tracked changed files plus Ruff on new `test_chat_c_handler.py`
  - All checks passed.

## Risks / Notes

- W13-3 LLM fallback rate: not sampled. The slice is BLOCKED before implementation because the locked schema cannot store the required `summary_text` / `summary_text_method`; running a 10-patent LLM sample would not validate the writer contract. Current pre-W13 release path remains template-only.
- W13-2 `unmapped_company_alias` rate: not measured. No PG inserts were run because the target relation schema is blocked.
- W13-4 `chat.py` cumulative diff size: `git diff -- apps/admin-console/backend/api/chat.py | wc -l` = 365 lines; under the 600-line stop threshold.
- W13-4 real C-path hits for professor<->company and company<->patent depend on W13-2/W13-3 writers being unblocked and populated. The handler itself is covered with mocked retrieval results.
- No git commit, checkout, push, or PR was performed.
