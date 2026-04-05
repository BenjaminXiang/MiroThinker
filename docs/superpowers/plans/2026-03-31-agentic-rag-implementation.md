# Agentic RAG Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the user-facing Shenzhen sci-tech Agentic-RAG service from `docs/Agentic-RAG-PRD.md`: multi-turn query analysis, domain routing across professor/company/paper/patent, source-aware answer assembly, WeChat-embeddable H5 chat, and internal admin/feedback tooling.

**Architecture:** Keep the existing `apps/miroflow-agent` runtime as the orchestration and structured-output engine, but build a separate Flask service app in `apps/agentic-rag-service` for product-facing APIs, context management, routing, and UI. Use contract-shaped domain records as the service boundary; in the first implementation, read local JSONL exports from data agents and apply MiroFlow-assisted reranking, while keeping repository interfaces ready for PostgreSQL + Milvus adapters later.

**Tech Stack:** Python 3.12, Flask, Pydantic v2, Redis (with in-memory fallback), sqlite3, Hydra, existing `miroflow-agent` pipeline, pytest, pytest-asyncio

---

## Current State

- `docs/Agentic-RAG-PRD.md` already defines the user-facing product contract, including query types A/B/C/D/E/F/G, source-display rules, multi-turn behavior, H5 requirements, and admin requirements.
- `docs/Multi-turn-Context-Manager-Design.md` already defines the session context model, entity stack behavior, topic-switch rules, and Redis-backed TTL storage.
- `apps/miroflow-agent` already contains the reusable orchestration runtime, and the current worktree already includes an initial `output_mode=json` implementation with tests in `apps/miroflow-agent/tests/data_agents/test_structured_output_mode.py`.
- The repo does not yet contain a dedicated online Agentic-RAG service app, route planner, domain repository layer, or WeChat-facing H5 shell.
- The data-agent implementation plan is in progress, so this plan treats contract-valid domain exports as the online read model and does not wait for all long-term storage adapters before delivering the service layer.

## File Map

### Existing runtime changes

- Modify: `pyproject.toml`
- Modify: `justfile`
- Modify: `apps/miroflow-agent/conf/agent/default.yaml`
- Modify: `apps/miroflow-agent/src/io/input_handler.py`
- Modify: `apps/miroflow-agent/src/io/output_formatter.py`
- Modify: `apps/miroflow-agent/src/utils/prompt_utils.py`
- Modify: `apps/miroflow-agent/src/core/answer_generator.py`
- Modify: `apps/miroflow-agent/src/core/orchestrator.py`
- Modify: `apps/miroflow-agent/src/core/pipeline.py`
- Modify: `apps/miroflow-agent/tests/data_agents/test_structured_output_mode.py`

### New service application

- Create: `apps/agentic-rag-service/README.md`
- Create: `apps/agentic-rag-service/main.py`
- Create: `apps/agentic-rag-service/pyproject.toml`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/app.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/config.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/contracts.py`

### Runtime bridge

- Create: `apps/agentic-rag-service/src/agentic_rag_service/runtime/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/runtime/miroflow_runner.py`

### Multi-turn context layer

- Create: `apps/agentic-rag-service/src/agentic_rag_service/context/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/context/manager.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/context/store.py`

### Query analysis and routing

- Create: `apps/agentic-rag-service/src/agentic_rag_service/routing/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/routing/analyzer.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/routing/planner.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/routing/prompts.py`

### Retrieval and answer assembly

- Create: `apps/agentic-rag-service/src/agentic_rag_service/retrieval/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/retrieval/jsonl_repository.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/retrieval/web_search.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/service/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/service/answer_builder.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/service/progress.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/service/query_service.py`

### Admin and observability

- Create: `apps/agentic-rag-service/src/agentic_rag_service/admin/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/admin/store.py`

### HTTP and H5 layer

- Create: `apps/agentic-rag-service/src/agentic_rag_service/api/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/api/admin.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/api/chat.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/web/templates/admin.html`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/web/templates/chat.html`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/web/static/css/admin.css`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/web/static/css/chat.css`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/web/static/js/admin.js`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/web/static/js/chat.js`

### Test suite

- Create: `apps/agentic-rag-service/tests/conftest.py`
- Create: `apps/agentic-rag-service/tests/fixtures/scenarios.json`
- Create: `apps/agentic-rag-service/tests/fixtures/companies.jsonl`
- Create: `apps/agentic-rag-service/tests/fixtures/papers.jsonl`
- Create: `apps/agentic-rag-service/tests/fixtures/patents.jsonl`
- Create: `apps/agentic-rag-service/tests/fixtures/professors.jsonl`
- Create: `apps/agentic-rag-service/tests/unit/test_contracts.py`
- Create: `apps/agentic-rag-service/tests/unit/test_context_manager.py`
- Create: `apps/agentic-rag-service/tests/unit/test_miroflow_runner.py`
- Create: `apps/agentic-rag-service/tests/unit/test_query_analyzer.py`
- Create: `apps/agentic-rag-service/tests/unit/test_query_service.py`
- Create: `apps/agentic-rag-service/tests/unit/test_route_planner.py`
- Create: `apps/agentic-rag-service/tests/unit/test_source_policy.py`
- Create: `apps/agentic-rag-service/tests/integration/test_admin_api.py`
- Create: `apps/agentic-rag-service/tests/integration/test_chat_api.py`
- Create: `apps/agentic-rag-service/tests/e2e/test_agentic_rag_scenarios.py`
- Create: `apps/agentic-rag-service/tests/e2e/test_streaming_sla.py`

## Dependency Graph

