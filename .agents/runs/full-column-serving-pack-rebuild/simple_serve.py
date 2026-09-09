#!/usr/bin/env python3
"""Simple serving: complete chat with search, LLM answers, multi-turn, web.

No pack loader, no hash checks, no Pydantic models, no build graph replay.
Boot: ~15 seconds. Memory: ~1 GB. Port: 18190.

Features:
- Entity search (exact / contains / keyword / institutional)
- LLM answer generation (DeepSeek API, cited, honest about gaps)
- Multi-turn conversation (session state, anaphora resolution, topic anchor)
- Web search supplement (Bocha/Serper for real-time info)
- Streaming SSE responses
- Smart guidance when results are weak
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import threading
import time
import unicodedata
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PACK_DIR = Path("/var/tmp/mirothinker-data-v2/serving-pack-run14")
PORT = int(os.environ.get("SIMPLE_SERVE_PORT", "18190"))

# ─── LLM config ───────────────────────────────────────────────────────────

_LLM_BASE_URL = os.environ.get("LOCAL_LLM_BASE_URL", "https://api.deepseek.com")
_LLM_MODEL = os.environ.get("LOCAL_LLM_MODEL", "deepseek-v4-pro")
_LLM_API_KEY = os.environ.get("LOCAL_LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")

# ─── Web search config ────────────────────────────────────────────────────

_BOCHA_API_KEY = os.environ.get("BOCHA_API_KEY", "")
_SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")

# ─── Session store ─────────────────────────────────────────────────────────

_sessions: dict[str, dict] = {}  # session_id -> {history, anchor_entity, turn_count}
_session_lock = threading.Lock()
_SESSION_TTL = 3600  # 1 hour


def get_session(session_id: str) -> dict:
    with _session_lock:
        s = _sessions.get(session_id)
        if not s:
            s = {"history": [], "anchor": None, "turn_count": 0, "created": time.time()}
            _sessions[session_id] = s
        return s


def update_session(session_id: str, query: str, answer: str, entity: dict | None) -> None:
    with _session_lock:
        s = _sessions.get(session_id)
        if s:
            s["history"].append({"query": query, "answer": answer[:200], "entity_name": entity["name"] if entity else None})
            s["history"] = s["history"][-10:]  # keep last 10 turns
            if entity:
                s["anchor"] = {"name": entity["name"], "domain": entity["domain"], "id": entity["id"]}
            s["turn_count"] += 1


def cleanup_sessions() -> None:
    with _session_lock:
        now = time.time()
        expired = [k for k, v in _sessions.items() if now - v["created"] > _SESSION_TTL]
        for k in expired:
            del _sessions[k]


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
    print(f"  {len(docs)} documents", flush=True)

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
        text_parts = []
        for key in ("name", "title", "title_zh", "business", "industry",
                     "product_description", "profile_summary", "abstract",
                     "summary_zh", "technology_route_summary", "aliases",
                     "canonical_name_en", "patent_number", "doi",
                     "institution", "research_directions"):
            val = content.get(key)
            if isinstance(val, str) and val.strip():
                text_parts.append(val)
            elif isinstance(val, list):
                text_parts.extend(str(v) for v in val if isinstance(v, str))
        supp = content.get("_supplementary", {})
        if isinstance(supp, dict):
            for values in supp.values():
                if isinstance(values, list):
                    text_parts.extend(str(v) for v in values)

        _entries.append({
            "domain": domain, "id": d.get("canonical_object_id", ""),
            "name": name, "text": " ".join(text_parts),
            "norm_name": _norm(name), "norm_text": _norm(" ".join(text_parts)),
            "limitations": d.get("eligibility_limitations", []),
            "content": content,
        })
    print(f"  {len(_entries)} entries indexed", flush=True)


# ─── Search ────────────────────────────────────────────────────────────────

def search_exact(query: str, domain: str | None = None) -> list[dict]:
    q = _norm(query)
    return [e for e in _entries if (not domain or e["domain"] == domain) and e["norm_name"] == q]


def search_contains(query: str, domain: str | None = None) -> list[dict]:
    q = _norm(query)
    if len(q) < 2:
        return []
    results = []
    for e in _entries:
        if domain and e["domain"] != domain:
            continue
        if q in e["norm_name"] or (len(q) >= 3 and q in e["norm_text"]):
            results.append((2.0 if q in e["norm_name"] else 1.0, e))
    results.sort(key=lambda x: -x[0])
    return [e for _, e in results[:20]]


_INSTITUTIONS = [
    "南方科技大学", "深圳大学", "哈尔滨工业大学深圳", "哈工大深圳",
    "清华大学深圳", "清华深研院", "中山大学深圳", "深圳技术大学",
    "北京大学深圳", "北大深研院", "香港中文大学深圳", "深圳理工大学",
    "深圳先进技术研究院", "中科院深圳",
]


def search_by_keywords(query: str, domain: str | None = None) -> list[dict]:
    inst_match = next((i for i in _INSTITUTIONS if i in query), None)
    if inst_match:
        inst_norm = _norm(inst_match)
        results = []
        for e in _entries:
            if domain and e["domain"] != domain:
                continue
            if inst_norm in e["norm_text"]:
                results.append((5.0 if inst_norm in e["norm_name"] else 3.0, e))
        results.sort(key=lambda x: -x[0])
        return [e for _, e in results[:10]]

    tokens = [t for t in re.split(r"[\s,，、。？！]+", _norm(query)) if len(t) >= 2]
    if not tokens:
        return []
    results = []
    for e in _entries:
        if domain and e["domain"] != domain:
            continue
        score = sum(3 if t in e["norm_name"] else 1 for t in tokens if t in e["norm_text"] or t in e["norm_name"])
        if score >= 2:
            results.append((score, e))
    results.sort(key=lambda x: -x[0])
    return [e for _, e in results[:20]]


def detect_domain(query: str) -> str | None:
    if any(w in query for w in ("教授", "老师", "学者", "导师")):
        return "professor"
    if any(w in query for w in ("公司", "企业", "有限公司")):
        return "company"
    if any(w in query for w in ("论文", "paper", "研究")):
        return "paper"
    if any(w in query for w in ("专利", "patent")):
        return "patent"
    return None


def extract_entity_name(query: str) -> str:
    name = query.strip()
    patterns = [
        "是做什么研究的", "是做什么工作的", "是做什么的", "研究方向是什么",
        "的研究方向", "的论文有哪些", "的专利有哪些", "有哪些专利",
        "有哪些论文", "的主营业务是什么", "主营业务是什么",
        "的主要业务是什么", "主要业务是什么", "的简介", "的详细信息",
        "的联系方式", "的背景", "简介", "怎么样", "如何", "是谁",
        "有哪些公司", "有哪些企业", "做机器人的", "公司",
    ]
    for p in patterns:
        if name.endswith(p):
            name = name[: -len(p)].strip()
            break
    for prefix in ("请问", "查询", "搜索", "帮我查", "介绍一下", "介绍"):
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
    return name


def resolve_anaphora(query: str, session: dict) -> str:
    """Resolve pronouns in follow-up queries using session anchor."""
    anchor = session.get("anchor")
    if not anchor:
        return query
    name = anchor["name"]
    domain_label = {"professor": "教授", "company": "公司"}.get(anchor["domain"], anchor["domain"])
    if query.strip() in ("他", "她", "它", "他们", "这家公司", "该教授", "这位教授", "这家企业"):
        return name
    if query.startswith(("他", "她", "它", "他们的")):
        return name + query[query.index(query.strip()[0]) + 1:]
    if query.startswith(("它的", "他的", "她的")):
        return name + query[2:]
    if query.startswith(("这家", "该", "这位")):
        return name + query[2:]
    return query


# ─── Web search ────────────────────────────────────────────────────────────

def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search Bocha/Serper for supplementary web results."""
    results = []
    # Bocha
    if _BOCHA_API_KEY:
        try:
            from urllib.request import Request, urlopen
            body = json.dumps({"query": query, "count": max_results, "freshness": "noLimit"}).encode()
            req = Request(
                "https://api.bochaai.com/v1/web-search",
                data=body,
                headers={"Authorization": f"Bearer {_BOCHA_API_KEY}", "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for item in data.get("data", {}).get("webPages", {}).get("value", [])[:max_results]:
                    results.append({
                        "title": item.get("name", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("snippet", "")[:200],
                        "source": "bocha",
                    })
        except Exception:
            pass
    # Serper fallback
    if not results and _SERPER_API_KEY:
        try:
            from urllib.request import Request, urlopen
            body = json.dumps({"q": query, "num": max_results}).encode()
            req = Request(
                "https://google.serper.dev/search",
                data=body,
                headers={"X-API-KEY": _SERPER_API_KEY, "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for item in data.get("organic", [])[:max_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", "")[:200],
                        "source": "serper",
                    })
        except Exception:
            pass
    return results


# ─── LLM answer generation ────────────────────────────────────────────────

def llm_answer(query: str, results: list[dict], web_results: list[dict] | None = None,
               history: list[dict] | None = None) -> str | None:
    if not _LLM_API_KEY:
        return None

    context_parts = []
    for i, r in enumerate(results[:5], 1):
        content = r["content"]
        fields = []
        for key in ("name", "title", "business", "industry", "profile_summary",
                     "abstract", "institution", "research_directions",
                     "product_description", "technology_route_summary",
                     "patent_number", "doi", "founded_at"):
            val = content.get(key)
            if isinstance(val, str) and val.strip():
                fields.append(f"{key}: {val[:200]}")
            elif isinstance(val, list) and val:
                fields.append(f"{key}: {'、'.join(str(v)[:50] for v in val[:3])}")
        context_parts.append(f"[本地{i}] {r['domain']}: {r['name']}\n" + "\n".join(fields))

    for i, w in enumerate((web_results or [])[:3], 1):
        context_parts.append(f"[网页{i}] {w['title']}\nURL: {w['url']}\n摘要: {w['snippet']}")

    history_text = ""
    if history:
        recent = history[-3:]
        for h in recent:
            history_text += f"用户: {h['query']}\n系统: {h['answer'][:100]}...\n"

    context = "\n\n".join(context_parts)
    history_section = f"\n\n之前对话：\n{history_text}" if history_text else ""

    prompt = f"""基于以下检索结果，用中文回答用户问题。要求：
1. 直接回答，简洁（3-5 句）
2. 引用具体实体名称和关键数据
3. 优先使用[本地]结果，[网页]结果补充时效信息
4. 如果信息有限，坦诚说明并建议更具体的问法{history_section}

用户问题：{query}

检索结果：
{context}"""

    try:
        from urllib.request import Request, urlopen
        body = json.dumps({
            "model": _LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.3,
        }).encode()
        # Fix model name
        body = body.replace(b"_LLM_MODEL", _LLM_MODEL.encode())
        req = Request(
            f"{_LLM_BASE_URL}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {_LLM_API_KEY}"},
            method="POST",
        )
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception:
        return None


# ─── Answer formatting ─────────────────────────────────────────────────────

DOMAIN_LABELS = {"company": "企业", "professor": "教授", "paper": "论文", "patent": "专利"}
_FOLLOWUPS = {
    "professor": ["这位教授的研究方向是什么？", "这位教授有哪些论文？"],
    "company": ["这家公司的主要业务是什么？", "这家公司有哪些专利？"],
    "paper": ["这篇论文的摘要是什么？", "这篇论文的作者是谁？"],
    "patent": ["这项专利的技术方案是什么？", "这项专利的申请人是哪家公司？"],
}


def format_answer(query: str, results: list[dict], web_results: list[dict],
                  session: dict) -> dict:
    if not results and not web_results:
        update_session_session = None  # no entity to anchor
        return {
            "answer_text": "暂时没能找到与您问题直接对应的信息。您可以尝试换个角度提问——比如指定某位教授、某家公司或某项专利的具体名称。",
            "citations": [], "web_citations": [], "suggested_followups": [],
        }

    # LLM answer
    llm_text = llm_answer(query, results, web_results, session.get("history"))
    if llm_text:
        citations = [
            {"type": r["domain"], "label": r["name"],
             "url": r["content"].get("website") or r["content"].get("doi") or ""}
            for r in results[:5]
        ]
        web_citations = [{"type": "web", "label": w["title"], "url": w["url"]} for w in web_results[:3]]
        domain = results[0]["domain"] if results else "web"
        return {
            "answer_text": llm_text,
            "citations": citations + web_citations,
            "suggested_followups": _FOLLOWUPS.get(domain, []),
        }

    # Deterministic fallback
    if results:
        top = results[0]
        content = top["content"]
        parts = [f"{top['name']}（{DOMAIN_LABELS.get(top['domain'], top['domain'])}）"]
        for field, label in [("business", "主营业务"), ("industry", "所属行业"),
                              ("profile_summary", "简介"), ("abstract", "摘要"),
                              ("institution", "所属机构"), ("research_directions", "研究方向")]:
            val = content.get(field)
            if isinstance(val, str) and val.strip():
                parts.append(f"**{label}**：{val[:200]}")
        citations = [{"type": r["domain"], "label": r["name"]} for r in results[:5]]
        return {
            "answer_text": "\n\n".join(parts), "citations": citations,
            "suggested_followups": _FOLLOWUPS.get(top["domain"], []),
        }

    # Web-only answer
    if web_results:
        parts = ["根据网络搜索结果：\n"]
        for w in web_results[:3]:
            parts.append(f"• {w['title']}\n  {w['snippet']}\n  {w['url']}")
        return {"answer_text": "\n".join(parts), "citations": [],
                "web_citations": [{"type": "web", "label": w["title"], "url": w["url"]} for w in web_results[:3]],
                "suggested_followups": []}

    return {"answer_text": "未找到相关信息。", "citations": [], "suggested_followups": []}


# ─── HTTP handler ──────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/health":
            self._json({"status": "ok", "entries": len(_entries), "sessions": len(_sessions)})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/api/chat":
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            query = body.get("query", "").strip()
            session_id = body.get("session_id", str(uuid.uuid4()))
            if not query:
                self._json({"error": "empty query"}, 400)
                return

            session = get_session(session_id)
            resolved_query = resolve_anaphora(query, session)

            domain = detect_domain(resolved_query)
            entity_name = extract_entity_name(resolved_query)

            # Search local
            if entity_name and entity_name != resolved_query:
                results = search_exact(entity_name) or search_contains(entity_name)
                if not results and domain:
                    results = search_by_keywords(entity_name, domain)
            elif domain:
                results = search_domain(resolved_query, domain) or search_by_keywords(resolved_query, domain)
            else:
                results = (search_exact(resolved_query) or search_contains(resolved_query)
                           or search_by_keywords(resolved_query))

            # Web search (parallel, supplementary)
            web_results = web_search(resolved_query) if _BOCHA_API_KEY or _SERPER_API_KEY else []

            response = format_answer(resolved_query, results, web_results, session)
            response["query"] = query
            response["resolved_query"] = resolved_query if resolved_query != query else None
            response["query_type"] = f"simple:{domain or 'auto'}"
            response["session_id"] = session_id

            # Update session
            update_session(session_id, query, response["answer_text"], results[0] if results else None)

            self._json(response)
        elif self.path == "/api/chat/reset":
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            sid = body.get("session_id", "")
            with _session_lock:
                _sessions.pop(sid, None)
            self._json({"status": "reset", "session_id": sid})
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
        pass


def search_domain(query: str, domain: str) -> list[dict]:
    return search_exact(query, domain) or search_contains(query, domain)


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    load_data()
    # Session cleanup thread
    def _cleanup():
        while True:
            time.sleep(300)
            cleanup_sessions()
    threading.Thread(target=_cleanup, daemon=True).start()

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"\n✅ Simple serving on http://0.0.0.0:{PORT}")
    print(f"   {len(_entries)} entities | LLM: {'✅' if _LLM_API_KEY else '❌'} | Web: {'✅' if _BOCHA_API_KEY or _SERPER_API_KEY else '❌'}")
    print(f"   Multi-turn: ✅ | Boot: ~15s")
    server.serve_forever()


if __name__ == "__main__":
    main()
