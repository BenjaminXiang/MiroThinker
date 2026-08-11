from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from typing import Any

import pytest


TARGET_MODULE = "src.data_agents.canonical_v2.knowledge_read"
NOW = datetime(2026, 7, 15, 6, 0, tzinfo=timezone.utc)
PUBLIC_DOMAINS = ("professor", "company", "paper", "patent")


class _MissingKnowledgeReadModule(RuntimeError):
    """Exact S8Q1 target sentinel; nested missing dependencies fail normally."""


class _MissingS8P2ProposalTaxonomyValidation(RuntimeError):
    """Exact S8P2 RED sentinel for the still-permissive proposal schema."""


class _MissingS8P2CandidateReviewHardening(RuntimeError):
    """Exact Candidate-review RED sentinel for executable planning bypasses."""


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


def _planning_policy(module: Any) -> Any:
    return module.QueryPlanningPolicy(
        policy_id="query-planning-policy-v1",
        policy_version="synthetic-fixture-v1",
        public_domains=PUBLIC_DOMAINS,
        supported_lanes=(
            "exact",
            "structured",
            "lexical",
            "vector",
            "relationship",
            "internal_reference",
            "web",
        ),
        supported_relationship_paths=(
            ("company_has_patent", "company_to_patent"),
            ("professor_authored_paper", "professor_to_paper"),
            ("person_company_role", "person_to_company"),
            ("technology_company_relationship", "technology_to_company"),
        ),
        max_candidates=40,
        max_provider_calls=3,
        max_planning_attempts=2,
        official_web_domains=("sz.gov.cn",),
    )


def _empty_institution_catalog(module: Any) -> Any:
    return module.InstitutionCatalog(
        catalog_id="institution-catalog:empty",
        catalog_version="synthetic-v1",
        release_id="release-r1",
        entries=(),
    )


def _request(
    module: Any,
    *,
    token: str,
    query: str,
    release_id: str = "release-r1",
    displayed_entity_ids: tuple[str, ...] = (),
    enumeration_context: Any | None = None,
    ambiguity_candidates: tuple[Any, ...] = (),
) -> Any:
    return module.QueryPlanningRequest(
        request_id=f"query-request:{token}",
        release_id=release_id,
        original_query=query,
        as_of=NOW,
        displayed_entity_ids=displayed_entity_ids,
        enumeration_context=enumeration_context,
        ambiguity_candidates=ambiguity_candidates,
    )


def _view(
    module: Any,
    *,
    request: Any,
    kind: str,
    text: str,
    retained_values: tuple[str, ...] = (),
) -> Any:
    return module.QueryViewProposal(
        view_id=f"view:{request.request_id}:{kind}",
        kind=kind,
        text=text,
        original_query_sha256=request.original_query_sha256,
        retained_protected_values=retained_values,
        producer_kind=("deterministic" if kind == "original" else "recorded_model"),
        producer_version=(
            "query-planning-policy-v1" if kind == "original" else "rewrite-prompt-v1"
        ),
    )


def _path(
    module: Any,
    *,
    relationship_type_id: str,
    direction: str,
    source_type: str,
    target_type: str,
) -> Any:
    return module.RelationshipPathProposal(
        relationship_type_id=relationship_type_id,
        direction=direction,
        source_type=source_type,
        target_type=target_type,
    )


def _proposal(
    module: Any,
    request: Any,
    *,
    token: str,
    behavior_class: str,
    interaction_mode: str,
    domains: tuple[str, ...],
    lanes: tuple[str, ...],
    views: tuple[Any, ...] = (),
    paths: tuple[Any, ...] = (),
    max_candidates: int = 20,
    max_provider_calls: int = 1,
    enumeration_mode: str | None = None,
    internal_reference_targets: tuple[str, ...] = (),
    web_mode: str | None = None,
    allowed_web_domains: tuple[str, ...] = (),
    max_web_results: int = 0,
    professor_vector_view: str | None = None,
) -> Any:
    values: dict[str, Any] = dict(
        proposal_id=f"planning-proposal:{token}",
        request_sha256=request.content_sha256,
        schema_version="retrieval-plan-proposal-v1",
        model_id="recorded-planner-fixture",
        prompt_version="query-plan-prompt-v1",
        behavior_class=behavior_class,
        interaction_mode=interaction_mode,
        domains=domains,
        lanes=lanes,
        query_views=views,
        relationship_paths=paths,
        max_candidates=max_candidates,
        max_provider_calls=max_provider_calls,
        enumeration_mode=enumeration_mode,
        internal_reference_targets=internal_reference_targets,
        web_mode=web_mode,
        allowed_web_domains=allowed_web_domains,
        max_web_results=max_web_results,
    )
    if (
        professor_vector_view is not None
        and "professor_vector_view" in module.RecordedPlanningProposal.model_fields
    ):
        values["professor_vector_view"] = professor_vector_view
    return module.RecordedPlanningProposal(**values)


def _planner(
    module: Any,
    proposal_provider: Any,
    *,
    institution_catalog: Any | None = None,
    ambiguity_policy: Any | None = None,
    person_references: tuple[Any, ...] = (),
    technology_routes: tuple[Any, ...] = (),
) -> Any:
    kwargs: dict[str, Any] = {
        "planning_policy": _planning_policy(module),
        "institution_catalog": (
            institution_catalog or _empty_institution_catalog(module)
        ),
        "proposal_provider": proposal_provider,
        "person_references": person_references,
        "technology_routes": technology_routes,
    }
    if ambiguity_policy is not None:
        kwargs["ambiguity_policy"] = ambiguity_policy
    return module.create_ephemeral_query_planner(**kwargs)


def _assert_plan_identity(module: Any, request: Any, plan: Any) -> None:
    assert isinstance(plan, module.RetrievalPlan)
    assert plan.request_sha256 == request.content_sha256
    assert plan.release_id == request.release_id
    assert plan.original_query == request.original_query
    assert plan.as_of == request.as_of
    assert plan.content_sha256
    assert module.RetrievalPlan.model_validate(plan.model_dump(mode="json")) == plan


def _without_content_hashes(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_content_hashes(item)
            for key, item in value.items()
            if key != "content_sha256"
        }
    if isinstance(value, (list, tuple)):
        return [_without_content_hashes(item) for item in value]
    return value


def test_soft_context_subject_defaults_none_and_roundtrips_content_sha() -> None:
    module = _module()
    baseline = _request(
        module,
        token="soft-context-default",
        query="有没有更详细的信息",
    )
    # Absent by default and invisible in the serialized form, so content
    # hashes of requests that never carry the field stay unchanged.
    assert baseline.soft_context_subject is None
    assert "soft_context_subject" not in baseline.model_dump(mode="json")

    anchored = module.QueryPlanningRequest(
        request_id="query-request:soft-context-anchored",
        release_id="release-r1",
        original_query="有没有更详细的信息",
        as_of=NOW,
        soft_context_subject="优必选",
    )
    # The release-bound planner rebuilds requests through model_dump; the
    # field must ride that payload with the content hash intact.
    payload = anchored.model_dump(mode="json", exclude={"content_sha256"})
    rebuilt = module.QueryPlanningRequest.model_validate(payload)
    assert rebuilt.soft_context_subject == "优必选"
    assert rebuilt.content_sha256 == anchored.content_sha256
    # The field participates in the binding hash when present.
    assert anchored.content_sha256 != baseline.content_sha256
    # Non-normalized values are rejected like displayed entity names.
    with pytest.raises(ValueError, match="soft context subject"):
        module.QueryPlanningRequest(
            request_id="query-request:soft-context-unnormalized",
            release_id="release-r1",
            original_query="有没有更详细的信息",
            as_of=NOW,
            soft_context_subject=" 优必选 ",
        )


