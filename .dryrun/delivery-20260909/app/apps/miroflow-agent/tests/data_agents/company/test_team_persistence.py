from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from src.data_agents.company.team_parser import StructuredTeamMember
from src.data_agents.company.team_persistence import persist_structured_team_members


class _Result:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Conn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def execute(self, query: str, params: object = None) -> _Result:
        sql = " ".join(query.split())
        self.calls.append((sql, params))
        return _Result([])


def test_persist_structured_team_members_writes_structured_fields() -> None:
    conn = _Conn()
    members = [
        StructuredTeamMember(
            name="王博洋",
            role="CEO&联合创始人",
            background="连续创业者，长期参与医疗产品商业化。",
            experience_highlights=("医疗产品商业化", "公司经营管理"),
            relevance="负责旭宏医疗整体经营和心电产品商业化。",
            confidence=0.86,
            evidence_span="王博洋，旭宏医疗CEO&联合创始人。",
            raw_text="王博洋，职务：CEO&联合创始人，介绍：王博洋，旭宏医疗CEO&联合创始人。",
        )
    ]

    inserted = persist_structured_team_members(
        conn,
        company_id="COMP-1",
        snapshot_id=UUID("11111111-1111-1111-1111-111111111111"),
        members=members,
    )

    assert inserted == 1
    sql, params = conn.calls[0]
    assert "INSERT INTO company_team_member" in sql
    assert "structured_background" in sql
    assert params["structured_background"] == "连续创业者，长期参与医疗产品商业化。"
    highlights = getattr(
        params["structured_experience_highlights"],
        "obj",
        params["structured_experience_highlights"],
    )
    assert highlights == [
        "医疗产品商业化",
        "公司经营管理",
    ]
    assert params["structured_relevance"] == "负责旭宏医疗整体经营和心电产品商业化。"
    assert params["structured_confidence"] == Decimal("0.86")
    assert params["structured_evidence_span"] == "王博洋，旭宏医疗CEO&联合创始人。"
    assert params["structured_raw_text"].startswith("王博洋，职务")
