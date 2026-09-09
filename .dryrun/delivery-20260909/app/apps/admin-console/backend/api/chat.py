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

import json
import logging
import os
import re
import time
from typing import Any, Literal, cast
from urllib.parse import urlparse

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from openai import OpenAI
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from backend.api.canonical_v2_chat import router as canonical_v2_chat_router
from backend.api.chat_contracts import (
    CandidateOption,
    ChatCitation,
    ChatFeedbackRequest,
    ChatFeedbackResponse,
    ChatRequest,
    ChatResponse,
    ChatSessionResetResponse,
    ClarificationPayload,
)
from backend.deps import (
    _get_reranker_client,
    _get_web_search_provider,
    chat_e_web_fallback_threshold,
    chat_use_retrieval_service,
    get_pg_conn,
    get_retrieval_service,
)
from backend.services.web_search_cache import (
    WebSearchCache,
    answer_knowledge_qa_with_web_search,
)
from backend.services.chat_context import (
    ChipPredicate,
    SetReferent,
    answer_company_profile as _answer_company_profile,
    answer_narrowed_results,
    answer_paper_profile as _answer_paper_profile,
    answer_patent_profile as _answer_patent_profile,
    detect_chip_predicate,
    detect_set_operation,
    detect_set_referent,
    domain_id_key,
    evaluate_chip_predicate,
    infer_a_target_domain,
    looks_like_narrowing_query,
    lookup_company as _lookup_company,
    lookup_paper as _lookup_paper,
    lookup_patent as _lookup_patent,
    normalize_narrowing_topic,
    result_ids_by_domain,
)
from backend.storage.chat_session import SessionStore
from src.data_agents.professor.llm_profiles import (
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)
from src.data_agents.service.retrieval import Evidence

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

_CHAT_SYNTHESIS_TIMEOUT_SECONDS = float(os.environ.get("CHAT_SYNTHESIS_TIMEOUT", "60.0"))
_CHAT_SYNTHESIS_REPORTED_BY = "round_9_p1_v1_chat_synthesis"
_CHAT_FEEDBACK_REPORTED_BY = "chat_user_feedback"
_COMPANY_TOPIC_GENERIC_AI_GROUP = ("AI", "人工智能", "智能")
_COMPANY_TOPIC_GENERIC_AI_TERMS = frozenset(_COMPANY_TOPIC_GENERIC_AI_GROUP)
_COMPANY_TOPIC_STEP1_TARGET_COUNT = 10
_COMPANY_TOPIC_SPECIFICITY_TOP_K = 5
_COMPANY_TOPIC_SELECTION_MAX_COUNT = 15
_COMPANY_TOPIC_SPECIFICITY_REASON = "高主题相关度(具体主题词 top-K)"
_PROFESSOR_TOPIC_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "视触觉": ("触觉", "视触", "haptic", "tactile", "visuotactile"),
    "触觉": ("haptic", "tactile"),
    "灵巧手": ("dexterous",),
    "具身智能": ("embodied",),
    "机器人": ("robot", "robotic"),
}
_PROFESSOR_TOPIC_STOPWORDS = (
    "有哪些",
    "有那些",
    "有什么",
    "有谁",
    "哪位",
    "哪些",
    "请问",
    "一下",
    "清华大学深圳国际研究生院",
    "清华大学深圳研究生院",
    "清华大学深圳",
    "清华深圳",
    "清华",
    "深圳",
    "大学",
    "学院",
    "教授",
    "研究员",
    "老师",
    "学者",
    "专家",
    "研究方向",
    "方向",
    "领域",
    "相关",
    "研究",
    "做",
    "的",
)
_CHAT_SYNTHESIS_SYSTEM_PROMPT = (
    "你是深圳科创信息检索助手。基于下面的证据回答用户问题。规则："
    "(1) 只使用证据中出现的事实，不要编造；证据不足以回答时直说\"证据不足以回答\"。"
    "(2) 每个事实用 [N] 标注来源编号，每个标记只写一个编号(不要合并成 [1,2,3])。"
    "(3) 回答用中文，结构清晰、信息完整：人物/企业画像用多字段呈现"
    "(基本信息、技术或产品、核心亮点等)；列表类问题逐条列出关键对象及其要点，"
    "可使用编号或项目符号；优先覆盖证据中最相关、最具代表性的对象，不要遗漏重要条目。"
)

# --- Intent-aware structured synthesis prompts (comprehensive coverage enforcement) ---

_CHAT_SYNTHESIS_PROMPT_PROFILE = (
    "你是深圳科创信息检索助手。基于下面的证据全面回答用户问题。\n"
    "规则：\n"
    "(1) 只使用证据中出现的事实，不要编造；具体人名/机构/数字必须来自证据并用[N]标注。\n"
    "(2) 你收到了 {n} 条证据。回答必须覆盖每条证据的关键信息，不要遗漏。\n"
    "(3) 回答参考以下结构组织（从证据中填充有内容的节；无证据的节直接跳过，不要写'证据不足'）：\n"
    "    ## 基本信息：名称、机构/单位、职位/行业\n"
    "    ## 核心技术或产品：主要技术方向/产品/研究方向\n"
    "    ## 履历或团队：教育/工作经历/创始团队\n"
    "    ## 成就或荣誉：奖项/学术兼职/融资/市场地位\n"
    "    ## 其他亮点：科研进展/近期动态/行业评价\n"
    "(4) 用中文，结构清晰，信息完整。优先呈现证据中最丰富的方面。"
)

_CHAT_SYNTHESIS_PROMPT_LIST = (
    "你是深圳科创信息检索助手。基于下面的证据回答用户问题。\n"
    "规则：\n"
    "(1) 只使用证据中出现的事实，不要编造；每个实体用[N]标注。\n"
    "(2) **只列出与问题直接相关的实体**。'直接相关' = 实体的**核心产品/业务/研究方向属于问题所问类别**"
    "（即使该实体同时服务其它领域）。例：问'PCB厂商'→核心业务是印制电路板制造的（鹏鼎/深南电路）=直接相关；"
    "核心是 PCB 组装设备/元件（插件机/回流焊）=邻接，不列主清单。"
    "问'酒店送餐机器人供应商'→核心业务是配送/送餐机器人且服务酒店/餐饮场景的（普渡/擎朗）=直接相关，"
    "即使也服务医疗/工业。问'做视触觉的教授'→研究方向含视触觉/触觉智能/视觉感知的=直接相关。"
    "邻接但不直接匹配的（核心业务属另一类别、仅提到关键词）→末尾'相关但非直接匹配'简述或省略。\n"
    "(3) 每个直接相关实体列出：名称、与问题直接相关的关键特征/要点（引用其研究方向/产品等）。\n"
    "(4) **去重**：跨来源（数据库与网络）出现同一实体时合并为一条。\n"
    "(5) 若证据中无直接相关实体：**干净拒答**——说明'未找到直接匹配的 X'，"
    "可简述最接近的及缺什么。**绝不**把无关实体凑数列出。\n"
    "(6) 用中文，编号或项目符号，主清单只含直接相关实体。"
)

_CHAT_SYNTHESIS_PROMPT_QA = (
    "你是深圳科创信息检索助手。用户问了一个科创领域的知识性问题。\n"
    "规则：\n"
    "(1) 基于证据和你的领域知识回答。具体人名/机构/数字必须来自证据并用[N]标注，不要编造。\n"
    "(2) 你收到了 {n} 条证据。回答必须覆盖每条证据的关键信息。\n"
    "(3) 通用概念/方法/分类/趋势可使用你的领域知识，标注'（行业一般认知）'。\n"
    "(4) 回答参考以下结构组织（有内容的节展开；无证据的节跳过，不要写'证据不足'）：\n"
    "    ## 概念定义：问题涉及的核心概念\n"
    "    ## 主要方法或分类：技术路线/方法/类型的逐一列举\n"
    "    ## 代表企业或学者：每个路线/方法的代表\n"
    "    ## 技术对比：各路线/方法的优劣/差异\n"
    "    ## 发展趋势：行业方向\n"
    "(5) 用中文，结构清晰。回答末尾标注：（综合自网络搜索和AI分析，非本地数据库结果）"
)

_CHAT_SYNTHESIS_PROMPT_PAPER = (
    "你是深圳科创信息检索助手。基于下面的证据全面回答关于论文的问题。\n"
    "规则：\n"
    "(1) 只使用证据中出现的事实，不要编造；具体数据/方法用[N]标注。\n"
    "(2) 你收到了 {n} 条证据。回答必须覆盖每条证据的关键信息，不要遗漏。\n"
    "(3) 回答参考以下结构组织（有内容的节展开；无证据的节跳过）：\n"
    "    ## 基本信息：论文标题、发表年份、会议/期刊、作者\n"
    "    ## 研究摘要：核心问题、解决思路、主要贡献\n"
    "    ## 技术方案：具体方法/算法/创新点（从摘要中提取）\n"
    "    ## 实验结果：性能/效果/对比（如有）\n"
    "(4) 用中文，结构清晰。摘要部分务必详细展开。"
)

_CHAT_SYNTHESIS_PROMPT_PATENT = (
    "你是深圳科创信息检索助手。基于下面的证据全面回答关于专利的问题。\n"
    "规则：\n"
    "(1) 只使用证据中出现的事实，不要编造；具体专利号/申请人/技术用[N]标注。\n"
    "(2) 你收到了 {n} 条证据。回答必须覆盖每条证据的关键信息，不要遗漏。\n"
    "(3) 回答参考以下结构组织（有内容的节展开；无证据的节跳过）：\n"
    "    ## 专利概览：专利号、标题、申请人/发明人\n"
    "    ## 技术摘要：核心技术方案/技术效果\n"
    "    ## 技术领域：IPC分类/应用场景\n"
    "    ## 专利列表（如有多个）：逐条列出每个专利的标题+摘要要点\n"
    "(4) 用中文，结构清晰。"
)

# Knowledge keywords that force qa-intent even if query_type isn't E.
_KNOWLEDGE_INTENT_KEYWORDS = frozenset({
    "几种", "多少种", "路线", "方式", "方法", "原理", "分类", "类型",
    "区别", "趋势", "发展", "什么是", "如何实现", "具体方式", "对比",
})


def _detect_answer_intent(query: str, query_type: str, structured_payload: dict) -> str:
    """Detect synthesis intent: 'profile' | 'list' | 'qa'.
    Derives from query_type prefixes + knowledge keywords."""
    if query_type and query_type.startswith("E_"):
        return "qa"
    # Knowledge keywords force qa even for non-E routing
    if any(kw in query for kw in _KNOWLEDGE_INTENT_KEYWORDS):
        return "qa"
    if query_type and (query_type.startswith("A_patent") or structured_payload.get("patent_id")):
        return "patent"
    if query_type and query_type.startswith("A_paper"):
        return "paper_profile"
    if query_type and query_type.startswith("A_"):
        return "profile"
    if query_type and (query_type.startswith("B_") or query_type.startswith("C_") or query_type.startswith("D_")):
        return "list"
    # Check structured_payload for entity-id (profile) vs matched list
    if structured_payload.get("professor_id") or structured_payload.get("company_id") or structured_payload.get("paper_id"):
        return "profile"
    if structured_payload.get("matched_professors") or structured_payload.get("matched_objects"):
        return "list"
    return "list"  # default to list (safer than profile for unknown)


def _chat_synthesis_extra_body(model_name: str | None) -> dict[str, Any]:
    return build_non_thinking_extra_body(model_name)


_SCHOLARLY_DOMAINS = frozenset(
    {
        "arxiv.org",
        "doi.org",
        "acm.org",
        "ieee.org",
        "nature.com",
        "science.org",
        "sciencedirect.com",
        "springer.com",
        "openreview.net",
        "semanticscholar.org",
        "pubmed.ncbi.nlm.nih.gov",
        "ncbi.nlm.nih.gov",
        "biorxiv.org",
        "medrxiv.org",
    }
)


def _configured_admin_frontend_base_url() -> str:
    return (
        os.environ.get("ADMIN_CONSOLE_PUBLIC_BASE_URL")
        or os.environ.get("ADMIN_FRONTEND_BASE_URL")
        or os.environ.get("FRONTEND_PUBLIC_BASE_URL")
        or ""
    ).rstrip("/")


def _local_record_detail_url(domain: str, record_id: str) -> str:
    path = f"/{domain}/{record_id}"
    base_url = _configured_admin_frontend_base_url()
    return f"{base_url}{path}" if base_url else path


def _local_paper_detail_url(paper_id: str) -> str:
    return _local_record_detail_url("paper", paper_id)


# --- Round 11 v3: LLM query classifier ---
# The configured LLM categorizes the user query into one of A/B/C/D/E/F/G.
# UNKNOWN lets the rule engine try, then fall through.

QueryType = Literal["A", "B", "C", "D", "E", "F", "G", "UNKNOWN"]
TargetDomain = Literal["professor", "paper", "company", "patent"]


class ClassifyResult(BaseModel):
    type: QueryType
    topic: str = ""
    name: str = ""
    target_domain: TargetDomain | None = None
    reason: str = ""


_CLASSIFIER_TIMEOUT = 2.5
_CLASSIFIER_TYPES = {"A", "B", "C", "D", "E", "F", "G", "UNKNOWN"}
_TARGET_DOMAINS = {"professor", "paper", "company", "patent"}
_SZ_INSTITUTION_HINTS = (
    "清华",
    "清华大学深圳",
    "清华深圳",
    "南科大",
    "南方科技大学",
    "北大",
    "北大深研院",
    "北京大学深圳",
    "深大",
    "深圳大学",
    "哈工大深圳",
    "哈尔滨工业大学深圳",
    "港中大深圳",
    "香港中文大学深圳",
    "中山大学深圳",
    "深圳理工",
    "深圳理工大学",
    "深圳技术大学",
    "先进院",
    "深先院",
    "中国科学院深圳先进技术研究院",
)
_CLASSIFIER_CONTEXT_RE = re.compile(
    r"^(他|她|这个|这位|该|这家|这些|上述|上面|这几项|这篇)"
)
_TOPIC_SWITCH_PREFIX_RE = re.compile(
    r"^\s*(?:对了|另外|另一个问题|换个话题|换一个话题|再问一个|再问下|顺便问下|顺便问一下)[，,、\s]*"
)
_CLASSIFIER_OUT_OF_SCOPE_RE = re.compile(r"(写一首诗|天气|翻译|黄赌毒|赌博|色情|毒品|吸毒|嫖娼|卖淫|非法交易|违禁品)")
_CLASSIFIER_KNOWLEDGE_RE = re.compile(
    r"(几种实现方法|有什么不同|具体方式|基本原理|为什么|原理是什么|数据需求)"
)
_CLASSIFIER_CN_PATENT_RE = re.compile(
    r"\b(?:CN|US|EP|WO)\d[A-Z0-9.]{2,}\b",
    re.IGNORECASE,
)
_CLASSIFIER_SYSTEM = (
    "你是深圳科创检索助手的查询分类器。把用户一句话归入以下类别，"
    "JSON 输出，不要其他文字：\n"
    '{"type": "A" | "B" | "C" | "D" | "E" | "F" | "G" | "UNKNOWN",'
    ' "topic": "", "name": "", "target_domain": "", "reason": ""}\n'
    "类别定义：\n"
    "A = 精确查询单个教授/公司/专利/论文（明确指向一个实体；"
    "可问简介、成果、专利、作者、核心技术、业务、布局）\n"
    "B = 单域语义检索（按主题/技术/服务找教授、公司、论文或专利；"
    "地域/机构/产业限定不改变 B，只需填 target_domain）\n"
    "C = 跨域跳转（用户在已有上下文的教授/公司/论文/专利基础上，"
    "追问另一个域的关联实体；如'他的论文'、'她参与的公司'、"
    "'这家公司的专利'）。输出 target_domain: "
    '"professor" | "paper" | "company" | "patent"；目标模糊时优先 "paper"。\n'
    "D = 跨域聚合（同一句明确要多个实体类型，或要教授+企业+论文+专利等全景；"
    "不是单纯'地域 + 产业/技术'组合）\n"
    "E = 科创知识问答（如'具身智能合成数据有几种方法'、'大模型蒸馏原理'——"
    "  需要综合知识回答，不是查具体人/公司）\n"
    "F = 闲聊/范围外（天气、股票、情感、违法）\n"
    "G = 歧义查询（只给人名/简称/近名企业，常见模板为'介绍 X'、'X 是谁'、"
    "'X 的相关信息'，需要先列候选或默认高置信候选）\n"
    "UNKNOWN = 无法判断\n"
    "topic：B/D 给方向词（≤10 字），E 给核心关键词，其他留空。\n"
    "name：A/G 给出教授/公司名，其他留空。\n"
    "target_domain：C 必填；B/G/A 若明显也填写 professor/paper/company/patent。\n"
    "边界：C 需要依赖上文代词/指代；若本句已明确给出实体名，则通常是 A 或 G，不是 C。\n"
    "边界：E 是技术原理/方法解释；若是按主题找本地实体列表则是 B。\n"
    "示例：Q: '介绍清华的丁文伯' → type A, name='丁文伯', target_domain='professor'。\n"
    "示例：Q: '他的论文' → type C, target_domain='paper'。\n"
    "示例：Q: '他参与了哪些公司' → type C, target_domain='company'。\n"
    "示例：Q: '深圳哪些公司做激光雷达' → type B, topic='激光雷达', target_domain='company'。\n"
    "示例：Q: '深圳做合成数据平台的企业' → type B, topic='合成数据平台', target_domain='company'。\n"
    "示例：Q: '做脑机接口的深圳团队' → type B, topic='脑机接口', target_domain='company'。\n"
    "示例：Q: '介绍无界智航' → type G, name='无界智航', target_domain='company'。\n"
    "示例：Q: '介绍王伟' → type G, name='王伟', target_domain='professor'。\n"
    "示例：Q: 'X 是谁' → type G。"
)


def _infer_context_source_domain(query: str) -> str | None:
    if re.match(r"^(他|她|这位|该教授|该学者|这位教授|这位老师|这位学者)", query):
        return "professor"
    if re.match(r"^(这家公司|该公司|这家企业|该企业)", query):
        return "company"
    if re.match(r"^(这篇论文|这本论文|该论文)", query):
        return "paper"
    if re.match(r"^(这件专利|该专利)", query):
        return "patent"
    return None


def _infer_context_target_domain(query: str, *, default: str = "paper") -> str:
    """Infer the requested related-object domain, not the pronoun source domain."""
    source_domain = _infer_context_source_domain(query)

    if source_domain == "professor":
        if re.search(r"(公司|企业|创业|创立|参与|任职|成果转化)", query):
            return "company"
        if re.search(r"(专利|发明)", query):
            return "patent"
        if re.search(r"(论文|文章|成果)", query):
            return "paper"
    elif source_domain == "company":
        if re.search(r"(专利|发明)", query):
            return "patent"
        if re.search(r"(教授|专家|学者|研究员|团队|创始人|创办人|负责人)", query):
            return "professor"
        if re.search(r"(论文|文章)", query):
            return "paper"
    elif source_domain == "paper":
        if re.search(r"(作者|谁写|研究团队|教授|专家|学者|研究员)", query):
            return "professor"
        if re.search(r"(公司|企业|产业化|转化)", query):
            return "company"
        if re.search(r"(专利|发明)", query):
            return "patent"
    elif source_domain == "patent":
        if re.search(r"(申请人|哪个公司|哪家公司|公司|企业|所属|属于)", query):
            return "company"
        if re.search(r"(发明人|作者|教授|专家|学者|研究员|团队)", query):
            return "professor"
        if re.search(r"(论文|文章)", query):
            return "paper"

    if re.search(r"(作者|发明人|教授|专家|学者|研究员|团队)", query):
        return "professor"
    if re.search(r"(专利|发明)", query):
        return "patent"
    if re.search(r"(论文|文章)", query):
        return "paper"
    if re.search(r"(申请人|公司|企业|厂商|供应商|平台)", query):
        return "company"
    return default


def _classifier_response(
    query_type: str,
    *,
    topic: str = "",
    name: str = "",
    target_domain: str | None = None,
    reason: str = "deterministic classifier fallback",
) -> dict[str, str]:
    response = {
        "type": query_type,
        "topic": topic.strip(),
        "name": name.strip(),
        "reason": reason,
    }
    if target_domain in _TARGET_DOMAINS:
        response["target_domain"] = target_domain
    return response


def _strip_topic_switch_prefix(query: str) -> str:
    return _TOPIC_SWITCH_PREFIX_RE.sub("", query.strip(), count=1)


def _normalize_query_for_rules(query: str) -> str:
    return re.sub(r"[\s?？。！!]+$", "", query.strip())


def _clean_classifier_topic(query: str) -> str:
    topic = _strip_topic_switch_prefix(query)
    topic = re.sub(r"^(查找|查询|查一下|我想找|找几篇|有没有|有哪些|哪些|深圳有哪些|深圳哪些|中国成熟的)", "", topic)
    topic = re.sub(r"(有哪些|有谁|有什么|推荐|供应商|厂商|企业|公司|教授|专家|学者|团队|论文|专利|方向|领域|代表论文)$", "", topic)
    topic = re.sub(r"^(公司|企业|厂商|供应商|高校教授|教授|专家|学者|团队)\s*", "", topic)
    topic = re.sub(r"^(做|研究|关于|和)\s*", "", topic)
    topic = re.sub(r"(的深圳|深圳高校|深圳|中国|近两年|方向上|方向的)", "", topic)
    topic = re.sub(r"(有哪些|有谁|有什么|推荐|供应商|厂商|企业|公司|教授|专家|学者|团队|论文|专利|方向|领域|代表论文)$", "", topic)
    # Strip residual domain nouns + list connectors anywhere so cross-domain
    # queries reduce to the subject, e.g. "具身智能的教授和企业" -> "具身智能".
    topic = re.sub(
        r"(教授|研究员|专家|学者|团队|企业|公司|厂商|供应商|平台|论文|文章|专利|方向|领域|主题|代表论文|和|、|及|与|等)",
        "",
        topic,
    )
    topic = re.sub(r"的+", "的", topic)
    topic = topic.strip(" ，、的")
    return topic[:80] or query.strip()[:80]


def _infer_classifier_target_domain(query: str, *, default: str = "professor") -> str:
    q = query.casefold()
    if "论文" in q or "paper" in q or "文章" in q:
        return "paper"
    if "专利" in q or _CLASSIFIER_CN_PATENT_RE.search(query):
        return "patent"
    if any(token in query for token in ("公司", "企业", "厂商", "供应商", "平台", "打板")):
        return "company"
    if any(token in query for token in ("教授", "专家", "学者", "高校", "团队", "研究员")):
        return "professor"
    return default


def _extract_professor_name(query: str) -> str:
    q = _normalize_query_for_rules(query)
    q_without_intro = re.sub(
        r"^(?:介绍(?:一下)?|查询|查一下|了解(?:一下)?)\s*",
        "",
        q,
    )
    if re.search(r"(哪些|有哪些|有没有|有谁).*(教授|研究员)", q) or re.search(
        r"(教授|研究员)有哪些$", q
    ):
        return ""
    match = re.search(
        r"^(?:教授|研究员)?\s*(?P<name>[\u4e00-\u9fff]{2,4}?)(?:\s*(?:教授|研究员))?$",
        q_without_intro,
    )
    if match:
        return match.group("name")
    match = re.search(r"(?P<name>[\u4e00-\u9fff]{2,4}?)\s*(教授|研究员)", q_without_intro)
    if match and not re.search(r"(哪些|有哪些|做|研究|高校|深圳|的)$", match.group("name")):
        return match.group("name")
    if re.search(r"(研究方向|研究领域|论文情况|论文)", q) and re.search(
        r"(大学|学院|研究院|高校)",
        q,
    ):
        match = re.match(r"(?P<name>[\u4e00-\u9fff]{2,4})[\s，,：:]+", q)
        if match:
            candidate = match.group("name")
            if not re.search(r"(大学|学院|研究院|高校)", candidate):
                return candidate
    return ""


