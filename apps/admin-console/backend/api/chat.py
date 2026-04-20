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
import threading
import time
import uuid
from collections import deque
from typing import Any, Deque, Literal

from fastapi import APIRouter, Cookie, Depends, Response
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


# --- Round 11 v3: LLM query classifier ---
# gemma4 categorizes the user query into one of:
#   A — exact single-entity lookup (介绍X / X有哪些专利 → rule path handles)
#   B — semantic/topic search across SZ institutions (自由描述需求)
#   F — refuse (闲聊/out-of-scope: 天气/股票/情感咨询)
#   UNKNOWN — let the rule engine try; fall through
# D/E deferred to Round 12.

_CLASSIFIER_TIMEOUT = 2.5
_CLASSIFIER_SYSTEM = (
    "你是深圳科创检索助手的查询分类器。把用户一句话归入以下类别，"
    "JSON 输出，不要其他文字：\n"
    '{"type": "A" | "B" | "D" | "E" | "F" | "G" | "UNKNOWN",'
    ' "topic": "", "name": "", "reason": ""}\n'
    "类别定义：\n"
    "A = 精确查询单个教授/公司/专利（有明确姓名+学校/专利号）\n"
    "B = 语义模糊检索教授（如'做机器人的专家'、'研究芯片的教授'）\n"
    "D = 跨域聚合（如'深圳做具身智能的教授和企业有哪些'、'深圳的 AI 生态'——"
    "  想要同时看教授+企业+专利的概览）\n"
    "E = 科创知识问答（如'具身智能合成数据有几种方法'、'大模型蒸馏原理'——"
    "  需要综合知识回答，不是查具体人/公司）\n"
    "F = 闲聊/范围外（天气、股票、情感、违法）\n"
    "G = 歧义查询（只给了人名没给学校，如'介绍王伟'、'李雪芳是谁'）\n"
    "UNKNOWN = 无法判断\n"
    "topic：B/D 给方向词（≤10 字），E 给核心关键词，其他留空。\n"
    "name：A/G 给出教授/公司名，其他留空。"
)


