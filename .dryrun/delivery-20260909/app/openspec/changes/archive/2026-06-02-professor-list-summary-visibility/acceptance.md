# Acceptance Evidence

## Scenarios

| Requirement | Evidence | Status |
| --- | --- | --- |
| Professor list shows profile summary previews. | RED test `src/pages/DomainList.test.tsx` failed before implementation because Ahmed Elazab's `summary_fields.profile_summary` was not in the professor list DOM. After adding the professor-only summary column, the same test passed. | Verified |
| Missing summary remains visible as missing. | The summary column uses the same `-` placeholder as existing missing table fields when `summary_fields.profile_summary` is null or empty. Live `/professor` verification showed rows such as Albert Evans with `-` in the summary column. | Verified |
| Professor summary is visible before opening detail. | Browser verification on `http://127.0.0.1:5180/professor` showed a `摘要` column and visible summary text for Ahmed Elazab, Buddhi Wijesiri, Charles M. Lieber, Ercan Engin Kuruoğlu, and other rows. | Verified |
| Existing detail workbench remains unchanged. | No code path in `ProfessorWorkbench.tsx` was modified; the existing `ProfessorWorkbench.test.tsx` suite continued to pass as part of the full frontend test run. | Verified |

## Commands

```bash
cd apps/admin-console/frontend
npm run test -- src/pages/DomainList.test.tsx
```

Result before implementation: failed because the professor summary preview was not rendered.

Result after implementation: passed, 1 test.

```bash
cd apps/admin-console/frontend
npm run test
```

Result: passed, 2 test files and 4 tests.

```bash
cd apps/admin-console/frontend
npm run build
```

Result: passed. Vite emitted the existing large-chunk warning only.

```bash
timeout 20s agent-browser --session summary-check open http://127.0.0.1:5180/professor
timeout 20s agent-browser --session summary-check wait --text 'Ahmed Elazab'
timeout 20s agent-browser --session summary-check snapshot -i -c
```

Result: passed. The snapshot included the `摘要` column and visible `profile_summary` text for Ahmed Elazab.

```bash
curl -sS http://127.0.0.1:5180/src/pages/DomainList.tsx | rg -n "title: \"摘要\"|profile_summary|summary_fields"
```

Result: confirmed the Vite dev server is serving the updated professor summary column source.

```bash
uv run --no-sync python -c 'import json, urllib.request; payload=json.load(urllib.request.urlopen("http://127.0.0.1:5180/api/professor?page=1&page_size=1")); item=payload["items"][0]; print(item["display_name"]); print(item["summary_fields"].get("profile_summary"))'
```

Result: printed Ahmed Elazab and the same profile summary shown in the list.