- Task 1 is the base for every later task because both query analysis and answer generation depend on validated JSON outputs.
- Task 2 depends on Task 1 because the context manager stores and returns typed contract objects.
- Task 3 depends on Tasks 1 and 2 because analysis output must include both session context and resolved entities.
- Task 4 depends on Task 3 because retrieval orchestration uses the route plan.
- Task 5 depends on Task 4 because the H5/API layer needs the service-layer response contract and progress events.
- Task 6 depends on Task 5 because feedback capture and dashboard metrics sit on top of live query handling.
- Task 7 depends on Tasks 1 through 6 because scenario coverage and SLA checks must exercise the whole stack.

## Out of Scope For This Plan

- Production-grade WeChat OAuth or account management
- Vendor-specific PostgreSQL / Milvus deployment manifests
- Rewriting the four data-agent collection plans
- A general-purpose chatbot outside Shenzhen sci-tech retrieval and the narrow safety exception defined in the PRD

### Task 1: Stabilize Structured JSON Output And Create The Service Skeleton

**Files:**
- Modify: `pyproject.toml`
- Modify: `justfile`
- Modify: `apps/miroflow-agent/conf/agent/default.yaml`
- Modify: `apps/miroflow-agent/src/io/input_handler.py`
- Modify: `apps/miroflow-agent/src/io/output_formatter.py`
- Modify: `apps/miroflow-agent/src/utils/prompt_utils.py`
- Modify: `apps/miroflow-agent/src/core/answer_generator.py`
- Modify: `apps/miroflow-agent/src/core/orchestrator.py`
- Modify: `apps/miroflow-agent/src/core/pipeline.py`
- Modify: `apps/miroflow-agent/tests/data_agents/test_structured_output_mode.py`
- Create: `apps/agentic-rag-service/pyproject.toml`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/config.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/contracts.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/runtime/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/runtime/miroflow_runner.py`
- Create: `apps/agentic-rag-service/tests/unit/test_contracts.py`
- Create: `apps/agentic-rag-service/tests/unit/test_miroflow_runner.py`

- [ ] **Step 1: Write the failing tests for typed structured output and service contracts**

```python
# apps/agentic-rag-service/tests/unit/test_contracts.py
from agentic_rag_service.contracts import QueryAnalysis, RoutePlan


def test_query_analysis_accepts_prd_query_types():
    analysis = QueryAnalysis(
        intent_type="C",
        target_modules=["paper"],
        is_topic_switch=False,
        additional_filters={"year_from": 2025},
        explicit_entities=[],
        coreferences=[],
    )
    assert analysis.intent_type == "C"


def test_route_plan_defaults_to_no_web_search():
    route = RoutePlan(
        strategy="single_domain",
        modules=["company"],
        query_text="介绍优必选",
    )
    assert route.needs_web_search is False
```

```python
# apps/agentic-rag-service/tests/unit/test_miroflow_runner.py
import pytest
from pydantic import BaseModel

from agentic_rag_service.runtime.miroflow_runner import MiroflowStructuredRunner


class DemoPayload(BaseModel):
    name: str
    score: float


@pytest.mark.asyncio
async def test_runner_validates_json_payload():
    async def fake_execute_pipeline(**_kwargs):
        return "summary", '{"name":"优必选","score":0.93}', "log.json", None

    runner = MiroflowStructuredRunner(execute_pipeline=fake_execute_pipeline)
    payload = await runner.run(
        task_description="Return one object",
        schema_model=DemoPayload,
    )

    assert payload == DemoPayload(name="优必选", score=0.93)
```

- [ ] **Step 2: Run the runtime and skeleton tests to verify the new service package fails before implementation**

Run:

```bash
uv run pytest apps/miroflow-agent/tests/data_agents/test_structured_output_mode.py -v -n 0
uv run pytest apps/agentic-rag-service/tests/unit/test_contracts.py -v -n 0
```

Expected:

```text
The existing `miroflow-agent` JSON-mode tests pass, but the new service tests fail because `agentic_rag_service` does not exist yet.
```

- [ ] **Step 3: Implement the new service package, typed contracts, and the MiroFlow JSON bridge**

```toml
# pyproject.toml
[project]
dependencies = [
    "miroflow-tools",
    "miroflow-agent",
    "agentic-rag-service",
    "collect-trace",
    "gradio-demo",
    "flask>=2.3.3",
    "werkzeug>=2.3.7",
]

[tool.uv.sources]
agentic-rag-service = { path = "apps/agentic-rag-service", editable = true }
```

```toml
# apps/agentic-rag-service/pyproject.toml
[project]
name = "agentic-rag-service"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "flask>=2.3.3",
    "pydantic>=2.11.3",
    "python-dotenv>=1.0.1",
    "redis>=6.0.0",
    "miroflow-agent",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agentic_rag_service"]
```

```python
# apps/agentic-rag-service/src/agentic_rag_service/contracts.py
from typing import Any, Literal

from pydantic import BaseModel, Field

IntentType = Literal["A", "B", "C", "D", "E", "F", "G"]
ModuleName = Literal["professor", "company", "paper", "patent"]


class ResolvedEntity(BaseModel):
    type: ModuleName
    id: str
    name: str
    confidence: float = Field(ge=0.0, le=1.0)


class QueryAnalysis(BaseModel):
    intent_type: IntentType
    target_modules: list[ModuleName]
    is_topic_switch: bool = False
    additional_filters: dict[str, Any] = Field(default_factory=dict)
    explicit_entities: list[ResolvedEntity] = Field(default_factory=list)
    coreferences: list[ResolvedEntity] = Field(default_factory=list)


class RoutePlan(BaseModel):
    strategy: Literal[
        "single_domain",
        "single_domain_follow_up",
        "cross_domain_jump",
        "aggregate",
        "knowledge",
        "reject",
        "clarify",
    ]
    modules: list[ModuleName]
    query_text: str
    needs_web_search: bool = False
    clarification_question: str | None = None
    source_note: str | None = None
```

```python
# apps/agentic-rag-service/src/agentic_rag_service/runtime/miroflow_runner.py
import json
import uuid
from typing import Any, TypeVar

from pydantic import BaseModel

