"""Build a professor projection from the pack's own relationship edges.

The serving documents carry no paper link at all: ``paper.professor_ids`` is
empty and 86% of the professors that *do* have edges still have no
``paper_count``. The edges exist (``relationships.json`` → 10,742 of them), but
the audit showed they cannot be projected blindly: the top node by edges is a
real professor whose *name* was scraped from breadcrumb navigation text
(``面包屑``), and one 210-paper node carries a same-name merge risk.

So this tool puts a **field-quality gate** in front of the projection:

- a plausible person name (2–4 CJK characters, or a latin name) and not a
  placeholder picked up from page chrome;
- an email that survives a strict check (the crawler concatenates page labels
  into the field: ``...@cuhk.edu.cnofficeaddressphoneteachingarea...``); a bad
  email is dropped from the projection, it does not reject the person;
- a homepage that is actually a URL.

Admitted professors get ``paper_count``, ``paper_ids`` and ``top_papers``
computed from their edges; suspicious nodes are admitted but flagged
(``high_paper_count``, ``duplicate_name``) so a later step can review them
before anything reaches an answer.

Nothing here writes to a pack or to Postgres: it produces a projection file plus
a coverage report, and materialisation is a separate, reviewed step.

Usage::

    python scripts/build_professor_paper_projection.py \
        --pack /var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth \
        --out .agents/runs/professor-paper-slice
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import re
import sqlite3

EDGE_TYPE = "professor_attributed_to_paper"
TOP_PAPERS = 5
MAX_PAPER_IDS = 50
HIGH_PAPER_COUNT = 100
LOW_CONFIDENCE = 0.8

# Names that are page chrome or a generic appellation rather than a person.
JUNK_NAMES = frozenset(
    {
        "教授",
        "副教授",
        "讲师",
        "老师",
        "教师",
        "博士",
        "研究员",
        "院士",
        "面包屑",
        "首页",
        "更多",
        "登录",
        "详情",
        "简介",
        "返回",
        "全部",
        "展开",
        "收起",
        "搜索",
        "师资力量",
        "师资队伍",
        "教师队伍",
        "研究人员",
        "教师名录",
    }
)

_CJK_NAME = re.compile(r"^[\u4e00-\u9fff·]{2,4}$")
_LATIN_NAME = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,48}$")
_URL = re.compile(r"^https?://[^\s]+$")
_TEMPLATE_SPLIT = re.compile(r"[。！？]")


def is_plausible_name(name: str | None) -> bool:
    """A person's name, not page chrome and not a generic title."""
    if not name:
        return False
    stripped = name.strip()
    if stripped in JUNK_NAMES:
        return False
    return bool(_CJK_NAME.fullmatch(stripped) or _LATIN_NAME.fullmatch(stripped))


def is_valid_email(email: str | None) -> bool:
    """Strict enough to reject page-label concatenation.

    The crawler glues ``office address phone teaching area other biography``
    onto the address, which still looks like ``local@domain.tld`` to a naive
    regex. Bounding the total length and every domain label catches it.
    """
    if not email or len(email) > 64 or " " in email:
        return False
    local, separator, domain = email.rpartition("@")
    if not separator or not local:
        return False
    labels = domain.split(".")
    if len(labels) < 2 or any(not 1 <= len(label) <= 24 for label in labels):
        return False
    tld = labels[-1]
    return 2 <= len(tld) <= 6 and tld.isalpha()


def _is_template_summary(summary: str) -> bool:
    parts = [
        part.strip() for part in _TEMPLATE_SPLIT.split(summary or "") if part.strip()
    ]
    if len(parts) < 2:
        return False
    top = collections.Counter(parts).most_common(1)[0][1]
    return top >= 2 and top / len(parts) >= 0.5


def gate_professor(record: dict) -> dict:
    """Return ``{"admitted": bool, "reasons": [...], "email": cleaned or None}``."""
    reasons: list[str] = []
    if not is_plausible_name(record.get("name")):
        reasons.append("implausible_name")
    homepage = record.get("homepage")
    if homepage and not _URL.fullmatch(str(homepage)):
        reasons.append("bad_homepage")
    email = record.get("email")
    cleaned_email = email if is_valid_email(email) else None
    if email and cleaned_email is None:
        # A corrupted email does not disqualify the person: the projection does
        # not need it, so drop the field and keep the record.
        reasons.append("email_dropped")
    blocking = [reason for reason in reasons if reason != "email_dropped"]
    return {
        "admitted": not blocking,
        "reasons": reasons,
        "blocking": blocking,
        "email": cleaned_email,
    }


