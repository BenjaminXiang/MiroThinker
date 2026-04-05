---
title: Admin console FastAPI + SQLite patterns and production hardening
date: 2026-04-04
category: docs/solutions
module: apps/admin-console, apps/miroflow-agent/src/data_agents/storage
problem_type: implementation_pattern
component: admin_console, sqlite_store
severity: medium
applies_when:
  - Adding paginated list endpoints backed by SQLite
  - Building FastAPI REST APIs that share storage with other apps
  - Handling user search input in SQL LIKE queries
  - Routing domain-generic endpoints in FastAPI
tags: [admin-console, fastapi, sqlite, pagination, like-escaping, route-collision, wal-mode, cross-app-import]
---

# Admin console FastAPI + SQLite patterns and production hardening

## Context

On April 4, 2026, the web admin console was built as a FastAPI + React SPA for browsing the released_objects knowledge base across professor/company/paper/patent domains. The backend reuses `SqliteReleasedObjectStore` from miroflow-agent via uv workspace editable dependencies. Cross-validation and adversarial review surfaced four production issues that unit tests alone would not have caught.

## Guidance

### 1. LIKE metacharacter escaping in SQLite parameterized queries

Parameterized queries (`?` placeholders) prevent SQL injection but do NOT prevent LIKE semantic manipulation. User input containing `%` or `_` characters changes the LIKE pattern semantics, producing incorrect search results.

Always escape LIKE metacharacters before embedding user input in a LIKE pattern:

```python
escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
where = "WHERE display_name LIKE ? ESCAPE '\\'"
params = (f"%{escaped}%",)
```

The `ESCAPE '\\'` clause is required to tell SQLite which character is the escape prefix. Without it, the backslash escapes are ignored.

Test this with a dedicated test case that searches for literal `%` and `_` and asserts zero results when no records contain those characters.

### 2. DomainEnum for preventing catch-all route collisions in FastAPI

A generic `/{domain}` path parameter will match ANY path segment, including `/dashboard`, `/health`, or other routes. Router registration order determines which wins, making the app fragile to refactoring.

Use a `str` + `Enum` path parameter to constrain matching:

```python
class DomainEnum(str, Enum):
    professor = "professor"
    company = "company"
    paper = "paper"
    patent = "patent"

@router.get("/{domain}")
def list_domain(domain: DomainEnum, ...):
    store.list_domain_paginated(domain.value, ...)
```

FastAPI returns 422 automatically for values not in the enum. No manual validation needed, and no risk of shadowing other routes.

### 3. WAL mode for concurrent SQLite access

Default SQLite journal mode (`DELETE`) locks the entire database file during writes. When the admin console reads while E2E scripts write, this produces `database is locked` errors.

Enable WAL (Write-Ahead Logging) mode during initialization:

```python
def _initialize(self) -> None:
    with sqlite3.connect(self.db_path, timeout=10) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        # ... create tables
```

WAL allows concurrent readers during writes. The `timeout=10` parameter makes connections wait up to 10 seconds for locks instead of failing immediately.

### 4. Cross-app import via uv workspace editable dependencies

When one app in the monorepo needs to import modules from another, use uv workspace editable dependencies. The pattern is proven in the root `pyproject.toml`:

In the consuming app's `pyproject.toml`:
```toml
[project]
dependencies = ["miroflow-agent"]

[tool.uv.sources]
miroflow-agent = { path = "../miroflow-agent", editable = true }
```

The producing app must have `packages = ["src"]` (or equivalent) in its build config so the `src` package is exposed as a top-level import. Verified: `from src.data_agents.contracts import ReleasedObject` works from the admin-console app context.

### 5. Reflected input in error messages creates XSS vectors

Never echo user-provided values (path parameters, query strings) in error response messages:

```python
# BAD: reflected XSS via object_id
raise HTTPException(status_code=404, detail=f"Object {object_id} not found")

# GOOD: generic message
raise HTTPException(status_code=404, detail="Object not found")
```

Similarly for sort_by validation errors. Use a fixed message listing allowed values, not one that includes the invalid input.

### 6. Python-side aggregation vs json_extract for small datasets

For `quality_breakdown()`, Python-side counting via `Counter` on loaded objects is simpler and correct for datasets under a few thousand records. SQL-level `json_extract(payload_json, '$.quality_status')` adds complexity and a SQLite JSON1 extension dependency with no measurable performance benefit at current scale (hundreds of records per domain).

Optimize to SQL-level aggregation only when data grows to tens of thousands per domain, which would make loading all rows expensive.

## Why This Matters

These patterns prevent four classes of bugs that are invisible in unit tests but break production:
- LIKE escaping: search queries with `%` return all records instead of zero
- Route collision: adding a new `/api/foo` endpoint silently stops working when `/{domain}` catches it first
- WAL mode: concurrent read/write produces intermittent `database is locked` errors
- Reflected XSS: user-controlled strings appear in HTTP responses, enabling script injection

## When to Apply

- When adding search endpoints that use SQL LIKE on user input.
- When designing FastAPI routers with both specific routes and parameterized catch-all routes.
- When multiple processes read/write the same SQLite database file.
- When building admin consoles or APIs that return error messages containing user input.
- When importing shared modules across apps in a uv workspace monorepo.

## Examples

Before:
```python
# Search with raw user input in LIKE
rows = conn.execute(
    "SELECT * FROM released_objects WHERE display_name LIKE ?",
    (f"%{query}%",),
)
```

After:
```python
escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
rows = conn.execute(
    "SELECT * FROM released_objects WHERE display_name LIKE ? ESCAPE '\\'",
    (f"%{escaped}%",),
)
```

Before:
```python
@router.get("/{domain}")  # catches /dashboard, /health, everything
def list_domain(domain: str, ...): ...
```

After:
```python
class DomainEnum(str, Enum):
    professor = "professor"
    company = "company"

@router.get("/{domain}")  # only matches enum values, 422 for others
def list_domain(domain: DomainEnum, ...): ...
```

## Related

- Plan: `docs/plans/2026-04-04-001-feat-admin-console-plan.md`
- Store: `apps/miroflow-agent/src/data_agents/storage/sqlite_store.py`
- API: `apps/admin-console/backend/api/domains.py`
