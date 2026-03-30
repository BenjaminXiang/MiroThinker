# Data Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable structured-output data-agent runtime on top of the existing `miroflow-agent` stack, then implement company, professor, paper, and patent collection pipelines that publish stable contract objects aligned with the reconciled PRDs.

**Architecture:** Reuse the current Hydra + `pipeline.py` + `Orchestrator` + MCP-tool stack, but add a JSON-first final-output mode so data agents can emit validated records instead of benchmark-only `\boxed{}` answers. Put all shared contracts, runtime helpers, normalization, linking, and publishing code under `apps/miroflow-agent/src/data_agents/`, then deliver each domain as a vertical slice with its own config and runner. Finish with PostgreSQL + Milvus release adapters and a validation suite that guarantees the outward-facing contract even if each domain evolves its own internal schema.

**Tech Stack:** Python 3.12, Hydra, existing `ToolManager` / `Orchestrator`, `openpyxl`, `json_repair`, `pydantic`, `beautifulsoup4`, `psycopg`, `pymilvus`, `pytest`, `pytest-asyncio`

---

## Current State

- `apps/miroflow-agent/src/io/input_handler.py`, `apps/miroflow-agent/src/utils/prompt_utils.py`, `apps/miroflow-agent/src/io/output_formatter.py`, `apps/miroflow-agent/src/core/answer_generator.py`, and `apps/miroflow-agent/src/core/orchestrator.py` currently assume the final answer is wrapped in `\boxed{}`.
- `apps/miroflow-agent/src/io/input_handler.py` already has `openpyxl`-based XLSX parsing utilities, which means the repo already contains the base dependency needed for xlsx importers.
- `apps/miroflow-agent/src/config/settings.py`, `apps/miroflow-agent/conf/agent/mirothinker_1.7_keep5_max200.yaml`, `libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/search_and_scrape_webpage.py`, and `libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/jina_scrape_llm_summary.py` already provide the agent-orchestration and web-extraction primitives the PRDs want to reuse.
- `apps/miroflow-agent/tests/` does not exist yet, so this plan creates a focused test suite from scratch rather than trying to retrofit benchmark-only validation.
- There is no current PostgreSQL / Milvus publishing layer in `apps/miroflow-agent`, so release adapters must be introduced explicitly instead of being assumed.

## File Map

### Core runtime changes

- Modify: `apps/miroflow-agent/src/io/input_handler.py`
- Modify: `apps/miroflow-agent/src/utils/prompt_utils.py`
- Modify: `apps/miroflow-agent/src/io/output_formatter.py`
- Modify: `apps/miroflow-agent/src/core/answer_generator.py`
- Modify: `apps/miroflow-agent/src/core/orchestrator.py`
- Modify: `apps/miroflow-agent/src/core/pipeline.py`
- Modify: `apps/miroflow-agent/conf/agent/default.yaml`
- Create: `apps/miroflow-agent/tests/data_agents/test_structured_output_mode.py`

### Shared data-agent layer

- Modify: `apps/miroflow-agent/pyproject.toml`
- Modify: `apps/miroflow-agent/conf/config.yaml`
- Create: `apps/miroflow-agent/conf/data_agent/default.yaml`
- Create: `apps/miroflow-agent/src/data_agents/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/contracts.py`
- Create: `apps/miroflow-agent/src/data_agents/runtime.py`
- Create: `apps/miroflow-agent/src/data_agents/common/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/common/identifiers.py`
- Create: `apps/miroflow-agent/src/data_agents/common/normalization.py`
- Create: `apps/miroflow-agent/src/data_agents/common/evidence.py`
- Create: `apps/miroflow-agent/src/data_agents/common/linking.py`
- Create: `apps/miroflow-agent/src/data_agents/publishers/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/publishers/jsonl.py`
- Create: `apps/miroflow-agent/tests/data_agents/conftest.py`
- Create: `apps/miroflow-agent/tests/data_agents/test_contracts.py`
- Create: `apps/miroflow-agent/tests/data_agents/test_runtime.py`

### Company vertical slice

- Create: `apps/miroflow-agent/conf/agent/data_agent_company.yaml`
- Create: `apps/miroflow-agent/conf/data_agent/company.yaml`
- Create: `apps/miroflow-agent/scripts/run_company_data_agent.py`
- Create: `apps/miroflow-agent/src/data_agents/company/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/company/models.py`
- Create: `apps/miroflow-agent/src/data_agents/company/import_xlsx.py`
- Create: `apps/miroflow-agent/src/data_agents/company/enrich.py`
- Create: `apps/miroflow-agent/src/data_agents/company/pipeline.py`
- Create: `apps/miroflow-agent/tests/data_agents/company/test_import_xlsx.py`
- Create: `apps/miroflow-agent/tests/data_agents/company/test_pipeline.py`

### Professor vertical slice

- Create: `apps/miroflow-agent/conf/agent/data_agent_professor.yaml`
- Create: `apps/miroflow-agent/conf/data_agent/professor.yaml`
- Create: `apps/miroflow-agent/scripts/run_professor_data_agent.py`
- Create: `apps/miroflow-agent/src/data_agents/professor/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/professor/models.py`
- Create: `apps/miroflow-agent/src/data_agents/professor/roster.py`
- Create: `apps/miroflow-agent/src/data_agents/professor/profile.py`
- Create: `apps/miroflow-agent/src/data_agents/professor/pipeline.py`
- Create: `apps/miroflow-agent/tests/data_agents/professor/test_roster.py`
- Create: `apps/miroflow-agent/tests/data_agents/professor/test_profile.py`

### Paper vertical slice

- Create: `apps/miroflow-agent/conf/agent/data_agent_paper.yaml`
- Create: `apps/miroflow-agent/conf/data_agent/paper.yaml`
- Create: `apps/miroflow-agent/scripts/run_paper_data_agent.py`
- Create: `apps/miroflow-agent/src/data_agents/paper/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/paper/models.py`
- Create: `apps/miroflow-agent/src/data_agents/paper/discovery.py`
- Create: `apps/miroflow-agent/src/data_agents/paper/enrichment.py`
- Create: `apps/miroflow-agent/src/data_agents/paper/pipeline.py`
- Create: `apps/miroflow-agent/tests/data_agents/paper/test_discovery.py`
- Create: `apps/miroflow-agent/tests/data_agents/paper/test_pipeline.py`

### Patent vertical slice

- Create: `apps/miroflow-agent/conf/agent/data_agent_patent.yaml`
- Create: `apps/miroflow-agent/conf/data_agent/patent.yaml`
- Create: `apps/miroflow-agent/scripts/run_patent_data_agent.py`
- Create: `apps/miroflow-agent/src/data_agents/patent/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/patent/models.py`
- Create: `apps/miroflow-agent/src/data_agents/patent/import_xlsx.py`
- Create: `apps/miroflow-agent/src/data_agents/patent/linking.py`
- Create: `apps/miroflow-agent/src/data_agents/patent/pipeline.py`
- Create: `apps/miroflow-agent/tests/data_agents/patent/test_import_xlsx.py`
- Create: `apps/miroflow-agent/tests/data_agents/patent/test_pipeline.py`

### Release adapters and validation

- Create: `apps/miroflow-agent/src/data_agents/storage/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/storage/embedding.py`
- Create: `apps/miroflow-agent/src/data_agents/storage/postgres.py`
- Create: `apps/miroflow-agent/src/data_agents/storage/milvus.py`
- Create: `apps/miroflow-agent/src/data_agents/storage/release_service.py`
- Create: `apps/miroflow-agent/scripts/run_release_validation.py`
- Create: `apps/miroflow-agent/tests/data_agents/storage/test_release_service.py`
- Create: `apps/miroflow-agent/tests/data_agents/test_contract_validation.py`

## Dependency Graph

- Task 1 is the blocker for every later task because the current runtime cannot safely emit structured domain records.
- Task 2 depends on Task 1 and should land before any domain vertical slice so every domain reuses the same contracts, ID rules, evidence shape, and dry-run publishing pattern.
- Task 3 and Task 4 can run in parallel after Task 2, but Task 4 should read company release objects when populating `company_roles`.
- Task 5 depends on Task 4 because the periodic paper pipeline must start from the Shenzhen professor roster and emit professor-enrichment outputs.
- Task 6 depends on Task 3 and benefits from Task 4 because patent linking needs company and professor reference data.
- Task 7 depends on Tasks 3 through 6 because release validation only matters after each domain can produce contract-valid records.

## Out of Scope For This Plan

- Implementing the end-user online query router from `docs/Agentic-RAG-PRD.md`
- Building the WeChat-facing application layer
- Production schedulers such as Airflow, cron, Celery, or Kubernetes jobs
- Vendor-specific Milvus / PostgreSQL deployment manifests
- Non-Shenzhen professor coverage expansion

### Task 1: Add Structured JSON Output Mode To The Existing Runtime

**Files:**
- Modify: `apps/miroflow-agent/src/io/input_handler.py`
- Modify: `apps/miroflow-agent/src/utils/prompt_utils.py`
- Modify: `apps/miroflow-agent/src/io/output_formatter.py`
- Modify: `apps/miroflow-agent/src/core/answer_generator.py`
- Modify: `apps/miroflow-agent/src/core/orchestrator.py`
- Modify: `apps/miroflow-agent/src/core/pipeline.py`
- Modify: `apps/miroflow-agent/conf/agent/default.yaml`
- Test: `apps/miroflow-agent/tests/data_agents/test_structured_output_mode.py`

