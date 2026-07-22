from __future__ import annotations

from importlib import import_module
from typing import Any


TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_answer"
READ_TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_read"


def _answer_module() -> Any:
    return import_module(TARGET_MODULE)


def _read_module() -> Any:
    return import_module(READ_TARGET_MODULE)


def _evidence_set(
    read_module: Any,
    *,
    query: str,
    turn_number: int,
    snippets: tuple[str, ...],
) -> Any:
    return read_module.EvidenceSet(
        release_id="candidate-r1",
        original_query=query,
        protected_slots=(),
        items=tuple(
            read_module.EvidenceItem(
                evidence_id=f"evidence:{turn_number}:{index}",
                object_id=f"object:{turn_number}",
                domain=("professor" if "专家" in query else "company"),
                lane="exact",
                source_nature="local",
                source_locator=f"artifact:assessment-{turn_number}#item:{index}",
                snippet=snippet,
                score=1.0,
                claim_binding=read_module.EvidenceClaimBinding(
                    subject_id=f"object:{turn_number}",
                    predicate="assessment_signal",
                    value=snippet,
                    status=f"source_{index}",
                ),
            )
            for index, snippet in enumerate(snippets, start=1)
        ),
        traces=(),
        limitations=(),
    )


def _selection_proposal(
    module: Any,
    request: Any,
    dimensions: tuple[tuple[str, tuple[str, ...], str, str | None, str], ...],
    *,
    synthesis: str,
) -> Any:
    evidence_by_id = {item.evidence_id: item for item in request.evidence_set.items}
    return module.AssessmentSelectionProposal(
        selection_input_sha256=request.content_sha256,
        schema_version="assessment-selection-v1",
        decision_id=f"decision:{request.turn_id}",
        model_id="recorded-assessment-selector",
        prompt_version="assessment-selector-prompt-v1",
        decision_run_id=f"assessment-selector-run:{request.turn_id}",
        dimensions=tuple(
            module.AssessmentDimensionProposal(
                name=name,
                rationale=f"Dimension {name} is relevant to this turn.",
                evidence_ids=evidence_ids,
                evidence_bindings=tuple(
                    module.AssessmentEvidenceBinding(
                        evidence_id=evidence_id,
                        subject_id=item.claim_binding.subject_id,
                        predicate=item.claim_binding.predicate,
                        value=item.claim_binding.value,
                        status=item.claim_binding.status,
                    )
                    for evidence_id in evidence_ids
                    if (item := evidence_by_id.get(evidence_id)) is not None
                    and item.claim_binding is not None
                ),
                outcome=outcome,
                conclusion=conclusion,
                uncertainty=uncertainty,
            )
            for name, evidence_ids, outcome, conclusion, uncertainty in dimensions
        ),
        conditional_synthesis=synthesis,
    )


def _turn_request(
    module: Any,
    *,
    turn_number: int,
    query: str,
    evidence_set: Any,
    kind: str,
    user_criteria: tuple[str, ...] = (),
) -> Any:
    return module.TurnRequest(
        session_id="session:assessment-red",
        turn_id=f"turn:{turn_number}",
        query=query,
        release_id=evidence_set.release_id,
        evidence_set=evidence_set,
        assessment_intent=module.AssessmentIntent(
            kind=kind,
            user_criteria=user_criteria,
        ),
    )


def _mapping_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for nested in value.values() for key in _mapping_keys(nested)
        }
    if isinstance(value, (list, tuple)):
        return {key for nested in value for key in _mapping_keys(nested)}
    return set()


