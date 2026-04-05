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


def test_generate_agent_summarize_prompt_defaults_to_boxed_mode():
    prompt = generate_agent_summarize_prompt(
        task_description="Return the best answer",
        agent_type="main",
    )

    assert "Wrap your final answer in \\boxed{}." in prompt


def test_output_formatter_extracts_json_payload():
    formatter = OutputFormatter()
    _, payload, _ = formatter.format_final_summary_and_log(
        '<think>ignore</think>\n{"object_type":"company","name":"优必选"}',
        output_mode="json",
    )

    assert payload == '{"name":"优必选","object_type":"company"}'