def _extract_a_name(query: str, target_domain: str) -> str:
    if target_domain == "patent":
        if match := _CLASSIFIER_CN_PATENT_RE.search(query):
            return match.group(0).upper()
        title = re.sub(r"(这件专利|的详情|详细信息是什么|讲的是什么|介绍|摘要|有哪些发明人|法律状态和技术领域|是什么产品)", "", query)
        title = title.replace("专利", "").strip(" ：，。")
        return title[:80]
    if target_domain == "paper":
        if match := re.search(r"《(?P<title>[^》]+)》", query):
            return match.group("title").strip()[:240]
        title = re.sub(
            r"^\s*(?:请|帮我|麻烦)?\s*(?:介绍|查找|查一下|查询|找|看看|看一下)?\s*"
            r"(?:论文|paper)?\s*",
            "",
            query,
            flags=re.IGNORECASE,
        )
        title = title.strip(" ：，。?？\"'“”‘’《》")
        title = re.sub(
            r"(?:这篇|这本|该)?(?:论文|文章|paper)?(?:的)?(?:作者是谁|摘要是什么|摘要和作者|作者和摘要|"
            r"研究内容|主要内容|摘要|作者|主要讲什么|讲了什么|讲的是什么|"
            r"讲什么|主要解决什么问题|主要解决了什么问题|解决什么问题|解决了什么问题|"
            r"主要解决什么|贡献是什么|核心贡献是什么|方法是什么|主要方法是什么|"
            r"是什么|是啥|主要是什么|介绍一下|深圳作者有哪些|最近发了什么论文|有哪些论文|"
            r"论文列表|论文|paper)$",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = title.strip(" ：，。?？\"'“”‘’《》")
        return title[:240]
    if target_domain == "professor":
        return _extract_professor_name(query)
    company = query.strip()
    company = re.sub(r"^(介绍|请介绍|查一下|查找|查询)\s*", "", company)
    # isolate the company name in multi-clause queries: cut at "这家公司/这家企业/该公司"
    company = re.split(r"这家公司|这家企业|该公司|本企业|本家公司", company, maxsplit=1)[0]
    company = re.sub(
        r"(有哪些专利|有什么专利|有哪些机器人产品|有哪些科研成果|"
        r"的技术实力怎么样|在深圳的科创业务介绍|公司画像|的核心技术|"
        r"的专利布局|公司的技术方向|相关信息|"
        r"的产品特点以及团队介绍|的产品特点|团队介绍|产品特点|"
        r"的产品|的团队|团队|产品|的业务|业务|的简介|简介|的介绍|介绍|"
        r"的概况|概况|的画像|画像|的实力|实力|的基本信息|基本信息|"
        r"的详细信息|详细信息|的产品信息|产品信息|怎么样|如何|"
        r"企业(情况|信息|创始人|评价|市场|动态|融资|投资|前景).*$"
        r"|的情况.*$|的创始人.*$|的创始人信息.*$|的市场.*$|的市场评价.*$|的动态.*$)$",
        "",
        company,
    )
    return company.strip(" ：，。")


def _classify_query_by_rules(query: str) -> dict[str, str] | None:
    q = _normalize_query_for_rules(_strip_topic_switch_prefix(query))
    if not q:
        return None
    if _CLASSIFIER_OUT_OF_SCOPE_RE.search(q):
        return _classifier_response("F", reason="out-of-scope deterministic rule")
    if _CLASSIFIER_KNOWLEDGE_RE.search(q):
        return _classifier_response(
            "E",
            topic=_clean_classifier_topic(q),
            reason="knowledge question deterministic rule",
        )
    if _CLASSIFIER_CONTEXT_RE.search(q):
        return _classifier_response(
            "C",
            topic=_clean_classifier_topic(q) if "有关" in q else "",
            target_domain=_infer_context_target_domain(q, default="paper"),
            reason="context-dependent cross-domain deterministic rule",
        )

    domain_hits = sum(
        1
        for token in ("教授", "高校团队", "企业", "公司", "论文", "专利")
        if token in q
    )
    if domain_hits >= 2 and re.search(r"(和|、|全景|生态|布局|趋势)", q):
        return _classifier_response(
            "D",
            topic=_clean_classifier_topic(q),
            reason="multi-domain aggregate deterministic rule",
        )

    if (
        _CLASSIFIER_CN_PATENT_RE.search(q)
        or re.search(r"(这件专利|专利号|外观设计专利)", q)
        or (q.startswith("一种") and "专利" in q)
    ):
        return _classifier_response(
            "A",
            name=_extract_a_name(q, "patent"),
            target_domain="patent",
            reason="exact patent deterministic rule",
        )
    if match := re.match(
        r"^(?P<name>.+?)\s*是\s*哪一?篇\s*(论文|文章|paper)?$",
        q,
        re.IGNORECASE,
    ):
        return _classifier_response(
            "G",
            name=match.group("name").strip(" ：，。?？"),
            target_domain="paper",
            reason="ambiguous paper title deterministic rule",
        )
    if match := re.match(r"^(?P<name>.+?)\s*是\s*哪一?(件|项|条)\s*专利$", q):
        return _classifier_response(
            "G",
            name=match.group("name").strip(" ：，。?？"),
            target_domain="patent",
            reason="ambiguous patent title deterministic rule",
        )
    if re.search(r"(方向|领域|主题|相关)\s*的?\s*(论文|文章|paper)s?$", q, re.IGNORECASE) or (
        # Topic-search intent over papers that does NOT end in 论文: "关于X的论文有哪些" /
        # "X的最新论文" / "找X相关论文". Without this, the exact-paper rule below over-fires
        # (论文 + an ASCII run like 'perovskite') and routes them to A/unknown — the
        # paper-retrievability-baseline Type4 gap (qid109/110 were 0/4).
        re.search(r"(论文|文章|paper)", q, re.IGNORECASE)
        and re.search(r"(关于|有关|哪些|有哪些|有什么|有没有|找|查找|搜索|检索|推荐|最新|最近|相关)", q)
        and not re.match(r"^[A-Za-z][A-Za-z0-9\s:,\-./]{15,}$", q)  # bare EN title -> english-title rule
        and not re.search(r"(教授|研究员|创始人|企业家|公司|企业)", q)  # entity-anchored -> prof/company rules
        and not re.search(r"(作者|团队|发明人)", q)  # paper-author lookup -> A/cross-domain, not topic search
    ):
        return _classifier_response(
            "B",
            topic=_clean_classifier_topic(q),
            target_domain="paper",
            reason="paper topic deterministic rule",
        )
    # bare English paper-title query (e.g. "pFedGPA: Diffusion-based Generative ...")
    # — mostly ASCII, long, looks like a paper title; route to A_paper deterministically
    # (without this, it falls to the LLM classifier which intermittently mis-refuses).
    if (
        re.match(r"^[A-Za-z][A-Za-z0-9\s:,\-./]{15,}$", q)
        and not _CLASSIFIER_KNOWLEDGE_RE.search(q)
        and not _CLASSIFIER_OUT_OF_SCOPE_RE.search(q)
    ):
        return _classifier_response(
            "A",
            name=_extract_a_name(q, "paper"),
            target_domain="paper",
            reason="english paper-title deterministic rule",
        )
    if q.startswith("论文 ") or q.startswith("介绍论文 ") or (
        "论文" in q and re.search(r"[A-Za-z][^\u4e00-\u9fff]{8,}", q)
    ) or re.search(r"[A-Za-z][^\u4e00-\u9fff]{12,}\s*的(研究内容|作者|摘要)", q):
        return _classifier_response(
            "A",
            name=_extract_a_name(q, "paper"),
            target_domain="paper",
            reason="exact paper deterministic rule",
        )
    if match := re.search(r"^介绍\s*(?P<inst>.+?)的(?P<name>[\u4e00-\u9fff]{2,5})$", q):
        if not any(hint in match.group("inst") for hint in _SZ_INSTITUTION_HINTS):
            match = None
    if match:
        return _classifier_response(
            "A",
            name=match.group("name"),
            target_domain="professor",
            reason="institution-qualified professor deterministic rule",
        )
    if re.search(r"(公司|科技|集团|有限|企业)(的)?(产品特点|产量特点|团队介绍|产品特点以及团队介绍|产品|产量|团队|业务|简介|介绍|概况|画像|实力|基本信息|详细信息|产品信息|相关信息|信息|市场竞争力|竞争力|特点|怎么样|如何|情况|创始人|评价|市场|动态|融资|投资|前景)", q):
        return _classifier_response(
            "A",
            name=_extract_a_name(q, "company"),
            target_domain="company",
            reason="company-profile-by-name deterministic rule",
        )
    if re.search(r"(有哪些专利|有什么专利|有哪些机器人产品|有哪些科研成果)", q) and not q.startswith(
        ("哪些", "有哪些", "有没有")
    ):
        return _classifier_response(
            "A",
            name=_extract_a_name(q, "company"),
            target_domain="company",
            reason="exact company deterministic rule",
        )
    if re.search(r"^(介绍)?\s*[\u4e00-\u9fffA-Za-z0-9]{2,12}\s*(是谁|的相关信息)$", q) and not re.search(
        r"(教授|研究员|博导|院士)", q
    ):
        name = re.sub(r"^(介绍)\s*", "", q)
        name = re.sub(r"(是谁|的相关信息)$", "", name).strip()
        target_domain = "company" if len(name) > 3 else "professor"
        return _classifier_response(
            "G",
            name=name,
            target_domain=target_domain,
            reason="ambiguous intro deterministic rule",
        )
    if re.search(r"^介绍\s*[\u4e00-\u9fff]{2,5}$", q):
        name = q.replace("介绍", "").strip()
        target_domain = "company" if len(name) > 3 else "professor"
        return _classifier_response(
            "G",
            name=name,
            target_domain=target_domain,
            reason="ambiguous person intro deterministic rule",
        )
    professor_name = _extract_professor_name(q)
    if professor_name:
        return _classifier_response(
            "A",
            name=professor_name,
            target_domain="professor",
            reason="exact professor deterministic rule",
        )
    if any(hint in q for hint in _SZ_INSTITUTION_HINTS) and re.search(
        r"[\u4e00-\u9fff]{2,4}(教授|研究员)", q
    ):
        professor_name = _extract_professor_name(q)
        if professor_name:
            return _classifier_response(
                "A",
                name=professor_name,
                target_domain="professor",
                reason="institution-qualified professor deterministic rule",
            )

    # Cross-filter professor/people search: an origin/school attribute AND a field plus a
    # person noun (企业家/创始人/学者/...) → type B, domain professor. The explicit
    # target_domain overrides the "企业" substring inside 企业家 (which would otherwise
    # route to company). Rescues queries like "毕业于早稻田，且专注机器人行业的企业家有谁".
    if re.search(
        r"(毕业|毕业于|学校|大学|学院|博士|硕士|校友|师从|出身)",
        q,
    ) and re.search(r"(企业家|创始人|创办人|学者|教授|研究员|团队|人物|有谁)", q):
        return _classifier_response(
            "B",
            topic=_clean_classifier_topic(q),
            target_domain="professor",
            reason="cross-filter professor search deterministic rule",
        )

    if re.search(r"(哪些|有哪些|有没有|查一下|找|推荐|供应商|厂商|专家|代表论文)", q) or re.search(
        r"(深圳)?做.+的?(企业|公司|厂商|论文)", q
    ):
        return _classifier_response(
            "B",
            topic=_clean_classifier_topic(q),
            target_domain=_infer_classifier_target_domain(q),
            reason="semantic list deterministic rule",
        )

    if re.search(r"(公司画像|核心技术|技术实力|科创业务|科研成果|专利布局|技术方向|相关信息|机器人产品|有哪些专利)", q):
        return _classifier_response(
            "A",
            name=_extract_a_name(q, "company"),
            target_domain="company",
            reason="exact company deterministic rule",
        )
    return None


def _classify_query_with_llm(query: str) -> dict[str, str] | None:
    """Return classifier fields or None on error. Caller decides fallback."""
    rule_response = _classify_query_by_rules(query)
    if rule_response is not None:
        return rule_response
    if os.environ.get("CHAT_QUERY_CLASSIFIER", "on").lower() == "off":
        return None
    settings = resolve_professor_llm_settings(None, include_profile=True)
    _clear_proxy_env()
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
            extra_body=_chat_synthesis_extra_body(settings["local_llm_model"]),
        )
        text = resp.choices[0].message.content or ""
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
        import json
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        t = str(data.get("type") or "").strip().upper()
        if t not in _CLASSIFIER_TYPES:
            return None
        target_domain = str(data.get("target_domain") or "").strip().lower()
        if t == "C":
            if target_domain not in _TARGET_DOMAINS:
                target_domain = "paper"
        elif target_domain not in _TARGET_DOMAINS:
            target_domain = None
        result = ClassifyResult(
            type=t,
            topic=str(data.get("topic") or "").strip(),
            name=str(data.get("name") or "").strip(),
            target_domain=target_domain,
            reason=str(data.get("reason") or "").strip()[:200],
        )
        response: dict[str, str] = {
            "type": result.type,
            "topic": result.topic,
            "name": result.name,
            "reason": result.reason,
        }
        if result.target_domain:
            response["target_domain"] = result.target_domain
        return response
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


def _get_web_search_provider_or_none():
    try:
        provider = _get_web_search_provider()
    except Exception as exc:
        logger.warning("Failed to initialize web search provider: %s", exc)
        return None
    if not getattr(provider, "api_key", "").strip():
        return None
    return provider


def _get_reranker_client_or_none():
    try:
        return _get_reranker_client()
    except Exception as exc:
        logger.warning("Failed to initialize reranker client: %s", exc)
        return None


def _rerank_web_organics(
    query: str,
    organics: list[dict],
    reranker,
    top_n: int = 3,
) -> list[dict]:
    """Rerank scholarly organic results via Qwen3-Reranker-8B.

    Returns a list of organic dicts with `rerank_score` added, sorted by
    rerank score desc. On any reranker exception, falls back to the first
    `top_n` organics with `rerank_score=0.5` (preserving input order).
    """
    if not organics:
        return []
    docs = [
        ((o.get("title") or "") + " — " + (o.get("snippet") or "")).strip(" —")
        for o in organics
    ]
    try:
        rerank_results = reranker.rerank(query, docs, top_n=top_n)
    except Exception as exc:
        logger.warning("Web organic rerank failed: %s", exc)
        return [{**o, "rerank_score": 0.5} for o in organics[:top_n]]

    ordered: list[dict] = []
    for result in rerank_results:
        idx = result.index
        if 0 <= idx < len(organics):
            ordered.append({**organics[idx], "rerank_score": result.score})
    return ordered[:top_n]


def _evidence_list_from_retrieval(results: list[Evidence]) -> list[dict]:
    rows: list[dict] = []
    for evidence in results:
        metadata = evidence.metadata or {}
        if evidence.object_type == "professor":
            rows.append(
                {
                    "type": "professor",
                    "id": evidence.object_id,
                    "title": metadata.get("name", ""),
                    "snippet": evidence.snippet,
                    "url": evidence.source_url,
                    "score": evidence.score,
                    "institution": metadata.get("institution", ""),
                    "professor_id": evidence.object_id,
                    "canonical_name": metadata.get("name", ""),
                    "matched_topics": [],
                }
            )
            continue
        if evidence.object_type == "paper":
            title = (
                metadata.get("title_clean")
                or metadata.get("title")
                or metadata.get("paper_id")
                or evidence.object_id
            )
            rows.append(
                {
                    "type": "paper",
                    "id": evidence.object_id,
                    "title": title,
                    "snippet": evidence.snippet,
                    "url": evidence.source_url,
                    "score": evidence.score,
                    "year": metadata.get("year"),
                    "venue": metadata.get("venue"),
                    "paper_id": evidence.object_id,
                    "title_clean": title,
                    "quality_status": metadata.get("quality_status"),
                }
            )
            continue
        if evidence.object_type == "web":
            rows.append(
                {
                    "type": "web",
                    "source_type": "web",
                    "id": evidence.source_url,
                    "title": metadata.get("title", ""),
                    "snippet": evidence.snippet,
                    "url": evidence.source_url,
                    "score": evidence.score,
                }
            )
            continue
        if evidence.object_type == "company":
            rows.append(
                {
                    "type": "company",
                    "id": evidence.object_id,
                    "title": metadata.get("name", "") or evidence.object_id,
                    "snippet": evidence.snippet,
                    "url": evidence.source_url,
                    "score": evidence.score,
                    "company_id": evidence.object_id,
                    "canonical_name": metadata.get("name", "") or evidence.object_id,
                    "industry": metadata.get("industry"),
                    "business": metadata.get("business")
                    or metadata.get("description")
                    or metadata.get("profile_summary"),
                    "description": metadata.get("description"),
                    "profile_summary": metadata.get("profile_summary"),
                    "technology_route_summary": metadata.get(
                        "technology_route_summary"
                    ),
                }
            )
            continue
        if evidence.object_type == "patent":
            rows.append(
                {
                    "type": "patent",
                    "id": evidence.object_id,
                    "title": metadata.get("title", "") or evidence.object_id,
                    "snippet": evidence.snippet,
                    "url": evidence.source_url,
                    "score": evidence.score,
                    "patent_id": evidence.object_id,
                    "patent_number": metadata.get("patent_number"),
                    "title_clean": metadata.get("title", "") or evidence.object_id,
                    "patent_type": metadata.get("patent_type"),
                }
            )
    return rows


def _validate_and_strip_citations(answer_text: str, evidence_count: int) -> str:
    def _replace(match: re.Match[str]) -> str:
        n = int(match.group(1))
        if n == 0 or n > evidence_count:
            logger.info("stripped out-of-range citation [%d]", n)
            return ""
        return match.group(0)

    return re.sub(r"\[(\d+)\]", _replace, answer_text)


def _maybe_prefix_low_confidence(
    answer_text: str, evidence: list[Evidence], threshold: float = 0.3
) -> str:
    if not evidence:
        return answer_text
    top = max(item.score for item in evidence)
    if top < threshold:
        return f"根据检索结果置信度较低，以下仅供参考：{answer_text}"
    return answer_text


def _e_route_filter_scholarly_organics(organics: list[dict]) -> list[dict]:
    filtered: list[dict] = []
    for organic in organics:
        link = str(organic.get("link") or "").strip()
        hostname = (urlparse(link).hostname or "").lower()
        if hostname and any(hostname.endswith(domain) for domain in _SCHOLARLY_DOMAINS):
            filtered.append(organic)
    return filtered[:3]


def _lookup_companies_by_topic(conn: Any, *, topic: str) -> list[dict]:
    term_groups = _company_topic_term_groups(topic)
    funding_query = _is_company_funding_query(topic)
    predicates: list[str] = []
    params: list[str] = []
    for group in term_groups:
        group_predicates = []
        for term in group:
            group_predicates.append("search.search_text ILIKE %s")
            params.append(f"%{term}%")
        if group_predicates:
            predicates.append("(" + " OR ".join(group_predicates) + ")")
    if not predicates:
        predicates.append("search.search_text ILIKE %s")
        params.append(f"%{topic}%")
    # Layer C: relevance score — rank companies whose core self-description
    # (industry/profile_summary/technology_route_summary) mentions the topic more
    # frequently above peripheral mentions. COUNT of occurrences (not binary) —
    # 118 Shenzhen companies mention '具身智能' in profile_summary (over-match);
    # truly-embodied companies (e.g. 无界智航, 2+ mentions) must outrank those that
    # mention it once, so they enter the Step-1 candidate pool instead of being cut
    # by the alphabetical tiebreak. product_category is NOT a signal (embodied
    # companies are categorized as '机器人').
    score_terms = _company_topic_score_terms(topic, term_groups)
    score_expr = " + ".join(
        "(char_length(search.core_text) - char_length(REPLACE(search.core_text, %s, ''))) / GREATEST(char_length(%s), 1)"
        for _ in score_terms
    ) or "0"
    score_params = [val for t in score_terms for val in (t, t)]
    funding_predicate = (
        "AND (latest.latest_funding_time IS NOT NULL OR events.funding_event_count > 0)"
        if funding_query
        else ""
    )
    order_clause = (
        "latest.latest_funding_time DESC NULLS LAST, "
        "events.latest_event_date DESC NULLS LAST, core_score DESC, c.canonical_name"
        if funding_query
        else "core_score DESC, c.canonical_name"
    )
    return conn.execute(
        f"""
        SELECT c.company_id, c.canonical_name,
               latest.industry, latest.business,
               latest.latest_funding_round,
               latest.latest_funding_time,
               latest.latest_funding_amount_raw,
               COALESCE(products.product_snippet, scenarios.scenario_snippet, events.event_snippet) AS snippet,
               c.profile_summary,
               ({score_expr}) AS core_score,
               count(*) OVER ()::int AS total_count
          FROM company c
          JOIN LATERAL (
            SELECT cs.industry, cs.business, cs.description,
                   cs.latest_funding_round,
                   cs.latest_funding_time,
                   cs.latest_funding_amount_raw
              FROM company_snapshot cs
             WHERE cs.company_id = c.company_id
             ORDER BY cs.snapshot_created_at DESC NULLS LAST
             LIMIT 1
          ) latest ON true
          LEFT JOIN LATERAL (
            SELECT string_agg(
                       concat_ws(
                           ' ',
                           cp.canonical_name,
                           cp.short_description,
                           cp.product_category,
                           cp.target_customers,
                           cp.application_scenarios,
                           cp.technical_tags
                       ),
                       ' '
                   ) AS product_text,
                   (array_agg(
                       concat_ws('：', cp.canonical_name, cp.short_description)
                       ORDER BY cp.confidence DESC NULLS LAST,
                                cp.last_refreshed_at DESC NULLS LAST
                   ))[1] AS product_snippet
              FROM company_product cp
             WHERE cp.company_id = c.company_id
               AND cp.quality_status = 'ready'
          ) products ON true
          LEFT JOIN LATERAL (
            SELECT string_agg(
                       concat_ws(
                           ' ',
                           cas.scenario_name,
                           cas.scenario_category,
                           cas.description,
                           cas.target_customer
                       ),
                       ' '
                   ) AS scenario_text,
                   (array_agg(
                       concat_ws('：', cas.scenario_name, cas.description)
                       ORDER BY cas.confidence DESC NULLS LAST,
                                cas.last_refreshed_at DESC NULLS LAST
                   ))[1] AS scenario_snippet
              FROM company_application_scenario cas
             WHERE cas.company_id = c.company_id
               AND cas.quality_status = 'ready'
          ) scenarios ON true
          LEFT JOIN LATERAL (
            SELECT string_agg(
                       concat_ws(' ', cse.event_date::text, cse.event_type, cse.event_summary),
                       ' '
                   ) AS event_text,
                   max(cse.event_date) AS latest_event_date,
                   count(*) FILTER (WHERE cse.event_type = 'funding') AS funding_event_count,
                   (array_agg(
                       concat_ws(' ', cse.event_date::text, cse.event_type, cse.event_summary)
                       ORDER BY cse.event_date DESC NULLS LAST,
                                cse.created_at DESC NULLS LAST
                   ))[1] AS event_snippet
              FROM company_signal_event cse
             WHERE cse.company_id = c.company_id
               AND cse.status = 'active'
          ) events ON true
          CROSS JOIN LATERAL (
            SELECT concat_ws(' ', latest.industry, c.profile_summary, c.technology_route_summary) AS core_text,
                   concat_ws(
                       ' ',
                       latest.industry, latest.business, latest.description,
                       c.profile_summary, c.technology_route_summary,
                       products.product_text, scenarios.scenario_text, events.event_text
                   ) AS search_text
          ) search
         WHERE c.is_shenzhen = true
           AND c.identity_status != 'inactive'
           {funding_predicate}
           AND (
             {" AND ".join(predicates)}
           )
         ORDER BY {order_clause}
         LIMIT 45
        """,
        tuple(score_params + params),
    ).fetchall()


def _company_lookup_topic(topic: str, raw_query: str) -> str:
    raw_query = raw_query.strip()
    topic = topic.strip()
    if raw_query and raw_query not in topic:
        return f"{topic} {raw_query}".strip()
    return topic or raw_query


def _is_company_funding_query(topic: str) -> bool:
    return bool(re.search(r"(融资|募资|投资|最新轮次|最近.*轮|[ABCD]\+?轮)", topic, re.IGNORECASE))


def _company_topic_term_groups(topic: str) -> list[list[str]]:
    normalized = topic.strip()
    groups: list[list[str]] = []
    if re.search(r"(医疗|医药|健康|临床|心电)", normalized):
        groups.append(["医疗", "医药", "健康", "临床", "心电"])
    if re.search(r"\bAI\b|人工智能|智能", normalized, re.IGNORECASE):
        groups.append(["AI", "人工智能", "智能"])

    for token in re.split(r"[\s,，、]+", normalized):
        cleaned = token.strip(" ：，。；;")
        cleaned = re.sub(r"(最近|融资|募资|投资|深圳|哪些|有哪些|有谁|有什么|公司|企业|厂商|供应商|团队|做|找|的)", "", cleaned)
        if not cleaned or len(cleaned) < 2:
            continue
        if cleaned.upper() == "AI":
            group = ["AI", "人工智能", "智能"]
        else:
            group = [cleaned]
        if group not in groups:
            groups.append(group)

    deduped: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for group in groups:
        key = tuple(group)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(group)
    return deduped[:4]


def _company_topic_score_terms(topic: str, term_groups: list[list[str]]) -> list[str]:
    """Score on specific topic terms, but keep generic-AI fallback for pure AI queries."""
    specific_terms: list[str] = []
    for group in term_groups:
        if tuple(group) == _COMPANY_TOPIC_GENERIC_AI_GROUP:
            continue
        for term in group:
            cleaned = str(term).strip()
            if not cleaned:
                continue
            if cleaned.upper() == "AI" or cleaned in _COMPANY_TOPIC_GENERIC_AI_TERMS:
                continue
            specific_terms.append(cleaned)
    if specific_terms:
        return specific_terms
    fallback_terms = [
        str(term).strip()
        for group in term_groups
        for term in group
        if str(term).strip()
    ]
    stripped_topic = topic.strip()
    return fallback_terms or ([stripped_topic] if stripped_topic else [])


def _company_topic_specific_count(
    candidate: dict[str, Any],
    score_terms: list[str],
) -> int:
    core_score = candidate.get("core_score")
    if core_score is not None:
        try:
            return max(0, int(float(core_score)))
        except (TypeError, ValueError):
            pass
    text = " ".join(
        str(candidate.get(key) or "")
        for key in (
            "industry",
            "business",
            "profile_summary",
            "snippet",
        )
    )
    return sum(text.count(term) for term in score_terms if term)


