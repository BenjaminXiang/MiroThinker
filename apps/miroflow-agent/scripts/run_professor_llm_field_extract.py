#!/usr/bin/env python
"""L2 professor field-completion: LLM structured-field extraction + bilingual (EN→ZH) translation.

Reads a professor's homepage (static/browser fetch), asks the LLM to extract
research_directions / education / academic_position / work_experience / contact_email, translating
English structured facts to `English (中文)` while preserving the original. The optional
profile_summary is a canonical 200-300 char Chinese bio before it can update professor.profile_summary.
Writes professor_fact rows with source provenance (`llm_extraction` + run_id).

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
from decimal import Decimal

import psycopg
from dotenv import load_dotenv
from openai import OpenAI
from psycopg.types.json import Json

from src.data_agents.professor.canonical_writer import _upsert_fact
from src.data_agents.browser_fetch import (
    CDPChromeRenderer,
    fetch_html_with_browser_fallback,
    render_html_with_browser,
)
from src.data_agents.professor.llm_profiles import resolve_professor_llm_settings
from src.data_agents.professor.profile_summary_contract import (
    PROFILE_SUMMARY_PROMPT_CONTRACT,
    is_valid_profile_summary,
)

RUN_KIND = "backfill_real"  # must be a valid pipeline_run.run_kind enum value
SOURCE = "llm_extraction"

_SYS = "You extract structured fields from a professor's homepage. Return ONLY minified JSON, no prose."
_PROMPT = """Homepage text (may be English):
{text}

Extract these fields. For English structured fact content, append a Chinese translation in parentheses like "English (中文)"; always keep the original. Use null or [] for fields not present.
For profile_summary only, follow this canonical summary contract: {profile_summary_contract}
Return JSON ONLY with keys:
- research_directions: list of strings (bilingual)
- education: list of {{"school","degree","field"}} (bilingual school/field)
- academic_position: string or null (bilingual)
- work_experience: list of {{"organization","role"}} (bilingual)
- contact_email: string or null
- profile_summary: string or null (200-300 char 中文 canonical biography)
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
    profile_summary = str(data.get("profile_summary") or "").strip()
    if is_valid_profile_summary(profile_summary):
        facts.append(("homepage", profile_summary))
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
    p.add_argument(
        "--model",
        default=None,
        help="override the LLM model (e.g. deepseek-v4-flash) if the profile is hijacked by an env var like DEEPSEEK_MODEL.",
    )
    p.add_argument("--sleep", type=float, default=3.0)
    p.add_argument("--max-text", type=int, default=6000)
    p.add_argument(
        "--all",
        action="store_true",
        help="process all profs; default skips profs already having both academic_position and education (no wasted work).",
    )
    p.add_argument(
        "--use-cdp",
        action="store_true",
        help="instantiate a CDPChromeRenderer for 瑞数/Rishu JS-challenge sites (csse.szu etc.); run under xvfb-run.",
    )
    p.add_argument(
        "--force-browser",
        action="store_true",
        help="skip static fetch; always render via headless browser (for JS-rendered sites like HIT).",
    )
    args = p.parse_args()
    # Load .env only for DeepSeek profiles (needs DEEPSEEK_API_KEY). For gemma4/etc.
    # skip it: .env's DEEPSEEK_MODEL/LOCAL_LLM_MODEL would hijack the profile model.
    if "deepseek" in args.llm_profile.lower():
        load_dotenv(override=True)
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
    model = args.model or settings["local_llm_model"]
    run_id = str(uuid.uuid4())
    cdp_renderer = CDPChromeRenderer() if args.use_cdp else None

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
        gap_skip = (
            ""
            if args.all
            else (
                " AND NOT (EXISTS(SELECT 1 FROM professor_fact f WHERE f.professor_id=p.professor_id"
                " AND f.fact_type='academic_position' AND f.status='active')"
                " AND EXISTS(SELECT 1 FROM professor_fact g WHERE g.professor_id=p.professor_id"
                " AND g.fact_type='education' AND g.status='active'))"
            )
        )
        cur.execute(
            "SELECT p.professor_id, sp.page_id, sp.url FROM professor p"
            " JOIN professor_affiliation pa ON pa.professor_id=p.professor_id AND pa.is_primary AND pa.institution=%s"
            " JOIN source_page sp ON sp.page_id=p.primary_official_profile_page_id"
            " WHERE sp.url IS NOT NULL"
            + gap_skip
            + " ORDER BY p.professor_id LIMIT %s OFFSET %s",
            (args.institution, args.limit, args.offset),
        )
        profs = cur.fetchall()

    print(
        f"run_id={run_id} | institution={args.institution} | {len(profs)} profs | model={model}"
    )
    total_in = total_out = grand = 0
    for pid, page_id, url in profs:
        try:
            if args.force_browser:
                html = render_html_with_browser(url, timeout=90.0)
            else:
                html, _method = fetch_html_with_browser_fallback(
                    url, cdp_renderer=cdp_renderer
                )
            text = _to_text(html)[: args.max_text]
            if len(text) < 60:
                print(f"  {url}: skip (page too short)")
                continue
            create_kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": _SYS},
                    {
                        "role": "user",
                        "content": _PROMPT.format(
                            text=text,
                            profile_summary_contract=PROFILE_SUMMARY_PROMPT_CONTRACT,
                        ),
                    },
                ],
                "max_tokens": 1200,
                "temperature": 0.2,
            }
            # DeepSeek V4 defaults to thinking mode (consumes all tokens on reasoning,
            # empty output). Disable it for this extraction task.
            if "deepseek" in args.llm_profile.lower():
                create_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            r = client.chat.completions.create(**create_kwargs)
            total_in += r.usage.prompt_tokens or 0
            total_out += r.usage.completion_tokens or 0
            content = (r.choices[0].message.content or "").strip()
            content = content[content.find("{") : content.rfind("}") + 1]
            data = json.loads(content)
            facts = _facts_from(data)
            for fact_type, value in facts:
                _upsert_fact(
                    conn,
                    professor_id=pid,
                    fact_type=fact_type,
                    value_raw=value,
                    source_page_id=page_id,
                    evidence_span=text[:400],
                    confidence=Decimal("0.8"),
                    run_id=run_id,
                )
            conn.commit()
            # Also update the professor.profile_summary column (the admin-visible bio)
            profile_summary = str(data.get("profile_summary") or "").strip()
            if is_valid_profile_summary(profile_summary):
                with conn.cursor() as c:
                    c.execute(
                        "UPDATE professor SET profile_summary=%s WHERE professor_id=%s",
                        (profile_summary, pid),
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
    if cdp_renderer is not None:
        cdp_renderer.close()
    n = max(len(profs), 1)
    print(
        f"DONE: {grand} facts | tokens in/out={total_in}/{total_out} | per-prof in={total_in // n} out={total_out // n}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