def _classify_query_with_llm(query: str) -> dict[str, str] | None:
    """Return {type, topic, name, reason} or None on error. Caller decides fallback."""
    if os.environ.get("CHAT_QUERY_CLASSIFIER", "on").lower() == "off":
        return None
    settings = resolve_professor_llm_settings("gemma4", include_profile=True)
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings["local_llm_api_key"] or "EMPTY",
        timeout=_CLASSIFIER_TIMEOUT,
    )
    try:
        resp = client.chat.completions.create(
            model=settings["local_llm_model"],
            messages=[
                {"role": "system", "content": _CLASSIFIER_SYSTEM},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
            max_tokens=160,
            extra_body=_CHAT_SYNTHESIS_EXTRA_BODY,
        )
        text = resp.choices[0].message.content or ""
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
        import json
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        t = data.get("type")
        if t not in {"A", "B", "D", "E", "F", "G", "UNKNOWN"}:
            return None
        return {
            "type": t,
            "topic": str(data.get("topic") or "").strip(),
            "name": str(data.get("name") or "").strip(),
            "reason": str(data.get("reason") or "").strip()[:200],
        }
    except Exception:
        return None


_SZ_INSTITUTIONS_ALL = (
    "南方科技大学",
    "清华大学深圳国际研究生院",
    "清华大学深圳研究生院",
    "北京大学深圳研究生院",
    "深圳大学",
    "深圳理工大学",
    "哈尔滨工业大学（深圳）",
    "香港中文大学（深圳）",
    "中山大学（深圳）",
    "深圳技术大学",
    "中国科学院深圳先进技术研究院",
)


def _answer_refuse(query: str, reason: str) -> str:
    return (
        "这个问题超出了深圳科创检索助手的范围。\n"
        "我能帮你查：深圳 11 所高校的教授、1000+ 科创企业、7000+ 论文、专利。\n"
        "试试换个科创相关的问题？"
    )


# --- Round 11 v3.1: D/E/G handlers ---


def _lookup_companies_by_topic(conn: Any, *, topic: str) -> list[dict]:
    like = f"%{topic}%"
    return conn.execute(
        """
        SELECT c.company_id, c.canonical_name,
               latest.industry, latest.business,
               count(*) OVER ()::int AS total_count
          FROM company c
          JOIN LATERAL (
            SELECT cs.industry, cs.business, cs.description
              FROM company_snapshot cs
             WHERE cs.company_id = c.company_id
             ORDER BY cs.snapshot_created_at DESC NULLS LAST
             LIMIT 1
          ) latest ON true
         WHERE c.is_shenzhen = true
           AND (
             latest.industry ILIKE %s
             OR latest.business ILIKE %s
             OR latest.description ILIKE %s
           )
         ORDER BY c.canonical_name
         LIMIT 15
        """,
        (like, like, like),
    ).fetchall()


def _answer_cross_domain(topic: str, profs: list[dict], companies: list[dict]) -> str:
    """D — 3-section cross-domain summary."""
    p_total = profs[0].get("total_count", len(profs)) if profs else 0
    c_total = companies[0].get("total_count", len(companies)) if companies else 0
    lines = [f"深圳 {topic} 生态全景："]
    lines.append("")
    lines.append(f"▎ 教授（{p_total} 位）：")
    if profs:
        for r in profs[:5]:
            lines.append(f"  • {r['canonical_name']} — {r['institution']}")
        if p_total > 5:
            lines.append(f"  ... 还有 {p_total - 5} 位")
    else:
        lines.append("  （本地库未命中）")
    lines.append("")
    lines.append(f"▎ 企业（{c_total} 家）：")
    if companies:
        for r in companies[:5]:
            bits = [r['canonical_name']]
            if r.get('industry'): bits.append(r['industry'])
            lines.append(f"  • {' — '.join(bits[:2])}")
        if c_total > 5:
            lines.append(f"  ... 还有 {c_total - 5} 家")
    else:
        lines.append("  （本地库未命中）")
    return "\n".join(lines)


_KNOWLEDGE_QA_SYSTEM = (
    "你是深圳科创信息检索助手。用户问了一个科创领域的知识性问题，"
    "本地数据库无法直接回答。基于你的知识做一个 3-5 句的简明回答。规则：\n"
    "(1) 中文，简洁，不列 bullet。\n"
    "(2) 不要编造具体人名/机构/数字。\n"
    "(3) 回答末尾加标注：（综合自 AI 推理，非本地数据库结果）"
)


def _answer_knowledge_qa(query: str) -> tuple[str, str | None]:
    """E — LLM knowledge answer with explicit disclaimer. No web search yet
    (Round 12 follow-up). Returns (answer_text, error_or_None)."""
    try:
        settings = resolve_professor_llm_settings("gemma4", include_profile=True)
        client = OpenAI(
            base_url=settings["local_llm_base_url"],
            api_key=settings["local_llm_api_key"] or "EMPTY",
            timeout=5.0,
        )
        resp = client.chat.completions.create(
            model=settings["local_llm_model"],
            messages=[
                {"role": "system", "content": _KNOWLEDGE_QA_SYSTEM},
                {"role": "user", "content": query},
            ],
            temperature=0.3,
            max_tokens=400,
            extra_body=_CHAT_SYNTHESIS_EXTRA_BODY,
        )
        answer = (resp.choices[0].message.content or "").strip()
        if not answer:
            return ("LLM 返回空回答。", "empty")
        if "AI 推理" not in answer and "非本地" not in answer:
            answer += "\n\n（综合自 AI 推理，非本地数据库结果）"
        return (answer, None)
    except Exception as exc:
        return (f"知识问答失败：{exc}", str(exc))


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
# Round 10 v2 — follow-up query patterns once context pins a prof.
# Name is non-greedy ({2,20}?) and the connector (的/发了/有) is required so
# the name class doesn't swallow the 的 connector.
_Q_PROF_PAPERS_RE = re.compile(
    r"^(?P<name>[\u4e00-\u9fff A-Za-z.-]{2,20}?)\s*(的|发了(哪些)?|有(哪些|什么))\s*(论文|文章|paper)s?\s*$",
    re.IGNORECASE,
)
_Q_PROF_TOPICS_RE = re.compile(
    r"^(?P<name>[\u4e00-\u9fff A-Za-z.-]{2,20}?)\s*的\s*(研究方向|研究领域|研究)\s*(是什么|有哪些)?\s*$"
)


# --- Round 10 v2: multi-turn context ---
# In-memory session store. Keyed by an opaque session_id we hand back via
# cookie. Each SessionContext keeps the last few entities and turns so we
# can resolve pronouns ("他"/"她"/"这位教授") to the most-recently-mentioned
# professor. Process-local only — lost on restart. A future iteration
# could persist to Postgres or Redis for HA.

_SESSION_COOKIE = "miroflow_chat_session"
_SESSION_TTL_SECONDS = 24 * 3600
_SESSION_MAX_ENTITIES = 5
_SESSION_MAX_TURNS = 5
_SESSION_PRONOUNS_RE = re.compile(
    r"(他|她|这位(?:教授|老师|学者)?|该(?:教授|学者)|上面那位)"
)
_SESSIONS_LOCK = threading.Lock()
_SESSIONS: dict[str, "SessionContext"] = {}


class SessionEntity(BaseModel):
    kind: Literal["professor", "paper", "patent", "company"]
    id: str
    label: str


class SessionContext:
    """Per-session state. Not a Pydantic model to allow mutable deque usage."""

    __slots__ = ("session_id", "entities", "turns", "last_seen_at")

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.entities: Deque[SessionEntity] = deque(maxlen=_SESSION_MAX_ENTITIES)
        self.turns: Deque[dict[str, Any]] = deque(maxlen=_SESSION_MAX_TURNS)
        self.last_seen_at = time.time()

    def push_entity(self, entity: SessionEntity) -> None:
        # Drop existing copies so the most-recent mention lands at the end
        self.entities = deque(
            [e for e in self.entities if not (e.kind == entity.kind and e.id == entity.id)],
            maxlen=_SESSION_MAX_ENTITIES,
        )
        self.entities.append(entity)

    def latest_professor(self) -> SessionEntity | None:
        for e in reversed(self.entities):
            if e.kind == "professor":
                return e
        return None

    def push_turn(self, query: str, query_type: str, answer_text: str) -> None:
        self.turns.append({
            "query": query,
            "query_type": query_type,
            "answer_text": answer_text[:300],  # trim for memory hygiene
            "at": time.time(),
        })


def _get_or_create_session(session_id: str | None) -> SessionContext:
    with _SESSIONS_LOCK:
        now = time.time()
        # Opportunistic cleanup: drop stale sessions (cheap since we're holding the lock)
        stale = [
            k for k, ctx in _SESSIONS.items()
            if now - ctx.last_seen_at > _SESSION_TTL_SECONDS
        ]
        for k in stale:
            _SESSIONS.pop(k, None)

        if session_id and session_id in _SESSIONS:
            ctx = _SESSIONS[session_id]
            ctx.last_seen_at = now
            return ctx
        new_id = session_id or uuid.uuid4().hex
        ctx = SessionContext(new_id)
        _SESSIONS[new_id] = ctx
        return ctx


def _rewrite_query_with_context(query: str, session: SessionContext) -> str:
    """If the query has pronouns and session has a pinned professor, splice
    the prof's canonical_name in. Heuristic but covers the common case."""
    if not _SESSION_PRONOUNS_RE.search(query):
        return query
    prof = session.latest_professor()
    if not prof:
        return query
    rewritten = _SESSION_PRONOUNS_RE.sub(prof.label, query)
    return rewritten


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


def _lookup_verified_papers_for_prof(conn: Any, *, professor_id: str) -> list[dict]:
    return conn.execute(
        """
        SELECT p.paper_id, p.title_clean, p.year, p.venue, p.citation_count,
               ppl.topic_consistency_score,
               count(*) OVER ()::int AS total_count
          FROM professor_paper_link ppl
          JOIN paper p ON p.paper_id = ppl.paper_id
         WHERE ppl.professor_id = %s AND ppl.link_status = 'verified'
         ORDER BY p.year DESC NULLS LAST, p.citation_count DESC NULLS LAST
         LIMIT 20
        """,
        (professor_id,),
    ).fetchall()


def _answer_prof_papers(prof: dict, rows: list[dict]) -> str:
    name = prof["canonical_name"]
    if not rows:
        return f"{name} 目前没有 verified 论文。"
    total = rows[0].get("total_count", len(rows))
    lines = [
        f"{name} 共有 {total} 篇已验证论文（显示前 {min(len(rows), 10)} 篇）：",
        "",
    ]
    for r in rows[:10]:
        y = r.get("year") or "?"
        venue = r.get("venue") or ""
        lines.append(f"  • {y} | {r['title_clean'][:80]} | {venue[:40]}")
    return "\n".join(lines)


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    response: Response,
    miroflow_chat_session: str | None = Cookie(default=None),
    conn: Any = Depends(get_pg_conn),
) -> ChatResponse:
    # --- Round 10 v2: session + pronoun rewrite ---
    session = _get_or_create_session(miroflow_chat_session)
    if session.session_id != miroflow_chat_session:
        response.set_cookie(
            _SESSION_COOKIE,
            session.session_id,
            max_age=_SESSION_TTL_SECONDS,
            httponly=True,
            samesite="lax",
        )
    raw_query = payload.query.strip()
    query = _rewrite_query_with_context(raw_query, session)

    def _record_and_return(chat_resp: ChatResponse) -> ChatResponse:
        """Push the primary entity from this response onto the session stack."""
        sp = chat_resp.structured_payload or {}
        prof_id = sp.get("professor_id")
        prof_name = sp.get("canonical_name")
        if prof_id and prof_name:
            session.push_entity(SessionEntity(
                kind="professor", id=prof_id, label=prof_name
            ))
        session.push_turn(raw_query, chat_resp.query_type, chat_resp.answer_text)
        return chat_resp

    # Pattern D' (v2): "<name>的研究方向" — follow-up on a pinned professor
    if m := _Q_PROF_TOPICS_RE.search(query):
        name = m.group("name").strip()
        profs = _lookup_professor(conn, name=name, institutions=None)
        if len(profs) == 1:
            prof = profs[0]
            topics = _prof_research_topics(conn, prof["professor_id"])
            topic_text = (
                "、".join(topics[:10])
                if topics
                else "(暂无已记录的研究方向)"
            )
            return _record_and_return(_build_chat_response(
                conn=conn,
                query=raw_query,
                query_type="D_prof_topics_followup",
                answer_text=f"{prof['canonical_name']} 的研究方向包括：{topic_text}",
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
                    "research_topics": topics,
                },
            ))

    # Pattern D (v2): "<name>的论文" — follow-up on a pinned professor
    if m := _Q_PROF_PAPERS_RE.search(query):
        name = m.group("name").strip()
        profs = _lookup_professor(conn, name=name, institutions=None)
        if len(profs) == 1:
            prof = profs[0]
            papers = _lookup_verified_papers_for_prof(
                conn, professor_id=prof["professor_id"]
            )
            structured_payload = {
                "professor_id": prof["professor_id"],
                "canonical_name": prof["canonical_name"],
                "paper_count": papers[0]["total_count"] if papers else 0,
                "papers": [
                    {
                        "paper_id": p["paper_id"],
                        "title": p["title_clean"],
                        "year": p["year"],
                        "venue": p["venue"],
                    }
                    for p in papers[:10]
                ],
            }
            return _record_and_return(
                _build_chat_response(
                    conn=conn,
                    query=raw_query,
                    query_type="D_prof_papers_followup",
                    answer_text=_answer_prof_papers(prof, papers),
                    citations=[
                        ChatCitation(
                            type="paper",
                            id=p["paper_id"],
                            label=f"{p.get('year') or '?'} · {p['title_clean'][:80]}",
                            url=f"/browse#paper/{p['paper_id']}",
                        )
                        for p in papers[:10]
                    ],
                    structured_payload=structured_payload,
                )
            )

    # Pattern A: "介绍<inst>的<name>" — single professor profile
    if m := _Q_PROFILE_RE.search(query):
        name = m.group("name")
        inst_fragment = m.group("inst") or ""
        institutions = _resolve_institution(inst_fragment)
        profs = _lookup_professor(conn, name=name, institutions=institutions)
        if not profs:
            # If we had an institution filter, commit to "not found" — the
            # user was specific. If no inst filter, fall through to the
            # classifier (which may route to G for common names like 王伟
            # that don't exactly match canonical_name — the name might be
            # in aliases / need Latin-pinyin mapping / a typo).
            if institutions is not None:
                return ChatResponse(
                    query=query,
                    query_type="A_prof_profile",
                    answer_text=f"没有找到{inst_fragment or ''}的{name}。",
                    citations=[],
                )
            # else: fall through silently (no matching rule, let classifier try)
        # Only run the match-handling branches when we have at least one prof.
        # Empty profs here means "fall through to classifier" (set above).
        elif len(profs) > 1 and institutions is None:
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
        elif profs:
            prof = profs[0]
            topics = _prof_research_topics(conn, prof["professor_id"])
            n_papers = _prof_paper_count(conn, prof["professor_id"])
            return _record_and_return(_build_chat_response(
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
            ))

    # Pattern B: "<inst>做<topic>的教授" — list professors by topic + institution
    # If inst doesn't resolve (e.g. user wrote "深圳" / "南方" / "亚洲"), fall
    # through to the v3 classifier at end of endpoint rather than returning
    # a helpless "未能识别" — classifier may reroute as B semantic search.
    if (m := _Q_TOPIC_LIST_RE.search(query)) and (
        _resolve_institution(m.group("inst")) is not None
    ):
        inst_fragment = m.group("inst")
        topic = m.group("topic").strip()
        institutions = _resolve_institution(inst_fragment)
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

    # Round 11 v3 / v3.1: no rule pattern matched — ask LLM classifier
    classification = _classify_query_with_llm(query)
    if classification:
        ctype = classification["type"]
        topic = classification["topic"]
        name = classification["name"]
        reason = classification["reason"]

        if ctype == "F":
            return _record_and_return(ChatResponse(
                query=raw_query,
                query_type="F_out_of_scope",
                answer_text=_answer_refuse(raw_query, reason),
                citations=[],
                structured_payload={"classifier_reason": reason},
            ))

        if ctype == "B" and topic:
            rows = _lookup_professors_by_topic(
                conn, institutions=_SZ_INSTITUTIONS_ALL, topic=topic
            )
            return _record_and_return(_build_chat_response(
                conn=conn,
                query=raw_query,
                query_type="B_semantic_topic_search",
                answer_text=_answer_prof_list(_SZ_INSTITUTIONS_ALL, topic, rows),
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
                    "classifier_topic": topic,
                    "classifier_reason": reason,
                    "match_count": rows[0].get("total_count", len(rows)) if rows else 0,
                },
            ))

        if ctype == "D" and topic:
            # 跨域聚合: 教授 + 企业（专利留下一轮，目前 patent 表空）
            profs = _lookup_professors_by_topic(
                conn, institutions=_SZ_INSTITUTIONS_ALL, topic=topic
            )
            companies = _lookup_companies_by_topic(conn, topic=topic)
            citations: list[ChatCitation] = []
            for r in profs[:5]:
                citations.append(ChatCitation(
                    type="professor", id=r["professor_id"],
                    label=f"{r['canonical_name']} - {r['institution']}",
                    url=f"/browse#professor/{r['professor_id']}",
                ))
            for r in companies[:5]:
                citations.append(ChatCitation(
                    type="company", id=r["company_id"],
                    label=f"{r['canonical_name']} - {r.get('industry') or ''}",
                    url=f"/browse#company/{r['company_id']}",
                ))
            return _record_and_return(ChatResponse(
                query=raw_query,
                query_type="D_cross_domain_topic",
                answer_text=_answer_cross_domain(topic, profs, companies),
                citations=citations,
                structured_payload={
                    "topic": topic,
                    "classifier_reason": reason,
                    "prof_count": profs[0].get("total_count", len(profs)) if profs else 0,
                    "company_count": companies[0].get("total_count", len(companies)) if companies else 0,
                },
            ))

        if ctype == "E":
            answer, err = _answer_knowledge_qa(raw_query)
            return _record_and_return(ChatResponse(
                query=raw_query,
                query_type="E_knowledge_qa",
                answer_text=answer,
                citations=[],
                structured_payload={
                    "classifier_reason": reason,
                    "llm_error": err,
                },
            ))

        if ctype == "G" and name:
            # 歧义名：直接复用 _lookup_professor（no institution filter）
            profs = _lookup_professor(conn, name=name, institutions=None)
            if len(profs) == 0:
                return _record_and_return(ChatResponse(
                    query=raw_query,
                    query_type="G_ambiguous_not_found",
                    answer_text=f"没有找到名为 {name!r} 的教授。",
                    citations=[],
                    structured_payload={"name": name, "classifier_reason": reason},
                ))
            if len(profs) == 1:
                prof = profs[0]
                topics = _prof_research_topics(conn, prof["professor_id"])
                n_papers = _prof_paper_count(conn, prof["professor_id"])
                return _record_and_return(_build_chat_response(
                    conn=conn,
                    query=raw_query,
                    query_type="A_prof_profile",
                    answer_text=_answer_prof_profile(prof, topics, n_papers),
                    citations=[ChatCitation(
                        type="professor",
                        id=prof["professor_id"],
                        label=f"{prof['canonical_name']} - {prof.get('institution') or '单位未知'}",
                        url=f"/browse#professor/{prof['professor_id']}",
                    )],
                    structured_payload={
                        "professor_id": prof["professor_id"],
                        "canonical_name": prof["canonical_name"],
                        "institution": prof.get("institution"),
                        "research_topics": topics,
                        "verified_paper_count": n_papers,
                    },
                ))
            return _record_and_return(ChatResponse(
                query=raw_query,
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
                    "classifier_reason": reason,
                },
            ))

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
