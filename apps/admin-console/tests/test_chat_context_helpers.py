from __future__ import annotations

from typing import Any

from backend.services.chat_context import (
    _paper_title_lookup_key,
    lookup_company,
    lookup_paper,
)


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


def test_lookup_paper_excludes_rejected_rows() -> None:
    conn = _Conn()

    lookup_paper(conn, title="Communication Efficient Federated Learning")

    assert "identity_status, 'unverified') != 'rejected'" in conn.sql
    assert "quality_status, 'needs_enrichment') != 'rejected'" in conn.sql
    assert conn.params == (
        "Communication Efficient Federated Learning",
        "%Communication Efficient Federated Learning%",
        "Communication Efficient Federated Learning",
        "communicationefficientfederatedlearning",
        "%communicationefficientfederatedlearning%",
    )


def test_lookup_paper_uses_normalized_title_key_for_unicode_punctuation() -> None:
    conn = _Conn()

    title = (
        "Concurrent Ferroptosis and Pyroptosis Induced by a "
        "Dual-Organelle-Targeted Type I/II AIE Photosensitizer"
    )
    lookup_paper(conn, title=title)

    assert _paper_title_lookup_key("Dual‐Organelle‐Targeted Type I/II") == (
        "dualorganelletargetedtypeiii"
    )
    assert "regexp_replace(lower(title_clean)" in conn.sql
    assert conn.params[-2] == _paper_title_lookup_key(title)
    assert conn.params[-1] == f"%{_paper_title_lookup_key(title)}%"


def test_lookup_paper_uses_normalized_partial_title_key_for_punctuation_gaps() -> None:
    conn = _Conn()

    title_prefix = "OctGLP-Net Learning Octree-Structured Context Entropy Model"
    lookup_paper(conn, title=title_prefix)

    partial_key = _paper_title_lookup_key(title_prefix)
    assert "regexp_replace(lower(title_clean), '[^[:alnum:]]', '', 'g') LIKE %s" in conn.sql
    assert conn.params[-1] == f"%{partial_key}%"


def test_lookup_paper_short_title_sentinel_is_postgres_text_safe() -> None:
    conn = _Conn()

    lookup_paper(conn, title="PAPER-C0CB4902CF93")

    assert conn.params is not None
    assert "\x00" not in conn.params[-1]
