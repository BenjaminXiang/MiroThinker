"""D1-a controlled technical vocabulary: replay, projection application and gate.

The fixture bundle is built exactly like the recorder builds it (same prompt
renderers, same batch composition, same hashes), so these tests exercise the real
replay path.  No provider is contacted: the recorded transcripts are the contract.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.data_agents.canonical_v2.domain_projection import (
    CATALOG_CONTENT_SHA256,
    CATALOG_SCHEMA_VERSION,
    CATALOG_VERSION,
)
from src.data_agents.canonical_v2.domain_projection_models import CompanyProjection
from src.data_agents.canonical_v2.tech_vocabulary import (
    BUNDLE_SCHEMA_VERSION,
    INDUCTION_BATCH_ID,
    MINIMUM_MAPPED_VALUE_COVERAGE,
    OUTPUT_SCHEMA_VERSION,
    PROMPT_VERSION,
    VOCABULARY_SCHEMA_VERSION,
    VocabularyIntegrityError,
    VocabularyQualityError,
    apply_vocabulary,
    artifact_document,
    assert_mapping_arity,
    assert_vocabulary_quality,
    attach_vocabulary_section,
    build_vocabulary_quality_section,
    induction_sample,
    load_recorded_vocabulary_bundle,
    mapping_batches,
    parse_concept_drafts,
    parse_mapping_lines,
    render_concept_catalogue,
    render_induction_prompt,
    render_mapping_prompt,
    replay_vocabulary_from_bundle,
    vocabulary_content_sha256,
)

TECH_VALUES = (
    "室内外配送机器人研发商",
    "智能餐饮机器人研发商",
    "社区收纳系统解决方案提供商",
    "PCB 打样及电路板生产商",
    "激光雷达传感器研发商",
)
INDUSTRY_VALUES = ("机器人", "物流运输")

CONCEPT_RECORDS = (
    {
        "id": "robotics.delivery",
        "name": "配送机器人",
        "definition": "面向室内外场景的自主配送机器人整机与系统。",
        "evidence": ["自述研发/生产该产品"],
        "kind": "technology",
    },
    {
        "id": "robotics.service",
        "name": "餐饮服务机器人",
        "definition": "面向餐饮场景的服务机器人整机与系统。",
        "evidence": ["自述研发/生产该产品"],
        "kind": "technology",
    },
    {
        "id": "electronics.pcb",
        "name": "PCB 制造",
        "definition": "印制电路板的设计、打样与生产。",
        "evidence": ["自述生产该产品"],
        "kind": "technology",
    },
    {
        "id": "sensing.lidar",
        "name": "激光雷达",
        "definition": "激光雷达整机与核心器件。",
        "evidence": ["自述研发/生产该产品"],
        "kind": "technology",
    },
    {
        "id": "industry.robotics",
        "name": "机器人行业",
        "definition": "以机器人整机或系统为主营的行业归属。",
        "evidence": ["行业自述"],
        "kind": "industry",
    },
    {
        "id": "industry.logistics",
        "name": "物流运输行业",
        "definition": "以物流运输服务为主营的行业归属。",
        "evidence": ["行业自述"],
        "kind": "industry",
    },
)

TECH_MAPPING = {
    "室内外配送机器人研发商": ("robotics.delivery",),
    "智能餐饮机器人研发商": ("robotics.service",),
    "社区收纳系统解决方案提供商": (),
    "PCB 打样及电路板生产商": ("electronics.pcb",),
    "激光雷达传感器研发商": ("sensing.lidar",),
}
INDUSTRY_MAPPING = {
    "机器人": ("industry.robotics",),
    "物流运输": ("industry.logistics",),
}

FIXTURE_ARTIFACT_DIR = Path(__file__).resolve().parent / "fixtures"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _jsonl(records: tuple[dict[str, Any], ...]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records)


def _fixture_bundle(
    *,
    tech_values: tuple[str, ...] = TECH_VALUES,
    industry_values: tuple[str, ...] = INDUSTRY_VALUES,
    tech_mapping: dict[str, tuple[str, ...]] | None = None,
    industry_mapping: dict[str, tuple[str, ...]] | None = None,
    concept_records: tuple[dict[str, Any], ...] = CONCEPT_RECORDS,
    batch_size: int = 2,
) -> dict[str, Any]:
    tech_mapping = TECH_MAPPING if tech_mapping is None else tech_mapping
    industry_mapping = (
        INDUSTRY_MAPPING if industry_mapping is None else industry_mapping
    )
    concepts = parse_concept_drafts(_jsonl(concept_records))
    concepts_by_id = {concept.concept_id: concept for concept in concepts}
    catalogue = render_concept_catalogue(concepts)
    concept_ids = sorted(concepts_by_id)
    sample = induction_sample(sorted(tech_values))
    calls: list[dict[str, Any]] = []
    induction_output = _jsonl(concept_records)
    calls.append(
        {
            "call_id": f"induct:{INDUCTION_BATCH_ID}",
            "kind": "induct",
            "input_value_ids": list(sample),
            "input_sha256": _canonical_sha256(list(sample)),
            "raw_output": induction_output,
            "output_sha256": _sha256(induction_output),
        }
    )
    for field, values, mapping in (
        ("tech_tags", tech_values, tech_mapping),
        ("industry", industry_values, industry_mapping),
    ):
        for index, batch in enumerate(
            mapping_batches(sorted(values), batch_size=batch_size)
        ):
            output = _jsonl(
                tuple(
                    {"v": value, "c": list(mapping.get(value, ()))} for value in batch
                )
            )
            calls.append(
                {
                    "call_id": f"map:{field}:{index:04d}",
                    "kind": "value_mapping",
                    "input_value_ids": list(batch),
                    "input_sha256": _canonical_sha256(list(batch)),
                    "raw_output": output,
                    "output_sha256": _sha256(output),
                }
            )
    prompts = {
        "induct": {
            "sha256": _sha256(render_induction_prompt(sample, max_concepts=240)),
            "text": render_induction_prompt(sample, max_concepts=240),
        },
        "map": {
            "sha256": _sha256(
                render_mapping_prompt(
                    "tech_tags",
                    ["<sample>"],
                    catalogue=catalogue,
                    concept_ids=concept_ids,
                )
            ),
            "text": render_mapping_prompt(
                "tech_tags",
                ["<sample>"],
                catalogue=catalogue,
                concept_ids=concept_ids,
            ),
        },
    }
    payload: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "provider": "fixture-provider",
        "model": "fixture-model",
        "endpoint": "http://fixture.invalid/v1",
        "prompt_version": PROMPT_VERSION,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "temperature": 0.0,
        "pythonhashseed_invariant": True,
        "prompts": prompts,
        "source_value_counts": {
            "industry": len(set(industry_values)),
            "tech_tags": len(set(tech_values)),
        },
        "induction_sample_values": list(sample),
        "induction_max_concepts": 240,
        "mapping_batch_size": batch_size,
        "calls": sorted(calls, key=lambda item: item["call_id"]),
        "call_count": len(calls),
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }
    payload["content_sha256"] = vocabulary_content_sha256(payload)
    return payload


def _reseal(bundle: dict[str, Any]) -> dict[str, Any]:
    """Recompute every hash a tampering author would have to recompute."""
    resealed = deepcopy(bundle)
    for call in resealed["calls"]:
        call["output_sha256"] = _sha256(call["raw_output"])
        call["input_sha256"] = _canonical_sha256(call["input_value_ids"])
    resealed["call_count"] = len(resealed["calls"])
    resealed["content_sha256"] = vocabulary_content_sha256(resealed)
    return resealed


def _bundle_path(tmp_path: Path, bundle: dict[str, Any]) -> Path:
    path = tmp_path / "recorded-vocabulary-decision-bundle.json"
    path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    return path


def _company_payload() -> dict[str, Any]:
    return {
        "id": "company-c-fixture",
        "name": "深圳市普渡科技有限公司",
        "normalized_name": "深圳市普渡科技有限公司",
        "industry": {"reference_id": "source-reference:industry", "name": "机器人"},
        "industry_tags": [
            {"reference_id": "source-reference:industry", "name": "机器人"}
        ],
        "tech_tags": [
            {
                "reference_id": "source-reference:tag-1",
                "name": "室内外配送机器人研发商",
            },
            {
                "reference_id": "source-reference:tag-2",
                "name": "社区收纳系统解决方案提供商",
            },
        ],
    }


# --------------------------------------------------------------------------- #
# replay
# --------------------------------------------------------------------------- #


def test_replay_is_deterministic_and_separates_mapped_from_unmapped() -> None:
    bundle = _fixture_bundle()
    first = replay_vocabulary_from_bundle(bundle)
    second = replay_vocabulary_from_bundle(deepcopy(bundle))

    assert artifact_document(first) == artifact_document(second)
    assert first.content_sha256 == second.content_sha256
    assert first.schema_version == VOCABULARY_SCHEMA_VERSION
    assert first.llm_call_count == bundle["call_count"]
    assert [concept.concept_id for concept in first.concepts] == sorted(
        concept["id"] for concept in CONCEPT_RECORDS
    )
    assert first.concept_ids_for("tech_tags", "室内外配送机器人研发商") == (
        "robotics.delivery",
    )
    assert first.concept_names(("robotics.delivery",)) == ("配送机器人",)
    assert first.concept_ids_for("tech_tags", "社区收纳系统解决方案提供商") == ()
    assert [item.value for item in first.unmapped] == ["社区收纳系统解决方案提供商"]
    assert first.source_value_counts == {"industry": 2, "tech_tags": 5}


def test_bundle_loader_rejects_a_modified_transcript(tmp_path: Path) -> None:
    bundle = _fixture_bundle()
    bundle["calls"][1]["raw_output"] = bundle["calls"][1]["raw_output"] + "\n"
    bundle["content_sha256"] = vocabulary_content_sha256(bundle)

    with pytest.raises(VocabularyIntegrityError, match="transcript was modified"):
        load_recorded_vocabulary_bundle(_bundle_path(tmp_path, bundle))


def test_replay_rejects_a_lost_mapping_call() -> None:
    bundle = _fixture_bundle()
    bundle["calls"] = [
        call for call in bundle["calls"] if call["call_id"] != "map:tech_tags:0001"
    ]

    with pytest.raises(
        VocabularyIntegrityError, match="do not cover the recorded value set"
    ):
        replay_vocabulary_from_bundle(_reseal(bundle))


def test_replay_rejects_a_concept_outside_the_vocabulary() -> None:
    bundle = _fixture_bundle()
    for call in bundle["calls"]:
        if call["call_id"] == "map:tech_tags:0000":
            call["raw_output"] = call["raw_output"].replace(
                "robotics.delivery", "robotics.invented"
            )

    with pytest.raises(VocabularyIntegrityError, match="outside the vocabulary"):
        replay_vocabulary_from_bundle(_reseal(bundle))


def test_replay_rejects_a_malformed_transcript_line() -> None:
    bundle = _fixture_bundle()
    for call in bundle["calls"]:
        if call["call_id"] == "map:tech_tags:0000":
            call["raw_output"] = "this is not JSON\n" + call["raw_output"]

    with pytest.raises(VocabularyIntegrityError, match="is not JSON"):
        replay_vocabulary_from_bundle(_reseal(bundle))


def test_replay_rejects_a_drifted_prompt() -> None:
    bundle = _fixture_bundle()
    bundle["prompts"]["map"]["text"] = bundle["prompts"]["map"]["text"] + "extra rule"
    bundle["prompts"]["map"]["sha256"] = _sha256(bundle["prompts"]["map"]["text"])

    with pytest.raises(VocabularyIntegrityError, match="prompt map drifted"):
        replay_vocabulary_from_bundle(_reseal(bundle))


def test_replay_rejects_a_changed_source_value_set() -> None:
    bundle = _fixture_bundle()
    bundle["source_value_counts"]["tech_tags"] = 4

    with pytest.raises(
        VocabularyIntegrityError, match="do not cover the recorded value set"
    ):
        replay_vocabulary_from_bundle(_reseal(bundle))


def test_load_rejects_an_edited_bundle(tmp_path: Path) -> None:
    bundle = _fixture_bundle()
    bundle["model"] = "another-model"

    with pytest.raises(VocabularyIntegrityError, match="content_sha256 does not match"):
        load_recorded_vocabulary_bundle(_bundle_path(tmp_path, bundle))


def test_single_valued_field_cannot_map_to_several_concepts() -> None:
    parsed = {"机器人": ("industry.robotics", "industry.logistics")}

    with pytest.raises(VocabularyIntegrityError, match="at most one concept"):
        assert_mapping_arity("industry", parsed)


def test_mapping_parser_rejects_an_unrequested_value() -> None:
    output = _jsonl(({"v": "别的标签", "c": []},))

    with pytest.raises(
        VocabularyIntegrityError, match="not one of the requested values"
    ):
        parse_mapping_lines(output, expected_values=["机器人"], concept_ids=frozenset())


# --------------------------------------------------------------------------- #
# projection application
# --------------------------------------------------------------------------- #


def test_application_publishes_concepts_and_keeps_unmapped_verbatim() -> None:
    vocabulary = replay_vocabulary_from_bundle(_fixture_bundle())
    applied, unmapped = apply_vocabulary("company", _company_payload(), vocabulary)

    assert [item["name"] for item in applied["tech_tags"]] == [
        "社区收纳系统解决方案提供商",
        "配送机器人",
    ]
    assert applied["industry"]["name"] == "机器人行业"
    assert [item["name"] for item in applied["industry_tags"]] == ["机器人行业"]
    assert [item.value for item in unmapped] == ["社区收纳系统解决方案提供商"]
    # the passthrough reference id is the one the build derives from the raw value
    passthrough = next(
        item
        for item in applied["tech_tags"]
        if item["name"] == "社区收纳系统解决方案提供商"
    )
    assert passthrough == {
        "reference_id": (
            "source-reference:"
            + hashlib.sha256(
                "社区收纳系统解决方案提供商".casefold().encode("utf-8")
            ).hexdigest()
        ),
        "name": "社区收纳系统解决方案提供商",
    }


def test_applied_tags_validate_against_the_projection_model() -> None:
    vocabulary = replay_vocabulary_from_bundle(_fixture_bundle())
    applied, _ = apply_vocabulary("company", _company_payload(), vocabulary)

    projection = CompanyProjection.model_validate(
        {
            **applied,
            "canonical_identity_id": "company-c-fixture",
            "identity_decision_id": "identity-decision:fixture",
            "inclusion_decision_id": "inclusion:fixture",
            "projection_version": "domain-projection-v1",
            "catalog_schema_version": CATALOG_SCHEMA_VERSION,
            "catalog_version": CATALOG_VERSION,
            "catalog_content_sha256": CATALOG_CONTENT_SHA256,
            "as_of": "2026-09-15T00:00:00+00:00",
            "last_updated": "2026-09-15T00:00:00+00:00",
            "quality_status": "partial",
            "run_id": "fixture-run",
            "content_sha256": "0" * 64,
            "release_id": "candidate-fixture",
            "profile_summary": "企业简介。",
            "technology_route_summary": "技术路线。",
            "evidence": [
                {
                    "assertion_id": "assertion:fixture",
                    "decision_id": "field-decision:fixture",
                    "field_path": "tech_tags",
                }
            ],
            "field_lineage": [
                {
                    "field_path": "tech_tags",
                    "decision_id": "field-decision:fixture",
                    "supporting_assertion_ids": ["assertion:fixture"],
                }
            ],
        },
        context={"allow_unbound_projection_hash": True},
    )

    assert [item.name for item in projection.tech_tags] == [
        "社区收纳系统解决方案提供商",
        "配送机器人",
    ]
    assert projection.industry is not None and projection.industry.name == "机器人行业"


def test_other_domains_are_untouched() -> None:
    vocabulary = replay_vocabulary_from_bundle(_fixture_bundle())
    payload = {"tech_tags": [{"reference_id": "x", "name": "室内外配送机器人研发商"}]}
    applied, unmapped = apply_vocabulary("professor", payload, vocabulary)

    assert applied == payload
    assert unmapped == ()


# --------------------------------------------------------------------------- #
# quality section, gate and report wiring
# --------------------------------------------------------------------------- #


def test_quality_section_counts_coverage_and_published_values() -> None:
    vocabulary = replay_vocabulary_from_bundle(_fixture_bundle())
    section = build_vocabulary_quality_section(
        vocabulary=vocabulary,
        published_values={"tech_tags": ["配送机器人", "社区收纳系统解决方案提供商"]},
        collection_gap={"tags_per_company": 1.0, "companies_without_tech_tags": 1601},
        category_probes={"机器人": {"before": 422, "after": 500}},
    )

    assert section["fields"]["tech_tags"] == {
        "source_values": 5,
        "mapped_values": 4,
        "unmapped_values": 1,
        "coverage": 0.8,
    }
    assert section["concepts"] == {"total": 6, "technology": 4, "industry": 2}
    assert section["llm_calls"] == 5
    assert section["published"]["tech_tags"] == {
        "published_values": 2,
        "concept_names": 1,
        "unmapped_passthrough": 1,
        "unrecognized": 0,
    }
    assert section["collection_gap"]["companies_without_tech_tags"] == 1601
    assert section["minimum_coverage"] == MINIMUM_MAPPED_VALUE_COVERAGE
    assert section["unmapped_examples"] == ["社区收纳系统解决方案提供商"]


def _passing_bundle() -> dict[str, Any]:
    """A fixture whose coverage clears the gate: every value maps to a concept."""
    extra = CONCEPT_RECORDS + (
        {
            "id": "services.storage",
            "name": "仓储收纳服务",
            "definition": "面向家庭与企业的仓储收纳系统与服务。",
            "evidence": ["自述提供该服务"],
            "kind": "technology",
        },
    )
    mapping = dict(TECH_MAPPING)
    mapping["社区收纳系统解决方案提供商"] = ("services.storage",)
    return _fixture_bundle(tech_mapping=mapping, concept_records=extra)


def test_gate_rejects_coverage_below_the_floor() -> None:
    vocabulary = replay_vocabulary_from_bundle(_fixture_bundle())
    section = build_vocabulary_quality_section(vocabulary=vocabulary)

    assert section["fields"]["tech_tags"]["coverage"] == 0.8
    with pytest.raises(VocabularyQualityError, match="below the"):
        assert_vocabulary_quality(section)


def test_gate_rejects_a_published_value_without_a_decision() -> None:
    vocabulary = replay_vocabulary_from_bundle(_passing_bundle())
    section = build_vocabulary_quality_section(
        vocabulary=vocabulary,
        published_values={"tech_tags": ["配送机器人", "凭空出现的标签"]},
    )

    assert section["fields"]["tech_tags"]["coverage"] == 1.0
    with pytest.raises(VocabularyQualityError, match="neither concepts nor recorded"):
        assert_vocabulary_quality(section)


def test_collection_gap_does_not_block_the_gate() -> None:
    vocabulary = replay_vocabulary_from_bundle(_passing_bundle())
    section = build_vocabulary_quality_section(
        vocabulary=vocabulary,
        published_values={"tech_tags": ["配送机器人", "仓储收纳服务"]},
        collection_gap={"tags_per_company": 1.0, "companies_without_tech_tags": 1601},
    )

    assert section["collection_gap"]["tags_per_company"] == 1.0
    assert section["published"]["tech_tags"]["unrecognized"] == 0
    assert_vocabulary_quality(section)


def test_attach_section_merges_idempotently_and_keeps_the_report() -> None:
    vocabulary = replay_vocabulary_from_bundle(_fixture_bundle())
    section = build_vocabulary_quality_section(vocabulary=vocabulary)
    report = {
        "schema_version": "canonical-v2-publication-quality-report-v1",
        "release_id": "r",
    }

    merged = attach_vocabulary_section(report, section)
    assert merged["vocabulary"] == section
    assert attach_vocabulary_section(merged, section) == merged
    assert report == {
        "schema_version": "canonical-v2-publication-quality-report-v1",
        "release_id": "r",
    }
    with pytest.raises(VocabularyQualityError, match="already carries a different"):
        attach_vocabulary_section(
            merged, {**section, "llm_calls": section["llm_calls"] + 1}
        )