def load_documents(pack: Path, domain: str) -> dict[str, dict]:
    database = pack / "lookup.sqlite3"
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        cursor = connection.execute(
            "select document_json from lookup_document "
            "where json_extract(document_json,'$.domain')=?",
            (domain,),
        )
        documents: dict[str, dict] = {}
        for (raw,) in cursor:
            document = json.loads(raw)
            content = document.get("lookup_content")
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    continue
            if isinstance(content, dict):
                documents[content["canonical_identity_id"]] = content
        return documents
    finally:
        connection.close()


def load_edges(pack: Path, cache: Path | None = None) -> list[tuple]:
    """Professor→paper edges with decision confidence, cached as JSONL.

    The relationships file is 3.5 GB and takes ~60 s to load, so the first run
    writes ``(professor_id, paper_id, confidence, method)`` tuples to a cache and
    later runs read that instead.

    The confidence matters: a name-based attribution between a Chinese
    professor name and an English author name can merge several people. The
    record-level gate cannot see that; the edge-level confidence can.
    """
    if cache is not None and cache.exists():
        rows = []
        with cache.open() as handle:
            for line in handle:
                if line.strip():
                    value = json.loads(line)
                    rows.append(tuple(value))
        return rows
    payload = json.loads((pack / "relationships.json").read_text())
    result = payload["relationship_projection_result"]
    decisions = {
        decision["decision_id"]: decision
        for decision in result.get("relationship_decisions", ())
    }
    edges = []
    for relationship in result["current_relationships"]:
        if relationship["relationship_type_id"] != EDGE_TYPE:
            continue
        decision = decisions.get(relationship.get("decision_id")) or {}
        edges.append(
            (
                relationship["source_endpoint"]["canonical_identity_id"],
                relationship["target_endpoint"]["canonical_identity_id"],
                decision.get("confidence"),
                decision.get("method"),
            )
        )
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with cache.open("w") as handle:
            for edge in edges:
                handle.write(json.dumps(edge) + "\n")
    return edges


def _top_papers(
    paper_ids: list[str], papers: dict[str, dict], limit: int
) -> list[dict]:
    documents = [papers[identifier] for identifier in paper_ids if identifier in papers]
    documents.sort(
        key=lambda document: (
            -(document.get("citation_count") or 0),
            -(document.get("year") or 0),
            document.get("title") or "",
        )
    )
    return [
        {
            "id": document.get("canonical_identity_id") or document.get("id"),
            "title": document.get("title"),
            "title_zh": document.get("title_zh"),
            "year": document.get("year"),
            "citation_count": document.get("citation_count"),
            "doi": document.get("doi"),
        }
        for document in documents[:limit]
    ]