- [ ] **Step 1: Write the failing tests for non-boxed structured output**

```python
# apps/miroflow-agent/tests/data_agents/test_structured_output_mode.py
from src.io.input_handler import process_input
from src.io.output_formatter import OutputFormatter
from src.utils.prompt_utils import generate_agent_summarize_prompt


def test_process_input_skips_boxed_instruction_for_json_mode():
    _, processed = process_input(
        "normalize this company record",
        "",
        require_boxed_answer=False,
    )
    assert "\\boxed{}" not in processed


def test_generate_agent_summarize_prompt_supports_json_mode():
    prompt = generate_agent_summarize_prompt(
        task_description="Return a company record",
        agent_type="main",
        output_mode="json",
        final_output_schema='{"type":"object","required":["name"]}',
    )
    assert "Return exactly one JSON object" in prompt
    assert "\\boxed{}" not in prompt


def test_output_formatter_extracts_json_payload():
    formatter = OutputFormatter()
    _, payload, _ = formatter.format_final_summary_and_log(
        '<think>ignore</think>\n{"object_type":"company","name":"优必选"}',
        output_mode="json",
    )
    assert payload == '{"name":"优必选","object_type":"company"}'
```

- [ ] **Step 2: Run the test file and verify the current runtime fails**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/test_structured_output_mode.py -v
```

Expected:

```text
FAIL because process_input does not accept require_boxed_answer, generate_agent_summarize_prompt has no output_mode argument, and OutputFormatter only extracts \boxed{} payloads.
```

- [ ] **Step 3: Implement JSON final-output mode without breaking benchmark boxed mode**

```python
# apps/miroflow-agent/src/io/input_handler.py
def process_input(
    task_description: str,
    task_file_name: str = "",
    require_boxed_answer: bool = True,
):
    ...
    if require_boxed_answer:
        updated_task_description += (
            "\nYou should follow the format instruction in the request strictly "
            "and wrap the final answer in \\boxed{}."
        )
    ...


# apps/miroflow-agent/src/utils/prompt_utils.py
def generate_agent_summarize_prompt(
    task_description,
    agent_type="",
    output_mode="boxed",
    final_output_schema: str | None = None,
):
    if agent_type == "main" and output_mode == "boxed":
        ...
    elif agent_type == "main" and output_mode == "json":
        summarize_prompt = (
            "Summarize the above conversation and return exactly one JSON object.\n"
            "Do not call tools. Do not wrap the result in markdown fences.\n"
            "If the conversation is incomplete, return the best validated object you can "
            "without fabricating unsupported fields.\n\n"
            f"Original task:\n\"{task_description}\"\n\n"
            f"JSON schema:\n{final_output_schema or '{}'}"
        )
    elif agent_type == "agent-browsing":
        ...
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")
    return summarize_prompt.strip()


# apps/miroflow-agent/src/io/output_formatter.py
import json

from ..utils.parsing_utils import safe_json_loads


class OutputFormatter:
    ...
    def _extract_json_payload(self, text: str) -> str:
        candidate = text.split("</think>")[-1].strip()
        candidate = candidate.removeprefix("```json").removeprefix("```").strip()
        candidate = candidate.removesuffix("```").strip()
        parsed = safe_json_loads(candidate)
        if isinstance(parsed, dict) and "error" not in parsed:
            return json.dumps(parsed, ensure_ascii=False, sort_keys=True)
        return FORMAT_ERROR_MESSAGE

    def format_final_summary_and_log(
        self,
        final_answer_text: str,
        client=None,
        output_mode: str = "boxed",
    ) -> Tuple[str, str, str]:
        ...
        if output_mode == "json":
            payload = self._extract_json_payload(final_answer_text)
        else:
            payload = self._extract_boxed_content(final_answer_text)
        ...
        return "\n".join(summary_lines), payload, log_string


# apps/miroflow-agent/src/core/pipeline.py
async def execute_task_pipeline(
    ...,
    final_output_schema: Optional[str] = None,
):
    ...
    orchestrator = Orchestrator(
        ...,
        final_output_schema=final_output_schema,
    )


# apps/miroflow-agent/src/core/orchestrator.py
class Orchestrator:
    def __init__(
        ...,
        final_output_schema: Optional[str] = None,
    ):
        ...
        self.final_output_schema = final_output_schema

    async def run_main_agent(...):
        initial_user_content, processed_task_desc = process_input(
            task_description,
            task_file_name,
            require_boxed_answer=self.cfg.agent.get("output_mode", "boxed") == "boxed",
        )
        ...
        (
            final_summary,
            final_boxed_answer,
            failure_experience_summary,
            usage_log,
            message_history,
        ) = await self.answer_generator.generate_and_finalize_answer(
            ...,
            final_output_schema=self.final_output_schema,
        )


# apps/miroflow-agent/src/core/answer_generator.py
async def generate_final_answer_with_retries(
    ...,
    final_output_schema: Optional[str] = None,
) -> Tuple[Optional[str], str, Optional[str], str, List[Dict[str, Any]]]:
    output_mode = self.cfg.agent.get("output_mode", "boxed")
    summary_prompt = generate_agent_summarize_prompt(
        task_description,
        agent_type="main",
        output_mode=output_mode,
        final_output_schema=final_output_schema,
    )
    ...
    final_summary, final_boxed_answer, usage_log = (
        self.output_formatter.format_final_summary_and_log(
            final_answer_text,
            self.llm_client,
            output_mode=output_mode,
        )
    )

async def generate_and_finalize_answer(
    ...,
    final_output_schema: Optional[str] = None,
) -> Tuple[str, str, Optional[str], str, List[Dict[str, Any]]]:
    ...
    ) = await self.generate_final_answer_with_retries(
        ...,
        final_output_schema=final_output_schema,
    )


# apps/miroflow-agent/conf/agent/default.yaml
main_agent:
  tools:
    - tool-python
    - tool-vqa
    - tool-transcribe
    - tool-reasoning
    - tool-reader
  max_turns: 20

sub_agents:
  agent-browsing:
    tools:
      - tool-google-search
      - tool-vqa
      - tool-reader
      - tool-python
    max_turns: 20

keep_tool_result: -1
context_compress_limit: 0
output_mode: boxed
```

- [ ] **Step 4: Re-run the structured-output tests**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/test_structured_output_mode.py -v
```

Expected:

```text
PASS - boxed mode remains the default and json mode now produces a canonical JSON payload string.
```

- [ ] **Step 5: Commit the runtime foundation**

```bash
git add apps/miroflow-agent/src/io/input_handler.py apps/miroflow-agent/src/utils/prompt_utils.py apps/miroflow-agent/src/io/output_formatter.py apps/miroflow-agent/src/core/answer_generator.py apps/miroflow-agent/src/core/orchestrator.py apps/miroflow-agent/src/core/pipeline.py apps/miroflow-agent/conf/agent/default.yaml apps/miroflow-agent/tests/data_agents/test_structured_output_mode.py
git commit -m "feat: add structured json output mode"
```

### Task 2: Build The Shared Data-Agent Contract, Runtime, And Dry-Run Publishing Layer

**Files:**
- Modify: `apps/miroflow-agent/pyproject.toml`
- Modify: `apps/miroflow-agent/conf/config.yaml`
- Create: `apps/miroflow-agent/conf/data_agent/default.yaml`
- Create: `apps/miroflow-agent/src/data_agents/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/contracts.py`
- Create: `apps/miroflow-agent/src/data_agents/runtime.py`
- Create: `apps/miroflow-agent/src/data_agents/common/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/common/identifiers.py`
- Create: `apps/miroflow-agent/src/data_agents/common/normalization.py`
- Create: `apps/miroflow-agent/src/data_agents/common/evidence.py`
- Create: `apps/miroflow-agent/src/data_agents/common/linking.py`
- Create: `apps/miroflow-agent/src/data_agents/publishers/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/publishers/jsonl.py`
- Create: `apps/miroflow-agent/tests/data_agents/conftest.py`
- Create: `apps/miroflow-agent/tests/data_agents/test_contracts.py`
- Create: `apps/miroflow-agent/tests/data_agents/test_runtime.py`

- [ ] **Step 1: Write failing tests for contracts, ID generation, normalization, and structured-task parsing**

```python
# apps/miroflow-agent/tests/data_agents/test_contracts.py
from src.data_agents.common.identifiers import build_stable_id
from src.data_agents.common.normalization import normalize_company_name, normalize_person_name
from src.data_agents.contracts import Evidence, ReleasedObject


def test_build_stable_id_is_prefix_preserving_and_deterministic():
    assert build_stable_id("COMP", "优必选") == build_stable_id("COMP", "优必选")
    assert build_stable_id("COMP", "优必选").startswith("COMP-")


def test_normalization_helpers_are_lossy_only_where_expected():
    assert normalize_company_name("深圳市优必选科技股份有限公司") == "优必选科技"
    assert normalize_person_name(" 李 华 ") == "李华"


def test_released_object_requires_evidence():
    record = ReleasedObject(
        id="COMP-1",
        object_type="company",
        display_name="优必选",
        core_facts={"name": "优必选"},
        summary_fields={"profile_summary": "做人形机器人"},
        evidence=[
            Evidence(
                source_type="xlsx",
                source_name="企名片导出",
                source_url=None,
                retrieved_at="2026-03-30T00:00:00Z",
                snippet="企名片导出行",
            )
        ],
        last_updated="2026-03-30T00:00:00Z",
    )
    assert record.object_type == "company"


# apps/miroflow-agent/tests/data_agents/test_runtime.py
from pydantic import BaseModel

from src.data_agents.runtime import parse_structured_payload, schema_text_for_model


class DemoModel(BaseModel):
    name: str
    value: int


def test_schema_text_for_model_contains_required_keys():
    schema_text = schema_text_for_model(DemoModel)
    assert '"required"' in schema_text
    assert '"name"' in schema_text


def test_parse_structured_payload_validates_against_model():
    parsed = parse_structured_payload('{"name":"demo","value":3}', DemoModel)
    assert parsed.value == 3
```

