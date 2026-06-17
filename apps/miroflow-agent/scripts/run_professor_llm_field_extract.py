#!/usr/bin/env python
"""L2 professor field-completion: LLM structured-field extraction + bilingual (EN→ZH) translation.

Reads a professor's homepage (static fetch via fetch_homepage_html), asks the LLM to extract
research_directions / education / academic_position / work_experience / contact_email /
profile_summary, translating any English content to bilingual `English (中文)` (original
preserved), and writes professor_fact rows with source provenance (`llm_extraction` + run_id).

This is the template-agnostic Layer 2 of the professor-profile-field-completion pipeline
(see openspec/changes/professor-profile-field-completion-pipeline). Use for schools whose
homepage content the SIGS-only static extractor (L1) misses — especially English/bilingual
homepages (CUHK-SZ, SUSTech, ...).

Env: localhost DB needs the 6 proxy vars UNSET; the LLM + homepage fetch are external and
NEED the proxy env (the OpenAI/httpx client reads ALL_PROXY/HTTPS_PROXY via socksio).
Requires socksio (uv add socksio) for SOCKS-proxy LLM access.
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
from openai import OpenAI
from psycopg.types.json import Json

from src.data_agents.paper.homepage_http import fetch_homepage_html
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings

RUN_KIND = "backfill_real"  # must be a valid pipeline_run.run_kind enum value
SOURCE = "llm_extraction"

_SYS = "You extract structured fields from a professor's homepage. Return ONLY minified JSON, no prose."
_PROMPT = """Homepage text (may be English):
{text}

Extract these fields. For ANY English content, append a Chinese translation in parentheses like "English (中文)"; always keep the original. Use null or [] for fields not present.
Return JSON ONLY with keys:
- research_directions: list of strings (bilingual)
- education: list of {{"school","degree","field"}} (bilingual school/field)
- academic_position: string or null (bilingual)
- work_experience: list of {{"organization","role"}} (bilingual)
- contact_email: string or null
- profile_summary: string or null (bilingual bio, <=300 chars)
"""


def _to_text(html: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html_mod.unescape(t)).strip()


def _facts_from(data: dict[str, Any]) -> list[tuple[str, str]]:
    facts: list[tuple[str, str]] = []
    for d in data.get("research_directions") or []:
        facts.append(("research_topic", str(d)))
    if data.get("academic_position"):
        facts.append(("academic_position", str(data["academic_position"])))
    for e in data.get("education") or []:
        facts.append(("education", json.dumps(e, ensure_ascii=False)))
    for w in data.get("work_experience") or []:
        facts.append(("work_experience", json.dumps(w, ensure_ascii=False)))
    if data.get("contact_email"):
        facts.append(("contact", str(data["contact_email"])))
    if data.get("profile_summary"):
        facts.append(("homepage", str(data["profile_summary"])[:500]))
    return facts


def main() -> int:
    p = argparse.ArgumentParser(
        description="L2 LLM professor field extraction + bilingual translation."
    )
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    p.add_argument(
        "--institution",
        required=True,
        help="professor_affiliation.institution to target.",
    )
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--llm-profile", default="gemma4")
    p.add_argument("--sleep", type=float, default=3.0)
    p.add_argument("--max-text", type=int, default=6000)
    args = p.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL or --dsn required")
    if "+psycopg" in args.dsn:
        args.dsn = args.dsn.replace("postgresql+psycopg://", "postgresql://")

    settings = resolve_professor_llm_settings(args.llm_profile)
    client = OpenAI(
        base_url=settings["local_llm_base_url"],
        api_key=settings.get("local_llm_api_key") or "EMPTY",
        timeout=90.0,
    )
    model = settings["local_llm_model"]
    run_id = str(uuid.uuid4())

    conn = psycopg.connect(args.dsn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pipeline_run(run_id,run_kind,run_scope,started_at,status,created_at,triggered_by)"
            " VALUES(%s,%s,%s,now(),'running',now(),'llm_field_extract')",
            (
                run_id,
                RUN_KIND,
                Json(
                    {"purpose": "l2_field_completion", "institution": args.institution}
                ),
            ),
        )
        conn.commit()
        cur.execute(
            "SELECT p.professor_id, sp.page_id, sp.url FROM professor p"
            " JOIN professor_affiliation pa ON pa.professor_id=p.professor_id AND pa.is_primary AND pa.institution=%s"
            " JOIN source_page sp ON sp.page_id=p.primary_official_profile_page_id"
            " WHERE sp.url IS NOT NULL ORDER BY p.professor_id LIMIT %s OFFSET %s",
            (args.institution, args.limit, args.offset),
        )
        profs = cur.fetchall()

    print(
        f"run_id={run_id} | institution={args.institution} | {len(profs)} profs | model={model}"
    )
    total_in = total_out = grand = 0
    for pid, page_id, url in profs:
        try:
            text = _to_text(fetch_homepage_html(url))[: args.max_text]
            if len(text) < 60:
                print(f"  {url}: skip (page too short)")
                continue
            r = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYS},
                    {"role": "user", "content": _PROMPT.format(text=text)},
                ],
                max_tokens=1200,
                temperature=0.2,
            )
            total_in += r.usage.prompt_tokens or 0
            total_out += r.usage.completion_tokens or 0
            content = (r.choices[0].message.content or "").strip()
            content = content[content.find("{") : content.rfind("}") + 1]
            data = json.loads(content)
            facts = _facts_from(data)
            with conn.cursor() as c:
                for fact_type, value in facts:
                    c.execute(
                        "INSERT INTO professor_fact(professor_id,fact_type,value_raw,source_page_id,"
                        "evidence_span,confidence,status,run_id) VALUES(%s,%s,%s,%s,%s,0.8,'active',%s)"
                        " ON CONFLICT DO NOTHING",
                        (pid, fact_type, value, page_id, text[:400], run_id),
                    )
            conn.commit()
            grand += len(facts)
            print(
                f"  {url}: +{len(facts)} facts | email={data.get('contact_email')!r}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - per-prof resilience
            conn.rollback()
            print(f"  {url}: ERR {type(exc).__name__}: {str(exc)[:120]}", flush=True)
        time.sleep(args.sleep)

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE pipeline_run SET status='succeeded',finished_at=now(),items_processed=%s WHERE run_id=%s",
            (grand, run_id),
        )
    conn.commit()
    conn.close()
    n = max(len(profs), 1)
    print(
        f"DONE: {grand} facts | tokens in/out={total_in}/{total_out} | per-prof in={total_in // n} out={total_out // n}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
