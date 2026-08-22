"""Light-lane query API: hybrid search + entity details over miroflow_light_lane_r1.

Boring by design: single file, localhost-only, direct SQL, school embedding
endpoint for query vectors. Serves the three acceptance scenarios:
company patents, embodied-AI company lists, company detail profiles.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
import requests
from fastapi import Body, FastAPI, HTTPException, Query, Request

import os

DATABASE_URL = os.environ.get(
    "LIGHT_LANE_DATABASE_URL",
    "postgresql://miroflow@127.0.0.1:55458/miroflow_light_lane_r1",
)
HOST = os.environ.get("LIGHT_LANE_HOST", "127.0.0.1")
PORT = int(os.environ.get("LIGHT_LANE_PORT", "18201"))
EMBED_ENDPOINT = os.environ.get(
    "LIGHT_LANE_EMBED_ENDPOINT",
    "http://100.64.0.27:18005/v1/embeddings",
)
EMBED_MODEL = os.environ.get("LIGHT_LANE_EMBED_MODEL", "Qwen/Qwen3-Embedding-8B")
EMBED_KEY_PATH = os.environ.get(
    "LIGHT_LANE_EMBED_KEY_PATH",
    "/home/longxiang/MiroThinker/.sglang_api_key",
)


def _embed_key() -> str:
    path = Path(EMBED_KEY_PATH)
    if path.exists():
        return path.read_text().splitlines()[0]
    return os.environ.get("LIGHT_LANE_EMBED_KEY", "")

app = FastAPI(title="mirothinker-light-lane", version="r1")
CHAT_MODEL = os.environ.get("LIGHT_LANE_CHAT_MODEL", "deepseek-v4-flash")
CHAT_BASE_URL = os.environ.get(
    "LIGHT_LANE_CHAT_ENDPOINT", "https://api.deepseek.com/v1/chat/completions"
)

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
RUNTIME_KEYS = (
    "embed_endpoint", "embed_model", "embed_key",
    "chat_endpoint", "chat_model", "chat_key", "admin_token",
)
DEFAULTS = {
    "embed_endpoint": EMBED_ENDPOINT,
    "embed_model": EMBED_MODEL,
    "embed_key": "",
    "chat_endpoint": CHAT_BASE_URL,
    "chat_model": CHAT_MODEL,
    "chat_key": "",
    "admin_token": "",
}


def _runtime_config() -> dict:
    try:
        stored = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    except (OSError, json.JSONDecodeError):
        stored = {}
    return stored if isinstance(stored, dict) else {}


def _cfg(field: str) -> str:
    stored = _runtime_config().get(field)
    if isinstance(stored, str) and stored.strip():
        return stored.strip()
    if field == "embed_key":
        return _embed_key()
    if field == "chat_key":
        return _deepseek_key()
    return DEFAULTS.get(field, "")


def _save_runtime_config(update: dict) -> None:
    stored = _runtime_config()
    stored.update(update)
    temporary = CONFIG_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(stored, ensure_ascii=False, indent=1))
    temporary.replace(CONFIG_PATH)


_local = threading.local()


def connection() -> psycopg.Connection:
    if getattr(_local, "conn", None) is None or _local.conn.closed:
        _local.conn = psycopg.connect(
            DATABASE_URL, autocommit=True, connect_timeout=5, row_factory=dict_row
        )
    return _local.conn


def embed(text: str) -> str | None:
    """Query embedding; returns None when the endpoint is unreachable so the
    caller can degrade to keyword-only instead of failing the request."""
    try:
        response = requests.post(
            _cfg("embed_endpoint"),
            headers={"Authorization": f"Bearer {_cfg('embed_key')}"},
            json={"model": _cfg("embed_model"), "input": [text]},
            timeout=15,
        )
        response.raise_for_status()
        vector = response.json()["data"][0]["embedding"]
        return "[" + ",".join(repr(value) for value in vector) + "]"
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return None


ENTITY_COLUMNS = {
    "professor": "p.name",
    "company": "c.company_name",
    "patent": "pt.title",
    "paper": "pp.title",
}

ENTITY_JOINS = """
FROM embedding e
LEFT JOIN professor p ON e.entity_type = 'professor' AND p.professor_id = e.entity_id
LEFT JOIN company c ON e.entity_type = 'company' AND c.company_name = e.entity_id
LEFT JOIN patent pt ON e.entity_type = 'patent' AND pt.patent_id = e.entity_id
LEFT JOIN paper pp ON e.entity_type = 'paper' AND pp.paper_id = e.entity_id
"""


def _semantic_hits(query_vector: str, entity_type: str | None, limit: int):
    sql = f"""
        SELECT e.entity_type, e.entity_id,
               CASE e.entity_type
                 WHEN 'professor' THEN p.name
                 WHEN 'company' THEN c.company_name
                 WHEN 'patent' THEN pt.title
                 WHEN 'paper' THEN pp.title END AS label,
               1 - (e.vec <=> %s::vector) AS score
        {ENTITY_JOINS}
        WHERE (%s::text IS NULL OR e.entity_type = %s)
        ORDER BY e.vec <=> %s::vector
        LIMIT %s
        """
    return connection().execute(
        sql, (query_vector, entity_type, entity_type, query_vector, limit)
    ).fetchall()


def _keyword_hits(query: str, entity_type: str | None, limit: int):
    """Keyword hits straight from the entity tables (no embedding join)."""
    like = f"%{query}%"
    subqueries = []
    params: list = []
    if entity_type in (None, "company"):
        subqueries.append(
            "SELECT 'company' AS entity_type, company_name AS entity_id, "
            "company_name AS label FROM company "
            "WHERE company_name ILIKE %s OR industry ILIKE %s OR business ILIKE %s "
            "LIMIT %s"
        )
        params.extend([like, like, like, limit])
    if entity_type in (None, "professor"):
        subqueries.append(
            "SELECT 'professor' AS entity_type, professor_id AS entity_id, "
            "name AS label FROM professor "
            "WHERE name ILIKE %s OR institution ILIKE %s OR department ILIKE %s "
            "LIMIT %s"
        )
        params.extend([like, like, like, limit])
    if entity_type in (None, "patent"):
        subqueries.append(
            "SELECT 'patent' AS entity_type, patent_id AS entity_id, "
            "title AS label FROM patent "
            "WHERE title ILIKE %s OR applicants::text ILIKE %s "
            "LIMIT %s"
        )
        params.extend([like, like, limit])
    if entity_type in (None, "paper"):
        subqueries.append(
            "SELECT 'paper' AS entity_type, paper_id AS entity_id, "
            "title AS label FROM paper WHERE title ILIKE %s LIMIT %s"
        )
        params.extend([like, limit])
    sql = "SELECT * FROM (" + " UNION ALL ".join(
        f"({sub})" for sub in subqueries
    ) + ") AS merged LIMIT %s"
    params.append(limit)
    return connection().execute(sql, params).fetchall()


def _fuse(semantic, keyword, limit: int):
    """Reciprocal rank fusion (k=60) over the two result lists."""
    scores: dict[tuple[str, str], dict] = {}
    for rank, row in enumerate(semantic):
        key = (row["entity_type"], row["entity_id"])
        scores.setdefault(key, {"entity_type": row["entity_type"], "entity_id": row["entity_id"], "label": row["label"], "score": 0.0})
        scores[key]["score"] += 1.0 / (60 + rank + 1)
    for rank, row in enumerate(keyword):
        key = (row["entity_type"], row["entity_id"])
        scores.setdefault(key, {"entity_type": row["entity_type"], "entity_id": row["entity_id"], "label": row["label"], "score": 0.0})
        scores[key]["score"] += 1.0 / (60 + rank + 1)
    ranked = sorted(scores.values(), key=lambda item: -item["score"])
    return ranked[:limit]


@app.get("/healthz")
def healthz():
    count = connection().execute(
        "SELECT count(*) AS count FROM embedding"
    ).fetchone()["count"]
    return {"ok": True, "embeddings": count}


@app.get("/api/search")
def search(
    q: str = Query(min_length=1),
    type: str | None = Query(default=None, pattern="^(company|patent|paper|professor)$"),
    mode: str = Query(default="hybrid", pattern="^(semantic|keyword|hybrid)$"),
    limit: int = Query(default=10, ge=1, le=50),
):
    query_vector = embed(q) if mode in ("semantic", "hybrid") else None
    if query_vector is not None:
        semantic = _semantic_hits(query_vector, type, 30)
    else:
        semantic = []
        if mode == "semantic":
            mode = "keyword"
    keyword = _keyword_hits(q, type, 30) if mode in ("keyword", "hybrid") else []
    if mode == "semantic":
        results = [
            {"entity_type": r["entity_type"], "entity_id": r["entity_id"], "label": r["label"], "score": round(float(r["score"]), 4)}
            for r in semantic[:limit]
        ]
    elif mode == "keyword":
        results = [
            {"entity_type": r["entity_type"], "entity_id": r["entity_id"], "label": r["label"]}
            for r in keyword[:limit]
        ]
    else:
        results = _fuse(semantic, keyword, limit)
    return {
        "query": q,
        "mode": mode,
        "type": type,
        "semantic_available": query_vector is not None,
        "results": results,
    }


def _public_paper_link(row) -> list[str]:
    links = []
    if row.get("doi"):
        links.append(f"https://doi.org/{row['doi']}")
    if row.get("arxiv_id"):
        links.append(f"https://arxiv.org/abs/{row['arxiv_id']}")
    if row.get("openalex_id"):
        links.append(f"https://openalex.org/{row['openalex_id']}")
    return links


@app.get("/api/company/{name}")
def company_detail(name: str):
    row = connection().execute(
        "SELECT * FROM company WHERE company_name = %s", (name,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "company not found")
    raw = row["raw"]
    binding = connection().execute(
        "SELECT aliases, evidence_urls, status FROM applicant_binding "
        "WHERE applicant_name = %s OR resolved_company = %s",
        (name, name),
    ).fetchone()
    aliases = list(binding["aliases"]) if binding else []
    names = {name, *aliases}
    patent_rows = []
    for candidate in sorted(names):
        patent_rows = connection().execute(
            "SELECT patent_id, patent_number, title, patent_type, grant_date "
            "FROM patent WHERE applicants @> to_jsonb(%s::text) "
            "ORDER BY patent_number LIMIT 500",
            (candidate,),
        ).fetchall()
        if patent_rows:
            break
    return {
        "name": raw.get("company_name"),
        "fields": {
            key: value for key, value in raw.items()
            if key != "company_name" and value not in (None, "", "-")
        },
        "aliases": aliases,
        "sources": list(binding["evidence_urls"]) if binding else [],
        "patent_count": len(patent_rows),
        "patents": [
            {
                "patent_id": p["patent_id"],
                "number": p["patent_number"],
                "title": p["title"],
                "type": p["patent_type"],
                "grant_date": p["grant_date"],
            }
            for p in patent_rows[:50]
        ],
    }


@app.get("/api/professor/{professor_id}")
def professor_detail(professor_id: str):
    row = connection().execute(
        "SELECT * FROM professor WHERE professor_id = %s", (professor_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "professor not found")
    papers = connection().execute(
        "SELECT pp.paper_id, pp.title, pp.year, pp.doi, pp.arxiv_id "
        "FROM prof_paper_link l JOIN paper pp ON pp.paper_id = l.paper_id "
        "WHERE l.professor_id = %s ORDER BY pp.year DESC NULLS LAST LIMIT 200",
        (professor_id,),
    ).fetchall()
    return {
        "professor_id": professor_id,
        "name": row["name"],
        "fields": {
            key: value for key, value in row["raw"].items()
            if key not in ("professor_id", "name") and value not in (None, "", "-")
        },
        "paper_count": len(papers),
        "papers": [
            {
                "paper_id": p["paper_id"],
                "title": p["title"],
                "year": p["year"],
                "public_link": (
                    f"https://doi.org/{p['doi']}" if p["doi"]
                    else f"https://arxiv.org/abs/{p['arxiv_id']}" if p["arxiv_id"]
                    else None
                ),
            }
            for p in papers[:50]
        ],
    }


@app.get("/api/patent/{patent_id}")
def patent_detail(patent_id: str):
    row = connection().execute(
        "SELECT * FROM patent WHERE patent_id = %s", (patent_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "patent not found")
    applicants = row["applicants"]
    bindings = connection().execute(
        "SELECT applicant_name, status, resolved_company, aliases, evidence_urls "
        "FROM applicant_binding WHERE applicant_name = ANY(%s)",
        (list(applicants),),
    ).fetchall()
    return {
        "patent_id": patent_id,
        "fields": {
            key: value for key, value in row["raw"].items()
            if key != "patent_id" and value not in (None, "", "-")
        },
        "applicants": [
            {
                "name": b["applicant_name"],
                "status": b["status"],
                "resolved_company": b["resolved_company"] or None,
                "aliases": list(b["aliases"]),
                "sources": list(b["evidence_urls"]),
            }
            for b in bindings
        ] or list(applicants),
    }


@app.get("/api/paper/{paper_id}")
def paper_detail(paper_id: str):
    row = connection().execute(
        "SELECT * FROM paper WHERE paper_id = %s", (paper_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "paper not found")
    professors = connection().execute(
        "SELECT p.professor_id, p.name FROM prof_paper_link l "
        "JOIN professor p ON p.professor_id = l.professor_id "
        "WHERE l.paper_id = %s",
        (paper_id,),
    ).fetchall()
    return {
        "paper_id": paper_id,
        "fields": {
            key: value for key, value in row["raw"].items()
            if key != "paper_id" and value not in (None, "", "-")
        },
        "public_links": _public_paper_link(row),
        "authors": row["authors"],
        "linked_professors": [
            {"professor_id": p["professor_id"], "name": p["name"]} for p in professors
        ],
    }


@app.get("/api/inventory")
def inventory():
    conn = connection()
    counts = {
        table: conn.execute(f"SELECT count(*) AS count FROM {table}").fetchone()["count"]
        for table in ("company", "patent", "paper", "professor",
                      "prof_paper_link", "applicant_binding", "embedding")
    }
    binding_breakdown = conn.execute(
        "SELECT status, count(*) AS count FROM applicant_binding GROUP BY status"
    ).fetchall()
    doi_coverage = conn.execute(
        "SELECT count(*) FILTER (WHERE doi IS NOT NULL) AS with_doi, count(*) AS total FROM paper"
    ).fetchone()
    return {
        "counts": counts,
        "applicant_binding": {row["status"]: row["count"] for row in binding_breakdown},
        "paper_doi_coverage": {
            "with_doi": doi_coverage["with_doi"], "total": doi_coverage["total"],
            "ratio": round(doi_coverage["with_doi"] / max(doi_coverage["total"], 1), 3),
        },
    }




# ---------------------------------------------------------------------------
# Grounded QA over the light lane: retrieve → compose with an LLM (env-keyed
# DeepSeek, project default) → answer only from retrieved context.
# ---------------------------------------------------------------------------

import os

SYSTEM_PROMPT = """你是深圳科创数据平台的查询助手。严格依据下面提供的【资料】回答用户问题，规则：
1. 只用资料中的信息回答；资料不足以回答时，明确说"内部数据暂无相关记录"，不要编造。
2. 企业联系方式（电话/邮箱）缺失时：直接说明"通过公开渠道无法获得联系方式"，然后简要介绍该公司业务，若资料中有邮箱则附上。绝不展示"-"之类的占位符。
3. 回答末尾列出处：论文用 DOI 链接、专利用公开号、企业解析附网页出处（资料里给了才列）。
4. 用简洁中文回答，列表优先，数字要准确（资料里给了数量就用准确数）。
5. 资料只给了部分样例时，说明"共 N 项，以下为部分列举"，不要说查不到。"""


def _deepseek_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    env_path = Path(os.environ.get(
        "LIGHT_LANE_DEEPSEEK_KEY_FILE",
        "/home/longxiang/MiroThinker/apps/miroflow-agent/.env",
    ))
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def _chat(messages: list[dict]) -> str | None:
    key = _cfg("chat_key")
    if not key:
        return None
    response = requests.post(
        _cfg("chat_endpoint"),
        headers={"Authorization": f"Bearer {key}"},
        json={"model": _cfg("chat_model"), "messages": messages,
              "temperature": 0.1, "max_tokens": 4000},
        timeout=60,
    )
    if response.status_code != 200:
        return None
    content = response.json()["choices"][0]["message"]["content"]
    return content if content and content.strip() else None


def _named_entities(question: str) -> list[dict]:
    """Companies/professors whose name contains a question n-gram (short-name match)."""
    question = "".join(ch for ch in question if not ch.isspace())
    grams: list[str] = []
    for size in (5, 4, 3):
        for start in range(0, max(len(question) - size + 1, 0) + 1):
            gram = question[start:start + size]
            if len(gram) == size:
                grams.append(gram)
    grams = [f"%{gram}%" for gram in grams]
    if not grams:
        return []
    conn = connection()
    found: list[dict] = []
    for row in conn.execute(
        "SELECT DISTINCT company_name AS name FROM company "
        "WHERE company_name LIKE ANY(%s) LIMIT 3", (grams,)
    ).fetchall():
        found.append({"entity_type": "company", "entity_id": row["name"], "label": row["name"]})
    for row in conn.execute(
        "SELECT professor_id, name FROM professor WHERE name LIKE ANY(%s) LIMIT 3",
        (grams,),
    ).fetchall():
        found.append({
            "entity_type": "professor",
            "entity_id": row["professor_id"],
            "label": row["name"],
        })
    return found[:4]


def _build_context(question: str) -> tuple[str, list[dict]]:
    named = _named_entities(question)
    query_vector = embed(question)
    semantic_hits = (
        _semantic_hits(query_vector, None, 10) if query_vector is not None else []
    )
    hits = _fuse(semantic_hits, _keyword_hits(question, None, 10), 10)
    named_keys = {(item["entity_type"], item["entity_id"]) for item in named}
    ordered = named + [
        hit for hit in hits
        if (hit["entity_type"], hit["entity_id"]) not in named_keys
    ]
    blocks: list[str] = []
    sources: list[dict] = []
    for hit in ordered[:6]:
        etype, eid, label = hit["entity_type"], hit["entity_id"], hit["label"]
        if etype == "company":
            detail = company_detail(label)
            patents = detail["patents"][:12]
            block = {
                "类型": "企业", "名称": detail["name"],
                "字段": detail["fields"], "别名": detail["aliases"],
                "专利数": detail["patent_count"],
                "专利样例": [f"{p['number']} {p['title']}（{p['type']}）" for p in patents],
            }
            for url in detail["sources"][:2]:
                sources.append({"type": "企业解析", "label": detail["name"], "url": url})
        elif etype == "professor":
            detail = professor_detail(eid)
            block = {
                "类型": "教授", "姓名": detail["name"],
                "字段": {k: v for k, v in detail["fields"].items() if not isinstance(v, (list, dict))},
                "论文数": detail["paper_count"],
                "论文样例": [p["title"] for p in detail["papers"][:8]],
            }
            for p in detail["papers"][:3]:
                if p["public_link"]:
                    sources.append({"type": "论文", "label": p["title"][:40], "url": p["public_link"]})
        elif etype == "patent":
            detail = patent_detail(eid)
            block = {"类型": "专利", "标题": detail["fields"].get("title"),
                     "公开号": detail["fields"].get("patent_number"),
                     "类型/摘要": detail["fields"].get("patent_type")}
            sources.append({"type": "专利", "label": detail["fields"].get("title", "")[:40],
                            "url": detail["fields"].get("patent_number", "")})
        else:
            detail = paper_detail(eid)
            block = {"类型": "论文", "标题": detail["fields"].get("title"),
                     "作者数": len(detail["authors"]),
                     "摘要片段": str(detail["fields"].get("abstract", ""))[:200]}
            for url in detail["public_links"][:1]:
                sources.append({"type": "论文", "label": detail["fields"].get("title", "")[:40], "url": url})
        blocks.append(json.dumps(block, ensure_ascii=False, default=str))
    context = "\n\n".join(f"【资料{i+1}】\n{b}" for i, b in enumerate(blocks))
    return context, sources


@app.get("/api/ask")
def ask(q: str = Query(min_length=1)):
    context, sources = _build_context(q)
    if not context:
        return {"question": q, "answer": "内部数据暂无相关记录。", "sources": [], "grounded": False}
    answer = _chat([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"【问题】{q}\n\n{context}"},
    ])
    if answer is None:
        return {"question": q, "answer": None, "sources": sources,
                "grounded": False, "note": "LLM 不可用，返回检索结果供人工查看",
                "retrieved": context[:2000]}
    return {"question": q, "answer": answer, "sources": sources, "grounded": True}


import json  # noqa: E402  (used by _build_context)

def _admin_authorized(request) -> bool:
    token = _cfg("admin_token")
    supplied = request.headers.get("X-Admin-Token", "")
    if token:
        return supplied == token
    return request.client.host in ("127.0.0.1", "::1") if request.client else False


def _masked(value: str) -> str:
    if not value:
        return ""
    return f"***({value[-4:]})" if len(value) > 8 else "***"


@app.get("/api/admin/config")
def admin_get_config(request: Request):
    if not _admin_authorized(request):
        raise HTTPException(403, "admin token required (set admin_token in config)")
    return {
        field: (_masked(_cfg(field)) if field.endswith("_key") or field == "admin_token" else _cfg(field))
        for field in RUNTIME_KEYS
    }


@app.put("/api/admin/config")
def admin_put_config(request: Request, payload: dict = Body(...)):
    if not _admin_authorized(request):
        raise HTTPException(403, "admin token required")
    update = {
        key: value for key, value in payload.items()
        if key in RUNTIME_KEYS and isinstance(value, str)
    }
    unknown = sorted(set(payload) - set(RUNTIME_KEYS))
    if unknown:
        raise HTTPException(400, f"unknown fields: {unknown}")
    _save_runtime_config(update)
    return {"saved": sorted(update)}


@app.post("/api/admin/config/test")
def admin_test_config(request: Request):
    """Probe both model endpoints with the effective config."""
    if not _admin_authorized(request):
        raise HTTPException(403, "admin token required")
    result: dict = {}
    started = time.time()
    vector = embed("连通性测试")
    result["embed"] = {
        "ok": vector is not None,
        "latency_ms": int((time.time() - started) * 1000),
        "endpoint": _cfg("embed_endpoint"),
        "model": _cfg("embed_model"),
        "dimension": len(json.loads(vector)) if vector else None,
    }
    started = time.time()
    answer = _chat([{"role": "user", "content": "回复：ok"}])
    result["chat"] = {
        "ok": answer is not None,
        "latency_ms": int((time.time() - started) * 1000),
        "endpoint": _cfg("chat_endpoint"),
        "model": _cfg("chat_model"),
        "sample": (answer or "")[:40],
    }
    return result


ADMIN_PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>模型配置 · 轻量线管理</title>
<style>
body{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;background:#fafafa}
h1{font-size:20px}table{width:100%;border-collapse:collapse;background:#fff}
td{border:1px solid #e0e0e0;padding:8px;font-size:14px}
td:first-child{width:180px;color:#555}input{width:95%;padding:6px;font-size:14px}
button{padding:8px 16px;margin:12px 8px 0 0}#status{margin-top:16px;white-space:pre-wrap;font-size:13px;background:#fff;border:1px solid #e0e0e0;padding:12px;border-radius:8px}
</style></head><body>
<h1>模型配置（保存即生效，免重启）</h1>
<table id="t"></table>
<button onclick="save()">保存配置</button>
<button onclick="testAll()">连通性测试</button>
<div id="status">加载中…</div>
<script>
const FIELDS=[["embed_endpoint","嵌入接口 URL"],["embed_model","嵌入模型"],
["embed_key","嵌入密钥（留空=沿用现值）"],["chat_endpoint","对话接口 URL"],
["chat_model","对话模型"],["chat_key","对话密钥（留空=沿用现值）"],
["admin_token","管理令牌（空=仅本机可管）"]];
const token=prompt("管理令牌（未设置则直接确定）")||"";
const H={"X-Admin-Token":token,"Content-Type":"application/json"};
async function load(){const r=await fetch("/api/admin/config",{headers:H});const d=await r.json();
if(d.detail){document.getElementById("status").textContent="鉴权失败："+d.detail;return;}
const t=document.getElementById("t");t.innerHTML="";
for(const [k,label] of FIELDS){const tr=document.createElement("tr");
const cur=d[k]&&d[k].startsWith("***")?d[k]:"";
tr.innerHTML=`<td>${label}<br><span style="font-size:11px;color:#999">${k}${cur?" 当前:"+cur:""}</span></td><td><input id="f_${k}" placeholder=""></td>`;
t.appendChild(tr);}document.getElementById("status").textContent="已加载当前配置。带 *** 的为现值（打码），留空不修改。";}
async function save(){const payload={};for(const [k] of FIELDS){const v=document.getElementById("f_"+k).value;if(v)payload[k]=v;}
if(!Object.keys(payload).length){document.getElementById("status").textContent="没有修改。";return;}
const r=await fetch("/api/admin/config",{method:"PUT",headers:H,body:JSON.stringify(payload)});
document.getElementById("status").textContent=JSON.stringify(await r.json());load();}
async function testAll(){document.getElementById("status").textContent="测试中…";
const r=await fetch("/api/admin/config/test",{method:"POST",headers:H});
const d=await r.json();
document.getElementById("status").textContent=
"嵌入："+(d.embed.ok?"✓ "+d.embed.dimension+" 维 / "+d.embed.latency_ms+"ms":"✗ 失败（语义检索将降级为关键词）")+"\n"+
"对话："+(d.chat.ok?"✓ "+d.chat.latency_ms+"ms / 回复: "+d.chat.sample:"✗ 失败（问答将降级为检索直出）");}
load();
</script></body></html>"""


