"""RED owner for the S11B Canonical V2 candidate consumer boundary."""

from __future__ import annotations

from collections.abc import Callable
import copy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import importlib
from importlib import util
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import ModuleType
from typing import Any

from fastapi.testclient import TestClient
import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_RELEASE_ID = "candidate-s11b-consumer-release"
_NOW = datetime(2026, 7, 20, 21, 30, tzinfo=UTC)
_S9J_CORRECTED_CHAT_OWNER_SHA256 = (
    "71e04271b9c6ef867795fba0ca3f9427ef418a8b5f736a952f9594130088a06a"
)
_PUBLIC_DOMAINS = ("company", "paper", "patent", "professor")
_INITIAL_QUERY = "介绍 “Robotics Co” 并核实 2026 年当前营收"
_RELATIONSHIP_QUERY = "列出已展示 Robotics Co 作为申请人的代表性专利"
_REPRESENTATIVE_SCOPE = (
    "representative Patents naming one displayed Company as applicant"
)
_RUNTIME_UNAVAILABLE = "canonical_v2_runtime_unavailable"
_RELATIONSHIP_PATH_BY_SOURCE_ID = {
    "company-robotics": (
        "company_has_patent",
        "company_to_patent",
        "company",
        "patent",
    ),
    "patent-ada": (
        "company_has_patent",
        "patent_to_company",
        "patent",
        "company",
    ),
    "professor-ada": (
        "professor_authored_paper",
        "professor_to_paper",
        "professor",
        "paper",
    ),
    "paper-ada": (
        "professor_authored_paper",
        "paper_to_professor",
        "paper",
        "professor",
    ),
}
_KNOWN_API_ROUTES = frozenset(
    {
        ("GET", "/api/health"),
        ("POST", "/api/chat"),
        ("POST", "/api/chat/feedback"),
        ("POST", "/api/chat/session/reset"),
        ("GET", "/api/canonical-v2/operations/gaps"),
        ("GET", "/api/canonical-v2/operations/gaps/{gap_id}"),
        ("GET", "/api/canonical-v2/admin/status"),
        ("GET", "/api/canonical-v2/admin/domains/{domain}"),
        ("GET", "/api/canonical-v2/admin/domains/{domain}/facets/{field}"),
        ("GET", "/api/canonical-v2/admin/domains/{domain}/export"),
        ("GET", "/api/canonical-v2/admin/domains/{domain}/{canonical_id}"),
        (
            "GET",
            "/api/canonical-v2/admin/domains/{domain}/{canonical_id}/related",
        ),
    }
)
_STATIC_ROUTES = frozenset(
    {("GET", "/"), ("GET", "/browse"), ("GET", "/chat"), ("MOUNT", "/static")}
)
_REJECT_METHODS = frozenset(
    {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"}
)
_DOMAIN_INPUTS = {
    "company": {
        "filters": ("industry", "geography", "quality_status"),
        "sorts": ("name", "founded_at", "last_updated"),
        "typed": {
            "industry": "industry:robotics",
            "geography": "Shenzhen",
            "quality_status": "partial",
        },
    },
    "paper": {
        "filters": ("venue", "year", "quality_status"),
        "sorts": ("title", "year", "citation_count", "last_updated"),
        "typed": {
            "venue": "venue:robotics",
            "year": "2026",
            "quality_status": "partial",
        },
    },
    "patent": {
        "filters": ("patent_type", "publication_date", "quality_status"),
        "sorts": ("title", "publication_date", "filing_date", "last_updated"),
        "typed": {
            "patent_type": "invention",
            "publication_date": "2026-01-02",
            "quality_status": "partial",
        },
    },
    "professor": {
        "filters": ("institution", "department", "quality_status"),
        "sorts": ("name", "h_index", "citation_count", "last_updated"),
        "typed": {
            "institution": "SUSTech",
            "department": "department:cs",
            "quality_status": "partial",
        },
    },
}


class _ObservedPort:
    """Count observable port calls while delegating every algorithm to Accepted code."""

    def __init__(self, delegate: Any, probes: dict[str, Any], stage: str) -> None:
        self.delegate = delegate
        self.probes = probes
        self.stage = stage

    def __deepcopy__(self, memo: dict[int, Any]) -> _ObservedPort:
        return _ObservedPort(
            copy.deepcopy(self.delegate, memo), self.probes, self.stage
        )

    def _call(self, method: str, value: Any) -> Any:
        self.probes["effects"][self.stage] += 1
        self.probes["captured"][f"{self.stage}_input"] = value
        result = getattr(self.delegate, method)(value)
        transform = self.probes.get("faults", {}).get(f"{self.stage}_after")
        if transform is not None:
            result = transform(result)
        if self.stage == "plan":
            self.probes["captured"]["raw_plan"] = result
            self.probes["captured"]["raw_plan_bytes"] = result.model_dump_json()
        self.probes["captured"][self.stage] = result
        return result

    def plan(self, value: Any) -> Any:
        return self._call("plan", value)

    def execute(self, value: Any) -> Any:
        return self._call("execute", value)

    def answer(self, value: Any) -> Any:
        return self._call("answer", value)


class _ObservedGapOperations:
    """Recorded persistence boundary over the Accepted pure S10 gap lifecycle."""

    def __init__(self, pure: Any, module: ModuleType, probes: dict[str, Any]) -> None:
        self.pure = pure
        self.module = module
        self.probes = probes
        self.gaps: dict[str, Any] = {}

    def record(self, signal: Any) -> Any:
        self.probes["effects"]["gap"] += 1
        gap = self.pure.record(signal)
        self.gaps[gap.gap_id] = gap
        self.probes["captured"]["gap_signal"] = signal
        self.probes["captured"]["gap"] = gap
        return gap

    def list_for_admin(self, query: Any) -> Any:
        self.probes["captured"]["gap_query"] = query
        items = tuple(
            gap
            for gap in self.gaps.values()
            if query.release_id is None or gap.release_id == query.release_id
        )
        return self.module.GapAdminPage(
            items=items[query.offset : query.offset + query.limit],
            total=len(items),
            limit=query.limit,
            offset=query.offset,
        )

    def get_for_admin(self, gap_id: str) -> Any:
        gap = self.gaps.get(gap_id)
        if gap is None:
            return None
        return self.module.GapAdminDetail(
            gap=gap,
            transitions=(),
            field_assertions=(),
            relationship_assertions=(),
            canonical_decisions=(),
            relationship_decisions=(),
            releases=(),
            provenance=tuple(
                {"evidence_id": evidence_id} for evidence_id in gap.evidence_ids
            ),
            unresolved_evidence_ids=gap.evidence_ids,
        )


class _MissingS11BAdminRuntime(AssertionError):
    """The exact S11B Admin seam is not implemented yet."""


@dataclass(frozen=True, slots=True)
class _S11BAdminSeam:
    consumer_runtime_type: type[Any]
    admin_runtime_type: type[Any]
    compose_runtime: Callable[..., Any]
    consumer_router: Any
    chat_router: Any
    original_gap_getter: Callable[..., Any]
    original_chat_getter: Callable[..., Any]
    compose_operations: Callable[..., Any]
    admin_getter: Callable[..., Any]
    candidate_gap_getter: Callable[..., Any]
    candidate_chat_getter: Callable[..., Any]
    route_shell_factory: Callable[..., Any]
    candidate_app_factory: Callable[..., Any]
    main_module: ModuleType
    test_client_type: type[TestClient]


def _import_required_module(module_name: str) -> ModuleType:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise
        raise _MissingS11BAdminRuntime(
            f"missing required S11B module: {module_name}"
        ) from exc


def _required_attribute(module: ModuleType, attribute: str) -> Any:
    try:
        return vars(module)[attribute]
    except KeyError as exc:
        raise _MissingS11BAdminRuntime(
            f"missing required S11B seam: {module.__name__}.{attribute}"
        ) from exc


def _load_s11b_admin_seam() -> _S11BAdminSeam:
    admin_module = _import_required_module("backend.services.canonical_v2_admin")
    consumer_runtime_type = _required_attribute(
        admin_module,
        "CanonicalV2ConsumerRuntime",
    )
    admin_runtime_type = _required_attribute(
        admin_module,
        "CanonicalV2AdminRuntime",
    )
    compose_runtime = _required_attribute(
        admin_module,
        "compose_canonical_v2_consumer_runtime",
    )

    consumer_module = _import_required_module("backend.api.canonical_v2_consumers")
    consumer_router = _required_attribute(consumer_module, "router")

    chat_module = _import_required_module("backend.api.canonical_v2_chat")
    chat_router = _required_attribute(chat_module, "router")

    deps_module = _import_required_module("backend.canonical_v2_deps")
    original_gap_getter = _required_attribute(
        deps_module,
        "get_knowledge_gap_operations",
    )
    original_chat_getter = _required_attribute(
        deps_module,
        "get_canonical_v2_chat_adapter",
    )
    compose_operations = _required_attribute(deps_module, "_compose_operations")
    admin_getter = _required_attribute(
        deps_module,
        "get_canonical_v2_admin_runtime",
    )
    candidate_gap_getter = _required_attribute(
        deps_module,
        "get_canonical_v2_gap_operations",
    )
    candidate_chat_getter = _required_attribute(
        deps_module,
        "get_canonical_v2_candidate_chat_adapter",
    )

    main_module = _import_required_module("backend.main")
    route_shell_factory = _required_attribute(
        main_module,
        "_create_canonical_v2_route_shell",
    )
    candidate_app_factory = _required_attribute(
        main_module,
        "create_canonical_v2_candidate_app",
    )

    return _S11BAdminSeam(
        consumer_runtime_type=consumer_runtime_type,
        admin_runtime_type=admin_runtime_type,
        compose_runtime=compose_runtime,
        consumer_router=consumer_router,
        chat_router=chat_router,
        original_gap_getter=original_gap_getter,
        original_chat_getter=original_chat_getter,
        compose_operations=compose_operations,
        admin_getter=admin_getter,
        candidate_gap_getter=candidate_gap_getter,
        candidate_chat_getter=candidate_chat_getter,
        route_shell_factory=route_shell_factory,
        candidate_app_factory=candidate_app_factory,
        main_module=main_module,
        test_client_type=TestClient,
    )


def _has_one_request_parameter(callable_: Callable[..., Any]) -> bool:
    parameters = tuple(inspect.signature(callable_).parameters.values())
    if len(parameters) != 1 or parameters[0].name != "request":
        return False
    annotation = parameters[0].annotation
    annotation_name = getattr(annotation, "__name__", annotation)
    return annotation_name == "Request" or str(annotation_name).endswith(".Request")


def _has_keyword_only_runtime_parameter(callable_: Callable[..., Any]) -> bool:
    parameters = tuple(inspect.signature(callable_).parameters.values())
    return (
        len(parameters) == 1
        and parameters[0].name == "runtime"
        and parameters[0].kind is inspect.Parameter.KEYWORD_ONLY
        and parameters[0].default is inspect.Parameter.empty
    )


def _load_s9j_corrected_chat_owner() -> ModuleType:
    path = (
        _REPO_ROOT / "apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py"
    )
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        == _S9J_CORRECTED_CHAT_OWNER_SHA256
    )
    spec = util.spec_from_file_location("_s11b_s9j_corrected_chat_owner", path)
    if spec is None or spec.loader is None:
        raise AssertionError("Accepted S9J-corrected chat owner cannot be loaded")
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build_accepted_release_scenario(tmp_path: Path) -> dict[str, Any]:
    corrected_chat_owner = _load_s9j_corrected_chat_owner()
    fixture_owner = corrected_chat_owner._load_accepted_logical_fixture_owner()
    logical = fixture_owner._s8r2_scenario(
        tmp_path=tmp_path,
        release_id=_RELEASE_ID,
    )
    scenario = corrected_chat_owner._materialize_release_bound_scenario(
        scenario=logical,
        tmp_path=tmp_path,
    )
    bundle = scenario["bundle"]
    index_request = scenario["index_request"]

    release_module = importlib.import_module(
        "src.data_agents.canonical_v2.release_publication"
    )
    publication = release_module.create_ephemeral_release_publication(
        candidate_manifests={_RELEASE_ID: bundle.manifest},
        actual_index_projections={
            _RELEASE_ID: bundle.index_result.actual_index_projections
        },
        expected_index_points={_RELEASE_ID: bundle.index_result.points},
        actual_index_points={_RELEASE_ID: bundle.index_result.points},
        active_release_state={
            "canonical_release_id": "accepted-s11a-prior",
            "published_projection_release_id": "accepted-s11a-prior",
            "index_release_id": "accepted-s11a-prior",
        },
        verification_store={},
        discrepancy_store={},
        publication_history=[],
        clock=lambda: _NOW,
    )
    verification = publication.verify(_RELEASE_ID)
    published = publication.promote(_RELEASE_ID)
    assert verification.accepted is True
    assert verification.evidence_ids == published.verification_evidence_ids

    read_module = importlib.import_module("src.data_agents.canonical_v2.knowledge_read")
    isolated_read_module = importlib.import_module(
        "src.data_agents.canonical_v2.knowledge_read_isolated"
    )
    planning_policy = read_module.QueryPlanningPolicy(
        policy_id="planning-policy:s11b-consumer",
        policy_version="query-planning-policy-v1",
        public_domains=_PUBLIC_DOMAINS,
        supported_lanes=("exact", "relationship", "web"),
        supported_relationship_paths=tuple(
            (relationship_type, direction)
            for relationship_type, direction, _, _ in (
                _RELATIONSHIP_PATH_BY_SOURCE_ID.values()
            )
        ),
        max_candidates=100,
        max_provider_calls=1,
        max_planning_attempts=1,
    )
    revenue_part = read_module.MaterialQuestionPart(
        part_id="material-part:s11b-current-revenue",
        text="核实 Robotics Co 的 2026 年当前营收",
        subject_id="company-robotics",
        predicate="current_revenue",
        requested_value="2026",
    )

    def proposal_provider(value: Any) -> Any:
        source_id = (
            value.displayed_entity_ids[0]
            if len(value.displayed_entity_ids) == 1
            else None
        )
        relationship_path = (
            None
            if source_id is None
            else _RELATIONSHIP_PATH_BY_SOURCE_ID.get(source_id)
        )
        if relationship_path is not None and (
            value.original_query == _RELATIONSHIP_QUERY
            or value.enumeration_context is not None
        ):
            relationship_type, direction, source_type, target_type = relationship_path
            return read_module.RecordedPlanningProposal(
                proposal_id=f"planning-proposal:s11b:relationship:{value.request_id}",
                request_sha256=value.content_sha256,
                schema_version="retrieval-plan-proposal-v1",
                model_id="recorded-s11b-planner",
                prompt_version="query-plan-prompt-v1",
                behavior_class="E",
                interaction_mode="information_retrieval",
                domains=(target_type,),
                lanes=("relationship", "web"),
                relationship_paths=(
                    read_module.RelationshipPathProposal(
                        relationship_type_id=relationship_type,
                        direction=direction,
                        source_type=source_type,
                        target_type=target_type,
                    ),
                ),
                max_candidates=20,
                max_provider_calls=1,
                enumeration_mode="representative",
                web_mode="universal",
                max_web_results=5,
            )
        return read_module.RecordedPlanningProposal(
            proposal_id=f"planning-proposal:s11b:{value.request_id}",
            request_sha256=value.content_sha256,
            schema_version="retrieval-plan-proposal-v1",
            model_id="recorded-s11b-planner",
            prompt_version="query-plan-prompt-v1",
            behavior_class="A",
            interaction_mode="information_retrieval",
            domains=_PUBLIC_DOMAINS,
            lanes=("exact", "web"),
            material_parts=(
                (revenue_part,) if value.original_query == _INITIAL_QUERY else ()
            ),
            max_candidates=100,
            max_provider_calls=1,
            web_mode="universal",
            max_web_results=5,
        )

    planner = isolated_read_module.create_isolated_release_query_planner(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=scenario["catalog"],
        planning_policy=planning_policy,
        proposal_provider=proposal_provider,
    )

    def missing_sufficiency(value: Any) -> Any:
        return read_module.SufficiencyProposal(
            decision_input_sha256=value.content_sha256,
            schema_version="sufficiency-v1",
            decision_id=f"sufficiency:s11b:{value.plan_id}",
            parts=tuple(
                read_module.MaterialPartProposal(
                    part_id=part.part_id,
                    outcome="missing",
                    evidence_ids=(),
                    rationale="No retained evidence supports the requested value.",
                    uncertainty="high",
                    confidence=0.0,
                )
                for part in value.material_parts
            ),
        )

    knowledge_read = isolated_read_module.create_isolated_release_knowledge_read(
        release_bundle=bundle,
        published_release=published,
        index_projection_request=index_request,
        release_institution_catalog=scenario["catalog"],
        universal_web_policy=read_module.WebSearchPolicy(
            mode="universal",
            max_provider_calls=1,
            timeout_ms=1_000,
            max_results=5,
        ),
        web_search=lambda _: read_module.RetrievalLaneResult(),
        web_snapshot_policy=read_module.WebSnapshotPolicy(
            policy_id="web-snapshot-policy:s11b",
            policy_version="web-snapshot-policy-v1",
            max_bytes=8_192,
        ),
        sufficiency_decider=missing_sufficiency,
        supplemental_search=lambda _: read_module.SupplementalLaneResult(
            items=(), elapsed_ms=1, cost_units=0.0, retryable=False
        ),
        web_handle_ttl=timedelta(hours=1),
        clock=lambda: _NOW,
    )

    answer_module = importlib.import_module(
        "src.data_agents.canonical_v2.knowledge_answer"
    )

    def answer_factory() -> Any:
        return answer_module.create_ephemeral_knowledge_answer(
            answer_selector=lambda value: corrected_chat_owner._answer_proposal(
                answer_module, value
            )
        )

    gap_module = importlib.import_module(
        "src.data_agents.canonical_v2.knowledge_gap_feedback"
    )
    gap_postgres_module = importlib.import_module(
        "src.data_agents.canonical_v2.knowledge_gap_postgres"
    )
    target_module = importlib.import_module("src.data_agents.storage.database_target")
    gap_operations = gap_postgres_module.PostgresKnowledgeGapOperations(
        target=target_module.DestructiveDatabaseTarget(
            url="postgresql://localhost/s11b_disposable",
            expected_database="s11b_disposable",
            target_kind="disposable",
        ),
        backup_gate_root=tmp_path / "recorded-s10o-boundary",
        classifier=None,
        clock=lambda: _NOW,
    )
    supplemental_budget = read_module.SupplementalBudget(
        max_wall_time_ms=1_000,
        max_provider_calls=2,
        max_retries=1,
        max_cost_units=5.0,
    )
    alternate = fixture_owner._s8r2_scenario(
        tmp_path=tmp_path / "alternate",
        release_id=_RELEASE_ID,
        nonmatching_relationship_authority=True,
    )
    return {
        **scenario,
        "corrected_chat_owner": corrected_chat_owner,
        "fixture_owner": fixture_owner,
        "modules": {
            "read": read_module,
            "answer": answer_module,
            "gap": gap_module,
            "gap_postgres": gap_postgres_module,
        },
        "published": published,
        "verification": verification,
        "planner": planner,
        "knowledge_read": knowledge_read,
        "answer_factory": answer_factory,
        "gap_operations": gap_operations,
        "supplemental_budget": supplemental_budget,
        "alternate": alternate,
    }


