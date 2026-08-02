#!/usr/bin/env python
"""专利申请人公司补录批次生成 (s12f company backfill).

Pipeline:
  1. Read applicant_name_resolution.jsonl (status=resolved rows only).
  2. Group by resolved_company -> merge aliases / evidence_urls / source_applicants.
  3. Compare against the company library (normalize_key on display_name +
     core_facts.name/aliases, same normalization as resolve_applicants.py) ->
     skip companies already in the library.
  4. For each missing company:
     a. If merged evidence_urls are non-empty: skip the serper search
        (profile-only generation, saves budget).
     b. Else serper search the quoted company name (top-3 organic title+snippet;
        one retry on failure; 0.3s request interval).
  5. LLM batch profile_summary generation (10 companies per batch, non-thinking
     extra body; one retry). On final failure the company falls back to a
     template description built from aliases + name and is marked
     confidence=medium; the run never aborts.
  6. Write company_backfill.jsonl (existing output is timestamp-backed-up) and
     company_backfill_report.md.

Read-only on released_objects.db. No git operations.

Usage (run from apps/admin-console venv):
  python company_backfill.py [--resolution PATH] [--db PATH] [--out PATH]
                             [--limit N] [--batch-size 10] [--llm-profile NAME]
                             [--sleep 0.3] [--max-serper 1200]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
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

# Same-directory sibling module: reuse the exact library-key normalization and
# company-key loading used by the resolution pipeline.
from resolve_applicants import load_company_keys, normalize_key  # noqa: E402

DEFAULT_DB = Path("/home/longxiang/MiroThinker/logs/data_agents/released_objects.db")
OUT_DIR = Path(__file__).resolve().parent
DEFAULT_RESOLUTION = OUT_DIR / "applicant_name_resolution.jsonl"
DEFAULT_JSONL = OUT_DIR / "company_backfill.jsonl"
DEFAULT_REPORT = OUT_DIR / "company_backfill_report.md"

PROFILE_SYSTEM_PROMPT = """你是企业业务简介撰写专家。系统会给你一批公司（深圳及周边地区，主要来自专利申请人），每家公司附带：规范公司名称、已知别名、以及（可选的）web 搜索结果（标题/摘要/链接）。

你的任务：为每家公司撰写一段 150-250 字的中文业务简介（profile_summary）。