def _append_professor_topic_term(
    terms: list[str],
    seen: set[str],
    term: str,
) -> None:
    cleaned = term.strip(" ：，。；;、,")
    if not cleaned or cleaned in seen:
        return
    seen.add(cleaned)
    terms.append(cleaned)


def _professor_topic_terms(topic: str) -> list[str]:
    normalized = _normalize_query_for_rules(topic)
    normalized = re.sub(r"[?？!！。；;，,、:：]+", " ", normalized)
    stripped = normalized
    stopwords = sorted(
        (*_INSTITUTION_KEYS_BY_LEN, *_PROFESSOR_TOPIC_STOPWORDS),
        key=len,
        reverse=True,
    )
    for stopword in stopwords:
        stripped = stripped.replace(stopword, " ")

    raw_tokens = [token.strip() for token in re.split(r"\s+", stripped) if token.strip()]
    terms: list[str] = []
    seen: set[str] = set()
    for token in raw_tokens:
        _append_professor_topic_term(terms, seen, token)
        for key, equivalents in _PROFESSOR_TOPIC_EQUIVALENTS.items():
            if key not in token:
                continue
            _append_professor_topic_term(terms, seen, key)
            for equivalent in equivalents:
                _append_professor_topic_term(terms, seen, equivalent)
    return terms


def _company_topic_leaderboard(candidates: list[dict], query: str) -> list[dict[str, Any]]:
    score_terms = _company_topic_score_terms(query, _company_topic_term_groups(query))
    leaderboard: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        profile_summary = str(candidate.get("profile_summary") or "").strip()
        leaderboard.append(
            {
                "index": index,
                "canonical_name": candidate.get("canonical_name") or "",
                "business": candidate.get("business") or "",
                "profile_head": profile_summary[:70],
                "specific_term_count": _company_topic_specific_count(
                    candidate,
                    score_terms,
                ),
            }
        )
    return leaderboard


def _json_object_from_text(text: str) -> dict[str, Any]:
    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        text.strip(),
        flags=re.MULTILINE,
    )
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Step-1 selection returned non-object JSON")
    return data


def _candidate_by_step1_item(
    item: Any,
    candidates: list[dict],
) -> tuple[dict | None, str]:
    reason = ""
    index_value: Any = None
    name_value = ""
    company_id_value = ""
    if isinstance(item, int):
        index_value = item
    elif isinstance(item, str):
        name_value = item.strip()
    elif isinstance(item, dict):
        index_value = (
            item.get("index")
            or item.get("candidate_index")
            or item.get("rank_index")
        )
        name_value = str(
            item.get("canonical_name")
            or item.get("name")
            or item.get("company")
            or ""
        ).strip()
        company_id_value = str(item.get("company_id") or item.get("id") or "").strip()
        reason = str(item.get("reason") or item.get("rationale") or "").strip()[:160]

    if index_value is not None:
        try:
            index = int(index_value)
        except (TypeError, ValueError):
            index = 0
        if 1 <= index <= len(candidates):
            return candidates[index - 1], reason

    if company_id_value:
        for candidate in candidates:
            candidate_id = str(candidate.get("company_id") or candidate.get("id") or "")
            if candidate_id == company_id_value:
                return candidate, reason
    if name_value:
        for candidate in candidates:
            if str(candidate.get("canonical_name") or "").strip() == name_value:
                return candidate, reason
    return None, reason


def _selected_company_step1_items(payload: dict[str, Any]) -> list[Any]:
    for key in (
        "leaders",
        "selected_leaders",
        "selected_companies",
        "selected_indices",
        "companies",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _company_topic_candidate_keys(candidate: dict[str, Any], fallback_index: int) -> list[str]:
    keys: list[str] = []
    identifier = str(candidate.get("company_id") or candidate.get("id") or "").strip()
    if identifier:
        keys.append(f"id:{identifier}")
    canonical_name = str(candidate.get("canonical_name") or "").strip()
    if canonical_name:
        keys.append(f"name:{canonical_name}")
    return keys or [f"candidate:{fallback_index}"]


def _company_topic_specificity_topk(
    candidates: list[dict],
    query: str,
    *,
    top_k: int = _COMPANY_TOPIC_SPECIFICITY_TOP_K,
) -> list[dict]:
    score_terms = _company_topic_score_terms(query, _company_topic_term_groups(query))
    ranked = [
        (
            _company_topic_specific_count(candidate, score_terms),
            index,
            candidate,
        )
        for index, candidate in enumerate(candidates)
    ]
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [candidate for _score, _index, candidate in ranked[:top_k]]


def _compose_company_topic_selection(
    step1_selected: list[dict],
    candidates: list[dict],
    query: str,
) -> list[dict]:
    final: list[dict] = []
    selected_keys: set[str] = set()

    def append_candidate(candidate: dict, *, reason: str | None = None) -> None:
        if len(final) >= _COMPANY_TOPIC_SELECTION_MAX_COUNT:
            return
        keys = _company_topic_candidate_keys(candidate, len(final))
        if any(key in selected_keys for key in keys):
            return
        selected_keys.update(keys)
        selected_candidate = dict(candidate)
        if reason is not None:
            selected_candidate["leader_selection_reason"] = reason
        selected_candidate["leader_selection_rank"] = len(final) + 1
        final.append(selected_candidate)

    for candidate in step1_selected:
        append_candidate(candidate)
    for candidate in _company_topic_specificity_topk(candidates, query):
        append_candidate(candidate, reason=_COMPANY_TOPIC_SPECIFICITY_REASON)
    return final


def _select_company_leaders_step1(candidates: list[dict], query: str) -> list[dict]:
    if not candidates:
        logger.info(
            "company_topic_step1_selection query=%r candidate_count=0 selected_count=0 selected=[]",
            query,
        )
        return []

    leaderboard = _company_topic_leaderboard(candidates, query)
    system_prompt = (
        "你是深圳科创企业检索的第一步筛选器。只能从候选列表中选择公司，"
        "不要新增候选外公司。目标是选出与用户主题直接相关、行业公认度更高、"
        "更像代表性厂商/龙头/重要玩家的企业，按重要性排序。"
        "排除只蹭关键词、纯邻接业务、数据标注/通用AI软件等明显不直接匹配的公司；"
        "若主题是具身智能，排除非机器人/非具身智能核心业务。"
        "输出严格 JSON：{\"leaders\":[{\"index\":候选index,\"reason\":\"简短理由\"}]}，"
        "leaders 数量最多 10。"
    )
    user_prompt = (
        f"用户问题：{query}\n\n"
        "候选企业（index 为唯一可引用编号；specific_term_count 是核心文本中具体主题词命中数）：\n"
        f"{json.dumps(leaderboard, ensure_ascii=False)}"
    )

    try:
        _clear_proxy_env()
        settings = resolve_professor_llm_settings(None, include_profile=True)
        model = os.getenv("LOCAL_LLM_MODEL") or settings["local_llm_model"]
        client = OpenAI(
            base_url=settings["local_llm_base_url"],
            api_key=settings["local_llm_api_key"] or "EMPTY",
            timeout=60.0,
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            max_tokens=1200,
            response_format={"type": "json_object"},
            extra_body=build_non_thinking_extra_body(model),
        )
        payload = _json_object_from_text(_extract_chat_completion_text(response))
        selected: list[dict] = []
        selected_keys: set[str] = set()
        for item in _selected_company_step1_items(payload):
            candidate, reason = _candidate_by_step1_item(item, candidates)
            if candidate is None:
                continue
            candidate_keys = _company_topic_candidate_keys(candidate, len(selected))
            if any(key in selected_keys for key in candidate_keys):
                continue
            selected_keys.update(candidate_keys)
            selected_candidate = dict(candidate)
            if reason:
                selected_candidate["leader_selection_reason"] = reason
            selected_candidate["leader_selection_rank"] = len(selected) + 1
            selected.append(selected_candidate)
            if len(selected) >= _COMPANY_TOPIC_STEP1_TARGET_COUNT:
                break
        if not selected:
            selected = [dict(candidate) for candidate in candidates[:_COMPANY_TOPIC_STEP1_TARGET_COUNT]]
    except Exception as exc:  # noqa: BLE001 - preserve chat path on selector failure
        logger.warning(
            "company_topic_step1_selection_failed query=%r candidate_count=%d error=%s",
            query,
            len(candidates),
            exc,
        )
        selected = [dict(candidate) for candidate in candidates[:_COMPANY_TOPIC_STEP1_TARGET_COUNT]]

    selected = _compose_company_topic_selection(selected, candidates, query)

    logger.info(
        "company_topic_step1_selection query=%r candidate_count=%d selected_count=%d selected=%s",
        query,
        len(candidates),
        len(selected),
        [
            {
                "rank": index,
                "company_id": row.get("company_id") or row.get("id"),
                "canonical_name": row.get("canonical_name"),
                "reason": row.get("leader_selection_reason"),
            }
            for index, row in enumerate(selected, start=1)
        ],
    )
    return selected


def _company_topic_response_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "type": "company",
            "id": row.get("company_id"),
            "company_id": row.get("company_id"),
            "canonical_name": row.get("canonical_name"),
            "industry": row.get("industry"),
            "business": row.get("business"),
            "snippet": row.get("snippet"),
            "latest_funding_round": row.get("latest_funding_round"),
            "latest_funding_time": row.get("latest_funding_time"),
            "latest_funding_amount_raw": row.get("latest_funding_amount_raw"),
            "total_count": row.get("total_count"),
            "leader_selection_rank": row.get("leader_selection_rank"),
            "leader_selection_reason": row.get("leader_selection_reason"),
        }
        for row in rows
    ]


def _answer_cross_domain(
    topic: str,
    profs: list[dict],
    companies: list[dict],
    papers: list[dict] | None = None,
) -> str:
    """D — 3-section cross-domain summary."""
    papers = papers or []
    p_total = profs[0].get("total_count", len(profs)) if profs else 0
    paper_total = papers[0].get("total_count", len(papers)) if papers else 0
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
    lines.append(f"▎ 论文（{paper_total} 篇）：")
    if papers:
        for r in papers[:5]:
            title = r.get("title") or r.get("title_clean") or r.get("paper_id") or ""
            bits = [str(title)]
            if r.get("year"):
                bits.append(str(r["year"]))
            if r.get("venue"):
                bits.append(str(r["venue"]))
            lines.append(f"  • {' — '.join(bit for bit in bits if bit)}")
        if paper_total > 5:
            lines.append(f"  ... 还有 {paper_total - 5} 篇")
    else:
        lines.append("  （本地库未命中）")
    lines.append("")
    lines.append(f"▎ 企业（{c_total} 家）：")
    if companies:
        for r in companies[:5]:
            bits = [r["canonical_name"]]
            if r.get("industry"):
                bits.append(r["industry"])
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


def _answer_knowledge_qa_fallback(query: str) -> tuple[str, str | None]:
    try:
        settings = resolve_professor_llm_settings(None, include_profile=True)
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
            extra_body=_chat_synthesis_extra_body(settings["local_llm_model"]),
        )
        answer = (resp.choices[0].message.content or "").strip()
        if not answer:
            return ("LLM 返回空回答。", "empty")
        if "AI 推理" not in answer and "非本地" not in answer:
            answer += "\n\n（综合自 AI 推理，非本地数据库结果）"
        return (answer, None)
    except Exception as exc:
        return (f"知识问答失败：{exc}", str(exc))


def _answer_knowledge_qa(query: str) -> tuple[str, str | None]:
    if chat_use_retrieval_service():
        results: list[Evidence] = []
        try:
            retrieval_service = get_retrieval_service()
            results = retrieval_service.retrieve(
                query,
                domains=("paper",),
                final_top_k=10,
            )
        except Exception as exc:
            logger.warning("Paper retrieval failed for knowledge QA %r: %s", query, exc)
            results = []

        merged = list(results)
        top_score = max((item.score for item in results), default=0.0)
        if not results or top_score < chat_e_web_fallback_threshold():
            web_provider = _get_web_search_provider_or_none()
            if web_provider is not None:
                try:
                    web_resp = web_provider.search(query)
                except Exception as exc:
                    logger.warning("Web fallback failed for knowledge QA %r: %s", query, exc)
                else:
                    scholarly = _e_route_filter_scholarly_organics(
                        web_resp.get("organic", [])
                    )
                    reranker = _get_reranker_client_or_none()
                    if reranker is not None:
                        reranked = _rerank_web_organics(
                            query, scholarly, reranker, top_n=3
                        )
                    else:
                        reranked = [
                            {**o, "rerank_score": 0.5} for o in scholarly[:3]
                        ]
                    for organic in reranked:
                        link = str(organic.get("link") or "").strip()
                        merged.append(
                            Evidence(
                                object_type="web",
                                object_id=link,
                                score=float(organic.get("rerank_score", 0.5)),
                                snippet=str(organic.get("snippet") or "")[:500],
                                source_url=link,
                                metadata={"title": organic.get("title", "")},
                            )
                        )

        if merged:
            evidence_text, _ = _build_evidence_blocks(
                {"retrieval_evidence": _evidence_list_from_retrieval(merged)}
            )
            answer_text = f"以下是检索到的相关资料：\n{evidence_text}"
            answer_text = _validate_and_strip_citations(answer_text, len(merged))
            answer_text = _maybe_prefix_low_confidence(answer_text, merged)
            return (answer_text, None)

    return _answer_knowledge_qa_fallback(query)


def _synthesize_web_search_answer(query: str, evidence: list[dict[str, Any]]) -> str:
    evidence_text, citation_map = _build_evidence_blocks(
        {"retrieval_evidence": evidence}
    )
    if not evidence_text:
        raise ValueError("empty web evidence")
    answer = _call_gemma_synthesis(
        query,
        evidence_text,
        timeout=_CHAT_SYNTHESIS_TIMEOUT_SECONDS,
    )
    answer = _validate_and_strip_citations(answer, len(citation_map))
    return answer


def _answer_knowledge_qa_with_web_search(
    query: str,
) -> tuple[str, str | None, list[dict[str, Any]]]:
    return answer_knowledge_qa_with_web_search(
        query,
        cache=_get_web_search_cache(),
        provider_factory=_get_web_search_provider_or_none,
        synthesize=_synthesize_web_search_answer,
        fallback=_answer_knowledge_qa_fallback,
        logger=logger,
    )


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
    r"(?:介绍(?:一下)?|查询|查一下|了解(?:一下)?)\s*(?:教授|研究员)?\s*(?:(?P<inst>[\u4e00-\u9fff]{2,15}?)\s*的\s*)?"
    r"(?P<name>[\u4e00-\u9fff]{2,5}?)(?:\s*(?:教授|研究员))?$"
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
    r"^(?:看看|看一下|查一下|列一下)?\s*(?P<name>[\u4e00-\u9fff A-Za-z.-]{2,20}?)\s*(的|发了(哪些)?|有(哪些|什么))\s*(论文|文章|paper)s?\s*$",
    re.IGNORECASE,
)
_Q_PROF_TOPICS_RE = re.compile(
    r"^(?P<name>[\u4e00-\u9fff A-Za-z.-]{2,20}?)\s*的\s*(研究方向|研究领域|研究)\s*(是什么|有哪些)?\s*$"
)
_Q_PROF_PROFILE_DETAIL_RE = re.compile(
    r"^(?:介绍(?:一下)?|查询|查一下|了解(?:一下)?)?\s*"
    r"(?P<subject>[\u4e00-\u9fff A-Za-z.()（）-]{2,40}?)\s*的\s*"
    r"(?:研究方向|研究领域|论文情况|论文|相关信息)\s*(?:是什么|有哪些)?\s*$"
)
_Q_PAPER_RELATED_PROFESSORS_RE = re.compile(
    r"^(?P<paper_id>PAPER-[A-Z0-9]+)\s*(?:这篇论文|论文)?\s*的\s*"
    r"(?:关联|相关)?\s*(?:教授|老师|学者)\s*(?:是谁|有哪些)?\s*$",
    re.IGNORECASE,
)


# --- Round 10 v2: multi-turn context ---
# SessionStore persists the small per-session context to Postgres while keeping
# an in-process cache/fallback. Each SessionContext keeps the last few entities
# and turns so pronouns ("他"/"她"/"这位教授") resolve to the most-recently
# mentioned professor.

_SESSION_COOKIE = "miroflow_chat_session"
_SESSION_TTL_SECONDS = 30 * 60
_SESSION_MAX_ENTITIES = 5
_SESSION_MAX_TURNS = 5
_SESSION_RESULT_SET_CAP = 100
_PRONOUN_DOMAIN_MAP = {
    "他": "professor",
    "她": "professor",
    "这位": "professor",
    "这位教授": "professor",
    "这位老师": "professor",
    "这位学者": "professor",
    "该教授": "professor",
    "该学者": "professor",
    "上面那位": "professor",
    "这家公司": "company",
    "该公司": "company",
    "这件专利": "patent",
    "该专利": "patent",
    "这篇论文": "paper",
    "这论文": "paper",
    "这本论文": "paper",
    "该篇论文": "paper",
    "该论文": "paper",
}
_SESSION_PRONOUNS_RE = re.compile(
    "|".join(
        re.escape(key)
        for key in sorted(_PRONOUN_DOMAIN_MAP, key=len, reverse=True)
    )
)


def _chat_session_dsn() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")


class SessionEntity(BaseModel):
    kind: Literal["professor", "paper", "patent", "company"]
    id: str
    label: str


class SessionContext(BaseModel):
    session_id: str
    user_id: str | None = None
    entities: list[SessionEntity] = Field(default_factory=list)
    turns: list[dict[str, Any]] = Field(default_factory=list)
    last_result_set: dict[str, list[str]] = Field(default_factory=dict)
    last_seen_at: float = Field(default_factory=time.time)

    def model_post_init(self, __context: Any) -> None:
        self.entities = self.entities[-_SESSION_MAX_ENTITIES:]
        self.turns = self.turns[-_SESSION_MAX_TURNS:]
        self.last_result_set = {
            domain: list(ids)[:_SESSION_RESULT_SET_CAP]
            for domain, ids in self.last_result_set.items()
            if domain in _TARGET_DOMAINS and isinstance(ids, list)
        }

    def push_entity(self, entity: SessionEntity) -> None:
        # Drop existing copies so the most-recent mention lands at the end
        entities = [
            e
            for e in self.entities
            if not (e.kind == entity.kind and e.id == entity.id)
        ]
        entities.append(entity)
        self.entities = entities[-_SESSION_MAX_ENTITIES:]

    def latest_professor(self) -> SessionEntity | None:
        return self.latest_for("professor")

    def latest_for(self, domain: str) -> SessionEntity | None:
        if domain not in _TARGET_DOMAINS:
            return None
        for e in reversed(self.entities):
            if e.kind == domain:
                return e
        return None

    def latest_entity_for_other_domains(
        self, target_domain: str
    ) -> SessionEntity | None:
        if target_domain not in _TARGET_DOMAINS:
            return None
        for e in reversed(self.entities):
            if e.kind != target_domain:
                return e
        return None

    def latest_result_domain(self) -> str | None:
        for domain in reversed(self.last_result_set):
            if self.last_result_set.get(domain):
                return domain
        return None

    def resolve_set_referent(
        self, referent: SetReferent
    ) -> tuple[str, list[str]] | None:
        if referent.domain:
            ids = self.last_result_set.get(referent.domain) or []
            return (referent.domain, list(ids)) if ids else None

        domain = self.latest_result_domain()
        if domain is None:
            return None
        ids = self.last_result_set.get(domain) or []
        return (domain, list(ids)) if ids else None

    def push_result_set(
        self, domain: str, ids: list[str], cap: int = _SESSION_RESULT_SET_CAP
    ) -> None:
        if domain not in _TARGET_DOMAINS:
            return
        seen: set[str] = set()
        deduped: list[str] = []
        for item in ids:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        self.last_result_set.pop(domain, None)
        self.last_result_set[domain] = deduped[:cap]

    def clear_active_context(self) -> None:
        self.entities = []
        self.last_result_set = {}

    def clear_other_domains(self, current: str) -> None:
        """W11 keeps per-domain result history; this hook is intentionally no-op."""
        if current not in _TARGET_DOMAINS:
            return

    def push_turn(self, query: str, query_type: str, answer_text: str) -> None:
        self.turns.append({
            "query": query,
            "query_type": query_type,
            "answer_text": answer_text[:300],  # trim for memory hygiene
            "at": time.time(),
        })
        self.turns = self.turns[-_SESSION_MAX_TURNS:]


_SESSION_STORE = SessionStore(_chat_session_dsn(), ttl_seconds=_SESSION_TTL_SECONDS)
_WEB_SEARCH_CACHE = WebSearchCache(_chat_session_dsn())


def _get_or_create_session(session_id: str | None) -> SessionContext:
    if not isinstance(session_id, str):
        session_id = None
    return _SESSION_STORE.get_or_create(session_id)


def _get_web_search_cache() -> WebSearchCache:
    return _WEB_SEARCH_CACHE


def _rewrite_query_with_context(query: str, session: SessionContext) -> str:
    """Replace known pronouns with the latest matching-domain entity label."""
    if not _SESSION_PRONOUNS_RE.search(query):
        return query

    def replace(match: re.Match[str]) -> str:
        pronoun = match.group(0)
        domain = _PRONOUN_DOMAIN_MAP.get(pronoun)
        entity = session.latest_for(domain or "")
        return entity.label if entity else pronoun

    return _SESSION_PRONOUNS_RE.sub(replace, query)


_SINGULAR_CONTEXT_DOMAIN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?:这个|这位|该)(?:教授|老师|学者)"), "professor"),
    (re.compile(r"^(?:这家|这个|该)(?:公司|企业)"), "company"),
    (re.compile(r"^(?:这篇|这个|该)(?:论文|文章)"), "paper"),
    (re.compile(r"^(?:这件|这个|该)(?:专利)"), "patent"),
    (re.compile(r"^这家"), "company"),
    (re.compile(r"^这篇"), "paper"),
)


