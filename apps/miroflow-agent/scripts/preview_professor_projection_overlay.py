"""Render professor claims with the projection overlay, for review before deploy.

Builds the same text the answer composer would produce (it calls the real
``_semantic_text``) for two groups:

- professors on the materialisation allowlist — they gain ``论文数`` and ``代表作``;
- professors in the review bucket — the overlay does not contain them, so the
  text must look exactly like today's.

Usage::

    CANONICAL_V2_PROFESSOR_PROJECTION=<allowlist.json> \
      python scripts/preview_professor_projection_overlay.py \
        --pack <serving pack> --allowlist <allowlist.json> \
        --review <review.json> --out <preview.md>
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data_agents.canonical_v2.knowledge_read import EvidenceItem  # noqa: E402
from src.data_agents.canonical_v2.knowledge_serving_isolated import (  # noqa: E402
    _semantic_text,
)
from src.data_agents.canonical_v2 import professor_projection_overlay as overlay_module  # noqa: E402


def load_professors(pack: Path) -> dict[str, dict]:
    import sqlite3

    connection = sqlite3.connect(f"file:{pack / 'lookup.sqlite3'}?mode=ro", uri=True)
    try:
        cursor = connection.execute(
            "select document_json from lookup_document "
            "where json_extract(document_json,'$.domain')='professor'"
        )
        documents = {}
        for (raw,) in cursor:
            content = json.loads(raw)["lookup_content"]
            if isinstance(content, str):
                content = json.loads(content)
            documents[content["canonical_identity_id"]] = content
        return documents
    finally:
        connection.close()


def payload_for(document: dict) -> dict:
    """The subset the claim builder reads (same shape the pack stores)."""
    keys = (
        "name",
        "canonical_name_zh",
        "institution",
        "department",
        "title",
        "email",
        "homepage",
        "profile_summary",
        "research_directions",
        "paper_count",
        "patent_count",
        "education_history",
        "work_history",
        "awards",
        "company_roles",
    )
    return {
        key: document[key] for key in keys if document.get(key) not in (None, "", [])
    }


def render(document: dict, professor_id: str) -> str:
    item = EvidenceItem(
        evidence_id="preview",
        object_id=professor_id,
        domain="professor",
        lane="exact",
        source_nature="local",
        source_locator="lookup:professor",
        snippet=json.dumps(payload_for(document), ensure_ascii=False),
        score=1.0,
    )
    return _semantic_text(item, str(document.get("name") or ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--allowlist", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args(argv)

    os.environ[overlay_module.ENV_VAR] = args.allowlist
    overlay_module.reset_overlay_cache()
    overlay = overlay_module.active_overlay()
    if overlay is None:
        print("overlay failed to load", file=sys.stderr)
        return 2

    documents = load_professors(Path(args.pack))
    allowlist = json.loads(Path(args.allowlist).read_text())
    review = json.loads(Path(args.review).read_text())

    lines = [
        "# 教授 claim 干跑（overlay 开 vs 关）",
        "",
        f"overlay: {len(overlay)} 条；素材: {len(documents)} 位教授",
        "",
        "## 白名单：会写进答案",
        "",
    ]
    for professor_id in list(allowlist)[: args.limit]:
        document = documents.get(professor_id)
        if not document:
            continue
        record = allowlist[professor_id]
        lines.append(f"**{record['name']}**（{record.get('coherence_top3')}）")
        lines.append("")
        lines.append(f"> {render(document, professor_id)}")
        lines.append("")

    lines += ["## 复核桶：保持沉默", ""]
    for professor_id in list(review)[: args.limit]:
        document = documents.get(professor_id)
        if not document:
            continue
        record = review[professor_id]
        lines.append(f"**{record['name']}**（{record.get('coherence_top3')}）")
        lines.append("")
        lines.append(f"> {render(document, professor_id)}")
        lines.append("")

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines))
    print("\n".join(lines[:14]))
    print(f"\nwritten: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