def test_s8p2_planning_proposal_taxonomy_and_safety_matrix_is_machine_validated() -> (
    None
):
    module = _module()
    valid_cases = (
        (
            "information",
            "A",
            "information_retrieval",
            ("company",),
            ("exact", "web"),
            "universal",
            (),
            2,
            "universal",
        ),
        (
            "ordinary-refusal",
            "F",
            "ordinary_refusal",
            (),
            (),
            None,
            (),
            0,
            "disabled",
        ),
        (
            "interface-control",
            "control",
            "interface_control",
            (),
            (),
            None,
            (),
            0,
            "disabled",
        ),
        (
            "safety-default",
            "F",
            "safety_guidance",
            (),
            (),
            None,
            (),
            0,
            "disabled",
        ),
        (
            "safety-official",
            "F",
            "safety_guidance",
            (),
            ("web",),
            "official_only",
            ("sz.gov.cn",),
            2,
            "official_only",
        ),
    )
    for (
        token,
        behavior_class,
        interaction_mode,
        domains,
        lanes,
        web_mode,
        allowed_web_domains,
        max_web_results,
        expected_web_mode,
    ) in valid_cases:
        request = _request(
            module,
            token=f"s8p2-valid-{token}",
            query=f"S8P2 valid planning form: {token}",
        )

        def provider(
            value: Any,
            *,
            case_token: str = token,
            case_behavior: str = behavior_class,
            case_interaction: str = interaction_mode,
            case_domains: tuple[str, ...] = domains,
            case_lanes: tuple[str, ...] = lanes,
            case_web_mode: str | None = web_mode,
            case_allowed_domains: tuple[str, ...] = allowed_web_domains,
            case_max_web_results: int = max_web_results,
        ) -> Any:
            return _proposal(
                module,
                value,
                token=f"s8p2-valid-{case_token}",
                behavior_class=case_behavior,
                interaction_mode=case_interaction,
                domains=case_domains,
                lanes=case_lanes,
                max_provider_calls=(1 if case_lanes else 0),
                web_mode=case_web_mode,
                allowed_web_domains=case_allowed_domains,
                max_web_results=case_max_web_results,
            )

        plan = _planner(module, provider).plan(request)
        assert plan.behavior_class == behavior_class
        assert plan.interaction_mode == interaction_mode
        assert plan.domains == domains
        assert plan.lanes == lanes
        assert plan.web_policy.mode == expected_web_mode

    hostile_request = _request(
        module,
        token="s8p2-hostile-matrix",
        query="S8P2 hostile planning form",
    )
    valid_proposal = _proposal(
        module,
        hostile_request,
        token="s8p2-hostile-base",
        behavior_class="A",
        interaction_mode="information_retrieval",
        domains=("company",),
        lanes=("exact", "web"),
        max_provider_calls=1,
        web_mode="universal",
        max_web_results=2,
    )

    def hostile_payload(**updates: Any) -> dict[str, Any]:
        payload = _without_content_hashes(valid_proposal.model_dump(mode="json"))
        assert isinstance(payload, dict)
        payload.update(updates)
        return payload

    same_class_payload = {
        name: getattr(valid_proposal, name)
        for name in module.RecordedPlanningProposal.model_fields
        if name != "content_sha256"
    }
    same_class_payload.update(
        behavior_class="F",
        interaction_mode="safety_guidance",
        domains=("company",),
        lanes=("web",),
        web_mode="universal",
    )
    hostile_cases: tuple[tuple[str, Any], ...] = (
        (
            "wrong_schema",
            hostile_payload(schema_version="retrieval-plan-proposal-v2"),
        ),
        ("unknown_behavior", hostile_payload(behavior_class="H")),
        ("unknown_interaction", hostile_payload(interaction_mode="free_form")),
        (
            "model_proposed_blocking",
            hostile_payload(interaction_mode="blocking_clarification"),
        ),
        ("unknown_web_mode", hostile_payload(web_mode="private_web")),
        ("f_information", hostile_payload(behavior_class="F")),
        (
            "a_refusal",
            hostile_payload(behavior_class="A", interaction_mode="ordinary_refusal"),
        ),
        ("control_information", hostile_payload(behavior_class="control")),
        ("information_without_web", hostile_payload(lanes=["exact"])),
        (
            "refusal_with_public_web_execution",
            hostile_payload(
                behavior_class="F",
                interaction_mode="ordinary_refusal",
            ),
        ),
        (
            "safety_with_public_domain",
            hostile_payload(
                behavior_class="F",
                interaction_mode="safety_guidance",
                lanes=[],
                web_mode=None,
                max_web_results=0,
            ),
        ),
        (
            "safety_with_universal_web",
            hostile_payload(
                behavior_class="F",
                interaction_mode="safety_guidance",
                domains=[],
                lanes=["web"],
                web_mode="universal",
            ),
        ),
        (
            "official_only_outside_safety",
            hostile_payload(
                web_mode="official_only", allowed_web_domains=["sz.gov.cn"]
            ),
        ),
        (
            "official_safety_empty_allowlist",
            hostile_payload(
                behavior_class="F",
                interaction_mode="safety_guidance",
                domains=[],
                lanes=["web"],
                web_mode="official_only",
                allowed_web_domains=[],
            ),
        ),
        (
            "official_safety_zero_provider_bound",
            hostile_payload(
                behavior_class="F",
                interaction_mode="safety_guidance",
                domains=[],
                lanes=["web"],
                web_mode="official_only",
                allowed_web_domains=["sz.gov.cn"],
                max_provider_calls=0,
            ),
        ),
        (
            "official_safety_zero_result_bound",
            hostile_payload(
                behavior_class="F",
                interaction_mode="safety_guidance",
                domains=[],
                lanes=["web"],
                web_mode="official_only",
                allowed_web_domains=["sz.gov.cn"],
                max_web_results=0,
            ),
        ),
        (
            "same_class_model_construct_safety_crosswire",
            module.RecordedPlanningProposal.model_construct(**same_class_payload),
        ),
    )
    accepted_hostile_cases: list[str] = []
    for case_name, provider_value in hostile_cases:

        def hostile_provider(_: Any, *, value: Any = provider_value) -> Any:
            return value

        try:
            _planner(module, hostile_provider).plan(hostile_request)
        except module.InvalidRetrievalPlanError as exc:
            assert exc.reason_code == "invalid_planning_proposal"
        else:
            accepted_hostile_cases.append(case_name)

    if accepted_hostile_cases:
        raise _MissingS8P2ProposalTaxonomyValidation(
            "accepted hostile planning proposal cases: "
            + ",".join(accepted_hostile_cases)
        )

    review_request = _request(
        module,
        token="s8p2-candidate-review",
        query="联合大学 S8P2 Candidate review request",
    )
    review_base = _proposal(
        module,
        review_request,
        token="s8p2-candidate-review-base",
        behavior_class="A",
        interaction_mode="information_retrieval",
        domains=("company",),
        lanes=("exact", "web"),
        max_candidates=2,
        max_provider_calls=1,
        web_mode="universal",
        max_web_results=2,
    )

    def review_payload(**updates: Any) -> dict[str, Any]:
        payload = _without_content_hashes(review_base.model_dump(mode="json"))
        assert isinstance(payload, dict)
        payload.update(updates)
        return payload

    review_cases = (
        (
            "model_authored_official_domain",
            review_payload(
                behavior_class="F",
                interaction_mode="safety_guidance",
                domains=[],
                lanes=["web"],
                max_provider_calls=1,
                web_mode="official_only",
                allowed_web_domains=["attacker.example"],
                max_web_results=1,
            ),
            "unsupported_official_web_domain",
        ),
        (
            "zero_information_provider_budget",
            review_payload(max_provider_calls=0),
            "invalid_planning_proposal",
        ),
        (
            "negative_web_result_budget",
            review_payload(max_web_results=-1),
            "invalid_planning_proposal",
        ),
        (
            "unbounded_web_result_budget",
            review_payload(max_web_results=999_999),
            "budget_exceeded",
        ),
    )
    open_review_findings: list[str] = []
    for case_name, provider_value, expected_reason in review_cases:

        def review_provider(_: Any, *, value: Any = provider_value) -> Any:
            return value

        try:
            _planner(module, review_provider).plan(review_request)
        except module.InvalidRetrievalPlanError as exc:
            assert exc.reason_code == expected_reason
        else:
            open_review_findings.append(case_name)

    ambiguous_catalog = _institution_catalog(module)
    non_information_cases = (
        ("ordinary_refusal", "F", (), (), None),
        ("safety_guidance", "F", (), (), None),
        ("interface_control", "control", (), (), None),
    )
    for (
        interaction_mode,
        behavior_class,
        domains,
        lanes,
        web_mode,
    ) in non_information_cases:

        def non_information_provider(
            value: Any,
            *,
            case_interaction: str = interaction_mode,
            case_behavior: str = behavior_class,
            case_domains: tuple[str, ...] = domains,
            case_lanes: tuple[str, ...] = lanes,
            case_web_mode: str | None = web_mode,
        ) -> Any:
            return _proposal(
                module,
                value,
                token=f"s8p2-ambiguous-{case_interaction}",
                behavior_class=case_behavior,
                interaction_mode=case_interaction,
                domains=case_domains,
                lanes=case_lanes,
                max_provider_calls=0,
                web_mode=case_web_mode,
            )

        try:
            non_information_plan = _planner(
                module,
                non_information_provider,
                institution_catalog=ambiguous_catalog,
            ).plan(review_request)
        except ValueError:
            open_review_findings.append(f"ambiguity_replaced_{interaction_mode}")
        else:
            if non_information_plan.interaction_mode != interaction_mode:
                open_review_findings.append(f"ambiguity_replaced_{interaction_mode}")

    if open_review_findings:
        raise _MissingS8P2CandidateReviewHardening(
            "open S8P2 Candidate review findings: " + ",".join(open_review_findings)
        )


