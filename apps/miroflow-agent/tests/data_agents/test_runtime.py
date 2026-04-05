import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.data_agents.contracts import CompanyRecord
from src.data_agents.evidence import build_evidence, merge_evidence
from src.data_agents.linking import build_normalized_index, link_normalized_values
from src.data_agents.normalization import (
    build_stable_id,
    normalize_company_name,
    normalize_person_name,
)
from src.data_agents.providers.mirothinker import MiroThinkerProvider
from src.data_agents.providers.qwen import QwenProvider
from src.data_agents.providers.web_search import WebSearchProvider
from src.data_agents.publish import publish_jsonl
from src.data_agents.runtime import (
    load_domain_cfg,
    parse_structured_payload,
    run_structured_task,
    schema_text_for_model,
)


TIMESTAMP = datetime(2026, 4, 1, tzinfo=timezone.utc)


def _load_module_from_path(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_text_for_model_is_json_schema():
    schema = json.loads(schema_text_for_model(CompanyRecord))

    assert schema["type"] == "object"
    assert "name" in schema["properties"]


def test_load_domain_cfg_defaults_data_agents_to_json_mode():
    cfg = load_domain_cfg()

    assert cfg.agent.output_mode == "json"


def test_parse_structured_payload_validates_model():
    payload = """
    ```json
    {"id":"COMP-001","name":"优必选","normalized_name":"优必选","industry":"机器人","profile_summary":"A","evaluation_summary":"B","technology_route_summary":"C","evidence":[{"source_type":"xlsx_import","source_file":"seed.xlsx","fetched_at":"2026-04-01T00:00:00Z"}],"last_updated":"2026-04-01T00:00:00Z"}
    ```
    """

    record = parse_structured_payload(payload, CompanyRecord)

    assert record.id == "COMP-001"
    assert record.display_name == "优必选"


def test_shared_helpers_cover_ids_normalization_evidence_linking_and_publish(tmp_path):
    stable_id = build_stable_id("comp", " 深圳市优必选科技股份有限公司 ")
    assert stable_id.startswith("COMP-")
    assert build_stable_id("comp", "深圳市优必选科技股份有限公司") == stable_id

    assert normalize_company_name("深圳市优必选科技股份有限公司") == "优必选科技"
    assert normalize_person_name(" Ada  Lovelace ") == "AdaLovelace"

    official = build_evidence(
        source_type="official_site",
        source_url="https://example.com",
        fetched_at=TIMESTAMP,
        snippet="Official profile.",
    )
    duplicate_official = build_evidence(
        source_type="official_site",
        source_url="https://example.com",
        fetched_at=TIMESTAMP,
        snippet="Official profile.",
    )
    auxiliary = build_evidence(
        source_type="public_web",
        source_url="https://search.example.com",
        fetched_at=TIMESTAMP,
        snippet="Auxiliary result.",
    )
    merged = merge_evidence([official], [duplicate_official, auxiliary])
    assert merged == [official, auxiliary]

    index = build_normalized_index(
        {"优必选科技股份有限公司": "COMP-001"},
        normalizer=normalize_company_name,
    )
    assert link_normalized_values(
        ["优必选科技股份有限公司", "未知公司", "深圳市优必选科技股份有限公司"],
        index,
        normalizer=normalize_company_name,
    ) == ["COMP-001"]

    ambiguous_index = build_normalized_index(
        {
            "深圳市优必选科技股份有限公司": "COMP-001",
            "优必选科技有限公司": "COMP-002",
        },
        normalizer=normalize_company_name,
    )
    assert (
        link_normalized_values(
            ["深圳市优必选科技股份有限公司"],
            ambiguous_index,
            normalizer=normalize_company_name,
        )
        == []
    )

    record = CompanyRecord(
        id="COMP-001",
        name="优必选科技股份有限公司",
        normalized_name="优必选科技",
        industry="机器人",
        profile_summary="A",
        evaluation_summary="B",
        technology_route_summary="C",
        evidence=[official],
        last_updated=TIMESTAMP,
    )
    path = tmp_path / "company.jsonl"
    publish_jsonl(path, [record])
    assert path.read_text(encoding="utf-8").strip().startswith('{"id":"COMP-001"')


def test_provider_adapters_are_thin_and_configurable(monkeypatch):
    client_calls = []

    def fake_factory(**kwargs):
        client_calls.append(kwargs)
        return kwargs

    mirothinker = MiroThinkerProvider(api_key="token", client_factory=fake_factory)
    qwen = QwenProvider(api_key="token", client_factory=fake_factory)

    miro_request = mirothinker.build_request(
        system_prompt="system",
        user_prompt="hello",
        stream=False,
    )
    qwen_request = qwen.build_request(
        system_prompt="system",
        user_prompt="hello",
        stream=False,
    )

    assert miro_request["model"] == "mirothinker-1.7-235b-fp8"
    assert miro_request["extra_body"]["separate_reasoning"] is True
    assert qwen_request["model"] == "qwen3.5-35b-a3b"
    assert qwen_request["extra_body"]["chat_template_kwargs"]["enable_thinking"] is (
        False
    )

    assert mirothinker.create_client()["api_key"] == "token"
    assert qwen.create_client()["base_url"].endswith("/qwen35/v1")

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeSession:
        def __init__(self):
            self.calls = []

        def post(self, url, json, headers, timeout):
            self.calls.append(
                {
                    "url": url,
                    "json": json,
                    "headers": headers,
                    "timeout": timeout,
                }
            )
            return FakeResponse({"organic": [{"title": "Result"}]})

    monkeypatch.setenv("SERPER_API_KEY", "env-token")
    session = FakeSession()
    search = WebSearchProvider(session=session)
    result = search.search("apple inc")

    assert result["organic"][0]["title"] == "Result"
    assert session.calls[0]["headers"]["X-API-KEY"] == "env-token"


def test_mirothinker_provider_uses_compat_client_helper(monkeypatch):
    from src.data_agents.providers import mirothinker as mirothinker_module

    compat_calls = []

    def fake_build_openai_client(**kwargs):
        compat_calls.append(kwargs)
        return {"client": "compat", **kwargs}

    monkeypatch.setattr(
        mirothinker_module,
        "build_openai_client",
        fake_build_openai_client,
        raising=False,
    )

    provider = MiroThinkerProvider(api_key="token")
    client = provider.create_client()

    assert client["client"] == "compat"
    assert compat_calls == [
        {
            "base_url": "http://star.sustech.edu.cn/service/model/mirothinker/v1",
            "api_key": "token",
            "timeout": 300.0,
        }
    ]


def test_web_search_provider_exposes_example_aligned_request_surface(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "env-token")
    provider = WebSearchProvider()

    assert provider.build_payload("apple inc") == {
        "q": "apple inc",
        "gl": "cn",
        "hl": "zh-cn",
    }
    assert provider.build_headers() == {
        "Content-Type": "application/json",
        "X-API-KEY": "env-token",
    }


@pytest.mark.parametrize(
    ("template_file", "provider_symbol"),
    [
        ("recommended_client_template_mirothinker17_fp8.py", "MiroThinkerProvider"),
        ("recommended_client_template_35b_a3b.py", "QwenProvider"),
    ],
)
def test_recommended_templates_delegate_to_shared_provider_entrypoints(
    monkeypatch, template_file, provider_symbol
):
    repo_root = Path(__file__).resolve().parents[4]
    app_root = repo_root / "apps" / "miroflow-agent"
    monkeypatch.syspath_prepend(str(repo_root))
    monkeypatch.syspath_prepend(str(app_root))

    template_module = _load_module_from_path(
        f"test_{template_file.replace('.', '_')}",
        repo_root / template_file,
    )

    provider_calls = {"init": [], "build_request": [], "create_client": 0}

    class FakeProvider:
        def __init__(self, **kwargs):
            provider_calls["init"].append(kwargs)

        def create_client(self):
            provider_calls["create_client"] += 1
            return {"client": "from-provider"}

        def build_request(self, **kwargs):
            provider_calls["build_request"].append(kwargs)
            return {"request": "from-provider"}

    monkeypatch.setattr(template_module, provider_symbol, FakeProvider, raising=False)

    args = argparse.Namespace(
        base_url="http://example.local/v1",
        api_key="token",
        model="demo-model",
        prompt="hello",
        system="system",
        max_tokens=17,
        temperature=0.2,
        top_p=0.7,
        frequency_penalty=0.3,
        presence_penalty=0.4,
        repetition_penalty=1.2,
        timeout=12.5,
        thinking=True,
        show_reasoning=False,
        stream=False,
    )

    request_kwargs = template_module.build_request_kwargs(args)
    assert request_kwargs == {"request": "from-provider"}
    assert provider_calls["init"][0] == {
        "base_url": "http://example.local/v1",
        "api_key": "token",
        "model": "demo-model",
        "timeout": 12.5,
    }
    assert provider_calls["build_request"][0] == {
        "system_prompt": "system",
        "user_prompt": "hello",
        "stream": False,
        "temperature": 0.2,
        "top_p": 0.7,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.4,
        "max_tokens": 17,
        "repetition_penalty": 1.2,
        "thinking": True,
    }

    args.stream = True
    monkeypatch.setattr(template_module, "parse_args", lambda: args)
    captured = {}

    def fake_run_streaming(client, run_args):
        captured["client"] = client
        captured["args"] = run_args

    monkeypatch.setattr(template_module, "run_streaming", fake_run_streaming)
    template_module.main()

    assert captured["client"] == {"client": "from-provider"}
    assert captured["args"] is args
    assert provider_calls["create_client"] == 1


@pytest.mark.asyncio
async def test_runtime_loads_config_and_executes_structured_task():
    cfg = load_domain_cfg()
    assert cfg.data_agent.providers.mirothinker.model == "mirothinker-1.7-235b-fp8"
    assert cfg.agent.output_mode == "json"

    create_calls = []
    execute_calls = []

    def fake_create_components(_cfg):
        create_calls.append(_cfg)
        return "main-tools", {"sub": "tools"}, "formatter"

    async def fake_execute_task_pipeline(**kwargs):
        execute_calls.append(kwargs)
        return (
            "summary",
            '{"id":"COMP-001","name":"优必选","normalized_name":"优必选","industry":"机器人","profile_summary":"A","evaluation_summary":"B","technology_route_summary":"C","evidence":[{"source_type":"xlsx_import","source_file":"seed.xlsx","fetched_at":"2026-04-01T00:00:00Z"}],"last_updated":"2026-04-01T00:00:00Z"}',
            str(Path(cfg.debug_dir) / "log.json"),
            None,
        )

    record, log_path = await run_structured_task(
        cfg=cfg,
        task_id="company-1",
        task_description="Normalize a company record",
        output_model=CompanyRecord,
        create_components_fn=fake_create_components,
        execute_task_pipeline_fn=fake_execute_task_pipeline,
    )

    assert create_calls == [cfg]
    assert execute_calls[0]["final_output_schema"] == schema_text_for_model(
        CompanyRecord
    )
    assert record.id == "COMP-001"
    assert log_path.endswith("log.json")


@pytest.mark.asyncio
async def test_runtime_surfaces_pipeline_failures_before_schema_validation():
    cfg = load_domain_cfg()

    def fake_create_components(_cfg):
        return "main-tools", {"sub": "tools"}, "formatter"

    async def fake_execute_task_pipeline(**kwargs):
        return (
            "Error executing task company-1:\nmodel backend unavailable",
            "",
            str(Path(cfg.debug_dir) / "failed-log.json"),
            None,
        )

    with pytest.raises(RuntimeError, match="Error executing task company-1"):
        await run_structured_task(
            cfg=cfg,
            task_id="company-1",
            task_description="Normalize a company record",
            output_model=CompanyRecord,
            create_components_fn=fake_create_components,
            execute_task_pipeline_fn=fake_execute_task_pipeline,
        )
