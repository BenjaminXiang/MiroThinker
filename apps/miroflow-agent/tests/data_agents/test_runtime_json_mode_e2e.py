import copy

import pytest
from omegaconf import OmegaConf

from src.core.orchestrator import Orchestrator
from src.io.output_formatter import OutputFormatter
from src.logging.task_logger import TaskLog, get_utc_plus_8_time


class FakeToolManager:
    async def get_all_tool_definitions(self):
        return []


class FakeLLMClient:
    def __init__(self, scripted_responses):
        self.scripted_responses = scripted_responses
        self.calls = []
        self.last_call_tokens = {"prompt_tokens": 0, "completion_tokens": 0}
        self.task_log = None

    def generate_agent_system_prompt(self, date, mcp_servers):
        return "system\n"

    async def create_message(
        self,
        system_prompt,
        message_history,
        tool_definitions,
        keep_tool_result=-1,
        step_id=1,
        task_log=None,
        agent_type="main",
    ):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "message_history": copy.deepcopy(message_history),
                "tool_definitions": copy.deepcopy(tool_definitions),
                "step_id": step_id,
                "agent_type": agent_type,
            }
        )
        call_index = len(self.calls) - 1
        if call_index >= len(self.scripted_responses):
            raise AssertionError(f"Unexpected LLM call index: {call_index}")
        return self.scripted_responses[call_index], copy.deepcopy(message_history)

    def process_llm_response(self, response, message_history, agent_type):
        text = response["text"]
        should_break = response.get("should_break", False)
        updated_history = copy.deepcopy(message_history)
        updated_history.append({"role": "assistant", "content": text})
        return text, should_break, updated_history

    def extract_tool_calls_info(self, response, assistant_response_text):
        return response.get("tool_calls", [])

    def update_message_history(self, message_history, all_tool_results_content_with_id):
        return copy.deepcopy(message_history)

    def ensure_summary_context(self, message_history, temp_summary_prompt):
        return True, copy.deepcopy(message_history)


def _build_cfg(output_mode="json"):
    return OmegaConf.create(
        {
            "agent": {
                "output_mode": output_mode,
                "keep_tool_result": -1,
                "context_compress_limit": 0,
                "retry_with_summary": True,
                "main_agent": {"max_turns": 2},
                "sub_agents": None,
            }
        }
    )


def _build_task_log(tmp_path):
    return TaskLog(
        task_id="runtime-json-mode-test",
        start_time=get_utc_plus_8_time(),
        input={"task_description": "stub", "task_file_name": ""},
        log_dir=str(tmp_path / "logs"),
    )


@pytest.mark.asyncio
async def test_runtime_json_mode_extracts_payload_and_canonicalizes_schema(tmp_path):
    llm_client = FakeLLMClient(
        scripted_responses=[
            {
                "text": "I already have enough information to answer.",
                "should_break": True,
                "tool_calls": [],
            },
            {
                "text": '<think>internal</think>\n{"object_type":"company","name":"优必选"}',
                "should_break": True,
                "tool_calls": [],
            },
        ]
    )
    schema = (
        '{"required":["name"],"type":"object","properties":{"name":{"type":"string"}}}'
    )

    orchestrator = Orchestrator(
        main_agent_tool_manager=FakeToolManager(),
        sub_agent_tool_managers={},
        llm_client=llm_client,
        output_formatter=OutputFormatter(),
        cfg=_build_cfg("json"),
        task_log=_build_task_log(tmp_path),
        final_output_schema=schema,
    )

    _, final_payload, _ = await orchestrator.run_main_agent(
        task_description="Normalize this company record",
        task_file_name="",
        task_id="json-e2e",
    )

    assert final_payload == '{"name":"优必选","object_type":"company"}'
    assert len(llm_client.calls) == 2

    first_call_user_prompt = llm_client.calls[0]["message_history"][0]["content"]
    assert "\\boxed{}" not in first_call_user_prompt

    summary_prompt = llm_client.calls[1]["message_history"][-1]["content"]
    assert (
        'JSON schema:\n{"properties":{"name":{"type":"string"}},"required":["name"],"type":"object"}'
        in summary_prompt
    )


def test_runtime_json_mode_rejects_invalid_final_output_schema(tmp_path):
    with pytest.raises(ValueError, match="final_output_schema"):
        Orchestrator(
            main_agent_tool_manager=FakeToolManager(),
            sub_agent_tool_managers={},
            llm_client=FakeLLMClient(scripted_responses=[]),
            output_formatter=OutputFormatter(),
            cfg=_build_cfg("json"),
            task_log=_build_task_log(tmp_path),
            final_output_schema='{"type":"object"',
        )
