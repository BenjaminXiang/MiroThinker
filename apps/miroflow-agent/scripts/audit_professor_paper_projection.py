"""Audit the professor→paper projection gap in a serving pack.

Answers one question offline, without rebuilding anything: **the pack already
holds 10k professor→paper edges, but the lookup documents carry neither side of
them.** How much would change if they were projected?

Reads a serving pack read-only:

- ``lookup.sqlite3``      professor/paper documents (the serving view)
- ``relationships.json``  relationship authority (loaded whole: ~3.5 GB, ~50 s)

and reports, for the professor and paper populations:

- how many professors/papers the relationship graph touches,
- how many of those are *not* reflected in the documents
  (``professor.paper_count`` null, ``professor.research_directions`` empty,
  ``paper.professor_ids`` empty),
- the template-summary share (a summary that is one sentence repeated),
- the top professors by edge count, i.e. the natural sample for a vertical slice.

Usage::

    python scripts/audit_professor_paper_projection.py \
        --pack /var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth \
        --out .agents/runs/professor-paper-slice/projection-audit.json
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

EDGE_TYPE = "professor_attributed_to_paper"
_SENTENCE_SPLIT = re.compile(r"[。！？]")


def _load_documents(pack: Path, domain: str) -> dict[str, dict]:
    """Return ``canonical id -> lookup_content`` for one domain."""
    database = pack / "lookup.sqlite3"
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "select document_json from lookup_document where json_extract(document_json,'$.domain')=?",
            (domain,),
        )
        documents: dict[str, dict] = {}
        for (raw,) in rows:
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


def _load_edges(pack: Path) -> list[tuple[str, str]]:
    """Return ``(professor_id, paper_id)`` for every professor→paper edge."""
    started = time.time()
    payload = json.loads((pack / "relationships.json").read_text())
    relationships = payload["relationship_projection_result"]["current_relationships"]
    edges = [
        (
            relationship["source_endpoint"]["canonical_identity_id"],
            relationship["target_endpoint"]["canonical_identity_id"],
        )
        for relationship in relationships
        if relationship["relationship_type_id"] == EDGE_TYPE
    ]
    print(
        f"loaded {len(edges)} {EDGE_TYPE} edges in {time.time() - started:.1f}s "
        f"(all types: {collections.Counter(r['relationship_type_id'] for r in relationships)})",
        file=sys.stderr,
    )
    return edges


def _template_summary(summary: str) -> bool:
    """A summary counts as template when one sentence is repeated.

    The pack carries summaries like "X现任Y教师。该教授在深圳科创领域有持续贡献，
    研究成果具有重要学术价值。" repeated up to a dozen times; that text dilutes the
    research vector and must not be treated as evidence.
    """
    sentences = [
        part.strip() for part in _SENTENCE_SPLIT.split(summary or "") if part.strip()
    ]
    if len(sentences) < 2:
        return False
    counts = collections.Counter(sentences)
    top = counts.most_common(1)[0][1]
    return top >= 2 and top / len(sentences) >= 0.5


def audit(pack: Path, *, top: int) -> dict:
    professors = _load_documents(pack, "professor")
    papers = _load_documents(pack, "paper")
    edges = _load_edges(pack)

    papers_by_professor: dict[str, list[str]] = collections.defaultdict(list)
    for professor_id, paper_id in edges:
        papers_by_professor[professor_id].append(paper_id)

    linked_professors = set(papers_by_professor)
    linked_papers = {paper_id for _, paper_id in edges}

    def _professor_row(professor_id: str) -> dict:
        content = professors.get(professor_id, {})
        return {
            "id": professor_id,
            "name": content.get("name"),
            "institution": content.get("institution"),
            "papers": len(papers_by_professor[professor_id]),
            "paper_count_in_pack": content.get("paper_count"),
            "directions": len(content.get("research_directions") or []),
            "template_summary": _template_summary(content.get("profile_summary") or ""),
        }

    linked_rows = [
        _professor_row(identifier) for identifier in sorted(linked_professors)
    ]
    missing_paper_count = [
        row for row in linked_rows if row["paper_count_in_pack"] is None
    ]
    missing_directions = [row for row in linked_rows if row["directions"] == 0]

    template_total = sum(
        1
        for content in professors.values()
        if _template_summary(content.get("profile_summary") or "")
    )
    papers_with_professor_ids = sum(
        1 for content in papers.values() if content.get("professor_ids")
    )
    professors_with_directions = sum(
        1 for content in professors.values() if content.get("research_directions")
    )
    professors_with_paper_count = sum(
        1 for content in professors.values() if content.get("paper_count") is not None
    )

    ranked = sorted(linked_rows, key=lambda row: (-row["papers"], row["name"] or ""))
    return {
        "pack": str(pack),
        "population": {
            "professors": len(professors),
            "papers": len(papers),
            "professor_paper_edges": len(edges),
            "professors_with_edges": len(linked_professors),
            "professors_with_edges_pct": round(
                100 * len(linked_professors) / max(len(professors), 1), 1
            ),
            "papers_with_edges": len(linked_papers),
            "papers_with_edges_pct": round(
                100 * len(linked_papers) / max(len(papers), 1), 1
            ),
            "avg_papers_per_linked_professor": round(
                len(edges) / max(len(linked_professors), 1), 1
            ),
        },
        "document_gap": {
            "papers_with_professor_ids": papers_with_professor_ids,
            "professors_with_paper_count": professors_with_paper_count,
            "professors_with_directions": professors_with_directions,
            "linked_professors_missing_paper_count": len(missing_paper_count),
            "linked_professors_missing_directions": len(missing_directions),
            "template_summaries": template_total,
            "template_summary_pct": round(
                100 * template_total / max(len(professors), 1), 1
            ),
        },
        "sample_top_professors": ranked[:top],
        "sample_missing_both": [
            row
            for row in ranked
            if row["paper_count_in_pack"] is None and row["directions"] == 0
        ][:top],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True, help="serving pack directory")
    parser.add_argument("--out", required=True, help="report JSON path")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args(argv)

    report = audit(Path(args.pack), top=args.top)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    population = report["population"]
    gap = report["document_gap"]
    print("\n=== POPULATION ===")
    for key, value in population.items():
        print(f"  {key}: {value}")
    print("\n=== DOCUMENT GAP ===")
    for key, value in gap.items():
        print(f"  {key}: {value}")
    print("\n=== TOP LINKED PROFESSORS ===")
    for row in report["sample_top_professors"][:10]:
        print(
            f"  {row['name']} ({row['institution']}) papers={row['papers']} "
            f"paper_count={row['paper_count_in_pack']} directions={row['directions']}"
        )
    print(f"\nwritten: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