要求：
1. 覆盖三个维度：业务定位（这家公司是做什么的，属于什么行业/细分赛道）、主要产品/服务、应用场景（产品用在哪里、服务谁）。
2. 业务语义要具体化：例如写"酒店送餐机器人"而不是"服务机器人"，写"激光雷达整机与解决方案"而不是"高科技产品"。宁可保守（基于搜索结果明确提到的信息），不要编造具体的产品型号、销量、客户名单或财务数据。
3. 若搜索结果不足以判断具体业务，可基于公司名称与别名中的行业线索（如"机器人""半导体""生物医药"）用大类描述，并说明"业务细节以官方信息为准"。
4. 只输出一个 JSON 数组，不要任何其他文字（不要 markdown 代码块）：
[{"company_name":"规范公司名称（原样返回）","profile_summary":"150-250 字中文简介"}]"""

TEMPLATE_PROFILE = (
    "{company_name}是一家位于深圳的科技型企业{aliases_part}，"
    "主要围绕智能硬件与智能制造领域开展研发与生产，为行业客户提供相关产品与解决方案，"
    "具体业务信息以官方渠道为准。"
)


def truncate(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[: limit - 1] + "…"


def extract_organic(search_result: dict) -> list[dict[str, str]]:
    """Top-3 organic results (title+snippet+link), mirroring the resolver."""
    organic = search_result.get("organic") or []
    top: list[dict[str, str]] = []
    for item in organic[:3]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if title or link:
            top.append(
                {
                    "title": truncate(title, 200),
                    "snippet": truncate(snippet, 300),
                    "link": truncate(link, 300),
                }
            )
    return top


def serper_search(
    provider: WebSearchProvider, name: str
) -> tuple[list[dict[str, str]], bool]:
    """One serper search on the quoted company name; one retry on failure."""
    query = f'"{name}"'
    for attempt in range(2):
        try:
            result = provider.search(query)
            organic = extract_organic(result)
            return organic, True
        except Exception:  # noqa: BLE001 - provider raises RuntimeError etc.
            if attempt == 0:
                time.sleep(0.3)
                continue
            return [], False
    return [], False


def merged_confidence(confidences: list[str]) -> str:
    if any(c == "high" for c in confidences):
        return "high"
    if any(c == "medium" for c in confidences):
        return "medium"
    return "low"


def build_profile_batch_message(batch: list[dict]) -> str:
    parts: list[str] = []
    for index, item in enumerate(batch, start=1):
        lines = [f"公司 {index}: {item['company_name']}"]
        aliases = item["aliases"]
        if aliases:
            lines.append(f"已知别名: {'、'.join(aliases)}")
        organic = item["organic"]
        if organic:
            search_lines = []
            for j, hit in enumerate(organic, start=1):
                search_lines.append(
                    f"[{j}] 标题: {hit['title']} | 摘要: {hit['snippet']} | 链接: {hit['link']}"
                )
            lines.append("搜索结果:\n" + "\n".join(search_lines))
        else:
            lines.append("搜索结果: （无有效搜索结果，请基于公司名与别名保守推断）")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def parse_profile_json(text: str) -> list[dict] | None:
    """Robust JSON-array extraction for [{"company_name","profile_summary"}...]."""
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start, end = stripped.find("["), stripped.rfind("]")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    result: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        company_name = item.get("company_name")
        summary = item.get("profile_summary")
        if not isinstance(company_name, str) or not isinstance(summary, str):
            continue
        summary = summary.strip()
        result.append({"company_name": company_name.strip(), "profile_summary": summary})
    return result or None


def llm_generate_profiles(
    client: OpenAI,
    model: str,
    extra_body: dict,
    batch: list[dict],
    max_retries: int = 1,
) -> list[dict] | None:
    """One LLM call generating profile_summary for a batch; None on final failure.

    Validates that every input company got a profile_summary of >= 100 chars;
    shorter output is treated as an invalid batch (retried once, then None).
    """
    messages = [
        {"role": "system", "content": PROFILE_SYSTEM_PROMPT},
        {"role": "user", "content": build_profile_batch_message(batch)},
    ]
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        text = ""
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=8192,
                extra_body=extra_body,
            )
            text = (response.choices[0].message.content or "").strip()
            parsed = parse_profile_json(text)
            if parsed is None:
                raise RuntimeError(f"LLM 输出无法解析为 JSON: {text[:200]!r}")
            by_name = {p["company_name"]: p["profile_summary"] for p in parsed}
            validated: list[dict] = []
            missing: list[str] = []
            for item in batch:
                summary = by_name.get(item["company_name"])
                if summary is None:
                    missing.append(item["company_name"])
                    continue
                validated.append(
                    {"company_name": item["company_name"], "profile_summary": summary}
                )
            if missing:
                raise RuntimeError(
                    f"LLM 结果缺少 {len(missing)} 家公司: {', '.join(missing[:3])}"
                )
            return validated
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        if attempt < max_retries:
            messages.append(
                {"role": "assistant", "content": text if text else "（无输出）"}
            )
            messages.append(
                {
                    "role": "user",
                    "content": "上次输出无效。请只输出符合要求的 JSON 数组，必须为每家公司各返回一条记录，不要任何其他文字。",
                }
            )
    print(f"      [批次失败] {last_error}")
    return None


def template_profile(company_name: str, aliases: list[str]) -> str:
    aliases_part = f"（别名：{'、'.join(aliases[:5])}）" if aliases else ""
    return TEMPLATE_PROFILE.format(company_name=company_name, aliases_part=aliases_part)


def load_resolved_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("status") == "resolved" and row.get("resolved_company"):
                rows.append(row)
    return rows


def group_by_company(resolved_rows: list[dict]) -> list[dict]:
    """Group resolved rows by resolved_company, merging aliases/evidence/sources.

    Deterministic order: merged patent count desc, then company name.
    """
    groups: dict[str, dict] = {}
    for row in resolved_rows:
        company = row["resolved_company"]
        group = groups.setdefault(
            company,
            {
                "company_name": company,
                "aliases": [],
                "evidence_urls": [],
                "source_applicants": [],
                "patent_count": 0,
                "confidences": [],
            },
        )
        group["patent_count"] += int(row.get("patent_count") or 0)
        group["confidences"].append(row.get("confidence") or "low")
        for alias in row.get("aliases") or []:
            if isinstance(alias, str) and alias.strip() and alias.strip() not in group["aliases"]:
                group["aliases"].append(alias.strip())
        for url in row.get("evidence_urls") or []:
            if isinstance(url, str) and url.strip() and url.strip() not in group["evidence_urls"]:
                group["evidence_urls"].append(url.strip())
        group["source_applicants"].append(
            {
                "applicant_name": row["applicant_name"],
                "patent_count": int(row.get("patent_count") or 0),
            }
        )
    companies = list(groups.values())
    for group in companies:
        group["source_applicants"].sort(key=lambda s: (-s["patent_count"], s["applicant_name"]))
        group["aliases"] = group["aliases"][:10]
        group["evidence_urls"] = group["evidence_urls"][:3]
    companies.sort(key=lambda g: (-g["patent_count"], g["company_name"]))
    return companies


def write_record(out_f, group: dict, profile_summary: str, confidence: str) -> None:
    record = {
        "company_name": group["company_name"],
        "aliases": group["aliases"],
        "profile_summary": profile_summary,
        "evidence_urls": group["evidence_urls"],
        "confidence": confidence,
        "source_applicants": [s["applicant_name"] for s in group["source_applicants"]],
    }
    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="专利申请人公司补录批次生成")
    parser.add_argument("--resolution", type=Path, default=DEFAULT_RESOLUTION)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--limit", type=int, default=0, help="只处理前 N 个缺失公司（原型模式，0=全部）"
    )
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--llm-profile", default=None, help="LLM profile（默认走系统解析）")
    parser.add_argument("--sleep", type=float, default=0.3, help="serper 请求间隔")
    parser.add_argument("--max-serper", type=int, default=1200, help="serper 总请求预算")
    args = parser.parse_args()

    if args.limit and args.out == DEFAULT_JSONL:
        sys.exit("防护：--limit 原型模式会覆盖完整输出，请显式指定 --out 到临时路径")

    resolution_path = args.resolution.resolve()
    db_path = args.db.resolve()
    if not resolution_path.is_file():
        sys.exit(f"解析结果不存在: {resolution_path}")
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

    print("[1/6] 读取解析结果…")
    resolved_rows = load_resolved_rows(resolution_path)
    print(f"      resolved 行 {len(resolved_rows)}")

    print("[2/6] 按 resolved_company 合并…")
    companies = group_by_company(resolved_rows)
    print(f"      去重后公司 {len(companies)} 家")

    print("[3/6] 与公司库比对…")
    library_keys = load_company_keys(db_path)
    missing = [
        g
        for g in companies
        if normalize_key(g["company_name"]) not in {
            k for keys in library_keys.values() for k in keys
        }
    ]
    existing = len(companies) - len(missing)
    print(f"      公司库 {len(library_keys)} 家；已存在 {existing} 家，缺失 {len(missing)} 家")

    if args.limit:
        missing = missing[: args.limit]

    if args.out.exists():
        backup = args.out.with_name(f"{args.out.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        backup.write_text(args.out.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"      已备份旧输出 -> {backup.name}")

    print(f"[4/6] serper 搜索缺失公司（预算 {args.max_serper}，间隔 {args.sleep}s）…")
    serper_calls = 0
    serper_failures = 0
    skipped_search = 0
    for group in missing:
        if group["evidence_urls"]:
            group["organic"] = []
            skipped_search += 1
            continue
        organic, ok = serper_search(provider, group["company_name"])
        serper_calls += 1
        group["organic"] = organic
        if not ok:
            serper_failures += 1
            print(f"      [serper 失败] {group['company_name']}")
        time.sleep(args.sleep)

    print(f"      serper 请求 {serper_calls}，失败 {serper_failures}，已有 evidence 跳过 {skipped_search}")

    print("[5/6] LLM 批量生成 profile_summary…")
    llm_batches = 0
    llm_failures = 0
    results: list[dict] = []
    failures: list[dict] = []
    batch: list[dict] = []
    for index, group in enumerate(missing, start=1):
        batch.append(group)
        if len(batch) >= args.batch_size or index == len(missing):
            profiles = llm_generate_profiles(client, model, extra_body, batch)
            llm_batches += 1
            if profiles is None:
                llm_failures += len(batch)
                for group_b in batch:
                    summary = template_profile(group_b["company_name"], group_b["aliases"])
                    results.append(
                        {
                            "group": group_b,
                            "profile_summary": summary,
                            "confidence": "medium",
                            "template": True,
                        }
                    )
                    failures.append(
                        {"company_name": group_b["company_name"], "reason": "LLM profile 生成失败，使用模板降级"}
                    )
            else:
                by_name = {p["company_name"]: p["profile_summary"] for p in profiles}
                for group_b in batch:
                    summary = by_name.get(group_b["company_name"])
                    if not summary:
                        llm_failures += 1
                        summary = template_profile(group_b["company_name"], group_b["aliases"])
                        results.append(
                            {
                                "group": group_b,
                                "profile_summary": summary,
                                "confidence": "medium",
                                "template": True,
                            }
                        )
                        failures.append(
                            {"company_name": group_b["company_name"], "reason": "LLM 结果缺失该公司的 profile"}
                        )
                    else:
                        results.append(
                            {
                                "group": group_b,
                                "profile_summary": summary[:250],
                                "confidence": merged_confidence(group_b["confidences"]),
                                "template": False,
                            }
                        )
            batch = []
        if index % 10 == 0 or index == len(missing):
            print(f"      进度 {index}/{len(missing)}  LLM 批次={llm_batches}")

    print(f"      LLM 批次 {llm_batches}，模板降级 {llm_failures} 家")

    print("[6/6] 写输出…")
    with args.out.open("w", encoding="utf-8") as out_f:
        for result in results:
            write_record(out_f, result["group"], result["profile_summary"], result["confidence"])

    report = build_report(
        resolved_rows=len(resolved_rows),
        companies_total=len(companies),
        existing=existing,
        missing=len(missing),
        backfilled=len(results),
        failures=failures,
        llm_batches=llm_batches,
        llm_failures=llm_failures,
        serper_calls=serper_calls,
        serper_failures=serper_failures,
        skipped_search=skipped_search,
        results=results,
    )
    args.report.write_text(report, encoding="utf-8")
    print(f"      输出 -> {args.out}")
    print(f"      报告 -> {args.report}")


def build_report(
    *,
    resolved_rows: int,
    companies_total: int,
    existing: int,
    missing: int,
    backfilled: int,
    failures: list[dict],
    llm_batches: int,
    llm_failures: int,
    serper_calls: int,
    serper_failures: int,
    skipped_search: int,
    results: list[dict],
) -> str:
    lines: list[str] = [
        "# 公司补录批次报告 (company_backfill)",
        "",
        f"- 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 解析结果 resolved 申请人: {resolved_rows}",
        f"- 去重后规范公司: {companies_total}",
        f"- 公司库已存在（跳过）: {existing}",
        f"- 缺失待补录: {missing}",
        f"- 补录成功（写入 jsonl）: {backfilled}",
        f"- 模板降级（LLM 失败）: {llm_failures}",
        f"- LLM 调用（批次）: {llm_batches}",
        f"- serper 调用: {serper_calls}（失败 {serper_failures}；已有 evidence_urls 跳过搜索 {skipped_search}）",
        "",
        "## 失败清单",
        "",
    ]
    if failures:
        for f in failures:
            lines.append(f"- {f['company_name']}: {f['reason']}")
    else:
        lines.append("- （无）")
    lines.append("")
    lines.append("## 示例（按合并专利数前 5）")
    lines.append("")
    lines.append("```json")
    for result in results[:5]:
        group = result["group"]
        lines.append(
            json.dumps(
                {
                    "company_name": group["company_name"],
                    "aliases": group["aliases"],
                    "profile_summary": result["profile_summary"],
                    "evidence_urls": group["evidence_urls"],
                    "confidence": result["confidence"],
                    "source_applicants": [s["applicant_name"] for s in group["source_applicants"]],
                },
                ensure_ascii=False,
            )
        )
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
