#!/usr/bin/env python3
"""Replay counters for D1-a on the read-only run15 copy.

Reports, before and after the controlled vocabulary is applied to the published
company tag fields:

  * distinct ``tech_tags`` values -> distinct published values (concepts + the
    unmapped values that stay verbatim) and mapping coverage;
  * tags per company;
  * category-probe support: the assessment's substring method (comparable
    before/after) and a concept-level count with the probe's concept set printed,
    so the reviewer can see exactly which concepts answer the probe.

Also verifies that the packaged artifact is the recorded bundle's replay output.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
APP_ROOT = REPO_ROOT / "apps" / "miroflow-agent"
sys.path.insert(0, str(APP_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from extract_vocabulary_inputs import (  # noqa: E402
    CATEGORY_PROBES,
    load_documents,
    probe_support,
    reference_names,
)
from src.data_agents.canonical_v2.tech_vocabulary import (  # noqa: E402
    TECH_TAG_FIELD,
    apply_vocabulary,
    artifact_document,
    load_packaged_vocabulary,
    load_recorded_vocabulary_bundle,
    replay_vocabulary_from_bundle,
)

DEFAULT_OUT = REPO_ROOT / ".agents/runs/d1a-tech-vocabulary/out"
DEFAULT_BUNDLE = DEFAULT_OUT / "recorded-vocabulary-decision-bundle.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lookup", type=Path, default=Path("/tmp/d1a-scratch/lookup-run15.sqlite3")
    )
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    documents = load_documents(args.lookup)
    vocabulary = load_packaged_vocabulary()

    bundle = load_recorded_vocabulary_bundle(args.bundle)
    replayed = artifact_document(replay_vocabulary_from_bundle(bundle))
    if replayed != artifact_document(vocabulary):
        raise SystemExit(
            "packaged vocabulary is not the replay output of the recorded bundle"
        )

    before_values: Counter[str] = Counter()
    before_tags_per_company: list[int] = []
    after_values: Counter[str] = Counter()
    after_tags_per_company: list[int] = []
    companies_with_concepts = 0
    concept_rows: Counter[str] = Counter()
    unmapped_published: Counter[str] = Counter()
    passthrough_tag_rows = 0
    for document in documents:
        raw_names = reference_names(document.get(TECH_TAG_FIELD))
        before_values.update(raw_names)
        before_tags_per_company.append(len(raw_names))
        applied, _unmapped = apply_vocabulary("company", document, vocabulary)
        published = reference_names(applied.get(TECH_TAG_FIELD))
        after_values.update(published)
        after_tags_per_company.append(len(published))
        concept_names = [item for item in published if vocabulary.is_concept_name(item)]
        passthrough_tag_rows += len(published) - len(concept_names)
        unmapped_published.update(
            item for item in published if not vocabulary.is_concept_name(item)
        )
        if concept_names:
            companies_with_concepts += 1
        for name in concept_names:
            concept = vocabulary.concept_by_name(name)
            assert concept is not None
            concept_rows[concept.concept_id] += 1

    probes: dict[str, Any] = {}
    for probe in CATEGORY_PROBES:
        matched = tuple(
            sorted(
                concept.concept_id
                for concept in vocabulary.concepts
                if probe in concept.canonical_name or probe in concept.definition
            )
        )
        matched_names = {vocabulary.concept_name(item) for item in matched}
        companies = 0
        if matched_names:
            for document in documents:
                applied, _ = apply_vocabulary("company", document, vocabulary)
                if matched_names & set(reference_names(applied.get(TECH_TAG_FIELD))):
                    companies += 1
        probes[probe] = {
            "concepts": list(matched),
            "concept_names": sorted(matched_names),
            "companies_via_concepts": companies,
        }

    after_probe_support = probe_support(
        [
            {
                TECH_TAG_FIELD: [
                    {"name": name}
                    for name in reference_names(
                        apply_vocabulary("company", document, vocabulary)[0].get(
                            TECH_TAG_FIELD
                        )
                    )
                ]
            }
            for document in documents
        ],
        CATEGORY_PROBES,
    )

    tech_tag_mappings = [
        item for item in vocabulary.mappings if item.field == TECH_TAG_FIELD
    ]
    tech_tag_unmapped = [
        item for item in vocabulary.unmapped if item.field == TECH_TAG_FIELD
    ]
    report = {
        "lookup_path": str(args.lookup),
        "company_documents": len(documents),
        "vocabulary": {
            "content_sha256": vocabulary.content_sha256,
            "bundle_content_sha256": vocabulary.bundle_content_sha256,
            "concepts_total": len(vocabulary.concepts),
            "concepts_technology": sum(
                1 for item in vocabulary.concepts if item.kind == "technology"
            ),
            "concepts_industry": sum(
                1 for item in vocabulary.concepts if item.kind == "industry"
            ),
            "llm_calls": vocabulary.llm_call_count,
            "provider": vocabulary.provider,
            "model": vocabulary.model,
            "prompt_version": vocabulary.prompt_version,
        },
        "tech_tags": {
            "distinct_values_before": len(before_values),
            "rows_before": sum(before_values.values()),
            "mapped_values": len(tech_tag_mappings),
            "unmapped_values": len(tech_tag_unmapped),
            "coverage": round(len(tech_tag_mappings) / len(before_values), 6),
            "distinct_values_after": len(after_values),
            "concept_rows_after": sum(concept_rows.values()),
            "passthrough_rows_after": passthrough_tag_rows,
            "largest_concepts": [
                {"concept": name, "companies": count}
                for name, count in concept_rows.most_common(12)
            ],
            "unmapped_published_values": len(unmapped_published),
        },
        "industry": {
            "values": len(
                [item for item in vocabulary.source_value_counts if item == "industry"]
            )
            and vocabulary.source_value_counts["industry"],
            "mapped_values": len(
                [item for item in vocabulary.mappings if item.field == "industry"]
            ),
            "concepts": [
                concept.canonical_name
                for concept in vocabulary.concepts
                if concept.kind == "industry"
            ],
        },
        "tags_per_company": {
            "before_mean": round(sum(before_tags_per_company) / len(documents), 6),
            "after_mean": round(sum(after_tags_per_company) / len(documents), 6),
            "before_companies_without": sum(
                1 for count in before_tags_per_company if count == 0
            ),
            "after_companies_without": sum(
                1 for count in after_tags_per_company if count == 0
            ),
            "after_companies_with_concepts": companies_with_concepts,
            "after_distribution": dict(
                sorted(Counter(str(count) for count in after_tags_per_company).items())
            ),
            "after_passthrough_only_companies": sum(
                1 for count, _ in zip(after_tags_per_company, documents) if count > 0
            )
            - companies_with_concepts,
        },
        "category_probe_support": {
            probe: {
                "before_tag_fields": before_probe,
                "after_tag_fields": after_probe_support[probe],
                "after_concepts": probes[probe],
            }
            for probe, before_probe in probe_support(documents, CATEGORY_PROBES).items()
        },
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "vocabulary-replay-counts.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