def _compose_arguments(scenario: dict[str, Any], **updates: Any) -> dict[str, Any]:
    arguments = {
        "published_release": scenario["published"],
        "release_verification": scenario["verification"],
        "release_bundle": scenario["bundle"],
        "index_projection_request": scenario["index_request"],
        "planner": scenario["planner"],
        "knowledge_read": scenario["knowledge_read"],
        "answer_factory": scenario["answer_factory"],
        "answer_session_fork": copy.deepcopy,
        "gap_operations": scenario["gap_operations"],
        "supplemental_budget": scenario["supplemental_budget"],
    }
    arguments.update(updates)
    return arguments


def _compose_observed_runtime(
    seam: _S11BAdminSeam,
    scenario: dict[str, Any],
) -> tuple[Any, dict[str, Any]]:
    probes: dict[str, Any] = {
        "effects": {
            "plan": 0,
            "read": 0,
            "answer": 0,
            "answer_factory": 0,
            "gap": 0,
            "legacy": 0,
            "sql": 0,
            "provider": 0,
        },
        "captured": {},
        "faults": {},
    }
    pure_gap = scenario["modules"]["gap"].create_ephemeral_knowledge_gap_feedback(
        clock=lambda: _NOW
    )
    recorded_gap = _ObservedGapOperations(
        pure_gap,
        scenario["modules"]["gap_postgres"],
        probes,
    )

    def answer_factory() -> Any:
        probes["effects"]["answer_factory"] += 1
        return _ObservedPort(scenario["answer_factory"](), probes, "answer")

    arguments = _compose_arguments(
        scenario,
        planner=_ObservedPort(scenario["planner"], probes, "plan"),
        knowledge_read=_ObservedPort(scenario["knowledge_read"], probes, "read"),
        answer_factory=answer_factory,
        gap_operations=recorded_gap,
    )
    runtime = seam.compose_runtime(**arguments)
    probes["recorded_gap"] = recorded_gap
    probes["composition_arguments"] = arguments
    return runtime, probes


