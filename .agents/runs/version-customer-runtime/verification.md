# Verification: version-customer-runtime

Date: 2026-10-26 (CST). Environment: worktree `.worktrees/customer-20261026`,
branch `hotfix/customer-20261026`, python `/home/longxiang/MiroThinker/.venv/bin/python`.

## 1. Snapshot (task 1.1)

```
git worktree add .worktrees/customer-20261026 -b hotfix/customer-20261026 67933138
ssh root@100.64.0.96 "cd /root/deploy/fullstack-v2/code && tar czf - ... apps" | tar xzf -
commit 82047a7b "chore(customer): snapshot the deployed runtime as hotfix/customer-20261026"
41 files changed, 2315 insertions(+), 528 deletions(-)
```

- 33 modified + 4 added source files; 4 snapshot artefacts under
  `.agents/runs/version-customer-runtime/prod-snapshot/`.
- 49 hot-patch residue files (`.bak-*`, `.pre-*`) identified and excluded; names
  recorded in `excluded-patch-residue.txt` (44 `.bak`, 5 `.pre`).
- `run.sh` snapshot `sha256 fd17c4e6…`.

## 2. Drift check (tasks 1.2 / 1.3)

```
python apps/admin-console/scripts/check_runtime_drift.py \
  --ref hotfix/customer-20261026 \
  --remote root@100.64.0.96:/root/deploy/fullstack-v2/code
→ no drift: deployed tree matches the git ref
→ runtime files ignored (4): apps/miroflow-agent/.env, .env.example, milvus.db, report.html
→ compared 697 ref files against 697 deployed files
exit=0
```

Findings while wiring it up:

- Comparing all of `apps/` reports 50 false differences: `apps/collect-trace/`
  and `apps/gradio-demo/` are historical and never deployed. Default scope is now
  `apps/admin-console` + `apps/miroflow-agent`.
- `apps/admin-console/.agents/runs/**` (tracked evidence) is not deployed; `.agents`
  is ignored.
- The deployed bundle ships a **trimmed test tree**: 8 test files exist in git but
  not on the host (`test_canonical_v2_answer_cache.py`, `test_standalone_anchor.py`,
  `test_star_coupling_defaults.py`, `test_alias_foothold.py`, `test_web_wide_window.py`,
  `test_deepseek_search.py`, `test_fallback_web_search.py`,
  `test_star_domain_retirement.py`). Tests are excluded by default (`--include-tests`
  opts in), because they are not runtime behaviour.
- The host has `apps/miroflow-agent/.env` inside the source tree (runtime artefact,
  ignored by the gate, reported by it).

## 3. Adopted-behaviour tests (task 1.4)

New / updated tests, all green:

| File | Tests | Locks |
|---|---|---|
| `apps/admin-console/tests/test_standalone_anchor.py` | +2 | topic-professor guard fires only without a company word; named relations keep their anchor |
| `apps/admin-console/tests/test_canonical_v2_answer_cache.py` | +1, 3 updated | mixed local+web envelope caches; web-only rejected; marker rejected; coverage tail allowed; >1200-char answer accepted; index-keyed citation map accepted |
| `apps/admin-console/tests/test_canonical_v2_manual_recall.py` | +1 | professor serializer keeps department/email/homepage/counts/education/work/awards/company_roles |
| `apps/miroflow-agent/tests/canonical_v2/test_entity_name_forms_generic_names.py` | +4 | generic appellations never indexed; real names survive; longer names unaffected |
| `apps/admin-console/tests/test_check_runtime_drift.py` | +7 | residue/runtime classification, compare, local and git scans |

```
48 passed in 0.40s   (4 admin-console modules)
 4 passed            (entity name forms module)
 9 passed            (test_alias_foothold.py sibling regression)
```

### RED evidence (proved each test bites)

1. **Topic guard** — disabled the guard condition (`False and "教授" in query`),
   ran `test_standalone_anchor.py`:
   `FAILED test_topic_professor_query_does_not_anchor_a_company` with
   `+ where ('company-c-lingqiao', '浙江灵巧智能科技有限公司') = _standalone_anchor(...)`
   — the exact production symptom. File restored (`sha256 4c94732e…`), `git diff` clean.
2. **Pre-adoption cache tests** — replayed the branch's pre-patch test file against
   the adopted code: 4 failed (`accepts_local_grounded_answer`,
   `rejects_web_citation`, `rejects_marker_and_member_wall`,
   `accepts_index_keyed_citation_map`); the gate now validates the HTTP envelope,
   so `checks["local_only"]` no longer exists and length/marker read the response.
3. **Generic-name blocklist** — runtime probe with the blocklist emptied:

   ```
   with blocklist   : []
   blocklist emptied: ['教授']
   ```

## 4. Lint

```
ruff check <6 touched files>  → All checks passed!
ruff format --check           → only pre-existing files differ (formatter version);
                                the two new files are formatted, adopted files were
                                left unformatted to avoid drive-by reformatting
```

## Known gaps

- Dev line (`:18188`) still serves the s12a preview harness; task 1.6 open.
- turn-debug artefacts still present; task 1.5 open.
- The customer host files were not modified by this change.
