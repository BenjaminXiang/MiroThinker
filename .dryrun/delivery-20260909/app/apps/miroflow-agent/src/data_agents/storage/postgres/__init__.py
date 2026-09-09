"""Postgres backing store for the canonical knowledge graph.

Plan reference: docs/plans/2026-04-17-005 §9.2 storage/postgres/.
Phase 0 minimum: connection helper + seed loader. Repos arrive in Phase 1+.
"""

from .connection import connect, open_pool

__all__ = ["connect", "open_pool"]