def _install_forbidden_effect_canaries(
    monkeypatch: pytest.MonkeyPatch,
    probes: dict[str, Any],
) -> None:
    def canary(kind: str, label: str) -> Callable[..., Any]:
        def fail(*_: Any, **__: Any) -> Any:
            probes["effects"][kind] += 1
            raise AssertionError(f"forbidden S11B effect reached: {label}")

        return fail

    compatibility_module = ModuleType("openai_client_compat")
    setattr(
        compatibility_module,
        "build_openai_client",
        canary(
            "provider",
            "openai_client_compat.build_openai_client",
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "openai_client_compat",
        compatibility_module,
    )

    targets = (
        ("backend.deps", "get_pg_conn", "sql"),
        ("backend.deps", "get_retrieval_service", "provider"),
        ("backend.api.chat", "chat", "legacy"),
        ("backend.api.domains", "update_domain_object", "legacy"),
        ("backend.api.domains", "delete_domain_object", "legacy"),
        ("backend.api.pipeline", "_run_milvus_backfill_command", "legacy"),
        ("backend.api.pipeline", "_run_retrieval_validation_command", "legacy"),
        ("backend.api.seeds", "_schedule_seed_run", "legacy"),
        (
            "src.data_agents.company.canonical_import",
            "import_company_xlsx_to_postgres",
            "legacy",
        ),
        (
            "src.data_agents.professor.canonical_writer",
            "write_professor_bundle",
            "legacy",
        ),
        ("src.data_agents.paper.canonical_writer", "upsert_paper", "legacy"),
        ("src.data_agents.patent.canonical_writer", "upsert_patent", "legacy"),
        (
            "src.data_agents.paper.milvus_backfill",
            "backfill_paper_chunks",
            "legacy",
        ),
    )
    for module_name, attribute, kind in targets:
        module = importlib.import_module(module_name)
        monkeypatch.setattr(
            module, attribute, canary(kind, f"{module_name}.{attribute}")
        )


def _assert_seam_contract(seam: _S11BAdminSeam) -> None:
    assert tuple(inspect.signature(seam.original_gap_getter).parameters) == ()
    assert tuple(inspect.signature(seam.compose_operations).parameters) == ()
    assert _has_one_request_parameter(seam.original_chat_getter)
    assert _has_one_request_parameter(seam.candidate_chat_getter)
    assert _has_one_request_parameter(seam.candidate_gap_getter)
    assert _has_one_request_parameter(seam.admin_getter)
    assert tuple(inspect.signature(seam.route_shell_factory).parameters) == ()
    assert _has_keyword_only_runtime_parameter(seam.candidate_app_factory)
    compose_parameters = inspect.signature(seam.compose_runtime).parameters
    assert tuple(compose_parameters) == (
        "published_release",
        "release_verification",
        "release_bundle",
        "index_projection_request",
        "planner",
        "knowledge_read",
        "answer_factory",
        "answer_session_fork",
        "gap_operations",
        "supplemental_budget",
    )
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and parameter.default is inspect.Parameter.empty
        for parameter in compose_parameters.values()
    )
    assert seam.original_gap_getter.__module__ == "backend.canonical_v2_deps"
    assert seam.original_chat_getter.__module__ == "backend.canonical_v2_deps"
    assert seam.candidate_gap_getter.__module__ == "backend.canonical_v2_deps"
    assert seam.candidate_chat_getter.__module__ == "backend.canonical_v2_deps"
    assert seam.admin_getter.__module__ == "backend.canonical_v2_deps"


def _assert_composition_rejected_without_effects(
    seam: _S11BAdminSeam,
    scenario: dict[str, Any],
    probes: dict[str, Any],
    **updates: Any,
) -> None:
    del scenario
    before = dict(probes["effects"])
    arguments = dict(probes["composition_arguments"])
    arguments.update(updates)
    with pytest.raises((TypeError, ValueError)):
        seam.compose_runtime(**arguments)
    assert probes["effects"] == before


def _hostile_bundle(bundle: Any, **updates: Any) -> Any:
    payload = {field: getattr(bundle, field) for field in type(bundle).model_fields}
    payload.update(updates)
    return type(bundle).model_construct(**payload)


def _hostile_model(value: Any, **updates: Any) -> Any:
    payload = {field: getattr(value, field) for field in type(value).model_fields}
    payload.update(updates)
    return type(value).model_construct(**payload)


