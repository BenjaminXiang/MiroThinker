"""Materialise professor↔paper links into a built serving pack.

The build computes 10,742 `professor_attributed_to_paper` edges and writes them
only to `relationships.json`; the lookup documents keep `paper.professor_ids`
empty and `professor.paper_count`/`paper_ids` absent, so the serving runtime can
answer "this professor's papers" but never "this paper's authors", and a profile
cannot show how many papers the graph attributes to it.

This step runs **after the pack is built and before it is sealed**: it rewrites
`lookup_content` for the affected documents and recomputes the content hash, so
the seal covers the patched file. It deliberately touches metadata only — the
vectors are not recomputed here (a summary change is a source-data fix, not a
pack patch).

Rules (same precision posture as gate 3.3):

- edges whose paper or professor is missing from the pack are dropped;
- `paper.professor_ids` is the deduped, sorted list of linked professors;
- `professor.paper_ids` is capped (`--max-paper-ids`), `paper_count` is the true
  edge count, `top_papers` are the three most cited of those papers;
- an existing non-empty value is never overwritten: a source `paper_count`
  wins over the graph count, existing `paper_ids` / `professor_ids` win too;
- `--dry-run` reports what would change without writing.

Usage::

    python scripts/materialize_pack_links.py \
        --pack /var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth \
        --edges /var/tmp/mirothinker-data-v2/professor-projection/edges.jsonl \
        [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

TOP_PAPERS = 3
MAX_PAPER_IDS = 50


def sha256_text(text: str) -> str:
    """Same digest format as the builder's ``_sha256_text``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_edges(path: Path) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            value = json.loads(line)
            edges.append((str(value[0]), str(value[1])))
    return edges


def build_maps(
    edges: list[tuple[str, str]],
    *,
    professor_ids: set[str],
    paper_ids: set[str],
) -> tuple[dict[str, list[str]], dict[str, list[str]], int]:
    """Return (paper→professors, professor→papers, dropped) for known objects."""
    by_paper: dict[str, list[str]] = {}
    by_professor: dict[str, list[str]] = {}
    dropped = 0
    for professor_id, paper_id in edges:
        if professor_id not in professor_ids or paper_id not in paper_ids:
            dropped += 1
            continue
        by_paper.setdefault(paper_id, []).append(professor_id)
        by_professor.setdefault(professor_id, []).append(paper_id)
    return by_paper, by_professor, dropped


def _top_papers(paper_ids: list[str], papers: dict[str, dict], limit: int) -> list[str]:
    ranked = sorted(
        (papers[identifier] for identifier in paper_ids if identifier in papers),
        key=lambda document: (
            -(document.get("citation_count") or 0),
            -(document.get("year") or 0),
            document.get("title") or "",
        ),
    )
    return [str(document.get("canonical_identity_id")) for document in ranked[:limit]]


def apply_links(
    *,
    professors: dict[str, dict],
    papers: dict[str, dict],
    by_paper: dict[str, list[str]],
    by_professor: dict[str, list[str]],
    max_paper_ids: int = MAX_PAPER_IDS,
    top_papers: int = TOP_PAPERS,
) -> tuple[dict[str, dict], dict[str, dict], dict]:
    """Return (updated papers, updated professors, stats) without mutating inputs."""

    updated_papers: dict[str, dict] = {}
    for paper_id, linked in by_paper.items():
        document = dict(papers[paper_id])
        existing = document.get("professor_ids") or []
        if existing:
            continue
        document["professor_ids"] = sorted(set(linked))
        updated_papers[paper_id] = document

    updated_professors: dict[str, dict] = {}
    for professor_id, linked in by_professor.items():
        document = dict(professors[professor_id])
        unique = sorted(set(linked))
        changed = False
        if not document.get("paper_ids"):
            document["paper_ids"] = unique[:max_paper_ids]
            changed = True
        if not document.get("top_papers"):
            document["top_papers"] = _top_papers(unique, papers, top_papers)
            changed = True
        if document.get("paper_count") is None:
            # A count that came from the source (homepage, roster) wins over the
            # graph count; only fill the hole.
            document["paper_count"] = len(unique)
            changed = True
        if changed:
            updated_professors[professor_id] = document

    stats = {
        "papers_updated": len(updated_papers),
        "professors_updated": len(updated_professors),
        "papers_already_set": len(by_paper) - len(updated_papers),
        "professors_already_set": len(by_professor) - len(updated_professors),
    }
    return updated_papers, updated_professors, stats


def _read_documents(connection: sqlite3.Connection, domain: str) -> dict[str, dict]:
    rows = connection.execute(
        "select document_json from lookup_document where json_extract(document_json,'$.domain')=?",
        (domain,),
    )
    documents: dict[str, dict] = {}
    for (raw,) in rows:
        document = json.loads(raw)
        content = document.get("lookup_content")
        if isinstance(content, str):
            content = json.loads(content)
        documents[content["canonical_identity_id"]] = content
    return documents


def _write_documents(
    connection: sqlite3.Connection, domain: str, documents: dict[str, dict]
) -> int:
    written = 0
    for canonical_id, content in documents.items():
        rendered = json.dumps(
            content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        digest = sha256_text(rendered)
        rows = connection.execute(
            "select document_id, document_json from lookup_document "
            "where json_extract(document_json,'$.domain')=? "
            "and canonical_object_id=?",
            (domain, canonical_id),
        ).fetchall()
        for document_id, raw in rows:
            document = json.loads(raw)
            document["lookup_content"] = rendered
            document["lookup_content_sha256"] = digest
            connection.execute(
                "update lookup_document set document_json=? where document_id=?",
                (json.dumps(document, ensure_ascii=False), document_id),
            )
            written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--edges", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-paper-ids", type=int, default=MAX_PAPER_IDS)
    parser.add_argument("--top-papers", type=int, default=TOP_PAPERS)
    args = parser.parse_args(argv)

    pack = Path(args.pack)
    database = pack / "lookup.sqlite3"
    if not database.is_file():
        print(f"no lookup database at {database}", file=sys.stderr)
        return 2

    connection = sqlite3.connect(database)
    try:
        professors = _read_documents(connection, "professor")
        papers = _read_documents(connection, "paper")
        edges = load_edges(Path(args.edges))
        by_paper, by_professor, dropped = build_maps(
            edges,
            professor_ids=set(professors),
            paper_ids=set(papers),
        )
        updated_papers, updated_professors, stats = apply_links(
            professors=professors,
            papers=papers,
            by_paper=by_paper,
            by_professor=by_professor,
            max_paper_ids=args.max_paper_ids,
            top_papers=args.top_papers,
        )
        print(f"edges: {len(edges)} (dropped {dropped})")
        print(
            f"papers: {stats['papers_updated']} to update, "
            f"{stats['papers_already_set']} already set"
        )
        print(
            f"professors: {stats['professors_updated']} to update, "
            f"{stats['professors_already_set']} already set"
        )
        if args.dry_run:
            print("dry run: nothing written")
            return 0
        written = _write_documents(connection, "paper", updated_papers)
        written += _write_documents(connection, "professor", updated_professors)
        connection.commit()
        print(f"written documents: {written}")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
