---
title: "Company Milvus dogfood — blocked"
date: 2026-05-02
owner: codex-ops
spec: ../../.agents/specs/2026-05-02-w13-V2-company-milvus-dogfood.md
status: blocked
---

# Company Milvus Dogfood — 2026-05-02

## Result

V2 did not reach narrative backfill, Milvus backfill, or retrieval sampling.
The environment could not reach the required DB/network boundary:

- V1 Alembic checks against both `localhost:15432` Postgres databases returned
  `psycopg.OperationalError: connection is bad: no error details available`.
- Python socket creation returned `PermissionError: [Errno 1] Operation not permitted`.
- DNS resolution for the internal Gemma endpoint failed from this session.

The first V2 command from the spec was also rejected by the current CLI parser:

```bash
uv run python scripts/run_company_narrative_backfill.py --limit 50 --dry-run=false
```

`--dry-run` is implemented as a boolean flag, so argparse returned:

```text
argument --dry-run: ignored explicit argument 'false'
```

No DB writes were attempted.

## Validation Gates

| Gate | Result |
|---|---|
| `profile_summary` coverage | Not available |
| `technology_route_summary` coverage | Not available |
| narrative length distribution | Not available |
| LLM failure rate | Not available |
| Milvus `company_profiles` row count | Not available |
| 50-query Top-5 accuracy | Not available |

## Archives

No narrative checkpoint JSONL was produced, so
`docs/source_backfills/company-narrative-backfill-2026-05-02.jsonl` was not
created.

## Next Step

Before rerunning, align the V2 command syntax with the actual CLI (`--dry-run`
as a flag, omitted for writes), then execute from an environment that can reach
`miroflow_real`, Milvus, the embedding API, and Gemma-4.
