---
id: ADR-001
title: Postgres driver — psycopg3 (binary + pool)
status: accepted
date: 2026-04-17
plan: docs/plans/2026-04-17-005-company-primary-knowledge-graph-architecture-plan.md
---

# ADR-001: Postgres driver — psycopg3 (binary + pool)

## Context

Plan 005 moves the canonical truth store from SQLite to Postgres 16 + pgvector.
We need a Python driver. Candidates: `psycopg` (v3), `asyncpg`, `pg8000`.

The rest of the agent stack (`apps/miroflow-agent/`, `apps/admin-console/`) is
currently mostly synchronous. The admin-console FastAPI handlers call SQLite
directly in sync style (`apps/admin-console/backend/api/domains.py` is
`def`, not `async def`). Data-agent pipelines are a mix; ingestion and
enrichment jobs are sync subprocesses triggered by Hydra CLIs.

Alembic (our migration tool, see ADR-005) is sync by design and works with
any DB-API 2.0 driver.

## Decision

Use **`psycopg` v3** with the **`[binary,pool]` extras**.

```toml
"psycopg[binary,pool]>=3.2",
```

DSN format: `postgresql://user:pass@host:port/dbname`.

SQLAlchemy's own URL form `postgresql+psycopg://...` is accepted by alembic's
env.py but stripped to the plain form when we open a raw psycopg connection
(see `apps/miroflow-agent/alembic/env.py`).

## Rationale

- **Sync + async from one driver.** psycopg3 provides both `psycopg.connect()`
  (sync) and `psycopg.AsyncConnection.connect()` (async). We need sync now
  (admin-console, ingestion jobs) and can adopt async per-module later
  without changing drivers.
- **Binary wheel.** `[binary]` bundles libpq; no system `libpq-dev` install
  step required on developer machines or CI runners.
- **Connection pool included.** `psycopg_pool.ConnectionPool` is first-party;
  no third-party dep.
- **No ORM required.** We manage DDL in raw alembic migrations (no
  SQLAlchemy MetaData / declarative models). Row access uses the DB-API
  cursor + dict_row. Less magic than an ORM and easier to debug.
- **Avoid asyncpg.** asyncpg is faster but async-only; mixing sync/async
  adds friction for a 1-3 person team.
- **Avoid pg8000.** Pure-Python driver is fine for constrained environments
  but we don't need that and binary is faster.

## Consequences

Positive:
- Single driver across sync and async code paths.
- Alembic works out of the box with the sync connection.
- No build-time native deps.

Negative:
- psycopg3 API differs from psycopg2 in a few places (named-cursor semantics,
  `COPY` syntax); if someone pastes old psycopg2 snippets, expect small
  corrections.
- `[binary]` wheels pin a specific libpq version; if we ever need a newer
  libpq than the wheel bundles, switch to `[c]` and install system libpq.

## Related

- ADR-005 (Postgres jobstore for APScheduler; also uses psycopg)
- `apps/miroflow-agent/pyproject.toml` — dep declaration
- `apps/miroflow-agent/alembic/env.py` — DSN resolution