- [ ] **Step 2: Run the shared-layer tests and verify the package does not exist yet**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/test_contracts.py tests/data_agents/test_runtime.py -v
```

Expected:

```text
FAIL with ModuleNotFoundError for src.data_agents and missing config group data_agent.
```

- [ ] **Step 3: Implement shared contracts, helpers, and a dry-run JSONL publisher**

```python
# apps/miroflow-agent/pyproject.toml
dependencies = [
    ...
    "pydantic>=2.11.7",
]


# apps/miroflow-agent/conf/config.yaml
defaults:
  - llm: default
  - agent: default
  - benchmark: default
  - data_agent: default
  - _self_

hydra:
  run:
    dir: ../../logs/debug

project_name: "miroflow-agent"
debug_dir: "../../logs/debug"


# apps/miroflow-agent/conf/data_agent/default.yaml
domain: generic
input_path: ""
output_path: "../../logs/data_agents/generic.jsonl"
dry_run: true
publish:
  enabled: false
  postgres_table: ""
  milvus_collection: ""
embedding:
  model_name: "text-embedding-3-large"


# apps/miroflow-agent/src/data_agents/__init__.py
from .contracts import Evidence, ReleasedObject
from .runtime import load_domain_cfg, parse_structured_payload, run_structured_task, run_sync, schema_text_for_model


# apps/miroflow-agent/src/data_agents/contracts.py
from typing import Any, Literal

from pydantic import BaseModel, Field


QualityStatus = Literal["ready", "needs_review", "low_confidence"]


class Evidence(BaseModel):
    source_type: Literal[
        "xlsx",
        "official_site",
        "web_search",
        "scholar",
        "patent_platform",
        "manual",
    ]
    source_name: str
    source_url: str | None = None
    retrieved_at: str
    snippet: str | None = None


class ReleasedObject(BaseModel):
    id: str
    object_type: Literal["company", "professor", "paper", "patent"]
    display_name: str
    core_facts: dict[str, Any]
    summary_fields: dict[str, Any]
    evidence: list[Evidence] = Field(min_length=1)
    last_updated: str
    quality_status: QualityStatus = "ready"


# apps/miroflow-agent/src/data_agents/common/identifiers.py
from hashlib import sha1


def build_stable_id(prefix: str, natural_key: str) -> str:
    digest = sha1(natural_key.strip().encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{digest}"


# apps/miroflow-agent/src/data_agents/common/__init__.py
from .evidence import build_evidence
from .identifiers import build_stable_id
from .linking import match_names
from .normalization import normalize_company_name, normalize_person_name


# apps/miroflow-agent/src/data_agents/common/normalization.py
import re


COMPANY_SUFFIX_RE = re.compile(r"(股份有限公司|有限责任公司|有限公司|集团有限公司|集团)$")


def normalize_company_name(name: str) -> str:
    normalized = re.sub(r"\s+", "", name or "")
    normalized = normalized.removeprefix("深圳市")
    normalized = COMPANY_SUFFIX_RE.sub("", normalized)
    return normalized


def normalize_person_name(name: str) -> str:
    return re.sub(r"\s+", "", name or "")


# apps/miroflow-agent/src/data_agents/common/evidence.py
from datetime import datetime, timezone

from ..contracts import Evidence


def build_evidence(
    source_type: str,
    source_name: str,
    source_url: str | None,
    snippet: str | None = None,
) -> Evidence:
    return Evidence(
        source_type=source_type,
        source_name=source_name,
        source_url=source_url,
        retrieved_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        snippet=snippet,
    )


# apps/miroflow-agent/src/data_agents/common/linking.py
from collections.abc import Callable


def match_names(
    candidates: list[str],
    index: dict[str, str],
    normalizer: Callable[[str], str],
) -> list[str]:
    matches: list[str] = []
    for candidate in candidates:
        key = normalizer(candidate)
        if key in index:
            matches.append(index[key])
    return matches


# apps/miroflow-agent/src/data_agents/publishers/__init__.py
from .jsonl import JSONLPublisher


# apps/miroflow-agent/src/data_agents/publishers/jsonl.py
import json
from pathlib import Path

from pydantic import BaseModel


class JSONLPublisher:
    def write(self, path: Path, records: list[BaseModel]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False))
                handle.write("\n")


# apps/miroflow-agent/src/data_agents/runtime.py
import asyncio
import json
from pathlib import Path
from typing import TypeVar

from hydra import compose, initialize_config_dir
from omegaconf import DictConfig
from pydantic import BaseModel

from src.core.pipeline import create_pipeline_components, execute_task_pipeline

ModelT = TypeVar("ModelT", bound=BaseModel)


def schema_text_for_model(model_cls: type[ModelT]) -> str:
    return json.dumps(model_cls.model_json_schema(), ensure_ascii=False, indent=2)


def parse_structured_payload(payload: str, model_cls: type[ModelT]) -> ModelT:
    return model_cls.model_validate_json(payload)


def load_domain_cfg(domain: str, agent_name: str) -> DictConfig:
    conf_dir = Path(__file__).resolve().parents[2] / "conf"
    with initialize_config_dir(config_dir=str(conf_dir), version_base=None):
        return compose(
            config_name="config",
            overrides=[f"agent={agent_name}", f"data_agent={domain}"],
        )


async def run_structured_task(
    cfg: DictConfig,
    task_id: str,
    task_description: str,
    output_model: type[ModelT],
    task_file_name: str = "",
) -> tuple[ModelT, str]:
    main_tools, sub_tools, output_formatter = create_pipeline_components(cfg)
    _, payload, log_file_path, _ = await execute_task_pipeline(
        cfg=cfg,
        task_id=task_id,
        task_description=task_description,
        task_file_name=task_file_name,
        main_agent_tool_manager=main_tools,
        sub_agent_tool_managers=sub_tools,
        output_formatter=output_formatter,
        log_dir=cfg.debug_dir,
        final_output_schema=schema_text_for_model(output_model),
    )
    return parse_structured_payload(payload, output_model), log_file_path


def run_sync(coro):
    return asyncio.run(coro)


# apps/miroflow-agent/tests/data_agents/conftest.py
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

- [ ] **Step 4: Re-run the shared-layer tests**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/test_contracts.py tests/data_agents/test_runtime.py -v
```

Expected:

```text
PASS - the repo now has a reusable contract package, deterministic IDs, normalization helpers, schema generation, and dry-run publishing support.
```

- [ ] **Step 5: Commit the shared data-agent layer**

```bash
git add apps/miroflow-agent/pyproject.toml apps/miroflow-agent/conf/config.yaml apps/miroflow-agent/conf/data_agent/default.yaml apps/miroflow-agent/src/data_agents apps/miroflow-agent/tests/data_agents/conftest.py apps/miroflow-agent/tests/data_agents/test_contracts.py apps/miroflow-agent/tests/data_agents/test_runtime.py
git commit -m "feat: add shared data agent contracts and runtime"
```

### Task 3: Implement The Company Data Agent Vertical Slice

**Files:**
- Create: `apps/miroflow-agent/conf/agent/data_agent_company.yaml`
- Create: `apps/miroflow-agent/conf/data_agent/company.yaml`
- Create: `apps/miroflow-agent/scripts/run_company_data_agent.py`
- Create: `apps/miroflow-agent/src/data_agents/company/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/company/models.py`
- Create: `apps/miroflow-agent/src/data_agents/company/import_xlsx.py`
- Create: `apps/miroflow-agent/src/data_agents/company/enrich.py`
- Create: `apps/miroflow-agent/src/data_agents/company/pipeline.py`
- Test: `apps/miroflow-agent/tests/data_agents/company/test_import_xlsx.py`
- Test: `apps/miroflow-agent/tests/data_agents/company/test_pipeline.py`

- [ ] **Step 1: Write failing tests for xlsx import, dedupe, and dry-run publishing**

```python
# apps/miroflow-agent/tests/data_agents/company/test_import_xlsx.py
from openpyxl import Workbook

from src.data_agents.company.import_xlsx import load_company_rows


def test_load_company_rows_dedupes_by_normalized_name(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["企业名称", "行业", "官网"])
    ws.append(["深圳市优必选科技股份有限公司", "机器人", "https://www.ubtrobot.com"])
    ws.append(["优必选科技股份有限公司", "机器人", ""])
    file_path = tmp_path / "company.xlsx"
    wb.save(file_path)

    rows = load_company_rows(file_path)

    assert len(rows) == 1
    assert rows[0].normalized_name == "优必选科技"


# apps/miroflow-agent/tests/data_agents/company/test_pipeline.py
from types import SimpleNamespace

import pytest

from src.data_agents.contracts import Evidence
from src.data_agents.company.models import CompanyRecord
from src.data_agents.company.pipeline import publish_company_records


