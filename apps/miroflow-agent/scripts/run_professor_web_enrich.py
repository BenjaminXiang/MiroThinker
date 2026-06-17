#!/usr/bin/env python
"""Web-search enrichment: multi-source, identity-verified professor profile enrichment.

For each professor:
  1. LLM generates 3-5 targeted search queries (name + institution + email/research → reduces false matches).
  2. Serper × queries → merged results.
  3. Identity filter (name + institution keywords in title/snippet).
  4. Fetch verified result pages (static → headless → CDP).
  5. Recursive crawl: follow personal-homepage links from verified pages (depth 1).
  6. gemma4 synthesizes a comprehensive bilingual profile_summary (300-500 chars) from all content.
  7. UPDATE professor.profile_summary + UPSERT enriched professor_fact.

Env: localhost DB needs proxy UNSET; Serper + external fetches are external.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import uuid
from typing import Any

import psycopg
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from psycopg.types.json import Json

from src.data_agents.browser_fetch import fetch_html_with_browser_fallback
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings
from src.data_agents.providers.web_search import WebSearchProvider

RUN_KIND = "backfill_real"
_SYS_QUERY = 'You generate web search queries. Return ONLY JSON {"queries": ["..."]}.'
_SYS_SYNTH = (
    "You write a comprehensive bilingual professor biography. "
    "Format: English paragraph (中文段落). "
    "Include: academic title, research areas, key projects/grants, career highlights, publications summary. "
    "300-500 characters total. Be specific — use the provided web content."
)


def _to_text(html: str) -> str:
    t = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    import html as H

    return re.sub(r"\s+", " ", H.unescape(t)).strip()


def _inst_keywords(institution: str) -> list[str]:
    """Extract institution-specific keyword fragments for identity matching."""
    kws = [institution]
    if "哈尔滨工业" in institution or "哈工大" in institution:
        kws += ["哈工大", "哈尔滨工业", "HIT", "hitsz", "hit.edu"]
    elif "南方科技" in institution or "南科大" in institution:
        kws += ["南科大", "南方科技", "SUSTech", "sustech"]
    elif "香港中文" in institution or "港中深" in institution:
        kws += ["港中深", "香港中文", "CUHK", "cuhk"]
    elif "深圳大学" in institution:
        kws += ["深圳大学", "深大", "SZU", "szu.edu"]
    elif "清华" in institution:
        kws += ["清华", "Tsinghua", "SIGS", "tsinghua"]
    elif "中山" in institution:
        kws += ["中山", "SYSU", "sysu.edu"]
    elif "电子科技" in institution:
        kws += ["电子科技", "UESTC", "uestc.edu"]
    elif "深圳理工" in institution:
        kws += ["深圳理工", "SUAT", "suat"]
    elif "深圳信息" in institution:
        kws += ["深圳信息", "sziit"]
    return list(set(kws))


def _generate_queries(
    client: OpenAI,
    model: str,
    name: str,
    institution: str,
    department: str | None,
    email: str | None,
    research: str | None,
) -> list[str]:
    prompt = (
        f"Generate 3-5 search queries to find comprehensive info about this professor.\n"
        f"Professor: {name}\nInstitution: {institution}\nDepartment: {department or 'N/A'}\n"
        f"Email: {email or 'N/A'}\nResearch: {research or 'N/A'}\n\n"
        f"Rules: Each query MUST include the name + institution. Use different angles "
        f"(Chinese name+institution, English name+institution, email, research area+institution). "
        f'Return JSON {{"queries": ["..."]}}.'
    )
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYS_QUERY},
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
            temperature=0.3,
        )
        content = (r.choices[0].message.content or "").strip()
        content = content[content.find("{") : content.rfind("}") + 1]
        queries = json.loads(content).get("queries", [])
        return [q for q in queries if q and len(q) > 5][:5]
    except Exception:
        # fallback: simple queries
        return [
            f"{name} {institution} 教授 简介",
            f"{name} {institution} 研究方向 科研项目",
        ]


def _identity_filter(
    results: list[dict],
    name: str,
    institution: str,
) -> list[dict]:
    kws = _inst_keywords(institution)
    verified = []
    for r in results:
        text = f"{r.get('title', '')} {r.get('snippet', '')}"
        if name in text and any(kw.lower() in text.lower() for kw in kws):
            verified.append(r)
    # dedupe by link
    seen = set()
    deduped = []
    for v in verified:
        link = v.get("link", "")
        if link not in seen:
            seen.add(link)
            deduped.append(v)
    return deduped


def _find_personal_links(
    html: str, base_url: str, school_domains: list[str]
) -> list[str]:
    """Extract links that look like personal homepages (different domain from school)."""
    soup = BeautifulSoup(html or "", "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http") and not any(d in href for d in school_domains):
            # skip social media, generic sites
            if any(
                x in href.lower()
                for x in [
                    "scholar.google",
                    "researchgate",
                    "orcid",
                    "github.io",
                    "wp-content",
                    "/cv",
                    "/pub",
                ]
            ):
                links.append(href)
            # personal domain (heuristic: short path, name-like)
            elif re.match(r"https?://[^/]+(/\w+)?/?$", href) and len(href) < 80:
                links.append(href)
    return list(dict.fromkeys(links))[:3]  # dedupe, limit 3


def main() -> int:
    p = argparse.ArgumentParser(
        description="Web-search enrichment for professor profiles."
    )
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    p.add_argument("--institution", default=None, help="filter by institution.")
    p.add_argument("--professor-id", default=None, help="target a specific professor.")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--llm-profile", default="gemma4")
    p.add_argument("--sleep", type=float, default=2.0)
    p.add_argument(
        "--min-summary-len",
        type=int,
        default=200,
        help="only enrich profs whose profile_summary is shorter than this (0 = all).",
    )
    args = p.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL or --dsn required")
    if "+psycopg" in args.dsn:
        args.dsn = args.dsn.replace("postgresql+psycopg://", "postgresql://")
    load_dotenv(override=True)  # need SERPER_API_KEY

    settings = resolve_professor_llm_settings(args.llm_profile)
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings.get("local_llm_api_key") or "EMPTY",
        timeout=120.0,
    )
    model = settings["local_llm_model"]
    serper = WebSearchProvider()
    run_id = str(uuid.uuid4())

    conn = psycopg.connect(args.dsn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pipeline_run(run_id,run_kind,run_scope,started_at,status,created_at,triggered_by)"
            " VALUES(%s,%s,%s,now(),'running',now(),'web_enrich')",
            (run_id, RUN_KIND, Json({"purpose": "web_search_enrichment"})),
        )
        conn.commit()

        # select profs to enrich
        where = ["p.profile_summary IS NOT NULL"]
        params: list[Any] = []
        if args.professor_id:
            where.append("p.professor_id = %s")
            params.append(args.professor_id)
        if args.institution:
            where.append("pa.institution = %s")
            params.append(args.institution)
        if args.min_summary_len > 0:
            where.append("length(coalesce(p.profile_summary,'')) < %s")
            params.append(args.min_summary_len)
        where_sql = " AND ".join(where)
        cur.execute(
            f"""SELECT p.professor_id, p.canonical_name, p.profile_summary, p.email,
                       pa.institution, pa.department, sp.url
                FROM professor p
                JOIN professor_affiliation pa ON pa.professor_id=p.professor_id AND pa.is_primary
                LEFT JOIN source_page sp ON sp.page_id=p.primary_official_profile_page_id
                WHERE {where_sql}
                ORDER BY p.professor_id LIMIT %s OFFSET %s""",
            params + [args.limit, args.offset],
        )
        profs = cur.fetchall()

    print(f"run_id={run_id} | {len(profs)} profs to enrich | model={model}")
    enriched_count = 0
    for (
        pid,
        name,
        current_summary,
        email,
        institution,
        department,
        homepage_url,
    ) in profs:
        try:
            # 1. LLM query rewrite
            queries = _generate_queries(
                client, model, name, institution, department, email, current_summary
            )

            # 2. Serper search
            all_results: list[dict] = []
            for q in queries:
                try:
                    raw = serper.search(q)
                    all_results.extend(raw.get("organic", []))
                except Exception:
                    pass
                time.sleep(0.5)

            # 3. Identity filter
            verified = _identity_filter(all_results, name, institution)
            if not verified:
                print(
                    f"  {name}: no verified results from {len(all_results)} total",
                    flush=True,
                )
                time.sleep(args.sleep)
                continue

            # 4. Fetch verified pages
            school_domains = ["edu.cn", institution[:4]] if institution else ["edu.cn"]
            gathered_texts: list[str] = []
            for v in verified[:5]:
                url = v.get("link", "")
                if not url:
                    continue
                try:
                    html, _method = fetch_html_with_browser_fallback(
                        url, min_text_len=100
                    )
                    text = _to_text(html)[:3000]
                    if len(text) > 100:
                        gathered_texts.append(f"[{v.get('title', '')}] {text}")
                        # 5. Recursive: find personal homepage links
                        personal = _find_personal_links(html, url, school_domains)
                        for pl in personal[:2]:
                            try:
                                ph, _ = fetch_html_with_browser_fallback(
                                    pl, min_text_len=100
                                )
                                pt = _to_text(ph)[:2000]
                                if len(pt) > 100:
                                    gathered_texts.append(f"[personal: {pl}] {pt}")
                            except Exception:
                                pass
                except Exception:
                    pass

            if not gathered_texts:
                print(f"  {name}: verified results but no content fetched", flush=True)
                time.sleep(args.sleep)
                continue

            # 6. Synthesize comprehensive bio
            all_content = "\n---\n".join(gathered_texts)[:8000]
            synth_prompt = (
                f"Professor: {name}, {institution}\n"
                f"Department: {department or 'N/A'}\n"
                f"Current bio: {(current_summary or '')[:200]}\n\n"
                f"Web content (verified for this professor):\n{all_content}\n\n"
                f"Write a comprehensive bilingual biography."
            )
            r = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYS_SYNTH},
                    {"role": "user", "content": synth_prompt},
                ],
                max_tokens=800,
                temperature=0.3,
            )
            enriched = (r.choices[0].message.content or "").strip()
            if len(enriched) < 50:
                print(
                    f"  {name}: synthesis too short ({len(enriched)}c), skipping",
                    flush=True,
                )
                time.sleep(args.sleep)
                continue

            # 7. Write
            with conn.cursor() as c:
                c.execute(
                    "UPDATE professor SET profile_summary=%s WHERE professor_id=%s AND length(coalesce(profile_summary,'')) < %s",
                    (enriched[:800], pid, len(enriched)),
                )
                updated = c.rowcount
                if updated:
                    c.execute(
                        "INSERT INTO professor_fact(professor_id,fact_type,value_raw,source_page_id,evidence_span,confidence,status,run_id)"
                        " VALUES(%s,'homepage',%s,%s,%s,0.85,'active',%s) ON CONFLICT DO NOTHING",
                        (
                            pid,
                            enriched[:500],
                            None,
                            f"web_enrich: {len(verified)} verified results",
                            run_id,
                        ),
                    )
                conn.commit()

            enriched_count += 1
            print(
                f"  {name}: enriched ({len(enriched)}c, {len(verified)} verified, {len(gathered_texts)} pages fetched) {'✓ written' if updated else '(existing longer)'}",
                flush=True,
            )
        except Exception as exc:
            conn.rollback()
            print(f"  {name}: ERR {type(exc).__name__}: {str(exc)[:100]}", flush=True)
        time.sleep(args.sleep)

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE pipeline_run SET status='succeeded',finished_at=now(),items_processed=%s WHERE run_id=%s",
            (enriched_count, run_id),
        )
    conn.commit()
    conn.close()
    print(f"DONE: {enriched_count}/{len(profs)} enriched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