def test_explicit_user_criteria_win_for_all_named_assessment_families() -> None:
    module = _answer_module()
    read_module = _read_module()
    scenarios = (
        (
            "technical_strength",
            "这家公司的技术实力如何？请只按专利转化证据判断。",
            "专利转化证据",
            "The retained release links two patents to deployed products.",
        ),
        (
            "competitiveness",
            "这家公司的竞争力如何？请只看目标客户复购。",
            "目标客户复购",
            "Two named target customers renewed contracts in the retained release.",
        ),
        (
            "maturity",
            "这条技术路线成熟吗？请只看公开部署规模。",
            "公开部署规模",
            "The evidence records three bounded production deployments.",
        ),
        (
            "expert_standing",
            "这位专家是不是行业领军者？请只按标准组织任职判断。",
            "标准组织任职",
            "The Professor chairs one named standards working group.",
        ),
    )

    for turn_number, (kind, query, criterion, snippet) in enumerate(scenarios, start=1):
        evidence = _evidence_set(
            read_module,
            query=query,
            turn_number=turn_number,
            snippets=(snippet,),
        )
        request = _turn_request(
            module,
            turn_number=turn_number,
            query=query,
            evidence_set=evidence,
            kind=kind,
            user_criteria=(criterion,),
        )

        def recorded_selector(value: Any) -> Any:
            return _selection_proposal(
                module,
                value,
                (
                    (
                        criterion,
                        (evidence.items[0].evidence_id,),
                        "supported",
                        "supported by the retained evidence",
                        "low",
                    ),
                    (
                        "模型默认维度",
                        (evidence.items[0].evidence_id,),
                        "supported",
                        "also appears favorable",
                        "medium",
                    ),
                ),
                synthesis="Conditional on the user-prescribed criterion, evidence is favorable.",
            )

        answer = module.create_ephemeral_knowledge_answer(
            assessment_selector=recorded_selector
        )
        result = answer.answer(request)
        frame = result.assessment_frame
        evidence_ids = {item.evidence_id for item in evidence.items}

        assert isinstance(result, module.TurnResult)
        assert isinstance(frame, module.AssessmentFrame)
        assert frame.intent_kind == kind
        assert tuple(dimension.name for dimension in frame.dimensions) == (criterion,)
        assert all(dimension.evidence_ids for dimension in frame.dimensions)
        assert all(
            set(dimension.evidence_ids) <= evidence_ids
            for dimension in frame.dimensions
        )
        assert all(dimension.outcome == "supported" for dimension in frame.dimensions)
        assert all(dimension.conclusion for dimension in frame.dimensions)
        assert all(dimension.uncertainty for dimension in frame.dimensions)


def test_selector_chooses_small_evidence_bound_dimensions_per_turn() -> None:
    module = _answer_module()
    read_module = _read_module()
    inputs = (
        (
            11,
            "这家公司的技术竞争力怎么样？",
            "technical_strength",
            (
                "The retained patents cite a distinct production process.",
                "A current benchmark shows lower energy use than two named alternatives.",
            ),
            ("技术差异化", "基准表现"),
        ),
        (
            12,
            "这条技术路线是否已经成熟？",
            "maturity",
            ("The route has one pilot and no retained scaled deployment evidence.",),
            ("部署阶段",),
        ),
    )
    requests: list[Any] = []
    expected_names: dict[str, tuple[str, ...]] = {}

    for turn_number, query, kind, snippets, names in inputs:
        evidence = _evidence_set(
            read_module,
            query=query,
            turn_number=turn_number,
            snippets=snippets,
        )
        request = _turn_request(
            module,
            turn_number=turn_number,
            query=query,
            evidence_set=evidence,
            kind=kind,
        )
        requests.append(request)
        expected_names[request.turn_id] = names

    def recorded_selector(value: Any) -> Any:
        names = expected_names[value.turn_id]
        evidence_ids = tuple(item.evidence_id for item in value.evidence_set.items)
        dimensions = tuple(
            (
                name,
                (evidence_ids[index],),
                "supported",
                "supported by current-turn evidence",
                "medium",
            )
            for index, name in enumerate(names)
        )
        return _selection_proposal(
            module,
            value,
            dimensions,
            synthesis="The judgment is conditional on this turn's retained evidence.",
        )

    answer = module.create_ephemeral_knowledge_answer(
        assessment_selector=recorded_selector
    )
    results = tuple(answer.answer(request) for request in requests)
    selected_names = tuple(
        tuple(dimension.name for dimension in result.assessment_frame.dimensions)
        for result in results
    )

    assert selected_names == tuple(
        expected_names[request.turn_id] for request in requests
    )
    assert selected_names[0] != selected_names[1]
    assert all(names for names in selected_names)
    for request, result in zip(requests, results, strict=True):
        evidence_ids = {item.evidence_id for item in request.evidence_set.items}
        assert all(
            set(dimension.evidence_ids) <= evidence_ids
            for dimension in result.assessment_frame.dimensions
        )
        assert "global_dimension_registry" not in _mapping_keys(
            result.assessment_frame.model_dump(mode="python")
        )


