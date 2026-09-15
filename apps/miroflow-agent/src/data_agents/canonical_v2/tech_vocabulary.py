"""Controlled technical vocabulary for the Canonical V2 company tag fields.

``tech_tags`` and ``industry`` are free text in the source batches: run15
publishes 4,945 distinct ``tech_tags`` values for 5,485 rows, 90.2% of them used
once, and 41 overlapping ``industry`` labels.  Category queries therefore cannot
recall a category (``送餐`` matches no company in the tag fields).

This module owns the controlled concept vocabulary that replaces them, and it
owns the *replay* of the LLM decisions that produced it:

* the mapping is induced **offline** by batched LLM calls and recorded as a
  decision bundle (provider, model, prompt version, exact transcripts);
* a rebuild **replays** that bundle - it never calls a provider - so the published
  tag values are reproducible byte for byte;
* a value the LLM could not decide is *not* guessed: it stays published verbatim
  and is counted as unmapped, which is what keeps the coverage number honest.

Projection application happens at the same seam as the D0 cleaning rules
(``domain_projection._ProjectionContext.project_identity``), so lookup documents,
the vector embedded content and the Postgres projection inherit one mapping.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal, cast

from pydantic import Field, JsonValue, ValidationError

from .contracts import ContractModel, NonEmptyStr, Sha256


VOCABULARY_SCHEMA_VERSION = "canonical-v2-technical-vocabulary-v1"
BUNDLE_SCHEMA_VERSION = "canonical-v2-recorded-vocabulary-decision-bundle-v1"
PROMPT_VERSION = "d1a-tech-vocabulary-prompts-v1"
OUTPUT_SCHEMA_VERSION = "d1a-tech-vocabulary-output-v1"

VOCABULARY_ARTIFACT_FILENAME = "technical-vocabulary-v1.json"
VOCABULARY_QUALITY_SECTION_KEY = "vocabulary"

MAPPING_BATCH_SIZE = 100
INDUCTION_SAMPLE_SIZE = 600
INDUCTION_BATCH_ID = "0000"

TECH_TAG_FIELD = "tech_tags"
INDUSTRY_FIELD = "industry"
INDUSTRY_TAG_FIELD = "industry_tags"
MAPPED_FIELDS = (TECH_TAG_FIELD, INDUSTRY_FIELD)
# ``industry`` is published as a single reference, so its values may only map to
# one concept; any other field publishes a list.
SINGLE_VALUED_FIELDS = frozenset({INDUSTRY_FIELD})
# ``industry_tags`` is a pure duplicate of ``industry`` (run15: 5,480 equal rows,
# 0 differing) and has no reader, so it is mapped through the industry table
# instead of getting its own concepts.  Retiring the declaration is a catalog
# revision and stays out of this module.
FIELD_SOURCE_KEY = {INDUSTRY_TAG_FIELD: INDUSTRY_FIELD}

MINIMUM_MAPPED_VALUE_COVERAGE = 0.90
UNMAPPED_EXAMPLE_LIMIT = 20

ConceptKind = Literal["technology", "industry"]
_SOURCE_REFERENCE_PREFIX = "source-reference:"
_JSONL_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*$")


class VocabularyIntegrityError(RuntimeError):
    """The vocabulary, its bundle or a published projection broke the contract."""


class VocabularyQualityError(ValueError):
    """The published tags do not satisfy the controlled-vocabulary gate."""


class VocabularyConcept(ContractModel):
    """One controlled concept: name, definition and qualifying evidence forms."""

    concept_id: NonEmptyStr
    canonical_name: NonEmptyStr
    definition: NonEmptyStr
    acceptable_evidence_forms: tuple[NonEmptyStr, ...] = Field(min_length=1)
    kind: ConceptKind


class TagConceptMapping(ContractModel):
    """A raw tag value and the controlled concepts it maps into."""

    field: str
    value: NonEmptyStr
    concept_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)


class UnmappedTagValue(ContractModel):
    """A raw value the induction could not decide; it stays published verbatim."""

    field: str
    value: NonEmptyStr
    reason: Literal["undecided"] = "undecided"


class TechnicalVocabulary(ContractModel):
    """The packaged controlled vocabulary (the build input)."""

    schema_version: str
    artifact_version: NonEmptyStr
    prompt_version: NonEmptyStr
    output_schema_version: NonEmptyStr
    provider: NonEmptyStr
    model: NonEmptyStr
    bundle_content_sha256: Sha256
    llm_call_count: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    source_value_counts: dict[str, int]
    concepts: tuple[VocabularyConcept, ...]
    mappings: tuple[TagConceptMapping, ...]
    unmapped: tuple[UnmappedTagValue, ...]
    content_sha256: Sha256

    def concept_name(self, concept_id: str) -> str:
        for concept in self.concepts:
            if concept.concept_id == concept_id:
                return concept.canonical_name
        raise VocabularyIntegrityError(f"unknown vocabulary concept: {concept_id}")

    def concept_names(self, concept_ids: Iterable[str]) -> tuple[str, ...]:
        return tuple(sorted({self.concept_name(item) for item in concept_ids}))

    def concept_by_name(self, canonical_name: str) -> VocabularyConcept | None:
        for concept in self.concepts:
            if concept.canonical_name == canonical_name:
                return concept
        return None

    def concept_ids_for(self, field: str, value: str) -> tuple[str, ...]:
        source_field = FIELD_SOURCE_KEY.get(field, field)
        for mapping in self.mappings:
            if mapping.field == source_field and mapping.value == value:
                return mapping.concept_ids
        return ()

    def is_concept_name(self, value: str) -> bool:
        return self.concept_by_name(value) is not None

    def unmapped_values(self, field: str) -> tuple[str, ...]:
        source_field = FIELD_SOURCE_KEY.get(field, field)
        return tuple(item.value for item in self.unmapped if item.field == source_field)

    def as_document(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], self.model_dump(mode="json"))


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def vocabulary_content_sha256(payload: Mapping[str, Any]) -> str:
    """Content hash of a vocabulary or bundle payload (``content_sha256`` excluded)."""
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    return _canonical_sha256(body)


def source_reference_id(name: str) -> str:
    """Deterministic reference id for a published label (same scheme as the build)."""
    digest = hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()
    return f"{_SOURCE_REFERENCE_PREFIX}{digest}"


def named_reference(name: str) -> dict[str, str]:
    return {"reference_id": source_reference_id(name), "name": name}


def _reference_names(value: JsonValue) -> tuple[str, ...]:
    """Read the published tag values of one field, in their published order."""
    if value is None:
        return ()
    items = value if isinstance(value, list) else [value]
    names: list[str] = []
    for item in items:
        if isinstance(item, str):
            if item.strip():
                names.append(item.strip())
        elif isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    return tuple(names)


# --------------------------------------------------------------------------- #
# deterministic batch composition (replay depends on this being a pure function)
# --------------------------------------------------------------------------- #


def induction_sample(
    values: Sequence[str], *, size: int = INDUCTION_SAMPLE_SIZE
) -> tuple[str, ...]:
    """Deterministic stratified sample used as the concept-induction input.

    Sorted values are strided, so the sample is a pure function of the value set:
    a replay from a different value set cannot validate against the recording.
    """
    ordered = sorted(set(values))
    if len(ordered) <= size:
        return tuple(ordered)
    stride = len(ordered) / float(size)
    return tuple(ordered[int(index * stride)] for index in range(size))


def mapping_batches(
    values: Sequence[str], *, batch_size: int = MAPPING_BATCH_SIZE
) -> tuple[tuple[str, ...], ...]:
    ordered = sorted(set(values))
    return tuple(
        tuple(ordered[offset : offset + batch_size])
        for offset in range(0, len(ordered), batch_size)
    )


# --------------------------------------------------------------------------- #
# prompts (recorded by sha256 in the bundle; drift fails the replay)
# --------------------------------------------------------------------------- #


def render_induction_prompt(values: Sequence[str], *, max_concepts: int) -> str:
    listing = "\n".join(json.dumps(value, ensure_ascii=False) for value in values)
    return (
        "你是深圳科创数据平台的产业分类专家，熟悉中国科技企业的产品与服务。\n"
        "下面是一批企业技术标签（企业自述短语，多为“XX研发商/服务商/提供商”），"
        "每行一个 JSON 字符串。\n"
        "请归纳出一套**受控概念词表**：受控概念要足够粗，是用户会直接发问的类目"
        f"（如“配送机器人”“PCB 制造”），最多 {max_concepts} 个。\n"
        "每个概念必须包含：id（稳定的英文小写点分层级，如 robotics.delivery-robot）、"
        "name（规范中文名）、definition（一句话定义，说明概念边界）、"
        "evidence（1-3 条“可接受的证据形态”，说明什么样的企业自述足以支撑该概念，"
        "如“自述研发/生产该产品”）、kind（只能是 technology 或 industry，"
        "technology 表示技术/产品类，industry 表示行业类）。\n"
        "输出格式（严格遵守）：纯 JSON Lines，每行一个 JSON 对象，"
        "对象只能有 id/name/definition/evidence/kind 五个键，evidence 是字符串数组。\n"
        "每一行必须以 { 开头、以 } 结尾；禁止表头、禁止 CSV、禁止 Markdown 代码块、"
        "禁止解释文字。示例（仅示意格式）：\n"
        '{"id":"robotics.delivery-robot","name":"配送机器人","definition":"面向室内外场景'
        '自主完成物品配送的机器人整机与系统。","evidence":["自述研发/生产该类产品"],'
        '"kind":"technology"}\n'
        "标签样本：\n"
        f"{listing}\n"
    )


def render_concept_catalogue(concepts: Sequence[VocabularyConcept]) -> str:
    return "\n".join(
        f"{concept.concept_id}\t{concept.canonical_name}" for concept in concepts
    )


def render_mapping_prompt(
    field: str,
    values: Sequence[str],
    *,
    catalogue: str,
    concept_ids: Sequence[str],
) -> str:
    listing = "\n".join(json.dumps(value, ensure_ascii=False) for value in values)
    field_label = {
        TECH_TAG_FIELD: "企业技术标签 tech_tags",
        INDUSTRY_FIELD: "企业行业标签 industry",
    }.get(field, field)
    return (
        "你是深圳科创数据平台的产业分类专家，熟悉中国科技企业的产品与服务。\n"
        f"下面是一批{field_label}的原值，每行一个 JSON 字符串。\n"
        "请把每个原值映射到给定的受控概念（只允许使用下面列出的 id）：\n"
        f"{catalogue}\n"
        "规则：\n"
        "1) 一个原值可以映射到多个概念（如“机器人视觉及触觉技术研发商” → 机器视觉 + 触觉传感器）；\n"
        "2) 只能在列表内选择；不确定、超出列表、或明显不是科技/产业类目（如生活服务、"
        "餐饮住宿、广告营销）的原值，一律映射为空数组 []，**不要猜测、不要发明新概念**；\n"
        f"3) 每行必须对应输入中的一行，一共 {len(values)} 行。\n"
        "输出格式（严格遵守）：纯 JSON Lines，每行一个 JSON 对象，"
        "对象只能有 v 与 c 两个键：v 是原值（逐字复制），c 是概念 id 的数组。"
        "每一行必须以 { 开头、以 } 结尾；禁止表头、禁止 CSV、禁止 Markdown 代码块、"
        "禁止解释文字。示例（仅示意格式）：\n"
        '{"v":"室内外配送机器人研发商","c":["robotics.delivery-robot"]}\n'
        f"概念 id 总数：{len(concept_ids)}\n"
        "原值列表：\n"
        f"{listing}\n"
    )


# --------------------------------------------------------------------------- #
# parsing (shared by the recording script and the replay)
# --------------------------------------------------------------------------- #


def _jsonl_records(raw_output: str) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw_output.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or _JSONL_FENCE_RE.match(stripped):
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise VocabularyIntegrityError(
                f"provider transcript line {line_number} is not JSON: {stripped[:120]!r}"
            ) from exc
        if not isinstance(record, dict):
            raise VocabularyIntegrityError(
                f"provider transcript line {line_number} is not an object"
            )
        records.append(record)
    if not records:
        raise VocabularyIntegrityError("provider transcript carries no records")
    return tuple(records)


def parse_concept_drafts(raw_output: str) -> tuple[VocabularyConcept, ...]:
    """Parse the induction transcript into concepts, fail-closed on every defect."""
    concepts: list[VocabularyConcept] = []
    for record in _jsonl_records(raw_output):
        try:
            concept = VocabularyConcept.model_validate(
                {
                    "concept_id": record["id"],
                    "canonical_name": record["name"],
                    "definition": record["definition"],
                    "acceptable_evidence_forms": tuple(record["evidence"]),
                    "kind": record["kind"],
                }
            )
        except (KeyError, TypeError, ValidationError) as exc:
            raise VocabularyIntegrityError(
                f"induction record is not a valid concept: {record!r}"
            ) from exc
        concepts.append(concept)
    ordered = tuple(sorted(concepts, key=lambda item: item.concept_id))
    identifiers = [concept.concept_id for concept in ordered]
    if len(set(identifiers)) != len(identifiers):
        raise VocabularyIntegrityError("induction transcript repeats a concept id")
    names = [concept.canonical_name for concept in ordered]
    if len(set(names)) != len(names):
        duplicates = sorted({name for name in names if names.count(name) > 1})
        raise VocabularyIntegrityError(
            f"induction transcript repeats a concept name: {duplicates}"
        )
    return ordered


def parse_mapping_lines(
    raw_output: str,
    *,
    expected_values: Sequence[str],
    concept_ids: frozenset[str],
) -> dict[str, tuple[str, ...]]:
    """Parse one mapping transcript; every input value must appear exactly once."""
    expected = set(expected_values)
    parsed: dict[str, tuple[str, ...]] = {}
    for record in _jsonl_records(raw_output):
        if set(record) != {"v", "c"}:
            raise VocabularyIntegrityError(
                f"mapping record keys must be v/c: {sorted(record)}"
            )
        value = record["v"]
        concepts = record["c"]
        if not isinstance(value, str) or value not in expected:
            raise VocabularyIntegrityError(
                f"mapping record is not one of the requested values: {value!r}"
            )
        if value in parsed:
            raise VocabularyIntegrityError(f"mapping value answered twice: {value!r}")
        if not isinstance(concepts, list) or not all(
            isinstance(item, str) for item in concepts
        ):
            raise VocabularyIntegrityError(
                f"mapping concepts must be a list of ids: {value!r}"
            )
        unknown = sorted(set(concepts) - set(concept_ids))
        if unknown:
            raise VocabularyIntegrityError(
                f"mapping invented concepts outside the vocabulary: {unknown}"
            )
        parsed[value] = tuple(sorted(set(concepts)))
    missing = sorted(expected - set(parsed))
    if missing:
        raise VocabularyIntegrityError(
            f"mapping transcript is missing {len(missing)} value(s), e.g. {missing[:3]}"
        )
    return parsed


def assert_mapping_arity(field: str, parsed: Mapping[str, tuple[str, ...]]) -> None:
    """A single-valued published field cannot map a value to several concepts."""
    if field not in SINGLE_VALUED_FIELDS:
        return
    offenders = sorted(value for value, ids in parsed.items() if len(ids) > 1)
    if offenders:
        raise VocabularyIntegrityError(
            f"{field} values must map to at most one concept: {offenders[:3]}"
        )


# --------------------------------------------------------------------------- #
# bundle loading and replay
# --------------------------------------------------------------------------- #


_BUNDLE_KEYS = frozenset(
    {
        "schema_version",
        "provider",
        "model",
        "endpoint",
        "prompt_version",
        "output_schema_version",
        "temperature",
        "pythonhashseed_invariant",
        "prompts",
        "source_value_counts",
        "induction_sample_values",
        "induction_max_concepts",
        "mapping_batch_size",
        "calls",
        "call_count",
        "usage",
        "content_sha256",
    }
)
_CALL_KEYS = frozenset(
    {
        "call_id",
        "kind",
        "input_value_ids",
        "input_sha256",
        "raw_output",
        "output_sha256",
    }
)


def load_recorded_vocabulary_bundle(path: Path) -> dict[str, Any]:
    """Load a recorded vocabulary bundle, refusing every shape deviation."""
    if path.is_symlink():
        raise VocabularyIntegrityError("vocabulary bundle cannot be a symlink")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise VocabularyIntegrityError(
            f"vocabulary bundle is unreadable: {path}"
        ) from exc
    if not isinstance(document, dict) or set(document) != _BUNDLE_KEYS:
        raise VocabularyIntegrityError(
            f"vocabulary bundle keys differ from {BUNDLE_SCHEMA_VERSION}"
        )
    if document["schema_version"] != BUNDLE_SCHEMA_VERSION:
        raise VocabularyIntegrityError(
            f"vocabulary bundle schema_version must be {BUNDLE_SCHEMA_VERSION}"
        )
    if document["content_sha256"] != vocabulary_content_sha256(document):
        raise VocabularyIntegrityError(
            "vocabulary bundle content_sha256 does not match"
        )
    calls = document["calls"]
    if not isinstance(calls, list) or not calls:
        raise VocabularyIntegrityError("vocabulary bundle carries no calls")
    if document["call_count"] != len(calls):
        raise VocabularyIntegrityError(
            "vocabulary bundle call_count does not match calls"
        )
    for call in calls:
        if not isinstance(call, dict) or set(call) != _CALL_KEYS:
            raise VocabularyIntegrityError("vocabulary bundle call shape differs")
        if call["kind"] not in ("induct", "value_mapping"):
            raise VocabularyIntegrityError(
                f"unknown vocabulary call kind: {call['kind']}"
            )
        raw_output = call["raw_output"]
        if not isinstance(raw_output, str):
            raise VocabularyIntegrityError("vocabulary bundle transcript must be text")
        if (
            hashlib.sha256(raw_output.encode("utf-8")).hexdigest()
            != call["output_sha256"]
        ):
            raise VocabularyIntegrityError(
                f"recorded transcript was modified: {call['call_id']}"
            )
        value_ids = call["input_value_ids"]
        if not isinstance(value_ids, list) or not all(
            isinstance(item, str) for item in value_ids
        ):
            raise VocabularyIntegrityError("vocabulary bundle input ids must be text")
        if call["input_sha256"] != _canonical_sha256(value_ids):
            raise VocabularyIntegrityError(
                f"recorded input list was modified: {call['call_id']}"
            )
    prompts = document["prompts"]
    if not isinstance(prompts, dict) or set(prompts) != {"induct", "map"}:
        raise VocabularyIntegrityError("vocabulary bundle prompts must be induct/map")
    for kind, prompt in prompts.items():
        if not isinstance(prompt, dict) or set(prompt) != {"sha256", "text"}:
            raise VocabularyIntegrityError(
                f"vocabulary bundle prompt {kind} shape differs"
            )
        if (
            hashlib.sha256(prompt["text"].encode("utf-8")).hexdigest()
            != prompt["sha256"]
        ):
            raise VocabularyIntegrityError(
                f"vocabulary bundle prompt {kind} was modified"
            )
    return document


def _validate_prompt_versions(document: Mapping[str, Any]) -> None:
    if document["prompt_version"] != PROMPT_VERSION:
        raise VocabularyIntegrityError(
            "vocabulary bundle was recorded with a different prompt version"
        )
    if document["output_schema_version"] != OUTPUT_SCHEMA_VERSION:
        raise VocabularyIntegrityError(
            "vocabulary bundle was recorded with a different output schema version"
        )


def replay_vocabulary_from_bundle(
    document: Mapping[str, Any], *, validate_prompts: bool = True
) -> TechnicalVocabulary:
    """Rebuild the vocabulary from recorded transcripts - the build's only path.

    The batch composition is recomputed from the recorded inputs, so a bundle
    recorded against a different value set (or with a missing/extra call) fails
    instead of silently mapping part of the corpus.
    """
    if document.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise VocabularyIntegrityError(
            f"vocabulary bundle schema_version must be {BUNDLE_SCHEMA_VERSION}"
        )
    _validate_prompt_versions(document)
    calls = cast(list[dict[str, Any]], list(document["calls"]))
    if document["content_sha256"] != vocabulary_content_sha256(document):
        raise VocabularyIntegrityError(
            "vocabulary bundle content_sha256 does not match"
        )

    induction_calls = [call for call in calls if call["kind"] == "induct"]
    mapping_calls = [call for call in calls if call["kind"] == "value_mapping"]
    if len(induction_calls) != 1:
        raise VocabularyIntegrityError(
            "vocabulary bundle must carry exactly one induction call"
        )
    induction = induction_calls[0]
    recorded_sample = document["induction_sample_values"]
    if list(induction["input_value_ids"]) != list(recorded_sample):
        raise VocabularyIntegrityError(
            "induction call input differs from the recorded sample"
        )
    concepts = parse_concept_drafts(cast(str, induction["raw_output"]))
    concept_ids = frozenset(concept.concept_id for concept in concepts)

    if validate_prompts:
        prompts = cast(dict[str, dict[str, str]], document["prompts"])
        expected_induction = render_induction_prompt(
            tuple(recorded_sample), max_concepts=int(document["induction_max_concepts"])
        )
        expected_mapping = render_mapping_prompt(
            TECH_TAG_FIELD,
            ["<sample>"],
            catalogue=render_concept_catalogue(concepts),
            concept_ids=sorted(concept_ids),
        )
        for kind, expected in (
            ("induct", expected_induction),
            ("map", expected_mapping),
        ):
            if prompts[kind]["text"] != expected:
                raise VocabularyIntegrityError(
                    f"vocabulary prompt {kind} drifted from the recording"
                )

    mappings: list[TagConceptMapping] = []
    unmapped: list[UnmappedTagValue] = []
    seen: dict[str, list[str]] = {field: [] for field in MAPPED_FIELDS}
    batch_size = document["mapping_batch_size"]
    expected_keys = {
        f"map:{field}:{index:04d}"
        for field in MAPPED_FIELDS
        for index in range(0, -(-document["source_value_counts"][field] // batch_size))
    }
    recorded_keys = {call["call_id"] for call in mapping_calls}
    if recorded_keys != expected_keys:
        raise VocabularyIntegrityError(
            "vocabulary bundle mapping calls do not cover the recorded value set"
        )
    for call in sorted(mapping_calls, key=lambda item: item["call_id"]):
        _, field, _index = cast(str, call["call_id"]).split(":", 2)
        values = cast(list[str], call["input_value_ids"])
        parsed = parse_mapping_lines(
            cast(str, call["raw_output"]),
            expected_values=values,
            concept_ids=concept_ids,
        )
        assert_mapping_arity(field, parsed)
        seen[field].extend(values)
        for value, concepts_for_value in parsed.items():
            if concepts_for_value:
                mappings.append(
                    TagConceptMapping(
                        field=field, value=value, concept_ids=concepts_for_value
                    )
                )
            else:
                unmapped.append(UnmappedTagValue(field=field, value=value))
    for field, values in seen.items():
        if len(values) != len(set(values)):
            raise VocabularyIntegrityError(
                f"vocabulary bundle maps a {field} value twice"
            )
        if len(values) != document["source_value_counts"][field]:
            raise VocabularyIntegrityError(
                f"vocabulary bundle covers {len(values)} {field} values, "
                f"the recording declares {document['source_value_counts'][field]}"
            )
        if values != sorted(values):
            raise VocabularyIntegrityError(
                f"vocabulary bundle {field} batches are not in deterministic order"
            )
    expected_sample = induction_sample(sorted(seen[TECH_TAG_FIELD]))
    if tuple(recorded_sample) != expected_sample:
        raise VocabularyIntegrityError(
            "induction sample is not the deterministic sample of the recorded values"
        )

    ordered_mappings = tuple(
        sorted(mappings, key=lambda item: (item.field, item.value))
    )
    ordered_unmapped = tuple(
        sorted(unmapped, key=lambda item: (item.field, item.value))
    )
    usage = cast(dict[str, int], document["usage"])
    payload: dict[str, Any] = {
        "schema_version": VOCABULARY_SCHEMA_VERSION,
        "artifact_version": f"{document['prompt_version']}+{cast(str, document['model'])}",
        "prompt_version": document["prompt_version"],
        "output_schema_version": document["output_schema_version"],
        "provider": document["provider"],
        "model": document["model"],
        "bundle_content_sha256": document["content_sha256"],
        "llm_call_count": len(calls),
        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
        "completion_tokens": int(usage.get("completion_tokens", 0)),
        "source_value_counts": dict(document["source_value_counts"]),
        "concepts": [concept.model_dump(mode="json") for concept in concepts],
        "mappings": [mapping.model_dump(mode="json") for mapping in ordered_mappings],
        "unmapped": [item.model_dump(mode="json") for item in ordered_unmapped],
    }
    payload["content_sha256"] = vocabulary_content_sha256(payload)
    return TechnicalVocabulary.model_validate(payload)


def artifact_document(vocabulary: TechnicalVocabulary) -> dict[str, JsonValue]:
    """Deterministic on-disk form of the vocabulary artifact."""
    return vocabulary.as_document()


VOCABULARY_ARTIFACT_CONTENT_SHA256 = "PENDING_GENERATION"
VOCABULARY_ARTIFACT_PATH = (
    Path(__file__).resolve().parent / "catalogs" / VOCABULARY_ARTIFACT_FILENAME
)


def load_packaged_vocabulary(path: Path | None = None) -> TechnicalVocabulary:
    """Load the packaged vocabulary the projection applies (content-hash pinned)."""
    artifact_path = VOCABULARY_ARTIFACT_PATH if path is None else path
    try:
        document = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise VocabularyIntegrityError(
            f"packaged vocabulary is unreadable: {artifact_path}"
        ) from exc
    if not isinstance(document, dict):
        raise VocabularyIntegrityError("packaged vocabulary must be a JSON object")
    if document.get("content_sha256") != vocabulary_content_sha256(document):
        raise VocabularyIntegrityError(
            "packaged vocabulary content_sha256 does not match"
        )
    vocabulary = TechnicalVocabulary.model_validate(document)
    if vocabulary.schema_version != VOCABULARY_SCHEMA_VERSION:
        raise VocabularyIntegrityError(
            f"packaged vocabulary schema_version must be {VOCABULARY_SCHEMA_VERSION}"
        )
    if (
        path is None
        and VOCABULARY_ARTIFACT_CONTENT_SHA256 != "PENDING_GENERATION"
        and vocabulary.content_sha256 != VOCABULARY_ARTIFACT_CONTENT_SHA256
    ):
        raise VocabularyIntegrityError(
            "packaged vocabulary differs from the revision pinned in code"
        )
    return vocabulary


# --------------------------------------------------------------------------- #
# projection application
# --------------------------------------------------------------------------- #


def apply_vocabulary(
    domain: str,
    values: Mapping[str, JsonValue],
    vocabulary: TechnicalVocabulary,
) -> tuple[dict[str, JsonValue], tuple[UnmappedTagValue, ...]]:
    """Rewrite the tag fields of one projected document into controlled concepts.

    Mapped values publish the concept names (union, de-duplicated, sorted, so two
    synonyms stop being two tags).  Undecided values publish the raw label again:
    nothing is guessed and nothing is dropped.  Other fields are untouched.
    """
    if domain != "company":
        return dict(values), ()
    projected = dict(values)
    unmapped_records: list[UnmappedTagValue] = []
    for field in (INDUSTRY_FIELD, INDUSTRY_TAG_FIELD, TECH_TAG_FIELD):
        raw_value = values.get(field)
        if raw_value is None:
            continue
        names = _reference_names(raw_value)
        if not names:
            continue
        concept_names: set[str] = set()
        passthrough: list[str] = []
        for name in names:
            concept_ids = vocabulary.concept_ids_for(field, name)
            if concept_ids:
                concept_names.update(vocabulary.concept_names(concept_ids))
            else:
                passthrough.append(name)
                unmapped_records.append(
                    UnmappedTagValue(
                        field=FIELD_SOURCE_KEY.get(field, field), value=name
                    )
                )
        published = tuple(sorted(concept_names | set(passthrough)))
        references = [named_reference(name) for name in published]
        projected[field] = cast(
            JsonValue,
            references if isinstance(raw_value, list) else _singular(references),
        )
    return projected, tuple(unmapped_records)


def _singular(references: Sequence[dict[str, str]]) -> JsonValue:
    if len(references) != 1:
        raise VocabularyIntegrityError(
            "a single-valued reference field mapped to several concepts"
        )
    return cast(JsonValue, references[0])


@lru_cache(maxsize=1)
def _packaged_vocabulary() -> TechnicalVocabulary:
    return load_packaged_vocabulary()


def apply_packaged_vocabulary(
    domain: str, values: Mapping[str, JsonValue]
) -> tuple[dict[str, JsonValue], tuple[UnmappedTagValue, ...]]:
    """Projection seam entry point: apply the packaged vocabulary to one domain."""
    if domain != "company":
        return dict(values), ()
    return apply_vocabulary(domain, values, _packaged_vocabulary())


# --------------------------------------------------------------------------- #
# quality section, gate and report wiring
# --------------------------------------------------------------------------- #


def build_vocabulary_quality_section(
    *,
    vocabulary: TechnicalVocabulary,
    published_values: Mapping[str, Sequence[str]] | None = None,
    unmapped_examples: int = UNMAPPED_EXAMPLE_LIMIT,
    collection_gap: Mapping[str, JsonValue] | None = None,
    category_probes: Mapping[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    """Compose the ``vocabulary`` section of the build quality report.

    ``published_values`` maps a tag field to the values that were published, which
    is what turns "no guessing" into a checkable claim: every published value is
    either a concept name or a recorded unmapped value.
    """
    per_field: dict[str, JsonValue] = {}
    for field in MAPPED_FIELDS:
        mapped_count = sum(1 for item in vocabulary.mappings if item.field == field)
        unmapped_count = sum(1 for item in vocabulary.unmapped if item.field == field)
        source_count = vocabulary.source_value_counts.get(field, 0)
        if mapped_count + unmapped_count != source_count:
            raise VocabularyIntegrityError(
                f"vocabulary {field} counts do not add up to the source value count"
            )
        per_field[field] = cast(
            JsonValue,
            {
                "source_values": source_count,
                "mapped_values": mapped_count,
                "unmapped_values": unmapped_count,
                "coverage": round(mapped_count / source_count, 6)
                if source_count
                else 0.0,
            },
        )
    section: dict[str, JsonValue] = {
        "schema_version": VOCABULARY_SCHEMA_VERSION,
        "artifact_content_sha256": vocabulary.content_sha256,
        "bundle_content_sha256": vocabulary.bundle_content_sha256,
        "prompt_version": vocabulary.prompt_version,
        "provider": vocabulary.provider,
        "model": vocabulary.model,
        "llm_calls": vocabulary.llm_call_count,
        "prompt_tokens": vocabulary.prompt_tokens,
        "completion_tokens": vocabulary.completion_tokens,
        "concepts": cast(
            JsonValue,
            {
                "total": len(vocabulary.concepts),
                "technology": sum(
                    1 for item in vocabulary.concepts if item.kind == "technology"
                ),
                "industry": sum(
                    1 for item in vocabulary.concepts if item.kind == "industry"
                ),
            },
        ),
        "fields": cast(JsonValue, per_field),
        "minimum_coverage": MINIMUM_MAPPED_VALUE_COVERAGE,
        "unmapped_examples": cast(
            JsonValue, [item.value for item in vocabulary.unmapped[:unmapped_examples]]
        ),
    }
    if published_values is not None:
        published: dict[str, JsonValue] = {}
        for field, values in published_values.items():
            concept_hits = sum(
                1 for value in values if vocabulary.is_concept_name(value)
            )
            recorded_unmapped = set(vocabulary.unmapped_values(field))
            unmapped_hits = sum(1 for value in values if value in recorded_unmapped)
            published[field] = cast(
                JsonValue,
                {
                    "published_values": len(set(values)),
                    "concept_names": concept_hits,
                    "unmapped_passthrough": unmapped_hits,
                    "unrecognized": len(set(values)) - concept_hits - unmapped_hits,
                },
            )
        section["published"] = cast(JsonValue, published)
    if collection_gap is not None:
        section["collection_gap"] = cast(JsonValue, dict(collection_gap))
    if category_probes is not None:
        section["category_probe_support"] = cast(JsonValue, dict(category_probes))
    return section


def assert_vocabulary_quality(section: Mapping[str, JsonValue]) -> None:
    """Fail the build when the published vocabulary breaks its own contract.

    The collection gap (tags per company, companies without tags) is deliberately
    not part of this gate: that is a collection defect the report records, not a
    vocabulary defect the build can fix.
    """
    fields = section.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise VocabularyQualityError("vocabulary quality section carries no fields")
    for field, payload in sorted(fields.items()):
        if not isinstance(payload, dict):
            raise VocabularyQualityError(f"vocabulary field {field} is malformed")
        coverage = payload.get("coverage")
        if (
            not isinstance(coverage, (int, float))
            or coverage < MINIMUM_MAPPED_VALUE_COVERAGE
        ):
            raise VocabularyQualityError(
                f"vocabulary coverage for {field} is {coverage}, "
                f"below the {MINIMUM_MAPPED_VALUE_COVERAGE} floor"
            )
    published = section.get("published")
    if isinstance(published, dict):
        for field, payload in sorted(published.items()):
            if not isinstance(payload, dict):
                raise VocabularyQualityError(f"published {field} counts are malformed")
            if payload.get("unrecognized"):
                raise VocabularyQualityError(
                    f"published {field} carries {payload['unrecognized']} value(s) that are "
                    "neither concepts nor recorded unmapped values"
                )
    concepts = section.get("concepts")
    if not isinstance(concepts, dict) or int(concepts.get("total", 0)) < 1:
        raise VocabularyQualityError("vocabulary carries no concepts")


def attach_vocabulary_section(
    payload: Mapping[str, JsonValue], section: Mapping[str, JsonValue]
) -> dict[str, JsonValue]:
    """Merge the vocabulary section into a quality report payload (idempotent)."""
    merged = dict(payload)
    existing = merged.get(VOCABULARY_QUALITY_SECTION_KEY)
    if existing is not None and dict(existing) != dict(section):
        raise VocabularyQualityError(
            "quality report already carries a different vocabulary section"
        )
    merged[VOCABULARY_QUALITY_SECTION_KEY] = cast(JsonValue, dict(section))
    return merged


def published_tag_values(
    documents: Iterable[Mapping[str, JsonValue]],
) -> dict[str, list[str]]:
    """Collect the published tag values of company lookup documents."""
    collected: dict[str, list[str]] = {field: [] for field in MAPPED_FIELDS}
    for document in documents:
        for field in MAPPED_FIELDS:
            collected[field].extend(_reference_names(document.get(field)))
    return collected