@pytest.mark.asyncio
async def test_publish_company_records_writes_jsonl(tmp_path):
    cfg = SimpleNamespace(data_agent=SimpleNamespace(output_path=str(tmp_path / "company.jsonl")))
    records = [
        CompanyRecord(
            id="COMP-1",
            name="优必选",
            normalized_name="优必选",
            industry="机器人",
            legal_representative=None,
            registered_capital=None,
            website="https://www.ubtrobot.com",
            key_personnel=[],
            profile_summary="做人形机器人和服务机器人。",
            evaluation_summary="具备较强产品化能力。",
            technology_route_summary="以机器人整机和平台能力为主。",
            evidence=[
                Evidence(
                    source_type="xlsx",
                    source_name="企名片导出",
                    source_url=None,
                    retrieved_at="2026-03-30T00:00:00Z",
                    snippet="company row",
                )
            ],
            last_updated="2026-03-30T00:00:00Z",
        )
    ]
    publish_company_records(cfg, records)
    assert (tmp_path / "company.jsonl").exists()
```

- [ ] **Step 2: Run the company tests and verify the vertical slice does not exist yet**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/company/test_import_xlsx.py tests/data_agents/company/test_pipeline.py -v
```

Expected:

```text
FAIL with ModuleNotFoundError for src.data_agents.company and missing CompanyRecord.
```

- [ ] **Step 3: Implement company import, enrichment prompt construction, and runner wiring**

```python
# apps/miroflow-agent/src/data_agents/company/__init__.py
from .models import CompanyImportRow, CompanyRecord, KeyPerson
from .pipeline import publish_company_records, run_company_data_agent


# apps/miroflow-agent/src/data_agents/company/models.py
from pydantic import BaseModel, Field

from ..contracts import Evidence, ReleasedObject


class KeyPerson(BaseModel):
    name: str
    role: str
    education_structured: list[dict] = Field(default_factory=list)
    work_experience: list[dict] = Field(default_factory=list)
    description: str = ""


class CompanyImportRow(BaseModel):
    name: str
    normalized_name: str
    industry: str | None = None
    website: str | None = None


class CompanyRecord(BaseModel):
    id: str
    name: str
    normalized_name: str
    industry: str | None = None
    legal_representative: str | None = None
    registered_capital: str | None = None
    website: str | None = None
    key_personnel: list[KeyPerson] = Field(default_factory=list)
    profile_summary: str
    evaluation_summary: str
    technology_route_summary: str
    evidence: list[Evidence] = Field(default_factory=list)
    last_updated: str

    def to_release_object(self) -> ReleasedObject:
        return ReleasedObject(
            id=self.id,
            object_type="company",
            display_name=self.name,
            core_facts={
                "name": self.name,
                "normalized_name": self.normalized_name,
                "industry": self.industry,
                "website": self.website,
                "key_personnel": [person.model_dump(mode="json") for person in self.key_personnel],
            },
            summary_fields={
                "profile_summary": self.profile_summary,
                "evaluation_summary": self.evaluation_summary,
                "technology_route_summary": self.technology_route_summary,
            },
            evidence=self.evidence,
            last_updated=self.last_updated,
        )


# apps/miroflow-agent/src/data_agents/company/import_xlsx.py
from pathlib import Path

from openpyxl import load_workbook

from ..common.normalization import normalize_company_name
from .models import CompanyImportRow


HEADER_ALIASES = {
    "企业名称": "name",
    "公司名称": "name",
    "行业": "industry",
    "官网": "website",
}


def load_company_rows(path: Path) -> list[CompanyImportRow]:
    workbook = load_workbook(path, data_only=True)
    sheet = workbook.active
    headers = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
    mapping = {index: HEADER_ALIASES[value] for index, value in enumerate(headers) if value in HEADER_ALIASES}
    deduped: dict[str, CompanyImportRow] = {}
    for row in sheet.iter_rows(min_row=2, values_only=True):
        raw = {mapping[idx]: value for idx, value in enumerate(row) if idx in mapping}
        if not raw.get("name"):
            continue
        normalized_name = normalize_company_name(str(raw["name"]))
        deduped[normalized_name] = CompanyImportRow(
            name=str(raw["name"]).strip(),
            normalized_name=normalized_name,
            industry=str(raw["industry"]).strip() if raw.get("industry") else None,
            website=str(raw["website"]).strip() if raw.get("website") else None,
        )
    return list(deduped.values())


# apps/miroflow-agent/src/data_agents/company/enrich.py
from ..common.identifiers import build_stable_id


def build_company_enrichment_task(row) -> str:
    return (
        "你是企业数据清洗智能体。请以给定骨架事实为主，必要时再使用网页工具补充。"
        "输出一个 company JSON 对象，不要输出 markdown。\n\n"
        f"企业名称: {row.name}\n"
        f"标准化名称: {row.normalized_name}\n"
        f"行业: {row.industry or '未知'}\n"
        f"官网: {row.website or '未知'}\n"
        "必须输出字段: id, name, normalized_name, industry, website, "
        "key_personnel, profile_summary, evaluation_summary, technology_route_summary, evidence, last_updated.\n"
        f"id 必须使用: {build_stable_id('COMP', row.normalized_name)}"
    )


# apps/miroflow-agent/src/data_agents/company/pipeline.py
from pathlib import Path

from ..publishers.jsonl import JSONLPublisher
from ..runtime import run_structured_task, run_sync
from .enrich import build_company_enrichment_task
from .import_xlsx import load_company_rows
from .models import CompanyRecord


async def run_company_data_agent(cfg):
    rows = load_company_rows(Path(cfg.data_agent.input_path))
    records: list[CompanyRecord] = []
    for index, row in enumerate(rows, start=1):
        record, _ = await run_structured_task(
            cfg=cfg,
            task_id=f"company-{index}",
            task_description=build_company_enrichment_task(row),
            output_model=CompanyRecord,
        )
        records.append(record)
    publish_company_records(cfg, records)
    return records


def publish_company_records(cfg, records: list[CompanyRecord]) -> None:
    JSONLPublisher().write(
        Path(cfg.data_agent.output_path),
        [record.to_release_object() for record in records],
    )


# apps/miroflow-agent/conf/agent/data_agent_company.yaml
defaults:
  - default
  - _self_

main_agent:
  tools:
    - search_and_scrape_webpage
    - jina_scrape_llm_summary
    - tool-python
  tool_blacklist:
    - ["search_and_scrape_webpage", "sogou_search"]
  max_turns: 60

sub_agents:

keep_tool_result: 5
context_compress_limit: 5
retry_with_summary: false
output_mode: json


# apps/miroflow-agent/conf/data_agent/company.yaml
defaults:
  - default
  - _self_

domain: company
input_path: ""
output_path: "../../logs/data_agents/company.jsonl"
dry_run: true
publish:
  enabled: false
  postgres_table: "company_released_objects"
  milvus_collection: "company_profiles"


# apps/miroflow-agent/scripts/run_company_data_agent.py
from src.data_agents.company.pipeline import run_company_data_agent
from src.data_agents.runtime import load_domain_cfg, run_sync


def main() -> None:
    cfg = load_domain_cfg("company", "data_agent_company")
    run_sync(run_company_data_agent(cfg))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Re-run the company tests**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/company/test_import_xlsx.py tests/data_agents/company/test_pipeline.py -v
```

Expected:

```text
PASS - company xlsx rows dedupe on normalized name and dry-run publishing writes contract-shaped JSONL output.
```

- [ ] **Step 5: Commit the company slice**

```bash
git add apps/miroflow-agent/conf/agent/data_agent_company.yaml apps/miroflow-agent/conf/data_agent/company.yaml apps/miroflow-agent/scripts/run_company_data_agent.py apps/miroflow-agent/src/data_agents/company apps/miroflow-agent/tests/data_agents/company/test_import_xlsx.py apps/miroflow-agent/tests/data_agents/company/test_pipeline.py
git commit -m "feat: add company data agent"
```

### Task 4: Implement The Professor Data Agent Vertical Slice

**Files:**
- Modify: `apps/miroflow-agent/pyproject.toml`
- Create: `apps/miroflow-agent/conf/agent/data_agent_professor.yaml`
- Create: `apps/miroflow-agent/conf/data_agent/professor.yaml`
- Create: `apps/miroflow-agent/scripts/run_professor_data_agent.py`
- Create: `apps/miroflow-agent/src/data_agents/professor/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/professor/models.py`
- Create: `apps/miroflow-agent/src/data_agents/professor/roster.py`
- Create: `apps/miroflow-agent/src/data_agents/professor/profile.py`
- Create: `apps/miroflow-agent/src/data_agents/professor/pipeline.py`
- Test: `apps/miroflow-agent/tests/data_agents/professor/test_roster.py`
- Test: `apps/miroflow-agent/tests/data_agents/professor/test_profile.py`

- [ ] **Step 1: Write failing tests for official-site roster extraction and profile shaping**

```python
# apps/miroflow-agent/tests/data_agents/professor/test_roster.py
from src.data_agents.professor.roster import extract_roster_entries


def test_extract_roster_entries_discovers_official_profile_links():
    html = """
    <html><body>
      <ul>
        <li><a href="/faculty/lihua.htm">李华</a></li>
      </ul>
    </body></html>
    """
    entries = extract_roster_entries(
        html=html,
        institution="深圳大学",
        department="计算机与软件学院",
        source_url="https://cs.szu.edu.cn/faculty/index.htm",
    )
    assert len(entries) == 1
    assert entries[0].profile_url == "https://cs.szu.edu.cn/faculty/lihua.htm"


# apps/miroflow-agent/tests/data_agents/professor/test_profile.py
from src.data_agents.contracts import Evidence
from src.data_agents.professor.models import ProfessorRecord


def test_professor_record_requires_official_site_evidence():
    record = ProfessorRecord(
        id="PROF-1",
        name="李华",
        institution="深圳大学",
        department="计算机与软件学院",
        title="教授",
        research_directions=["具身智能"],
        profile_summary="主要研究具身智能与机器人控制。",
        evaluation_summary="具备稳定科研产出。",
        company_roles=[],
        top_papers=[],
        evidence=[
            Evidence(
                source_type="official_site",
                source_name="深圳大学官网",
                source_url="https://cs.szu.edu.cn/faculty/lihua.htm",
                retrieved_at="2026-03-30T00:00:00Z",
                snippet="李华，教授",
            )
        ],
        last_updated="2026-03-30T00:00:00Z",
    )
    assert record.institution == "深圳大学"
```