from miroflow_agent.src.core.pipeline import execute_task_pipeline

ModelT = TypeVar("ModelT", bound=BaseModel)


class MiroflowStructuredRunner:
    def __init__(self, execute_pipeline=execute_task_pipeline):
        self._execute_pipeline = execute_pipeline

    async def run(self, *, schema_model: type[ModelT], task_description: str, **kwargs: Any) -> ModelT:
        schema = json.dumps(schema_model.model_json_schema(), ensure_ascii=False)
        _summary, payload, _log_file, _failure = await self._execute_pipeline(
            task_id=f"agentic-rag-{uuid.uuid4()}",
            task_description=task_description,
            task_file_name="",
            final_output_schema=schema,
            **kwargs,
        )
        return schema_model.model_validate_json(payload)
```

```make
# justfile
agentic-rag-service:
    uv run python apps/agentic-rag-service/main.py
```

- [ ] **Step 4: Run the focused tests and sync dependencies**

Run:

```bash
uv sync
uv run pytest apps/miroflow-agent/tests/data_agents/test_structured_output_mode.py -v -n 0
uv run pytest apps/agentic-rag-service/tests/unit/test_contracts.py apps/agentic-rag-service/tests/unit/test_miroflow_runner.py -v -n 0
```

Expected:

```text
PASS for the JSON-mode runtime tests and PASS for the new contract/runner tests.
```

- [ ] **Step 5: Commit the runtime and service skeleton**

```bash
git add pyproject.toml justfile \
  apps/miroflow-agent/conf/agent/default.yaml \
  apps/miroflow-agent/src/io/input_handler.py \
  apps/miroflow-agent/src/io/output_formatter.py \
  apps/miroflow-agent/src/utils/prompt_utils.py \
  apps/miroflow-agent/src/core/answer_generator.py \
  apps/miroflow-agent/src/core/orchestrator.py \
  apps/miroflow-agent/src/core/pipeline.py \
  apps/miroflow-agent/tests/data_agents/test_structured_output_mode.py \
  apps/agentic-rag-service
git commit -m "feat: bootstrap agentic rag service contracts"
```

### Task 2: Implement The Multi-Turn Context Manager

**Files:**
- Modify: `apps/agentic-rag-service/pyproject.toml`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/context/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/context/manager.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/context/store.py`
- Create: `apps/agentic-rag-service/tests/unit/test_context_manager.py`

- [ ] **Step 1: Write the failing tests for entity stacks, topic switching, and TTL-backed storage**

```python
# apps/agentic-rag-service/tests/unit/test_context_manager.py
from agentic_rag_service.context.manager import ContextManager
from agentic_rag_service.context.store import InMemorySessionStore
from agentic_rag_service.contracts import QueryAnalysis, ResolvedEntity


def test_context_manager_uses_latest_professor_for_pronoun_resolution():
    manager = ContextManager(store=InMemorySessionStore())
    session = manager.get_or_create("session-1", "wechat-openid-1")
    professor = ResolvedEntity(type="professor", id="PROF-1", name="丁文伯", confidence=0.96)

    session = manager.record_turn(
        session,
        user_input="介绍清华的丁文伯",
        analysis=QueryAnalysis(
            intent_type="A",
            target_modules=["professor"],
            explicit_entities=[professor],
            coreferences=[],
        ),
        result_summary="丁文伯教授画像",
    )

    resolved = manager.resolve_reference(session, "他", "professor")
    assert resolved is not None
    assert resolved.name == "丁文伯"


def test_context_manager_clears_entity_stack_on_topic_switch():
    manager = ContextManager(store=InMemorySessionStore())
    session = manager.get_or_create("session-2", "wechat-openid-2")
    session.active_entities["company"].append(
        ResolvedEntity(type="company", id="COMP-1", name="优必选", confidence=0.95)
    )

    cleared = manager.apply_topic_switch(session)
    assert cleared.active_entities["company"] == []
```

- [ ] **Step 2: Run the context test and verify it fails because the context layer does not exist yet**

Run:

```bash
uv run pytest apps/agentic-rag-service/tests/unit/test_context_manager.py -v -n 0
```

Expected:

```text
FAIL with import errors for `agentic_rag_service.context`.
```

- [ ] **Step 3: Implement the session model, entity stacks, and memory/Redis stores**

```python
# apps/agentic-rag-service/src/agentic_rag_service/context/store.py
from collections import defaultdict
from datetime import UTC, datetime, timedelta


class InMemorySessionStore:
    def __init__(self, ttl_seconds: int = 1800):
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, dict] = {}

    def load(self, session_id: str) -> dict | None:
        item = self._items.get(session_id)
        if not item:
            return None
        if item["expires_at"] < datetime.now(UTC):
            self._items.pop(session_id, None)
            return None
        return item["value"]

    def save(self, session_id: str, payload: dict) -> None:
        self._items[session_id] = {
            "value": payload,
            "expires_at": datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
        }
```