def build_projection(
    professors: dict[str, dict],
    papers: dict[str, dict],
    edges: list[tuple[str, str]],
    *,
    top_papers: int = TOP_PAPERS,
    max_paper_ids: int = MAX_PAPER_IDS,
) -> tuple[dict[str, dict], dict]:
    by_professor: dict[str, list[str]] = collections.defaultdict(list)
    confidences: dict[str, list[float]] = collections.defaultdict(list)
    dropped_edges = 0
    for edge in edges:
        professor_id, paper_id = edge[0], edge[1]
        confidence = edge[2] if len(edge) > 2 else None
        if paper_id not in papers:
            dropped_edges += 1
            continue
        by_professor[professor_id].append(paper_id)
        if isinstance(confidence, (int, float)):
            confidences[professor_id].append(float(confidence))

    projection: dict[str, dict] = {}
    admitted_papers: set[str] = set()
    rejections: collections.Counter[str] = collections.Counter()
    email_dropped = 0
    for professor_id, paper_ids in sorted(by_professor.items()):
        record = professors.get(professor_id)
        if record is None:
            rejections["professor_not_in_pack"] += 1
            continue
        verdict = gate_professor(record)
        if not verdict["admitted"]:
            rejections[verdict["blocking"][0]] += 1
            continue
        if verdict["email"] is None and record.get("email"):
            email_dropped += 1
        unique_ids = sorted(set(paper_ids))
        flags: list[str] = []
        if len(unique_ids) >= HIGH_PAPER_COUNT:
            flags.append("high_paper_count")
        if _is_template_summary(record.get("profile_summary") or ""):
            flags.append("template_summary")
        if not record.get("research_directions"):
            flags.append("no_directions")
        scores = confidences.get(professor_id) or []
        if scores and min(scores) < LOW_CONFIDENCE:
            flags.append("low_confidence_edge")
        admitted_papers.update(unique_ids)
        projection[professor_id] = {
            "professor_id": professor_id,
            "name": record.get("name"),
            "institution": record.get("institution"),
            "email": verdict["email"],
            "paper_count": len(unique_ids),
            "paper_ids": unique_ids[:max_paper_ids],
            "top_papers": _top_papers(unique_ids, papers, top_papers),
            "flags": flags,
            "confidence": {
                "min": round(min(scores), 3) if scores else None,
                "median": (
                    round(sorted(scores)[len(scores) // 2], 3) if scores else None
                ),
                "edges": len(scores),
            },
            "gate": {"reasons": verdict["reasons"]},
        }

    name_counts = collections.Counter(row["name"] for row in projection.values())
    for row in projection.values():
        if name_counts[row["name"]] > 1:
            row["flags"].append("duplicate_name")

    current_counts = {
        professor_id: professors[professor_id].get("paper_count")
        for professor_id in projection
    }
    gaining = sum(1 for value in current_counts.values() if value is None)
    report = {
        "population": {
            "professors": len(professors),
            "papers": len(papers),
            "edges": len(edges),
            "edges_without_paper": dropped_edges,
            "professors_with_edges": len(by_professor),
            "projected_professors": len(projection),
            "rejected_professors": sum(rejections.values()),
            "rejected_by_reason": dict(rejections),
            "email_dropped": email_dropped,
            "projected_professor_paper_pairs": sum(
                row["paper_count"] for row in projection.values()
            ),
            "projected_distinct_papers": len(admitted_papers),
            "professors_gaining_paper_count": gaining,
        },
        "flags": dict(
            collections.Counter(
                flag for row in projection.values() for flag in row["flags"]
            )
        ),
        "confidence": {
            "edges_with_score": sum(len(values) for values in confidences.values()),
            "min": round(
                min(
                    (v for values in confidences.values() for v in values), default=0.0
                ),
                3,
            ),
            "below_threshold": sum(
                1
                for values in confidences.values()
                for v in values
                if v < LOW_CONFIDENCE
            ),
        },
        "samples": sorted(
            (
                {
                    "name": row["name"],
                    "institution": row["institution"],
                    "paper_count": row["paper_count"],
                    "flags": row["flags"],
                    "top_paper": (
                        row["top_papers"][0]["title"] if row["top_papers"] else None
                    ),
                }
                for row in projection.values()
            ),
            key=lambda row: -row["paper_count"],
        )[:20],
    }
    return projection, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--top-papers", type=int, default=TOP_PAPERS)
    parser.add_argument("--max-paper-ids", type=int, default=MAX_PAPER_IDS)
    parser.add_argument(
        "--edges-cache",
        default=None,
        help="JSONL cache of the edges (the relationships file takes ~60 s to load)",
    )
    args = parser.parse_args(argv)

    pack = Path(args.pack)
    out = Path(args.out)
    professors = load_documents(pack, "professor")
    papers = load_documents(pack, "paper")
    cache = Path(args.edges_cache) if args.edges_cache else out / "edges.jsonl"
    edges = load_edges(pack, cache)

    projection, report = build_projection(
        professors,
        papers,
        edges,
        top_papers=args.top_papers,
        max_paper_ids=args.max_paper_ids,
    )

    out.mkdir(parents=True, exist_ok=True)
    (out / "professor-projection.json").write_text(
        json.dumps(projection, ensure_ascii=False, indent=2)
    )
    (out / "projection-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )

    print("=== POPULATION ===")
    for key, value in report["population"].items():
        print(f"  {key}: {value}")
    print("=== FLAGS ===")
    for key, value in report["flags"].items():
        print(f"  {key}: {value}")
    print("=== TOP 10 ===")
    for row in report["samples"][:10]:
        print(
            f"  {row['name']} ({row['institution']}) papers={row['paper_count']} "
            f"flags={row['flags']}"
        )
    print(f"\nwritten: {out / 'professor-projection.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
