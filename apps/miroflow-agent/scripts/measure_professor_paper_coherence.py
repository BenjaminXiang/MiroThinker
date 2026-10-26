"""Measure semantic coherence between a professor's declared directions and their papers.

The projection (gate 3.1) is only as good as its edges, and the edges carry no
usable confidence (all 1.0 / deterministic). The open question is whether the
linked papers actually belong to that person. A cheap proxy: do the papers sit
near the professor's own declared research directions in embedding space?

This tool embeds the professor's `research_directions` (or the profile summary
when directions are empty) and up to ``--top`` linked paper titles, then reports
the mean cosine. It is a **review signal, not a gate**: on the ten professors
sampled during gate 3.1 it separated five matches (0.30–0.47) from three
same-name merges (0.20–0.25), but professors without directions cannot be scored
at all (they fall back to a generic summary and score low regardless).

Needs the embedding endpoint the serving line already uses:

    export CANONICAL_V2_EMBEDDING_API_KEY=...        # or --api-key-env
    export CANONICAL_V2_EMBEDDING_BASE_URL=https://maas.qianwenaiapi.com/api/v1

Usage::

    python scripts/measure_professor_paper_coherence.py \
        --pack /var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth \
        --projection .agents/runs/professor-paper-slice/professor-projection.json \
        --names 朱军,陈名华,王强,张旻,李骏 \
        --out .agents/runs/professor-paper-slice/coherence.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sqlite3
import urllib.request

DEFAULT_MODEL = "qwen3.7-text-embedding-flash"
DEFAULT_DIMENSION = 1024
BATCH = 20


def load_professor_documents(pack: Path) -> dict[str, dict]:
    connection = sqlite3.connect(f"file:{pack / 'lookup.sqlite3'}?mode=ro", uri=True)
    try:
        cursor = connection.execute(
            "select document_json from lookup_document "
            "where json_extract(document_json,'$.domain')='professor'"
        )
        documents: dict[str, dict] = {}
        for (raw,) in cursor:
            document = json.loads(raw)
            content = document.get("lookup_content")
            if isinstance(content, str):
                content = json.loads(content)
            documents[content["canonical_identity_id"]] = content
        return documents
    finally:
        connection.close()


def direction_text(document: dict) -> str:
    directions = [
        entry.get("name", "") for entry in (document.get("research_directions") or [])
    ]
    joined = "；".join(name for name in directions if name)
    if joined:
        return joined
    return (document.get("profile_summary") or "")[:200]


def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def embed(
    texts: list[str], *, endpoint: str, key: str, model: str, dimension: int
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH):
        body = {
            "model": model,
            "input": {"texts": texts[start : start + BATCH]},
            "parameters": {"text_type": "document", "dimension": dimension},
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read())
        vectors.extend(entry["embedding"] for entry in payload["output"]["embeddings"])
    return vectors


def select_names(
    projection: dict[str, dict],
    documents: dict[str, dict],
    *,
    top_n: int,
    require_directions: bool = True,
) -> list[str]:
    """Pick the top-N linked professors by paper count (scoreable ones only)."""
    rows = sorted(projection.values(), key=lambda row: -row["paper_count"])
    names: list[str] = []
    for row in rows:
        if require_directions and not (
            documents.get(row["professor_id"], {}).get("research_directions")
        ):
            continue
        names.append(row["name"])
        if len(names) >= top_n:
            break
    return names


def measure(
    *,
    projection: dict[str, dict],
    documents: dict[str, dict],
    names: list[str],
    top: int,
    endpoint: str,
    key: str,
    model: str = DEFAULT_MODEL,
    dimension: int = DEFAULT_DIMENSION,
) -> list[dict]:
    selected = []
    for name in names:
        rows = [row for row in projection.values() if row.get("name") == name]
        if not rows:
            selected.append({"name": name, "error": "not in projection"})
            continue
        row = rows[0]
        document = documents.get(row["professor_id"], {})
        selected.append(
            {
                "name": name,
                "professor_id": row["professor_id"],
                "paper_count": row["paper_count"],
                "has_directions": bool(document.get("research_directions")),
                "directions": direction_text(document),
                "titles": [
                    paper.get("title") or "" for paper in row["top_papers"][:top]
                ],
            }
        )

    texts: list[str] = []
    for entry in selected:
        if "error" in entry:
            continue
        texts.append(entry["directions"])
        texts.extend(entry["titles"])

    vectors = embed(texts, endpoint=endpoint, key=key, model=model, dimension=dimension)

    cursor = 0
    for entry in selected:
        if "error" in entry:
            continue
        direction_vector = vectors[cursor]
        cursor += 1
        similarities = []
        for _ in entry["titles"]:
            similarities.append(cosine(direction_vector, vectors[cursor]))
            cursor += 1
        entry["papers"] = len(similarities)
        entry["coherence"] = (
            round(sum(similarities) / len(similarities), 3) if similarities else None
        )
        entry.pop("titles", None)
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--projection", required=True)
    parser.add_argument("--names", default=None, help="comma separated display names")
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="instead of --names: the N linked professors with the most papers",
    )
    parser.add_argument(
        "--show-low",
        type=int,
        default=0,
        help="print the N lowest-scoring professors with their titles for review",
    )
    parser.add_argument(
        "--show-high",
        type=int,
        default=0,
        help="print the N highest-scoring professors with their titles for review",
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--dimension", type=int, default=DEFAULT_DIMENSION)
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "CANONICAL_V2_EMBEDDING_BASE_URL", "https://maas.qianwenaiapi.com/api/v1"
        ),
    )
    parser.add_argument("--api-key-env", default="CANONICAL_V2_EMBEDDING_API_KEY")
    args = parser.parse_args(argv)

    key = os.environ.get(args.api_key_env)
    if not key:
        print(f"missing embedding key: export {args.api_key_env}=…")
        return 2

    projection = json.loads(Path(args.projection).read_text())
    documents = load_professor_documents(Path(args.pack))
    if args.top_n:
        names = select_names(projection, documents, top_n=args.top_n)
    elif args.names:
        names = [name.strip() for name in args.names.split(",") if name.strip()]
    else:
        print("provide --names or --top-n")
        return 2
    endpoint = (
        args.base_url.rstrip("/") + "/services/embeddings/text-embedding/text-embedding"
    )
    results = measure(
        projection=projection,
        documents=documents,
        names=names,
        top=args.top,
        endpoint=endpoint,
        key=key,
        model=args.model,
        dimension=args.dimension,
    )

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2))

    print(f"{'name':<8}{'papers':>7}{'directions':>12}{'coherence':>11}")
    for entry in sorted(
        (item for item in results if "coherence" in item),
        key=lambda item: item["coherence"],
        reverse=True,
    ):
        print(
            f"{entry['name']:<8}{entry['papers']:>7}"
            f"{str(entry['has_directions']):>12}{entry['coherence']:>11}"
        )
    scored = sorted(
        (item for item in results if item.get("coherence") is not None),
        key=lambda item: item["coherence"],
    )
    for label, bucket in (("LOWEST", scored[: args.show_low]), ("HIGHEST", scored[-args.show_high :] if args.show_high else [])):
        if not bucket:
            continue
        print(f"\n=== {label} ===")
        for entry in bucket:
            document = documents.get(entry["professor_id"], {})
            directions = "；".join(
                item.get("name", "") for item in (document.get("research_directions") or [])
            )[:60]
            print(f"  {entry['name']} ({document.get('institution')}) papers={entry['paper_count']} coherence={entry['coherence']}")
            print(f"    directions: {directions}")
            for paper in projection[entry["professor_id"]]["top_papers"][:3]:
                print(f"    - {(paper.get('title') or '')[:88]}")
    print(f"\nwritten: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
