#!/usr/bin/env python
"""UPC: Unified Professor Crawl — one pass per professor, ALL dimensions.

Replaces the fragmented pipeline (L2 fields / web-enrich / paper-ingest run separately)
with a single per-professor pass:
  ① Fetch ALL pages: official homepage (static→headless→CDP) + recursive sub-pages + web search (Serper + identity-filtered).
  ② Unified LLM extraction (2 calls per user decision):
     Call 1: profile_summary + research_directions + education + academic_position + work_experience + contact + research_projects + awards.
     Call 2: papers (title/authors/year/venue/doi from all gathered text).
  ③ Write: UPDATE professor.profile_summary + UPSERT professor_fact + INSERT papers + professor_paper_link.

Usage: uv run python scripts/run_unified_professor_crawl.py --institution "深圳大学" --limit 50
       uv run python scripts/run_unified_professor_crawl.py --institution "哈尔滨工业大学（深圳）" --force-browser --limit 200
       xvfb-run -a uv run python scripts/run_unified_professor_crawl.py --institution "深圳大学" --use-cdp --limit 200
"""

from __future__ import annotations

import argparse
import html as html_mod
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

from src.data_agents.browser_fetch import (
    CDPChromeRenderer,
    fetch_html_with_browser_fallback,
    render_html_with_browser,
)
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings
from src.data_agents.providers.web_search import WebSearchProvider

RUN_KIND = "backfill_real"

# ── LLM prompts ─────────────────────────────────────────────────────────────

_SYS_FIELDS = (
    "You extract structured professor data from web pages. Return ONLY minified JSON."
)
_PROMPT_FIELDS = """Professor: {name}, {institution}
Department: {dept}

Web content from multiple sources (official homepage + verified web results):
{content}

Extract these fields. For English content, add Chinese in parentheses: "English (中文)".
Return JSON ONLY:
{{
  "profile_summary": "300-500 char comprehensive bilingual bio (include research, career, grants, achievements, publications count)",
  "research_directions": ["bilingual strings"],
  "education": [{{"school":"","degree":"","field":""}}],
  "academic_position": "bilingual or null",
  "work_experience": [{{"organization":"","role":""}}],
  "contact_email": "or null",
  "research_projects": [{{"name":"","funder":"","year":""}}],
  "awards": ["bilingual strings"]
}}

Rules: only include data that's actually in the content. null/[] for absent fields. Be comprehensive — this is the professor's complete profile.
"""

_SYS_PAPERS = "You extract academic publication titles from text. Return ONLY JSON."
_PROMPT_PAPERS = """Publications from professor {name}'s web pages:
{text}

Extract ALL publications. Return JSON ONLY:
{{"papers": [{{"title": "...", "authors": "...", "year": "...", "venue": "..."}}]}}

Rules: only real papers (skip section labels, nav, counts). Include ALL papers found.
"""

_SYS_QUERY = 'You generate web search queries. Return ONLY JSON {"queries": ["..."]}.'


# ── Helpers ──────────────────────────────────────────────────────────────────


def _to_text(html: str) -> str:
    t = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html_mod.unescape(t)).strip()


def _inst_keywords(institution: str) -> list[str]:
    kws = [institution]
    short_map = {
        "哈尔滨工业": ["哈工大", "HIT", "hitsz", "hit.edu"],
        "南方科技": ["南科大", "SUSTech", "sustech"],
        "香港中文": ["港中深", "CUHK", "cuhk"],
        "深圳大学": ["深大", "SZU", "szu.edu"],
        "清华": ["清华", "Tsinghua", "SIGS"],
        "中山": ["中山", "SYSU", "sysu.edu"],
        "电子科技": ["电子科技", "UESTC", "uestc.edu"],
        "深圳理工": ["深圳理工", "SUAT"],
        "深圳技术": ["深圳技术", "SZTU"],
        "深圳信息": ["深圳信息", "sziit"],
    }
    for key, vals in short_map.items():
        if key in institution:
            kws += vals
    return list(set(kws))


def _find_subpage_links(html: str, base_url: str) -> list[str]:
    """Find publication/research sub-page links on the homepage."""
    soup = BeautifulSoup(html or "", "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if any(
            kw in text
            for kw in [
                "论文",
                "publication",
                "paper",
                "著作",
                "成果",
                "research",
                "project",
                "科研",
                "项目",
            ]
        ):
            from urllib.parse import urljoin

            full = urljoin(base_url, href)
            if full.startswith("http"):
                links.append(full)
    return list(dict.fromkeys(links))[:3]