def test_query_planning_preserves_a_g_safety_and_enumeration_policy() -> None:
    module = _module()

    information_cases = (
        ("A", "介绍清华的丁文伯", ("professor",), ("exact", "web")),
        ("B", "深圳有哪些做灵巧手的企业", ("company",), ("lexical", "vector", "web")),
        (
            "C",
            "这位教授参与创立了哪些企业",
            ("professor", "company"),
            ("relationship", "web"),
        ),
        (
            "D",
            "深圳具身智能的教授、企业、论文和专利有哪些",
            PUBLIC_DOMAINS,
            ("structured", "lexical", "vector", "relationship", "web"),
        ),
        (
            "E",
            "比较两条机器人数据生成技术路线",
            ("company", "paper", "patent"),
            ("internal_reference", "relationship", "web"),
        ),
        (
            "G",
            "按已选中的王教授继续查其论文",
            ("professor", "paper"),
            ("relationship", "web"),
        ),
    )
    observed_lane_sets: set[tuple[str, ...]] = set()
    taxonomy_plans: dict[str, Any] = {}
    for behavior_class, query, domains, lanes in information_cases:
        request = _request(
            module,
            token=f"taxonomy-{behavior_class}",
            query=query,
        )

        def taxonomy_provider(
            value: Any,
            *,
            expected_request: Any = request,
            expected_class: str = behavior_class,
            expected_domains: tuple[str, ...] = domains,
            expected_lanes: tuple[str, ...] = lanes,
        ) -> Any:
            assert value == expected_request
            assert value.content_sha256 == expected_request.content_sha256
            return _proposal(
                module,
                value,
                token=f"taxonomy-{expected_class}",
                behavior_class=expected_class,
                interaction_mode="information_retrieval",
                domains=expected_domains,
                lanes=expected_lanes,
                professor_vector_view=("research" if expected_class == "D" else None),
            )

        recorded_proposal = taxonomy_provider(request)
        plan = _planner(module, taxonomy_provider).plan(request)
        taxonomy_plans[behavior_class] = plan
        _assert_plan_identity(module, request, plan)
        assert plan.behavior_class == behavior_class
        assert plan.interaction_mode == "information_retrieval"
        assert plan.domains == domains
        assert plan.web_policy.mode == "universal"
        assert "web" in plan.lanes
        assert (
            plan.planning_trace.proposal_id
            == f"planning-proposal:taxonomy-{behavior_class}"
        )
        assert plan.planning_trace.proposal_sha256 == recorded_proposal.content_sha256
        observed_lane_sets.add(plan.lanes)

    assert len(observed_lane_sets) > 1

    alternate_a_request = _request(
        module,
        token="taxonomy-A-cross-domain",
        query="核验公司 company:1 的专利 CN117873146A 及申请关系",
    )

    def alternate_a_provider(value: Any) -> Any:
        return _proposal(
            module,
            value,
            token="taxonomy-A-cross-domain",
            behavior_class="A",
            interaction_mode="information_retrieval",
            domains=("company", "patent"),
            lanes=("exact", "relationship", "web"),
            paths=(
                _path(
                    module,
                    relationship_type_id="company_has_patent",
                    direction="company_to_patent",
                    source_type="company",
                    target_type="patent",
                ),
            ),
        )

    alternate_a = _planner(module, alternate_a_provider).plan(alternate_a_request)
    assert alternate_a.behavior_class == taxonomy_plans["A"].behavior_class == "A"
    assert alternate_a.lanes != taxonomy_plans["A"].lanes
    assert alternate_a.domains != taxonomy_plans["A"].domains
    assert len(alternate_a.lanes) > 1
    assert alternate_a.relationship_paths

    refusal_request = _request(
        module,
        token="ordinary-refusal",
        query="请替我写一首与深圳科创无关的流行歌曲",
    )

    def refusal_provider(value: Any) -> Any:
        return _proposal(
            module,
            value,
            token="ordinary-refusal",
            behavior_class="F",
            interaction_mode="ordinary_refusal",
            domains=(),
            lanes=(),
        )

    refusal = _planner(module, refusal_provider).plan(refusal_request)
    assert refusal.behavior_class == "F"
    assert refusal.interaction_mode == "ordinary_refusal"
    assert refusal.domains == ()
    assert refusal.lanes == ()
    assert refusal.web_policy.mode == "disabled"

    safety_request = _request(
        module,
        token="safety-guidance",
        query="在深圳怎样合法避开黄赌毒风险，并找到官方求助渠道？",
    )

    def safety_provider(value: Any) -> Any:
        return _proposal(
            module,
            value,
            token="safety-guidance",
            behavior_class="F",
            interaction_mode="safety_guidance",
            domains=(),
            lanes=(),
        )

    safety = _planner(module, safety_provider).plan(safety_request)
    assert safety.behavior_class == "F"
    assert safety.interaction_mode == "safety_guidance"
    assert safety.domains == ()
    assert safety.lanes == ()
    assert safety.web_policy.mode == "disabled"
    assert "venue_discovery" not in safety.allowed_operations
    assert "general_web_search" not in safety.allowed_operations

    official_request = _request(
        module,
        token="safety-official-only",
        query="请查询深圳当前官方求助电话和最新政策页面",
    )

    def official_provider(value: Any) -> Any:
        return _proposal(
            module,
            value,
            token="safety-official-only",
            behavior_class="F",
            interaction_mode="safety_guidance",
            domains=(),
            lanes=("web",),
            max_provider_calls=1,
            web_mode="official_only",
            allowed_web_domains=("sz.gov.cn",),
            max_web_results=3,
        )

    official = _planner(module, official_provider).plan(official_request)
    assert official.behavior_class == "F"
    assert official.interaction_mode == "safety_guidance"
    assert official.domains == ()
    assert official.lanes == ("web",)
    assert official.web_policy.mode == "official_only"
    assert official.web_policy.allowed_domains == ("sz.gov.cn",)
    assert official.web_policy.max_provider_calls == 1
    assert official.web_policy.max_results == 3
    assert set(official.allowed_operations) == {"official_policy_lookup"}

    control_request = _request(
        module,
        token="interface-control",
        query="把当前结果切换成表格显示",
    )

    def control_provider(value: Any) -> Any:
        return _proposal(
            module,
            value,
            token="interface-control",
            behavior_class="control",
            interaction_mode="interface_control",
            domains=(),
            lanes=(),
        )

    control = _planner(module, control_provider).plan(control_request)
    assert control.interaction_mode == "interface_control"
    assert control.domains == ()
    assert control.lanes == ()
    assert control.web_policy.mode == "disabled"

    finite_universe = module.FiniteEnumerationUniverse(
        universe_id="universe:company-1-patents",
        release_id="release-r1",
        scope="all accepted Patents whose applicant is company:1",
        member_ids=("patent:1", "patent:2", "patent:3"),
        source_evidence_ids=("projection:company-1-patents",),
        as_of=NOW,
    )
    enumeration_cases = (
        (
            "finite",
            module.EnumerationPlanningContext(
                requested=True,
                scope=finite_universe.scope,
                as_of=NOW,
                finite_universe=finite_universe,
                required_member_ids=(),
            ),
            "exhaustive_bounded",
            finite_universe.member_ids,
        ),
        (
            "required",
            module.EnumerationPlanningContext(
                requested=True,
                scope="the three accepted Companies named by the user",
                as_of=NOW,
                finite_universe=None,
                required_member_ids=("company:1", "company:2", "company:3"),
            ),
            "required_members",
            ("company:1", "company:2", "company:3"),
        ),
        (
            "open-world",
            module.EnumerationPlanningContext(
                requested=True,
                scope="representative Shenzhen embodied-intelligence Companies",
                as_of=NOW,
                finite_universe=None,
                required_member_ids=(),
            ),
            "representative",
            (),
        ),
    )
    for (
        token,
        enumeration_context,
        expected_mode,
        expected_members,
    ) in enumeration_cases:
        request = _request(
            module,
            token=f"enumeration-{token}",
            query=f"synthetic list request: {token}",
            enumeration_context=enumeration_context,
        )

        def enumeration_provider(
            value: Any,
            *,
            expected_request: Any = request,
            mode: str = expected_mode,
        ) -> Any:
            assert value == expected_request
            assert value.content_sha256 == expected_request.content_sha256
            return _proposal(
                module,
                value,
                token=f"enumeration-{mode}",
                behavior_class="D",
                interaction_mode="information_retrieval",
                domains=("company", "patent"),
                lanes=("structured", "web"),
                enumeration_mode=mode,
            )

        plan = _planner(module, enumeration_provider).plan(request)
        policy = plan.enumeration_policy
        assert policy.mode == expected_mode
        assert policy.scope == enumeration_context.scope
        assert policy.as_of == NOW
        assert (
            policy.required_member_ids == expected_members
            if expected_mode == "required_members"
            else policy.required_member_ids == ()
        )
        if expected_mode == "exhaustive_bounded":
            assert policy.finite_universe_id == finite_universe.universe_id
            assert policy.eligible_member_ids == expected_members
        else:
            assert policy.finite_universe_id is None
        if expected_mode == "representative":
            assert policy.exhaustive is False
            assert policy.continuation_state == "available"


