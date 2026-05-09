from __future__ import annotations

from typing import Any

from backend.services.chat_context import lookup_company


class _Rows:
    def fetchall(self) -> list[dict[str, Any]]:
        return []


class _Conn:
    def __init__(self) -> None:
        self.sql = ""
        self.params: tuple[Any, ...] | None = None

    def execute(self, sql: str, params: tuple[Any, ...]) -> _Rows:
        self.sql = sql
        self.params = params
        return _Rows()


def test_lookup_company_uses_jsonb_alias_lookup() -> None:
    conn = _Conn()

    lookup_company(conn, name="无界智航")

    assert "ANY(c.aliases)" not in conn.sql
    assert "jsonb_exists(" in conn.sql
    assert "c.aliases" in conn.sql
    assert conn.params == ("无界智航", "无界智航", "%无界智航%")
