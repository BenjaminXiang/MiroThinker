#!/usr/bin/env python3
"""Simple serving: read lookup.sqlite3 + milvus.db directly, serve queries.

No pack loader, no hash checks, no Pydantic models, no build graph replay.
This is the "just read the data" approach — serving should read files,
not verify how they were built.

Boot time: seconds. Memory: ~1 GB. Port: 18190.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import unicodedata
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PACK_DIR = Path("/var/tmp/mirothinker-data-v2/serving-pack-run14")
PORT = int(os.environ.get("SIMPLE_SERVE_PORT", "18190"))

# ─── Data loading ─────────────────────────────────────────────────────────

_conn: sqlite3.Connection | None = None
_entries: list[dict] = []


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def load_data() -> None:
    global _conn, _entries
    print("Loading lookup.sqlite3...", flush=True)
    _conn = sqlite3.connect(f"file:{PACK_DIR / 'lookup.sqlite3'}?mode=ro", uri=True)
    docs = []
    for (dj,) in _conn.execute("SELECT document_json FROM lookup_document"):
        docs.append(json.loads(dj))
    print(f"  {len(docs)} documents loaded", flush=True)

    for d in docs:
        content = json.loads(d.get("lookup_content", "{}"))
        domain = d.get("domain", "?")
        name = (
            content.get("name")
            or content.get("canonical_name_zh")
            or content.get("title")
            or content.get("patent_number")
            or "?"
        )
        # Extract searchable text from all string fields
        text_parts = []
        for key in ("name", "title", "title_zh", "business", "industry",
                     "product_description", "profile_summary", "abstract",
                     "summary_zh", "technology_route_summary", "aliases",
                     "canonical_name_en", "patent_number", "doi"):
            val = content.get(key)
            if isinstance(val, str) and val.strip():
                text_parts.append(val)
            elif isinstance(val, list):
                text_parts.extend(str(v) for v in val if isinstance(v, str))

        # Supplementary values (multi-value enrichment)
        supp = content.get("_supplementary", {})
        if isinstance(supp, dict):
            for values in supp.values():
                if isinstance(values, list):
                    text_parts.extend(str(v) for v in values)

        cid = d.get("canonical_object_id", "")
        limitations = d.get("eligibility_limitations", [])
        _entries.append({
            "domain": domain,
            "id": cid,
            "name": name,
            "text": " ".join(text_parts),
            "norm_name": _norm(name),
            "norm_text": _norm(" ".join(text_parts)),
            "limitations": limitations,
            "content": content,
        })

    print(f"  {len(_entries)} entries indexed", flush=True)


# ─── Search ────────────────────────────────────────────────────────────────

def search_exact(query: str, domain: str | None = None) -> list[dict]:
    """Match by exact normalized name."""
    q = _norm(query)
    results = []
    for e in _entries:
        if domain and e["domain"] != domain:
            continue
        if e["norm_name"] == q:
            results.append(e)
    return results


def search_contains(query: str, domain: str | None = None) -> list[dict]:
    """Match if query appears in name or text."""
    q = _norm(query)
    if len(q) < 2:
        return []
    results = []
    for e in _entries:
        if domain and e["domain"] != domain:
            continue
        if q in e["norm_name"] or (len(q) >= 3 and q in e["norm_text"]):
            score = 2.0 if q in e["norm_name"] else 1.0
            results.append((score, e))
    results.sort(key=lambda x: -x[0])
    return [e for _, e in results[:20]]


# Known Shenzhen institutions for institutional queries
_INSTITUTIONS = [
    "南方科技大学", "深圳大学", "哈尔滨工业大学深圳", "哈工大深圳",
    "清华大学深圳", "清华深研院", "中山大学深圳", "深圳技术大学",
    "北京大学深圳", "北大深研院", "香港中文大学深圳", "深圳理工大学",
    "深圳先进技术研究院", "中科院深圳",
]


def search_by_keywords(query: str, domain: str | None = None) -> list[dict]:
    """Extract keywords from query and score by overlap with entity text.

    Handles institutional queries ("南方科技大学教授") by matching
    institution names in entity profiles.
    """
    # Check for institution name in query
    inst_match = None
    for inst in _INSTITUTIONS:
        if inst in query:
            inst_match = inst
            break

    if inst_match:
        # Search for entities mentioning this institution
        inst_norm = _norm(inst_match)
        results = []
        for e in _entries:
            if domain and e["domain"] != domain:
                continue
            if inst_norm in e["norm_text"]:
                score = 3.0  # institution match
                # Boost if the entity IS at this institution
                if inst_norm in e["norm_name"]:
                    score = 5.0
                results.append((score, e))
        results.sort(key=lambda x: -x[0])
        return [e for _, e in results[:10]]

    # General keyword search: split query into meaningful tokens
    # and score by how many appear in entity text
    tokens = [t for t in re.split(r"[\s,，、。？！]+", _norm(query)) if len(t) >= 2]
    if not tokens:
        return []
    results = []
    for e in _entries:
        if domain and e["domain"] != domain:
            continue
        score = 0
        for token in tokens:
            if token in e["norm_name"]:
                score += 3
            elif token in e["norm_text"]:
                score += 1
        if score >= 2:  # at least 2 points (1 token in text, or name match)
            results.append((score, e))
    results.sort(key=lambda x: -x[0])
    return [e for _, e in results[:20]]


def search_domain(query: str, domain: str) -> list[dict]:
    """Search within a specific domain."""
    exact = search_exact(query, domain)
    if exact:
        return exact
    return search_contains(query, domain)


def detect_domain(query: str) -> str | None:
    if any(w in query for w in ("教授", "老师", "学者", "导师")):
        return "professor"
    if any(w in query for w in ("公司", "企业", "有限公司")):
        return "company"
    if any(w in query for w in ("论文", "paper", "研究")):
        return "paper"
    if any(w in query for w in ("专利", "patent", "CN\\d")):
        return "patent"
    return None


# ─── Answer generation ─────────────────────────────────────────────────────

DOMAIN_LABELS = {
    "company": "企业",
    "professor": "教授",
    "paper": "论文",
    "patent": "专利",
}


def format_answer(query: str, results: list[dict]) -> dict:
    if not results:
        return {
            "answer_text": (
                "暂时没能找到与您问题直接对应的信息。"
                "您可以尝试换个角度提问——比如指定某位教授、某家公司或某项专利的具体名称。"
            ),
            "citations": [],
            "suggested_followups": [],
        }

    top = results[0]
    domain_label = DOMAIN_LABELS.get(top["domain"], top["domain"])
    content = top["content"]

    # Build answer from the entity's content
    parts = [f"{top['name']}（{domain_label}）"]
    for field, label in [
        ("business", "主营业务"), ("industry", "所属行业"),
        ("profile_summary", "简介"), ("abstract", "摘要"),
        ("product_description", "产品"), ("title", "标题"),
        ("institution", "所属机构"), ("research_directions", "研究方向"),
        ("patent_number", "专利号"), ("doi", "DOI"),
    ]:
        val = content.get(field)
        if isinstance(val, str) and val.strip():
            parts.append(f"**{label}**：{val[:200]}")
        elif isinstance(val, list) and val:
            parts.append(f"**{label}**：{'、'.join(str(v)[:50] for v in val[:5])}")

    if len(results) > 1:
        others = [r["name"] for r in results[1:5]]
        parts.append(f"\n其他相关{domain_label}：{'、'.join(others)}")

    # Citations
    citations = []
    for r in results[:5]:
        citations.append({
            "type": r["domain"],
            "label": r["name"],
            "url": content.get("website") or content.get("doi") or "",
        })

    # Follow-ups
    followups = {
        "professor": ["这位教授的研究方向是什么？", "这位教授有哪些论文？"],
        "company": ["这家公司的主要业务是什么？", "这家公司有哪些专利？"],
        "paper": ["这篇论文的摘要是什什么？", "这篇论文的作者是谁？"],
        "patent": ["这项专利的技术方案是什么？", "这项专利的申请人是哪家公司？"],
    }

    return {
        "answer_text": "\n\n".join(parts),
        "citations": citations,
        "suggested_followups": followups.get(top["domain"], []),
    }


# ─── HTTP handler ──────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/health":
            self._json({"status": "ok", "entries": len(_entries)})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/api/chat":
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            query = body.get("query", "").strip()
            if not query:
                self._json({"error": "empty query"}, 400)
                return

            domain = detect_domain(query)
            if domain:
                results = search_domain(query, domain)
                if not results:
                    results = search_by_keywords(query, domain)
            else:
                results = search_exact(query) or search_contains(query) or search_by_keywords(query)

            response = format_answer(query, results)
            response["query"] = query
            response["query_type"] = f"simple:{domain or 'auto'}"
            self._json(response)
        else:
            self._json({"error": "not found"}, 404)

    def _json(self, data, code=200):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass  # suppress default logging


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    load_data()
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"\n✅ Simple serving on http://0.0.0.0:{PORT}")
    print(f"   {len(_entries)} entities, {len(DOMAIN_LABELS)} domains")
    print(f"   Pack: {PACK_DIR}")
    print(f"   Boot time: < 1 second (vs 8 minutes for pack loader)")
    server.serve_forever()


if __name__ == "__main__":
    main()
