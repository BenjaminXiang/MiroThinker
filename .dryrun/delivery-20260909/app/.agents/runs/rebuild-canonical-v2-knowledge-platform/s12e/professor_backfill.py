#!/usr/bin/env python3
"""s12e professor backfill batch generator (Task 7 Step 1 of 2026-07-31-llm-wide-recall).

Generates the append-only landing batch ``s12e-professor-backfill-v1`` for the
audit-prioritized professors (Top-14 by citation_count + 金欣 + 王学谦,
hard cap 20) in the s12c r8 candidate database.

Workflow:
  1. ``collect``  : web search (Bocha, Serper fallback) + direct fetch of the
     known homepage per person; candidate field values are extracted from
     official institution pages and stored in professor_backfill_research.json
     with source url / observed_at / evidence quote.
  2. default      : dry-run. Loads the (reviewed) research JSON, builds the
     batch records, and prints exactly what would be inserted. No DB writes.
  3. ``--apply``  : append-only INSERTs into landing.evidence_artifact /
     parser_run / source_record / ingest_run, mirroring the canonical
     EvidenceLandingService id/fingerprint derivations (verified against
     batch s12c-r7-professor-company-roles-v1).
  4. ``--verify`` : read-only SELECT proving the batch landed.

Hard rules honored: append-only (INSERT only, never UPDATE/DELETE), no live
server contact, every value carries a source assertion, hard cap 20 people.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
import charset_normalizer

HERE = Path(__file__).resolve().parent
RESEARCH_PATH = HERE / "professor_backfill_research.json"
BATCH_PATH = HERE / "professor_backfill_batch.jsonl"
STAGING_DIR = Path("/var/tmp/mirothinker-canonical-v2-s12e/staging")

SOURCE_BATCH_ID = "s12e-professor-backfill-v1"
SOURCE_KIND = "historical_jsonl"
PARSER_NAME = "historical_jsonl"
PARSER_VERSION = "v1"
SCHEMA_VERSION = "historical-jsonl-record-v1"
RUN_ID = "landing:s12e-professor-backfill-20260801:staging/professor_backfill_s12e_v1.jsonl"

DEFAULT_DB_URL = (
    "postgresql://miroflow@127.0.0.1:55458/miroflow_candidate_s12c_20260726_r8"
)

BOCHA_URL = "https://api.bochaai.com/v1/web-search"
SERPER_URL = "https://google.serper.dev/search"
BOCHA_KEY_PATH = Path("/home/longxiang/MiroThinker/.bocha_api_key")
SERPER_KEY_PATH = Path("/home/longxiang/MiroThinker/.serper_api_key")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Priority queue (from s12e/professor-audit.md §1, Top-14 by citation_count
# + 金欣 + 王学谦; missing fields read from landing payload core_facts).
# ---------------------------------------------------------------------------

PEOPLE: tuple[dict, ...] = (
    {
        "professor_id": "PROF-F7D43B28799E",
        "name": "周垚",
        "institution": "南方科技大学",
        "homepage": "https://www.sustech.edu.cn/zh/faculties/zhouyao.html",
        "missing_fields": ["department"],
        "citation_count": 14746,
    },
    {
        "professor_id": "PROF-814BDB064B97",
        "name": "唐仙",
        "institution": "清华大学深圳国际研究生院",
        "homepage": "http://www.sigs.tsinghua.edu.cn/tx/main.htm",
        "missing_fields": ["department"],
        "citation_count": 5569,
    },
    {
        "professor_id": "PROF-F65FAFD07ECB",
        "name": "姚勇",
        "institution": "哈尔滨工业大学（深圳）",
        "homepage": "https://homepage.hit.edu.cn/yaoyong",
        "missing_fields": ["email", "title"],
        "citation_count": 4242,
    },
    {
        "professor_id": "PROF-A4A3D3B0C942",
        "name": "Parvej Alam",
        "institution": "香港中文大学（深圳）",
        "homepage": "https://sse.cuhk.edu.cn/faculty/parvejalam",
        "missing_fields": ["email"],
        "citation_count": 4236,
    },
    {
        "professor_id": "PROF-1EC0B2448E6D",
        "name": "黄建华",
        "institution": "香港中文大学（深圳）",
        "homepage": "https://sai.cuhk.edu.cn/teacher/108",
        "missing_fields": ["email"],
        "citation_count": 3201,
    },
    {
        "professor_id": "PROF-8BCB9CE81A01",
        "name": "田佳峻",
        "institution": "哈尔滨工业大学（深圳）",
        "homepage": "https://homepage.hit.edu.cn/tianjiajun",
        "missing_fields": ["email", "title"],
        "citation_count": 2917,
    },
    {
        "professor_id": "PROF-19535075873E",
        "name": "张灿荣",
        "institution": "清华大学深圳国际研究生院",
        "homepage": "http://www.sigs.tsinghua.edu.cn/zcr/main.htm",
        "missing_fields": ["department"],
        "citation_count": 1913,
    },
    {
        "professor_id": "PROF-77D468AF93F5",
        "name": "孔庆磊",
        "institution": "哈尔滨工业大学（深圳）",
        "homepage": "https://homepage.hit.edu.cn/kongqinglei",
        "missing_fields": ["email", "title"],
        "citation_count": 1245,
    },
    {
        "professor_id": "PROF-70F168547DAE",
        "name": "高林",
        "institution": "哈尔滨工业大学（深圳）",
        "homepage": "https://homepage.hit.edu.cn/gaolin",
        "missing_fields": ["email", "title"],
        "citation_count": 1205,
    },
    {
        "professor_id": "PROF-FF636C8A09C3",
        "name": "冯建设",
        "institution": "中山大学（深圳）",
        "homepage": "https://www.researchgate.net/profile/Jianshe-Feng",
        "missing_fields": ["email"],
        "citation_count": 1153,
    },
    {
        "professor_id": "PROF-A732D59BBDB0",
        "name": "徐小川",
        "institution": "哈尔滨工业大学（深圳）",
        "homepage": "https://homepage.hit.edu.cn/xuxiaochuan",
        "missing_fields": ["email", "title"],
        "citation_count": 947,
    },
    {
        "professor_id": "PROF-C91EBBAC3D23",
        "name": "王凯旭",
        "institution": "哈尔滨工业大学（深圳）",
        "homepage": "https://homepage.hit.edu.cn/WangKaiXu",
        "missing_fields": ["email", "title"],
        "citation_count": 909,
    },
    {
        "professor_id": "PROF-ABBDE6D18E0E",
        "name": "吴日",
        "institution": "南方科技大学",
        "homepage": "http://faculty.sustech.edu.cn/wuri",
        "missing_fields": ["department", "title"],
        "citation_count": 845,
    },
    {
        "professor_id": "PROF-E0221A651BF9",
        "name": "朱时裴",
        "institution": "哈尔滨工业大学（深圳）",
        "homepage": "https://homepage.hit.edu.cn/zhushipei",
        "missing_fields": ["email"],
        "citation_count": 466,
    },
    {
        "professor_id": "PROF-013E2C1D4602",
        "name": "金欣",
        "institution": "清华大学深圳国际研究生院",
        "homepage": "http://www.sigs.tsinghua.edu.cn/jx/main.htm",
        "missing_fields": ["department"],
        "citation_count": None,
    },
    {
        "professor_id": "PROF-132D3CC74120",
        "name": "王学谦",
        "institution": "清华大学深圳国际研究生院",
        "homepage": "http://www.sigs.tsinghua.edu.cn/wxq/main.htm",
        "missing_fields": ["department"],
        "citation_count": 1,
    },
)

assert len(PEOPLE) <= 20, "hard cap 20 people"

# Institution short forms for search queries, and official domains whose pages
# are treated as authoritative sources.
INSTITUTION_SEARCH_NAME = {
    "南方科技大学": "南方科技大学",
    "清华大学深圳国际研究生院": "清华大学深圳国际研究生院",
    "哈尔滨工业大学（深圳）": "哈尔滨工业大学 深圳",
    "香港中文大学（深圳）": "香港中文大学深圳",
    "中山大学（深圳）": "中山大学 深圳",
}

OFFICIAL_DOMAINS = {
    "南方科技大学": ("sustech.edu.cn",),
    "清华大学深圳国际研究生院": ("sigs.tsinghua.edu.cn", "tsinghua.edu.cn"),
    "哈尔滨工业大学（深圳）": ("hit.edu.cn", "hitsz.edu.cn"),
    "香港中文大学（深圳）": ("cuhk.edu.cn",),
    "中山大学（深圳）": ("sysu.edu.cn",),
}

TITLE_WORDS = (
    "讲席教授",
    "长聘教授",
    "长聘副教授",
    "特聘教授",
    "客座教授",
    "客座助理教授",
    "教授",
    "副教授",
    "助理教授",
    "研究助理教授",
    "研究员",
    "副研究员",
    "助理研究员",
    "讲师",
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_TOKEN_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9._-]+")
# reversed anti-scrape emails, e.g. moc.liamg@88gnat.nilnuhs, nc.ude.tih@...
REVERSED_DOMAIN_HINTS = ("moc.", "nc.", "gro.", "ten.", "ude.", "ng.")

BACKFILL_FIELD_ORDER = (
    "department",
    "title",
    "email",
    "homepage",
    "research_directions",
    "canonical_name_en",
    "aliases",
)

# ---------------------------------------------------------------------------
# Reviewed backfill values (Task 7c manual review, 2026-08-01).
# Each entry: field, value, source_url, anchor (must appear in the fetched
# page text; the evidence quote is built around it), method.
# The --review step re-fetches every source_url live, asserts the anchor is
# present, and writes professor_backfill_research.json "fields".
# ---------------------------------------------------------------------------

SIGS_TEACHER_API = (
    "https://www.sigs.tsinghua.edu.cn/_wp3services/generalQuery?queryObj=teacherHome"
)
CIST_ICE_LIST = "http://cist.hitsz.edu.cn/szdw1/jcdlkxygcxk.htm"  # 集成电路科学与工程学科
CIST_ICT_LIST = "http://cist.hitsz.edu.cn/szdw1/xxytxgcxk.htm"  # 信息与通信工程学科

REVIEWED_FIELDS: dict[str, tuple[dict, ...]] = {
    # 周垚: identity anchor is the CHER 周垚 (email+homepage match the record);
    # metrics/research directions in the record belong to a different person
    # (formal methods) - contamination flagged in the report.
    "PROF-F7D43B28799E": (
        {
            "field": "department",
            "value": "高等教育研究中心",
            "source_url": "https://cher.sustech.edu.cn/faculty/detail/id/277.html",
            "anchor": "南方科技大学高等教育研究中心研究助理教授",
            "method": "official_page",
        },
    ),
    # 唐仙 (SIGS): 数据与信息研究院 per official teacher-search backend.
    "PROF-814BDB064B97": (
        {
            "field": "department",
            "value": "数据与信息研究院",
            "source_url": SIGS_TEACHER_API,
            "anchor": "唐仙",
            "method": "official_api",
        },
    ),
    "PROF-F65FAFD07ECB": (  # 姚勇
        {
            "field": "email",
            "value": "yaoyong@hit.edu.cn",
            "source_url": "https://homepage.hit.edu.cn/yaoyong",
            "anchor": "nc.ude.tih@gnoyoay",
            "method": "official_page_email_deobfuscated",
        },
        {
            "field": "title",
            "value": "教授",
            "source_url": CIST_ICE_LIST,
            "anchor": "姚勇",
            "method": "official_page",
        },
    ),
    # Parvej Alam (CUHK-SZ): email from his personal academic homepage which is
    # linked ("个人网站") from the official SSE faculty page.
    "PROF-A4A3D3B0C942": (
        {
            "field": "email",
            "value": "alamparvej@cuhk.edu.cn",
            "source_url": "https://alam-parvej.github.io/",
            "anchor": "alamparvej@cuhk.edu.cn",
            "method": "personal_homepage_linked_from_official",
        },
    ),
    "PROF-1EC0B2448E6D": (  # 黄建华
        {
            "field": "email",
            "value": "jhuang@cuhk.edu.cn",
            "source_url": "https://sai.cuhk.edu.cn/teacher/108",
            "anchor": "jhuang@cuhk.edu.cn",
            "method": "official_page",
        },
    ),
    "PROF-8BCB9CE81A01": (  # 田佳峻
        {
            "field": "email",
            "value": "tianjiajun@hit.edu.cn",
            "source_url": "https://homepage.hit.edu.cn/tianjiajun",
            "anchor": "nc.ude.tih@nujaijnait",
            "method": "official_page_email_deobfuscated",
        },
        {
            "field": "title",
            "value": "教授",
            "source_url": CIST_ICE_LIST,
            "anchor": "田佳峻",
            "method": "official_page",
        },
    ),
    "PROF-19535075873E": (  # 张灿荣
        {
            "field": "department",
            "value": "数据与信息研究院",
            "source_url": SIGS_TEACHER_API,
            "anchor": "张灿荣",
            "method": "official_api",
        },
    ),
    "PROF-77D468AF93F5": (  # 孔庆磊: title left as placeholder (no source found)
        {
            "field": "email",
            "value": "kongqinglei@hit.edu.cn",
            "source_url": "https://homepage.hit.edu.cn/kongqinglei",
            "anchor": "nc.ude.tih@ielgniqgnok",
            "method": "official_page_email_deobfuscated",
        },
    ),
    "PROF-70F168547DAE": (  # 高林
        {
            "field": "email",
            "value": "gaol@hit.edu.cn",
            "source_url": "https://homepage.hit.edu.cn/gaolin",
            "anchor": "nc.ude.tih@loag",
            "method": "official_page_email_deobfuscated",
        },
        {
            "field": "title",
            "value": "教授",
            "source_url": CIST_ICT_LIST,
            "anchor": "高林",
            "method": "official_page",
        },
    ),
    "PROF-FF636C8A09C3": (  # 冯建设
        {
            "field": "email",
            "value": "fengjsh7@mail.sysu.edu.cn",
            "source_url": "https://am.sysu.edu.cn/teacher",
            "anchor": "fengjsh7@mail.sysu.edu.cn",
            "method": "official_page",
        },
    ),
    "PROF-A732D59BBDB0": (  # 徐小川
        {
            "field": "email",
            "value": "xuxiaochuan@hit.edu.cn",
            "source_url": "https://homepage.hit.edu.cn/xuxiaochuan",
            "anchor": "nc.ude.tih@nauhcoaixux",
            "method": "official_page_email_deobfuscated",
        },
        {
            "field": "title",
            "value": "教授",
            "source_url": CIST_ICE_LIST,
            "anchor": "徐小川",
            "method": "official_page",
        },
    ),
    # 王凯旭: email left as placeholder (no source; faculty page 未开通).
    "PROF-C91EBBAC3D23": (
        {
            "field": "title",
            "value": "副教授",
            "source_url": CIST_ICT_LIST,
            "anchor": "王凯旭",
            "method": "official_page",
        },
    ),
    "PROF-ABBDE6D18E0E": (  # 吴日
        {
            "field": "department",
            "value": "理学院化学系（与先进光源科学中心双聘）",
            "source_url": "https://www.sustech.edu.cn/zh/faculties/riwu.html",
            "anchor": "南方科技大学理学院先进光源科学中心与化学系双聘副教授",
            "method": "official_page",
        },
        {
            "field": "title",
            "value": "副教授",
            "source_url": "https://www.sustech.edu.cn/zh/faculties/riwu.html",
            "anchor": "吴日\n副教授",
            "method": "official_page",
        },
    ),
    "PROF-E0221A651BF9": (  # 朱时裴
        {
            "field": "email",
            "value": "zhushipei@hit.edu.cn",
            "source_url": "https://homepage.hit.edu.cn/zhushipei",
            "anchor": "nc.ude.tih@iepihsuhz",
            "method": "official_page_email_deobfuscated",
        },
    ),
    "PROF-013E2C1D4602": (  # 金欣
        {
            "field": "department",
            "value": "数据与信息研究院",
            "source_url": SIGS_TEACHER_API,
            "anchor": "金欣",
            "method": "official_api",
        },
    ),
    "PROF-132D3CC74120": (  # 王学谦
        {
            "field": "department",
            "value": "数据与信息研究院",
            "source_url": "https://www.sigs.tsinghua.edu.cn/2026/0714/c7687a292200/page.htm",
            "anchor": "数据与信息研究院党总支书记",
            "method": "official_page",
        },
    ),
}


# ---------------------------------------------------------------------------
# ID / fingerprint derivations (mirror evidence_landing.py exactly; verified
# against landing batch s12c-r7-professor-company-roles-v1).
# ---------------------------------------------------------------------------


def _stable_id(prefix: str, *parts: str) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()
    return f"{prefix}:sha256:{hashlib.sha256(encoded).hexdigest()}"


def _record_fingerprint(record_locator: str, payload: dict) -> str:
    draft = {
        "record_locator": record_locator,
        "parse_status": "parsed",
        "payload": payload,
        "errors": [],
    }
    encoded = json.dumps(
        draft, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _request_fingerprint(
    *,
    artifact_id: str,
    content_sha256: str,
    source_batch_id: str,
    observed_at_utc: str,
) -> str:
    payload = {
        "artifact_id": artifact_id,
        "content_sha256": content_sha256,
        "source_batch_id": source_batch_id,
        "observed_at": observed_at_utc,
        "parent_artifact_id": None,
        "parent_content_sha256": None,
        "parser": {
            "parser_name": PARSER_NAME,
            "parser_version": PARSER_VERSION,
            "schema_version": SCHEMA_VERSION,
            "options": {},
        },
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _output_fingerprint(request_fingerprint: str, record_fps: list[str]) -> str:
    payload = {"request_fingerprint": request_fingerprint, "records": record_fps}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


# ---------------------------------------------------------------------------
# collect: web search + fetch + candidate extraction
# ---------------------------------------------------------------------------


def _load_research() -> dict:
    if RESEARCH_PATH.exists():
        return json.loads(RESEARCH_PATH.read_text(encoding="utf-8"))
    return {"people": {}}


def _save_research(data: dict) -> None:
    RESEARCH_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _bocha_search(query: str, count: int = 8) -> list[dict]:
    key = BOCHA_KEY_PATH.read_text().strip()
    resp = httpx.post(
        BOCHA_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"query": query, "count": count},
        timeout=25,
    )
    resp.raise_for_status()
    values = (
        resp.json().get("data", {}).get("webPages", {}).get("value", []) or []
    )
    return [
        {"name": v.get("name"), "url": v.get("url"), "snippet": v.get("snippet")}
        for v in values
    ]


def _serper_search(query: str, count: int = 8) -> list[dict]:
    key = SERPER_KEY_PATH.read_text().strip()
    resp = httpx.post(
        SERPER_URL,
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        json={"q": query, "num": count, "hl": "zh-cn"},
        timeout=25,
    )
    resp.raise_for_status()
    return [
        {"name": v.get("title"), "url": v.get("link"), "snippet": v.get("snippet")}
        for v in resp.json().get("organic", [])[:count]
    ]


def search(query: str) -> tuple[str, list[dict]]:
    try:
        return "bocha", _bocha_search(query)
    except Exception as exc:  # noqa: BLE001 - fallback path
        print(f"  [search] bocha failed ({type(exc).__name__}), trying serper")
        return "serper", _serper_search(query)


def _curl_fetch(url: str) -> tuple[int, str, str]:
    """Fallback fetch via curl (some hosts, e.g. cuhk.edu.cn, reject the
    Python TLS handshake; curl with TLS1.2 + browser headers succeeds)."""
    import subprocess

    proc = subprocess.run(
        [
            "curl",
            "-sSL",
            "-m",
            "30",
            "-o",
            "-",
            "-w",
            "\n%{http_code} %{url_effective}",
            url,
            "-H",
            f"User-Agent: {USER_AGENT}",
            "-H",
            "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "-H",
            "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
            "--tlsv1.2",
            "--compressed",
        ],
        capture_output=True,
        timeout=40,
        check=False,
    )
    body = proc.stdout.decode("utf-8", errors="replace")
    marker = body.rfind("\n")
    meta = body[marker + 1 :].strip().split(" ", 1)
    status = int(meta[0]) if meta and meta[0].isdigit() else 0
    final_url = meta[1] if len(meta) > 1 else url
    return status, final_url, body[:marker]


def fetch_page(url: str) -> dict:
    try:
        try:
            resp = httpx.get(
                url,
                timeout=25,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
            status = resp.status_code
            final_url = str(resp.url)
            raw_html = resp.content
            encoding = resp.encoding
        except httpx.ConnectError:
            status, final_url, html = _curl_fetch(url)
            raw_html = html.encode("utf-8", errors="replace")
            encoding = None
        fetched_at = datetime.now(timezone.utc).isoformat()
        # many legacy university pages are GBK but mislabel; trust detection
        if encoding is None or encoding.lower() in ("iso-8859-1", "ascii"):
            encoding = (
                charset_normalizer.from_bytes(raw_html).best().encoding
                if charset_normalizer.from_bytes(raw_html).best() is not None
                else "utf-8"
            )
        text_html = raw_html.decode(encoding, errors="replace")
        soup = BeautifulSoup(text_html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        title_tag = soup.find("title")
        return {
            "url": url,
            "final_url": final_url,
            "status": status,
            "fetched_at": fetched_at,
            "title": title_tag.get_text(strip=True) if title_tag else None,
            "text": text[:12000],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "url": url,
            "final_url": None,
            "status": None,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "title": None,
            "text": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _quote_around(text: str, needle: str, width: int = 100) -> str | None:
    idx = text.find(needle)
    if idx < 0:
        return None
    start = max(0, idx - width)
    end = min(len(text), idx + len(needle) + width)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def _decode_reversed_email(candidate: str) -> str | None:
    local = candidate.split("@", 1)[0].lower()
    if not local.startswith(REVERSED_DOMAIN_HINTS):
        return None
    reversed_email = candidate[::-1]
    if EMAIL_RE.fullmatch(reversed_email):
        rdomain = reversed_email.split("@", 1)[-1].lower()
        if rdomain.endswith((".com", ".cn", ".net", ".org", ".edu")):
            return reversed_email
    return None


def extract_candidates(person: dict, pages: list[dict]) -> dict:
    """Suggest field values from fetched pages; every suggestion is quoted."""
    name = person["name"]
    suggestions: dict[str, dict] = {}
    official_suffixes = OFFICIAL_DOMAINS[person["institution"]]

    for page in pages:
        if page.get("status") != 200 or not page.get("text"):
            continue
        text = page["text"]
        url = page["final_url"] or page["url"]
        is_official = any(url.endswith(s) or f".{s}" in url for s in official_suffixes)
        if name not in text:
            continue

        # email (incl. reversed anti-scrape strings like nc.ude.tih@gnoyoay)
        if "email" in person["missing_fields"] and "email" not in suggestions:
            for match in EMAIL_TOKEN_RE.finditer(text):
                raw = match.group(0).rstrip(".,;:")
                if EMAIL_RE.fullmatch(raw):
                    value, decoded = raw, None
                else:
                    decoded = _decode_reversed_email(raw)
                    if decoded is None:
                        continue
                    value = decoded
                quote = _quote_around(text, raw)
                if quote:
                    suggestions["email"] = {
                        "value": value,
                        "source_url": url,
                        "observed_at": page["fetched_at"],
                        "evidence_quote": quote,
                        "method": (
                            "official_page_email_deobfuscated"
                            if decoded
                            else ("official_page" if is_official else "web_page")
                        ),
                        "accepted": None,
                    }
                    break

        # title
        if "title" in person["missing_fields"] and "title" not in suggestions:
            for word in TITLE_WORDS:
                idx = text.find(name)
                window = text[max(0, idx - 0): idx + 400] if idx >= 0 else ""
                if word in window:
                    quote = _quote_around(text, word)
                    if quote:
                        suggestions["title"] = {
                            "value": word,
                            "source_url": url,
                            "observed_at": page["fetched_at"],
                            "evidence_quote": quote,
                            "method": "official_page" if is_official else "web_page",
                            "accepted": None,
                        }
                        break

        # department (…研究院 / …学院 / …学部 / …系 near the name)
        if "department" in person["missing_fields"] and "department" not in suggestions:
            for match in re.finditer(
                r"[一-鿿]{2,12}(研究院|学院|学部|学系|系)", text
            ):
                candidate = match.group(0)
                if any(
                    skip in candidate
                    for skip in ("研究生院", "国际研究生院", "研究院研究生院")
                ) and candidate not in ("数据与信息研究院",):
                    continue
                quote = _quote_around(text, candidate)
                if quote and name in quote:
                    suggestions["department"] = {
                        "value": candidate,
                        "source_url": url,
                        "observed_at": page["fetched_at"],
                        "evidence_quote": quote,
                        "method": "official_page" if is_official else "web_page",
                        "accepted": None,
                    }
                    break
    return suggestions


def collect(person_names: list[str] | None, refresh: bool) -> None:
    research = _load_research()
    for person in PEOPLE:
        if person_names and person["name"] not in person_names:
            continue
        pid = person["professor_id"]
        entry = research["people"].get(pid, {})
        if entry.get("pages") and not refresh:
            print(f"[collect] {person['name']}: cached ({len(entry['pages'])} pages)")
            continue
        print(f"[collect] {person['name']} ({person['institution']})")
        inst = INSTITUTION_SEARCH_NAME[person["institution"]]
        engine, results = search(f"{person['name']} {inst} 院系 简介 教授")
        official_suffixes = OFFICIAL_DOMAINS[person["institution"]]
        candidate_urls: list[str] = [person["homepage"]]
        for item in results:
            url = item.get("url") or ""
            if any(s in url for s in official_suffixes) and url not in candidate_urls:
                candidate_urls.append(url)
        for item in results:  # then non-official but plausible pages
            url = item.get("url") or ""
            if url and url not in candidate_urls and len(candidate_urls) < 7:
                candidate_urls.append(url)
        pages = []
        for url in candidate_urls[:7]:
            page = fetch_page(url)
            print(f"  fetch {url} -> {page['status']} ({len(page.get('text') or '')} chars)")
            pages.append(page)
        suggestions = extract_candidates(person, pages)
        research["people"][pid] = {
            "professor_id": pid,
            "name": person["name"],
            "institution": person["institution"],
            "homepage": person["homepage"],
            "missing_fields": person["missing_fields"],
            "search_engine": engine,
            "search_query": f"{person['name']} {inst} 院系 简介 教授",
            "search_results": results,
            "pages": pages,
            "suggestions": suggestions,
            "fields": entry.get("fields", {}),
        }
        _save_research(research)
    print(f"[collect] research saved -> {RESEARCH_PATH}")


# ---------------------------------------------------------------------------
# review: verify REVIEWED_FIELDS live against their sources and accept them
# ---------------------------------------------------------------------------


def _sigs_teacher_rows() -> list[dict]:
    """POST the SIGS 师资队伍 search backend (same call the list page makes)."""
    fields = [
        "title",
        "career",
        "cnUrl",
        "phone",
        "email",
        "exField1",
        "exField4",
        "exField5",
        "exField8",
    ]
    data = {
        "siteId": "3",
        "pageIndex": "1",
        "rows": "999",
        "orders": json.dumps([{"field": "firstLetter", "type": "asc"}]),
        "conditions": json.dumps(
            [{"conditions": [{"field": "published", "value": "1", "judge": "="}]}]
        ),
        "returnInfos": json.dumps([{"field": f, "name": f} for f in fields]),
        "articleType": "1",
        "level": "1",
    }
    resp = httpx.post(
        SIGS_TEACHER_API, data=data, timeout=30, headers={"User-Agent": USER_AGENT}
    )
    resp.raise_for_status()
    return resp.json().get("data") or []


def review() -> int:
    """Re-fetch every reviewed source, assert the anchor, accept the field."""
    research = _load_research()
    failures: list[str] = []
    sigs_rows: list[dict] | None = None
    sigs_fetched_at: str | None = None

    for person in PEOPLE:
        pid = person["professor_id"]
        specs = REVIEWED_FIELDS.get(pid, ())
        if not specs:
            continue
        entry = research["people"].setdefault(
            pid,
            {
                "professor_id": pid,
                "name": person["name"],
                "institution": person["institution"],
                "homepage": person["homepage"],
                "missing_fields": person["missing_fields"],
                "pages": [],
                "suggestions": {},
                "fields": {},
            },
        )
        fields = entry.setdefault("fields", {})
        for spec in specs:
            label = f"{person['name']}.{spec['field']}"
            if spec["method"] == "official_api":
                if sigs_rows is None:
                    sigs_rows = _sigs_teacher_rows()
                    sigs_fetched_at = datetime.now(timezone.utc).isoformat()
                row = next(
                    (r for r in sigs_rows if r.get("title") == spec["anchor"]), None
                )
                if row is None:
                    failures.append(f"{label}: no SIGS teacher row for {spec['anchor']}")
                    continue
                quote = json.dumps(row, ensure_ascii=False, sort_keys=True)
                if spec["value"] not in quote:
                    failures.append(f"{label}: value not in SIGS row: {quote[:160]}")
                    continue
                fields[spec["field"]] = {
                    "value": spec["value"],
                    "source_url": spec["source_url"],
                    "observed_at": sigs_fetched_at,
                    "evidence_quote": quote,
                    "method": spec["method"],
                    "accepted": True,
                }
                print(f"[review] {label} = {spec['value']}  (official_api)")
                continue

            page = fetch_page(spec["source_url"])
            text = page.get("text") or ""
            anchor = spec["anchor"]
            if page.get("status") != 200 or anchor not in text:
                failures.append(
                    f"{label}: fetch {spec['source_url']} -> {page.get('status')}, "
                    f"anchor {anchor!r} present={anchor in text} "
                    f"err={page.get('error')}"
                )
                continue
            quote = _quote_around(text, anchor, width=200)
            fields[spec["field"]] = {
                "value": spec["value"],
                "source_url": page["final_url"] or spec["source_url"],
                "observed_at": page["fetched_at"],
                "evidence_quote": quote,
                "method": spec["method"],
                "accepted": True,
            }
            print(f"[review] {label} = {spec['value']}")
    _save_research(research)
    if failures:
        print("\n[review] FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"\n[review] all reviewed fields verified -> {RESEARCH_PATH}")
    return 0


# ---------------------------------------------------------------------------
# pinyin-derived canonical_name_en / aliases
# ---------------------------------------------------------------------------


def derive_name_en(name: str) -> tuple[str | None, str | None, str]:
    """Return (western-order, eastern-order, method) romanization for a name.

    method is "identity" when the name is already latin, else "pinyin".
    Given-name syllables are joined (黄建华 -> Jianhua Huang).
    """
    if all(
        unicodedata.category(ch).startswith("L") and ord(ch) < 128
        for ch in name.replace(" ", "")
    ):
        return name, None, "identity"  # already latin
    from pypinyin import Style, pinyin

    parts = [p[0] for p in pinyin(name, style=Style.NORMAL)]
    if not parts or any(not p for p in parts):
        return None, None, "pinyin"
    family, given = parts[0], parts[1:]
    given_joined = "".join(given).capitalize()
    western = f"{given_joined} {family.capitalize()}"
    eastern = f"{family.capitalize()} {given_joined}"
    return western, eastern, "pinyin"


# ---------------------------------------------------------------------------
# batch building (dry-run) + apply + verify
# ---------------------------------------------------------------------------


def build_records(research: dict) -> tuple[list[dict], list[str]]:
    """Build batch payloads from reviewed research. Returns (payloads, problems)."""
    payloads: list[dict] = []
    problems: list[str] = []
    for person in PEOPLE:
        pid = person["professor_id"]
        entry = research["people"].get(pid)
        if entry is None:
            problems.append(f"{person['name']}: no research entry (skipped)")
            continue
        fields: dict[str, dict] = {}
        for fname, spec in (entry.get("fields") or {}).items():
            if fname not in BACKFILL_FIELD_ORDER:
                problems.append(f"{person['name']}: unknown field {fname} (dropped)")
                continue
            value = spec.get("value")
            if value in (None, "", []):
                continue
            if not spec.get("accepted", False):
                problems.append(
                    f"{person['name']}.{fname}: not accepted (left as placeholder)"
                )
                continue
            if not spec.get("source_url") or not spec.get("evidence_quote"):
                problems.append(
                    f"{person['name']}.{fname}: missing source assertion (dropped)"
                )
                continue
            fields[fname] = {
                "value": value,
                "source_url": spec["source_url"],
                "observed_at": spec["observed_at"],
                "evidence_quote": spec["evidence_quote"],
                "method": spec.get("method", "official_page"),
            }

        # canonical_name_en / aliases (romanization-derived, marked as such)
        western, eastern, name_method = derive_name_en(person["name"])
        if western and "canonical_name_en" not in fields:
            en_spec = (entry.get("fields") or {}).get("canonical_name_en")
            if en_spec and en_spec.get("accepted"):
                pass  # handled above via fields loop
            else:
                if name_method == "identity":
                    quote = f"name {person['name']} is already latin script"
                else:
                    quote = (
                        f"derived from Chinese name {person['name']} "
                        "via pypinyin (Style.NORMAL)"
                    )
                fields["canonical_name_en"] = {
                    "value": western,
                    "source_url": person["homepage"],
                    "observed_at": (entry.get("pages") or [{}])[0].get("fetched_at"),
                    "evidence_quote": quote,
                    "method": name_method,
                }
                if eastern and eastern != western:
                    fields["aliases"] = {
                        "value": [eastern],
                        "source_url": person["homepage"],
                        "observed_at": (entry.get("pages") or [{}])[0].get("fetched_at"),
                        "evidence_quote": (
                            f"family-name-first pinyin variant of {person['name']}"
                        ),
                        "method": "pinyin",
                    }

        if not fields:
            problems.append(f"{person['name']}: nothing to backfill (no record emitted)")
            continue
        payloads.append(
            {
                "professor_id": pid,
                "professor_name": person["name"],
                "institution": person["institution"],
                "missing_fields_before": person["missing_fields"],
                "fields": fields,
                "backfill_batch": SOURCE_BATCH_ID,
                "backfill_reason": (
                    "s12e professor audit priority queue (Top-14 citation_count "
                    "+ 金欣/王学谦); values extracted from official institution pages"
                ),
            }
        )
    return payloads, problems


def _batch_content(payloads: list[dict]) -> bytes:
    lines = [
        json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for p in payloads
    ]
    return ("\n".join(lines) + "\n").encode()


def _landing_derivation(content: bytes, payloads: list[dict], observed_at: datetime):
    observed_utc = observed_at.astimezone(timezone.utc)
    content_sha256 = hashlib.sha256(content).hexdigest()
    source_locator = str(STAGING_DIR / "professor_backfill_s12e_v1.jsonl")
    artifact_id = _stable_id("artifact", SOURCE_KIND, source_locator, content_sha256)
    parse_run_id = _stable_id(
        "parse-run",
        RUN_ID,
        SOURCE_BATCH_ID,
        artifact_id,
        PARSER_NAME,
        PARSER_VERSION,
        SCHEMA_VERSION,
    )
    records = []
    record_fps = []
    for ordinal, payload in enumerate(payloads):
        locator = f"line:{ordinal + 1}"
        fp = _record_fingerprint(locator, payload)
        record_fps.append(fp)
        records.append(
            {
                "record_id": _stable_id("record", parse_run_id, locator, fp),
                "record_locator": locator,
                "record_ordinal": ordinal,
                "payload": payload,
            }
        )
    request_fp = _request_fingerprint(
        artifact_id=artifact_id,
        content_sha256=content_sha256,
        source_batch_id=SOURCE_BATCH_ID,
        observed_at_utc=observed_utc.isoformat(),
    )
    output_fp = _output_fingerprint(request_fp, record_fps)
    return {
        "observed_at": observed_utc,
        "content_sha256": content_sha256,
        "source_locator": source_locator,
        "artifact_id": artifact_id,
        "parse_run_id": parse_run_id,
        "records": records,
        "request_fingerprint": request_fp,
        "output_fingerprint": output_fp,
        "byte_size": len(content),
    }


def dry_run(research: dict) -> int:
    payloads, problems = build_records(research)
    for problem in problems:
        print(f"  [skip] {problem}")
    print(f"\n[dry-run] {len(payloads)} records would be inserted:")
    field_counts: dict[str, int] = {}
    for payload in payloads:
        print(f"  - {payload['professor_name']} ({payload['professor_id']})")
        for fname, spec in payload["fields"].items():
            field_counts[fname] = field_counts.get(fname, 0) + 1
            print(f"      {fname}: {json.dumps(spec['value'], ensure_ascii=False)}")
            print(f"        source: {spec['source_url']} [{spec['method']}]")
            print(f"        quote: {spec['evidence_quote'][:140]}")
    print("\n[dry-run] per-field counts:", json.dumps(field_counts, ensure_ascii=False))
    content = _batch_content(payloads)
    deriv = _landing_derivation(content, payloads, datetime.now(timezone.utc))
    print(f"[dry-run] artifact_id  = {deriv['artifact_id']}")
    print(f"[dry-run] parse_run_id = {deriv['parse_run_id']}")
    print(f"[dry-run] batch file   = {BATCH_PATH} (not written in dry-run)")
    print("[dry-run] no DB writes performed")
    return 0


def apply(research: dict) -> int:
    import psycopg
    from psycopg.types.json import Jsonb

    payloads, problems = build_records(research)
    if not payloads:
        print("[apply] nothing to insert")
        return 1
    for problem in problems:
        print(f"  [skip] {problem}")

    content = _batch_content(payloads)
    BATCH_PATH.write_bytes(content)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    staging_path = STAGING_DIR / "professor_backfill_s12e_v1.jsonl"
    staging_path.write_bytes(content)
    deriv = _landing_derivation(content, payloads, datetime.now(timezone.utc))
    observed_at = deriv["observed_at"]

    db_url = os.environ.get("S12E_CANDIDATE_DB_URL", DEFAULT_DB_URL)
    with psycopg.connect(db_url) as conn:
        with conn.transaction():
            existing = conn.execute(
                "SELECT count(*) AS n FROM landing.source_record WHERE source_batch_id = %s",
                (SOURCE_BATCH_ID,),
            ).fetchone()
            if existing and existing[0] > 0:
                raise SystemExit(
                    f"[apply] batch {SOURCE_BATCH_ID} already exists "
                    f"({existing[0]} rows); refusing duplicate insert"
                )
            conn.execute(
                "INSERT INTO landing.evidence_artifact "
                "(artifact_id, source_kind, source_locator, content_sha256, "
                "byte_size, acquired_at, run_id, parent_artifact_id, "
                "parent_content_sha256) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    deriv["artifact_id"],
                    SOURCE_KIND,
                    deriv["source_locator"],
                    deriv["content_sha256"],
                    deriv["byte_size"],
                    observed_at,
                    RUN_ID,
                    None,
                    None,
                ),
            )
            conn.execute(
                "INSERT INTO landing.parser_run "
                "(parse_run_id, artifact_id, parser_name, parser_version, "
                "schema_version, parser_options, run_status, started_at, "
                "finished_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    deriv["parse_run_id"],
                    deriv["artifact_id"],
                    PARSER_NAME,
                    PARSER_VERSION,
                    SCHEMA_VERSION,
                    Jsonb({}),
                    "succeeded",
                    observed_at,
                    observed_at,
                ),
            )
            for record in deriv["records"]:
                conn.execute(
                    "INSERT INTO landing.source_record "
                    "(record_id, artifact_id, source_batch_id, record_locator, "
                    "parse_run_id, record_ordinal, parse_status, payload, parsed_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        record["record_id"],
                        deriv["artifact_id"],
                        SOURCE_BATCH_ID,
                        record["record_locator"],
                        deriv["parse_run_id"],
                        record["record_ordinal"],
                        "parsed",
                        Jsonb(record["payload"]),
                        observed_at,
                    ),
                )
            conn.execute(
                "INSERT INTO landing.ingest_run "
                "(run_id, source_batch_id, artifact_id, content_sha256, "
                "parse_run_id, request_fingerprint_sha256, "
                "output_fingerprint_sha256, landing_status, bytes_written, "
                "record_count, observed_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    RUN_ID,
                    SOURCE_BATCH_ID,
                    deriv["artifact_id"],
                    deriv["content_sha256"],
                    deriv["parse_run_id"],
                    deriv["request_fingerprint"],
                    deriv["output_fingerprint"],
                    "accepted",
                    deriv["byte_size"],
                    len(deriv["records"]),
                    observed_at,
                ),
            )
    print(f"[apply] inserted {len(deriv['records'])} records as {SOURCE_BATCH_ID}")
    print(f"[apply] artifact_id  = {deriv['artifact_id']}")
    print(f"[apply] parse_run_id = {deriv['parse_run_id']}")
    return 0


def verify() -> int:
    import psycopg

    db_url = os.environ.get("S12E_CANDIDATE_DB_URL", DEFAULT_DB_URL)
    with psycopg.connect(db_url) as conn:
        row = conn.execute(
            "SELECT source_batch_id, count(*) AS records, min(parse_status) AS status "
            "FROM landing.source_record WHERE source_batch_id = %s GROUP BY 1",
            (SOURCE_BATCH_ID,),
        ).fetchone()
        print("[verify] source_record:", row)
        rows = conn.execute(
            "SELECT payload->>'professor_name' AS name, "
            "jsonb_object_keys(payload->'fields') AS field "
            "FROM landing.source_record WHERE source_batch_id = %s "
            "ORDER BY name, field",
            (SOURCE_BATCH_ID,),
        ).fetchall()
        for name, field in rows:
            print(f"[verify]   {name}: {field}")
        run = conn.execute(
            "SELECT run_id, landing_status, record_count, bytes_written "
            "FROM landing.ingest_run WHERE source_batch_id = %s",
            (SOURCE_BATCH_ID,),
        ).fetchone()
        print("[verify] ingest_run:", run)
        assertion_check = conn.execute(
            "SELECT count(*) FROM landing.source_record r, "
            "jsonb_each(r.payload->'fields') AS f "
            "WHERE r.source_batch_id = %s AND ("
            "f.value->>'source_url' IS NULL OR f.value->>'evidence_quote' IS NULL "
            "OR f.value->>'observed_at' IS NULL)",
            (SOURCE_BATCH_ID,),
        ).fetchone()
        print("[verify] fields missing source assertion:", assertion_check[0])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collect",
        action="store_true",
        help="run web search + fetch + candidate extraction into research JSON",
    )
    parser.add_argument(
        "--person",
        action="append",
        default=None,
        help="restrict --collect to the given professor name (repeatable)",
    )
    parser.add_argument("--refresh", action="store_true", help="refetch cached pages")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="append-only INSERT of the batch (default is dry-run, no writes)",
    )
    parser.add_argument("--verify", action="store_true", help="verification SELECT")
    parser.add_argument(
        "--review",
        action="store_true",
        help="re-fetch reviewed sources, assert anchors, accept reviewed fields",
    )
    args = parser.parse_args()

    if args.collect:
        collect(args.person, args.refresh)
        return 0
    if args.review:
        return review()
    if args.apply:
        return apply(_load_research())
    if args.verify:
        return verify()
    return dry_run(_load_research())


if __name__ == "__main__":
    sys.exit(main())