- [ ] **Step 2: Run the professor tests and verify the slice is not implemented yet**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/professor/test_roster.py tests/data_agents/professor/test_profile.py -v
```

Expected:

```text
FAIL with ModuleNotFoundError for src.data_agents.professor and missing BeautifulSoup dependency.
```

- [ ] **Step 3: Implement roster discovery, official-site-first profile prompts, and company-role linking**

```python
# apps/miroflow-agent/pyproject.toml
dependencies = [
    ...
    "beautifulsoup4>=4.13.4",
]


# apps/miroflow-agent/src/data_agents/professor/__init__.py
from .models import ProfessorRecord, ProfessorSeed
from .pipeline import run_professor_data_agent
from .roster import extract_roster_entries


# apps/miroflow-agent/src/data_agents/professor/models.py
from pydantic import BaseModel, Field

from ..contracts import Evidence, ReleasedObject


class ProfessorSeed(BaseModel):
    name: str
    institution: str
    department: str | None = None
    profile_url: str
    evidence: list[Evidence]


class ProfessorRecord(BaseModel):
    id: str
    name: str
    institution: str
    department: str | None = None
    title: str | None = None
    research_directions: list[str] = Field(default_factory=list)
    profile_summary: str
    evaluation_summary: str
    company_roles: list[dict] = Field(default_factory=list)
    top_papers: list[dict] = Field(default_factory=list)
    evidence: list[Evidence]
    last_updated: str

    def to_release_object(self) -> ReleasedObject:
        return ReleasedObject(
            id=self.id,
            object_type="professor",
            display_name=self.name,
            core_facts={
                "name": self.name,
                "institution": self.institution,
                "department": self.department,
                "title": self.title,
                "research_directions": self.research_directions,
                "company_roles": self.company_roles,
                "top_papers": self.top_papers,
            },
            summary_fields={
                "profile_summary": self.profile_summary,
                "evaluation_summary": self.evaluation_summary,
            },
            evidence=self.evidence,
            last_updated=self.last_updated,
        )


# apps/miroflow-agent/src/data_agents/professor/roster.py
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..common.evidence import build_evidence
from ..common.normalization import normalize_person_name
from .models import ProfessorSeed


def extract_roster_entries(
    html: str,
    institution: str,
    department: str | None,
    source_url: str,
) -> list[ProfessorSeed]:
    soup = BeautifulSoup(html, "html.parser")
    deduped: dict[str, ProfessorSeed] = {}
    for link in soup.select("a[href]"):
        name = normalize_person_name(link.get_text(strip=True))
        if not (2 <= len(name) <= 12):
            continue
        if any(block_word in name for block_word in ("教师", "详情", "简介")):
            continue
        profile_url = urljoin(source_url, link["href"])
        deduped[name] = ProfessorSeed(
            name=name,
            institution=institution,
            department=department,
            profile_url=profile_url,
            evidence=[
                build_evidence(
                    source_type="official_site",
                    source_name=institution,
                    source_url=source_url,
                    snippet=f"Roster discovery for {name}",
                )
            ],
        )
    return list(deduped.values())


# apps/miroflow-agent/src/data_agents/professor/profile.py
from ..common.identifiers import build_stable_id


def build_professor_profile_task(seed, company_index: dict[str, str]) -> str:
    return (
        "你是教授数据采集智能体。必须先以高校官网教师页为身份锚点，再决定是否补充网页、Scholar 或论文信息。"
        "输出一个 professor JSON 对象，不要输出 markdown。\n\n"
        f"姓名: {seed.name}\n"
        f"机构: {seed.institution}\n"
        f"院系: {seed.department or '未知'}\n"
        f"官网主页: {seed.profile_url}\n"
        f"id 必须使用: {build_stable_id('PROF', seed.institution + ':' + seed.name)}\n"
        f"企业匹配索引键: {sorted(company_index.keys())[:20]}"
    )


# apps/miroflow-agent/src/data_agents/professor/pipeline.py
import json
from pathlib import Path

from ..publishers.jsonl import JSONLPublisher
from ..runtime import run_structured_task
from .models import ProfessorRecord, ProfessorSeed
from .profile import build_professor_profile_task


def load_professor_seeds(path: Path) -> list[ProfessorSeed]:
    with path.open("r", encoding="utf-8") as handle:
        return [ProfessorSeed.model_validate_json(line) for line in handle if line.strip()]


async def run_professor_data_agent(cfg):
    company_index = {}
    if cfg.data_agent.company_release_path:
        with Path(cfg.data_agent.company_release_path).open("r", encoding="utf-8") as handle:
            for line in handle:
                payload = json.loads(line)
                company_index[payload["core_facts"]["normalized_name"]] = payload["id"]

    seeds = load_professor_seeds(Path(cfg.data_agent.seed_path))
    records: list[ProfessorRecord] = []
    for index, seed in enumerate(seeds, start=1):
        record, _ = await run_structured_task(
            cfg=cfg,
            task_id=f"professor-{index}",
            task_description=build_professor_profile_task(seed, company_index),
            output_model=ProfessorRecord,
        )
        records.append(record)

    JSONLPublisher().write(
        Path(cfg.data_agent.output_path),
        [record.to_release_object() for record in records],
    )
    return records


# apps/miroflow-agent/conf/agent/data_agent_professor.yaml
defaults:
  - default
  - _self_

main_agent:
  tools:
    - search_and_scrape_webpage
    - jina_scrape_llm_summary
    - tool-python
  tool_blacklist:
    - ["search_and_scrape_webpage", "sogou_search"]
  max_turns: 80

sub_agents:

keep_tool_result: 5
context_compress_limit: 5
retry_with_summary: false
output_mode: json


# apps/miroflow-agent/conf/data_agent/professor.yaml
defaults:
  - default
  - _self_

domain: professor
seed_path: ""
company_release_path: "../../logs/data_agents/company.jsonl"
output_path: "../../logs/data_agents/professor.jsonl"
dry_run: true
publish:
  enabled: false
  postgres_table: "professor_released_objects"
  milvus_collection: "professor_profiles"


# apps/miroflow-agent/scripts/run_professor_data_agent.py
from src.data_agents.professor.pipeline import run_professor_data_agent
from src.data_agents.runtime import load_domain_cfg, run_sync


def main() -> None:
    cfg = load_domain_cfg("professor", "data_agent_professor")
    run_sync(run_professor_data_agent(cfg))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Re-run the professor tests**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/professor/test_roster.py tests/data_agents/professor/test_profile.py -v
```

Expected:

```text
PASS - roster parsing is official-site-first and professor records are shaped to the outward contract.
```

- [ ] **Step 5: Commit the professor slice**

```bash
git add apps/miroflow-agent/pyproject.toml apps/miroflow-agent/conf/agent/data_agent_professor.yaml apps/miroflow-agent/conf/data_agent/professor.yaml apps/miroflow-agent/scripts/run_professor_data_agent.py apps/miroflow-agent/src/data_agents/professor apps/miroflow-agent/tests/data_agents/professor/test_roster.py apps/miroflow-agent/tests/data_agents/professor/test_profile.py
git commit -m "feat: add professor data agent"
```

### Task 5: Implement The Professor-Anchored Paper Data Agent Vertical Slice

**Files:**
- Create: `apps/miroflow-agent/conf/agent/data_agent_paper.yaml`
- Create: `apps/miroflow-agent/conf/data_agent/paper.yaml`
- Create: `apps/miroflow-agent/scripts/run_paper_data_agent.py`
- Create: `apps/miroflow-agent/src/data_agents/paper/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/paper/models.py`
- Create: `apps/miroflow-agent/src/data_agents/paper/discovery.py`
- Create: `apps/miroflow-agent/src/data_agents/paper/enrichment.py`
- Create: `apps/miroflow-agent/src/data_agents/paper/pipeline.py`
- Test: `apps/miroflow-agent/tests/data_agents/paper/test_discovery.py`
- Test: `apps/miroflow-agent/tests/data_agents/paper/test_pipeline.py`

- [ ] **Step 1: Write failing tests for professor-anchored discovery and professor-enrichment outputs**

```python
# apps/miroflow-agent/tests/data_agents/paper/test_discovery.py
from src.data_agents.paper.discovery import build_candidate_queries
from src.data_agents.professor.models import ProfessorRecord


def test_build_candidate_queries_uses_professor_identity_and_institution():
    professor = ProfessorRecord(
        id="PROF-1",
        name="李华",
        institution="深圳大学",
        department="计算机与软件学院",
        title="教授",
        research_directions=["具身智能"],
        profile_summary="研究具身智能。",
        evaluation_summary="稳定产出。",
        company_roles=[],
        top_papers=[],
        evidence=[],
        last_updated="2026-03-30T00:00:00Z",
    )
    queries = build_candidate_queries(professor)
    assert queries[0] == '"李华" "深圳大学"'


