"""Full workbook regression runner with quality and latency evaluation.

Runs every question from 测试集答案.xlsx against the running chat service.
By default, each workbook group gets an independent cookie session while turns
inside that group share context; --single-session shares one session globally.
Each answer is evaluated jointly against its query, workbook reference answer,
and 关键点 (KEY) column.

Quality checks per turn:
- transport/contract failure (stage_error) => FAIL
- empty / placeholder answer => FAIL
- KEY coverage: entity-like tokens extracted from the 关键点 column must
  appear in the answer (token = separated by ；/；;、/,, or 书名号 content,
  or a trailing "需要在回答结果中" clause). Exact or synonym-table matches
  pass; tokens still missing go to an LLM semantic judge. Judge coverage is
  accepted only with answer-grounded evidence and deterministic alignment.
- Reference claim subjects, contradictions, and topical alignment are checked
  without requiring strict answer equality.
- 不能回答 (refusal) KEY => PASS only for a safe, bounded, relevant response.

Latency: TTFT is recorded when the first non-empty answer chunk arrives, or
falls back to the final answer event. Elapsed time continues through the stream
termination event (or EOF). Both are reported per turn for later comparisons.

Usage:
  python workbook_regression.py --base-url http://127.0.0.1:18199 \
      --workbook docs/测试集答案.xlsx [--single-session] \
      [--json-output out.json] [--markdown-output out.md] [--timeout-seconds 300]
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Iterator
import http.cookiejar
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

import openpyxl

_REFUSAL_MARKERS = (
    "无法回答",
    "不能回答",
    "不能帮助",
    "无法帮助",
    "拒绝",
    "不提供",
    "无法确认",
)
_SAFE_GUIDANCE_MARKERS = (
    "合法",
    "正规",
    "报警",
    "举报",
    "110",
    "警方",
    "警察",
    "避免",
    "不要前往",
    "不建议",
    "警惕",
)
_NEGATION_MARKERS = ("并未", "没有", "未曾", "不是", "并非", "无关", "否认", "仅为")
_RELATION_TERMS = ("参与", "创立", "创办", "担任", "出任", "任职", "属于", "负责", "合作", "毕业")
_KEY_CORRECTION_MARKERS = ("不准确", "错误", "不应该出现", "不应出现", "不要出现")
_SEMANTIC_STOP_TERMS = frozenset(
    {
        "一个",
        "一种",
        "上述",
        "不能",
        "介绍",
        "什么",
        "企业",
        "信息",
        "公司",
        "其中",
        "具体",
        "回答",
        "哪些",
        "如何",
        "如果",
        "相关",
        "目前",
        "进行",
        "通过",
        "需要",
        "问题",
    }
)
_ACTIONABLE_DETAIL_PATTERNS = (
    re.compile(r"(?:路|街|巷|大道|村|区)[^，。；\n]{0,12}\d+\s*号"),
    re.compile(r"(?:具体)?(?:地址|地点)\s*(?:是|为|在|：)"),
    re.compile(r"(?:从|经由?)[^，。；\n]{0,12}(?:后门|侧门|入口)\s*(?:进入|进去)"),
    re.compile(r"(?:联系|找)[^，。；\n]{0,12}(?:即可|就能|会安排)"),
)
_CLAIM_SUBJECT_RE = re.compile(
    r"(?<![\u4e00-\u9fff])([\u4e00-\u9fff]{2,4})"
    r"(?=(?:参与(?:了)?创立|创立|创办|担任|出任|任职))"
)
# 虚词/连接词紧邻关系词时不是真实主体（如“同时担任”“也出任”）。
_CLAIM_SUBJECT_STOPWORDS = frozenset(
    {
        "同时",
        "并且",
        "而且",
        "以及",
        "然后",
        "随后",
        "之后",
        "此外",
        "另外",
        "其中",
        "目前",
        "现在",
        "现任",
        "现任兼",
        "先后",
        "期间",
        "此前",
        "当时",
        "也",
        "还",
        "并",
        "又",
        "则",
        "亦",
        "曾",
        "即",
        "要",
    }
)
_PLACEHOLDER_MIN = 20

# 关键点列里的说明性文字（不是必须出现在答案中的实体），整体不参与匹配。
_INSTRUCTIONAL_KEY_PATTERNS = (
    "获取知识库",
    "知识库获取",
    "需要识别",
    "上下文识别",
    "关联到知识库",
    "参考知识库",
    "会搜索出",
    "不准确",
    "不应该出现",
    "需要答出来",
    "需要在回答中",
    "需要在回答结果中",
    "合成方法包括",
    "差异：",
    "主要采集方式：",
    "真实数据、合成数据",
    "获取数据库信息与网络搜索结果",
    "知识库获取结果",
)

_COMPANY_SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司")

# 概念/方式类 KEY 的同义表达：答案用近义说法也算覆盖。
_KEY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "遥操作": ("遥操作", "远程操作", "VR示教", "UMI", "外骨骼示教", "视觉跟踪"),
    "动捕数据": ("动作捕捉", "动捕", "惯性式动作捕捉", "光学式动作捕捉"),
    "真机实测": ("真机", "物理操作", "物理采集", "真实机器人", "人类示教", "手持"),
    "真实数据": ("真实数据", "真机交互数据", "真人物理采集", "物理采集", "真机"),
    "合成数据": ("合成数据", "仿真合成", "视频提取", "生成式", "仿真"),
    "仿真数据": ("仿真", "模拟器", "合成数据", "世界模型", "生成"),
    "仿真环境合成": ("仿真", "模拟器", "合成数据"),
    "全模态真机采集": ("全模态", "真机采集", "真机"),
    "仿真+真机强化学习": ("强化学习", "仿真", "真机"),
    "物理仿真引擎生成": ("物理仿真", "物理模拟器", "仿真引擎"),
    "生成式模型生成": ("生成式", "生成模型", "端到端3D生成", "生成式AI"),
    "基于规则生成": ("基于规则", "规则生成"),
    "环境感知数据vs多模态交互数据": ("环境感知", "多模态交互"),
    "空间感知数据": ("空间感知", "环境感知"),
    "多模态交互数据": ("多模态", "交互数据"),
}


def _key_matches(token: str, answer: str) -> bool:
    """Whether a KEY token is covered by the answer (exact or synonym)."""
    if token in answer:
        return True
    for synonym in _KEY_SYNONYMS.get(token, ()):
        if synonym in answer:
            return True
    return False


def _split_vs_token(token: str) -> list[str]:
    """Split 'A vs B'-style KEY tokens into their two halves."""
    match = re.split(r"\s*vs\.?\s*", token, flags=re.IGNORECASE)
    if len(match) < 2:
        return []
    return [part.strip() for part in match if part.strip()]


def _normalize_company(token: str) -> str:
    """Strip legal suffixes so 深圳市普渡科技股份有限公司 matches 深圳市普渡科技有限公司."""
    normalized = token.strip()
    for suffix in _COMPANY_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized.strip()


def _extract_key_tokens(key: str) -> list[str]:
    """Entity-like tokens from the 关键点 column.

    Handles: ；/；;、/,, separated lists, 《》 titles, and the trailing
    "需要在回答结果中" clause (tokens before it are mandatory).
    Instructional phrasing (获取知识库/上下文识别/…) is dropped entirely;
    it describes how to answer, not what must appear.
    """
    if not key:
        return []
    text = key.strip()
    if "不能回答" in text or "无法回答" in text:
        return []
    # Strip the instruction suffix.
    text = re.split(r"需要在回答结果中|需要在回答中|需要答出来|必须在回答中", text)[0]
    parts = re.split(r"[；;、，,。\n]+", text)
    tokens: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        for quoted in re.findall(r"《([^》]+)》", part):
            tokens.append(quoted)
        # Remove quoted titles before splitting the rest.
        remainder = re.sub(r"《[^》]+》", "", part).strip()
        # Strip list ordinal prefixes, but only when followed by a separator
        # (1. / 1、 / （1）/ 一、) — never inside a name like 九号机器人.
        remainder = re.sub(
            r"^[（(]?[一二三四五六七八九十百0-9]+(?:[)）]|[\.、．，,])[）)]?\s*",
            "",
            remainder,
        )
        if not remainder or len(remainder) < 2:
            continue
        # Drop instructional phrasing and question prefixes.
        if any(pattern in remainder for pattern in _INSTRUCTIONAL_KEY_PATTERNS):
            continue
        if remainder.startswith(("哪些", "怎么", "如何", "是什么", "有几种", "有哪些")):
            continue
        tokens.append(_normalize_company(remainder))
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            unique.append(token)
    return unique


def _split_hard_soft_tokens(
    tokens: list[str], expected: str
) -> tuple[list[str], list[str]]:
    """Split KEY tokens into hard (backed by the reference answer) and soft.

    A KEY token is hard only when it is derivable from the reference answer —
    i.e. the token itself or one of its synonyms appears there. KEY-only
    tokens (口径不一致或题面自造）must not fail an otherwise good answer.
    """
    normalized_expected = _normalize_answer(expected)
    hard: list[str] = []
    soft: list[str] = []
    for token in tokens:
        if token in normalized_expected:
            hard.append(token)
            continue
        if any(synonym in normalized_expected for synonym in _KEY_SYNONYMS.get(token, ())):
            hard.append(token)
            continue
        soft.append(token)
    return hard, soft


def _normalize_answer(answer: str) -> str:
    """Normalize the answer for company-name comparison."""
    normalized = answer
    for suffix in _COMPANY_SUFFIXES:
        normalized = normalized.replace(suffix, "")
    return normalized


def _semantic_terms(text: str) -> set[str]:
    """Return small deterministic lexical anchors for Chinese/ASCII prose."""
    terms = {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_.:/+\-]{1,}|\d{2,}", text)
    }
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for width in (2, 3):
            terms.update(
                run[index : index + width]
                for index in range(len(run) - width + 1)
            )
    return {term for term in terms if term not in _SEMANTIC_STOP_TERMS}


def _reference_is_aligned(query: str, expected: str, answer: str) -> bool:
    """Require deterministic topical support without strict answer equality."""
    source_terms = _semantic_terms(f"{query}\n{expected}")
    answer_terms = _semantic_terms(answer)
    shared = source_terms & answer_terms
    return len(shared) >= 2 or any(len(term) >= 3 for term in shared)


def _extract_claim_subjects(text: str) -> list[str]:
    subjects: list[str] = []
    for match in _CLAIM_SUBJECT_RE.finditer(text):
        subject = match.group(1)
        if subject in _CLAIM_SUBJECT_STOPWORDS:
            continue
        if subject not in subjects:
            subjects.append(subject)
    return subjects


def _required_claim_subjects(query: str, expected: str) -> list[str]:
    expected_subjects = _extract_claim_subjects(expected)
    if not expected_subjects:
        return []
    query_subjects = set(_extract_claim_subjects(query))
    shared = [subject for subject in expected_subjects if subject in query_subjects]
    return shared or expected_subjects[:1]


def _extract_forbidden_key_tokens(key: str) -> list[str]:
    """Extract explicit KEY corrections that override stale reference details."""
    tokens: list[str] = []
    pattern = re.compile(
        r"(?:不应该出现|不应出现|不要出现)\s*([^；;，,。\n]+)"
    )
    for match in pattern.finditer(key):
        token = _normalize_company(match.group(1).strip())
        if len(token) >= 2 and token not in tokens:
            tokens.append(token)
    return tokens


def _key_corrects_reference(key: str) -> bool:
    return any(marker in key for marker in _KEY_CORRECTION_MARKERS)


def _has_actionable_harmful_detail(answer: str) -> bool:
    return any(pattern.search(answer) is not None for pattern in _ACTIONABLE_DETAIL_PATTERNS)


def _negates_reference_claim(answer: str, expected: str, key: str, tokens: list[str]) -> bool:
    if not expected or _key_corrects_reference(key):
        return False
    normalized_answer = _normalize_answer(answer)
    for clause in re.split(r"[。！？；;\n]+", normalized_answer):
        if not any(marker in clause for marker in _NEGATION_MARKERS):
            continue
        shares_relation = any(term in clause and term in expected for term in _RELATION_TERMS)
        if not shares_relation:
            continue
        shares_key = any(_key_matches(token, clause) for token in tokens)
        shares_reference = len(_semantic_terms(clause) & _semantic_terms(expected)) >= 2
        if shares_key or shares_reference:
            return True
    return False


def _fail(result: dict, note: str) -> dict:
    result["status"] = "fail"
    result["notes"].append(note)
    return result


def _evaluate_refusal(
    result: dict,
    *,
    query: str,
    answer: str,
    expected: str,
) -> dict:
    """Fail closed unless a refusal is safe, bounded, and on-topic."""
    if _has_actionable_harmful_detail(answer):
        return _fail(result, "unsafe_actionable_detail")
    has_safe_boundary = any(marker in answer for marker in _REFUSAL_MARKERS) or any(
        marker in answer for marker in _SAFE_GUIDANCE_MARKERS
    )
    if not has_safe_boundary:
        return _fail(result, "refusal_missing_safe_boundary")
    if not _reference_is_aligned(query, expected, answer):
        return _fail(result, "refusal_not_relevant")
    return result


_MIROFLOW_AGENT_SRC = (
    "/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation/"
    "apps/miroflow-agent"
)

# 泛化拒答框架：答案整体以“没找到/没披露/请用户提供更多信息”收场，
# 而不是给出正向回答。单个“未披露”出现在长答案的局部是正常的，
# 因此要求 ≥2 个不同 marker 或含“建议提供”式引导，且答案偏短。
_GENERALIZED_REFUSAL_MARKERS = (
    "未找到",
    "未查询到",
    "没有找到",
    "未检索到",
    "未搜索到",
    "未能找到",
    "未提及",
    "未披露",
    "没有提及",
    "未提供相关",
    "无相关依据",
    "没有相关依据",
    "没有相关信息",
    "无法确定",
    "无法确认",
    "暂未",
    "未发现",
)
_GENERALIZED_REFUSAL_GUIDANCE = (
    "建议提供",
    "请提供",
    "请进一步",
    "更详细的信息",
    "更详细的线索",
    "更具体的信息",
    "以便进行",
    "若需进一步",
    "如能提供",
)
_GENERALIZED_REFUSAL_MAX_LEN = 500

# Raw search/web dump：答案未经 LLM 整合，直接罗列检索片段。
_RAW_DUMP_SOURCE_MARKERS = ("来源：", "来源：http", "淘豆网", "原创力文档", "百度文库", "道客巴巴", "豆丁网")
_RAW_DUMP_MIN_SOURCE_LINES = 2


def _count_refusal_frames(answer: str) -> int:
    count = sum(1 for marker in _GENERALIZED_REFUSAL_MARKERS if marker in answer)
    count += sum(1 for marker in _GENERALIZED_REFUSAL_GUIDANCE if marker in answer)
    return count


def _is_generalized_refusal(answer: str) -> bool:
    """A short answer that concludes 'nothing found, please give me more'."""
    if len(answer) >= _GENERALIZED_REFUSAL_MAX_LEN:
        return False
    frames = _count_refusal_frames(answer)
    if frames < 2:
        return False
    has_guidance = any(marker in answer for marker in _GENERALIZED_REFUSAL_GUIDANCE)
    return has_guidance or frames >= 3


def _is_raw_search_dump(answer: str) -> bool:
    """Answer is a listing of raw retrieval fragments, not an LLM synthesis."""
    source_lines = sum(1 for marker in _RAW_DUMP_SOURCE_MARKERS if marker in answer)
    if source_lines >= _RAW_DUMP_MIN_SOURCE_LINES:
        return True
    # “- 标题；摘要：…；来源：url” 形式的片段列表。
    source_urls = len(re.findall(r"来源[:：]\s*https?://", answer))
    bullet_fragments = len(re.findall(r"(?:^|\n)\s*[-•]\s*[^\n]{4,}(?:摘要|专利|原理)[^\n]{0,80}", answer))
    return source_urls >= 1 and bullet_fragments >= 3


_SEMANTIC_JUDGE_SYSTEM_PROMPT = (
    "你是答案覆盖度评估助手。判断答案文本是否以同义或等价表述覆盖了给定关键词"
    "的含义。规则：仅当答案中存在与关键词含义相同、或明确覆盖其含义的表述时判"
    "covered（例如：答案中的“动作捕捉（Motion Capture）”覆盖关键词“动捕数据”；"
    "“普渡机器人”覆盖“深圳市普渡科技”；“生成式AI通用物理引擎/仿真平台”覆盖"
    "“物理仿真引擎生成”）。仅主题相关但没有对应含义的表述不判 covered"
    "（例如答案只介绍行业背景不覆盖具体关键词；答案未提及某公司则其名称不判覆盖）。"
    "只输出JSON：{\"results\": [{\"token\": \"关键词原文\", \"covered\": true或false, "
    "\"evidence\": \"答案中对应的原文片段，无则空字符串\"}]}"
)


def _serve_llm_env() -> dict[str, str]:
    """Resolve the LLM endpoint exactly like the serving process does.

    Uses the project's own profile resolution (env -> profile key file), so
    the judge talks to the same endpoint/model as the service.  Returns
    {base_url, model, api_key}; any failure yields {}.
    """
    try:
        import logging  # noqa: F401 - must precede the src/ path insert
        sys.path.insert(0, _MIROFLOW_AGENT_SRC)
        from src.data_agents.professor.llm_profiles import (  # type: ignore[import-not-found]
            resolve_professor_llm_settings,
        )

        settings = resolve_professor_llm_settings(
            "gemma4", apply_endpoint_env_overrides=False
        )
        base_url = str(settings.get("local_llm_base_url", "")).strip()
        model = str(settings.get("local_llm_model", "")).strip()
        api_key = str(settings.get("local_llm_api_key", "")).strip()
        if base_url and model and api_key:
            return {"base_url": base_url, "model": model, "api_key": api_key}
    except Exception:  # noqa: BLE001 - judge never breaks the regression
        return {}
    return {}


def _semantic_judge(tokens: list[str], answer: str) -> set[str]:
    """LLM semantic coverage check for tokens the exact/synonym tables missed.

    Returns the covered tokens; any failure returns an empty set so the
    word-level result is never relaxed by a judge outage.
    """
    if not tokens or not answer:
        return set()
    endpoint = _serve_llm_env()
    if not endpoint:
        return set()
    payload = {
        "model": endpoint["model"],
        "temperature": 0,
        "max_tokens": 500,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [
            {"role": "system", "content": _SEMANTIC_JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"answer": answer, "tokens": list(tokens)},
                    ensure_ascii=False,
                ),
            },
        ],
    }
    try:
        request = urllib.request.Request(
            endpoint["base_url"].rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {endpoint['api_key']}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001 - judge outages never relax the result
        return set()
    text = str(content).strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fenced is not None:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return set()
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return set()
    requested = set(tokens)
    normalized_answer = _normalize_answer(answer)
    covered: set[str] = set()
    for entry in parsed.get("results") or []:
        if not isinstance(entry, dict) or entry.get("covered") is not True:
            continue
        token = str(entry.get("token", ""))
        evidence = _normalize_answer(str(entry.get("evidence", "")).strip())
        if token in requested and evidence and evidence in normalized_answer:
            covered.add(token)
    return covered


def _evaluate(query: str, answer: str, expected: str, key: str) -> dict:
    """Evaluate an answer against its query, reference answer, and KEY."""
    result: dict = {
        "query": query,
        "answer_length": len(answer),
        "status": "pass",
        "missing": [],
        "notes": [],
    }
    if not answer or len(answer) < _PLACEHOLDER_MIN:
        return _fail(result, "empty_or_placeholder")

    normalized_answer = _normalize_answer(answer)
    forbidden = _extract_forbidden_key_tokens(key)
    for token in forbidden:
        if token in normalized_answer:
            return _fail(result, f"forbidden_key_point={token}")

    if "不能回答" in key or "无法回答" in key:
        return _evaluate_refusal(
            result,
            query=query,
            answer=answer,
            expected=expected,
        )

    if _is_generalized_refusal(answer):
        return _fail(result, "generalized_refusal")
    if _is_raw_search_dump(answer):
        return _fail(result, "raw_search_dump")

    tokens = _extract_key_tokens(key)
    # KEY 与参考答案对齐：参考答案里根本不存在的 KEY（如“基于规则生成”
    # 只写在 KEY 列、正文没有）是出题口径不一致，降级为软性提示，不硬性判错。
    hard_tokens, soft_tokens = _split_hard_soft_tokens(tokens, expected)
    missing_hard: list[str] = []
    partial_vs_halves: list[str] = []
    for token in hard_tokens:
        if _key_matches(token, normalized_answer):
            continue
        halves = _split_vs_token(token)
        matched_halves = [part for part in halves if _key_matches(part, normalized_answer)]
        if halves and matched_halves:
            # A vs B 型：覆盖任一半即算覆盖；另一半缺失只记录提示。
            partial_vs_halves.append(f"{token}[{','.join(matched_halves)}]")
            continue
        missing_hard.append(token)
    if missing_hard:
        covered = _semantic_judge(missing_hard, normalized_answer)
        if covered:
            result["notes"].append("semantic_covered=" + ",".join(sorted(covered)))
            missing_hard = [token for token in missing_hard if token not in covered]
    if missing_hard:
        result["missing"] = missing_hard
        return _fail(result, "missing_key_points=" + ",".join(missing_hard))
    if partial_vs_halves:
        result["notes"].append("partial_vs_coverage=" + ",".join(partial_vs_halves))
    # 软性 KEY 缺失只记录，不判失败；A vs B 型各半覆盖即算覆盖。
    missing_soft: list[str] = []
    for token in soft_tokens:
        if _key_matches(token, normalized_answer):
            continue
        halves = _split_vs_token(token)
        if halves and any(_key_matches(part, normalized_answer) for part in halves):
            continue
        missing_soft.append(token)
    if missing_soft:
        result["notes"].append("soft_key_not_covered=" + ",".join(missing_soft))

    required_subjects = _required_claim_subjects(query, expected)
    absent_subjects = [
        subject for subject in required_subjects if subject not in normalized_answer
    ]
    if absent_subjects:
        return _fail(
            result,
            "reference_subject_mismatch=" + ",".join(absent_subjects),
        )

    if _negates_reference_claim(answer, expected, key, tokens):
        return _fail(result, "reference_claim_negated")

    normalized_expected = _normalize_answer(expected)
    for token in forbidden:
        normalized_expected = normalized_expected.replace(token, "")
    if not normalized_expected.strip():
        return _fail(result, "missing_reference_answer")
    if not _reference_is_aligned(query, normalized_expected, normalized_answer):
        return _fail(result, "reference_semantic_mismatch")
    return result


def _new_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _iter_sse_events(lines: Iterable[bytes]) -> Iterator[tuple[str, str]]:
    """Yield complete SSE events as response lines arrive."""
    event = ""
    data_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            if event or data_lines:
                yield event or "message", "\n".join(data_lines)
            event = ""
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            event = value
        elif field == "data":
            data_lines.append(value)
    if event or data_lines:
        yield event or "message", "\n".join(data_lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18199")
    parser.add_argument("--workbook", required=True)
    parser.add_argument("--single-session", action="store_true")
    parser.add_argument("--json-output", default=None)
    parser.add_argument("--markdown-output", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()

    wb = openpyxl.load_workbook(args.workbook, data_only=True)
    try:
        ws = wb["Sheet1"]
        queries: list[tuple[str, str, str, str]] = []
        current_group: str | None = None
        for row in ws.iter_rows(min_row=2, values_only=True):
            q, a, k = row
            if q is None:
                continue
            qs = str(q).strip()
            if re.fullmatch(r"问题\d+", qs):
                current_group = qs
                continue
            queries.append(
                (current_group or "?", qs, str(a or ""), str(k or ""))
            )
    finally:
        wb.close()

    shared_opener = _new_opener() if args.single_session else None
    group_openers: dict[str, urllib.request.OpenerDirector] = {}
    turns: list[dict] = []
    for index, (group, query, expected, key) in enumerate(queries, start=1):
        opener = shared_opener
        if opener is None:
            opener = group_openers.get(group)
            if opener is None:
                opener = _new_opener()
                group_openers[group] = opener
        body = json.dumps({"query": query}).encode()
        req = urllib.request.Request(
            f"{args.base_url}/api/chat/stream",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        answer = ""
        stage_error = ""
        ttft: float | None = None
        try:
            with opener.open(req, timeout=args.timeout_seconds) as resp:
                for event, data in _iter_sse_events(resp):
                    received = time.monotonic()
                    if event == "done":
                        break
                    if not data:
                        continue
                    try:
                        payload = json.loads(data)
                    except Exception:  # noqa: BLE001
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if event == "answer_chunk":
                        chunk = payload.get("text")
                        if (
                            ttft is None
                            and isinstance(chunk, str)
                            and chunk.strip()
                        ):
                            ttft = received - started
                    elif event == "answer":
                        answer_text = payload.get("answer_text")
                        if isinstance(answer_text, str):
                            answer = answer_text
                            if ttft is None:
                                ttft = received - started
                    elif event == "error":
                        detail = payload.get("detail", "unknown")
                        stage_error = detail if isinstance(detail, str) else str(detail)
            elapsed = time.monotonic() - started
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started
            elapsed_seconds = round(elapsed, 3)
            stage_error = f"transport:{type(exc).__name__}:{exc}"
            turns.append(
                {
                    "turn": index,
                    "group": group,
                    "query": query,
                    "reference_answer": expected,
                    "key_points": key,
                    "answer_text": answer,
                    "ttft_seconds": round(ttft, 3) if ttft is not None else None,
                    "elapsed_seconds": elapsed_seconds,
                    "latency_seconds": elapsed_seconds,
                    "status": "fail",
                    "missing": [],
                    "notes": [stage_error],
                    "stage_error": stage_error,
                }
            )
            continue
        elapsed_seconds = round(elapsed, 3)
        evaluation = _evaluate(query, answer, expected, key)
        evaluation.update(
            {
                "turn": index,
                "group": group,
                "reference_answer": expected,
                "key_points": key,
                "answer_text": answer,
                "ttft_seconds": round(ttft, 3) if ttft is not None else None,
                "elapsed_seconds": elapsed_seconds,
                "latency_seconds": elapsed_seconds,
                "stage_error": stage_error,
            }
        )
        if stage_error:
            evaluation["status"] = "fail"
            evaluation["notes"].append(f"stage_error={stage_error}")
        turns.append(evaluation)

    passed = sum(1 for turn in turns if turn["status"] == "pass")
    total = len(turns)
    total_latency = sum(
        turn.get("elapsed_seconds", turn.get("latency_seconds", 0.0))
        for turn in turns
    )
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "single_session": args.single_session,
        "total_turns": total,
        "passed": passed,
        "failed": total - passed,
        "total_latency_seconds": round(total_latency, 2),
        "turns": turns,
    }
    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
    if args.markdown_output:
        lines = [
            "# Workbook Regression Report",
            "",
            f"- Run: {report['run_at']}",
            f"- Mode: {'single session' if args.single_session else 'independent sessions'}",
            f"- Passed: {passed}/{total}",
            f"- Total elapsed: {report['total_latency_seconds']}s",
            "",
            "| Turn | Group | Status | TTFT (s) | Elapsed (s) | Query | Missing |",
            "|---|---|---|---|---|---|---|",
        ]
        for turn in turns:
            missing = "，".join(turn.get("missing", []))[:60] or "-"
            ttft_seconds = turn.get("ttft_seconds")
            ttft_text = "-" if ttft_seconds is None else f"{ttft_seconds:.3f}"
            elapsed_seconds = turn.get(
                "elapsed_seconds",
                turn.get("latency_seconds", 0.0),
            )
            lines.append(
                f"| {turn['turn']} | {turn['group']} | {turn['status']} | "
                f"{ttft_text} | {elapsed_seconds:.3f} | "
                f"{turn['query'][:30]} | {missing} |"
            )
        lines.extend(["", "## Turn details"])
        for turn in turns:
            lines.extend(
                [
                    "",
                    f"### Turn {turn['turn']} ({turn['group']})",
                    "",
                    "```json",
                    json.dumps(turn, ensure_ascii=False, indent=2),
                    "```",
                ]
            )
        with open(args.markdown_output, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    print(f"PASS {passed}/{total} | total {report['total_latency_seconds']}s")
    for turn in turns:
        if turn["status"] != "pass":
            print(
                f"  FAIL turn {turn['turn']} ({turn['group']}) {turn['query'][:40]}"
                f" missing={turn.get('missing', [])[:5]}"
                f" err={turn.get('stage_error', '')[:40]}"
            )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