```python
# apps/agentic-rag-service/src/agentic_rag_service/context/manager.py
from copy import deepcopy
from datetime import UTC, datetime

from agentic_rag_service.contracts import QueryAnalysis, ResolvedEntity


ENTITY_TYPES = ("professor", "company", "paper", "patent")


class ContextManager:
    def __init__(self, store):
        self.store = store

    def get_or_create(self, session_id: str, user_id: str) -> dict:
        session = self.store.load(session_id)
        if session:
            return session
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "current_module": None,
            "last_result_set": None,
            "turns": [],
            "active_entities": {entity_type: [] for entity_type in ENTITY_TYPES},
            "last_active_at": datetime.now(UTC).isoformat(),
        }
        self.store.save(session_id, session)
        return session

    def record_turn(self, session: dict, *, user_input: str, analysis: QueryAnalysis, result_summary: str) -> dict:
        updated = deepcopy(session)
        for entity in analysis.explicit_entities + analysis.coreferences:
            bucket = updated["active_entities"][entity.type]
            bucket.insert(0, entity.model_dump())
            del bucket[3:]
        updated["current_module"] = analysis.target_modules[0] if analysis.target_modules else None
        updated["turns"].append(
            {
                "user_input": user_input,
                "intent_type": analysis.intent_type,
                "target_modules": analysis.target_modules,
                "result_summary": result_summary,
            }
        )
        updated["turns"] = updated["turns"][-10:]
        updated["last_active_at"] = datetime.now(UTC).isoformat()
        self.store.save(updated["session_id"], updated)
        return updated

    def resolve_reference(self, session: dict, mention: str, entity_type: str):
        candidates = session["active_entities"].get(entity_type, [])
        if mention in {"他", "她", "他的", "她的", "这家公司", "这篇论文", "这个专利"} and candidates:
            return ResolvedEntity.model_validate(candidates[0])
        return None

    def apply_topic_switch(self, session: dict) -> dict:
        updated = deepcopy(session)
        updated["active_entities"] = {entity_type: [] for entity_type in ENTITY_TYPES}
        self.store.save(updated["session_id"], updated)
        return updated
```

- [ ] **Step 4: Run the context tests and confirm the core behaviors pass**

Run:

```bash
uv run pytest apps/agentic-rag-service/tests/unit/test_context_manager.py -v -n 0
```

Expected:

```text
PASS for pronoun resolution, stack truncation, and topic-switch reset behavior.
```

- [ ] **Step 5: Commit the context manager**

```bash
git add apps/agentic-rag-service/pyproject.toml \
  apps/agentic-rag-service/src/agentic_rag_service/context \
  apps/agentic-rag-service/tests/unit/test_context_manager.py
git commit -m "feat: add multi-turn context manager"
```

### Task 3: Build Query Analysis And Route Planning For Types A Through G

**Files:**
- Create: `apps/agentic-rag-service/src/agentic_rag_service/routing/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/routing/analyzer.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/routing/planner.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/routing/prompts.py`
- Create: `apps/agentic-rag-service/tests/unit/test_query_analyzer.py`
- Create: `apps/agentic-rag-service/tests/unit/test_route_planner.py`

- [ ] **Step 1: Write failing tests for intent classification, ambiguity handling, and route strategy selection**

```python
# apps/agentic-rag-service/tests/unit/test_route_planner.py
from agentic_rag_service.contracts import QueryAnalysis, ResolvedEntity
from agentic_rag_service.routing.planner import RoutePlanner


def test_route_planner_maps_cross_domain_follow_up_to_jump_strategy():
    analysis = QueryAnalysis(
        intent_type="C",
        target_modules=["company"],
        explicit_entities=[],
        coreferences=[ResolvedEntity(type="professor", id="PROF-1", name="丁文伯", confidence=0.96)],
    )
    plan = RoutePlanner().build("他参与创立了哪些企业", analysis)
    assert plan.strategy == "cross_domain_jump"
    assert plan.modules == ["company"]


def test_route_planner_uses_reject_strategy_for_out_of_scope_query():
    analysis = QueryAnalysis(
        intent_type="F",
        target_modules=[],
        explicit_entities=[],
        coreferences=[],
    )
    plan = RoutePlanner().build("今天天气怎么样", analysis)
    assert plan.strategy == "reject"
```

```python
# apps/agentic-rag-service/tests/unit/test_query_analyzer.py
import pytest

from agentic_rag_service.contracts import QueryAnalysis
from agentic_rag_service.routing.analyzer import QueryAnalyzer


@pytest.mark.asyncio
async def test_query_analyzer_returns_typed_analysis():
    class FakeRunner:
        async def run(self, **_kwargs):
            return QueryAnalysis(
                intent_type="D",
                target_modules=["professor", "company"],
                explicit_entities=[],
                coreferences=[],
            )

    analyzer = QueryAnalyzer(runner=FakeRunner())
    result = await analyzer.analyze(
        user_input="深圳做具身智能的教授和企业有哪些",
        session_context={"turns": [], "active_entities": {"professor": [], "company": [], "paper": [], "patent": []}},
    )
    assert result.intent_type == "D"
    assert result.target_modules == ["professor", "company"]
```

- [ ] **Step 2: Run the routing tests to verify failure before the routing layer exists**

Run:

```bash
uv run pytest apps/agentic-rag-service/tests/unit/test_query_analyzer.py apps/agentic-rag-service/tests/unit/test_route_planner.py -v -n 0
```

Expected:

```text
FAIL because the routing package and planner are not implemented yet.
```

- [ ] **Step 3: Implement the analysis prompt contract and route planner**

```python
# apps/agentic-rag-service/src/agentic_rag_service/routing/prompts.py
ANALYSIS_PROMPT = """
你是深圳科创检索助手的查询分析器。
请结合用户输入、最近 5 轮摘要和当前实体栈，输出一个 JSON 对象：
{
  "intent_type": "A|B|C|D|E|F|G",
  "target_modules": ["professor" | "company" | "paper" | "patent"],
  "is_topic_switch": false,
  "additional_filters": {},
  "explicit_entities": [],
  "coreferences": []
}

规则：
1. 类型 F 只用于明显超出科创范围的问题。
2. 类型 G 默认先选择最高置信候选；只有没有明显优先候选时才要求澄清。
3. 类型 E 允许本地库线索 + Web Search。
4. 不确定时保持保守，不要猜测低置信实体。
""".strip()
```

```python
# apps/agentic-rag-service/src/agentic_rag_service/routing/analyzer.py
from agentic_rag_service.contracts import QueryAnalysis
from agentic_rag_service.routing.prompts import ANALYSIS_PROMPT


class QueryAnalyzer:
    def __init__(self, runner):
        self.runner = runner

    async def analyze(self, *, user_input: str, session_context: dict) -> QueryAnalysis:
        task_description = (
            f"{ANALYSIS_PROMPT}\n\n"
            f"最近对话摘要: {session_context.get('turns', [])}\n"
            f"当前实体栈: {session_context.get('active_entities', {})}\n"
            f"用户输入: {user_input}"
        )
        return await self.runner.run(
            schema_model=QueryAnalysis,
            task_description=task_description,
        )
```