def _generate_queries(client, model, name, institution, dept, email) -> list[str]:
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYS_QUERY},
                {
                    "role": "user",
                    "content": (
                        f"Generate 3 search queries for this professor. Each MUST include name+institution.\n"
                        f"Professor: {name}\nInstitution: {institution}\nDept: {dept or 'N/A'}\nEmail: {email or 'N/A'}\n"
                        f'Return JSON {{"queries":["..."]}}.'
                    ),
                },
            ],
            max_tokens=300,
            temperature=0.3,
        )
        content = (r.choices[0].message.content or "").strip()
        return json.loads(content[content.find("{") : content.rfind("}") + 1]).get(
            "queries", []
        )[:3]
    except Exception:
        return [
            f"{name} {institution} 教授 简介",
            f"{name} {institution} 研究方向 科研项目",
        ]


def _identity_filter(results: list[dict], name: str, institution: str) -> list[dict]:
    kws = _inst_keywords(institution)
    verified, seen = [], set()
    for r in results:
        text = f"{r.get('title', '')} {r.get('snippet', '')}"
        link = r.get("link", "")
        if (
            name in text
            and any(kw.lower() in text.lower() for kw in kws)
            and link not in seen
        ):
            verified.append(r)
            seen.add(link)
    return verified


# ── Core: per-professor unified crawl ───────────────────────────────────────


def crawl_one_professor(
    pid: str,
    name: str,
    institution: str,
    dept: str | None,
    email: str | None,
    homepage_url: str | None,
    page_id: str | None,
    client: OpenAI,
    model: str,
    serper: WebSearchProvider,
    cdp_renderer: CDPChromeRenderer | None,
    force_browser: bool,
    max_text: int = 6000,
    web_search: bool = True,
) -> dict[str, Any]:
    """One professor → gather all text → extract fields + papers → return results."""

    # ① FETCH ALL PAGES
    gathered: list[str] = []

    # ①a. Official homepage (+ sub-pages)
    if homepage_url:
        try:
            if force_browser:
                html = render_html_with_browser(homepage_url, timeout=90)
            else:
                html, _ = fetch_html_with_browser_fallback(
                    homepage_url, cdp_renderer=cdp_renderer
                )
            text = _to_text(html)
            if len(text) > 60:
                gathered.append(f"[homepage] {text[:max_text]}")
                # ①b. Recursive: find + fetch sub-pages (publications/projects)
                for sub_url in _find_subpage_links(html, homepage_url):
                    try:
                        if force_browser:
                            sub_html = render_html_with_browser(sub_url, timeout=60)
                        else:
                            sub_html, _ = fetch_html_with_browser_fallback(
                                sub_url, cdp_renderer=cdp_renderer
                            )
                        sub_text = _to_text(sub_html)
                        if len(sub_text) > 100:
                            gathered.append(f"[subpage: {sub_url}] {sub_text[:4000]}")
                    except Exception:
                        pass
        except Exception:
            pass

    # ①c. Web search supplement
    if web_search:
        queries = _generate_queries(client, model, name, institution, dept, email)
        all_results: list[dict] = []
        for q in queries:
            try:
                raw = serper.search(q)
                all_results.extend(raw.get("organic", []))
            except Exception:
                pass
            time.sleep(0.3)
        verified = _identity_filter(all_results, name, institution)
        for v in verified[:3]:
            url = v.get("link", "")
            if not url:
                continue
            try:
                vhtml, _ = fetch_html_with_browser_fallback(url, min_text_len=100)
                vtext = _to_text(vhtml)
                if len(vtext) > 100:
                    gathered.append(f"[web: {v.get('title', '')}] {vtext[:3000]}")
            except Exception:
                pass

    if not gathered:
        return {"status": "no_content", "fields": None, "papers": []}

    all_content = "\n---\n".join(gathered)[:10000]

    # ②a. LLM Call 1: FIELDS + BIO + PROJECTS + AWARDS
    try:
        r1 = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYS_FIELDS},
                {
                    "role": "user",
                    "content": _PROMPT_FIELDS.format(
                        name=name,
                        institution=institution,
                        dept=dept or "N/A",
                        content=all_content,
                    ),
                },
            ],
            max_tokens=2000,
            temperature=0.3,
        )
        content1 = (r1.choices[0].message.content or "").strip()
        content1 = content1[content1.find("{") : content1.rfind("}") + 1]
        fields = json.loads(content1)
    except Exception:
        fields = {}

    # ②b. LLM Call 2: PAPERS
    papers = []
    try:
        r2 = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYS_PAPERS},
                {
                    "role": "user",
                    "content": _PROMPT_PAPERS.format(
                        name=name, text=all_content[:6000]
                    ),
                },
            ],
            max_tokens=4000,
            temperature=0.1,
        )
        content2 = (r2.choices[0].message.content or "").strip()
        content2 = content2[content2.find("{") : content2.rfind("}") + 1]
        papers = json.loads(content2).get("papers", [])
    except Exception:
        pass

    return {
        "status": "ok",
        "fields": fields,
        "papers": papers,
        "n_sources": len(gathered),
    }


