"""Light-lane query API: hybrid search + entity details over miroflow_light_lane_r1.

Boring by design: single file, localhost-only, direct SQL, school embedding
endpoint for query vectors. Serves the three acceptance scenarios:
company patents, embodied-AI company lists, company detail profiles.
"""

from __future__ import annotations

import threading
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
import requests
from fastapi import FastAPI, HTTPException, Query

DATABASE = "miroflow_light_lane_r1"
EMBED_ENDPOINT = "http://100.64.0.27:18005/v1/embeddings"
EMBED_MODEL = "Qwen/Qwen3-Embedding-8B"
EMBED_KEY = (
    Path("/home/longxiang/MiroThinker/.sglang_api_key").read_text().splitlines()[0]
)

app = FastAPI(title="mirothinker-light-lane", version="r1")
_local = threading.local()


def connection() -> psycopg.Connection:
    if getattr(_local, "conn", None) is None or _local.conn.closed:
        _local.conn = psycopg.connect(
            f"postgresql://miroflow@127.0.0.1:55458/{DATABASE}",
            autocommit=True,
            connect_timeout=5,
            row_factory=dict_row,
        )
    return _local.conn


def embed(text: str) -> str:
    response = requests.post(
        EMBED_ENDPOINT,
        headers={"Authorization": f"Bearer {EMBED_KEY}"},
        json={"model": EMBED_MODEL, "input": [text]},
        timeout=60,
    )
    response.raise_for_status()
    vector = response.json()["data"][0]["embedding"]
    return "[" + ",".join(repr(value) for value in vector) + "]"


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
    if mode in ("semantic", "hybrid"):
        semantic = _semantic_hits(embed(q), type, 30)
    else:
        semantic = []
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
    return {"query": q, "mode": mode, "type": type, "results": results}


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=18201)