```python
# apps/agentic-rag-service/src/agentic_rag_service/routing/planner.py
from agentic_rag_service.contracts import QueryAnalysis, RoutePlan


class RoutePlanner:
    def build(self, user_input: str, analysis: QueryAnalysis) -> RoutePlan:
        if analysis.intent_type == "F":
            return RoutePlan(strategy="reject", modules=[], query_text=user_input)
        if analysis.intent_type == "G" and not analysis.target_modules:
            return RoutePlan(
                strategy="clarify",
                modules=[],
                query_text=user_input,
                clarification_question="请补充更具体的学校、公司名称或地区，我再切换到正确对象。",
            )
        if analysis.intent_type == "C":
            return RoutePlan(strategy="cross_domain_jump", modules=analysis.target_modules, query_text=user_input)
        if analysis.intent_type == "D":
            return RoutePlan(strategy="aggregate", modules=analysis.target_modules, query_text=user_input)
        if analysis.intent_type == "E":
            return RoutePlan(
                strategy="knowledge",
                modules=analysis.target_modules,
                query_text=user_input,
                needs_web_search=True,
                source_note="综合自网络搜索和 AI 分析",
            )
        if analysis.intent_type == "B":
            return RoutePlan(strategy="single_domain_follow_up", modules=analysis.target_modules, query_text=user_input)
        return RoutePlan(strategy="single_domain", modules=analysis.target_modules, query_text=user_input)
```

- [ ] **Step 4: Run the routing tests and confirm A/B/C/D/E/F/G behaviors are represented**

Run:

```bash
uv run pytest apps/agentic-rag-service/tests/unit/test_query_analyzer.py apps/agentic-rag-service/tests/unit/test_route_planner.py -v -n 0
```

Expected:

```text
PASS for typed analysis output and PASS for route strategy selection.
```

- [ ] **Step 5: Commit the routing layer**

```bash
git add apps/agentic-rag-service/src/agentic_rag_service/routing \
  apps/agentic-rag-service/tests/unit/test_query_analyzer.py \
  apps/agentic-rag-service/tests/unit/test_route_planner.py
git commit -m "feat: add agentic rag query analysis and routing"
```

### Task 4: Implement Retrieval Orchestration And Source-Aware Answer Assembly

**Files:**
- Create: `apps/agentic-rag-service/src/agentic_rag_service/retrieval/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/retrieval/jsonl_repository.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/retrieval/web_search.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/service/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/service/answer_builder.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/service/progress.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/service/query_service.py`
- Create: `apps/agentic-rag-service/tests/fixtures/companies.jsonl`
- Create: `apps/agentic-rag-service/tests/fixtures/papers.jsonl`
- Create: `apps/agentic-rag-service/tests/fixtures/patents.jsonl`
- Create: `apps/agentic-rag-service/tests/fixtures/professors.jsonl`
- Create: `apps/agentic-rag-service/tests/unit/test_query_service.py`
- Create: `apps/agentic-rag-service/tests/unit/test_source_policy.py`

- [ ] **Step 1: Write failing tests for local retrieval, cross-domain jumps, and source-display policy**

```python
# apps/agentic-rag-service/tests/unit/test_source_policy.py
from agentic_rag_service.contracts import RoutePlan
from agentic_rag_service.service.answer_builder import AnswerBuilder


def test_answer_builder_hides_source_banner_for_local_high_confidence_hits():
    builder = AnswerBuilder()
    answer = builder.build(
        route_plan=RoutePlan(strategy="single_domain", modules=["company"], query_text="介绍优必选"),
        result_sets={"company": [{"display_name": "优必选", "summary_fields": {"profile_summary": "做人形机器人"}}]},
        used_web_search=False,
    )
    assert answer["source_note"] is None


def test_answer_builder_marks_web_backed_knowledge_answers():
    builder = AnswerBuilder()
    answer = builder.build(
        route_plan=RoutePlan(strategy="knowledge", modules=["company"], query_text="合成数据路线有哪些", needs_web_search=True),
        result_sets={"company": []},
        used_web_search=True,
    )
    assert answer["source_note"] == "综合自网络搜索和 AI 分析，非本地数据库直接结果。"
```

```python
# apps/agentic-rag-service/tests/unit/test_query_service.py
import pytest

from agentic_rag_service.contracts import QueryAnalysis, RoutePlan
from agentic_rag_service.service.query_service import QueryService


@pytest.mark.asyncio
async def test_query_service_executes_cross_domain_jump():
    class FakeAnalyzer:
        async def analyze(self, **_kwargs):
            return QueryAnalysis(
                intent_type="C",
                target_modules=["paper"],
                explicit_entities=[],
                coreferences=[],
            )

    class FakePlanner:
        def build(self, user_input, analysis):
            return RoutePlan(strategy="cross_domain_jump", modules=["paper"], query_text=user_input)

    class FakeRepository:
        async def search(self, module, query_text, filters):
            return [{"display_name": "A Policy-Guided Diffusion Method", "summary_fields": {"summary_zh": "论文摘要"}}]

    service = QueryService(
        analyzer=FakeAnalyzer(),
        planner=FakePlanner(),
        repository=FakeRepository(),
        answer_builder=lambda **kwargs: {"cards": kwargs["result_sets"]["paper"]},
        context_manager=None,
        web_search_client=None,
        metrics_store=None,
    )

    result = await service.handle(session_id="s1", user_id="u1", user_input="看看他的论文")
    assert result["cards"][0]["display_name"] == "A Policy-Guided Diffusion Method"
```