def _singular_pronoun_domain(
    query: str,
    session: SessionContext,
) -> str | None:
    """Infer the singular context domain without treating set words as singular."""
    normalized = _normalize_query_for_rules(_strip_topic_switch_prefix(query))
    if not normalized:
        return None

    for pronoun, domain in sorted(
        _PRONOUN_DOMAIN_MAP.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if pronoun in {"他", "她"}:
            if re.search(rf"{re.escape(pronoun)}(?!们)", normalized):
                return domain
            continue
        if pronoun in normalized:
            return domain

    for pattern, domain in _SINGULAR_CONTEXT_DOMAIN_PATTERNS:
        if pattern.search(normalized):
            return domain

    if normalized.startswith("这个"):
        live_domains = [
            domain for domain, ids in session.last_result_set.items() if ids
        ]
        if len(live_domains) == 1:
            return live_domains[0]
    return None


def _query_uses_context(query: str) -> bool:
    stripped = _strip_topic_switch_prefix(query)
    return bool(
        _SESSION_PRONOUNS_RE.search(stripped)
        or _CLASSIFIER_CONTEXT_RE.search(stripped)
        or looks_like_narrowing_query(stripped)
    )


def _should_clear_active_context(query: str, query_type: str) -> bool:
    if _query_uses_context(query):
        return False
    if _TOPIC_SWITCH_PREFIX_RE.search(query):
        return True
    return query_type.startswith(("A_", "B_", "G_"))


def _chat_citations_from_result_rows(rows: list[dict]) -> list[ChatCitation]:
    citations: list[ChatCitation] = []
    for row in rows[:10]:
        domain = str(row.get("type") or "")
        if domain not in _TARGET_DOMAINS:
            continue
        object_id = row.get(domain_id_key(domain)) or row.get("id")
        if not object_id:
            continue
        title = (
            row.get("canonical_name")
            or row.get("title")
            or row.get("title_clean")
            or row.get("patent_number")
            or str(object_id)
        )
        citations.append(
            ChatCitation(
                type=domain,
                id=str(object_id),
                label=str(title),
                url=f"/browse#{domain}/{object_id}",
            )
        )
    return citations


def _lookup_narrowed_results(
    conn: Any,
    *,
    domain: str,
    allowed_ids: list[str],
    topic: str,
    limit: int = 20,
) -> list[dict]:
    del conn
    allowed = set(allowed_ids)
    if not chat_use_retrieval_service():
        return []
    try:
        results = get_retrieval_service().retrieve(
            query=topic,
            domains=(domain,),
            candidate_limit=max(30, min(len(allowed_ids) * 2, 100)),
            final_top_k=min(limit, max(len(allowed_ids), 1)),
        )
    except Exception as exc:
        logger.warning("Narrowing retrieval failed for %s %r: %s", domain, topic, exc)
        return []
    return [
        row
        for row in _evidence_list_from_retrieval(results)
        if str(row.get("id") or "") in allowed
    ][:limit]


def _resolve_institution(fragment: str) -> tuple[str, ...] | None:
    """Return canonical institution strings matching a user-typed fragment."""
    if not fragment:
        return None
    for key in _INSTITUTION_KEYS_BY_LEN:
        if key in fragment:
            return _INSTITUTION_ALIASES[key]
    return None


def _parse_professor_papers_subject(
    fragment: str,
) -> tuple[str, tuple[str, ...] | None]:
    subject = _normalize_query_for_rules(fragment)
    subject = re.sub(
        r"^(?:介绍(?:一下)?|查询|查一下|了解(?:一下)?)\s*",
        "",
        subject,
    )
    institutions = _resolve_institution(subject)
    subject = re.sub(r"\s*(?:教授|研究员|老师|学者)\s*$", "", subject).strip()
    if institutions is not None:
        subject = _strip_resolved_institution_from_subject(subject, institutions)
    subject = subject.strip(" 的：:，,、")
    if match := re.search(r"(?P<name>[\u4e00-\u9fff]{2,5})$", subject):
        return match.group("name"), institutions
    return subject, institutions


def _strip_resolved_institution_from_subject(
    subject: str,
    institutions: tuple[str, ...],
) -> str:
    candidates = sorted(
        {*_INSTITUTION_KEYS_BY_LEN, *institutions},
        key=len,
        reverse=True,
    )
    for candidate in candidates:
        if candidate and candidate in subject:
            subject = subject.replace(candidate, "", 1)
            break
    return subject.strip()


def _should_handle_professor_profile_rule(
    *, inst_fragment: str, name: str, institutions: tuple[str, ...] | None
) -> bool:
    if name in {"相关信息", "基本信息", "公司信息"}:
        return False
    if inst_fragment and institutions is None:
        return False
    if not inst_fragment and len(name) > 3:
        return False
    return True


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
               p.discipline_family,
               p.h_index,
               p.citation_count,
               p.paper_count
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


def _lookup_professor_by_id(conn: Any, *, professor_id: str) -> dict | None:
    rows = conn.execute(
        """
        SELECT p.professor_id,
               p.canonical_name,
               p.canonical_name_en,
               pa.institution,
               pa.title,
               p.discipline_family,
               p.h_index,
               p.citation_count,
               p.paper_count
          FROM professor p
          LEFT JOIN LATERAL (
            SELECT pa_inner.institution, pa_inner.title
              FROM professor_affiliation pa_inner
             WHERE pa_inner.professor_id = p.professor_id
               AND pa_inner.is_primary = true
             LIMIT 1
          ) pa ON true
         WHERE p.identity_status = 'resolved'
           AND p.professor_id = %s
         LIMIT 1
        """,
        (professor_id,),
    ).fetchall()
    return rows[0] if rows else None


def _professor_topic_paper_counts(
    conn: Any,
    professor_ids: list[str],
    topic_terms: list[str],
) -> dict[str, int]:
    unique_professor_ids = list(
        dict.fromkeys(
            professor_id
            for professor_id in (str(item).strip() for item in professor_ids)
            if professor_id
        )
    )
    counts = {professor_id: 0 for professor_id in unique_professor_ids}
    clean_terms = list(
        dict.fromkeys(term for term in (item.strip() for item in topic_terms) if term)
    )
    if not unique_professor_ids or not clean_terms:
        return counts

    like_terms = [f"%{term}%" for term in clean_terms]
    rows = conn.execute(
        """
        SELECT pl.professor_id, count(*)::int AS count
          FROM professor_paper_link pl
          JOIN paper p ON p.paper_id=pl.paper_id
         WHERE pl.professor_id = ANY(%s)
           AND pl.link_status='verified'
           AND (p.title_clean ILIKE ANY(%s) OR p.title_raw ILIKE ANY(%s))
         GROUP BY pl.professor_id
        """,
        (unique_professor_ids, like_terms, like_terms),
    ).fetchall()
    for row in rows:
        if isinstance(row, dict):
            professor_id = str(row.get("professor_id") or "").strip()
            count = row.get("count")
        else:
            professor_id = str(row[0]).strip()
            count = row[1]
        if professor_id in counts:
            counts[professor_id] = int(count or 0)
    return counts


def _rerank_professor_topic_rows_by_paper_count(
    conn: Any,
    rows: list[dict],
    *,
    topic: str,
) -> list[dict]:
    topic_terms = _professor_topic_terms(topic)
    if not rows or not topic_terms:
        return rows

    ranked_rows: list[tuple[int, dict, str]] = []
    professor_ids: list[str] = []
    for original_rank, row in enumerate(rows):
        professor_id = str(row.get("professor_id") or row.get("id") or "").strip()
        ranked_rows.append((original_rank, row, professor_id))
        if professor_id:
            professor_ids.append(professor_id)
    if not professor_ids:
        return rows

    try:
        topic_paper_counts = _professor_topic_paper_counts(
            conn,
            professor_ids,
            topic_terms,
        )
    except Exception as exc:
        logger.warning(
            "Professor topic-paper-count fusion failed for topic %r: %s",
            topic,
            exc,
        )
        return rows

    nonzero = {pid: c for pid, c in topic_paper_counts.items() if c}
    logger.info(
        "professor_topic_rerank topic=%r rows=%d prof_ids=%d nonzero=%s",
        topic,
        len(rows),
        len(professor_ids),
        nonzero,
    )
    return [
        item[1]
        for item in sorted(
            ranked_rows,
            key=lambda item: (-topic_paper_counts.get(item[2], 0), item[0]),
        )
    ]


def _lookup_company_by_id(conn: Any, *, company_id: str) -> dict | None:
    rows = conn.execute(
        """
        SELECT c.company_id, c.canonical_name, c.registered_name,
               c.hq_province, c.hq_city, c.hq_district, c.is_shenzhen,
               latest.industry, latest.business, latest.description,
               latest.region, latest.registered_address,
               c.website,
               COALESCE(products.products_json, '[]'::jsonb) AS products,
               COALESCE(scenarios.application_scenarios_json, '[]'::jsonb) AS application_scenarios,
               COALESCE(recent_events.recent_events_json, '[]'::jsonb) AS recent_events,
               1::int AS total_count
          FROM company c
          LEFT JOIN LATERAL (
            SELECT cs.industry, cs.business, cs.description,
                   cs.region, cs.registered_address
              FROM company_snapshot cs
             WHERE cs.company_id = c.company_id
             ORDER BY cs.snapshot_created_at DESC NULLS LAST
             LIMIT 1
          ) latest ON true
          LEFT JOIN LATERAL (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'name', cp.canonical_name,
                    'description', cp.short_description,
                    'source_url', cp.official_product_url,
                    'quality_status', cp.quality_status,
                    'confidence', cp.confidence,
                    'product_category', cp.product_category,
                    'target_customers', cp.target_customers,
                    'application_scenarios', cp.application_scenarios,
                    'technical_tags', cp.technical_tags
                )
                ORDER BY cp.confidence DESC NULLS LAST, cp.last_refreshed_at DESC NULLS LAST
            ) AS products_json
              FROM company_product cp
             WHERE cp.company_id = c.company_id
               AND cp.quality_status = 'ready'
          ) products ON true
          LEFT JOIN LATERAL (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'scenario_id', cas.scenario_id,
                    'scenario_name', cas.scenario_name,
                    'scenario_category', cas.scenario_category,
                    'description', cas.description,
                    'target_customer', cas.target_customer,
                    'source_url', cas.source_url,
                    'quality_status', cas.quality_status,
                    'confidence', cas.confidence
                )
                ORDER BY cas.confidence DESC NULLS LAST, cas.last_refreshed_at DESC NULLS LAST
            ) AS application_scenarios_json
              FROM company_application_scenario cas
             WHERE cas.company_id = c.company_id
               AND cas.quality_status = 'ready'
          ) scenarios ON true
          LEFT JOIN LATERAL (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'event_type', cse.event_type,
                    'event_date', cse.event_date,
                    'summary', cse.event_summary,
                    'confidence', cse.confidence,
                    'source_url', news.source_url,
                    'normalized', cse.event_subject_normalized
                )
                ORDER BY cse.event_date DESC, cse.created_at DESC NULLS LAST
            ) AS recent_events_json
              FROM (
                SELECT *
                  FROM company_signal_event cse
                 WHERE cse.company_id = c.company_id
                   AND cse.status = 'active'
                 ORDER BY cse.event_date DESC, cse.created_at DESC NULLS LAST
                 LIMIT 5
              ) cse
              LEFT JOIN company_news_item news ON news.news_id = cse.primary_news_id
          ) recent_events ON true
         WHERE c.identity_status != 'inactive'
           AND c.company_id = %s
         LIMIT 1
        """,
        (company_id,),
    ).fetchall()
    return rows[0] if rows else None


def _lookup_paper_by_id(conn: Any, *, paper_id: str) -> dict | None:
    rows = conn.execute(
        """
        SELECT paper_id, title_clean, year, venue, authors_display,
               abstract_clean, summary_zh, citation_count,
               identity_status, quality_status,
               1::int AS total_count
          FROM paper
         WHERE paper_id = %s
           AND COALESCE(identity_status, 'unverified') != 'rejected'
           AND COALESCE(quality_status, 'needs_enrichment') != 'rejected'
         LIMIT 1
        """,
        (paper_id,),
    ).fetchall()
    return rows[0] if rows else None


def _lookup_patent_by_id(conn: Any, *, patent_id: str) -> dict | None:
    rows = conn.execute(
        """
        SELECT patent_id, patent_number, title_clean, applicants_raw,
               filing_date, grant_date, patent_type, abstract_clean,
               status AS legal_status,
               1::int AS total_count
          FROM patent
         WHERE patent_id = %s
           AND COALESCE(status, '') != 'inactive'
         LIMIT 1
        """,
        (patent_id,),
    ).fetchall()
    return rows[0] if rows else None


def _lookup_professors_by_topic_sql(
    conn: Any, *, institutions: tuple[str, ...], topic: str, limit: int
) -> list[dict]:
    placeholders = ", ".join(["%s"] * len(institutions))
    sql = f"""
        WITH matches AS (
          SELECT p.professor_id,
                 p.canonical_name,
                 pa.institution,
                 p.h_index,
                 p.citation_count,
                 p.paper_count,
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
           GROUP BY
             p.professor_id,
             p.canonical_name,
             pa.institution,
             p.h_index,
             p.citation_count,
             p.paper_count
        )
        SELECT *, count(*) OVER ()::int AS total_count
          FROM matches
         ORDER BY canonical_name
         LIMIT %s
    """
    like = f"%{topic}%"
    return conn.execute(sql, [like, *institutions, like, limit]).fetchall()


def _lookup_professors_by_topic(
    conn: Any, *, institutions: tuple[str, ...], topic: str, limit: int
) -> list[dict]:
    if not chat_use_retrieval_service():
        return _lookup_professors_by_topic_sql(
            conn, institutions=institutions, topic=topic, limit=limit
        )

    filters: dict[str, str] = {}
    if institutions:
        filters["institution"] = institutions[0]
    try:
        retrieval_service = get_retrieval_service()
        results = retrieval_service.retrieve(
            query=topic,
            domains=("professor",),
            filters=filters or None,
            candidate_limit=64,
            final_top_k=limit,
        )
        rows = _evidence_list_from_retrieval(results)
        # FM4 cross-domain rescue: professor vector recall is weak for topic queries
        # (profile_summary doesn't emphasize the topic the way paper titles do). When recall
        # is thin, recall papers on the topic and rescue their authors via paper->professor
        # (get_related_objects; the link SQL already exists). Rank rescued professors by
        # topic-paper-count (more papers on the topic = more relevant) so high-volume authors
        # surface first. Dedup by professor_id.
        if len(rows) < limit:
            try:
                paper_results = retrieval_service.retrieve(
                    query=topic, domains=("paper",),
                    candidate_limit=64, final_top_k=20,
                )
                seen = {r.get("professor_id") for r in rows if r.get("professor_id")}
                prof_counts: dict[str, int] = {}
                prof_rows: dict[str, dict] = {}
                for ev in paper_results:
                    oid = getattr(ev, "object_id", "")
                    if getattr(ev, "object_type", "") != "paper" or not oid:
                        continue
                    rel = retrieval_service.get_related_objects(
                        source_domain="paper", source_id=oid,
                        target_domain="professor", limit=20,
                    )
                    for r in rel:
                        pid = str(r.get("professor_id") or "").strip()
                        if pid and pid not in seen:
                            prof_counts[pid] = prof_counts.get(pid, 0) + 1
                            prof_rows.setdefault(pid, {**r, "type": "professor"})
                ranked = sorted(prof_counts, key=lambda p: prof_counts[p], reverse=True)
                slots = max(0, limit - len(rows))
                rescued = [prof_rows[p] for p in ranked[:slots]]
                if rescued:
                    rows.extend(rescued)
            except Exception as exc:
                logger.warning("Paper->professor rescue failed for topic %r: %s", topic, exc)
        # Re-rank the FULL set (vector + rescued) by topic-paper-count: professors with
        # topic papers (often surfaced via the paper->professor rescue) must outrank vector
        # false-positives that have zero topic papers. Runs AFTER rescue so rescued profs are
        # included; demotes 0-count profs, never drops them.
        rows = _rerank_professor_topic_rows_by_paper_count(conn, rows, topic=topic)
        normalized_rows = _normalize_professor_topic_rows(
            conn,
            rows,
            institutions=institutions,
            limit=limit,
        )
        if normalized_rows:
            return normalized_rows
        return _lookup_professors_by_topic_sql(
            conn, institutions=institutions, topic=topic, limit=limit
        )
    except Exception as exc:
        logger.warning("Professor retrieval failed for topic %r: %s", topic, exc)
        return _lookup_professors_by_topic_sql(
            conn, institutions=institutions, topic=topic, limit=limit
        )


def _normalize_professor_topic_rows(
    conn: Any,
    rows: list[dict],
    *,
    institutions: tuple[str, ...],
    limit: int,
) -> list[dict]:
    allowed_institutions = set(institutions)
    normalized: list[dict] = []
    for row in _hydrate_cross_domain_evidence(conn, rows):
        if row.get("type") not in (None, "professor"):
            continue
        professor_id = str(row.get("professor_id") or row.get("id") or "").strip()
        canonical_name = str(
            row.get("canonical_name") or row.get("title") or ""
        ).strip()
        institution = str(row.get("institution") or "").strip()
        if not professor_id or not canonical_name or canonical_name == professor_id:
            continue
        if allowed_institutions and institution not in allowed_institutions:
            continue
        normalized.append({
            **row,
            "type": "professor",
            "id": professor_id,
            "professor_id": professor_id,
            "title": canonical_name,
            "canonical_name": canonical_name,
            "institution": institution,
            "matched_topics": row.get("matched_topics") or [],
        })
    total_count = len(normalized)
    for row in normalized:
        row["total_count"] = total_count
    return normalized[:limit]


def _cross_domain_retrieval_query(topic: str, raw_query: str = "") -> str:
    topic = topic.strip()
    raw_query = raw_query.strip()
    if raw_query and raw_query not in topic:
        return f"{topic} {raw_query}".strip()
    return topic or raw_query


def _hydrate_cross_domain_evidence(conn: Any, rows: list[dict]) -> list[dict]:
    hydrated: list[dict] = []
    for row in rows:
        if row.get("type") != "professor":
            hydrated.append(row)
            continue

        professor_id = str(row.get("professor_id") or row.get("id") or "")
        needs_name = not row.get("canonical_name")
        needs_institution = not row.get("institution")
        if not professor_id or not (needs_name or needs_institution):
            hydrated.append(row)
            continue

        try:
            prof = _lookup_professor_by_id(conn, professor_id=professor_id)
        except Exception as exc:
            logger.warning(
                "Cross-domain professor hydration failed for %s: %s",
                professor_id,
                exc,
            )
            hydrated.append(row)
            continue

        if not prof:
            hydrated.append(row)
            continue

        canonical_name = row.get("canonical_name") or prof.get("canonical_name")
        institution = row.get("institution") or prof.get("institution")
        hydrated.append(
            {
                **row,
                "title": row.get("title") or canonical_name or professor_id,
                "canonical_name": canonical_name or professor_id,
                "institution": institution or "",
                "academic_title": row.get("academic_title") or prof.get("title"),
                "discipline_family": row.get("discipline_family")
                or prof.get("discipline_family"),
                "h_index": row.get("h_index") or prof.get("h_index"),
                "citation_count": row.get("citation_count")
                or prof.get("citation_count"),
                "paper_count": row.get("paper_count") or prof.get("paper_count"),
            }
        )

    return _enrich_paper_topic_rows(conn, hydrated)


def _lookup_cross_domain_evidence(
    conn: Any, *, topic: str, raw_query: str = ""
) -> list[dict]:
    company_rows = _lookup_companies_by_topic(conn, topic=topic)
    merged: list[dict] = []
    if chat_use_retrieval_service():
        retrieval_query = _cross_domain_retrieval_query(topic, raw_query)
        retrieval_service = get_retrieval_service()
        def _retrieve_domain(domains_tuple, augment_web, top_k):
            try:
                return retrieval_service.retrieve(
                    query=retrieval_query,
                    domains=domains_tuple,
                    final_top_k=top_k,
                    augment_with_web=augment_web,
                    web_top_n=5,
                )
            except Exception as exc:
                logger.warning(
                    "Cross-domain retrieval failed for topic %r domains %s: %s",
                    retrieval_query, domains_tuple, exc,
                )
                return []

        # Run professor / paper / company retrieves concurrently (I/O-bound:
        # embed + Milvus search + rerank + web). Wall-time = max(1) not sum.
        # Company includes web augment (augment_with_web=True) — the primary
        # semantic path for category queries; SQL keyword pass below is a
        # second path, both deduped-fused.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = [
                ex.submit(_retrieve_domain, ("professor",), False, 5),
                ex.submit(_retrieve_domain, ("paper",), False, 5),
                ex.submit(_retrieve_domain, ("company",), True, 10),
            ]
            for f in futures:
                merged.extend(_evidence_list_from_retrieval(f.result()))

    for row in company_rows:
        company_id = row.get("company_id") or row.get("id") or row.get("canonical_name") or row.get("name")
        company_name = row.get("canonical_name") or row.get("name") or ""
        merged.append(
            {
                "type": "company",
                "id": company_id,
                "title": company_name,
                "snippet": row.get("business") or row.get("industry") or "",
                "url": row.get("url"),
                "score": row.get("score", 0.0),
                "company_id": company_id,
                "canonical_name": company_name,
                "industry": row.get("industry"),
                "business": row.get("business"),
                "total_count": row.get("total_count"),
            }
        )

    deduped: list[dict] = []
    seen: set[tuple[str | None, Any]] = set()
    for row in merged:
        key = (row.get("type"), row.get("id"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return _hydrate_cross_domain_evidence(conn, deduped)


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


def _prof_rich_profile_facts(conn: Any, professor_id: str) -> dict[str, Any]:
    """Rich facts for synthesis depth: profile_summary + awards + education +
    work_experience + academic_positions.

    These exist in the collected data (e.g. 丁文伯 has 11 awards, education, work
    history, academic positions) but were never surfaced to synthesis, so the LLM
    emitted shallow answers (basic info + paper counts). Surfacing them lets the
    synthesis generate the deep prose the standard answers expect.
    """
    facts: dict[str, Any] = {}
    summary_row = conn.execute(
        "SELECT profile_summary FROM professor WHERE professor_id = %s",
        (professor_id,),
    ).fetchone()
    summary = (summary_row or {}).get("profile_summary") if summary_row else None
    if summary and summary.strip():
        facts["profile_summary"] = summary.strip()
    for key, ftype in (
        ("awards", "award"),
        ("education", "education"),
        ("work_experience", "work_experience"),
        ("academic_positions", "academic_position"),
    ):
        rows = conn.execute(
            """
            SELECT value_raw FROM professor_fact
             WHERE professor_id = %s AND fact_type = %s AND status = 'active'
             ORDER BY created_at
             LIMIT 12
            """,
            (professor_id, ftype),
        ).fetchall()
        values = [r["value_raw"] for r in rows if (r.get("value_raw") or "").strip()]
        if values:
            facts[key] = values
    return facts


def _company_rich_facts(conn: Any, company_id: str) -> dict[str, Any]:
    """Rich company facts for synthesis depth: products + team members + news.

    These exist in company_product / company_team_member / company_news_item
    but were never surfaced to synthesis. E.g. 爱博合创 has 10 products
    (PANVIS®系列), 14 team members (郭书祥/郭健), 10 news items — none reached
    the LLM. Surfacing them lets the synthesis cover the specific facts the
    standard expects (products, founders, market evaluation).
    """
    facts: dict[str, Any] = {}

    # Products (top 5)
    rows = conn.execute(
        """
        SELECT canonical_name, short_description, product_category
          FROM company_product
         WHERE company_id = %s
         ORDER BY confidence DESC NULLS LAST, canonical_name
         LIMIT 5
        """,
        (company_id,),
    ).fetchall()
    products = []
    for r in rows:
        name = (r.get("canonical_name") or "").strip() if r else ""
        if not name:
            continue
        desc = (r.get("short_description") or "").strip()
        cat = (r.get("product_category") or "").strip()
        entry = name
        if cat:
            entry += f"（{cat}）"
        if desc:
            entry += f"：{desc[:200]}"
        products.append(entry)
    if products:
        facts["company_products"] = products

    # Team members (top 5)
    rows = conn.execute(
        """
        SELECT raw_name, raw_role, raw_intro
          FROM company_team_member
         WHERE company_id = %s
         ORDER BY member_order NULLS LAST, raw_name
         LIMIT 5
        """,
        (company_id,),
    ).fetchall()
    members = []
    for r in rows:
        name = (r.get("raw_name") or "").strip() if r else ""
        if not name:
            continue
        role = (r.get("raw_role") or "").strip()
        intro = (r.get("raw_intro") or "").strip()
        entry = name
        if role:
            entry += f"（{role}）"
        if intro:
            entry += f"：{intro[:200]}"
        members.append(entry)
    if members:
        facts["company_team"] = members

    # News items (top 3 — for market evaluation / recent events)
    rows = conn.execute(
        """
        SELECT title, summary_clean
          FROM company_news_item
         WHERE company_id = %s
         ORDER BY published_at DESC NULLS LAST, fetched_at DESC
         LIMIT 3
        """,
        (company_id,),
    ).fetchall()
    news = []
    for r in rows:
        title = (r.get("title") or "").strip() if r else ""
        summary = (r.get("summary_clean") or "").strip()
        entry = title
        if summary:
            entry += f"：{summary[:300]}"
        news.append(entry)
    if news:
        facts["company_news"] = news

    return facts


def _compact_prof_rich(facts: dict[str, Any]) -> str:
    """Compact one-line rich-fact string for a professor list entry.

    Picks the 1-2 highest-signal facts (top award + research summary) so a list
    query surfaces depth without token bloat. Returns '' if nothing notable.
    """
    if not facts:
        return ""
    parts: list[str] = []
    awards = facts.get("awards") or []
    if awards:
        parts.append(f"奖项：{str(awards[0])[:80]}")
    summary = (facts.get("profile_summary") or "").strip()
    if summary:
        parts.append(f"研究概要：{summary[:100]}")
    if not parts:
        edu = facts.get("education") or []
        if edu:
            parts.append(f"教育：{str(edu[0])[:80]}")
    return "；".join(parts)[:200]


def _compact_company_rich(facts: dict[str, Any]) -> str:
    """Compact one-line rich-fact string for a company list entry.

    Picks flagship product + founder so a list query surfaces depth.
    """
    if not facts:
        return ""
    parts: list[str] = []
    products = facts.get("company_products") or []
    if products:
        parts.append(f"产品：{str(products[0])[:100]}")
    team = facts.get("company_team") or []
    if team:
        parts.append(f"团队：{str(team[0])[:80]}")
    return "；".join(parts)[:200]


def _enrich_list_entities(
    structured_payload: dict[str, Any],
    *,
    conn: Any,
    prof_rich_fn: Any = _prof_rich_profile_facts,
    company_rich_fn: Any = _company_rich_facts,
) -> None:
    """Attach a compact `rich_summary` to the top list entities (in place).

    List queries return matched_professors / matched_objects with name+snippet
    only; the rich-fact fetchers were never called for them, so synthesis saw
    shallow detail. This fetches rich facts for the top-3 of each and stores a
    compact one-liner the list renderers surface. Fetchers are injectable for
    unit testing (no DB needed).
    """
    for prof in (structured_payload.get("matched_professors") or [])[:10]:
        if not isinstance(prof, dict):
            continue
        pid = prof.get("professor_id")
        if not pid:
            continue
        compact = _compact_prof_rich(prof_rich_fn(conn, str(pid)))
        if compact:
            prof["rich_summary"] = compact
    company_enrich_limit = structured_payload.get("matched_objects_enrich_limit", 10)
    if not isinstance(company_enrich_limit, int) or company_enrich_limit < 0:
        company_enrich_limit = 10
    for obj in (structured_payload.get("matched_objects") or [])[:company_enrich_limit]:
        if not isinstance(obj, dict):
            continue
        cid = obj.get("company_id")
        if not cid:
            continue  # only companies have a rich-facts fetcher; papers/patents skipped
        compact = _compact_company_rich(company_rich_fn(conn, str(cid)))
        if compact:
            obj["rich_summary"] = compact


def _paper_rich_fields(conn: Any, paper_id: str) -> dict[str, Any]:
    """Rich paper fields for synthesis depth: abstract_clean/summary_zh + authors.

    The paper profile payload only carries title/year/venue/citation_count; the
    abstract + authors exist in the paper table but were never surfaced to the LLM.
    """
    row = conn.execute(
        "SELECT abstract_clean, summary_zh, authors_display FROM paper WHERE paper_id = %s",
        (paper_id,),
    ).fetchone()
    if not row:
        return {}
    out: dict[str, Any] = {}
    abstract_clean = (row.get("abstract_clean") or "").strip()
    summary_zh = (row.get("summary_zh") or "").strip()
    if abstract_clean:
        out["abstract_clean"] = abstract_clean
    if summary_zh:
        out["summary_zh"] = summary_zh
    authors_display = row.get("authors_display")
    if authors_display:
        # authors_display is a single display string ("Name1, Name2, ..."); keep it as
        # one entry so _build_evidence_blocks renders the full author list in one block.
        if isinstance(authors_display, (list, tuple)):
            names = [str(a) for a in authors_display if a]
            if names:
                out["authors"] = names
        elif isinstance(authors_display, str) and authors_display.strip():
            out["authors"] = [authors_display.strip()]
    return out


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
         ORDER BY
           CASE WHEN patent_type = 'invention' THEN 0 ELSE 1 END,
           grant_date DESC NULLS LAST,
           filing_date DESC NULLS LAST
         LIMIT 30
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


def _prof_paper_list_intent(query: str) -> bool:
    """True when a professor-anchored query asks to LIST the professor's papers (vs. a profile).

    "X教授发表了哪些论文" / "X的代表作" / "X的论文" → True. A bare profile query
    ("介绍X" / "X的研究方向") → False. Guards the A_prof_papers branch of
    `_professor_profile_or_papers_response` (paper-retrievability-baseline Type2 fix).
    """
    return bool(
        re.search(
            r"(发表.{0,4}论文|哪些论文|什么论文|的论文|代表作|代表论文|著作|论文列表|所有论文)",
            query,
        )
    )


def _professor_profile_or_papers_response(
    conn, query: str, prof: dict, topics: list[str], n_papers: int,
):
    """Return A_prof_papers (paper-list intent + verified papers) or A_prof_profile.

    Paper-list intent ("X教授发表了哪些论文" / "X的代表作"): list the professor's verified
    papers via the professor→paper related-objects SQL, instead of the count-only profile.
    Closes the paper-retrievability-baseline Type2 gap (professor→paper was 1/9 — the profile
    only mentioned papers incidentally). Falls back to the profile when there is no paper-list
    intent or the professor has no verified papers.
    """
    prof_id = prof["professor_id"]
    prof_citation = ChatCitation(
        type="professor",
        id=prof_id,
        label=f"{prof['canonical_name']} - {prof.get('institution') or '单位未知'}",
        url=f"/browse#professor/{prof_id}",
    )
    base_payload = {
        "professor_id": prof_id,
        "canonical_name": prof["canonical_name"],
        "institution": prof.get("institution"),
        "research_topics": topics,
        "verified_paper_count": n_papers,
        **_professor_metric_payload(prof),
    }
    if _prof_paper_list_intent(query):
        papers = _lookup_verified_papers_for_prof(conn, professor_id=prof_id)
        if papers:
            return _build_chat_response(
                conn=conn,
                query=query,
                query_type="A_prof_papers",
                answer_text=_answer_prof_papers(prof, papers),
                citations=[prof_citation] + [
                    ChatCitation(
                        type="paper",
                        id=p["paper_id"],
                        label=f"{p.get('year') or '?'} · {p.get('title_clean') or p['paper_id']}",
                        url=_local_paper_detail_url(p["paper_id"]),
                    )
                    for p in papers
                ],
                structured_payload={
                    **base_payload,
                    "papers": [
                        {
                            "paper_id": p["paper_id"],
                            "title_clean": p.get("title_clean"),
                            "year": p.get("year"),
                            "citation_count": p.get("citation_count"),
                        }
                        for p in papers
                    ],
                },
            )
    return _build_chat_response(
        conn=conn,
        query=query,
        query_type="A_prof_profile",
        answer_text=_answer_prof_profile(prof, topics, n_papers),
        citations=[prof_citation],
        structured_payload=base_payload,
    )


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


def _answer_domain_topic_list(domain: str, topic: str, rows: list[dict]) -> str:
    label = _TARGET_DOMAIN_LABELS.get(domain, "结果")
    if not rows:
        return f"未找到与 {topic!r} 相关的{label}。"
    total = rows[0].get("total_count", len(rows))
    header = (
        f"共找到 {total} 个{label}（显示前 {min(len(rows), 10)} 个）："
        if total > len(rows) or len(rows) > 10
        else f"共找到 {total} 个{label}："
    )
    lines = [header, ""]
    if domain == "paper" and any(
        row.get("quality_status") and row.get("quality_status") != "ready"
        for row in rows
    ):
        lines.append("论文域质量门尚未完全完成，以下为检索候选，需结合来源复核。")
        lines.append("")
    for row in rows[:10]:
        title = (
            row.get("canonical_name")
            or row.get("title")
            or row.get("title_clean")
            or row.get("patent_number")
            or row.get("id")
        )
        if domain == "company":
            snippet = row.get("snippet") or row.get("industry") or row.get("business") or ""
        else:
            snippet = row.get("industry") or row.get("snippet") or row.get("business") or ""
        suffix = f" — {snippet[:60]}" if snippet else ""
        lines.append(f"  • {title}{suffix}")
    remaining = total - min(len(rows), 10)
    if remaining > 0:
        lines.append(f"  ... (另有 {remaining} 个未列出)")
    return "\n".join(lines)


def _enrich_paper_topic_rows(conn: Any, rows: list[dict]) -> list[dict]:
    paper_ids = [
        str(row.get("paper_id") or row.get("id") or "")
        for row in rows
        if row.get("paper_id") or row.get("id")
    ]
    if not paper_ids:
        return rows
    unique_ids = list(dict.fromkeys(paper_ids))
    placeholders = ", ".join(["%s"] * len(unique_ids))
    try:
        db_rows = conn.execute(
            f"""
            SELECT paper_id, title_clean, year, venue, identity_status, quality_status
              FROM paper
             WHERE paper_id IN ({placeholders})
            """,
            tuple(unique_ids),
        ).fetchall()
    except Exception as exc:
        logger.warning("Paper topic row enrichment failed: %s", exc)
        return rows

    by_id = {str(row["paper_id"]): dict(row) for row in db_rows}
    enriched: list[dict] = []
    for row in rows:
        paper_id = str(row.get("paper_id") or row.get("id") or "")
        db_row = by_id.get(paper_id)
        if not db_row:
            enriched.append(row)
            continue
        title = db_row.get("title_clean") or row.get("title") or paper_id
        enriched.append(
            {
                **row,
                "title": title,
                "title_clean": title,
                "year": row.get("year") or db_row.get("year"),
                "venue": row.get("venue") or db_row.get("venue"),
                "identity_status": row.get("identity_status")
                or db_row.get("identity_status"),
                "quality_status": row.get("quality_status")
                or db_row.get("quality_status"),
            }
        )
    return enriched


def _filter_topic_rows_for_user_answer(
    domain: str,
    rows: list[dict],
    *,
    ready_only: bool = False,
) -> list[dict]:
    if domain != "paper":
        return rows
    filtered = [
        row
        for row in rows
        if row.get("quality_status") != "rejected"
        and row.get("identity_status") != "rejected"
    ]
    if not ready_only:
        return filtered
    return [row for row in filtered if row.get("quality_status") == "ready"]


def _dedupe_topic_rows(domain: str, rows: list[dict]) -> list[dict]:
    id_key = domain_id_key(domain)
    ordered_keys: list[str] = []
    by_key: dict[str, dict] = {}

    for index, row in enumerate(rows):
        key = _topic_row_dedupe_key(domain, row, id_key=id_key) or f"__row_{index}"
        if key not in by_key:
            ordered_keys.append(key)
            by_key[key] = dict(row)
            continue
        by_key[key] = _merge_topic_duplicate_row(by_key[key], row)

    return [by_key[key] for key in ordered_keys]


def _topic_row_dedupe_key(domain: str, row: dict, *, id_key: str) -> str:
    if domain == "paper":
        title = str(row.get("title_clean") or row.get("title") or "").strip()
        normalized_title = re.sub(r"\W+", "", title.lower(), flags=re.UNICODE)
        if len(normalized_title) >= 8:
            return f"title:{normalized_title}"
    object_id = str(row.get(id_key) or row.get("id") or "").strip()
    return f"id:{object_id}" if object_id else ""


def _merge_topic_duplicate_row(existing: dict, candidate: dict) -> dict:
    existing_score = _topic_row_score(existing)
    candidate_score = _topic_row_score(candidate)
    primary, secondary = (
        (candidate, existing)
        if candidate_score > existing_score
        else (existing, candidate)
    )
    merged = dict(primary)
    for key, value in secondary.items():
        if not _has_topic_row_value(merged.get(key)) and _has_topic_row_value(value):
            merged[key] = value
    return merged


def _topic_row_score(row: dict) -> float:
    value = row.get("score")
    if isinstance(value, (int, float)):
        return float(value)
    return -1.0


def _has_topic_row_value(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _augment_rows_with_web(query: str, rows: list[dict], *, web_top_n: int = 5) -> list[dict]:
    """Append web-search results as type='web' rows (closes the FM1a coverage gap).

    Surfaces entities absent from the local DB (e.g. well-known market leaders never
    ingested) so they appear in matched_objects/citations. Best-effort: on any failure
    returns rows unchanged. Gated by CHAT_AUGMENT_WEB (default on).
    """
    if os.environ.get("CHAT_AUGMENT_WEB", "1") == "0":
        return rows
    provider = _get_web_search_provider_or_none()
    if provider is None:
        return rows
    try:
        payload = provider.search(query)
    except Exception as exc:  # noqa: BLE001 - web is best-effort augmentation
        logger.warning("Web row augmentation failed for %r: %s", query, exc)
        return rows
    organic = payload.get("organic") or payload.get("results") or []
    existing_urls = {row.get("url") for row in rows if row.get("url")}
    web_rows: list[dict] = []
    for index, item in enumerate(organic):
        if len(web_rows) >= web_top_n:
            break
        url = item.get("link") or item.get("url") or ""
        title = (item.get("title") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        if not (title or snippet):
            continue
        if url and url in existing_urls:
            continue
        existing_urls.add(url)
        web_rows.append(
            {
                "type": "web",
                "source_type": "web",
                "id": url or f"web-{index}",
                "title": title,
                "snippet": snippet,
                "url": url,
                "score": 0.0,
            }
        )
    return rows + web_rows


def _lookup_domain_by_topic(
    conn: Any,
    *,
    domain: str,
    topic: str,
    limit: int,
    raw_query: str = "",
) -> list[dict]:
    if domain == "company":
        lookup_topic = _company_lookup_topic(topic, raw_query)
        sql_rows = _lookup_companies_by_topic(conn, topic=lookup_topic)
        if sql_rows:
            selected_rows = _select_company_leaders_step1(
                sql_rows,
                raw_query or lookup_topic,
            )
            return _company_topic_response_rows(selected_rows)
        if not chat_use_retrieval_service():
            return []
    if domain == "professor":
        return _lookup_professors_by_topic(
            conn,
            institutions=_SZ_INSTITUTIONS_ALL,
            topic=topic,
            limit=limit,
        )
    if not chat_use_retrieval_service():
        return []
    if domain == "paper":
        for ready_only in (True, False):
            try:
                results = get_retrieval_service().retrieve(
                    query=topic,
                    domains=(domain,),
                    candidate_limit=64,
                    final_top_k=limit,
                    filter_by_quality_status=ready_only,
                )
            except Exception as exc:
                logger.warning("%s retrieval failed for topic %r: %s", domain, topic, exc)
                return []
            rows = _evidence_list_from_retrieval(results)
            rows = _enrich_paper_topic_rows(conn, rows)
            rows = _filter_topic_rows_for_user_answer(
                domain,
                rows,
                ready_only=ready_only,
            )
            rows = _dedupe_topic_rows(domain, rows)
            if rows or not ready_only:
                return rows
        return []
    try:
        results = get_retrieval_service().retrieve(
            query=topic,
            domains=(domain,),
            candidate_limit=64,
            final_top_k=limit,
            filter_by_quality_status=None,
            augment_with_web=os.environ.get("CHAT_AUGMENT_WEB", "1") != "0",
            web_top_n=5,
        )
        rows = _evidence_list_from_retrieval(results)
        rows = _dedupe_topic_rows(domain, rows)
        return rows
    except Exception as exc:
        logger.warning("%s retrieval failed for topic %r: %s", domain, topic, exc)
        return []


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


_TARGET_DOMAIN_LABELS = {
    "professor": "教授",
    "paper": "论文",
    "company": "企业",
    "patent": "专利",
}
_SET_TRAVERSAL_SOURCE_CAP = 10
_SET_TRAVERSAL_TARGET_CAP = 10


def _relation_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    role_type = row.get("role_type") or row.get("link_role")
    if role_type:
        metadata["role_type"] = role_type
    for key in ("link_status", "match_reason", "link_role"):
        value = row.get(key)
        if value is not None and value != "":
            metadata[key] = value
    return metadata


def _row_display_label(domain: str, row: dict[str, Any], fallback: str = "") -> str:
    if domain in {"professor", "company"}:
        label = row.get("canonical_name") or row.get("name") or row.get("title")
    elif domain == "paper":
        label = row.get("title") or row.get("title_clean")
    else:
        label = row.get("patent_number") or row.get("title") or row.get("title_clean")
    return str(label or row.get("id") or fallback)


def _link_status_label(status: Any) -> str:
    status_text = str(status or "").strip()
    if status_text == "candidate":
        return "候选"
    return status_text


def _relation_annotation(target: dict[str, Any]) -> str:
    parts: list[str] = []
    if role_type := target.get("role_type"):
        parts.append(str(role_type))
    if status := _link_status_label(target.get("link_status")):
        parts.append(status)
    return ", ".join(parts)


def _target_annotation(target_domain: str, target: dict[str, Any]) -> str:
    label = _row_display_label(target_domain, target, str(target.get("id") or ""))
    relation = _relation_annotation(target)
    return f"{label}（{relation}）" if relation else label


def _member_backlink_annotation(
    member: dict[str, Any],
    target: dict[str, Any],
) -> str:
    relation = _relation_annotation(target)
    label = str(member.get("member_label") or member.get("member_id") or "")
    return f"{label}（{relation}）" if relation else label


def _dedupe_set_traversal_targets(
    mapping: list[dict[str, Any]],
    target_domain: str,
) -> list[dict[str, Any]]:
    id_key = domain_id_key(target_domain)
    seen: set[str] = set()
    targets: list[dict[str, Any]] = []
    for member in mapping:
        for target in member.get("targets") or []:
            target_id = str(target.get(id_key) or target.get("id") or "").strip()
            if not target_id or target_id in seen:
                continue
            seen.add(target_id)
            targets.append(dict(target))
    return targets


def _render_set_traversal_answer(
    *,
    query: str,
    source_domain: str,
    target_domain: str,
    mapping: list[dict[str, Any]],
    unique_targets: list[dict[str, Any]],
    displayed_targets: list[dict[str, Any]],
    truncated_source_count: int,
) -> str:
    source_label = _TARGET_DOMAIN_LABELS.get(source_domain, "结果")
    target_label = _TARGET_DOMAIN_LABELS.get(target_domain, "关联对象")
    member_count = len(mapping)
    linked_member_count = sum(1 for member in mapping if member.get("targets"))
    target_count = len(unique_targets)
    lines = [
        (
            f"上轮 {member_count} 位{source_label}中，{linked_member_count} 位有"
            f"{target_label}关联记录，共涉及 {target_count} 个{target_label}。"
            f"其余 {member_count - linked_member_count} 位暂无收录。"
        )
    ]
    if truncated_source_count > 0:
        lines.append(
            f"本次仅处理前 {member_count} 位{source_label}，"
            f"还有 {truncated_source_count} 位未处理。"
        )
    lines.append("")

    if "分别" in query:
        lines.append(f"按{source_label}分别列出关联{target_label}：")
        for member in mapping:
            member_label = str(member.get("member_label") or member.get("member_id"))
            targets = member.get("targets") or []
            if not targets:
                lines.append(f"  • {member_label}：暂无收录")
                continue
            target_text = "、".join(
                _target_annotation(target_domain, target) for target in targets
            )
            lines.append(f"  • {member_label}：{target_text}")
        return "\n".join(lines)

    if not unique_targets:
        lines.append(f"暂未找到这些{source_label}关联的{target_label}记录。")
    else:
        header = f"关联{target_label}："
        if len(unique_targets) > len(displayed_targets):
            header = (
                f"关联{target_label}（显示前 {len(displayed_targets)} 个，"
                f"共 {len(unique_targets)} 个）："
            )
        lines.append(header)
        id_key = domain_id_key(target_domain)
        for displayed in displayed_targets:
            displayed_id = str(displayed.get(id_key) or displayed.get("id") or "")
            backlinks: list[str] = []
            for member in mapping:
                for target in member.get("targets") or []:
                    target_id = str(target.get(id_key) or target.get("id") or "")
                    if target_id == displayed_id:
                        backlinks.append(_member_backlink_annotation(member, target))
            target_label_text = _row_display_label(
                target_domain,
                displayed,
                displayed_id,
            )
            lines.append(f"  • {target_label_text}：{'、'.join(backlinks)}")

    empty_members = [
        str(member.get("member_label") or member.get("member_id"))
        for member in mapping
        if not member.get("targets")
    ]
    if empty_members:
        lines.append(f"暂无收录：{'、'.join(empty_members)}")
    return "\n".join(lines)


def _related_row_to_chat_row(domain: str, row: dict[str, Any]) -> dict[str, Any]:
    if domain == "professor":
        professor_id = str(row.get("professor_id") or row.get("id") or "")
        name = str(row.get("canonical_name") or row.get("name") or professor_id)
        payload = {
            "type": "professor",
            "id": professor_id,
            "professor_id": professor_id,
            "title": name,
            "canonical_name": name,
            "institution": row.get("institution")
            or row.get("primary_affiliation_institution"),
            "snippet": row.get("profile_summary") or row.get("match_reason") or "",
            "score": row.get("score", 1.0),
        }
        payload.update(_relation_metadata(row))
        return payload
    if domain == "paper":
        paper_id = str(row.get("paper_id") or row.get("id") or "")
        title = str(row.get("title_clean") or row.get("title") or paper_id)
        payload = {
            "type": "paper",
            "id": paper_id,
            "paper_id": paper_id,
            "title": title,
            "title_clean": title,
            "year": row.get("year"),
            "venue": row.get("venue"),
            "snippet": row.get("abstract_clean") or row.get("match_reason") or "",
            "score": row.get("score", 1.0),
        }
        payload.update(_relation_metadata(row))
        return payload
    if domain == "company":
        company_id = str(row.get("company_id") or row.get("id") or "")
        name = str(row.get("canonical_name") or row.get("name") or company_id)
        payload = {
            "type": "company",
            "id": company_id,
            "company_id": company_id,
            "title": name,
            "canonical_name": name,
            "industry": row.get("industry"),
            "business": row.get("business")
            or row.get("description")
            or row.get("profile_summary"),
            "snippet": row.get("match_reason") or row.get("description") or "",
            "score": row.get("score", 1.0),
        }
        payload.update(_relation_metadata(row))
        return payload
    patent_id = str(row.get("patent_id") or row.get("id") or "")
    title = str(row.get("title_clean") or row.get("title") or patent_id)
    payload = {
        "type": "patent",
        "id": patent_id,
        "patent_id": patent_id,
        "patent_number": row.get("patent_number"),
        "title": title,
        "title_clean": title,
        "patent_type": row.get("patent_type"),
        "snippet": row.get("abstract_clean") or row.get("match_reason") or "",
        "score": row.get("score", 1.0),
    }
    payload.update(_relation_metadata(row))
    return payload


_OPEN_PREDICATE_SYSTEM_PROMPT = """你是深圳科创数据平台的集合筛选审计器。
任务：只根据给定成员字段，逐个判断成员是否满足用户的筛选条件。
输出必须是 JSON 数组，不要输出解释性正文。每个元素格式：
{"member_id": "...", "verdict": true|false|"unknown", "evidence_field": "字段名", "quote": "原文短摘"}
verdict=true 表示证据支持满足；false 表示证据支持不满足；unknown 表示字段缺失或证据不足。"""


def _domain_list_payload_key(domain: str) -> str:
    return {
        "professor": "matched_professors",
        "paper": "papers",
        "company": "companies",
        "patent": "patents",
    }[domain]


def _coerce_narrowing_member_row(
    domain: str,
    row: dict[str, Any] | None,
    member_id: str,
) -> dict[str, Any]:
    id_key = domain_id_key(domain)
    payload = dict(row or {})
    payload.setdefault(id_key, member_id)
    payload.setdefault("id", member_id)
    payload.setdefault("type", domain)
    return payload


def _lookup_narrowing_member_rows(
    conn: Any,
    *,
    domain: str,
    member_ids: list[str],
    rich: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for member_id in member_ids:
        row: dict[str, Any] | None = None
        try:
            if domain == "professor":
                row = _lookup_professor_by_id(conn, professor_id=member_id)
                if row and rich:
                    try:
                        row["research_topics"] = _prof_research_topics(conn, member_id)
                    except Exception as exc:  # noqa: BLE001 - enrichment best-effort
                        logger.warning("Professor narrowing topics fetch failed: %s", exc)
                    try:
                        row.update(_prof_rich_profile_facts(conn, member_id))
                    except Exception as exc:  # noqa: BLE001 - enrichment best-effort
                        logger.warning("Professor narrowing rich fetch failed: %s", exc)
            elif domain == "company":
                row = _lookup_company_by_id(conn, company_id=member_id)
                if row and rich:
                    try:
                        row.update(_company_rich_facts(conn, member_id))
                    except Exception as exc:  # noqa: BLE001 - enrichment best-effort
                        logger.warning("Company narrowing rich fetch failed: %s", exc)
            elif domain == "paper":
                row = _lookup_paper_by_id(conn, paper_id=member_id)
            elif domain == "patent":
                row = _lookup_patent_by_id(conn, patent_id=member_id)
        except Exception as exc:  # noqa: BLE001 - one missing row must not abort narrowing
            logger.warning("Narrowing member lookup failed: %s:%s: %s", domain, member_id, exc)
        rows.append(_coerce_narrowing_member_row(domain, row, member_id))
    return rows


def _chip_predicate_payload(predicate: ChipPredicate) -> dict[str, Any]:
    return {
        "kind": predicate.kind,
        "domain": predicate.domain,
        "param": dict(predicate.param),
    }


def _chip_predicate_phrase(predicate: ChipPredicate) -> str:
    if predicate.kind == "region":
        return f"在{predicate.param.get('city') or '深圳'}"
    if predicate.kind == "recency":
        if predicate.param.get("mode") == "year":
            return f"{predicate.param.get('year')}年"
        years = predicate.param.get("years") or ""
        return f"近{years}年"
    if predicate.kind == "grant_status":
        return "已授权"
    if predicate.kind == "applicant_type":
        return f"申请人是{predicate.param.get('type') or '企业'}"
    return "满足条件"


def _verdict_rank(verdict: bool | None) -> int:
    if verdict is True:
        return 0
    if verdict is False:
        return 1
    return 2


def _narrowing_evidence_rows(domain: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_related_row_to_chat_row(domain, row) for row in rows]


def _render_chip_narrowing_answer(
    *,
    domain: str,
    predicate: ChipPredicate,
    verdicts: list[dict[str, Any]],
    total: int,
) -> str:
    label = _TARGET_DOMAIN_LABELS.get(domain, "结果")
    phrase = _chip_predicate_phrase(predicate)
    satisfied = sum(1 for item in verdicts if item["verdict"] is True)
    unsatisfied = sum(1 for item in verdicts if item["verdict"] is False)
    unknown = sum(1 for item in verdicts if item["verdict"] is None)
    lines = [
        f"上轮 {total} 个{label}中，{satisfied} 个{phrase}，{unsatisfied} 个不满足，{unknown} 个信息缺失。",
        "",
    ]
    for item in sorted(verdicts, key=lambda item: _verdict_rank(item["verdict"])):
        lines.append(f"  • {item['basis']}")
    return "\n".join(lines)


def _build_chip_narrowing_response(
    *,
    conn: Any,
    query: str,
    domain: str,
    source_ids: list[str],
    predicate: ChipPredicate,
) -> ChatResponse:
    member_rows = _lookup_narrowing_member_rows(
        conn,
        domain=domain,
        member_ids=source_ids,
    )
    verdicts: list[dict[str, Any]] = []
    satisfied_rows: list[dict[str, Any]] = []
    for row in member_rows:
        verdict, basis = evaluate_chip_predicate(domain, row, predicate)
        member_id = str(row.get(domain_id_key(domain)) or row.get("id") or "")
        label = _row_display_label(domain, row, member_id)
        verdicts.append(
            {
                "member_id": member_id,
                "label": label,
                "verdict": verdict,
                "basis": basis,
            }
        )
        if verdict is True:
            satisfied_rows.append(row)

    evidence_rows = _narrowing_evidence_rows(domain, satisfied_rows)
    structured_payload: dict[str, Any] = {
        "source_ids": source_ids,
        "narrowing_domain": domain,
        "narrowing_mechanism": "chip",
        "predicate": _chip_predicate_payload(predicate),
        "verdicts": verdicts,
        "retrieval_evidence": evidence_rows,
        _domain_list_payload_key(domain): evidence_rows,
    }
    return _build_chat_response(
        conn=conn,
        query=query,
        query_type="D_narrowing",
        answer_text=_render_chip_narrowing_answer(
            domain=domain,
            predicate=predicate,
            verdicts=verdicts,
            total=len(source_ids),
        ),
        citations=_chat_citations_from_result_rows(evidence_rows),
        structured_payload=structured_payload,
        skip_synthesis=True,
    )


def _strip_json_response(text: str) -> str:
    stripped = text.strip()
    if match := re.search(r"```(?:json)?\s*(?P<body>.*?)\s*```", stripped, re.DOTALL):
        stripped = match.group("body").strip()
    start = min(
        [idx for idx in (stripped.find("["), stripped.find("{")) if idx >= 0],
        default=0,
    )
    return stripped[start:]


def _normalize_open_verdict(raw: Any) -> bool | str:
    if raw is True or raw is False:
        return raw
    text = str(raw or "").strip().casefold()
    if text in {"true", "yes", "y", "满足", "是", "support", "supported"}:
        return True
    if text in {"false", "no", "n", "不满足", "否", "unsupported"}:
        return False
    return "unknown"


def _parse_open_predicate_verdicts(
    text: str,
    *,
    allowed_ids: set[str],
) -> list[dict[str, Any]]:
    parsed = json.loads(_strip_json_response(text))
    if isinstance(parsed, dict):
        parsed = parsed.get("verdicts") or parsed.get("results") or []
    if not isinstance(parsed, list):
        raise ValueError("open-predicate verdict payload must be a JSON array")
    verdicts: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        member_id = str(item.get("member_id") or item.get("id") or "").strip()
        if member_id not in allowed_ids:
            continue
        verdicts.append(
            {
                "member_id": member_id,
                "verdict": _normalize_open_verdict(item.get("verdict")),
                "evidence_field": str(item.get("evidence_field") or "").strip(),
                "quote": str(item.get("quote") or "").strip(),
            }
        )
    return verdicts


def _call_open_predicate_verdicts(
    *,
    query: str,
    domain: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    allowed_ids = {
        str(row.get(domain_id_key(domain)) or row.get("id") or "")
        for row in rows
    }
    evidence_text = json.dumps(
        {
            "domain": domain,
            "members": rows,
        },
        ensure_ascii=False,
        default=str,
    )
    try:
        llm_text = _call_gemma_synthesis(
            query,
            evidence_text,
            timeout=_CHAT_SYNTHESIS_TIMEOUT_SECONDS,
            system_prompt=_OPEN_PREDICATE_SYSTEM_PROMPT,
        )
    except Exception as exc:  # noqa: BLE001 - open lane can degrade to topic narrowing
        logger.warning("Open predicate batch LLM call failed: %s", exc)
        return None

    try:
        return _parse_open_predicate_verdicts(llm_text, allowed_ids=allowed_ids)
    except Exception as exc:  # noqa: BLE001 - retry per member on parse failure
        logger.warning("Open predicate batch parse failed, retrying per member: %s", exc)

    verdicts: list[dict[str, Any]] = []
    for row in rows:
        member_id = str(row.get(domain_id_key(domain)) or row.get("id") or "")
        member_text = json.dumps(
            {"domain": domain, "members": [row]},
            ensure_ascii=False,
            default=str,
        )
        try:
            llm_text = _call_gemma_synthesis(
                query,
                member_text,
                timeout=_CHAT_SYNTHESIS_TIMEOUT_SECONDS,
                system_prompt=_OPEN_PREDICATE_SYSTEM_PROMPT,
            )
            parsed = _parse_open_predicate_verdicts(
                llm_text,
                allowed_ids={member_id},
            )
        except Exception as exc:  # noqa: BLE001 - preserve audit as unknown
            logger.warning("Open predicate per-member parse failed for %s: %s", member_id, exc)
            parsed = []
        verdicts.extend(
            parsed
            or [
                {
                    "member_id": member_id,
                    "verdict": "unknown",
                    "evidence_field": "",
                    "quote": "",
                }
            ]
        )
    return verdicts


def _open_verdict_to_optional_bool(verdict: Any) -> bool | None:
    normalized = _normalize_open_verdict(verdict)
    if normalized is True:
        return True
    if normalized is False:
        return False
    return None


def _render_open_narrowing_answer(
    *,
    domain: str,
    verdicts: list[dict[str, Any]],
    total: int,
) -> str:
    label = _TARGET_DOMAIN_LABELS.get(domain, "结果")
    satisfied = sum(1 for item in verdicts if item["verdict"] is True)
    unsatisfied = sum(1 for item in verdicts if item["verdict"] is False)
    unknown = sum(1 for item in verdicts if item["verdict"] is None)
    lines = [
        f"上轮 {total} 个{label}中，{satisfied} 个满足，{unsatisfied} 个不满足，{unknown} 个信息缺失。",
        "",
    ]
    for item in sorted(verdicts, key=lambda item: _verdict_rank(item["verdict"])):
        lines.append(f"  • {item['basis']}")
    return "\n".join(lines)


def _build_open_predicate_narrowing_response(
    *,
    conn: Any,
    query: str,
    domain: str,
    source_ids: list[str],
) -> ChatResponse | None:
    member_rows = _lookup_narrowing_member_rows(
        conn,
        domain=domain,
        member_ids=source_ids,
        rich=True,
    )
    raw_verdicts = _call_open_predicate_verdicts(
        query=query,
        domain=domain,
        rows=member_rows,
    )
    if raw_verdicts is None:
        return None

    raw_by_id = {item["member_id"]: item for item in raw_verdicts}
    complete_raw_verdicts: list[dict[str, Any]] = []
    display_verdicts: list[dict[str, Any]] = []
    satisfied_rows: list[dict[str, Any]] = []
    for row in member_rows:
        member_id = str(row.get(domain_id_key(domain)) or row.get("id") or "")
        label = _row_display_label(domain, row, member_id)
        raw = raw_by_id.get(member_id) or {
            "member_id": member_id,
            "verdict": "unknown",
            "evidence_field": "",
            "quote": "",
        }
        verdict = _open_verdict_to_optional_bool(raw.get("verdict"))
        field = raw.get("evidence_field") or "evidence"
        quote = raw.get("quote") or "未提供可审计证据"
        verdict_text = "满足" if verdict is True else "不满足" if verdict is False else "信息缺失"
        complete_raw_verdicts.append(raw)
        display_verdicts.append(
            {
                "member_id": member_id,
                "label": label,
                "verdict": verdict,
                "basis": f"{label} - {field}: {quote} -> {verdict_text}",
            }
        )
        if verdict is True:
            satisfied_rows.append(row)

    evidence_rows = _narrowing_evidence_rows(domain, satisfied_rows)
    structured_payload: dict[str, Any] = {
        "source_ids": source_ids,
        "narrowing_domain": domain,
        "narrowing_mechanism": "open_predicate_llm",
        "open_predicate_verdicts": complete_raw_verdicts,
        "verdicts": display_verdicts,
        "retrieval_evidence": evidence_rows,
        _domain_list_payload_key(domain): evidence_rows,
    }
    return _build_chat_response(
        conn=conn,
        query=query,
        query_type="D_narrowing",
        answer_text=_render_open_narrowing_answer(
            domain=domain,
            verdicts=display_verdicts,
            total=len(source_ids),
        ),
        citations=_chat_citations_from_result_rows(evidence_rows),
        structured_payload=structured_payload,
        skip_synthesis=True,
    )


def _build_topic_narrowing_response(
    *,
    conn: Any,
    query: str,
    domain: str,
    source_ids: list[str],
    topic: str,
    degraded_from_open_predicate: bool = False,
) -> ChatResponse:
    rows = _lookup_narrowed_results(
        conn,
        domain=domain,
        allowed_ids=source_ids,
        topic=topic,
    )
    answer_text = answer_narrowed_results(domain, topic, rows, len(source_ids))
    structured_payload: dict[str, Any] = {
        "narrowing_domain": domain,
        "narrowing_topic": topic,
        "narrowing_mechanism": "topic",
        "narrowed_from_count": len(source_ids),
        "retrieval_evidence": rows,
    }
    if degraded_from_open_predicate:
        answer_text = f"按语义相关性筛选：\n{answer_text}"
        structured_payload["degraded_from_open_predicate"] = True
    return _build_chat_response(
        conn=conn,
        query=query,
        query_type="D_narrowing",
        answer_text=answer_text,
        citations=_chat_citations_from_result_rows(rows),
        structured_payload=structured_payload,
    )


def _answer_c_related_objects(
    source: SessionEntity,
    target_domain: str,
    rows: list[dict[str, Any]],
) -> str:
    target_label = _TARGET_DOMAIN_LABELS.get(target_domain, "关联对象")
    if not rows:
        return f"暂未收录{source.label}关联的{target_label}数据。"
    lines = [
        f"{source.label}关联的{target_label}如下（显示前 {min(len(rows), 5)} 条）：",
        "",
    ]
    for row in rows[:5]:
        title = (
            row.get("canonical_name")
            or row.get("title")
            or row.get("title_clean")
            or row.get("patent_number")
            or row.get("id")
        )
        if row.get("type") == "patent" and row.get("patent_number"):
            if row.get("title") and row["title"] != row["patent_number"]:
                title = f"{row['patent_number']} — {row['title']}"
            else:
                title = row["patent_number"]
        detail = row.get("institution") or row.get("venue") or row.get("industry") or ""
        suffix = f" — {detail}" if detail else ""
        lines.append(f"  • {title}{suffix}")
    return "\n".join(lines)


def _primary_payload_for_c_target(
    target_domain: str,
    row: dict[str, Any] | None,
) -> dict[str, Any]:
    if not row:
        return {}
    if target_domain == "professor":
        return {
            "professor_id": row.get("professor_id") or row.get("id"),
            "canonical_name": row.get("canonical_name") or row.get("title"),
        }
    if target_domain == "paper":
        return {
            "paper_id": row.get("paper_id") or row.get("id"),
            "title": row.get("title") or row.get("title_clean"),
        }
    if target_domain == "company":
        return {
            "company_id": row.get("company_id") or row.get("id"),
            "canonical_name": row.get("canonical_name") or row.get("title"),
        }
    if target_domain == "patent":
        return {
            "patent_id": row.get("patent_id") or row.get("id"),
            "patent_number": row.get("patent_number") or row.get("title"),
        }
    return {}


def _build_c_type_response(
    *,
    conn: Any,
    query: str,
    session: SessionContext,
    target_domain: str,
) -> ChatResponse | None:
    if target_domain not in _TARGET_DOMAINS:
        return None
    source = session.latest_entity_for_other_domains(target_domain)
    if source is None:
        target_label = _TARGET_DOMAIN_LABELS.get(target_domain, "目标")
        return ChatResponse(
            query=query,
            query_type="C_cross_domain_clarification",
            answer_text=f"请先确认要查询哪一个实体，再追问它关联的{target_label}。",
            citations=[],
            structured_payload={"target_domain": target_domain},
        )
    try:
        rows = get_retrieval_service().get_related_objects(
            source_domain=source.kind,
            source_id=source.id,
            target_domain=target_domain,
            limit=5,
        )
    except Exception as exc:
        logger.warning(
            "C type related lookup failed: %s:%s -> %s: %s",
            source.kind,
            source.id,
            target_domain,
            exc,
        )
        return None

    evidence_rows = [_related_row_to_chat_row(target_domain, row) for row in rows]
    citations = _chat_citations_from_result_rows(evidence_rows)
    structured_payload = {
        "source_domain": source.kind,
        "source_id": source.id,
        "source_label": source.label,
        "target_domain": target_domain,
        "retrieval_evidence": evidence_rows,
        **_primary_payload_for_c_target(
            target_domain,
            evidence_rows[0] if evidence_rows else None,
        ),
    }
    return _build_chat_response(
        conn=conn,
        query=query,
        query_type="C_cross_domain_related",
        answer_text=_answer_c_related_objects(source, target_domain, evidence_rows),
        citations=citations,
        structured_payload=structured_payload,
    )


def _build_c_fallback_a_response(
    *,
    conn: Any,
    query: str,
    target_domain: str,
) -> ChatResponse | None:
    if target_domain == "company":
        companies = _lookup_company(conn, name=query)
        if len(companies) == 1:
            company = companies[0]
            return _build_chat_response(
                conn=conn,
                query=query,
                query_type="A_company_profile",
                answer_text=_answer_company_profile(company),
                citations=[
                    ChatCitation(
                        type="company",
                        id=company["company_id"],
                        label=company["canonical_name"],
                        url=f"/browse#company/{company['company_id']}",
                    )
                ],
                structured_payload=_company_profile_payload(company),
            )
    if target_domain == "paper":
        papers = _lookup_paper(conn, title=query)
        if paper := _select_exact_paper_profile_match(query, papers):
            return _build_paper_profile_response(
                conn=conn,
                query=query,
                paper=paper,
            )
    if target_domain == "patent":
        patents = _lookup_patent(conn, query=query)
        if len(patents) == 1:
            patent = patents[0]
            return _build_chat_response(
                conn=conn,
                query=query,
                query_type="A_patent_profile",
                answer_text=_answer_patent_profile(patent),
                citations=[
                    ChatCitation(
                        type="patent",
                        id=patent["patent_id"],
                        label=patent.get("patent_number") or patent["patent_id"],
                        url=f"/browse#patent/{patent['patent_id']}",
                    )
                ],
                structured_payload={
                    "patent_id": patent["patent_id"],
                    "patent_number": patent.get("patent_number"),
                    "title_clean": patent.get("title_clean"),
                    "applicants_raw": patent.get("applicants_raw"),
                    "patent_type": patent.get("patent_type"),
                },
            )
    profs = _lookup_professor(conn, name=query, institutions=None)
    if len(profs) == 1:
        prof = profs[0]
        topics = _prof_research_topics(conn, prof["professor_id"])
        n_papers = _prof_paper_count(conn, prof["professor_id"])
        return _professor_profile_or_papers_response(conn, query, prof, topics, n_papers)
    return None


def _professor_metric_payload(prof: dict) -> dict[str, int | None]:
    return {
        "h_index": prof.get("h_index"),
        "citation_count": prof.get("citation_count"),
        "paper_count": prof.get("paper_count"),
    }


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


def _professor_clarification(name: str, profs: list[dict]) -> ClarificationPayload | None:
    if len(profs) <= 1:
        return None
    ranked = sorted(
        profs,
        key=lambda p: (
            p.get("paper_count") or 0,
            p.get("citation_count") or 0,
            p.get("h_index") or 0,
        ),
        reverse=True,
    )
    options: list[CandidateOption] = []
    for prof in ranked[:5]:
        institution = prof.get("institution") or "单位未知"
        title = prof.get("title") or "职称未知"
        paper_count = prof.get("paper_count")
        hint_parts = [institution, title]
        if paper_count is not None:
            hint_parts.append(f"{paper_count} 篇论文")
        options.append(
            CandidateOption(
                id=prof["professor_id"],
                domain="professor",
                label=prof.get("canonical_name") or name,
                hint=" / ".join(hint_parts),
            )
        )
    if not options:
        return None
    return ClarificationPayload(
        prompt=f"找到 {len(profs)} 位名为 {name} 的教授，请选择具体对象。",
        options=options,
        default_id=options[0].id,
        omitted=max(0, len(profs) - len(options)),
    )


def _answer_ambiguous_companies(name: str, companies: list[dict]) -> str:
    lines = [
        f"找到 {len(companies)} 家与 {name!r} 匹配的企业，请选择具体对象：",
        "",
    ]
    for company in companies[:10]:
        industry = company.get("industry") or "行业未知"
        lines.append(f"  • {company.get('canonical_name') or name} — {industry}")
    return "\n".join(lines)


def _company_clarification(
    name: str, companies: list[dict]
) -> ClarificationPayload | None:
    if len(companies) <= 1:
        return None
    options: list[CandidateOption] = []
    for company in companies[:5]:
        industry = company.get("industry") or "行业未知"
        business = company.get("business") or company.get("description") or ""
        hint = " / ".join([part for part in (industry, business[:40]) if part])
        options.append(
            CandidateOption(
                id=company["company_id"],
                domain="company",
                label=company.get("canonical_name") or name,
                hint=hint,
            )
        )
    if not options:
        return None
    return ClarificationPayload(
        prompt=f"找到 {len(companies)} 家与 {name} 匹配的企业，请选择具体对象。",
        options=options,
        default_id=options[0].id,
        omitted=max(0, len(companies) - len(options)),
    )


def _answer_ambiguous_papers(name: str, papers: list[dict]) -> str:
    lines = [
        f"找到 {len(papers)} 篇与 {name!r} 匹配的论文，请选择具体对象：",
        "",
    ]
    for paper in papers[:10]:
        title = paper.get("title_clean") or paper.get("title") or name
        year = paper.get("year") or "年份未知"
        venue = paper.get("venue") or "来源未知"
        lines.append(f"  • {title} — {year} / {venue}")
    return "\n".join(lines)


def _paper_clarification(name: str, papers: list[dict]) -> ClarificationPayload | None:
    if len(papers) <= 1:
        return None
    options: list[CandidateOption] = []
    for paper in papers[:5]:
        title = paper.get("title_clean") or paper.get("title") or name
        hint_parts = [
            str(part)
            for part in (
                paper.get("year"),
                paper.get("venue"),
                f"{paper['citation_count']} 次引用"
                if paper.get("citation_count") is not None
                else None,
            )
            if part
        ]
        options.append(
            CandidateOption(
                id=paper["paper_id"],
                domain="paper",
                label=title,
                hint=" / ".join(hint_parts) or "论文",
            )
        )
    if not options:
        return None
    return ClarificationPayload(
        prompt=f"找到 {len(papers)} 篇与 {name} 匹配的论文，请选择具体对象。",
        options=options,
        default_id=options[0].id,
        omitted=max(0, len(papers) - len(options)),
    )


def _select_exact_paper_profile_match(name: str, papers: list[dict]) -> dict | None:
    if not papers:
        return None
    if len(papers) == 1:
        return papers[0]

    query_key = _paper_lookup_title_key(name)
    if not query_key:
        return None
    exact = [
        paper
        for paper in papers
        if _paper_lookup_title_key(
            str(paper.get("title_clean") or paper.get("title") or "")
        )
        == query_key
    ]
    if not exact:
        partial = [
            paper
            for paper in papers
            if _paper_lookup_title_key_matches_query(
                _paper_lookup_title_key(
                    str(paper.get("title_clean") or paper.get("title") or "")
                ),
                query_key,
            )
        ]
        if not partial:
            return None
        return sorted(partial, key=_paper_profile_match_rank, reverse=True)[0]
    return sorted(exact, key=_paper_profile_match_rank, reverse=True)[0]


def _paper_lookup_title_key(value: str) -> str:
    return "".join(char.casefold() for char in value if char.isalnum())


def _paper_lookup_title_key_matches_query(candidate_key: str, query_key: str) -> bool:
    if not candidate_key:
        return False
    if candidate_key == query_key:
        return True
    return (
        len(query_key) >= 32
        and len(candidate_key) > len(query_key)
        and query_key in candidate_key
    )


def _paper_profile_match_rank(paper: dict) -> tuple[int, int, int, int, int]:
    has_summary = 1 if str(paper.get("summary_zh") or "").strip() else 0
    has_abstract = 1 if str(paper.get("abstract_clean") or "").strip() else 0
    has_authors = 1 if str(paper.get("authors_display") or "").strip() else 0
    citation_count = paper.get("citation_count")
    if not isinstance(citation_count, int):
        citation_count = -1
    year = paper.get("year")
    if not isinstance(year, int):
        year = -1
    return (has_summary, has_abstract, has_authors, citation_count, year)


def _answer_ambiguous_patents(name: str, patents: list[dict]) -> str:
    lines = [
        f"找到 {len(patents)} 件与 {name!r} 匹配的专利，请选择具体对象：",
        "",
    ]
    for patent in patents[:10]:
        number = patent.get("patent_number") or patent.get("patent_id") or "编号未知"
        title = patent.get("title_clean") or patent.get("title") or name
        lines.append(f"  • {number} — {title}")
    return "\n".join(lines)


def _patent_clarification(
    name: str, patents: list[dict]
) -> ClarificationPayload | None:
    if len(patents) <= 1:
        return None
    options: list[CandidateOption] = []
    for patent in patents[:5]:
        number = patent.get("patent_number") or patent.get("patent_id") or name
        title = patent.get("title_clean") or patent.get("title") or ""
        hint_parts = [
            str(part)
            for part in (
                patent.get("patent_type"),
                patent.get("applicants_raw"),
                title[:40],
            )
            if part
        ]
        options.append(
            CandidateOption(
                id=patent["patent_id"],
                domain="patent",
                label=number,
                hint=" / ".join(hint_parts) or "专利",
            )
        )
    if not options:
        return None
    return ClarificationPayload(
        prompt=f"找到 {len(patents)} 件与 {name} 匹配的专利，请选择具体对象。",
        options=options,
        default_id=options[0].id,
        omitted=max(0, len(patents) - len(options)),
    )


def _build_company_profile_response(
    *,
    conn: Any,
    query: str,
    company: dict,
) -> ChatResponse:
    return _build_chat_response(
        conn=conn,
        query=query,
        query_type="A_company_profile",
        answer_text=_answer_company_profile(company),
        citations=[
            ChatCitation(
                type="company",
                id=company["company_id"],
                label=company["canonical_name"],
                url=f"/browse#company/{company['company_id']}",
            )
        ],
        structured_payload={
            **_company_profile_payload(company),
        },
    )


def _company_profile_payload(company: dict) -> dict[str, Any]:
    return {
        "company_id": company["company_id"],
        "canonical_name": company["canonical_name"],
        "industry": company.get("industry"),
        "business": company.get("business"),
        "description": company.get("description"),
        "products": company.get("products") or [],
        "application_scenarios": company.get("application_scenarios") or [],
        "recent_events": company.get("recent_events") or [],
    }


def _build_paper_profile_response(
    *,
    conn: Any,
    query: str,
    paper: dict,
) -> ChatResponse:
    return _build_chat_response(
        conn=conn,
        query=query,
        query_type="A_paper_profile",
        answer_text=_answer_paper_profile(paper),
        citations=[
            ChatCitation(
                type="paper",
                id=paper["paper_id"],
                label=paper.get("title_clean") or paper["paper_id"],
                url=_local_paper_detail_url(paper["paper_id"]),
            )
        ],
        structured_payload={
            "paper_id": paper["paper_id"],
            "title": paper.get("title_clean"),
            "year": paper.get("year"),
            "venue": paper.get("venue"),
            "citation_count": paper.get("citation_count"),
        },
    )


def _build_patent_profile_response(
    *,
    conn: Any,
    query: str,
    patent: dict,
) -> ChatResponse:
    return _build_chat_response(
        conn=conn,
        query=query,
        query_type="A_patent_profile",
        answer_text=_answer_patent_profile(patent),
        citations=[
            ChatCitation(
                type="patent",
                id=patent["patent_id"],
                label=patent.get("patent_number") or patent["patent_id"],
                url=f"/browse#patent/{patent['patent_id']}",
            )
        ],
        structured_payload={
            "patent_id": patent["patent_id"],
            "patent_number": patent.get("patent_number"),
            "title_clean": patent.get("title_clean"),
            "applicants_raw": patent.get("applicants_raw"),
            "patent_type": patent.get("patent_type"),
        },
    )


def llm_synthesis_enabled() -> bool:
    return os.getenv("CHAT_LLM_SYNTHESIS", "on").strip().lower() != "off"


def _suggested_followups(
    *,
    query_type: str,
    structured_payload: dict[str, Any],
    citations: list[ChatCitation],
    clarification: ClarificationPayload | None,
) -> list[str]:
    if clarification and clarification.options:
        return []

    domain = _followup_domain(query_type, structured_payload, citations)
    if query_type.startswith("A_"):
        if domain == "professor" or structured_payload.get("professor_id"):
            return [
                "看看他的论文",
                "他的专利有哪些",
                "他参与创立了哪些企业",
            ]
        if domain == "company" or structured_payload.get("company_id"):
            return [
                "这家公司有哪些专利",
                "这家公司相关论文有哪些",
                "找相似企业",
            ]
        if domain == "paper" or structured_payload.get("paper_id"):
            return [
                "这篇论文的作者是谁",
                "相关专利有哪些",
                "找相近论文",
            ]
        if domain == "patent" or structured_payload.get("patent_id"):
            return [
                "该专利属于哪个公司",
                "该专利的发明人是谁",
                "相关论文有哪些",
            ]

    if query_type.startswith("B_"):
        if domain == "company":
            return [
                "上述哪些在深圳",
                "换成同方向论文",
                "换成同方向专利",
            ]
        if domain == "professor":
            return [
                "上述哪些在深圳",
                "看看这些教授的论文",
                "换成同方向企业",
            ]
        if domain == "paper":
            return [
                "上述哪些是近两年的",
                "换成同方向专利",
                "换成同方向企业",
            ]
        if domain == "patent":
            return [
                "上述哪些申请人是企业",
                "换成同方向论文",
                "换成同方向企业",
            ]

    if query_type.startswith("C_"):
        retrieval_evidence = structured_payload.get("retrieval_evidence")
        if isinstance(retrieval_evidence, list) and not retrieval_evidence:
            return []
        target_domain = str(structured_payload.get("target_domain") or "")
        if target_domain == "paper":
            return ["上述哪些是近两年的", "换成相关专利", "回到原实体画像"]
        if target_domain == "patent":
            return ["上述哪些已授权", "换成相关论文", "回到原实体画像"]
        if target_domain == "company":
            return ["这些公司有哪些专利", "换成相关论文", "回到原实体画像"]
        if target_domain == "professor":
            return ["看看他的论文", "他的专利有哪些", "回到原实体画像"]

    if query_type == "D_narrowing":
        return ["继续收窄范围", "换一个方向筛选", "回到上一批结果"]

    if query_type == "E_knowledge_qa":
        return ["找相关企业", "找相关论文", "找相关专利"]

    return []


def _followup_domain(
    query_type: str,
    structured_payload: dict[str, Any],
    citations: list[ChatCitation],
) -> str | None:
    for key in ("classifier_target_domain", "target_domain", "narrowing_domain"):
        value = structured_payload.get(key)
        if value in _TARGET_DOMAINS:
            return str(value)
    for domain in ("professor", "company", "paper", "patent"):
        if domain in query_type:
            return domain
    if citations:
        return citations[0].type
    return None


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
        h_index = structured_payload.get("h_index")
        citation_count = structured_payload.get("citation_count")
        paper_count = structured_payload.get("paper_count")

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
        if h_index is not None:
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="academic_metric",
                summary=f"H-index：{h_index}",
                evidence_id=professor_id,
            )
        if citation_count is not None:
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="academic_metric",
                summary=f"引用数：{citation_count}",
                evidence_id=professor_id,
            )
        if paper_count is not None:
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="academic_metric",
                summary=f"论文数：{paper_count}",
                evidence_id=professor_id,
            )
        # Rich facts for synthesis depth (awards/education/work/positions/summary).
        # Without these the LLM emits shallow answers; the data has them.
        profile_summary_text = structured_payload.get("profile_summary")
        if profile_summary_text:
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="research_overview",
                summary=f"研究概况：{profile_summary_text}",
                evidence_id=professor_id,
            )
        for label, key in (
            ("奖励荣誉", "awards"),
            ("教育经历", "education"),
            ("工作经历", "work_experience"),
            ("学术兼职", "academic_positions"),
        ):
            values = structured_payload.get(key)
            if values:
                marker = _append_evidence_block(
                    blocks=blocks,
                    citation_map=citation_map,
                    marker=marker,
                    kind=key,
                    summary=f"{label}：{'；'.join(str(v) for v in values)[:400]}",
                    evidence_id=professor_id,
                )
        return "\n".join(blocks), citation_map

    if company_id := structured_payload.get("company_id"):
        canonical_name = structured_payload.get("canonical_name")
        if canonical_name:
            marker = _append_evidence_block(
                blocks=blocks, citation_map=citation_map, marker=marker,
                kind="company", summary=f"企业名称：{canonical_name}", evidence_id=company_id,
            )
        for label, key in (
            ("行业", "industry"), ("主营业务", "business"), ("企业简介", "description"),
        ):
            value = structured_payload.get(key)
            if value:
                marker = _append_evidence_block(
                    blocks=blocks, citation_map=citation_map, marker=marker,
                    kind=key, summary=f"{label}：{str(value)[:400]}", evidence_id=company_id,
                )
        for products in (structured_payload.get("products") or [])[:8]:
            marker = _append_evidence_block(
                blocks=blocks, citation_map=citation_map, marker=marker,
                kind="product", summary=f"产品：{str(products)[:200]}", evidence_id=company_id,
            )
        for scenario in (structured_payload.get("application_scenarios") or [])[:6]:
            marker = _append_evidence_block(
                blocks=blocks, citation_map=citation_map, marker=marker,
                kind="application_scenario", summary=f"应用场景：{str(scenario)[:200]}",
                evidence_id=company_id,
            )
        for event in (structured_payload.get("recent_events") or [])[:5]:
            marker = _append_evidence_block(
                blocks=blocks, citation_map=citation_map, marker=marker,
                kind="recent_event", summary=f"近期动态：{str(event)[:200]}", evidence_id=company_id,
            )
        for product in (structured_payload.get("company_products") or [])[:5]:
            marker = _append_evidence_block(
                blocks=blocks, citation_map=citation_map, marker=marker,
                kind="product", summary=f"核心产品：{str(product)[:300]}", evidence_id=company_id,
            )
        for member in (structured_payload.get("company_team") or [])[:5]:
            marker = _append_evidence_block(
                blocks=blocks, citation_map=citation_map, marker=marker,
                kind="team_member", summary=f"团队/创始人：{str(member)[:300]}", evidence_id=company_id,
            )
        for news in (structured_payload.get("company_news") or [])[:3]:
            marker = _append_evidence_block(
                blocks=blocks, citation_map=citation_map, marker=marker,
                kind="news", summary=f"近期新闻/市场评价：{str(news)[:400]}", evidence_id=company_id,
            )
        return "\n".join(blocks), citation_map

    if paper_id := structured_payload.get("paper_id"):
        title = structured_payload.get("title")
        if title:
            marker = _append_evidence_block(
                blocks=blocks, citation_map=citation_map, marker=marker,
                kind="paper", summary=f"论文标题：{title}", evidence_id=paper_id,
            )
        for label, key in (("发表年份", "year"), ("发表期刊/会议", "venue"), ("引用数", "citation_count")):
            value = structured_payload.get(key)
            if value is not None:
                marker = _append_evidence_block(
                    blocks=blocks, citation_map=citation_map, marker=marker,
                    kind=key, summary=f"{label}：{value}", evidence_id=paper_id,
                )
        abstract = structured_payload.get("abstract_clean") or structured_payload.get("summary_zh")
        if abstract:
            marker = _append_evidence_block(
                blocks=blocks, citation_map=citation_map, marker=marker,
                kind="abstract", summary=f"摘要：{str(abstract)[:500]}", evidence_id=paper_id,
            )
        authors = structured_payload.get("authors") or []
        if authors:
            marker = _append_evidence_block(
                blocks=blocks, citation_map=citation_map, marker=marker,
                kind="authors", summary=f"作者：{'，'.join(str(a) for a in authors[:10])[:300]}",
                evidence_id=paper_id,
            )
        return "\n".join(blocks), citation_map

    matched_professors = structured_payload.get("matched_professors") or []
    if matched_professors:
        for prof in matched_professors[:10]:
            topics = prof.get("matched_topics") or []
            topic_text = f"，匹配方向：{'、'.join(topics[:3])}" if topics else ""
            rich_text = ""
            rich = (prof.get("rich_summary") or "").strip()
            if rich:
                rich_text = f"，亮点：{rich}"
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind="professor",
                summary=(
                    f"{prof.get('canonical_name') or '姓名未知'}，"
                    f"{prof.get('institution') or '机构未知'}"
                    f"{topic_text}{rich_text}"
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

    retrieval_evidence = structured_payload.get("retrieval_evidence") or []
    if retrieval_evidence:
        for item in retrieval_evidence[:10]:
            evidence_type = item.get("type") or "evidence"
            if evidence_type == "professor":
                summary = (
                    f"{item.get('title') or item.get('canonical_name') or '姓名未知'}，"
                    f"{item.get('institution') or '机构未知'}"
                )
            elif evidence_type == "paper":
                parts = [item.get("title") or "标题未知"]
                if item.get("year"):
                    parts.append(str(item["year"]))
                if item.get("venue"):
                    parts.append(str(item["venue"]))
                summary = "，".join(parts)
            elif evidence_type == "company":
                company_parts = [
                    item.get("title") or item.get("canonical_name") or "企业未知",
                    item.get("industry") or "行业未知",
                    item.get("snippet")
                    or item.get("business")
                    or item.get("profile_summary")
                    or item.get("technology_route_summary"),
                ]
                if item.get("latest_funding_round"):
                    company_parts.append(f"最新融资轮次：{item['latest_funding_round']}")
                if item.get("latest_funding_time"):
                    company_parts.append(f"最新融资时间：{item['latest_funding_time']}")
                if item.get("latest_funding_amount_raw"):
                    company_parts.append(f"最新融资金额：{item['latest_funding_amount_raw']}")
                summary = "，".join(str(part) for part in company_parts if part)
            elif evidence_type == "patent":
                summary = (
                    f"{item.get('patent_number') or item.get('id') or '编号未知'}，"
                    f"{item.get('title') or item.get('title_clean') or '标题未知'}"
                )
            else:
                summary = item.get("title") or item.get("url") or "网页结果"
            marker = _append_evidence_block(
                blocks=blocks,
                citation_map=citation_map,
                marker=marker,
                kind=str(evidence_type),
                summary=summary,
                evidence_id=str(item.get("id") or ""),
            )
        return "\n".join(blocks), citation_map

    # B-topic list results (company/professor/patent topic search) + web evidence.
    # Builds blocks from matched_professors/matched_objects so synthesis fires for
    # list queries (otherwise these paths fall through to template answers).
    list_rows = (
        structured_payload.get("matched_professors")
        or structured_payload.get("matched_objects")
        or []
    )
    list_limit = structured_payload.get("synthesis_list_limit", 10)
    if not isinstance(list_limit, int) or list_limit < 0:
        list_limit = 10
    for item in list_rows[:list_limit]:
        if not isinstance(item, dict):
            continue
        name = (
            item.get("canonical_name")
            or item.get("title")
            or item.get("name")
            or item.get("id")
            or "对象"
        )
        detail = (
            item.get("snippet")
            or item.get("business")
            or item.get("industry")
            or item.get("institution")
            or ""
        )
        summary = f"{name}：{detail}" if detail else str(name)
        rich = (item.get("rich_summary") or "").strip()
        if rich:
            summary = f"{summary}（亮点：{rich}）"
        marker = _append_evidence_block(
            blocks=blocks,
            citation_map=citation_map,
            marker=marker,
            kind=str(item.get("type") or "evidence"),
            summary=summary[:320],
            evidence_id=str(
                item.get("id")
                or item.get("professor_id")
                or item.get("company_id")
                or name
            ),
        )
    for item in (structured_payload.get("web_evidence") or [])[:10]:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or "网络来源"
        snippet = item.get("snippet") or ""
        marker = _append_evidence_block(
            blocks=blocks,
            citation_map=citation_map,
            marker=marker,
            kind="web",
            summary=f"{title}：{snippet}"[:200],
            evidence_id=str(item.get("id") or item.get("url") or title),
        )
    if blocks:
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
    system_prompt: str = _CHAT_SYNTHESIS_SYSTEM_PROMPT,
) -> str:
    _clear_proxy_env()
    llm_settings = resolve_professor_llm_settings(None)
    api_key = llm_settings.get("local_llm_api_key")
    if not api_key:
        raise ValueError("missing local_llm_api_key for configured LLM")
    client = OpenAI(
        base_url=llm_settings["local_llm_base_url"],
        api_key=api_key,
        timeout=timeout,
    )
    response = client.chat.completions.create(
        model=llm_settings["local_llm_model"],
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"用户问题: {query}\n\n"
                    f"证据（请引用 [N]）:\n{evidence_text}"
                ),
            },
        ],
        extra_body=_chat_synthesis_extra_body(llm_settings["local_llm_model"]),
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