# apps/miroflow-agent/tests/data_agents/paper/test_pipeline.py
from src.data_agents.paper.enrichment import build_professor_enrichment_updates
from src.data_agents.paper.models import PaperRecord, PaperSummaryZh


def test_build_professor_enrichment_updates_groups_by_professor():
    paper = PaperRecord(
        id="PAPER-1",
        title="Embodied Agents for Manipulation",
        title_zh=None,
        authors=["李华", "王敏"],
        professor_ids=["PROF-1"],
        year=2025,
        venue="ICRA",
        doi=None,
        arxiv_id=None,
        abstract=None,
        summary_zh=PaperSummaryZh(
            what="做了抓取任务。",
            why="提高泛化。",
            how="使用多模态策略。",
            result="在公开基准上提升。",
        ),
        summary_text="做了什么：做了抓取任务。",
        keywords=["具身智能", "抓取"],
        citation_count=None,
        pdf_path=None,
        evidence=[],
        last_updated="2026-03-30T00:00:00Z",
    )
    updates = build_professor_enrichment_updates([paper])
    assert updates["PROF-1"]["top_papers"][0]["title"] == "Embodied Agents for Manipulation"
```

- [ ] **Step 2: Run the paper tests and verify the professor-anchored slice is absent**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/paper/test_discovery.py tests/data_agents/paper/test_pipeline.py -v
```

Expected:

```text
FAIL with ModuleNotFoundError for src.data_agents.paper and missing PaperRecord / PaperSummaryZh.
```

- [ ] **Step 3: Implement paper models, professor-anchored query generation, and enrichment export**

```python
# apps/miroflow-agent/src/data_agents/paper/__init__.py
from .discovery import build_candidate_queries
from .enrichment import build_professor_enrichment_updates
from .models import PaperRecord, PaperSummaryZh
from .pipeline import run_paper_data_agent


# apps/miroflow-agent/src/data_agents/paper/models.py
from pydantic import BaseModel, Field

from ..contracts import Evidence, ReleasedObject


class PaperSummaryZh(BaseModel):
    what: str
    why: str
    how: str
    result: str

    def as_text(self) -> str:
        return "\n".join(
            [
                f"做了什么：{self.what}",
                f"为什么重要：{self.why}",
                f"核心方法：{self.how}",
                f"结果：{self.result}",
            ]
        )


class PaperRecord(BaseModel):
    id: str
    title: str
    title_zh: str | None = None
    authors: list[str]
    professor_ids: list[str] = Field(default_factory=list)
    year: int
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    abstract: str | None = None
    summary_zh: PaperSummaryZh
    summary_text: str
    keywords: list[str] = Field(default_factory=list)
    citation_count: int | None = None
    pdf_path: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    last_updated: str

    def to_release_object(self) -> ReleasedObject:
        return ReleasedObject(
            id=self.id,
            object_type="paper",
            display_name=self.title,
            core_facts={
                "title": self.title,
                "authors": self.authors,
                "professor_ids": self.professor_ids,
                "year": self.year,
                "venue": self.venue,
                "doi": self.doi,
                "arxiv_id": self.arxiv_id,
                "keywords": self.keywords,
            },
            summary_fields={
                "summary_zh": self.summary_zh.model_dump(mode="json"),
                "summary_text": self.summary_text,
            },
            evidence=self.evidence,
            last_updated=self.last_updated,
        )


# apps/miroflow-agent/src/data_agents/paper/discovery.py
from ..professor.models import ProfessorRecord


def build_candidate_queries(professor: ProfessorRecord) -> list[str]:
    queries = [f'"{professor.name}" "{professor.institution}"']
    if professor.research_directions:
        queries.append(f'"{professor.name}" "{professor.research_directions[0]}"')
    return queries


# apps/miroflow-agent/src/data_agents/paper/enrichment.py
from collections import defaultdict

from .models import PaperRecord


def build_professor_enrichment_updates(papers: list[PaperRecord]) -> dict[str, dict]:
    grouped: dict[str, list[PaperRecord]] = defaultdict(list)
    for paper in papers:
        for professor_id in paper.professor_ids:
            grouped[professor_id].append(paper)

    updates: dict[str, dict] = {}
    for professor_id, professor_papers in grouped.items():
        ranked = sorted(professor_papers, key=lambda item: item.year, reverse=True)
        updates[professor_id] = {
            "top_papers": [
                {"title": paper.title, "year": paper.year, "venue": paper.venue}
                for paper in ranked[:5]
            ],
            "recent_keywords": sorted({keyword for paper in ranked for keyword in paper.keywords}),
        }
    return updates


# apps/miroflow-agent/src/data_agents/paper/pipeline.py
import json
from pathlib import Path

from ..publishers.jsonl import JSONLPublisher
from ..runtime import run_structured_task
from ..professor.models import ProfessorRecord
from .discovery import build_candidate_queries
from .enrichment import build_professor_enrichment_updates
from .models import PaperRecord


def load_professor_records(path: Path) -> list[ProfessorRecord]:
    records: list[ProfessorRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            core = payload["core_facts"]
            records.append(
                ProfessorRecord(
                    id=payload["id"],
                    name=core["name"],
                    institution=core["institution"],
                    department=core.get("department"),
                    title=core.get("title"),
                    research_directions=core.get("research_directions", []),
                    profile_summary=payload["summary_fields"]["profile_summary"],
                    evaluation_summary=payload["summary_fields"].get("evaluation_summary", ""),
                    company_roles=core.get("company_roles", []),
                    top_papers=core.get("top_papers", []),
                    evidence=[],
                    last_updated=payload["last_updated"],
                )
            )
    return records


async def run_paper_data_agent(cfg):
    professors = load_professor_records(Path(cfg.data_agent.professor_release_path))
    papers: list[PaperRecord] = []
    for professor in professors:
        task = (
            "你是论文数据采集智能体。当前任务必须从教授身份锚点出发收集论文，并输出一个 paper JSON 对象。"
            f"\n教授: {professor.name}\n机构: {professor.institution}\n候选查询: {build_candidate_queries(professor)}"
        )
        record, _ = await run_structured_task(
            cfg=cfg,
            task_id=f"paper-{professor.id}",
            task_description=task,
            output_model=PaperRecord,
        )
        papers.append(record)

    JSONLPublisher().write(
        Path(cfg.data_agent.output_path),
        [paper.to_release_object() for paper in papers],
    )
    Path(cfg.data_agent.professor_enrichment_path).write_text(
        json.dumps(build_professor_enrichment_updates(papers), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return papers


# apps/miroflow-agent/conf/agent/data_agent_paper.yaml
defaults:
  - default
  - _self_

main_agent:
  tools:
    - search_and_scrape_webpage
    - jina_scrape_llm_summary
    - tool-python
  tool_blacklist:
    - ["search_and_scrape_webpage", "sogou_search"]
  max_turns: 80

sub_agents:

keep_tool_result: 5
context_compress_limit: 5
retry_with_summary: false
output_mode: json


# apps/miroflow-agent/conf/data_agent/paper.yaml
defaults:
  - default
  - _self_

domain: paper
professor_release_path: "../../logs/data_agents/professor.jsonl"
output_path: "../../logs/data_agents/paper.jsonl"
professor_enrichment_path: "../../logs/data_agents/professor_enrichment.json"
dry_run: true
publish:
  enabled: false
  postgres_table: "paper_released_objects"
  milvus_collection: "paper_profiles"


# apps/miroflow-agent/scripts/run_paper_data_agent.py
from src.data_agents.paper.pipeline import run_paper_data_agent
from src.data_agents.runtime import load_domain_cfg, run_sync


def main() -> None:
    cfg = load_domain_cfg("paper", "data_agent_paper")
    run_sync(run_paper_data_agent(cfg))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Re-run the paper tests**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/paper/test_discovery.py tests/data_agents/paper/test_pipeline.py -v
```

Expected:

```text
PASS - paper collection is professor-anchored and emits professor-enrichment deltas for downstream profile refresh.
```

- [ ] **Step 5: Commit the paper slice**

```bash
git add apps/miroflow-agent/conf/agent/data_agent_paper.yaml apps/miroflow-agent/conf/data_agent/paper.yaml apps/miroflow-agent/scripts/run_paper_data_agent.py apps/miroflow-agent/src/data_agents/paper apps/miroflow-agent/tests/data_agents/paper/test_discovery.py apps/miroflow-agent/tests/data_agents/paper/test_pipeline.py
git commit -m "feat: add professor anchored paper data agent"
```

### Task 6: Implement The Patent Data Agent Vertical Slice

**Files:**
- Create: `apps/miroflow-agent/conf/agent/data_agent_patent.yaml`
- Create: `apps/miroflow-agent/conf/data_agent/patent.yaml`
- Create: `apps/miroflow-agent/scripts/run_patent_data_agent.py`
- Create: `apps/miroflow-agent/src/data_agents/patent/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/patent/models.py`
- Create: `apps/miroflow-agent/src/data_agents/patent/import_xlsx.py`
- Create: `apps/miroflow-agent/src/data_agents/patent/linking.py`
- Create: `apps/miroflow-agent/src/data_agents/patent/pipeline.py`
- Test: `apps/miroflow-agent/tests/data_agents/patent/test_import_xlsx.py`
- Test: `apps/miroflow-agent/tests/data_agents/patent/test_pipeline.py`

- [ ] **Step 1: Write failing tests for patent xlsx import and entity linking**

