# Code Tutorial - Progress Tracker
> Total: 89 source Python files + 36 YAML config files to document
> Created: 2026-03-16

## Progress Overview
| Module | Files | Completed | Status |
|--------|-------|-----------|--------|
| apps/miroflow-agent/src/core | 5 | 0 | ⏳ Pending |
| apps/miroflow-agent/src/config | 1 | 0 | ⏳ Pending |
| apps/miroflow-agent/src/io | 2 | 0 | ⏳ Pending |
| apps/miroflow-agent/src/llm | 5 | 0 | ⏳ Pending |
| apps/miroflow-agent/src/logging | 2 | 0 | ⏳ Pending |
| apps/miroflow-agent/src/utils | 3 | 0 | ⏳ Pending |
| apps/miroflow-agent/main.py | 1 | 0 | ⏳ Pending |
| apps/miroflow-agent/conf | 36 | 0 | ⏳ Pending |
| apps/miroflow-agent/benchmarks | 18 | 0 | ⏳ Pending |
| libs/miroflow-tools | 19 | 0 | ⏳ Pending |
| apps/collect-trace | 8 | 0 | ⏳ Pending |
| apps/gradio-demo | 3 | 0 | ⏳ Pending |
| apps/visualize-trace | 5 | 0 | ⏳ Pending |
| apps/lobehub-compatibility | 3 | 0 | ⏳ Pending |

## File List by Module

### apps/miroflow-agent/src/core/
- [ ] `src/core/orchestrator.py` → `tutorial/apps/miroflow-agent/src/core/orchestrator.md`
- [ ] `src/core/pipeline.py` → `tutorial/apps/miroflow-agent/src/core/pipeline.md`
- [ ] `src/core/tool_executor.py` → `tutorial/apps/miroflow-agent/src/core/tool_executor.md`
- [ ] `src/core/answer_generator.py` → `tutorial/apps/miroflow-agent/src/core/answer_generator.md`
- [ ] `src/core/stream_handler.py` → `tutorial/apps/miroflow-agent/src/core/stream_handler.md`

### apps/miroflow-agent/src/config/
- [ ] `src/config/settings.py` → `tutorial/apps/miroflow-agent/src/config/settings.md`

### apps/miroflow-agent/src/io/
- [ ] `src/io/input_handler.py` → `tutorial/apps/miroflow-agent/src/io/input_handler.md`
- [ ] `src/io/output_formatter.py` → `tutorial/apps/miroflow-agent/src/io/output_formatter.md`

### apps/miroflow-agent/src/llm/
- [ ] `src/llm/base_client.py` → `tutorial/apps/miroflow-agent/src/llm/base_client.md`
- [ ] `src/llm/factory.py` → `tutorial/apps/miroflow-agent/src/llm/factory.md`
- [ ] `src/llm/util.py` → `tutorial/apps/miroflow-agent/src/llm/util.md`
- [ ] `src/llm/providers/anthropic_client.py` → `tutorial/apps/miroflow-agent/src/llm/providers/anthropic_client.md`
- [ ] `src/llm/providers/openai_client.py` → `tutorial/apps/miroflow-agent/src/llm/providers/openai_client.md`

### apps/miroflow-agent/src/logging/
- [ ] `src/logging/task_logger.py` → `tutorial/apps/miroflow-agent/src/logging/task_logger.md`
- [ ] `src/logging/summary_time_cost.py` → `tutorial/apps/miroflow-agent/src/logging/summary_time_cost.md`

### apps/miroflow-agent/src/utils/
- [ ] `src/utils/parsing_utils.py` → `tutorial/apps/miroflow-agent/src/utils/parsing_utils.md`
- [ ] `src/utils/prompt_utils.py` → `tutorial/apps/miroflow-agent/src/utils/prompt_utils.md`
- [ ] `src/utils/wrapper_utils.py` → `tutorial/apps/miroflow-agent/src/utils/wrapper_utils.md`

### apps/miroflow-agent/main.py
- [ ] `main.py` → `tutorial/apps/miroflow-agent/main.md`

### apps/miroflow-agent/conf/
- [ ] `conf/config.yaml` → `tutorial/apps/miroflow-agent/conf/config.md`
- [ ] `conf/agent/*.yaml` (13 files) → `tutorial/apps/miroflow-agent/conf/agent/index.md`
- [ ] `conf/benchmark/*.yaml` (14+ files) → `tutorial/apps/miroflow-agent/conf/benchmark/index.md`
- [ ] `conf/llm/*.yaml` (4 files) → `tutorial/apps/miroflow-agent/conf/llm/index.md`

### apps/miroflow-agent/benchmarks/
- [ ] `benchmarks/common_benchmark.py` → `tutorial/apps/miroflow-agent/benchmarks/common_benchmark.md`
- [ ] `benchmarks/check_progress/common.py` → `tutorial/apps/miroflow-agent/benchmarks/check_progress/common.md`
- [ ] `benchmarks/check_progress/*.py` (12 checkers) → `tutorial/apps/miroflow-agent/benchmarks/check_progress/index.md`
- [ ] `benchmarks/evaluators/*.py` (3 files) → `tutorial/apps/miroflow-agent/benchmarks/evaluators/index.md`
- [ ] `benchmarks/subset_extraction/*.py` (2 files) → `tutorial/apps/miroflow-agent/benchmarks/subset_extraction/index.md`