# ── Write ────────────────────────────────────────────────────────────────────


def _write_results(
    conn: psycopg.Connection,
    pid: str,
    page_id: str | None,
    run_id: str,
    result: dict[str, Any],
) -> tuple[int, int]:
    """Write fields + papers. Returns (facts_written, papers_linked)."""
    fields = result.get("fields") or {}
    papers = result.get("papers") or []
    facts_w = 0
    papers_w = 0

    with conn.cursor() as c:
        # profile_summary
        summary = fields.get("profile_summary")
        if summary and len(summary) > 50:
            c.execute(
                "UPDATE professor SET profile_summary=%s WHERE professor_id=%s AND length(coalesce(profile_summary,''))<%s",
                (summary[:800], pid, len(summary)),
            )
            if c.rowcount:
                facts_w += 1

        # structured facts
        fact_map = [
            ("research_topic", fields.get("research_directions") or []),
            (
                "academic_position",
                [fields.get("academic_position")]
                if fields.get("academic_position")
                else [],
            ),
            (
                "education",
                [
                    json.dumps(e, ensure_ascii=False)
                    for e in (fields.get("education") or [])
                ],
            ),
            (
                "work_experience",
                [
                    json.dumps(w, ensure_ascii=False)
                    for w in (fields.get("work_experience") or [])
                ],
            ),
            ("award", fields.get("awards") or []),
            (
                "contact",
                [fields.get("contact_email")] if fields.get("contact_email") else [],
            ),
            ("homepage", [summary[:500]] if summary and len(summary) > 50 else []),
        ]
        # research_projects → store as 'homepage' evidence or a new fact_type
        for proj in fields.get("research_projects") or []:
            fact_map.append(
                ("homepage", [f"科研项目: {json.dumps(proj, ensure_ascii=False)}"])
            )

        for fact_type, values in fact_map:
            for val in values:
                if not val or (isinstance(val, str) and len(val) < 2):
                    continue
                c.execute(
                    "INSERT INTO professor_fact(professor_id,fact_type,value_raw,source_page_id,evidence_span,confidence,status,run_id)"
                    " SELECT %s,%s,%s,primary_official_profile_page_id,'unified_crawl',0.85,'active',%s"
                    " FROM professor WHERE professor_id=%s ON CONFLICT DO NOTHING",
                    (pid, fact_type, str(val)[:500], run_id, pid),
                )
                facts_w += c.rowcount

        # papers
        for p in papers:
            title = (p.get("title") or "").strip()
            if not title or len(title) < 5:
                continue
            paper_id = str(uuid.uuid4())
            c.execute(
                "INSERT INTO paper(paper_id,title_clean,year,authors_display,canonical_source,first_seen_at,updated_at,quality_status,identity_status,run_id)"
                " VALUES(%s,%s,%s,%s,'prof_page_only',now(),now(),'needs_enrichment','unverified',%s)",
                (
                    paper_id,
                    title[:300],
                    p.get("year", ""),
                    (p.get("authors", "") or "")[:200],
                    run_id,
                ),
            )
            c.execute(
                "INSERT INTO professor_paper_link(professor_id,paper_id,link_status,evidence_source_type,match_reason,author_name_match_score,is_officially_listed,run_id)"
                " VALUES(%s,%s,'candidate','personal_homepage','unified_crawl_llm',0,true,%s) ON CONFLICT DO NOTHING",
                (pid, paper_id, run_id),
            )
            papers_w += 1

    conn.commit()
    return facts_w, papers_w


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    p = argparse.ArgumentParser(description="UPC: Unified Professor Crawl.")
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    p.add_argument("--institution", required=True)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--llm-profile", default="gemma4")
    p.add_argument("--sleep", type=float, default=3.0)
    p.add_argument(
        "--force-browser",
        action="store_true",
        help="always render (JS-rendered sites like HIT).",
    )
    p.add_argument(
        "--use-cdp",
        action="store_true",
        help="CDPChromeRenderer for 瑞数 (run under xvfb-run).",
    )
    p.add_argument(
        "--no-web-search",
        action="store_true",
        help="skip Serper web search (homepage only).",
    )
    p.add_argument(
        "--all", action="store_true", help="process all profs (no gap-skip)."
    )
    args = p.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL or --dsn required")
    if "+psycopg" in args.dsn:
        args.dsn = args.dsn.replace("postgresql+psycopg://", "postgresql://")

    settings = resolve_professor_llm_settings(args.llm_profile)
    load_dotenv(override=True)
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings.get("local_llm_api_key") or "EMPTY",
        timeout=120.0,
    )
    model = settings["local_llm_model"]
    serper = WebSearchProvider()
    cdp_renderer = CDPChromeRenderer() if args.use_cdp else None
    run_id = str(uuid.uuid4())

    conn = psycopg.connect(args.dsn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pipeline_run(run_id,run_kind,run_scope,started_at,status,created_at,triggered_by)"
            " VALUES(%s,%s,%s,now(),'running',now(),'unified_crawl')",
            (
                run_id,
                RUN_KIND,
                Json(
                    {
                        "purpose": "unified_professor_crawl",
                        "institution": args.institution,
                    }
                ),
            ),
        )
        conn.commit()
        gap_skip = (
            ""
            if args.all
            else (
                " AND NOT (EXISTS(SELECT 1 FROM professor_fact f WHERE f.professor_id=p.professor_id"
                " AND f.fact_type='academic_position' AND f.status='active')"
                " AND EXISTS(SELECT 1 FROM professor_fact g WHERE g.professor_id=p.professor_id"
                " AND g.fact_type='education' AND g.status='active')"
                " AND EXISTS(SELECT 1 FROM professor_paper_link l WHERE l.professor_id=p.professor_id))"
            )
        )
        cur.execute(
            "SELECT p.professor_id, p.canonical_name, pa.department, sp.url, sp.page_id,"
            " (SELECT f.value_raw FROM professor_fact f WHERE f.professor_id=p.professor_id AND f.fact_type='contact' AND f.status='active' LIMIT 1)"
            " FROM professor p"
            " JOIN professor_affiliation pa ON pa.professor_id=p.professor_id AND pa.is_primary AND pa.institution=%s"
            " LEFT JOIN source_page sp ON sp.page_id=p.primary_official_profile_page_id"
            f" WHERE sp.url IS NOT NULL{gap_skip}"
            " ORDER BY p.professor_id LIMIT %s OFFSET %s",
            (args.institution, args.limit, args.offset),
        )
        profs = cur.fetchall()

    print(
        f"run_id={run_id} | institution={args.institution} | {len(profs)} profs | model={model}"
    )
    total_facts = total_papers = ok = 0
    for pid, name, dept, url, page_id, email in profs:
        try:
            result = crawl_one_professor(
                pid,
                name,
                args.institution,
                dept,
                email,
                url,
                page_id,
                client,
                model,
                serper,
                cdp_renderer,
                args.force_browser,
                web_search=not args.no_web_search,
            )
            if result["status"] == "no_content":
                print(f"  {name}: no content", flush=True)
                time.sleep(args.sleep)
                continue
            fw, pw = _write_results(conn, pid, page_id, run_id, result)
            total_facts += fw
            total_papers += pw
            ok += 1
            print(
                f"  {name}: {fw} facts + {pw} papers | {result.get('n_sources', 0)} sources | summary={len((result.get('fields') or {}).get('profile_summary', ''))}c",
                flush=True,
            )
        except Exception as exc:
            conn.rollback()
            print(f"  {name}: ERR {type(exc).__name__}: {str(exc)[:100]}", flush=True)
        time.sleep(args.sleep)

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE pipeline_run SET status='succeeded',finished_at=now(),items_processed=%s WHERE run_id=%s",
            (ok, run_id),
        )
    conn.commit()
    if cdp_renderer:
        cdp_renderer.close()
    conn.close()
    print(
        f"DONE: {ok}/{len(profs)} profs | {total_facts} facts + {total_papers} papers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