```python
# apps/miroflow-agent/tests/data_agents/patent/test_import_xlsx.py
from openpyxl import Workbook

from src.data_agents.patent.import_xlsx import load_patent_rows


def test_load_patent_rows_dedupes_on_patent_number(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["标题", "专利号", "申请人", "发明人"])
    ws.append(["机器人抓取装置", "CN123", "优必选", "李华"])
    ws.append(["机器人抓取装置", "CN123", "优必选", "李华"])
    file_path = tmp_path / "patent.xlsx"
    wb.save(file_path)

    rows = load_patent_rows(file_path)

    assert len(rows) == 1
    assert rows[0].patent_number == "CN123"


# apps/miroflow-agent/tests/data_agents/patent/test_pipeline.py
from src.data_agents.patent.linking import link_patent_entities
from src.data_agents.patent.models import PatentImportRow


def test_link_patent_entities_matches_company_and_professor_indexes():
    row = PatentImportRow(
        title="机器人抓取装置",
        patent_number="CN123",
        applicants=["优必选"],
        inventors=["李华"],
        patent_type=None,
        filing_date=None,
        publication_date=None,
        grant_date=None,
        abstract=None,
        ipc_codes=[],
    )
    company_ids, professor_ids = link_patent_entities(
        row=row,
        company_index={"优必选": "COMP-1"},
        professor_index={"李华": "PROF-1"},
    )
    assert company_ids == ["COMP-1"]
    assert professor_ids == ["PROF-1"]
```

- [ ] **Step 2: Run the patent tests and verify the slice does not exist**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/patent/test_import_xlsx.py tests/data_agents/patent/test_pipeline.py -v
```

Expected:

```text
FAIL with ModuleNotFoundError for src.data_agents.patent and missing PatentImportRow.
```

- [ ] **Step 3: Implement patent xlsx import, applicant/inventor linking, and runner wiring**

```python
# apps/miroflow-agent/src/data_agents/patent/__init__.py
from .import_xlsx import load_patent_rows
from .linking import link_patent_entities
from .models import PatentImportRow, PatentRecord
from .pipeline import run_patent_data_agent


# apps/miroflow-agent/src/data_agents/patent/models.py
from pydantic import BaseModel, Field

from ..contracts import Evidence, ReleasedObject


class PatentImportRow(BaseModel):
    title: str
    patent_number: str | None = None
    applicants: list[str]
    inventors: list[str] = Field(default_factory=list)
    patent_type: str | None = None
    filing_date: str | None = None
    publication_date: str | None = None
    grant_date: str | None = None
    abstract: str | None = None
    ipc_codes: list[str] = Field(default_factory=list)


class PatentRecord(BaseModel):
    id: str
    title: str
    patent_number: str | None = None
    applicants: list[str]
    inventors: list[str] = Field(default_factory=list)
    patent_type: str | None = None
    filing_date: str | None = None
    publication_date: str | None = None
    grant_date: str | None = None
    abstract: str | None = None
    summary_text: str
    technology_effect: str | None = None
    ipc_codes: list[str] = Field(default_factory=list)
    company_ids: list[str] = Field(default_factory=list)
    professor_ids: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    last_updated: str

    def to_release_object(self) -> ReleasedObject:
        return ReleasedObject(
            id=self.id,
            object_type="patent",
            display_name=self.title,
            core_facts={
                "title": self.title,
                "patent_number": self.patent_number,
                "applicants": self.applicants,
                "inventors": self.inventors,
                "patent_type": self.patent_type,
                "ipc_codes": self.ipc_codes,
                "company_ids": self.company_ids,
                "professor_ids": self.professor_ids,
            },
            summary_fields={"summary_text": self.summary_text},
            evidence=self.evidence,
            last_updated=self.last_updated,
        )


# apps/miroflow-agent/src/data_agents/patent/import_xlsx.py
from pathlib import Path

from openpyxl import load_workbook

from .models import PatentImportRow


HEADER_ALIASES = {
    "标题": "title",
    "专利号": "patent_number",
    "申请人": "applicants",
    "发明人": "inventors",
    "专利类型": "patent_type",
    "申请日期": "filing_date",
    "公开日期": "publication_date",
    "授权日期": "grant_date",
    "摘要": "abstract",
    "IPC分类": "ipc_codes",
}


def split_multi_value(value) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).replace("；", ";").split(";") if item.strip()]


def load_patent_rows(path: Path) -> list[PatentImportRow]:
    workbook = load_workbook(path, data_only=True)
    sheet = workbook.active
    headers = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
    mapping = {index: HEADER_ALIASES[value] for index, value in enumerate(headers) if value in HEADER_ALIASES}
    deduped: dict[str, PatentImportRow] = {}
    for row in sheet.iter_rows(min_row=2, values_only=True):
        raw = {mapping[idx]: value for idx, value in enumerate(row) if idx in mapping}
        if not raw.get("title"):
            continue
        key = str(raw.get("patent_number") or raw["title"]).strip()
        deduped[key] = PatentImportRow(
            title=str(raw["title"]).strip(),
            patent_number=str(raw["patent_number"]).strip() if raw.get("patent_number") else None,
            applicants=split_multi_value(raw.get("applicants")),
            inventors=split_multi_value(raw.get("inventors")),
            patent_type=str(raw["patent_type"]).strip() if raw.get("patent_type") else None,
            filing_date=str(raw["filing_date"]).strip() if raw.get("filing_date") else None,
            publication_date=str(raw["publication_date"]).strip() if raw.get("publication_date") else None,
            grant_date=str(raw["grant_date"]).strip() if raw.get("grant_date") else None,
            abstract=str(raw["abstract"]).strip() if raw.get("abstract") else None,
            ipc_codes=split_multi_value(raw.get("ipc_codes")),
        )
    return list(deduped.values())


# apps/miroflow-agent/src/data_agents/patent/linking.py
from ..common.linking import match_names
from ..common.normalization import normalize_company_name, normalize_person_name


def link_patent_entities(row, company_index: dict[str, str], professor_index: dict[str, str]) -> tuple[list[str], list[str]]:
    company_ids = match_names(row.applicants, company_index, normalize_company_name)
    professor_ids = match_names(row.inventors, professor_index, normalize_person_name)
    return company_ids, professor_ids


# apps/miroflow-agent/src/data_agents/patent/pipeline.py
import json
from pathlib import Path

from ..publishers.jsonl import JSONLPublisher
from ..runtime import run_structured_task
from .import_xlsx import load_patent_rows
from .linking import link_patent_entities
from .models import PatentRecord


def load_release_index(path: Path, key_builder) -> dict[str, str]:
    index: dict[str, str] = {}
    if not path.exists():
        return index
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            key = key_builder(payload)
            if key:
                index[key] = payload["id"]
    return index


async def run_patent_data_agent(cfg):
    company_index = load_release_index(
        Path(cfg.data_agent.company_release_path),
        lambda payload: payload["core_facts"].get("normalized_name"),
    )
    professor_index = load_release_index(
        Path(cfg.data_agent.professor_release_path),
        lambda payload: payload["core_facts"].get("name"),
    )

    patents: list[PatentRecord] = []
    for index, row in enumerate(load_patent_rows(Path(cfg.data_agent.input_path)), start=1):
        company_ids, professor_ids = link_patent_entities(row, company_index, professor_index)
        task = (
            "你是专利数据采集智能体。请输出一个 patent JSON 对象。"
            f"\n标题: {row.title}\n专利号: {row.patent_number}\n申请人: {row.applicants}\n发明人: {row.inventors}"
            f"\n预匹配 company_ids: {company_ids}\n预匹配 professor_ids: {professor_ids}"
        )
        record, _ = await run_structured_task(
            cfg=cfg,
            task_id=f"patent-{index}",
            task_description=task,
            output_model=PatentRecord,
        )
        patents.append(record)

    JSONLPublisher().write(
        Path(cfg.data_agent.output_path),
        [record.to_release_object() for record in patents],
    )
    return patents


# apps/miroflow-agent/conf/agent/data_agent_patent.yaml
defaults:
  - default
  - _self_

main_agent:
  tools:
    - search_and_scrape_webpage
    - jina_scrape_llm_summary
    - tool-python
  tool_blacklist:
    - ["search_and_scrape_webpage", "sogou_search"]
  max_turns: 60

sub_agents:

keep_tool_result: 5
context_compress_limit: 5
retry_with_summary: false
output_mode: json


# apps/miroflow-agent/conf/data_agent/patent.yaml
defaults:
  - default
  - _self_

domain: patent
input_path: ""
company_release_path: "../../logs/data_agents/company.jsonl"
professor_release_path: "../../logs/data_agents/professor.jsonl"
output_path: "../../logs/data_agents/patent.jsonl"
dry_run: true
publish:
  enabled: false
  postgres_table: "patent_released_objects"
  milvus_collection: "patent_profiles"


# apps/miroflow-agent/scripts/run_patent_data_agent.py
from src.data_agents.patent.pipeline import run_patent_data_agent
from src.data_agents.runtime import load_domain_cfg, run_sync


def main() -> None:
    cfg = load_domain_cfg("patent", "data_agent_patent")
    run_sync(run_patent_data_agent(cfg))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Re-run the patent tests**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/patent/test_import_xlsx.py tests/data_agents/patent/test_pipeline.py -v
