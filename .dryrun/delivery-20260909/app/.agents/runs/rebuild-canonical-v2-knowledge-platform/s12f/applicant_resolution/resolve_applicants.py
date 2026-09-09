#!/usr/bin/env python
"""专利申请人名称解析管线 (s12f applicant resolution).

Pipeline:
  1. Aggregate patent applicants from `released_objects` (object_type='patent',
     payload_json.core_facts.applicants).
  2. Normalize-match against the company library (object_type='company',
     display_name + core_facts.name/aliases) -> status=already_matched.
  3. Institution filter -> status=institution (no company resolution).
  4. Individual (pure Chinese personal-name) filter -> status=unresolved
     (no search, saved serper budget).
  5. For the remaining company-type applicants (sorted by patent count desc):
     a. serper search the quoted applicant name (one retry on failure;
        one suffix retry "中国 公司"/"China company" only when organic is empty)
     b. take top-5 organic (title+snippet+link)
     c. LLM batch judgment (10 per batch) -> canonical Chinese company name
     d. write one line per applicant to applicant_name_resolution.jsonl

Idempotent: an existing output jsonl is backed up (timestamped) before overwrite.
Read-only on released_objects.db. No git operations.

Usage (run from apps/admin-console venv):
  python resolve_applicants.py [--db PATH] [--limit N] [--llm-profile NAME]
                               [--batch-size 10] [--max-serper 800]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

WORKTREE = Path("/home/longxiang/MiroThinker/.worktrees/canonical-v2-s11-consolidation")
MIROFLOW_AGENT_ROOT = WORKTREE / "apps/miroflow-agent"
if str(MIROFLOW_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(MIROFLOW_AGENT_ROOT))

from openai import OpenAI  # noqa: E402
from src.data_agents.professor.llm_profiles import (  # noqa: E402
    build_non_thinking_extra_body,
    resolve_professor_llm_settings,
)
from src.data_agents.providers.web_search import WebSearchProvider  # noqa: E402

DEFAULT_DB = Path("/home/longxiang/MiroThinker/logs/data_agents/released_objects.db")
OUT_DIR = Path(__file__).resolve().parent
DEFAULT_JSONL = OUT_DIR / "applicant_name_resolution.jsonl"

INSTITUTION_RE = re.compile(
    r"大学|学院|研究院|研究所|医院|中心|实验室|学校|局|委员会|总院|党校|科学院"
)
COMPANY_SUFFIX_RE = re.compile(r"公司|集团|股份|有限$|厂$|工厂|合伙")
# Pure Chinese personal names, e.g. 黄誉 / 杨一诺 (individual applicants).
PERSON_RE = re.compile(r"^[\u4e00-\u9fff]{2,4}$")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

SYSTEM_PROMPT = """你是专利申请人名称解析专家。系统给你一批"专利申请人名称"及各自的 web 搜索结果（标题/摘要/链接）。
你的任务：把每个申请人名称解析为规范的中文公司全称（例如"深圳市优必选科技股份有限公司"）。

规则：
1. resolved_company：该公司最规范的现行中文全称。若申请人本身就是规范全称，原样返回；若申请人是对应的英文名/简称/旧称，返回规范中文全称。
2. 若申请人不是公司（个人、高校、科研机构、医院、政府单位等），或无法确定对应公司，resolved_company 必须为空字符串 ""。
3. 若搜索结果指向多个不同公司且无法确定是哪一个，confidence 填 "low"，resolved_company 填最可能的一个，note 说明不确定性。
4. aliases：搜索结果中出现过的该公司的其他名称（英文名、简称、曾用名），最多 5 个，没有则空数组。
5. evidence_urls：支持你判定的搜索结果链接，最多 3 个，没有则空数组。
6. confidence：high=搜索结果明确指向唯一公司；medium=较明确；low=模糊或无法判定。
7. note：简短中文说明判定依据（如"搜索结果首条为该公司官网/企业信息页"）。

输出格式：只输出一个 JSON 数组，不要任何其他文字（不要 markdown 代码块）：
[{"applicant":"申请人名称原样","resolved_company":"规范中文公司全称或空","aliases":["..."],"evidence_urls":["..."],"confidence":"high|medium|low","note":"..."}]"""


def normalize_key(value: object) -> str | None:
    """Company/applicant normalization: strip non-alphanumeric + casefold
    (mirrors `_identity_lookup_key` in knowledge_build_isolated.py)."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = "".join(ch for ch in value.casefold() if ch.isalnum())
    return normalized or None