def test_representative_plan_without_context_defaults_a_valid_policy() -> None:
    module = _module()
    request = _request(
        module,
        token="representative-without-context",
        query="他的代表作是什么",
        displayed_entity_ids=("professor:anchor",),
    )

    def representative_provider(value: Any) -> Any:
        return _proposal(
            module,
            value,
            token="representative-without-context",
            behavior_class="C",
            interaction_mode="information_retrieval",
            domains=("paper",),
            lanes=("relationship", "web"),
            paths=(
                _path(
                    module,
                    relationship_type_id="professor_authored_paper",
                    direction="professor_to_paper",
                    source_type="professor",
                    target_type="paper",
                ),
            ),
            enumeration_mode="representative",
        )

    plan = _planner(module, representative_provider).plan(request)
    policy = plan.enumeration_policy
    assert policy is not None
    assert policy.mode == "representative"
    assert policy.scope == request.original_query
    assert policy.as_of == NOW
    assert policy.exhaustive is False
    assert policy.continuation_state == "available"
    assert policy.finite_universe_id is None
    assert not policy.required_member_ids

    def plain_provider(value: Any) -> Any:
        return _proposal(
            module,
            value,
            token="plain-without-context",
            behavior_class="A",
            interaction_mode="information_retrieval",
            domains=("professor",),
            lanes=("exact", "web"),
            enumeration_mode=None,
        )

    plain_plan = _planner(module, plain_provider).plan(request)
    assert plain_plan.enumeration_policy is None


def _institution_catalog(module: Any) -> Any:
    return module.InstitutionCatalog(
        catalog_id="institution-catalog:fixture",
        catalog_version="synthetic-v1",
        release_id="release-r1",
        entries=(
            module.InstitutionCatalogEntry(
                canonical_id="institution:tsinghua",
                canonical_name="清华大学",
                aliases=("清华",),
            ),
            module.InstitutionCatalogEntry(
                canonical_id="institution:tsinghua-sigs",
                canonical_name="清华大学深圳国际研究生院",
                aliases=("清华SIGS", "清华深圳"),
            ),
            module.InstitutionCatalogEntry(
                canonical_id="institution:sustech",
                canonical_name="南方科技大学",
                aliases=("南科大", "联合大学"),
            ),
            module.InstitutionCatalogEntry(
                canonical_id="institution:szu",
                canonical_name="深圳大学",
                aliases=("深大", "深大星图"),
            ),
            module.InstitutionCatalogEntry(
                canonical_id="institution:cuhk-sz",
                canonical_name="香港中文大学（深圳）",
                aliases=("港中大深圳", "联合大学"),
            ),
        ),
    )