- [ ] **Step 2: Run the retrieval/service tests and verify failure before the service layer exists**

Run:

```bash
uv run pytest apps/agentic-rag-service/tests/unit/test_query_service.py apps/agentic-rag-service/tests/unit/test_source_policy.py -v -n 0
```

Expected:

```text
FAIL because the retrieval repository, answer builder, and query service are missing.
```

- [ ] **Step 3: Implement JSONL-backed domain retrieval, optional web search, and answer assembly**

```python
# apps/agentic-rag-service/src/agentic_rag_service/retrieval/jsonl_repository.py
import json
from pathlib import Path


class JsonlDomainRepository:
    def __init__(self, export_paths: dict[str, Path]):
        self.export_paths = export_paths

    async def search(self, module: str, query_text: str, filters: dict) -> list[dict]:
        path = self.export_paths[module]
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        terms = [part for part in query_text.lower().split() if part]
        scored = []
        for record in records:
            haystack = json.dumps(record, ensure_ascii=False).lower()
            score = sum(term in haystack for term in terms)
            if score:
                scored.append((score, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [record for _score, record in scored[:5]]
```

```python
# apps/agentic-rag-service/src/agentic_rag_service/service/answer_builder.py
class AnswerBuilder:
    def build(self, *, route_plan, result_sets: dict[str, list[dict]], used_web_search: bool) -> dict:
        source_note = None
        if used_web_search:
            source_note = "综合自网络搜索和 AI 分析，非本地数据库直接结果。"
        cards = []
        for module, hits in result_sets.items():
            for hit in hits:
                cards.append(
                    {
                        "module": module,
                        "title": hit.get("display_name"),
                        "summary": hit.get("summary_fields", {}).get("profile_summary")
                        or hit.get("summary_fields", {}).get("summary_zh")
                        or hit.get("summary_fields", {}).get("summary_text"),
                    }
                )
        return {"source_note": source_note, "cards": cards}
```

```python
# apps/agentic-rag-service/src/agentic_rag_service/service/query_service.py
class QueryService:
    def __init__(self, *, analyzer, planner, repository, answer_builder, context_manager, web_search_client, metrics_store):
        self.analyzer = analyzer
        self.planner = planner
        self.repository = repository
        self.answer_builder = answer_builder
        self.context_manager = context_manager
        self.web_search_client = web_search_client
        self.metrics_store = metrics_store

    async def handle(self, *, session_id: str, user_id: str, user_input: str) -> dict:
        session = self.context_manager.get_or_create(session_id, user_id) if self.context_manager else {"turns": [], "active_entities": {}}
        analysis = await self.analyzer.analyze(user_input=user_input, session_context=session)
        plan = self.planner.build(user_input, analysis)
        result_sets: dict[str, list[dict]] = {}
        for module in plan.modules:
            result_sets[module] = await self.repository.search(module, user_input, analysis.additional_filters)
        used_web_search = bool(plan.needs_web_search and self.web_search_client)
        answer = self.answer_builder.build(route_plan=plan, result_sets=result_sets, used_web_search=used_web_search)
        if self.context_manager:
            self.context_manager.record_turn(session, user_input=user_input, analysis=analysis, result_summary=str(answer["cards"][:2]))
        if self.metrics_store:
            self.metrics_store.record_query(intent_type=analysis.intent_type, modules=plan.modules)
        return answer
```

- [ ] **Step 4: Run the retrieval and source-policy tests**

Run:

```bash
uv run pytest apps/agentic-rag-service/tests/unit/test_query_service.py apps/agentic-rag-service/tests/unit/test_source_policy.py -v -n 0
```

Expected:

```text
PASS for query orchestration and PASS for conditional source-display policy.
```

- [ ] **Step 5: Commit the retrieval and answer layer**

```bash
git add apps/agentic-rag-service/src/agentic_rag_service/retrieval \
  apps/agentic-rag-service/src/agentic_rag_service/service \
  apps/agentic-rag-service/tests/fixtures \
  apps/agentic-rag-service/tests/unit/test_query_service.py \
  apps/agentic-rag-service/tests/unit/test_source_policy.py
git commit -m "feat: add agentic rag retrieval orchestration"
```

### Task 5: Deliver The Flask Chat API And Mobile H5 Shell

**Files:**
- Create: `apps/agentic-rag-service/README.md`
- Create: `apps/agentic-rag-service/main.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/app.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/api/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/api/chat.py`
- Modify: `apps/agentic-rag-service/src/agentic_rag_service/service/query_service.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/service/progress.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/web/templates/chat.html`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/web/static/css/chat.css`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/web/static/js/chat.js`
- Create: `apps/agentic-rag-service/tests/conftest.py`
- Create: `apps/agentic-rag-service/tests/integration/test_chat_api.py`

- [ ] **Step 1: Write failing integration tests for the chat API, SSE progress events, and mobile shell**

```python
# apps/agentic-rag-service/tests/integration/test_chat_api.py
def test_chat_page_contains_mobile_viewport(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'name="viewport"' in html
    assert "chat-shell" in html


def test_chat_api_returns_cards_and_source_note(client):
    response = client.post(
        "/api/chat",
        json={"session_id": "session-1", "user_id": "user-1", "message": "介绍优必选"},
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert "cards" in payload


def test_chat_stream_emits_progress_then_final(client):
    response = client.post(
        "/api/chat/stream",
        json={"session_id": "session-2", "user_id": "user-2", "message": "深圳做具身智能的教授和企业有哪些"},
        buffered=True,
    )
    body = response.get_data(as_text=True)
    assert "event: progress" in body
    assert "event: final" in body
```

- [ ] **Step 2: Run the integration tests and verify failure before the Flask app exists**

Run:

```bash
uv run pytest apps/agentic-rag-service/tests/integration/test_chat_api.py -v -n 0
```

Expected:

```text
FAIL because no Flask application factory or chat routes exist yet.
```