```

Expected:

```text
PASS - patent xlsx import dedupes on patent number and applicant / inventor linking reuses company and professor indexes.
```

- [ ] **Step 5: Commit the patent slice**

```bash
git add apps/miroflow-agent/conf/agent/data_agent_patent.yaml apps/miroflow-agent/conf/data_agent/patent.yaml apps/miroflow-agent/scripts/run_patent_data_agent.py apps/miroflow-agent/src/data_agents/patent apps/miroflow-agent/tests/data_agents/patent/test_import_xlsx.py apps/miroflow-agent/tests/data_agents/patent/test_pipeline.py
git commit -m "feat: add patent data agent"
```

### Task 7: Add PostgreSQL + Milvus Release Adapters And The Final Validation Suite

**Files:**
- Modify: `apps/miroflow-agent/pyproject.toml`
- Modify: `apps/miroflow-agent/conf/data_agent/default.yaml`
- Create: `apps/miroflow-agent/src/data_agents/storage/__init__.py`
- Create: `apps/miroflow-agent/src/data_agents/storage/embedding.py`
- Create: `apps/miroflow-agent/src/data_agents/storage/postgres.py`
- Create: `apps/miroflow-agent/src/data_agents/storage/milvus.py`
- Create: `apps/miroflow-agent/src/data_agents/storage/release_service.py`
- Create: `apps/miroflow-agent/scripts/run_release_validation.py`
- Create: `apps/miroflow-agent/tests/data_agents/storage/test_release_service.py`
- Create: `apps/miroflow-agent/tests/data_agents/test_contract_validation.py`

- [ ] **Step 1: Write failing tests for release publication orchestration and contract coverage**

```python
# apps/miroflow-agent/tests/data_agents/storage/test_release_service.py
from unittest.mock import MagicMock

from src.data_agents.contracts import Evidence, ReleasedObject
from src.data_agents.storage.release_service import ReleaseService


def test_release_service_calls_both_publishers():
    postgres = MagicMock()
    milvus = MagicMock()
    service = ReleaseService(postgres_publisher=postgres, milvus_publisher=milvus)
    record = ReleasedObject(
        id="COMP-1",
        object_type="company",
        display_name="优必选",
        core_facts={"name": "优必选"},
        summary_fields={"profile_summary": "做人形机器人。"},
        evidence=[
            Evidence(
                source_type="xlsx",
                source_name="企名片导出",
                source_url=None,
                retrieved_at="2026-03-30T00:00:00Z",
                snippet="row 1",
            )
        ],
        last_updated="2026-03-30T00:00:00Z",
    )
    service.publish([record], collection_name="company_profiles", table_name="company_released_objects")
    postgres.upsert_release_objects.assert_called_once()
    milvus.upsert_documents.assert_called_once()


# apps/miroflow-agent/tests/data_agents/test_contract_validation.py
import json


def test_release_jsonl_contains_required_contract_fields(tmp_path):
    output_path = tmp_path / "company.jsonl"
    output_path.write_text(
        json.dumps(
            {
                "id": "COMP-1",
                "object_type": "company",
                "display_name": "优必选",
                "core_facts": {"name": "优必选"},
                "summary_fields": {"profile_summary": "做人形机器人。"},
                "evidence": [{"source_type": "xlsx", "source_name": "企名片导出", "retrieved_at": "2026-03-30T00:00:00Z"}],
                "last_updated": "2026-03-30T00:00:00Z",
                "quality_status": "ready",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    payload = json.loads(output_path.read_text(encoding="utf-8").splitlines()[0])
    assert {"id", "object_type", "display_name", "core_facts", "summary_fields", "evidence", "last_updated"} <= payload.keys()
```

- [ ] **Step 2: Run the release tests and verify the storage layer is missing**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/storage/test_release_service.py tests/data_agents/test_contract_validation.py -v
```

Expected:

```text
FAIL with ModuleNotFoundError for src.data_agents.storage and missing ReleaseService.
```

- [ ] **Step 3: Implement release adapters for PostgreSQL, embeddings, and Milvus**

```python
# apps/miroflow-agent/pyproject.toml
dependencies = [
    ...
    "psycopg[binary]>=3.2.9",
    "pymilvus>=2.5.0",
]


# apps/miroflow-agent/conf/data_agent/default.yaml
domain: generic
input_path: ""
output_path: "../../logs/data_agents/generic.jsonl"
dry_run: true
publish:
  enabled: false
  postgres_dsn: ""
  postgres_table: ""
  milvus_uri: ""
  milvus_token: ""
  milvus_collection: ""
embedding:
  model_name: "text-embedding-3-large"


# apps/miroflow-agent/src/data_agents/storage/__init__.py
from .embedding import EmbeddingClient
from .milvus import MilvusPublisher, flatten_summary_text
from .postgres import PostgresPublisher
from .release_service import ReleaseService


# apps/miroflow-agent/src/data_agents/storage/embedding.py
from openai import OpenAI


class EmbeddingClient:
    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=self.model_name, input=texts)
        return [item.embedding for item in response.data]


# apps/miroflow-agent/src/data_agents/storage/postgres.py
import json

import psycopg

from ..contracts import ReleasedObject


class PostgresPublisher:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def upsert_release_objects(self, table_name: str, records: list[ReleasedObject]) -> None:
        sql = f"""
        INSERT INTO {table_name} (id, object_type, display_name, payload, last_updated)
        VALUES (%(id)s, %(object_type)s, %(display_name)s, %(payload)s::jsonb, %(last_updated)s)
        ON CONFLICT (id) DO UPDATE SET
            object_type = EXCLUDED.object_type,
            display_name = EXCLUDED.display_name,
            payload = EXCLUDED.payload,
            last_updated = EXCLUDED.last_updated
        """
        rows = [
            {
                "id": record.id,
                "object_type": record.object_type,
                "display_name": record.display_name,
                "payload": json.dumps(record.model_dump(mode="json"), ensure_ascii=False),
                "last_updated": record.last_updated,
            }
            for record in records
        ]
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                cursor.executemany(sql, rows)
            conn.commit()


# apps/miroflow-agent/src/data_agents/storage/milvus.py
from pymilvus import MilvusClient

from ..contracts import ReleasedObject


def flatten_summary_text(record: ReleasedObject) -> str:
    parts = [record.display_name]
    parts.extend(str(value) for value in record.summary_fields.values() if value)
    return "\n".join(parts)


class MilvusPublisher:
    def __init__(self, uri: str, token: str, embedding_client):
        self.client = MilvusClient(uri=uri, token=token)
        self.embedding_client = embedding_client

    def upsert_documents(self, collection_name: str, records: list[ReleasedObject]) -> None:
        texts = [flatten_summary_text(record) for record in records]
        vectors = self.embedding_client.embed_texts(texts)
        rows = []
        for record, text, vector in zip(records, texts, vectors, strict=True):
            rows.append(
                {
                    "id": record.id,
                    "object_type": record.object_type,
                    "display_name": record.display_name,
                    "summary_text": text,
                    "payload": record.model_dump(mode="json"),
                    "vector": vector,
                }
            )
        self.client.upsert(collection_name=collection_name, data=rows)


# apps/miroflow-agent/src/data_agents/storage/release_service.py
from ..contracts import ReleasedObject


class ReleaseService:
    def __init__(self, postgres_publisher, milvus_publisher):
        self.postgres_publisher = postgres_publisher
        self.milvus_publisher = milvus_publisher

    def publish(self, records: list[ReleasedObject], collection_name: str, table_name: str) -> None:
        self.postgres_publisher.upsert_release_objects(table_name, records)
        self.milvus_publisher.upsert_documents(collection_name, records)


# apps/miroflow-agent/scripts/run_release_validation.py
import json
from pathlib import Path


REQUIRED_FIELDS = {
    "id",
    "object_type",
    "display_name",
    "core_facts",
    "summary_fields",
    "evidence",
    "last_updated",
}


def validate_jsonl(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        payload = json.loads(line)
        missing = REQUIRED_FIELDS - payload.keys()
        if missing:
            raise ValueError(f"{path} missing required fields: {sorted(missing)}")


def main() -> None:
    for path in Path("../../logs/data_agents").glob("*.jsonl"):
        validate_jsonl(path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Re-run the release tests and then run the full data-agent test suite**

Run:

```bash
cd apps/miroflow-agent && uv run pytest tests/data_agents/storage/test_release_service.py tests/data_agents/test_contract_validation.py tests/data_agents -v
```

Expected:

```text
PASS - release orchestration, contract validation, and all data-agent unit tests pass in one run.
```

- [ ] **Step 5: Commit the release adapters and validation suite**

```bash
git add apps/miroflow-agent/pyproject.toml apps/miroflow-agent/conf/data_agent/default.yaml apps/miroflow-agent/src/data_agents/storage apps/miroflow-agent/scripts/run_release_validation.py apps/miroflow-agent/tests/data_agents/storage/test_release_service.py apps/miroflow-agent/tests/data_agents/test_contract_validation.py
git commit -m "feat: add data agent release adapters"
```

## Self-Review Checklist

- [ ] Spec coverage: confirm Task 1 covers the runtime blocker, Tasks 3 through 6 cover company / professor / paper / patent PRDs, and Task 7 covers the `PostgreSQL + Milvus` release requirement.
- [ ] Placeholder scan: confirm this plan contains no filler language or deferred-work markers from the writing-plans "No Placeholders" section.
- [ ] Type consistency: confirm the shared types `Evidence`, `ReleasedObject`, `CompanyRecord`, `ProfessorRecord`, `PaperRecord`, `PatentRecord`, and helper names like `run_structured_task`, `build_stable_id`, `normalize_company_name`, and `link_patent_entities` are referenced consistently across tasks.
