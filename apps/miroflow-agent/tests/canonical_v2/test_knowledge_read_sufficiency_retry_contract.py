from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from typing import Any

TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_read"
NOW = datetime(2026, 7, 15, 3, 0, tzinfo=timezone.utc)


class _MissingKnowledgeReadModule(RuntimeError):
    """Exact Task 8.6 RED sentinel; nested missing dependencies fail normally."""


def _module() -> Any:
    try:
        return import_module(TARGET_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != TARGET_MODULE:
            raise AssertionError(
                f"{TARGET_MODULE} has an unexpected missing dependency: {exc.name}"
            ) from exc
        raise _MissingKnowledgeReadModule(
            f"exact target module is absent: {TARGET_MODULE}"
        ) from exc


def _web_policy(module: Any, mode: str) -> Any:
    if mode == "disabled":
        return module.WebSearchPolicy(mode=mode)
    return module.WebSearchPolicy(
        mode=mode,
        max_provider_calls=1,
        timeout_ms=1_500,
        max_results=5,
        allowed_domains=(),
    )


def _part(
    module: Any,
    *,
    part_id: str,
    text: str,
    subject_id: str,
    predicate: str,
    value: str,
    answer_scoped: bool = False,
) -> Any:
    return module.MaterialQuestionPart(
        part_id=part_id,
        text=text,
        subject_id=subject_id,
        predicate=predicate,
        requested_value=value,
        material=True,
        answer_scoped=answer_scoped,
    )


def _item(
    module: Any,
    *,
    evidence_id: str,
    subject_id: str,
    predicate: str,
    value: str,
    snippet: str,
) -> Any:
    return module.EvidenceItem(
        evidence_id=evidence_id,
        object_id=subject_id,
        domain=("patent" if subject_id.startswith("patent:") else "company"),
        lane="exact",
        source_nature="local",
        source_locator=f"artifact:sufficiency#{evidence_id}",
        snippet=snippet,
        score=1.0,
        observed_at=NOW,
        claim_binding=module.EvidenceClaimBinding(
            subject_id=subject_id,
            predicate=predicate,
            value=value,
        ),
    )


def _lane_result(module: Any, *items: Any) -> Any:
    return module.RetrievalLaneResult(items=items)


def _proposal(
    module: Any,
    request: Any,
    parts: tuple[tuple[str, str, tuple[str, ...], str], ...],
) -> Any:
    return module.SufficiencyProposal(
        decision_input_sha256=request.content_sha256,
        schema_version="sufficiency-v1",
        decision_id=f"sufficiency:{request.plan_id}",
        parts=tuple(
            module.MaterialPartProposal(
                part_id=part_id,
                outcome=outcome,
                evidence_ids=evidence_ids,
                rationale=rationale,
                uncertainty=("high" if outcome != "supported" else "low"),
                confidence=(0.9 if outcome == "supported" else 0.5),
            )
            for part_id, outcome, evidence_ids, rationale in parts
        ),
    )


def _plan(
    module: Any,
    *,
    plan_id: str,
    query: str,
    material_parts: tuple[Any, ...] = (),
    enumeration_policy: Any | None = None,
    supplemental_budget: Any | None = None,
    max_candidates: int = 10,
) -> Any:
    return module.RetrievalPlan(
        plan_id=plan_id,
        plan_version="retrieval-plan-v1",
        original_query=query,
        behavior_class="A",
        interaction_mode="information_retrieval",
        release_id="candidate-r1",
        domains=("company",),
        protected_slots=(),
        lanes=("exact",),
        max_candidates=max_candidates,
        web_required=False,
        web_policy=_web_policy(module, "disabled"),
        freshness_material=False,
        material_parts=material_parts,
        enumeration_policy=enumeration_policy,
        supplemental_budget=supplemental_budget,
    )


def _empty_web(module: Any, _: Any) -> Any:
    return _lane_result(module)


def test_sufficiency_is_per_material_part_and_product_capability_is_direct() -> None:
    module = _module()
    parts = (
        _part(
            module,
            part_id="part:company-identity",
            text="确认 Example Robotics 公司",
            subject_id="company:example-robotics",
            predicate="identity",
            value="Example Robotics",
        ),
        _part(
            module,
            part_id="part:current-role",
            text="确认公司当前负责人",
            subject_id="company:example-robotics",
            predicate="current_role",
            value="chief executive",
        ),
        _part(
            module,
            part_id="part:product-capability",
            text="delivery-robot-x1 是否能自主操作电梯按钮",
            subject_id="product:delivery-robot-x1",
            predicate="capability",
            value="autonomous_elevator_button_operation",
            answer_scoped=True,
        ),
    )
    evidence = (
        _item(
            module,
            evidence_id="evidence:company-identity",
            subject_id="company:example-robotics",
            predicate="identity",
            value="Example Robotics",
            snippet="The retained registry record identifies Example Robotics.",
        ),
        _item(
            module,
            evidence_id="evidence:role-a",
            subject_id="company:example-robotics",
            predicate="current_role",
            value="chief executive:Alice",
            snippet="The retained local profile names Alice as chief executive.",
        ),
        _item(
            module,
            evidence_id="evidence:role-b",
            subject_id="company:example-robotics",
            predicate="current_role",
            value="chief executive:Bob",
            snippet="A second retained source names Bob as chief executive.",
        ),
        _item(
            module,
            evidence_id="evidence:company-general-capability",
            subject_id="company:example-robotics",
            predicate="capability",
            value="autonomous_elevator_button_operation",
            snippet="The Company describes general elevator integration capability.",
        ),
        _item(
            module,
            evidence_id="evidence:other-product-capability",
            subject_id="product:delivery-robot-x2",
            predicate="capability",
            value="autonomous_elevator_button_operation",
            snippet="Another Product is directly demonstrated with the requested capability.",
        ),
        _item(
            module,
            evidence_id="evidence:technology-route",
            subject_id="technology:elevator-integration",
            predicate="demonstrated_use",
            value="autonomous_elevator_button_operation",
            snippet="A Technology route may enable the capability in principle.",
        ),
        _item(
            module,
            evidence_id="evidence:same-product-wrong-capability",
            subject_id="product:delivery-robot-x1",
            predicate="capability",
            value="autonomous_door_opening",
            snippet="The named Product is directly evidenced for a different capability.",
        ),
    )

    def local_search(_: Any) -> Any:
        return _lane_result(module, *evidence)

    def sufficiency_decider(request: Any) -> Any:
        return _proposal(
            module,
            request,
            (
                (
                    "part:company-identity",
                    "supported",
                    ("evidence:company-identity",),
                    "Direct retained identity evidence exists.",
                ),
                (
                    "part:current-role",
                    "conflicting",
                    ("evidence:role-a", "evidence:role-b"),
                    "Retained current-role evidence conflicts.",
                ),
                (
                    "part:product-capability",
                    "supported",
                    ("evidence:company-general-capability",),
                    "A hostile proposal propagates Company capability to the Product.",
                ),
            ),
        )

    read = module.create_ephemeral_knowledge_read(
        local_search=local_search,
        web_search=lambda request: _empty_web(module, request),
        universal_web_policy=_web_policy(module, "universal"),
        sufficiency_decider=sufficiency_decider,
    )
    result = read.execute(
        _plan(
            module,
            plan_id="plan:material-parts",
            query="确认公司负责人，并判断其 delivery-robot-x1 是否能自主操作电梯按钮",
            material_parts=parts,
        )
    )
    report = result.sufficiency_report
    decisions = {part.part_id: part for part in report.parts}
    current_evidence_ids = {item.evidence_id for item in result.items}

    assert result.items
    assert tuple(decisions) == tuple(part.part_id for part in parts)
    assert decisions["part:company-identity"].outcome == "supported"
    assert decisions["part:company-identity"].evidence_ids == (
        "evidence:company-identity",
    )
    assert decisions["part:current-role"].outcome == "conflicting"
    assert set(decisions["part:current-role"].evidence_ids) == {
        "evidence:role-a",
        "evidence:role-b",
    }
    assert decisions["part:product-capability"].outcome == "missing"
    assert decisions["part:product-capability"].evidence_ids == ()
    assert decisions["part:product-capability"].uncertainty
    assert decisions["part:product-capability"].answer_scoped is True
    assert decisions["part:product-capability"].canonical is False
    assert all(
        set(decision.evidence_ids) <= current_evidence_ids for decision in report.parts
    )
    assert all(decision.rationale for decision in report.parts)
    assert all(decision.uncertainty for decision in report.parts)
    assert all(0.0 <= decision.confidence <= 1.0 for decision in report.parts)
    assert report.decision_input_sha256
    assert report.complete is False

    forbidden_product_support = (
        ("evidence:other-product-capability",),
        ("evidence:technology-route",),
        ("evidence:same-product-wrong-capability",),
        ("model-memory:product-capability",),
    )
    for forbidden_evidence_ids in forbidden_product_support:

        def forbidden_sufficiency_decider(request: Any) -> Any:
            return _proposal(
                module,
                request,
                (
                    (
                        "part:company-identity",
                        "supported",
                        ("evidence:company-identity",),
                        "Direct retained identity evidence exists.",
                    ),
                    (
                        "part:current-role",
                        "conflicting",
                        ("evidence:role-a", "evidence:role-b"),
                        "Retained current-role evidence conflicts.",
                    ),
                    (
                        "part:product-capability",
                        "supported",
                        forbidden_evidence_ids,
                        "A hostile proposal cites a non-direct source.",
                    ),
                ),
            )

        forbidden_read = module.create_ephemeral_knowledge_read(
            local_search=local_search,
            web_search=lambda request: _empty_web(module, request),
            universal_web_policy=_web_policy(module, "universal"),
            sufficiency_decider=forbidden_sufficiency_decider,
        )
        forbidden_result = forbidden_read.execute(
            _plan(
                module,
                plan_id=f"plan:material-parts:forbidden:{forbidden_evidence_ids[0]}",
                query=(
                    "确认公司负责人，并判断其 delivery-robot-x1 是否能自主操作电梯按钮"
                ),
                material_parts=parts,
            )
        )
        forbidden_product = {
            part.part_id: part for part in forbidden_result.sufficiency_report.parts
        }["part:product-capability"]

        assert forbidden_product.outcome == "missing"
        assert forbidden_product.evidence_ids == ()
        assert forbidden_product.answer_scoped is True
        assert forbidden_product.canonical is False

    direct_product_evidence = _item(
        module,
        evidence_id="evidence:direct-product-capability",
        subject_id="product:delivery-robot-x1",
        predicate="capability",
        value="autonomous_elevator_button_operation",
        snippet=(
            "A retained dated demonstration directly binds delivery-robot-x1 to autonomous "
            "elevator button operation."
        ),
    )

    def positive_local_search(_: Any) -> Any:
        return _lane_result(module, *evidence, direct_product_evidence)

    def positive_sufficiency_decider(request: Any) -> Any:
        return _proposal(
            module,
            request,
            (
                (
                    "part:company-identity",
                    "supported",
                    ("evidence:company-identity",),
                    "Direct retained identity evidence exists.",
                ),
                (
                    "part:current-role",
                    "conflicting",
                    ("evidence:role-a", "evidence:role-b"),
                    "Retained current-role evidence conflicts.",
                ),
                (
                    "part:product-capability",
                    "supported",
                    (direct_product_evidence.evidence_id,),
                    "Direct dated evidence binds the named Product and capability.",
                ),
            ),
        )

    positive_read = module.create_ephemeral_knowledge_read(
        local_search=positive_local_search,
        web_search=lambda request: _empty_web(module, request),
        universal_web_policy=_web_policy(module, "universal"),
        sufficiency_decider=positive_sufficiency_decider,
    )
    positive_result = positive_read.execute(
        _plan(
            module,
            plan_id="plan:material-parts:direct-product-evidence",
            query="确认公司负责人，并判断其 delivery-robot-x1 是否能自主操作电梯按钮",
            material_parts=parts,
        )
    )
    positive_product = {
        part.part_id: part for part in positive_result.sufficiency_report.parts
    }["part:product-capability"]
    bound_evidence = {item.evidence_id: item for item in positive_result.items}[
        direct_product_evidence.evidence_id
    ]

    assert positive_product.outcome == "supported"
    assert positive_product.evidence_ids == (direct_product_evidence.evidence_id,)
    assert positive_product.answer_scoped is True
    assert positive_product.canonical is False
    assert bound_evidence.object_id == "product:delivery-robot-x1"
    assert bound_evidence.claim_binding.subject_id == "product:delivery-robot-x1"
    assert bound_evidence.claim_binding.predicate == "capability"
    assert bound_evidence.claim_binding.value == "autonomous_elevator_button_operation"
    assert bound_evidence.source_nature in {"local", "current_web"}
    assert bound_evidence.observed_at == NOW


def test_enumeration_modes_account_members_without_false_exhaustiveness() -> None:
    module = _module()
    available_ids = ("patent:1", "patent:2")

    def local_search(_: Any) -> Any:
        return _lane_result(
            module,
            *(
                _item(
                    module,
                    evidence_id=f"evidence:{object_id}",
                    subject_id=object_id,
                    predicate="applicant",
                    value="company:example-robotics",
                    snippet=f"{object_id} names Example Robotics as applicant.",
                )
                for object_id in available_ids
            ),
        )

    def sufficiency_decider(request: Any) -> Any:
        return _proposal(module, request, ())

    read = module.create_ephemeral_knowledge_read(
        local_search=local_search,
        web_search=lambda request: _empty_web(module, request),
        universal_web_policy=_web_policy(module, "universal"),
        sufficiency_decider=sufficiency_decider,
    )
    exhaustive = module.EnumerationPolicy(
        mode="exhaustive_bounded",
        scope="accepted applicant-to-Patent release universe",
        as_of=NOW,
        finite_universe_source="release:candidate-r1:company-patents",
        finite_universe_ids=available_ids,
        required_member_ids=(),
    )
    required = module.EnumerationPolicy(
        mode="required_members",
        scope="three user-required Patents",
        as_of=NOW,
        finite_universe_source=None,
        finite_universe_ids=(),
        required_member_ids=(*available_ids, "patent:3"),
    )
    representative = module.EnumerationPolicy(
        mode="representative",
        scope="open-world robotics Patent landscape",
        as_of=NOW,
        finite_universe_source=None,
        finite_universe_ids=(),
        required_member_ids=(),
    )
    incomplete_exhaustive = module.EnumerationPolicy(
        mode="exhaustive_bounded",
        scope="incompletely checked applicant-to-Patent universe",
        as_of=NOW,
        finite_universe_source="release:candidate-r1:company-patents",
        finite_universe_ids=(*available_ids, "patent:3"),
        required_member_ids=(),
    )

    def assert_id_count_consistency(coverage: Any) -> None:
        assert coverage.checked_count == len(coverage.checked_ids)
        assert coverage.eligible_count == len(coverage.eligible_ids)
        assert coverage.retrieved_count == len(coverage.retrieved_ids)
        assert coverage.displayed_count == len(coverage.displayed_ids)
        assert coverage.omitted_count == len(coverage.omitted_ids)
        if coverage.unknown_scope:
            assert coverage.unknown_count is None
        else:
            assert coverage.unknown_count == len(coverage.unknown_ids)

    exhaustive_result = read.execute(
        _plan(
            module,
            plan_id="plan:enumeration:exhaustive",
            query="列出该公司在当前 release 的全部专利",
            enumeration_policy=exhaustive,
        )
    )
    exhaustive_coverage = exhaustive_result.enumeration_coverage
    assert exhaustive_coverage.mode == "exhaustive_bounded"
    assert exhaustive_coverage.scope == exhaustive.scope
    assert exhaustive_coverage.as_of == NOW
    assert exhaustive_coverage.checked_ids == available_ids
    assert exhaustive_coverage.eligible_ids == available_ids
    assert exhaustive_coverage.retrieved_ids == available_ids
    assert exhaustive_coverage.displayed_ids == available_ids
    assert exhaustive_coverage.omitted_ids == ()
    assert exhaustive_coverage.unknown_ids == ()
    assert exhaustive_coverage.unknown_scope is False
    assert exhaustive_coverage.exhaustive is True
    assert exhaustive_coverage.accounting_complete is True
    assert exhaustive_coverage.continuation_state == "complete"
    assert exhaustive_coverage.continuation_required is False
    assert_id_count_consistency(exhaustive_coverage)

    incomplete_result = read.execute(
        _plan(
            module,
            plan_id="plan:enumeration:incomplete-exhaustive",
            query="尝试列出当前 release 的全部专利但第三项未检查",
            enumeration_policy=incomplete_exhaustive,
        )
    )
    incomplete_coverage = incomplete_result.enumeration_coverage
    assert incomplete_coverage.mode == "exhaustive_bounded"
    assert incomplete_coverage.scope == incomplete_exhaustive.scope
    assert incomplete_coverage.as_of == NOW
    assert incomplete_coverage.checked_ids == available_ids
    assert incomplete_coverage.eligible_ids == available_ids
    assert incomplete_coverage.retrieved_ids == available_ids
    assert incomplete_coverage.displayed_ids == available_ids
    assert incomplete_coverage.omitted_ids == ("patent:3",)
    assert incomplete_coverage.unknown_ids == ("patent:3",)
    assert incomplete_coverage.unknown_scope is False
    assert incomplete_coverage.exhaustive is False
    assert incomplete_coverage.accounting_complete is False
    assert incomplete_coverage.continuation_state == "universe_unchecked"
    assert incomplete_coverage.continuation_required is True
    assert_id_count_consistency(incomplete_coverage)

    required_result = read.execute(
        _plan(
            module,
            plan_id="plan:enumeration:required",
            query="逐项核对 patent:1、patent:2、patent:3",
            enumeration_policy=required,
        )
    )
    required_coverage = required_result.enumeration_coverage
    assert required_coverage.mode == "required_members"
    assert required_coverage.scope == required.scope
    assert required_coverage.as_of == NOW
    assert required_coverage.checked_ids == required.required_member_ids
    assert required_coverage.eligible_ids == available_ids
    assert required_coverage.retrieved_ids == available_ids
    assert required_coverage.displayed_ids == available_ids
    assert required_coverage.omitted_ids == ("patent:3",)
    assert required_coverage.unknown_ids == ("patent:3",)
    assert required_coverage.unknown_scope is False
    assert required_coverage.exhaustive is False
    assert required_coverage.accounting_complete is True
    required_outcomes = {
        outcome.member_id: outcome
        for outcome in required_coverage.required_member_outcomes
    }
    assert set(required_outcomes) == set(required.required_member_ids)
    assert len(required_coverage.required_member_outcomes) == len(
        required.required_member_ids
    )
    assert required_outcomes["patent:1"].outcome == "included"
    assert required_outcomes["patent:1"].evidence_ids == ("evidence:patent:1",)
    assert required_outcomes["patent:2"].outcome == "included"
    assert required_outcomes["patent:2"].evidence_ids == ("evidence:patent:2",)
    assert required_outcomes["patent:3"].outcome == "unsupported"
    assert required_outcomes["patent:3"].evidence_ids == ()
    assert required_outcomes["patent:3"].reason
    assert required_coverage.continuation_state == "required_member_unresolved"
    assert required_coverage.continuation_required is True
    assert_id_count_consistency(required_coverage)

    representative_result = read.execute(
        _plan(
            module,
            plan_id="plan:enumeration:representative",
            query="给出机器人专利的代表性样本",
            enumeration_policy=representative,
            max_candidates=2,
        )
    )
    representative_coverage = representative_result.enumeration_coverage
    assert representative_coverage.mode == "representative"
    assert representative_coverage.scope == representative.scope
    assert representative_coverage.as_of == NOW
    assert representative_coverage.checked_ids == available_ids
    assert representative_coverage.eligible_ids == available_ids
    assert representative_coverage.retrieved_ids == available_ids
    assert representative_coverage.displayed_ids == available_ids
    assert representative_coverage.omitted_ids == ()
    assert representative_coverage.unknown_ids == ()
    assert representative_coverage.unknown_scope is True
    assert representative_coverage.exhaustive is False
    assert representative_coverage.accounting_complete is True
    assert representative_coverage.continuation_state == "open_world"
    assert representative_coverage.continuation_required is True
    assert_id_count_consistency(representative_coverage)


def test_only_unresolved_parts_retry_and_all_budgets_stop_with_partial_evidence() -> (
    None
):
    module = _module()
    supported_part = _part(
        module,
        part_id="part:company-identity",
        text="确认 Example Robotics 公司",
        subject_id="company:example-robotics",
        predicate="identity",
        value="Example Robotics",
    )
    missing_part = _part(
        module,
        part_id="part:latest-financing",
        text="确认该公司的最新融资轮次",
        subject_id="company:example-robotics",
        predicate="financing_round",
        value="latest",
    )
    conflicting_part = _part(
        module,
        part_id="part:current-role",
        text="澄清该公司的当前负责人冲突",
        subject_id="company:example-robotics",
        predicate="current_role",
        value="chief executive",
    )
    identity_evidence = _item(
        module,
        evidence_id="evidence:company-identity",
        subject_id="company:example-robotics",
        predicate="identity",
        value="Example Robotics",
        snippet="The retained registry record identifies Example Robotics.",
    )
    role_evidence_a = _item(
        module,
        evidence_id="evidence:role-a",
        subject_id="company:example-robotics",
        predicate="current_role",
        value="chief executive:Alice",
        snippet="The retained local profile names Alice as chief executive.",
    )
    role_evidence_b = _item(
        module,
        evidence_id="evidence:role-b",
        subject_id="company:example-robotics",
        predicate="current_role",
        value="chief executive:Bob",
        snippet="A second retained source names Bob as chief executive.",
    )

    def local_search(_: Any) -> Any:
        return _lane_result(
            module,
            identity_evidence,
            role_evidence_a,
            role_evidence_b,
        )

    def sufficiency_decider(request: Any) -> Any:
        return _proposal(
            module,
            request,
            (
                (
                    supported_part.part_id,
                    "supported",
                    (identity_evidence.evidence_id,),
                    "Direct retained identity evidence exists.",
                ),
                (
                    conflicting_part.part_id,
                    "conflicting",
                    (role_evidence_a.evidence_id, role_evidence_b.evidence_id),
                    "Retained current-role evidence conflicts and needs clarification.",
                ),
                (
                    missing_part.part_id,
                    "missing",
                    (),
                    "No retained evidence establishes the latest financing round.",
                ),
            ),
        )

    scenarios = (
        (
            "wall_time",
            module.SupplementalBudget(
                max_wall_time_ms=5,
                max_provider_calls=2,
                max_retries=1,
                max_cost_units=10.0,
            ),
            6,
            0.1,
            5,
            6,
        ),
        (
            "provider_calls",
            module.SupplementalBudget(
                max_wall_time_ms=1_000,
                max_provider_calls=1,
                max_retries=3,
                max_cost_units=10.0,
            ),
            1,
            0.1,
            1,
            1,
        ),
        (
            "retries",
            module.SupplementalBudget(
                max_wall_time_ms=1_000,
                max_provider_calls=2,
                max_retries=0,
                max_cost_units=10.0,
            ),
            1,
            0.1,
            0,
            0,
        ),
        (
            "cost",
            module.SupplementalBudget(
                max_wall_time_ms=1_000,
                max_provider_calls=2,
                max_retries=1,
                max_cost_units=1.0,
            ),
            1,
            1.1,
            1.0,
            1.1,
        ),
    )

    for (
        expected_reason,
        budget,
        elapsed_ms,
        cost_units,
        expected_limit,
        expected_used,
    ) in scenarios:
        supplemental_requests: list[Any] = []

        def supplemental_search(request: Any) -> Any:
            supplemental_requests.append(request)
            assert request.material_part_ids == (
                conflicting_part.part_id,
                missing_part.part_id,
            )
            assert supported_part.part_id not in request.material_part_ids
            assert conflicting_part.text in request.query_view
            assert missing_part.text in request.query_view
            return module.SupplementalLaneResult(
                items=(),
                elapsed_ms=elapsed_ms,
                cost_units=cost_units,
                retryable=True,
            )

        read = module.create_ephemeral_knowledge_read(
            local_search=local_search,
            web_search=lambda request: _empty_web(module, request),
            universal_web_policy=_web_policy(module, "universal"),
            sufficiency_decider=sufficiency_decider,
            supplemental_search=supplemental_search,
        )
        plan = _plan(
            module,
            plan_id=f"plan:budget:{expected_reason}",
            query="确认 Example Robotics，澄清负责人冲突并核实最新融资轮次",
            material_parts=(supported_part, conflicting_part, missing_part),
            supplemental_budget=budget,
        )
        result = read.execute(plan)
        decisions = {part.part_id: part for part in result.sufficiency_report.parts}
        supplemental_traces = tuple(
            trace for trace in result.traces if trace.phase == "supplemental"
        )
        limitations = tuple(
            limitation
            for limitation in result.limitations
            if limitation.code == "supplemental_budget_exhausted"
        )
        receipt = result.supplemental_budget_receipt

        assert len(supplemental_requests) == 1
        assert supplemental_requests[0].material_part_ids == (
            conflicting_part.part_id,
            missing_part.part_id,
        )
        assert {item.evidence_id for item in result.items} == {
            identity_evidence.evidence_id,
            role_evidence_a.evidence_id,
            role_evidence_b.evidence_id,
        }
        assert decisions[supported_part.part_id].outcome == "supported"
        assert decisions[conflicting_part.part_id].outcome == "conflicting"
        assert set(decisions[conflicting_part.part_id].evidence_ids) == {
            role_evidence_a.evidence_id,
            role_evidence_b.evidence_id,
        }
        assert decisions[missing_part.part_id].outcome == "missing"
        assert decisions[missing_part.part_id].evidence_ids == ()
        assert len(supplemental_traces) == receipt.attempt_count == 1
        assert all(
            trace.material_part_ids == (conflicting_part.part_id, missing_part.part_id)
            for trace in supplemental_traces
        )
        assert receipt.exhausted is True
        assert receipt.exhaustion_reason == expected_reason
        assert receipt.exhausted_axis == expected_reason
        assert receipt.limit_value == expected_limit
        assert receipt.used_value == expected_used
        assert receipt.provider_calls == 1
        assert receipt.provider_calls <= budget.max_provider_calls
        assert receipt.retry_count == 0
        assert receipt.retry_count <= budget.max_retries
        assert receipt.elapsed_ms == elapsed_ms
        assert receipt.cost_units == cost_units
        assert len(limitations) == 1
        assert limitations[0].material_part_ids == (
            conflicting_part.part_id,
            missing_part.part_id,
        )
        assert limitations[0].reason == expected_reason
        assert set(result.continuation_reasons) == {
            "evidence_gap",
            "budget_exhausted",
        }