def _assert_constructor_contract(
    seam: _S11BAdminSeam,
    scenario: dict[str, Any],
    probes: dict[str, Any],
) -> None:
    runtime = seam.compose_runtime(**probes["composition_arguments"])
    assert type(runtime) is seam.consumer_runtime_type
    assert runtime.release_id == _RELEASE_ID
    assert runtime.gap_operations is probes["recorded_gap"]
    assert runtime.admin_runtime.gap_operations is runtime.gap_operations
    assert type(runtime.admin_runtime) is seam.admin_runtime_type
    assert runtime.admin_runtime.release_id == _RELEASE_ID
    assert probes["effects"] == {
        "plan": 0,
        "read": 0,
        "answer": 0,
        "answer_factory": 0,
        "gap": 0,
        "legacy": 0,
        "sql": 0,
        "provider": 0,
    }

    for key in (
        "published_release",
        "release_verification",
        "release_bundle",
        "index_projection_request",
    ):
        original = probes["composition_arguments"][key]
        _assert_composition_rejected_without_effects(
            seam, scenario, probes, **{key: object()}
        )
        subclass = type(f"S11BHostile{type(original).__name__}", (type(original),), {})
        subclass_value = subclass.model_validate(original.model_dump(mode="json"))
        _assert_composition_rejected_without_effects(
            seam, scenario, probes, **{key: subclass_value}
        )

    hostile_artifacts = {
        "published_release": _hostile_model(
            scenario["published"], verification_evidence_ids=()
        ),
        "release_verification": _hostile_model(
            scenario["verification"], evidence_ids=()
        ),
        "release_bundle": _hostile_bundle(scenario["bundle"], index_result=object()),
        "index_projection_request": _hostile_model(
            scenario["index_request"], candidate_projection_result=object()
        ),
    }
    for key, hostile in hostile_artifacts.items():
        _assert_composition_rejected_without_effects(
            seam, scenario, probes, **{key: hostile}
        )

    published = scenario["published"]
    hostile_publication = published.model_copy(update={"verification_evidence_ids": ()})
    _assert_composition_rejected_without_effects(
        seam,
        scenario,
        probes,
        published_release=hostile_publication,
    )
    cross_release_publication = type(published).model_validate(
        {
            **published.model_dump(mode="json"),
            "release_id": "cross-release",
            "canonical_release_id": "cross-release",
            "published_projection_release_id": "cross-release",
            "index_release_id": "cross-release",
        }
    )
    _assert_composition_rejected_without_effects(
        seam,
        scenario,
        probes,
        published_release=cross_release_publication,
    )

    manifest = scenario["bundle"].manifest
    forged_manifest = manifest.model_copy(update={"manifest_sha256": "f" * 64})
    forged_bundle = _hostile_bundle(scenario["bundle"], manifest=forged_manifest)
    _assert_composition_rejected_without_effects(
        seam, scenario, probes, release_bundle=forged_bundle
    )

    verification = scenario["verification"]
    verification_variants = (
        verification.model_copy(
            update={"accepted": False, "canonical_index_parity": False}
        ),
        verification.model_copy(update={"candidate_release_id": "cross-release"}),
        verification.model_copy(update={"manifest_sha256": "e" * 64}),
        verification.model_copy(update={"evidence_ids": ("release-parity:wrong",)}),
    )
    for variant in verification_variants:
        _assert_composition_rejected_without_effects(
            seam, scenario, probes, release_verification=variant
        )

    index_request = scenario["index_request"]
    alternate_request = scenario["alternate"]["index_request"]
    candidate_drift = type(index_request).model_validate(
        {
            **index_request.model_dump(mode="json"),
            "candidate_projection_result": (
                alternate_request.candidate_projection_result.model_dump(mode="json")
            ),
        }
    )
    _assert_composition_rejected_without_effects(
        seam,
        scenario,
        probes,
        index_projection_request=candidate_drift,
    )
    index_drift = index_request.model_copy(
        update={"embedding_model": "recorded-embedding-v2"}
    )
    _assert_composition_rejected_without_effects(
        seam,
        scenario,
        probes,
        index_projection_request=index_drift,
    )

    missing_relationships = _hostile_bundle(
        scenario["bundle"],
        relationship_projection_request=None,
        relationship_projection_result=None,
    )
    _assert_composition_rejected_without_effects(
        seam, scenario, probes, release_bundle=missing_relationships
    )
    crosswired_relationships = _hostile_bundle(
        scenario["bundle"],
        relationship_projection_request=scenario["alternate"][
            "bundle"
        ].relationship_projection_request,
        relationship_projection_result=scenario["alternate"][
            "bundle"
        ].relationship_projection_result,
    )
    _assert_composition_rejected_without_effects(
        seam, scenario, probes, release_bundle=crosswired_relationships
    )
    relationship_drift = scenario["bundle"].relationship_projection_result.model_copy(
        update={"content_sha256": "c" * 64}
    )
    drifted_relationship_bundle = _hostile_bundle(
        scenario["bundle"],
        relationship_projection_result=relationship_drift,
    )
    _assert_composition_rejected_without_effects(
        seam,
        scenario,
        probes,
        release_bundle=drifted_relationship_bundle,
    )

    candidate_result = index_request.candidate_projection_result
    company = next(
        value
        for value in candidate_result.public_domain_projections
        if value.entity_type == "company"
    )
    fifth_domain = _hostile_model(company, entity_type="technology")
    hostile_result = _hostile_model(
        candidate_result,
        public_domain_projections=(
            *candidate_result.public_domain_projections,
            fifth_domain,
        ),
    )
    hostile_index_request = _hostile_model(
        index_request,
        candidate_projection_result=hostile_result,
    )
    _assert_composition_rejected_without_effects(
        seam,
        scenario,
        probes,
        index_projection_request=hostile_index_request,
    )


def _assert_typed_runtime_unavailable(response: Any) -> None:
    assert response.status_code == 503
    body = response.json()
    assert isinstance(body, dict)
    detail = body.get("detail")
    if isinstance(detail, dict):
        assert detail.get("code") == _RUNTIME_UNAVAILABLE
    else:
        assert detail == _RUNTIME_UNAVAILABLE


def _runtime_variant(runtime: Any, **updates: Any) -> Any:
    variant = copy.copy(runtime)
    for name, value in updates.items():
        object.__setattr__(variant, name, value)
    return variant


def _assert_candidate_factory_contract(
    seam: _S11BAdminSeam,
    runtime: Any,
    probes: dict[str, Any],
) -> Any:
    module_app = seam.main_module.app
    assert not hasattr(module_app.state, "canonical_v2_consumer_runtime")
    assert module_app.dependency_overrides == {}

    candidate = seam.candidate_app_factory(runtime=runtime)
    second = seam.candidate_app_factory(runtime=runtime)
    assert candidate is not second and candidate is not module_app
    assert candidate.state.canonical_v2_consumer_runtime is runtime
    assert candidate.dependency_overrides == {
        seam.original_chat_getter: seam.candidate_chat_getter,
        seam.original_gap_getter: seam.candidate_gap_getter,
    }

    effects_before = dict(probes["effects"])
    for invalid in (None, object()):
        broken = seam.route_shell_factory()
        if invalid is not None:
            broken.state.canonical_v2_consumer_runtime = invalid
        broken.dependency_overrides[seam.original_chat_getter] = (
            seam.candidate_chat_getter
        )
        broken.dependency_overrides[seam.original_gap_getter] = (
            seam.candidate_gap_getter
        )
        broken_client = seam.test_client_type(broken, raise_server_exceptions=False)
        _assert_typed_runtime_unavailable(
            broken_client.get("/api/canonical-v2/admin/status")
        )
        _assert_typed_runtime_unavailable(
            broken_client.get("/api/canonical-v2/operations/gaps")
        )
        broken.state.canonical_v2_chat_adapter = runtime.chat_adapter
        _assert_typed_runtime_unavailable(
            broken_client.post(
                "/api/chat",
                json={"query": "介绍 Robotics Co", "entity_id_hint": None},
            )
        )
        assert probes["effects"] == effects_before

    crossed_cases = (
        (
            _runtime_variant(runtime, admin_runtime=object()),
            "GET",
            "/api/canonical-v2/admin/status",
            None,
        ),
        (
            _runtime_variant(runtime, chat_adapter=object()),
            "POST",
            "/api/chat",
            {"query": "介绍 Robotics Co", "entity_id_hint": None},
        ),
        (
            _runtime_variant(runtime, gap_operations=object()),
            "GET",
            "/api/canonical-v2/operations/gaps",
            None,
        ),
        (
            _runtime_variant(runtime, release_id="cross-release"),
            "GET",
            "/api/canonical-v2/admin/status",
            None,
        ),
    )
    for crossed_runtime, method, path, body in crossed_cases:
        crossed = seam.route_shell_factory()
        crossed.state.canonical_v2_consumer_runtime = crossed_runtime
        crossed.dependency_overrides.update(candidate.dependency_overrides)
        crossed_client = seam.test_client_type(crossed, raise_server_exceptions=False)
        _assert_typed_runtime_unavailable(
            crossed_client.request(method, path, json=body)
        )
        assert probes["effects"] == effects_before
    return candidate


def _route_rows(app: Any) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for route in app.routes:
        if route.path == "/static":
            rows.append(("MOUNT", route.path))
            continue
        rows.extend((method, route.path) for method in (route.methods or set()))
    return rows


