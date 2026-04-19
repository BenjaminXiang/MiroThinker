"""Round 9/P1-v0 chat API — template-based RAG MVP.

Goal per docs/plans/2026-04-18-001-user-chat-interface-plan.md v0:
end-to-end chat path that answers three golden-path queries with NO LLM:

    1. "介绍清华的丁文伯"              → profile card for a single prof
    2. "南科大做力控的教授"            → list of profs matching topic
    3. "优必选有哪些专利"              → patent list by applicant

v0 = single-turn, rule-based query parsing, template answers, Postgres-only.
Future iterations add LLM synthesis (v1), multi-turn context (v2), query
classifier (v3), web search fallback (v4), WeChat H5 (v4+).

Keep this module rigorously minimal. Resist the urge to add features that
belong in v1+. When in doubt, return {answer_text: "没找到...", citations: []}
and let the UI show it — that's better than faking an answer.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.deps import get_pg_conn

router = APIRouter(prefix="/api")


# --- Pydantic schemas ---


class ChatCitation(BaseModel):
    type: Literal["professor", "paper", "patent", "company"]
    id: str
    label: str
    url: str | None = None


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


class ChatResponse(BaseModel):
    query: str
    query_type: str  # A_prof_profile | A_prof_list_by_topic | A_patent_by_applicant | unknown
    answer_text: str
    citations: list[ChatCitation] = Field(default_factory=list)
    structured_payload: dict[str, Any] = Field(default_factory=dict)


# --- Institution alias map ---
# User query fragments → canonical Shenzhen primary institution strings.
# Values are ILIKE patterns (% added by the caller). Multi-value entries mean
# "match ANY of these" (we OR them in the WHERE clause).

_INSTITUTION_ALIASES: dict[str, tuple[str, ...]] = {
    "清华": ("清华大学深圳国际研究生院", "清华大学深圳研究生院"),
    "清华深圳": ("清华大学深圳国际研究生院", "清华大学深圳研究生院"),
    "清华大学深圳": ("清华大学深圳国际研究生院", "清华大学深圳研究生院"),
    "南科大": ("南方科技大学",),
    "南方科技大学": ("南方科技大学",),
    "深大": ("深圳大学",),
    "深圳大学": ("深圳大学",),
    "哈深": ("哈尔滨工业大学（深圳）",),
    "哈工大深圳": ("哈尔滨工业大学（深圳）",),
    "中大深圳": ("中山大学（深圳）",),
    "中山大学深圳": ("中山大学（深圳）",),
    "港中深": ("香港中文大学（深圳）",),
    "深技大": ("深圳技术大学",),
    "深圳技术大学": ("深圳技术大学",),
    "深理工": ("深圳理工大学",),
    "深圳理工": ("深圳理工大学",),
    "深圳理工大学": ("深圳理工大学",),
    "北大深圳": ("北京大学深圳研究生院",),
    "北大深研": ("北京大学深圳研究生院",),
    "中科院深圳": ("中国科学院深圳先进技术研究院",),
    "深先院": ("中国科学院深圳先进技术研究院",),
}

# Longest-first match so "清华大学深圳" resolves before "清华"
_INSTITUTION_KEYS_BY_LEN = sorted(
    _INSTITUTION_ALIASES.keys(), key=lambda k: -len(k)
)


# --- Query-type classifier (rule-based, v0) ---


_Q_PROFILE_RE = re.compile(
    r"介绍\s*(?:(?P<inst>[\u4e00-\u9fff]{2,15}?)\s*的\s*)?(?P<name>[\u4e00-\u9fff]{2,5})$"
)
_Q_TOPIC_LIST_RE = re.compile(
    r"(?P<inst>[\u4e00-\u9fff]{2,15}?)\s*做\s*(?P<topic>.{2,30}?)\s*的?\s*(教授|老师|学者)"
)
_Q_PATENT_LIST_RE = re.compile(
    r"(?P<company>[\u4e00-\u9fff A-Za-z0-9]{2,20})\s*(有哪些|有什么|的)\s*专利"
)


def _resolve_institution(fragment: str) -> tuple[str, ...] | None:
    """Return canonical institution strings matching a user-typed fragment."""
    if not fragment:
        return None
    for key in _INSTITUTION_KEYS_BY_LEN:
        if key in fragment:
            return _INSTITUTION_ALIASES[key]
    return None


# --- SQL helpers ---


def _lookup_professor(
    conn: Any, *, name: str, institutions: tuple[str, ...] | None
) -> list[dict]:
    params: list[Any] = [name, name]
    inst_clause = ""
    if institutions:
        placeholders = ", ".join(["%s"] * len(institutions))
        inst_clause = f" AND pa.institution IN ({placeholders})"
        params.extend(institutions)
    sql = f"""
        SELECT p.professor_id,
               p.canonical_name,
               p.canonical_name_en,
               pa.institution,
               pa.title,
               p.discipline_family
          FROM professor p
          LEFT JOIN LATERAL (
            SELECT pa_inner.institution, pa_inner.title
              FROM professor_affiliation pa_inner
             WHERE pa_inner.professor_id = p.professor_id
               AND pa_inner.is_primary = true
             LIMIT 1
          ) pa ON true
         WHERE p.identity_status = 'resolved'
           AND (p.canonical_name = %s OR %s = ANY (p.aliases))
           {inst_clause}
         LIMIT 10
    """
    return conn.execute(sql, params).fetchall()


def _lookup_professors_by_topic(
    conn: Any, *, institutions: tuple[str, ...], topic: str
) -> list[dict]:
    placeholders = ", ".join(["%s"] * len(institutions))
    sql = f"""
        WITH matches AS (
          SELECT p.professor_id,
                 p.canonical_name,
                 pa.institution,
                 array_agg(DISTINCT f.value_raw) FILTER (
                   WHERE f.value_raw ILIKE %s
                 ) AS matched_topics
            FROM professor p
            JOIN professor_affiliation pa
              ON pa.professor_id = p.professor_id AND pa.is_primary = true
            JOIN professor_fact f
              ON f.professor_id = p.professor_id
                 AND f.fact_type = 'research_topic'
                 AND f.status = 'active'
           WHERE p.identity_status = 'resolved'
             AND pa.institution IN ({placeholders})
             AND f.value_raw ILIKE %s
           GROUP BY p.professor_id, p.canonical_name, pa.institution
        )
        SELECT *, count(*) OVER ()::int AS total_count
          FROM matches
         ORDER BY canonical_name
         LIMIT 20
    """
    like = f"%{topic}%"
    return conn.execute(sql, [like, *institutions, like]).fetchall()


def _prof_research_topics(conn: Any, professor_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT value_raw FROM professor_fact
         WHERE professor_id = %s
           AND fact_type = 'research_topic'
           AND status = 'active'
         ORDER BY created_at
         LIMIT 12
        """,
        (professor_id,),
    ).fetchall()
    return [r["value_raw"] for r in rows]


