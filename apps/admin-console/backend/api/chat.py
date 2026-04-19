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

import os
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends
from openai import OpenAI
from pydantic import BaseModel, Field

from backend.deps import get_pg_conn
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings

router = APIRouter(prefix="/api")

_CHAT_SYNTHESIS_TIMEOUT_SECONDS = 3.0
_CHAT_SYNTHESIS_REPORTED_BY = "round_9_p1_v1_chat_synthesis"
_CHAT_SYNTHESIS_SYSTEM_PROMPT = (
    "你是深圳科创信息检索助手。基于下面的证据回答用户问题。规则："
    "(1) 只使用证据中出现的事实，不要编造。"
    "(2) 每个事实用 [N] 标注来源编号，每个标记只写一个编号；"
    "不要合并成 [1, 2, 3]——要么分别标 [1][2][3]，要么只标最关键的那个。"
    "(3) 回答用中文，简洁自然，不要列 bullet。"
    '(4) 如果证据不足，直说"证据不足以回答"。'
)
_CHAT_SYNTHESIS_EXTRA_BODY = {
    "chat_template_kwargs": {"enable_thinking": False}
}


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
    answer_style: Literal["template", "llm_synthesized"] = "template"
    citation_map: dict[str, str] = Field(default_factory=dict)


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


def llm_synthesis_enabled() -> bool:
    return os.getenv("CHAT_LLM_SYNTHESIS", "on").strip().lower() != "off"


def _clear_proxy_env() -> None:
    for key in (
        "all_proxy",
        "ALL_PROXY",
        "http_proxy",
        "HTTP_PROXY",
        "https_proxy",
        "HTTPS_PROXY",
    ):
        os.environ.pop(key, None)


def _append_evidence_block(
    *,
    blocks: list[str],
    citation_map: dict[str, str],
    marker: int,
    kind: str,
    summary: str,
    evidence_id: str,
) -> int:
    blocks.append(f"[{marker}] ({kind}) {summary} id={evidence_id}")
    citation_map[str(marker)] = evidence_id
    return marker + 1


def _build_evidence_blocks(
    structured_payload: dict[str, Any],
) -> tuple[str, dict[str, str]]:
    blocks: list[str] = []
    citation_map: dict[str, str] = {}
    marker = 1

    if professor_id := structured_payload.get("professor_id"):
        canonical_name = structured_payload.get("canonical_name")
        institution = structured_payload.get("institution")
        title = structured_payload.get("title")
        research_topics = structured_payload.get("research_topics") or []
        verified_paper_count = structured_payload.get("verified_paper_count")

        if canonical_name:
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="professor",
                summary=f"教授姓名：{canonical_name}",
                evidence_id=professor_id,
            )
        if institution:
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="professor",
                summary=f"所属机构：{institution}",
                evidence_id=professor_id,
            )
        if title:
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="professor",
                summary=f"职称：{title}",
                evidence_id=professor_id,
            )
        for topic in research_topics[:6]:
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="research_topic",
                summary=f"研究方向：{topic}",
                evidence_id=professor_id,
            )
        if verified_paper_count is not None:
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="paper_count",
                summary=f"已收录论文数：{verified_paper_count}",
                evidence_id=professor_id,
            )
        return "\n".join(blocks), citation_map

    matched_professors = structured_payload.get("matched_professors") or []
    if matched_professors:
        for prof in matched_professors[:10]:
            topics = prof.get("matched_topics") or []
            topic_text = f"，匹配方向：{'、'.join(topics[:3])}" if topics else ""
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="professor",
                summary=(
                    f"{prof.get('canonical_name') or '姓名未知'}，"
                    f"{prof.get('institution') or '机构未知'}"
                    f"{topic_text}"
                ),
                evidence_id=prof["professor_id"],
            )
        return "\n".join(blocks), citation_map

    patents = structured_payload.get("patents") or []
    if patents:
        for patent in patents[:10]:
            date = patent.get("grant_date") or patent.get("filing_date") or "日期未知"
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="patent",
                summary=(
                    f"{patent.get('patent_number') or '编号未知'}，"
                    f"{patent.get('title_clean') or '标题未知'}，"
                    f"申请人：{patent.get('applicants_raw') or '未知'}，"
                    f"{patent.get('patent_type') or '类型未知'}，"
                    f"{date}"
                ),
                evidence_id=patent["patent_id"],
            )
        return "\n".join(blocks), citation_map

    candidates = structured_payload.get("candidates") or []
    if candidates:
        for prof in candidates[:10]:
            title = prof.get("title") or "职称未知"
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="professor_candidate",
                summary=(
                    f"{prof.get('canonical_name') or '姓名未知'}，"
                    f"{prof.get('institution') or '机构未知'}，"
                    f"{title}"
                ),
                evidence_id=prof["professor_id"],
            )
        return "\n".join(blocks), citation_map

    return "", {}


