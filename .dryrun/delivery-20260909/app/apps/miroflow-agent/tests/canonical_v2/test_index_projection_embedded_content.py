from __future__ import annotations

import json

from src.data_agents.canonical_v2 import index_projection
from src.data_agents.canonical_v2 import knowledge_build_isolated
from src.data_agents.canonical_v2 import knowledge_serving_isolated
from src.data_agents.canonical_v2.domain_projection_models import (
    NamedReference,
    ProfessorProjection,
)

_PROFESSOR_MISSING_FIELD_FALLBACK = (
    knowledge_build_isolated._PROFESSOR_MISSING_FIELD_FALLBACK
)


def _professor_projection(*, department: str, title: str) -> ProfessorProjection:
    return ProfessorProjection.model_construct(
        name="张三",
        canonical_name_zh="张三",
        canonical_name_en=None,
        aliases=(),
        institution="清华大学深圳国际研究生院",
        department=NamedReference(
            reference_id="department:computer-science",
            name=department,
        ),
        title=title,
    )


def test_public_embedded_content_omits_missing_field_placeholder() -> None:
    degraded = index_projection._public_embedded_content(
        _professor_projection(
            department=_PROFESSOR_MISSING_FIELD_FALLBACK,
            title=_PROFESSOR_MISSING_FIELD_FALLBACK,
        ),
        index_projection.ProjectionView.identity,
    )
    assert "Not supplied" not in degraded
    degraded_payload = json.loads(degraded)
    assert "department" not in degraded_payload
    assert "title" not in degraded_payload
    assert degraded_payload["name"] == "张三"
    assert degraded_payload["institution"] == "清华大学深圳国际研究生院"

    complete = index_projection._public_embedded_content(
        _professor_projection(department="计算机科学与技术系", title="副教授"),
        index_projection.ProjectionView.identity,
    )
    complete_payload = json.loads(complete)
    assert complete_payload["department"] == "计算机科学与技术系"
    assert complete_payload["title"] == "副教授"


def test_missing_field_placeholder_constant_matches_build_side() -> None:
    # knowledge_build_isolated imports both serving and index_projection, so
    # the consumers pin a private copy instead of importing the constant back
    # across the cycle; this contract keeps the copies aligned.
    assert (
        knowledge_serving_isolated._PROFESSOR_MISSING_FIELD_FALLBACK
        == knowledge_build_isolated._PROFESSOR_MISSING_FIELD_FALLBACK
    )
    assert (
        index_projection._PROFESSOR_MISSING_FIELD_FALLBACK
        == knowledge_build_isolated._PROFESSOR_MISSING_FIELD_FALLBACK
    )