def test_query_planning_protects_slots_rewrites_institution_matrix_and_rejects_invalid_plans() -> (
    None
):
    module = _module()
    institution_catalog = _institution_catalog(module)
    protected_request = _request(
        module,
        token="protected-rewrites",
        query=(
            "请核验 2024 年深圳“星海机器人”的专利 CN117873146A，不要包含海外专利，"
            "并按公司到专利方向查看上述公司"
        ),
        displayed_entity_ids=("company:star-sea", "company:other"),
    )
    retained_values = (
        "2024",
        "深圳",
        "星海机器人",
        "CN117873146A",
        "海外专利",
        "company_to_patent",
        "company:star-sea",
        "company:other",
    )
    view_kinds = (
        "original",
        "contextual",
        "canonical_alias",
        "semantic",
        "domain",
        "relationship",
        "web",
    )
    views = tuple(
        _view(
            module,
            request=protected_request,
            kind=kind,
            text=f"{kind}: {protected_request.original_query}",
            retained_values=retained_values,
        )
        for kind in view_kinds
    )
    valid_path = _path(
        module,
        relationship_type_id="company_has_patent",
        direction="company_to_patent",
        source_type="company",
        target_type="patent",
    )

    def valid_provider(value: Any) -> Any:
        assert value == protected_request
        assert value.content_sha256 == protected_request.content_sha256
        return _proposal(
            module,
            value,
            token="protected-rewrites",
            behavior_class="C",
            interaction_mode="information_retrieval",
            domains=("company", "patent"),
            lanes=("exact", "relationship", "web"),
            views=views,
            paths=(valid_path,),
        )

    plan = _planner(
        module,
        valid_provider,
        institution_catalog=institution_catalog,
    ).plan(protected_request)
    _assert_plan_identity(module, protected_request, plan)
    slots = {(slot.kind, slot.raw_text) for slot in plan.protected_slots}
    assert {
        ("year", "2024"),
        ("geography", "深圳"),
        ("explicit_name", "星海机器人"),
        ("exact_identifier", "CN117873146A"),
        ("negation", "海外专利"),
        ("relationship_direction", "公司到专利"),
    } <= slots
    displayed_slot = next(
        slot for slot in plan.protected_slots if slot.kind == "displayed_entity_set"
    )
    assert displayed_slot.entity_ids == protected_request.displayed_entity_ids
    protected_ids = {slot.slot_id for slot in plan.protected_slots}
    assert tuple(view.kind for view in plan.query_views) == view_kinds
    assert all(
        view.original_query_sha256 == protected_request.original_query_sha256
        for view in plan.query_views
    )
    assert all(
        set(view.protected_slot_ids) == protected_ids for view in plan.query_views
    )
    assert all(
        view.producer_kind and view.producer_version for view in plan.query_views
    )
    assert plan.structured_constraints.displayed_entity_ids == (
        "company:star-sea",
        "company:other",
    )
    assert plan.structured_constraints.geography == ("深圳",)
    assert plan.structured_constraints.excluded_terms == ("海外专利",)
    contextual_view = next(
        view for view in plan.query_views if view.kind == "contextual"
    )
    assert contextual_view.bound_entity_ids == protected_request.displayed_entity_ids
    assert plan.relationship_paths == (valid_path,)
    repeated_plan = _planner(
        module,
        valid_provider,
        institution_catalog=institution_catalog,
    ).plan(protected_request)
    assert repeated_plan == plan
    assert repeated_plan.content_sha256 == plan.content_sha256
    valid_recorded_proposal = valid_provider(protected_request)
    assert plan.planning_trace.proposal_sha256 == valid_recorded_proposal.content_sha256

    proposal_variant_views = tuple(
        (
            _view(
                module,
                request=protected_request,
                kind="semantic",
                text=f"semantic-expanded: {protected_request.original_query} 机器人申请关系",
                retained_values=retained_values,
            )
            if view.kind == "semantic"
            else view
        )
        for view in views
    )

    def proposal_variant_provider(value: Any) -> Any:
        return _proposal(
            module,
            value,
            token="protected-rewrites",
            behavior_class="C",
            interaction_mode="information_retrieval",
            domains=("company", "patent"),
            lanes=("exact", "relationship", "web"),
            views=proposal_variant_views,
            paths=(valid_path,),
        )

    proposal_variant = proposal_variant_provider(protected_request)
    proposal_variant_plan = _planner(
        module,
        proposal_variant_provider,
        institution_catalog=institution_catalog,
    ).plan(protected_request)
    assert proposal_variant.proposal_id == valid_recorded_proposal.proposal_id
    assert proposal_variant.request_sha256 == valid_recorded_proposal.request_sha256
    assert proposal_variant.content_sha256 != valid_recorded_proposal.content_sha256
    assert (
        proposal_variant_plan.planning_trace.proposal_sha256
        == proposal_variant.content_sha256
    )
    assert proposal_variant_plan.request_sha256 == plan.request_sha256
    assert proposal_variant_plan.content_sha256 != plan.content_sha256
    assert proposal_variant_plan.protected_slots == plan.protected_slots

    changed_membership_request = module.QueryPlanningRequest(
        request_id=protected_request.request_id,
        release_id=protected_request.release_id,
        original_query=protected_request.original_query,
        as_of=protected_request.as_of,
        displayed_entity_ids=("company:star-sea",),
        enumeration_context=None,
        ambiguity_candidates=(),
    )
    changed_retained_values = tuple(
        value for value in retained_values if value != "company:other"
    )
    changed_views = tuple(
        _view(
            module,
            request=changed_membership_request,
            kind=kind,
            text=f"{kind}: {changed_membership_request.original_query}",
            retained_values=changed_retained_values,
        )
        for kind in view_kinds
    )

    def changed_membership_provider(value: Any) -> Any:
        return _proposal(
            module,
            value,
            token="protected-rewrites-one-member",
            behavior_class="C",
            interaction_mode="information_retrieval",
            domains=("company", "patent"),
            lanes=("exact", "relationship", "web"),
            views=changed_views,
            paths=(valid_path,),
        )

    changed_membership_plan = _planner(
        module,
        changed_membership_provider,
        institution_catalog=institution_catalog,
    ).plan(changed_membership_request)
    assert changed_membership_request.request_id == protected_request.request_id
    assert changed_membership_request.content_sha256 != protected_request.content_sha256
    assert changed_membership_plan.content_sha256 != plan.content_sha256
    assert changed_membership_plan.structured_constraints.displayed_entity_ids == (
        "company:star-sea",
    )

    institution_cases = (
        (
            "full-name",
            "清华大学深圳国际研究生院有哪些具身智能教授",
            (("resolved", "institution:tsinghua-sigs", ()),),
            ("清华大学深圳国际研究生院",),
            "具身智能教授",
        ),
        (
            "alias",
            "清华SIGS有哪些具身智能教授",
            (("resolved", "institution:tsinghua-sigs", ()),),
            ("清华SIGS",),
            "具身智能教授",
        ),
        (
            "injected-alias",
            "深大星图有哪些具身智能教授",
            (("resolved", "institution:szu", ()),),
            ("深大星图",),
            "具身智能教授",
        ),
        (
            "multiple",
            "比较南科大和深大的机器人研究",
            (
                ("resolved", "institution:sustech", ()),
                ("resolved", "institution:szu", ()),
            ),
            ("南科大", "深大"),
            "机器人研究",
        ),
        (
            "ambiguous",
            "联合大学有哪些教授",
            (
                (
                    "ambiguous",
                    None,
                    ("institution:cuhk-sz", "institution:sustech"),
                ),
            ),
            ("联合大学",),
            "教授",
        ),
        (
            "unknown",
            "未来科学大学有哪些教授",
            (("unresolved", None, ()),),
            ("未来科学大学",),
            "教授",
        ),
        (
            "absent",
            "具身智能有哪些研究方向",
            (),
            (),
            "具身智能有哪些研究方向",
        ),
        (
            "repeated",
            "南科大和南方科技大学有哪些机器人教授",
            (("resolved", "institution:sustech", ()),),
            ("南科大", "南方科技大学"),
            "机器人教授",
        ),
        (
            "overlap",
            "清华大学深圳国际研究生院有哪些教授",
            (("resolved", "institution:tsinghua-sigs", ()),),
            ("清华大学深圳国际研究生院",),
            "教授",
        ),
    )
    catalog_entries = {
        entry.canonical_id: entry for entry in institution_catalog.entries
    }
    catalog_terms = {
        term
        for entry in institution_catalog.entries
        for term in (entry.canonical_name, *entry.aliases)
    }
    matrix_results: dict[str, Any] = {}
    for (
        token,
        query,
        expected_slots,
        expected_raw_texts,
        expected_pure_topic,
    ) in institution_cases:
        request = _request(module, token=f"institution-{token}", query=query)

        def provider(value: Any, *, case_token: str = token) -> Any:
            return _proposal(
                module,
                value,
                token=f"institution-{case_token}",
                behavior_class="B",
                interaction_mode="information_retrieval",
                domains=("professor",),
                lanes=("structured", "lexical", "vector", "web"),
                professor_vector_view="research",
            )

        matrix_plan = _planner(
            module,
            provider,
            institution_catalog=institution_catalog,
        ).plan(request)
        matrix_results[token] = matrix_plan
        actual_slots = tuple(
            (
                slot.resolution_state,
                slot.canonical_id,
                tuple(sorted(slot.candidate_ids)),
            )
            for slot in matrix_plan.institution_slots
        )
        assert actual_slots == expected_slots
        occurrences = tuple(
            occurrence
            for slot in matrix_plan.institution_slots
            for occurrence in slot.occurrences
        )
        assert tuple(occurrence.raw_text for occurrence in occurrences) == (
            expected_raw_texts
        )
        assert tuple(
            (occurrence.start, occurrence.end) for occurrence in occurrences
        ) == tuple(
            (query.index(raw_text), query.index(raw_text) + len(raw_text))
            for raw_text in expected_raw_texts
        )
        assert all(
            query[occurrence.start : occurrence.end] == occurrence.raw_text
            for occurrence in occurrences
        )
        assert all(
            slot.catalog_sha256 == institution_catalog.content_sha256
            for slot in matrix_plan.institution_slots
        )
        assert all(
            slot.catalog_version == institution_catalog.catalog_version
            for slot in matrix_plan.institution_slots
        )
        assert all(
            slot.release_id == request.release_id
            for slot in matrix_plan.institution_slots
        )
        for slot, (_, expected_canonical_id, expected_candidate_ids) in zip(
            matrix_plan.institution_slots,
            expected_slots,
            strict=True,
        ):
            expected_ids = set(expected_candidate_ids)
            if expected_canonical_id is not None:
                expected_ids.add(expected_canonical_id)
            actual_candidates = {
                candidate.canonical_id: candidate.canonical_name
                for candidate in slot.candidates
            }
            assert set(actual_candidates) == expected_ids
            assert actual_candidates == {
                canonical_id: catalog_entries[canonical_id].canonical_name
                for canonical_id in expected_ids
            }
        assert catalog_terms.isdisjoint(
            matrix_plan.rewrite_policy.generic_topic_stopwords
        )
        assert matrix_plan.pure_topic_text == expected_pure_topic
        if matrix_plan.interaction_mode != "blocking_clarification":
            assert matrix_plan.lane_queries
            assert all(
                lane_query.release_id == request.release_id
                and lane_query.catalog_sha256 == institution_catalog.content_sha256
                and lane_query.pure_topic_text == matrix_plan.pure_topic_text
                and matrix_plan.pure_topic_text in lane_query.query_text
                for lane_query in matrix_plan.lane_queries
            )
            resolved_ids = tuple(
                slot.canonical_id
                for slot in matrix_plan.institution_slots
                if slot.canonical_id is not None
            )
            assert all(
                lane_query.institution_constraint_ids == resolved_ids
                for lane_query in matrix_plan.lane_queries
            )
        if token == "ambiguous":
            assert matrix_plan.interaction_mode == "blocking_clarification"
            assert matrix_plan.lanes == ()
            assert matrix_plan.web_policy.mode == "disabled"
        if token == "absent":
            assert matrix_plan.institution_slots == ()
            assert matrix_plan.pure_topic_text == request.original_query
        if token == "overlap":
            assert all(
                slot.canonical_id != "institution:tsinghua"
                for slot in matrix_plan.institution_slots
            )

    assert (
        matrix_results["full-name"].pure_topic_text
        == matrix_results["alias"].pure_topic_text
    )
    assert matrix_results["full-name"].lane_queries[0].institution_constraint_ids == (
        "institution:tsinghua-sigs",
    )
    assert matrix_results["alias"].lane_queries[0].institution_constraint_ids == (
        "institution:tsinghua-sigs",
    )
    assert matrix_results["injected-alias"].lane_queries[
        0
    ].institution_constraint_ids == ("institution:szu",)
    assert "机器人教授" in matrix_results["repeated"].pure_topic_text
    assert "教授" in matrix_results["overlap"].pure_topic_text

    valid_proposal = _proposal(
        module,
        protected_request,
        token="invalid-base",
        behavior_class="C",
        interaction_mode="information_retrieval",
        domains=("company", "patent"),
        lanes=("exact", "relationship", "web"),
        views=views,
        paths=(valid_path,),
    )

    def fresh_payload() -> dict[str, Any]:
        payload = _without_content_hashes(valid_proposal.model_dump(mode="json"))
        assert isinstance(payload, dict)
        return payload

    lost_slot_payload = fresh_payload()
    lost_slot_payload["query_views"][-1]["retained_protected_values"] = [
        value for value in retained_values if value != "CN117873146A"
    ]

    unsupported_path_payload = fresh_payload()
    unsupported_path_payload["relationship_paths"] = [
        {
            "relationship_type_id": "invented_company_controls_professor",
            "direction": "company_to_professor",
            "source_type": "company",
            "target_type": "professor",
        }
    ]

    wrong_direction_payload = fresh_payload()
    wrong_direction_payload["relationship_paths"] = [
        {
            "relationship_type_id": "company_has_patent",
            "direction": "patent_to_company",
            "source_type": "company",
            "target_type": "patent",
        }
    ]

    unsupported_operation_payload = fresh_payload()
    unsupported_operation_payload["lanes"] = ["filesystem_scan", "web"]

    excessive_budget_payload = fresh_payload()
    excessive_budget_payload["max_candidates"] = 41
    excessive_budget_payload["max_provider_calls"] = 4

    wrong_request_payload = fresh_payload()
    wrong_request_payload["request_sha256"] = "0" * 64

    invalid_proposals = (
        ("lost_protected_slot", lost_slot_payload),
        ("unsupported_relationship_path", unsupported_path_payload),
        ("unsupported_relationship_direction", wrong_direction_payload),
        ("unsupported_operation", unsupported_operation_payload),
        ("budget_exceeded", excessive_budget_payload),
        ("proposal_request_mismatch", wrong_request_payload),
    )

    def provider_for(payload: dict[str, Any]) -> Any:
        def return_payload(_: Any) -> dict[str, Any]:
            return payload

        return return_payload

    for reason_code, invalid_payload in invalid_proposals:
        invalid_planner = _planner(
            module,
            provider_for(invalid_payload),
            institution_catalog=institution_catalog,
        )
        with pytest.raises(module.InvalidRetrievalPlanError) as caught:
            invalid_planner.plan(protected_request)
        assert caught.value.reason_code == reason_code

    wrong_release_catalog = module.InstitutionCatalog(
        catalog_id=institution_catalog.catalog_id,
        catalog_version=institution_catalog.catalog_version,
        release_id="release-r2",
        entries=institution_catalog.entries,
    )
    with pytest.raises(module.InvalidRetrievalPlanError) as caught:
        _planner(
            module,
            valid_provider,
            institution_catalog=wrong_release_catalog,
        ).plan(protected_request)
    assert caught.value.reason_code == "catalog_release_mismatch"