def _assert_candidate_route_contract(candidate: Any, probes: dict[str, Any]) -> None:
    rows = _route_rows(candidate)
    reject_rows = {
        (method, path) for method, path in rows if path == "/api/{path:path}"
    }
    known_rows = {
        (method, path)
        for method, path in rows
        if path.startswith("/api/") and path != "/api/{path:path}"
    }
    static_rows = {
        (method, path) for method, path in rows if not path.startswith("/api/")
    }
    assert known_rows == _KNOWN_API_ROUTES
    assert reject_rows == {(method, "/api/{path:path}") for method in _REJECT_METHODS}
    assert static_rows == _STATIC_ROUTES
    assert candidate.openapi_url is None
    assert candidate.docs_url is None
    assert candidate.redoc_url is None
    assert not any(
        middleware.cls.__name__ == "CORSMiddleware"
        for middleware in candidate.user_middleware
    )
    assert not any(
        path in {"/docs", "/openapi.json", "/redoc"}
        or "{path:path}" in path
        and not path.startswith("/api/")
        for _, path in rows
    )

    route_paths = [route.path for route in candidate.routes]
    assert route_paths.index(
        "/api/canonical-v2/admin/domains/{domain}/export"
    ) < route_paths.index("/api/canonical-v2/admin/domains/{domain}/{canonical_id}")
    assert route_paths.index("/api/{path:path}") < route_paths.index("/static")

    client = TestClient(candidate, raise_server_exceptions=False)
    effects_before = dict(probes["effects"])
    bodies: list[Any] = []
    for method in sorted(_REJECT_METHODS):
        response = client.request(method, "/api/legacy/mutate")
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/json")
        if method == "HEAD":
            assert response.content == b""
            continue
        bodies.append(response.json())
        if method == "OPTIONS":
            preflight = client.options(
                "/api/legacy/mutate",
                headers={
                    "Origin": "https://legacy.invalid",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert preflight.status_code == 404
            assert preflight.json() == bodies[-1]
    assert all(body == bodies[0] for body in bodies)
    assert probes["effects"] == effects_before

    writer_fragments = (
        "edit",
        "delete",
        "upload",
        "batch",
        "build",
        "promote",
        "alias",
        "seed",
        "pipeline",
        "milvus",
        "quality",
    )
    assert not any(
        path.startswith("/api/")
        and path != "/api/{path:path}"
        and any(fragment in path.casefold() for fragment in writer_fragments)
        for _, path in rows
    )


def _nested_values(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for current_key, child in value.items():
            if current_key == key:
                found.append(child)
            found.extend(_nested_values(child, key))
    elif isinstance(value, list):
        for child in value:
            found.extend(_nested_values(child, key))
    return found


def _assert_release_bound_payload(
    payload: Any,
    *,
    release_id: str,
    lineage: bool = False,
) -> None:
    releases = _nested_values(payload, "release_id")
    assert releases and set(releases) == {release_id}
    if lineage:
        lineage_values = [
            value
            for key in (
                "evidence_ids",
                "field_lineage",
                "relationship_lineage",
                "retrieval_traces",
            )
            for value in _nested_values(payload, key)
        ]
        assert any(value for value in lineage_values)
        assert any(value for value in _nested_values(payload, "limitations"))


def _assert_runtime_plan_controls(
    plan: Any,
    *,
    relationship: bool,
    expected_enumeration_policy: Any = None,
) -> None:
    budget = plan.supplemental_budget
    assert budget is not None
    assert budget.model_dump(mode="json") == {
        "max_wall_time_ms": 1_000,
        "max_provider_calls": 2,
        "max_retries": 1,
        "max_cost_units": 5.0,
    }
    if relationship:
        assert len(plan.relationship_paths) == 1
        path = plan.relationship_paths[0]
        assert (
            path.relationship_type_id,
            path.direction,
            path.source_type,
            path.target_type,
        ) == ("company_has_patent", "company_to_patent", "company", "patent")
        assert plan.structured_constraints.displayed_entity_ids
        policy = plan.enumeration_policy
        assert policy is not None
        assert policy.mode == "representative"
        assert policy.scope == _REPRESENTATIVE_SCOPE
        assert policy.as_of == plan.as_of
        assert policy.exhaustive is False
        assert policy.continuation_state == "available"
    else:
        assert plan.enumeration_policy == expected_enumeration_policy


def _assert_raw_plan_unchanged(probes: dict[str, Any]) -> None:
    raw = probes["captured"]["raw_plan"]
    assert raw.model_dump_json() == probes["captured"]["raw_plan_bytes"]
    assert raw is probes["captured"]["plan"]


def _projection_ids(scenario: dict[str, Any]) -> dict[str, str]:
    result = scenario["index_request"].candidate_projection_result
    return {
        projection.entity_type: projection.canonical_identity_id
        for projection in result.public_domain_projections
    }


def _assert_release_bound_vertical(
    client: TestClient,
    runtime: Any,
    scenario: dict[str, Any],
    probes: dict[str, Any],
) -> None:
    status = client.get("/api/canonical-v2/admin/status")
    assert status.status_code == 200
    status_payload = status.json()
    _assert_release_bound_payload(status_payload, release_id=_RELEASE_ID)
    assert scenario["bundle"].manifest.manifest_sha256 in _nested_values(
        status_payload, "manifest_sha256"
    )
    assert set(_nested_values(status_payload, "domain")) == set(_PUBLIC_DOMAINS)
    assert status_payload["gap_summary"] == {
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }
    gap_query = probes["captured"]["gap_query"]
    assert gap_query.release_id == _RELEASE_ID
    assert gap_query.limit == 50 and gap_query.offset == 0

    ids = _projection_ids(scenario)
    for domain in _PUBLIC_DOMAINS:
        page = client.get(
            f"/api/canonical-v2/admin/domains/{domain}",
            params={"limit": 25, "offset": 0},
        )
        assert page.status_code == 200, page.text
        _assert_release_bound_payload(page.json(), release_id=_RELEASE_ID, lineage=True)
        assert set(_nested_values(page.json(), "domain")) == {domain}
        assert ids[domain] in _nested_values(page.json(), "canonical_identity_id")
        _assert_runtime_plan_controls(
            probes["captured"]["read_input"], relationship=False
        )
        _assert_raw_plan_unchanged(probes)

    detail = client.get(f"/api/canonical-v2/admin/domains/company/{ids['company']}")
    assert detail.status_code == 200
    _assert_release_bound_payload(detail.json(), release_id=_RELEASE_ID, lineage=True)
    assert _nested_values(detail.json(), "canonical_identity_id") == [ids["company"]]
    _assert_runtime_plan_controls(probes["captured"]["read_input"], relationship=False)

    related = client.get(
        f"/api/canonical-v2/admin/domains/company/{ids['company']}/related",
        params={"relation_type": "company_has_patent", "limit": 20},
    )
    assert related.status_code == 200, related.text
    related_payload = related.json()
    _assert_release_bound_payload(related_payload, release_id=_RELEASE_ID, lineage=True)
    assert ids["patent"] in json.dumps(related_payload, ensure_ascii=False)
    _assert_runtime_plan_controls(probes["captured"]["read_input"], relationship=True)
    _assert_raw_plan_unchanged(probes)

    initial = client.post(
        "/api/chat",
        json={"query": _INITIAL_QUERY, "entity_id_hint": None},
    )
    assert initial.status_code == 200, initial.text
    initial_payload = initial.json()
    initial_v2 = initial_payload["structured_payload"]["canonical_v2"]
    assert "Robotics company." in initial_payload["answer_text"]
    assert "2026 年当前营收" in initial_payload["answer_text"]
    assert initial_v2["release_id"] == _RELEASE_ID
    assert initial_v2["lanes"] == ["exact", "web"]
    _assert_runtime_plan_controls(probes["captured"]["read_input"], relationship=False)
    offer = initial_v2["continuation_offer"]
    assert offer is not None and 1 <= len(offer["options"]) <= 3
    selected_option = offer["options"][0]["option_id"]
    continued = client.post(
        "/api/chat",
        json={"query": _INITIAL_QUERY, "entity_id_hint": selected_option},
    )
    assert continued.status_code == 200, continued.text
    continued_v2 = continued.json()["structured_payload"]["canonical_v2"]
    assert continued_v2["context_receipt"]["selected_option_id"] == selected_option
    _assert_runtime_plan_controls(probes["captured"]["read_input"], relationship=False)

    chat = client.post(
        "/api/chat",
        json={"query": _RELATIONSHIP_QUERY, "entity_id_hint": None},
    )
    assert chat.status_code == 200, chat.text
    chat_payload = chat.json()
    v2 = chat_payload["structured_payload"]["canonical_v2"]
    assert v2["release_id"] == _RELEASE_ID
    assert v2["plan_id"]
    assert v2["plan_version"]
    assert v2["lanes"] == ["relationship", "web"]
    assert v2["retrieval_traces"]
    assert v2["evidence_ids"]
    assert v2["claims"]
    assert v2["claim_evidence_mappings"]
    assert "Robot control system" in chat_payload["answer_text"]
    assert "Robotics Co" in chat_payload["answer_text"]
    _assert_runtime_plan_controls(probes["captured"]["read_input"], relationship=True)

    session_id = client.cookies.get("miroflow_chat_session")
    assert session_id
    checkpoint = runtime.chat_adapter.get_feedback_checkpoint(session_id)
    assert checkpoint is not None and checkpoint.release_id == _RELEASE_ID
    forged = {
        **chat_payload,
        "feedback_type": "incorrect_answer",
        "note": "Please review the retained answer evidence.",
        "answer_text": "CLIENT_FORGED_ANSWER",
        "structured_payload": {
            "release_id": "client-forged-release",
            "query_trace_id": "client-forged-query",
            "answer_trace_id": "client-forged-answer",
            "evidence_ids": ["client-forged-evidence"],
        },
    }
    feedback = client.post("/api/chat/feedback", json=forged)
    assert feedback.status_code == 200, feedback.text
    feedback_payload = feedback.json()
    assert feedback_payload["status"] == "filed"
    assert feedback_payload["issue_id"]

    gap_detail = client.get(
        f"/api/canonical-v2/operations/gaps/{feedback_payload['issue_id']}"
    )
    assert gap_detail.status_code == 200, gap_detail.text
    gap_payload = gap_detail.json()["gap"]
    assert gap_payload["release_id"] == checkpoint.release_id
    assert gap_payload["query_trace_id"] == checkpoint.query_trace_id
    assert gap_payload["answer_trace_id"] == checkpoint.answer_trace_id
    assert gap_payload["evidence_ids"] == list(checkpoint.evidence_ids)
    assert "client-forged" not in json.dumps(gap_payload, ensure_ascii=False)
    assert probes["captured"]["gap_signal"].release_id == checkpoint.release_id
    assert runtime.gap_operations is probes["recorded_gap"]
    updated_status = client.get("/api/canonical-v2/admin/status")
    assert updated_status.status_code == 200
    updated_summary = updated_status.json()["gap_summary"]
    assert updated_summary["total"] == 1
    assert updated_summary["limit"] == 50 and updated_summary["offset"] == 0
    assert [item["gap_id"] for item in updated_summary["items"]] == [
        feedback_payload["issue_id"]
    ]


def _assert_422_without_effects(
    client: TestClient,
    probes: dict[str, Any],
    method: str,
    path: str,
    **kwargs: Any,
) -> None:
    before = {key: probes["effects"][key] for key in ("plan", "read", "answer", "gap")}
    response = client.request(method, path, **kwargs)
    assert response.status_code == 422, (path, kwargs, response.text)
    assert {
        key: probes["effects"][key] for key in ("plan", "read", "answer", "gap")
    } == before


def _assert_admin_input_contract(
    client: TestClient,
    runtime: Any,
    probes: dict[str, Any],
) -> None:
    entity_ids = {
        "company": "company-robotics",
        "paper": "paper-ada",
        "patent": "patent-ada",
        "professor": "professor-ada",
    }
    nonempty_filters = {
        ("company", "quality_status"),
        ("paper", "venue"),
        ("paper", "year"),
        ("paper", "quality_status"),
        ("patent", "quality_status"),
        ("professor", "institution"),
        ("professor", "department"),
        ("professor", "quality_status"),
    }
    for domain, contract in _DOMAIN_INPUTS.items():
        root = f"/api/canonical-v2/admin/domains/{domain}"
        default_page = client.get(root)
        assert default_page.status_code == 200
        assert _nested_values(default_page.json(), "limit") == [25]
        assert _nested_values(default_page.json(), "offset") == [0]
        for field in contract["filters"]:
            value = contract["typed"].get(field, "accepted")
            response = client.get(
                root,
                params=(("filter_field", field), ("filter_value", value)),
            )
            assert response.status_code == 200, (domain, field, response.text)
            ids = _nested_values(response.json(), "canonical_identity_id")
            assert ids == (
                [entity_ids[domain]] if (domain, field) in nonempty_filters else []
            )
            receipts = _nested_values(response.json(), "filter_receipt")
            assert receipts == [{"field": field, "value": value}]
            _assert_runtime_plan_controls(
                probes["captured"]["read_input"], relationship=False
            )
        for field in contract["filters"]:
            response = client.get(f"{root}/facets/{field}")
            assert response.status_code == 200, (domain, field, response.text)
            buckets = response.json().get("buckets", [])
            assert (
                buckets
                == sorted(
                    buckets,
                    key=lambda bucket: (
                        -bucket["count"],
                        str(
                            bucket.get("normalized_value", bucket.get("value", ""))
                        ).casefold(),
                    ),
                )[:100]
            )
            if (domain, field) in nonempty_filters:
                assert buckets and buckets[0]["count"] == 1
            else:
                assert buckets == []
        for sort in contract["sorts"]:
            for order in ("asc", "desc"):
                response = client.get(
                    root,
                    params={"sort": sort, "order": order, "limit": 100, "offset": 0},
                )
                assert response.status_code == 200, (domain, sort, response.text)
                assert _nested_values(response.json(), "sort_keys") == [
                    [
                        {"field": sort, "order": order},
                        {"field": "canonical_identity_id", "order": "asc"},
                    ]
                ]
                _assert_runtime_plan_controls(
                    probes["captured"]["read_input"], relationship=False
                )

    original_candidate = runtime.admin_runtime.candidate_projection
    paper_projection = next(
        item
        for item in original_candidate.public_domain_projections
        if item.entity_type == "paper"
    )
    numeric_papers = (
        paper_projection.model_copy(
            update={
                "canonical_identity_id": "paper-numeric-2",
                "citation_count": 2,
            }
        ),
        paper_projection.model_copy(
            update={
                "canonical_identity_id": "paper-numeric-10",
                "citation_count": 10,
            }
        ),
    )
    numeric_candidate = original_candidate.model_copy(
        update={
            "public_domain_projections": (
                *(
                    item
                    for item in original_candidate.public_domain_projections
                    if item.entity_type != "paper"
                ),
                *numeric_papers,
            )
        }
    )
    object.__setattr__(runtime.admin_runtime, "candidate_projection", numeric_candidate)
    try:
        for order, expected in (
            ("asc", ("paper-numeric-2", "paper-numeric-10")),
            ("desc", ("paper-numeric-10", "paper-numeric-2")),
        ):
            numeric = client.get(
                "/api/canonical-v2/admin/domains/paper",
                params={"sort": "citation_count", "order": order},
            )
            assert numeric.status_code == 200
            assert (
                tuple(item["canonical_identity_id"] for item in numeric.json()["items"])
                == expected
            )
            _assert_raw_plan_unchanged(probes)
    finally:
        object.__setattr__(
            runtime.admin_runtime,
            "candidate_projection",
            original_candidate,
        )

    for domain, contract in _DOMAIN_INPUTS.items():
        root = f"/api/canonical-v2/admin/domains/{domain}"
        all_fields = set().union(
            *(set(value["filters"]) for value in _DOMAIN_INPUTS.values())
        ) | {"raw_json_path"}
        all_sorts = set().union(
            *(set(value["sorts"]) for value in _DOMAIN_INPUTS.values())
        ) | {"raw_sql"}
        for field in sorted(all_fields - set(contract["filters"])):
            _assert_422_without_effects(
                client,
                probes,
                "GET",
                root,
                params={"filter_field": field, "filter_value": "value"},
            )
            _assert_422_without_effects(
                client,
                probes,
                "GET",
                f"{root}/facets/{field}",
            )
        for sort in sorted(all_sorts - set(contract["sorts"])):
            _assert_422_without_effects(
                client, probes, "GET", root, params={"sort": sort}
            )

    for domain, field, display_value in (
        ("paper", "venue", "Robotics Journal"),
        ("professor", "department", "Computer Science"),
    ):
        response = client.get(
            f"/api/canonical-v2/admin/domains/{domain}",
            params={"filter_field": field, "filter_value": display_value},
        )
        assert response.status_code == 200
        assert _nested_values(response.json(), "canonical_identity_id") == []

    paper = "/api/canonical-v2/admin/domains/paper"
    patent = "/api/canonical-v2/admin/domains/patent"
    for value in ("999", "10000", "2026.5", "not-a-year"):
        _assert_422_without_effects(
            client,
            probes,
            "GET",
            paper,
            params={"filter_field": "year", "filter_value": value},
        )
    for value in ("2026", "2026-02-30", "2026-1-2", "not-a-date"):
        _assert_422_without_effects(
            client,
            probes,
            "GET",
            patent,
            params={"filter_field": "publication_date", "filter_value": value},
        )

    invalid_list_cases = (
        ("/api/canonical-v2/admin/domains/person", {}),
        ("/api/canonical-v2/admin/domains/company", {"q": ""}),
        ("/api/canonical-v2/admin/domains/company", {"q": "x" * 201}),
        ("/api/canonical-v2/admin/domains/company", {"limit": 0}),
        ("/api/canonical-v2/admin/domains/company", {"limit": 101}),
        ("/api/canonical-v2/admin/domains/company", {"offset": -1}),
        ("/api/canonical-v2/admin/domains/company", {"offset": 9_950, "limit": 51}),
        ("/api/canonical-v2/admin/domains/company", {"sort": "raw_sql"}),
        ("/api/canonical-v2/admin/domains/company", {"order": "sideways"}),
        ("/api/canonical-v2/admin/domains/company", {"filter_field": "industry"}),
        ("/api/canonical-v2/admin/domains/company", {"filter_value": "robotics"}),
        (
            "/api/canonical-v2/admin/domains/company",
            {"filter_field": "venue", "filter_value": "venue:neurips"},
        ),
    )
    for path, params in invalid_list_cases:
        _assert_422_without_effects(client, probes, "GET", path, params=params)

    for query in ("x", "x" * 200):
        bounded = client.get(
            "/api/canonical-v2/admin/domains/company", params={"q": query}
        )
        assert bounded.status_code == 200
    edge_page = client.get(
        "/api/canonical-v2/admin/domains/company",
        params={"offset": 9_999, "limit": 1},
    )
    assert edge_page.status_code == 200

    five_pairs = [
        (name, value)
        for index in range(5)
        for name, value in (
            ("filter_field", "quality_status"),
            ("filter_value", f"accepted-{index}"),
        )
    ]
    _assert_422_without_effects(
        client,
        probes,
        "GET",
        "/api/canonical-v2/admin/domains/company",
        params=five_pairs,
    )
    duplicate_pair = (
        ("filter_field", "quality_status"),
        ("filter_value", "partial"),
        ("filter_field", "quality_status"),
        ("filter_value", "partial"),
    )
    _assert_422_without_effects(
        client,
        probes,
        "GET",
        "/api/canonical-v2/admin/domains/company",
        params=duplicate_pair,
    )
    _assert_422_without_effects(
        client,
        probes,
        "GET",
        "/api/canonical-v2/admin/domains/company/facets/name",
    )

    invalid_id = "x" * 201
    _assert_422_without_effects(
        client,
        probes,
        "GET",
        f"/api/canonical-v2/admin/domains/company/{invalid_id}",
    )
    for domain, relation in (
        ("company", "professor_authored_paper"),
        ("paper", "company_has_patent"),
        ("patent", "professor_authored_paper"),
        ("professor", "company_has_patent"),
    ):
        _assert_422_without_effects(
            client,
            probes,
            "GET",
            f"/api/canonical-v2/admin/domains/{domain}/accepted-id/related",
            params={"relation_type": relation},
        )
    for limit in (0, 51):
        _assert_422_without_effects(
            client,
            probes,
            "GET",
            "/api/canonical-v2/admin/domains/company/accepted-id/related",
            params={"relation_type": "company_has_patent", "limit": limit},
        )

    legal_relations = (
        ("company", "company-robotics", "company_has_patent", ("patent-ada",)),
        ("patent", "patent-ada", "company_has_patent", ("company-robotics",)),
        ("professor", "professor-ada", "professor_authored_paper", ()),
        ("paper", "paper-ada", "professor_authored_paper", ()),
    )
    for domain, source_id, relation, expected_target in legal_relations:
        related = client.get(
            f"/api/canonical-v2/admin/domains/{domain}/{source_id}/related",
            params={"relation_type": relation},
        )
        assert related.status_code == 200, (domain, relation, related.text)
        assert _nested_values(related.json(), "relation_type") == [relation]
        assert 20 in _nested_values(related.json(), "limit")
        expected_path = _RELATIONSHIP_PATH_BY_SOURCE_ID[source_id]
        captured_plan = probes["captured"]["read_input"]
        assert len(captured_plan.relationship_paths) == 1
        captured_path = captured_plan.relationship_paths[0]
        assert (
            captured_path.relationship_type_id,
            captured_path.direction,
            captured_path.source_type,
            captured_path.target_type,
        ) == expected_path
        _assert_runtime_plan_controls(
            captured_plan,
            relationship=(source_id == "company-robotics"),
            expected_enumeration_policy=(
                None
                if source_id == "company-robotics"
                else probes["captured"]["raw_plan"].enumeration_policy
            ),
        )
        _assert_raw_plan_unchanged(probes)
        assert (
            tuple(item["canonical_identity_id"] for item in related.json()["items"])
            == expected_target
        )

    _assert_422_without_effects(
        client,
        probes,
        "GET",
        "/api/canonical-v2/admin/domains/company/patent-ada/related",
        params={"relation_type": "company_has_patent"},
    )

    export = "/api/canonical-v2/admin/domains/company/export"
    for params in (
        {},
        (("id", "company-robotics"), ("id", "company-robotics")),
        {"id": "company-robotics", "format": "csv"},
        [("id", f"company-{index}") for index in range(501)],
        (
            ("id", "company-robotics"),
            ("id", "company-unknown"),
            ("format", "jsonl"),
        ),
    ):
        _assert_422_without_effects(client, probes, "GET", export, params=params)
    exported = client.get(
        export,
        params=(("id", "company-robotics"), ("format", "jsonl")),
    )
    assert exported.status_code == 200
    lines = exported.content.splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["canonical_identity_id"] == "company-robotics"
    assert row["release_id"] == _RELEASE_ID


def _assert_failure_response(response: Any) -> None:
    assert response.status_code in {409, 422, 503}
    assert response.headers["content-type"].startswith("application/json")


def _assert_effect_order_and_atomicity(
    seam: _S11BAdminSeam,
    scenario: dict[str, Any],
    probes: dict[str, Any],
) -> None:
    del probes

    binding_fields = (
        "release_id",
        "publication_state",
        "published_release_sha256",
        "publication_verification_evidence_ids",
        "manifest_sha256",
        "index_projection_request_sha256",
        "index_projection_result_sha256",
        "candidate_projection_result_sha256",
        "internal_reference_projection_result_sha256",
    )
    for field in binding_fields:
        runtime, plan_probes = _compose_observed_runtime(seam, scenario)

        def corrupt_binding(plan: Any, *, target: str = field) -> Any:
            binding = plan.release_binding
            assert binding is not None
            if target == "release_id":
                value: Any = "cross-release"
            elif target == "publication_state":
                value = (
                    "rolled_back" if binding.publication_state == "active" else "active"
                )
            elif target == "publication_verification_evidence_ids":
                value = ("release-parity:wrong",)
            else:
                value = "d" * 64
            return plan.model_copy(
                update={"release_binding": binding.model_copy(update={target: value})}
            )

        plan_probes["faults"]["plan_after"] = corrupt_binding
        plan_client = TestClient(
            seam.candidate_app_factory(runtime=runtime),
            raise_server_exceptions=False,
        )
        _assert_failure_response(
            plan_client.get("/api/canonical-v2/admin/domains/company")
        )
        assert {
            key: plan_probes["effects"][key]
            for key in ("plan", "read", "answer", "answer_factory")
        } == {"plan": 1, "read": 0, "answer": 0, "answer_factory": 0}

    read_module = scenario["modules"]["read"]

    def orphan_item(evidence: Any) -> Any:
        assert evidence.items
        first = evidence.items[0].model_copy(update={"lane": "orphan-lane"})
        return evidence.model_copy(update={"items": (first, *evidence.items[1:])})

    def orphan_evidence_id(evidence: Any) -> Any:
        assert evidence.items
        first = evidence.items[0].model_copy(update={"evidence_id": "orphan:evidence"})
        return evidence.model_copy(update={"items": (first, *evidence.items[1:])})

    read_faults: tuple[Callable[[Any], Any], ...] = (
        lambda evidence: evidence.model_copy(update={"release_id": "cross-release"}),
        lambda evidence: evidence.model_copy(update={"original_query": "cross-query"}),
        orphan_item,
        orphan_evidence_id,
        lambda evidence: evidence.model_copy(
            update={
                "supplemental_budget_receipt": read_module.SupplementalBudgetReceipt(
                    exhausted=False,
                    exhaustion_reason=None,
                    exhausted_axis=None,
                    limit_value=None,
                    used_value=None,
                    provider_calls=99,
                    retry_count=99,
                    elapsed_ms=99_999,
                    cost_units=99.0,
                    attempt_count=99,
                )
            }
        ),
    )
    for transform in read_faults:
        runtime, read_probes = _compose_observed_runtime(seam, scenario)
        read_probes["faults"]["read_after"] = transform
        read_client = TestClient(
            seam.candidate_app_factory(runtime=runtime),
            raise_server_exceptions=False,
        )
        _assert_failure_response(
            read_client.get("/api/canonical-v2/admin/domains/company")
        )
        assert {
            key: read_probes["effects"][key]
            for key in ("plan", "read", "answer", "answer_factory")
        } == {"plan": 1, "read": 1, "answer": 0, "answer_factory": 0}

    def answer_claim_drift(answer: Any) -> Any:
        assert answer.claims
        claim = answer.claims[0].model_copy(
            update={"evidence_ids": ("orphan:evidence",)}
        )
        return answer.model_copy(update={"claims": (claim, *answer.claims[1:])})

    def answer_mapping_drift(answer: Any) -> Any:
        assert answer.claim_evidence_map
        mapping = answer.claim_evidence_map[0].model_copy(
            update={"evidence_ids": ("orphan:evidence",)}
        )
        return answer.model_copy(
            update={"claim_evidence_map": (mapping, *answer.claim_evidence_map[1:])}
        )

    answer_faults: tuple[Callable[[Any], Any], ...] = (
        lambda answer: answer.model_copy(update={"release_id": "cross-release"}),
        answer_claim_drift,
        answer_mapping_drift,
    )
    for transform in answer_faults:
        runtime, answer_probes = _compose_observed_runtime(seam, scenario)
        answer_client = TestClient(
            seam.candidate_app_factory(runtime=runtime),
            raise_server_exceptions=False,
        )
        established = answer_client.post(
            "/api/chat",
            json={"query": _INITIAL_QUERY, "entity_id_hint": None},
        )
        assert established.status_code == 200
        session_id = answer_client.cookies.get("miroflow_chat_session")
        checkpoint = runtime.chat_adapter.get_feedback_checkpoint(session_id)
        assert checkpoint is not None
        checkpoint_bytes = checkpoint.model_dump_json().encode("utf-8")
        cookie_before = dict(answer_client.cookies)
        effects_before = dict(answer_probes["effects"])
        option = established.json()["structured_payload"]["canonical_v2"][
            "continuation_offer"
        ]["options"][0]["option_id"]
        answer_probes["faults"]["answer_after"] = transform
        _assert_failure_response(
            answer_client.post(
                "/api/chat",
                json={"query": _INITIAL_QUERY, "entity_id_hint": option},
            )
        )
        assert {
            key: answer_probes["effects"][key] - effects_before[key]
            for key in ("plan", "read", "answer", "answer_factory")
        } == {"plan": 1, "read": 1, "answer": 1, "answer_factory": 1}
        retained = runtime.chat_adapter.get_feedback_checkpoint(session_id)
        assert retained is not None
        assert retained.model_dump_json().encode("utf-8") == checkpoint_bytes
        assert dict(answer_client.cookies) == cookie_before

    runtime, gap_probes = _compose_observed_runtime(seam, scenario)
    gap_client = TestClient(
        seam.candidate_app_factory(runtime=runtime), raise_server_exceptions=False
    )
    feedback_body = {
        "query": "unknown",
        "query_type": "canonical_v2:A",
        "answer_text": "client-only",
        "answer_style": "template",
        "citations": [],
        "citation_map": {},
        "structured_payload": {},
        "feedback_type": "incorrect_answer",
        "note": "missing checkpoint",
    }
    _assert_failure_response(gap_client.post("/api/chat/feedback", json=feedback_body))
    assert gap_probes["effects"]["gap"] == 0

    valid_chat = gap_client.post(
        "/api/chat",
        json={"query": _RELATIONSHIP_QUERY, "entity_id_hint": None},
    )
    assert valid_chat.status_code == 200
    session_id = gap_client.cookies.get("miroflow_chat_session")
    checkpoint = runtime.chat_adapter.get_feedback_checkpoint(session_id)
    assert checkpoint is not None
    original_getter = runtime.chat_adapter.get_feedback_checkpoint
    runtime.chat_adapter.get_feedback_checkpoint = lambda _: checkpoint.model_copy(
        update={"release_id": "cross-release"}
    )
    try:
        _assert_failure_response(
            gap_client.post("/api/chat/feedback", json=feedback_body)
        )
    finally:
        runtime.chat_adapter.get_feedback_checkpoint = original_getter
    assert gap_probes["effects"]["gap"] == 0

    monkeypatch = scenario["monkeypatch"]
    with monkeypatch.context() as guarded:
        guarded.setattr(
            seam.main_module,
            "_compose_operations",
            lambda: (_ for _ in ()).throw(
                AssertionError("environment composer reached")
            ),
            raising=False,
        )
        guarded.setattr(
            importlib.import_module("backend.canonical_v2_deps"),
            "_compose_operations",
            lambda: (_ for _ in ()).throw(
                AssertionError("environment composer reached")
            ),
        )
        gaps = gap_client.get("/api/canonical-v2/operations/gaps")
    assert gaps.status_code == 200


def _path_hash_digest(paths: list[Path]) -> str:
    value = [
        {
            "path": path.relative_to(_REPO_ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(paths)
    ]
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def test_s9j_static_chat_uses_typed_public_copy() -> None:
    chat_path = _REPO_ROOT / "apps/admin-console/backend/static/chat.html"
    chat = chat_path.read_text(encoding="utf-8")
    for marker in (
        "继续检索针对性证据",
        "缺少支持证据",
        "证据存在冲突",
    ):
        assert marker in chat
    continuation = re.search(
        r"function continuationText\(option\) \{.*?\n      \}",
        chat,
        re.DOTALL,
    )
    assert continuation is not None
    harness = f"""
function safePublicText(value) {{
  return typeof value === "string" && value.trim() ? value.trim() : null;
}}
{continuation.group(0)}
console.log(JSON.stringify([
  continuationText({{operation: "targeted_evidence_search", label: "RAW_ENUM"}}),
  continuationText({{operation: "narrow_scope", label: "缩小范围"}}),
]));
"""
    completed = subprocess.run(
        ["node", "-"],
        input=harness,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == ["继续检索针对性证据", "缩小范围"]


def _assert_static_and_import_quarantine(
    candidate: Any, probes: dict[str, Any]
) -> None:
    browse_path = _REPO_ROOT / "apps/admin-console/backend/static/browse.html"
    browse = browse_path.read_text(encoding="utf-8")
    for path in (
        "/api/canonical-v2/admin/status",
        "/api/canonical-v2/admin/domains/",
        "/api/canonical-v2/operations/gaps",
    ):
        assert path in browse
    for marker in (
        "Canonical V2 科创知识平台",
        "版本概览",
        "数据目录",
        "证据与限制",
        "查看关联",
        "进入 V2 对话",
    ):
        assert marker in browse
    api_literals = set(re.findall(r"/api/[A-Za-z0-9_{}./:-]+", browse))
    assert api_literals == {
        "/api/canonical-v2/admin/status",
        "/api/canonical-v2/admin/domains/",
        "/api/canonical-v2/operations/gaps",
    }
    assert any(token in browse for token in ("textContent", "createTextNode"))
    for forbidden in (
        "/api/data/",
        "/api/seeds/",
        "/api/pipeline",
        "/api/upload",
        "insertAdjacentHTML",
        "promote",
        "Milvus",
        "canonical_writer",
    ):
        assert forbidden not in browse
    assert re.search(r"(?:inner|outer)\s*HTML", browse, re.IGNORECASE) is None

    chat_path = _REPO_ROOT / "apps/admin-console/backend/static/chat.html"
    chat = chat_path.read_text(encoding="utf-8")
    for marker in (
        "Canonical V2 智能检索",
        "safePublicText(data.answer_text)",
        "limitationText(limitation)",
        "continuationText(option)",
        "renderTrace(view.bubble, trace)",
        "继续检索针对性证据",
        "缺少支持证据",
        "证据存在冲突",
    ):
        assert marker in chat
    for forbidden_fixture in (
        "Robotics Co",
        "陈艾达",
        "Evidence-bound robotics",
    ):
        assert forbidden_fixture not in chat

    react_files = list((_REPO_ROOT / "apps/admin-console/frontend/src").rglob("*"))
    react_files = [path for path in react_files if path.is_file()]
    assert len(react_files) == 22
    assert _path_hash_digest(react_files) == (
        "99abf5922399cd8bf20990934fa251c2a246da300fd4af3af384e6a9478ead77"
    )
    assert not any(
        getattr(route, "path", None) in {"/{path:path}", "/assets"}
        for route in candidate.routes
    )

    script = r"""
import importlib.abc
import json
import sys

forbidden = (
    "backend.api.chat",
    "backend.deps",
    "backend.api.admin_professor",
    "backend.api.batch",
    "backend.api.data",
    "backend.api.domains",
    "backend.api.pipeline",
    "backend.api.review",
    "backend.api.seeds",
    "backend.api.upload",
    "src.data_agents.canonical",
    "src.data_agents.company.canonical_import",
    "src.data_agents.company.release",
    "src.data_agents.company.vectorizer",
    "src.data_agents.professor.canonical_writer",
    "src.data_agents.professor.release",
    "src.data_agents.professor.vectorizer",
    "src.data_agents.paper.canonical_writer",
    "src.data_agents.paper.identity_status_writer",
    "src.data_agents.paper.quality_promotion",
    "src.data_agents.paper.release",
    "src.data_agents.patent.canonical_writer",
    "src.data_agents.patent.quality_promotion",
    "src.data_agents.patent.release",
    "src.data_agents.patent.vectorizer",
    "src.data_agents.service.retrieval",
    "src.data_agents.service.search_service",
    "src.data_agents.publish",
    "src.data_agents.paper.milvus_backfill",
    "src.data_agents.storage.milvus_collections",
    "src.data_agents.storage.milvus_store",
    "pymilvus",
)

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in forbidden):
            raise ImportError("forbidden S11B import attempted: " + fullname)
        return None

sys.meta_path.insert(0, Blocker())
import backend.main
shell = backend.main._create_canonical_v2_route_shell()
assert not hasattr(shell.state, "canonical_v2_consumer_runtime")
try:
    backend.main.create_canonical_v2_candidate_app(runtime=object())
except (TypeError, ValueError):
    pass
else:
    raise AssertionError("candidate factory accepted a wrong runtime")
loaded = sorted(
    name for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
)
assert not loaded, loaded
print(json.dumps(sorted((method, route.path) for route in shell.routes for method in (getattr(route, "methods", None) or {"MOUNT"}))))
"""
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (
                str(_REPO_ROOT / "apps/admin-console"),
                str(_REPO_ROOT / "apps/miroflow-agent"),
            )
        ),
    }
    imported = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_REPO_ROOT / "apps/admin-console",
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert imported.returncode == 0, imported.stdout + imported.stderr
    for key in ("legacy", "sql", "provider"):
        assert probes["effects"][key] == 0


def test_s11b_candidate_app_exposes_only_release_bound_v2_consumers(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seam = _load_s11b_admin_seam()
    _assert_seam_contract(seam)

    scenario = _build_accepted_release_scenario(tmp_path)
    scenario["monkeypatch"] = monkeypatch
    runtime, probes = _compose_observed_runtime(seam, scenario)
    _install_forbidden_effect_canaries(monkeypatch, probes)

    _assert_constructor_contract(seam, scenario, probes)
    candidate = _assert_candidate_factory_contract(seam, runtime, probes)
    _assert_candidate_route_contract(candidate, probes)

    client = seam.test_client_type(candidate, raise_server_exceptions=False)
    _assert_release_bound_vertical(client, runtime, scenario, probes)
    _assert_admin_input_contract(client, runtime, probes)
    _assert_effect_order_and_atomicity(seam, scenario, probes)
    _assert_static_and_import_quarantine(candidate, probes)
    assert request.node.nodeid.endswith(
        "test_s11b_candidate_app_exposes_only_release_bound_v2_consumers"
    )