- [ ] **Step 3: Implement the Flask app factory, chat routes, progress events, and H5 frontend**

```python
# apps/agentic-rag-service/src/agentic_rag_service/app.py
from flask import Flask

from agentic_rag_service.api.chat import chat_bp


def create_app(query_service) -> Flask:
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.config["query_service"] = query_service
    app.register_blueprint(chat_bp)
    return app
```

```python
# apps/agentic-rag-service/src/agentic_rag_service/api/chat.py
import asyncio
import json

from flask import Blueprint, Response, current_app, jsonify, render_template, request

chat_bp = Blueprint("chat", __name__)


@chat_bp.get("/")
def index():
    return render_template("chat.html")


@chat_bp.post("/api/chat")
def chat():
    payload = request.get_json()
    result = asyncio.run(
        current_app.config["query_service"].handle(
            session_id=payload["session_id"],
            user_id=payload["user_id"],
            user_input=payload["message"],
        )
    )
    return jsonify(result)


@chat_bp.post("/api/chat/stream")
def chat_stream():
    payload = request.get_json()

    def generate():
        yield "event: progress\ndata: 正在分析查询意图...\n\n"
        result = asyncio.run(
            current_app.config["query_service"].handle(
                session_id=payload["session_id"],
                user_id=payload["user_id"],
                user_input=payload["message"],
            )
        )
        yield f"event: final\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream")
```

```html
<!-- apps/agentic-rag-service/src/agentic_rag_service/web/templates/chat.html -->
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <title>深圳科创智能检索</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/chat.css') }}">
  </head>
  <body class="chat-shell">
    <main class="chat-layout">
      <header class="hero">
        <p class="eyebrow">Shenzhen Sci-Tech Navigator</p>
        <h1>一句话进入教授、企业、论文、专利四库</h1>
      </header>
      <section id="chat-log" class="chat-log"></section>
      <form id="chat-form" class="composer">
        <textarea id="message" rows="3" placeholder="例如：深圳做具身智能的教授和企业有哪些"></textarea>
        <button type="submit">发送</button>
      </form>
    </main>
    <script src="{{ url_for('static', filename='js/chat.js') }}"></script>
  </body>
</html>
```

```css
/* apps/agentic-rag-service/src/agentic_rag_service/web/static/css/chat.css */
:root {
  --ink: #102a43;
  --sand: #f5efe6;
  --card: rgba(255, 255, 255, 0.86);
  --teal: #0f766e;
  --amber: #f59e0b;
}

body.chat-shell {
  margin: 0;
  min-height: 100vh;
  color: var(--ink);
  background:
    radial-gradient(circle at top right, rgba(245, 158, 11, 0.18), transparent 28%),
    linear-gradient(180deg, #fcfaf5 0%, #efe4d2 100%);
}

.chat-layout {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px 40px;
}

@media (max-width: 428px) {
  .chat-layout {
    padding: 18px 14px 32px;
  }
}
```

- [ ] **Step 4: Run the chat API integration tests**

Run:

```bash
uv run pytest apps/agentic-rag-service/tests/integration/test_chat_api.py -v -n 0
```

Expected:

```text
PASS for the page shell, PASS for `/api/chat`, and PASS for SSE progress/final events.
```

- [ ] **Step 5: Commit the chat API and H5 shell**

```bash
git add apps/agentic-rag-service/README.md \
  apps/agentic-rag-service/main.py \
  apps/agentic-rag-service/src/agentic_rag_service/app.py \
  apps/agentic-rag-service/src/agentic_rag_service/api \
  apps/agentic-rag-service/src/agentic_rag_service/service/progress.py \
  apps/agentic-rag-service/src/agentic_rag_service/web \
  apps/agentic-rag-service/tests/conftest.py \
  apps/agentic-rag-service/tests/integration/test_chat_api.py
git commit -m "feat: add agentic rag chat api and h5 shell"
```

### Task 6: Add Admin Dashboard, Feedback Intake, And Import Job Tracking

**Files:**
- Create: `apps/agentic-rag-service/src/agentic_rag_service/admin/__init__.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/admin/store.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/api/admin.py`
- Modify: `apps/agentic-rag-service/src/agentic_rag_service/app.py`
- Modify: `apps/agentic-rag-service/src/agentic_rag_service/service/query_service.py`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/web/templates/admin.html`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/web/static/css/admin.css`
- Create: `apps/agentic-rag-service/src/agentic_rag_service/web/static/js/admin.js`
- Create: `apps/agentic-rag-service/tests/integration/test_admin_api.py`

- [ ] **Step 1: Write failing tests for dashboard metrics, feedback issue creation, and import job registration**

```python
# apps/agentic-rag-service/tests/integration/test_admin_api.py
def test_dashboard_requires_admin_token(client):
    response = client.get("/api/admin/dashboard")
    assert response.status_code == 401


def test_feedback_creates_issue_record(client):
    response = client.post(
        "/api/feedback",
        json={
            "session_id": "session-1",
            "user_id": "user-1",
            "message": "优必选有哪些专利",
            "issue_type": "user_feedback",
            "details": "回答里没给出专利号",
        },
    )
    payload = response.get_json()
    assert response.status_code == 201
    assert payload["issue"]["status"] == "pending"


def test_admin_dashboard_returns_query_counts(client, admin_headers):
    response = client.get("/api/admin/dashboard", headers=admin_headers)
    payload = response.get_json()
    assert response.status_code == 200
    assert "summary" in payload
```

- [ ] **Step 2: Run the admin tests and confirm they fail before the admin layer exists**

Run:

```bash
uv run pytest apps/agentic-rag-service/tests/integration/test_admin_api.py -v -n 0
```

Expected:

```text
FAIL because admin routes, persistence, and feedback endpoints are not implemented.
```

- [ ] **Step 3: Implement sqlite-backed admin storage and protected admin routes**