def _evidence_rows_for_response(structured_payload: dict[str, Any]) -> list[dict]:
    """Flatten the evidence-bearing keys of structured_payload into uniform rows.

    Restores snippet-level provenance on the response (the `evidence` field was
    previously declared but never populated). Includes web_evidence rows.
    """
    rows: list[dict] = []
    for key in ("retrieval_evidence", "matched_objects", "matched_professors", "web_evidence"):
        value = structured_payload.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "type": item.get("type") or item.get("source_type") or "",
                    "id": (
                        item.get("id")
                        or item.get("professor_id")
                        or item.get("company_id")
                        or item.get("paper_id")
                        or item.get("patent_id")
                        or ""
                    ),
                    "title": item.get("title") or item.get("canonical_name") or "",
                    "snippet": item.get("snippet") or "",
                    "url": item.get("url"),
                    "score": item.get("score"),
                }
            )
    return rows


def _build_chat_response(
    *,
    conn: Any,
    query: str,
    query_type: str,
    answer_text: str,
    citations: list[ChatCitation],
    structured_payload: dict[str, Any],
    clarification: ClarificationPayload | None = None,
    skip_synthesis: bool = False,
) -> ChatResponse:
    suggested_followups = _suggested_followups(
        query_type=query_type,
        structured_payload=structured_payload,
        citations=citations,
        clarification=clarification,
    )
    evidence_rows = _evidence_rows_for_response(structured_payload)
    base_response = ChatResponse(
        query=query,
        query_type=query_type,
        answer_text=answer_text,
        citations=citations,
        clarification=clarification,
        structured_payload=structured_payload,
        suggested_followups=suggested_followups,
        evidence=evidence_rows,
    )
    if not llm_synthesis_enabled() or skip_synthesis:
        return base_response

    # Enrich professor profiles with rich facts (awards/education/work/positions/
    # summary) so synthesis can generate deep prose, not just basic fields. The data
    # has these (e.g. 11 awards); they were never surfaced to the LLM before.
    prof_id_for_rich = structured_payload.get("professor_id")
    if prof_id_for_rich:
        rich_facts = _prof_rich_profile_facts(conn, str(prof_id_for_rich))
        if rich_facts:
            structured_payload.update(rich_facts)
    company_id_for_rich = structured_payload.get("company_id")
    if company_id_for_rich:
        company_rich = _company_rich_facts(conn, str(company_id_for_rich))
        if company_rich:
            structured_payload.update(company_rich)
    paper_id_for_rich = structured_payload.get("paper_id")
    if paper_id_for_rich:
        paper_rich = _paper_rich_fields(conn, str(paper_id_for_rich))
        if paper_rich:
            structured_payload.update(paper_rich)

    # List-entity enrichment (Fix1): fetch rich facts for the top list entities so
    # the list render surfaces depth (flagship product, top award), not just name.
    _enrich_list_entities(
        structured_payload,
        conn=conn,
        prof_rich_fn=_prof_rich_profile_facts,
        company_rich_fn=_company_rich_facts,
    )

    # Every query goes through web search (per product decision): if the retrieval
    # path did not already web-augment (e.g. profile paths don't call retrieve with
    # augment_with_web), do it here so synthesis sees web evidence too. Best-effort:
    # on failure, fall through to the local-only answer.
    if not structured_payload.get("web_evidence"):
        web_provider = _get_web_search_provider_or_none()
        if web_provider is not None:
            try:
                web_payload = web_provider.search(query)
                organic = web_payload.get("organic") or web_payload.get("results") or []
                web_evidence_rows: list[dict[str, Any]] = []
                for item in organic[:10]:
                    web_evidence_rows.append(
                        {
                            "id": item.get("link") or item.get("url") or f"web-{len(web_evidence_rows)}",
                            "title": (item.get("title") or "").strip(),
                            "snippet": (item.get("snippet") or "").strip(),
                            "url": item.get("link") or item.get("url") or "",
                            "type": "web",
                        }
                    )
                if web_evidence_rows:
                    structured_payload["web_evidence"] = web_evidence_rows
            except Exception as exc:  # noqa: BLE001 - web is best-effort
                logger.warning("Web search augmentation failed for %r: %s", query, exc)

    evidence_text, citation_map = _build_evidence_blocks(structured_payload)
    if not evidence_text:
        return base_response

    # Intent-aware structured synthesis: detect intent → select template → enforce coverage
    n_evidence = len(citation_map)
    intent = _detect_answer_intent(query, query_type, structured_payload)
    if intent == "profile":
        synth_prompt = _CHAT_SYNTHESIS_PROMPT_PROFILE.format(n=n_evidence)
    elif intent == "paper_profile":
        synth_prompt = _CHAT_SYNTHESIS_PROMPT_PAPER.format(n=n_evidence)
    elif intent == "qa":
        synth_prompt = _CHAT_SYNTHESIS_PROMPT_QA.format(n=n_evidence)
    elif intent == "patent":
        synth_prompt = _CHAT_SYNTHESIS_PROMPT_PATENT.format(n=n_evidence)
    else:
        synth_prompt = _CHAT_SYNTHESIS_PROMPT_LIST.format(n=n_evidence)

    try:
        llm_answer = _call_gemma_synthesis(
            query,
            evidence_text,
            timeout=_CHAT_SYNTHESIS_TIMEOUT_SECONDS,
            system_prompt=synth_prompt,
        )
        llm_answer = _validate_and_strip_citations(llm_answer, len(citation_map))
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
        retrieval_evidence = structured_payload.get("retrieval_evidence") or []
        scored_evidence = [
            Evidence(
                object_type=str(item.get("type") or ""),
                object_id=str(item.get("id") or ""),
                score=float(item.get("score") or 0.0),
                snippet=str(item.get("snippet") or ""),
                source_url=item.get("url"),
                metadata={},
            )
            for item in retrieval_evidence
            if item.get("score") is not None
        ]
        llm_answer = _maybe_prefix_low_confidence(llm_answer, scored_evidence)
        return ChatResponse(
            query=query,
            query_type=query_type,
            answer_text=llm_answer,
            citations=citations,
            clarification=clarification,
            structured_payload=structured_payload,
            answer_style="llm_synthesized",
            citation_map=citation_map,
            suggested_followups=suggested_followups,
            evidence=evidence_rows,
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
           AND COALESCE(p.identity_status, 'unverified') != 'rejected'
           AND COALESCE(p.quality_status, 'needs_enrichment') != 'rejected'
         ORDER BY p.year DESC NULLS LAST, p.citation_count DESC NULLS LAST
         LIMIT 20
        """,
        (professor_id,),
    ).fetchall()


def _lookup_paper_related_professors(conn: Any, *, paper_id: str) -> list[dict]:
    return conn.execute(
        """
        SELECT p.professor_id,
               p.canonical_name,
               p.canonical_name_en,
               pa.institution,
               pa.title,
               p.discipline_family,
               p.h_index,
               p.citation_count,
               p.paper_count,
               ppl.topic_consistency_score,
               count(*) OVER ()::int AS total_count
          FROM professor_paper_link ppl
          JOIN professor p ON p.professor_id = ppl.professor_id
          LEFT JOIN LATERAL (
            SELECT pa_inner.institution, pa_inner.title
              FROM professor_affiliation pa_inner
             WHERE pa_inner.professor_id = p.professor_id
               AND pa_inner.is_primary = true
             LIMIT 1
          ) pa ON true
         WHERE ppl.paper_id = %s
           AND ppl.link_status IN ('verified', 'candidate')
           AND p.identity_status = 'resolved'
         ORDER BY
           CASE ppl.link_status WHEN 'verified' THEN 0 ELSE 1 END,
           ppl.topic_consistency_score DESC NULLS LAST,
           p.canonical_name ASC
         LIMIT 20
        """,
        (paper_id,),
    ).fetchall()


def _query_asks_paper_related_professors(query: str) -> bool:
    return bool(re.search(r"(关联|相关)?\s*(教授|老师|学者)\s*(是谁|有哪些)?", query))


def _build_paper_related_professors_response(
    *,
    conn: Any,
    query: str,
    paper_id: str,
    paper_title: str | None = None,
) -> ChatResponse:
    rows = _lookup_paper_related_professors(conn, paper_id=paper_id)
    evidence_rows = [_related_row_to_chat_row("professor", row) for row in rows]
    source = SessionEntity(kind="paper", id=paper_id, label=paper_title or paper_id)
    return _build_chat_response(
        conn=conn,
        query=query,
        query_type="C_cross_domain_related",
        answer_text=_answer_c_related_objects(source, "professor", evidence_rows),
        citations=_chat_citations_from_result_rows(evidence_rows),
        structured_payload={
            "source_domain": "paper",
            "source_id": paper_id,
            "source_label": source.label,
            "target_domain": "professor",
            "paper_id": paper_id,
            "retrieval_evidence": evidence_rows,
            "related_professors": evidence_rows[:10],
            "match_count": len(evidence_rows),
        },
    )


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


def _feedback_domain(body: ChatFeedbackRequest) -> str | None:
    if body.citations:
        return body.citations[0].type
    query_type = body.query_type.lower()
    for domain in ("professor", "company", "paper", "patent"):
        if domain in query_type:
            return domain
    return None


def _chat_feedback_evidence(
    body: ChatFeedbackRequest,
    *,
    session_id: str | None,
) -> dict[str, Any]:
    return {
        "issue_type": "chat_feedback",
        "domain": _feedback_domain(body),
        "session_id": session_id,
        "query": body.query,
        "query_type": body.query_type,
        "answer_text": body.answer_text,
        "answer_style": body.answer_style,
        "citations": [citation.model_dump() for citation in body.citations],
        "citation_map": body.citation_map,
        "structured_payload": body.structured_payload,
        "feedback_type": body.feedback_type,
        "note": body.note,
        "recommended_action": "Review the chat answer, routing, citations, and source evidence.",
    }


def reset_chat_session(response: Response) -> ChatSessionResetResponse:
    session = _get_or_create_session(None)
    response.set_cookie(
        _SESSION_COOKIE,
        session.session_id,
        max_age=_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return ChatSessionResetResponse(session_id=session.session_id)


@router.post("/chat/feedback", response_model=ChatFeedbackResponse)
def create_chat_feedback(
    body: ChatFeedbackRequest,
    miroflow_chat_session: str | None = Cookie(default=None),
    conn: Any = Depends(get_pg_conn),
) -> ChatFeedbackResponse:
    session_id = miroflow_chat_session or "anonymous"
    feedback_type = (body.feedback_type or "incorrect_answer").strip()
    description = (
        f"Chat feedback ({feedback_type}) for {body.query_type}: "
        f"{body.query[:160]}"
    )
    params = {
        "institution": f"chat-feedback:{session_id}",
        "stage": "data_quality_flag",
        "severity": "medium",
        "description": description,
        "evidence_snapshot": Jsonb(
            _chat_feedback_evidence(body, session_id=session_id)
        ),
        "reported_by": _CHAT_FEEDBACK_REPORTED_BY,
    }
    row = conn.execute(
        """
        INSERT INTO pipeline_issue (
            institution,
            stage,
            severity,
            description,
            evidence_snapshot,
            reported_by
        )
        VALUES (
            %(institution)s,
            %(stage)s,
            %(severity)s,
            %(description)s,
            %(evidence_snapshot)s,
            %(reported_by)s
        )
        ON CONFLICT DO NOTHING
        RETURNING issue_id::text AS issue_id, reported_at
        """,
        params,
    ).fetchone()
    if row is None:
        row = conn.execute(
            """
            SELECT issue_id::text AS issue_id, reported_at
              FROM pipeline_issue
             WHERE institution = %(institution)s
               AND stage = %(stage)s
               AND reported_by = %(reported_by)s
               AND description = %(description)s
               AND resolved = false
             ORDER BY reported_at DESC
             LIMIT 1
            """,
            params,
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to file chat feedback")
    return ChatFeedbackResponse(
        issue_id=str(row["issue_id"]),
        status="filed",
        reported_at=row.get("reported_at"),
    )


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
    query = _normalize_query_for_rules(_rewrite_query_with_context(raw_query, session))

    def _record_and_return(chat_resp: ChatResponse) -> ChatResponse:
        """Persist session context derived from this response."""
        if _should_clear_active_context(raw_query, chat_resp.query_type):
            session.clear_active_context()
        sp = chat_resp.structured_payload or {}
        primary_entities = {
            "professor": (
                sp.get("professor_id"),
                sp.get("canonical_name"),
            ),
            "company": (
                sp.get("company_id"),
                sp.get("canonical_name") or sp.get("company_name"),
            ),
            "paper": (
                sp.get("paper_id"),
                sp.get("title") or sp.get("title_clean"),
            ),
            "patent": (
                sp.get("patent_id"),
                sp.get("patent_number") or sp.get("title_clean") or sp.get("title"),
            ),
        }
        for domain, (object_id, label) in primary_entities.items():
            if object_id and label:
                session.push_entity(SessionEntity(
                    kind=domain, id=str(object_id), label=str(label)
                ))
        for domain, ids in result_ids_by_domain(sp, chat_resp.citations).items():
            session.push_result_set(domain, ids)
        session.push_turn(raw_query, chat_resp.query_type, chat_resp.answer_text)
        _SESSION_STORE.persist(session)
        return chat_resp

    def _handle_d_narrowing(topic_hint: str = "") -> ChatResponse | None:
        domain = session.latest_result_domain()
        if domain is None:
            return None
        allowed_ids = session.last_result_set.get(domain) or []
        if not allowed_ids:
            return None
        topic = normalize_narrowing_topic(query, fallback=topic_hint)
        predicate = detect_chip_predicate(query, domain)
        if predicate is not None:
            return _record_and_return(
                _build_chip_narrowing_response(
                    conn=conn,
                    query=raw_query,
                    domain=domain,
                    source_ids=allowed_ids,
                    predicate=predicate,
                )
            )
        if llm_synthesis_enabled():
            open_response = _build_open_predicate_narrowing_response(
                conn=conn,
                query=raw_query,
                domain=domain,
                source_ids=allowed_ids,
            )
            if open_response is not None:
                return _record_and_return(open_response)
        return _record_and_return(
            _build_topic_narrowing_response(
                conn=conn,
                query=raw_query,
                domain=domain,
                source_ids=allowed_ids,
                topic=topic,
                degraded_from_open_predicate=not llm_synthesis_enabled(),
            )
        )

    def _source_member_label(
        retrieval_service: Any,
        source_domain: str,
        source_id: str,
    ) -> str:
        get_object = getattr(retrieval_service, "get_object", None)
        if callable(get_object):
            try:
                row = get_object(domain=source_domain, object_id=source_id)
            except Exception as exc:  # noqa: BLE001 - labels are best-effort
                logger.warning(
                    "Set traversal source label lookup failed: %s:%s: %s",
                    source_domain,
                    source_id,
                    exc,
                )
            else:
                if isinstance(row, dict) and row:
                    return _row_display_label(source_domain, row, source_id)
        return source_id

    def _member_label_by_id(
        retrieval_service: Any | None,
        domain: str,
        object_id: str,
    ) -> str:
        get_object = getattr(retrieval_service, "get_object", None)
        if callable(get_object):
            try:
                row = get_object(domain=domain, object_id=object_id)
            except Exception as exc:  # noqa: BLE001 - labels are best-effort
                logger.warning(
                    "Clarification member label lookup failed: %s:%s: %s",
                    domain,
                    object_id,
                    exc,
                )
            else:
                if isinstance(row, dict) and row:
                    return _row_display_label(domain, row, object_id)

        try:
            if domain == "professor":
                row = _lookup_professor_by_id(conn, professor_id=object_id)
            elif domain == "company":
                row = _lookup_company_by_id(conn, company_id=object_id)
            elif domain == "paper":
                row = _lookup_paper_by_id(conn, paper_id=object_id)
            elif domain == "patent":
                row = _lookup_patent_by_id(conn, patent_id=object_id)
            else:
                row = None
        except Exception as exc:  # noqa: BLE001 - labels are best-effort
            logger.warning(
                "Clarification member by-id label lookup failed: %s:%s: %s",
                domain,
                object_id,
                exc,
            )
            row = None
        if isinstance(row, dict) and row:
            return _row_display_label(domain, row, object_id)
        return object_id

    def _singular_member_listing_clarification() -> ChatResponse | None:
        domain = _singular_pronoun_domain(raw_query, session)
        if domain is None or session.latest_for(domain) is not None:
            return None
        live_ids = [str(item) for item in session.last_result_set.get(domain, []) if item]
        if not live_ids:
            return None

        try:
            retrieval_service = get_retrieval_service()
        except Exception as exc:  # noqa: BLE001 - labels are best-effort
            logger.warning("Clarification retrieval service unavailable: %s", exc)
            retrieval_service = None

        candidate_ids = live_ids[:10]
        labels = [
            _member_label_by_id(retrieval_service, domain, object_id)
            for object_id in candidate_ids
        ]
        selector_label, unit = {
            "professor": ("哪一位", "位"),
            "company": ("哪家公司", "家"),
            "paper": ("哪篇论文", "篇"),
            "patent": ("哪件专利", "件"),
        }.get(domain, ("哪一个", "个"))
        lines = [f"{index}. {label}" for index, label in enumerate(labels, start=1)]
        answer_text = (
            f"您指的是上轮列表中的{selector_label}？请先确认后再追问：\n"
            + "\n".join(lines)
        )
        if len(live_ids) > len(candidate_ids):
            answer_text += f"\n以上列出前 {len(candidate_ids)} {unit}，等共 {len(live_ids)} {unit}。"
        return _record_and_return(ChatResponse(
            query=raw_query,
            query_type="C_cross_domain_clarification",
            answer_text=answer_text,
            citations=[],
            structured_payload={
                "referent_domain": domain,
                "candidate_ids": candidate_ids,
                "candidate_labels": labels,
                "clarification_reason": "singular_pronoun_no_anchor_live_set",
            },
        ))

    def _handle_set_traversal(
        source_domain: str,
        source_ids: list[str],
        target_domain: str,
    ) -> ChatResponse:
        all_source_ids = [str(item) for item in source_ids if item]
        capped_source_ids = all_source_ids[:_SET_TRAVERSAL_SOURCE_CAP]
        truncated_source_count = max(len(all_source_ids) - len(capped_source_ids), 0)
        retrieval_service = get_retrieval_service()
        mapping: list[dict[str, Any]] = []
        for source_id in capped_source_ids:
            member_label = _source_member_label(
                retrieval_service,
                source_domain,
                source_id,
            )
            try:
                rows = retrieval_service.get_related_objects(
                    source_domain=source_domain,
                    source_id=source_id,
                    target_domain=target_domain,
                    limit=5,
                )
            except Exception as exc:  # noqa: BLE001 - per-member failure must not abort
                logger.warning(
                    "Set traversal related lookup failed: %s:%s -> %s: %s",
                    source_domain,
                    source_id,
                    target_domain,
                    exc,
                )
                rows = []
            target_rows = [
                _related_row_to_chat_row(target_domain, row)
                for row in rows
                if row.get(domain_id_key(target_domain)) or row.get("id")
            ]
            mapping.append(
                {
                    "member_id": source_id,
                    "member_label": member_label,
                    "targets": target_rows,
                }
            )

        unique_targets = _dedupe_set_traversal_targets(mapping, target_domain)
        displayed_targets = unique_targets[:_SET_TRAVERSAL_TARGET_CAP]
        citations = _chat_citations_from_result_rows(displayed_targets)
        structured_payload = {
            "source_domain": source_domain,
            "source_ids": capped_source_ids,
            "source_total_count": len(all_source_ids),
            "target_domain": target_domain,
            "member_target_mapping": mapping,
            "retrieval_evidence": displayed_targets,
        }
        if truncated_source_count:
            structured_payload["truncated_source_count"] = truncated_source_count
        return _record_and_return(_build_chat_response(
            conn=conn,
            query=raw_query,
            query_type="C_cross_domain_related",
            answer_text=_render_set_traversal_answer(
                query=query,
                source_domain=source_domain,
                target_domain=target_domain,
                mapping=mapping,
                unique_targets=unique_targets,
                displayed_targets=displayed_targets,
                truncated_source_count=truncated_source_count,
            ),
            citations=citations,
            structured_payload=structured_payload,
            # Set traversal is a deterministic join over verified relation tables;
            # the rendered mapping (coverage statement + back-links + citations) is
            # the complete auditable answer. Synthesis here only adds hallucination
            # risk (verified: it ignored the mapping and web-searched the raw query).
            skip_synthesis=True,
        ))

    def _set_referent_clarification(referent: SetReferent) -> ChatResponse:
        available_domains = [
            domain for domain, ids in session.last_result_set.items() if ids
        ]
        available_labels = [
            _TARGET_DOMAIN_LABELS.get(domain, domain) for domain in available_domains
        ]
        if referent.domain:
            referent_label = _TARGET_DOMAIN_LABELS.get(referent.domain, "结果")
            answer_text = (
                f"当前上下文没有可指代的{referent_label}列表，请先检索"
                f"{referent_label}列表后再追问。"
            )
        else:
            answer_text = "当前上下文没有可指代的结果列表，请先检索列表后再追问。"
        if available_labels:
            answer_text += f" 当前可指代的列表：{'、'.join(available_labels)}。"
        else:
            answer_text += " 当前没有其他可指代的列表。"
        return _record_and_return(ChatResponse(
            query=raw_query,
            query_type="C_cross_domain_clarification",
            answer_text=answer_text,
            citations=[],
            structured_payload={
                "referent_domain": referent.domain,
                "available_result_set_domains": available_domains,
            },
        ))

    def _handle_entity_id_hint() -> ChatResponse | None:
        hint = (payload.entity_id_hint or "").strip()
        if not hint:
            return None
        if hint.startswith("COMP"):
            company = _lookup_company_by_id(conn, company_id=hint)
            if company:
                return _record_and_return(
                    _build_company_profile_response(
                        conn=conn,
                        query=raw_query,
                        company=company,
                    )
                )
        if hint.startswith("PAPER"):
            papers = _lookup_paper(conn, title=hint)
            if _query_asks_paper_related_professors(query):
                paper_title = papers[0].get("title_clean") if papers else None
                return _record_and_return(
                    _build_paper_related_professors_response(
                        conn=conn,
                        query=raw_query,
                        paper_id=hint,
                        paper_title=paper_title,
                    )
                )
            if len(papers) == 1:
                return _record_and_return(
                    _build_paper_profile_response(
                        conn=conn,
                        query=raw_query,
                        paper=papers[0],
                    )
                )
        if hint.startswith("PAT"):
            patents = _lookup_patent(conn, query=hint)
            if len(patents) == 1:
                return _record_and_return(
                    _build_patent_profile_response(
                        conn=conn,
                        query=raw_query,
                        patent=patents[0],
                    )
                )
        prof = _lookup_professor_by_id(conn, professor_id=hint)
        if not prof:
            return None
        topics = _prof_research_topics(conn, prof["professor_id"])
        n_papers = _prof_paper_count(conn, prof["professor_id"])
        return _record_and_return(_build_chat_response(
            conn=conn,
            query=raw_query,
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
                **_professor_metric_payload(prof),
            },
        ))

    if hint_response := _handle_entity_id_hint():
        return hint_response

    if clarification_response := _singular_member_listing_clarification():
        return clarification_response

    if m := _Q_PAPER_RELATED_PROFESSORS_RE.match(query):
        return _record_and_return(
            _build_paper_related_professors_response(
                conn=conn,
                query=raw_query,
                paper_id=m.group("paper_id"),
            )
        )

    set_referent = detect_set_referent(query)
    resolved_set = (
        session.resolve_set_referent(set_referent)
        if set_referent is not None
        else None
    )
    if set_referent is not None and resolved_set is None:
        if set_referent.domain is not None or session.latest_result_domain() is None:
            return _set_referent_clarification(set_referent)
    if resolved_set is not None:
        operation, target_domain = detect_set_operation(query, resolved_set[0])
        if operation == "traverse" and target_domain is not None:
            return _handle_set_traversal(
                resolved_set[0],
                resolved_set[1],
                target_domain,
            )

    if looks_like_narrowing_query(query):
        if narrowed_response := _handle_d_narrowing():
            return narrowed_response

    if m := _Q_PROF_PROFILE_DETAIL_RE.search(query):
        name, institutions = _parse_professor_papers_subject(m.group("subject"))
        if institutions is not None and name:
            profs = _lookup_professor(conn, name=name, institutions=institutions)
            if len(profs) == 1:
                prof = profs[0]
                topics = _prof_research_topics(conn, prof["professor_id"])
                n_papers = _prof_paper_count(conn, prof["professor_id"])
                return _record_and_return(_build_chat_response(
                    conn=conn,
                    query=raw_query,
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
                        **_professor_metric_payload(prof),
                    },
                ))

    # Pattern D' (v2): "<name>的研究方向" — follow-up on a pinned professor
    if m := _Q_PROF_TOPICS_RE.search(query):
        name, institutions = _parse_professor_papers_subject(m.group("name"))
        profs = _lookup_professor(conn, name=name, institutions=institutions)
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
        name, institutions = _parse_professor_papers_subject(m.group("name"))
        profs = _lookup_professor(conn, name=name, institutions=institutions)
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
                            url=_local_paper_detail_url(p["paper_id"]),
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
        if _should_handle_professor_profile_rule(
            inst_fragment=inst_fragment,
            name=name,
            institutions=institutions,
        ):
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
                    clarification=_professor_clarification(name, profs),
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
                        **_professor_metric_payload(prof),
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
            conn, institutions=institutions, topic=topic, limit=20
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
                    **_professor_metric_payload(r),
                }
                for r in rows[:10]
            ]
        return _record_and_return(
            _build_chat_response(
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
        return _record_and_return(
            _build_chat_response(
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
        )

    # Round 11 v3 / v3.1: no rule pattern matched — ask LLM classifier
    classification = _classify_query_with_llm(raw_query)
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

        if ctype == "C":
            target_domain = classification.get("target_domain") or "paper"
            c_response = _build_c_type_response(
                conn=conn,
                query=raw_query,
                session=session,
                target_domain=target_domain,
            )
            if c_response is not None:
                return _record_and_return(c_response)
            fallback_response = _build_c_fallback_a_response(
                conn=conn,
                query=raw_query,
                target_domain=target_domain
                if target_domain in _TARGET_DOMAINS
                else "paper",
            )
            if fallback_response is not None:
                return _record_and_return(fallback_response)

        if ctype == "A" and name:
            target_domain = infer_a_target_domain(raw_query, name, classification)
            if target_domain == "company":
                companies = _lookup_company(conn, name=name)
                if len(companies) == 1:
                    company = companies[0]
                    return _record_and_return(_build_chat_response(
                        conn=conn,
                        query=raw_query,
                        query_type="A_company_profile",
                        answer_text=_answer_company_profile(company),
                        citations=[
                            ChatCitation(
                                type="company",
                                id=company["company_id"],
                                label=company["canonical_name"],
                                url=f"/browse#company/{company['company_id']}",
                            )
                        ],
                        structured_payload=_company_profile_payload(company),
                    ))
            elif target_domain == "paper":
                papers = _lookup_paper(conn, title=name)
                if paper := _select_exact_paper_profile_match(name, papers):
                    return _record_and_return(
                        _build_paper_profile_response(
                            conn=conn,
                            query=raw_query,
                            paper=paper,
                        )
                    )
            elif target_domain == "patent":
                patents = _lookup_patent(conn, query=name)
                if len(patents) == 1:
                    patent = patents[0]
                    return _record_and_return(_build_chat_response(
                        conn=conn,
                        query=raw_query,
                        query_type="A_patent_profile",
                        answer_text=_answer_patent_profile(patent),
                        citations=[
                            ChatCitation(
                                type="patent",
                                id=patent["patent_id"],
                                label=patent.get("patent_number") or patent["patent_id"],
                                url=f"/browse#patent/{patent['patent_id']}",
                            )
                        ],
                        structured_payload={
                            "patent_id": patent["patent_id"],
                            "patent_number": patent.get("patent_number"),
                            "title_clean": patent.get("title_clean"),
                            "applicants_raw": patent.get("applicants_raw"),
                            "patent_type": patent.get("patent_type"),
                        },
                    ))
            else:
                profs = _lookup_professor(conn, name=name, institutions=None)
                if len(profs) == 1:
                    prof = profs[0]
                    topics = _prof_research_topics(conn, prof["professor_id"])
                    n_papers = _prof_paper_count(conn, prof["professor_id"])
                    return _record_and_return(_professor_profile_or_papers_response(
                        conn, raw_query, prof, topics, n_papers,
                    ))

        if ctype == "B" and topic:
            target_domain = (
                classification.get("target_domain")
                or _infer_classifier_target_domain(raw_query)
            )
            if target_domain not in _TARGET_DOMAINS:
                target_domain = "professor"
            rows = _lookup_domain_by_topic(
                conn,
                domain=target_domain,
                topic=topic,
                limit=20,
                raw_query=raw_query,
            )
            rows = _augment_rows_with_web(raw_query, rows)
            if target_domain != "professor":
                id_key = domain_id_key(target_domain)
                local_rows = [r for r in rows if r.get("type") != "web"]
                web_rows = [r for r in rows if r.get("type") == "web"][:5]
                shown_rows = (
                    local_rows
                    if target_domain == "company"
                    else local_rows[:10]
                ) + web_rows
                selected_company_count = (
                    len(local_rows)
                    if target_domain == "company"
                    else 10
                )
                citation_domain = cast(TargetDomain, target_domain)
                return _record_and_return(_build_chat_response(
                    conn=conn,
                    query=raw_query,
                    query_type=f"B_{target_domain}_topic_search",
                    answer_text=_answer_domain_topic_list(target_domain, topic, rows),
                    citations=[
                        ChatCitation(
                            type=citation_domain,
                            id=str(r.get(id_key) or r.get("id") or ""),
                            label=str(
                                r.get("canonical_name")
                                or r.get("title")
                                or r.get("title_clean")
                                or r.get("patent_number")
                                or r.get("id")
                                or ""
                            ),
                            url=str(
                                r.get("url")
                                or f"/browse#{target_domain}/{r.get(id_key) or r.get('id') or ''}"
                            ),
                        )
                        for r in shown_rows
                        if r.get(id_key) or r.get("id")
                    ],
                    structured_payload={
                        "classifier_topic": topic,
                        "classifier_target_domain": target_domain,
                        "classifier_reason": reason,
                        "match_count": rows[0].get("total_count", len(rows)) if rows else 0,
                        "matched_objects": shown_rows,
                        "matched_objects_enrich_limit": selected_company_count,
                        "synthesis_list_limit": selected_company_count,
                    },
                ))
            prof_rows = [r for r in rows if r.get("type") != "web"]
            web_rows = [r for r in rows if r.get("type") == "web"][:5]
            return _record_and_return(_build_chat_response(
                conn=conn,
                query=raw_query,
                query_type="B_semantic_topic_search",
                answer_text=_answer_prof_list(_SZ_INSTITUTIONS_ALL, topic, prof_rows),
                citations=[
                    ChatCitation(
                        type="professor",
                        id=r["professor_id"],
                        label=f"{r['canonical_name']} - {r['institution']}",
                        url=f"/browse#professor/{r['professor_id']}",
                    )
                    for r in prof_rows[:10]
                ],
                structured_payload={
                    "classifier_topic": topic,
                    "classifier_reason": reason,
                    "match_count": prof_rows[0].get("total_count", len(prof_rows)) if prof_rows else 0,
                    "matched_professors": [
                        {
                            "professor_id": r["professor_id"],
                            "canonical_name": r["canonical_name"],
                            "institution": r.get("institution"),
                            "matched_topics": r.get("matched_topics") or [],
                            **_professor_metric_payload(r),
                        }
                        for r in prof_rows[:10]
                    ],
                    "web_evidence": web_rows,
                },
            ))

        if ctype == "D" and topic:
            if looks_like_narrowing_query(query) and (
                narrowed_response := _handle_d_narrowing(topic)
            ):
                return narrowed_response
            # 跨域聚合: 教授 + 企业（专利留下一轮，目前 patent 表空）
            evidence = _lookup_cross_domain_evidence(
                conn, topic=topic, raw_query=raw_query
            )
            profs = [row for row in evidence if row.get("type") == "professor"]
            papers = [row for row in evidence if row.get("type") == "paper"]
            companies = [row for row in evidence if row.get("type") == "company"]
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
            for r in papers[:5]:
                citations.append(ChatCitation(
                    type="paper",
                    id=r["paper_id"],
                    label=f"{r.get('year') or '?'} · {r.get('title') or r['paper_id']}",
                    url=_local_paper_detail_url(r["paper_id"]),
                ))
            return _record_and_return(_build_chat_response(
                query=raw_query,
                conn=conn,
                query_type="D_cross_domain_topic",
                answer_text=_answer_cross_domain(topic, profs, companies, papers),
                citations=citations,
                structured_payload={
                    "topic": topic,
                    "classifier_reason": reason,
                    "prof_count": profs[0].get("total_count", len(profs)) if profs else 0,
                    "paper_count": papers[0].get("total_count", len(papers)) if papers else 0,
                    "company_count": companies[0].get("total_count", len(companies)) if companies else 0,
                    "retrieval_evidence": evidence,
                },
            ))

        if ctype == "E":
            answer, err, evidence = _answer_knowledge_qa_with_web_search(raw_query)
            return _record_and_return(ChatResponse(
                query=raw_query,
                query_type="E_knowledge_qa",
                answer_text=answer,
                citations=[],
                evidence=evidence,
                structured_payload={
                    "classifier_reason": reason,
                    "llm_error": err,
                    "retrieval_evidence": evidence,
                },
            ))

        if ctype == "G" and name:
            target_domain = classification.get("target_domain")
            # Clean the name: strip common prefixes/suffixes the classifier may leave in
            clean_name = re.sub(r"^(请介绍|介绍|请|查一下|查找|查询)\s*", "", name)
            clean_name = re.sub(r"(的相关信息|的相关信息是什么|的信息|的基本信息|的详细信息|怎么样|如何)$", "", clean_name)
            clean_name = clean_name.strip(" ：，。")
            if target_domain == "company":
                companies = _lookup_company(conn, name=clean_name or name)
                if len(companies) == 0:
                    return _record_and_return(ChatResponse(
                        query=raw_query,
                        query_type="G_ambiguous_not_found",
                        answer_text=f"没有找到与 {name!r} 匹配的企业。",
                        citations=[],
                        structured_payload={
                            "name": name,
                            "target_domain": "company",
                            "classifier_reason": reason,
                        },
                    ))
                if len(companies) == 1:
                    return _record_and_return(
                        _build_company_profile_response(
                            conn=conn,
                            query=raw_query,
                            company=companies[0],
                        )
                    )
                return _record_and_return(ChatResponse(
                    query=raw_query,
                    query_type="G_ambiguous_clarification",
                    answer_text=_answer_ambiguous_companies(name, companies),
                    citations=[
                        ChatCitation(
                            type="company",
                            id=company["company_id"],
                            label=company["canonical_name"],
                            url=f"/browse#company/{company['company_id']}",
                        )
                        for company in companies[:10]
                    ],
                    clarification=_company_clarification(name, companies),
                    structured_payload={
                        "name": name,
                        "target_domain": "company",
                        "candidate_count": len(companies),
                        "classifier_reason": reason,
                        "companies": [
                            {
                                "company_id": company["company_id"],
                                "canonical_name": company["canonical_name"],
                                "industry": company.get("industry"),
                                "business": company.get("business"),
                            }
                            for company in companies[:10]
                        ],
                    },
                ))
            if target_domain == "paper":
                papers = _lookup_paper(conn, title=name)
                if len(papers) == 0:
                    return _record_and_return(ChatResponse(
                        query=raw_query,
                        query_type="G_ambiguous_not_found",
                        answer_text=f"没有找到与 {name!r} 匹配的论文。",
                        citations=[],
                        structured_payload={
                            "name": name,
                            "target_domain": "paper",
                            "classifier_reason": reason,
                        },
                    ))
                if len(papers) == 1:
                    return _record_and_return(
                        _build_paper_profile_response(
                            conn=conn,
                            query=raw_query,
                            paper=papers[0],
                        )
                    )
                return _record_and_return(ChatResponse(
                    query=raw_query,
                    query_type="G_ambiguous_clarification",
                    answer_text=_answer_ambiguous_papers(name, papers),
                    citations=[
                        ChatCitation(
                            type="paper",
                            id=paper["paper_id"],
                            label=paper.get("title_clean") or paper["paper_id"],
                            url=_local_paper_detail_url(paper["paper_id"]),
                        )
                        for paper in papers[:10]
                    ],
                    clarification=_paper_clarification(name, papers),
                    structured_payload={
                        "name": name,
                        "target_domain": "paper",
                        "candidate_count": len(papers),
                        "classifier_reason": reason,
                        "papers": [
                            {
                                "paper_id": paper["paper_id"],
                                "title": paper.get("title_clean"),
                                "year": paper.get("year"),
                                "venue": paper.get("venue"),
                                "citation_count": paper.get("citation_count"),
                            }
                            for paper in papers[:10]
                        ],
                    },
                ))
            if target_domain == "patent":
                patents = _lookup_patent(conn, query=name)
                if len(patents) == 0:
                    return _record_and_return(ChatResponse(
                        query=raw_query,
                        query_type="G_ambiguous_not_found",
                        answer_text=f"没有找到与 {name!r} 匹配的专利。",
                        citations=[],
                        structured_payload={
                            "name": name,
                            "target_domain": "patent",
                            "classifier_reason": reason,
                        },
                    ))
                if len(patents) == 1:
                    return _record_and_return(
                        _build_patent_profile_response(
                            conn=conn,
                            query=raw_query,
                            patent=patents[0],
                        )
                    )
                return _record_and_return(ChatResponse(
                    query=raw_query,
                    query_type="G_ambiguous_clarification",
                    answer_text=_answer_ambiguous_patents(name, patents),
                    citations=[
                        ChatCitation(
                            type="patent",
                            id=patent["patent_id"],
                            label=patent.get("patent_number") or patent["patent_id"],
                            url=f"/browse#patent/{patent['patent_id']}",
                        )
                        for patent in patents[:10]
                    ],
                    clarification=_patent_clarification(name, patents),
                    structured_payload={
                        "name": name,
                        "target_domain": "patent",
                        "candidate_count": len(patents),
                        "classifier_reason": reason,
                        "patents": [
                            {
                                "patent_id": patent["patent_id"],
                                "patent_number": patent.get("patent_number"),
                                "title_clean": patent.get("title_clean"),
                                "applicants_raw": patent.get("applicants_raw"),
                                "patent_type": patent.get("patent_type"),
                            }
                            for patent in patents[:10]
                        ],
                    },
                ))
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
                        **_professor_metric_payload(prof),
                    },
                ))
            return _record_and_return(ChatResponse(
                query=raw_query,
                query_type="G_ambiguous_clarification",
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
                clarification=_professor_clarification(name, profs),
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
            "我还没判断清楚要查哪类科创信息。请补充要查询的主体、方向或范围，"
            "例如：介绍某位教授、查某家企业、找某方向的论文/专利，"
            "或问“深圳做具身智能的教授和企业有哪些”。当前支持教授、企业、论文、专利四类数据。"
        ),
        citations=[],
    )


# Keep the comparison/feedback callables importable while V2 owns chat/reset.
_legacy_comparison_router = router
router = APIRouter()
router.include_router(_legacy_comparison_router)
router.include_router(canonical_v2_chat_router)
