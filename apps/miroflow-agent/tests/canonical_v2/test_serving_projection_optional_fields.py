"""Run16 coupling: the serving loader must accept null D0-a projection fields.

``data-cleaning-batch1`` (D0-a) makes nine historically required projection
text fields optional, so the run16 serving pack serializes them as JSON
``null``. The serving pack loader validates every record of
``candidate_projection_result.public_domain_projections`` through the typed
models (:func:`serving_pack_loader._parse_model`), so the serving line must
carry the same optionality or the run16 pack is rejected at boot with
``ServingPackIntegrityError``.

The fixture is a de-identified, structurally faithful derivative of two real
records decoded (read-only) from the sealed run15 pack
``/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed/relationships.json``;
see its ``provenance`` block. Each variant re-binds ``content_sha256`` exactly
the way the models recompute it, so a passing validation also proves the
serving-side dump equals the payload the data line will hash in run16.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from src.data_agents.canonical_v2 import serving_pack_loader as pack_loader
from src.data_agents.canonical_v2.domain_projection_models import (
    CompanyProjection,
    ProfessorProjection,
)

_FIXTURE = (
    Path(__file__).with_name("fixtures") / "run15_public_domain_projection_records.json"
)

D0A_FIELDS = {
    "company": ("profile_summary", "technology_route_summary"),
    "professor": (
        "department",
        "email",
        "homepage",
        "paper_summary",
        "patent_summary",
        "profile_summary",
        "title",
    ),
}

MODELS = {"company": CompanyProjection, "professor": ProfessorProjection}


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _record(domain: str) -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))[domain]


def _rebind(
    domain: str, record: dict[str, Any], *, null_fields: bool
) -> dict[str, Any]:
    """Return the record with a freshly bound hash; optionally null the 9 fields."""
    payload = {key: value for key, value in record.items() if key != "content_sha256"}
    if null_fields:
        for field in D0A_FIELDS[domain]:
            payload[field] = None
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


@pytest.mark.parametrize("domain", sorted(D0A_FIELDS))
def test_run15_record_round_trips_through_serving_model(domain: str) -> None:
    """The fixture stays byte-faithful: validate, dump, compare."""
    bound = _rebind(domain, _record(domain), null_fields=False)
    projection = MODELS[domain].model_validate(bound)
    assert projection.model_dump(mode="json", exclude={"content_sha256"}) == {
        key: value for key, value in bound.items() if key != "content_sha256"
    }


@pytest.mark.parametrize("domain", sorted(D0A_FIELDS))
def test_projection_accepts_null_d0a_fields(domain: str) -> None:
    """A run16-shaped record (nine nulls) validates and keeps its hash binding."""
    bound = _rebind(domain, _record(domain), null_fields=True)
    projection = MODELS[domain].model_validate(bound)
    for field in D0A_FIELDS[domain]:
        assert getattr(projection, field) is None
    assert projection.model_dump(mode="json", exclude={"content_sha256"}) == {
        key: value for key, value in bound.items() if key != "content_sha256"
    }


@pytest.mark.parametrize("domain", sorted(D0A_FIELDS))
def test_loader_parse_helper_accepts_null_d0a_fields(domain: str) -> None:
    """The exact loader entry point parses a nulled record instead of refusing."""
    bound = _rebind(domain, _record(domain), null_fields=True)
    owner = "relationships.candidate_projection_result.public_domain_projections[0]"
    parsed = pack_loader._parse_model(MODELS[domain], bound, owner=owner)
    for field in D0A_FIELDS[domain]:
        assert getattr(parsed, field) is None