```python
# apps/agentic-rag-service/src/agentic_rag_service/admin/store.py
import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS query_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  intent_type TEXT NOT NULL,
  modules_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS issue_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  issue_type TEXT NOT NULL,
  details TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS import_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  module_name TEXT NOT NULL,
  filename TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


class AdminStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
```

```python
# apps/agentic-rag-service/src/agentic_rag_service/api/admin.py
from flask import Blueprint, current_app, jsonify, request

admin_bp = Blueprint("admin", __name__)


def _require_admin():
    expected = current_app.config["admin_token"]
    if request.headers.get("X-Admin-Token") != expected:
        return jsonify({"error": "unauthorized"}), 401
    return None


@admin_bp.get("/api/admin/dashboard")
def dashboard():
    unauthorized = _require_admin()
    if unauthorized:
        return unauthorized
    summary = current_app.config["admin_store"].dashboard_summary()
    return jsonify({"summary": summary})


@admin_bp.post("/api/feedback")
def feedback():
    payload = request.get_json()
    issue = current_app.config["admin_store"].create_issue(
        session_id=payload["session_id"],
        user_id=payload["user_id"],
        issue_type=payload["issue_type"],
        details=payload["details"],
    )
    return jsonify({"issue": issue}), 201
```

- [ ] **Step 4: Run the admin integration tests**

Run:

```bash
uv run pytest apps/agentic-rag-service/tests/integration/test_admin_api.py -v -n 0
```

Expected:

```text
PASS for admin auth, PASS for feedback issue creation, and PASS for dashboard responses.
```

- [ ] **Step 5: Commit the admin tooling**

```bash
git add apps/agentic-rag-service/src/agentic_rag_service/admin \
  apps/agentic-rag-service/src/agentic_rag_service/api/admin.py \
  apps/agentic-rag-service/src/agentic_rag_service/web/templates/admin.html \
  apps/agentic-rag-service/src/agentic_rag_service/web/static/css/admin.css \
  apps/agentic-rag-service/src/agentic_rag_service/web/static/js/admin.js \
  apps/agentic-rag-service/tests/integration/test_admin_api.py
git commit -m "feat: add agentic rag admin dashboard"
```

### Task 7: Validate End-To-End PRD Scenarios And Streaming SLA

**Files:**
- Modify: `apps/agentic-rag-service/README.md`
- Create: `apps/agentic-rag-service/tests/fixtures/scenarios.json`
- Create: `apps/agentic-rag-service/tests/e2e/test_agentic_rag_scenarios.py`
- Create: `apps/agentic-rag-service/tests/e2e/test_streaming_sla.py`

- [ ] **Step 1: Write failing end-to-end tests for representative PRD scenarios**

```python
# apps/agentic-rag-service/tests/e2e/test_agentic_rag_scenarios.py
import json
from pathlib import Path

import pytest


SCENARIOS = json.loads(
    Path("apps/agentic-rag-service/tests/fixtures/scenarios.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_prd_scenarios(client, scenario):
    response = client.post(
        "/api/chat",
        json={
            "session_id": scenario["session_id"],
            "user_id": "user-e2e",
            "message": scenario["message"],
        },
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["cards"]
```

```python
# apps/agentic-rag-service/tests/e2e/test_streaming_sla.py
import time


def test_streaming_endpoint_emits_progress_quickly(client):
    started = time.perf_counter()
    response = client.post(
        "/api/chat/stream",
        json={"session_id": "sla-1", "user_id": "user-sla", "message": "深圳做具身智能的教授和企业有哪些"},
        buffered=True,
    )
    body = response.get_data(as_text=True)
    elapsed = time.perf_counter() - started
    assert "event: progress" in body
    assert elapsed < 1.0
```

- [ ] **Step 2: Run the end-to-end tests and verify failure before scenario fixtures and SLA hooks exist**

Run:

```bash
uv run pytest apps/agentic-rag-service/tests/e2e/test_agentic_rag_scenarios.py apps/agentic-rag-service/tests/e2e/test_streaming_sla.py -v -n 0
```

Expected:

```text
FAIL because the scenario fixture file and final E2E wiring are not in place yet.
```

- [ ] **Step 3: Add scenario fixtures, finish README instructions, and wire the remaining E2E expectations**

```json
// apps/agentic-rag-service/tests/fixtures/scenarios.json
[
  {
    "session_id": "scenario-a",
    "message": "介绍清华的丁文伯"
  },
  {
    "session_id": "scenario-b",
    "message": "深圳做具身智能的教授和企业有哪些"
  },
  {
    "session_id": "scenario-c",
    "message": "在具身智能的合成数据发展方向上，有几种实现方法，代表厂商有哪些"
  }
]
```

```markdown
<!-- apps/agentic-rag-service/README.md -->
# Agentic RAG Service

## Run locally

```bash
uv sync
uv run python apps/agentic-rag-service/main.py
```

## Test

```bash
uv run pytest apps/agentic-rag-service/tests/unit -v -n 0
uv run pytest apps/agentic-rag-service/tests/integration -v -n 0
uv run pytest apps/agentic-rag-service/tests/e2e -v -n 0
```
```

- [ ] **Step 4: Run the full service test matrix**

Run:

```bash
uv run pytest apps/agentic-rag-service/tests/unit -v -n 0
uv run pytest apps/agentic-rag-service/tests/integration -v -n 0
uv run pytest apps/agentic-rag-service/tests/e2e -v -n 0
```

Expected:

```text
PASS for unit, integration, and E2E scenario coverage.
```

- [ ] **Step 5: Commit the validation layer**

```bash
git add apps/agentic-rag-service/README.md \
  apps/agentic-rag-service/tests/fixtures/scenarios.json \
  apps/agentic-rag-service/tests/e2e/test_agentic_rag_scenarios.py \
  apps/agentic-rag-service/tests/e2e/test_streaming_sla.py
git commit -m "test: add agentic rag end-to-end coverage"
```