def test_supported_conflicting_and_missing_dimensions_remain_grounded() -> None:
    module = _answer_module()
    read_module = _read_module()
    query = "这项产品成熟吗？请分别看公开部署和量产规模。"
    evidence = _evidence_set(
        read_module,
        query=query,
        turn_number=21,
        snippets=(
            "The public release describes the named site as a production deployment.",
            "The audited project record classifies the same named site as a pilot.",
        ),
    )
    first_binding = evidence.items[0].claim_binding
    assert first_binding is not None
    evidence = evidence.model_copy(
        update={
            "material_conflicts": (
                read_module.EvidenceConflict(
                    conflict_id="conflict:assessment:deployment-stage",
                    subject_id=first_binding.subject_id,
                    predicate=first_binding.predicate,
                    evidence_ids=tuple(item.evidence_id for item in evidence.items),
                    material=True,
                    fusion_decision_id=None,
                ),
            )
        }
    )
    request = _turn_request(
        module,
        turn_number=21,
        query=query,
        evidence_set=evidence,
        kind="maturity",
        user_criteria=("公开部署", "量产规模"),
    )

    def model_memory_is_not_evidence(value: Any) -> Any:
        return _selection_proposal(
            module,
            value,
            (
                (
                    "公开部署",
                    tuple(item.evidence_id for item in evidence.items),
                    "conflicting_evidence",
                    "retained sources disagree whether the named site is production or pilot",
                    "high",
                ),
                (
                    "量产规模",
                    ("model-memory:mass-production",),
                    "supported",
                    "mass production is mature",
                    "low",
                ),
            ),
            synthesis="Maturity is conditional and the production-scale evidence is missing.",
        )

    answer = module.create_ephemeral_knowledge_answer(
        assessment_selector=model_memory_is_not_evidence
    )
    result = answer.answer(request)
    frame = result.assessment_frame
    dimensions = {dimension.name: dimension for dimension in frame.dimensions}
    current_evidence_ids = {item.evidence_id for item in evidence.items}

    assert tuple(dimensions) == request.assessment_intent.user_criteria
    assert set(dimensions["公开部署"].evidence_ids) == current_evidence_ids
    assert dimensions["公开部署"].outcome == "conflicting_evidence"
    assert dimensions["公开部署"].conclusion
    assert dimensions["公开部署"].uncertainty
    assert dimensions["量产规模"].evidence_ids == ()
    assert dimensions["量产规模"].outcome == "insufficient_evidence"
    assert dimensions["量产规模"].conclusion is None
    assert dimensions["量产规模"].uncertainty
    assert all(
        set(dimension.evidence_ids) <= current_evidence_ids
        for dimension in frame.dimensions
    )
    assert frame.conditional_synthesis
    assert frame.answer_scoped is True
    assert frame.canonical is False
    assert {
        "numeric_score",
        "weighted_score",
        "weights",
        "canonical_label",
        "global_dimension_registry",
    }.isdisjoint(_mapping_keys(frame.model_dump(mode="python")))
