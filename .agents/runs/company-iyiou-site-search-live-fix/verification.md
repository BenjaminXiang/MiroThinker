# Verification

## 2026-05-28

### Focused Tests

Command:

```bash
cd apps/miroflow-agent
uv run pytest tests/data_agents/company/test_serper_news_connector.py tests/data_agents/company/test_yiou_adapter.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_enrichment_e2e.py -q -n0 --no-cov
```

Result:

- Passed: `57 passed in 0.63s`.

### Ruff

Command:

```bash
cd apps/miroflow-agent
uv run ruff check src/data_agents/company/news_connectors/serper.py src/data_agents/company/news_connectors/iyiou.py src/data_agents/company/news_connectors/__init__.py scripts/run_company_news_ingest.py scripts/run_company_enrichment_e2e.py tests/data_agents/company/test_serper_news_connector.py tests/data_agents/company/test_yiou_adapter.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_enrichment_e2e.py
```

Result:

- Passed: `All checks passed!`.

### Live Yiou And PitchHub E2E

Command:

```bash
cd apps/miroflow-agent
uv run python scripts/run_company_enrichment_e2e.py --live --live-limit 20 --output ../../.agents/runs/company-iyiou-site-search-live-fix/company-live-20-2026-05-28.json
```

Result:

- Exit code: `0`.
- `deterministic_status`: `passed`.
- XLSX company rows parsed: `1025`.
- Released records: `1025`.
- Live status: `passed`.
- Companies checked: `20`.
- Companies with company-confirmed Yiou records: `3`.
- Accepted company-confirmed Yiou records: `7`.
- Companies with company-confirmed PitchHub records: `9`.
- Accepted company-confirmed PitchHub records: `16`.
- PitchHub fetched content characters: `29523`.
- `深圳旭宏医疗科技有限公司`: `1` accepted Yiou company profile URL plus `2` accepted PitchHub URLs.
- `深圳元戎启行科技有限公司`: `1` accepted Yiou record plus `1` accepted PitchHub URL.
- Generic Yiou pages are rejected and reported via `items_rejected_irrelevant_path`.
- Name-mismatched Yiou detail pages are rejected and reported via `items_rejected_name_mismatch`.
- PitchHub generic or name-mismatched search hits are rejected before detail fetch.

### Live PitchHub Detail Probe

Command:

```bash
cd apps/miroflow-agent
uv run python scripts/run_company_enrichment_e2e.py --live --live-limit 2 --output -
```

Result:

- Exit code: `0`.
- `deterministic_status`: `passed`.
- `live_checks.status`: `passed`.
- Companies checked: `2`.
- `深圳旭宏医疗科技有限公司`: `2` accepted PitchHub records.
- Accepted PitchHub URLs:
  - `https://pitchhub.36kr.com/project/1678475362006017`
  - `https://pitchhub.36kr.com/organization/1678213442122752`
- PitchHub detail fetch attempts: `2`.
- PitchHub detail fetch successes: `2`.
- PitchHub fetched content characters: `3537`.

### Root-Cause Probe

Command:

```bash
cd apps/miroflow-agent
uv run python - <<'PY'
...
PY
```

Result:

- `深圳旭宏医疗科技有限公司 site:data.iyiou.com` with `tbs=qdr:y`: `organic_count=0`.
- The same query without `tbs`: `organic_count=1`.
- The returned URL was the Yiou company profile page.
- Follow-up probing showed that a single zero result is not proof Yiou has no data. The implementation now tries normalized-name fallback and requires company-name confirmation to avoid accepting unrelated Yiou pages.
- Follow-up PitchHub probing showed that accepted project detail pages can provide product, financing, industrial/commercial, and team evidence through reader fallback body text.

### OpenSpec

Command:

```bash
openspec validate company-iyiou-site-search-live-fix --strict
```

Result:

- Passed: `Change 'company-iyiou-site-search-live-fix' is valid`.

### Diff Whitespace

Command:

```bash
git diff --check -- apps/miroflow-agent/src/data_agents/company/news_connectors/serper.py apps/miroflow-agent/src/data_agents/company/news_connectors/iyiou.py apps/miroflow-agent/src/data_agents/company/news_connectors/__init__.py apps/miroflow-agent/scripts/run_company_news_ingest.py apps/miroflow-agent/scripts/run_company_enrichment_e2e.py apps/miroflow-agent/tests/data_agents/company/test_serper_news_connector.py apps/miroflow-agent/tests/data_agents/company/test_yiou_adapter.py apps/miroflow-agent/tests/scripts/test_run_company_news_ingest.py apps/miroflow-agent/tests/scripts/test_run_company_enrichment_e2e.py openspec/changes/company-iyiou-site-search-live-fix .agents/runs/company-iyiou-site-search-live-fix
```

Result:

- Passed with no output.