@app.get("/admin")
def admin_page():
    from fastapi.responses import HTMLResponse

    return HTMLResponse(ADMIN_PAGE)


CHAT_PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>科创数据查询（轻量线）</title>
<style>
body{font-family:system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 16px;background:#fafafa}
h1{font-size:20px} #q{width:70%;padding:10px;font-size:15px} button{padding:10px 18px;font-size:15px}
#a{margin-top:24px;white-space:pre-wrap;background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:18px;min-height:60px}
.src{margin-top:10px;font-size:13px;color:#555}.src a{color:#06c}
</style></head><body>
<h1>深圳科创数据查询（轻量线 · 全列数据）</h1>
<div><input id="q" placeholder="例如：优必选有哪些专利？/ 深圳做机器人的公司有哪些？" autofocus>
<button onclick="ask()">查询</button></div>
<div id="a">输入问题开始查询。</div>
<script>
async function ask(){
  const q=document.getElementById('q').value; if(!q)return;
  document.getElementById('a').textContent='查询中…';
  try{
    const r=await fetch('/api/ask?q='+encodeURIComponent(q));
    const d=await r.json();
    let html=(d.answer||d.note||'')+'';
    if(d.sources&&d.sources.length){
      html+='\\n\\n出处：';
      for(const s of d.sources.slice(0,6)) html+='\\n· '+(s.url.startsWith('http')?'<a href="'+s.url+'" target="_blank">'+s.label+'</a>':s.label+'（'+s.url+'）');
    }
    document.getElementById('a').innerHTML=html;
  }catch(e){document.getElementById('a').textContent='查询失败：'+e;}
}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')ask();});
</script></body></html>"""


@app.get("/")
def chat_page():
    from fastapi.responses import HTMLResponse

    return HTMLResponse(CHAT_PAGE)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