def _ambiguity_policy(
    module: Any,
    *,
    token: str,
    minimum_evidence_count: int,
    confidence_threshold: float,
    minimum_lead_margin: float,
) -> Any:
    return module.AmbiguityPolicy(
        policy_id=f"ambiguity-policy:synthetic:{token}",
        policy_version=f"fixture-only-not-calibrated:{token}",
        entity_type="professor",
        minimum_evidence_count=minimum_evidence_count,
        confidence_threshold=confidence_threshold,
        minimum_lead_margin=minimum_lead_margin,
    )


def _ambiguity_candidate(
    module: Any,
    *,
    token: str,
    evidence_ids: tuple[str, ...],
    evidence_confidence: float,
    model_confidence: float = 0.99,
    protected_constraint_conflicts: tuple[str, ...] = (),
) -> Any:
    return module.AmbiguityCandidate(
        candidate_id=f"candidate:{token}",
        entity_type="professor",
        canonical_id=f"professor:{token}",
        display_name="王教授",
        evidence_ids=evidence_ids,
        evidence_confidence=evidence_confidence,
        model_confidence=model_confidence,
        protected_constraint_conflicts=protected_constraint_conflicts,
        discriminators=(
            (
                module.CandidateDiscriminator(
                    kind="institution",
                    value=f"institution:{token}",
                    evidence_ids=evidence_ids[:1],
                ),
            )
            if evidence_ids
            else ()
        ),
    )