def aggregate_applicants(db_path: Path) -> Counter[str]:
    """Count patents per applicant name across all patents."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT payload_json FROM released_objects WHERE object_type='patent'"
        )
        counts: Counter[str] = Counter()
        for (payload_json,) in rows:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                continue
            applicants = (payload.get("core_facts") or {}).get("applicants")
            if applicants is None:
                continue
            if isinstance(applicants, str):
                applicants = [applicants]
            if isinstance(applicants, list):
                for name in applicants:
                    if isinstance(name, str) and name.strip():
                        counts[name] += 1
        return counts
    finally:
        con.close()


def load_company_keys(db_path: Path) -> dict[str, set[str]]:
    """Map company display_name -> normalized keys (display_name + core_facts.name + aliases)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT display_name, payload_json FROM released_objects WHERE object_type='company'"
        )
        companies: dict[str, set[str]] = {}
        for display_name, payload_json in rows:
            keys: set[str] = set()
            key = normalize_key(display_name)
            if key:
                keys.add(key)
            try:
                core = (json.loads(payload_json).get("core_facts") or {})
            except json.JSONDecodeError:
                core = {}
            for field in ("name", "aliases"):
                value = core.get(field)
                if isinstance(value, str):
                    key = normalize_key(value)
                    if key:
                        keys.add(key)
                elif isinstance(value, list):
                    for item in value:
                        key = normalize_key(item)
                        if key:
                            keys.add(key)
            companies[display_name] = keys
        return companies
    finally:
        con.close()


def classify_applicant(
    name: str, companies: dict[str, set[str]]
) -> tuple[str, str]:
    """Return (status, matched_company_or_empty)."""
    key = normalize_key(name)
    if key:
        for display_name, keys in companies.items():
            if key in keys:
                return "already_matched", display_name
    if INSTITUTION_RE.search(name) and not COMPANY_SUFFIX_RE.search(name):
        return "institution", ""
    if PERSON_RE.match(name):
        return "individual", ""
    return "company", ""


def extract_organic(search_result: dict) -> list[dict[str, str]]:
    organic = search_result.get("organic") or []
    top: list[dict[str, str]] = []
    for item in organic[:5]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if title or link:
            top.append(
                {
                    "title": title[:200],
                    "snippet": snippet[:300],
                    "link": link[:300],
                }
            )
    return top


def serper_search(
    provider: WebSearchProvider, name: str
) -> tuple[list[dict[str, str]], list[str], bool]:
    """Search applicant name; return (organic_top5, queries_used, search_ok).

    One retry on transient failure; one suffix retry when organic is empty.
    """
    queries = [f'"{name}"']
    if CJK_RE.search(name):
        queries.append(f'"{name}" 中国 公司')
    else:
        queries.append(f'"{name}" China company')

    organic: list[dict[str, str]] = []
    queries_used: list[str] = []
    for attempt, query in enumerate(queries):
        try:
            result = provider.search(query)
            queries_used.append(query)
            organic = extract_organic(result)
            if organic:
                return organic, queries_used, True
        except Exception as exc:  # noqa: BLE001 - provider raises RuntimeError etc.
            queries_used.append(query)
            if attempt == 0:
                # transient failure -> one retry with the primary query
                try:
                    result = provider.search(query)
                    organic = extract_organic(result)
                    if organic:
                        return organic, queries_used, True
                except Exception:  # noqa: BLE001
                    pass
    return organic, queries_used, bool(organic)


