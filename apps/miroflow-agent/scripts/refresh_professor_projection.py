"""Refresh the professor paper projection end to end and report the metrics.

Gate 3 produced the allowlist with three manual steps (build the projection,
score coherence, join by hand). Gate 4 needs this to be one reproducible command
that also emits the numbers we track: link coverage, template share, allowlist
size, coherence distribution.

The embedding step needs the serving endpoint:

    export CANONICAL_V2_EMBEDDING_API_KEY=...
    export CANONICAL_V2_EMBEDDING_BASE_URL=https://maas.qianwenaiapi.com/api/v1

Usage::

    python scripts/refresh_professor_projection.py \
        --pack /var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth \
        --out .agents/runs/professor-paper-slice/refresh \
        --threshold 0.33

Writes ``projection-report.json``, ``coherence-all.json``,
``professor-projection-allowlist.json``, ``professor-projection-review.json``,
``metrics.json`` and ``metrics.md``. ``--skip-coherence`` reuses a previous
``coherence-all.json`` (useful when only the gate or the pack changed).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import sys
from datetime import datetime, timezone

_SCRIPTS = Path(__file__).resolve().parent


def _load(name: str):
    path = _SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load("build_professor_paper_projection")
coherence = _load("measure_professor_paper_coherence")


def compute_metrics(
    *,
    report: dict,
    scores: list[dict],
    allowlist: dict,
    review: dict,
    threshold: float,
) -> dict:
    """Turn the artefacts into the numbers we track across refreshes."""
    values = sorted(
        entry["coherence_top3"]
        for entry in scores
        if entry.get("coherence_top3") is not None
    )
    population = report["population"]
    gap = report["document_gap"]
    scored = len(values)
    unscorable = population["projected_professors"] - scored
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "population": {
            "professors": population["professors"],
            "papers": population["papers"],
            "edges": population["edges"],
            "linked_professors": population["professors_with_edges"],
            "linked_pct": round(
                100 * population["professors_with_edges"] / max(population["professors"], 1),
                1,
            ),
            "projected_professors": population["projected_professors"],
            "rejected_professors": population["rejected_professors"],
            "rejected_by_reason": population["rejected_by_reason"],
            "email_dropped": population["email_dropped"],
        },
        "documents": {
            "papers_with_professor_ids": gap["papers_with_professor_ids"],
            "professors_with_paper_count": gap["professors_with_paper_count"],
            "professors_with_directions": gap["professors_with_directions"],
            "template_summaries": gap["template_summaries"],
            "template_pct": gap["template_summary_pct"],
        },
        "coherence": {
            "threshold": threshold,
            "scored": scored,
            "unscorable_no_directions": unscorable,
            "median": round(statistics.median(values), 3) if values else None,
            "p10": round(values[int(0.1 * (len(values) - 1))], 3) if values else None,
            "allowlist": len(allowlist),
            "review": len(review),
            "allowlist_pct_of_scored": (
                round(100 * len(allowlist) / scored, 1) if scored else 0.0
            ),
        },
        "overlay": {
            "effective_records": sum(
                1 for row in allowlist.values() if "duplicate_name" not in row["flags"]
            ),
            "flagged_records": sum(1 for row in allowlist.values() if row["flags"]),
            "papers_covered": sum(row["paper_count"] for row in allowlist.values()),
        },
    }


def render_markdown(metrics: dict) -> str:
    population = metrics["population"]
    documents = metrics["documents"]
    coherence_metrics = metrics["coherence"]
    overlay = metrics["overlay"]
    return "\n".join(
        [
            "# 教授×论文投影：刷新指标",
            "",
            f"生成时间：{metrics['generated_at']}",
            "",
            "| 指标 | 值 |",
            "|---|---|",
            f"| 教授 / 论文 / 边 | {population['professors']} / {population['papers']} / {population['edges']} |",
            f"| 有链接教授 | {population['linked_professors']}（{population['linked_pct']}%） |",
            f"| 通过记录门的教授 | {population['projected_professors']}（拒 {population['rejected_professors']}） |",
            f"| 论文有 professor_ids | {documents['papers_with_professor_ids']} |",
            f"| 教授有 paper_count | {documents['professors_with_paper_count']} |",
            f"| 模板简介 | {documents['template_summaries']}（{documents['template_pct']}%） |",
            f"| 可评分（有方向） | {coherence_metrics['scored']} |",
            f"| top-3 中位 / p10 | {coherence_metrics['median']} / {coherence_metrics['p10']} |",
            f"| 白名单（≥{coherence_metrics['threshold']}） | {coherence_metrics['allowlist']}（占可评分 {coherence_metrics['allowlist_pct_of_scored']}%） |",
            f"| 复核桶 | {coherence_metrics['review']} |",
            f"| overlay 生效 / 带旗标 | {overlay['effective_records']} / {overlay['flagged_records']} |",
            f"| 白名单覆盖论文 | {overlay['papers_covered']} |",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--threshold", type=float, default=0.33)
    parser.add_argument("--top-papers", type=int, default=builder.TOP_PAPERS)
    parser.add_argument(
        "--skip-coherence",
        action="store_true",
        help="reuse <out>/coherence-all.json instead of calling the embedding API",
    )
    args = parser.parse_args(argv)

    pack = Path(args.pack)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    professors = builder.load_documents(pack, "professor")
    papers = builder.load_documents(pack, "paper")
    edges = builder.load_edges(pack, out / "edges.jsonl")
    projection, report = builder.build_projection(
        professors, papers, edges, top_papers=args.top_papers
    )
    (out / "professor-projection.json").write_text(
        json.dumps(projection, ensure_ascii=False, indent=2)
    )
    (out / "projection-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )

    scores_path = out / "coherence-all.json"
    if args.skip_coherence and scores_path.exists():
        scores = json.loads(scores_path.read_text())
    else:
        names = coherence.select_names(projection, professors, top_n=len(projection))
        endpoint = (
            coherence.os.environ.get(
                "CANONICAL_V2_EMBEDDING_BASE_URL", "https://maas.qianwenaiapi.com/api/v1"
            ).rstrip("/")
            + "/services/embeddings/text-embedding/text-embedding"
        )
        key = coherence.os.environ.get("CANONICAL_V2_EMBEDDING_API_KEY")
        if not key:
            print("missing CANONICAL_V2_EMBEDDING_API_KEY", file=sys.stderr)
            return 2
        scores = coherence.measure(
            projection=projection,
            documents=professors,
            names=names,
            top=5,
            endpoint=endpoint,
            key=key,
        )
        scores_path.write_text(json.dumps(scores, ensure_ascii=False, indent=2))

    allowlist: dict[str, dict] = {}
    review: dict[str, dict] = {}
    for entry in scores:
        score = entry.get("coherence_top3")
        if score is None:
            continue
        row = projection[entry["professor_id"]]
        target = allowlist if score >= args.threshold else review
        target[entry["professor_id"]] = {
            "name": row["name"],
            "institution": row["institution"],
            "paper_count": row["paper_count"],
            "coherence_top3": score,
            "coherence_mean": entry.get("coherence"),
            "top_papers": row["top_papers"],
            "flags": row["flags"],
        }
    (out / "professor-projection-allowlist.json").write_text(
        json.dumps(allowlist, ensure_ascii=False, indent=2)
    )
    (out / "professor-projection-review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2)
    )

    metrics = compute_metrics(
        report=report,
        scores=scores,
        allowlist=allowlist,
        review=review,
        threshold=args.threshold,
    )
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    markdown = render_markdown(metrics)
    (out / "metrics.md").write_text(markdown)

    print(markdown)
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