def test_query_planning_applies_injected_ambiguity_mechanics_without_calibrated_defaults() -> (
    None
):
    module = _module()
    policy_specs = (
        ("policy-a", 2, 0.75, 0.15, 0.93, 0.61, 0.84),
        ("policy-b", 3, 0.55, 0.05, 0.78, 0.45, 0.75),
    )
    dominant_checkpoint: dict[str, Any] = {}
    for (
        policy_token,
        minimum_evidence_count,
        confidence_threshold,
        minimum_lead_margin,
        dominant_confidence,
        alternative_confidence,
        close_confidence,
    ) in policy_specs:
        policy = _ambiguity_policy(
            module,
            token=policy_token,
            minimum_evidence_count=minimum_evidence_count,
            confidence_threshold=confidence_threshold,
            minimum_lead_margin=minimum_lead_margin,
        )

        def evidence_ids(token: str, count: int) -> tuple[str, ...]:
            return tuple(
                f"evidence:{policy_token}:{token}:{index}" for index in range(count)
            )

        dominant = _ambiguity_candidate(
            module,
            token=f"dominant-{policy_token}",
            evidence_ids=evidence_ids("dominant", minimum_evidence_count + 1),
            evidence_confidence=dominant_confidence,
        )
        alternative = _ambiguity_candidate(
            module,
            token=f"alternative-{policy_token}",
            evidence_ids=evidence_ids("alternative", minimum_evidence_count),
            evidence_confidence=alternative_confidence,
        )
        close_second = _ambiguity_candidate(
            module,
            token=f"close-second-{policy_token}",
            evidence_ids=evidence_ids("close", minimum_evidence_count),
            evidence_confidence=close_confidence,
        )
        constraint_conflict = _ambiguity_candidate(
            module,
            token=f"constraint-conflict-{policy_token}",
            evidence_ids=evidence_ids("conflict", minimum_evidence_count + 1),
            evidence_confidence=0.98,
            protected_constraint_conflicts=("institution:requested",),
        )
        model_only = _ambiguity_candidate(
            module,
            token=f"model-only-{policy_token}",
            evidence_ids=(),
            evidence_confidence=0.99,
            model_confidence=1.0,
        )
        cases = (
            (
                "dominant",
                (dominant, alternative),
                "non_blocking",
                dominant.canonical_id,
                "dominant_candidate",
            ),
            ("no-candidate", (), "blocking", None, "no_candidate"),
            (
                "multiple",
                (dominant, close_second),
                "blocking",
                None,
                "multiple_candidates",
            ),
            (
                "protected-conflict",
                (constraint_conflict, alternative),
                "blocking",
                None,
                "no_candidate",
            ),
            (
                "model-only",
                (model_only,),
                "blocking",
                None,
                "no_candidate",
            ),
        )
        for (
            token,
            candidates,
            expected_mode,
            expected_selected,
            expected_reason,
        ) in cases:
            request = _request(
                module,
                token=f"ambiguity-{policy_token}-{token}",
                query="介绍清华的王教授",
                ambiguity_candidates=candidates,
            )

            def provider(
                value: Any,
                *,
                case_token: str = token,
                current_policy_token: str = policy_token,
            ) -> Any:
                return _proposal(
                    module,
                    value,
                    token=f"ambiguity-{current_policy_token}-{case_token}",
                    behavior_class="G",
                    interaction_mode="information_retrieval",
                    domains=("professor",),
                    lanes=("exact", "structured", "web"),
                )

            first = _planner(
                module,
                provider,
                ambiguity_policy=policy,
            ).plan(request)
            second = _planner(
                module,
                provider,
                ambiguity_policy=policy,
            ).plan(request)
            assert first == second
            decision = first.ambiguity_decision
            assert decision.mode == expected_mode
            assert decision.selected_canonical_id == expected_selected
            assert decision.reason_code == expected_reason
            assert decision.policy_id == policy.policy_id
            assert decision.policy_version == policy.policy_version
            assert decision.policy_sha256 == policy.content_sha256
            assert decision.request_sha256 == request.content_sha256
            assert (
                decision.candidate_manifest_sha256
                == request.ambiguity_candidate_manifest_sha256
            )
            assert tuple(
                item.candidate_id for item in decision.candidate_traces
            ) == tuple(candidate.candidate_id for candidate in candidates)
            for trace, candidate in zip(
                decision.candidate_traces,
                candidates,
                strict=True,
            ):
                assert trace.candidate_sha256 == candidate.content_sha256
                assert trace.evidence_ids == candidate.evidence_ids
                assert trace.evidence_count == len(candidate.evidence_ids)
                assert trace.evidence_confidence == candidate.evidence_confidence
                assert (
                    trace.protected_constraint_conflicts
                    == candidate.protected_constraint_conflicts
                )
                expected_eligible = (
                    len(candidate.evidence_ids) >= policy.minimum_evidence_count
                    and candidate.evidence_confidence >= policy.confidence_threshold
                    and not candidate.protected_constraint_conflicts
                )
                assert trace.eligible is expected_eligible
                if candidate.protected_constraint_conflicts:
                    assert trace.rejection_reason == "protected_constraint_conflict"
                elif len(candidate.evidence_ids) < policy.minimum_evidence_count:
                    assert trace.rejection_reason == "insufficient_evidence"
                elif candidate.evidence_confidence < policy.confidence_threshold:
                    assert trace.rejection_reason == "below_confidence_threshold"
                else:
                    assert trace.rejection_reason is None
                assert trace.discriminators == candidate.discriminators
            if expected_mode == "blocking":
                assert first.interaction_mode == "blocking_clarification"
                assert first.lanes == ()
                assert first.web_policy.mode == "disabled"
                if expected_reason == "multiple_candidates":
                    assert decision.qualifying_candidate_ids == tuple(
                        candidate.candidate_id for candidate in candidates
                    )
                    lead_confidence, runner_up_confidence = sorted(
                        (candidate.evidence_confidence for candidate in candidates),
                        reverse=True,
                    )
                    assert decision.observed_lead_margin == pytest.approx(
                        lead_confidence - runner_up_confidence
                    )
                    assert decision.observed_lead_margin < policy.minimum_lead_margin
                else:
                    assert decision.qualifying_candidate_ids == ()
            else:
                assert first.interaction_mode == "information_retrieval"
                assert decision.viable_alternative_ids == (alternative.candidate_id,)
                assert decision.qualifying_candidate_ids == (dominant.candidate_id,)
                assert decision.observed_lead_margin == pytest.approx(
                    dominant.evidence_confidence - alternative.evidence_confidence
                )
                assert first.lanes
                if policy_token == "policy-a":
                    dominant_checkpoint = {
                        "request": request,
                        "provider": provider,
                        "policy": policy,
                        "plan": first,
                        "dominant": dominant,
                        "alternative": alternative,
                    }

    margin_lead = _ambiguity_candidate(
        module,
        token="margin-flip-lead",
        evidence_ids=("evidence:margin:lead:1", "evidence:margin:lead:2"),
        evidence_confidence=0.90,
    )
    margin_runner_up = _ambiguity_candidate(
        module,
        token="margin-flip-runner-up",
        evidence_ids=("evidence:margin:runner:1", "evidence:margin:runner:2"),
        evidence_confidence=0.80,
    )
    margin_request = _request(
        module,
        token="ambiguity-margin-flip",
        query="介绍清华的王教授",
        ambiguity_candidates=(margin_lead, margin_runner_up),
    )

    def margin_provider(value: Any) -> Any:
        return _proposal(
            module,
            value,
            token="ambiguity-margin-flip",
            behavior_class="G",
            interaction_mode="information_retrieval",
            domains=("professor",),
            lanes=("exact", "structured", "web"),
        )

    high_margin_policy = module.AmbiguityPolicy(
        policy_id="ambiguity-policy:margin-flip",
        policy_version="fixture-margin-flip",
        entity_type="professor",
        minimum_evidence_count=2,
        confidence_threshold=0.75,
        minimum_lead_margin=0.15,
    )
    low_margin_policy = module.AmbiguityPolicy(
        policy_id=high_margin_policy.policy_id,
        policy_version=high_margin_policy.policy_version,
        entity_type=high_margin_policy.entity_type,
        minimum_evidence_count=high_margin_policy.minimum_evidence_count,
        confidence_threshold=high_margin_policy.confidence_threshold,
        minimum_lead_margin=0.05,
    )
    assert {
        key: value
        for key, value in high_margin_policy.model_dump(mode="json").items()
        if key not in {"minimum_lead_margin", "content_sha256"}
    } == {
        key: value
        for key, value in low_margin_policy.model_dump(mode="json").items()
        if key not in {"minimum_lead_margin", "content_sha256"}
    }
    high_margin_plan = _planner(
        module,
        margin_provider,
        ambiguity_policy=high_margin_policy,
    ).plan(margin_request)
    low_margin_plan = _planner(
        module,
        margin_provider,
        ambiguity_policy=low_margin_policy,
    ).plan(margin_request)
    assert high_margin_plan.ambiguity_decision.observed_lead_margin == pytest.approx(
        0.10
    )
    assert low_margin_plan.ambiguity_decision.observed_lead_margin == pytest.approx(
        0.10
    )
    assert high_margin_plan.ambiguity_decision.mode == "blocking"
    assert high_margin_plan.ambiguity_decision.reason_code == "multiple_candidates"
    assert low_margin_plan.ambiguity_decision.mode == "non_blocking"
    assert low_margin_plan.ambiguity_decision.reason_code == "dominant_candidate"
    assert (
        low_margin_plan.ambiguity_decision.selected_canonical_id
        == margin_lead.canonical_id
    )
    assert high_margin_plan.ambiguity_decision.policy_sha256 == (
        high_margin_policy.content_sha256
    )
    assert low_margin_plan.ambiguity_decision.policy_sha256 == (
        low_margin_policy.content_sha256
    )
    assert high_margin_plan.content_sha256 != low_margin_plan.content_sha256

    base_policy = dominant_checkpoint["policy"]
    policy_only_variant = _ambiguity_policy(
        module,
        token="policy-a-version-variant",
        minimum_evidence_count=base_policy.minimum_evidence_count,
        confidence_threshold=base_policy.confidence_threshold,
        minimum_lead_margin=base_policy.minimum_lead_margin,
    )
    variant_plan = _planner(
        module,
        dominant_checkpoint["provider"],
        ambiguity_policy=policy_only_variant,
    ).plan(dominant_checkpoint["request"])
    assert variant_plan.ambiguity_decision.mode == "non_blocking"
    assert (
        variant_plan.ambiguity_decision.selected_canonical_id
        == dominant_checkpoint["dominant"].canonical_id
    )
    assert variant_plan.ambiguity_decision.policy_sha256 != base_policy.content_sha256
    assert variant_plan.content_sha256 != dominant_checkpoint["plan"].content_sha256

    request_without_policy = _request(
        module,
        token="ambiguity-missing-policy",
        query="介绍清华的王教授",
        ambiguity_candidates=(
            dominant_checkpoint["dominant"],
            dominant_checkpoint["alternative"],
        ),
    )

    def missing_policy_provider(value: Any) -> Any:
        return _proposal(
            module,
            value,
            token="ambiguity-missing-policy",
            behavior_class="G",
            interaction_mode="information_retrieval",
            domains=("professor",),
            lanes=("exact", "web"),
        )

    with pytest.raises(module.MissingAmbiguityPolicyError):
        _planner(module, missing_policy_provider).plan(request_without_policy)


def _person_references(module: Any) -> tuple[Any, ...]:
    resolved = module.PersonReferenceRecord(
        reference_id="person-reference:resolved-founder",
        release_id="release-r1",
        resolution_state="resolved",
        canonical_person_id="person:founder-1",
        public_domain_evidence_ids=(
            "professor:profile-1",
            "company:personnel-1",
            "paper:author-1",
        ),
        typed_facts=(
            module.InternalReferenceFact(
                field="education",
                value="南方科技大学",
                evidence_ids=("professor:profile-1",),
            ),
            module.InternalReferenceFact(
                field="company_role",
                value="founder",
                evidence_ids=("company:personnel-1",),
            ),
            module.InternalReferenceFact(
                field="geography",
                value="深圳",
                evidence_ids=("company:personnel-1",),
            ),
        ),
    )
    resolved_nonmatching = module.PersonReferenceRecord(
        reference_id="person-reference:resolved-nonmatching",
        release_id="release-r1",
        resolution_state="resolved",
        canonical_person_id="person:nonmatching-2",
        public_domain_evidence_ids=("company:personnel-nonmatching",),
        typed_facts=(
            module.InternalReferenceFact(
                field="education",
                value="北京大学",
                evidence_ids=("company:personnel-nonmatching",),
            ),
            module.InternalReferenceFact(
                field="company_role",
                value="advisor",
                evidence_ids=("company:personnel-nonmatching",),
            ),
            module.InternalReferenceFact(
                field="geography",
                value="上海",
                evidence_ids=("company:personnel-nonmatching",),
            ),
        ),
    )
    unresolved = module.PersonReferenceRecord(
        reference_id="person-reference:unresolved-same-name",
        release_id="release-r1",
        resolution_state="unresolved",
        canonical_person_id=None,
        public_domain_evidence_ids=("paper:author-unresolved",),
        typed_facts=(
            module.InternalReferenceFact(
                field="education",
                value="南方科技大学",
                evidence_ids=("paper:author-unresolved",),
            ),
        ),
    )
    return (resolved, resolved_nonmatching, unresolved)