def truncate(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[: limit - 1] + "…"


def build_batch_user_message(batch: list[tuple[str, int, list[dict[str, str]]]]) -> str:
    parts: list[str] = []
    for index, (name, count, organic) in enumerate(batch, start=1):
        parts.append(f"申请人 {index}: {name}（专利数 {count}）")
        if not organic:
            parts.append("搜索结果: （无有效搜索结果）")
            continue
        lines = []
        for j, item in enumerate(organic, start=1):
            title = truncate(item["title"], 200)
            snippet = truncate(item["snippet"], 300)
            lines.append(
                f"[{j}] 标题: {title} | 摘要: {snippet} | 链接: {item['link']}"
            )
        parts.append("搜索结果:\n" + "\n".join(lines))
    return "\n\n".join(parts)


def parse_llm_json(text: str) -> list[dict] | None:
    """Robust JSON-array extraction from an LLM response."""
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start, end = stripped.find("["), stripped.rfind("]")
    if start != -1 and end > start:
        candidate = stripped[start : end + 1]
    else:
        # single object fallback
        start, end = stripped.find("{"), stripped.rfind("}")
        if start == -1 or end <= start:
            return None
        candidate = f"[{stripped[start:end + 1]}]"
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    result: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        applicant = item.get("applicant")
        if not isinstance(applicant, str):
            continue
        confidence = item.get("confidence")
        if confidence not in ("high", "medium", "low"):
            confidence = "low"
        def as_str_list(value: object) -> list[str]:
            if not isinstance(value, list):
                return []
            return [str(v).strip() for v in value if isinstance(v, str) and v.strip()][:5]
        result.append(
            {
                "applicant": applicant,
                "resolved_company": str(item.get("resolved_company") or "").strip(),
                "aliases": as_str_list(item.get("aliases")),
                "evidence_urls": as_str_list(item.get("evidence_urls"))[:3],
                "confidence": confidence,
                "note": str(item.get("note") or "").strip(),
            }
        )
    return result or None


def llm_judge_batch(
    client: OpenAI,
    model: str,
    extra_body: dict,
    batch: list[tuple[str, int, list[dict[str, str]]]],
    max_retries: int = 1,
) -> list[dict]:
    """One LLM call for a batch of applicants; returns per-applicant judgments.

    Raises on final failure so the caller can downgrade the whole batch to
    unresolved without aborting the run.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_batch_user_message(batch)},
    ]
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=8192,
                extra_body=extra_body,
            )
            text = (response.choices[0].message.content or "").strip()
            parsed = parse_llm_json(text)
            if parsed is not None:
                return parsed
            last_error = RuntimeError(f"LLM 输出无法解析为 JSON: {text[:200]!r}")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        if attempt < max_retries:
            messages.append(
                {
                    "role": "assistant",
                    "content": text if "text" in locals() else "（无输出）",
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": "上次输出无效。请只输出符合要求的 JSON 数组，不要任何其他文字。",
                }
            )
    raise RuntimeError(f"LLM 批量解析失败: {last_error}")


def status_for(judgment: dict) -> str:
    confidence = judgment.get("confidence", "low")
    company = judgment.get("resolved_company", "")
    if company and confidence == "high":
        return "resolved"
    if company and confidence == "medium":
        return "resolved"
    if company and confidence == "low":
        return "ambiguous"
    return "unresolved"


def main() -> None:
    parser = argparse.ArgumentParser(description="专利申请人名称解析管线")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="released_objects.db 路径")
    parser.add_argument("--out", type=Path, default=DEFAULT_JSONL, help="输出 jsonl 路径")
    parser.add_argument(
        "--limit", type=int, default=0, help="只解析前 N 个公司类申请人（原型模式，0=全部）"
    )
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--max-serper", type=int, default=800, help="serper 总请求预算")
    parser.add_argument("--llm-profile", default=None, help="LLM profile（默认走系统解析）")
    parser.add_argument("--sleep", type=float, default=0.3, help="serper 请求间隔")
    args = parser.parse_args()

    if args.limit and args.out == DEFAULT_JSONL and DEFAULT_JSONL.exists():
        line_count = sum(1 for _ in DEFAULT_JSONL.open(encoding="utf-8"))
        if line_count > 100:
            sys.exit(
                "防护：--limit 原型模式会覆盖完整输出，请显式指定 --out 到临时路径"
            )

    db_path = args.db.resolve()
    if not db_path.is_file():
        sys.exit(f"数据库不存在: {db_path}")

    settings = resolve_professor_llm_settings(
        profile_name=args.llm_profile, apply_endpoint_env_overrides=False
    )
    base_url = settings["local_llm_base_url"]
    model = settings["local_llm_model"]
    api_key = settings["local_llm_api_key"]
    if not api_key:
        sys.exit("LLM api key 为空，无法调用")
    extra_body = build_non_thinking_extra_body(model)
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=120)
    provider = WebSearchProvider(timeout=8)
    if not provider.api_key:
        sys.exit("serper api key 为空，无法搜索")

    print(f"[1/5] 聚合申请人… ({db_path})")
    applicants = aggregate_applicants(db_path)
    print(f"      专利 {len(applicants)} 个申请人（合计 {sum(applicants.values())} 条专利-申请人记录）")

    print("[2/5] 加载公司库归一化键…")
    companies = load_company_keys(db_path)
    print(f"      公司 {len(companies)} 家")

    print("[3/5] 分类（已匹配 / 机构 / 个人 / 公司类）…")
    rows: list[dict] = []
    stats = Counter()
    for name, count in sorted(applicants.items(), key=lambda kv: (-kv[1], kv[0])):
        status, matched = classify_applicant(name, companies)
        row = {
            "applicant_name": name,
            "patent_count": count,
            "status": status,
            "resolved_company": matched if status == "already_matched" else "",
            "aliases": [],
            "evidence_urls": [],
            "confidence": "",
            "note": ("公司库归一化匹配" if status == "already_matched"
                     else "机构（大学/研究院/医院等，不做公司解析）" if status == "institution"
                     else "个人申请人" if status == "individual"
                     else ""),
            "search_queries": [],
        }
        rows.append(row)
        stats[status] += 1
    print(f"      already_matched={stats['already_matched']} institution={stats['institution']} "
          f"individual={stats['individual']} company={stats['company']}")

    company_rows = [row for row in rows if row["status"] == "company"]
    if args.limit:
        company_rows = company_rows[: args.limit]
    print(f"[4/5] 解析 {len(company_rows)} 个公司类申请人（serper 预算 {args.max_serper}）…")

    if args.out.exists():
        backup = args.out.with_name(f"{args.out.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        backup.write_text(args.out.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"      已备份旧输出 -> {backup.name}")

    # already_matched / institution / individual rows are written first
    done_rows = [row for row in rows if row["status"] != "company"]
    with args.out.open("w", encoding="utf-8") as out_f:
        for row in done_rows:
            out_f.write(json.dumps(row, ensure_ascii=False) + "\n")

        serper_used = 0
        llm_batches = 0
        llm_failures = 0
        batch: list[tuple[str, int, list[dict[str, str]]]] = []
        for index, row in enumerate(company_rows, start=1):
            name = row["applicant_name"]
            organic, queries_used, ok = serper_search(provider, name)
            serper_used += len(queries_used)
            row["search_queries"] = queries_used
            row["_organic"] = organic
            batch.append((name, row["patent_count"], organic))
            if not ok:
                row["status"] = "unresolved"
                row["confidence"] = "low"
                row["note"] = "serper 无有效搜索结果（已重试）"
            time.sleep(args.sleep)

            if len(batch) >= args.batch_size or index == len(company_rows):
                pending = [b for b in batch if b[2] is not None]
                # rows without organic were already marked unresolved above
                judge_batch = [b for b in pending if b[2]]
                if judge_batch:
                    try:
                        judgments = llm_judge_batch(client, model, extra_body, judge_batch)
                        llm_batches += 1
                    except Exception as exc:  # noqa: BLE001
                        llm_failures += 1
                        print(f"      [批次失败] {exc}")
                        judgments = [
                            {"applicant": name_j, "resolved_company": "", "aliases": [],
                             "evidence_urls": [], "confidence": "low",
                             "note": "LLM 批量解析失败，降级为 unresolved"}
                            for name_j, _, _ in judge_batch
                        ]
                    by_name = {j["applicant"]: j for j in judgments}
                    for name_j, _, _ in judge_batch:
                        target = next(r for r in company_rows if r["applicant_name"] == name_j)
                        judgment = by_name.get(name_j)
                        if judgment is None:
                            target["status"] = "unresolved"
                            target["confidence"] = "low"
                            target["note"] = "LLM 结果缺失该申请人"
                            continue
                        target["resolved_company"] = judgment["resolved_company"]
                        target["aliases"] = judgment["aliases"]
                        target["evidence_urls"] = judgment["evidence_urls"]
                        target["confidence"] = judgment["confidence"]
                        target["note"] = judgment["note"]
                        target["status"] = status_for(judgment)
                    for name_j, _, _ in pending:
                        target = next(r for r in company_rows if r["applicant_name"] == name_j)
                        out_f.write(
                            json.dumps({k: v for k, v in target.items() if k != "_organic"},
                                       ensure_ascii=False) + "\n"
                        )
                else:
                    for name_j, _, _ in pending:
                        target = next(r for r in company_rows if r["applicant_name"] == name_j)
                        out_f.write(
                            json.dumps({k: v for k, v in target.items() if k != "_organic"},
                                       ensure_ascii=False) + "\n"
                        )
                batch = []

            if index % 10 == 0 or index == len(company_rows):
                print(f"      进度 {index}/{len(company_rows)}  serper_used={serper_used}")

            if serper_used >= args.max_serper and index < len(company_rows):
                print(f"      serper 预算耗尽（{args.max_serper}），其余标记 unresolved")
                for rest in company_rows[index:]:
                    rest["status"] = "unresolved"
                    rest["confidence"] = "low"
                    rest["note"] = "serper 预算不足，未解析"
                    out_f.write(
                        json.dumps({k: v for k, v in rest.items() if k != "_organic"},
                                   ensure_ascii=False) + "\n"
                    )
                break

    print("[5/5] 统计")
    final_stats = Counter()
    with args.out.open(encoding="utf-8") as f:
        for line in f:
            final_stats[json.loads(line)["status"]] += 1
    print(f"      总行数={sum(final_stats.values())} {dict(final_stats)}")
    print(f"      serper 请求总数={serper_used}  LLM 批次={llm_batches}  LLM 批次失败={llm_failures}")
    print(f"      输出 -> {args.out}")


if __name__ == "__main__":
    main()
