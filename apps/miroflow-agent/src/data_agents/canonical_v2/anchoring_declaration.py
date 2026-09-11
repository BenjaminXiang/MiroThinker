"""Packaged anchoring declaration for category recall (C1 batch 0).

Skeleton per `openspec/changes/close-workbook-gaps/design.md` §C1-5: a
packaged, versioned JSON resource (loading precedent: `domain_catalog.py`)
seeded from `g-series/g3-vocabulary.json` plus the F1 scoring constants
previously hardcoded in `knowledge_read_isolated`. Batch 0 wires exactly one
consumer: F1 category scoring reads its field-tier multipliers and
thresholds from here — seeded values are identical to the old constants, so
behavior is unchanged. Unknown schema versions fail closed at load time.
"""

from __future__ import annotations

from importlib.resources import files
import json
from typing import Any, Literal, cast

from pydantic import JsonValue

from .contracts import ContractModel, NonEmptyStr, Sha256

DECLARATION_RESOURCE = "catalogs/anchoring-declaration-v1.json"
DECLARATION_SCHEMA_VERSION = "canonical-v2-anchoring-declaration-v1"


class AnchoringDeclarationProvenance(ContractModel):
    pack_id: NonEmptyStr
    pack_sha256: Sha256
    sources: tuple[NonEmptyStr, ...]


class AnchoringFieldTierMultipliers(ContractModel):
    industry_label: int
    tag: int
    product: int


class AnchoringF1CategoryScoring(ContractModel):
    field_tier_multipliers: AnchoringFieldTierMultipliers
    min_bigram_coverage: int
    min_score: int


class AnchoringDeclarationTerm(ContractModel):
    term: NonEmptyStr
    tier: Literal["S", "T", "N"]
    anchor_field: NonEmptyStr | None = None
    match_mode: Literal["substring"] = "substring"
    multiplier: int = 1
    confidence_class: Literal["structured_anchored", "text_only", "no_signal"]
    whitelisted: bool = False
    # AQ-S5 (A-2): when set, this entry is a paraphrase member of the named
    # trigger head; the F1 category recall admits it only on queries whose
    # extracted terms include the head, at `multiplier` as the member weight.
    expands: NonEmptyStr | None = None


class InstalledAnchoringDeclaration(ContractModel):
    schema_version: Literal["canonical-v2-anchoring-declaration-v1"]
    generated_from: AnchoringDeclarationProvenance
    f1_category_scoring: AnchoringF1CategoryScoring
    terms: tuple[AnchoringDeclarationTerm, ...]


def _reject_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate declaration key: {key}")
        result[key] = value
    return result


def parse_anchoring_declaration(raw_bytes: bytes) -> InstalledAnchoringDeclaration:
    """Fail-closed parse: unknown schema, bad JSON, or shape drift all raise."""
    value = json.loads(
        raw_bytes.decode("utf-8", errors="strict"),
        object_pairs_hook=_reject_duplicate_keys,
    )
    if not isinstance(value, dict):
        raise RuntimeError("anchoring declaration must be a JSON object")
    payload = cast(dict[str, Any], value)
    if payload.get("schema_version") != DECLARATION_SCHEMA_VERSION:
        raise RuntimeError(
            "anchoring declaration schema version is not supported: "
            f"{payload.get('schema_version')!r}"
        )
    return InstalledAnchoringDeclaration.model_validate(payload)


def _load_packaged_declaration() -> InstalledAnchoringDeclaration:
    raw_bytes = files(__package__).joinpath(DECLARATION_RESOURCE).read_bytes()
    return parse_anchoring_declaration(raw_bytes)


PACKAGED_ANCHORING_DECLARATION = _load_packaged_declaration()


__all__ = [
    "DECLARATION_RESOURCE",
    "DECLARATION_SCHEMA_VERSION",
    "InstalledAnchoringDeclaration",
    "PACKAGED_ANCHORING_DECLARATION",
    "parse_anchoring_declaration",
]