def _extract_chat_completion_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise ValueError("parse failure: missing choices")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str):
        text = content.strip()
        if text:
            return text
        raise ValueError("parse failure: empty content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
            else:
                text = getattr(item, "text", None)
            if text:
                parts.append(str(text))
        merged = "".join(parts).strip()
        if merged:
            return merged
    raise ValueError("parse failure: unsupported content shape")


def _call_gemma_synthesis(
    query: str,
    evidence_text: str,
    *,
    timeout: float,
) -> str:
    _clear_proxy_env()
    llm_settings = resolve_professor_llm_settings("gemma4")
    api_key = llm_settings.get("local_llm_api_key")
    if not api_key:
        raise ValueError("missing local_llm_api_key for gemma4")
    client = OpenAI(
        base_url=llm_settings["local_llm_base_url"],
        api_key=api_key,
        timeout=timeout,
    )
    response = client.chat.completions.create(
        model=llm_settings["local_llm_model"],
        messages=[
            {"role": "system", "content": _CHAT_SYNTHESIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"用户问题: {query}\n\n"
                    f"证据（请引用 [N]）:\n{evidence_text}"
                ),
            },
        ],
        extra_body=_CHAT_SYNTHESIS_EXTRA_BODY,
    )
    return _extract_chat_completion_text(response)


def _file_chat_synthesis_issue(
    conn: Any,
    query: str,
    query_type: str,
    exc: Exception,
) -> None:
    del query
    try:
        conn.execute(
            """
            INSERT INTO pipeline_issue (
                professor_id,
                institution,
                stage,
                severity,
                description,
                reported_by
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                None,
                "UNKNOWN_INSTITUTION",
                "chat_synthesis",
                "low",
                f"LLM synthesis failed for {query_type}: {exc}",
                _CHAT_SYNTHESIS_REPORTED_BY,
            ),
        )
    except Exception:
        # Best effort only; synthesis fallback must not turn into a 500.
        return


def _build_chat_response(
    *,
    conn: Any,
    query: str,
    query_type: str,
    answer_text: str,
    citations: list[ChatCitation],
    structured_payload: dict[str, Any],
) -> ChatResponse:
    base_response = ChatResponse(
        query=query,
        query_type=query_type,
        answer_text=answer_text,
        citations=citations,
        structured_payload=structured_payload,
    )
    if not llm_synthesis_enabled():
        return base_response

    evidence_text, citation_map = _build_evidence_blocks(structured_payload)
    if not evidence_text:
        return base_response

    try:
        llm_answer = _call_gemma_synthesis(
            query,
            evidence_text,
            timeout=_CHAT_SYNTHESIS_TIMEOUT_SECONDS,
        )
        # Match single [N] markers AND compound [1, 2, 3] markers (just in case
        # the LLM ignores the prompt rule). Extract every number inside brackets.
        markers: set[str] = set()
        for group in re.findall(r"\[([\d,\s]+)\]", llm_answer):
            for n in re.findall(r"\d+", group):
                markers.add(n)
        if not markers:
            raise ValueError("no citation markers found")
        if not markers.issubset(citation_map):
            raise ValueError("dangling citation marker")
        return ChatResponse(
            query=query,
            query_type=query_type,
            answer_text=llm_answer,
            citations=citations,
            structured_payload=structured_payload,
            answer_style="llm_synthesized",
            citation_map=citation_map,
        )
    except Exception as exc:
        _file_chat_synthesis_issue(conn, query, query_type, exc)
        return base_response


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
            structured_payload = {
                "name": name,
                "candidate_count": len(profs),
            }
            if llm_synthesis_enabled():
                structured_payload["candidates"] = [
                    {
                        "professor_id": p["professor_id"],
                        "canonical_name": p["canonical_name"],
                        "institution": p.get("institution"),
                        "title": p.get("title"),
                    }
                    for p in profs[:10]
                ]
            return _build_chat_response(
                conn=conn,
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
                structured_payload=structured_payload,
            )
        prof = profs[0]
        topics = _prof_research_topics(conn, prof["professor_id"])
        n_papers = _prof_paper_count(conn, prof["professor_id"])
        return _build_chat_response(
            conn=conn,
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
        structured_payload = {
            "institutions": list(institutions),
            "topic": topic,
            "match_count": rows[0].get("total_count", len(rows)) if rows else 0,
        }
        if llm_synthesis_enabled():
            structured_payload["matched_professors"] = [
                {
                    "professor_id": r["professor_id"],
                    "canonical_name": r["canonical_name"],
                    "institution": r.get("institution"),
                    "matched_topics": r.get("matched_topics") or [],
                }
                for r in rows[:10]
            ]
        return _build_chat_response(
            conn=conn,
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
            structured_payload=structured_payload,
        )

    # Pattern C: "<company>有哪些专利" — patents by applicant
    if m := _Q_PATENT_LIST_RE.search(query):
        company = m.group("company").strip()
        rows = _lookup_patents_by_applicant(conn, company_name=company)
        structured_payload = {
            "company_name_query": company,
            "match_count": rows[0].get("total_count", len(rows)) if rows else 0,
        }
        if llm_synthesis_enabled():
            structured_payload["patents"] = [
                {
                    "patent_id": r["patent_id"],
                    "patent_number": r.get("patent_number"),
                    "title_clean": r.get("title_clean"),
                    "applicants_raw": r.get("applicants_raw"),
                    "filing_date": r.get("filing_date"),
                    "grant_date": r.get("grant_date"),
                    "patent_type": r.get("patent_type"),
                }
                for r in rows[:10]
            ]
        return _build_chat_response(
            conn=conn,
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
            structured_payload=structured_payload,
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