def _prof_paper_count(conn: Any, professor_id: str) -> int:
    return conn.execute(
        """
        SELECT count(*)::int FROM professor_paper_link
         WHERE professor_id = %s AND link_status = 'verified'
        """,
        (professor_id,),
    ).fetchall()[0]["count"]


def _lookup_patents_by_applicant(
    conn: Any, *, company_name: str
) -> list[dict]:
    like = f"%{company_name}%"
    return conn.execute(
        """
        SELECT patent_id, patent_number, title_clean, applicants_raw,
               filing_date, grant_date, patent_type,
               count(*) OVER ()::int AS total_count
          FROM patent
         WHERE applicants_raw ILIKE %s
         ORDER BY filing_date DESC NULLS LAST
         LIMIT 20
        """,
        (like,),
    ).fetchall()


# --- Template answer builders ---


def _answer_prof_profile(prof: dict, topics: list[str], n_papers: int) -> str:
    name = prof["canonical_name"]
    name_en = prof.get("canonical_name_en")
    inst = prof.get("institution") or "单位未知"
    title = prof.get("title") or "教授"
    name_piece = f"{name}（{name_en}）" if name_en else name
    parts = [f"{name_piece} 是 {inst} 的{title}。"]
    if topics:
        topic_list = "、".join(topics[:5])
        parts.append(f"研究方向包括 {topic_list}。")
    if n_papers:
        parts.append(f"已收录 {n_papers} 篇论文。")
    return " ".join(parts)


def _answer_prof_list(institutions: tuple[str, ...], topic: str, rows: list[dict]) -> str:
    if not rows:
        inst = "/".join(institutions)
        return f"在 {inst} 未找到研究 {topic!r} 方向的教授。"
    total = rows[0].get("total_count", len(rows))
    header = (
        f"共找到 {total} 位教授（显示前 {min(len(rows), 10)} 位）："
        if total > len(rows) or len(rows) > 10
        else f"共找到 {total} 位教授："
    )
    lines = [header, ""]
    for r in rows[:10]:
        topics = r.get("matched_topics") or []
        topic_str = "、".join(topics[:3]) if topics else "(无)"
        lines.append(
            f"  • {r['canonical_name']} — {r['institution']} — 匹配方向: {topic_str}"
        )
    remaining = total - min(len(rows), 10)
    if remaining > 0:
        lines.append(f"  ... (另有 {remaining} 位未列出)")
    return "\n".join(lines)


def _answer_patent_list(company: str, rows: list[dict]) -> str:
    if not rows:
        return f"未找到以 {company!r} 为申请人的专利。"
    total = rows[0].get("total_count", len(rows))
    header = (
        f"共找到 {total} 件专利（显示前 {min(len(rows), 10)} 件）："
        if total > len(rows) or len(rows) > 10
        else f"共找到 {total} 件专利："
    )
    lines = [header, ""]
    for r in rows[:10]:
        date = (r.get("grant_date") or r.get("filing_date"))
        date_str = str(date) if date else "日期未知"
        lines.append(
            f"  • {r['patent_number']} — {r['title_clean']} "
            f"（{r.get('patent_type') or '类型未知'}, {date_str}）"
        )
    remaining = total - min(len(rows), 10)
    if remaining > 0:
        lines.append(f"  ... (另有 {remaining} 件未列出)")
    return "\n".join(lines)