### libs/miroflow-tools/
- [ ] `src/miroflow_tools/manager.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/manager.md`
- [ ] `src/miroflow_tools/mcp_servers/audio_mcp_server.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/mcp_servers/audio_mcp_server.md`
- [ ] `src/miroflow_tools/mcp_servers/audio_mcp_server_os.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/mcp_servers/audio_mcp_server_os.md`
- [ ] `src/miroflow_tools/mcp_servers/browser_session.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/mcp_servers/browser_session.md`
- [ ] `src/miroflow_tools/mcp_servers/python_mcp_server.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/mcp_servers/python_mcp_server.md`
- [ ] `src/miroflow_tools/mcp_servers/reading_mcp_server.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/mcp_servers/reading_mcp_server.md`
- [ ] `src/miroflow_tools/mcp_servers/reasoning_mcp_server.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/mcp_servers/reasoning_mcp_server.md`
- [ ] `src/miroflow_tools/mcp_servers/reasoning_mcp_server_os.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/mcp_servers/reasoning_mcp_server_os.md`
- [ ] `src/miroflow_tools/mcp_servers/searching_google_mcp_server.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/mcp_servers/searching_google_mcp_server.md`
- [ ] `src/miroflow_tools/mcp_servers/searching_sogou_mcp_server.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/mcp_servers/searching_sogou_mcp_server.md`
- [ ] `src/miroflow_tools/mcp_servers/serper_mcp_server.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/mcp_servers/serper_mcp_server.md`
- [ ] `src/miroflow_tools/mcp_servers/vision_mcp_server.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/mcp_servers/vision_mcp_server.md`
- [ ] `src/miroflow_tools/mcp_servers/vision_mcp_server_os.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/mcp_servers/vision_mcp_server_os.md`
- [ ] `src/miroflow_tools/mcp_servers/utils/url_unquote.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/mcp_servers/utils/url_unquote.md`
- [ ] `src/miroflow_tools/dev_mcp_servers/jina_scrape_llm_summary.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/jina_scrape_llm_summary.md`
- [ ] `src/miroflow_tools/dev_mcp_servers/search_and_scrape_webpage.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/search_and_scrape_webpage.md`
- [ ] `src/miroflow_tools/dev_mcp_servers/stateless_python_server.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/stateless_python_server.md`
- [ ] `src/miroflow_tools/dev_mcp_servers/task_planner.py` → `tutorial/libs/miroflow-tools/src/miroflow_tools/dev_mcp_servers/task_planner.md`

### apps/collect-trace/
- [ ] `utils/converters/convert_non_oai_to_chatml.py` → `tutorial/apps/collect-trace/utils/converters/convert_non_oai_to_chatml.md`
- [ ] `utils/converters/convert_oai_to_chatml.py` → `tutorial/apps/collect-trace/utils/converters/convert_oai_to_chatml.md`
- [ ] `utils/converters/convert_to_chatml_auto_batch.py` → `tutorial/apps/collect-trace/utils/converters/convert_to_chatml_auto_batch.md`
- [ ] `utils/converters/example_usage.py` → `tutorial/apps/collect-trace/utils/converters/example_usage.md`
- [ ] `utils/converters/system_prompts.py` → `tutorial/apps/collect-trace/utils/converters/system_prompts.md`
- [ ] `utils/merge_chatml_msgs_to_one_json.py` → `tutorial/apps/collect-trace/utils/merge_chatml_msgs_to_one_json.md`
- [ ] `utils/process_logs.py` → `tutorial/apps/collect-trace/utils/process_logs.md`

### apps/gradio-demo/
- [ ] `main.py` → `tutorial/apps/gradio-demo/main.md`
- [ ] `prompt_patch.py` → `tutorial/apps/gradio-demo/prompt_patch.md`
- [ ] `utils.py` → `tutorial/apps/gradio-demo/utils.md`

### apps/visualize-trace/
- [ ] `app.py` → `tutorial/apps/visualize-trace/app.md`
- [ ] `run.py` → `tutorial/apps/visualize-trace/run.md`
- [ ] `trace_analyzer.py` → `tutorial/apps/visualize-trace/trace_analyzer.md`
- [ ] `static/js/script.js` → `tutorial/apps/visualize-trace/static/js/script.md`
- [ ] `templates/index.html` → `tutorial/apps/visualize-trace/templates/index.md`

### apps/lobehub-compatibility/
- [ ] `MiroThinkerToolParser.py` → `tutorial/apps/lobehub-compatibility/MiroThinkerToolParser.md`
- [ ] `test_tool_parser.py` → `tutorial/apps/lobehub-compatibility/test_tool_parser.md`
- [ ] `unit_test.py` → `tutorial/apps/lobehub-compatibility/unit_test.md`