def _technology_routes(module: Any) -> tuple[Any, ...]:
    return (
        module.TechnologyRouteRecord(
            reference_id="technology-route:simulator",
            release_id="release-r1",
            canonical_route_id="technology-route:simulator-generation",
            canonical_name="模拟器生成数据",
            aliases=("仿真合成数据", "simulator data"),
            definition_evidence_ids=("evidence:route-definition:simulator",),
        ),
        module.TechnologyRouteRecord(
            reference_id="technology-route:world-model",
            release_id="release-r1",
            canonical_route_id="technology-route:world-model-generation",
            canonical_name="世界模型生成数据",
            aliases=("世界模型合成", "world-model data"),
            definition_evidence_ids=("evidence:route-definition:world-model",),
        ),
        module.TechnologyRouteRecord(
            reference_id="technology-route:teleoperation",
            release_id="release-r1",
            canonical_route_id="technology-route:teleoperation-collection",
            canonical_name="遥操作采集数据",
            aliases=("遥操数据", "teleoperation data"),
            definition_evidence_ids=("evidence:route-definition:teleoperation",),
        ),
    )


def test_query_planning_uses_internal_person_filters_and_technology_route_aliases_without_public_domains() -> (
    None
):
    module = _module()
    institution_catalog = _institution_catalog(module)
    person_references = _person_references(module)
    technology_routes = _technology_routes(module)
    request = _request(
        module,
        token="internal-person-technology",
        query=(
            "找出南方科技大学毕业并在深圳企业担任创始人的人，再比较仿真合成数据和"
            "世界模型合成两条路线及代表性企业，并确认量子奇点路线是否已解析"
        ),
        enumeration_context=module.EnumerationPlanningContext(
            requested=True,
            scope="representative Companies related to two accepted Technology routes",
            as_of=NOW,
            finite_universe=None,
            required_member_ids=(),
        ),
    )
    technology_path = _path(
        module,
        relationship_type_id="technology_company_relationship",
        direction="technology_to_company",
        source_type="technology_route",
        target_type="company",
    )

    def provider(value: Any) -> Any:
        return _proposal(
            module,
            value,
            token="internal-person-technology",
            behavior_class="E",
            interaction_mode="information_retrieval",
            domains=("professor", "company", "paper", "patent"),
            lanes=("internal_reference", "relationship", "web"),
            paths=(technology_path,),
            enumeration_mode="representative",
            internal_reference_targets=("person", "technology_route"),
        )

    plan = _planner(
        module,
        provider,
        institution_catalog=institution_catalog,
        person_references=person_references,
        technology_routes=technology_routes,
    ).plan(request)
    _assert_plan_identity(module, request, plan)
    assert set(plan.domains) <= set(PUBLIC_DOMAINS)
    assert "person" not in plan.domains
    assert "technology" not in plan.domains
    assert "technology_route" not in plan.domains

    person_query = next(
        item
        for item in plan.internal_reference_queries
        if item.reference_type == "person"
    )
    assert tuple((item.field, item.value) for item in person_query.typed_filters) == (
        ("education", "南方科技大学"),
        ("company_role", "founder"),
        ("geography", "深圳"),
    )
    assert person_query.eligible_reference_ids == ("person-reference:resolved-founder",)
    assert person_query.excluded_reference_ids == (
        "person-reference:resolved-nonmatching",
        "person-reference:unresolved-same-name",
    )
    assert set(person_query.originating_public_evidence_ids) == {
        "professor:profile-1",
        "company:personnel-1",
        "paper:author-1",
    }
    assert person_query.release_id == request.release_id
    assert tuple(
        (filter_item.field, filter_item.value, filter_item.evidence_ids)
        for filter_item in person_query.typed_filters
    ) == (
        ("education", "南方科技大学", ("professor:profile-1",)),
        ("company_role", "founder", ("company:personnel-1",)),
        ("geography", "深圳", ("company:personnel-1",)),
    )
    nonmatching_person = person_query.nonmatching_reference_traces
    assert tuple(item.reference_id for item in nonmatching_person) == (
        "person-reference:resolved-nonmatching",
    )
    assert nonmatching_person[0].resolution_state == "resolved"
    assert nonmatching_person[0].failed_filter_fields == (
        "education",
        "company_role",
        "geography",
    )
    assert nonmatching_person[0].evidence_ids == ("company:personnel-nonmatching",)
    unresolved_person = person_query.unresolved_reference_traces
    assert tuple(item.reference_id for item in unresolved_person) == (
        "person-reference:unresolved-same-name",
    )
    assert unresolved_person[0].evidence_ids == ("paper:author-unresolved",)
    assert unresolved_person[0].eligible_for_identity_filter is False
    assert unresolved_person[0].eligible_for_traversal is False
    assert person_query.reference_content_sha256s == tuple(
        (reference.reference_id, reference.content_sha256)
        for reference in person_references
    )
    assert person_query.public_population is False

    route_query = next(
        item
        for item in plan.internal_reference_queries
        if item.reference_type == "technology_route"
    )
    assert route_query.canonical_route_ids == (
        "technology-route:simulator-generation",
        "technology-route:world-model-generation",
    )
    assert "technology-route:teleoperation-collection" not in (
        route_query.canonical_route_ids
    )
    assert route_query.resolved_aliases == (
        ("仿真合成数据", "technology-route:simulator-generation"),
        ("世界模型合成", "technology-route:world-model-generation"),
    )
    assert route_query.relationship_states == (
        "discussion_or_mention",
        "claimed_adoption",
        "demonstrated_use",
    )
    assert route_query.release_id == request.release_id
    assert route_query.scope == request.enumeration_context.scope
    assert route_query.as_of == request.as_of
    assert route_query.definition_evidence_ids == (
        "evidence:route-definition:simulator",
        "evidence:route-definition:world-model",
    )
    assert route_query.route_content_sha256s == tuple(
        (route.reference_id, route.content_sha256) for route in technology_routes[:2]
    )
    assert route_query.definition_evidence_required is True
    assert route_query.relationship_evidence_required is True
    assert route_query.allowed_state_promotions == ()
    assert route_query.state_semantics == (
        ("discussion_or_mention", "non_adoption"),
        ("claimed_adoption", "claimed_only"),
        ("demonstrated_use", "demonstrated_only"),
    )
    assert route_query.enumeration_policy.mode == "representative"
    assert route_query.enumeration_policy.exhaustive is False
    assert route_query.public_population is False
    assert tuple(item.raw_text for item in plan.unresolved_technology_terms) == (
        "量子奇点路线",
    )
    assert plan.unresolved_technology_terms[0].canonical_route_id is None
    assert plan.unresolved_technology_terms[0].search_view_id
    assert (
        plan.unresolved_technology_terms[0].gap_reason == "unresolved_technology_term"
    )
    assert "product_has_capability" not in {
        path.relationship_type_id for path in plan.relationship_paths
    }
    assert "product_has_capability" not in repr(plan.model_dump(mode="json"))

    base_internal_payload = _without_content_hashes(
        provider(request).model_dump(mode="json")
    )
    assert isinstance(base_internal_payload, dict)

    public_internal_payload = _without_content_hashes(base_internal_payload)
    public_internal_payload["domains"] = ["person", "company"]

    product_relation_payload = _without_content_hashes(base_internal_payload)
    product_relation_payload["relationship_paths"] = [
        {
            "relationship_type_id": "product_has_capability",
            "direction": "product_to_capability",
            "source_type": "product",
            "target_type": "technology_route",
        }
    ]

    false_exhaustive_payload = _without_content_hashes(base_internal_payload)
    false_exhaustive_payload["enumeration_mode"] = "exhaustive_bounded"

    def provider_for(payload: dict[str, Any]) -> Any:
        def return_payload(_: Any) -> dict[str, Any]:
            return payload

        return return_payload

    hostile_cases = (
        (
            "internal_reference_promoted_to_public_domain",
            public_internal_payload,
        ),
        (
            "unsupported_product_capability_relation",
            product_relation_payload,
        ),
        ("false_exhaustive_enumeration", false_exhaustive_payload),
    )
    for expected_reason, hostile_payload in hostile_cases:
        hostile_planner = _planner(
            module,
            provider_for(hostile_payload),
            institution_catalog=institution_catalog,
            person_references=person_references,
            technology_routes=technology_routes,
        )
        with pytest.raises(module.InvalidRetrievalPlanError) as caught:
            hostile_planner.plan(request)
        assert caught.value.reason_code == expected_reason

    wrong_release_person_payload = _without_content_hashes(
        person_references[0].model_dump(mode="json")
    )
    wrong_release_person_payload["release_id"] = "release-r2"
    wrong_release_person = module.PersonReferenceRecord.model_validate(
        wrong_release_person_payload
    )
    wrong_release_references = (wrong_release_person, *person_references[1:])
    with pytest.raises(module.InvalidRetrievalPlanError) as caught:
        _planner(
            module,
            provider,
            institution_catalog=institution_catalog,
            person_references=wrong_release_references,
            technology_routes=technology_routes,
        ).plan(request)
    assert caught.value.reason_code == "person_reference_release_mismatch"