def _answer_ambiguous_profs(name: str, profs: list[dict]) -> str:
    """Multiple profs share canonical_name; ask user to disambiguate by school."""
    lines = [
        f"找到 {len(profs)} 位名为 {name!r} 的教授，请加上学校再问一次：",
        "",
    ]
    for p in profs[:10]:
        inst = p.get("institution") or "单位未知"
        lines.append(f"  • {name} — {inst}")
    return "\n".join(lines)


# --- Endpoint ---


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    conn: Any = Depends(get_pg_conn),
) -> ChatResponse:
    query = payload.query.strip()

    # Pattern A: "介绍<inst>的<name>" — single professor profile
    if m := _Q_PROFILE_RE.search(query):
        name = m.group("name")
        inst_fragment = m.group("inst") or ""
        institutions = _resolve_institution(inst_fragment)
        profs = _lookup_professor(conn, name=name, institutions=institutions)
        if not profs:
            return ChatResponse(
                query=query,
                query_type="A_prof_profile",
                answer_text=f"没有找到{inst_fragment or ''}的{name}。",
                citations=[],
            )
        # Ambiguous: multiple matches without an institution filter.
        # Don't silently pick profs[0] — ask the user to disambiguate.
        if len(profs) > 1 and institutions is None:
            return ChatResponse(
                query=query,
                query_type="A_prof_profile_ambiguous",
                answer_text=_answer_ambiguous_profs(name, profs),
                citations=[
                    ChatCitation(
                        type="professor",
                        id=p["professor_id"],
                        label=f"{p['canonical_name']} - {p.get('institution') or '单位未知'}",
                        url=f"/browse#professor/{p['professor_id']}",
                    )
                    for p in profs[:10]
                ],
                structured_payload={
                    "name": name,
                    "candidate_count": len(profs),
                },
            )
        prof = profs[0]
        topics = _prof_research_topics(conn, prof["professor_id"])
        n_papers = _prof_paper_count(conn, prof["professor_id"])
        return ChatResponse(
            query=query,
            query_type="A_prof_profile",
            answer_text=_answer_prof_profile(prof, topics, n_papers),
            citations=[
                ChatCitation(
                    type="professor",
                    id=prof["professor_id"],
                    label=f"{prof['canonical_name']} - {prof.get('institution') or '单位未知'}",
                    url=f"/browse#professor/{prof['professor_id']}",
                )
            ],
            structured_payload={
                "professor_id": prof["professor_id"],
                "canonical_name": prof["canonical_name"],
                "canonical_name_en": prof.get("canonical_name_en"),
                "institution": prof.get("institution"),
                "title": prof.get("title"),
                "discipline_family": prof.get("discipline_family"),
                "research_topics": topics,
                "verified_paper_count": n_papers,
            },
        )

    # Pattern B: "<inst>做<topic>的教授" — list professors by topic + institution
    if m := _Q_TOPIC_LIST_RE.search(query):
        inst_fragment = m.group("inst")
        topic = m.group("topic").strip()
        institutions = _resolve_institution(inst_fragment)
        if not institutions:
            return ChatResponse(
                query=query,
                query_type="A_prof_list_by_topic",
                answer_text=f"未能识别学校名 {inst_fragment!r}。支持：清华、南科大、深大、港中深、中大深圳、深技大、深理工、哈深、北大深圳。",
                citations=[],
            )
        rows = _lookup_professors_by_topic(
            conn, institutions=institutions, topic=topic
        )
        return ChatResponse(
            query=query,
            query_type="A_prof_list_by_topic",
            answer_text=_answer_prof_list(institutions, topic, rows),
            citations=[
                ChatCitation(
                    type="professor",
                    id=r["professor_id"],
                    label=f"{r['canonical_name']} - {r['institution']}",
                    url=f"/browse#professor/{r['professor_id']}",
                )
                for r in rows[:10]
            ],
            structured_payload={
                "institutions": list(institutions),
                "topic": topic,
                "match_count": rows[0].get("total_count", len(rows)) if rows else 0,
            },
        )

    # Pattern C: "<company>有哪些专利" — patents by applicant
    if m := _Q_PATENT_LIST_RE.search(query):
        company = m.group("company").strip()
        rows = _lookup_patents_by_applicant(conn, company_name=company)
        return ChatResponse(
            query=query,
            query_type="A_patent_by_applicant",
            answer_text=_answer_patent_list(company, rows),
            citations=[
                ChatCitation(
                    type="patent",
                    id=r["patent_id"],
                    label=f"{r['patent_number']} - {r['title_clean']}",
                    url=f"/browse#patent/{r['patent_id']}",
                )
                for r in rows[:10]
            ],
            structured_payload={
                "company_name_query": company,
                "match_count": rows[0].get("total_count", len(rows)) if rows else 0,
            },
        )

    return ChatResponse(
        query=query,
        query_type="unknown",
        answer_text=(
            "未理解您的问题。v0 支持三种查询：\n"
            "  • 介绍<学校>的<教授名>\n"
            "  • <学校>做<方向>的教授\n"
            "  • <公司>有哪些专利"
        ),
        citations=[],
    )
